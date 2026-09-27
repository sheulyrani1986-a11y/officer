"""Putting a sheet on a real printer, through whatever queue the machine offers.

Printing is the feature an office suite is judged on, and it is judged by what
comes out of the machine rather than by what the dialog looked like. So the
tests below send the work to a printer that writes a PDF instead of paper --
the same code path, the same page layout, the same painter, and a file that can
be measured -- and then compare it against the sheet the same document exports.

The system dialog itself cannot be answered by a test, so it is stood in for by
one that records the options it was handed and the paper it chose. The point of
that substitute is not to exercise the stub: it is to prove that the document's
own margins survive the dialog, that the range the dialog reports decides
which sheets go, and that only the application which prints offers the way to
ask for it.
"""

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeySequence, QPageLayout, QShortcut
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPrintSupport import QAbstractPrintDialog, QPrinter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QMenu

from officer.core.io import printing
from officer.core.ui.base_window import OfficeBaseWindow
from officer.presentr.window import PresentRWindow
from officer.rsheet.window import RSheetWindow
from officer.writer.window import WriteRWindow

POINTS_TO_MM = 25.4 / 72
A4_MM = (210.0, 297.0)
#: A paper the document was not set to, which the printer may insist upon.
LETTER_MM = (215.9, 279.4)


# -- reading a printed sheet ---------------------------------------------------- #

def _document(filepath: str) -> QPdfDocument:
    pdf = QPdfDocument()
    assert pdf.load(filepath) == QPdfDocument.Error.None_, \
        f"{filepath} did not open"
    return pdf


def _sheets_mm(filepath: str) -> list:
    """Every sheet of the file, in millimetres, as a printer would report it."""
    pdf = _document(filepath)
    return [(round(pdf.pagePointSize(i).width() * POINTS_TO_MM, 1),
             round(pdf.pagePointSize(i).height() * POINTS_TO_MM, 1))
            for i in range(pdf.pageCount())]


def _rendered(pdf: QPdfDocument, page: int):
    """A sheet drawn square, so its measurements still add up."""
    size = pdf.pagePointSize(page)
    width = 600
    image = pdf.render(page, QSize(
        width, max(1, round(width * size.height() / size.width()))))
    assert not image.isNull()
    return image


def _is_ink(pixel) -> bool:
    return pixel.alpha() > 0 and pixel.lightness() < 245


def _ink(pdf: QPdfDocument, page: int) -> int:
    """The dots the renderer laid down on a sheet, counted off the PDF."""
    image = _rendered(pdf, page)
    return sum(1 for y in range(image.height()) for x in range(image.width())
               if _is_ink(image.pixelColor(x, y)))


def _ink_per_sheet(filepath: str) -> list:
    pdf = _document(filepath)
    return [_ink(pdf, page) for page in range(pdf.pageCount())]


def _is_paper(filepath: str, expected: list) -> bool:
    """Whether the file's sheets are the paper asked for, to the millimetre.

    A printer rounds a paper's size to the point it carries, so A4 arrives as
    209.9 mm rather than the 210 the document asked for.
    """
    sheets = _sheets_mm(filepath)
    return len(sheets) == len(expected) and all(
        got == pytest.approx(want, abs=1.0) for got, want in zip(sheets,
                                                                 expected))


# -- the dialog, stood in for --------------------------------------------------- #

def _dialog(monkeypatch, *, accept: bool = True, adjust=None) -> dict:
    """Replace the system print dialog with one that answers and records.

    *adjust* plays the printer's own part in the bargain: the paper it actually
    holds, the run of pages the reader asked for, the file a virtual queue
    writes to instead of paper.
    """
    seen = {"titles": [], "options": {}, "printers": []}

    class StoodIn:
        def __init__(self, printer, parent=None):
            self.printer = printer
            seen["printers"].append(printer)

        def setWindowTitle(self, title):
            seen["titles"].append(title)

        def setOption(self, option, on):
            seen["options"][option] = on

        def exec(self):
            if adjust:
                adjust(self.printer)
            return (QDialog.DialogCode.Accepted if accept
                    else QDialog.DialogCode.Rejected)

    monkeypatch.setattr(printing, "QPrintDialog", StoodIn)
    return seen


def _to_pdf(filepath: str):
    """A queue that writes a file instead of paper."""
    def adjust(printer: QPrinter) -> None:
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(filepath)
    return adjust


def _on_paper(width_mm: float, height_mm: float):
    def adjust(printer: QPrinter) -> None:
        printer.setPageLayout(printing.sheet_layout(width_mm, height_mm))
    return adjust


def _sheets(number: int, last: int):
    def adjust(printer: QPrinter) -> None:
        printer.setPrintRange(QPrinter.PrintRange.PageRange)
        printer.setFromTo(number, last)
    return adjust


def _chain(*adjustments):
    def adjust(printer: QPrinter) -> None:
        for one in adjustments:
            one(printer)
    return adjust


