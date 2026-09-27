"""Collapsible Office ribbon built from a tab band and a command body.

The geometry and states follow the Microsoft 365 ribbon: the tab row sits on the
application's color band, the command body below it is white, groups are divided
by hairlines with a small caption underneath, and each group may carry the
circular "dialog launcher" arrow in its lower-right corner.
"""

from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal, QSize, QPoint
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QTabBar, QMenu,
    QToolButton, QLabel, QStackedWidget, QSizePolicy
)
from officer.core.ui.icons import IconProvider


class RibbonButton(QToolButton):
    """A ribbon command: large (icon over text) or compact (icon beside text)."""

    def __init__(
        self,
        text: str,
        icon: Optional[QIcon] = None,
        large: bool = False,
        parent: Optional[QWidget] = None
    ):
        super().__init__(parent)
        self.setText(text)
        if icon:
            self.setIcon(icon)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setAutoRaise(True)

        if large:
            self.setObjectName("RibbonLarge")
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            self.setFixedHeight(68)
            # Maximum, not Minimum: Office never stretches a command to absorb
            # slack in the tab, it leaves the slack at the right-hand end.
            self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            # QToolButton can't wrap, so break two-word labels the way Office does.
            if " " in text and "\n" not in text:
                first, _, rest = text.partition(" ")
                self.setText(f"{first}\n{rest}")
            label_lines = self.text().splitlines() or [""]
            if len(label_lines) > 1:
                # Two caption lines need the smaller icon to stay inside 68px.
                self.setIconSize(QSize(24, 24))
            else:
                self.setIconSize(QSize(32, 32))
            metrics = self.fontMetrics()
            widest = max(metrics.horizontalAdvance(line) for line in label_lines)
            self.setMinimumWidth(max(52, widest + 10))
        else:
            self.setObjectName("RibbonCompact")
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.setIconSize(QSize(16, 16))
            self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
            self.setMinimumWidth(0)
            if "\n" in text:
                # Excel's two-line compact commands (Format Painter) run taller.
                # Both bounds are pinned or a tight column squeezes the caption.
                self.setFixedHeight(44)
                self.setMinimumHeight(44)
            else:
                self.setFixedHeight(21)

    @property
    def is_large(self) -> bool:
        return self.objectName() == "RibbonLarge"

    def setMenu(self, menu: Optional[QMenu]) -> None:
        super().setMenu(menu)
        if menu is None or getattr(self, "_menu_allowance", False):
            return
        # MenuButtonPopup carves a chevron column out of the button's own width.
        # Without an allowance for it the arrow paints over the label ("Insert"
        # renders as "Insert|"), so size the button from its text metrics instead
        # of trusting the style's hint.
        self._menu_allowance = True
        metrics = self.fontMetrics()
        lines = self.text().splitlines() or [""]
        widest = max(metrics.horizontalAdvance(line) for line in lines)
        icon_width = 0
        if (self.toolButtonStyle() != Qt.ToolButtonStyle.ToolButtonTextUnderIcon
                and not self.icon().isNull()):
            icon_width = self.iconSize().width() + 6
        self.setMinimumWidth(max(self.minimumWidth(), widest + icon_width + 30))


