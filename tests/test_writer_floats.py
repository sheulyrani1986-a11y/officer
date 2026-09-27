"""WriteR's objects that lie on the sheet: their place, size, anchor and wrapping.

A picture in the sentence is a character (see ``test_writer_pictures.py``); an
object on the sheet is a thing you drag about the page while the words run
round it. These tests measure the second kind in the centimetres the ribbon
shows, because that is what the user is promised.
"""

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QSize, Qt
from PySide6.QtGui import QImage, QKeyEvent, QMouseEvent, QTextCursor
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication, QTabBar

from officer.writer.document_view import FLOAT_BASE_LEFT, FLOAT_BASE_RIGHT, PX_PER_CM
from officer.writer.floating import MIN_SIZE_CM, WRAP_GAP_CM
from officer.writer.window import WriteRWindow

GREEN = Qt.GlobalColor.darkGreen


@pytest.fixture
def square(tmp_path):
    """A 200 x 200 green PNG: 5.29 cm on its own, narrower than the column."""
    path = str(tmp_path / "square.png")
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    image.fill(GREEN)
    assert image.save(path)
    return path


@pytest.fixture
def wide(tmp_path):
    """A 1200 x 300 PNG: wider than any sheet, so it has to be fitted."""
    path = str(tmp_path / "wide.png")
    image = QImage(1200, 300, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.red)
    assert image.save(path)
    return path


@pytest.fixture
def writer(q_app):
    """A laid-out WriteR window with two paragraphs for objects to sit against.

    Qt only measures a document once its viewport has a width, and an object's
    height is measured against the paragraphs it covers, so an unseen window
    cannot answer any of these questions.
    """
    win = WriteRWindow()
    win.page.setPlainText("First paragraph.\n" + "lots of words " * 200)
    cursor = win.page.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
    win.page.setTextCursor(cursor)
    win.resize(1200, 900)
    win.show()
    q_app.processEvents()
    return win


def _tie(q_app):
    """Let the deferred pass that ropes the words round the objects run."""
    for _ in range(4):
        q_app.processEvents()


def _block_formats(page):
    return [page.document().findBlockByNumber(i).blockFormat()
            for i in range(page.document().blockCount())]


