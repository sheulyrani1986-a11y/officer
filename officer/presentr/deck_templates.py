"""PresentR's deck designs: a whole presentation from one gallery choice.

A design here is a palette plus a short run of slides built from the same few
recipes, so that every deck the gallery offers is dressed the way a designer
would dress it — a cover that carries the room, sections that break the run,
figures set large — rather than a title box and a shrug.

The slide's own units are PresentR's: a 960 by 540 sheet, 64 of margin, and
type measured in points as PowerPoint measures it.
"""

import math
from dataclasses import dataclass, field, replace
from typing import Callable, List, Optional, Sequence, Tuple

from PySide6.QtGui import QFontDatabase, QPixmap

from officer.core.ui.template_gallery import TILE_WIDTH, GalleryEntry
from officer.presentr.canvas import render_slide_to_pixmap
from officer.presentr.slide_deck import (
    ShapeObject, Slide, TextObject)

#: How the sheet is shared out: the margin, the column inside it, and where the
#: writing begins once a slide's heading has been set.
MARGIN = 64
WIDE = 960
TALL = 540
COLUMN = WIDE - 2 * MARGIN

#: Where a slide's writing starts under a one-line heading, and how far down the
#: last mark may reach before the footnote line.
BODY_TOP = 140
FLOOR = 476

#: Three cards, four, or any even spread: the panel widths that tile the column.
CARD_GUTTER = 32


def _installed(*preferred: str) -> str:
    """The first of *preferred* this machine can actually draw.

    A slide carries one family, not a chain, so the choice has to be settled
    here: a deck that asked for a face the machine lacks would fall back to
    Qt's default rather than to the next name the design would have picked.
    """
    known = {family.casefold(): family for family in QFontDatabase.families()}
    for name in preferred:
        if name.casefold() in known:
            return known[name.casefold()]
    return preferred[-1]


def sans() -> str:
    """The face a sans design sets its slides in."""
    return _installed("Aptos", "Calibri", "Carlito", "Liberation Sans",
                      "DejaVu Sans")


def serif() -> str:
    """The face a serif design sets both its headings and its writing in."""
    return _installed("Cambria", "Georgia", "Caladea", "Tinos",
                      "Liberation Serif", "DejaVu Serif")


#: A line of type stands this many ems tall once PresentR applies its leading.
LINE = 1.55


def _wrapped(text: str, wide: float, size: float) -> int:
    """About how many lines *text* takes in a box *wide* points across.

    PresentR's text boxes grow downwards and are placed by hand, so a recipe
    that sets a heading has to know how tall it will stand before it can put
    the rule under it. An average glyph is three fifths of an em, and an em is
    the point size times Qt's 96 to 72.
    """
    per = max(6.0, wide / (size * 1.333 * 0.6))
    return sum(max(1, math.ceil(len(line) / per)) for line in text.split("\n"))


def _tall(text: str, wide: float, size: float, spacing: float = 1.15) -> float:
    """The height *text* needs, in slide units.

    PresentR sets a paragraph's leading as a percentage of the font's own line
    height, and a face's line height stands about a sixth above its em, which is
    what :data:`LINE` carries.
    """
    return _wrapped(text, wide, size) * size * LINE * spacing


@dataclass(frozen=True)
class Palette:
    """The six colours a design is made of, and the two faces it writes in.

    The faces are named by flag rather than by font, because a design is built
    when this module is imported and the machine's fonts cannot be listed until
    an application exists: :class:`Kit` settles the question at build time.
    """

    bg: str = "#FFFFFF"
    ink: str = "#1F2937"
    muted: str = "#6B7280"
    accent: str = "#2B579A"
    on_accent: str = "#FFFFFF"
    wash: str = "#EDF1F8"
    rule: str = "#D1D5DB"
    #: What the cover's spine and a section's full sheet are painted.
    block: str = ""
    #: Set for a design that writes its slides in the machine's serif.
    serif: bool = False
    head: str = ""
    body: str = ""

    def __post_init__(self) -> None:
        if not self.block:
            object.__setattr__(self, "block", self.accent)


