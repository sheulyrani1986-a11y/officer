"""The lines and designs WriteR's sheets wear along their margins.

Word draws a page border outside the writing, on the paper's own margin, and
carries it down every sheet of a long document. These tests measure that ring
of ink -- where it falls on the sheet, whether the style chosen is the style
painted, and whether it reaches the printer -- rather than trusting that a
dialog which opens is a dialog that does anything.
"""

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPdf import QPdfDocument

from officer.writer.document_view import PX_PER_CM
from officer.writer.page_border import (BORDER_SPACE_CM, COLOURS,
                                        DEFAULT_COLOUR, DEFAULT_WIDTH_PT,
                                        PAGE_BORDERS, STYLE_ORDER)
from officer.writer.page_border_dialog import PageBorderDialog
from officer.writer.window import WriteRWindow

MM_TO_PT = 72.0 / 25.4


@pytest.fixture
def sheet(q_app):
    """A laid-out WriteR window: Qt only measures a page it has shown."""
    win = WriteRWindow()
    win.page.setPlainText("A sheet with a border.\n" + "filling words " * 120)
    win.resize(1200, 900)
    win.show()
    q_app.processEvents()
    return win


def _painted(sheet, style, width_pt=2.0):
    """The border as the page draws it, alone on a blank sheet of pixels."""
    sheet.page.set_page_border(style=style, width_pt=width_pt)
    zoom = sheet.page._zoom_factor
    image = QImage(int(sheet.page._base_width * zoom),
                   int(sheet.page._base_height * zoom),
                   QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    sheet.page.paint_page_borders(painter)
    painter.end()
    return image


def _ink(image):
    """Every dark-enough pixel on the sheet: the border, wherever it fell."""
    return [(x, y) for y in range(image.height()) for x in range(image.width())
            if image.pixel(x, y) & 0x00FFFFFF != 0x00FFFFFF]


def _columns(image):
    return [x for x, _ in _ink(image)]


# -- what the page remembers -------------------------------------------------- #

def test_a_fresh_sheet_wears_nothing(sheet):
    assert sheet.page.page_border() == {"style": "none", "colour": DEFAULT_COLOUR,
                                        "width_pt": DEFAULT_WIDTH_PT}
    assert _ink(_painted(sheet, "none")) == []


def test_the_border_remembers_style_colour_and_weight(sheet):
    sheet.page.set_page_border(style="double", colour=COLOURS["Red"],
                               width_pt=4.0)
    assert sheet.page.page_border() == {"style": "double",
                                        "colour": COLOURS["Red"],
                                        "width_pt": 4.0}


def test_asking_for_only_a_colour_keeps_the_line(sheet):
    """Word's dialog sends the whole set; a caller may change one thing."""
    sheet.page.set_page_border(style="dashed", width_pt=3.0)
    sheet.page.set_page_border(colour=COLOURS["Blue"])
    kept = sheet.page.page_border()
    assert (kept["style"], kept["width_pt"]) == ("dashed", 3.0)
    assert kept["colour"] == COLOURS["Blue"]


def test_dressing_the_sheet_marks_it_unsaved(sheet):
    sheet.page.document().setModified(False)
    sheet.page.set_page_border(style="box")
    assert sheet.page.document().isModified() is True


# -- what the page paints ----------------------------------------------------- #

@pytest.mark.parametrize("style", [key for key in STYLE_ORDER if key != "none"])
def test_every_border_on_offer_draws_something(sheet, style):
    """A style in the menu that paints nothing is a dead button by another name."""
    image = _painted(sheet, style)
    assert image.pixelColor(0, 0).name() == "#ffffff"
    assert len(_ink(image)) > 50


def test_the_border_rings_the_writing_not_the_edge_of_the_paper(sheet):
    page = sheet.page
    margin = page.margin_pixels * page._zoom_factor
    space = page.to_display(BORDER_SPACE_CM * PX_PER_CM)
    left = margin - space
    columns = _columns(_painted(sheet, "box"))
    assert min(columns) == pytest.approx(left, abs=2.0)
    right = left + page.printable_width_px * page._zoom_factor + 2 * space
    assert max(columns) == pytest.approx(right, abs=2.0)
    # The ring stands in the paper's margin, so it never covers the column.
    assert min(columns) < margin and max(columns) > margin + page.printable_width_px


def test_a_heavier_border_weighs_more_on_the_sheet(sheet):
    thin = len(_ink(_painted(sheet, "box", width_pt=1.0)))
    thick = len(_ink(_painted(sheet, "box", width_pt=6.0)))
    assert thick > thin * 2


def test_the_shadow_falls_outside_the_line_it_shades(sheet):
    """Word's shadow tints the paper beside the rule, never the page inside it."""
    image = _painted(sheet, "shadow", width_pt=4.0)
    page = sheet.page
    inset = page.margin_pixels * page._zoom_factor - page.to_display(
        BORDER_SPACE_CM * PX_PER_CM)
    centre = image.pixelColor(int(image.width() / 2), int(image.height() / 2))
    assert centre.name() == "#ffffff"
    fringe = image.pixelColor(int(inset + page.printable_width_px * page._zoom_factor
                                 + 2 * page.to_display(BORDER_SPACE_CM * PX_PER_CM)
                                 + 6), int(image.height() / 2))
    assert fringe.name() != "#ffffff"


def test_the_border_follows_the_sheet_when_the_paper_changes(sheet):
    """A3 is wider than Letter: the ring has to open with it, not stay put."""
    narrow = _columns(_painted(sheet, "box"))
    sheet.page.set_paper("A3")
    sheet.page.set_page_border(style="box")
    wide = _columns(_painted(sheet, "box"))
    assert max(wide) > max(narrow)


# -- the ribbon and the dialog ------------------------------------------------ #

def test_the_ribbon_lists_word_s_borders_and_choosing_one_dresses_the_sheet(sheet):
    menu = next(menu for menu in sheet._ribbon_menus
                if menu.objectName() == "page-border")
    captions = [action.text() for action in menu.actions() if action.text()]
    assert captions[:6] == [PAGE_BORDERS[key][0] for key in
                            ("none", "box", "shadow", "double", "dashed", "dotted")]
    assert "Page Borders and Designs…" in captions
    menu.actions()[1].trigger()
    assert sheet.page.page_border()["style"] == "box"


def test_the_dialog_answers_with_the_border_that_was_picked(sheet):
    dialog = PageBorderDialog(sheet.page.page_border(), sheet)
    dialog.styles.setCurrentRow(STYLE_ORDER.index("hearts"))
    dialog.colour_box.setCurrentIndex(dialog.colour_box.findData(COLOURS["Green"]))
    dialog.width_box.setValue(3.5)
    assert dialog.border() == {"style": "hearts", "colour": COLOURS["Green"],
                               "width_pt": 3.5}
    sheet.page.set_page_border(**dialog.border())
    assert sheet.page.page_border() == dialog.border()


def test_the_dialog_opens_on_what_the_sheet_already_wears(sheet):
    sheet.page.set_page_border(style="sunken", colour=COLOURS["Purple"],
                               width_pt=2.5)
    dialog = PageBorderDialog(sheet.page.page_border(), sheet)
    assert dialog.styles.currentRow() == STYLE_ORDER.index("sunken")
    assert dialog.colour_box.currentData() == COLOURS["Purple"]
    assert dialog.width_box.value() == pytest.approx(2.5)


def test_the_dialog_offers_every_border_it_paints(sheet):
    dialog = PageBorderDialog(parent=sheet)
    keys = [dialog.styles.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(dialog.styles.count())]
    assert keys == list(STYLE_ORDER)


# -- the printed sheet -------------------------------------------------------- #

def _non_white(pdf_path, pixels=500):
    """Ink on the printed sheet.

    Qt renders a PDF page with no paper behind it, so a pixel only counts as
    ink where the file actually puts something down.
    """
    document = QPdfDocument()
    assert document.load(pdf_path) == QPdfDocument.Error.None_
    size = document.pagePointSize(0)
    image = document.render(0, QSize(pixels, round(pixels * size.height() / size.width())))
    ink = 0
    for y in range(image.height()):
        for x in range(image.width()):
            colour = image.pixelColor(x, y)
            if colour.alpha() > 0 and (colour.red() < 250 or colour.green() < 250
                                       or colour.blue() < 250):
                ink += 1
    return ink


def test_a_bordered_sheet_prints_wider_ink_than_a_plain_one(sheet, tmp_path):
    sheet.page.set_paper("A4")
    sheet.page.setPlainText("Only a line of writing, so the ink is the border.")
    plain = str(tmp_path / "plain.pdf")
    assert sheet.export_pdf(plain) is True
    plain_ink = _non_white(plain)

    sheet.page.set_page_border(style="box", colour=COLOURS["Red"], width_pt=6.0)
    dressed = str(tmp_path / "dressed.pdf")
    assert sheet.export_pdf(dressed) is True
    assert _non_white(dressed) > plain_ink + 500


def test_the_printed_border_reaches_the_paper_s_margin(sheet, tmp_path):
    """The ring must fall on the paper's own margin, outside the writing."""
    sheet.page.set_paper("A4")
    sheet.page.setPlainText("A short note.")
    sheet.page.set_page_border(style="box", colour=COLOURS["Blue"], width_pt=8.0)
    path = str(tmp_path / "ring.pdf")
    assert sheet.export_pdf(path) is True
    document = QPdfDocument()
    document.load(path)
    size = document.pagePointSize(0)
    image = document.render(0, QSize(600, round(600 * size.height() / size.width())))
    blue = [(x, y) for y in range(image.height()) for x in range(image.width())
            if image.pixelColor(x, y).blue() > 120
            and image.pixelColor(x, y).red() < 100]
    assert blue, "no blue border reached the sheet"
    left_mm = min(x for x, _ in blue) / image.width() * (size.width() / MM_TO_PT)
    right_mm = max(x for x, _ in blue) / image.width() * (size.width() / MM_TO_PT)
    margin_mm = sheet.page.margin_pixels * 10.0 / PX_PER_CM
    assert 15.0 < left_mm < margin_mm, (left_mm, margin_mm)
    assert 210.0 - margin_mm < right_mm < 195.0, right_mm
