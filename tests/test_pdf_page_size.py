"""Every app must hand out a PDF cut to the page it was set to, not to A4."""

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtPdf import QPdfDocument

from officer.presentr.slide_deck import ShapeObject, TextObject
from officer.presentr.window import PresentRWindow
from officer.rsheet.window import RSheetWindow
from officer.writer.window import WriteRWindow

POINTS_TO_MM = 25.4 / 72


def _pages_mm(filepath: str) -> list:
    """Each sheet of the PDF, in millimetres, as a reader's printer would report it."""
    pdf = QPdfDocument()
    assert pdf.load(filepath) == QPdfDocument.Error.None_, f"{filepath} did not open"
    return [(round(pdf.pagePointSize(i).width() * POINTS_TO_MM, 1),
             round(pdf.pagePointSize(i).height() * POINTS_TO_MM, 1))
            for i in range(pdf.pageCount())]


def _ink(filepath: str, page: int = 0) -> float:
    """The share of a printed sheet that carries ink, measured off the PDF.

    Untouched paper comes back transparent rather than white, so a pixel only
    counts as ink when the renderer actually laid something down.
    """
    pdf = QPdfDocument()
    assert pdf.load(filepath) == QPdfDocument.Error.None_
    image = pdf.render(page, QSize(400, 300))
    assert not image.isNull()
    inked = 0
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() > 0 and color.lightness() < 245:
                inked += 1
    return inked / (image.width() * image.height())


@pytest.fixture
def writer(q_app):
    win = WriteRWindow()
    win.resize(1200, 900)
    win.show()
    q_app.processEvents()
    win.page.setPlainText("A document that is asked to be printed on its own paper.")
    return win


@pytest.fixture
def sheet(q_app):
    win = RSheetWindow()
    win.resize(1200, 900)
    win.show()
    q_app.processEvents()
    return win


@pytest.fixture
def deck(q_app):
    win = PresentRWindow()
    win.resize(1200, 900)
    win.show()
    q_app.processEvents()
    return win


# -- WriteR -------------------------------------------------------------------- #

@pytest.mark.parametrize("paper, mm", [("A4", (210.0, 297.0)),
                                       ("Letter", (215.9, 279.4)),
                                       ("A6", (105.0, 148.0)),
                                       ("C5 Envelope", (162.0, 229.0))])
def test_write_prints_on_the_sheet_the_size_box_chose(writer, tmp_path, paper, mm):
    writer.page.set_paper(paper)
    path = str(tmp_path / f"{paper.replace(' ', '')}.pdf")
    assert writer.export_pdf(path) is True
    assert _pages_mm(path)[0] == pytest.approx(mm, abs=1.5)


def test_a_landscape_sheet_comes_out_landscape(writer, tmp_path):
    writer.page.set_paper("A4")
    writer.page.set_landscape(True)
    path = str(tmp_path / "wide.pdf")
    assert writer.export_pdf(path) is True
    wide, tall = _pages_mm(path)[0]
    assert wide > tall


def test_a_document_prints_at_its_real_sizes_however_the_view_is_zoomed(writer, tmp_path):
    """Zoom is a display state: the sheet must not come out 175% bigger."""
    writer.page.set_paper("A4")
    plain = str(tmp_path / "plain.pdf")
    assert writer.export_pdf(plain) is True
    before = writer.page.document().size().height()

    writer.page.set_zoom(175)
    zoomed = str(tmp_path / "zoomed.pdf")
    assert writer.export_pdf(zoomed) is True
    assert _pages_mm(zoomed) == _pages_mm(plain)
    assert writer.page.document().size().height() == pytest.approx(
        before * 1.75, abs=6), "the view is still the zoomed one"


def test_a_written_page_carries_its_words(writer, tmp_path):
    """A PDF of the right size that is empty inside is still a broken export."""
    writer.page.set_paper("A4")
    path = str(tmp_path / "words.pdf")
    assert writer.export_pdf(path) is True
    assert _ink(path) > 0.0, "the words reached the sheet"