class Kit:
    """The recipes every design builds its slides from, in one palette.

    Nothing here is specific to a design: a deck is a :class:`Palette` and a
    list of calls, which is what keeps ten decks looking like ten decks rather
    than ten layouts.
    """

    def __init__(self, pal: Palette, foot: str = ""):
        head = serif() if pal.serif else sans()
        self.pal = replace(pal, head=pal.head or head, body=pal.body or head)
        self.default_foot = foot
        self._n = 0

    # -- the sheet ----------------------------------------------------------- #

    def slide(self, title: str, bg: Optional[str] = None) -> Slide:
        """A fresh, blank sheet: the recipes put every mark on it from here."""
        self._n = 0
        return Slide(title=title, layout="blank",
                     background_color=bg or self.pal.bg)

    def _oid(self, kind: str) -> str:
        self._n += 1
        return f"{kind}{self._n}"

    def put(self, s: Slide, x: float, y: float, w: float, text: str, size: float,
            colour: Optional[str] = None, bold: bool = False, italic: bool = False,
            align: str = "left", family: Optional[str] = None,
            spacing: float = 1.15) -> TextObject:
        """Set *text* on *s* at its size, wrapped to *w*."""
        lines = _wrapped(text, w, size)
        obj = TextObject(id=self._oid("text"), x=x, y=y, width=w,
                         height=round(max(size * 1.45,
                                          _tall(text, w, size, spacing))),
                         z_order=len(s.objects), text=text,
                         font_family=family or self.pal.body,
                         font_size=int(round(size)), bold=bold, italic=italic,
                         text_color=colour or self.pal.ink, alignment=align,
                         line_spacing=spacing)
        s.objects.append(obj)
        return obj

    def box(self, s: Slide, x: float, y: float, w: float, h: float,
            colour: str, gradient: Optional[str] = None, shape: str = "rect",
            border: Optional[str] = None, width: int = 0) -> ShapeObject:
        """Paint *colour* over a rectangle of the sheet, outline it if asked.

        A shape with no border of its own is drawn in its own fill, because
        PresentR's shapes carry an outline whatever happens; the flat panel a
        design wants is the one whose outline cannot be seen.
        """
        obj = ShapeObject(id=self._oid("shape"), x=x, y=y, width=w, height=h,
                          z_order=len(s.objects), shape_type=shape,
                          fill_color=colour, gradient_color=gradient,
                          border_color=border or colour,
                          border_width=width if border else 0)
        s.objects.append(obj)
        return obj

    # -- the parts ----------------------------------------------------------- #

    def head(self, s: Slide, title: str, eyebrow: str = "") -> float:
        """A slide's heading, and the y its body should start at.

        The hairline has to fall below the title however many lines the title
        takes, so the recipes are told where the writing starts instead of
        assuming a one-line heading.
        """
        if eyebrow:
            self.put(s, MARGIN, 38, COLUMN, eyebrow.upper(), 11,
                     colour=self.pal.accent, bold=True, family=self.pal.head)
        rule = 60 + _tall(title, COLUMN, 27) + 11
        self.put(s, MARGIN, 60, COLUMN, title, 27, bold=True,
                 family=self.pal.head)
        self.box(s, MARGIN, rule, COLUMN, 1, self.pal.rule)
        return rule + 28

    def fit(self, text: str, wide: float, size: float, room: float,
             spacing: float = 1.15, floor: float = 10.0) -> float:
        """The biggest size at which *text* stands no taller than *room*.

        A deck is a fixed sheet: the words a presenter brings with them are not.
        Sizing the type down a point or two keeps a slide intact on the screen
        and in the thumbnail, and the presenter can set it back afterwards.
        """
        while size > floor and _tall(text, wide, size, spacing) > room:
            size -= 0.5
        return size

    def settle(self, objs: Sequence[TextObject], bottom: float,
               weight: float = .4) -> None:
        """Slide finished marks down the slack under them, to roughly centre them.

        A short block stranded directly beneath a heading leaves the bottom third
        of the sheet empty, which reads as a mistake rather than as air; a
        presenter's eye wants the group sitting in the space it was given. The
        whole group moves together, so a lead line and its list keep their gap.
        """
        lowest = max(obj.y + obj.height for obj in objs)
        slack = bottom - lowest
        if slack > 24:
            for obj in objs:
                obj.y += round(slack * weight)

    def foot(self, s: Slide, note: str = "") -> None:
        """The quiet line at the bottom, which is where a deck signs itself."""
        line = note or self.default_foot
        if line:
            self.put(s, MARGIN, 498, COLUMN, line, 10, colour=self.pal.muted)

    def bullets(self, s: Slide, items: Sequence[str], y: float = BODY_TOP + 24,
                size: float = 17, x: float = MARGIN, w: float = COLUMN,
                colour: Optional[str] = None) -> TextObject:
        """One text box holding the list, so it edits as a list does."""
        text = "\n".join(f"•   {each}" for each in items)
        return self.put(s, x, y, w, text,
                        self.fit(text, w, size, FLOOR - y, 1.5), spacing=1.5,
                        colour=colour)

    # -- the slides ---------------------------------------------------------- #

    def cover(self, kicker: str, title: str, subtitle: str,
              foot: str = "") -> Slide:
        """The sheet the deck opens on: a spine of the accent and large type."""
        s = self.slide(title)
        self.box(s, 0, 0, 18, TALL, self.pal.block)
        self.put(s, 88, 148, COLUMN, kicker.upper(), 12,
                 colour=self.pal.accent, bold=True, family=self.pal.head)
        size = self.fit(title, 740, 42, 2 * 42 * LINE * 1.05, 1.05, 30.0)
        self.put(s, 88, 176, 740, title, size, bold=True,
                 family=self.pal.head, spacing=1.05)
        rule = 176 + _tall(title, 740, size, 1.05) + 26
        self.box(s, 88, rule, 92, 4, self.pal.accent)
        sub = self.fit(subtitle, 680, 17, 462 - (rule + 24), floor=12.0)
        self.put(s, 88, rule + 24, 680, subtitle, sub, colour=self.pal.muted)
        if foot:
            self.put(s, 88, 470, 680, foot, 11, colour=self.pal.muted)
        return s

    def section(self, number: str, title: str, line: str) -> Slide:
        """A full sheet of the accent, which is how a deck marks a new chapter."""
        s = self.slide(title, bg=self.pal.block)
        self.put(s, 88, 168, 200, number, 58, bold=True,
                 colour=self.pal.on_accent, family=self.pal.head)
        self.box(s, 88, 258, 92, 4, self.pal.on_accent)
        size = self.fit(title, 760, 32, 2 * 32 * LINE * 1.15, 1.15, 24.0)
        self.put(s, 88, 282, 760, title, size, bold=True,
                 colour=self.pal.on_accent, family=self.pal.head)
        self.put(s, 88, 282 + _tall(title, 760, size) + 18, 700, line, 15,
                 colour=self.pal.on_accent)
        return s

    def points(self, title: str, lead: str, items: Sequence[str],
               eyebrow: str = "", note: str = "") -> Slide:
        """A heading, one line of standing type, and the list underneath."""
        s = self.slide(title)
        top = self.head(s, title, eyebrow)
        lead_box = self.put(s, MARGIN, top, COLUMN, lead, 15,
                            colour=self.pal.muted)
        list_box = self.bullets(s, items,
                                y=top + _tall(lead, COLUMN, 15) + 26, size=17)
        self.settle([lead_box, list_box], FLOOR, .35)
        self.foot(s, note)
        return s

    def agenda(self, title: str, items: Sequence[str],
               eyebrow: str = "Agenda") -> Slide:
        """The run of the deck, each turn numbered in the accent."""
        s = self.slide(title)
        top = self.head(s, title, eyebrow)
        step = min(64, (FLOOR - top) / max(1, len(items)))
        for row, item in enumerate(items):
            y = top + 12 + row * step
            self.put(s, MARGIN, y, 40, f"{row + 1:02d}", 15, bold=True,
                     colour=self.pal.accent, family=self.pal.head)
            self.put(s, MARGIN + 56, y, COLUMN - 56, item,
                     self.fit(item, COLUMN - 56, 16, step - 12))
            self.box(s, MARGIN, y + step - 8, COLUMN, 1, self.pal.rule)
        return s

    def cards(self, title: str, cells: Sequence[Tuple[str, str]],
              eyebrow: str = "", note: str = "") -> Slide:
        """Side-by-side panels: the answer to a wall of bullets.

        Every panel is as tall as the fullest of them, so a short card still
        closes level with its neighbours instead of leaving a ragged row.
        """
        s = self.slide(title)
        top = self.head(s, title, eyebrow)
        wide = (COLUMN - CARD_GUTTER * (len(cells) - 1)) / max(1, len(cells))
        room = FLOOR - top
        set_up = []
        for head_line, body in cells:
            inner = _tall(head_line, wide - 40, 16)
            size = self.fit(body, wide - 40, 13, room - 76 - inner, 1.32, 9.5)
            set_up.append((inner, size,
                           _tall(body, wide - 40, size, 1.32)))
        high = min(room, max(84 + inner + tall for inner, _, tall in set_up))
        top += max(0.0, (room - high) / 2)
        for column, ((head_line, body), (inner, size, _)) in enumerate(
                zip(cells, set_up)):
            x = MARGIN + column * (wide + CARD_GUTTER)
            self.box(s, x, top, wide, high, self.pal.wash)
            self.box(s, x, top, wide, 4, self.pal.accent)
            self.put(s, x + 20, top + 26, wide - 40, head_line, 16,
                     bold=True, colour=self.pal.accent, family=self.pal.head)
            self.put(s, x + 20, top + 42 + inner, wide - 40, body, size,
                     spacing=1.32)
        self.foot(s, note)
        return s

    def split(self, title: str, left: Tuple[str, Sequence[str]],
              right: Tuple[str, Sequence[str]], eyebrow: str = "",
              note: str = "") -> Slide:
        """Two columns, each with its own head, facing one another."""
        s = self.slide(title)
        top = self.head(s, title, eyebrow)
        half = (COLUMN - CARD_GUTTER) / 2
        lists = []
        for column, (head_line, items) in enumerate((left, right)):
            x = MARGIN + column * (half + CARD_GUTTER)
            self.put(s, x, top, half, head_line, 16, bold=True,
                     colour=self.pal.accent, family=self.pal.head)
            self.box(s, x, top + 30, 40, 3, self.pal.accent)
            lists.append(self.bullets(s, items, y=top + 48, size=14, x=x,
                                      w=half, colour=self.pal.ink))
        # Both columns settle by the same amount, or the shorter one's list
        # would stop lining up with its own heading's partner.
        self.settle(lists, FLOOR)
        self.foot(s, note)
        return s

    def numbers(self, title: str, cells: Sequence[Tuple[str, str]],
                lead: str = "", eyebrow: str = "", note: str = "") -> Slide:
        """A row of figures set as large as the design dares."""
        s = self.slide(title)
        top = self.head(s, title, eyebrow)
        if lead:
            self.put(s, MARGIN, top, COLUMN, lead, 14, colour=self.pal.muted)
            top += _tall(lead, COLUMN, 14) + 20
        else:
            top += 4
        wide = (COLUMN - CARD_GUTTER * (len(cells) - 1)) / max(1, len(cells))
        high = min(156, FLOOR - top)
        top += max(0.0, (FLOOR - top - high) / 2)
        for column, (figure, caption) in enumerate(cells):
            x = MARGIN + column * (wide + CARD_GUTTER)
            self.box(s, x, top, wide, high, self.pal.wash)
            self.put(s, x + 18, top + 20, wide - 36, figure,
                     self.fit(figure, wide - 36, 38, 64, 1.0, 22.0), bold=True,
                     colour=self.pal.accent, family=self.pal.head,
                     spacing=1.0)
            self.put(s, x + 18, top + 86, wide - 36, caption,
                     self.fit(caption, wide - 36, 12, high - 96, 1.25, 9.5),
                     colour=self.pal.muted, spacing=1.25)
        self.foot(s, note)
        return s

    def bars(self, title: str, rows: Sequence[Tuple[str, float, str]],
             eyebrow: str = "", note: str = "") -> Slide:
        """A chart drawn from shapes, so the presenter can move every bar.

        The figures sit in a column of their own at the right rather than at the
        end of each bar: a bar that nearly fills the sheet would otherwise push
        its number off the edge.
        """
        s = self.slide(title)
        top = self.head(s, title, eyebrow)
        tallest = max((value for _, value, _ in rows), default=1.0) or 1.0
        label_w, start = 206, MARGIN + 222
        figure_w = 104
        track = COLUMN - 222 - figure_w - 14
        step = min(64, (FLOOR - top) / max(1, len(rows)))
        for row, (label, value, caption) in enumerate(rows):
            y = top + 12 + row * step
            self.put(s, MARGIN, y, label_w,
                     label, self.fit(label, label_w, 13, step - 6, 1.0, 10.0),
                     colour=self.pal.muted, spacing=1.0)
            self.box(s, start, y - 2, track, 22, self.pal.wash)
            self.box(s, start, y - 2, max(3.0, track * value / tallest), 22,
                     self.pal.accent)
            self.put(s, MARGIN + COLUMN - figure_w, y - 2, figure_w, caption,
                     13, bold=True, align="right")
        self.foot(s, note)
        return s

    def steps(self, title: str, cells: Sequence[Tuple[str, str, str]],
              eyebrow: str = "", note: str = "") -> Slide:
        """A process: numbered panels in the order they happen."""
        s = self.slide(title)
        top = self.head(s, title, eyebrow)
        wide = (COLUMN - CARD_GUTTER * (len(cells) - 1)) / max(1, len(cells))
        room = FLOOR - top
        # Three short panels left stranded under the heading read as a mistake,
        # so the row is measured and floated down the sheet to sit in its space.
        set_up = [(_tall(head_line, wide - 46, 15),
                   self.fit(body, wide, 12.5, room - 92, 1.3, 9.5))
                  for _, head_line, body in cells]
        group = max(20 + inner + _tall(body, wide, size, 1.3)
                    for (inner, size), (_, _, body) in zip(set_up, cells))
        base = top + max(0.0, (room - group) / 2)
        for column, ((marker, head_line, body), (inner, size)) in enumerate(
                zip(cells, set_up)):
            x = MARGIN + column * (wide + CARD_GUTTER)
            self.box(s, x, base, 34, 34, self.pal.accent, shape="ellipse")
            self.put(s, x, base + 6, 34, marker, 15, bold=True,
                     colour=self.pal.on_accent, align="center")
            self.put(s, x + 46, base + 4, wide - 46, head_line, 15, bold=True,
                     family=self.pal.head)
            self.put(s, x, base + 20 + inner, wide, body, size, spacing=1.3)
            if column + 1 < len(cells):
                self.box(s, x + wide + 6, base + 8, 20, 18,
                         self.pal.rule, shape="chevron")
        self.foot(s, note)
        return s

    def timeline(self, title: str, marks: Sequence[Tuple[str, str]],
                 eyebrow: str = "", note: str = "") -> Slide:
        """The run of dates, each in a chevron that points at the next."""
        s = self.slide(title)
        top = self.head(s, title, eyebrow)
        gaps = 10 * max(0, len(marks) - 1)
        wide = (COLUMN - gaps) / max(1, len(marks))
        tall = max((_tall(what, wide - 14, 12, 1.25) for _, what in marks),
                   default=16.0)
        # The band of dates is floated down the sheet rather than left hanging
        # under the heading, which is what a run of four of them tends to do.
        base = top + max(0.0, (FLOOR - top - 114 - tall) / 2)
        for column, (when, what) in enumerate(marks):
            x = MARGIN + column * (wide + 10)
            self.box(s, x, base + 28, wide, 62, self.pal.accent
                     if column % 2 == 0 else self.pal.wash, shape="chevron")
            ink = (self.pal.on_accent if column % 2 == 0 else self.pal.ink)
            self.put(s, x + 26, base + 48, wide - 40, when, 13, bold=True,
                     colour=ink)
            self.put(s, x, base + 102, wide - 14, what, 12,
                     colour=self.pal.muted, spacing=1.25)
        self.box(s, MARGIN, base + 12, COLUMN, 1, self.pal.rule)
        self.foot(s, note)
        return s

    def quote(self, text: str, who: str, title: str = "Quote") -> Slide:
        """One voice, large, with a bar of the accent holding it up.

        This is the one sheet that carries no heading, so the line is set in the
        middle of it, which is where the room looks for a quotation.
        """
        s = self.slide(title)
        size = self.fit(text, 760, 24, 300, 1.3, 16.0)
        high = _tall(text, 760, size, 1.3)
        y = (TALL - high - 46) / 2
        self.put(s, MARGIN + 36, y, 760, text, size, italic=True,
                 family=self.pal.head, spacing=1.3)
        self.box(s, MARGIN, y + 6, 6, max(24.0, high - 12), self.pal.accent)
        self.put(s, MARGIN + 36, y + high + 26, 700, who.upper(), 11,
                 bold=True, colour=self.pal.accent)
        return s

    def closing(self, title: str, line: str, foot: str = "") -> Slide:
        """The sheet the deck ends on, in the accent so it reads as an end."""
        s = self.slide(title, bg=self.pal.block)
        self.box(s, MARGIN, 176, 92, 4, self.pal.on_accent)
        size = self.fit(title, 800, 34, 2 * 34 * LINE * 1.15, 1.15, 26.0)
        self.put(s, MARGIN, 202, 800, title, size, bold=True,
                 colour=self.pal.on_accent, family=self.pal.head)
        self.put(s, MARGIN, 202 + _tall(title, 800, size) + 18, 720, line, 16,
                 colour=self.pal.on_accent)
        if foot:
            self.put(s, MARGIN, 448, 720, foot, 11, colour=self.pal.on_accent)
        return s

    def table(self, title: str, head_row: Sequence[str],
              rows: Sequence[Sequence[str]], eyebrow: str = "",
              note: str = "") -> Slide:
        """A grid drawn from panels: the only table a slide needs."""
        s = self.slide(title)
        top = self.head(s, title, eyebrow)
        columns = len(head_row)
        wide = COLUMN / max(1, columns)
        step = min(64, (FLOOR - top) / max(1, len(rows) + 1))
        for column, cell in enumerate(head_row):
            x = MARGIN + column * wide
            self.box(s, x, top, wide - 6, step - 6, self.pal.accent)
            self.put(s, x + 14, top + (step - 23) / 2, wide - 30,
                     cell.upper(), 11, bold=True, colour=self.pal.on_accent)
        for row, cells in enumerate(rows):
            y = top + (row + 1) * step
            for column, cell in enumerate(cells):
                x = MARGIN + column * wide
                if row % 2 == 0:
                    self.box(s, x, y, wide - 6, step - 6, self.pal.wash)
                size = self.fit(cell, wide - 30, 13, step - 12, 1.0, 9.5)
                self.put(s, x + 14, y + (step - 6 - size * LINE) / 2, wide - 30,
                         cell, size, bold=column == 0, spacing=1.0)
        self.foot(s, note)
        return s


