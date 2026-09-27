"""Quick access toolbar shown in the colored window title band."""

from typing import Optional
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import QWidget, QHBoxLayout, QToolButton, QLabel, QFrame, QSizePolicy
from officer.core.ui.icons import IconProvider
from officer.core.commands.stack import CommandStack
from officer.core.themes.theme_manager import ThemeManager


class QuickAccessBar(QWidget):
    """
    The band across the top of every OfficeR window: app badge, the pinned
    New/Open/Save/Undo/Redo commands, the document title in the middle and the
    theme switcher on the right.
    """

    BAND_HEIGHT = 32

    newRequested = Signal()
    openRequested = Signal()
    saveRequested = Signal()
    undoRequested = Signal()
    redoRequested = Signal()

    def __init__(self, app_title: str = "OfficeR", app_name: str = "suite",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("TitleHeader")
        # A bare QWidget only paints its style-sheet background when asked to.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.app_title = app_title
        self._doc_name = "Untitled"
        self._dirty = False
        self.setFixedHeight(self.BAND_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(1)

        white = "#FFFFFF"
        badge = QLabel(self)
        badge.setPixmap(IconProvider.get_app_icon().pixmap(16, 16))
        badge.setFixedSize(20, 20)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(badge)

        layout.addSpacing(6)
        self.new_btn = self._command("new", "New (Ctrl+N)", white, layout)
        self.new_btn.clicked.connect(self.newRequested.emit)
        self.open_btn = self._command("open", "Open (Ctrl+O)", white, layout)
        self.open_btn.clicked.connect(self.openRequested.emit)
        self.save_btn = self._command("save", "Save (Ctrl+S)", white, layout)
        self.save_btn.clicked.connect(self.saveRequested.emit)

        layout.addSpacing(4)
        sep = QFrame(self)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("background-color: rgba(255, 255, 255, 80); border: none;")
        sep.setFixedWidth(1)
        sep.setFixedHeight(16)
        layout.addWidget(sep)
        layout.addSpacing(4)

        self.undo_btn = self._command("undo", "Undo (Ctrl+Z)", white, layout)
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undoRequested.emit)
        self.redo_btn = self._command("redo", "Redo (Ctrl+Y)", white, layout)
        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self.redoRequested.emit)

        layout.addStretch(1)
        self.doc_title_label = QLabel(self)
        self.doc_title_label.setObjectName("DocTitleLabel")
        self.doc_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.doc_title_label, 4)
        layout.addStretch(1)

        self.theme_btn = self._command("theme", "Switch to dark mode", white, layout)
        self.theme_btn.clicked.connect(self._toggle_theme)

        # Placeholder label kept so callers can query the branding text.
        self.app_label = QLabel(app_title, self)
        self.app_label.setObjectName("AppTitleLabel")
        self.app_label.setVisible(False)

        self.set_document_title(self._doc_name)

    def _command(self, icon_name: str, tooltip: str, color: str, layout) -> QToolButton:
        btn = QToolButton(self)
        btn.setIcon(IconProvider.get_icon(icon_name, color=color, size=16))
        btn.setIconSize(QSize(16, 16))
        btn.setToolTip(tooltip)
        btn.setFixedSize(26, 24)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        layout.addWidget(btn)
        return btn

    def set_document_title(self, title: str, is_dirty: bool = False) -> None:
        """Show Office's "<document> — <App>" caption, with a dot for unsaved work."""
        self._doc_name = title
        self._dirty = is_dirty
        marker = " •" if is_dirty else ""
        self.doc_title_label.setText(f"{title}{marker} — {self.app_title}")

    @property
    def document_title(self) -> str:
        return self._doc_name

    def bind_command_stack(self, stack: CommandStack) -> None:
        """Enable the undo/redo buttons from the active command stack state."""
        self.undo_btn.setEnabled(stack.can_undo)
        self.redo_btn.setEnabled(stack.can_redo)
        stack.canUndoChanged.connect(self.undo_btn.setEnabled)
        stack.canRedoChanged.connect(self.redo_btn.setEnabled)

    def _toggle_theme(self) -> None:
        manager = ThemeManager.instance()
        manager.toggle_theme(self)
        self.theme_btn.setToolTip(
            "Switch to light mode" if manager.is_dark else "Switch to dark mode"
        )
