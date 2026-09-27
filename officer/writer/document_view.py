"""Paginated WYSIWYG Document Editor View for WriteR."""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional, Tuple
from PySide6.QtCore import Qt, Signal, QRectF, QSizeF, QPointF, QTimer
from PySide6.QtGui import (
    QTextDocument, QTextCursor, QTextCharFormat, QTextBlockFormat,
    QTextTableFormat, QTextListFormat, QTextLength, QTextFormat, QFont, QColor,
    QPainter, QBrush, QPen, QTextImageFormat, QTextFrameFormat, QTextFrame,
    QImage, QImageReader
)
from PySide6.QtWidgets import (
    QWidget, QTextEdit, QVBoxLayout, QHBoxLayout, QScrollArea, QFrame,
    QGraphicsDropShadowEffect
)
from officer.core.themes.theme_manager import ThemeManager
from officer.core.ui.fonts import body_font, math_font
from officer.writer.floating import (FloatPictureWidget, MIN_SIZE_CM, PX_PER_CM,
                                     WRAP_GAP_CM)
from officer.writer.page_border import (BORDER_SPACE_CM, DEFAULT_COLOUR,
                                        DEFAULT_WIDTH_PT, border_box,
                                        border_painter)
from officer.writer.page_color import (DEFAULT_OPACITY, DEFAULT_PAGE_COLOUR,
                                       FILL_KINDS, clamp_opacity, load_picture,
                                       paint_page_fill)
from officer.writer.header_footer import (BAND_POINT_SIZE, BAND_SIDES,
                                          bands_setting, default_bands,
                                          has_bands, paint_page_bands)
from officer.writer.watermark import (MARK_KINDS, clamp_scale, paint_watermark,
                                      watermark_mark)
from officer.writer.unicode_math import to_math_runs

#: Millimetres → the 96 DPI pixels Word lays the page out in.
MM_TO_PX = 96.0 / 25.4

#: Points → the same pixels, for the sizes a sheet's dress and its bands are
#: written in. Word measures the paper in inches and the writing in points.
PX_PER_POINT = 96.0 / 72.0

#: Word's Size gallery: the sheet in millimetres, exactly as Office prints the
#: numbers in the menu. Envelopes are included because Word's list includes them.
PAPER_SIZES_MM = {
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
    "Tabloid": (279.4, 431.8),
    "Ledger": (431.8, 279.4),
    "A3": (297.0, 420.0),
    "A4": (210.0, 297.0),
    "A5": (148.0, 210.0),
    "A6": (105.0, 148.0),
    "B4 (ISO)": (250.0, 353.0),
    "B5 (ISO)": (176.0, 250.0),
    "B5 (JIS)": (182.0, 257.0),
    "Executive": (184.2, 266.7),
    "Folio": (215.9, 330.2),
    "Statement": (139.7, 215.9),
    "#10 Envelope": (98.4, 241.3),
    "Monarch Envelope": (98.4, 190.5),
    "DL Envelope": (110.0, 220.0),
    "C5 Envelope": (162.0, 229.0),
}

#: How Layout ▸ Size ▸ Paper groups those entries, as Office's separators do.
PAPER_GROUPS = (
    ("Paper", ("Letter", "Legal", "Tabloid", "Ledger", "A3", "A4", "A5", "A6")),
    ("Extra", ("B4 (ISO)", "B5 (ISO)", "B5 (JIS)", "Executive", "Folio", "Statement")),
    ("Envelopes", ("#10 Envelope", "Monarch Envelope", "DL Envelope", "C5 Envelope")),
)

#: Word's paper sizes in pixels at 96 DPI (portrait).
PAPER_SIZES = {
    name: (round(w * MM_TO_PX), round(h * MM_TO_PX))
    for name, (w, h) in PAPER_SIZES_MM.items()
}


def paper_size_caption(name: str) -> str:
    """Office's menu text: ``A4 (210 × 297 mm)``."""
    w, h = PAPER_SIZES_MM[name]
    return f"{name} ({w:g} × {h:g} mm)"


#: Word's margin presets in pixels at 96 DPI.
MARGIN_PRESETS = {
    "Normal": 96,
    "Moderate": 72,
    "Narrow": 36,
    "Wide": 144,
}

#: A picture is measured in centimetres to the user and in these pixels to the
#: page; the floating layer does the same arithmetic, so it owns the constant
#: and the page reads it back from there.

#: How far a wrapped picture stands off the text that runs beside it.
PICTURE_GAP_PX = 8.0

#: Word's wrapping choices that this document model can really draw: a picture
#: on its own line, one that keeps the lines above and below clear, or one
#: floated to a margin with text running past it.
PICTURE_WRAPS = ("inline", "top_bottom", "left", "right")

#: Which of those a picture was placed as, carried on its own format.
PICTURE_WRAP = QTextFormat.UserProperty + 11

#: Marks the frame a floated picture lives in as ours, not a table's.
PICTURE_FRAME = QTextFormat.UserProperty + 12

#: The indent a paragraph had before any floating object pushed the lines
#: around it. Carried on the block, so undo takes it back with the rest of the
#: paragraph's formatting.
FLOAT_BASE_LEFT = QTextFormat.UserProperty + 13
FLOAT_BASE_RIGHT = QTextFormat.UserProperty + 14

#: The paragraph's own top space, kept aside while an object below it on the
#: sheet sends the line further down.
FLOAT_BASE_TOP = QTextFormat.UserProperty + 15

#: An object is only pulled back onto its paragraph when the two have drifted
#: by more than this: re-measuring every line after every keystroke is not free.
ANCHOR_DRIFT_CM = 0.05

#: How many times the wrapping is worked out before the layout is taken as
#: settled: text that narrows gets taller, and taller text meets more objects.
FLOAT_SETTLE_PASSES = 4


def _picture_size(width: Optional[float], height: Optional[float],
                  natural_width: float, natural_height: float,
                  column_px: float) -> Tuple[float, float]:
    """The centimetres Word would settle on: the asked-for size, shape kept,
    never wider than the column between the margins."""
    wide = float(width or natural_width)
    tall = float(height or natural_height)
    if width and not height:
        tall = wide * natural_height / max(1.0, natural_width)
    elif height and not width:
        wide = tall * natural_width / max(1.0, natural_height)
    if wide > column_px:
        tall *= column_px / max(1.0, wide)
        wide = column_px
    return max(1.0, wide), max(1.0, tall)


def _natural_size(filepath: str) -> Optional[Tuple[int, int]]:
    """The picture's own pixels, which is where Word's Reset Size goes back to."""
    size = QImageReader(filepath).size()
    return (size.width(), size.height()) if size.isValid() else None


def _is_variable(expression: str, index: int) -> bool:
    """Whether ``expression[index]`` is a letter standing on its own."""
    char = expression[index]
    if not char.isalpha():
        return False
    before = expression[index - 1] if index > 0 else " "
    after = expression[index + 1] if index + 1 < len(expression) else " "
    return not (before.isalpha() or after.isalpha())


@dataclass
class _Picture:
    """An embedded image as the document holds it.

    A picture is one character when it sits on its own line, and a frame around
    that character when text wraps past it. *start*/*end* cover whichever of the
    two is being replaced, so changing a picture's wrap cannot leave a stray box
    behind the old one.
    """

    start: int
    end: int
    char: int
    image: QTextImageFormat
    wrap: str
    frame: Optional[QTextFrame] = None


