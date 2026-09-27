"""PresentR Application Entry Point."""

import sys
from PySide6.QtWidgets import QApplication
from officer.core.args import file_argument
from officer.presentr.window import PresentRWindow
from officer.core.themes.theme_manager import ThemeManager


def main() -> None:
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    app.setApplicationName("OfficeR PresentR")
    app.setApplicationDisplayName("PresentR")

    ThemeManager.instance().set_app_name("presentr")

    window = PresentRWindow()
    path = file_argument()
    if path:
        window.open_path(path)
    window.show()

    if "pytest" not in sys.modules:
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