# --------------------------------------------------------------------------- #
# the designs                                                                 #
# --------------------------------------------------------------------------- #

def corporate_brief() -> "DeckTemplate":
    """The deck a company shows its board: blue, orderly, figures first."""
    pal = Palette(accent="#2B579A", wash="#EDF1F8", block="#1F3864")

    def build() -> List[Slide]:
        k = Kit(pal, "Northbridge Distribution · quarterly operations review")
        return [
            k.cover("Quarterly review", "Eastern line: the second carrier",
                    "What nine per cent more volume cost us, and what we do "
                    "about it before May.",
                    "[Your name] · Head of Operations · [Day month year]"),
            k.agenda("How the quarter went", [
                "The three numbers the board asked for",
                "Where the eastern line is short",
                "The second carrier, and what it costs",
                "Dates, owners, and the next review",
            ]),
            k.numbers("The quarter in three figures", [
                ("97.4%", "on-time delivery, against a 96% target"),
                ("41.20", "taka per order, down from 45.00"),
                ("+9.1%", "orders received, 19,640 in all"),
            ], lead="Both depots met their commitments; the east did not.",
               eyebrow="Summary"),
            k.points("Where we are short",
                     "Two missed windows in February cost three stores a week "
                     "of shelf time.",
                     ["A single carrier holds a fifth of the network's volume.",
                      "The depot has no relief pool for the peak weeks.",
                      "Fuel beyond the boundary is absorbed, not passed on."],
                     eyebrow="The problem"),
            k.section("02", "The second carrier",
                      "Six vehicles at the depot already in use, and one named "
                      "coordinator on the phone."),
            k.cards("What we propose", [
                ("One line, six vehicles",
                 "Held at the depot you already use, so nothing in receiving "
                 "has to change."),
                ("A named coordinator",
                 "On your side of the call, in place before the first run and "
                 "answerable weekly."),
                ("Three measures",
                 "On-time delivery, cost per order, and runs leaving on "
                 "schedule. Published, not promised."),
            ], eyebrow="The offer"),
            k.table("What it costs", ["Option", "Vehicles", "Monthly", "Holds"],
                    [["Standard", "4", "180,000", "Daytime windows"],
                     ["Recommended", "6", "236,000", "Both windows"],
                     ["Peak cover", "8", "304,000", "Weekend and surge"]],
                    eyebrow="Pricing"),
            k.timeline("Dates the board can hold us to", [
                ("14 Mar", "Terms signed"),
                ("28 Mar", "Vehicles assigned"),
                ("02 Apr", "Drivers briefed"),
                ("07 Apr", "First paid run"),
            ], eyebrow="Plan"),
            k.quote("The quarter's real gain was not the volume. It was that we "
                    "absorbed it without adding a single vehicle.",
                    "Operations Board minutes, 14 March"),
            k.closing("Two decisions today",
                      "Contract the second line for April, and keep the second "
                      "depot open on Saturdays through the peak.",
                      "[Your name] · operations@example.com · +880 9000 0000"),
        ]

    return DeckTemplate(key="corporate-brief", name="Corporate Brief",
                        group="Business",
                        blurb="Board-ready: figures, offer, dates, decision.",
                        detail="Ten sheets that open on the quarter's three "
                               "numbers and close on the decision being asked "
                               "for, with a chart-free pricing grid and a "
                               "timeline in chevrons.",
                        build=build)


