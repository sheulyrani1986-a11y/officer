"""Tests for PresentR's shapes and pictures: their size, place, colour and gallery."""

import pytest
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient
from PySide6.QtWidgets import QTabBar

from officer.presentr.canvas import (
    PX_PER_CM, SHAPE_KEYS, dragged_box, shape_box, shape_path
)
from officer.presentr.io.pptx_handler import PptxHandler
from officer.presentr.slide_deck import ImageObject, ShapeObject
from officer.presentr.window import PresentRWindow


@pytest.fixture
def deck(q_app):
    """A PresentR window with one shape in the middle of the slide, selected."""
    win = PresentRWindow()
    win.resize(1400, 900)
    win.show()
    q_app.processEvents()
    win.insert_shape("rect")
    q_app.processEvents()
    return win


def _shape(win) -> ShapeObject:
    return next(obj for obj in win.scene.current_slide.objects
                if isinstance(obj, ShapeObject))


def _select(win, obj):
    win.scene.clearSelection()
    for item in win.scene.items():
        if item.data(0) is obj:
            item.setSelected(True)


# -- the gallery ------------------------------------------------------------- #

def test_the_shapes_gallery_offers_twenty_shapes():
    assert len(PresentRWindow._SHAPE_GALLERY) >= 20
    assert [kind for kind, _ in PresentRWindow._SHAPE_GALLERY if kind not in SHAPE_KEYS] == []


def test_every_gallery_shape_is_a_button_that_names_the_shape(deck):
    assert len(deck._shape_buttons) == len(PresentRWindow._SHAPE_GALLERY)
    for kind, caption in PresentRWindow._SHAPE_GALLERY:
        button = deck._shape_buttons[kind]
        assert button.accessibleName() == caption
        assert not button.icon().isNull(), f"{caption} has no picture of its own"


@pytest.mark.parametrize("kind", [kind for kind in SHAPE_KEYS
                                 if kind not in ("rect", "ellipse")])
def test_a_gallery_shape_fills_the_box_it_is_given(kind):
    box = QRectF(0, 0, 120, 90)
    outline = shape_path(kind, box)
    assert outline is not None
    bounds = outline.boundingRect()
    assert bounds.width() == pytest.approx(120, abs=2)
    assert bounds.height() == pytest.approx(90, abs=2)


def test_a_shape_lands_in_the_middle_of_the_slide_at_its_own_size(deck):
    shp = _shape(deck)
    assert (shp.width, shp.height) == shape_box("rect")
    assert shp.x == pytest.approx((deck.scene.slide_width - shp.width) / 2)
    assert shp.y == pytest.approx((deck.scene.slide_height - shp.height) / 2)


def test_a_line_gets_a_line_s_box_rather_than_a_square():
    wide, tall = shape_box("line")
    assert wide / tall > 10


# -- the contextual tab ------------------------------------------------------ #

def _tabs(win):
    bar = win.ribbon.findChild(QTabBar)
    return {bar.tabText(i): bar.isTabVisible(i) for i in range(bar.count())}


def test_the_format_tab_only_appears_over_an_object(deck):
    assert _tabs(deck)["Shape Format"] is True
    assert deck.ribbon.current_tab_name == "Shape Format"
    deck.scene.clearSelection()
    assert _tabs(deck)["Shape Format"] is False


def test_the_tab_shows_the_shape_s_own_measurements(deck):
    shp = _shape(deck)
    assert deck.shape_width_spin.value() == pytest.approx(shp.width / PX_PER_CM, abs=0.02)
    assert deck.shape_height_spin.value() == pytest.approx(shp.height / PX_PER_CM, abs=0.02)
    assert deck.shape_pos_x_spin.value() == pytest.approx(shp.x / PX_PER_CM, abs=0.02)


