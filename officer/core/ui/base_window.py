"""Shared Base Window for all OfficeR applications."""

import os
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut, QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QMenu, QFileDialog, QMessageBox
)
from officer.core.ui.quick_access import QuickAccessBar
from officer.core.ui.ribbon import OfficeRibbon
from officer.core.ui.status_bar import OfficeStatusBar
from officer.core.ui.icons import IconProvider
from officer.core.ui.template_gallery import TemplateGalleryDialog
from officer.core.commands.stack import CommandStack
from officer.core.themes.theme_manager import ThemeManager


class OfficeBaseWindow(QMainWindow):
    """
    Foundational window structure for WriteR, RSheet and PresentR: the colored
    title band, the ribbon, the document workspace and the status strip.
    """

    #: An app that holds a wall of designs sets this, answers the three hooks
    #: below, and gets the backstage entry and its warning for nothing.
    has_templates = False

    def __init__(
        self,
        app_name: str,
        app_title: str,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.app_name = app_name
        self.app_title = app_title
        self.current_filepath: Optional[str] = None

        # Command & Undo/Redo engine
        self.command_stack = CommandStack(parent=self)
        self.command_stack.cleanChanged.connect(self._on_clean_changed)

        # Apply the application's branded theme and register for dark-mode flips
        manager = ThemeManager.instance()
        manager.set_app_name(app_name, self)
        manager.register_window(self, app_name)

        # Main Layout Setup
        self.central_container = QWidget(self)
        self.central_container.setObjectName("MainContainer")
        self.setCentralWidget(self.central_container)

        self.root_layout = QVBoxLayout(self.central_container)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        # 1. Colored title band with the quick access commands
        self.quick_access = QuickAccessBar(app_title=app_title, app_name=app_name, parent=self)
        self.quick_access.bind_command_stack(self.command_stack)
        self.quick_access.newRequested.connect(self.on_new)
        self.quick_access.openRequested.connect(self.on_open)
        self.quick_access.saveRequested.connect(self.on_save)
        self.quick_access.undoRequested.connect(self.command_stack.undo)
        self.quick_access.redoRequested.connect(self.command_stack.redo)
        self.root_layout.addWidget(self.quick_access)

        # 2. Ribbon (tab band + command body)
        self.ribbon = OfficeRibbon(self)
        self.ribbon.fileClicked.connect(self.show_file_menu)
        self.root_layout.addWidget(self.ribbon)

        # 3. Document workspace placeholder (subclasses fill this in)
        self.workspace_container = QWidget(self)
        self.workspace_layout = QVBoxLayout(self.workspace_container)
        self.workspace_layout.setContentsMargins(0, 0, 0, 0)
        self.workspace_layout.setSpacing(0)
        self.root_layout.addWidget(self.workspace_container, 1)

        # 4. Status strip
        self.status_bar = OfficeStatusBar(self)
        self.setStatusBar(self.status_bar)

        self.setWindowIcon(IconProvider.get_app_icon())

        # Global Keyboard Shortcuts
        self._setup_shortcuts()
        self.resize(1280, 820)
        self._update_window_title()

    # -- chrome ------------------------------------------------------------ #

    def _setup_shortcuts(self) -> None:
        """Standard Office shortcuts."""
        QShortcut(QKeySequence.StandardKey.New, self, self.on_new)
        QShortcut(QKeySequence.StandardKey.Open, self, self.on_open)
        QShortcut(QKeySequence.StandardKey.Save, self, self.on_save)
        QShortcut(QKeySequence.StandardKey.SaveAs, self, self.on_save_as)
        QShortcut(QKeySequence("F12"), self, self.on_save_as)
        QShortcut(QKeySequence.StandardKey.Print, self, self.on_export_pdf)
        QShortcut(QKeySequence("Ctrl+P"), self, self.on_export_pdf)
        QShortcut(QKeySequence.StandardKey.Undo, self, self.command_stack.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, self.command_stack.redo)
        QShortcut(QKeySequence("Ctrl+F1"), self, self.ribbon.toggle_collapse)
        QShortcut(QKeySequence("F10"), self, self._focus_ribbon)

    def _focus_ribbon(self) -> None:
        self.ribbon.tab_bar.setFocus()
        self.ribbon.tab_bar.setCurrentIndex(max(0, self.ribbon.tab_bar.currentIndex()))

    def show_file_menu(self) -> None:
        """Display the backstage File menu, opened from the tab band."""
        menu = QMenu(self)
        menu.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        menu.setMinimumWidth(230)
        self._add_menu_action(menu, "New", "new", self.on_new, QKeySequence.StandardKey.New)
        if self.has_templates:
            self._add_menu_action(menu, "New from Template...", "templates",
                                  self.open_template_gallery, None)
        self._add_menu_action(menu, "Open...", "open", self.on_open, QKeySequence.StandardKey.Open)
        menu.addSeparator()
        self._add_menu_action(menu, "Save", "save", self.on_save, QKeySequence.StandardKey.Save)
        self._add_menu_action(
            menu, "Save As...", "save-as", self.on_save_as, QKeySequence.StandardKey.SaveAs
        )
        self._add_menu_action(
            menu, "Export to PDF...", "pdf", self.on_export_pdf, QKeySequence("Ctrl+P")
        )
        menu.addSeparator()
        self._add_menu_action(menu, "Close", "close", self.close, QKeySequence("Ctrl+W"))

        btn = self.ribbon.file_btn
        menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))

    @staticmethod
    def _add_menu_action(menu: QMenu, text: str, icon_name: str, slot, shortcut) -> QAction:
        action = QAction(IconProvider.get_icon(icon_name, size=16), text, menu)
        action.triggered.connect(slot)
        if shortcut is not None:
            action.setShortcut(shortcut)
        menu.addAction(action)
        return action

    # -- starting from a design ---------------------------------------------- #

    def template_entries(self):
        """This app's designs as gallery tiles. An app without any has none."""
        return []

    def template_held(self) -> bool:
        """Whether the app is holding work a design would cover over."""
        return False

    def apply_template(self, key: str) -> None:
        """Put the design called *key* on the screen, in the app's own terms."""

    def open_template_gallery(self) -> None:
        """Office's *New from Template*: a wall of previews, then a fresh start.

        The wall is built by the app, because only it can paint a real sheet;
        the choice and the warning over the work it would cover are common to
        both, and live here so the two apps cannot drift apart on it.
        """
        entries = self.template_entries()
        if not entries:
            return
        dialog = TemplateGalleryDialog("Choose a design to start from",
                                       entries, self)
        picked = dialog.chosen() if dialog.exec() else None
        if picked is None:
            return
        if self.template_held() and not self._confirm_over_work(picked.name):
            return
        self.apply_template(picked.key)

    def _confirm_over_work(self, design: str) -> bool:
        """Ask before a design replaces what the app is already holding."""
        answer = QMessageBox.question(
            self, "Start from a design",
            f"“{design}” will replace everything now in this document.\n"
            "Save it first, or carry on and lose it?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            self.on_save()
            # The design may only cover the work over once it is on disk: a
            # Save As the user backed out of leaves nothing saved to go back to.
            return bool(self.current_filepath)
        return True

    # -- title / dirty state ------------------------------------------------ #

    def _on_clean_changed(self, is_clean: bool) -> None:
        self._update_window_title()

    def _update_window_title(self) -> None:
        doc_name = os.path.basename(self.current_filepath) if self.current_filepath else "Untitled"
        dirty = not self.command_stack.is_clean
        self.quick_access.set_document_title(doc_name, is_dirty=dirty)
        star = " •" if dirty else ""
        self.setWindowTitle(f"{doc_name}{star} — {self.app_title}")

    def on_theme_changed(self, dark: bool) -> None:
        """Subclasses override this to recolor anything painted by hand."""

    # Subclasses implement these document hooks
    def on_new(self) -> None:
        pass

    def on_open(self) -> None:
        pass

    def on_save(self) -> None:
        pass

    def on_save_as(self) -> None:
        pass

    def on_export_pdf(self) -> None:
        pass
