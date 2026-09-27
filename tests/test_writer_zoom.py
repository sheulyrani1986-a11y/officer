"""Tests for WriteR's view zoom: the page grows, the document keeps its sizes."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QTextCursor, QTextDocument

from officer.writer.document_view import MARGIN_PRESETS, PX_PER_CM
from officer.writer.io.docx_handler import DocxHandler
from officer.writer.window import WriteRWindow

WIDE_PX = 900


@pytest.fixture
def writer(q_app):
    """A WriteR window with a heading and a body line, as Word opens on one."""
    win = WriteRWindow()
    win.resize(1400, 900)
    win.show()
    q_app.processEvents()
    page = win.page
    page.setPlainText("")
    page.set_font_size(20)
    page.textCursor().insertText("Heading")
    page.textCursor().insertBlock()
    page.set_font_size(11)
    page.textCursor().insertText("Body text")
    q_app.processEvents()
    return win


def _sizes(page) -> list:
    """Every point size the document itself carries, in the units it holds them."""
    found = []
    block = page.document().begin()
    while block.isValid():
        walk = block.begin()
        while not walk.atEnd():
            format_ = walk.fragment().charFormat()
            if format_.fontPointSize() > 0:
                found.append(round(format_.fontPointSize(), 2))
            walk += 1
        block = block.next()
    return found


# -- what zoom does to the page and to the document --------------------------- #

def test_the_size_box_reads_the_points_that_were_typed_not_the_ones_on_screen(writer):
    writer.page.set_zoom(150)
    cursor = writer.page.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(QTextCursor.MoveOperation.NextCharacter,
                        QTextCursor.MoveMode.KeepAnchor, 1)
    writer.page.setTextCursor(cursor)
    assert _sizes(writer.page) == [30.0, 16.5], "the document carries zoomed sizes"
    assert writer.page.current_font_point_size() == pytest.approx(20.0)
    writer._sync_font_box()
    assert writer.size_spin.value() == 20, "and Word's box shows the real one"


def test_every_run_grows_by_the_same_ratio(writer):
    """A zoom that only grew the default font left headings behind the body."""
    writer.page.set_zoom(200)
    assert _sizes(writer.page) == [40.0, 22.0]


@pytest.mark.parametrize("percent", [110, 150, 200, 400, 60])
def test_zooming_straight_back_restores_the_sizes_exactly(writer, percent):
    before = _sizes(writer.page)
    writer.page.set_zoom(percent)
    writer.page.set_zoom(100)
    assert _sizes(writer.page) == before


def test_the_page_and_its_text_grow_together(writer):
    page = writer.page
    page.set_zoom(100)
    q_app_height = page.document().size().height()
    width = page.width()
    page.set_zoom(200)
    assert page.width() == pytest.approx(width * 2, abs=2)
    assert page.document().size().height() == pytest.approx(q_app_height * 2, abs=4)


def test_the_margins_on_the_sheet_grow_with_the_page(writer):
    page = writer.page
    page.set_zoom(150)
    assert page.margin_pixels == MARGIN_PRESETS["Normal"], "Word's box still says Normal"
    assert page.document().documentMargin() == pytest.approx(
        MARGIN_PRESETS["Normal"] * 1.5)


def test_zooming_leaves_the_undo_history_and_the_modified_flag_alone(writer):
    """A change of view must not throw away what was typed, nor ask to save it."""
    page = writer.page
    cursor = page.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText(" and more")
    page.document().setModified(False)
    undo = page.document().availableUndoSteps()
    page.set_zoom(170)
    assert page.document().isModified() is False
    assert page.document().availableUndoSteps() >= undo
    text = page.toPlainText()
    page.document().undo()
    page.document().undo()
    assert "Heading" in page.toPlainText(), "the typing history is still there"
    page.document().redo()
    page.document().redo()
    assert page.toPlainText() == text


# -- sizes the user sets while the view is zoomed ----------------------------- #

def _select_body(page) -> None:
    """Put the caret on the body line the fixture wrote, as a reader would."""
    cursor = page.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.MoveAnchor)
    cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock,
                        QTextCursor.MoveMode.KeepAnchor)
    page.setTextCursor(cursor)


def test_picking_a_size_while_zoomed_writes_the_size_that_was_asked_for(writer):
    page = writer.page
    page.set_zoom(125)
    _select_body(page)
    page.set_font_size(14)
    assert _sizes(page)[-1] == pytest.approx(17.5)
    assert page.current_font_point_size() == pytest.approx(14.0)


def test_growing_a_font_while_zoomed_adds_the_points_it_promised(writer):
    page = writer.page
    page.set_zoom(200)
    _select_body(page)
    page.increase_font_size()
    page.increase_font_size()
    assert page.current_font_point_size() == pytest.approx(13.0)
    page.decrease_font_size()
    assert page.current_font_point_size() == pytest.approx(12.0)
    assert _sizes(page)[-1] == pytest.approx(24.0)


def test_a_heading_applied_while_zoomed_is_the_heading_it_always_was(writer):
    page = writer.page
    page.set_zoom(250)
    _select_body(page)
    page.apply_heading(1)
    assert page.current_font_point_size() == pytest.approx(20.0)
    assert page.textCursor().blockFormat().topMargin() == pytest.approx(30.0)


# -- pictures ------------------------------------------------------------------ #

def test_a_picture_is_still_its_own_centimetres_when_the_view_is_zoomed(writer, tmp_path):
    path = str(tmp_path / "photo.png")
    image = QImage(WIDE_PX, 300, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.darkGreen)
    assert image.save(path)
    page = writer.page
    _select_body(page)
    page.insert_image(path)
    fitted = page.picture_info()["width_cm"]
    assert fitted == pytest.approx(page.printable_width_px / PX_PER_CM, abs=0.1)
    page.set_zoom(150)
    writer._sync_picture_tab()
    assert page.picture_info()["width_cm"] == pytest.approx(fitted, abs=0.1)
    assert writer.pic_width_spin.value() == pytest.approx(fitted, abs=0.1)
    page.set_picture_size(width_cm=5.0)
    assert page.picture_info()["width_cm"] == pytest.approx(5.0, abs=0.05)
    page.set_zoom(100)
    assert page.picture_info()["width_cm"] == pytest.approx(5.0, abs=0.05)


# -- the way out to disk ------------------------------------------------------- #

def _sizes_of(document) -> list:
    found = []
    block = document.begin()
    while block.isValid():
        walk = block.begin()
        while not walk.atEnd():
            size = walk.fragment().charFormat().fontPointSize()
            if size > 0:
                found.append(round(size, 2))
            walk += 1
        block = block.next()
    return found


def test_a_document_saved_while_zoomed_keeps_the_sizes_it_was_written_in(writer, tmp_path):
    writer.page.set_zoom(175)
    filepath = str(tmp_path / "zoomed.docx")
    writer._save_to_path(filepath)
    back = QTextDocument()
    assert DocxHandler.load(filepath, back) is True
    sizes = _sizes_of(back)
    assert 20.0 in sizes and 11.0 in sizes, f"zoom leaked into the file: {sizes}"
    assert _sizes_of(writer.page.document()) == [35.0, 19.25], "the view is still zoomed"


def test_a_document_opened_at_a_zoom_is_shown_at_that_zoom(writer):
    """A file arrives at its own sizes; the view has to catch up with it."""
    page = writer.page
    page.set_zoom(200)
    page.document().setHtml('<p style="font-size:20pt">Heading</p>'
                            '<p style="font-size:11pt">Body</p>')
    page.reapply_zoom()
    assert _sizes(page) == [40.0, 22.0]
    assert page.current_font_point_size() == pytest.approx(11.0)
    assert page.document().documentMargin() == pytest.approx(
        MARGIN_PRESETS["Normal"] * 2)


def test_the_default_font_follows_the_view_so_new_text_arrives_at_that_size(writer):
    page = writer.page
    page.set_zoom(150)
    assert page.document().defaultFont().pointSizeF() == pytest.approx(16.5)
    assert page.font().pointSizeF() == pytest.approx(16.5)
    assert page.current_font_point_size() == pytest.approx(11.0)