# -- RSheet --------------------------------------------------------------------- #

@pytest.mark.parametrize("paper, mm", [("A4", (210.0, 297.0)),
                                       ("A3", (297.0, 420.0)),
                                       ("A5", (148.0, 210.0)),
                                       ("Letter", (216.0, 279.0)),
                                       ("Legal", (216.0, 356.0))])
def test_a_sheet_prints_on_the_paper_it_lists(sheet, tmp_path, paper, mm):
    sheet._set_paper_size(paper)
    sheet._set_orientation(False)
    path = str(tmp_path / f"{paper}.pdf")
    assert sheet.export_pdf(path) is True
    assert _pages_mm(path)[0] == pytest.approx(mm, abs=1.5)


def test_a_landscape_sheet_prints_landscape(sheet, tmp_path):
    sheet._set_paper_size("A4")
    sheet._set_orientation(True)
    path = str(tmp_path / "sheet_wide.pdf")
    assert sheet.export_pdf(path) is True
    wide, tall = _pages_mm(path)[0]
    assert wide == pytest.approx(297.0, abs=1.5)
    assert tall == pytest.approx(210.0, abs=1.5)


def _fill(sheet, cells: dict) -> None:
    model = sheet.sheet_widget.grid.model()
    for (row, column), value in cells.items():
        model.setData(model.index(row, column), value, Qt.ItemDataRole.EditRole)


def test_a_sheet_prints_the_cells_that_were_typed(sheet, tmp_path):
    """A sheet that arrives blank is a sheet that was never drawn."""
    _fill(sheet, {(0, 0): "Region", (1, 0): "North", (2, 0): "South",
                  (0, 1): "Sales", (1, 1): "1200", (2, 1): "940"})
    path = str(tmp_path / "typed.pdf")
    assert sheet.export_pdf(path) is True
    assert _ink(path) > 0.005


def test_a_blank_sheet_still_prints_one_clean_sheet(sheet, tmp_path):
    sheet._set_paper_size("A4")
    sheet._set_orientation(False)
    path = str(tmp_path / "blank.pdf")
    assert sheet.export_pdf(path) is True
    assert _pages_mm(path)[0] == pytest.approx((210.0, 297.0), abs=1.5)
    assert _ink(path) < 0.001


def test_a_sheet_taller_than_the_paper_flows_onto_more_sheets(sheet, tmp_path):
    sheet._set_paper_size("A5")
    sheet._set_orientation(False)
    _fill(sheet, {(row, 0): f"row {row}" for row in range(200)})
    path = str(tmp_path / "long.pdf")
    assert sheet.export_pdf(path) is True
    pages = _pages_mm(path)
    assert len(pages) > 1
    assert all(mm == pytest.approx((148.0, 210.0), abs=1.5) for mm in pages)
    assert _ink(path, 1) > 0.0, "the second sheet carries the overflow"


# -- PresentR ------------------------------------------------------------------- #

def test_a_widescreen_deck_prints_widescreen_not_on_a4(deck, tmp_path):
    """960 x 540 scene pixels at 96 to the inch is a 10in by 5.625in sheet."""
    path = str(tmp_path / "deck.pdf")
    assert deck.export_pdf(path) is True
    assert _pages_mm(path) == [(254.0, 142.9)]


def test_every_slide_gets_its_own_sheet_at_the_deck_s_size(deck, q_app, tmp_path):
    deck.presentation.slides[0].objects.append(
        TextObject(id="t", x=40, y=40, width=500, height=80, text="One"))
    deck.add_new_slide()
    deck.add_new_slide()
    deck.presentation.slides[2].objects.append(
        ShapeObject(id="s", x=100, y=100, width=200, height=120))
    q_app.processEvents()
    path = str(tmp_path / "three.pdf")
    assert deck.export_pdf(path) is True
    assert _pages_mm(path) == [(254.0, 142.9)] * 3
    assert _ink(path, 0) > 0.001, "the typed slide has ink"
    assert _ink(path, 2) > 0.001, "the drawn shape reaches its own sheet"
