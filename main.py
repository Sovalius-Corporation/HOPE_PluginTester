"""HOPE Plugin Tester — entry point."""
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from PySide6.QtWidgets import QApplication
from ui.app import HOPEPluginTester


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("HOPE Plugin Tester")
    app.setOrganizationName("SVG_HOPE")
    win = HOPEPluginTester()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