def _press_move_release(widget, from_px, to_px, q_app):
    """Carry the pointer from one point of *widget* to another, as a drag does."""
    start = widget.mapToGlobal(from_px)
    end = widget.mapToGlobal(to_px)
    for kind, local, global_ in (
            (QEvent.Type.MouseButtonPress, from_px, start),
            (QEvent.Type.MouseMove, to_px, end),
            (QEvent.Type.MouseButtonRelease, to_px, end)):
        QApplication.sendEvent(widget, QMouseEvent(
            kind, QPointF(local), QPointF(global_), Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove
            else Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    q_app.processEvents()


# -- an object is not a character ------------------------------------------- #

def test_an_object_lies_on_the_sheet_rather_than_in_the_sentence(writer, square):
    before = writer.page.toPlainText()
    assert writer.page.insert_float(square) is True
    assert len(writer.page.floats()) == 1
    # The writing keeps exactly its own characters: nothing was inserted for it.
    assert writer.page.toPlainText() == before
    assert writer.page.picture_info() is None


def test_a_picture_that_cannot_be_read_never_reaches_the_sheet(writer, tmp_path):
    assert writer.page.insert_float(str(tmp_path / "missing.png")) is False
    assert writer.page.floats() == []


def test_an_object_lands_beside_the_writing_it_was_inserted_in(writer, square):
    block = writer.page.document().findBlock(writer.page.textCursor().position())
    top = writer.page._block_top_cm(block)
    writer.page.insert_float(square)
    placed = writer.page.float_info()
    assert placed["y_cm"] == pytest.approx(top, abs=0.05)
    # Word drops a new object inside the margin it was given, not at the edge
    # of the paper.
    assert placed["x_cm"] == pytest.approx(
        writer.page.margin_pixels / PX_PER_CM, abs=0.01)


def test_an_object_wider_than_the_sheet_is_fitted_to_it(writer, wide):
    writer.page.insert_float(wide)
    placed = writer.page.float_info()
    assert placed["width_cm"] <= writer.page.printable_width_px / PX_PER_CM + 0.01
    assert placed["height_cm"] / placed["width_cm"] == pytest.approx(300 / 1200,
                                                                    rel=1e-3)


# -- moving and stretching -------------------------------------------------- #

def test_one_edge_of_an_object_follows_the_other(writer, square):
    writer.page.insert_float(square)
    before = writer.page.float_info()
    assert writer.page.set_float_geometry(width_cm=3.0)
    after = writer.page.float_info()
    assert after["width_cm"] == pytest.approx(3.0)
    assert after["height_cm"] == pytest.approx(
        3.0 * before["height_cm"] / before["width_cm"])


def test_an_object_cannot_be_pushed_off_the_sheet(writer, square):
    writer.page.insert_float(square)
    writer.page.set_float_geometry(x_cm=40.0, y_cm=40.0)
    placed = writer.page.float_info()
    assert placed["x_cm"] + placed["width_cm"] <= writer.page.paper_width_cm() + 1e-6
    assert placed["x_cm"] >= 0.0
    assert placed["y_cm"] >= 0.0


def test_dragging_the_body_carries_the_object(writer, square, q_app):
    writer.page.insert_float(square)
    widget = writer.page.floats()[0]
    before = widget.rect_cm
    carried = QPoint(60, 40)
    _press_move_release(widget, widget.rect().center(),
                        widget.rect().center() + carried, q_app)
    after = widget.rect_cm
    wanted = writer.page.to_actual(carried.x()) / PX_PER_CM
    assert after[0] - before[0] == pytest.approx(wanted, abs=0.05)
    assert after[2] == pytest.approx(before[2])


def test_a_grip_stretches_the_object_and_holds_the_opposite_edge(writer, square,
                                                                 q_app):
    writer.page.insert_float(square)
    widget = writer.page.floats()[0]
    before = widget.rect_cm
    grip = widget._handle_rects()["right"].center()
    _press_move_release(widget, grip, grip + QPoint(50, 0), q_app)
    after = widget.rect_cm
    assert after[0] == pytest.approx(before[0], abs=1e-6)
    assert after[2] - before[2] == pytest.approx(
        writer.page.to_actual(50) / PX_PER_CM, abs=0.05)


def test_a_grip_cannot_bring_the_edges_across(writer, square, q_app):
    writer.page.insert_float(square)
    widget = writer.page.floats()[0]
    before = widget.rect_cm
    grip = widget._handle_rects()["left"].center()
    _press_move_release(widget, grip, grip + QPoint(4000, 0), q_app)
    assert widget.rect_cm[2] >= MIN_SIZE_CM - 1e-6
    assert widget.rect_cm[0] + widget.rect_cm[2] <= before[0] + before[2] + 1e-6


def test_the_zoom_does_not_change_how_far_a_drag_carries(writer, square, q_app):
    writer.page.insert_float(square)
    widget = writer.page.floats()[0]
    writer.page.set_zoom(200)
    q_app.processEvents()
    before = widget.rect_cm
    _press_move_release(widget, widget.rect().center(),
                        widget.rect().center() + QPoint(60, 0), q_app)
    assert widget.rect_cm[0] - before[0] == pytest.approx(
        writer.page.to_actual(60) / PX_PER_CM, abs=0.05)


# -- the anchor ------------------------------------------------------------- #

def test_an_object_is_left_behind_by_the_writing_above_it(writer, square, q_app):
    """New paragraphs at the top push their lines down, and the object too."""
    writer.page.insert_float(square)
    before = writer.page.float_info()["y_cm"]

    cursor = QTextCursor(writer.page.document())
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    cursor.insertText("Written above the object after it was placed.\n")
    writer.page.setTextCursor(cursor)
    _tie(q_app)

    assert writer.page.floats()[0].y_cm > before + 0.3


def test_an_object_below_the_last_line_still_hangs_on_the_last_paragraph(writer,
                                                                         square):
    writer.page.insert_float(square, y_cm=writer.page.limit_top_cm() - 1)
    widget = writer.page.floats()[0]
    assert widget.anchor is not None
    assert widget.anchor.blockNumber() == writer.page.document().blockCount() - 1


# -- the words running round it --------------------------------------------- #

def test_the_lines_step_round_an_object_on_the_left(writer, square, q_app):
    writer.page.insert_float(square)
    _tie(q_app)
    widget = writer.page.floats()[0]
    long_block = _block_formats(writer.page)[-1]
    margin_cm = writer.page.margin_pixels / PX_PER_CM
    wanted = widget.x_cm + widget.width_cm + WRAP_GAP_CM - margin_cm
    assert wanted > 0
    assert writer.page.to_actual(long_block.leftMargin()) / PX_PER_CM == \
        pytest.approx(wanted, abs=0.05)
    assert long_block.property(FLOAT_BASE_RIGHT) == pytest.approx(0.0)


def test_the_lines_step_round_an_object_on_the_right(writer, square, q_app):
    writer.page.insert_float(square)
    writer.page.set_float_geometry(
        x_cm=writer.page.paper_width_cm() - writer.page.float_info()["width_cm"]
        - 0.2)
    _tie(q_app)
    widget = writer.page.floats()[0]
    long_block = _block_formats(writer.page)[-1]
    wanted = (writer.page.paper_width_cm() - margin_cm(writer) - widget.x_cm
              + WRAP_GAP_CM)
    assert writer.page.to_actual(long_block.rightMargin()) / PX_PER_CM == \
        pytest.approx(wanted, abs=0.05)
    assert writer.page.to_actual(long_block.leftMargin()) / PX_PER_CM == \
        pytest.approx(0.0, abs=0.01)


def margin_cm(writer):
    return writer.page.margin_pixels / PX_PER_CM


def test_an_object_that_lets_the_words_under_it_leaves_the_margins_alone(writer,
                                                                        square,
                                                                        q_app):
    writer.page.insert_float(square)
    _tie(q_app)
    assert _block_formats(writer.page)[-1].leftMargin() > 0
    assert writer.page.set_float_wrap(False) is True
    _tie(q_app)
    assert _block_formats(writer.page)[-1].leftMargin() == pytest.approx(0, abs=1)


def test_a_full_width_object_sends_the_lines_below_it(writer, wide, q_app):
    writer.page.insert_float(wide, y_cm=writer.page._block_top_cm(
        writer.page.document().findBlockByNumber(1)))
    _tie(q_app)
    assert _block_formats(writer.page)[-1].topMargin() > 0


def test_a_paragraph_keeps_the_indent_it_was_written_with(writer, square, q_app):
    cursor = QTextCursor(writer.page.document())
    cursor.movePosition(QTextCursor.MoveOperation.End)
    cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
    cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
    format_ = cursor.blockFormat()
    format_.setLeftMargin(writer.page.to_display(2 * PX_PER_CM))
    cursor.setBlockFormat(format_)
    q_app.processEvents()

    writer.page.insert_float(square)
    _tie(q_app)
    # The user's 2 cm and the object's clearance are both in the margin, and
    # the object's own claim is remembered apart from the paragraph's.
    assert _block_formats(writer.page)[-1].leftMargin() > writer.page.to_display(
        2 * PX_PER_CM)

    writer.page.remove_float()
    _tie(q_app)
    assert writer.page.to_actual(
        _block_formats(writer.page)[-1].leftMargin()) / PX_PER_CM == \
        pytest.approx(2.0, abs=0.05)


def test_opening_a_document_takes_every_object_off(writer, square, q_app):
    writer.page.insert_float(square)
    _tie(q_app)
    writer.page.clear_floats()
    _tie(q_app)
    assert writer.page.floats() == []
    assert _block_formats(writer.page)[-1].leftMargin() == pytest.approx(0, abs=1)


# -- stacking and the keyboard ---------------------------------------------- #

def test_the_front_object_is_the_last_one_and_the_back_is_the_first(writer,
                                                                   square):
    writer.page.insert_float(square, x_cm=1.0)
    writer.page.insert_float(square, x_cm=8.0)
    assert writer.page.floats()[1].x_cm == pytest.approx(8.0)
    writer.page.select_float(writer.page.floats()[1])
    assert writer.page.move_float_z(-1) is True
    assert writer.page.floats()[1].x_cm == pytest.approx(1.0)


def test_an_object_at_the_front_of_the_page_has_nothing_to_pass(writer, square):
    writer.page.insert_float(square)
    assert writer.page.move_float_z(1) is False


def test_the_delete_key_takes_the_object_off(writer, square, q_app):
    writer.page.insert_float(square)
    QApplication.sendEvent(writer.page, QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key_Delete, Qt.KeyboardModifier.NoModifier))
    assert writer.page.floats() == []
    assert writer.page.float_info() is None


def test_the_escape_key_leaves_the_object_on_the_sheet(writer, square, q_app):
    writer.page.insert_float(square)
    QApplication.sendEvent(writer.page, QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key_Escape, Qt.KeyboardModifier.NoModifier))
    assert len(writer.page.floats()) == 1
    assert writer.page.float_info() is None