def test_typing_a_new_size_resizes_the_shape_on_the_slide(deck, q_app):
    shp = _shape(deck)
    before = (shp.width, shp.height)
    deck.shape_width_spin.setValue(before[0] / PX_PER_CM * 1.5)
    q_app.processEvents()
    shp = _shape(deck)
    assert shp.width == pytest.approx(before[0] * 1.5, abs=1)
    # PowerPoint's Width box changes the width; the other edge is left alone.
    assert shp.height == pytest.approx(before[1], abs=0.01)


def test_typing_a_position_moves_the_shape_and_keeps_its_size(deck, q_app):
    shp = _shape(deck)
    wide, tall = shp.width, shp.height
    deck.shape_pos_x_spin.setValue(2.0)
    deck.shape_pos_y_spin.setValue(1.0)
    q_app.processEvents()
    shp = _shape(deck)
    assert (shp.x, shp.y) == pytest.approx((2 * PX_PER_CM, 1 * PX_PER_CM), abs=1)
    assert (shp.width, shp.height) == pytest.approx((wide, tall), abs=0.01)


def test_the_ribbon_never_asks_for_a_shape_off_the_slide(deck):
    deck.shape_pos_x_spin.setValue(90.0)
    shp = _shape(deck)
    assert shp.x >= 0
    assert shp.width > 0


def test_rotating_the_shape_turns_the_item_it_is_drawn_by(deck, q_app):
    deck.shape_rotate_spin.setValue(30.0)
    q_app.processEvents()
    assert _shape(deck).rotation == pytest.approx(30.0)
    item = next(i for i in deck.scene.items() if i.data(0) is _shape(deck))
    assert item.rotation() == pytest.approx(30.0)


def test_reset_size_returns_a_shape_to_the_box_it_was_inserted_with(deck):
    deck.shape_width_spin.setValue(1.0)
    deck._reset_shape_size()
    shp = _shape(deck)
    assert (shp.width, shp.height) == shape_box(shp.shape_type)


# -- colour ------------------------------------------------------------------ #

def test_a_gradient_fills_the_shape_with_both_of_its_colours(deck):
    deck._apply_shape_gradient("#3B82F6", "#DBEAFE")
    shp = _shape(deck)
    assert shp.gradient_color == "#DBEAFE"
    item = next(i for i in deck.scene.items() if i.data(0) is shp)
    brush = item.brush()
    gradient = brush.gradient()
    assert isinstance(gradient, QLinearGradient)
    assert [colour.name().upper() for _pos, colour in gradient.stops()] == [
        "#3B82F6", "#DBEAFE"]


def test_no_gradient_puts_the_shape_back_to_one_flat_colour(deck):
    deck._apply_shape_gradient("#3B82F6", "#DBEAFE")
    deck._apply_shape_gradient(None, None)
    shp = _shape(deck)
    assert shp.gradient_color is None
    item = next(i for i in deck.scene.items() if i.data(0) is shp)
    assert item.brush().style() == Qt.BrushStyle.SolidPattern


def test_the_outline_commands_recolour_the_border_and_its_weight(deck):
    deck.scene.set_selection_paint(border="#10B981", border_width=6)
    shp = _shape(deck)
    assert (shp.border_color, shp.border_width) == ("#10B981", 6)
    item = next(i for i in deck.scene.items() if i.data(0) is shp)
    assert item.pen().color().name().upper() == "#10B981"
    assert item.pen().widthF() == pytest.approx(6.0)


def test_the_style_group_stays_home_when_a_picture_is_selected(deck, tmp_path, q_app):
    from PySide6.QtGui import QImage
    path = str(tmp_path / "shot.png")
    image = QImage(400, 240, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.darkCyan)
    assert image.save(path)
    _select(deck, _shape(deck))
    deck.scene.clearSelection()
    picture = ImageObject(id="pic", x=40, y=40, width=200, height=120, image_path=path)
    item = deck.scene._add_image_item(picture)
    deck.scene.clearSelection()
    item.setSelected(True)
    q_app.processEvents()
    assert _tabs(deck)["Shape Format"] is True
    assert deck._format_style_group.isVisible() is False
    deck.shape_height_spin.setValue(2.0)
    q_app.processEvents()
    assert picture.height == pytest.approx(2 * PX_PER_CM, abs=1)
    # A picture is scaled from its own pixels, so shrinking and growing is lossless.
    deck.shape_height_spin.setValue(6.0)
    assert picture.height == pytest.approx(6 * PX_PER_CM, abs=1)


