"""Just Trim: a local, portable Windows MOV trimmer."""
from __future__ import annotations
import bisect
import json
import os
from pathlib import Path
import sys
import threading
import traceback

# Qt's bundled FFmpeg backend supplies HEVC playback without a Store codec pack.
os.environ.setdefault('QT_MEDIA_BACKEND', 'ffmpeg')
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPalette, QKeySequence, QShortcut, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QLineEdit, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QProgressBar, QSlider,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from movcut import Movie, MovieError, Cancelled, format_time, parse_time
from drop_support import MovieDropHandler


class Task(QThread):
    result = Signal(object)
    failure = Signal(str)
    progress = Signal(int, str)

    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.cancel = threading.Event()

    def run(self):
        try:
            self.result.emit(self.action(self))
        except Exception as e:
            self.failure.emit(str(e) or type(e).__name__)


class Timeline(QWidget):
    seek = Signal(float)
    changed = Signal(float, float)

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(70)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName('Video timeline. Drag the blue start and end handles, or click to seek.')
        self.duration = 1.0
        self.view_start = 0.0
        self.view_end = 1.0
        self.start = self.end = self.position = 0.0
        self.dragging = None
        self.keys = []

    def x(self, t):
        return 18+(self.width()-36)*(t-self.view_start)/max(self.view_end-self.view_start, 0.001)

    def time(self, x):
        return max(self.view_start, min(self.view_end, self.view_start+(x-18)/max(1,self.width()-36)*(self.view_end-self.view_start)))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = 24
        p.fillRect(QRectF(18, y, self.width()-36, 18), QColor('#d8dde3'))
        a,b=max(self.view_start,self.start),min(self.view_end,self.end)
        if b>a:
            p.fillRect(QRectF(self.x(a), y, max(1,self.x(b)-self.x(a)), 18), QColor('#9bc8f1'))
        p.setPen(QPen(QColor('#8b959f'), 1))
        visible = [k for k in self.keys if self.view_start <= k <= self.view_end]
        stride = max(1, len(visible)//150)
        for k in visible[::stride]:
            x = self.x(k)
            p.drawLine(QPointF(x,y+13),QPointF(x,y+18))
        for t, label in [(self.start,'IN'), (self.end,'OUT')]:
            if not self.view_start <= t <= self.view_end:
                continue
            x = self.x(t)
            p.fillRect(QRectF(x-4,y-6,8,30), QColor('#1769aa'))
            p.setPen(QColor('#174e7d'))
            p.drawText(QRectF(max(0,min(self.width()-40,x-20)),1,40,20), Qt.AlignmentFlag.AlignCenter, label)
        x = self.x(self.position)
        p.setPen(QPen(QColor('#c23430'), 2))
        if self.view_start <= self.position <= self.view_end:
            p.drawLine(QPointF(x,y-1),QPointF(x,y+24))
        p.setPen(self.palette().text().color())
        p.drawText(QRectF(18,48,130,18), format_time(self.view_start))
        p.drawText(QRectF(self.width()-155,48,137,18), Qt.AlignmentFlag.AlignRight, format_time(self.view_end))

    def mousePressEvent(self, e):
        if not self.isEnabled():
            return
        x = e.position().x()
        if abs(x-self.x(self.start)) < 12:
            self.dragging = 'start'
        elif abs(x-self.x(self.end)) < 12:
            self.dragging = 'end'
        else:
            self.dragging = 'seek'
        self.mouseMoveEvent(e)

    def mouseMoveEvent(self, e):
        if not self.dragging:
            return
        t = self.time(e.position().x())
        if self.dragging == 'start':
            self.start = min(t, self.end-0.001)
            self.changed.emit(max(0,self.start), self.end)
            self.seek.emit(max(0,self.start))
        elif self.dragging == 'end':
            self.end = max(t, self.start+0.001)
            self.changed.emit(self.start, min(self.duration,self.end))
            self.seek.emit(min(self.duration,self.end))
        else:
            self.seek.emit(t)
        self.update()

    def mouseReleaseEvent(self, e):
        self.dragging = None


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Just Trim — lossless MOV clips')
        self.resize(1050, 830)
        self.setMinimumSize(800, 690)
        self.setAcceptDrops(True)
        self.movie = None
        self.task = None
        self.busy = False
        self.output_folder = None
        self.ranges = []
        self.preview_end = None
        self.requested = (0.0, 0.0)
        self.zoomed = False
        self.last_results = []
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)
        top = QHBoxLayout()
        self.open_button = QPushButton('Open MOV…')
        self.open_button.setObjectName('openButton')
        self.open_button.clicked.connect(self.choose_file)
        self.filename = QLabel('Drop a MOV video here, or click Open MOV.')
        self.filename.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top.addWidget(self.open_button)
        top.addWidget(self.filename, 1)
        layout.addLayout(top)
        self.drop_hint = QLabel()
        self.drop_hint.setObjectName('dropHint')
        self.drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.drop_hint)
        self.info = QLabel('Local files only • Original never overwritten • No re-encoding')
        layout.addWidget(self.info)
        self.video = QVideoWidget()
        self.video.setMinimumHeight(180)
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.video.setStyleSheet('background: #111;')
        layout.addWidget(self.video, 1)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.7)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.positionChanged.connect(self.position_changed)
        self.player.playbackStateChanged.connect(self.playback_changed)
        self.player.errorOccurred.connect(self.playback_error)
        self.player.mediaStatusChanged.connect(self.media_status)
        transport = QHBoxLayout()
        self.play_button = QPushButton('Play  [Space]')
        self.play_button.clicked.connect(self.toggle_play)
        transport.addWidget(self.play_button)
        self.back = QPushButton('◀ Keyframe')
        self.back.clicked.connect(lambda:self.key_seek(-1))
        self.forward = QPushButton('Keyframe ▶')
        self.forward.clicked.connect(lambda:self.key_seek(1))
        transport.addWidget(self.back)
        transport.addWidget(self.forward)
        self.position_label = QLabel('00:00:00.000 / 00:00:00.000')
        transport.addWidget(self.position_label, 1)
        transport.addWidget(QLabel('Volume'))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0,100)
        self.volume.setValue(70)
        self.volume.setMaximumWidth(100)
        self.volume.valueChanged.connect(lambda v:self.audio.setVolume(v/100))
        transport.addWidget(self.volume)
        layout.addLayout(transport)
        self.timeline = Timeline()
        self.timeline.seek.connect(self.seek)
        self.timeline.changed.connect(self.set_range)
        layout.addWidget(self.timeline)
        fields = QHBoxLayout()
        self.in_button = QPushButton('Set start  [I]')
        self.in_button.clicked.connect(self.mark_in)
        self.out_button = QPushButton('Set end  [O]')
        self.out_button.clicked.connect(self.mark_out)
        self.start_edit = QLineEdit('00:00:00.000')
        self.start_edit.setObjectName('startTime')
        self.end_edit = QLineEdit('00:00:00.000')
        self.end_edit.setObjectName('endTime')
        for w in (self.start_edit, self.end_edit):
            w.setMaximumWidth(135)
            w.setPlaceholderText('HH:MM:SS.mmm')
            w.editingFinished.connect(self.read_range)
        fields.addWidget(self.in_button)
        fields.addWidget(self.start_edit)
        fields.addWidget(self.out_button)
        fields.addWidget(self.end_edit)
        self.preview_button = QPushButton('Play range')
        self.preview_button.clicked.connect(self.play_range)
        fields.addWidget(self.preview_button)
        self.add_button = QPushButton('Add clip  [A]')
        self.add_button.setObjectName('addClipButton')
        self.add_button.clicked.connect(self.add_clip)
        fields.addWidget(self.add_button)
        self.zoom_button = QPushButton('Zoom range')
        self.zoom_button.clicked.connect(self.toggle_zoom)
        fields.addWidget(self.zoom_button)
        fields.addStretch()
        layout.addLayout(fields)
        self.actual = QLabel('Select a start and end, then add a clip. Repeat for more clips.')
        self.actual.setWordWrap(True)
        layout.addWidget(self.actual)
        self.note = QLabel('Cuts expand to surrounding keyframes to keep the original quality. Actual export times appear above.\n'
                           'Drag the blue handles, type times, or use I / O. Arrow keys: ±1 frame; Ctrl+arrows: ±1 second.')
        self.note.setWordWrap(True)
        self.note.setStyleSheet('color: #555; font-size: 11px;')
        layout.addWidget(self.note)
        self.table = QTableWidget(0, 4)
        self.table.setObjectName('clipsTable')
        self.table.setHorizontalHeaderLabels(['Export', 'Start', 'End', 'Length'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMaximumHeight(160)
        self.table.setMinimumHeight(100)
        self.table.cellDoubleClicked.connect(lambda row,col:self.load_row(row))
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        self.remove_button = QPushButton('Remove selected')
        self.remove_button.clicked.connect(self.remove_selected)
        actions.addWidget(self.remove_button)
        actions.addStretch()
        self.folder_button = QPushButton('Open output folder')
        self.folder_button.setEnabled(False)
        self.folder_button.clicked.connect(self.open_output)
        actions.addWidget(self.folder_button)
        self.export_button = QPushButton('Export MOV clips…')
        self.export_button.setObjectName('exportButton')
        self.export_button.clicked.connect(self.choose_export)
        self.export_button.setStyleSheet('font-weight: 600; padding: 7px 16px;')
        actions.addWidget(self.export_button)
        self.cancel_button = QPushButton('Cancel export')
        self.cancel_button.clicked.connect(self.cancel_task)
        self.cancel_button.hide()
        actions.addWidget(self.cancel_button)
        layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel('Ready. Nothing is uploaded.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.controls = [self.play_button,self.back,self.forward,self.timeline,self.in_button,
                         self.out_button,self.start_edit,self.end_edit,self.preview_button,
                         self.add_button,self.zoom_button,self.table,self.remove_button,self.export_button]
        self.enable_controls()
        for keys, fn in [('Space',self.toggle_play),('I',self.mark_in),('O',self.mark_out),
                         ('A',self.add_clip),('Left',lambda:self.step(-1)),('Right',lambda:self.step(1)),
                         ('Ctrl+Left',lambda:self.seek(self.player.position()/1000-1)),
                         ('Ctrl+Right',lambda:self.seek(self.player.position()/1000+1))]:
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(lambda f=fn:self.shortcut(f))
        QShortcut(QKeySequence('Ctrl+O'),self).activated.connect(self.choose_file)
        self.file_drops = MovieDropHandler(self, self.drop_hint)

    def shortcut(self, fn):
        if not isinstance(QApplication.focusWidget(), QLineEdit) and not self.busy:
            fn()

    def enable_controls(self):
        for w in self.controls:
            w.setEnabled(self.movie is not None and not self.busy)
        self.open_button.setEnabled(not self.busy)

    def start_task(self, action, success, exporting=False):
        if self.busy:
            return
        self.busy = True
        self.enable_controls()
        self.progress.setRange(0,100 if exporting else 0)
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_button.setVisible(exporting)
        self.task = Task(action, self)
        self.task.result.connect(success)
        self.task.failure.connect(self.task_failed)
        self.task.progress.connect(self.task_progress)
        self.task.finished.connect(self.task_finished)
        self.task.start()

    def task_progress(self, value, text):
        self.progress.setValue(value)
        self.status.setText(text)

    def task_failed(self, message):
        self.status.setText(message)
        if 'cancelled' not in message.lower():
            QMessageBox.warning(self, 'Could not complete', message)

    def task_finished(self):
        self.busy = False
        self.enable_controls()
        self.progress.hide()
        self.cancel_button.hide()
        self.task.deleteLater()
        self.task = None

    def cancel_task(self):
        if self.task:
            self.task.cancel.set()
            self.status.setText('Cancelling… completed clips are kept; incomplete output is removed.')

    def choose_file(self):
        if self.busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Open a MOV video', '', 'MOV videos (*.mov *.MOV)')
        if path:
            self.open_path(path)

    def open_path(self, path):
        if self.busy:
            return
        if Path(path).suffix.lower() != '.mov':
            QMessageBox.information(self, 'MOV videos only', 'Choose a .mov video file.')
            return
        if self.ranges:
            choice = QMessageBox.question(self, 'Open another video?', 'Clear the current clip list and open another video?')
            if choice != QMessageBox.StandardButton.Yes:
                return
        self.player.stop()
        self.status.setText('Reading the MOV index…')
        self.start_task(lambda task:Movie(path), self.loaded)

    def loaded(self, movie):
        self.movie = movie
        self.ranges = []
        self.table.setRowCount(0)
        self.filename.setText(movie.path.name)
        self.filename.setToolTip(str(movie.path))
        self.info.setText(f'{format_time(movie.duration)}  •  {movie.identity[0]/1024**3:.2f} GB  •  '
                          f'{movie.video.codec.upper()}  •  All {len(movie.tracks)} tracks retained')
        self.timeline.duration = float(movie.duration)
        self.timeline.view_start = 0
        self.timeline.view_end = float(movie.duration)
        self.zoomed = False
        self.zoom_button.setText('Zoom range')
        self.timeline.keys = movie.key_times
        self.set_range(0, min(10,float(movie.duration)))
        self.position_changed(0)
        self.player.setSource(QUrl.fromLocalFile(str(movie.path)))
        self.player.pause()
        self.status.setText('Ready. Choose your clip ranges. The original file stays untouched.')

    def media_status(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            if self.player.audioTracks() and self.player.activeAudioTrack() != 0:
                self.player.setActiveAudioTrack(0)

    def playback_error(self, error, message):
        self.status.setText('Preview error: '+message+'. Export uses the original data independently of preview.')

    def playback_changed(self, state):
        self.play_button.setText('Pause  [Space]' if state == QMediaPlayer.PlaybackState.PlayingState else 'Play  [Space]')

    def position_changed(self, ms):
        t = ms/1000
        self.timeline.position = t
        self.timeline.update()
        if self.movie:
            self.position_label.setText(f'{format_time(t)} / {format_time(self.movie.duration)}')
        if self.preview_end is not None and t >= self.preview_end:
            self.player.pause()
            self.preview_end = None

    def seek(self, seconds):
        if not self.movie or self.busy:
            return
        self.preview_end = None
        self.player.setPosition(round(max(0,min(float(self.movie.duration),seconds))*1000))

    def step(self, direction):
        if self.movie:
            self.player.pause()
            fps = self.movie.video.count/float(self.movie.duration)
            self.seek(self.player.position()/1000+direction/fps)

    def key_seek(self, direction):
        if not self.movie:
            return
        t = self.player.position()/1000
        keys = self.movie.boundaries
        i = bisect.bisect_right(keys,t+0.002) if direction > 0 else bisect.bisect_left(keys,t-0.002)-1
        self.player.pause()
        self.seek(keys[max(0,min(len(keys)-1,i))])

    def toggle_play(self):
        if not self.movie or self.busy:
            return
        self.preview_end = None
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def mark_in(self):
        if self.movie and not self.busy:
            t = min(self.player.position()/1000,float(self.movie.duration)-0.001)
            end = self.requested[1] if self.requested[1] > t else min(float(self.movie.duration),t+1)
            self.set_range(t,end)

    def mark_out(self):
        if self.movie and not self.busy:
            t = max(0.001,self.player.position()/1000)
            start = self.requested[0] if self.requested[0] < t else max(0,t-1)
            self.set_range(start,t)

    def set_range(self, start, end):
        if not self.movie:
            return
        self.requested = (start,end)
        self.start_edit.setText(format_time(start))
        self.end_edit.setText(format_time(end))
        self.timeline.start, self.timeline.end = start,end
        self.timeline.update()
        self.update_actual()

    def toggle_zoom(self):
        if not self.movie or not self.read_range():
            return
        self.zoomed = not self.zoomed
        if self.zoomed:
            a,b = self.requested
            pad = max(2,(b-a)*0.2)
            self.timeline.view_start = max(0,a-pad)
            self.timeline.view_end = min(float(self.movie.duration),b+pad)
        else:
            self.timeline.view_start = 0
            self.timeline.view_end = float(self.movie.duration)
        self.zoom_button.setText('Full timeline' if self.zoomed else 'Zoom range')
        self.timeline.update()

    def read_range(self):
        if not self.movie:
            return False
        try:
            a,b = parse_time(self.start_edit.text()),parse_time(self.end_edit.text())
            self.movie.snap(a,b)
            self.requested = (a,b)
            self.timeline.start,self.timeline.end = a,min(b,float(self.movie.duration))
            self.timeline.update()
            self.update_actual()
            return True
        except MovieError as e:
            self.actual.setText(str(e))
            return False

    def update_actual(self):
        try:
            a,b = self.movie.snap(*self.requested)
            self.actual.setText(f'Actual export: {format_time(a)} → {format_time(b)}   |   Length: {format_time(b-a)}')
        except MovieError as e:
            self.actual.setText(str(e))

    def play_range(self):
        if self.movie and not self.busy and self.read_range():
            a,b = self.movie.snap(*self.requested)
            self.seek(float(a))
            self.preview_end = float(b)
            self.player.play()

    def add_clip(self):
        if not self.movie or self.busy or not self.read_range():
            return
        a,b = self.movie.snap(*self.requested)
        self.ranges.append((float(a),float(b)))
        row = self.table.rowCount()
        self.table.insertRow(row)
        check = QTableWidgetItem(f'Clip {row+1}')
        check.setFlags(check.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        check.setCheckState(Qt.CheckState.Checked)
        self.table.setItem(row,0,check)
        for col,value in enumerate([a,b,b-a],1):
            self.table.setItem(row,col,QTableWidgetItem(format_time(value)))
        self.table.selectRow(row)
        self.status.setText(f'{len(self.ranges)} clip(s) ready. Add more ranges or export the checked clips.')

    def load_row(self, row):
        if 0 <= row < len(self.ranges):
            self.set_range(*self.ranges[row])
            self.seek(self.ranges[row][0])

    def remove_selected(self):
        for row in sorted({i.row() for i in self.table.selectedIndexes()},reverse=True):
            self.table.removeRow(row)
            self.ranges.pop(row)
        for row in range(len(self.ranges)):
            self.table.item(row,0).setText(f'Clip {row+1}')

    def choose_export(self):
        if not self.movie or self.busy:
            return
        if not self.ranges:
            self.add_clip()
        selected = [(i,a,b) for i,(a,b) in enumerate(self.ranges)
                    if self.table.item(i,0).checkState() == Qt.CheckState.Checked]
        if not selected:
            self.status.setText('Check at least one clip to export.')
            return
        folder = QFileDialog.getExistingDirectory(self,'Choose where to save your MOV clips',
                                                  str(self.output_folder or self.movie.path.parent))
        if folder:
            self.export_to(Path(folder),selected)

    def export_to(self, folder, selected):
        self.player.pause()
        self.output_folder = Path(folder)
        self.last_results = []
        self.folder_button.setEnabled(True)
        movie = self.movie
        def action(task):
            results = []
            for number,(row,a,b) in enumerate(selected,1):
                if task.cancel.is_set():
                    raise Cancelled(f'Export cancelled. {len(results)} completed clip(s) kept. Original unchanged.')
                stamp = format_time(a).replace(':','-').replace('.','-')
                stem = f'{movie.path.stem[:100]}_clip_{row+1:03}_{stamp}'
                path = self.output_folder/(stem+'.mov')
                n = 2
                while path.exists():
                    path = self.output_folder/(stem+f'_{n}.mov')
                    n += 1
                last = -1
                def report(p,text):
                    nonlocal last
                    overall = int(((number-1)+p/100)/len(selected)*100)
                    if overall != last:
                        task.progress.emit(overall,f'Clip {number}/{len(selected)} — {text}')
                        last = overall
                result = movie.export(a,b,path,report,task.cancel.is_set)
                results.append(result)
                self.last_results = results[:]
            return results
        self.start_task(action,self.exported,True)

    def exported(self, results):
        self.status.setText(f'Exported and byte-verified {len(results)} MOV clip(s) to {self.output_folder}. Original unchanged.')

    def open_output(self):
        if self.output_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_folder)))

    def closeEvent(self, e):
        if self.busy:
            self.status.setText('Wait for the operation to finish, or cancel the export before closing.')
            e.ignore()
        else:
            self.player.stop()
            e.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Just Trim')
    app.setOrganizationName('Shardul Narvekar')
    app.setApplicationVersion('1.1.2')
    app.setStyle('Fusion')
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,QColor('#f5f5f5'))
    palette.setColor(QPalette.ColorRole.WindowText,QColor('#202020'))
    palette.setColor(QPalette.ColorRole.Base,QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.AlternateBase,QColor('#edf2f7'))
    palette.setColor(QPalette.ColorRole.Text,QColor('#202020'))
    palette.setColor(QPalette.ColorRole.Button,QColor('#eeeeee'))
    palette.setColor(QPalette.ColorRole.ButtonText,QColor('#202020'))
    palette.setColor(QPalette.ColorRole.Highlight,QColor('#1769aa'))
    palette.setColor(QPalette.ColorRole.HighlightedText,QColor('#ffffff'))
    palette.setColor(QPalette.ColorGroup.Disabled,QPalette.ColorRole.ButtonText,QColor('#888888'))
    palette.setColor(QPalette.ColorRole.ToolTipBase,QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.ToolTipText,QColor('#202020'))
    app.setPalette(palette)
    # Keep ordinary Windows controls readable regardless of the system's dark theme.
    app.setStyleSheet('QWidget { font-family: "Segoe UI"; font-size: 12px; } '
                     'QPushButton { padding: 5px 9px; } QLineEdit { padding: 5px; }')
    w = Window()
    w.show()
    if len(sys.argv) == 5 and sys.argv[1] == '--self-test':
        from selfcheck import run_check
        run_check(app, w, *sys.argv[2:])
    elif len(sys.argv) > 1:
        QTimer.singleShot(100,lambda:w.open_path(sys.argv[1]))
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
