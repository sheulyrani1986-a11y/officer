"""Vector PDF Export utilities for OfficeR applications."""

import os
from typing import Optional, Sequence, Tuple
from PySide6.QtCore import QMarginsF, QRect, QRectF, QSizeF, Qt
from PySide6.QtGui import (QFont, QImage, QPageLayout, QPageSize,
                           QPagedPaintDevice, QPainter, QTextDocument)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPdfWriter


class PdfExporter:
    """Exports QTextDocument, QGraphicsScene, or custom paint layouts to vector PDF."""

    @staticmethod
    def export_text_document(
        document: QTextDocument,
        output_filepath: str,
        page_size: QPageSize.PageSizeId = QPageSize.PageSizeId.A4,
        margins_mm: float = 20.0,
        page_size_mm: Optional[tuple] = None,
        landscape: bool = False,
        objects: Optional[Sequence[Tuple[tuple, str]]] = None,
        border: Optional[dict] = None,
        page_colour: Optional[dict] = None,
        watermark: Optional[dict] = None,
        header_footer: Optional[dict] = None
    ) -> bool:
        """Export a paginated QTextDocument to a high-resolution PDF.

        *page_size_mm* overrides the named *page_size* so an editor's own paper
        list (including sizes QPageSize has no constant for) reaches the file.

        *objects* are the pictures lying on the sheet rather than in the words:
        ``((from left, from top, width, height) in centimetres of paper, path)``.
        They are printed where they were put, on the sheet of paper they land
        on, which is why the writing has to be laid out a page at a time here
        instead of being handed to ``QTextDocument.print_``.

        *border* is the sheet's own decoration -- ``{"style", "colour",
        "width_pt"}`` -- drawn on every page that goes out.

        *page_colour* is what the paper is dressed with -- ``{"kind",
        "colour", "image_path", "opacity"}`` -- laid over the whole sheet under
        the writing, which is the only order in which ink and words agree.

        *watermark* is the word or picture set into the paper behind the
        writing, and *header_footer* the two bands of paper above and below it.
        Both belong to the sheet rather than the paragraph, so both go on every
        page that goes out, with the sheet's own number answered.
        """
        writer = QPdfWriter(output_filepath)
        if page_size_mm:
            size = QPageSize(QSizeF(page_size_mm[0], page_size_mm[1]),
                             QPageSize.Unit.Millimeter)
        else:
            size = QPageSize(page_size)
        layout = QPageLayout(
            size,
            QPageLayout.Orientation.Landscape if landscape
            else QPageLayout.Orientation.Portrait,
            QMarginsF(margins_mm, margins_mm, margins_mm, margins_mm),
            QPageLayout.Unit.Millimeter
        )
        writer.setPageLayout(layout)
        resolution = 300
        writer.setResolution(resolution)
        # A document is laid out in Word's units -- 96 to the inch -- and its
        # layout is computed once, on screen. The printer runs at 300 to the
        # inch, so the writing has to be drawn through that ratio: measured
        # straight onto the printer, an 11 pt sheet comes out at 3.6 pt.
        unit_scale = resolution / 96.0

        # Clone document to avoid modifying original layout during pagination
        doc_clone = document.clone()
        # The page layout owns the margins; the document's own margin would
        # stack on top of them and print the text twice as far from the edge.
        doc_clone.setDocumentMargin(0)
        area = layout.paintRectPixels(resolution)
        sheet = QRectF(0, 0, area.width() / unit_scale,
                       area.height() / unit_scale)
        doc_clone.setTextWidth(sheet.width())

        painter = QPainter(writer)
        if not painter.isActive():
            return False
        px_per_cm = resolution / 2.54
        px_per_point = resolution / 72.0
        margin_cm = margins_mm / 10.0
        margin_px = margin_cm * px_per_cm
        sheet_cm = area.height() / px_per_cm
        # The painter starts inside the page's margins, so the whole of the
        # paper -- which is what a sheet of dressing is measured against -- lies
        # a margin outside the painting area on every side.
        paper = QRectF(-margin_px, -margin_px, area.width() + 2 * margin_px,
                       area.height() + 2 * margin_px)
        written = doc_clone.size().height() / max(1.0, sheet.height())
        pages = max(1, int(written) + (1 if written % 1 else 0))
        picture = None
        if page_colour and page_colour.get("kind") == "picture":
            from officer.writer.page_color import load_picture
            picture = load_picture(page_colour.get("image_path", ""))
        mark_image = None
        if watermark and watermark.get("kind") == "picture":
            from officer.writer.page_color import load_picture
            mark_image = load_picture(watermark.get("image_path", ""))
        band_font = None
        if header_footer:
            from officer.writer.header_footer import BAND_POINT_SIZE
            band_font = QFont(document.defaultFont())
            band_font.setPixelSize(round(BAND_POINT_SIZE * px_per_point))
        for page in range(pages):
            if page:
                writer.newPage()
            PdfExporter._draw_page_colour(painter, page_colour, paper,
                                          picture)
            PdfExporter._draw_watermark(painter, watermark, paper, px_per_point,
                                        mark_image)
            # The painter already starts inside the page's margins, so the
            # writing is laid down from there and only slid up by the sheets
            # that went before.
            painter.save()
            painter.scale(unit_scale, unit_scale)
            painter.setClipRect(sheet)
            painter.translate(0, -page * sheet.height())
            doc_clone.drawContents(painter)
            painter.restore()
            PdfExporter._draw_page_border(painter, border, area, px_per_cm)
            PdfExporter._draw_header_footer(painter, header_footer, paper, page,
                                            pages, margin_px, px_per_cm,
                                            band_font)
            PdfExporter._draw_sheet_objects(painter, objects, page, area,
                                            px_per_cm, margin_cm, sheet_cm)
        painter.end()
        return os.path.exists(output_filepath) and os.path.getsize(
            output_filepath) > 0

    @staticmethod
    def _draw_watermark(painter: QPainter, mark: Optional[dict],
                        paper: QRectF, px_per_point: float,
                        image: Optional[QImage] = None) -> None:
        """Set the mark into the sheet being written, under its writing.

        A mark is a word or a picture, so an unreadable picture or an empty
        word leaves the sheet clean rather than printing a box of nothing.
        """
        if not mark or mark.get("kind", "none") == "none":
            return
        from officer.writer.watermark import paint_watermark
        paint_watermark(painter, mark, paper,
                        size_px=float(mark.get("size_pt", 54)) * px_per_point,
                        image=image)

    @staticmethod
    def _draw_header_footer(painter: QPainter, bands: Optional[dict],
                            paper: QRectF, page: int, total: int,
                            margin_px: float, px_per_cm: float,
                            font: Optional[QFont]) -> None:
        """Write both bands on the sheet being written.

        *page* counts from nought where the printer does, and the fields count
        from one where the reader does, which is the only translation this
        function makes.
        """
        if not bands or font is None:
            return
        from officer.writer.header_footer import paint_page_bands
        paint_page_bands(painter, bands, paper, page + 1, total, font,
                         margin_px, px_per_cm)

    @staticmethod
    def _draw_page_border(painter: QPainter, border: Optional[dict],
                          area: QRectF, px_per_cm: float) -> None:
        """Draw the sheet's own border on the page being written.

        The painter starts inside the margins, so the border stands off the
        writing by the same breath it does on screen -- which means it falls
        partly on the paper's margin, exactly as Word's does.
        """
        if not border or border.get("style", "none") == "none":
            return
        from officer.writer.page_border import (BORDER_SPACE_CM,
                                                DEFAULT_COLOUR,
                                                DEFAULT_WIDTH_PT, border_painter)
        space = BORDER_SPACE_CM * px_per_cm
        border_painter(
            painter,
            QRectF(-space, -space, area.width() + 2 * space,
                   area.height() + 2 * space),
            border["style"], border.get("colour", DEFAULT_COLOUR),
            border.get("width_pt", DEFAULT_WIDTH_PT),
            pixels_per_point=300.0 / 72.0)

    @staticmethod
    def _draw_page_colour(painter: QPainter, fill: Optional[dict],
                          paper: QRectF,
                          picture: Optional[QImage] = None) -> None:
        """Dress the whole sheet, under the writing that follows.

        The painter starts inside the margins, so *paper* -- the sheet as the
        printer sees it -- reaches a margin beyond the writing on every side.
        """
        if not fill or fill.get("kind", "none") == "none":
            return
        from officer.writer.page_color import paint_page_fill
        paint_page_fill(painter, fill, paper, picture)

    @staticmethod
    def _draw_sheet_objects(painter: QPainter, objects, page: int, area: QRectF,
                            px_per_cm: float, margin_cm: float,
                            sheet_cm: float) -> None:
        """Print the objects that belong on *page*, where the sheet put them."""
        if not objects:
            return
        for (rect_cm, path) in objects:
            x_cm, y_cm, wide_cm, tall_cm = rect_cm
            # An object's centimetres are measured from the edge of the paper
            # and the page is cut at the printable height, so take the margin
            # off to find where inside the writing it lies -- and which sheet
            # of it it belongs to.
            index = max(0, int((y_cm - margin_cm) // sheet_cm))
            if index != page:
                continue
            image = QImage(path)
            if image.isNull():
                continue
            painter.drawImage(QRectF((x_cm - margin_cm) * px_per_cm,
                                     (y_cm - margin_cm
                                      - index * sheet_cm) * px_per_cm,
                                     wide_cm * px_per_cm, tall_cm * px_per_cm),
                              image)