# -- resizing on the canvas --------------------------------------------------- #

def test_a_selected_object_gets_powerpoint_s_eight_handles(deck):
    box = deck.scene.selection_rect()
    points = deck.canvas_view._handle_points()
    assert len(points) == 8
    # The handles span the selected box, corners included.
    assert min(point.x() for point in points) == pytest.approx(
        deck.canvas_view.mapFromScene(box.topLeft()).x())
    assert max(point.y() for point in points) == pytest.approx(
        deck.canvas_view.mapFromScene(box.bottomRight()).y())
    assert deck.canvas_view._handle_under(points[4]) == 4
    assert deck.canvas_view._handle_under(QPointF(-400, -400)) == -1


def test_dragging_a_handle_keeps_the_corner_it_is_pulled_from(deck):
    box = QRectF(100, 80, 120, 90)
    grown = dragged_box(box, 4, QPointF(260, 190))
    assert grown == QRectF(100, 80, 160, 110)
    # The top-left handle pulls the opposite way; the bottom-right stays put.
    assert dragged_box(box, 0, QPointF(60, 40)) == QRectF(60, 40, 160, 130)
    # An edge handle moves one side only, so the other keeps its measurement.
    assert dragged_box(box, 1, QPointF(140, 60)) == QRectF(100, 60, 120, 110)


def test_grabbing_a_handle_grows_the_shape_on_the_slide(deck):
    shp = _shape(deck)
    original = QRectF(shp.x, shp.y, shp.width, shp.height)
    here = QPointF(original.right() + 40, original.bottom() + 20)
    box = dragged_box(original, 4, here)
    assert deck.scene.set_selection_box(x=box.x(), y=box.y(),
                                        width=box.width(), height=box.height())
    deck.scene.sync_to_slide()
    shp = _shape(deck)
    assert (shp.width, shp.height) == pytest.approx(
        (original.width() + 40, original.height() + 20))
    assert (shp.x, shp.y) == pytest.approx((original.x(), original.y()))


def test_growing_and_shrinking_a_shape_returns_it_to_its_box(deck):
    shp = _shape(deck)
    before = (shp.x, shp.y, shp.width, shp.height)
    deck.scene.scale_selection(1.25)
    deck.scene.scale_selection(1 / 1.25)
    shp = _shape(deck)
    assert (shp.x, shp.y, shp.width, shp.height) == pytest.approx(before, abs=0.5)


def test_nothing_selected_means_nothing_to_resize(deck):
    deck.scene.clearSelection()
    assert deck.scene.selection_info() is None
    assert deck.scene.set_selection_box(width=100) is False


# -- saving ------------------------------------------------------------------- #

def test_a_gradient_shape_survives_saving_and_reopening(tmp_path):
    prs = PresentRWindow().presentation
    prs.slides[0].objects.clear()
    prs.slides[0].objects.append(ShapeObject(id="s", x=100, y=80, width=200, height=140,
                                             shape_type="hexagon",
                                             fill_color="#F59E0B",
                                             gradient_color="#EF4444"))
    path = str(tmp_path / "gradient.pptx")
    assert PptxHandler.save(path, prs) is True
    back = PptxHandler.load(path)
    shapes = [obj for slide in back.slides for obj in slide.objects
              if isinstance(obj, ShapeObject)]
    assert len(shapes) == 1
    assert shapes[0].shape_type == "hexagon"
    assert shapes[0].fill_color == "#F59E0B"
    assert shapes[0].gradient_color == "#EF4444"
