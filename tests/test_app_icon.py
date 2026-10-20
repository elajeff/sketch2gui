import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from sketch2gui.app_icon import app_icon_path, load_app_icon
from sketch2gui.ui.main_window import MainWindow


class ApplicationIconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_icon_asset_loads_from_project(self):
        self.assertTrue(app_icon_path().is_file())
        self.assertFalse(load_app_icon().isNull())

    def test_main_window_uses_application_icon(self):
        window = MainWindow()
        try:
            self.assertFalse(window.windowIcon().isNull())
        finally:
            window.close()
            window.deleteLater()
            self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
