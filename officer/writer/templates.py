"""Ready-dressed documents: the pages WriteR's gallery opens.

A template here is data, not a stored file. Each one is a list of blocks --
paragraphs, bands, lists, tables, gaps, page breaks -- plus the sheet it wants
cut to and the dress that sheet wears. :class:`Template` knows how to write its
blocks into any :class:`QTextDocument`, and :func:`build_tiles` shows each
design by writing it into a real page and photographing the result, so a tile
in the gallery cannot promise a layout the sheet would not keep.

Two units are at work, and mixing them up is the classic way to get this wrong:
type is measured in **points**, exactly as Word measures it, while the sheet and
everything placed on it are measured in the **96-to-the-inch pixels** WriteR
lays paper out in.

This Qt offers no paragraph border and no keep-with-next, so the horizontal
rules a design leans on are bands of ink: a block whose only face is a few
points tall, painted behind itself. That is why :class:`Rule` spaces itself with
blocks of bare paper either side rather than with margins, which a block's
background would otherwise swallow.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import (QBrush, QColor, QFont, QImage, QPainter, QPixmap,
                           QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextLength, QTextListFormat,
                           QTextTableFormat)

from officer.core.ui.fonts import BODY_CHAIN, family_chain
from officer.core.ui.template_gallery import GalleryEntry
from officer.writer.header_footer import bands_setting
from officer.writer.page_border import DEFAULT_COLOUR as BORDER_COLOUR
from officer.writer.watermark import watermark_mark
from officer.writer.document_view import PAPER_SIZES, PX_PER_CM

#: The ink a template's writing is set in, unless the design says otherwise.
INK = "#1F2937"

#: The grey a design puts its asides, captions and labels in.
MUTED = "#6B7280"

#: The rules that separate a design's parts: quiet, so the type carries the page.
HAIRLINE = "#D1D5DB"

#: Word's own blue and its pale wash, which is what a table head is shaded with
#: when a design has no accent of its own.
ACCENT = "#2B579A"
ACCENT_WASH = "#EDF1F8"

#: Two face chains: the serif designs and the sans ones. A machine without
#: Word's fonts substitutes from the names after the first.
SERIF_CHAIN: Tuple[str, ...] = ("Cambria", "Georgia", "Caladea", "Tinos",
                                "Liberation Serif", "DejaVu Serif")
SANS_CHAIN: Tuple[str, ...] = BODY_CHAIN

#: How a design names a line of text, in Qt's words.
ALIGNMENTS = {
    "left": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute,
    "centre": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute,
    "justify": Qt.AlignmentFlag.AlignJustify,
}

#: A band has to have a face to be measured by; this one is hair-thin.
BAND_FACE_PT = 1.0

#: How wide the gallery's tiles are, which is how a sheet is photographed.
TILE_WIDTH = 188


# --------------------------------------------------------------------------- #
# blocks                                                                       #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Text:
    """One paragraph, or several when the text holds a newline.

    Every field left at ``None`` falls back to the design's own body settings,
    so a template states only what makes it different. ``above``, ``below``,
    ``left``, ``right``, ``first`` and ``narrow`` are pixels of the sheet;
    ``size`` is points and ``tracking`` per cent of extra air between the faces.
    """

    text: str
    size: Optional[float] = None
    bold: Optional[bool] = None
    italic: Optional[bool] = None
    underline: Optional[bool] = None
    colour: Optional[str] = None
    family: Optional[Tuple[str, ...]] = None
    align: Optional[str] = None
    above: float = 0.0
    below: float = 0.0
    spacing: Optional[float] = None
    left: Optional[float] = None
    right: Optional[float] = None
    first: float = 0.0
    narrow: float = 0.0
    caps: bool = False
    tracking: float = 0.0
    fill: str = ""
    fill_ink: str = ""
    pad_above: float = 0.0
    pad_below: float = 0.0


@dataclass(frozen=True)
class Rule:
    """A band of ink across part of the column: the design's horizontal rule.

    *weight* is points, which is what a band of face is measured in.
    """

    colour: str = HAIRLINE
    weight: float = 1.0
    width_pct: float = 100.0
    align: str = "left"
    above: float = 5.0
    below: float = 9.0


@dataclass(frozen=True)
class Bullets:
    """A real list, so the writer can carry on typing bullets inside it.

    ``numbered`` asks for Word's 1. 2. 3. instead of the discs.
    """

    items: Sequence[str]
    size: Optional[float] = None
    colour: Optional[str] = None
    family: Optional[Tuple[str, ...]] = None
    above: float = 0.0
    below: float = 0.0
    spacing: Optional[float] = None
    numbered: bool = False
    indent: float = 22.0
    bold: Optional[bool] = None


@dataclass(frozen=True)
class Table:
    """A grid of words: a shaded head, and figures kept off the left edge.

    ``widths`` shares out the column as percentages of the printable run, which
    is what lets an invoice's description take most of the page while its money
    stays narrow. ``aligns`` is one letter per column.
    """

    rows: Sequence[Sequence[str]]
    widths: Sequence[float] = ()
    aligns: str = ""
    header: bool = True
    shade: str = ACCENT_WASH
    stripe: str = ""
    rule: str = HAIRLINE
    ink: Optional[str] = None
    head_ink: Optional[str] = None
    size: float = 10.5
    family: Optional[Tuple[str, ...]] = None
    pad: float = 6.0
    above: float = 6.0
    below: float = 12.0
    bold_cells: Tuple[Tuple[int, int], ...] = ()
    head_bold: bool = True


@dataclass(frozen=True)
class Gap:
    """Bare paper: the white space a design asks for by name."""

    px: float = 12.0


@dataclass(frozen=True)
class PageBreak:
    """Start the next block on a fresh sheet, as Word's break does."""


