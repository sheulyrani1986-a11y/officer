"""PowerPoint's slide thumbnail strip: a number gutter beside a rendered slide."""

from typing import Callable, List, Optional, Sequence

from PySide6.QtCore import QPointF, Qt, QRect, QRectF, QSize
from PySide6.QtGui import (
    QBrush, QColor, QFontMetrics, QIcon, QLinearGradient, QPainter, QPen, QPolygonF,
    QPixmap
)
from PySide6.QtWidgets import QListView, QListWidget, QListWidgetItem, QStyle, QStyledItemDelegate

from officer.core.themes.theme_manager import ThemeManager
from officer.presentr.canvas import render_slide_to_pixmap, shape_path
from officer.presentr.slide_deck import LAYOUT_PLACEHOLDERS, Slide

# PowerPoint's gutter: the slide number sits in its own column, right-aligned.
GUTTER_WIDTH = 30
THUMB_WIDTH = 168
ITEM_HEIGHT = 106


class ThumbnailDelegate(QStyledItemDelegate):
    """Draws Office's slide card: a hairline frame around the rendered slide,
    an accent border when selected, and optionally the slide number in a gutter.
    """

    def __init__(self, app_name: str, gutter: bool = True, parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.gutter = gutter

    def paint(self, painter: QPainter, option, index) -> None:  # type: ignore[override]
        colors = ThemeManager.instance().colors(self.app_name)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        rect = option.rect

        # --- number gutter ------------------------------------------------- #
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if self.gutter:
            painter.setPen(QColor(colors.text if selected else colors.text_secondary))
            painter.drawText(QRect(rect.left() + 2, rect.top(),
                                   GUTTER_WIDTH - 10, rect.height()),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             str(index.row() + 1))

        pixmap = index.data(Qt.ItemDataRole.DecorationRole)
        if isinstance(pixmap, QPixmap) and not pixmap.isNull():
            card = self._card_rect(rect, pixmap)
            painter.drawPixmap(card, pixmap)
            painter.setPen(QColor(colors.accent if selected else colors.border_strong))
            painter.drawRect(card.adjusted(0, 0, -1, -1))
            if selected:
                # Office leaves a pixel of white between the card and its focus ring.
                painter.setPen(QColor(colors.accent))
                painter.drawRect(card.adjusted(-1, -1, 0, 0))
            if not self.gutter:
                # The sorter captions each card with its number underneath.
                painter.setPen(QColor(colors.text if selected else colors.text_secondary))
                painter.drawText(QRect(card.left(), card.bottom() + 2,
                                       card.width(), 16),
                                 Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                                 str(index.row() + 1))
        painter.restore()

    def _card_rect(self, rect: QRect, pixmap: QPixmap) -> QRect:
        """The largest card of the pixmap's aspect that fits the row, centred."""
        gutter = GUTTER_WIDTH if self.gutter else 8
        # The sorter keeps a strip below the card for its number caption.
        bottom = 14 if self.gutter else 34
        available = rect.width() - gutter - 12
        height = rect.height() - 8 - bottom
        width = min(available, int(height * pixmap.width() / max(1, pixmap.height())))
        height = int(width * pixmap.height() / max(1, pixmap.width()))
        x = rect.left() + gutter + (available - width) // 2
        y = rect.top() + 8 + ((rect.height() - 8 - bottom) - height) // 2
        return QRect(x, y, width, height)


class ThumbnailPane(QListWidget):
    """The vertical strip of slide previews down PowerPoint's left edge."""

    def __init__(self, app_name: str = "presentr",
                 slide_size: Sequence[int] = (960, 540), parent=None):
        super().__init__(parent)
        self.app_name = app_name
        self.slide_size = tuple(slide_size)
        self.setObjectName("ThumbnailPane")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setViewMode(QListView.ViewMode.ListMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setMovement(QListView.Movement.Static)
        self.setSpacing(4)
        self.setItemDelegate(ThumbnailDelegate(app_name, gutter=True, parent=self))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMinimumWidth(210)

    # -- content ------------------------------------------------------------ #

    def refresh(self, slides: List[Slide], current_row: int = -1) -> None:
        """Re-render every thumbnail; *current_row* stays selected without a signal."""
        self.blockSignals(True)
        self.clear()
        for slide in slides:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.DecorationRole, self.render(slide))
            item.setSizeHint(self.item_size())
            self.addItem(item)
        if 0 <= current_row < self.count():
            self.setCurrentRow(current_row)
        self.blockSignals(False)

    def render(self, slide: Slide) -> QPixmap:
        return render_slide_to_pixmap(slide, THUMB_WIDTH, self.slide_size)

    def update_thumbnail(self, row: int, slide: Slide) -> None:
        """Re-render just one card, so editing a slide does not repaint the deck."""
        if 0 <= row < self.count():
            self.item(row).setData(Qt.ItemDataRole.DecorationRole, self.render(slide))
            self.viewport().update()

    def item_size(self) -> QSize:
        return QSize(max(self.viewport().width(), self.minimumWidth()), ITEM_HEIGHT)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        size = self.item_size()
        for row in range(self.count()):
            self.item(row).setSizeHint(size)


class SlideSorterView(QListWidget):
    """PowerPoint's Slide Sorter: the same cards, tiled, for reordering the deck."""

    CARD_WIDTH = 232

    def __init__(self, app_name: str = "presentr",
                 slide_size: Sequence[int] = (960, 540), parent=None,
                 on_reorder: Optional[Callable[[int, int], None]] = None):
        super().__init__(parent)
        self.app_name = app_name
        self.slide_size = tuple(slide_size)
        # The deck owns the order, so a drop is reported rather than replayed on
        # the widget's own items; the window then rebuilds this view from the model.
        self._on_reorder = on_reorder
        self._drag_row = -1
        self.setObjectName("SlideSorter")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setWrapping(True)
        self.setSpacing(18)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setItemDelegate(ThumbnailDelegate(app_name, gutter=False, parent=self))
        self.setIconSize(QSize(self.CARD_WIDTH,
                               int(self.CARD_WIDTH * slide_size[1] / slide_size[0])))
        self.setGridSize(QSize(self.CARD_WIDTH + 40,
                               int(self.CARD_WIDTH * slide_size[1] / slide_size[0]) + 44))

    def startDrag(self, supportedActions) -> None:  # type: ignore[override]
        self._drag_row = self.currentRow()
        super().startDrag(supportedActions)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        target = self._row_at(event.position())
        source, self._drag_row = self._drag_row, -1
        if (self._on_reorder is not None and event.dropAction() == Qt.DropAction.MoveAction
                and source >= 0 and target >= 0 and source != target):
            self._on_reorder(source, target)
        event.accept()

    def _row_at(self, position: QPointF) -> int:
        item = self.itemAt(position.toPoint())
        if item is None:
            # Dropping past the last card means "move to the end".
            return self.count() - 1
        return self.row(item)

    def refresh(self, slides: List[Slide], current_row: int = -1) -> None:
        self.blockSignals(True)
        self.clear()
        for slide in slides:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.DecorationRole,
                         render_slide_to_pixmap(slide, self.CARD_WIDTH, self.slide_size))
            item.setToolTip(slide.title)
            self.addItem(item)
        if 0 <= current_row < self.count():
            self.setCurrentRow(current_row)
        self.blockSignals(False)