class DocumentPageWidget(QTextEdit):
    """
    A physical sheet of paper (any size in :data:`PAPER_SIZES`) centered on the
    workspace canvas, with Word's drop shadow and 1-inch margins.
    """

    contentStatsChanged = Signal(int, int)  # word count, char count

    #: The object the ribbon is editing changed.
    floatSelectionChanged = Signal()

    #: An object was dragged or stretched: the ribbon's boxes must follow it.
    floatGeometryChanged = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("DocumentPaper")

        self._paper = "Letter"
        self._landscape = False
        self._base_width, self._base_height = PAPER_SIZES[self._paper]
        self._zoom_factor = 1.0
        self._margin_px = MARGIN_PRESETS["Normal"]

        self.setFixedWidth(self._base_width)
        self.setMinimumHeight(self._base_height)

        # Standard 1-inch (96px) margins via document margin
        self.document().setDocumentMargin(self._margin_px)
        self.setAcceptRichText(True)
        self.setTabChangesFocus(False)

        # Word's body font: Calibri 11, with the substitutes this machine has.
        body = body_font(11)
        self.setFont(body)
        self.document().setDefaultFont(body)

        # Connect text changes to word/char count stats
        self.textChanged.connect(self._update_stats)

        # The objects lying on this sheet, and the one the ribbon edits.
        self._floats = []
        self._selected_float = None
        self._tying_floats = False
        #: One cursor for every paragraph the objects push aside, so that a
        #: drag is a single thing to undo rather than a hundred margins.
        self._block_cursor = QTextCursor(self.document())
        self.document().contentsChanged.connect(self.tie_text_round_floats)
        # A page break opens the sheet that is left, and the writing above it
        # can change how much of a sheet is left with a single keystroke.
        self._paginating = False
        self.document().contentsChanged.connect(self._note_page_breaks)

        #: The lines or design this sheet wears along its margins.
        self._border = {"style": "none", "colour": DEFAULT_COLOUR,
                        "width_pt": DEFAULT_WIDTH_PT}

        #: What the paper itself is dressed with, and the picture read from it
        #: once so that no repaint has to touch the disk.
        self._fill = {"kind": "none", "colour": DEFAULT_PAGE_COLOUR,
                      "image_path": "", "opacity": DEFAULT_OPACITY}
        self._fill_image: Optional[QImage] = None

        #: The word or picture set into the paper behind the writing.
        self._mark = watermark_mark(None)
        self._mark_image: Optional[QImage] = None

        #: What the top and the bottom of every sheet carry.
        self._bands = default_bands()

        # The paper itself is styled by the theme (objectName DocumentPaper);
        # the shadow is what sells "a sheet on a desk".
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(26)
        shadow.setColor(QColor(0, 0, 0, 70))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    # -- page geometry ------------------------------------------------------ #

    def set_paper(self, name: str) -> None:
        if name in PAPER_SIZES:
            self._paper = name
            self._apply_page_geometry()

    def set_landscape(self, landscape: bool) -> None:
        self._landscape = bool(landscape)
        self._apply_page_geometry()

    @property
    def landscape(self) -> bool:
        return self._landscape

    def set_margin_pixels(self, margin: float) -> None:
        self._margin_px = max(12.0, float(margin))
        self.document().setDocumentMargin(self._margin_px * self._zoom_factor)
        self._notify_ruler()
        self.tie_text_round_floats()

    @property
    def margin_pixels(self) -> float:
        return self._margin_px

    @property
    def paper_size(self) -> str:
        return self._paper

    @property
    def paper_size_mm(self) -> tuple:
        """The chosen sheet in millimetres, portrait order, as PDF wants it."""
        return PAPER_SIZES_MM[self._paper]

    def _apply_page_geometry(self) -> None:
        width, height = PAPER_SIZES[self._paper]
        if self._landscape:
            width, height = height, width
        self._base_width, self._base_height = width, height
        self.setFixedWidth(int(width * self._zoom_factor))
        self.setMinimumHeight(int(height * self._zoom_factor))
        self._notify_ruler()
        self._relayout_floats()
        self.viewport().update()

    # -- the border the sheet wears ----------------------------------------- #

    def set_page_border(self, style: Optional[str] = None,
                        colour: Optional[str] = None,
                        width_pt: Optional[float] = None) -> None:
        """Dress the margins, as Word's Page Borders dialog does.

        Only what is given is changed: the dialog sends the whole set at once,
        and a caller that only wants a different colour keeps the line it had.
        """
        if style is not None:
            self._border["style"] = style
        if colour:
            self._border["colour"] = colour
        if width_pt:
            self._border["width_pt"] = float(width_pt)
        self.viewport().update()
        self.document().setModified(True)

    def page_border(self) -> dict:
        """What the sheet wears: the style, its colour and its weight."""
        return dict(self._border)

    # -- what the paper itself is dressed with ------------------------------ #

    def set_page_colour(self, kind: Optional[str] = None,
                        colour: Optional[str] = None,
                        image_path: Optional[str] = None,
                        opacity: Optional[float] = None) -> None:
        """Dress the paper, as Word's Page Color does.

        Only what is given changes, so a caller that only fades the picture it
        already chose keeps the picture. A picture that cannot be read is no
        picture at all: the sheet keeps the dress it wore.
        """
        if colour:
            self._fill["colour"] = colour
        if image_path is not None:
            # An empty path is the dialog's "no picture chosen" rather than a
            # file that failed to read, so it clears the dress without refusing
            # the kind that came with it.
            image = load_picture(image_path) if image_path else None
            self._fill["image_path"] = image_path if image else ""
            self._fill_image = image
            if image_path and image is None:
                kind = None
        if opacity is not None:
            self._fill["opacity"] = clamp_opacity(opacity)
        if kind == "picture" and self._fill_image is None:
            kind = None
        if kind in FILL_KINDS:
            self._fill["kind"] = kind
        self.viewport().update()
        self.document().setModified(True)

    def page_colour(self) -> dict:
        """How the paper is dressed now: nothing, an ink, or a picture."""
        return dict(self._fill)

    # -- the mark set into the paper ---------------------------------------- #

    def set_watermark(self, kind: Optional[str] = None,
                      text: Optional[str] = None,
                      family: Optional[str] = None,
                      size_pt: Optional[float] = None,
                      colour: Optional[str] = None,
                      layout: Optional[str] = None,
                      opacity: Optional[float] = None,
                      scale: Optional[int] = None,
                      image_path: Optional[str] = None) -> bool:
        """Set the mark the sheet wears behind its writing, as Word's does.

        Only what is given changes, so the dialog can send the whole mark at
        once while a caller that only wants a different word keeps the rest. A
        picture that cannot be read is no picture: the sheet keeps the mark it
        wore, and ``False`` says so.
        """
        mark = watermark_mark(self._mark)
        if text is not None:
            mark["text"] = text
        if family is not None:
            mark["family"] = family
        if size_pt is not None:
            mark["size_pt"] = size_pt
        if colour:
            mark["colour"] = colour
        if layout is not None:
            mark["layout"] = layout
        if opacity is not None:
            mark["opacity"] = opacity
        if scale is not None:
            mark["scale"] = clamp_scale(scale)
        if image_path:
            # An empty path is the dialog's "no picture chosen", not a picture
            # that failed to load: only a path that names a file can be refused.
            image = load_picture(image_path)
            if image is None:
                return False
            mark["image_path"] = image_path
            self._mark_image = image
        if kind in MARK_KINDS:
            mark["kind"] = kind
        if mark["kind"] == "picture" and self._mark_image is None:
            return False
        if mark["kind"] == "text" and not mark["text"].strip():
            mark["kind"] = "none"
        self._mark = mark
        self.viewport().update()
        self.document().setModified(True)
        return True

    def watermark(self) -> dict:
        """What the paper is marked with, in the shape the printer wants."""
        return dict(self._mark)

    def remove_watermark(self) -> None:
        """Take the mark off, and the picture that came with it."""
        self._mark["kind"] = "none"
        self._mark_image = None
        self.viewport().update()
        self.document().setModified(True)

    # -- the bands above and below the writing ------------------------------ #

    def set_header_footer(self, header: Optional[dict] = None,
                          footer: Optional[dict] = None,
                          show_first_page: Optional[bool] = None) -> None:
        """Write the bands every sheet wears, as Word's Header & Footer does.

        A band given empty is left as it stands: the dialog sends both, but a
        caller that only cares about the footer should not silence the header.
        """
        bands = bands_setting(self._bands)
        for kind, given in (("header", header), ("footer", footer)):
            if given:
                for side, text in given.items():
                    if side in BAND_SIDES:
                        bands[kind][side] = text
        if show_first_page is not None:
            bands["show_first_page"] = bool(show_first_page)
        self._bands = bands
        self.viewport().update()
        self.document().setModified(True)

    def header_footer(self) -> dict:
        """What the two bands carry, fields and all."""
        return dict(self._bands)

    def remove_header_footer(self) -> None:
        """Take both bands off the paper."""
        self._bands = default_bands()
        self.viewport().update()
        self.document().setModified(True)

    def clear_page_dress(self) -> None:
        """Take off everything the paper itself wears, as a fresh document asks.

        None of it is saved with the words, so a sheet allowed to keep its
        dress would carry one document's colour, border, mark and bands into
        the next one opened over the top of it.
        """
        self._border["style"] = "none"
        self._fill["kind"] = "none"
        self._mark = watermark_mark(None)
        self._mark_image = None
        self._bands = default_bands()
        self.viewport().update()

    def sheet_box(self, page: int) -> QRectF:
        """One sheet of this page, where it lies among the words."""
        sheet_px = self._base_height * self._zoom_factor
        return QRectF(0, page * sheet_px,
                      self._base_width * self._zoom_factor, sheet_px)

    def _visible_sheets(self) -> int:
        """How many sheets of paper the screen shows at once."""
        sheet_px = max(1.0, self._base_height * self._zoom_factor)
        return max(1, int((self.scroll_offset_px() + self.viewport().height())
                          // sheet_px) + 1)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        # The paper's dress and its mark go under the writing; the border and
        # the bands over it, so the two painters sandwich the document.
        if self._fill["kind"] != "none" or self._mark["kind"] != "none":
            under = self._sheet_painter()
            self.paint_page_colour(under)
            self.paint_page_watermark(under)
            under.end()
        super().paintEvent(event)
        if self._border["style"] != "none" or has_bands(self._bands):
            over = self._sheet_painter()
            self.paint_page_borders(over)
            self.paint_page_header_footer(over)
            over.end()

    def _sheet_painter(self) -> QPainter:
        """A painter whose origin is the top-left corner of the first sheet."""
        painter = QPainter(self.viewport())
        # The scroll has carried the top of the paper up out of sight; the
        # sheets are where the paper is, not where the screen begins.
        painter.resetTransform()
        painter.translate(-self.horizontalScrollBar().value(),
                          -self.verticalScrollBar().value())
        return painter

    def paint_page_colour(self, painter: QPainter) -> None:
        """Dress every sheet this page is cut into, edge to edge."""
        if self._fill["kind"] == "none":
            return
        for page in range(self._visible_sheets()):
            paint_page_fill(painter, self._fill, self.sheet_box(page),
                            self._fill_image)

    def paint_page_borders(self, painter: QPainter) -> None:
        """Draw the border on every sheet this page is cut into.

        The painter's origin is the top-left corner of the first sheet, so a
        page's border simply goes where that page does.
        """
        if self._border["style"] == "none":
            return
        sheet_px = self._base_height * self._zoom_factor
        margin_px = self._margin_px * self._zoom_factor
        printable_px = self.printable_width_px * self._zoom_factor
        space_px = self.to_display(BORDER_SPACE_CM * PX_PER_CM)
        for page in range(self._visible_sheets()):
            border_painter(
                painter,
                border_box(margin_px, printable_px, sheet_px, space_px,
                           page * sheet_px),
                self._border["style"], self._border["colour"],
                self._border["width_pt"], pixels_per_point=self._zoom_factor)

    def paint_page_watermark(self, painter: QPainter) -> None:
        """Set the mark into every sheet this page is cut into.

        A mark belongs under the writing, so the caller hands it the same
        painter that dressed the paper. Its size is measured in the sheet's own
        zoomed pixels, which is the only way 54 pt means the same thing here as
        it does on the printer.
        """
        if self._mark["kind"] == "none":
            return
        size_px = self._mark["size_pt"] * PX_PER_POINT * self._zoom_factor
        for page in range(self._visible_sheets()):
            paint_watermark(painter, self._mark, self.sheet_box(page),
                            size_px=size_px, image=self._mark_image)

    def paint_page_header_footer(self, painter: QPainter) -> None:
        """Write both bands on every sheet this page is cut into.

        The bands are the paper's, not the paragraph's, so they go on every
        sheet whether or not the writing reaches it. A sheet's own number and
        the document's length are answered as they are painted, because that is
        the first moment either is known.
        """
        if not has_bands(self._bands):
            return
        sheet_px = self._base_height * self._zoom_factor
        total = self._sheets_written()
        for page in range(self._visible_sheets()):
            paint_page_bands(
                painter, self._bands, self.sheet_box(page), page + 1, total,
                self._band_font(), self._margin_px * self._zoom_factor,
                PX_PER_CM * self._zoom_factor)

    def _sheets_written(self) -> int:
        """How many sheets the writing fills, which is what ``{PAGES}`` means.

        The printer measures the writing against the paper *inside* the margins,
        so this does too: the document's own height carries a margin on each
        side, and only the run between them can hold words. Measured against the
        whole sheet instead, a long document counts short and the band prints a
        number the printer never reaches.
        """
        written = self.to_actual(self.document().size().height())
        written = max(0.0, written - 2 * self._margin_px)
        per_sheet = max(1.0, self._base_height - 2 * self._margin_px)
        return max(1, int(-(-written // per_sheet)))

    def _band_font(self) -> QFont:
        """The face the bands are set in: the body's, at Word's 10 pt."""
        font = QFont(self.document().defaultFont())
        font.setPixelSize(round(BAND_POINT_SIZE * PX_PER_POINT
                                * self._zoom_factor))
        return font

    def _notify_ruler(self) -> None:
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, DocumentWorkspace):
                parent.sync_page_geometry()
                return
            parent = parent.parentWidget()

    def set_zoom(self, percent: int) -> None:
        """Word's view zoom: the sheet grows and so does everything drawn on it.

        A ``QTextEdit`` has no display-only zoom, so each size the document
        carries is multiplied by the same factor. The document therefore holds
        zoomed numbers while the ribbon, the font box and the way out to disk all
        work in the sizes that were actually typed: see :meth:`at_actual_size`,
        :meth:`to_display` and :meth:`to_actual`.
        """
        factor = min(max(percent / 100.0, 0.2), 6.0)
        ratio = factor / self._zoom_factor
        if ratio == 1.0:
            return
        modified = self.document().isModified()
        self._zoom_factor = factor
        self._scale_sizes(ratio)
        self._scale_default_font(ratio)
        self.document().setDocumentMargin(self._margin_px * factor)
        self._apply_page_geometry()
        self.document().setModified(modified)
        self._update_stats()

    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor

    def to_display(self, actual: float) -> float:
        """A size the document is written in, as it sits on screen."""
        return actual * self._zoom_factor

    def to_actual(self, displayed: float) -> float:
        """A size on screen, as the document is written in."""
        return displayed / self._zoom_factor

    def _scale_default_font(self, ratio: float) -> None:
        """Grow or shrink the face new text falls back to."""
        document = self.document()
        font = QFont(document.defaultFont())
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * ratio)
        document.setDefaultFont(font)
        self.setFont(font)

    def _scale_sizes(self, ratio: float) -> None:
        """Multiply every size in the document by *ratio*, run by run.

        The walk happens as one edit block rather than with the undo stack
        switched off, because switching it off would throw away everything typed
        since the document opened. The modified flag is put back afterwards: a
        change of view is not a change of the document.
        """
        document = self.document()
        modified = document.isModified()
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        block = document.begin()
        while block.isValid():
            walk = block.begin()
            while not walk.atEnd():
                fragment = walk.fragment()
                fmt = fragment.charFormat()
                image = fmt.toImageFormat() if fmt.isImageFormat() else None
                if image is not None and image.width() > 0 and image.height() > 0:
                    image.setWidth(image.width() * ratio)
                    image.setHeight(image.height() * ratio)
                    fmt = image
                elif fmt.fontPointSize() > 0:
                    fmt.setFontPointSize(fmt.fontPointSize() * ratio)
                else:
                    walk += 1
                    continue
                cursor.setPosition(fragment.position())
                cursor.setPosition(fragment.position() + fragment.length(),
                                   QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(fmt)
                walk += 1
            block_fmt = block.blockFormat()
            changed = False
            for setter, getter in (("setLeftMargin", "leftMargin"),
                                   ("setRightMargin", "rightMargin"),
                                   ("setTopMargin", "topMargin"),
                                   ("setBottomMargin", "bottomMargin"),
                                   ("setTextIndent", "textIndent")):
                value = getattr(block_fmt, getter)()
                if value:
                    getattr(block_fmt, setter)(value * ratio)
                    changed = True
            if changed:
                cursor.setPosition(block.position())
                cursor.setBlockFormat(block_fmt)
            block = block.next()
        cursor.endEditBlock()
        document.setModified(modified)

    def reapply_zoom(self) -> None:
        """Scale a document that arrived at its own sizes up to the view."""
        factor = self._zoom_factor
        if factor == 1.0:
            return
        self._scale_sizes(factor)
        self._scale_default_font(factor)
        self.document().setDocumentMargin(self._margin_px * factor)

    @contextmanager
    def at_actual_size(self):
        """Hand over the document at the sizes it was written in, then put it back."""
        factor = self._zoom_factor
        if factor == 1.0:
            yield self.document()
            return
        self._zoom_factor = 1.0
        self._scale_sizes(1.0 / factor)
        self._scale_default_font(1.0 / factor)
        self.document().setDocumentMargin(self._margin_px)
        try:
            yield self.document()
        finally:
            self._zoom_factor = factor
            self._scale_sizes(factor)
            self._scale_default_font(factor)
            self.document().setDocumentMargin(self._margin_px * factor)

    def _note_page_breaks(self) -> None:
        """The writing changed: the sheets a break opens must be measured again.

        A break is given the height of the paper left on its sheet, so anything
        written above it can leave the next sheet starting part-way down. The
        work is deferred to the next turn of the loop, where the lines the change
        has just written have been measured, and it is skipped while our own
        margin-setting is the change being answered.
        """
        if self._paginating:
            return
        QTimer.singleShot(0, self._repaginate)

    def _repaginate(self) -> None:
        from officer.writer.templates import paginate_breaks
        if self._paginating or self.viewport().width() <= 1:
            return
        factor = self._zoom_factor
        written = self.document().isModified()
        self._paginating = True
        try:
            paginate_breaks(self.document(),
                            (self._base_width * factor, self._base_height * factor),
                            self._margin_px * factor)
        finally:
            self._paginating = False
            # Measuring the paper is not a change the user made, so it must not
            # leave the document asking to be saved.
            self.document().setModified(written)

    def _update_stats(self) -> None:
        text = self.toPlainText()
        words = len(text.split()) if text.strip() else 0
        chars = len(text)
        self.contentStatsChanged.emit(words, chars)

    def page_count(self) -> int:
        """How many sheets the writing fills, which is what ``{PAGES}`` means."""
        return self._sheets_written()

    def current_page_number(self) -> int:
        """Which sheet the caret stands on, counted the way the printer does."""
        per_page = max(1.0, self._base_height - 2 * self._margin_px)
        per_page *= self._zoom_factor
        y = self.cursorRect().top() + self.verticalScrollBar().value()
        written = max(0.0, y - self._margin_px * self._zoom_factor)
        return max(1, min(self.page_count(), int(written // per_page) + 1))

    # --- Paragraph operations (Word's Paragraph group) --- #

    def set_bullet_list(self) -> None:
        self._apply_list_style(QTextListFormat.Style.ListDisc)

    def set_numbered_list(self) -> None:
        self._apply_list_style(QTextListFormat.Style.ListDecimal)

    def _apply_list_style(self, style) -> None:
        cursor = self.textCursor()
        existing = cursor.currentList()
        if existing is not None and existing.format().style() == style:
            cursor.joinPreviousEditBlock()
            cursor.removeList()
            cursor.endEditBlock()
            return
        fmt = QTextListFormat()
        fmt.setStyle(style)
        fmt.setIndent(max(1, cursor.blockFormat().indent() or 1))
        cursor.joinPreviousEditBlock()
        if existing is not None:
            existing.setFormat(fmt)
        else:
            cursor.createList(fmt)
        cursor.endEditBlock()

    def set_indent(self, levels: int = 1) -> None:
        """Word's Increase / Decrease Indent on the current block or selection."""
        cursor = self.textCursor()
        block_fmt = cursor.blockFormat()
        block_fmt.setIndent(max(0.0, block_fmt.indent() + levels))
        cursor.joinPreviousEditBlock()
        cursor.setBlockFormat(block_fmt)
        cursor.endEditBlock()

    def set_line_spacing(self, multiple: float) -> None:
        """Apply Word's line-spacing multiple (1.0, 1.15, 1.5, 2.0)."""
        cursor = self.textCursor()
        block_fmt = cursor.blockFormat()
        block_fmt.setLineHeight(
            QTextBlockFormat.LineHeightTypes.ProportionalHeight.value, multiple * 100.0
        )
        cursor.joinPreviousEditBlock()
        cursor.setBlockFormat(block_fmt)
        cursor.endEditBlock()

    def insert_page_break(self) -> None:
        """Start the following text on a new page (Ctrl+Enter)."""
        cursor = self.textCursor()
        block_fmt = QTextBlockFormat()
        block_fmt.setPageBreakPolicy(
            QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore
        )
        cursor.joinPreviousEditBlock()
        cursor.insertBlock(block_fmt)
        cursor.endEditBlock()

    # --- Formatting Operations ---

    def set_bold(self) -> None:
        cursor = self.textCursor()
        fmt = cursor.charFormat()
        weight = QFont.Weight.Normal if fmt.fontWeight() >= QFont.Weight.Bold else QFont.Weight.Bold
        fmt.setFontWeight(weight)
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def set_italic(self) -> None:
        cursor = self.textCursor()
        fmt = cursor.charFormat()
        fmt.setFontItalic(not fmt.fontItalic())
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def set_underline(self) -> None:
        cursor = self.textCursor()
        fmt = cursor.charFormat()
        fmt.setFontUnderline(not fmt.fontUnderline())
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def set_strikethrough(self) -> None:
        cursor = self.textCursor()
        fmt = cursor.charFormat()
        fmt.setFontStrikeOut(not fmt.fontStrikeOut())
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def set_font_family(self, family: str) -> None:
        cursor = self.textCursor()
        fmt = cursor.charFormat()
        fmt.setFontFamilies([family])
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def set_font_size(self, pt: float) -> None:
        """Set the caret's size in points, whatever the view is zoomed to."""
        cursor = self.textCursor()
        fmt = cursor.charFormat()
        fmt.setFontPointSize(self.to_display(pt))
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def increase_font_size(self, delta: int = 1) -> None:
        """Increase font size of current selection by *delta* points (Ctrl+])."""
        self._nudge_font_size(delta)

    def decrease_font_size(self, delta: int = 1) -> None:
        """Decrease font size of current selection by *delta* points (Ctrl+[)."""
        self._nudge_font_size(-delta)

    def _nudge_font_size(self, delta: float) -> None:
        cursor = self.textCursor()
        fmt = cursor.charFormat()
        size = self.to_actual(fmt.fontPointSize() or self.font().pointSizeF())
        fmt.setFontPointSize(self.to_display(max(1.0, size + delta)))
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def toggle_ruler(self) -> None:
        """Show or hide the ruler widget in the containing DocumentWorkspace."""
        # Walk up to find the DocumentWorkspace (which owns the ruler)
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "ruler"):
                parent.ruler.setVisible(not parent.ruler.isVisible())
                return
            parent = parent.parent() if hasattr(parent, "parent") else None

    def set_text_color(self, color_hex: str) -> None:
        cursor = self.textCursor()
        fmt = cursor.charFormat()
        fmt.setForeground(QColor(color_hex))
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def set_highlight_color(self, color_hex: str) -> None:
        cursor = self.textCursor()
        fmt = cursor.charFormat()
        fmt.setBackground(QColor(color_hex))
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)

    def clear_character_format(self) -> None:
        """Word's "Clear Formatting": strip direct character formatting."""
        cursor = self.textCursor()
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        if start == end:
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            start, end = cursor.selectionStart(), cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.mergeCharFormat(QTextCharFormat())
        self.setTextCursor(cursor)

    def current_font_family(self) -> str:
        family = self.textCursor().charFormat().fontFamilies()
        return family[0] if family else self.document().defaultFont().family()

    def current_font_point_size(self) -> float:
        """The caret's size in the points it was written in, not on screen."""
        size = self.textCursor().charFormat().fontPointSize()
        if not size:
            size = self.document().defaultFont().pointSizeF()
        return self.to_actual(size)

    def set_alignment(self, alignment: Qt.AlignmentFlag) -> None:
        cursor = self.textCursor()
        fmt = cursor.blockFormat()
        fmt.setAlignment(alignment)
        cursor.setBlockFormat(fmt)
        self.setTextCursor(cursor)

    #: Heading 1..6 and Normal (0): the body size, whether it is bold, and the
    #: space above and below, in the points and pixels Word ships them in.
    _HEADING_STYLES = {
        0: (11, QFont.Weight.Normal, 0, 4),
        1: (20, QFont.Weight.Bold, 12, 6),
        2: (16, QFont.Weight.Bold, 10, 4),
        3: (13, QFont.Weight.Bold, 8, 2),
    }

    def apply_heading(self, level: int) -> None:
        """Apply Heading 1..6 or Normal (0)."""
        cursor = self.textCursor()
        block_fmt = cursor.blockFormat()
        char_fmt = cursor.charFormat()

        style = self._HEADING_STYLES.get(level)
        if style is not None:
            size, weight, above, below = style
            char_fmt.setFontPointSize(self.to_display(size))
            char_fmt.setFontWeight(weight)
            block_fmt.setTopMargin(self.to_display(above))
            block_fmt.setBottomMargin(self.to_display(below))

        cursor.setBlockFormat(block_fmt)
        cursor.setCharFormat(char_fmt)
        self.setTextCursor(cursor)

    def insert_table(self, rows: int, cols: int) -> None:
        """Insert Word's default table: as wide as the column, columns shared out."""
        cursor = self.textCursor()
        table_fmt = QTextTableFormat()
        table_fmt.setBorder(1)
        table_fmt.setBorderStyle(QTextTableFormat.BorderStyle.BorderStyle_Solid)
        table_fmt.setCellPadding(self.to_display(6))
        table_fmt.setCellSpacing(0)
        table_fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
        table_fmt.setColumnWidthConstraints(
            [QTextLength(QTextLength.Type.PercentageLength, 100.0 / max(1, cols))]
            * max(1, cols))
        table_fmt.setAlignment(Qt.AlignmentFlag.AlignLeft)
        cursor.insertTable(rows, cols, table_fmt)

    def insert_image(self, filepath: str, wrap: str = "inline",
                     width_px: Optional[float] = None,
                     height_px: Optional[float] = None) -> None:
        """Place a picture on the page, at a size the sheet can actually hold.

        Word never lets an image run past the margins and neither do we, because
        a wide screenshot used to swallow the whole column: the size is asked
        for, then fitted, then kept on the picture so the ribbon can show it.
        """
        natural = QImage(filepath)
        if natural.isNull():
            return
        wide, tall = _picture_size(width_px, height_px, natural.width(),
                                   natural.height(), self.printable_width_px)
        image = QTextImageFormat()
        image.setName(filepath)
        image.setWidth(self.to_display(wide))
        image.setHeight(self.to_display(tall))
        cursor = self.textCursor()
        self._exit_picture_frame(cursor)
        cursor.beginEditBlock()
        self._write_picture(cursor, image, wrap)
        cursor.endEditBlock()
        self.setTextCursor(cursor)

    def _exit_picture_frame(self, cursor: QTextCursor) -> None:
        """Step past a wrapped picture's frame before inserting anything.

        The caret stays on a picture after it is placed, so without this the
        next shape would be dropped inside the previous one's text run.
        """
        document = self.document()
        frame = cursor.currentFrame()
        if (frame is not None and frame != document.rootFrame()
                and frame.frameFormat().boolProperty(PICTURE_FRAME)):
            cursor.setPosition(min(document.characterCount() - 1,
                                   frame.lastPosition() + 1))

    def _write_picture(self, cursor: QTextCursor, image: QTextImageFormat,
                       wrap: str) -> None:
        """Lay *image* out at *cursor* the way *wrap* asks, leaving the caret on it."""
        image.setProperty(PICTURE_WRAP, wrap)
        if wrap in ("left", "right"):
            # Text runs past a floated frame; an inline character cannot do that.
            frame_format = QTextFrameFormat()
            frame_format.setPosition(
                QTextFrameFormat.Position.FloatLeft if wrap == "left"
                else QTextFrameFormat.Position.FloatRight)
            frame_format.setMargin(self.to_display(PICTURE_GAP_PX))
            frame_format.setBorder(0)
            frame_format.setPadding(0)
            frame_format.setWidth(image.width() + 2 * self.to_display(PICTURE_GAP_PX))
            frame_format.setProperty(PICTURE_FRAME, True)
            frame = cursor.insertFrame(frame_format)
            inner = QTextCursor(frame)
            inner.insertImage(image)
            cursor.setPosition(inner.position())
            return
        if cursor.block().text().strip():
            cursor.insertBlock()
        block_format = cursor.blockFormat()
        block_format.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # "Top and Bottom" is an inline picture with the lines beside it pushed
        # away, which is exactly what Word's spacing does for it.
        block_format.setTopMargin(self.to_display(12) if wrap == "top_bottom" else 0)
        block_format.setBottomMargin(self.to_display(12) if wrap == "top_bottom" else 0)
        cursor.setBlockFormat(block_format)
        cursor.insertImage(image)

    @property
    def printable_width_px(self) -> float:
        """The column between the margins, which is as wide as anything gets.

        Everything measured against it — paper, margins, picture sizes the ribbon
        shows — is in the sizes the document is written in, not the zoomed ones.
        """
        return max(1.0, self._base_width - 2 * self._margin_px)

    def _picture(self) -> Optional[_Picture]:
        """The picture the caret is on, or ``None`` when it is sitting in text."""
        document = self.document()
        caret = self.textCursor()
        root = document.rootFrame()
        last = document.characterCount() - 1
        for start in (caret.position() - 1, caret.position()):
            if not 0 <= start <= last:
                continue
            probe = QTextCursor(document)
            probe.setPosition(start)
            probe.setPosition(min(start + 1, last), QTextCursor.MoveMode.KeepAnchor)
            format_ = probe.charFormat()
            if not format_.isImageFormat():
                continue
            image = format_.toImageFormat()
            frame = probe.currentFrame()
            floated = (frame is not None and frame != root
                       and frame.frameFormat().boolProperty(PICTURE_FRAME))
            if floated:
                position = frame.frameFormat().position()
                side = "left" if position == QTextFrameFormat.Position.FloatLeft else "right"
                # The frame's own boundary characters have to go with it, or the
                # emptied frame stays on the page as a blank box.
                return _Picture(start=max(0, frame.firstPosition() - 1),
                                end=min(last, frame.lastPosition() + 1),
                                char=start, image=image, wrap=side, frame=frame)
            return _Picture(start=start, end=start + 1, char=start, image=image,
                            wrap=image.stringProperty(PICTURE_WRAP) or "inline")
        return None

    def picture_info(self) -> Optional[dict]:
        """The caret's picture as the ribbon shows it: centimetres and wrapping."""
        picture = self._picture()
        if picture is None:
            return None
        return {
            "path": picture.image.name(),
            "width_px": self.to_actual(picture.image.width()),
            "height_px": self.to_actual(picture.image.height()),
            "width_cm": self.to_actual(picture.image.width()) / PX_PER_CM,
            "height_cm": self.to_actual(picture.image.height()) / PX_PER_CM,
            "wrap": picture.wrap,
            "natural": _natural_size(picture.image.name()),
        }

    def set_picture_size(self, width_cm: Optional[float] = None,
                         height_cm: Optional[float] = None) -> bool:
        """Resize the caret's picture, keeping its shape unless both edges are given.

        The centimetres are the ones the ribbon shows and the sheet prints, so
        they hold whatever the view is zoomed to.
        """
        picture = self._picture()
        if picture is None or not (width_cm or height_cm):
            return False
        wide = (width_cm or 0) * PX_PER_CM
        tall = (height_cm or 0) * PX_PER_CM
        image = picture.image
        if wide and not tall:
            tall = wide * image.height() / max(1.0, image.width())
        elif tall and not wide:
            wide = tall * image.width() / max(1.0, image.height())
        wide, tall = _picture_size(wide, tall, wide, tall, self.printable_width_px)
        image.setWidth(self.to_display(wide))
        image.setHeight(self.to_display(tall))
        cursor = QTextCursor(self.document())
        cursor.setPosition(picture.char)
        cursor.setPosition(picture.char + 1, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(image)
        if picture.frame is not None:
            frame_format = picture.frame.frameFormat()
            frame_format.setWidth(image.width() + 2 * self.to_display(PICTURE_GAP_PX))
            picture.frame.setFrameFormat(frame_format)
        self.setTextCursor(cursor)
        self.document().setModified(True)
        return True

    def scale_picture(self, factor: float) -> bool:
        """Grow or shrink the caret's picture by a ratio, as Word's resize does."""
        picture = self._picture()
        if picture is None:
            return False
        return self.set_picture_size(
            self.to_actual(picture.image.width()) * factor / PX_PER_CM,
            self.to_actual(picture.image.height()) * factor / PX_PER_CM)

    def reset_picture_size(self) -> bool:
        """Back to the picture's own pixels, fitted to the column."""
        picture = self._picture()
        if picture is None:
            return False
        natural = _natural_size(picture.image.name())
        if natural is None:
            return False
        wide, tall = _picture_size(None, None, natural[0], natural[1],
                                   self.printable_width_px)
        return self.set_picture_size(wide / PX_PER_CM, tall / PX_PER_CM)

    def set_picture_wrap(self, wrap: str) -> bool:
        """Re-place the caret's picture so text runs around it, or does not."""
        picture = self._picture()
        if picture is None or wrap not in PICTURE_WRAPS or picture.wrap == wrap:
            return False
        image = picture.image
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        cursor.setPosition(picture.start)
        cursor.setPosition(picture.end, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.setPosition(min(picture.start, self.document().characterCount() - 1))
        self._write_picture(cursor, image, wrap)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.document().setModified(True)
        return True

    def set_picture_alignment(self, alignment: Qt.AlignmentFlag) -> bool:
        """Move an inline picture within the column; a wrapped one is placed by side."""
        picture = self._picture()
        if picture is None or picture.frame is not None:
            return False
        cursor = QTextCursor(self.document())
        cursor.setPosition(picture.start)
        block_format = cursor.blockFormat()
        block_format.setAlignment(alignment)
        cursor.setBlockFormat(block_format)
        self.document().setModified(True)
        return True

    # -- objects lying on the sheet ------------------------------------------ #

    def insert_float(self, filepath: str, x_cm: Optional[float] = None,
                     y_cm: Optional[float] = None,
                     width_cm: Optional[float] = None,
                     height_cm: Optional[float] = None,
                     wrap: bool = True) -> bool:
        """Lay a picture on the sheet at its own position, beside the caret.

        Word drops a new object where the writing is, not at the top of the
        page, and the ribbon's boxes then edit that place. Missing measurements
        come from the picture's own pixels, never wider than the column.
        """
        natural = _natural_size(filepath)
        if natural is None:
            return False
        wide, tall = _picture_size(
            (width_cm or 0) * PX_PER_CM or None,
            (height_cm or 0) * PX_PER_CM or None,
            natural[0], natural[1], self.printable_width_px)
        wide_cm, tall_cm = wide / PX_PER_CM, tall / PX_PER_CM
        if x_cm is None:
            x_cm = self.margin_pixels / PX_PER_CM
        if y_cm is None:
            y_cm = self._block_top_cm(self.document().findBlock(
                self.textCursor().position()))
        widget = FloatPictureWidget(filepath, self, x_cm, y_cm, wide_cm, tall_cm,
                                     wrap, self.viewport())
        widget.geometryChanged.connect(self._floats_moved)
        self._floats.append(widget)
        widget.show()
        self.select_float(widget)
        self.anchor_float(widget)
        widget.raise_()
        self.tie_text_round_floats()
        self.document().setModified(True)
        return True

    def floats(self) -> list:
        """The objects on this sheet, front one last."""
        return list(self._floats)

    def float_info(self) -> Optional[dict]:
        """The chosen object as the ribbon shows it: centimetres and wrapping."""
        widget = self._selected_float
        if widget is None:
            return None
        return {
            "path": widget.filepath,
            "x_cm": widget.x_cm,
            "y_cm": widget.y_cm,
            "width_cm": widget.width_cm,
            "height_cm": widget.height_cm,
            "wrap": widget.wrap,
            "natural": _natural_size(widget.filepath),
        }

    def select_float(self, widget: FloatPictureWidget) -> None:
        if self._selected_float is widget:
            return
        for other in self._floats:
            other.selected = other is widget
        self._selected_float = widget
        self.floatSelectionChanged.emit()

    def clear_float_selection(self) -> None:
        if self._selected_float is None:
            return
        for widget in self._floats:
            widget.selected = False
        self._selected_float = None
        self.floatSelectionChanged.emit()

    def set_float_geometry(self, x_cm: Optional[float] = None,
                           y_cm: Optional[float] = None,
                           width_cm: Optional[float] = None,
                           height_cm: Optional[float] = None) -> bool:
        """Place or stretch the chosen object; one edge alone keeps its shape.

        Nothing is allowed off the sheet: an object the reader cannot reach is
        an object they cannot click, and Word keeps it on the paper.
        """
        widget = self._selected_float
        if widget is None:
            return False
        wide = widget.width_cm if width_cm is None else width_cm
        tall = widget.height_cm if height_cm is None else height_cm
        ratio = widget.height_cm / max(0.01, widget.width_cm)
        if width_cm is not None and height_cm is None:
            tall = wide * ratio
        elif height_cm is not None and width_cm is None:
            wide = tall / max(0.01, ratio)
        wide = min(wide, self.paper_width_cm())
        tall = min(tall, self.limit_top_cm())
        left = widget.x_cm if x_cm is None else x_cm
        top = widget.y_cm if y_cm is None else y_cm
        widget.set_rect_cm(min(max(0.0, left), self.paper_width_cm() - wide),
                           min(max(0.0, top), self.limit_top_cm() - tall),
                           wide, tall)
        self.anchor_float(widget)
        self.document().setModified(True)
        return True

    def set_float_wrap(self, wraps: bool) -> bool:
        """Let the words run round the object, or let them lie under it."""
        widget = self._selected_float
        if widget is None or widget.wrap == wraps:
            return False
        widget.wrap = wraps
        self.tie_text_round_floats()
        self.floatSelectionChanged.emit()
        self.document().setModified(True)
        return True

    def move_float_z(self, step: int) -> bool:
        """Cross the chosen object in front of, or behind, its neighbours.

        ``QTextEdit`` gives its viewport no child ordering, so the stack is
        rebuilt from the model each time: raising every object in turn leaves
        the one at the back of the list on top.
        """
        if self._selected_float is None or step == 0:
            return False
        index = self._floats.index(self._selected_float)
        target = min(max(0, index + step), len(self._floats) - 1)
        if target == index:
            return False
        self._floats.insert(target, self._floats.pop(index))
        for widget in self._floats:
            widget.raise_()
        self.document().setModified(True)
        return True

    def remove_float(self) -> bool:
        """Take the chosen object off the sheet, and let its lines close up."""
        widget = self._selected_float
        if widget is None:
            return False
        self._floats.remove(widget)
        widget.deleteLater()
        self._selected_float = None
        self.tie_text_round_floats()
        self.floatSelectionChanged.emit()
        self.document().setModified(True)
        return True

    def clear_floats(self) -> None:
        """Take every object off, as a newly opened document asks."""
        for widget in self._floats:
            widget.deleteLater()
        self._floats = []
        self._selected_float = None
        self._block_cursor.beginEditBlock()
        self._release_clearances()
        self._block_cursor.endEditBlock()
        self.floatSelectionChanged.emit()

    def float_draw_list(self) -> list:
        """(centimetres from the sheet edges, picture) for each object, back first."""
        return [(widget.rect_cm, widget.filepath) for widget in self._floats]

    def paper_width_cm(self) -> float:
        """The sheet's own width, which is what the ribbon measures across."""
        return self._base_width / PX_PER_CM

    def limit_top_cm(self) -> float:
        """The furthest down an object may be put and still be on the sheet.

        The sheet is as long as the paper it prints on, or as the writing that
        runs past it, whichever is further: an object dropped on an empty page
        still belongs on that page.
        """
        written = self.to_actual(self.document().size().height())
        return max(self._base_height, written) / PX_PER_CM

    def anchor_float(self, widget: FloatPictureWidget) -> None:
        """Hang the object on the paragraph it now covers.

        A page grows as it is written on, and an object pinned to nothing would
        be left behind by the passage it was placed beside. Word's answer is an
        anchor: the object keeps its distance from a paragraph, and moves when
        the paragraph does.
        """
        block = self._block_covering(widget.y_cm)
        if block is None:
            return
        anchor = QTextCursor(self.document())
        anchor.setPosition(block.position())
        widget.anchor = anchor
        widget.anchor_offset_cm = widget.y_cm - self._block_top_cm(block)

    def _relayout_floats(self) -> None:
        """The sheet or the zoom changed under the objects: measure them again."""
        for widget in self._floats:
            widget.relayout()

    def scroll_offset_px(self) -> float:
        """How far the sheet has been carried up out of sight.

        The viewport reports places relative to what is showing, so the
        absolute centimetres the ribbon edits have to be moved by this to be
        painted where the reader can see them.
        """
        return self.verticalScrollBar().value()

    def _block_top_cm(self, block) -> float:
        """Where a paragraph begins, measured from the top edge of the sheet."""
        if not block.isValid():
            return 0.0
        cursor = QTextCursor(self.document())
        cursor.setPosition(block.position())
        return self._cm_below_top(self.cursorRect(cursor).top()) - self._pushed_cm(
            block.blockFormat())

    def _pushed_cm(self, format_) -> float:
        """How far an object has already sent this paragraph down.

        A paragraph that a full-width object sits above is held back by its own
        top margin, and the objects are measured against where the paragraph
        would begin without that clearance: otherwise the object follows the
        room it made, makes more, and the two never settle.
        """
        margin_cm = self.to_actual(format_.topMargin()) / PX_PER_CM
        return max(0.0, margin_cm - self._base_cm(format_, FLOAT_BASE_TOP,
                                                 format_.topMargin()))

    def _cm_below_top(self, viewport_px: float) -> float:
        """A place in the viewport as the centimetres down the sheet it is."""
        return self.to_actual(viewport_px + self.scroll_offset_px()) / PX_PER_CM

    def _block_covering(self, y_cm: float):
        """The paragraph whose lines sit at *y_cm* down the sheet.

        An object below all the writing, or above its first line, has no
        paragraph to cover, so it hangs on the nearest one and follows that.
        """
        document = self.document()
        nearest = None
        gap = None
        block = document.begin()
        while block.isValid():
            top, bottom = self._block_band_cm(block)
            distance = (0.0 if top <= y_cm < bottom
                        else min(abs(y_cm - top), abs(y_cm - bottom)))
            if gap is None or distance < gap:
                nearest, gap = block, distance
            block = block.next()
        return nearest

    def _block_band_cm(self, block) -> tuple:
        """(first line, last line) of a paragraph, in centimetres down the sheet.

        Measured where the paragraph would sit without the clearance the objects
        gave it, which is the place an object hanging on it is measured from.
        """
        if not block.isValid():
            return (0.0, 0.0)
        document = self.document()
        start = QTextCursor(document)
        start.setPosition(block.position())
        end = QTextCursor(document)
        end.setPosition(min(block.position() + max(0, block.length() - 1),
                            document.characterCount() - 1))
        pushed = self._pushed_cm(block.blockFormat())
        top = self._cm_below_top(self.cursorRect(start).top()) - pushed
        bottom = self._cm_below_top(self.cursorRect(end).bottom()) - pushed
        return (top, max(top, bottom))

    def _floats_moved(self) -> None:
        """An object was dragged: the lines, and the ribbon, must follow it."""
        self.floatGeometryChanged.emit()
        if self._tying_floats:
            return
        self.tie_text_round_floats()

    def tie_text_round_floats(self) -> None:
        """Re-measure the paragraphs, now that the objects have moved.

        Laying out is deferred to the next turn of the event loop because the
        viewport is asked for paragraph places it can only know once the text
        it holds has been measured.
        """
        if self._tying_floats:
            # Our own clearing of the margins is a change to the document, and
            # answering it with another pass would never stop.
            return
        QTimer.singleShot(0, self._tie_now)

    def _tie_now(self) -> None:
        # A paragraph's place is only known once the text has been measured
        # against a viewport that has a width, so an unwinnable tie is left
        # until the sheet is on screen.
        if self._tying_floats or self.viewport().width() <= 1:
            return
        self._tying_floats = True
        try:
            self._follow_anchors()
            for _ in range(FLOAT_SETTLE_PASSES):
                if not self._reserve_round_floats():
                    break
        finally:
            self._tying_floats = False

    def _follow_anchors(self) -> None:
        """Carry each object with the paragraph it is hung on."""
        for widget in self._floats:
            if widget.anchor is None:
                continue
            block = self.document().findBlock(widget.anchor.position())
            if not block.isValid():
                continue
            target = self._block_top_cm(block) + widget.anchor_offset_cm
            if abs(target - widget.y_cm) > ANCHOR_DRIFT_CM:
                widget.y_cm = target
                widget.relayout()

    def _reserve_round_floats(self) -> bool:
        """Push the lines clear of every wrapped object; did anything move?

        A paragraph keeps the indent it was given and takes the clearance the
        objects ask for on top, so the two are stored apart: the clearance is
        written as the margin and the paragraph's own indent rides in the
        format as :data:`FLOAT_BASE_LEFT` and :data:`FLOAT_BASE_RIGHT`.
        """
        document = self.document()
        wanted = []
        block = document.begin()
        while block.isValid():
            format_ = block.blockFormat()
            band = self._block_band_cm(block)
            left, right, below = self._clearance_cm_at(*band)
            base_left = self._base_cm(format_, FLOAT_BASE_LEFT,
                                      format_.leftMargin())
            base_right = self._base_cm(format_, FLOAT_BASE_RIGHT,
                                       format_.rightMargin())
            base_top = self._base_cm(format_, FLOAT_BASE_TOP, format_.topMargin())
            want_left = self.to_display((base_left + left) * PX_PER_CM)
            want_right = self.to_display((base_right + right) * PX_PER_CM)
            want_top = self.to_display((base_top + below) * PX_PER_CM)
            if (abs(format_.leftMargin() - want_left) > 1
                    or abs(format_.rightMargin() - want_right) > 1
                    or abs(format_.topMargin() - want_top) > 1):
                format_.setProperty(FLOAT_BASE_LEFT, base_left)
                format_.setProperty(FLOAT_BASE_RIGHT, base_right)
                format_.setProperty(FLOAT_BASE_TOP, base_top)
                format_.setLeftMargin(want_left)
                format_.setRightMargin(want_right)
                format_.setTopMargin(want_top)
                wanted.append((block.position(), format_))
            block = block.next()
        if not wanted:
            # Writing an edit block that changes nothing would set off another
            # round of this method through the document's own changed signal.
            return False
        self._block_cursor.beginEditBlock()
        for position, format_ in wanted:
            self._block_cursor.setPosition(position)
            self._block_cursor.setBlockFormat(format_)
        self._block_cursor.endEditBlock()
        return True

    def _base_cm(self, format_, key: int, margin_px: float) -> float:
        """The indent a paragraph was written with, in centimetres.

        The clearance an object asks for is written on top of it, so the two are
        kept apart: a paragraph no object has ever touched carries only its own
        margin, which is read back as the indent.
        """
        stored = format_.property(key)
        if stored is None:
            return self.to_actual(margin_px) / PX_PER_CM
        return float(stored)

    def _release_clearances(self) -> None:
        """Hand every paragraph back its own indent, with no objects left."""
        document = self.document()
        block = document.begin()
        while block.isValid():
            format_ = block.blockFormat()
            if format_.property(FLOAT_BASE_LEFT) is not None:
                for key, setter, getter in (
                        (FLOAT_BASE_LEFT, "setLeftMargin", "leftMargin"),
                        (FLOAT_BASE_RIGHT, "setRightMargin", "rightMargin"),
                        (FLOAT_BASE_TOP, "setTopMargin", "topMargin")):
                    getattr(format_, setter)(self.to_display(
                        self._base_cm(format_, key, getattr(format_, getter)())
                        * PX_PER_CM))
                self._block_cursor.setPosition(block.position())
                self._block_cursor.setBlockFormat(format_)
            block = block.next()

    def _clearance_cm_at(self, top_cm: float, bottom_cm: float) -> tuple:
        """How far the lines at this height must step back, and how far down.

        An object with the words running round it takes the side of the column
        it lies on. When it spans nearly the whole width there is no side left
        to step back to, and Word sends the line below it instead.
        """
        left = right = below = 0.0
        margin_cm = self.margin_pixels / PX_PER_CM
        column_cm = self.printable_width_px / PX_PER_CM
        for widget in self._floats:
            if not widget.wrap:
                continue
            if widget.y_cm >= bottom_cm or widget.y_cm + widget.height_cm <= top_cm:
                continue
            if widget.width_cm >= column_cm - MIN_SIZE_CM:
                # Nothing is left of the column for a line to squeeze through,
                # so the line goes below the object instead of beside it.
                below = max(below, widget.y_cm + widget.height_cm + WRAP_GAP_CM
                            - top_cm)
                continue
            if widget.x_cm + widget.width_cm / 2 < self.paper_width_cm() / 2:
                left = max(left, widget.x_cm + widget.width_cm + WRAP_GAP_CM
                           - margin_cm)
            else:
                right = max(right, self.paper_width_cm() - margin_cm
                            - widget.x_cm + WRAP_GAP_CM)
        if left + right > column_cm - MIN_SIZE_CM:
            left, right = (left, 0.0) if left > right else (0.0, right)
        return (max(0.0, left), max(0.0, right), max(0.0, below))

    # -- the sheet, under the objects --------------------------------------- #

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        # Anything that reaches the text reached it past every object, so the
        # chosen one -- if there was one -- goes back on the sheet unmarked.
        self.clear_float_selection()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        key = event.key()
        if self._selected_float is not None and key in (
                Qt.Key.Key_Delete, Qt.Key.Key_Backspace, Qt.Key.Key_Escape):
            if key == Qt.Key.Key_Escape:
                self.clear_float_selection()
            else:
                self.remove_float()
            return
        super().keyPressEvent(event)

    def insert_equation(self, expression: str) -> None:
        """Insert Unicode maths at the cursor, set in Word's equation face.

        The expression is plain text (see :mod:`officer.writer.unicode_math`),
        so it stays searchable and correctable; only the run's formatting says
        "equation". A letter with no letter beside it is a variable, and Word
        italicises those. A script Unicode has no raised form for -- there is no
        superscript pi -- is lifted by the run's vertical alignment instead.
        """
        if not expression:
            return
        runs = to_math_runs(expression)
        # What the document holds: the typed scripts without their markers.
        plain = "".join(piece for piece, _ in runs)
        cursor = self.textCursor()
        families = math_font(11).families()
        size = self.to_display(self.current_font_point_size() or 11.0)
        raised = {1: QTextCharFormat.VerticalAlignment.AlignSuperScript,
                  -1: QTextCharFormat.VerticalAlignment.AlignSubScript}
        cursor.beginEditBlock()
        offset = 0
        for piece, script in runs:
            alignment = raised.get(script,
                                   QTextCharFormat.VerticalAlignment.AlignNormal)
            start = 0
            for index in range(1, len(piece) + 1):
                if (index == len(piece)
                        or _is_variable(plain, offset + index)
                        != _is_variable(plain, offset + start)):
                    fmt = QTextCharFormat()
                    fmt.setFontFamilies(families)
                    fmt.setFontPointSize(size)
                    fmt.setFontItalic(_is_variable(plain, offset + start))
                    fmt.setVerticalAlignment(alignment)
                    cursor.insertText(plain[offset + start:offset + index], fmt)
                    start = index
            offset += len(piece)
        cursor.endEditBlock()
        self.setTextCursor(cursor)


class RulerWidget(QWidget):
    """
    Word's horizontal ruler: grey margin gutters, inch ticks with numbers,
    eighth-inch subdivisions and the three indent markers.
    """

    HEIGHT = 22

    def __init__(self, page: Optional["DocumentPageWidget"] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("RulerStrip")
        self.setFixedHeight(self.HEIGHT)
        self._page = page
        self._zoom = 1.0

    def set_page(self, page: "DocumentPageWidget") -> None:
        self._page = page

    def set_zoom(self, zoom: float) -> None:
        self._zoom = zoom
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colors = ThemeManager.instance().colors("writer")

        page = self._page
        margin = (page.margin_pixels if page else 96) * self._zoom
        ppi = 96 * self._zoom
        width = self.width()
        height = self.height()
        right_gutter = max(0, width - margin)

        # Surface + the grey gutters Word uses for the page margins.
        painter.fillRect(0, 0, width, height, QColor(colors.surface))
        painter.fillRect(0, 0, margin, height, QColor(colors.window))
        if right_gutter > margin:
            painter.fillRect(right_gutter, 0, width - right_gutter, height, QColor(colors.window))

        ink = QColor(colors.text_secondary)
        tick_pen = QPen(ink, 1)
        painter.setPen(tick_pen)
        painter.drawLine(0, height - 1, width, height - 1)

        # Inch ticks with numbers, eighth-inch ticks between them.
        font = painter.font()
        font.setPixelSize(9)
        font.setFamily("Segoe UI")
        painter.setFont(font)
        x = margin
        inch = 0
        while x <= width + 1:
            painter.drawLine(int(x) + 0.5, height - 8, int(x) + 0.5, height - 1)
            if inch > 0:
                painter.drawText(QRectF(x - 9, 1, 18, 9),
                                 Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                                 str(inch))
            for eighths in range(1, 8):
                mx = x + eighths * ppi / 8.0
                if mx > width:
                    break
                half = height - 5 if eighths == 4 else height - 3
                painter.drawLine(int(mx) + 0.5, half, int(mx) + 0.5, height - 1)
            x += ppi
            inch += 1

        # The three indent markers: left indent, first line, right indent.
        indent_px = margin
        hanging_px = margin
        if page is not None:
            block_indent = page.textCursor().blockFormat().indent()
            list_indent = 0.0
            current_list = page.textCursor().currentList()
            if current_list is not None:
                list_indent = current_list.format().indent()
            step = 0.5 * ppi * max(block_indent, list_indent)
            indent_px = margin + step
            hanging_px = margin + step if block_indent == 0 else margin
        marker = QPen(QColor(colors.text), 1)
        painter.setPen(marker)
        painter.setBrush(QBrush(QColor(colors.text)))

        # first-line marker (points down from the top edge)
        painter.drawPolygon([
            QPointF(indent_px - 4, 1), QPointF(indent_px + 4, 1), QPointF(indent_px, 7)
        ])
        # left indent + hanging marker (point up from the bottom edge)
        painter.drawPolygon([
            QPointF(hanging_px - 4, height - 8), QPointF(hanging_px + 4, height - 8),
            QPointF(hanging_px, height - 2)
        ])
        painter.drawRect(QRectF(indent_px - 4, height - 11, 8, 4))
        # right indent marker, at the right margin rather than the paper edge
        right_x = max(margin + 8, width - margin)
        painter.drawPolygon([
            QPointF(right_x + 4, height - 11), QPointF(right_x - 4, height - 8),
            QPointF(right_x + 4, height - 5)
        ])
        painter.end()


class DocumentWorkspace(QScrollArea):
    """Scrollable page canvas: the ruler strip plus the centered paper."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("DocumentWorkspace")
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Centering canvas container
        self.canvas = QWidget(self)
        self.canvas.setObjectName("PageCanvas")
        self.canvas.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.canvas_layout = QVBoxLayout(self.canvas)
        self.canvas_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.canvas_layout.setContentsMargins(40, 12, 40, 40)
        self.canvas_layout.setSpacing(0)

        self.page = DocumentPageWidget(self.canvas)

        # Ruler above the page (Word shows it by default; Ctrl+R toggles it).
        self.ruler = RulerWidget(self.page, self.canvas)
        self.canvas_layout.addWidget(self.ruler, 0, Qt.AlignmentFlag.AlignHCenter)
        self.canvas_layout.addWidget(self.page)

        self.setWidget(self.canvas)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._web_layout = False
        self.sync_page_geometry()
        self.ruler.setVisible(True)

        # Keep the ruler honest as the caret moves between indented blocks.
        self.page.cursorPositionChanged.connect(self.ruler.update)

    # -- geometry ----------------------------------------------------------- #

    def sync_page_geometry(self) -> None:
        """Match the ruler's width to the page, including the current zoom."""
        self.ruler.setFixedWidth(self.page.width())
        self.ruler.set_zoom(self.page._zoom_factor)

    def set_ruler_visible(self, visible: bool) -> None:
        self.ruler.setVisible(visible)
        self.sync_page_geometry()

    # -- Word's view modes -------------------------------------------------- #

    def set_web_layout(self, enabled: bool) -> None:
        """Web Layout lets the page fill the window instead of a paper column."""
        self._web_layout = enabled
        if enabled:
            self.page.setFixedWidth(max(320, self.viewport().width() - 40))
            self.canvas_layout.setContentsMargins(20, 8, 20, 24)
        else:
            self.page.setFixedWidth(int(self.page._base_width * self.page._zoom_factor))
            self.canvas_layout.setContentsMargins(40, 12, 40, 40)
        self.sync_page_geometry()

    def set_read_mode(self, enabled: bool) -> None:
        """Read Mode: comfortable measure, no ruler, no page gutters."""
        if enabled:
            self.ruler.setVisible(False)
            self.page.setFixedWidth(min(760, max(420, self.viewport().width() - 160)))
            self.canvas_layout.setContentsMargins(24, 16, 24, 32)
        else:
            self.page.setFixedWidth(int(self.page._base_width * self.page._zoom_factor))
            self.canvas_layout.setContentsMargins(40, 12, 40, 40)
            self.ruler.setVisible(True)
        self.sync_page_geometry()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._web_layout:
            self.set_web_layout(True)

    def fit_page_to_window(self) -> int:
        """Zoom so the printable page just fits the viewport; returns the percent."""
        available = max(200, self.viewport().width() - 96)
        percent = int(round(100.0 * available / max(1, self.page._base_width)))
        return max(10, min(400, percent))
