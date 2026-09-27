"""Tests for PresentR slide deck model, PPTX, ODP, and PDF serialization."""

import os
import tempfile
import pytest
from PySide6.QtWidgets import (
    QApplication, QGraphicsPathItem, QGraphicsTextItem,
)
from PySide6.QtCore import QRectF, Qt
from PySide6.QtTest import QTest
from officer.presentr.slide_deck import (
    DEFAULT_FONT_FAMILY, Presentation, Slide, TextObject, ShapeObject
)
from officer.presentr.io.pptx_handler import PptxHandler
from officer.presentr.io.odp_handler import OdpHandler
from officer.presentr.presenter_mode import PresenterWindow
from officer.presentr.window import PresentRWindow
from officer.presentr.canvas import shape_path
from officer.presentr.slide_deck import LAYOUT_PLACEHOLDERS



def test_presentation_model():
    prs = Presentation("Quarterly Report")
    assert len(prs.slides) == 1
    assert prs.width == 960
    assert prs.height == 540

    slide2 = prs.add_slide(layout="title_content")
    assert len(prs.slides) == 2
    assert slide2.title == "Slide 2"
    assert len(slide2.objects) == 2


def test_pptx_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        pptx_path = os.path.join(tmpdir, "presentation.pptx")

        prs = Presentation("Tech Deck")
        s = prs.slides[0]
        s.objects.append(
            TextObject(id="t1", x=50, y=50, width=500, height=80, text="OfficeR PresentR Launch", font_size=32)
        )
        s.objects.append(
            ShapeObject(id="s1", x=100, y=150, width=200, height=100, shape_type="rect")
        )

        saved = PptxHandler.save(pptx_path, prs)
        assert saved is True
        assert os.path.exists(pptx_path)
        assert os.path.getsize(pptx_path) > 0

        loaded = PptxHandler.load(pptx_path)
        assert loaded is not None
        assert len(loaded.slides) >= 1
        found_text = any(
            obj.text == "OfficeR PresentR Launch"
            for s in loaded.slides
            for obj in s.objects
            if isinstance(obj, TextObject)
        )
        assert found_text is True


def test_odp_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        odp_path = os.path.join(tmpdir, "presentation.odp")

        prs = Presentation("OpenDocument Deck")
        s = prs.slides[0]
        s.objects.append(
            TextObject(id="t1", x=60, y=60, width=400, height=60, text="OpenDocument Slide 1", font_size=24)
        )

        saved = OdpHandler.save(odp_path, prs)
        assert saved is True
        assert os.path.exists(odp_path)

        loaded = OdpHandler.load(odp_path)
        assert loaded is not None
        assert len(loaded.slides) >= 1


def test_presentr_window():
    win = PresentRWindow()
    assert win.slide_list.count() == 1
    win.add_new_slide()
    assert win.slide_list.count() == 2
    assert len(win.presentation.slides) == 2
    win.delete_current_slide()
    assert win.slide_list.count() == 1
    win.close()


# --- Speaker Notes ---


def test_slide_model_defaults_to_empty_notes():
    assert Slide().notes == ""
    assert Slide(title="T", notes="cue").notes == "cue"


def test_notes_panel_follows_selected_slide():
    """Regression: switching slides must reload the panel, not carry text over.

    Previously the editor kept the previous slide's text while the index moved,
    so typing after a switch overwrote the new slide's notes.
    """
    win = PresentRWindow()
    try:
        win.notes_edit.setPlainText("Slide one cue")
        assert win.presentation.slides[0].notes == "Slide one cue"

        win.add_new_slide()
        assert win.notes_edit.toPlainText() == ""
        assert win.presentation.slides[0].notes == "Slide one cue"
        assert win.presentation.slides[1].notes == ""

        win.notes_edit.setPlainText("Slide two cue")
        assert win.presentation.slides[1].notes == "Slide two cue"
        assert win.presentation.slides[0].notes == "Slide one cue"

        win.slide_list.setCurrentRow(0)
        assert win.notes_edit.toPlainText() == "Slide one cue"
        assert win.presentation.slides[0].notes == "Slide one cue"
        assert win.presentation.slides[1].notes == "Slide two cue"
    finally:
        win.close()


