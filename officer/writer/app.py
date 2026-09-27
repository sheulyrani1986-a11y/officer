"""WriteR Application Entry Point."""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from officer.core.args import file_argument
from officer.writer.window import WriteRWindow
from officer.core.themes.theme_manager import ThemeManager


def main() -> None:
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    app.setApplicationName("OfficeR WriteR")
    app.setApplicationDisplayName("WriteR")

    ThemeManager.instance().set_app_name("writer")

    window = WriteRWindow()
    path = file_argument()
    if path:
        window.open_path(path)
    window.show()

    if "pytest" not in sys.modules:
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
