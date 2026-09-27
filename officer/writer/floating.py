"""Pictures and shapes that lie on the sheet instead of inside the words.

Word keeps two kinds of picture. One is a character: it travels with the
sentence, and the lines above and below are its neighbours. The other is an
object pinned to the page, which you drag where you want and the writing flows
round. This module is the second kind.

The object is a widget living in the text edit's viewport, which is the same
coordinate space :meth:`QTextEdit.cursorRect` reports, so it rides the scroll
with the lines it was placed beside. Its measurements are the centimetres the
ribbon shows and the sheet prints; the pixels are the zoomed ones the viewport
paints, so every geometry call goes through the page's ``to_display``.
"""

from typing import Optional, Tuple
from PySide6.QtCore import Qt, QRect, QPoint, Signal
from PySide6.QtGui import QCursor, QImage, QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget

#: Millimetres and centimetres → the 96 DPI pixels Word lays the page out in.
#: The page widget keeps this name so that the rest of the writer, and its
#: tests, read the measurement from one place.
PX_PER_CM = 96.0 / 2.54

#: Word's handle: a small square on the outline of the selected object.
HANDLE_PX = 8

#: The breathing gap Word leaves between a wrapped object and the text beside it.
WRAP_GAP_CM = 0.25

#: The smallest object that can still be picked up and dragged about.
MIN_SIZE_CM = 0.5

#: The eight places Office lets you grip a selected object.
SIDES = ("top-left", "top", "top-right", "right", "bottom-right", "bottom",
         "bottom-left", "left")

_HANDLE_CURSORS = {
    "top": Qt.CursorShape.SizeVerCursor,
    "bottom": Qt.CursorShape.SizeVerCursor,
    "left": Qt.CursorShape.SizeHorCursor,
    "right": Qt.CursorShape.SizeHorCursor,
    "top-left": Qt.CursorShape.SizeFDiagCursor,
    "bottom-right": Qt.CursorShape.SizeFDiagCursor,
    "top-right": Qt.CursorShape.SizeBDiagCursor,
    "bottom-left": Qt.CursorShape.SizeBDiagCursor,
}