class RibbonGroup(QFrame):
    """A logical section of a ribbon tab (Clipboard, Font, Cells, ...)"""

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("RibbonGroup")
        # Like its commands, a group keeps its own width: Office puts the slack
        # after the last group rather than inside every group.
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(7, 2, 7, 0)
        self.main_layout.setSpacing(1)

        self.content_widget = QWidget(self)
        self.content_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.content_layout = QHBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.main_layout.addWidget(self.content_widget, 1)

        self.title_label = QLabel(title, self)
        self.title_label.setObjectName("RibbonGroupTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.title_label.setFixedHeight(15)
        self.main_layout.addWidget(self.title_label, 0)

        # Office's "more options" arrow, pinned to the group's bottom-right corner.
        self._launcher: Optional[QToolButton] = None

    # -- content helpers --------------------------------------------------- #

    def add_widget(self, widget: QWidget) -> QWidget:
        self.content_layout.addWidget(widget)
        return widget

    def add_button(
        self,
        text: str,
        icon_name: Optional[str],
        large: bool = True,
        on_click=None,
        checkable: bool = False,
        tooltip: str = ""
    ) -> RibbonButton:
        icon = None if icon_name is None else IconProvider.get_icon(
            icon_name, size=32 if large else 16)
        btn = RibbonButton(text, icon=icon, large=large, parent=self)
        if on_click:
            btn.clicked.connect(on_click)
        if checkable:
            btn.setCheckable(True)
        if tooltip:
            btn.setToolTip(tooltip)
        self.content_layout.addWidget(btn)
        return btn

    def add_split_button(
        self,
        text: str,
        icon_name: str,
        menu: QMenu,
        large: bool = False,
        on_click=None
    ) -> RibbonButton:
        """A command with a drop-down chevron, like Paste or Borders."""
        btn = self.add_button(text, icon_name, large=large, on_click=on_click)
        btn.setMenu(menu)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        btn.setProperty("hasMenu", "true")
        return btn

    def add_column(self) -> QVBoxLayout:
        """A vertical strip of compact commands inside the group."""
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(1)
        col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.content_layout.addLayout(col)
        return col

    def add_sub_row(self, column: QVBoxLayout) -> QHBoxLayout:
        """A horizontal strip nested inside *column* (Word's Font layout)."""
        row_widget = QWidget(self)
        row_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(1)
        column.addWidget(row_widget)
        return row

    def add_button_to(self, layout, text: str, icon_name: Optional[str], large: bool = False,
                      on_click=None, checkable: bool = False,
                      menu: Optional[QMenu] = None) -> RibbonButton:
        """Add a command to a nested *layout* returned by add_column/add_sub_row.

        Passing *menu* turns it into Office's split button (command + chevron).
        """
        icon = None if icon_name is None else IconProvider.get_icon(
            icon_name, size=32 if large else 16)
        btn = RibbonButton(text, icon=icon, large=large, parent=self)
        if on_click:
            btn.clicked.connect(on_click)
        if checkable:
            btn.setCheckable(True)
        if menu is not None:
            btn.setMenu(menu)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            btn.setProperty("hasMenu", "true")
        layout.addWidget(btn)
        return btn

    # -- dialog launcher --------------------------------------------------- #

    def set_dialog_launcher(self, on_click=None) -> QToolButton:
        """Show Office's bottom-right group arrow."""
        if self._launcher is None:
            self._launcher = QToolButton(self)
            self._launcher.setObjectName("RibbonLauncher")
            self._launcher.setText("\u2197")
            self._launcher.setFixedSize(14, 13)
            self._launcher.move(self._launcher_position())
        if on_click:
            self._launcher.clicked.connect(on_click)
        self._launcher.show()
        return self._launcher

    def _launcher_position(self) -> QPoint:
        return QPoint(max(0, self.width() - 17), max(0, self.height() - 15))

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._launcher is not None:
            self._launcher.move(self._launcher_position())

    @property
    def leading(self) -> bool:
        return self.property("leading") == "true"

    def set_leading(self, leading: bool) -> None:
        """The first group of a tab has no separator on its left edge."""
        self.setProperty("leading", "true" if leading else "false")
        _repolish(self)


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)


