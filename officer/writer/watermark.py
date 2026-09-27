"""The mark a sheet wears behind its writing, on every page.

Word's *Watermark* sits beside Page Colour and Page Borders: a word or a picture
set lightly into the paper so that it shows through the writing without
competing with it. A text mark runs diagonally across the sheet by default, and
a picture is washed out to a fraction of its own strength.

Everything here is painted in the caller's units: the screen works in the
zoomed pixels a page is drawn at and the printer in the 300-dpi pixels a sheet
is laid out at, so both hand over the sizes they have already measured.
"""

from math import cos, radians, sin
from typing import Optional
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPen
from officer.writer.page_color import clamp_opacity

#: The three states a mark can be in, as Word's dialog radios name them.
MARK_KINDS = ("none", "text", "picture")

#: How Word lays the mark out: corner to corner, or straight across.
MARK_LAYOUTS = ("diagonal", "horizontal")

#: The grey Word sets a new text mark in: present without arguing with the ink.
DEFAULT_MARK_COLOUR = "#BFBFBF"

#: A mark is meant to be seen through, so it never arrives at full strength.
DEFAULT_MARK_OPACITY = 0.5

#: The point size Word's own DRAFT mark is drawn at, and where the box starts.
DEFAULT_MARK_SIZE_PT = 54
MIN_MARK_SIZE_PT = 8
MAX_MARK_SIZE_PT = 400

#: A picture mark covers this much of the sheet's width unless told otherwise.
DEFAULT_MARK_SCALE = 60

#: The inks Word's watermark gallery hands out.
MARK_COLOURS = ("#BFBFBF", "#D0CECE", "#808080", "#404040", "#111827",
                "#2E75B6", "#1F3864", "#2E7D32", "#FFC000", "#ED7D31",
                "#C00000", "#7030A0")

#: The marks Word's gallery offers before you write your own.
MARK_PRESETS = (
    ("CONFIDENTIAL", "CONFIDENTIAL"),
    ("DRAFT", "DRAFT"),
    ("SAMPLE", "SAMPLE"),
)

DEFAULT_WATERMARK = {
    "kind": "none",
    "text": "DRAFT",
    "family": "",
    "size_pt": DEFAULT_MARK_SIZE_PT,
    "colour": DEFAULT_MARK_COLOUR,
    "opacity": DEFAULT_MARK_OPACITY,
    "layout": "diagonal",
    "image_path": "",
    "scale": DEFAULT_MARK_SCALE,
}

#: How far a mark's own length may run before it is shrunk back onto the sheet.
MARK_FIT_RATIO = 0.92


def clamp_scale(value) -> int:
    """A picture mark's size as a percentage of the sheet: 5..100."""
    try:
        return min(100, max(5, int(round(float(value)))))
    except (TypeError, ValueError):
        return DEFAULT_MARK_SCALE


def watermark_mark(mark: Optional[dict] = None) -> dict:
    """A complete mark, with whatever *mark* leaves out taken as it came."""
    filled = dict(DEFAULT_WATERMARK)
    for key, value in (mark or {}).items():
        if key in filled and value is not None:
            filled[key] = value
    filled["opacity"] = clamp_opacity(filled["opacity"])
    filled["scale"] = clamp_scale(filled["scale"])
    filled["layout"] = (filled["layout"] if filled["layout"] in MARK_LAYOUTS
                        else "diagonal")
    try:
        filled["size_pt"] = min(MAX_MARK_SIZE_PT,
                                max(MIN_MARK_SIZE_PT, float(filled["size_pt"])))
    except (TypeError, ValueError):
        filled["size_pt"] = DEFAULT_MARK_SIZE_PT
    if filled["kind"] not in MARK_KINDS:
        filled["kind"] = "none"
    return filled