# -- the ribbon ------------------------------------------------------------- #

def _tabs(win):
    bar = win.ribbon.findChild(QTabBar)
    return {bar.tabText(i): bar.isTabVisible(i) for i in range(bar.count())}


def test_the_picture_tab_opens_for_an_object(writer, square):
    assert _tabs(writer)["Picture Format"] is False
    writer.page.insert_float(square)
    assert _tabs(writer)["Picture Format"] is True


def test_the_page_boxes_show_the_object_s_place(writer, square):
    writer.page.insert_float(square, x_cm=6.0, y_cm=3.0)
    assert writer.pic_x_spin.value() == pytest.approx(6.0, abs=0.01)
    assert writer.pic_y_spin.value() == pytest.approx(3.0, abs=0.01)
    assert writer.pic_x_spin.isEnabled() is True


def test_the_page_boxes_follow_a_drag(writer, square, q_app):
    writer.page.insert_float(square, x_cm=3.0, y_cm=2.6)
    widget = writer.page.floats()[0]
    centre = widget.rect().center()
    _press_move_release(widget, centre, centre + QPoint(120, 60), q_app)
    placed = writer.page.float_info()
    assert writer.pic_x_spin.value() == pytest.approx(placed["x_cm"], abs=0.01)
    assert writer.pic_y_spin.value() == pytest.approx(placed["y_cm"], abs=0.01)
    assert placed["x_cm"] > 3.0


