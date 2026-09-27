"""ThemeManager for managing application themes and dark/light switching."""

import weakref
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QWidget
from officer.core.themes.styles import OfficeColors, build_stylesheet, office_colors


class ThemeManager(QObject):
    """Central theme state; each window keeps its own app-colored stylesheet."""

    themeChanged = Signal(bool)  # True if dark mode

    _instance: Optional["ThemeManager"] = None

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._dark_mode = False
        self._app_name = "suite"
        self._windows: List["weakref.ReferenceType[QWidget]"] = []

    @classmethod
    def instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    @property
    def is_dark(self) -> bool:
        return self._dark_mode

    def colors(self, app_name: Optional[str] = None) -> OfficeColors:
        """Resolved palette for *app_name* (defaults to the last window registered)."""
        return office_colors(app_name or self._app_name, self._dark_mode)

    def toggle_theme(self, target: Optional[QWidget] = None) -> None:
        self.set_dark_mode(not self._dark_mode, target)

    def set_dark_mode(self, dark: bool, target: Optional[QWidget] = None) -> None:
        self._dark_mode = dark
        if target is not None:
            self.apply(target)
        if self._windows:
            self.apply_all()
        else:
            # Nothing has registered a window yet, so theme the whole application.
            self.apply(None)
        self.themeChanged.emit(self._dark_mode)

    def set_app_name(self, app_name: str, target: Optional[QWidget] = None) -> None:
        """Bind *app_name* branding to *target* (and remember it for theme switches)."""
        self._app_name = app_name
        if target is not None:
            self.register_window(target, app_name)
        self.apply(target)

    def register_window(self, window: QWidget, app_name: str) -> None:
        """Remember *window* so its own branding survives a dark-mode switch."""
        window.setProperty("officeApp", app_name)
        for ref in self._windows:
            if ref() is window:
                return
        self._windows.append(weakref.ref(window))

    def apply(self, target: Optional[QWidget] = None) -> None:
        """Apply the computed stylesheet to *target* or the whole QApplication."""
        qss = build_stylesheet(self._app_name, self._dark_mode)
        if target is not None:
            target.setStyleSheet(qss)
        else:
            app = QApplication.instance()
            if app:
                app.setStyleSheet(qss)

    def apply_all(self) -> None:
        """Re-apply every registered window's own branding (used on theme switch)."""
        alive = []
        for ref in self._windows:
            window = ref()
            if window is None:
                continue
            alive.append(ref)
            app_name = window.property("officeApp") or self._app_name
            window.setStyleSheet(build_stylesheet(str(app_name), self._dark_mode))
            on_theme_changed = getattr(window, "on_theme_changed", None)
            if callable(on_theme_changed):
                on_theme_changed(self._dark_mode)
        self._windows = alive
