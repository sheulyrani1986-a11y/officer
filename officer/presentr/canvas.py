"""Interactive 2D Graphics Canvas for slide layout and editing."""

import math
import os
from typing import Optional, List
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtWidgets import (
    QWidget, QGraphicsScene, QGraphicsView, QGraphicsItem,
    QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsTextItem,
    QGraphicsPixmapItem, QGraphicsPathItem, QVBoxLayout, QStyle
)
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPixmap, QTransform,
    QTextBlockFormat, QTextCursor, QLinearGradient
)
from officer.presentr.slide_deck import (
    DEFAULT_FONT_FAMILY, Slide, SlideObject, TextObject, ShapeObject, ImageObject
)

# PowerPoint's paragraph alignment names, as stored on TextObject.alignment.
ALIGNMENTS = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
}


def set_text_alignment(item: QGraphicsTextItem, name: str) -> None:
    """Align every paragraph of *item* the way the slide model asks for."""
    option = item.document().defaultTextOption()
    option.setAlignment(ALIGNMENTS.get(name, Qt.AlignmentFlag.AlignLeft))
    item.document().setDefaultTextOption(option)
    item.update()


def apply_text_style(item: QGraphicsTextItem, obj: TextObject) -> None:
    """Render *obj*'s character and paragraph formatting through *item*.

    PowerPoint's ribbon commands address the selection; a shape here carries one
    style for its whole text, so the font is set on the item as a unit.
    """
    font = QFont(obj.font_family or DEFAULT_FONT_FAMILY, obj.font_size)
    font.setBold(obj.bold)
    font.setItalic(obj.italic)
    font.setUnderline(obj.underline)
    font.setStrikeOut(obj.strike)
    item.setFont(font)
    item.setDefaultTextColor(QColor(obj.text_color))
    # PowerPoint keeps the paragraph alignment on the shape, so the scene has to
    # honour it or the ribbon's align buttons look dead. QGraphicsTextItem takes
    # alignment through the document's default text option.
    set_text_alignment(item, obj.alignment)
    # Qt's line height is a percentage of the text's own height, so PowerPoint's
    # "1.5" is 150. A value of 1.0 has to write SingleHeight back, or a box that
    # was once loosened would never tighten again.
    block = QTextBlockFormat()
    if obj.line_spacing == 1.0:
        block.setLineHeight(100.0, QTextBlockFormat.LineHeightTypes.SingleHeight.value)
    else:
        block.setLineHeight(obj.line_spacing * 100.0,
                            QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
    cursor = item.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeBlockFormat(block)
    cursor.clearSelection()
    item.setTextCursor(cursor)


#: PresentR's drawing units are PowerPoint's: 96 to the inch.
PX_PER_CM = 96 / 2.54

#: Every auto-shape the Insert ▸ Shapes gallery offers, in the order PowerPoint
#: groups them: rectangles, basic shapes, arrows, stars and banners.
SHAPE_KEYS = (
    "rect", "rounded_rect", "ellipse", "triangle", "right_triangle", "diamond",
    "pentagon", "hexagon", "octagon", "star", "star_4", "arrow", "double_arrow",
    "down_arrow", "chevron", "parallelogram", "trapezoid", "plus", "heart",
    "donut", "pie", "frame", "line",
)

#: The box a shape lands in when it is inserted, in centimetres. PowerPoint
#: gives a line a line's box rather than the square it uses for a rectangle.
SHAPE_BOXES_CM = {
    "line": (8.0, 0.1), "arrow": (4.8, 1.6), "double_arrow": (4.8, 1.6),
    "down_arrow": (1.6, 4.8),
}
DEFAULT_SHAPE_BOX_CM = (4.8, 3.2)


def shape_pen(obj: ShapeObject) -> QPen:
    """The outline a shape is drawn with, which a width of none switches off.

    Qt reads a zero-width pen as "one pixel wide whatever the zoom", so the
    ribbon's no-outline answer has to reach :class:`QPen` as a style, not a
    width, or a shape the presenter meant to sit flat on the slide keeps a
    hairline of its own.
    """
    pen = QPen(QColor(obj.border_color), max(1, obj.border_width))
    if obj.border_width <= 0:
        pen.setStyle(Qt.PenStyle.NoPen)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def shape_box(shape_type: str) -> tuple:
    """Width and height in slide units for a newly inserted *shape_type*."""
    wide_cm, tall_cm = SHAPE_BOXES_CM.get(shape_type, DEFAULT_SHAPE_BOX_CM)
    return wide_cm * PX_PER_CM, tall_cm * PX_PER_CM


#: For each of the eight selection handles, where the part of the box that stays
#: put sits: the bottom-right handle is anchored at the top-left corner, and the
#: ``0.5`` entries are the edge handles, which move one side only.
HANDLE_ANCHORS = (
    (1.0, 1.0), (0.5, 1.0), (0.0, 1.0), (0.0, 0.5),
    (0.0, 0.0), (0.5, 0.0), (1.0, 0.0), (1.0, 0.5),
)


def dragged_box(original: QRectF, handle: int, here: QPointF) -> QRectF:
    """The box described by pulling *handle* of *original* out to *here*."""
    fx, fy = HANDLE_ANCHORS[handle]
    anchor = QPointF(original.x() + fx * original.width(),
                     original.y() + fy * original.height())
    wide = original.width() if fx == 0.5 else abs(here.x() - anchor.x())
    tall = original.height() if fy == 0.5 else abs(here.y() - anchor.y())
    left = original.x() if fx == 0.5 else min(anchor.x(), here.x())
    top = original.y() if fy == 0.5 else min(anchor.y(), here.y())
    return QRectF(left, top, wide, tall)


def _fill_box(path: QPainterPath, rect: QRectF) -> QPainterPath:
    """Stretch *path* so its own outline lands exactly on *rect*.

    A pentagon drawn from a circle stops short of the box it was given; the
    presenter sized the box, so the shape has to fill it.
    """
    bounds = path.boundingRect()
    if bounds.width() <= 0 or bounds.height() <= 0:
        return path
    transform = QTransform()
    transform.translate(rect.x(), rect.y())
    transform.scale(rect.width() / bounds.width(), rect.height() / bounds.height())
    transform.translate(-bounds.x(), -bounds.y())
    return transform.map(path)


def _polygon(rect: QRectF, points: int, start_deg: float = -90.0) -> QPainterPath:
    """Path for a *points*-sided regular polygon inscribed in *rect*."""
    cx, cy = rect.center().x(), rect.center().y()
    step = 360.0 / points
    path = QPainterPath()
    for i in range(points):
        angle = math.radians(start_deg + step * i)
        point = QPointF(cx + rect.width() / 2 * math.cos(angle),
                        cy + rect.height() / 2 * math.sin(angle))
        if i == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return _fill_box(path, rect)


def _star(rect: QRectF, points: int, inner: float = 0.4) -> QPainterPath:
    """Path for a *points*-pointed star whose inner radius is *inner* of the outer."""
    cx, cy = rect.center().x(), rect.center().y()
    path = QPainterPath()
    for i in range(points * 2):
        angle = math.radians(180.0 / points * i - 90.0)
        radius = (inner if i % 2 else 1.0)
        point = QPointF(cx + rect.width() / 2 * radius * math.cos(angle),
                        cy + rect.height() / 2 * radius * math.sin(angle))
        if i == 0:
            path.moveTo(point)
        else:
            path.lineTo(point)
    path.closeSubpath()
    return _fill_box(path, rect)


def _ring(rect: QRectF, inner: float) -> QPainterPath:
    """A filled ring: the outer ellipse with a concentric hole cut out of it."""
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.OddEvenFill)
    path.addEllipse(rect)
    hole_w = rect.width() * inner
    hole_h = rect.height() * inner
    path.addEllipse(QRectF(rect.center().x() - hole_w / 2,
                           rect.center().y() - hole_h / 2, hole_w, hole_h))
    return path


