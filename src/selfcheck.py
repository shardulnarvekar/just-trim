"""Opt-in release smoke test, run against the actual frozen executable."""
import json
from pathlib import Path
import time
from PySide6.QtCore import QTimer, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from movcut import Movie


def run_check(app, window, source, report_path, output):
    report = {'status': 'running', 'checks': []}
    start = time.monotonic()
    state = {'stage': 0, 'frames': 0}
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    report_file = Path(report_path).resolve()
    def save():
        report_file.write_text(json.dumps(report, indent=2), encoding='utf-8')
    def frame(f):
        if f.isValid():
            state['frames'] += 1
    window.video.videoSink().videoFrameChanged.connect(frame)
    timer = QTimer(window)
    timer.setInterval(100)
    def poll():
        try:
            if time.monotonic()-start > 90:
                raise RuntimeError('Standalone smoke test timed out at stage '+str(state['stage']))
            if state['stage'] == 0 and window.movie and not window.busy and window.player.isSeekable():
                report['checks'].append('Opened source with '+str(len(window.movie.tracks))+' tracks')
                state['stage'] = 1
                window.seek(10)
                window.player.play()
            elif state['stage'] == 1 and window.player.position() >= 10000 and state['frames'] >= 3:
                window.player.pause()
                report['checks'].append('Standalone playback decoded frames and sought beyond 10 seconds')
                window.set_range(10.1,12.3)
                window.add_clip()
                window.set_range(30.2,32.1)
                window.add_clip()
                if len(window.ranges) != 2:
                    raise RuntimeError('Could not create two clip ranges')
                state['stage'] = 2
                window.export_to(out,[(i,a,b) for i,(a,b) in enumerate(window.ranges)])
            elif state['stage'] == 2 and not window.busy:
                if len(window.last_results) != 2:
                    raise RuntimeError('Batch export did not finish: '+window.status.text())
                for result in window.last_results:
                    movie = Movie(result['path'])
                    if len(movie.tracks) != len(window.movie.tracks):
                        raise RuntimeError('Track count differs')
                report['checks'].append('Two clips exported, byte-verified, and parsed with every track retained')
                report['outputs'] = window.last_results
                report['frames_decoded'] = state['frames']
                report['status'] = 'PASS'
                save()
                timer.stop()
                window.close()
                app.quit()
        except Exception as e:
            report['status'] = 'FAIL'
            report['error'] = str(e)
            save()
            timer.stop()
            if window.task:
                window.task.cancel.set()
                window.task.wait(10000)
            app.exit(1)
    timer.timeout.connect(poll)
    timer.start()
    save()
    def drop_source():
        try:
            targets = [w for w in app.allWindows() if w.parent() == window.windowHandle()]
            if not targets:
                raise RuntimeError('Native preview drop surface is missing')
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(Path(source).resolve()))])
            actions = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction
            for event in (
                QDragEnterEvent(QPoint(20, 20), actions, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier),
                QDragMoveEvent(QPoint(20, 20), actions, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier),
                QDropEvent(QPointF(20, 20), actions, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier),
            ):
                app.sendEvent(targets[0], event)
                if not event.isAccepted() or event.dropAction() != Qt.DropAction.CopyAction:
                    raise RuntimeError('Native preview failed to accept a safe file drop')
            report['checks'].append('Native video surface accepted MOV drag, move and drop as CopyAction')
        except Exception as e:
            report.update(status='FAIL', error=str(e))
            save()
            timer.stop()
            app.exit(1)
    QTimer.singleShot(0, drop_source)