def executive_dark() -> "DeckTemplate":
    """Dark ground, warm accent: the deck for a room with the lights down."""
    pal = Palette(bg="#0F172A", ink="#E2E8F0", muted="#94A3B8",
                  accent="#F59E0B", on_accent="#0F172A", wash="#1E293B",
                  rule="#334155", block="#0F172A")

    def build() -> List[Slide]:
        k = Kit(pal, "Northbridge Distribution · strategy evening")
        return [
            k.cover("Strategy evening", "A network that can take a bad week",
                    "Why the east gets a second source, and what it does to the "
                    "cost of an order.",
                    "[Your name] · [Day month year]"),
            k.agenda("Tonight", [
                "The single point of failure",
                "What redundancy costs, and earns",
                "The two-year shape of the network",
                "What we ask the room to back",
            ]),
            k.numbers("The exposure, in figures", [
                ("19.6%", "of all volume on one carrier"),
                ("7 days", "of shelf time lost in February"),
                ("0", "sources of relief at the eastern depot"),
            ], lead="One line carries a fifth of the company. It failed twice.",
               eyebrow="Risk"),
            k.section("02", "The shape we want",
                      "Two depots, three carriers, and a route schedule that "
                      "publishes to customers."),
            k.cards("Three moves", [
                ("Second carrier", "Contracted for April at the depot in use, "
                 "priced per window rather than per vehicle."),
                ("Relief pool", "Eight drivers on the peak rate, held against "
                 "the weeks that break, not the ones that do not."),
                ("Open schedule", "Routes published with the tariff, so a "
                 "customer sees the change before they feel it."),
            ], eyebrow="The plan"),
            k.bars("What it does to cost", [
                ("Cost per order, today", 45.0, "45.00"),
                ("After the redraw", 41.2, "41.20"),
                ("With peak cover", 44.8, "44.80"),
            ], eyebrow="Economics"),
            k.split("What we are not doing",
                    ("Left alone", ["The western route, which holds.",
                                    "The customer tariff, until next year.",
                                    "The Narayanganj lease."]),
                    ("In scope", ["The eastern line's second source.",
                                  "Saturday opening at depot two.",
                                  "Weekly reporting, published."]),
                    eyebrow="Boundaries"),
            k.closing("What we ask for",
                      "Back the second carrier for April and the relief pool "
                      "for the peak. Everything else is ours to settle.",
                      "[Your name] · [your.name]@example.com"),
        ]

    return DeckTemplate(key="executive-dark", name="Executive Dark",
                        group="Business",
                        blurb="Night room: dark ground, amber accent, big figures.",
                        detail="Built for a projected room. The palette inverts "
                               "to a deep ground with a warm accent, and the "
                               "deck leans on figures and bars rather than "
                               "paragraphs.",
                        build=build)