Block = Union[Text, Rule, Bullets, Table, Gap, PageBreak]


# --------------------------------------------------------------------------- #
# writing one block                                                            #
# --------------------------------------------------------------------------- #

def _char_format(size: float, bold: bool, italic: bool, colour: str,
                 family: Sequence[str], underline: bool = False,
                 tracking: float = 0.0) -> QTextCharFormat:
    """A run's chain of faces, its weight, its ink and its point size."""
    fmt = QTextCharFormat()
    chain = family_chain(family)
    if chain:
        fmt.setFontFamilies(chain)
    fmt.setFontPointSize(max(0.5, float(size)))
    fmt.setFontWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
    fmt.setFontItalic(bool(italic))
    fmt.setFontUnderline(bool(underline))
    fmt.setForeground(QColor(colour))
    if tracking:
        # Qt's letter spacing is a percentage of the face's own spacing, so 1.0
        # is not a point of air but a hundredth of it -- and text set that way
        # collapses into a smudge. One hundred is the way a face comes.
        fmt.setFontLetterSpacing(100.0 + float(tracking))
    return fmt


def _set_line_height(fmt: QTextBlockFormat, spacing: float) -> None:
    """Ask for *spacing* lines' height per line, the way Word's 1.15 means it.

    PySide6 binds :meth:`QTextBlockFormat.setLineHeight` with the height first
    and the type second, which is the opposite of the C++ signature a reader
    would expect; handing it the two the other way round leaves the type reading
    as a percentage and every block one point tall.
    """
    fmt.setLineHeight(spacing * 100.0,
                     QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)


def _is_dark(colour: str) -> bool:
    """Whether an ink is dark enough to need light words on it."""
    rgb = QColor(colour)
    return (0.299 * rgb.red() + 0.587 * rgb.green() + 0.114 * rgb.blue()) < 140


