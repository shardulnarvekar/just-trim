"""File drops across the window, including Qt's native video surface.

Copyright (c) 2026 Shardul Narvekar. See LICENSE.txt.
"""
from pathlib import Path

from PySide6.QtCore import QObject, QEvent, QTimer, Qt
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication, QWidget


class MovieDropHandler(QObject):
    def __init__(self, window, hint):
        super().__init__(window)
        self.window = window
        self.hint = hint
        self.highlighted = False
        # Child controls (especially line edits and item-view viewports) have
        # their own drop handling. Catch the event before they consume it.
        for widget in [window, *window.findChildren(QWidget)]:
            widget.setAcceptDrops(True)
        QApplication.instance().installEventFilter(self)
        self.show_hint(False)

    def owns_target(self, target):
        if isinstance(target, QWidget):
            return target.window() is self.window
        # QVideoWidget embeds a native QWindow. A main-window dragEnterEvent
        # alone does not reliably receive drops on that preview surface.
        if isinstance(target, QWindow):
            current = target
            while current is not None:
                if current == self.window.windowHandle():
                    return True
                current = current.parent()
        return False

    def movie_path(self, event):
        if self.window.busy or not event.possibleActions() & Qt.DropAction.CopyAction:
            return None
        urls = event.mimeData().urls()
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        path = Path(urls[0].toLocalFile())
        if path.suffix.lower() != '.mov' or not path.is_file():
            return None
        return str(path)

    def show_hint(self, active):
        self.highlighted = active
        self.hint.setText('Release to open this MOV' if active else
                          'Drop a MOV here — or anywhere in this window')
        self.hint.setStyleSheet(
            'padding: 9px; border: 2px dashed #1769aa; border-radius: 4px; '
            + ('background: #dcebfa; color: #174e7d;' if active else
               'background: #f5f8fb; color: #555;'))

    def eventFilter(self, target, event):
        kind = event.type()
        if kind not in (QEvent.Type.DragEnter, QEvent.Type.DragMove,
                        QEvent.Type.DragLeave, QEvent.Type.Drop):
            return False
        if not self.owns_target(target) or QApplication.activeModalWidget() is not None:
            return False
        if kind == QEvent.Type.DragLeave:
            self.show_hint(False)
            event.accept()
            return True
        path = self.movie_path(event)
        if path is None:
            self.show_hint(False)
            event.ignore()
            return True
        # Never report MoveAction to Explorer: dropping opens the source,
        # and must never tell another app to move or delete it.
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        self.show_hint(kind != QEvent.Type.Drop)
        if kind == QEvent.Type.Drop:
            # Complete the native drag before opening media or a confirmation.
            QTimer.singleShot(0, lambda: self.window.open_path(path))
        return True