def test_notes_panel_cleared_on_new_and_opened_deck():
    win = PresentRWindow()
    try:
        win.notes_edit.setPlainText("Temporary cue")
        win.on_new()
        assert win.notes_edit.toPlainText() == ""
        assert win.presentation.slides[0].notes == ""
    finally:
        win.close()


def test_notes_panel_toggle_from_ribbon():
    win = PresentRWindow()
    try:
        assert not win.notes_panel.isHidden()
        win.notes_button.click()
        assert win.notes_panel.isHidden()
        assert win.notes_button.isChecked() is False
        win.notes_button.click()
        assert not win.notes_panel.isHidden()
        assert win.notes_button.isChecked() is True
    finally:
        win.close()


def test_notes_survive_slide_delete():
    win = PresentRWindow()
    try:
        win.notes_edit.setPlainText("First slide cue")
        win.add_new_slide()
        win.notes_edit.setPlainText("Second slide cue")
        win.delete_current_slide()
        assert win.current_slide_idx == 0
        assert win.notes_edit.toPlainText() == "First slide cue"
        assert win.presentation.slides[0].notes == "First slide cue"
    finally:
        win.close()


def test_pptx_notes_round_trip():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "notes.pptx")

        prs = Presentation("Notes Deck")
        prs.slides[0].notes = "Open with the roadmap.\nThen ask for budget."
        prs.add_slide()
        prs.slides[1].notes = "Second slide cue"

        assert PptxHandler.save(path, prs) is True
        loaded = PptxHandler.load(path)
        assert loaded is not None
        assert loaded.slides[0].notes == "Open with the roadmap.\nThen ask for budget."
        assert loaded.slides[1].notes == "Second slide cue"


def test_odp_notes_round_trip():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "notes.odp")

        prs = Presentation("Notes Deck")
        prs.slides[0].objects.append(
            TextObject(id="t1", x=60, y=60, width=400, height=60, text="Visible slide text")
        )
        prs.slides[0].notes = "Speaker only line."

        assert OdpHandler.save(path, prs) is True
        loaded = OdpHandler.load(path)
        assert loaded is not None
        assert loaded.slides[0].notes == "Speaker only line."

        # The notes frame must not leak onto the slide as a text object.
        slide_texts = [
            obj.text for obj in loaded.slides[0].objects if isinstance(obj, TextObject)
        ]
        assert "Speaker only line." not in slide_texts


def test_notes_panel_cannot_be_dragged_out_of_reach():
    win = PresentRWindow()
    try:
        assert win.notes_splitter.childrenCollapsible() is False
        win.show()
        QTest.qWait(30)
        win.notes_splitter.setSizes([10000, 1])
        QTest.qWait(30)
        assert win.notes_panel.height() >= 120
    finally:
        win.close()


def test_canvas_refits_when_notes_pane_is_resized():
    """Dragging the notes splitter must rescale the slide instead of clipping it."""
    win = PresentRWindow()
    try:
        win.show()
        QTest.qWait(30)
        win.notes_splitter.setSizes([900, 120])
        QTest.qWait(30)
        scale_tall_canvas = win.canvas_view.transform().m11()

        win.notes_splitter.setSizes([300, 700])
        QTest.qWait(30)
        scale_short_canvas = win.canvas_view.transform().m11()

        assert scale_short_canvas < scale_tall_canvas
    finally:
        win.close()


def test_zoom_slider_disables_automatic_fit():
    """An explicit zoom level survives pane resizes, and returns on slide change."""
    win = PresentRWindow()
    try:
        win.show()
        QTest.qWait(30)
        win._on_zoom_changed(150)
        assert win.canvas_view.fit_to_view is False
        zoomed = win.canvas_view.transform().m11()
        assert zoomed == pytest.approx(1.5)

        win.notes_splitter.setSizes([300, 700])
        QTest.qWait(30)
        assert win.canvas_view.transform().m11() == pytest.approx(zoomed)

        win.add_new_slide()
        assert win.canvas_view.fit_to_view is True
    finally:
        win.close()