def _paragraph_format(template: "Template", block: Text) -> QTextBlockFormat:
    """A paragraph's own box: where it sits on the sheet, and what is behind it."""
    fmt = QTextBlockFormat()
    align = ALIGNMENTS.get(block.align or "left", ALIGNMENTS["left"])
    fmt.setAlignment(align)
    fmt.setTopMargin(max(0.0, block.above))
    fmt.setBottomMargin(max(0.0, block.below))
    spacing = block.spacing if block.spacing is not None else template.spacing
    if spacing and abs(spacing - 1.0) > 0.001:
        _set_line_height(fmt, spacing)
    left = block.left if block.left is not None else 0.0
    right = block.right if block.right is not None else 0.0
    if block.narrow:
        # A short line is a column the design wanted narrower than the sheet,
        # pinned to whichever margin its alignment reads from.
        spare = max(0.0, template.column_px - block.narrow)
        if align & Qt.AlignmentFlag.AlignRight:
            left = spare
        elif align & Qt.AlignmentFlag.AlignHCenter:
            left = right = spare / 2.0
        else:
            right = spare
    fmt.setLeftMargin(left)
    fmt.setRightMargin(right)
    fmt.setTextIndent(block.first)
    if block.fill:
        fmt.setBackground(QColor(block.fill))
    return fmt


def _band_format(template: "Template", block: Rule) -> QTextBlockFormat:
    """The box a rule is painted in, with no margins for its ink to swallow."""
    fmt = QTextBlockFormat()
    fmt.setAlignment(ALIGNMENTS.get(block.align, ALIGNMENTS["left"]))
    fmt.setTopMargin(0)
    fmt.setBottomMargin(0)
    spare = max(0.0, template.column_px * (100.0 - block.width_pct) / 100.0)
    if fmt.alignment() & Qt.AlignmentFlag.AlignRight:
        fmt.setLeftMargin(spare)
    elif fmt.alignment() & Qt.AlignmentFlag.AlignHCenter:
        fmt.setLeftMargin(spare / 2.0)
        fmt.setRightMargin(spare / 2.0)
    else:
        fmt.setRightMargin(spare)
    fmt.setBackground(QColor(block.colour))
    return fmt


def _spacer_format(px: float) -> QTextBlockFormat:
    """An empty block that asks for *px* of bare paper and nothing else."""
    fmt = QTextBlockFormat()
    fmt.setAlignment(ALIGNMENTS["left"])
    fmt.setTopMargin(0)
    fmt.setBottomMargin(max(0.0, px))
    fmt.setLeftMargin(0)
    fmt.setRightMargin(0)
    return fmt


def _write_list(cursor: QTextCursor, template: "Template", block: Bullets) -> None:
    """Write a list as one :class:`QTextList`, not as typed characters.

    A template's bullets have to stay bullets: whoever continues the list
    expects the next line to take its marker on its own.
    """
    size = block.size if block.size is not None else template.body_size
    char = _char_format(size, bool(block.bold), False,
                        block.colour or template.ink,
                        block.family or template.body_family)
    start = cursor.position()
    for index, item in enumerate(block.items):
        para = QTextBlockFormat()
        para.setAlignment(ALIGNMENTS["left"])
        para.setTopMargin(template.space_list if index else max(0.0, block.above))
        para.setBottomMargin(0 if index + 1 < len(block.items) else block.below)
        para.setLeftMargin(block.indent)
        spacing = block.spacing if block.spacing is not None else template.spacing
        if spacing and abs(spacing - 1.0) > 0.001:
            _set_line_height(para, spacing)
        if index:
            cursor.insertBlock(para, char)
        else:
            cursor.setBlockFormat(para)
        cursor.insertText(item, char)
    list_fmt = QTextListFormat()
    list_fmt.setStyle(QTextListFormat.Style.ListDecimal if block.numbered
                      else QTextListFormat.Style.ListDisc)
    list_fmt.setIndent(1)
    # The whole run of items is selected before the list is made, because
    # ``createList`` takes the blocks the selection covers -- and only those.
    end = cursor.position()
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    cursor.createList(list_fmt)
    cursor.clearSelection()


