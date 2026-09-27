"""The lines and designs a sheet wears along its margins.

Word's *Page Borders* offers a choice of rule -- a single line, a double, a
shadow, a dashed or dotted line -- and a choice of design repeated along the
edge of the page. Both are drawn here from one description, so the sheet on
screen and the sheet that comes out of the printer wear the same border.

A border is measured in the painter's own pixels: the caller works out the box
it belongs to (screen pixels on screen, print pixels on paper) and this module
fills it in.
"""

from math import cos, hypot, sin, pi
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

#: How far the border stands off the writing, in centimetres of paper. Word's
#: own default is a couple of points outside the text, not at the paper's edge.
BORDER_SPACE_CM = 0.25

#: The colour a border is drawn in when the user has not chosen one.
DEFAULT_COLOUR = "#1F2937"

#: The weight of a border, in points, when none has been chosen.
DEFAULT_WIDTH_PT = 1.0

#: Every border on offer: the name the dialog shows, and how it is drawn.
#: ``line`` styles are a pen round the box; ``art`` designs are a glyph
#: repeated along it.
PAGE_BORDERS = {
    "none": ("None", "line", Qt.PenStyle.NoPen),
    "box": ("Box", "line", Qt.PenStyle.SolidLine),
    "double": ("Double", "double", None),
    "thick_thin": ("Thick and thin", "thick_thin", None),
    "dashed": ("Dashed", "line", Qt.PenStyle.DashLine),
    "dotted": ("Dotted", "line", Qt.PenStyle.DotLine),
    "shadow": ("Shadow", "shadow", None),
    "raised": ("3D raised", "raised", None),
    "sunken": ("3D sunken", "sunken", None),
    "stars": ("Stars", "art", "star"),
    "hearts": ("Hearts", "art", "heart"),
    "leaves": ("Leaves", "art", "leaf"),
    "diamonds": ("Diamonds", "art", "diamond"),
}

#: The borders the dialog lists, in Word's own order.
STYLE_ORDER = ("none", "box", "shadow", "raised", "sunken", "double",
               "thick_thin", "dashed", "dotted", "stars", "hearts", "leaves",
               "diamonds")

COLOURS = {
    "Black": "#1F2937", "Dark grey": "#4B5563", "Grey": "#9CA3AF",
    "Red": "#C00000", "Orange": "#ED7D31", "Yellow": "#FFC000",
    "Green": "#2E7D32", "Blue": "#2E75B6", "Purple": "#7030A0",
}


def border_painter(painter: QPainter, box: QRectF, style: str,
                   colour: str = DEFAULT_COLOUR, width_pt: float = DEFAULT_WIDTH_PT,
                   pixels_per_point: float = 1.0) -> None:
    """Draw the *style* of border round *box*, in the painter's own units.

    *width_pt* is Word's weight in points; *pixels_per_point* says how big a
    point is where this is being painted, so the same border weighs the same on
    the screen and on the paper.
    """
    kind = PAGE_BORDERS.get(style, PAGE_BORDERS["none"])[1]
    if style == "none" or box.width() <= 0 or box.height() <= 0:
        return
    wide = max(1.0, width_pt * pixels_per_point)
    pen_colour = QColor(colour)
    if kind == "line":
        pen = QPen(pen_colour, wide, PAGE_BORDERS[style][2])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)
    elif kind == "double":
        painter.setPen(QPen(pen_colour, wide))
        painter.drawRect(box)
        inner = box.adjusted(-(wide + 2), -(wide + 2), wide + 2, wide + 2)
        painter.drawRect(inner)
    elif kind == "thick_thin":
        painter.setPen(QPen(pen_colour, wide * 2.4))
        painter.drawRect(box)
        painter.setPen(QPen(pen_colour, wide))
        painter.drawRect(box.adjusted(-(wide * 2.4 + 1), -(wide * 2.4 + 1),
                                      wide * 2.4 + 1, wide * 2.4 + 1))
    elif kind in ("shadow", "raised", "sunken"):
        _bevel(painter, box, pen_colour, wide, kind)
    elif kind == "art":
        _art(painter, box, PAGE_BORDERS[style][2], pen_colour, wide)