def minimal_mono() -> "DeckTemplate":
    """Nothing but type, hairlines and air: the quietest design here."""
    pal = Palette(accent="#111827", ink="#111827", muted="#9CA3AF",
                  wash="#F5F5F4", rule="#E5E7EB", block="#111827")

    def build() -> List[Slide]:
        k = Kit(pal, "[Your name] · [Day month year]")
        return [
            k.cover("A talk", "Mapping the eastern corridor",
                    "What the surveys of 1880 to 1930 say about the offices "
                    "that drew them.",
                    "Read in forty minutes"),
            k.agenda("The argument", [
                "The surveys are read as pictures of the ground",
                "Read as office documents, their silences speak",
                "Two sheets of the same reach, twenty years apart",
                "What a change of interest looks like on paper",
            ]),
            k.points("The received reading",
                     "Every history of the corridor treats a survey as a record "
                     "of what stood there.",
                     ["The channel is drawn once and lettered as settled.",
                      "Where two sheets disagree, one is thought wrong.",
                      "The office that drew them is never in the frame."],
                     eyebrow="One"),
            k.quote("A map is an argument that has been allowed to look like a "
                    "fact.", "[Name], on the 1901 sheets"),
            k.split("Two sheets",
                    ("1898", ["The river market at Narayanganj is drawn twice.",
                              "Soundings run the width of the channel."]),
                    ("1901", ["The market is gone from the sheet.",
                              "The channel is a single letterspaced line."]),
                    eyebrow="Two"),
            k.points("What the silence means",
                     "The river did not move by a furlong between the two "
                     "surveys. The office did.",
                     ["In 1901 the department took a new mandate over river "
                      "trade.",
                      "The market fell outside what it was paid to see.",
                      "The sheet records an interest, not a depth."],
                     eyebrow="Three"),
            k.closing("The cartographic eye",
                      "Lay the sheets against one another and the office shows "
                      "through the paper.",
                      "Questions"),
        ]

    return DeckTemplate(key="minimal-mono", name="Minimal Mono",
                        group="Editorial",
                        blurb="Black on white, hairlines, generous air.",
                        detail="For a talk that is really an argument: no "
                               "panels of colour, one accent used only for "
                               "rules and numbers, and a pull quote given the "
                               "whole sheet.",
                        build=build)


def bold_splash() -> "DeckTemplate":
    """Oversized type and a full sheet of colour: a product launch."""
    pal = Palette(accent="#7C3AED", wash="#F3EEFF", block="#7C3AED",
                  on_accent="#FFFFFF", muted="#6D28D9", rule="#DDD6FE")

    def build() -> List[Slide]:
        k = Kit(pal, "Launch · [Day month year]")
        return [
            k.cover("Launch", "Depot, in your pocket",
                    "The live view of every run, on the phone that is already "
                    "in the cab.",
                    "[Your name] · [Company]"),
            k.numbers("Why now", [
                ("68%", "of runs are still checked by phone call"),
                ("11 min", "average time to confirm a delivery"),
                ("3", "separate tools doing one job badly"),
            ], lead="The depot runs on a spreadsheet and a mobile network.",
               eyebrow="The gap"),
            k.section("01", "What it does",
                      "Three screens. One of them is the one people use."),
            k.steps("Three screens", [
                ("1", "Live board", "Every run, its vehicle, and the window it "
                 "is holding — updated at the gate, not at the office."),
                ("2", "The call sheet", "Who is on, where the relief pool is, "
                 "and what a peak day costs to cover."),
                ("3", "Customer line", "The schedule the customer sees, "
                 "published from the same data."),
            ], eyebrow="Product"),
            k.cards("What it replaces", [
                ("The whiteboard", "Still the fastest thing at the depot, and "
                 "gone by the end of the shift."),
                ("The 7am call", "Eleven minutes a run, times six runs, times "
                 "every day that it rains."),
                ("The Friday sheet", "Written from memory, wrong by lunch, "
                 "used for the tariff anyway."),
            ], eyebrow="Before"),
            k.bars("Pilot results", [
                ("Depot one", 34, "-34% late runs"),
                ("Depot two", 21, "-21% late runs"),
                ("Both, week 6", 29, "-29% late runs"),
            ], eyebrow="Proof"),
            k.timeline("Roadmap", [
                ("Apr", "Pilot closes"),
                ("Jun", "Both depots"),
                ("Aug", "Customer line"),
                ("Nov", "Carrier portal"),
            ], eyebrow="Roadmap"),
            k.quote("We stopped waiting for the schedule to be fixed and went "
                    "to where the schedule was actually being made.",
                    "Depot manager, pilot week 3"),
            k.closing("Get in the pilot",
                      "Six weeks, two depots, and a number we both agree on "
                      "before we start.",
                      "[name]@[company].com · +880 9000 0000"),
        ]

    return DeckTemplate(key="bold-splash", name="Bold Splash",
                        group="Creative",
                        blurb="Loud accent, big numbers, a product story.",
                        detail="A launch deck: one saturated colour used as a "
                               "full sheet for sections, a numbered process "
                               "with chevrons, and results drawn as bars.",
                        build=build)