def _shade_cell(cell, colour: str) -> None:
    """Put an ink behind a whole cell, not merely behind its words.

    This Qt hands back a cell's format as a char format, and shading a cell goes
    through :meth:`QTextTableCell.setFormat` rather than a frame format.
    """
    fmt = cell.format()
    fmt.setBackground(QColor(colour))
    cell.setFormat(fmt)


def _column_align(aligns: str, column: int) -> str:
    """The letter this column asked for, or left for anything not spelled out."""
    letter = aligns[column].lower() if column < len(aligns) else "l"
    return {"l": "left", "c": "centre", "r": "right"}.get(letter, "left")


def _leave_table(cursor: QTextCursor, table) -> None:
    """Put the cursor on the paragraph after *table*, making one if there is none.

    A fresh table leaves the cursor in its last cell, where the next block of the
    design would otherwise be written as another line of that cell -- which is
    how a heading ended up squeezed inside an invoice's fourth column.
    """
    cursor.setPosition(table.lastPosition())
    cursor.movePosition(QTextCursor.MoveOperation.NextBlock)
    if cursor.currentTable() is not None:
        cursor.insertBlock()


def _write_table(cursor: QTextCursor, template: "Template", block: Table) -> None:
    """Insert the grid, shade its head, and set every word in its own cell."""
    rows = [list(row) for row in block.rows]
    if not rows:
        return
    cols = max(len(row) for row in rows)
    fmt = QTextTableFormat()
    fmt.setBorder(1)
    fmt.setBorderStyle(QTextTableFormat.BorderStyle.BorderStyle_Solid)
    fmt.setBorderBrush(_q_brush(block.rule))
    fmt.setCellPadding(block.pad)
    fmt.setCellSpacing(0)
    fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
    shares = list(block.widths) or [100.0 / cols] * cols
    shares += [0.0] * max(0, cols - len(shares))
    total = float(sum(shares)) or 100.0
    fmt.setColumnWidthConstraints(
        [QTextLength(QTextLength.Type.PercentageLength, 100.0 * share / total)
         for share in shares[:cols]])
    cursor.insertBlock(_spacer_format(block.above), QTextCharFormat())
    table = cursor.insertTable(len(rows), cols, fmt)
    _leave_table(cursor, table)
    # The paragraph Qt leaves behind a table is where the design's next block
    # would otherwise be written. Kept as a line of its own, it carries the
    # space below the grid; a heading written straight into the frame's edge is
    # what makes a table look glued to the section after it.
    cursor.setBlockFormat(_spacer_format(block.below))
    cursor.setCharFormat(_char_format(1, False, False, block.ink or template.ink,
                                      block.family or template.body_family))

    ink = block.ink or template.ink
    family = block.family or template.body_family
    head_ink = block.head_ink or (template.accent_ink
                                  if _is_dark(block.shade) else template.accent)
    for r, row in enumerate(rows):
        head = block.header and r == 0
        if block.stripe and not head and r % 2 == 0:
            for c in range(cols):
                _shade_cell(table.cellAt(r, c), block.stripe)
        if head:
            _shade_cell_range(table, r, cols, block.shade)
        for c in range(cols):
            cell = table.cellAt(r, c)
            word = row[c] if c < len(row) else ""
            cell_cursor = cell.firstCursorPosition()
            para = QTextBlockFormat()
            para.setAlignment(ALIGNMENTS[_column_align(block.aligns, c)])
            para.setTopMargin(1)
            para.setBottomMargin(1)
            cell_cursor.setBlockFormat(para)
            cell_cursor.insertText(word, _char_format(
                block.size, (head and block.head_bold)
                or (r, c) in block.bold_cells, False,
                head_ink if head else ink, family))


def _shade_cell_range(table, row: int, cols: int, colour: str) -> None:
    """Shade one whole row, merging any cell that spans several columns."""
    for c in range(cols):
        _shade_cell(table.cellAt(row, c), colour)


def _q_brush(colour: str) -> QBrush:
    return QBrush(QColor(colour))