def test_presenter_notes_overlay():
    prs = Presentation("Deck")
    prs.slides[0].notes = "Say hello first."
    prs.add_slide()

    pres = PresenterWindow(prs)
    try:
        assert pres.notes_label.isHidden()  # hidden until the presenter asks
        pres.toggle_notes()
        assert not pres.notes_label.isHidden()
        assert pres.notes_label.text() == "Say hello first."

        pres.current_index = 1
        pres._show_current_slide()
        assert pres.notes_label.text() == "No notes for this slide."
    finally:
        pres.close()


def test_presenter_notes_can_open_visible():
    prs = Presentation("Deck")
    prs.slides[0].notes = "Pre-show cue."

    pres = PresenterWindow(prs, show_notes=True)
    try:
        assert not pres.notes_label.isHidden()
        assert pres.notes_label.text() == "Pre-show cue."
    finally:
        pres.close()



# --- PowerPoint-style commands: layouts, formatting, themes, sorter, round trip ---


def _select_box(win, obj_id: str) -> QGraphicsTextItem:
    """Select one placeholder box on the canvas so the ribbon has a target."""
    for item in win.scene.items():
        if isinstance(item, QGraphicsTextItem) and getattr(item.data(0), "id", None) == obj_id:
            win.scene.clearSelection()
            item.setSelected(True)
            return item
    raise AssertionError(f"no '{obj_id}' text box on the current slide")


def _model_box(win, obj_id: str, row: int = None) -> TextObject:
    row = win.current_slide_idx if row is None else row
    return next(obj for obj in win.presentation.slides[row].objects if obj.id == obj_id)


def test_apply_layout_moves_content_and_adds_missing_placeholders():
    """Reflowing keeps what the presenter typed; blank never deletes it."""
    slide = Slide()
    slide.apply_layout("title_content")
    _select_title = next(obj for obj in slide.objects if obj.id == "title")
    _select_title.text = "Revenue up 12%"
    _select_title.bold = False

    slide.apply_layout("two_content")
    assert slide.layout == "two_content"
    moved = next(obj for obj in slide.objects if obj.id == "title")
    assert moved.text == "Revenue up 12%", "typed text must survive a layout change"
    spec = {s[0]: s for s in LAYOUT_PLACEHOLDERS["two_content"]}["title"]
    assert (moved.x, moved.y, moved.width, moved.height) == spec[1:5]
    assert moved.bold is True, "the new layout's formatting wins"
    ids = {obj.id for obj in slide.objects}
    assert {"title", "left", "right"} <= ids
    assert "content" in ids, "a layout change never throws away what was typed"

    slide.apply_layout("blank")
    assert slide.layout == "blank"
    assert sum(obj.text == "Revenue up 12%" for obj in slide.objects) == 1


def test_change_layout_from_the_ribbon_redraws_the_canvas():
    win = PresentRWindow()
    try:
        win._change_layout("two_content")
        assert win.presentation.slides[0].layout == "two_content"
        slide_boxes = {obj.id for obj in win.presentation.slides[0].objects}
        assert {"title", "left", "right"} <= slide_boxes
        scene_boxes = {getattr(item.data(0), "id", None) for item in win.scene.items()}
        assert {"left", "right"} <= scene_boxes, "the canvas must show the new boxes"
        assert win.status_bar.info_label.text() == "Layout changed to: Two Content"
    finally:
        win.close()


def test_reset_slide_restores_formatting_but_keeps_the_text():
    win = PresentRWindow()
    try:
        win._change_layout("title_content")
        item = _select_box(win, "content")
        item.setPlainText("typed body")
        win.scene.sync_to_slide()

        win._set_text_align("center")
        win._set_line_spacing(2.0)
        win._toggle_text_attribute("italic")
        box = _model_box(win, "content")
        assert (box.alignment, box.line_spacing, box.italic) == ("center", 2.0, True)

        win._reset_current_slide()
        box = _model_box(win, "content")
        assert box.text == "typed body", "Office resets the formatting, not the content"
        assert (box.alignment, box.line_spacing, box.italic) == ("left", 1.0, False)
        assert box.font_size == 20
    finally:
        win.close()