def data_review() -> "DeckTemplate":
    """Charts on every sheet: the operations review that runs weekly."""
    pal = Palette(accent="#0E7490", wash="#ECFEFF", block="#164E63",
                  muted="#5B7A85")

    def build() -> List[Slide]:
        k = Kit(pal, "Operations review · week [00] · [Day month year]")
        return [
            k.cover("Operations review", "Week [00]: the eastern line",
                    "Six vehicles, two depots, three measures, one of them "
                    "moving the wrong way.",
                    "Prepared by [Your name]"),
            k.numbers("Headline", [
                ("97.4%", "on time"),
                ("41.20", "taka / order"),
                ("4/6", "vehicles live"),
                ("2", "open risks"),
            ], lead="Against a 96 per cent target and a 45.00 cost line.",
               eyebrow="At a glance"),
            k.bars("On-time delivery by depot", [
                ("Kingsway", 98.2, "98.2%"),
                ("Narayanganj", 95.1, "95.1%"),
                ("Eastern line", 97.4, "97.4%"),
                ("Network", 97.1, "97.1%"),
            ], eyebrow="Measure one"),
            k.bars("Cost per order, last four weeks", [
                ("Week 41", 44.1, "44.10"),
                ("Week 42", 43.0, "43.00"),
                ("Week 43", 41.9, "41.90"),
                ("Week 44", 41.2, "41.20"),
            ], eyebrow="Measure two"),
            k.table("Runs that left late", ["Run", "Depot", "Late by", "Cause"],
                    [["E-14", "Narayanganj", "41 min", "Loading"],
                     ["E-22", "Narayanganj", "18 min", "Traffic"],
                     ["K-07", "Kingsway", "12 min", "Fuel"],
                     ["E-31", "Narayanganj", "55 min", "Loading"]],
                    eyebrow="Exceptions"),
            k.split("Moving, and stuck",
                    ("Moved this week", [
                        "Cost per order fell again, for the third week.",
                        "The second carrier's terms came back clean.",
                        "Relief pool agreed at the peak rate."]),
                    ("Stuck", [
                        "Loading at Narayanganj: two runs, same dock.",
                        "The tariff note is with Finance since Monday.",
                        "Driver briefing slips to the 04th."]),
                    eyebrow="Status"),
            k.timeline("What happens next", [
                ("Mon", "Dock study"),
                ("Wed", "Terms signed"),
                ("Fri", "Briefing"),
                ("+2wk", "First paid run"),
            ], eyebrow="Next"),
            k.closing("Two asks",
                      "A decision on the Narayanganj dock, and cover for the "
                      "peak rate on the relief pool.",
                      "Review again in week [00 + 1]"),
        ]

    return DeckTemplate(key="data-review", name="Data Review",
                        group="Reports",
                        blurb="Two bar charts, an exceptions grid, wins and blockers.",
                        detail="For the weekly or monthly review: every sheet "
                               "carries a figure rather than a sentence, and "
                               "the charts are shapes, so a bar can be moved, "
                               "relabelled or recoloured in the editor.",
                        build=build)


def startup_pitch() -> "DeckTemplate":
    """The investor deck: problem, solution, market, traction, ask."""
    pal = Palette(accent="#059669", wash="#ECFDF5", block="#065F46",
                  muted="#4B7A68")

    def build() -> List[Slide]:
        k = Kit(pal, "[Company] · [Day month year]")
        return [
            k.cover("Seed round", "Freight that does not sit still",
                    "We sell the second source that a growing route never has "
                    "time to find.",
                    "[Your name] · founder"),
            k.points("The problem",
                     "A route that works stops working the week it grows.",
                     ["Carriers are contracted once and reviewed never.",
                      "A missed window costs a store a week of shelf time.",
                      "Nobody can price the risk of a single source."],
                     eyebrow="Problem"),
            k.section("02", "What we do",
                      "A standing bench of vetted carriers, sold by the window "
                      "rather than the vehicle."),
            k.cards("How it works", [
                ("Bench", "Carriers we have audited, at the depot the customer "
                 "already uses."),
                ("Trigger", "A missed window, a peak week, or a strike — "
                 "covered the same day."),
                ("Measure", "The customer's own three numbers, reported "
                 "weekly, priced against them."),
            ], eyebrow="Model"),
            k.numbers("Traction", [
                ("6", "customers paying"),
                ("236k", "taka a month"),
                ("97.4%", "kept on time"),
                ("3.1x", "retention of spend"),
            ], lead="Signed in the last two quarters, with two more in terms.",
               eyebrow="Traction"),
            k.bars("Market, by spend", [
                ("Eastern corridor", 2.4, "2.4bn"),
                ("All regional", 7.8, "7.8bn"),
                ("We hold", 0.03, "2.8m"),
            ], eyebrow="Market"),
            k.timeline("The next four quarters", [
                ("Q1", "12 customers"),
                ("Q2", "Second city"),
                ("Q3", "Carrier portal"),
                ("Q4", "Break even"),
            ], eyebrow="Plan"),
            k.split("Why us",
                    ("We have done it", [
                        "Founded by the head of operations who ran the line.",
                        "First six customers came from one conversation each.",
                        "Every contract we hold renewed at a higher price."]),
                    ("What we are short of", [
                        "One engineer, hired by March.",
                        "A second city's bench, built not bought.",
                        "This round, to do both at once."]),
                    eyebrow="Team"),
            k.closing("The ask",
                      "Sixty crore weeks of runway to reach twelve customers "
                      "and a second city.",
                      "[name]@[company].com · +880 9000 0000"),
        ]

    return DeckTemplate(key="startup-pitch", name="Startup Pitch",
                        group="Business",
                        blurb="Problem, model, traction, market, ask.",
                        detail="The investor run in the order a room expects, "
                               "with a green ground, a market drawn as bars, "
                               "and the ask given its own full sheet.",
                        build=build)


def quarterly_results() -> "DeckTemplate":
    """Results day: deep red, restrained, with the numbers up front."""
    pal = Palette(accent="#8E2334", wash="#F7EDEF", block="#5E1722",
                  muted="#7B5560")

    def build() -> List[Slide]:
        k = Kit(pal, "Northbridge Distribution · results, quarter ended March")
        return [
            k.cover("Results", "Quarter ended March",
                    "Volume up nine per cent, cost per order down for the "
                    "third quarter running.",
                    "[Your name] · Head of Operations"),
            k.numbers("The quarter", [
                ("19,640", "orders received, +9.1%"),
                ("97.4%", "delivered on time"),
                ("41.20", "taka per order, -8.4%"),
                ("1.1%", "returns"),
            ], lead="Every measure the board set was met or beaten.",
               eyebrow="Headline"),
            k.bars("Against plan", [
                ("Orders", 109.1, "+9.1%"),
                ("On time", 101.5, "+1.4 pts"),
                ("Cost", 91.6, "-8.4%"),
                ("Returns", 73.3, "-0.4 pts"),
            ], eyebrow="Variance"),
            k.section("02", "The east",
                      "A fifth of the volume on one carrier, and two missed "
                      "windows in February."),
            k.table("What we are doing", ["Action", "Owner", "By", "Cost"],
                    [["Second carrier contracted", "[Name]", "14 Mar",
                      "236,000/mo"],
                     ["Relief pool at the depot", "[Name]", "28 Mar",
                      "Peak rate"],
                     ["Schedule published", "[Name]", "27 Mar", "None"]],
                    eyebrow="Actions"),
            k.quote("The quarter's real gain was not the volume. It was that we "
                    "absorbed it without adding a single vehicle.",
                    "Operations Board minutes"),
            k.closing("Outlook",
                      "Two risks stay open until April. Everything else is "
                      "ahead of plan.",
                      "Questions · [Your name]"),
        ]

    return DeckTemplate(key="quarterly-results", name="Quarterly Results",
                        group="Reports",
                        blurb="Results day: four headline figures, variance, outlook.",
                        detail="A serif-headed deck in a deep red, built for "
                               "reading out loud: figures first, variance "
                               "drawn as bars, and the outlook on its own "
                               "sheet at the end.",
                        build=build)


