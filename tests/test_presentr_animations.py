"""Tests for PresentR's animations and transitions, and the ribbon that sets them."""

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor, QKeyEvent, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGraphicsPixmapItem, QTabBar

from officer.presentr.io.pptx_handler import PptxHandler
from officer.presentr.presenter_mode import ANIMATION_MS, TRANSITION_MS, PresenterWindow
from officer.presentr.slide_deck import ImageObject, Presentation, ShapeObject, TextObject
from officer.presentr.thumbnails import (
    animation_gallery_icon, shape_style_icon, transition_gallery_icon
)
from officer.presentr.window import PresentRWindow


@pytest.fixture
def editor(q_app):
    """A PresentR window that is shown, so its ribbon has laid itself out."""
    win = PresentRWindow()
    win.resize(1400, 900)
    win.show()
    q_app.processEvents()
    return win


def _deck_with_build() -> Presentation:
    """A two-slide deck whose first slide arrives in three steps."""
    prs = Presentation("Deck")
    slide = prs.slides[0]
    slide.layout = "blank"
    slide.objects = [
        TextObject(id="a", x=60, y=40, width=300, height=60, text="First",
                   animation="fade"),
        ShapeObject(id="b", x=300, y=200, width=100, height=80, animation="fly_in"),
        ShapeObject(id="c", x=500, y=200, width=100, height=80, animation="zoom"),
        # One object with no effect at all: the audience should see it from the
        # first frame, however long the rest of the build takes.
        ShapeObject(id="flat", x=640, y=40, width=60, height=60),
    ]
    prs.add_slide()
    return prs


def _show(q_app, presentation: Presentation, **kwargs) -> PresenterWindow:
    pres = PresenterWindow(presentation, **kwargs)
    pres.show()
    q_app.processEvents()
    return pres


def _press(pres: PresenterWindow, key) -> None:
    """Hand the show a key press, as the presenter's keyboard would."""
    pres.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key,
                                 Qt.KeyboardModifier.NoModifier))


def _lit(pres: PresenterWindow) -> dict:
    """What each object on the current slide looks like to the audience."""
    return {obj.id: (round(item.opacity(), 3), round(item.scale(), 3),
                     round(item.pos().x()))
            for item, obj in list(pres._pending) + list(pres._revealed)}


# -- what the model carries --------------------------------------------------- #

def test_a_fresh_deck_arrives_without_any_effects():
    slide = Presentation("Deck").slides[0]
    assert slide.transition == "none"
    assert [obj.animation for obj in slide.objects] == ["none", "none"]


# -- the build ---------------------------------------------------------------- #

def test_the_show_holds_every_animated_object_back(q_app):
    pres = _show(q_app, _deck_with_build())
    try:
        assert [obj.id for _, obj in pres._pending] == ["a", "b", "c"]
        assert [item.opacity() for item, _ in pres._pending] == [0.0, 0.0, 0.0]
        drawn = {item.data(0).id: item.opacity() for item in pres.scene.items()
                 if item.data(0) is not None}
        assert drawn["flat"] == 1.0
    finally:
        pres.close()


def test_each_click_brings_in_the_next_object(q_app):
    pres = _show(q_app, _deck_with_build())
    try:
        assert pres.reveal_next() is True
        assert [obj.id for _, obj in pres._pending] == ["b", "c"]
        assert [obj.id for _, obj in pres._revealed] == ["a"]
        assert pres.reveal_next() is True
        assert pres.reveal_next() is True
        assert pres.reveal_next() is False
    finally:
        pres.close()


def test_an_effect_leaves_the_object_where_the_model_says(q_app):
    prs = _deck_with_build()
    pres = _show(q_app, prs)
    try:
        for _ in range(3):
            pres.reveal_next()
        q_app.processEvents()
        QTest.qWait(ANIMATION_MS + 150)
        for item, obj in pres._revealed:
            assert item.opacity() == pytest.approx(1.0)
            assert item.scale() == pytest.approx(1.0)
            assert (round(item.pos().x()), round(item.pos().y())) == (obj.x, obj.y)
    finally:
        pres.close()


def test_a_fly_in_travels_rather_than_blinks(q_app):
    prs = _deck_with_build()
    pres = _show(q_app, prs)
    try:
        item, obj = pres._pending[1]
        assert item.pos().x() < 0, "it waits off the slide, to the left"
        assert item.opacity() == 0.0, "and the audience does not see it yet"
        pres.reveal_next()
        pres.reveal_next()
        q_app.processEvents()
        assert item.opacity() == 1.0, "a fly-in travels where it will land"
        assert item.pos().x() < obj.x, "and it is still travelling"
        QTest.qWait(ANIMATION_MS + 150)
        assert round(item.pos().x()) == obj.x
    finally:
        pres.close()


def test_the_page_only_turns_once_the_build_is_finished(q_app):
    pres = _show(q_app, _deck_with_build())
    try:
        for _ in range(3):
            assert pres.step_forward() is True
            assert pres.current_index == 0
        assert pres.step_forward() is True
        assert pres.current_index == 1
    finally:
        pres.close()