def _arrow_shaft(rect: QRectF, head: float, both: bool) -> QPainterPath:
    """A block arrow across *rect*: a shaft with one head, or with two."""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    shaft_h = h / 3.0
    shaft_y = y + h / 2.0 - shaft_h / 2.0
    left = x + (head * w if both else 0.0)
    right = x + w - head * w
    path = QPainterPath()
    path.moveTo(left, shaft_y)
    path.lineTo(right, shaft_y)
    path.lineTo(right, y)
    path.lineTo(x + w, y + h / 2)
    path.lineTo(right, y + h)
    path.lineTo(right, shaft_y + shaft_h)
    path.lineTo(left, shaft_y + shaft_h)
    if both:
        path.lineTo(left, y + h)
        path.lineTo(x, y + h / 2)
        path.lineTo(left, y)
    path.closeSubpath()
    return path


def shape_path(shape_type: str, rect: QRectF) -> Optional[QPainterPath]:
    """Outline for PowerPoint's auto-shapes, or None for plain rect/ellipse.

    The Insert tab's gallery is drawn from this, so a key that is missing here
    would land on the slide as a rectangle and the two would look identical.
    """
    x, y = rect.x(), rect.y()
    w, h = rect.width(), rect.height()
    path = QPainterPath()

    if shape_type in ("rect", "rectangle", "ellipse"):
        return None

    if shape_type == "rounded_rect":
        path.addRoundedRect(rect, min(w, h) * 0.12, min(w, h) * 0.12)
        return path
    if shape_type == "triangle":
        path.moveTo(x + w / 2, y)
        path.lineTo(x + w, y + h)
        path.lineTo(x, y + h)
    elif shape_type == "right_triangle":
        path.moveTo(x, y)
        path.lineTo(x + w, y + h)
        path.lineTo(x, y + h)
    elif shape_type == "diamond":
        path.moveTo(x + w / 2, y)
        path.lineTo(x + w, y + h / 2)
        path.lineTo(x + w / 2, y + h)
        path.lineTo(x, y + h / 2)
    elif shape_type == "pentagon":
        return _polygon(rect, 5)
    elif shape_type == "hexagon":
        return _polygon(rect, 6, start_deg=0.0)
    elif shape_type == "octagon":
        return _polygon(rect, 8, start_deg=-22.5)
    elif shape_type == "star":
        return _star(rect, 5)
    elif shape_type == "star_4":
        return _star(rect, 4, inner=0.34)
    elif shape_type == "arrow":
        return _arrow_shaft(rect, 1 / 3.0, both=False)
    elif shape_type == "double_arrow":
        return _arrow_shaft(rect, 1 / 3.0, both=True)
    elif shape_type == "down_arrow":
        shaft_w = w / 3.0
        shaft_x = x + w / 2.0 - shaft_w / 2.0
        head_h = h / 3.0
        path.moveTo(shaft_x, y)
        path.lineTo(shaft_x + shaft_w, y)
        path.lineTo(shaft_x + shaft_w, y + h - head_h)
        path.lineTo(x + w, y + h - head_h)
        path.lineTo(x + w / 2, y + h)
        path.lineTo(x, y + h - head_h)
        path.lineTo(shaft_x, y + h - head_h)
    elif shape_type == "chevron":
        notch = min(w, h) * 0.25
        path.moveTo(x, y)
        path.lineTo(x + w - notch, y)
        path.lineTo(x + w, y + h / 2)
        path.lineTo(x + w - notch, y + h)
        path.lineTo(x, y + h)
        path.lineTo(x + notch, y + h / 2)
    elif shape_type == "parallelogram":
        notch = w * 0.2
        path.moveTo(x + notch, y)
        path.lineTo(x + w, y)
        path.lineTo(x + w - notch, y + h)
        path.lineTo(x, y + h)
    elif shape_type == "trapezoid":
        inset = w * 0.2
        path.moveTo(x + inset, y)
        path.lineTo(x + w - inset, y)
        path.lineTo(x + w, y + h)
        path.lineTo(x, y + h)
    elif shape_type == "plus":
        arm = min(w, h) / 3.0
        path.moveTo(x + (w - arm) / 2, y)
        path.lineTo(x + (w + arm) / 2, y)
        path.lineTo(x + (w + arm) / 2, y + (h - arm) / 2)
        path.lineTo(x + w, y + (h - arm) / 2)
        path.lineTo(x + w, y + (h + arm) / 2)
        path.lineTo(x + (w + arm) / 2, y + (h + arm) / 2)
        path.lineTo(x + (w + arm) / 2, y + h)
        path.lineTo(x + (w - arm) / 2, y + h)
        path.lineTo(x + (w - arm) / 2, y + (h + arm) / 2)
        path.lineTo(x, y + (h + arm) / 2)
        path.lineTo(x, y + (h - arm) / 2)
        path.lineTo(x + (w - arm) / 2, y + (h - arm) / 2)
    elif shape_type == "heart":
        # Two cubic arcs from the notch down to the point, as PowerPoint draws it.
        path.moveTo(x + w / 2, y + h)
        path.cubicTo(x - w * 0.1, y + h * 0.55, x + w * 0.12, y - h * 0.08,
                     x + w / 2, y + h * 0.28)
        path.cubicTo(x + w * 0.88, y - h * 0.08, x + w * 1.1, y + h * 0.55,
                     x + w / 2, y + h)
        path.closeSubpath()
        return _fill_box(path, rect)
    elif shape_type == "donut":
        return _ring(rect, 0.55)
    elif shape_type == "frame":
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addRect(rect)
        inset_w, inset_h = w * 0.22, h * 0.22
        path.addRect(QRectF(x + inset_w / 2, y + inset_h / 2,
                            w - inset_w, h - inset_h))
    elif shape_type == "pie":
        path.moveTo(x + w / 2, y + h / 2)
        path.lineTo(x + w, y + h / 2)
        path.arcTo(rect, 0.0, 270.0)
    elif shape_type == "line":
        # An open stroke, not a filled region.
        path.moveTo(x, y + h)
        path.lineTo(x + w, y)
        return path
    else:
        return None

    path.closeSubpath()
    return path