def workshop() -> "DeckTemplate":
    """A teaching deck: objectives, steps, practice, and a check at the end."""
    pal = Palette(accent="#B45309", wash="#FEF3C7", block="#92400E",
                  muted="#7C5E21")

    def build() -> List[Slide]:
        k = Kit(pal, "Workshop · 90 minutes · [Your name]")
        return [
            k.cover("Workshop", "Reading a route schedule",
                    "What the sheet says, what it leaves out, and what to ask "
                    "for at the gate.",
                    "Ninety minutes · two depots"),
            k.agenda("By the end you will be able to", [
                "Read a run's window off the schedule in ten seconds",
                "Say which of the three measures a late run breaks",
                "Raise an exception the way the depot logs it",
                "Know who to call, and about what",
            ], eyebrow="Objectives"),
            k.section("01", "The sheet",
                      "Every line is a promise about a vehicle and a window."),
            k.steps("How to read one line", [
                ("1", "The run code", "E for eastern, K for Kingsway. The "
                 "number is the order the vehicle leaves."),
                ("2", "The window", "Two times, not one. The later is the "
                 "promise the customer is given."),
                ("3", "The dock", "Which bay it loads at, and therefore who to "
                 "find when it has not moved."),
            ], eyebrow="Practice"),
            k.split("Do, and do not",
                    ("Do", ["Read the window, not the departure time.",
                            "Log an exception the moment it is known.",
                            "Ask for the cause, not an apology."]),
                    ("Do not", ["Treat a schedule as a forecast.",
                                "Wait for the Friday sheet.",
                                "Change a run without telling the store."]),
                    eyebrow="Rules"),
            k.points("Three measures",
                     "Everything on the sheet is there to move one of these.",
                     ["On-time delivery: the window the customer was given.",
                      "Cost per order: what the run cost, all in.",
                      "Runs leaving on schedule: the depot's own promise."],
                     eyebrow="Measures"),
            k.cards("Check yourself", [
                ("A run is 40 minutes late",
                 "Which measure breaks, and who is told before the truck "
                 "moves?"),
                ("The window says 09:00 to 11:00",
                 "What time does the store plan for, and why not 09:00?"),
                ("The dock is busy at 07:20",
                 "What do you log, against which run, and by when?"),
            ], eyebrow="Exercise"),
            k.closing("One thing to take away",
                      "The schedule is a promise. Everything else on the sheet "
                      "is there to keep it.",
                      "Questions · then back to the gate"),
        ]

    return DeckTemplate(key="workshop", name="Workshop",
                        group="Teaching",
                        blurb="Objectives, steps, do and do not, an exercise.",
                        detail="Built for training: objectives stated as "
                               "outcomes, a numbered process, a two-column "
                               "rules sheet, and three exercise cards the room "
                               "can answer out loud.",
                        build=build)


def editorial_serif() -> "DeckTemplate":
    """A lecture deck in serif: long lines, washes, and a quote per chapter."""
    pal = Palette(accent="#7C2D12", ink="#1C1917", muted="#78716C",
                  wash="#FAF5F2", rule="#E7DDD5", block="#7C2D12", serif=True)

    def build() -> List[Slide]:
        k = Kit(pal, "[Course code] · [Day month year]")
        return [
            k.cover("A lecture", "The cartographic eye",
                    "Surveys of the eastern river, 1880 to 1930, read as the "
                    "work of offices rather than of the ground.",
                    "[Your name] · [Institution]"),
            k.points("The question",
                     "Why do two sheets of the same reach, twenty years apart, "
                     "disagree about a market that did not move?",
                     ["The surveys are catalogued as records of the channel.",
                      "They are also records of who paid to have it drawn.",
                      "The second fact explains the first."],
                     eyebrow="I"),
            k.agenda("The hour", [
                "The first series, 1880 to 1893",
                "The department's reconstitution",
                "The 1898 and 1901 sheets, laid together",
                "What a change of interest looks like",
            ]),
            k.section("II", "The first series",
                      "A channel drawn once, lettered as a settled thing."),
            k.quote("The sheet does not argue. It merely declines to "
                    "argue — which, in an office, is an argument.",
                    "[Name], on the earlier surveys"),
            k.split("1898, and then 1901",
                    ("1898", ["The river market at Narayanganj is drawn twice.",
                              "Soundings across the whole reach."]),
                    ("1901", ["The market is absent.",
                              "One letterspaced line where the soundings were.",
                              "A new mandate over river trade that year."]),
                    eyebrow="III"),
            k.points("Reading against, not along",
                     "Laid side by side, the silences become evidence.",
                     ["What is omitted changes when the office changes.",
                      "What is lettered changes when the reader does.",
                      "The river holds still through both."],
                     eyebrow="IV"),
            k.closing("For next week",
                      "Bring one map that disagrees with another, and we will "
                      "ask which of them has an office behind it.",
                      "Reading list on the course page"),
        ]

    return DeckTemplate(key="editorial-serif", name="Editorial Serif",
                        group="Editorial",
                        blurb="Serif throughout, warm washes, a quote per chapter.",
                        detail="For a lecture or a long argument: every face on "
                               "the sheet is a serif, the accent is a rust that "
                               "prints well, and the sections are full sheets "
                               "of it.",
                        build=build)