def test_the_arrow_keys_drive_the_show(q_app):
    pres = _show(q_app, _deck_with_build())
    try:
        _press(pres, Qt.Key.Key_Right)
        assert len(pres._revealed) == 1
        _press(pres, Qt.Key.Key_Space)
        assert len(pres._revealed) == 2
        _press(pres, Qt.Key.Key_PageUp)
        assert len(pres._revealed) == 1
    finally:
        pres.close()


def test_returning_to_a_slide_shows_it_already_finished(q_app):
    pres = _show(q_app, _deck_with_build())
    try:
        for _ in range(4):
            pres.step_forward()
        assert pres.current_index == 1
        assert pres.step_back() is True
        assert pres.current_index == 0
        assert [obj.id for _, obj in pres._revealed] == ["a", "b", "c"]
        assert pres._pending == []
        assert all(item.opacity() == 1.0 for item, _ in pres._revealed)
    finally:
        pres.close()


def test_a_building_object_cannot_be_left_half_drawn(q_app):
    pres = _show(q_app, _deck_with_build())
    try:
        pres.reveal_next()
        assert pres._effects, "the effect should still be running"
        assert pres.hide_last() is True
        q_app.processEvents()
        # The animation was cut short and the object put back where its build
        # started, rather than left at whatever point the break happened to hit.
        assert _lit(pres)["a"][0] == 0.0
    finally:
        pres.close()


def test_the_show_ends_after_the_last_slide(q_app):
    pres = _show(q_app, _deck_with_build())
    try:
        for _ in range(4):
            pres.step_forward()
        assert pres.current_index == 1
        assert pres.step_forward() is False
        assert not pres.isVisible()
    finally:
        pres.close()


# -- transitions -------------------------------------------------------------- #

def test_a_fade_transition_covers_the_view_and_then_lets_go(q_app):
    prs = _deck_with_build()
    prs.slides[1].transition = "fade"
    pres = _show(q_app, prs, start_index=1)
    try:
        assert pres.view.graphicsEffect() is not None
        QTest.qWait(TRANSITION_MS + 150)
        assert pres.view.graphicsEffect() is None
    finally:
        pres.close()


def test_a_push_transition_ends_where_a_plain_slide_sits(q_app):
    prs = _deck_with_build()
    prs.slides[1].transition = "push"
    pres = _show(q_app, prs, start_index=1)
    try:
        QTest.qWait(40)
        assert pres.view.transform().dx() > 1, "the page arrives from the right"
        QTest.qWait(TRANSITION_MS + 150)
        settled = pres.view.transform()
        pres._show_current_slide(transition=False)
        plain = pres.view.transform()
        for name in ("m11", "m12", "m13", "m21", "m22", "m23", "m31", "m32", "m33"):
            assert getattr(settled, name)() == pytest.approx(
                getattr(plain, name)(), abs=1.0)
    finally:
        pres.close()


def test_a_slide_with_no_transition_shows_nothing_extra(q_app):
    pres = _show(q_app, _deck_with_build())
    try:
        assert pres.view.graphicsEffect() is None
        assert pres.view.transform().dx() == pytest.approx(
            pres.scene.sceneRect().x(), abs=1.0)
    finally:
        pres.close()


# -- the ribbon's galleries --------------------------------------------------- #

def _tabs(win):
    bar = win.ribbon.findChild(QTabBar)
    return [bar.tabText(i) for i in range(bar.count()) if bar.isTabVisible(i)]


def test_the_ribbon_gains_powerpoint_s_two_new_tabs_in_order(editor):
    names = _tabs(editor)
    assert names.index("Transitions") < names.index("Animations")
    assert names.index("Animations") < names.index("Slide Show")
    # Shape Format is contextual: with nothing picked up it stays out of the way.
    assert "Shape Format" not in names


def test_every_effect_and_transition_has_a_gallery_button_of_its_own(editor):
    assert set(editor._animation_buttons) == {key for key, _ in PresentRWindow._EFFECTS}
    assert set(editor._transition_buttons) == {key for key, _ in PresentRWindow._TRANSITIONS}
    for button in list(editor._animation_buttons.values()) + list(
            editor._transition_buttons.values()):
        assert button.isCheckable()
        assert not button.icon().isNull(), "a gallery entry has to show its effect"


def test_picking_an_effect_writes_the_model_and_lights_the_button(editor, q_app):
    editor.insert_shape("rect")
    q_app.processEvents()
    editor.ribbon.select_tab("Animations")
    editor._animation_buttons["fly_in"].click()
    q_app.processEvents()
    assert editor.scene.selection_info()["animation"] == "fly_in"
    assert editor._animation_buttons["fly_in"].isChecked()
    assert sum(b.isChecked() for b in editor._animation_buttons.values()) == 1