def test_typing_a_place_in_the_box_moves_the_object(writer, square):
    writer.page.insert_float(square, x_cm=1.0, y_cm=1.0)
    writer.pic_x_spin.setValue(7.5)
    assert writer.page.float_info()["x_cm"] == pytest.approx(7.5, abs=0.01)
    assert writer.pic_y_spin.value() == pytest.approx(1.0, abs=0.01)


def test_a_picture_in_the_sentence_cannot_be_placed_by_the_page_boxes(writer,
                                                                     square):
    writer.page.insert_image(square)
    assert writer.pic_x_spin.isEnabled() is False
    assert writer._picture_wrap_toggle.isEnabled() is False
    assert writer._picture_align_buttons[0].isEnabled() is True


def test_an_object_shuts_the_boxes_that_belong_to_a_character(writer, square):
    writer.page.insert_float(square)
    assert writer._picture_align_buttons[0].isEnabled() is False
    assert writer._picture_wrap_buttons["left"].isEnabled() is False


def test_the_size_box_stretches_an_object_the_same_as_a_picture(writer, square):
    writer.page.insert_float(square)
    before = writer.page.float_info()
    writer.pic_width_spin.setValue(before["width_cm"] / 2)
    after = writer.page.float_info()
    assert after["width_cm"] == pytest.approx(before["width_cm"] / 2, abs=0.02)
    assert after["height_cm"] == pytest.approx(before["height_cm"] / 2, abs=0.02)