def test_font_and_paragraph_commands_write_through_to_the_model():
    win = PresentRWindow()
    try:
        item = _select_box(win, "title")
        box = _model_box(win, "title")          # the title placeholder starts bold

        win._toggle_text_attribute("bold")
        assert box.bold is False, "toggling a bold placeholder unbolds it"
        win._toggle_text_attribute("bold")
        assert box.bold is True
        win._toggle_text_attribute("underline")
        assert box.underline is True

        win._step_font_size(-4)
        assert box.font_size == 36
        win._set_text_align("left")
        assert box.alignment == "left"
        win._set_line_spacing(1.5)
        assert box.line_spacing == 1.5
        assert item.toPlainText() == box.text

        win._clear_text_format()
        assert (box.bold, box.italic, box.underline, box.strike) == (False,) * 4
        assert box.line_spacing == 1.0 and box.text_color == "#111827"
    finally:
        win.close()


def test_bullets_toggle_round_trips_without_eating_text():
    win = PresentRWindow()
    try:
        win._change_layout("title_content")
        item = _select_box(win, "content")
        item.setPlainText("First\nSecond")     # the canvas, not the model, holds it

        win._toggle_bullets()
        assert item.toPlainText() == "• First\n• Second"
        assert _model_box(win, "content").text == "• First\n• Second"
        win._toggle_bullets()
        assert _model_box(win, "content").text == "First\nSecond"
    finally:
        win.close()


def test_format_toggles_light_up_for_the_selection():
    """The ribbon must read the selection, so pressing Bold is a real undo."""
    win = PresentRWindow()
    try:
        _select_box(win, "title")               # bold, centred by the title layout
        assert win._text_attr_buttons["bold"].isChecked()
        assert not win._text_attr_buttons["underline"].isChecked()
        assert win._text_align_buttons["center"].isChecked()
        assert not win._text_align_buttons["left"].isChecked()

        win.scene.clearSelection()
        win._sync_text_buttons()
        assert not any(btn.isChecked() for btn in win._text_attr_buttons.values())
        assert not any(btn.isChecked() for btn in win._text_align_buttons.values())

        # With nothing selected the command warns instead of corrupting a slide.
        win._toggle_text_attribute("bold")
        assert win.status_bar.info_label.text() == "Select a text box first."
    finally:
        win.close()