def _bevel(painter: QPainter, box: QRectF, colour: QColor, wide: float,
           kind: str) -> None:
    """The three borders drawn as edges of light and shade rather than a rule."""
    painter.setPen(Qt.PenStyle.NoPen)
    if kind == "shadow":
        shade = QColor(colour)
        shade.setAlpha(120)
        painter.setBrush(shade)
        offset = wide * 2.5
        path = QPainterPath()
        path.addRect(box.adjusted(offset, offset, offset, offset))
        # Only the fringe the box leaves uncovered: a shadow does not tint the
        # page, it stands behind the rule.
        box_only = QPainterPath()
        box_only.addRect(box)
        painter.drawPath(path.subtracted(box_only))
        painter.setPen(QPen(colour, wide))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)
        return
    light = colour.lighter(180)
    dark = colour.darker(160)
    top_left, bottom_right = (light, dark) if kind == "raised" else (dark, light)
    painter.setPen(QPen(top_left, wide * 2))
    painter.drawLine(box.topLeft(), box.topRight())
    painter.drawLine(box.topLeft(), box.bottomLeft())
    painter.setPen(QPen(bottom_right, wide * 2))
    painter.drawLine(box.bottomRight(), box.bottomLeft())
    painter.drawLine(box.bottomRight(), box.topRight())


def _art(painter: QPainter, box: QRectF, glyph: str, colour: QColor,
         wide: float) -> None:
    """Repeat a small design along the edge of the page, as Word's art borders do.

    The glyphs march round the four sides at even spacing, and each stands
    upright against the side it decorates.
    """
    size = max(6.0, wide * 6.0)
    step = size * 1.6
    painter.setPen(QPen(colour, max(1.0, wide * 0.8)))
    painter.setBrush(colour)
    along = _path_points(box, step)
    for (point, angle) in along:
        painter.save()
        painter.translate(point)
        painter.rotate(angle)
        _glyph(painter, glyph, size)
        painter.restore()


def _path_points(box: QRectF, step: float) -> list:
    """Evenly spaced points round *box*, each with the turn that lays the glyph
    flat against the side it sits on."""
    sides = ((box.topLeft(), box.topRight(), 0.0),
             (box.topRight(), box.bottomRight(), 90.0),
             (box.bottomRight(), box.bottomLeft(), 180.0),
             (box.bottomLeft(), box.topLeft(), 270.0))
    points = []
    for (start, end, angle) in sides:
        vector = end - start
        length = hypot(vector.x(), vector.y()) or 1.0
        count = max(1, int(length // step))
        for index in range(count):
            along = (index + 0.5) * (length / count)
            points.append((start + QPointF(vector.x() * along / length,
                                           vector.y() * along / length), angle))
    return points


def _glyph(painter: QPainter, glyph: str, size: float) -> None:
    """One design, centred on the painter's origin and facing up."""
    half = size / 2.0
    if glyph == "star":
        path = QPainterPath()
        for index in range(10):
            radius = half if index % 2 == 0 else half * 0.42
            angle = pi / 2 + index * pi / 5
            point = QPointF(radius * cos(angle), -radius * sin(angle))
            if index:
                path.lineTo(point)
            else:
                path.moveTo(point)
        path.closeSubpath()
        painter.drawPath(path)
    elif glyph == "heart":
        path = QPainterPath()
        path.moveTo(0, half * 0.75)
        path.cubicTo(-half * 1.3, -half * 0.2, -half * 0.5, -half * 1.1,
                     0, -half * 0.35)
        path.cubicTo(half * 0.5, -half * 1.1, half * 1.3, -half * 0.2,
                     0, half * 0.75)
        painter.drawPath(path)
    elif glyph == "diamond":
        painter.drawPolygon([QPointF(0, -half), QPointF(half * 0.7, 0),
                             QPointF(0, half), QPointF(-half * 0.7, 0)])
    else:                                    # "leaf"
        path = QPainterPath()
        path.moveTo(0, half)
        path.cubicTo(half * 1.1, half * 0.2, half * 0.6, -half, 0, -half)
        path.cubicTo(-half * 0.6, -half, -half * 1.1, half * 0.2, 0, half)
        painter.drawPath(path)


def border_box(margin_px: float, printable_px: float, sheet_px: float,
               space_px: float, page_top: float) -> QRectF:
    """The rectangle a border is drawn in, on one sheet of a flowing page.

    It stands *space_px* outside the writing, which is how Word hangs its
    border on the text rather than on the edge of the paper.
    """
    inset = max(0.0, margin_px - space_px)
    return QRectF(inset, page_top + inset, printable_px + 2 * space_px,
                  max(0.0, sheet_px - 2 * inset))