# -- the sheet and the queues --------------------------------------------------- #

def test_a_sheet_is_cut_to_the_paper_it_names_with_the_margin_it_wears():
    layout = printing.sheet_layout(*A4_MM, margins_mm=20.0)
    sheet = layout.fullRect(QPageLayout.Unit.Millimeter)
    assert (round(sheet.width(), 1), round(sheet.height(), 1)) == A4_MM
    inside = layout.paintRect(QPageLayout.Unit.Millimeter)
    assert (round(inside.width(), 1), round(inside.height(), 1)) == (170.0, 257.0)


def test_the_size_stays_the_paper_and_the_orientation_does_the_turning():
    """Swapping the two as well lands a wide sheet back on a portrait page."""
    layout = printing.sheet_layout(*A4_MM, landscape=True)
    sheet = layout.fullRect(QPageLayout.Unit.Millimeter)
    assert layout.orientation() == QPageLayout.Orientation.Landscape
    assert (round(sheet.width(), 1), round(sheet.height(), 1)) == (297.0, 210.0)


# -- asking the printer --------------------------------------------------------- #

def test_a_cancelled_dialog_prints_nothing(q_app, monkeypatch):
    _dialog(monkeypatch, accept=False)
    assert printing.choose_printer(WriteRWindow(),
                                   printing.sheet_layout(*A4_MM)) is None


def test_the_dialog_is_titled_for_the_work_it_is_offering(q_app, monkeypatch):
    seen = _dialog(monkeypatch, accept=False)
    win = WriteRWindow()
    printing.choose_printer(win, win._sheet_layout(), "Print Document")
    assert seen["titles"] == ["Print Document"]
    options = seen["options"]
    assert options[
        QAbstractPrintDialog.PrintDialogOption.PrintSelection] is False, \
        "a document prints whole, not by selection"
    assert options[
        QAbstractPrintDialog.PrintDialogOption.PrintPageRange] is True, \
        "the sheets the reader named are the sheets that go out"




def test_the_paper_the_printer_holds_wins_but_the_margins_stay_ones_own(
        q_app, monkeypatch):
    """A sheet set to A4 sent to a Letter machine prints on Letter, as in Word.

    The margins belong to the document, because its border and its bands are
    measured from them, and no print dialog is entitled to move those.
    """
    _dialog(monkeypatch, adjust=_on_paper(*LETTER_MM))
    win = WriteRWindow()
    win.page.set_paper("A4")
    wanted = win._sheet_layout().margins(QPageLayout.Unit.Millimeter)
    printer = printing.choose_printer(win, win._sheet_layout())
    layout = printer.pageLayout()
    sheet = layout.fullRect(QPageLayout.Unit.Millimeter)
    assert (round(sheet.width(), 1), round(sheet.height(), 1)) == LETTER_MM
    got = layout.margins(QPageLayout.Unit.Millimeter)
    assert (round(got.left(), 1), round(got.top(), 1)) == (
        round(wanted.left(), 1), round(wanted.top(), 1))
    assert printer.resolution() == printing.PRINT_DPI


def test_asking_for_every_sheet_leaves_the_range_open_and_a_run_closes_it():
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    assert printing.page_range(printer) == (1, 0)
    printer.setPrintRange(QPrinter.PrintRange.PageRange)
    printer.setFromTo(3, 7)
    assert printing.page_range(printer) == (3, 7)


def test_a_job_is_laid_on_the_printer_and_its_whereabouts_answered(tmp_path):
    target = str(tmp_path / "job.pdf")
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(target)
    printer.setPageLayout(printing.sheet_layout(*A4_MM, margins_mm=20.0))
    printer.setResolution(printing.PRINT_DPI)
    where = printing.print_on(printer, lambda painter, device: painter.drawText(
        device.pageLayout().paintRectPixels(device.resolution()),
        Qt.AlignmentFlag.AlignCenter, "a line of ink"))
    assert where == target
    assert _is_paper(target, [A4_MM])
    assert _ink(_document(target), 0) > 0


# -- WriteR on a printer -------------------------------------------------------- #

@pytest.fixture
def writer(q_app):
    """A letter long enough to run over more than one sheet."""
    win = WriteRWindow()
    win.resize(1200, 900)
    win.show()
    q_app.processEvents()
    win.page.set_paper("A4")
    win.page.setPlainText("\n".join(
        f"Line {number} of the letter that runs over more than one sheet."
        for number in range(120)))
    return win


def test_a_printed_letter_lands_on_the_same_sheets_as_the_exported_one(
        writer, tmp_path, monkeypatch):
    exported = str(tmp_path / "exported.pdf")
    assert writer.export_pdf(exported) is True
    printed = str(tmp_path / "printed.pdf")
    _dialog(monkeypatch, adjust=_to_pdf(printed))
    writer.on_print()
    assert len(_sheets_mm(printed)) > 1, "the letter was written to run over"
    assert _sheets_mm(printed) == _sheets_mm(exported)
    assert _ink_per_sheet(printed) == pytest.approx(_ink_per_sheet(exported),
                                                    rel=0.02, abs=40)


