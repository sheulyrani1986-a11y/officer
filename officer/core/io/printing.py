"""Putting a sheet on paper, through whatever printer the machine offers.

A word processor that cannot print is a viewer. Qt talks to CUPS, so every
queue the system has -- network, USB, shared, virtual and print-to-file --
arrives in the dialog on its own: this module asks for the printer, agrees the
paper, and hands the drawing over.

The sheet is painted by the same code that writes the PDF, so what comes out
of a printer is what the screen showed, down to its border, watermark and
bands of header and footer.
"""

from typing import Callable, Optional, Tuple

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPainter, QPageSize
from PySide6.QtPrintSupport import (
    QAbstractPrintDialog, QPrintDialog, QPrinter
)
from PySide6.QtWidgets import QDialog

#: Dots per inch the sheet is measured in on its way out. The printer decides
#: how many dots it actually lays down; this decides how large the drawing is.
PRINT_DPI = 300


def sheet_layout(width_mm: float, height_mm: float, margins_mm: float = 0.0,
                 landscape: bool = False) -> QPageLayout:
    """A sheet of *width_mm* by *height_mm* with *margins_mm* all round.

    The size stays portrait and the orientation does the turning: swapping the
    two as well lands a landscape sheet back on a portrait page.
    """
    return QPageLayout(
        QPageSize(QSizeF(width_mm, height_mm), QPageSize.Unit.Millimeter),
        QPageLayout.Orientation.Landscape if landscape
        else QPageLayout.Orientation.Portrait,
        QMarginsF(margins_mm, margins_mm, margins_mm, margins_mm),
        QPageLayout.Unit.Millimeter)


def choose_printer(parent, layout: QPageLayout,
                   title: str = "Print") -> Optional[QPrinter]:
    """Ask for a printer through the system dialog, or return None.

    The dialog may well change the paper, and it should: a sheet set to A4
    sent to a machine holding only Letter prints on Letter, as it does in
    Word. The margins come back from the document afterwards, because that is
    what the sheet's own dress -- its border and its bands -- is measured
    against, and no print dialog is entitled to move those.
    """
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setResolution(PRINT_DPI)
    printer.setPageLayout(layout)
    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle(title)
    # Nothing is "selected" in the sense a print dialog means: the whole
    # document, or a run of its pages, is what goes out.
    dialog.setOption(QAbstractPrintDialog.PrintDialogOption.PrintSelection,
                     False)
    dialog.setOption(QAbstractPrintDialog.PrintDialogOption.PrintPageRange,
                     True)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    chosen = printer.pageLayout()
    # The paper the printer holds, dressed in the document's own margins. They
    # are set through a fresh layout rather than onto the chosen one, because a
    # layout measures its margins in its own units and the printer's may be
    # points while the document's are millimetres.
    printer.setPageLayout(QPageLayout(chosen.pageSize(), chosen.orientation(),
                                      layout.margins(QPageLayout.Unit.Millimeter),
                                      QPageLayout.Unit.Millimeter))
    printer.setResolution(PRINT_DPI)
    return printer


def page_range(printer: QPrinter) -> Tuple[int, int]:
    """Which sheets the dialog asked for, counted from one.

    ``(1, 0)`` means all of them, because an open-ended range cannot be
    answered until the sheet is laid out and its page count known.
    """
    if printer.printRange() == QPrinter.PrintRange.AllPages:
        return (1, 0)
    return (max(1, printer.fromPage()), max(0, printer.toPage()))


def print_on(printer: QPrinter,
             paint: Callable[[QPainter, QPrinter], object]) -> str:
    """Draw on *printer* and send the job; names where it went.

    Raises whatever the drawing raises only after closing the painter, so a
    failure cannot leave a half-open job sitting on the queue.
    """
    painter = QPainter(printer)
    if not painter.isActive():
        return ""
    try:
        paint(painter, printer)
    finally:
        painter.end()
    return printer.printerName() or printer.outputFileName() or "the printer"