def mark_description(mark: dict) -> str:
    """What the sheet wears, in the words the ribbon's status line shows."""
    kind = mark.get("kind", "none")
    if kind == "text":
        text = str(mark.get("text", "")).strip()
        if not text:
            return "A mark with no words in it."
        return "A {} “{}”.".format(mark.get("layout"), text)
    if kind == "picture":
        name = str(mark.get("image_path", "")).rsplit("/", 1)[-1]
        share = int(mark.get("scale", DEFAULT_MARK_SCALE))
        return f"A picture, {share}% wide: {name}"
    return "No mark on the page."


def mark_angle(layout: str) -> float:
    """The turn a text mark takes: Word's diagonal climbs to the right."""
    return -45.0 if layout != "horizontal" else 0.0


def fit_font(text: str, family: str, size_px: float, span_px: float) -> QFont:
    """The largest face of *size_px* that lays *text* inside *span_px*.

    Word shrinks a mark that would run off the paper rather than cut it, and a
    long word set at 54 pt does exactly that: the size comes down a step at a
    time until the line fits.
    """
    font = QFont(family)
    size = max(1.0, size_px)
    font.setPixelSize(max(1, round(size)))
    while size > 4 and QFontMetricsF(font).horizontalAdvance(text) > span_px:
        size = max(4.0, size - max(1.0, size / 24.0))
        font.setPixelSize(round(size))
    return font


def paint_watermark(painter: QPainter, mark: dict, sheet: QRectF,
                    size_px: Optional[float] = None,
                    image: Optional[QImage] = None) -> bool:
    """Set the mark into *sheet*, and say whether anything was drawn.

    *size_px* is the mark's point size already measured in the painter's own
    units, which is the only way one function can serve a screen at 96 dpi and
    a printer at 300. A text mark that cannot be read as words, and a picture
    mark with no picture, draw nothing -- but they are not errors either, so a
    sheet simply comes out clean.
    """
    kind = mark.get("kind", "none")
    if kind not in ("text", "picture") or sheet.width() <= 0:
        return False
    painter.save()
    painter.setClipRect(sheet)
    painter.setOpacity(clamp_opacity(mark.get("opacity", DEFAULT_MARK_OPACITY)))
    drawn = False
    if kind == "picture":
        if image is not None and not image.isNull():
            drawn = _paint_picture_mark(painter, mark, sheet, image)
    else:
        text = str(mark.get("text", "")).strip()
        if text:
            drawn = _paint_text_mark(painter, mark, sheet, text, size_px or 0.0)
    painter.restore()
    return drawn


def _paint_picture_mark(painter: QPainter, mark: dict, sheet: QRectF,
                        image: QImage) -> bool:
    """Centre the picture on the sheet at its share of the page's width."""
    scale = clamp_scale(mark.get("scale", DEFAULT_MARK_SCALE)) / 100.0
    wide = sheet.width() * scale
    if image.width() <= 0:
        return False
    tall = wide * image.height() / image.width()
    box = QRectF(sheet.center().x() - wide / 2.0,
                 sheet.center().y() - tall / 2.0, wide, tall)
    painter.drawImage(box, image)
    return True


def _paint_text_mark(painter: QPainter, mark: dict, sheet: QRectF, text: str,
                     size_px: float) -> bool:
    """Turn the sheet's centre and write the mark across it."""
    angle = mark_angle(mark.get("layout", "diagonal"))
    # The room a line has when it lies along the mark's own direction: the
    # sheet's width and height both contribute to a diagonal's run.
    span = (abs(sheet.width() * cos(radians(angle)))
            + abs(sheet.height() * sin(radians(angle)))) * MARK_FIT_RATIO
    font = fit_font(text, str(mark.get("family") or ""),
                    max(1.0, size_px), span)
    painter.translate(sheet.center())
    painter.rotate(angle)
    painter.setFont(font)
    painter.setPen(QPen(QColor(mark.get("colour") or DEFAULT_MARK_COLOUR)))
    height = QFontMetricsF(font).height()
    painter.drawText(QRectF(-span / 2.0, -height / 2.0, span, height),
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                     text)
    return True