class RibbonTab(QWidget):
    """One ribbon page holding several RibbonGroups."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("RibbonTab")
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(6, 0, 6, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    def add_group(self, title: str, launcher=None) -> RibbonGroup:
        group = RibbonGroup(title, self)
        group.set_leading(self.layout.count() == 0)
        self.layout.addWidget(group)
        if launcher is not None:
            group.set_dialog_launcher(launcher)
        return group


class OfficeRibbon(QFrame):
    """
    Top-level ribbon for OfficeR applications.

    Layout mirrors Microsoft Office: a colored tab band with the File command and
    the collapse chevron, and a white command body that can fold away.
    """

    TAB_HEIGHT = 28
    BODY_HEIGHT = 112
    COLLAPSED_HEIGHT = TAB_HEIGHT + 2
    EXPANDED_HEIGHT = TAB_HEIGHT + BODY_HEIGHT

    fileClicked = Signal()
    collapsedChanged = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("OfficeRibbon")
        self.setFixedHeight(self.EXPANDED_HEIGHT)

        self._tabs: Dict[str, RibbonTab] = {}
        self._tab_names: List[str] = []
        self._is_collapsed = False

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        # --- Tab band ----------------------------------------------------- #
        self.tab_row = QWidget(self)
        self.tab_row.setObjectName("RibbonTabRow")
        self.tab_row.setFixedHeight(self.TAB_HEIGHT)
        band_layout = QHBoxLayout(self.tab_row)
        band_layout.setContentsMargins(2, 0, 6, 0)
        band_layout.setSpacing(0)

        self.file_btn = QToolButton(self.tab_row)
        self.file_btn.setObjectName("FileMenuButton")
        self.file_btn.setText("File")
        self.file_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.file_btn.clicked.connect(self.fileClicked.emit)
        band_layout.addWidget(self.file_btn)

        self.tab_bar = QTabBar(self.tab_row)
        self.tab_bar.setObjectName("RibbonTabBar")
        self.tab_bar.setDrawBase(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setUsesScrollButtons(True)
        self.tab_bar.setMouseTracking(True)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        band_layout.addWidget(self.tab_bar)

        band_layout.addStretch(1)

        self.collapse_btn = QToolButton(self.tab_row)
        self.collapse_btn.setObjectName("RibbonCollapseButton")
        self.collapse_btn.setArrowType(Qt.ArrowType.UpArrow)
        self.collapse_btn.setIconSize(QSize(12, 12))
        self.collapse_btn.setCursor(Qt.CursorShape.ArrowCursor)
        self.collapse_btn.setToolTip("Collapse Ribbon (Ctrl+F1)")
        self.collapse_btn.clicked.connect(self.toggle_collapse)
        band_layout.addWidget(self.collapse_btn)

        self.root_layout.addWidget(self.tab_row)

        # --- Command body ------------------------------------------------- #
        self.content_stack = QStackedWidget(self)
        self.content_stack.setObjectName("RibbonBody")
        self.content_stack.setFixedHeight(self.BODY_HEIGHT)
        self.root_layout.addWidget(self.content_stack)

        # Kept for callers that reach for the old attribute name.
        self.header_bar = self.tab_row
        self.header_layout = band_layout
        self.tab_widget = self.tab_bar

        # Office expands a collapsed ribbon when a tab is hovered.
        self.tab_bar.installEventFilter(self)

    # -- tab management ---------------------------------------------------- #

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        if watched is self.tab_bar and self._is_collapsed:
            if event.type() == event.Type.HoverEnter or event.type() == event.Type.KeyPress:
                self.expand()
        return super().eventFilter(watched, event)

    def add_tab(self, name: str) -> RibbonTab:
        tab = RibbonTab(self.content_stack)
        self._tabs[name] = tab
        index = self.tab_bar.addTab(name)
        self._tab_names.append(name)
        self.content_stack.addWidget(tab)
        if index == 0:
            self.content_stack.setCurrentWidget(tab)
        return tab

    def get_tab(self, name: str) -> Optional[RibbonTab]:
        return self._tabs.get(name)

    @property
    def current_tab_name(self) -> Optional[str]:
        index = self.tab_bar.currentIndex()
        if 0 <= index < len(self._tab_names):
            return self._tab_names[index]
        return None

    def select_tab(self, name: str) -> None:
        if name in self._tabs:
            self.tab_bar.setCurrentIndex(self._tab_names.index(name))

    def set_tab_visible(self, name: str, visible: bool, fallback: str = "Home") -> None:
        """Office's contextual tabs: the tab only exists while its object does.

        Hiding the band entry rather than deleting it keeps every other tab's
        index, which the stacked body below is matched to.
        """
        if name not in self._tabs:
            return
        index = self._tab_names.index(name)
        if self.tab_bar.isTabVisible(index) == visible:
            return
        self.tab_bar.setTabVisible(index, visible)
        # A band that grew a tab has to be told to want the room for it, or the
        # new entry is drawn past the bar's old edge and simply never shows.
        self.tab_bar.updateGeometry()
        self.tab_row.layout().invalidate()
        if not visible and self.tab_bar.currentIndex() == index:
            self.select_tab(fallback)

    def _on_tab_changed(self, index: int) -> None:
        if 0 <= index < self.content_stack.count():
            self.content_stack.setCurrentIndex(index)
            if self._is_collapsed:
                self.expand()

    # -- collapse ---------------------------------------------------------- #

    def toggle_collapse(self) -> None:
        self.collapse() if self._is_collapsed else self.expand()

    def collapse(self) -> None:
        if not self._is_collapsed:
            self._is_collapsed = True
            self.content_stack.hide()
            self.setFixedHeight(self.COLLAPSED_HEIGHT)
            self.collapse_btn.setArrowType(Qt.ArrowType.DownArrow)
            self.collapse_btn.setToolTip("Expand Ribbon (Ctrl+F1)")
            self.collapsedChanged.emit(True)

    def expand(self) -> None:
        if self._is_collapsed:
            self._is_collapsed = False
            self.content_stack.show()
            self.setFixedHeight(self.EXPANDED_HEIGHT)
            self.collapse_btn.setArrowType(Qt.ArrowType.UpArrow)
            self.collapse_btn.setToolTip("Collapse Ribbon (Ctrl+F1)")
            self.collapsedChanged.emit(False)

    @property
    def is_collapsed(self) -> bool:
        return self._is_collapsed