def test_the_text_round_it_toggle_answers_to_the_object(writer, square):
    writer.page.insert_float(square)
    writer._picture_wrap_toggle.setChecked(False)
    writer._picture_wrap_toggle.click()
    assert writer.page.float_info()["wrap"] is True
    assert writer._picture_wrap_toggle.isChecked() is True


def test_reset_size_returns_an_object_to_its_own_pixels(writer, square):
    writer.page.insert_float(square)
    writer.page.set_float_geometry(width_cm=2.0)
    writer._reset_picture_size()
    natural = QImage(square).size().width() / PX_PER_CM
    assert writer.page.float_info()["width_cm"] == pytest.approx(natural, abs=0.05)


# -- shapes ----------------------------------------------------------------- #

@pytest.mark.parametrize("shape,edges", [
    ("line", (9.0, 0.6)),
    ("arrow", (7.5, 2.5)),
    ("rectangle", (6.0, 4.0)),
])
def test_a_shape_lands_on_the_sheet_at_its_own_size(writer, shape, edges):
    writer._insert_shape(shape)
    placed = writer.page.float_info()
    assert placed is not None, "a shape is an object, not a character"
    assert placed["width_cm"] == pytest.approx(edges[0], abs=0.05)
    assert placed["height_cm"] == pytest.approx(edges[1], abs=0.05)


def test_a_shape_is_moved_about_the_page_like_a_picture(writer, q_app):
    writer._insert_shape("star")
    before = writer.page.float_info()
    assert writer.page.set_float_geometry(x_cm=2.0, y_cm=2.0)
    after = writer.page.float_info()
    assert (after["x_cm"], after["y_cm"]) == (2.0, 2.0)
    assert after["width_cm"] == pytest.approx(before["width_cm"])


# -- printing --------------------------------------------------------------- #

def _green_bounds_mm(filepath, page_mm, pixels):
    """Where the green object's ink landed on the printed sheet, in mm."""
    pdf = QPdfDocument()
    assert pdf.load(filepath) == QPdfDocument.Error.None_
    image = pdf.render(0, QSize(pixels, round(pixels * page_mm[1] / page_mm[0])))
    x_scale = page_mm[0] / image.width()
    y_scale = page_mm[1] / image.height()
    left = top = float("inf")
    right = bottom = -float("inf")
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() > 0 and color.green() > 120 and color.red() < 100:
                left, right = min(left, x * x_scale), max(right, (x + 1) * x_scale)
                top, bottom = min(top, y * y_scale), max(bottom, (y + 1) * y_scale)
    if right == -float("inf"):
        return None
    return (left, top, right, bottom)


def test_the_printer_puts_the_object_where_the_sheet_showed_it(writer, square,
                                                              tmp_path):
    writer.page.set_paper("A4")
    writer.page.insert_float(square, x_cm=4.0, y_cm=6.0, width_cm=5.0,
                             height_cm=5.0)
    path = str(tmp_path / "object.pdf")
    assert writer.export_pdf(path) is True
    bounds = _green_bounds_mm(path, (210.0, 297.0), 600)
    assert bounds is not None, "the object reached the sheet"
    left, top, right, bottom = bounds
    assert left == pytest.approx(40.0, abs=3)
    assert top == pytest.approx(60.0, abs=3)
    assert right == pytest.approx(90.0, abs=3)
    assert bottom == pytest.approx(110.0, abs=3)


def test_the_printing_list_carries_every_object_in_centimetres(writer, square):
    writer.page.insert_float(square, x_cm=1.0, y_cm=2.0, width_cm=3.0,
                             height_cm=4.0)
    [((x_cm, y_cm, wide_cm, tall_cm), path)] = writer.page.float_draw_list()
    assert (x_cm, y_cm, wide_cm, tall_cm) == (1.0, 2.0, 3.0, 4.0)
    assert path == square
