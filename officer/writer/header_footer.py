"""The bands a sheet wears above and below its column of writing.

Word's *Header & Footer* is one line of paper at the top of every page and one
at the bottom, each carrying what the writer wants in three places: against the
left margin, in the middle, and against the right. Page numbers are not typed
but asked for, so that a sheet prints its own place in the document; ``{PAGE}``
and ``{PAGES}`` stand for the sheet's number and the document's length.

Like the border and the page's dress, the bands are painted rather than written:
they belong to the paper, not to the paragraph, so the same sheet of them goes
on every page both on screen and under the printer.
"""

from typing import Optional, Tuple
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen

#: Where each band sits: Word measures both 1.27 cm (half an inch) from the
#: edge of the paper, and keeps a breath of air from the writing.
BAND_EDGE_CM = 1.27
BAND_GAP_CM = 0.18

#: The size and ink a band is set in, so it never competes with the body.
BAND_POINT_SIZE = 10
BAND_COLOUR = "#1F2937"

#: The three places a band can put words, and the two bands a sheet wears.
BAND_SIDES = ("left", "centre", "right")
BAND_KINDS = ("header", "footer")

#: The fields a band carries, as Word's ribbon labels them.
PAGE_FIELD = "{PAGE}"
TOTAL_FIELD = "{PAGES}"
FIELDS = (PAGE_FIELD, TOTAL_FIELD)


def default_bands() -> dict:
    """A document as it comes: no words in either band, both on the first page."""
    return {"header": {side: "" for side in BAND_SIDES},
            "footer": {side: "" for side in BAND_SIDES},
            "show_first_page": True}


def bands_setting(bands: Optional[dict]) -> dict:
    """A complete pair of bands, with whatever *bands* leaves out as it came."""
    filled = default_bands()
    for key, value in (bands or {}).items():
        if key == "show_first_page":
            filled[key] = bool(value)
        elif key in BAND_KINDS and isinstance(value, dict):
            for side in BAND_SIDES:
                if value.get(side) is not None:
                    filled[key][side] = str(value[side])
    return filled


def has_bands(bands: dict) -> bool:
    """Whether either band has anything to say."""
    return any(str(bands.get(kind, {}).get(side, "")).strip()
               for kind in BAND_KINDS for side in BAND_SIDES)


def resolve_fields(text: str, page: int, total: int) -> str:
    """*text* with the page-number fields replaced by the numbers themselves.

    A sheet does not know its own place in the document until the whole of it
    has been laid out, so the fields travel as words and are read only when the
    band is drawn.
    """
    return (text.replace(PAGE_FIELD, str(page))
            .replace(TOTAL_FIELD, str(total)))


def band_texts(bands: dict, kind: str, page: int, total: int) -> dict:
    """One band's three places, with their fields answered.

    *page* and *total* count from one. A document's first sheet wears the same
    bands as the rest unless the writer has taken them off it.
    """
    band = bands.get(kind, {})
    return {side: resolve_fields(str(band.get(side, "")), page, total)
            for side in BAND_SIDES}


def band_rects(sheet: QRectF, margin_px: float, line_px: float,
               edge_px: float, gap_px: float) -> Tuple[QRectF, QRectF]:
    """Where the two bands lie on *sheet*, in the painter's own units.

    Word puts them half an inch from the edge of the paper; a sheet whose
    margins are thinner than that cannot hold them clear of the writing, so the
    band is brought in against the margin instead. Nothing is ever laid over
    the words.
    """
    column = max(1.0, sheet.width() - 2 * margin_px)
    room = max(0.0, margin_px - line_px - gap_px)
    stand = min(edge_px, room)
    header = QRectF(sheet.left() + margin_px, sheet.top() + stand,
                    column, line_px)
    footer = QRectF(sheet.left() + margin_px,
                    sheet.bottom() - stand - line_px, column, line_px)
    return header, footer


def paint_band(painter: QPainter, texts: dict, rect: QRectF) -> None:
    """Write one band's words into *rect*, each in its own place."""
    for side, align in (("left", Qt.AlignmentFlag.AlignLeft),
                        ("centre", Qt.AlignmentFlag.AlignHCenter),
                        ("right", Qt.AlignmentFlag.AlignRight)):
        text = texts.get(side, "")
        if not text.strip():
            continue
        box = QRectF(rect)
        if side == "left":
            box.setRight(rect.center().x())
        elif side == "right":
            box.setLeft(rect.center().x())
        painter.drawText(box, align | Qt.AlignmentFlag.AlignVCenter, text)


def paint_page_bands(painter: QPainter, bands: dict, sheet: QRectF, page: int,
                     total: int, font: QFont, margin_px: float,
                     px_per_cm: float) -> bool:
    """Set both bands on one sheet, and say whether anything was drawn.

    *font* is the band's face already measured in the painter's own units --
    which is what lets a screen at 96 to the inch and a printer at 300 ask for
    the same half-inch of paper and each get it.
    """
    if not has_bands(bands):
        return False
    if page == 1 and not bands.get("show_first_page", True):
        return False
    line_px = QFontMetricsF(font).height()
    header, footer = band_rects(sheet, margin_px, line_px,
                                BAND_EDGE_CM * px_per_cm,
                                BAND_GAP_CM * px_per_cm)
    painter.save()
    painter.setFont(font)
    painter.setPen(QPen(QColor(BAND_COLOUR)))
    paint_band(painter, band_texts(bands, "header", page, total), header)
    paint_band(painter, band_texts(bands, "footer", page, total), footer)
    painter.restore()
    return True
