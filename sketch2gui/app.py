from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication

from .app_icon import load_app_icon
from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setWindowIcon(load_app_icon())
    app.setApplicationName("Sketch2GUI")
    app.setOrganizationName("Sketch2GUI")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