def test_every_offered_shape_but_the_plain_ones_gets_its_own_path():
    rect = QRectF(0, 0, 100, 60)
    outlines = {}
    for shape_type in PresentRWindow._RIBBON_SHAPES:
        path = shape_path(shape_type, rect)
        if shape_type in ("rect", "ellipse"):
            assert path is None, f"{shape_type} keeps its dedicated item"
            continue
        assert path is not None and not path.isEmpty(), f"{shape_type} drew nothing"
        polygon = [(round(p.x(), 1), round(p.y(), 1)) for p in path.toFillPolygon()]
        outlines[shape_type] = (polygon[0], polygon[len(polygon) // 2], len(polygon))
    assert len(set(outlines.values())) == len(outlines), f"shapes share an outline: {outlines}"


def test_a_star_lands_on_the_canvas_as_a_path():
    win = PresentRWindow()
    try:
        win.insert_shape("star")
        win.insert_shape("rect")
        paths = [item for item in win.scene.items() if isinstance(item, QGraphicsPathItem)]
        assert len(paths) == 1, "only the star should be painted as a path"
        assert paths[0].data(0).shape_type == "star"
        win.scene.sync_to_slide()
        kinds = {obj.shape_type for obj in win.presentation.slides[0].objects
                 if isinstance(obj, ShapeObject)}
        assert kinds == {"star", "rect"}
    finally:
        win.close()


def test_theme_recolours_ground_text_and_shapes():
    win = PresentRWindow()
    try:
        win.insert_shape("rect")
        win.scene.sync_to_slide()
        before = _model_box(win, "title").text_color

        win._apply_theme("emerald_executive")
        bg, text, accent = PresentRWindow._THEMES["emerald_executive"]
        for slide in win.presentation.slides:
            assert slide.background_color == bg
            for obj in slide.objects:
                if isinstance(obj, TextObject):
                    assert obj.text_color == text
                elif isinstance(obj, ShapeObject):
                    assert obj.fill_color == accent
        assert before != text, "the light theme's text must actually change"
        assert win.status_bar.info_label.text() == "Theme applied: Emerald"
    finally:
        win.close()


def test_sorter_reorder_moves_the_slide_and_follows_it():
    win = PresentRWindow()
    try:
        win.add_new_slide()
        win.add_new_slide()
        first, second, third = list(win.presentation.slides)

        win._move_slide(0, 2)
        assert win.presentation.slides == [second, third, first]
        assert win.current_slide_idx == 2
        assert win.slide_list.currentRow() == 2
        assert win.slide_list.count() == win.sorter_view.count() == 3
    finally:
        win.close()


def test_status_strip_view_buttons_switch_the_editor():
    win = PresentRWindow()
    try:
        buttons = win.status_bar._mode_buttons
        assert set(buttons) == {"normal", "sorter", "reading"}

        buttons["sorter"].click()
        assert win.editor_stack.currentWidget() is win.sorter_view
        assert buttons["sorter"].isChecked() and not buttons["normal"].isChecked()

        buttons["reading"].click()
        assert win.editor_stack.currentWidget() is win.notes_splitter
        assert win.slide_list.isHidden(), "reading view shows the slide alone"
        assert buttons["reading"].isChecked()

        buttons["normal"].click()
        assert not win.slide_list.isHidden()
        assert win.editor_stack.currentWidget() is win.notes_splitter

        # PowerPoint's trailing Slide Show button is a command, not a view.
        show = win.status_bar.view_layout.itemAt(
            win.status_bar.view_layout.count() - 1).widget()
        assert not show.isCheckable()
        assert show not in buttons.values()
    finally:
        win.close()


def test_pptx_round_trips_the_formatting_the_ribbon_writes():
    """A deck PresentR saves must reopen in PresentR unchanged."""
    win = PresentRWindow()
    try:
        item = _select_box(win, "title")
        item.setPlainText("Quarterly")
        win._toggle_text_attribute("underline")
        win._toggle_text_attribute("strike")
        win._set_text_align("left")
        win._set_line_spacing(1.5)
        win._choose_text_color  # noqa: B018 -- the picker needs a human; set it directly
        _model_box(win, "title").text_color = "#FFFFFF"
        win.insert_shape("star")
        win.scene.sync_to_slide()
        expected = {obj.id: obj for obj in win.presentation.slides[0].objects}

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "deck.pptx")
            assert PptxHandler.save(path, win.presentation) is True
            back = PptxHandler.load(path)
            assert back is not None
    finally:
        win.close()

    boxes = [o for s in back.slides for o in s.objects if isinstance(o, TextObject)]
    stars = [o for s in back.slides for o in s.objects if isinstance(o, ShapeObject)]
    title = next(o for o in boxes if o.text == "Quarterly")
    assert (title.bold, title.underline, title.strike) == (True, True, True)
    assert (title.alignment, title.line_spacing, title.text_color) == ("left", 1.5, "#FFFFFF")
    assert title.font_size == 40
    assert [o.shape_type for o in stars] == ["star"]


# -- the face a slide is written in ------------------------------------------- #

def test_the_font_box_lists_every_family_the_machine_has():
    """PresentR's box is the same list WriteR and RSheet were given."""
    from officer.core.ui.fonts import installed_families
    win = PresentRWindow()
    try:
        assert win.font_combo.count() == len(installed_families())
        assert win.font_combo.isEditable()
        assert win.font_combo.itemText(0) == installed_families()[0]
        # Each name drawn by the font it names, or a long list is unreadable.
        for row in range(win.font_combo.count()):
            preview = win.font_combo.itemData(row, Qt.ItemDataRole.FontRole)
            assert preview.families()[0] == win.font_combo.itemText(row)
    finally:
        win.close()


def test_choosing_a_font_lands_on_the_box_and_on_the_canvas():
    from officer.core.ui.fonts import installed_families
    win = PresentRWindow()
    try:
        item = _select_box(win, "title")
        family = installed_families()[-1]
        win._set_font_family(family)
        assert _model_box(win, "title").font_family == family
        assert item.font().families()[0] == family
    finally:
        win.close()


def test_picking_a_font_from_the_box_reaches_the_slide():
    """The button is wired, not merely present: activating it is the command."""
    from officer.core.ui.fonts import installed_families
    win = PresentRWindow()
    try:
        _select_box(win, "title")
        family = installed_families()[1]
        win.font_combo.textActivated.emit(family)
        assert _model_box(win, "title").font_family == family
    finally:
        win.close()


def test_the_box_names_the_face_on_screen_not_the_one_the_deck_asked_for():
    """A deck can want a face this machine has not got; the box lists real ones."""
    from officer.core.ui.fonts import installed_families
    win = PresentRWindow()
    try:
        _select_box(win, "title")
        _model_box(win, "title").font_family = "Definitely Not A Real Face"
        win._sync_text_buttons()
        shown = win.font_combo.currentText()
        assert shown in installed_families(), shown
    finally:
        win.close()


def test_clearing_formatting_returns_to_the_default_face():
    from officer.core.ui.fonts import installed_families
    win = PresentRWindow()
    try:
        _select_box(win, "title")
        win._set_font_family(installed_families()[-1])
        win._clear_text_format()
        assert _model_box(win, "title").font_family == DEFAULT_FONT_FAMILY
    finally:
        win.close()


def test_pptx_round_trips_the_font_face():
    """The name a presenter picks is the name PowerPoint will show in its box."""
    prs = Presentation("Fonts")
    prs.slides[0].objects.clear()
    prs.slides[0].objects.append(TextObject(id="t", x=60, y=40, width=500,
                                            height=80, text="In Cambria",
                                            font_family="Cambria"))
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "faces.pptx")
        assert PptxHandler.save(path, prs) is True
        back = PptxHandler.load(path)
    assert back is not None
    box = back.slides[0].objects[0]
    assert box.font_family == "Cambria", "an uninstalled name still has to survive"
    assert box.text == "In Cambria"