class FloatPictureWidget(QWidget):
    """A picture or shape pinned to the page, which the user drags and stretches.

    The centimetres are the object's own, measured from the edges of the sheet;
    the widget's geometry is those centimetres as the page currently draws them.
    Movement is expressed against the box the drag started from, so zooming
    never changes how far the pointer carries the object.
    """

    #: The object moved or changed size: the words need laying out round it.
    geometryChanged = Signal()

    def __init__(self, filepath: str, page, x_cm: float, y_cm: float,
                 wide_cm: float, tall_cm: float, wrap: bool = True,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._image = QImage(filepath)
        self.page = page
        self.filepath = filepath
        self.x_cm = x_cm
        self.y_cm = y_cm
        self.width_cm = wide_cm
        self.height_cm = tall_cm
        self.wrap = wrap
        self._selected = False
        #: The paragraph the object hangs on, and its distance below that
        #: paragraph's first line. Word moves an object with its anchor, and
        #: so do we: writing above the object must not bury it.
        self.anchor = None
        self.anchor_offset_cm = 0.0
        self._drag = None            # (side, start point, box at start)
        self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        # The grips are only grips once the pointer is over them, and Qt sends
        # a move to a widget that nobody is pressing on only if it asks.
        self.setMouseTracking(True)
        self.set_rect_cm(x_cm, y_cm, wide_cm, tall_cm)

    # -- measurements ------------------------------------------------------- #

    @property
    def rect_cm(self) -> Tuple[float, float, float, float]:
        """(left, top, width, height) from the edges of the sheet, in cm."""
        return (self.x_cm, self.y_cm, self.width_cm, self.height_cm)

    def set_rect_cm(self, x_cm: float, y_cm: float, wide_cm: float,
                    tall_cm: float) -> None:
        """Place the object at sheet measurements of *page*'s own choosing."""
        self.x_cm = x_cm
        self.y_cm = y_cm
        self.width_cm = max(MIN_SIZE_CM, wide_cm)
        self.height_cm = max(MIN_SIZE_CM, tall_cm)
        self._apply()
        self.geometryChanged.emit()

    def _apply(self) -> None:
        self.setGeometry(self.viewport_rect())
        self.update()

    def viewport_rect(self) -> QRect:
        """Where the object is painted, in the space the text is measured in."""
        return QRect(
            round(self.page.to_display(self.x_cm * PX_PER_CM)),
            round(self.page.to_display(self.y_cm * PX_PER_CM)
                  - self.page.scroll_offset_px()),
            max(1, round(self.page.to_display(self.width_cm * PX_PER_CM))),
            max(1, round(self.page.to_display(self.height_cm * PX_PER_CM))))

    def relayout(self) -> None:
        """Re-measure: the zoom, the paper or the text under it has shifted."""
        self._apply()

    # -- selection ---------------------------------------------------------- #

    @property
    def selected(self) -> bool:
        """Whether the ribbon is editing this object, handles and all."""
        return self._selected

    @selected.setter
    def selected(self, chosen: bool) -> None:
        if chosen != self._selected:
            self._selected = chosen
            if not chosen:
                self._drag = None
                self.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
            self.update()

    # -- painting ----------------------------------------------------------- #

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self.rect(), self._image)
        if self.selected:
            self._paint_frame(painter)

    def _paint_frame(self, painter: QPainter) -> None:
        """Word's own marking: a fine line round the object, a handle at grip."""
        painter.setPen(QPen(QColor("#2E75B6"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.setBrush(QColor("#FFFFFF"))
        for rect in self._handle_rects().values():
            painter.drawRect(rect)

    def _handle_rects(self) -> dict:
        """The grip squares, in this widget's own coordinates."""
        box = self.rect()
        half = HANDLE_PX // 2
        xs = {"left": box.left(), "right": box.right(), "middle": box.center().x()}
        ys = {"top": box.top(), "bottom": box.bottom(), "middle": box.center().y()}
        spots = {"top-left": ("left", "top"), "top": ("middle", "top"),
                 "top-right": ("right", "top"), "right": ("right", "middle"),
                 "bottom-right": ("right", "bottom"), "bottom": ("middle", "bottom"),
                 "bottom-left": ("left", "bottom"), "left": ("left", "middle")}
        return {side: QRect(xs[x] - half, ys[y] - half, HANDLE_PX, HANDLE_PX)
                for side, (x, y) in spots.items()}

    def _side_at(self, point: QPoint) -> Optional[str]:
        if not self.selected:
            return None
        for side, rect in self._handle_rects().items():
            if rect.adjusted(-2, -2, 2, 2).contains(point):
                return side
        return None

    # -- dragging and stretching -------------------------------------------- #

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self.page.select_float(self)
        side = self._side_at(event.position().toPoint())
        self._drag = (side or "move", event.globalPosition().toPoint(), self.rect_cm)
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._drag is None:
            # Word tells you which edge a grip will pull before you press it.
            side = self._side_at(event.position().toPoint())
            self.setCursor(QCursor(_HANDLE_CURSORS.get(
                side, Qt.CursorShape.SizeAllCursor)))
            return super().mouseMoveEvent(event)
        wide, tall = self._centimetres(event.globalPosition().toPoint()
                                       - self._drag[1])
        self.set_rect_cm(*_shift(self._drag[2], self._drag[0], wide, tall))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._drag is not None:
            self.page.anchor_float(self)
        self._drag = None
        event.accept()

    def _centimetres(self, delta: QPoint) -> Tuple[float, float]:
        """Pointer movement on screen → the centimetres the ribbon counts in."""
        return (self.page.to_actual(delta.x()) / PX_PER_CM,
                self.page.to_actual(delta.y()) / PX_PER_CM)

    def showEvent(self, event) -> None:  # type: ignore[override]
        self.relayout()
        super().showEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        self.update()
        super().resizeEvent(event)


def _shift(box: Tuple[float, float, float, float], side: str,
           wide: float, tall: float) -> Tuple[float, float, float, float]:
    """The box after one edge, or the whole object, has been carried by the drag.

    A handle keeps the edge opposite it where it was, so pulling the west edge
    moves the left and the width and leaves the right alone.
    """
    x, y, w, h = box
    if side == "move":
        return (x + wide, y + tall, w, h)
    if "left" in side:
        carried = min(wide, w - MIN_SIZE_CM)
        x, w = x + carried, w - carried
    if "right" in side:
        w = w + wide
    if "top" in side:
        carried = min(tall, h - MIN_SIZE_CM)
        y, h = y + carried, h - carried
    if "bottom" in side:
        h = h + tall
    return (x, y, w, h)
