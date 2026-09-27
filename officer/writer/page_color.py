"""The colour or picture a sheet is filled with, behind the writing.

Word's *Page Color* dresses the paper itself rather than its margins: a solid
ink, or a picture stretched over the sheet and faded so that the writing still
reads on top of it. Both come from one description, so the sheet on screen and
the sheet that goes to the printer are dressed the same way.

Unlike the border, which stands off in the margins and is painted over the
writing, a fill belongs underneath every word -- so the caller lays it down
before the document is drawn.
"""

from typing import Optional
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

#: The paper before the user dresses it: the white of a Word sheet.
DEFAULT_PAGE_COLOUR = "#FFFFFF"

#: How strongly a picture shows through when none has been set. Half lets a
#: page of black writing stay readable over almost any photograph.
DEFAULT_OPACITY = 0.5

#: The three states the page can be in.
FILL_KINDS = ("none", "solid", "picture")

#: The inks Word's Page Colour gallery opens with.
PAGE_COLOURS = {
    "No colour": "none",
    "White": "#FFFFFF",
    "Light grey": "#F3F4F6",
    "Grey": "#D1D5DB",
    "Dark grey": "#6B7280",
    "Black": "#111827",
    "Blue": "#2E75B6",
    "Dark blue": "#1F3864",
    "Teal": "#1F9E9E",
    "Green": "#2E7D32",
    "Yellow": "#FFC000",
    "Orange": "#ED7D31",
    "Red": "#C00000",
    "Purple": "#7030A0",
    "Pink": "#E91E63",
    "Brown": "#7F5539",
}


def clamp_opacity(value) -> float:
    """An opacity always lands between a hint of the picture and all of it."""
    try:
        return min(1.0, max(0.1, float(value)))
    except (TypeError, ValueError):
        return DEFAULT_OPACITY


def load_picture(path: str) -> Optional[QImage]:
    """The picture at *path*, or nothing when it cannot be read."""
    if not path:
        return None
    image = QImage(path)
    if image.isNull():
        return None
    return image


def cover_box(image: QImage, box: QRectF) -> QRectF:
    """Where *image* must go, at its own ratio, to cover *box*.

    Cover rather than fit: a page dressed with a picture has no white gaps
    along an edge, even when the photo is a different shape than the sheet.
    """
    if image.width() <= 0 or image.height() <= 0:
        return box
    scale = max(box.width() / image.width(), box.height() / image.height())
    wide = image.width() * scale
    tall = image.height() * scale
    return QRectF(box.left() + (box.width() - wide) / 2.0,
                  box.top() + (box.height() - tall) / 2.0, wide, tall)


def paint_page_fill(painter: QPainter, fill: dict, box: QRectF,
                    image: Optional[QImage] = None) -> None:
    """Dress one sheet of paper, in the painter's own units.

    *box* is that sheet as the painter sees it; *image* is the already-loaded
    picture, which the caller keeps so that no scroll has to read the disk.
    """
    kind = fill.get("kind", "none")
    if kind not in ("solid", "picture") or box.width() <= 0 or box.height() <= 0:
        return
    painter.save()
    painter.setClipRect(box)
    if kind == "picture":
        if image is None or image.isNull():
            painter.restore()
            return
        painter.setOpacity(clamp_opacity(fill.get("opacity", DEFAULT_OPACITY)))
        painter.drawImage(cover_box(image, box), image)
    else:
        painter.fillRect(box, QColor(fill.get("colour") or DEFAULT_PAGE_COLOUR))
    painter.restore()
