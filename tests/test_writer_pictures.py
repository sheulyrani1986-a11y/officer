"""Tests for WriteR's pictures and shapes: their size, place and text wrapping."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QTextCursor
from PySide6.QtWidgets import QTabBar

from officer.writer.document_view import PX_PER_CM
from officer.writer.window import WriteRWindow

WIDE_PX = 900


@pytest.fixture
def photo(tmp_path):
    """A 900 x 300 pixel PNG, wider than the page's text column."""
    path = str(tmp_path / "photo.png")
    image = QImage(WIDE_PX, 300, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.darkGreen)
    assert image.save(path)
    return path


@pytest.fixture
def small(tmp_path):
    path = str(tmp_path / "small.png")
    image = QImage(300, 200, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.darkBlue)
    assert image.save(path)
    return path


@pytest.fixture
def writer(q_app):
    """A WriteR window that is shown and laid out, as Word's page is.

    Qt only lays a document out once its viewport has a width; a window nobody
    shows has no viewport at all, so every height measured on it comes back
    zero or stale.
    """
    win = WriteRWindow()
    win.page.setPlainText("A paragraph of words for the picture to sit beside.")
    cursor = win.page.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    win.page.setTextCursor(cursor)
    win.resize(1200, 900)
    win.show()
    q_app.processEvents()
    return win


# -- inserted size ---------------------------------------------------------- #

def test_a_picture_wider_than_the_page_is_fitted_to_the_column(writer, photo):
    writer.page.insert_image(photo)
    info = writer.page.picture_info()
    assert info["width_px"] <= writer.page.printable_width_px + 1
    assert info["natural"] == (WIDE_PX, 300)


def test_the_picture_keeps_its_shape_when_it_is_fitted(writer, photo):
    writer.page.insert_image(photo)
    info = writer.page.picture_info()
    assert info["width_px"] / info["height_px"] == pytest.approx(WIDE_PX / 300, rel=1e-3)


def test_the_picture_reports_its_size_in_centimetres(writer, small):
    writer.page.insert_image(small, width_px=5 * PX_PER_CM, height_px=2 * PX_PER_CM)
    info = writer.page.picture_info()
    assert info["width_cm"] == pytest.approx(5.0)
    assert info["height_cm"] == pytest.approx(2.0)


def test_an_explicit_height_follows_the_picture_s_own_ratio(writer, photo):
    writer.page.insert_image(photo, height_px=150)
    info = writer.page.picture_info()
    assert info["height_px"] == pytest.approx(150)
    assert info["width_px"] == pytest.approx(450)


def test_a_picture_that_cannot_be_read_is_never_inserted(writer, tmp_path):
    writer.page.insert_image(str(tmp_path / "missing.png"))
    assert writer.page.picture_info() is None


# -- resizing --------------------------------------------------------------- #

def test_resizing_one_edge_keeps_the_other_in_proportion(writer, photo):
    writer.page.insert_image(photo)
    before = writer.page.picture_info()
    assert writer.page.set_picture_size(width_cm=9.0)
    after = writer.page.picture_info()
    assert after["width_cm"] == pytest.approx(9.0)
    assert after["height_cm"] == pytest.approx(
        9.0 * before["height_px"] / before["width_px"])


def test_a_picture_cannot_be_stretched_past_the_printable_width(writer, photo):
    writer.page.insert_image(photo)
    writer.page.set_picture_size(width_cm=60.0)
    assert writer.page.picture_info()["width_px"] <= writer.page.printable_width_px + 1


def test_growing_and_shrinking_a_picture_returns_its_size(writer, small):
    writer.page.insert_image(small)
    original = writer.page.picture_info()["width_cm"]
    writer.page.scale_picture(1.1)
    writer.page.scale_picture(1 / 1.1)
    assert writer.page.picture_info()["width_cm"] == pytest.approx(original, abs=0.01)


def test_reset_size_brings_the_picture_back_to_its_own_pixels(writer, photo):
    writer.page.insert_image(photo)
    writer.page.set_picture_size(width_cm=4.0)
    writer.page.reset_picture_size()
    # The photo is wider than the sheet, so "its own size" is the whole column.
    assert writer.page.picture_info()["width_px"] == pytest.approx(
        writer.page.printable_width_px, rel=1e-3)


# -- text wrapping ---------------------------------------------------------- #

def _page_height(writer, q_app):
    """The laid-out height of the page, as it stands after the last edit."""
    q_app.processEvents()
    return writer.page.document().size().height()


def test_a_wrapped_picture_runs_the_words_past_it(writer, small, q_app):
    writer.page.insert_image(small)
    on_picture = writer.page.textCursor().position()
    cursor = writer.page.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.insertText("\n" + "lots of words " * 120)
    writer.page.setTextCursor(cursor)
    inline_height = _page_height(writer, q_app)

    caret = writer.page.textCursor()
    caret.setPosition(on_picture)
    writer.page.setTextCursor(caret)
    assert writer.page.set_picture_wrap("left")
    assert writer.page.picture_info()["wrap"] == "left"
    assert len(writer.page.document().rootFrame().childFrames()) == 1
    # The words that used to sit under the picture now sit beside it.
    assert _page_height(writer, q_app) < inline_height