def paginate_breaks(document: QTextDocument, sheet_px: Tuple[float, float],
                    margin_px: float) -> None:
    """Give every page break the height of the paper that is left.

    WriteR lays a document out as one continuous column: a break that only
    carries Qt's own flag does nothing on its own, so the writing after it starts
    wherever the writing before it ended. Filling the break with the remainder of
    its sheet puts what follows at the top of the next sheet under the printer,
    which is the reader that measures the writing a page at a time.

    *sheet_px* and *margin_px* are the sheet and its margins as this page is
    currently drawn, so the pass is run again whenever either changes. The margin
    is set rather than added to, which is what makes running it twice safe.
    """
    layout = document.documentLayout()
    # The printer keeps the margins to itself and gives each sheet the run of
    # paper between them, so that is the height a break has to fill up to.
    tall = max(1.0, float(sheet_px[1]) - 2 * margin_px)
    # Every break is worked out from the writing as it stands now: growing one
    # block moves the ones after it, so the heights are taken in a first pass
    # and the paper is filled in a second.
    found: List[Tuple[int, float, float]] = []
    block = document.begin()
    while block.isValid():
        fmt = block.blockFormat()
        if (fmt.pageBreakPolicy()
                & QTextBlockFormat.PageBreakFlag.PageBreak_AlwaysBefore):
            rect = layout.blockBoundingRect(block)
            found.append((block.position(), rect.y() + rect.height()
                          + fmt.bottomMargin(), fmt.bottomMargin()))
        block = block.next()
    for position, bottom, held in found:
        sheet = max(0, math.floor((bottom - margin_px - held) / tall) + 1)
        room = max(0.0, sheet * tall + margin_px - bottom + held)
        if abs(room - held) > 0.5:
            cursor = QTextCursor(document)
            cursor.beginEditBlock()
            cursor.setPosition(position)
            grown = cursor.blockFormat()
            grown.setBottomMargin(room)
            cursor.setBlockFormat(grown)
            cursor.endEditBlock()