def test_the_gallery_lights_for_whatever_is_picked_up(editor, q_app):
    slide = editor.scene.current_slide
    slide.objects.append(ShapeObject(id="lit", x=40, y=40, width=60, height=60,
                                     animation="zoom"))
    editor.scene.load_slide(slide)
    for item in editor.scene.items():
        if item.data(0) is not None and item.data(0).id == "lit":
            item.setSelected(True)
    q_app.processEvents()
    assert editor._animation_buttons["zoom"].isChecked()
    assert not editor._animation_buttons["fade"].isChecked()


def test_no_effect_is_lit_over_an_empty_selection(editor, q_app):
    editor.scene.clearSelection()
    q_app.processEvents()
    assert not any(b.isChecked() for b in editor._animation_buttons.values())


def test_a_transition_belongs_to_the_slide_being_edited(editor, q_app):
    editor._transition_buttons["fade"].click()
    q_app.processEvents()
    assert editor.presentation.slides[0].transition == "fade"
    editor.add_new_slide()
    q_app.processEvents()
    assert editor.presentation.slides[1].transition == "none"
    assert editor._transition_buttons["none"].isChecked()


def test_apply_to_all_gives_the_deck_one_transition(editor, q_app):
    editor.add_new_slide()
    editor.add_new_slide()
    editor._set_slide_transition("push")
    editor._apply_transition_to_all()
    q_app.processEvents()
    assert {slide.transition for slide in editor.presentation.slides} == {"push"}


def test_a_play_from_here_command_starts_the_show_on_this_slide(editor, q_app):
    editor.add_new_slide()
    q_app.processEvents()
    editor._play_from_here.click()
    q_app.processEvents()
    assert editor.presenter.current_index == 1
    assert editor.presenter.isActiveWindow() or editor.presenter.isVisible()
    editor.presenter.close()


# -- shape styles ------------------------------------------------------------- #

def test_the_style_gallery_paints_a_shape_in_one_click(editor, q_app):
    editor.insert_shape("hexagon")
    q_app.processEvents()
    preset, button = list(editor._style_buttons.items())[-1]
    button.click()
    q_app.processEvents()
    _name, fill, gradient, border, weight = preset
    info = editor.scene.selection_info()
    assert info["fill_color"] == fill
    assert info["gradient_color"] == gradient
    assert (info["border_color"], info["border_width"]) == (border, weight)
    assert sum(b.isChecked() for b in editor._style_buttons.values()) == 1


def test_a_shape_reveals_which_style_it_already_wears(editor, q_app):
    preset = PresentRWindow._SHAPE_STYLES[3]
    slide = editor.scene.current_slide
    _name, fill, gradient, border, weight = preset
    slide.objects.append(ShapeObject(id="worn", x=30, y=30, width=70, height=50,
                                     fill_color=fill, gradient_color=gradient,
                                     border_color=border, border_width=weight))
    editor.scene.load_slide(slide)
    for item in editor.scene.items():
        if item.data(0) is not None and item.data(0).id == "worn":
            item.setSelected(True)
    q_app.processEvents()
    assert editor._style_buttons[preset].isChecked()


def test_the_paint_galleries_stay_off_a_picture(editor, q_app, tmp_path):
    photo = tmp_path / "photo.png"
    pixmap = QPixmap(80, 60)
    pixmap.fill(QColor("#16A34A"))
    pixmap.save(str(photo))
    slide = editor.scene.current_slide
    slide.objects.append(ImageObject(id="pic", x=20, y=20, width=80, height=60,
                                     image_path=str(photo)))
    editor.scene.load_slide(slide)
    for item in editor.scene.items():
        if isinstance(item, QGraphicsPixmapItem):
            item.setSelected(True)
    q_app.processEvents()
    assert editor._format_style_group.isHidden()
    assert editor._format_styles_group.isHidden()
    # The numbers still describe the picture, because sizing one matters too.
    assert "Shape Format" in _tabs(editor)
    assert editor.scene.selection_info()["kind"] == "picture"


def test_a_gallery_card_is_painted_in_the_thing_it_applies(editor):
    for preset in PresentRWindow._SHAPE_STYLES:
        assert not shape_style_icon(preset).isNull()
    for key, _ in PresentRWindow._EFFECTS:
        assert not animation_gallery_icon(key).isNull()
    for key, _ in PresentRWindow._TRANSITIONS:
        assert not transition_gallery_icon(key).isNull()


# -- exports ------------------------------------------------------------------ #

def test_a_deck_with_a_build_still_saves_as_pptx(editor, tmp_path):
    """The new fields must not break the way out to PowerPoint."""
    editor.insert_shape("rect")
    editor._set_selection_animation("fade")
    editor._set_slide_transition("push")
    path = str(tmp_path / "build.pptx")
    assert PptxHandler.save(path, editor.presentation) is True
    back = PptxHandler.load(path)
    assert back is not None
    shapes = [obj for obj in back.slides[0].objects if isinstance(obj, ShapeObject)]
    assert len(shapes) == 1