def test_unwrapping_a_picture_takes_its_frame_with_it(writer, small):
    writer.page.insert_image(small)
    writer.page.set_picture_wrap("right")
    writer.page.set_picture_wrap("inline")
    assert writer.page.picture_info()["wrap"] == "inline"
    assert writer.page.document().rootFrame().childFrames() == []
    assert "￼" in writer.page.toPlainText()


def test_top_and_bottom_spacing_clears_the_lines_around_a_picture(writer, small):
    writer.page.insert_image(small)
    writer.page.set_picture_wrap("top_bottom")
    cursor = QTextCursor(writer.page.document())
    cursor.setPosition(writer.page.textCursor().position())
    assert cursor.blockFormat().bottomMargin() > 0


def test_the_next_picture_is_not_dropped_inside_a_wrapped_one(writer, small, photo):
    writer.page.insert_image(small, wrap="left")
    writer.page.insert_image(photo)
    assert writer.page.picture_info()["wrap"] == "inline"
    assert len(writer.page.document().rootFrame().childFrames()) == 1


def test_an_inline_picture_can_be_moved_across_the_column(writer, small):
    writer.page.insert_image(small)
    assert writer.page.set_picture_alignment(Qt.AlignmentFlag.AlignLeft)
    cursor = QTextCursor(writer.page.document())
    cursor.setPosition(writer.page.textCursor().position())
    assert cursor.blockFormat().alignment() == Qt.AlignmentFlag.AlignLeft


def test_a_wrapped_picture_is_placed_by_its_side_not_by_alignment(writer, small):
    writer.page.insert_image(small, wrap="right")
    assert writer.page.set_picture_alignment(Qt.AlignmentFlag.AlignLeft) is False


# -- the contextual ribbon tab ---------------------------------------------- #

def _tabs(win):
    bar = win.ribbon.findChild(QTabBar)
    return {bar.tabText(i): bar.isTabVisible(i) for i in range(bar.count())}


def test_the_picture_tab_only_appears_over_a_picture(writer, photo):
    assert _tabs(writer)["Picture Format"] is False
    writer.page.insert_image(photo)
    assert _tabs(writer)["Picture Format"] is True
    writer.page.moveCursor(QTextCursor.MoveOperation.Start)
    assert _tabs(writer)["Picture Format"] is False


def test_the_picture_tab_opens_itself_and_makes_room_for_the_words(writer, photo, q_app):
    writer.page.insert_image(photo)
    q_app.processEvents()
    bar = writer.ribbon.tab_bar
    assert writer.ribbon.current_tab_name == "Picture Format"
    index = next(i for i in range(bar.count()) if bar.tabText(i) == "Picture Format")
    # A band that grew a tab must want the room for it, or the tab paints
    # outside its own edge and the user never sees the command they clicked for.
    assert bar.tabRect(index).right() < bar.width()


def test_the_size_boxes_show_the_picture_s_centimetres(writer, small):
    writer.page.insert_image(small, width_px=5 * PX_PER_CM, height_px=2 * PX_PER_CM)
    assert writer.pic_width_spin.value() == pytest.approx(5.0, abs=0.01)
    assert writer.pic_height_spin.value() == pytest.approx(2.0, abs=0.01)


def test_typing_a_new_width_in_the_box_resizes_the_picture(writer, small):
    writer.page.insert_image(small)
    before = writer.page.picture_info()
    writer.pic_width_spin.setValue(before["width_cm"] / 2)
    after = writer.page.picture_info()
    assert after["width_cm"] == pytest.approx(before["width_cm"] / 2, abs=0.02)
    assert after["height_cm"] == pytest.approx(before["height_cm"] / 2, abs=0.02)


def test_the_wrap_menu_marks_the_way_the_picture_sits(writer, small):
    writer.page.insert_image(small)
    writer._picture_wrap_buttons["left"].trigger()
    assert writer.page.picture_info()["wrap"] == "left"
    assert writer._picture_wrap_buttons["left"].isChecked()
    assert writer._picture_wrap_buttons["inline"].isChecked() is False


# -- shapes ----------------------------------------------------------------- #

def test_a_shape_is_drawn_larger_than_it_prints_so_zooming_stays_crisp(writer):
    from officer.writer.shape_insert import SHAPE_SIZES_CM, render_shape_to_temp
    path = render_shape_to_temp("ellipse", width_cm=5.0, height_cm=5.0)
    natural = QImage(path).size()
    assert natural.width() > 5.0 * PX_PER_CM * 2


# -- tables ----------------------------------------------------------------- #

def test_a_table_spans_the_column_from_margin_to_margin(writer):
    writer.page.insert_table(3, 3)
    table = writer.page.document().rootFrame().childFrames()[0].frameFormat().toTableFormat()
    assert table.columns() == 3
    assert table.width().type().name == "PercentageLength"
    assert table.width().rawValue() == pytest.approx(100.0)
    assert [c.rawValue() for c in table.columnWidthConstraints()] == pytest.approx(
        [100 / 3] * 3)
