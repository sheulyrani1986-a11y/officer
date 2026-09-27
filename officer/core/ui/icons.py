"""Vector icon provider and application branding for OfficeR."""

import os
import sys
from typing import Dict, Optional
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QPainterPath, QColor, QPen, QBrush, QFont


class IconProvider:
    """Provides crisp vector icons rendered at requested size and color, and app logo."""

    _cache: Dict[str, QIcon] = {}
    _app_icon: Optional[QIcon] = None

    @classmethod
    def get_app_icon(cls) -> QIcon:
        """Returns the official OfficeR Gothic 'R' application icon."""
        if cls._app_icon is not None:
            return cls._app_icon

        if getattr(sys, "frozen", False):
            # A packaged build keeps its pictures in the bundle's data folder,
            # where no module's __file__ points.
            root = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.argv[0])))
            logo_path = os.path.join(root, "assets", "logo.png")
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            logo_path = os.path.join(base_dir, "assets", "logo.png")
        if os.path.exists(logo_path):
            cls._app_icon = QIcon(logo_path)
        else:
            cls._app_icon = cls.get_icon("new", color="#2563EB", size=64)
        return cls._app_icon

    @classmethod
    def get_icon(cls, name: str, color: str = "#374151", size: int = 24) -> QIcon:
        cache_key = f"{name}_{color}_{size}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        qcolor = QColor(color)
        pen = QPen(qcolor, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        w = float(size)
        h = float(size)
        pad = w * 0.15

        if name == "new":
            path = QPainterPath()
            path.moveTo(pad, pad)
            path.lineTo(w - pad - 4, pad)
            path.lineTo(w - pad, pad + 4)
            path.lineTo(w - pad, h - pad)
            path.lineTo(pad, h - pad)
            path.closeSubpath()
            painter.drawPath(path)
            painter.drawLine(QPointF(w - pad - 4, pad), QPointF(w - pad - 4, pad + 4))
            painter.drawLine(QPointF(w - pad - 4, pad + 4), QPointF(w - pad, pad + 4))

        elif name == "open":
            path = QPainterPath()
            path.moveTo(pad, pad + 4)
            path.lineTo(pad + 4, pad)
            path.lineTo(pad + 8, pad)
            path.lineTo(pad + 10, pad + 4)
            path.lineTo(w - pad, pad + 4)
            path.lineTo(w - pad, h - pad)
            path.lineTo(pad, h - pad)
            path.closeSubpath()
            painter.drawPath(path)

        elif name == "save":
            painter.drawRoundedRect(QRectF(pad, pad, w - 2 * pad, h - 2 * pad), 2, 2)
            painter.drawRect(QRectF(pad + 3, pad, w - 2 * pad - 6, (h - 2 * pad) * 0.45))
            painter.drawRect(QRectF(pad + 5, h - pad - 5, w - 2 * pad - 10, 5))

        elif name == "undo":
            path = QPainterPath()
            path.moveTo(pad + 2, h / 2)
            path.lineTo(pad + 7, h / 2 - 5)
            path.moveTo(pad + 2, h / 2)
            path.lineTo(pad + 7, h / 2 + 5)
            painter.drawPath(path)
            path_curve = QPainterPath()
            path_curve.moveTo(pad + 3, h / 2)
            path_curve.cubicTo(w * 0.5, h * 0.25, w - pad, h * 0.35, w - pad, h - pad)
            painter.drawPath(path_curve)

        elif name == "redo":
            path = QPainterPath()
            path.moveTo(w - pad - 2, h / 2)
            path.lineTo(w - pad - 7, h / 2 - 5)
            path.moveTo(w - pad - 2, h / 2)
            path.lineTo(w - pad - 7, h / 2 + 5)
            painter.drawPath(path)
            path_curve = QPainterPath()
            path_curve.moveTo(w - pad - 3, h / 2)
            path_curve.cubicTo(w * 0.5, h * 0.25, pad, h * 0.35, pad, h - pad)
            painter.drawPath(path_curve)

        elif name == "cut":
            painter.drawEllipse(QPointF(pad + 3, h - pad - 3), 3, 3)
            painter.drawEllipse(QPointF(w - pad - 3, h - pad - 3), 3, 3)
            painter.drawLine(QPointF(pad + 5, h - pad - 4), QPointF(w - pad - 2, pad + 2))
            painter.drawLine(QPointF(w - pad - 5, h - pad - 4), QPointF(pad + 2, pad + 2))

        elif name == "copy":
            painter.drawRoundedRect(QRectF(pad + 4, pad, w - 2 * pad - 4, h - 2 * pad - 4), 2, 2)
            painter.drawRoundedRect(QRectF(pad, pad + 4, w - 2 * pad - 4, h - 2 * pad - 4), 2, 2)

        elif name == "paste":
            painter.drawRoundedRect(QRectF(pad + 2, pad + 3, w - 2 * pad - 4, h - 2 * pad - 3), 2, 2)
            painter.drawRoundedRect(QRectF(w / 2 - 3, pad, 6, 4), 1, 1)

        elif name == "bold":
            font = QFont("serif", int(size * 0.55), QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "B")

        elif name == "italic":
            font = QFont("serif", int(size * 0.55), QFont.Weight.Normal)
            font.setItalic(True)
            painter.setFont(font)
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "I")

        elif name == "underline":
            font = QFont("serif", int(size * 0.52), QFont.Weight.Normal)
            painter.setFont(font)
            painter.drawText(QRectF(0, -2, w, h), Qt.AlignmentFlag.AlignCenter, "U")
            painter.drawLine(QPointF(pad + 2, h - pad + 1), QPointF(w - pad - 2, h - pad + 1))

        elif name == "strikethrough":
            font = QFont("serif", int(size * 0.52), QFont.Weight.Normal)
            painter.setFont(font)
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "S")
            painter.drawLine(QPointF(pad, h / 2), QPointF(w - pad, h / 2))

        elif name == "subscript":
            font_x = QFont("serif", int(size * 0.45), QFont.Weight.Bold)
            painter.setFont(font_x)
            painter.drawText(QRectF(pad - 1, pad - 2, w * 0.5, h * 0.7), Qt.AlignmentFlag.AlignCenter, "x")
            font_2 = QFont("sans-serif", int(size * 0.28), QFont.Weight.Bold)
            painter.setFont(font_2)
            painter.drawText(QRectF(w * 0.5, h * 0.4, w * 0.4, h * 0.5), Qt.AlignmentFlag.AlignCenter, "2")

        elif name == "superscript":
            font_x = QFont("serif", int(size * 0.45), QFont.Weight.Bold)
            painter.setFont(font_x)
            painter.drawText(QRectF(pad - 1, h * 0.3, w * 0.5, h * 0.7), Qt.AlignmentFlag.AlignCenter, "x")
            font_2 = QFont("sans-serif", int(size * 0.28), QFont.Weight.Bold)
            painter.setFont(font_2)
            painter.drawText(QRectF(w * 0.5, pad - 1, w * 0.4, h * 0.5), Qt.AlignmentFlag.AlignCenter, "2")

        elif name == "font-grow":
            font_a = QFont("sans-serif", int(size * 0.52), QFont.Weight.Bold)
            painter.setFont(font_a)
            painter.drawText(QRectF(pad, pad, w * 0.55, h * 0.75), Qt.AlignmentFlag.AlignCenter, "A")
            # Small up arrow on right
            path = QPainterPath()
            path.moveTo(w - pad - 4, pad + 8)
            path.lineTo(w - pad, pad + 2)
            path.lineTo(w - pad + 4, pad + 8)
            painter.drawPath(path)
            painter.drawLine(QPointF(w - pad, pad + 2), QPointF(w - pad, pad + 14))

        elif name == "font-shrink":
            font_a = QFont("sans-serif", int(size * 0.40), QFont.Weight.Bold)
            painter.setFont(font_a)
            painter.drawText(QRectF(pad, pad + 4, w * 0.55, h * 0.75), Qt.AlignmentFlag.AlignCenter, "A")
            # Small down arrow on right
            path = QPainterPath()
            path.moveTo(w - pad - 4, pad + 8)
            path.lineTo(w - pad, pad + 14)
            path.lineTo(w - pad + 4, pad + 8)
            painter.drawPath(path)
            painter.drawLine(QPointF(w - pad, pad + 2), QPointF(w - pad, pad + 14))

        elif name == "equation":
            # Mathematical Pi and Radical symbol
            font_pi = QFont("serif", int(size * 0.5), QFont.Weight.Bold)
            font_pi.setItalic(True)
            painter.setFont(font_pi)
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "π")

        elif name == "find":
            # Magnifying glass
            painter.drawEllipse(QRectF(pad, pad, w * 0.45, h * 0.45))
            painter.drawLine(QPointF(pad + w * 0.38, pad + h * 0.38), QPointF(w - pad, h - pad))

        elif name == "replace":
            # Magnifying glass with refresh arrow
            painter.drawEllipse(QRectF(pad, pad, w * 0.40, h * 0.40))
            painter.drawLine(QPointF(pad + w * 0.32, pad + h * 0.32), QPointF(w - pad - 2, h - pad - 2))
            path = QPainterPath()
            path.moveTo(w - pad, pad + 2)
            path.lineTo(w - pad + 5, pad + 6)
            path.lineTo(w - pad, pad + 10)
            painter.drawPath(path)

        elif name == "ruler":
            painter.drawRect(QRectF(pad, pad + 4, w - 2 * pad, h - 2 * pad - 8))
            for i in range(1, 6):
                x_pos = pad + (w - 2 * pad) * (i / 6.0)
                tick_h = 6 if i % 2 == 0 else 3
                painter.drawLine(QPointF(x_pos, pad + 4), QPointF(x_pos, pad + 4 + tick_h))

        elif name == "align-left":
            for y_off in [2, 6, 10, 14]:
                w_line = (w - pad) if y_off % 4 == 2 else (w - pad - 6)
                painter.drawLine(QPointF(pad, pad + y_off), QPointF(w_line, pad + y_off))

        elif name == "align-center":
            for y_off in [2, 6, 10, 14]:
                pad_l = 2 if y_off % 4 == 2 else 5
                painter.drawLine(QPointF(pad + pad_l, pad + y_off), QPointF(w - pad - pad_l, pad + y_off))

        elif name == "align-right":
            for y_off in [2, 6, 10, 14]:
                w_line = pad if y_off % 4 == 2 else (pad + 6)
                painter.drawLine(QPointF(w_line, pad + y_off), QPointF(w - pad, pad + y_off))

        elif name == "align-justify":
            for y_off in [2, 6, 10, 14]:
                painter.drawLine(QPointF(pad, pad + y_off), QPointF(w - pad, pad + y_off))

        elif name == "table":
            painter.drawRect(QRectF(pad, pad, w - 2 * pad, h - 2 * pad))
            painter.drawLine(QPointF(pad, h / 2), QPointF(w - pad, h / 2))
            painter.drawLine(QPointF(w / 2, pad), QPointF(w / 2, h - pad))

        elif name == "image":
            painter.drawRect(QRectF(pad, pad, w - 2 * pad, h - 2 * pad))
            painter.drawEllipse(QPointF(pad + 4, pad + 4), 2, 2)
            path = QPainterPath()
            path.moveTo(pad, h - pad)
            path.lineTo(pad + 5, h / 2)
            path.lineTo(pad + 9, h - pad - 2)
            path.lineTo(w - pad - 2, h / 2 + 2)
            path.lineTo(w - pad, h - pad)
            painter.drawPath(path)

        elif name == "shape":
            painter.drawRect(QRectF(pad, pad, w * 0.45, h * 0.45))
            painter.drawEllipse(QPointF(w - pad - 3, h - pad - 3), 4, 4)

        elif name == "shape-triangle":
            path = QPainterPath()
            path.moveTo(w / 2, pad)
            path.lineTo(w - pad, h - pad)
            path.lineTo(pad, h - pad)
            path.closeSubpath()
            painter.drawPath(path)

        elif name == "shape-diamond":
            path = QPainterPath()
            path.moveTo(w / 2, pad)
            path.lineTo(w - pad, h / 2)
            path.lineTo(w / 2, h - pad)
            path.lineTo(pad, h / 2)
            path.closeSubpath()
            painter.drawPath(path)

        elif name == "shape-star":
            path = QPainterPath()
            cx, cy = w / 2, h / 2
            outer_r, inner_r = (w / 2 - pad), (w / 2 - pad) * 0.45
            import math
            for i in range(10):
                angle = i * math.pi / 5 - math.pi / 2
                r = outer_r if i % 2 == 0 else inner_r
                x = cx + r * math.cos(angle)
                y = cy + r * math.sin(angle)
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            path.closeSubpath()
            painter.drawPath(path)

        elif name == "shape-arrow":
            path = QPainterPath()
            path.moveTo(pad, h * 0.38)
            path.lineTo(w * 0.6, h * 0.38)
            path.lineTo(w * 0.6, pad + 2)
            path.lineTo(w - pad, h / 2)
            path.lineTo(w * 0.6, h - pad - 2)
            path.lineTo(w * 0.6, h * 0.62)
            path.lineTo(pad, h * 0.62)
            path.closeSubpath()
            painter.drawPath(path)

        elif name == "shape-double-arrow":
            # PowerPoint's left-right arrow: the same block, headed both ends.
            path = QPainterPath()
            path.moveTo(pad + (w - 2 * pad) * 0.25, h * 0.38)
            path.lineTo(w * 0.75, h * 0.38)
            path.lineTo(w * 0.75, pad + 2)
            path.lineTo(w - pad, h / 2)
            path.lineTo(w * 0.75, h - pad - 2)
            path.lineTo(w * 0.75, h * 0.62)
            path.lineTo(pad + (w - 2 * pad) * 0.25, h * 0.62)
            path.lineTo(pad + (w - 2 * pad) * 0.25, h - pad - 2)
            path.lineTo(pad, h / 2)
            path.lineTo(pad + (w - 2 * pad) * 0.25, pad + 2)
            path.closeSubpath()
            painter.drawPath(path)

        elif name == "currency":
            font = QFont("sans-serif", int(size * 0.55), QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "$")

        elif name == "percent":
            font = QFont("sans-serif", int(size * 0.5), QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "%")

        elif name == "border-all":
            painter.drawRect(QRectF(pad, pad, w - 2 * pad, h - 2 * pad))
            painter.drawLine(QPointF(pad, h / 2), QPointF(w - pad, h / 2))
            painter.drawLine(QPointF(w / 2, pad), QPointF(w / 2, h - pad))

        elif name == "sort-az":
            font = QFont("sans-serif", int(size * 0.35), QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(QRectF(pad, pad - 2, w * 0.45, h * 0.5), Qt.AlignmentFlag.AlignCenter, "A")
            painter.drawText(QRectF(pad, h * 0.5, w * 0.45, h * 0.5), Qt.AlignmentFlag.AlignCenter, "Z")
            painter.drawLine(QPointF(w - pad - 3, pad + 2), QPointF(w - pad - 3, h - pad - 2))
            path = QPainterPath()
            path.moveTo(w - pad - 6, h - pad - 6)
            path.lineTo(w - pad - 3, h - pad - 2)
            path.lineTo(w - pad, h - pad - 6)
            painter.drawPath(path)

        elif name == "notes":
            painter.drawRect(QRectF(pad, pad, w - 2 * pad, h - 2 * pad))
            for y_off in [5, 9, 13]:
                painter.drawLine(QPointF(pad + 3, pad + y_off), QPointF(w - pad - 3, pad + y_off))

        elif name == "slide":
            painter.drawRoundedRect(QRectF(pad - 1, pad + 2, w - 2 * pad + 2, (h - 2 * pad) * 0.8), 2, 2)
            painter.drawLine(QPointF(pad + 2, pad + 5), QPointF(w - pad - 2, pad + 5))

        elif name == "play":
            path = QPainterPath()
            path.moveTo(pad + 2, pad)
            path.lineTo(w - pad, h / 2)
            path.lineTo(pad + 2, h - pad)
            path.closeSubpath()
            painter.setBrush(QBrush(qcolor))
            painter.drawPath(path)

        elif name == "theme":
            painter.drawEllipse(QRectF(pad, pad, w - 2 * pad, h - 2 * pad))
            path = QPainterPath()
            path.moveTo(w / 2, pad)
            path.arcTo(QRectF(pad, pad, w - 2 * pad, h - 2 * pad), 90, 180)
            painter.setBrush(QBrush(qcolor))
            painter.drawPath(path)

        elif name == "ai":
            cx, cy = w / 2, h / 2
            path = QPainterPath()
            path.moveTo(cx, pad)
            path.quadTo(cx, cy, w - pad, cy)
            path.quadTo(cx, cy, cx, h - pad)
            path.quadTo(cx, cy, pad, cy)
            path.quadTo(cx, cy, cx, pad)
            painter.setBrush(QBrush(qcolor))
            painter.drawPath(path)

        elif _draw_extended(name, painter, w, h, qcolor, pad):
            pass  # drawn by the extended Office glyph library below

        else:
            painter.drawEllipse(QRectF(pad, pad, w - 2 * pad, h - 2 * pad))

        painter.end()

        icon = QIcon(pixmap)
        cls._cache[cache_key] = icon
        return icon


# --------------------------------------------------------------------------- #
# Extended Office glyph library
#
# The ribbon needs roughly seventy distinct commands. Rather than seventy copies
# of the same boilerplate, names are routed through a handful of glyph families
# that all speak in fractions of the requested size, so one 16px toolbar button
# and one 32px large command render the same shape.
# --------------------------------------------------------------------------- #

INK_RED = "#C00000"
INK_GOLD = "#8A6200"
INK_BLUE = "#2B579A"
INK_GREEN = "#217346"
HIGHLIGHT = "#FFD966"

_PAGE_TOP = 0.14      # page glyphs are slightly narrower than square


def _pen(painter, color, w, width_fraction=0.062):
    pen = QPen(QColor(color), max(1.0, w * width_fraction))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _fill(painter, color):
    painter.setBrush(QBrush(QColor(color)))


def _no_fill(painter):
    painter.setBrush(Qt.BrushStyle.NoBrush)


def _text(painter, w, label, color, point_fraction=0.5, bold=True, italic=False,
          rect=None, family="sans-serif"):
    font = QFont(family, max(5, int(w * point_fraction)),
                 QFont.Weight.Bold if bold else QFont.Weight.Normal)
    font.setItalic(italic)
    painter.setFont(font)
    _no_fill(painter)
    area = QRectF(*rect) if rect else QRectF(0, 0, w, w)
    painter.drawText(area, Qt.AlignmentFlag.AlignCenter, label)


def colour_swatch_icon(colour: str, size: int = 14) -> QIcon:
    """A tile of *colour*, so a menu can name an ink by wearing it."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#9CA3AF"), 1))
    painter.setBrush(QColor(colour))
    painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1.0, size - 1.0), 2, 2)
    painter.end()
    return QIcon(pixmap)


def _draw_extended(name: str, painter, w: float, h: float, color, pad: float) -> bool:
    """Draw the glyphs outside the original icon set. Returns False if unknown."""
    L, T, R, B = pad, pad, w - pad, h - pad
    cx, cy = w / 2, h / 2
    ink = color.name() if hasattr(color, "name") else str(color)
    _pen(painter, ink, w)
    _no_fill(painter)

    # --- Literal glyph, e.g. "text:Σ" for Excel's AutoSum -------------------- #
    if name.startswith("text:"):
        label = name[5:]
        fraction = 0.62 if len(label) <= 1 else (0.40 if len(label) == 2 else 0.30)
        _text(painter, w, label, ink, point_fraction=fraction)
        return True

    # --- Page family --------------------------------------------------------- #
    if name in {
        "margins", "page-break", "paper-size", "header-footer", "footnote",
        "columns", "toc", "caption", "styles", "save-as", "pdf", "new-slide",
        "page-border", "page-colour", "watermark",
    }:
        pl, pt, pr, pb = w * 0.20, h * _PAGE_TOP, w * 0.80, h * (1 - _PAGE_TOP)
        painter.drawRect(QRectF(pl, pt, pr - pl, pb - pt))
        if name == "page-colour":
            # The sheet dressed edge to edge, with the outline drawn back over
            # the dress so the page still reads as a page.
            dressed = QColor(ink)
            dressed.setAlpha(80)
            painter.fillRect(QRectF(pl, pt, pr - pl, pb - pt), dressed)
            painter.drawRect(QRectF(pl, pt, pr - pl, pb - pt))
        elif name == "page-border":
            _fill(painter, ink)
            for frac in (0.14, 0.86):
                painter.drawEllipse(QPointF(pl + (pr - pl) * 0.5,
                                            pt + (pb - pt) * frac),
                                    max(1.0, w * 0.045), max(1.0, w * 0.045))
                painter.drawEllipse(QPointF(pl + (pr - pl) * frac,
                                            pt + (pb - pt) * 0.5),
                                    max(1.0, w * 0.045), max(1.0, w * 0.045))
            _no_fill(painter)
            painter.drawRect(QRectF(pl + 2.5, pt + 2.5, pr - pl - 5, pb - pt - 5))
        elif name == "margins":
            dashed = QPen(QColor(ink), max(1.0, w * 0.045))
            dashed.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(dashed)
            painter.drawRect(QRectF(pl + (pr - pl) * 0.22, pt + (pb - pt) * 0.2,
                                    (pr - pl) * 0.56, (pb - pt) * 0.6))
        elif name == "page-break":
            mid = (pt + pb) / 2
            dashed = QPen(QColor(ink), max(1.0, w * 0.045))
            dashed.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(dashed)
            painter.drawLine(QPointF(pl + 1, mid), QPointF(pr - 1, mid))
        elif name == "paper-size":
            painter.drawLine(QPointF(pl + 2, pb - 3), QPointF(pr - 2, pb - 3))
            painter.drawLine(QPointF(pl + 2, pb - 3), QPointF(pl + 4, pb - 5))
            painter.drawLine(QPointF(pl + 2, pb - 3), QPointF(pl + 4, pb - 1))
            painter.drawLine(QPointF(pr - 2, pb - 3), QPointF(pr - 4, pb - 5))
            painter.drawLine(QPointF(pr - 2, pb - 3), QPointF(pr - 4, pb - 1))
        elif name == "watermark":
            # The mark itself across the sheet's corner, set lighter than the
            # paper so the glyph reads as something seen through the writing.
            faded = QColor(ink)
            faded.setAlpha(90)
            heavy = QPen(faded, max(2.0, w * 0.13))
            painter.setPen(heavy)
            painter.drawLine(QPointF(pl + 2.5, pb - 2.5),
                             QPointF(pr - 2.5, pt + 2.5))
            painter.setPen(QPen(QColor(ink), max(1.0, w * 0.05)))
            painter.drawLine(QPointF(pl + 2.5, pb - 7.5),
                             QPointF(pr - 8.5, pt + 2.5))
        elif name == "header-footer":
            _fill(painter, ink)
            painter.drawRect(QRectF(pl + 1.5, pt + 1.5, pr - pl - 3, (pb - pt) * 0.2))
            _no_fill(painter)
            painter.drawRect(QRectF(pl + 1.5, pb - 3 - (pb - pt) * 0.12,
                                    pr - pl - 3, (pb - pt) * 0.12))
        elif name == "footnote":
            for frac in (0.28, 0.46, 0.64):
                painter.drawLine(QPointF(pl + 2.5, pt + (pb - pt) * frac),
                                 QPointF(pr - 2.5, pt + (pb - pt) * frac))
            painter.drawLine(QPointF(pl + 2.5, pb - 3.5),
                             QPointF(pl + 2.5 + (pr - pl) * 0.35, pb - 3.5))
        elif name == "columns":
            painter.drawLine(QPointF(cx, pt + 2), QPointF(cx, pb - 2))
        elif name == "toc":
            for frac in (0.28, 0.5, 0.72):
                y = pt + (pb - pt) * frac
                painter.drawLine(QPointF(pl + 2.5, y), QPointF(pr - 6, y))
                _fill(painter, ink)
                painter.drawEllipse(QPointF(pr - 3.2, y), 1.0, 1.0)
                _no_fill(painter)
        elif name == "caption":
            painter.drawRect(QRectF(pl + 2.5, pt + 2.5, pr - pl - 5, (pb - pt) * 0.45))
            painter.drawLine(QPointF(pl + 4, pb - 4), QPointF(pr - 4, pb - 4))
        elif name == "styles":
            _text(painter, w, "Aa", ink, point_fraction=0.30,
                  rect=(pl + 1, pt + 1, pr - pl - 2, (pb - pt) * 0.5))
            painter.drawLine(QPointF(pl + 2.5, pb - 4), QPointF(pr - 2.5, pb - 4))
        elif name == "save-as":
            _fill(painter, ink)
            painter.drawRect(QRectF(pl + 2, pt + 2, pr - pl - 4, (pb - pt) * 0.3))
            _no_fill(painter)
            painter.drawLine(QPointF(cx, pb - 8), QPointF(cx, pt + (pb - pt) * 0.45))
            painter.drawLine(QPointF(cx, pb - 8), QPointF(cx - 2.6, pb - 10.6))
            painter.drawLine(QPointF(cx, pb - 8), QPointF(cx + 2.6, pb - 10.6))
        elif name == "pdf":
            _fill(painter, INK_RED)
            painter.drawRoundedRect(QRectF(pl + 1, pb - (pb - pt) * 0.42,
                                           pr - pl - 2, (pb - pt) * 0.38), 1.5, 1.5)
            _no_fill(painter)
            painter.drawLine(QPointF(pl + 3, pt + 3), QPointF(pr - 3, pt + 3))
        return True

    if name == "orientation":
        painter.drawRect(QRectF(w * 0.14, h * 0.18, w * 0.30, h * 0.64))
        _fill(painter, ink)
        painter.drawRect(QRectF(w * 0.54, h * 0.26, w * 0.34, h * 0.48))
        _no_fill(painter)
        return True

    if name == "section":
        painter.drawRect(QRectF(L, T, R - L, B - T))
        _fill(painter, ink)
        painter.drawRect(QRectF(L + 1.5, T + 1.5, R - L - 3, (B - T) * 0.22))
        _no_fill(painter)
        return True

    if name == "new-slide":
        painter.drawRect(QRectF(L, T + 1, w * 0.62, h * 0.62))
        painter.drawLine(QPointF(w * 0.78, h * 0.34), QPointF(w * 0.78, h * 0.72))
        painter.drawLine(QPointF(w * 0.59, h * 0.53), QPointF(w * 0.97, h * 0.53))
        return True

    # --- Paragraph / list family --------------------------------------------- #
    if name in {"bullets", "numbering", "checklist"}:
        x_text = L + w * 0.24
        for i, frac in enumerate((0.24, 0.5, 0.76)):
            y = T + (B - T) * frac
            painter.drawLine(QPointF(x_text, y), QPointF(R, y))
            if name == "bullets":
                _fill(painter, ink)
                painter.drawEllipse(QPointF(L + w * 0.08, y), max(1.1, w * 0.055),
                                    max(1.1, w * 0.055))
                _no_fill(painter)
            elif name == "checklist":
                painter.drawRect(QRectF(L + w * 0.02, y - w * 0.075, w * 0.15, w * 0.15))
            else:
                _text(painter, w * 0.62, str(i + 1), ink, point_fraction=0.34,
                      rect=(L - w * 0.06, y - w * 0.14, w * 0.3, w * 0.28))
        return True

    if name in {"indent-more", "indent-less"}:
        for frac in (0.2, 0.4, 0.8):
            y = T + (B - T) * frac
            painter.drawLine(QPointF(L, y), QPointF(R, y))
        y = T + (B - T) * 0.6
        tip = R if name == "indent-more" else L
        base = L if name == "indent-more" else R
        painter.drawLine(QPointF(base, y), QPointF(tip, y))
        back = tip - (w * 0.16 if name == "indent-more" else -w * 0.16)
        painter.drawLine(QPointF(tip, y), QPointF(back, y - w * 0.13))
        painter.drawLine(QPointF(tip, y), QPointF(back, y + w * 0.13))
        return True

    if name in {"line-spacing", "paragraph-spacing"}:
        top, bottom = T + 1, B - 1
        for frac in (0.34, 0.5, 0.66):
            y = top + (bottom - top) * frac
            painter.drawLine(QPointF(cx - w * 0.04, y), QPointF(R, y))
        painter.drawLine(QPointF(L + w * 0.06, top), QPointF(L + w * 0.06, bottom))
        painter.drawLine(QPointF(L + w * 0.06, top), QPointF(L, top + w * 0.12))
        painter.drawLine(QPointF(L + w * 0.06, top), QPointF(L + w * 0.12, top + w * 0.12))
        painter.drawLine(QPointF(L + w * 0.06, bottom), QPointF(L, bottom - w * 0.12))
        painter.drawLine(QPointF(L + w * 0.06, bottom), QPointF(L + w * 0.12, bottom - w * 0.12))
        return True

    # --- Text color family --------------------------------------------------- #
    if name in {"design", "themes"}:
        half_w, half_h = (R - L) / 2.0, (B - T) / 2.0
        _fill(painter, ink)
        painter.drawRect(QRectF(L, T, half_w - 1, half_h - 1))
        _no_fill(painter)
        painter.drawRect(QRectF(L + half_w + 1, T, half_w - 1, half_h - 1))
        painter.drawRect(QRectF(L, T + half_h + 1, half_w - 1, half_h - 1))
        _fill(painter, ink)
        painter.drawRect(QRectF(L + half_w + 1, T + half_h + 1, half_w - 1, half_h - 1))
        _no_fill(painter)
        return True

    if name in {"font-color", "text-highlight", "fill-color", "theme-color"}:
        bar = INK_RED if name == "font-color" else (
            HIGHLIGHT if name == "text-highlight" else INK_BLUE)
        _text(painter, w, "A" if name != "fill-color" else "", ink,
              point_fraction=0.52, rect=(0, -w * 0.06, w, h * 0.8))
        if name == "fill-color":
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(-40)
            painter.drawRect(QRectF(-w * 0.09, -h * 0.30, w * 0.18, h * 0.42))
            painter.restore()
            _fill(painter, bar)
            path = QPainterPath()
            path.moveTo(w * 0.20, h * 0.80)
            path.cubicTo(w * 0.32, h * 0.62, w * 0.52, h * 0.72, w * 0.44, h * 0.86)
            painter.drawPath(path)
            _no_fill(painter)
        else:
            _fill(painter, bar)
            painter.drawRect(QRectF(L + w * 0.05, B - h * 0.13, (R - L) - w * 0.10, h * 0.11))
            _no_fill(painter)
        return True

    # --- Border family (a 3x3 grid with the chosen edges inked) -------------- #
    if name.startswith("border-"):
        kind = name[len("border-"):]
        grid = QRectF(L, T, R - L, B - T)
        painter.drawRect(grid)
        step_x, step_y = grid.width() / 3.0, grid.height() / 3.0
        inner_pen = QPen(QColor(ink), max(1.0, w * 0.04))
        painter.setPen(inner_pen)
        if kind in {"all", "inside-h", "thick"}:
            for i in (1, 2):
                y = grid.top() + step_y * i
                painter.drawLine(QPointF(grid.left(), y), QPointF(grid.right(), y))
        if kind in {"all", "inside-v"}:
            for i in (1, 2):
                x = grid.left() + step_x * i
                painter.drawLine(QPointF(x, grid.top()), QPointF(x, grid.bottom()))
        if kind in {"outside", "all", "bottom", "thick"}:
            heavy = QPen(QColor(ink), max(1.6, w * 0.09))
            painter.setPen(heavy)
            if kind == "bottom":
                painter.drawLine(QPointF(grid.left(), grid.bottom()),
                                 QPointF(grid.right(), grid.bottom()))
            else:
                painter.drawRect(grid)
        if kind == "none":
            faded = QColor(ink)
            faded.setAlphaF(0.55)
            light = QPen(faded, max(1.0, w * 0.04))
            light.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(light)
            painter.drawRect(grid)
            painter.setPen(QPen(QColor(INK_RED), max(1.6, w * 0.09)))
            painter.drawLine(QPointF(grid.left(), grid.bottom()),
                             QPointF(grid.right(), grid.top()))
        _no_fill(painter)
        return True

    # --- Frame / view family ------------------------------------------------- #
    if name in {
        "view-normal", "view-page-layout", "view-page-break", "view-read", "view-web",
        "view-slide-sorter", "view-outline", "view-notes", "view-master",
        "view-presenter", "gridlines", "layout", "freeze-panes", "table", "master",
    }:
        frame = QRectF(L, T + h * 0.04, R - L, (B - T) - h * 0.08)
        painter.drawRect(frame)
        kind = name
        if kind == "view-normal":
            painter.drawLine(QPointF(frame.left() + frame.width() * 0.3, frame.top()),
                             QPointF(frame.left() + frame.width() * 0.3, frame.bottom()))
        elif kind in {"view-page-layout", "view-read", "print-layout", "read-mode"}:
            painter.drawRect(frame.adjusted(frame.width() * 0.16, frame.height() * 0.14,
                                           -frame.width() * 0.16, -frame.height() * 0.14))
        elif kind == "view-page-break":
            dashed = QPen(QColor(ink), max(1.0, w * 0.045))
            dashed.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(dashed)
            mid = frame.center().y()
            painter.drawLine(QPointF(frame.left() + 1, mid), QPointF(frame.right() - 1, mid))
        elif kind in {"view-web", "web-layout"}:
            painter.drawEllipse(QRectF(frame.right() - frame.width() * 0.5,
                                       frame.top() - h * 0.04,
                                       frame.width() * 0.5, frame.height() * 0.5))
        elif kind == "view-slide-sorter":
            painter.setPen(QPen(QColor(ink), max(1.0, w * 0.05)))
            half_w, half_h = frame.width() / 2.3, frame.height() / 2.3
            for i in range(2):
                for j in range(2):
                    painter.drawRect(QRectF(frame.left() + i * frame.width() * 0.53 + 1,
                                            frame.top() + j * frame.height() * 0.53 + 1,
                                            half_w - 2, half_h - 2))
        elif kind == "view-outline":
            for i, frac in enumerate((0.28, 0.5, 0.72)):
                y = frame.top() + frame.height() * frac
                x0 = frame.left() + frame.width() * (0.12 if i < 2 else 0.4)
                painter.drawLine(QPointF(x0, y), QPointF(frame.right() - 3, y))
        elif kind == "view-notes":
            painter.drawLine(QPointF(frame.left(), frame.bottom() - frame.height() * 0.3),
                             QPointF(frame.right(), frame.bottom() - frame.height() * 0.3))
        elif kind in {"view-master", "master"}:
            _fill(painter, ink)
            painter.drawRect(QRectF(frame.left() + 2, frame.top() + 2,
                                    frame.width() - 4, frame.height() * 0.2))
            _no_fill(painter)
        elif kind == "view-presenter":
            painter.drawRect(QRectF(frame.left() + frame.width() * 0.18,
                                    frame.top() + frame.height() * 0.22,
                                    frame.width() * 0.64, frame.height() * 0.42))
            painter.drawLine(QPointF(cx, frame.top() + frame.height() * 0.64),
                             QPointF(cx, frame.bottom() - 2))
        elif kind == "gridlines":
            light = QPen(QColor(ink), max(1.0, w * 0.035))
            light.setStyle(Qt.PenStyle.DotLine)
            painter.setPen(light)
            for i in (1, 2):
                painter.drawLine(QPointF(frame.left() + frame.width() * i / 3.0, frame.top()),
                                 QPointF(frame.left() + frame.width() * i / 3.0, frame.bottom()))
                painter.drawLine(QPointF(frame.left(), frame.top() + frame.height() * i / 3.0),
                                 QPointF(frame.right(), frame.top() + frame.height() * i / 3.0))
        elif kind == "freeze-panes":
            _fill(painter, ink)
            painter.drawRect(QRectF(frame.left(), frame.top(),
                                    frame.width() * 0.3, frame.height() * 0.26))
            _no_fill(painter)
            heavy = QPen(QColor(ink), max(1.6, w * 0.08))
            painter.setPen(heavy)
            painter.drawLine(QPointF(frame.left() + frame.width() * 0.3, frame.top()),
                             QPointF(frame.left() + frame.width() * 0.3, frame.bottom()))
            painter.drawLine(QPointF(frame.left(), frame.top() + frame.height() * 0.26),
                             QPointF(frame.right(), frame.top() + frame.height() * 0.26))
        elif kind == "layout":
            _fill(painter, ink)
            painter.drawRect(QRectF(frame.left() + 2, frame.top() + 2,
                                    frame.width() - 4, frame.height() * 0.26))
            _no_fill(painter)
            painter.drawLine(QPointF(frame.left() + 3, frame.center().y()),
                             QPointF(frame.right() - 3, frame.center().y()))
        elif kind == "table":
            painter.drawLine(QPointF(frame.left(), frame.center().y()),
                             QPointF(frame.right(), frame.center().y()))
            painter.drawLine(QPointF(frame.center().x(), frame.top()),
                             QPointF(frame.center().x(), frame.bottom()))
        return True

    # --- Arrange family ------------------------------------------------------ #
    if name in {"bring-front", "send-back", "arrange"}:
        back = QRectF(L + w * 0.22, T, w * 0.42, h * 0.42)
        front = QRectF(L, T + h * 0.22, w * 0.42, h * 0.42)
        if name == "bring-front":
            painter.drawRect(back)
            _fill(painter, ink)
            painter.drawRect(front)
            _no_fill(painter)
        elif name == "send-back":
            painter.drawRect(front)
            light = QPen(QColor(ink), max(1.0, w * 0.04))
            light.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(light)
            painter.drawRect(back)
        else:
            painter.drawRect(back)
            painter.drawRect(front)
        return True

    if name in {"align-top", "align-middle", "align-bottom", "align-h-center"}:
        axis = {"align-top": 0, "align-middle": 1, "align-bottom": 2}.get(name, 1)
        guide = {0: L + w * 0.1, 1: cx, 2: R - w * 0.1}[axis]
        light = QPen(QColor(ink), max(1.0, w * 0.04))
        painter.setPen(light)
        if axis == 1:
            painter.drawLine(QPointF(guide, T), QPointF(guide, B))
        else:
            painter.drawLine(QPointF(T, guide), QPointF(B, guide))
        painter.setPen(QPen(QColor(ink), max(1.4, w * 0.07)))
        for i, frac in enumerate((0.28, 0.62)):
            if axis == 1:
                hgt = h * (0.34 if i == 0 else 0.2)
                painter.drawRect(QRectF(guide + w * 0.1, cy - hgt / 2, w * 0.26, hgt))
            else:
                wid = w * (0.34 if i == 0 else 0.2)
                painter.drawRect(QRectF(cx - wid / 2, guide + (4 if i else -h * 0.42),
                                        wid, h * 0.3))
        return True

    # --- Chart / data family ------------------------------------------------- #
    if name in {"chart-bar", "chart", "chart-line", "chart-pie"}:
        painter.drawLine(QPointF(L, T), QPointF(L, B))
        painter.drawLine(QPointF(L, B), QPointF(R, B))
        if name == "chart-bar":
            _fill(painter, ink)
            for i, frac in enumerate((0.35, 0.62, 0.22)):
                bw = (R - L) / 4.2
                x = L + 2 + i * bw * 1.5
                painter.drawRect(QRectF(x, B - (B - T) * (frac + 0.3), bw, (B - T) * (frac + 0.3)))
            _no_fill(painter)
        elif name == "chart-pie":
            _fill(painter, ink)
            painter.drawEllipse(QRectF(L, T, R - L, B - T))
            painter.setPen(QPen(QColor("#FFFFFF"), max(1.4, w * 0.07)))
            painter.drawLine(QPointF(cx, cy), QPointF(R, cy))
            painter.drawLine(QPointF(cx, cy), QPointF(cx, T))
            _no_fill(painter)
        else:
            path = QPainterPath()
            path.moveTo(L + 2, B - 3)
            for x_frac, y_frac in ((0.35, 0.55), (0.55, 0.72), (0.78, 0.28), (1.0, 0.42)):
                path.lineTo(L + (R - L) * x_frac, T + (B - T) * (1 - y_frac))
            painter.drawPath(path)
        return True

    if name == "filter":
        path = QPainterPath()
        path.moveTo(L, T + 1)
        path.lineTo(R, T + 1)
        path.lineTo(cx + w * 0.02, cy)
        path.lineTo(cx + w * 0.02, B - 2)
        path.lineTo(cx - w * 0.06, B - 5)
        path.lineTo(cx - w * 0.06, cy)
        path.closeSubpath()
        painter.drawPath(path)
        return True

    if name in {"sort-za", "sort"}:
        _text(painter, w * 0.95, "Z", ink, point_fraction=0.34,
              rect=(0, -h * 0.06, w * 0.62, h * 0.55))
        _text(painter, w * 0.95, "A", ink, point_fraction=0.34,
              rect=(0, h * 0.42, w * 0.62, h * 0.55))
        painter.drawLine(QPointF(R - w * 0.04, B - 2), QPointF(R - w * 0.04, T + 2))
        painter.drawLine(QPointF(R - w * 0.04, T + 2), QPointF(R - w * 0.14, T + w * 0.14))
        painter.drawLine(QPointF(R - w * 0.04, T + 2), QPointF(R - w * 0.04 + w * 0.1, T + w * 0.14))
        return True

    if name in {"formula-sum", "autosum", "function"}:
        if name == "function":
            _text(painter, w, "fx", ink, point_fraction=0.42, italic=True, family="serif")
            return True
        _text(painter, w, "\u03a3", ink, point_fraction=0.62)
        return True

    if name == "wrap-text":
        _text(painter, w, "A", ink, point_fraction=0.5,
              rect=(L - w * 0.1, -h * 0.04, w * 0.62, h * 0.9))
        for frac in (0.28, 0.44, 0.6):
            y = T + (B - T) * frac * 1.6
            painter.drawLine(QPointF(R - w * 0.36, y), QPointF(R - 1, y))
        painter.drawLine(QPointF(R - w * 0.36, T + 2), QPointF(R - w * 0.5, T + 5))
        return True

    if name in {"clear-format", "erase"}:
        _text(painter, w, "A", ink, point_fraction=0.52, rect=(0, -h * 0.05, w, h))
        painter.setPen(QPen(QColor(INK_RED), max(1.6, w * 0.09)))
        painter.drawLine(QPointF(L + 1, B - 1), QPointF(R - 1, T + 1))
        return True

    if name in {"paintbrush", "format-painter"}:
        # Word's Format Painter: a brush angled over the strip it just painted.
        painter.drawLine(QPointF(w * 0.66, T + 1), QPointF(w * 0.40, h * 0.50))
        path = QPainterPath()
        path.moveTo(w * 0.30, h * 0.44)
        path.lineTo(w * 0.52, h * 0.56)
        path.lineTo(w * 0.38, h * 0.80)
        path.closeSubpath()
        painter.drawPath(path)
        painter.setPen(QPen(QColor(INK_BLUE), max(1.8, w * 0.10)))
        painter.drawLine(QPointF(L + 1, B - 1), QPointF(R - 1, B - 1))
        return True

    # --- Review / insert family ---------------------------------------------- #
    if name == "spell-check":
        _text(painter, w, "A", ink, point_fraction=0.46, rect=(L - 3, 0, w * 0.7, h))
        painter.setPen(QPen(QColor(INK_GREEN), max(1.8, w * 0.11)))
        path = QPainterPath()
        path.moveTo(w * 0.52, h * 0.66)
        path.lineTo(w * 0.66, h * 0.82)
        path.lineTo(w * 0.92, h * 0.34)
        painter.drawPath(path)
        return True

    if name == "check":
        painter.setPen(QPen(QColor(ink), max(1.8, w * 0.12)))
        path = QPainterPath()
        path.moveTo(L + 1, cy)
        path.lineTo(cx - w * 0.02, B - 2)
        path.lineTo(R - 1, T + 2)
        painter.drawPath(path)
        return True

    if name in {"shape-rect", "rectangle"}:
        painter.drawRect(QRectF(L + 1, T + 1, (R - L) - 2, (B - T) - 2))
        return True

    if name in {"ellipse", "oval", "circle"}:
        painter.drawEllipse(QRectF(L + 1, T + 1, (R - L) - 2, (B - T) - 2))
        return True

    if name in {"rounded-rect", "shape-rounded"}:
        painter.drawRoundedRect(QRectF(L + 1, T + 1, (R - L) - 2, (B - T) - 2),
                                w * 0.16, h * 0.16)
        return True

    if name in {"name", "defined-name"}:
        # Excel's Define Name: a tag with a punched hole.
        path = QPainterPath()
        path.moveTo(L + w * 0.02, T + (B - T) * 0.18)
        path.lineTo(cx + w * 0.16, T + (B - T) * 0.18)
        path.lineTo(R - 1, cy)
        path.lineTo(cx + w * 0.16, B - (B - T) * 0.18)
        path.lineTo(L + w * 0.02, B - (B - T) * 0.18)
        path.closeSubpath()
        painter.drawPath(path)
        painter.setPen(QPen(QColor(ink), max(1.2, w * 0.05)))
        painter.drawEllipse(QRectF(L + w * 0.11, cy - h * 0.055, w * 0.11, h * 0.11))
        return True

    if name == "book":
        painter.drawRect(QRectF(L + w * 0.06, T, (R - L) * 0.86, B - T))
        painter.drawLine(QPointF(cx, T + 2), QPointF(cx, B - 2))
        return True

    if name == "comment":
        path = QPainterPath()
        path.moveTo(L + 1, T + 1)
        path.lineTo(R - 1, T + 1)
        path.lineTo(R - 1, cy + h * 0.06)
        path.lineTo(cx + w * 0.08, cy + h * 0.06)
        path.lineTo(cx - w * 0.02, B - 1)
        path.lineTo(cx - w * 0.04, cy + h * 0.06)
        path.lineTo(L + 1, cy + h * 0.06)
        path.closeSubpath()
        painter.drawPath(path)
        return True

    if name == "pen":
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(45)
        painter.drawRect(QRectF(-w * 0.09, -h * 0.34, w * 0.18, h * 0.48))
        path = QPainterPath()
        path.moveTo(-w * 0.09, h * 0.14)
        path.lineTo(0, h * 0.32)
        path.lineTo(w * 0.09, h * 0.14)
        painter.drawPath(path)
        painter.restore()
        return True

    if name in {"close", "clear", "remove"}:
        painter.setPen(QPen(QColor(ink), max(1.5, w * 0.09)))
        painter.drawLine(QPointF(L + 2, T + 2), QPointF(R - 2, B - 2))
        painter.drawLine(QPointF(R - 2, T + 2), QPointF(L + 2, B - 2))
        return True

    if name == "print":
        painter.drawRect(QRectF(L + w * 0.12, B - h * 0.34, (R - L) * 0.76, h * 0.32))
        painter.drawLine(QPointF(L + 2, B - h * 0.34), QPointF(R - 2, B - h * 0.34))
        _fill(painter, ink)
        painter.drawEllipse(QPointF(R - w * 0.16, T + h * 0.30), max(1.0, w * 0.05),
                            max(1.0, w * 0.05))
        _no_fill(painter)
        return True

    # --- Slide-show family --------------------------------------------------- #
    if name in {"play-from", "from-current"}:
        painter.drawLine(QPointF(L + 1, T + 2), QPointF(L + 1, B - 2))
        path = QPainterPath()
        path.moveTo(cx - w * 0.22, T + 2)
        path.lineTo(R - 1, cy)
        path.lineTo(cx - w * 0.22, B - 2)
        path.closeSubpath()
        _fill(painter, ink)
        painter.drawPath(path)
        _no_fill(painter)
        return True

    if name in {"transition", "animation"}:
        painter.drawRect(QRectF(L, T + h * 0.08, w * 0.34, h * 0.66))
        light = QPen(QColor(ink), max(1.0, w * 0.04))
        light.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(light)
        painter.drawRect(QRectF(R - w * 0.34, T + h * 0.08, w * 0.34, h * 0.66))
        _no_fill(painter)
        painter.drawLine(QPointF(L + w * 0.36, cy), QPointF(R - w * 0.36, cy))
        painter.drawLine(QPointF(R - w * 0.36, cy), QPointF(R - w * 0.46, cy - h * 0.08))
        painter.drawLine(QPointF(R - w * 0.36, cy), QPointF(R - w * 0.46, cy + h * 0.08))
        return True

    if name == "record":
        _fill(painter, INK_RED)
        painter.drawEllipse(QRectF(cx - w * 0.18, cy - w * 0.18, w * 0.36, w * 0.36))
        _no_fill(painter)
        return True

    if name == "text-box":
        dashed = QPen(QColor(ink), max(1.0, w * 0.045))
        dashed.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(dashed)
        painter.drawRect(QRectF(L, T, R - L, B - T))
        _text(painter, w, "A", ink, point_fraction=0.44, rect=(L, T - 1, R - L, B - T))
        return True

    if name == "templates":
        # A wall of designs: one sheet standing large with two of its size set
        # beside it, which is what the gallery itself looks like.
        tall = QRectF(L, T, (R - L) * 0.5, B - T)
        painter.drawRect(tall)
        narrow = (R - L) * 0.44
        painter.drawRect(QRectF(tall.right() + w * 0.06, T, narrow,
                                (B - T) * 0.44))
        painter.drawRect(QRectF(tall.right() + w * 0.06, T + (B - T) * 0.56,
                                narrow, (B - T) * 0.44))
        return True

    if name in {"ellipse", "rounded-rect", "line-shape", "diamond-shape"}:
        box = QRectF(L, T, R - L, B - T)
        if name == "ellipse":
            painter.drawEllipse(box)
        elif name == "rounded-rect":
            painter.drawRoundedRect(box, max(2.0, w * 0.14), max(2.0, w * 0.14))
        elif name == "line-shape":
            painter.drawLine(QPointF(L, B), QPointF(R, T))
        else:
            path = QPainterPath()
            path.moveTo(cx, T)
            path.lineTo(R, cy)
            path.lineTo(cx, B)
            path.lineTo(L, cy)
            path.closeSubpath()
            painter.drawPath(path)
        return True

    if name in {"zoom-fit", "fit-page", "fullscreen"}:
        painter.drawRect(QRectF(L, T, R - L, B - T))
        for corner, dx, dy in ((QPointF(L + 2, T + 2), 1, 1), (QPointF(R - 2, T + 2), -1, 1),
                               (QPointF(L + 2, B - 2), 1, -1), (QPointF(R - 2, B - 2), -1, -1)):
            painter.drawLine(corner, QPointF(corner.x() + dx * w * 0.14, corner.y()))
            painter.drawLine(corner, QPointF(corner.x(), corner.y() + dy * h * 0.14))
        return True

    if name in {"zoom-in", "zoom-out", "zoom", "search"}:
        r = min(w, h) * 0.34
        lens = QRectF(L, T, r * 2, r * 2)
        painter.drawEllipse(lens)
        painter.drawLine(QPointF(lens.right() - r * 0.35, lens.bottom() - r * 0.35),
                         QPointF(R - 1, B - 1))
        if name != "zoom":
            mid_x, mid_y = lens.center().x(), lens.center().y()
            painter.drawLine(QPointF(mid_x - r * 0.45, mid_y),
                             QPointF(mid_x + r * 0.45, mid_y))
            if name == "zoom-in":
                painter.drawLine(QPointF(mid_x, mid_y - r * 0.45),
                                 QPointF(mid_x, mid_y + r * 0.45))
        return True

    if name == "hyperlink":
        pen = QPen(QColor(ink), max(1.4, w * 0.09))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        link_w, link_h = w * 0.40, h * 0.26
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-40)
        painter.drawRoundedRect(QRectF(-link_w - link_w * 0.42, -link_h / 2,
                                       link_w, link_h), link_h / 2, link_h / 2)
        painter.drawRoundedRect(QRectF(link_w * 0.42, -link_h / 2, link_w, link_h),
                                link_h / 2, link_h / 2)
        painter.drawLine(QPointF(-link_w * 0.42, 0), QPointF(link_w * 0.42, 0))
        painter.restore()
        return True

    if name in {"select-all"}:
        dashed = QPen(QColor(ink), max(1.0, w * 0.05))
        dashed.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(dashed)
        outer = QRectF(L, T, R - L, B - T)
        painter.drawRect(outer)
        _pen(painter, ink, w)
        inner = outer.adjusted(outer.width() * 0.3, outer.height() * 0.3,
                              -outer.width() * 0.12, -outer.height() * 0.12)
        _fill(painter, ink)
        painter.setPen(QPen(QColor(ink)))
        painter.drawRect(inner)
        _no_fill(painter)
        return True

    return False

