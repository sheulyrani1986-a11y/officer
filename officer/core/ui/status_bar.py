"""Office status strip: document metrics, view-mode buttons and zoom control."""

from typing import Iterable, Optional, Sequence, Tuple
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtWidgets import (
    QStatusBar, QWidget, QHBoxLayout, QLabel, QSlider, QToolButton,
    QButtonGroup, QSizePolicy, QFrame
)
from officer.core.ui.icons import IconProvider

#: (key, label, tooltip, icon name, callback). *key* is what
#: :meth:`OfficeStatusBar.select_view_mode` looks up, so it must be unique.
#: An empty *key* makes the entry a plain command rather than a view toggle:
#: PowerPoint's status strip ends with one "Slide Show" button that never stays
#: pressed, and it must not steal the checked state from the real views.
ViewMode = Tuple[str, str, str, str, object]


class OfficeStatusBar(QStatusBar):
    """
    The strip along the bottom of an Office window: plain text metrics on the
    left, then the view-mode toggles, the zoom slider and the zoom percent.
    """

    zoomChanged = Signal(int)  # Zoom percentage

    def __init__(self, parent: Optional[QWidget] = None,
                 zoom_range: Sequence[int] = (10, 400)):
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        self.setFixedHeight(26)
        self._zoom_range = tuple(zoom_range)
        self._home_info = "Ready"
        self._message_token = 0

        # --- Left: document metrics --------------------------------------- #
        self.info_label = QLabel("Ready", self)
        self.info_label.setObjectName("StatusInfo")
        self.info_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                      QSizePolicy.Policy.Preferred)
        self.info_label.setMinimumWidth(160)
        self.addWidget(self.info_label, 1)

        self.stats_label = QLabel("", self)
        self.stats_label.setObjectName("StatusStats")
        self.addWidget(self.stats_label)

        # --- Right: view modes + zoom ------------------------------------- #
        self.right_container = QWidget(self)
        right_layout = QHBoxLayout(self.right_container)
        right_layout.setContentsMargins(0, 1, 6, 1)
        right_layout.setSpacing(4)

        self.view_group = QButtonGroup(self.right_container)
        self.view_group.setExclusive(True)
        self._mode_buttons: dict = {}
        self.view_bar = QWidget(self.right_container)
        self.view_layout = QHBoxLayout(self.view_bar)
        self.view_layout.setContentsMargins(0, 0, 0, 0)
        self.view_layout.setSpacing(1)
        right_layout.addWidget(self.view_bar)

        self.zoom_out_btn = self._zoom_button("−", "Zoom Out")
        self.zoom_out_btn.clicked.connect(self._zoom_step_down)
        right_layout.addWidget(self.zoom_out_btn)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal, self.right_container)
        self.zoom_slider.setRange(*self._zoom_range)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(110)
        self.zoom_slider.setTickPosition(QSlider.TickPosition.NoTicks)
        self.zoom_slider.valueChanged.connect(self._on_slider_changed)
        right_layout.addWidget(self.zoom_slider)

        self.zoom_in_btn = self._zoom_button("+", "Zoom In")
        self.zoom_in_btn.clicked.connect(self._zoom_step_up)
        right_layout.addWidget(self.zoom_in_btn)

        self.zoom_label = QLabel("100%", self.right_container)
        self.zoom_label.setObjectName("ZoomLabel")
        self.zoom_label.setFixedWidth(38)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.zoom_label.setToolTip("Zoom level")
        right_layout.addWidget(self.zoom_label)

        self.addPermanentWidget(self.right_container)

    # -- construction helpers ---------------------------------------------- #

    def _zoom_button(self, text: str, tooltip: str) -> QToolButton:
        btn = QToolButton(self.right_container)
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setFixedSize(20, 20)
        btn.setCursor(Qt.CursorShape.ArrowCursor)
        return btn

    def set_view_modes(self, modes: Iterable[ViewMode]) -> None:
        """Replace the view-mode toggles (Print Layout / Normal / Slide Sorter...)."""
        while self.view_layout.count():
            item = self.view_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                self.view_group.removeButton(widget)
                widget.deleteLater()

        self._mode_buttons = {}
        for index, (key, label, tooltip, icon_name, callback) in enumerate(modes):
            btn = QToolButton(self.view_bar)
            btn.setObjectName("ViewModeButton")
            btn.setCheckable(True)
            btn.setAutoRaise(True)
            btn.setCursor(Qt.CursorShape.ArrowCursor)
            btn.setToolTip(tooltip or label)
            icon = IconProvider.get_icon(icon_name, size=16)
            if icon is not None and not icon.isNull():
                btn.setIcon(icon)
                btn.setIconSize(QSize(16, 16))
            else:
                btn.setText(label)
            btn.setCheckable(bool(key))
            btn.setChecked(index == 0 and bool(key))
            if callback:
                btn.clicked.connect(lambda checked=False, cb=callback: cb())
            if not key:
                # A command, not a view: divide it from the toggle group the way
                # PowerPoint puts a hairline before its Slide Show button.
                if self.view_layout.count():
                    divider = QFrame(self.view_bar)
                    divider.setFrameShape(QFrame.Shape.VLine)
                    divider.setFrameShadow(QFrame.Shadow.Sunken)
                    self.view_layout.addWidget(divider)
                self.view_layout.addWidget(btn)
                continue
            self.view_group.addButton(btn)
            self.view_layout.addWidget(btn)
            self._mode_buttons[key] = btn

    def select_view_mode(self, key: str) -> None:
        """Check the status-strip toggle for a view mode chosen elsewhere."""
        btn = self._mode_buttons.get(key)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    # -- content ----------------------------------------------------------- #

    def set_info(self, text: str) -> None:
        """The permanent left readout (Excel's "Sheet1" cell)."""
        self._home_info = text
        self.info_label.setText(text)
        super().showMessage("")

    def set_stats(self, text: str) -> None:
        self.stats_label.setText(text)

    def showMessage(self, text: str, timeout: int = 0) -> None:
        """
        Show a transient message the way Excel does: in the left readout, which
        reverts after *timeout* ms. QStatusBar's own temporary message paints
        over the labels instead of replacing them, so it is never used here.
        """
        if not text:
            self.set_info(self._home_info)
            return
        self.info_label.setText(text)
        self._message_token += 1
        if timeout > 0:
            token = (text, self._message_token + 1)
            self._message_token = token[1]
            QTimer.singleShot(timeout, lambda: self._revert_message(token[0], token[1]))

    def _revert_message(self, text: str, token: int) -> None:
        if token == self._message_token and self.info_label.text() == text:
            self.info_label.setText(self._home_info)

    # -- zoom -------------------------------------------------------------- #

    def set_zoom_range(self, low: int, high: int, value: int = 100) -> None:
        self._zoom_range = (low, high)
        self.zoom_slider.setRange(low, high)
        self.set_zoom(value)

    def zoom_percent(self) -> int:
        return self.zoom_slider.value()

    def set_zoom(self, percent: int) -> None:
        percent = max(self._zoom_range[0], min(self._zoom_range[1], percent))
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(percent)
        self.zoom_slider.blockSignals(False)
        self.zoom_label.setText(f"{percent}%")
        self.zoomChanged.emit(percent)

    def _on_slider_changed(self, value: int) -> None:
        self.zoom_label.setText(f"{value}%")
        self.zoomChanged.emit(value)

    def _zoom_step_up(self) -> None:
        self.set_zoom(self.zoom_slider.value() + 10)

    def _zoom_step_down(self) -> None:
        self.set_zoom(self.zoom_slider.value() - 10)