def project_kickoff() -> "DeckTemplate":
    """The deck a project opens with: scope, owners, dates, risks."""
    pal = Palette(accent="#3B4CCA", wash="#ECEFFB", block="#2A3A99",
                  muted="#5B67A0")

    def build() -> List[Slide]:
        k = Kit(pal, "[Project] · kickoff · [Day month year]")
        return [
            k.cover("Kickoff", "Eastern line: the second carrier",
                    "Six vehicles, one coordinator, and four weeks to a first "
                    "paid run.",
                    "Sponsor [Name] · lead [Your name]"),
            k.points("What is in scope",
                     "One contracted line on the Narayanganj route, and the "
                     "reporting that proves it works.",
                     ["Six vehicles held at the depot in use.",
                      "A named coordinator, in place before the first run.",
                      "Weekly reporting against three measures."],
                     eyebrow="Scope"),
            k.split("And what is not",
                    ("Outside", ["The western route.",
                                 "Any change to the customer tariff.",
                                 "The Narayanganj lease."]),
                    ("Depends on us", ["Terms signed by the 14th.",
                                       "Stores clearing the second dock.",
                                       "Finance on the peak rate."]),
                    eyebrow="Boundaries"),
            k.agenda("Who is accountable", [
                "Carrier contract — [Name], with Finance",
                "Depot readiness — [Name], with Stores",
                "Driver briefing — [Name], with the depot",
                "Measurement — [Name], with the board office",
            ], eyebrow="Owners"),
            k.timeline("The four weeks", [
                ("Wk 1", "Terms signed"),
                ("Wk 2", "Vehicles assigned"),
                ("Wk 3", "Drivers briefed"),
                ("Wk 4", "First paid run"),
            ], eyebrow="Plan"),
            k.table("What could go wrong", ["Risk", "If it happens", "Owner"],
                    [["Second source late", "Hold the old line a month",
                      "[Name]"],
                     ["Drivers unavailable", "Relief pool at the peak rate",
                      "[Name]"],
                     ["Fuel above boundary", "Pass it through at tariff",
                      "[Name]"]],
                    eyebrow="Risks"),
            k.numbers("What done looks like", [
                ("96%+", "on time, four weeks running"),
                ("2", "reports the board did not ask for"),
                ("0", "changes to customer windows"),
            ], lead="Measured at the close of week four, then weekly.",
               eyebrow="Definition of done"),
            k.closing("This week",
                      "Terms to signature by Friday, and the dock study booked "
                      "for Monday.",
                      "Next review: [Day month year]"),
        ]

    return DeckTemplate(key="project-kickoff", name="Project Kickoff",
                        group="Plans",
                        blurb="Scope, owners, a four-week plan, risks, done.",
                        detail="The deck a project opens with: what is in and "
                               "out, who owns each workstream, the plan in "
                               "chevrons, and a definition of done stated as "
                               "three figures.",
                        build=build)


def annual_review() -> "DeckTemplate":
    """The year in one sitting: a figure per sheet and a look ahead."""
    pal = Palette(accent="#0F6E5F", wash="#E8F3F0", block="#0B4A40",
                  muted="#4E7A70")

    def build() -> List[Slide]:
        k = Kit(pal, "Northbridge Distribution · year in review")
        return [
            k.cover("Year in review", "Twelve months on two depots",
                    "What the network carried, what it cost, and what we are "
                    "asking for next.",
                    "[Your name] · [Day month year]"),
            k.numbers("The year", [
                ("74,900", "orders moved"),
                ("96.8%", "on time, all four quarters"),
                ("39.90", "taka per order, from 46.80"),
                ("214", "people employed"),
            ], eyebrow="Headline"),
            k.bars("Volume by quarter", [
                ("Q1", 17.4, "17,400"),
                ("Q2", 18.2, "18,200"),
                ("Q3", 19.7, "19,700"),
                ("Q4", 19.6, "19,600"),
            ], eyebrow="Growth"),
            k.section("02", "What we learned",
                      "Three things we did not know in January."),
            k.cards("Three lessons", [
                ("Redundancy pays", "The two missed windows cost less than a "
                 "standing second source would have — until they did not."),
                ("Publish the schedule", "Customers forgave a late run they "
                 "could see coming, and one they could not."),
                ("The depot is the constraint", "Every late run this year "
                 "started at a dock, not on the road."),
            ], eyebrow="Lessons"),
            k.quote("We spent the year finding out where the network actually "
                    "breaks. It breaks at the gates.",
                    "[Your name], year-end meeting"),
            k.timeline("Next year", [
                ("Q1", "Second carrier"),
                ("Q2", "Dock study"),
                ("Q3", "Third depot?"),
                ("Q4", "Tariff review"),
            ], eyebrow="Ahead"),
            k.closing("The ask",
                      "A second carrier for the east, a dock study at "
                      "Narayanganj, and one engineer.",
                      "Questions · [Your name]"),
        ]

    return DeckTemplate(key="annual-review", name="Annual Review",
                        group="Reports",
                        blurb="The year in figures, lessons, and an ask.",
                        detail="Twelve months told in one sitting: a figure per "
                               "sheet, three lessons in panels, and the year "
                               "ahead in chevrons.",
                        build=build)


@dataclass(frozen=True)
class DeckTemplate:
    """One design the gallery offers: its name, its use, and how to build it.

    The slides are built on demand rather than kept, because a deck handed to
    the user is a deck they will edit, and two openings must never share a
    :class:`Slide` object.
    """

    key: str
    name: str
    group: str
    blurb: str
    detail: str
    build: Callable[[], List[Slide]] = field(default=lambda: [])

    def slides(self) -> List[Slide]:
        """A fresh run of this design's sheets."""
        return self.build()

    def apply_to(self, presentation) -> None:
        """Replace what *presentation* holds with this design's sheets.

        The deck's own size is left alone: PresentR draws at 960 by 540, and a
        design that assumed anything else would land misaligned.
        """
        presentation.slides = self.build()
        if not presentation.title or presentation.title == "Untitled Presentation":
            presentation.title = self.name

    def preview(self, width: int = TILE_WIDTH) -> QPixmap:
        """The gallery's picture: the sheet the deck opens on."""
        first = self.build()[0]
        return render_slide_to_pixmap(first, width, (WIDE, TALL))


#: Every design the gallery holds, in the order its tiles appear.
DECK_TEMPLATES: Tuple[DeckTemplate, ...] = (
    corporate_brief(),
    executive_dark(),
    minimal_mono(),
    bold_splash(),
    data_review(),
    startup_pitch(),
    quarterly_results(),
    workshop(),
    editorial_serif(),
    project_kickoff(),
    annual_review(),
)


def deck_named(key: str) -> Optional[DeckTemplate]:
    """The design called *key*, which is how a gallery answer becomes a deck."""
    return next((each for each in DECK_TEMPLATES if each.key == key), None)


def build_deck_tiles(width_px: int = TILE_WIDTH,
                     templates: Optional[Sequence[DeckTemplate]] = None) -> dict:
    """Photograph each design's opening sheet, at the tile's width.

    The picture comes from the same renderer the thumbnail pane uses, so what
    the gallery shows is what the editor will hold.
    """
    tiles = {}
    for each in (templates or DECK_TEMPLATES):
        tiles[each.key] = each.preview(width_px)
    return tiles


def gallery_entries(templates: Sequence[DeckTemplate],
                    tiles: dict) -> List[GalleryEntry]:
    """The gallery's tiles, in the order the designs are listed."""
    return [GalleryEntry(key=each.key, name=each.name, blurb=each.blurb,
                         group=each.group, preview=tiles.get(each.key),
                         detail=each.detail or f"{each.group} — {each.blurb}")
            for each in templates]
