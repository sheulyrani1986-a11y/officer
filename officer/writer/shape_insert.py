"""Shape rendering utility for WriteR.

Draws vector shapes via QPainter → temporary PNG files that can be inserted
into the document as inline images.

Supported shape types:
    rectangle, rounded_rectangle, ellipse, triangle, diamond, star, arrow,
    double_arrow, callout, line
"""

import math
import os
import tempfile
from typing import Optional

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPolygonF, QImage, QPainterPath
)

#: The size each shape lands on the page at, in centimetres. Word gives a line
#: and a block arrow very different boxes, and an inserted shape that is a
#: 120-pixel square makes every one of them look like a sticker.
SHAPE_SIZES_CM = {
    "rectangle": (6.0, 4.0),
    "rounded_rectangle": (6.0, 4.0),
    "ellipse": (5.0, 5.0),
    "triangle": (5.0, 4.4),
    "diamond": (5.0, 5.0),
    "star": (5.0, 5.0),
    "arrow": (7.5, 2.5),
    "double_arrow": (7.5, 2.5),
    "callout": (7.0, 4.5),
    "line": (9.0, 0.6),
}

#: How much bigger than the printed size the PNG is drawn, so a shape stays
#: crisp when the page is zoomed in.
SUPERSAMPLE = 3


def render_shape_to_temp(
    shape_type: str,
    width_cm: float = 6.0,
    height_cm: float = 4.0,
    fill: str = "#5B8CCC",
    stroke: str = "#1E40AF",
    stroke_width: int = 2,
) -> Optional[str]:
    """Render *shape_type* at *width_cm* x *height_cm* into a temporary PNG.

    The file comes out larger than it prints (:data:`SUPERSAMPLE`), so the
    caller must state the printed size when it inserts the image. Returns
    ``None`` when the shape cannot be drawn.
    """
    from officer.writer.document_view import PX_PER_CM

    edge = max(1, stroke_width * 2)
    wide = max(1, int(round(width_cm * PX_PER_CM * SUPERSAMPLE)))
    tall = max(1, int(round(height_cm * PX_PER_CM * SUPERSAMPLE)))
    img = QImage(wide + edge, tall + edge, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(0, 0, 0, 0))  # transparent background

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    pen = QPen(QColor(stroke))
    # The stroke is scaled with the rest, or a shape printed small would lose it.
    pen.setWidth(max(1, int(round(stroke_width * SUPERSAMPLE))))
    painter.setPen(pen)
    painter.setBrush(QBrush(QColor(fill)))

    try:
        _draw_shape(painter, shape_type, edge, edge, wide, tall)
    except Exception:
        painter.end()
        return None

    painter.end()

    tmp = tempfile.NamedTemporaryFile(
        suffix=".png", delete=False, prefix=f"officer_shape_{shape_type}_"
    )
    img.save(tmp.name)
    return tmp.name


def _draw_shape(
    painter: QPainter,
    shape_type: str,
    x: int,
    y: int,
    w: int,
    h: int,
) -> None:
    st = shape_type.lower().replace("-", "_")

    if st == "rectangle":
        painter.drawRect(x, y, w, h)

    elif st in ("rounded_rectangle", "rounded"):
        painter.drawRoundedRect(x, y, w, h, 14, 14)

    elif st == "ellipse":
        painter.drawEllipse(x, y, w, h)

    elif st == "triangle":
        poly = QPolygonF([
            QPointF(x + w / 2, y),
            QPointF(x + w, y + h),
            QPointF(x, y + h),
        ])
        painter.drawPolygon(poly)

    elif st == "diamond":
        poly = QPolygonF([
            QPointF(x + w / 2, y),
            QPointF(x + w, y + h / 2),
            QPointF(x + w / 2, y + h),
            QPointF(x, y + h / 2),
        ])
        painter.drawPolygon(poly)

    elif st == "star":
        path = QPainterPath()
        cx, cy = x + w / 2, y + h / 2
        outer_r = min(w, h) / 2
        inner_r = outer_r * 0.4
        points = 5
        for i in range(points * 2):
            angle = math.pi / points * i - math.pi / 2
            r = outer_r if i % 2 == 0 else inner_r
            px_pt = cx + r * math.cos(angle)
            py_pt = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(px_pt, py_pt)
            else:
                path.lineTo(px_pt, py_pt)
        path.closeSubpath()
        painter.drawPath(path)

    elif st in ("arrow", "double_arrow"):
        # Right-pointing arrow; the double-headed one mirrors the head.
        shaft_h = h // 3
        shaft_y = y + h // 2 - shaft_h // 2
        head_w = w // 3
        left = x + (head_w if st == "double_arrow" else 0)
        path = QPainterPath()
        path.moveTo(left, shaft_y)
        path.lineTo(x + w - head_w, shaft_y)
        path.lineTo(x + w - head_w, y)
        path.lineTo(x + w, y + h / 2)
        path.lineTo(x + w - head_w, y + h)
        path.lineTo(x + w - head_w, shaft_y + shaft_h)
        path.lineTo(left, shaft_y + shaft_h)
        if st == "double_arrow":
            path.lineTo(left, y + h)
            path.lineTo(x, y + h / 2)
            path.lineTo(left, y)
        path.closeSubpath()
        painter.drawPath(path)

    elif st == "callout":
        # Rounded rect with a small tail
        path = QPainterPath()
        path.addRoundedRect(x, y, w, int(h * 0.75), 10, 10)
        # Tail
        tail_x = x + w // 4
        path.moveTo(tail_x, y + int(h * 0.75))
        path.lineTo(tail_x - w // 12, y + h)
        path.lineTo(tail_x + w // 8, y + int(h * 0.75))
        painter.drawPath(path)

    elif st == "line":
        painter.drawLine(x, y + h // 2, x + w, y + h // 2)

    else:
        # Fallback: rectangle
        painter.drawRect(x, y, w, h)
