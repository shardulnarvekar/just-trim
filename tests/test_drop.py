"""Regression checks for drops on child controls and the native preview."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDragLeaveEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QDialog
from main import Window

app = QApplication.instance() or QApplication([])


class FileDropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.movie = Path(self.temp.name) / 'My clip 日本語.MOV'
        self.movie.write_bytes(b'file drop test; parsing tested by the executable smoke test')
        self.window = Window()
        self.window.show()
        app.processEvents()
        self.opened = []
        self.window.open_path = self.opened.append

    def tearDown(self):
        self.window.busy = False
        self.window.close()
        self.window.deleteLater()
        app.processEvents()
        self.temp.cleanup()

    def drag(self, target, urls=None, actions=None):
        mime = QMimeData()
        mime.setUrls(urls if urls is not None else [QUrl.fromLocalFile(str(self.movie))])
        actions = actions if actions is not None else Qt.DropAction.CopyAction | Qt.DropAction.MoveAction
        enter = QDragEnterEvent(QPoint(10, 10), actions, mime,
                                Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        app.sendEvent(target, enter)
        return mime, actions, enter

    def drop(self, target):
        mime, actions, enter = self.drag(target)
        self.assertTrue(enter.isAccepted())
        self.assertEqual(enter.dropAction(), Qt.DropAction.CopyAction)
        self.assertTrue(self.window.file_drops.highlighted)
        move = QDragMoveEvent(QPoint(12, 12), actions, mime,
                             Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        app.sendEvent(target, move)
        self.assertTrue(move.isAccepted())
        drop = QDropEvent(QPointF(12, 12), actions, mime,
                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        app.sendEvent(target, drop)
        self.assertTrue(drop.isAccepted())
        self.assertEqual(drop.dropAction(), Qt.DropAction.CopyAction)
        app.processEvents()
        self.assertEqual(self.opened[-1], str(self.movie))
        self.assertFalse(self.window.file_drops.highlighted)
        self.assertTrue(self.movie.exists())

    def test_file_opens_from_all_drop_surfaces(self):
        for control in self.window.controls:
            control.setEnabled(True)
        native = [w for w in app.allWindows() if w.parent() == self.window.windowHandle()]
        self.assertTrue(native, 'Expected QVideoWidget native child surface')
        targets = [self.window, self.window.centralWidget(), self.window.drop_hint,
                   self.window.video, self.window.table.viewport(), self.window.start_edit,
                   self.window.timeline, self.window.open_button, self.window.windowHandle(), *native]
        for target in targets:
            with self.subTest(target=type(target).__name__):
                self.drop(target)
        self.assertEqual(len(self.opened), len(targets), 'Each drop opens exactly once')
        self.assertEqual(self.window.start_edit.text(), '00:00:00.000')

    def test_invalid_files_and_nonlocal_urls_rejected(self):
        cases = [[], [QUrl('https://example.com/clip.mov')],
                 [QUrl.fromLocalFile(str(self.movie)), QUrl.fromLocalFile(str(self.movie))],
                 [QUrl.fromLocalFile(str(self.movie.with_suffix('.mp4')))],
                 [QUrl.fromLocalFile(str(self.movie.parent / 'missing.mov'))],
                 [QUrl.fromLocalFile(str(self.movie.parent))]]
        for urls in cases:
            with self.subTest(urls=urls):
                self.assertFalse(self.drag(self.window.windowHandle(), urls)[2].isAccepted())
        self.assertEqual(self.opened, [])

    def test_busy_export_rejects_drop(self):
        self.window.busy = True
        self.assertFalse(self.drag(self.window.windowHandle())[2].isAccepted())
        self.assertEqual(self.opened, [])

    def test_move_only_drop_rejected(self):
        self.assertFalse(self.drag(self.window.windowHandle(), actions=Qt.DropAction.MoveAction)[2].isAccepted())

    def test_drag_leave_resets_highlight(self):
        mime, _, enter = self.drag(self.window.windowHandle())
        self.assertTrue(enter.isAccepted())
        app.sendEvent(self.window.windowHandle(), QDragLeaveEvent())
        self.assertFalse(self.window.file_drops.highlighted)

    def test_unrelated_dialog_not_intercepted(self):
        dialog = QDialog(self.window)
        self.assertFalse(self.window.file_drops.owns_target(dialog))
        dialog.deleteLater()


if __name__ == '__main__':
    unittest.main(verbosity=2)
