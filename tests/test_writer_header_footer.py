"""The bands WriteR's paper wears above and below its writing.

Word's *Header & Footer* is one line of paper at the top of every sheet and one
at the bottom, each carrying what the writer asks in three places, and each
sheet printing its own place in the document. These tests measure the bands
where they land -- inside the paper's margin, never over the writing -- and
follow the page numbers through to the printer, because a header that repeats
the first sheet's number on every one of them is wrong in exactly the way a
screenshot of a one-page document cannot show.
"""

import pytest
from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetricsF, QImage, QPainter, QTextCursor
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QApplication

from officer.writer.document_view import PX_PER_CM
from officer.writer.header_footer import (BAND_EDGE_CM, BAND_GAP_CM,
                                          BAND_POINT_SIZE, BAND_SIDES,
                                          PAGE_FIELD, TOTAL_FIELD,
                                          band_rects, band_texts,
                                          bands_setting, default_bands,
                                          has_bands, paint_page_bands,
                                          resolve_fields)
from officer.writer.header_footer_dialog import HeaderFooterDialog
from officer.writer.window import WriteRWindow


@pytest.fixture
def sheet(q_app):
    """A laid-out WriteR window with real writing on it."""
    win = WriteRWindow()
    win.page.setPlainText("A sheet with bands.\n" + "filling words " * 120)
    win.resize(1200, 900)
    win.show()
    q_app.processEvents()
    return win


# -- measuring a band --------------------------------------------------------- #

def _dark(image, step=2, crop=None, below=110):
    """How much of *image* is ink."""
    left, top, right, bottom = crop or (0, 0, image.width(), image.height())
    found = sampled = 0
    for y in range(int(top), int(bottom), step):
        for x in range(int(left), int(right), step):
            seen = QColor(image.pixel(x, y)).getRgb()
            if max(seen[0], seen[1], seen[2]) < below:
                found += 1
            sampled += 1
    return found / max(1, sampled)


def _rect_of(rect):
    """A ``QRectF`` as the integer crop a measurement wants."""
    return (rect.left(), rect.top(), rect.right() + 1, rect.bottom() + 1)


def _third(rect, which):
    """One of a band's three places, as a crop of its own."""
    left, top, right, bottom = _rect_of(rect)
    column = right - left
    return {"left": (left, top, left + column / 3, bottom),
            "centre": (left + column / 3, top, left + 2 * column / 3, bottom),
            "right": (left + 2 * column / 3, top, right, bottom)}[which]


def _diff(first, second, crop):
    """How much of two sheets' crops disagrees, as a share of the pixels."""
    box = QRect(int(crop[0]), int(crop[1]),
                int(crop[2] - crop[0]), int(crop[3] - crop[1]))
    a = first.copy(box)
    b = second.copy(box)
    if a.size() != b.size():
        return 1.0
    unlike = sampled = 0
    for y in range(a.height()):
        for x in range(a.width()):
            sampled += 1
            if a.pixel(x, y) != b.pixel(x, y):
                unlike += 1
    return unlike / max(1, sampled)


