"""A miniature sheet, dressed the way a dialog's choices would dress it.

Word's page dialogs show the page itself rather than a list of settings, and
this is the widget that does it here. It paints through the very functions the
page and the printer use -- the dress, the mark, the bands -- so a preview
cannot promise something the sheet would not deliver. Only the sizes are
nursed: writing a band at its true share of a sheet this small would leave
unreadable dots, so a floor is set under the two faces.
"""

from typing import Optional
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget
from officer.writer.header_footer import BAND_POINT_SIZE, paint_page_bands
from officer.writer.page_color import paint_page_fill
from officer.writer.watermark import paint_watermark

#: The image files a page can be dressed or marked with.
PICTURE_FILTER = "Pictures (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)"

#: A Letter sheet as Word lays it out, which is what a preview is scaled from.
PREVIEW_PAPER_PX = (816.0, 1056.0)

#: Word's default margin as a share of the sheet's width: an inch of Letter.
#: A preview has no reason to disagree about it.
PREVIEW_MARGIN_SHARE = 96.0 / PREVIEW_PAPER_PX[0]

#: A point measured in the 96 to the inch that Word lays a page out in.
PX_PER_POINT = 96.0 / 72.0

#: The smallest a band or a mark may be drawn and still be read on screen.
MIN_BAND_PX = 7.0
MIN_MARK_PX = 9.0


class SheetPreview(QWidget):
    """One sheet of paper, wearing what the dialog's choices would put on it."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("SheetPreview")
        self.setMinimumSize(170, 210)
        self.fill: dict = {"kind": "none"}
        self.fill_image: Optional[QImage] = None
        self.mark: dict = {"kind": "none"}
        self.mark_image: Optional[QImage] = None
        self.bands: dict = {}
        #: Which sheet is being shown, and how long the document is: fields
        #: have to be answered with real numbers to be judged.
        self.page = 1
        self.total = 3

    def show_page(self, fill: Optional[dict] = None,
                  fill_image: Optional[QImage] = None,
                  mark: Optional[dict] = None,
                  mark_image: Optional[QImage] = None,
                  bands: Optional[dict] = None, page: Optional[int] = None,
                  total: Optional[int] = None) -> None:
        """Put on the sheet whatever the dialog has just chosen."""
        if fill is not None:
            self.fill = dict(fill)
            self.fill_image = fill_image
        if mark is not None:
            self.mark = dict(mark)
            self.mark_image = mark_image
        if bands is not None:
            self.bands = dict(bands)
        if page is not None:
            self.page = max(1, int(page))
        if total is not None:
            self.total = max(self.page, int(total))
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        sheet = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        painter.setPen(QPen(QColor("#D1D5DB"), 1))
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRect(sheet)
        # Everything below is measured against a whole sheet of paper, so one
        # ratio carries the page's own units onto this card.
        scale = sheet.width() / PREVIEW_PAPER_PX[0]
        margin_px = PREVIEW_PAPER_PX[0] * scale * PREVIEW_MARGIN_SHARE
        paint_page_fill(painter, self.fill, sheet, self.fill_image)
        size_px = float(self.mark.get("size_pt", 54)) * PX_PER_POINT * scale
        paint_watermark(painter, self.mark, sheet,
                        size_px=max(MIN_MARK_PX, size_px),
                        image=self.mark_image)
        self._paint_writing(painter, sheet, margin_px)
        band_px = max(MIN_BAND_PX, BAND_POINT_SIZE * PX_PER_POINT * scale)
        font = QFont(self.font().family())
        font.setPixelSize(round(band_px))
        paint_page_bands(painter, self.bands, sheet, self.page, self.total,
                         font, margin_px, 96.0 * scale)
        painter.end()

    def _paint_writing(self, painter: QPainter, sheet: QRectF,
                       margin_px: float) -> None:
        """Real lines of writing, so a mark's fade can be judged against them.

        The mark belongs under the words and the bands above them, which is the
        only order in which the two agree on a printed page.
        """
        top = margin_px
        bottom = sheet.height() - margin_px
        if bottom <= top:
            return
        painter.setPen(QPen(QColor("#1F2937"), 1))
        rows = max(3, int((bottom - top) / (sheet.height() / 14.0)))
        for row in range(rows):
            y = top + (bottom - top) / (rows + 1) * (row + 1)
            short = (row % 3) * sheet.width() * 0.06
            painter.drawLine(QPointF(sheet.left() + margin_px, y),
                             QPointF(sheet.right() - margin_px - short, y))
