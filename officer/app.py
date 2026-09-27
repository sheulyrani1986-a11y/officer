"""OfficeR Suite Launcher and Welcome Hub."""

import os
import sys
import json
from typing import Optional, List, Dict
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QFont, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QScrollArea, QSizePolicy
)
from officer.core.args import file_argument
from officer.core.themes.theme_manager import ThemeManager
from officer.core.ui.icons import IconProvider
from officer.writer.window import WriteRWindow
from officer.rsheet.window import RSheetWindow
from officer.presentr.window import PresentRWindow


CONFIG_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "officer"
)
RECENT_FILES_PATH = os.path.join(CONFIG_DIR, "recent.json")


def load_recent_files() -> List[Dict[str, str]]:
    if not os.path.exists(RECENT_FILES_PATH):
        return []
    try:
        with open(RECENT_FILES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def add_recent_file(filepath: str, app_type: str) -> None:
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        recents = load_recent_files()
        recents = [r for r in recents if r.get("path") != filepath]
        recents.insert(0, {
            "path": filepath,
            "name": os.path.basename(filepath),
            "type": app_type
        })
        recents = recents[:15]  # Keep last 15
        with open(RECENT_FILES_PATH, "w", encoding="utf-8") as f:
            json.dump(recents, f, indent=2)
    except Exception:
        pass


class AppCard(QFrame):
    """Modern card widget for launching an OfficeR application."""

    def __init__(
        self,
        title: str,
        subtitle: str,
        color_hex: str,
        icon_name: str,
        launch_callback,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.launch_callback = launch_callback
        self.setFixedSize(270, 200)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.setStyleSheet(f"""
            QFrame {{
                background-color: #FFFFFF;
                border: 1px solid #E5E7EB;
                border-top: 5px solid {color_hex};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border: 1px solid {color_hex};
                border-top: 5px solid {color_hex};
                background-color: #F9FAFB;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        # Header with icon and title
        header = QHBoxLayout()
        icon_lbl = QLabel(self)
        icon_lbl.setPixmap(IconProvider.get_icon(icon_name, color=color_hex, size=32).pixmap(32, 32))
        header.addWidget(icon_lbl)

        title_lbl = QLabel(title, self)
        title_lbl.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {color_hex}; border: none; background: transparent;")
        header.addWidget(title_lbl)
        header.addStretch(1)
        layout.addLayout(header)

        # Subtitle description
        sub_lbl = QLabel(subtitle, self)
        sub_lbl.setFont(QFont("Segoe UI", 11))
        sub_lbl.setWordWrap(True)
        sub_lbl.setStyleSheet("color: #6B7280; border: none; background: transparent;")
        layout.addWidget(sub_lbl)

        layout.addStretch(1)

        # Launch Button
        btn = QPushButton(f"Open {title}", self)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color_hex};
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 8px 14px;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)
        btn.clicked.connect(self.launch_callback)
        layout.addWidget(btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.launch_callback()
        super().mousePressEvent(event)


class OfficeRHubWindow(QMainWindow):
    """Main start center / welcome hub for OfficeR."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("OfficeR — Modern Office Suite")
        self.setWindowIcon(IconProvider.get_app_icon())
        self.resize(1000, 680)

        self._active_windows = []

        ThemeManager.instance().set_app_name("suite", self)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Left Sidebar Navigation
        sidebar = QFrame(self)
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("""
            QFrame {
                background-color: #1E293B;
                color: #F8FAFC;
                border-right: 1px solid #334155;
            }
        """)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setContentsMargins(16, 24, 16, 24)
        sb_layout.setSpacing(12)

        # Suite Brand
        brand_lbl = QLabel("OfficeR", sidebar)
        brand_lbl.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        brand_lbl.setStyleSheet("color: #FFFFFF; border: none;")
        sb_layout.addWidget(brand_lbl)

        sub_brand = QLabel("Linux Native Office Suite", sidebar)
        sub_brand.setFont(QFont("Segoe UI", 10))
        sub_brand.setStyleSheet("color: #94A3B8; border: none; margin-bottom: 20px;")
        sb_layout.addWidget(sub_brand)

        # Sidebar Action Buttons
        self._add_sidebar_btn(sb_layout, "New Document", lambda: self.launch_writer())
        self._add_sidebar_btn(sb_layout, "New Workbook", lambda: self.launch_rsheet())
        self._add_sidebar_btn(sb_layout, "New Presentation", lambda: self.launch_presentr())

        sb_layout.addSpacing(16)
        open_btn = self._add_sidebar_btn(sb_layout, "Open Existing...", self.open_file_dialog)
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: #334155;
                color: #FFFFFF;
                border-radius: 5px;
                padding: 10px;
                font-weight: 600;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #475569;
            }
        """)

        sb_layout.addStretch(1)

        # Theme toggle button
        theme_btn = QPushButton("Toggle Theme", sidebar)
        theme_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #94A3B8;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                border-color: #94A3B8;
            }
        """)
        theme_btn.clicked.connect(lambda: ThemeManager.instance().toggle_theme(self))
        sb_layout.addWidget(theme_btn)

        root_layout.addWidget(sidebar)

        # 2. Main Welcome Content Area
        content_scroll = QScrollArea(self)
        content_scroll.setWidgetResizable(True)
        content_scroll.setStyleSheet("background-color: #F8FAFC; border: none;")

        content_container = QWidget(content_scroll)
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(36, 32, 36, 32)
        content_layout.setSpacing(28)

        # Header Title
        hero_title = QLabel("Welcome to OfficeR", content_container)
        hero_title.setFont(QFont("Segoe UI", 22, QFont.Weight.Bold))
        hero_title.setStyleSheet("color: #0F172A;")
        content_layout.addWidget(hero_title)

        hero_sub = QLabel("Select an application below or open an existing file to get started.", content_container)
        hero_sub.setFont(QFont("Segoe UI", 12))
        hero_sub.setStyleSheet("color: #64748B; margin-top: -18px;")
        content_layout.addWidget(hero_sub)

        # App Launch Cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)

        # WriteR Card
        card_writer = AppCard(
            title="WriteR",
            subtitle="Polished word processor with DOCX, ODT, and vector PDF support.",
            color_hex="#185ABD",
            icon_name="new",
            launch_callback=self.launch_writer,
            parent=content_container
        )
        cards_layout.addWidget(card_writer)

        # RSheet Card
        card_rsheet = AppCard(
            title="RSheet",
            subtitle="Spreadsheet app with virtualized grid, formulas, XLSX, and ODS.",
            color_hex="#107C41",
            icon_name="table",
            launch_callback=self.launch_rsheet,
            parent=content_container
        )
        cards_layout.addWidget(card_rsheet)

        # PresentR Card
        card_presentr = AppCard(
            title="PresentR",
            subtitle="Slide deck creator with shapes, canvas, PPTX, and fullscreen presentation.",
            color_hex="#C43E1C",
            icon_name="slide",
            launch_callback=self.launch_presentr,
            parent=content_container
        )
        cards_layout.addWidget(card_presentr)
        cards_layout.addStretch(1)

        content_layout.addLayout(cards_layout)

        # Recent Documents Section
        recent_header = QLabel("Recent Documents", content_container)
        recent_header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        recent_header.setStyleSheet("color: #1E293B; margin-top: 10px;")
        content_layout.addWidget(recent_header)

        self.recent_list = QListWidget(content_container)
        self.recent_list.setStyleSheet("""
            QListWidget {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 6px;
                min-height: 150px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #F1F5F9;
                color: #334155;
                font-size: 13px;
            }
            QListWidget::item:hover {
                background-color: #F8FAFC;
                color: #0F172A;
            }
        """)
        self.recent_list.itemDoubleClicked.connect(self._on_recent_item_clicked)
        content_layout.addWidget(self.recent_list)

        self._refresh_recent_files()

        content_scroll.setWidget(content_container)
        root_layout.addWidget(content_scroll, 1)

    def _add_sidebar_btn(self, layout: QVBoxLayout, text: str, callback) -> QPushButton:
        btn = QPushButton(text, self)
        btn.setFont(QFont("Segoe UI", 11))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {{
                background-color: transparent;
                color: #CBD5E1;
                border: none;
                border-radius: 4px;
                padding: 8px 12px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: #334155;
                color: #FFFFFF;
            }}
        """)
        btn.clicked.connect(callback)
        layout.addWidget(btn)
        return btn

    def _refresh_recent_files(self) -> None:
        self.recent_list.clear()
        recents = load_recent_files()
        if not recents:
            item = QListWidgetItem("No recent files yet. Create a new document or open a file above.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(item)
            return

        for r in recents:
            name = r.get("name", "Untitled")
            path = r.get("path", "")
            app_type = r.get("type", "Document")
            item = QListWidgetItem(f"[{app_type.upper()}]  {name}  —  {path}")
            item.setData(Qt.ItemDataRole.UserRole, r)
            self.recent_list.addItem(item)

    def _on_recent_item_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and "path" in data and os.path.exists(data["path"]):
            self.open_file(data["path"])

    def launch_writer(self, filepath: Optional[str] = None) -> WriteRWindow:
        win = WriteRWindow()
        if filepath and os.path.exists(filepath):
            from officer.writer.io.docx_handler import DocxHandler
            from officer.writer.io.odt_handler import OdtHandler
            ext = os.path.splitext(filepath)[1].lower()
            if ext == ".docx":
                DocxHandler.load(filepath, win.page.document())
            elif ext == ".odt":
                OdtHandler.load(filepath, win.page.document())
            win.current_filepath = filepath
            win._update_window_title()
            add_recent_file(filepath, "writer")

        win.show()
        self._active_windows.append(win)
        return win

    def launch_rsheet(self, filepath: Optional[str] = None) -> RSheetWindow:
        win = RSheetWindow()
        if filepath and os.path.exists(filepath):
            from officer.rsheet.io.xlsx_handler import XlsxHandler
            from officer.rsheet.io.ods_handler import OdsHandler
            ext = os.path.splitext(filepath)[1].lower()
            if ext == ".xlsx":
                win.sheets = XlsxHandler.load(filepath)
            elif ext == ".ods":
                win.sheets = OdsHandler.load(filepath)
            if win.sheets:
                win.tab_bar.blockSignals(True)
                while win.tab_bar.count() > 0:
                    win.tab_bar.removeTab(0)
                for name in win.sheets.keys():
                    win.tab_bar.addTab(name)
                win.tab_bar.blockSignals(False)
                win._on_sheet_tab_switched(0)
            win.current_filepath = filepath
            win._update_window_title()
            add_recent_file(filepath, "rsheet")

        win.show()
        self._active_windows.append(win)
        return win

    def launch_presentr(self, filepath: Optional[str] = None) -> PresentRWindow:
        win = PresentRWindow()
        if filepath and os.path.exists(filepath):
            from officer.presentr.io.pptx_handler import PptxHandler
            from officer.presentr.io.odp_handler import OdpHandler
            ext = os.path.splitext(filepath)[1].lower()
            if ext == ".pptx":
                loaded = PptxHandler.load(filepath)
            elif ext == ".odp":
                loaded = OdpHandler.load(filepath)
            else:
                loaded = None
            if loaded:
                win.presentation = loaded
                win._refresh_slide_list()
            win.current_filepath = filepath
            win._update_window_title()
            add_recent_file(filepath, "presentr")

        win.show()
        self._active_windows.append(win)
        return win

    def open_file_dialog(self) -> None:
        filters = (
            "All Supported Office Files (*.docx *.odt *.xlsx *.ods *.pptx *.odp *.csv *.txt);;"
            "Word Documents (*.docx *.odt);;"
            "Spreadsheets (*.xlsx *.ods *.csv);;"
            "Presentations (*.pptx *.odp);;"
            "All Files (*.*)"
        )
        filepath, _ = QFileDialog.getOpenFileName(self, "Open Document", "", filters)
        if filepath:
            self.open_file(filepath)

    def open_file(self, filepath: str) -> None:
        if not os.path.exists(filepath):
            QMessageBox.critical(self, "Error", f"File does not exist: {filepath}")
            return

        ext = os.path.splitext(filepath)[1].lower()
        if ext in (".docx", ".odt", ".txt"):
            self.launch_writer(filepath)
        elif ext in (".xlsx", ".ods", ".csv"):
            self.launch_rsheet(filepath)
        elif ext in (".pptx", ".odp"):
            self.launch_presentr(filepath)
        else:
            QMessageBox.warning(self, "Notice", f"Unsupported file extension: {ext}")


def main() -> None:
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    app.setApplicationName("OfficeR")
    app.setApplicationDisplayName("OfficeR")

    hub = OfficeRHubWindow()
    hub.show()

    path = file_argument()
    if path:
        hub.open_file(path)

    if "pytest" not in sys.modules:
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
