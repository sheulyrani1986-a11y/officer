"""Word's *Page Color* dialog: what the paper itself is dressed with.

A solid ink, or a picture stretched over the sheet and faded until the writing
on it reads again. The dialog changes nothing on its own: it answers with the
fill the user chose, and the window hands that to the page -- which paints it
under every word and passes it to the printer.
"""

from typing import Optional
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (QColorDialog, QDialog, QDialogButtonBox,
                               QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QSlider, QToolButton, QVBoxLayout,
                               QWidget)
from officer.writer.page_color import (DEFAULT_OPACITY, DEFAULT_PAGE_COLOUR,
                                       PAGE_COLOURS, load_picture,
                                       paint_page_fill)

#: The image files a page can be dressed with.
PICTURE_FILTER = "Pictures (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)"


class PageColorPreview(QWidget):
    """A miniature sheet, dressed as the choice would dress it."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.fill = {"kind": "none", "colour": DEFAULT_PAGE_COLOUR,
                     "image_path": "", "opacity": DEFAULT_OPACITY}
        self.image: Optional[QImage] = None
        self.setMinimumSize(160, 200)

    def show_fill(self, fill: dict, image: Optional[QImage]) -> None:
        self.fill = dict(fill)
        self.image = image
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        sheet = QRectF(self.rect()).adjusted(14, 14, -14, -14)
        painter.setPen(QPen(QColor("#D1D5DB"), 1))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRect(sheet)
        paint_page_fill(painter, self.fill, sheet, self.image)
        # Real writing over the dress: this is the decision the opacity slider
        # exists for, so the preview has to show it.
        writing = sheet.adjusted(sheet.width() * 0.14, sheet.height() * 0.12,
                                 -sheet.width() * 0.14, -sheet.height() * 0.12)
        painter.setPen(QColor("#1F2937"))
        for row in range(7):
            y = writing.top() + (writing.height() / 8) * (row + 1)
            painter.drawLine(QPointF(writing.left(), y),
                             QPointF(writing.right() - (row % 3) * 12, y))
        painter.end()


class PageColorDialog(QDialog):
    """Choose what the paper is dressed with: no colour, an ink, or a picture."""

    def __init__(self, fill: Optional[dict] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        fill = fill or {}
        self.setWindowTitle("Page Color")
        self.resize(680, 430)
        self._image = load_picture(fill.get("image_path", ""))
        self._fill = {
            "kind": fill.get("kind", "none"),
            "colour": fill.get("colour", DEFAULT_PAGE_COLOUR),
            "image_path": fill.get("image_path", ""),
            "opacity": fill.get("opacity", DEFAULT_OPACITY),
        }

        outer = QHBoxLayout(self)
        outer.addWidget(self._build_choices(), 3)
        right = QVBoxLayout()
        self.preview = PageColorPreview(self)
        right.addWidget(self.preview, 3)
        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        right.addWidget(self.summary)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel,
                                   parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)
        outer.addLayout(right, 2)

        self._refresh()

    # -- the choices ------------------------------------------------------- #

    def _build_choices(self) -> QWidget:
        box = QWidget(self)
        column = QVBoxLayout(box)

        column.addWidget(QLabel("Theme Colours:", box))
        self._swatches = {}
        rows = QVBoxLayout()
        row: Optional[QHBoxLayout] = None
        swatches = [(name, hex_value) for name, hex_value in PAGE_COLOURS.items()
                    if hex_value != "none"]
        for index, (name, hex_value) in enumerate(swatches):
            if index % 8 == 0:
                row = QHBoxLayout()
                rows.addLayout(row)
            tile = QToolButton(box)
            tile.setCheckable(True)
            tile.setAutoRaise(True)
            tile.setFixedSize(30, 30)
            tile.setToolTip(name)
            tile.setAccessibleName(name)
            tile.setStyleSheet(
                f"QToolButton {{ background: {hex_value}; "
                "border: 1px solid #9CA3AF; } }")
            tile.clicked.connect(lambda _=False, c=hex_value: self._choose_solid(c))
            row.addWidget(tile)
            self._swatches[hex_value.lower()] = tile
        column.addLayout(rows)

        actions = QHBoxLayout()
        self.no_colour = QPushButton("No Colour", box)
        self.no_colour.clicked.connect(lambda: self._choose_kind("none"))
        actions.addWidget(self.no_colour)
        self.more_colours = QPushButton("More Colours…", box)
        self.more_colours.clicked.connect(self._more_colours)
        actions.addWidget(self.more_colours)
        self.picture = QPushButton("Picture…", box)
        self.picture.clicked.connect(self._choose_picture)
        actions.addWidget(self.picture)
        for button in (self.no_colour, self.more_colours, self.picture):
            # The Office theme pads a button generously; three of them in a
            # row need the room or the middle name loses its first letters.
            button.setMinimumWidth(140)
        actions.addStretch(1)
        column.addLayout(actions)

        fade = QHBoxLayout()
        fade.addWidget(QLabel("Picture opacity:", box))
        self.opacity = QSlider(Qt.Orientation.Horizontal, box)
        self.opacity.setRange(10, 100)
        self.opacity.valueChanged.connect(
            lambda value: self._choose_opacity(value / 100.0))
        fade.addWidget(self.opacity, 1)
        self.opacity_value = QLabel(box)
        self.opacity_value.setFixedWidth(42)
        fade.addWidget(self.opacity_value)
        column.addLayout(fade)
        column.addStretch(1)
        return box

    # -- answers ------------------------------------------------------------ #

    def _choose_solid(self, colour: str) -> None:
        self._fill["kind"] = "solid"
        self._fill["colour"] = colour
        self._refresh()

    def _choose_kind(self, kind: str) -> None:
        self._fill["kind"] = kind
        self._refresh()

    def _choose_opacity(self, opacity: float) -> None:
        self._fill["opacity"] = opacity
        self._refresh()

    def _more_colours(self) -> None:
        colour = QColorDialog.getColor(QColor(self._fill["colour"]), self,
                                       "Page Color")
        if colour.isValid():
            self._choose_solid(colour.name())

    def _choose_picture(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Picture for Page", "",
                                             PICTURE_FILTER)
        if not path:
            return
        image = load_picture(path)
        if image is None:
            QMessageBox.warning(self, "Picture for Page",
                                f"{path} could not be read as a picture.")
            return
        self._image = image
        self._fill["image_path"] = path
        self._choose_kind("picture")

    def _refresh(self) -> None:
        for key, tile in self._swatches.items():
            tile.setChecked(self._fill["kind"] == "solid"
                            and self._fill["colour"].lower() == key)
        percent = int(round(float(self._fill["opacity"]) * 100))
        self.opacity.blockSignals(True)
        self.opacity.setValue(max(10, min(100, percent)))
        self.opacity.blockSignals(False)
        self.opacity_value.setText(f"{self.opacity.value()}%")
        self.opacity.setEnabled(self._fill["kind"] == "picture")
        self.opacity_value.setEnabled(self._fill["kind"] == "picture")
        self.preview.show_fill(self._fill, self._image)
        kind = self._fill["kind"]
        if kind == "picture":
            name = self._fill["image_path"].rsplit("/", 1)[-1]
            self.summary.setText(f"A picture, {self.opacity.value()}% strong: "
                                 f"{name}")
        elif kind == "solid":
            self.summary.setText(f"Solid {self._fill['colour']}")
        else:
            self.summary.setText("Plain paper, as it came.")

    def colour(self) -> dict:
        """The chosen dress, in the shape the page and the printer want."""
        return dict(self._fill)