def test_pptx_keeps_the_default_face_for_a_run_that_names_none():
    """A theme-inherited run from another program must not come back nameless."""
    prs = Presentation("Plain")
    prs.slides[0].objects.clear()
    prs.slides[0].objects.append(TextObject(id="t", x=60, y=40, width=500,
                                            height=80, text="Default face"))
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "default.pptx")
        assert PptxHandler.save(path, prs) is True
        back = PptxHandler.load(path)
    assert back.slides[0].objects[0].font_family == DEFAULT_FONT_FAMILY


@pytest.mark.parametrize("shape_type", list(PresentRWindow._RIBBON_SHAPES))
def test_pptx_round_trips_every_shape_button(shape_type):
    """Each Insert ▸ Shapes button must survive save and reopen."""
    prs = Presentation("Shapes")
    prs.slides[0].objects.clear()
    prs.slides[0].objects.append(ShapeObject(id="s1", x=100, y=150, width=180,
                                             height=120, shape_type=shape_type,
                                             fill_color="#10B981",
                                             border_color="#064E3B"))
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "shapes.pptx")
        assert PptxHandler.save(path, prs) is True
        back = PptxHandler.load(path)
        assert back is not None
        shapes = [o for s in back.slides for o in s.objects if isinstance(o, ShapeObject)]
        assert len(shapes) == 1, f"{shape_type} vanished"
        assert shapes[0].shape_type == shape_type
        assert shapes[0].fill_color == "#10B981"
        assert shapes[0].border_color == "#064E3B"