def shape_brush(obj: ShapeObject) -> QBrush:
    """The paint inside a shape: one colour, or PowerPoint's two-stop gradient."""
    if not obj.gradient_color:
        return QBrush(QColor(obj.fill_color))
    gradient = QLinearGradient(0, 0, max(1.0, obj.width), max(1.0, obj.height))
    gradient.setColorAt(0.0, QColor(obj.fill_color))
    gradient.setColorAt(1.0, QColor(obj.gradient_color))
    brush = QBrush(gradient)
    return brush


class _NoMarquee:
    """Qt paints a dashed marquee over a selected item; PowerPoint paints handles.

    The canvas already draws its own selection frame, so the item's own would
    only be a second box around the same object.
    """

    def paint(self, painter, option, widget=None) -> None:
        option.state &= ~QStyle.StateFlag.State_Selected
        super().paint(painter, option, widget)


class ShapeRectItem(_NoMarquee, QGraphicsRectItem):
    pass


class ShapeEllipseItem(_NoMarquee, QGraphicsEllipseItem):
    pass


class ShapePathItem(_NoMarquee, QGraphicsPathItem):
    pass


class SlideCanvasScene(QGraphicsScene):
    """QGraphicsScene representing a 16:9 widescreen presentation slide."""

    selectionChangedSignal = Signal()

    def __init__(self, width: int = 960, height: int = 540, parent = None):
        super().__init__(0, 0, width, height, parent)
        self.slide_width = width
        self.slide_height = height
        self.current_slide: Optional[Slide] = None

        # Background slide paper item
        self.bg_item = QGraphicsRectItem(0, 0, width, height)
        self.bg_item.setBrush(QBrush(QColor("#FFFFFF")))
        self.bg_item.setPen(QPen(QColor("#D1D5DB"), 1))
        self.bg_item.setZValue(-100)
        self.addItem(self.bg_item)

        self.selectionChanged.connect(self.selectionChangedSignal.emit)

    def load_slide(self, slide: Slide) -> None:
        """Populate the scene from the Slide data model."""
        self.current_slide = slide
        self._loading = True
        try:
            self._rebuild_from_slide(slide)
        finally:
            # Removing and adding items emits selectionChanged; a command that
            # answered it by writing the scene back would store a half-built
            # slide and silently delete objects.
            self._loading = False

    def _rebuild_from_slide(self, slide: Slide) -> None:
        # Clear existing items except background
        for item in list(self.items()):
            if item != self.bg_item:
                self.removeItem(item)

        # Set background color
        self.bg_item.setBrush(QBrush(QColor(slide.background_color)))

        for obj in slide.objects:
            if isinstance(obj, TextObject):
                self._add_text_item(obj)
            elif isinstance(obj, ShapeObject):
                self._add_shape_item(obj)
            elif isinstance(obj, ImageObject):
                self._add_image_item(obj)

    def _add_text_item(self, obj: TextObject) -> QGraphicsTextItem:
        item = QGraphicsTextItem()
        item.setPlainText(obj.text)
        apply_text_style(item, obj)
        item.setTextWidth(obj.width)
        item.setPos(obj.x, obj.y)
        item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        item.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        item.setData(0, obj)
        self.addItem(item)
        return item

    def _add_shape_item(self, obj: ShapeObject) -> QGraphicsItem:
        item = self._build_shape_item(obj)
        item.setPos(obj.x, obj.y)
        item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        item.setData(0, obj)
        self.addItem(item)
        return item

    @staticmethod
    def _build_shape_item(obj: ShapeObject) -> QGraphicsItem:
        """A shape item drawn to match *obj*, ready to be placed on the scene."""
        rect = QRectF(0, 0, obj.width, obj.height)
        pen = shape_pen(obj)

        outline = shape_path(obj.shape_type, rect)
        if outline is None:
            if obj.shape_type == "ellipse":
                item: QGraphicsItem = ShapeEllipseItem(rect)
            else:
                item = ShapeRectItem(rect)
        else:
            # A path item paints whichever auto-shape was asked for, so the
            # ribbon's shape buttons visibly do something.
            item = ShapePathItem(outline)

        item.setPen(pen)
        item.setBrush(shape_brush(obj))
        if obj.rotation:
            # PowerPoint turns a shape about its own middle, not about the
            # slide's corner the way QGraphicsItem's transform would.
            item.setTransformOriginPoint(rect.center())
            item.setRotation(obj.rotation)
        return item

    @staticmethod
    def _redraw_shape(item: QGraphicsItem, obj: ShapeObject) -> None:
        """Re-cut *item*'s outline, paint and turn for the shape it now shows."""
        rect = QRectF(0, 0, obj.width, obj.height)
        if isinstance(item, QGraphicsRectItem):
            item.setRect(rect)
        elif isinstance(item, QGraphicsEllipseItem):
            item.setRect(rect)
        elif isinstance(item, QGraphicsPathItem):
            outline = shape_path(obj.shape_type, rect)
            item.setPath(outline if outline is not None
                         else QPainterPath(rect))
        item.setPen(shape_pen(obj))
        item.setBrush(shape_brush(obj))
        item.setTransformOriginPoint(rect.center())
        item.setRotation(obj.rotation)

    def _add_image_item(self, obj: ImageObject) -> Optional[QGraphicsPixmapItem]:
        if not os.path.exists(obj.image_path):
            return None
        pix = QPixmap(obj.image_path)
        if pix.isNull():
            return None

        item = QGraphicsPixmapItem(pix)
        item.setData(1, pix)
        item.setPos(obj.x, obj.y)
        item.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        )
        item.setData(0, obj)
        self._scale_image_item(item, obj)
        self.addItem(item)
        return item

    @staticmethod
    def _scale_image_item(item: QGraphicsPixmapItem, obj: ImageObject) -> None:
        """Draw *item* at the box the model carries, keeping the picture's shape.

        The original pixmap stays on the item, so a picture shrunk and grown
        again returns to its own pixels rather than a blur of the last scale.
        """
        original = item.data(1)
        if not isinstance(original, QPixmap) or original.isNull():
            return
        scaled = original.scaled(int(obj.width), int(obj.height),
                                 Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        item.setPixmap(scaled)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)

    # -- editing what is selected --------------------------------------------- #

    def _selected_objects(self) -> List[tuple]:
        """(item, object) pairs for the selection, background and strays aside."""
        pairs = []
        for item in self.selectedItems():
            obj = item.data(0)
            if obj is not None and item != self.bg_item:
                pairs.append((item, obj))
        return pairs

    def selection_info(self) -> Optional[dict]:
        """The one selected object as the ribbon shows it, or ``None``.

        Nothing is reported for a multi-selection: PowerPoint's size boxes go
        blank rather than showing one object's numbers for three of them.
        """
        pairs = self._selected_objects()
        if len(pairs) != 1:
            return None
        _, obj = pairs[0]
        info = {
            "kind": ("shape" if isinstance(obj, ShapeObject) else
                     "picture" if isinstance(obj, ImageObject) else "text"),
            "x_cm": obj.x / PX_PER_CM, "y_cm": obj.y / PX_PER_CM,
            "width_cm": obj.width / PX_PER_CM,
            "height_cm": obj.height / PX_PER_CM,
            "rotation": getattr(obj, "rotation", 0.0),
            "animation": obj.animation,
        }
        if isinstance(obj, ShapeObject):
            info.update(shape_type=obj.shape_type, fill_color=obj.fill_color,
                        gradient_color=obj.gradient_color,
                        border_color=obj.border_color,
                        border_width=obj.border_width)
        return info

    def selection_rect(self) -> Optional[QRectF]:
        """The box of the one selected object, in slide units."""
        pairs = self._selected_objects()
        if len(pairs) != 1:
            return None
        _, obj = pairs[0]
        return QRectF(obj.x, obj.y, obj.width, obj.height)

    def set_selection_box(self, x: Optional[float] = None, y: Optional[float] = None,
                          width: Optional[float] = None,
                          height: Optional[float] = None) -> bool:
        """Place and size the selected object in slide units, and redraw it.

        The model keeps the box the presenter asked for; a picture's own drawing
        fits inside it, which is what PowerPoint's Size pane does too.
        """
        pairs = self._selected_objects()
        if not pairs:
            return False
        for item, obj in pairs:
            if x is not None:
                obj.x = max(0.0, float(x))
            if y is not None:
                obj.y = max(0.0, float(y))
            if width is not None:
                obj.width = min(float(width), self.slide_width * 4)
            if height is not None:
                obj.height = min(float(height), self.slide_height * 4)
            item.setPos(obj.x, obj.y)
            if isinstance(obj, ShapeObject):
                self._redraw_shape(item, obj)
            elif isinstance(obj, ImageObject):
                self._scale_image_item(item, obj)
            item.update()
        return True

    def set_selection_paint(self, **colour: Optional[str]) -> bool:
        """Recolour the selected shapes: ``fill``, ``gradient`` or ``border``.

        A gradient of ``None`` means "back to one flat colour", the way clearing
        PowerPoint's second stop does.
        """
        pairs = [(item, obj) for item, obj in self._selected_objects()
                 if isinstance(obj, ShapeObject)]
        if not pairs:
            return False
        for item, obj in pairs:
            if "fill" in colour and colour["fill"]:
                obj.fill_color = colour["fill"]
            if "gradient" in colour:
                obj.gradient_color = colour["gradient"] or None
            if "border" in colour and colour["border"]:
                obj.border_color = colour["border"]
            if "border_width" in colour and colour["border_width"] is not None:
                obj.border_width = max(0, int(colour["border_width"]))
            self._redraw_shape(item, obj)
        return True

    def scale_selection(self, factor: float) -> bool:
        """Grow or shrink the selection about its own centre, ratio kept."""
        pairs = self._selected_objects()
        if not pairs:
            return False
        for item, obj in pairs:
            wide, tall = obj.width * factor, obj.height * factor
            obj.x += (obj.width - wide) / 2
            obj.y += (obj.height - tall) / 2
            obj.width, obj.height = wide, tall
            item.setPos(obj.x, obj.y)
            if isinstance(obj, ShapeObject):
                self._redraw_shape(item, obj)
            elif isinstance(obj, ImageObject):
                self._scale_image_item(item, obj)
        return True

    def reset_selection_size(self) -> bool:
        """Give the selected pictures their own pixels back, shapes their default box."""
        pairs = self._selected_objects()
        if not pairs:
            return False
        for item, obj in pairs:
            if isinstance(obj, ImageObject):
                pix = QPixmap(obj.image_path)
                if not pix.isNull():
                    obj.width, obj.height = pix.width(), pix.height()
            elif isinstance(obj, ShapeObject):
                obj.width, obj.height = shape_box(obj.shape_type)
            item.setPos(obj.x, obj.y)
            if isinstance(obj, ShapeObject):
                self._redraw_shape(item, obj)
            elif isinstance(obj, ImageObject):
                self._scale_image_item(item, obj)
        return True

    def set_selection_animation(self, name: str) -> bool:
        """Say how the selected objects arrive during the show.

        The canvas itself never hides anything on the way: an animated object
        looks finished while it is being laid out, and only the presenter holds
        it back until its turn.
        """
        pairs = self._selected_objects()
        if not pairs:
            return False
        for _, obj in pairs:
            obj.animation = name
        return True

    def set_selection_rotation(self, degrees: float) -> bool:
        """Turn the selected shapes to *degrees*, the way PowerPoint's rotate box does."""
        pairs = [(item, obj) for item, obj in self._selected_objects()
                 if isinstance(obj, ShapeObject)]
        if not pairs:
            return False
        for item, obj in pairs:
            obj.rotation = float(degrees) % 360.0
            item.setRotation(obj.rotation)
        return True

    def sync_to_slide(self) -> None:
        """Write item positions and text back to the Slide model."""
        if self._loading or not self.current_slide:
            return

        new_objects: List[SlideObject] = []
        for item in self.items():
            if item == self.bg_item:
                continue

            obj = item.data(0)
            if obj is None:
                continue

            pos = item.pos()
            obj.x = pos.x()
            obj.y = pos.y()

            if isinstance(item, QGraphicsTextItem) and isinstance(obj, TextObject):
                obj.text = item.toPlainText()
                obj.width = item.textWidth()

            new_objects.append(obj)

        self.current_slide.objects = new_objects


