"""Word's *Page Borders* dialog: the lines and designs a sheet wears.

The dialog changes nothing on its own. It answers with the border the user
picked, and the window hands that to the page -- which paints it on every sheet
on screen and passes it to the printer.
"""

from typing import Optional
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFormLayout, QHBoxLayout,
                               QListWidget, QListWidgetItem, QVBoxLayout, QWidget)
from officer.writer.page_border import (COLOURS, DEFAULT_COLOUR,
                                        DEFAULT_WIDTH_PT, PAGE_BORDERS,
                                        STYLE_ORDER, border_painter)


class BorderPreview(QWidget):
    """A miniature sheet, wearing the border as it is being chosen."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.style = "none"
        self.colour = DEFAULT_COLOUR
        self.width_pt = DEFAULT_WIDTH_PT
        self.setMinimumSize(160, 200)

    def show_border(self, style: str, colour: str, width_pt: float) -> None:
        self.style = style
        self.colour = colour
        self.width_pt = width_pt
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        sheet = QRectF(self.rect()).adjusted(14, 14, -14, -14)
        painter.setPen(QPen(QColor("#D1D5DB"), 1))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRect(sheet)
        # A few grey lines stand in for the writing, so that the border can be
        # seen standing off it rather than off the paper.
        writing = sheet.adjusted(sheet.width() * 0.14, sheet.height() * 0.12,
                                 -sheet.width() * 0.14, -sheet.height() * 0.12)
        painter.setPen(QColor("#9CA3AF"))
        for row in range(7):
            y = writing.top() + (writing.height() / 8) * (row + 1)
            painter.drawLine(QPointF(writing.left(), y),
                             QPointF(writing.right() - (row % 3) * 12, y))
        box = writing.adjusted(-6, -6, 6, 6)
        border_painter(painter, box, self.style, self.colour, self.width_pt,
                       pixels_per_point=0.6)
        painter.end()


class PageBorderDialog(QDialog):
    """Choose a border for the sheet: its style, its colour and its weight."""

    def __init__(self, border: Optional[dict] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        border = border or {}
        self.setWindowTitle("Page Borders")
        self.resize(520, 420)
        outer = QHBoxLayout(self)

        self.styles = QListWidget(self)
        for key in STYLE_ORDER:
            item = QListWidgetItem(PAGE_BORDERS[key][0], self.styles)
            item.setData(Qt.ItemDataRole.UserRole, key)
        outer.addWidget(self.styles, 2)

        right = QVBoxLayout()
        self.preview = BorderPreview(self)
        right.addWidget(self.preview, 3)
        form = QFormLayout()
        self.colour_box = QComboBox(self)
        for name, hex_value in COLOURS.items():
            self.colour_box.addItem(name, hex_value)
        form.addRow("Colour:", self.colour_box)
        self.width_box = QDoubleSpinBox(self)
        self.width_box.setRange(0.25, 12.0)
        self.width_box.setDecimals(2)
        self.width_box.setSingleStep(0.25)
        self.width_box.setSuffix(" pt")
        form.addRow("Weight:", self.width_box)
        right.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel,
                                   parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)
        outer.addLayout(right, 3)

        self.styles.setCurrentRow(next(
            (i for i, key in enumerate(STYLE_ORDER)
             if key == border.get("style", "none")), 0))
        index = self.colour_box.findData(border.get("colour", DEFAULT_COLOUR))
        self.colour_box.setCurrentIndex(max(0, index))
        self.width_box.setValue(float(border.get("width_pt", DEFAULT_WIDTH_PT)))

        self.styles.currentItemChanged.connect(self._refresh)
        self.colour_box.currentIndexChanged.connect(self._refresh)
        self.width_box.valueChanged.connect(self._refresh)
        self._refresh()

    def _style(self) -> str:
        item = self.styles.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else "none"

    def _refresh(self) -> None:
        self.preview.show_border(self._style(), self.colour_box.currentData(),
                                 self.width_box.value())

    def border(self) -> dict:
        """The chosen border, in the shape the page and the printer want."""
        return {"style": self._style(),
                "colour": self.colour_box.currentData(),
                "width_pt": self.width_box.value()}