# -- ribbon gallery previews --------------------------------------------------- #

def theme_swatch_icon(background: str, text: str, accent: str,
                      size: Sequence[int] = (48, 30)) -> QIcon:
    """PowerPoint's Themes gallery: a slide in that theme, not a generic glyph."""
    w, h = size
    pixmap = QPixmap(w, h)
    pixmap.fill(QColor(background))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    margin = max(2, w // 12)
    painter.fillRect(QRectF(margin, margin, w * 0.34, h * 0.16), QColor(accent))
    painter.setPen(QPen(QColor(text)))
    for line, width in enumerate((0.72, 0.56)):
        painter.fillRect(QRectF(margin, h * (0.42 + line * 0.18),
                                w * width, max(1.0, h * 0.10)), QColor(text))
    painter.end()
    return QIcon(pixmap)


def layout_preview_icon(layout: str, size: Sequence[int] = (48, 30)) -> QIcon:
    """PowerPoint's Layout gallery: the placeholders a layout would create."""
    w, h = size
    pixmap = QPixmap(w, h)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    colors = ThemeManager.instance().colors("presentr")
    painter.setPen(QPen(QColor(colors.border_strong)))
    painter.setBrush(QColor(colors.surface))
    painter.drawRect(0, 0, w - 1, h - 1)
    slide_w, slide_h = 960.0, 540.0
    painter.setBrush(QColor(colors.accent))
    painter.setPen(Qt.PenStyle.NoPen)
    for role, x, y, box_w, box_h, *_ in LAYOUT_PLACEHOLDERS.get(layout, ()):
        painter.drawRect(QRectF(x / slide_w * (w - 4) + 2, y / slide_h * (h - 4) + 2,
                                box_w / slide_w * (w - 4), box_h / slide_h * (h - 4)))
    painter.end()
    return QIcon(pixmap)


def shape_gallery_icon(kind: str, size: Sequence[int] = (24, 24)) -> QIcon:
    """PowerPoint's Shapes gallery: the shape itself, drawn the way it lands.

    Twenty-odd buttons sharing one generic glyph would say nothing about which
    shape each one inserts, so each card is cut from the same outline the slide
    paints.
    """
    w, h = size
    pixmap = QPixmap(w, h)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    colors = ThemeManager.instance().colors("presentr")
    ink = QColor(colors.accent)
    box = QRectF(1.5, 1.5, w - 3, h - 3)
    outline = shape_path(kind, box)
    if kind == "line":
        painter.setPen(QPen(ink, max(1.6, w * 0.09)))
        painter.drawLine(box.bottomLeft(), box.topRight())
    elif outline is None:
        painter.setPen(QPen(ink, 1.2))
        painter.setBrush(QColor(ink.red(), ink.green(), ink.blue(), 70))
        if kind == "ellipse":
            painter.drawEllipse(box)
        else:
            painter.drawRect(box)
    else:
        painter.setPen(QPen(QColor(colors.border_strong), 1))
        painter.setBrush(ink)
        painter.drawPath(outline)
    painter.end()
    return QIcon(pixmap)


def shape_style_icon(style: Sequence, size: Sequence[int] = (44, 30)) -> QIcon:
    """PowerPoint's Shape Styles gallery: a shape wearing exactly that style.

    A preset you cannot see is a preset you have to guess at, so the card is
    painted with the same fill, gradient, outline and weight the command writes.
    """
    _name, fill, gradient, border, weight = style
    w, h = size
    pixmap = QPixmap(w, h)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    inset = weight / 2 + 1
    box = QRectF(inset, inset, w - 2 * inset, h - 2 * inset)
    if gradient:
        ramp = QLinearGradient(box.topLeft(), box.bottomRight())
        ramp.setColorAt(0.0, QColor(fill))
        ramp.setColorAt(1.0, QColor(gradient))
        painter.setBrush(QBrush(ramp))
    else:
        painter.setBrush(QColor(fill))
    painter.setPen(QPen(QColor(border), weight))
    corner = min(w, h) * 0.18
    painter.drawRoundedRect(box, corner, corner)
    painter.end()
    return QIcon(pixmap)


def animation_gallery_icon(name: str, size: Sequence[int] = (44, 30)) -> QIcon:
    """PowerPoint's Animation gallery: the object caught on its way in.

    None sits still, Fade arrives half-drawn, Fly In trails from the left and
    Zoom grows out of its own smaller outline.
    """
    w, h = size
    pixmap = QPixmap(w, h)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    colors = ThemeManager.instance().colors("presentr")
    ink = QColor(colors.accent)
    tall = h * 0.52
    box = QRectF(w - 6 - tall * 1.3, (h - tall) / 2, tall * 1.3, tall)
    if name == "none":
        pen = QPen(QColor(colors.border_strong), 1.4, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box, 3, 3)
    elif name == "fade":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ink.red(), ink.green(), ink.blue(), 105))
        painter.drawRoundedRect(box, 3, 3)
    elif name == "fly_in":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawRoundedRect(box, 3, 3)
        trail = QPolygonF([QPointF(w * 0.16, h * 0.22), QPointF(w * 0.30, h * 0.5),
                           QPointF(w * 0.16, h * 0.78)])
        for step in range(3):
            shift = QPointF(-w * 0.09 * step, 0)
            painter.setBrush(QColor(ink.red(), ink.green(), ink.blue(),
                                    200 - 60 * step))
            painter.drawPolygon(trail.translated(shift))
    else:  # zoom
        painter.setPen(QPen(ink, 1.4, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box.adjusted(-5, -4, 5, 4), 4, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ink)
        painter.drawRoundedRect(box, 3, 3)
    painter.end()
    return QIcon(pixmap)


def transition_gallery_icon(name: str, size: Sequence[int] = (44, 30)) -> QIcon:
    """PowerPoint's Transitions gallery: a slide caught in the act of changing.

    A plain card is "None", a card dissolving into its own colour is a fade, and
    a card with the next one pushing across it is a push.
    """
    w, h = size
    pixmap = QPixmap(w, h)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    colors = ThemeManager.instance().colors("presentr")
    ink = QColor(colors.accent)
    card = QRectF(2, 2, w - 4, h - 4)
    painter.setPen(QPen(QColor(colors.border_strong), 1))
    painter.setBrush(QColor(colors.surface))
    painter.drawRect(card)
    if name == "fade":
        ramp = QLinearGradient(card.left(), 0, card.right(), 0)
        ramp.setColorAt(0.0, QColor(ink.red(), ink.green(), ink.blue(), 0))
        ramp.setColorAt(1.0, QColor(ink.red(), ink.green(), ink.blue(), 210))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(ramp))
        painter.drawRect(card)
    elif name == "push":
        # The incoming page covers the right of the slide, seam and all.
        arriving = QRectF(card.center().x() + 2, card.top(),
                          card.right() - card.center().x() - 2, card.height())
        painter.setPen(QPen(QColor(colors.border_strong), 1))
        painter.setBrush(ink)
        painter.drawRect(arriving)
    painter.end()
    return QIcon(pixmap)