# --------------------------------------------------------------------------- #
# the design                                                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Template:
    """One page's whole design: its sheet, its dress, its writing."""

    key: str
    name: str
    group: str
    blurb: str
    blocks: Tuple[Block, ...]
    paper: str = "Letter"
    margin_px: float = 96.0
    landscape: bool = False
    body_family: Tuple[str, ...] = SANS_CHAIN
    head_family: Tuple[str, ...] = SANS_CHAIN
    body_size: float = 11.0
    ink: str = INK
    muted: str = MUTED
    accent: str = ACCENT
    accent_ink: str = "#FFFFFF"
    spacing: float = 1.12
    space_body: float = 7.0
    space_list: float = 3.0
    border: Optional[dict] = None
    fill: Optional[dict] = None
    mark: Optional[dict] = None
    bands: Optional[dict] = None
    #: What the gallery's detail line says beside the blurb.
    detail: str = ""

    # -- the sheet ----------------------------------------------------------- #

    @property
    def sheet_px(self) -> Tuple[float, float]:
        """The paper this design is cut to, in sheet pixels."""
        wide, tall = PAPER_SIZES.get(self.paper, (816, 1056))
        if self.landscape:
            return float(tall), float(wide)
        return float(wide), float(tall)

    @property
    def column_px(self) -> float:
        """The run of paper between the margins, which is where words go."""
        return max(48.0, self.sheet_px[0] - 2 * self.margin_px)

    def dress(self) -> dict:
        """The four things a sheet can be dressed with, each completed."""
        return {
            "border": {"style": "none", "colour": BORDER_COLOUR,
                       "width_pt": 1.0, **(self.border or {})},
            "fill": {"kind": "none", "colour": "#FFFFFF", "image_path": "",
                     "opacity": 1.0, **(self.fill or {})},
            "mark": watermark_mark(self.mark),
            "bands": bands_setting(self.bands),
        }

    # -- the page ------------------------------------------------------------ #

    def apply_to(self, page) -> None:
        """Dress and fill the sheet *page* is, replacing what it held.

        The writing goes in while the page is at its actual sizes, so a design
        that says twenty points means twenty points whatever zoom it lands on;
        the page scales the whole thing back up on the way out.
        """
        page.clear()
        page.clear_floats()
        page.clear_page_dress()
        page.set_paper(self.paper)
        page.set_landscape(self.landscape)
        page.set_margin_pixels(self.margin_px)
        dress = self.dress()
        page.set_page_border(**dress["border"])
        page.set_page_colour(**dress["fill"])
        if dress["mark"]["kind"] != "none":
            page.set_watermark(**dress["mark"])
        page.set_header_footer(header=dress["bands"]["header"],
                               footer=dress["bands"]["footer"],
                               show_first_page=dress["bands"]["show_first_page"])
        with page.at_actual_size() as document:
            self.write(QTextCursor(document))
            base = _char_format(self.body_size, False, False, self.ink,
                                self.body_family).font()
            document.setDefaultFont(base)
            page.setFont(base)
            paginate_breaks(document, self.sheet_px, self.margin_px)
        cursor = page.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        page.setTextCursor(cursor)
        page.document().setModified(False)
        page.viewport().update()

    def write(self, cursor: QTextCursor) -> None:
        """Lay this design's blocks out on *cursor*'s document."""
        cursor.beginEditBlock()
        opening = True
        for block in self.blocks:
            opening = self._write_block(cursor, block, opening)
        cursor.endEditBlock()

    def _write_block(self, cursor: QTextCursor, block, opening: bool) -> bool:
        """Write one block, and say whether the document is still untouched."""
        if isinstance(block, PageBreak):
            fmt = _spacer_format(0)
            fmt.setPageBreakPolicy(
                QTextBlockFormat.PageBreakFlag.PageBreak_AlwaysBefore)
            return self._open_block(cursor, fmt, QTextCharFormat(), opening)
        if isinstance(block, Gap):
            return self._open_block(cursor, _spacer_format(block.px),
                                    QTextCharFormat(), opening)
        if isinstance(block, Rule):
            if block.above:
                self._open_block(cursor, _spacer_format(block.above),
                                 QTextCharFormat(), opening)
                opening = False
            face = _char_format(max(BAND_FACE_PT, block.weight), False, False,
                                block.colour, self.body_family)
            opening = self._open_block(cursor, _band_format(self, block), face,
                                       opening)
            cursor.insertText(" ", face)
            if block.below:
                self._open_block(cursor, _spacer_format(block.below),
                                 QTextCharFormat(), False)
            return False
        if isinstance(block, Bullets):
            # A list starts on a block of its own: written onto the paragraph
            # before it, the whole of that paragraph would take the marker.
            if opening:
                cursor.setBlockFormat(_spacer_format(0))
            else:
                cursor.insertBlock(_spacer_format(0), QTextCharFormat())
            _write_list(cursor, self, block)
            return False
        if isinstance(block, Table):
            if opening:
                cursor.setBlockFormat(_spacer_format(0))
            else:
                cursor.insertBlock(_spacer_format(0), QTextCharFormat())
            _write_table(cursor, self, block)
            # The paragraph left behind the grid now carries the design's space
            # below it, so the next block starts a paragraph of its own.
            return False
        if isinstance(block, Text):
            fmt = _paragraph_format(self, block)
            text = block.text.upper() if block.caps else block.text
            colour = block.fill_ink if (block.fill and block.fill_ink) else (
                block.colour or self.ink)
            char = _char_format(
                block.size if block.size is not None else self.body_size,
                bool(block.bold), bool(block.italic), colour,
                block.family or self.body_family,
                underline=bool(block.underline), tracking=block.tracking)
            lines = text.split("\n")
            for index, line in enumerate(lines):
                if index:
                    follow = QTextBlockFormat(fmt)
                    follow.setTopMargin(0)
                    follow.setBottomMargin(
                        block.below if index + 1 == len(lines) else 0)
                    cursor.insertBlock(follow, char)
                elif opening:
                    cursor.setBlockFormat(fmt)
                else:
                    cursor.insertBlock(fmt, char)
                cursor.insertText(line, char)
                opening = False
            return False
        return opening

    @staticmethod
    def _open_block(cursor: QTextCursor, fmt: QTextBlockFormat,
                    char: QTextCharFormat, opening: bool) -> bool:
        """Start a block with no words in it, and report the document's state."""
        if opening:
            cursor.setBlockFormat(fmt)
            return False
        cursor.insertBlock(fmt, char)
        return False

    # -- the tile ------------------------------------------------------------ #

    def sheets(self, page) -> int:
        """How many sheets this design fills once *page* is wearing it."""
        return page.page_count()