def _bands(sheet, page=1, total=1, **given):
    """The page's own bands, painted alone onto one sheet of paper.

    Returns the sheet and the two rects the bands were asked to fill, so a test
    can look where the words belong without measuring the painter's arithmetic
    back into existence.
    """
    sheet.page.set_header_footer(**given)
    zoom = sheet.page._zoom_factor
    box = sheet.page.sheet_box(0)
    image = QImage(int(box.width()), int(box.height()),
                   QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    font = sheet.page._band_font()
    margin_px = sheet.page._margin_px * zoom
    painter = QPainter(image)
    drew = paint_page_bands(painter, sheet.page.header_footer(), box, page,
                            total, font, margin_px, PX_PER_CM * zoom)
    painter.end()
    header, footer = band_rects(box, margin_px, QFontMetricsF(font).height(),
                                BAND_EDGE_CM * PX_PER_CM * zoom,
                                BAND_GAP_CM * PX_PER_CM * zoom)
    return image, (header, footer), drew


# -- what the bands are made of ----------------------------------------------- #

def test_a_fresh_document_has_nothing_in_either_band(sheet):
    assert sheet.page.header_footer() == default_bands()
    assert has_bands(default_bands()) is False


def test_a_band_of_only_blanks_has_nothing_to_say():
    bands = default_bands()
    bands["footer"]["centre"] = "   "
    assert has_bands(bands) is False


def test_what_a_band_leaves_out_arrives_as_it_came():
    odd = bands_setting({"header": {"left": "Title"}, "footer": "nonsense",
                         "show_first_page": False, "side": "anywhere"})
    assert odd["header"] == {"left": "Title", "centre": "", "right": ""}
    assert odd["footer"] == {side: "" for side in BAND_SIDES}
    assert odd["show_first_page"] is False


def test_a_sheet_knows_its_own_place_and_the_documents_length():
    assert resolve_fields("Page {PAGE} of {PAGES}", 3, 12) == "Page 3 of 12"
    assert resolve_fields("No fields here", 1, 1) == "No fields here"
    texts = band_texts({"footer": {"right": "{PAGE}"}}, "footer", 2, 7)
    assert texts == {"left": "", "centre": "", "right": "2"}


def test_the_two_fields_are_the_only_ones_a_band_answers_to():
    assert PAGE_FIELD == "{PAGE}" and TOTAL_FIELD == "{PAGES}"


# -- where the bands lie on the paper ----------------------------------------- #

def test_a_band_sits_in_the_papers_own_margin(sheet):
    image, (header, footer), drew = _bands(
        sheet, header={"centre": "A Header"}, footer={"centre": "A Footer"})
    assert drew is True
    margin = sheet.page._margin_px
    box = sheet.page.sheet_box(0)
    assert header.top() >= box.top()
    assert header.bottom() <= margin, "the header stands in the writing"
    assert footer.top() >= margin, "the footer stands in the writing"
    assert footer.bottom() <= box.bottom()
    assert _dark(image, crop=_rect_of(header)) > 0.002, "no header was written"
    assert _dark(image, crop=_rect_of(footer)) > 0.002, "no footer was written"
    # The column itself, which the bands must never touch.
    column = (margin, margin, box.width() - margin, box.height() - margin)
    assert _dark(image, crop=column) == 0.0, "a band is over the writing"


def test_a_band_keeps_words_out_of_the_paper_it_cannot_use(sheet):
    """A sheet with narrow margins pulls its bands in rather than print off it."""
    box = QRectF(0, 0, 816, 1056)
    line = 20.0
    edge = BAND_EDGE_CM * PX_PER_CM
    wide, tall = band_rects(box, 96, line, edge, BAND_GAP_CM * PX_PER_CM)
    assert wide.top() == edge and tall.bottom() == box.bottom() - edge
    thin, thin_footer = band_rects(box, 24, line, edge, BAND_GAP_CM * PX_PER_CM)
    assert thin.top() >= 0, "the band left the paper altogether"
    assert thin.bottom() <= 24, "a thin margin's band stands in the writing"
    assert thin_footer.top() >= box.bottom() - 24


# -- what the page remembers -------------------------------------------------- #

def test_a_written_band_is_kept_whole(sheet):
    sheet.page.set_header_footer(header={"left": "OfficeR", "right": "Amlan"},
                                 footer={"centre": "Page {PAGE} of {PAGES}"},
                                 show_first_page=False)
    kept = sheet.page.header_footer()
    assert kept["header"]["left"] == "OfficeR"
    assert kept["header"]["right"] == "Amlan"
    assert kept["header"]["centre"] == ""
    assert kept["footer"]["centre"] == "Page {PAGE} of {PAGES}"
    assert kept["show_first_page"] is False


def test_writing_one_band_leaves_the_other_to_say_what_it_says(sheet):
    """Word's dialog sends both; a caller that only cares about one keeps the other."""
    sheet.page.set_header_footer(header={"centre": "Chapter One"})
    sheet.page.set_header_footer(footer={"right": "Amlan"})
    kept = sheet.page.header_footer()
    assert kept["header"]["centre"] == "Chapter One"
    assert kept["footer"]["right"] == "Amlan"


def test_an_empty_band_silences_only_itself(sheet):
    sheet.page.set_header_footer(header={"centre": "Chapter One"},
                                 footer={"right": "Amlan"})
    sheet.page.set_header_footer(footer={"left": "", "centre": "",
                                         "right": ""})
    kept = sheet.page.header_footer()
    assert kept["footer"] == {side: "" for side in BAND_SIDES}
    assert kept["header"]["centre"] == "Chapter One"


def test_a_word_written_into_a_band_reaches_the_paper(sheet):
    sheet.page.set_header_footer(header={"left": "OfficeR"})
    image, (header, _), _ = _bands(sheet)
    assert _dark(image, crop=_third(header, "left")) > 0.002
    assert _dark(image, crop=_third(header, "centre")) == 0.0
    assert _dark(image, crop=_third(header, "right")) == 0.0


def test_each_place_in_a_band_keeps_its_own_side_of_the_paper(sheet):
    sheet.page.set_header_footer(
        header={"left": "Title", "right": "Amlan"},
        footer={"centre": "Chapter"})
    image, (header, footer), _ = _bands(sheet)
    assert _dark(image, crop=_third(header, "left")) > 0.002
    assert _dark(image, crop=_third(header, "right")) > 0.002
    assert _dark(image, crop=_third(header, "centre")) == 0.0, \
        "a band's words drifted into the middle"
    assert _dark(image, crop=_third(footer, "centre")) > 0.002
    assert _dark(image, crop=_third(footer, "left")) == 0.0
    assert _dark(image, crop=_third(footer, "right")) == 0.0


def test_removing_both_bands_leaves_the_paper_plain(sheet):
    sheet.page.set_header_footer(header={"left": "OfficeR"},
                                 footer={"left": "2026"})
    sheet.page.remove_header_footer()
    assert sheet.page.header_footer() == default_bands()


def test_writing_a_band_marks_the_document_unsaved(sheet):
    sheet.page.document().setModified(False)
    sheet.page.set_header_footer(footer={"centre": "Page {PAGE}"})
    assert sheet.page.document().isModified() is True


# -- the numbers a band carries ----------------------------------------------- #

def test_each_sheet_prints_its_own_number_and_the_same_length(sheet):
    one, (_, footer1), _ = _bands(
        sheet, page=1, total=3, footer={"centre": "Page {PAGE} of {PAGES}"})
    two, (_, footer2), _ = _bands(
        sheet, page=2, total=3, footer={"centre": "Page {PAGE} of {PAGES}"})
    three, (_, _), _ = _bands(
        sheet, page=3, total=3, footer={"centre": "Page {PAGE} of {PAGES}"})
    assert _diff(one, two, _rect_of(footer1)) > 0.001, \
        "two sheets printed the same number"
    assert _diff(two, three, _rect_of(footer2)) > 0.001
    assert _diff(one, two, _rect_of(footer1)) < 0.5, \
        "the whole band changed for one digit"


def test_a_band_can_carry_both_numbers_apart(sheet):
    """One digit is a small thing to look for: measure every pixel."""
    one, (_, footer), _ = _bands(sheet, page=1, total=9,
                                 footer={"left": "{PAGE}",
                                         "right": "{PAGES}"})
    assert _dark(one, step=1, crop=_third(footer, "left")) > 0.0
    assert _dark(one, step=1, crop=_third(footer, "right")) > 0.0
    assert _dark(one, step=1, crop=_third(footer, "centre")) == 0.0


def test_the_first_sheet_can_be_left_plain(sheet):
    _, (_, _), drew = _bands(sheet, page=1, total=2, show_first_page=False,
                             header={"centre": "Chapter One"})
    assert drew is False, "the first sheet wore a band it was told not to"
    plain, (header, _), _ = _bands(sheet, page=1, total=2,
                                   show_first_page=False,
                                   header={"centre": "Chapter One"})
    assert _dark(plain, crop=_rect_of(header)) == 0.0
    dressed, (header2, _), drew2 = _bands(sheet, page=2, total=2,
                                          show_first_page=False,
                                          header={"centre": "Chapter One"})
    assert drew2 is True
    assert _dark(dressed, crop=_rect_of(header2)) > 0.002


def test_a_shown_first_page_wears_its_bands_like_every_other_sheet(sheet):
    image, (header, _), drew = _bands(sheet, page=1, total=2,
                                      show_first_page=True,
                                      header={"centre": "Chapter One"})
    assert drew is True
    assert _dark(image, crop=_rect_of(header)) > 0.002


def test_the_page_counts_its_own_sheets_the_way_the_printer_does(sheet):
    assert sheet.page._sheets_written() == 1
    sheet.page.setPlainText("A long document.\n" + "filling words " * 900)
    assert sheet.page._sheets_written() > 1


def test_the_status_bar_and_the_band_count_the_same_sheets(sheet):
    """Two numbers on the same screen must not disagree about one document."""
    sheet.page.setPlainText("A long document.\n" + "filling words " * 620)
    QApplication.instance().processEvents()
    assert sheet.page.page_count() == sheet.page._sheets_written() > 1
    start = sheet.page.textCursor()
    start.movePosition(QTextCursor.MoveOperation.Start)
    sheet.page.setTextCursor(start)
    assert sheet.page.current_page_number() == 1
    end = sheet.page.textCursor()
    end.movePosition(QTextCursor.MoveOperation.End)
    sheet.page.setTextCursor(end)
    assert sheet.page.current_page_number() == sheet.page.page_count()


# -- every sheet, at any zoom ------------------------------------------------- #

def test_sheets_beyond_the_first_wear_their_bands_too(sheet):
    sheet.page.set_header_footer(header={"centre": "Chapter One"},
                                 footer={"centre": "Page {PAGE}"})
    sheet.page.set_zoom(50)
    QApplication.instance().processEvents()
    pages = sheet.page._visible_sheets()
    assert pages >= 2, "the screen does not show two sheets at this size"
    zoom = sheet.page._zoom_factor
    tall = sheet.page._base_height * zoom
    image = QImage(int(sheet.page._base_width * zoom), int(tall * pages),
                   QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    font = sheet.page._band_font()
    for page in range(pages):
        paint_page_bands(painter, sheet.page.header_footer(),
                         sheet.page.sheet_box(page), page + 1, pages, font,
                         sheet.page._margin_px * zoom, PX_PER_CM * zoom)
    painter.end()
    for page in range(pages):
        band = (0, page * tall + 4, image.width(), page * tall + 40)
        assert _dark(image, step=1, crop=band) > 0.0, \
            f"sheet {page + 1} has no header on it"


def test_a_band_grows_with_the_zoom_it_is_read_at(sheet):
    one, (header, _), _ = _bands(sheet, header={"centre": "Chapter One"})
    sheet.page.set_zoom(200)
    QApplication.instance().processEvents()
    scaled, (big, _), _ = _bands(sheet, header={"centre": "Chapter One"})
    assert abs(big.height() - header.height() * 2) < 2, \
        "the band did not grow with the sheet"
    assert abs(big.top() - header.top() * 2) < 2
    assert _dark(scaled, crop=_rect_of(big)) > 0.002
    assert _dark(one, crop=_rect_of(header)) > 0.002


def test_a_band_is_set_in_the_documents_own_face_at_words_size(sheet):
    font = sheet.page._band_font()
    assert round(font.pixelSize()) == round(BAND_POINT_SIZE * 96 / 72)
    assert font.family() == sheet.page.document().defaultFont().family()


# -- the ribbon and the dialog ------------------------------------------------ #

def _band_menu(win):
    for menu in win._ribbon_menus:
        if menu.objectName() == "header-footer":
            return menu
    raise AssertionError("Insert has no Header & Footer menu")


def test_the_ribbon_offers_to_edit_each_band_and_to_take_it_off(sheet):
    named = [action.text() for action in _band_menu(sheet).actions()
             if action.text()]
    assert "Edit Header and Footer…" in named
    assert "Remove the header" in named and "Remove the footer" in named


def test_taking_one_band_off_leaves_the_other_alone(sheet):
    sheet.page.set_header_footer(header={"centre": "Chapter One"},
                                 footer={"right": "Amlan"})
    menu = _band_menu(sheet)
    next(a for a in menu.actions() if a.text() == "Remove the footer").trigger()
    kept = sheet.page.header_footer()
    assert kept["footer"] == {side: "" for side in BAND_SIDES}
    assert kept["header"]["centre"] == "Chapter One"


def test_the_dialog_answers_with_what_the_bands_already_carry(sheet):
    sheet.page.set_header_footer(header={"left": "OfficeR"},
                                 footer={"centre": "Page {PAGE} of {PAGES}"},
                                 show_first_page=False)
    dialog = HeaderFooterDialog(sheet.page.header_footer(), parent=sheet)
    assert dialog.bands() == sheet.page.header_footer()
    assert dialog._fields["header"]["left"].text() == "OfficeR"
    assert dialog._fields["footer"]["centre"].text() == "Page {PAGE} of {PAGES}"
    assert dialog.first_page.isChecked() is False
    assert dialog.description() == (
        "Header and footer on every sheet -- 1 page number field(s). "
        "The first sheet keeps them empty.")


def test_an_empty_dialog_says_the_sheets_stay_plain(sheet):
    dialog = HeaderFooterDialog(parent=sheet)
    assert dialog.bands() == default_bands()
    assert dialog.description() == (
        "No header and no footer: the sheets keep their margins empty.")


def test_the_page_number_buttons_write_into_the_band_being_edited(q_app):
    dialog = HeaderFooterDialog()
    dialog.show()
    q_app.processEvents()
    dialog._fields["footer"]["centre"].setFocus()
    q_app.processEvents()
    dialog._fields["footer"]["centre"].setText("Page ")
    dialog.page_number.click()
    dialog.page_count.click()
    assert dialog._fields["footer"]["centre"].text() == \
        "Page {PAGE}{PAGES}"
    assert dialog.bands()["footer"]["centre"] == "Page {PAGE}{PAGES}"
    dialog._fields["header"]["left"].setFocus()
    q_app.processEvents()
    dialog.page_number.click()
    assert dialog.bands()["header"]["left"] == PAGE_FIELD, \
        "the field went to the box that was not being edited"
    assert dialog.bands()["footer"]["centre"] == "Page {PAGE}{PAGES}"


def test_a_band_written_in_the_dialog_reaches_the_sheet(sheet):
    dialog = HeaderFooterDialog({"header": {"right": "Amlan"},
                                 "footer": {"centre": "Page {PAGE}"}})
    sheet.page.set_header_footer(**dialog.bands())
    kept = sheet.page.header_footer()
    assert kept["header"]["right"] == "Amlan"
    assert kept["footer"]["centre"] == "Page {PAGE}"
    assert kept["show_first_page"] is True


def test_a_new_document_sheds_its_bands(sheet):
    sheet.page.set_header_footer(header={"left": "OfficeR"},
                                 show_first_page=False)
    sheet.on_new()
    assert sheet.page.header_footer() == default_bands()


# -- what comes out of the printer -------------------------------------------- #

def _printed(win, tmp_path, name="page.pdf", size=QSize(1200, 1554), page=0):
    """One printed sheet, on the white paper a viewer shows it on."""
    pdf = str(tmp_path / name)
    assert win.export_pdf(pdf) is True
    document = QPdfDocument()
    document.load(pdf)
    assert document.pageCount() > page
    rendered = document.render(page, size)
    image = QImage(rendered.size(), QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    painter.drawImage(0, 0, rendered)
    painter.end()
    return image, document.pageCount()


def _margin_band(image, top, bottom):
    """A strip of the paper's own margin, where only a band can put ink."""
    return (0, top, image.width(), bottom)


def test_a_printed_sheet_wears_its_bands_in_the_margin(sheet, tmp_path):
    sheet.page.set_header_footer(header={"left": "OfficeR", "right": "Amlan"},
                                 footer={"centre": "Page {PAGE} of {PAGES}"})
    image, _ = _printed(sheet, tmp_path)
    tall = image.height()
    header_strip = _margin_band(image, int(tall * 0.03), int(tall * 0.065))
    footer_strip = _margin_band(image, int(tall * 0.925), int(tall * 0.97))
    assert _dark(image, crop=header_strip) > 0.001, "no printed header"
    assert _dark(image, crop=footer_strip) > 0.001, "no printed footer"
    # The writing's own column, which the bands must leave to the words.
    between = _margin_band(image, int(tall * 0.10), int(tall * 0.88))
    above = _dark(image, crop=_margin_band(image, 0, int(tall * 0.03)))
    assert above == 0.0, "a band printed on the paper's own edge"
    assert _dark(image, crop=between) > 0.002, "the sheet printed no writing"


def test_a_printed_header_keeps_its_two_ends_apart(sheet, tmp_path):
    sheet.page.set_header_footer(header={"left": "Title", "right": "Amlan"})
    image, _ = _printed(sheet, tmp_path)
    wide, tall = image.width(), image.height()
    left = _dark(image, crop=(0, int(tall * 0.03), wide * 0.32,
                              int(tall * 0.065)))
    middle = _dark(image, crop=(wide * 0.40, int(tall * 0.03), wide * 0.60,
                                int(tall * 0.065)))
    right = _dark(image, crop=(wide * 0.68, int(tall * 0.03), wide,
                               int(tall * 0.065)))
    assert left > 0.0 and right > 0.0
    assert middle == 0.0, "the header's two ends ran into one another"


def test_each_printed_sheet_carries_its_own_number(sheet, tmp_path):
    sheet.page.setPlainText("A long document.\n" + "filling words " * 900)
    sheet.page.set_header_footer(header={"centre": "Chapter One"},
                                 footer={"centre": "Page {PAGE} of {PAGES}"})
    first, pages = _printed(sheet, tmp_path, name="first.pdf")
    assert pages > 1, "the document does not reach a second sheet"
    assert sheet.page._sheets_written() == pages, \
        "the screen and the printer disagree on how long the document is"
    second, _ = _printed(sheet, tmp_path, name="second.pdf", page=1)
    wide, tall = first.width(), first.height()
    band = (int(wide * 0.35), int(tall * 0.925), int(wide * 0.65),
            int(tall * 0.97))
    assert _diff(first, second, band) > 0.001, \
        "two printed sheets carry the same page number"
    header_band = (int(wide * 0.30), int(tall * 0.03), int(wide * 0.70),
                   int(tall * 0.065))
    assert _diff(first, second, header_band) == 0.0, \
        "the same header came out differently on two sheets"


def test_a_printed_first_sheet_can_be_left_plain(sheet, tmp_path):
    sheet.page.setPlainText("A long document.\n" + "filling words " * 900)
    sheet.page.set_header_footer(header={"centre": "Chapter One"},
                                 show_first_page=False)
    first, pages = _printed(sheet, tmp_path, name="plain.pdf")
    assert pages > 1
    tall = first.height()
    strip = (0, int(tall * 0.02), first.width(), int(tall * 0.07))
    assert _dark(first, crop=strip) == 0.0, "the first sheet wore a band"
    second, _ = _printed(sheet, tmp_path, name="worn.pdf", page=1)
    assert _dark(second, crop=strip) > 0.001, \
        "the second sheet lost the band the first was spared"


def test_a_plain_sheet_prints_no_bands_of_its_own(sheet, tmp_path):
    image, _ = _printed(sheet, tmp_path)
    tall = image.height()
    assert _dark(image, crop=_margin_band(image, 0, int(tall * 0.08))) == 0.0
    assert _dark(image,
                 crop=_margin_band(image, int(tall * 0.92), tall)) == 0.0