class SlideCanvasView(QGraphicsView):
    """Interactive viewport for presenting and manipulating the slide scene."""

    #: PowerPoint's selection squares, drawn at a fixed size on the screen so
    #: they stay grabbable however far the slide is zoomed out.
    HANDLE_PX = 7

    def __init__(self, scene: SlideCanvasScene, parent: Optional[QWidget] = None):
        super().__init__(scene, parent)
        self.setObjectName("SlideCanvasView")
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        # While True the slide is scaled to the viewport on every resize; the
        # zoom slider turns it off so an explicit zoom level is preserved.
        self._fit_to_view = True
        # (handle index, box before the drag) while a handle is being pulled.
        self._resize_drag: Optional[tuple] = None

    @property
    def fit_to_view(self) -> bool:
        return self._fit_to_view

    def set_fit_to_view(self, fit: bool) -> None:
        """Enable or disable automatic scaling of the slide to the viewport."""
        self._fit_to_view = fit

    def fit_slide_to_view(self) -> None:
        """Scale the slide to the viewport (also reapplied on resize while fitted)."""
        if self._fit_to_view and self.scene():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_slide_to_view()

    # -- resizing by hand ------------------------------------------------------ #

    #: The arrow each handle asks for, so the pointer says which way it pulls.
    _CURSORS = (
        Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeVerCursor,
        Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeHorCursor,
        Qt.CursorShape.SizeFDiagCursor, Qt.CursorShape.SizeVerCursor,
        Qt.CursorShape.SizeBDiagCursor, Qt.CursorShape.SizeHorCursor,
    )

    def _handle_points(self) -> List[QPointF]:
        """The eight selection handles of the one selected object, in view coords."""
        scene = self.scene()
        if not isinstance(scene, SlideCanvasScene):
            return []
        box = scene.selection_rect()
        if box is None:
            return []
        corners = [box.topLeft(), QPointF(box.center().x(), box.top()),
                   box.topRight(), QPointF(box.right(), box.center().y()),
                   box.bottomRight(), QPointF(box.center().x(), box.bottom()),
                   box.bottomLeft(), QPointF(box.left(), box.center().y())]
        return [self.mapFromScene(point) for point in corners]

    def _handle_under(self, position: QPointF) -> int:
        """The handle within reach of *position* (view coords), or -1."""
        reach = self.HANDLE_PX + 2
        for index, point in enumerate(self._handle_points()):
            if (abs(point.x() - position.x()) <= reach
                    and abs(point.y() - position.y()) <= reach):
                return index
        return -1

    def mousePressEvent(self, event) -> None:
        scene = self.scene()
        if event.button() == Qt.MouseButton.LeftButton and isinstance(scene, SlideCanvasScene):
            index = self._handle_under(event.position())
            if index >= 0 and scene.selection_rect() is not None:
                self._resize_drag = (index, scene.selection_rect())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        scene = self.scene()
        if self._resize_drag is not None and isinstance(scene, SlideCanvasScene):
            handle, original = self._resize_drag
            here = self.mapToScene(event.position().toPoint())
            box = dragged_box(original, handle, here)
            if box.width() > 2 and box.height() > 2:
                scene.set_selection_box(x=box.x(), y=box.y(),
                                        width=box.width(), height=box.height())
                scene.sync_to_slide()
                self.viewport().update()
            event.accept()
            return
        if isinstance(scene, SlideCanvasScene):
            index = self._handle_under(event.position())
            self.viewport().setCursor(self._CURSORS[index] if index >= 0
                                      else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._resize_drag is not None:
            self._resize_drag = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """PowerPoint's selection frame: a hairline box with eight solid squares."""
        super().drawForeground(painter, rect)
        points = self._handle_points()
        if not points:
            return
        painter.save()
        painter.resetTransform()
        box = QRectF(points[0], points[4]).normalized()
        painter.setPen(QPen(QColor("#1D4ED8"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box)
        half = self.HANDLE_PX / 2
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        for point in points:
            painter.drawRect(QRectF(point.x() - half, point.y() - half,
                                    self.HANDLE_PX, self.HANDLE_PX))
        painter.restore()

    def keyPressEvent(self, event) -> None:
        # Delete selected shapes/objects if Del key pressed
        if event.key() == Qt.Key.Key_Delete:
            scene = self.scene()
            if isinstance(scene, SlideCanvasScene):
                for item in scene.selectedItems():
                    if item != scene.bg_item and not (isinstance(item, QGraphicsTextItem) and item.hasFocus()):
                        scene.removeItem(item)
                return
        super().keyPressEvent(event)


def render_slide_to_pixmap(slide: Slide, target_width: int = 160,
                           slide_size=(960, 540)) -> QPixmap:
    """Paint *slide* small enough for the thumbnail pane and the slide sorter.

    A throwaway :class:`SlideCanvasScene` does the drawing, so a thumbnail can
    never drift from what the editor shows for the same model.
    """
    scene_w, scene_h = slide_size
    scene = SlideCanvasScene(scene_w, scene_h)
    scene.load_slide(slide)

    height = max(1, int(round(target_width * scene_h / float(scene_w))))
    pixmap = QPixmap(max(1, int(target_width)), height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHints(QPainter.RenderHint.Antialiasing
                           | QPainter.RenderHint.TextAntialiasing
                           | QPainter.RenderHint.SmoothPixmapTransform)
    scene.render(painter, QRectF(0, 0, pixmap.width(), pixmap.height()),
                 QRectF(0, 0, scene_w, scene_h))
    painter.end()
    return pixmap