# --------------------------------------------------------------------------- #
# the gallery                                                                 #
# --------------------------------------------------------------------------- #

def sheet_photograph(page, wide: float, tall: float) -> QImage:
    """The first sheet of *page*, as one image of the whole paper.

    Two things about a page that is never shown catch a photographer out. It is
    never told how wide its paper is, so the document would lay its lines out at
    an unlimited width and run past the margin; and a grab comes back in *device*
    pixels, which on a scaled display are more of them than the sheet has points.
    Both are settled here, so every tile is measured the same way.

    The page is made taller than the whole writing before it is photographed,
    because a page one sheet high measures its last lines against a scrollbar the
    taller page never shows -- and a break below them is placed by that
    measurement, so a tight page puts the next sheet's writing a few points early.
    """
    document = page.document()
    page.resize(int(wide), int(tall))
    document.setTextWidth(int(wide) - 2 * page.frameWidth())
    page.resize(int(wide), int(tall) + int(document.size().height()) + 4)
    paginate_breaks(document, (wide, tall), page.margin_pixels)
    image = page.grab().toImage()
    ratio = image.devicePixelRatio() or 1.0
    sheet = image.copy(QRect(0, 0, int(wide * ratio), int(tall * ratio)))
    sheet.setDevicePixelRatio(1.0)
    return sheet


def build_tiles(templates: Sequence[Template], width_px: int = TILE_WIDTH,
                parent=None) -> Dict[str, QPixmap]:
    """Every design's first sheet, photographed off a real page.

    The tile is the page itself at full size, shrunk afterwards: painting the
    document into its own image would leave the dress and the writing to be
    ordered by hand again, and the point of a gallery is that it shows what the
    sheet will do.
    """
    from officer.writer.document_view import DocumentPageWidget
    tiles: Dict[str, QPixmap] = {}
    for template in templates:
        page = DocumentPageWidget(parent)
        try:
            template.apply_to(page)
            wide, tall = template.sheet_px
            sheet = sheet_photograph(page, wide, tall)
            shrunk = sheet.scaled(width_px, int(width_px * tall / wide),
                                  Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                  Qt.TransformationMode.SmoothTransformation)
            tiles[template.key] = _tiled(QPixmap.fromImage(shrunk))
        finally:
            page.setParent(None)
            page.deleteLater()
    return tiles


def _tiled(sheet: QPixmap) -> QPixmap:
    """One sheet with a hairline round it, so a white page reads as a tile."""
    framed = QPixmap(sheet.width() + 2, sheet.height() + 2)
    framed.fill(QColor("#E5E7EB"))
    painter = QPainter(framed)
    painter.drawPixmap(1, 1, sheet)
    painter.end()
    return framed


def gallery_entries(templates: Sequence[Template],
                    tiles: Dict[str, QPixmap]) -> List[GalleryEntry]:
    """The gallery's tiles, in the order the designs are listed."""
    return [GalleryEntry(key=each.key, name=each.name, blurb=each.blurb,
                         group=each.group, preview=tiles.get(each.key),
                         detail=each.detail or f"{each.group} — {each.blurb}")
            for each in templates]


def find(templates: Sequence[Template], key: str) -> Optional[Template]:
    """The design called *key*, which is how a gallery answer becomes a page."""
    return next((each for each in templates if each.key == key), None)