def test_a_printed_sheet_wears_the_border_the_exported_one_wears(
        writer, tmp_path, monkeypatch):
    writer.page.set_page_border(style="double", width_pt=3.0)
    exported = str(tmp_path / "dressed.pdf")
    assert writer.export_pdf(exported) is True
    printed = str(tmp_path / "dressed_print.pdf")
    _dialog(monkeypatch, adjust=_to_pdf(printed))
    writer.on_print()
    assert _ink_per_sheet(printed) == pytest.approx(_ink_per_sheet(exported),
                                                    rel=0.02, abs=40)


def test_the_completed_job_is_named_on_the_status_strip(writer, tmp_path,
                                                        monkeypatch):
    printed = str(tmp_path / "named.pdf")
    _dialog(monkeypatch, adjust=_to_pdf(printed))
    writer.on_print()
    assert printed in writer.status_bar.info_label.text()


def test_a_cancelled_dialog_sends_nothing_and_says_nothing(writer, tmp_path,
                                                           monkeypatch):
    _dialog(monkeypatch, accept=False,
            adjust=_to_pdf(str(tmp_path / "never.pdf")))
    writer.on_print()
    assert list(tmp_path.iterdir()) == []
    assert "Printed" not in writer.status_bar.info_label.text()


def test_only_the_sheets_the_reader_asked_for_go_out(writer, tmp_path,
                                                     monkeypatch):
    every = str(tmp_path / "every.pdf")
    assert writer.export_pdf(every) is True
    wanted = _ink_per_sheet(every)[1:3]
    printed = str(tmp_path / "two_sheets.pdf")
    _dialog(monkeypatch, adjust=_chain(_to_pdf(printed), _sheets(2, 3)))
    writer.on_print()
    assert _is_paper(printed, [A4_MM] * 2)
    assert _ink_per_sheet(printed) == pytest.approx(wanted, rel=0.02, abs=40)


# -- the controls that ask for all of this -------------------------------------- #

def _menu(q_app, monkeypatch, window_class):
    """The backstage File menu of an application, caught before it is shown."""
    captured = []

    class Grabbing(QMenu):
        def exec(self, *args):
            captured.append(self)
            return None

    monkeypatch.setattr("officer.core.ui.base_window.QMenu", Grabbing)
    win = window_class()
    win.show_file_menu()
    return captured[0]


def test_print_is_on_the_file_menu_and_reaches_the_document(q_app, monkeypatch):
    """A menu entry that did nothing would be a dead button in a new suit."""
    seen = _dialog(monkeypatch, accept=False)
    menu = _menu(q_app, monkeypatch, WriteRWindow)
    entry = next(a for a in menu.actions() if a.text() == "Print...")
    assert entry.shortcut().matches(
        QKeySequence(QKeySequence.StandardKey.Print)) == \
        QKeySequence.SequenceMatch.ExactMatch
    entry.trigger()
    assert seen["titles"] == ["Print Document"]
    export = next(a for a in menu.actions() if a.text() == "Export to PDF...")
    assert export.shortcut().isEmpty(), "Ctrl+P belongs to printing alone"


def test_the_printing_shortcut_asks_for_a_printer(q_app, monkeypatch):
    seen = _dialog(monkeypatch, accept=False)
    win = WriteRWindow()
    win.show()
    win.activateWindow()
    q_app.processEvents()
    QTest.keyClick(win, Qt.Key.Key_P, Qt.KeyboardModifier.ControlModifier)
    q_app.processEvents()
    assert seen["titles"] == ["Print Document"]
    # A shortcut swallows the release of the key that fired it, so the
    # application goes on believing Ctrl is held -- which the next window's
    # grid reads as "add to the selection". Hand the key back.
    QTest.keyRelease(win, Qt.Key.Key_Control)
    q_app.processEvents()
    win.close()


def test_an_application_that_does_not_print_offers_no_way_to_ask(q_app,
                                                                monkeypatch):
    """RSheet and PresentR export a PDF; a Print entry there would be dead."""
    assert RSheetWindow.can_print is False
    assert PresentRWindow.can_print is False
    assert OfficeBaseWindow.can_print is False
    menu = _menu(q_app, monkeypatch, RSheetWindow)
    assert [a.text() for a in menu.actions() if "Print" in a.text()] == []
    sheet = RSheetWindow()
    sheet.show()
    q_app.processEvents()
    wanted = QKeySequence(QKeySequence.StandardKey.Print)
    assert not [one for one in sheet.findChildren(QShortcut)
                if one.key().matches(wanted) == QKeySequence.SequenceMatch.ExactMatch]
    sheet.close()
