"""WriteR's gallery: fourteen ready-dressed documents.

Each design is written here as blocks rather than as a stored file, so a
template reads top to bottom the way the finished page reads, and so a design
can lean on WriteR's own page dress -- border, mark, header and footer --
instead of faking them with paragraphs.

The copy in square brackets is meant to be typed over. Everything else is the
kind of sentence that belongs in the document, because a design can only be
judged for spacing and weight when the words in it are the right length.
"""

from typing import List, Optional, Sequence, Tuple

from officer.writer.templates import (ACCENT, ACCENT_WASH, HAIRLINE, INK, MUTED,
                                      SERIF_CHAIN, SANS_CHAIN, Bullets, Gap,
                                      PageBreak, Rule, Table, Template, Text)

#: The groups the gallery sorts itself by, in the order it shows them.
GROUPS: Tuple[str, ...] = ("Reports", "Business", "Letters", "Plans",
                           "Editorial", "Academic")

#: A hairline the colour of paper: a grid set without any rules showing.
BORDERLESS = "#FFFFFF"


class Kit:
    """One design's type system, so its headings and body never drift apart.

    Every method answers with a block. A block leaves the colours it does not
    care about to the template, which is where the palette actually lives.
    """

    def __init__(self, accent: str = ACCENT, head: Tuple[str, ...] = SANS_CHAIN,
                 body: Tuple[str, ...] = SANS_CHAIN, ink: str = INK,
                 muted: str = MUTED, wash: str = ACCENT_WASH,
                 spacing: float = 1.12, space_body: float = 7.0):
        self.accent = accent
        self.head = head
        self.body = body
        self.ink = ink
        self.muted = muted
        self.wash = wash
        self.spacing = spacing
        self.space_body = space_body

    # -- headings ------------------------------------------------------------ #

    def _text(self, kw: dict, **defaults) -> Text:
        """A paragraph in this design's face, with the caller's word last.

        Every helper below states its own typographic defaults and then folds in
        whatever the template asked for, so a heading can be moved two points or
        re-centered without a second copy of the heading's definition.
        """
        return Text(**{**defaults, **kw})

    def title(self, text: str, **kw) -> Text:
        return self._text(kw, text=text, size=30.0, bold=True,
                          family=self.head, colour=self.ink, below=4)

    def h1(self, text: str, **kw) -> Text:
        return self._text(kw, text=text, size=15.5, bold=True,
                          family=self.head, colour=self.accent,
                          above=15, below=4)

    def h2(self, text: str, **kw) -> Text:
        return self._text(kw, text=text, size=12.5, bold=True,
                          family=self.head, colour=self.ink,
                          above=11, below=3)

    def label(self, text: str, **kw) -> Text:
        """An eyebrow: small, tracked out, upper case, in the design's accent."""
        kw.setdefault("colour", self.accent)
        return self._text(kw, text=text, size=8.5, bold=True, caps=True,
                          tracking=14, below=3)

    # -- writing ------------------------------------------------------------- #

    def para(self, text: str, **kw) -> Text:
        return self._text(kw, text=text, family=self.body, colour=self.ink,
                          below=self.space_body)

    def lead(self, text: str, **kw) -> Text:
        """The standing paragraph under a headline: larger, quieter."""
        return self._text(kw, text=text, size=13, italic=True,
                          colour=self.muted, family=self.body, below=10)

    def note(self, text: str, **kw) -> Text:
        return self._text(kw, text=text, size=9, colour=self.muted,
                          family=self.body, below=4)

    def bullets(self, items: Sequence[str], **kw) -> Bullets:
        return self._list(kw, items)

    def numbers(self, items: Sequence[str], **kw) -> Bullets:
        return self._list(kw, items, numbered=True)

    def _list(self, kw: dict, items: Sequence[str], **defaults) -> Bullets:
        return Bullets(**{"items": list(items), "family": self.body,
                          "colour": self.ink, "below": self.space_body,
                          **defaults, **kw})

    def quote(self, text: str, attribution: str = "") -> List:
        """A pull quote: rules above and below, drawn in from both margins."""
        blocks = [Rule(colour=self.accent, weight=1.6, width_pct=100,
                       above=8, below=10),
                  Text(text, size=13.5, italic=True, family=self.head,
                       colour=self.ink, left=30, right=30, below=4,
                       spacing=1.18)]
        if attribution:
            blocks.append(Text(attribution, size=9.5, colour=self.muted,
                               left=30, right=30, align="right", below=6))
        blocks.append(Rule(colour=self.accent, weight=1.6, above=6, below=14))
        return blocks

    # -- furniture ----------------------------------------------------------- #

    def rule(self, width_pct: float = 100.0, colour: Optional[str] = None,
             weight: float = 1.0, above: float = 5, below: float = 9,
             align: str = "left") -> Rule:
        return Rule(colour=colour or HAIRLINE, weight=weight,
                    width_pct=width_pct, above=above, below=below, align=align)

    def band(self, text: str, ink: str = "#FFFFFF", height: float = 9.0,
             size: float = 12.0, align: str = "left") -> Text:
        """A strip of the design's colour across the whole column."""
        return Text(text or " ", fill=self.accent, fill_ink=ink, size=size,
                    bold=True, family=self.head, align=align,
                    above=height, below=height)

    def gap(self, px: float = 12.0) -> Gap:
        return Gap(px)

    def page_break(self) -> PageBreak:
        return PageBreak()

    def table(self, rows: Sequence[Sequence[str]], **kw) -> Table:
        kw.setdefault("family", self.body)
        kw.setdefault("ink", self.ink)
        kw.setdefault("shade", self.wash)
        kw.setdefault("rule", HAIRLINE)
        return Table(rows=[list(row) for row in rows], **kw)

    def facts(self, rows: Sequence[Sequence[str]], label_width: float = 26.0,
              size: float = 10.5) -> Table:
        """A label-and-value block with no visible grid at all."""
        return Table(rows=[list(row) for row in rows],
                     widths=[label_width, 100.0 - label_width],
                     aligns="ll", header=False, rule=BORDERLESS,
                     shade=BORDERLESS, stripe="", size=size, family=self.body,
                     ink=self.ink, pad=2.0, above=2, below=8)

    def split(self, left: str, right: str, size: float = 11.0,
              bold: bool = False, colour: Optional[str] = None,
              below: float = 10.0) -> Table:
        """Two words at opposite ends of the column, with no rule between them."""
        return Table(rows=[[left, right]], widths=[62, 38], aligns="lr",
                     header=False, rule=BORDERLESS, shade=BORDERLESS,
                     size=size, bold_cells=((0, 0), (0, 1)) if bold else (),
                     family=self.body,
                     ink=colour or self.ink, pad=1.0, above=4, below=below)


# --------------------------------------------------------------------------- #
# reports                                                                     #
# --------------------------------------------------------------------------- #

def cover_page() -> Template:
    """The sheet a document is handed over with: nothing but its name."""
    k = Kit(accent="#1F3864", head=SERIF_CHAIN, wash="#F2F4F8")
    return Template(
        key="cover-page", name="Cover Page", group="Reports",
        blurb="A title sheet for a document handed over in person.",
        detail="Serif display type, a rule of the accent colour, and room at the "
               "foot of the sheet for whose name is on it.",
        body_family=SERIF_CHAIN, head_family=SERIF_CHAIN, accent="#1F3864",
        border={"style": "box", "colour": "#1F3864", "width_pt": 1.5},
        blocks=(
            k.gap(150),
            k.label("Prepared for review", align="centre"),
            k.title("Quarterly Operations Review", size=38, align="centre",
                    below=6),
            k.rule(width_pct=26, colour="#1F3864", weight=2.4, above=8, below=14,
                   align="centre"),
            k.lead("Northbridge Distribution · January to March",
                   align="centre", size=13),
            k.gap(58),
            k.para("Prepared by   [Your name], Head of Operations",
                   align="centre", size=11, below=2),
            k.para("Reviewed by   [Second name]", align="centre", size=11, below=2),
            k.para("Issued   [Day month year]", align="centre", size=11, below=2),
            k.gap(46),
            k.note("Northbridge Distribution · 12 Kingsway, Dhaka 1205 · "
                   "+880 9000 0000", align="centre"),
        ))


def business_report() -> Template:
    """Word's report: a title block, numbered sections, and sheets counted."""
    k = Kit(accent="#2C5697", head=SERIF_CHAIN)
    return Template(
        key="business-report", name="Business Report", group="Reports",
        blurb="Title block, findings, a table, page numbers in the band.",
        detail="Opens on a title block rather than a separate cover, carries the "
               "document's name in the header and its count in the footer from "
               "the second sheet.",
        body_family=SERIF_CHAIN, head_family=SERIF_CHAIN, accent="#2C5697",
        bands={"header": {"left": "Quarterly Operations Review",
                          "right": "[Your name]"},
               "footer": {"centre": "Page {PAGE} of {PAGES}",
                          "right": "Confidential"},
               "show_first_page": False},
        blocks=(
            k.gap(2),
            k.label("Report for the quarter ended March", colour=k.muted),
            k.title("Quarterly Operations Review", size=24, below=2),
            k.rule(colour=k.accent, weight=2.2, below=10),
            k.facts([["Prepared for", "[Director's name], Operations Board"],
                     ["Prepared by", "[Your name], Head of Operations"],
                     ["Issued", "[Day month year] · status Final"]]),
            k.h1("1.  Summary", above=11),
            k.para("Volume grew nine per cent against the previous quarter while "
                   "the cost of serving an order fell for the third quarter "
                   "running.", align="justify"),
            k.bullets([
                "On-time delivery held at 97.4 per cent, against a target of 96.",
                "Cost per order fell to 41.20 taka.",
                "Two of the nine risks carried into the quarter remain open.",
            ]),
            k.h1("2.  Performance against plan", above=11),
            k.table(
                [["Measure", "Target", "Actual", "Variance"],
                 ["Orders received", "18,000", "19,640", "+9.1%"],
                 ["Delivered on time", "96.0%", "97.4%", "+1.4 pts"],
                 ["Cost per order", "45.00", "41.20", "-8.4%"],
                 ["Returns", "1.5%", "1.1%", "-0.4 pts"]],
                widths=[38, 20, 20, 22], aligns="lccc", size=10, pad=4),
            k.h1("3.  Recommendations", above=11),
            k.numbers([
                "Keep the second depot open on Saturdays through the peak.",
                "Bring the carrier review forward to the first week of May.",
            ]),
            k.note("Appendix A, fleet and route data, is supplied separately."),
        ))


def draft_report() -> Template:
    """The same report while it is still a draft, said plainly on the page."""
    base = business_report()
    return Template(
        key="draft-report", name="Draft Report", group="Reports",
        blurb="The report design with a diagonal DRAFT behind the words.",
        detail="Identical to Business Report apart from the mark and a dashed "
               "border, both of which say the document is not yet for issue.",
        body_family=base.body_family, head_family=base.head_family,
        accent=base.accent,
        border={"style": "dashed", "colour": "#9CA3AF", "width_pt": 1.0},
        mark={"kind": "text", "text": "DRAFT", "size_pt": 88,
              "colour": "#BFBFBF", "layout": "diagonal", "opacity": 0.55,
              "scale": 70},
        blocks=base.blocks)


# --------------------------------------------------------------------------- #
# letters                                                                     #
# --------------------------------------------------------------------------- #

def business_letter() -> Template:
    """Block-style letter: everything flush left, an inch of air between parts."""
    k = Kit(accent="#1F2937", head=SERIF_CHAIN, body=SANS_CHAIN)
    return Template(
        key="business-letter", name="Business Letter", group="Letters",
        blurb="Block-style letterhead, counted from the second sheet.",
        detail="Sender's block, rule, date, inside address, subject line and "
               "signature block. The footer stays off the first page so the top "
               "of a letter reads as a letter.",
        body_size=11,
        bands={"header": {},
               "footer": {"left": "[Your name] · [Company]",
                          "right": "Page {PAGE} of {PAGES}"},
               "show_first_page": False},
        blocks=(
            k.title("[Your name]", size=22, align="centre", below=1),
            k.para("Head of Operations · [Company]", align="centre",
                   colour=k.muted, size=10, below=1),
            k.para("12 Kingsway, Dhaka 1205 · +880 9000 0000 · "
                   "you@example.com", align="centre", colour=k.muted, size=9.5,
                   below=4),
            k.rule(colour=k.accent, weight=1.6, above=2, below=16),
            k.para("[Day month year]", below=14),
            k.para("[Recipient's name]\nHead of Procurement\nNorthbridge "
                   "Distribution\n47 Gulshan Avenue\nDhaka 1212", below=14),
            k.para("Subject:  Renewal of the delivery contract for the "
                   "Narayanganj line", bold=True, below=12),
            k.para("Dear [Name],", below=11),
            k.para("Thank you for the draft terms sent on [date]. We are content "
                   "to renew on the pricing proposed, and have taken the liberty "
                   "of setting out below the two clauses we would like amended "
                   "before signature.", align="justify"),
            k.para("The first is the liability window in clause 8. A period of "
                   "fourteen days from delivery is shorter than the time our own "
                   "customers allow us to reject a consignment.",
                   align="justify"),
            k.para("The second is the review point in clause 12. We would prefer "
                   "it to fall at the end of the sixth month rather than the "
                   "twelfth, since that is when the redrawn routes are next "
                   "measured.", align="justify"),
            k.para("Neither should take long to settle, and we would be glad to "
                   "host a call during the week of [date].", align="justify",
                   below=16),
            k.para("With kind regards,", below=28),
            k.para("[Your name]", bold=True, below=1),
            k.para("Head of Operations · [Company]", size=10, colour=k.muted,
                   below=14),
            k.note("Enclosed:  revised route schedule, February performance pack"),
        ))


# --------------------------------------------------------------------------- #
# business                                                                    #
# --------------------------------------------------------------------------- #

def proposal() -> Template:
    """A proposal: what was heard, what is offered, what it costs, when."""
    k = Kit(accent="#0F6E5F", wash="#E8F3F0")
    return Template(
        key="proposal", name="Proposal", group="Business",
        blurb="What we heard, what we propose, what it costs.",
        detail="Opens on a band of the design's green, sets the headline numbers "
               "in a three-cell row, and closes with priced options and timings.",
        accent="#0F6E5F",
        bands={"footer": {"left": "[Company] · proposal [ref]",
                          "centre": "Page {PAGE} of {PAGES}",
                          "right": "Valid 60 days"},
               "show_first_page": True},
        blocks=(
            k.band("PROPOSAL  ·  [Company]  ·  [Day month year]", height=13),
            k.gap(6),
            k.title("A second delivery line for the eastern route", size=21,
                    below=3),
            k.lead("Submitted to [Client name] on [date], in answer to your "
                   "request.", below=8),
            k.h1("What we understood", above=11),
            k.para("Your volume on the eastern route has outgrown the single "
                   "carrier you hold, and the two missed windows in February cost "
                   "you a week of shelf time.", align="justify"),
            k.h1("What we propose", above=11),
            k.table(
                [["97.4%", "41.20", "6"],
                 ["on time, both depots", "taka per order",
                  "days to go live"]],
                widths=[34, 33, 33], aligns="lll", header=False,
                rule=BORDERLESS, shade=k.wash, size=15,
                bold_cells=((0, 0), (0, 1), (0, 2)), ink=k.accent,
                pad=6, below=10),
            k.numbers([
                "One contracted line of six vehicles, held at the depot you "
                "already use.",
                "A named coordinator, in place before the first run.",
            ]),
            k.h1("What it costs", above=11),
            k.table(
                [["Option", "Vehicles", "Monthly", "Includes"],
                 ["Standard", "4", "180,000", "Daytime windows, shared coordinator"],
                 ["Recommended", "6", "236,000", "Both windows, named coordinator"]],
                widths=[24, 14, 18, 44], aligns="lccl", size=10,
                bold_cells=((2, 0), (2, 1), (2, 2), (2, 3))),
            k.para("Prices hold sixty days and exclude fuel beyond the boundary. "
                   "Signed in week 1, briefed by week 3, first paid run in "
                   "week 4.", size=10, colour=k.muted, below=8),
            k.rule(colour=k.accent, weight=1.6),
            k.note("To accept, sign and return this page, or call [name] on "
                   "+880 9000 0000."),
        ))


def invoice() -> Template:
    """An invoice that reads at a glance: what, when, how much, where to pay."""
    k = Kit(accent="#1F3864", wash="#EDF1F8")
    return Template(
        key="invoice", name="Invoice", group="Business",
        blurb="Line items, a shaded head, totals kept on the right.",
        detail="Sets the word INVOICE against your own block, keeps the money in "
               "a right-hand column, and puts the banking in the footer band.",
        accent="#1F3864", margin_px=72,
        bands={"header": {},
               "footer": {"left": "[Bank] · account [0000 0000] · routing [000]",
                          "right": "Thank you"},
               "show_first_page": True},
        blocks=(
            k.title("[Company name]", size=19, below=1),
            k.para("12 Kingsway, Dhaka 1205 · +880 9000 0000 · "
                   "billing@example.com", size=9.5, colour=k.muted, below=2),
            k.split("INVOICE  [Number]", "[Day month year]", size=17,
                    bold=True, colour=k.accent, below=8),
            k.rule(colour=k.accent, weight=2.4, above=0, below=14),
            k.table(
                [["Billed to", "Terms", "Due"],
                 ["Northbridge Distribution\n47 Gulshan Avenue\nDhaka 1212",
                  "14 days", "[Day month year]"]],
                widths=[50, 20, 30], aligns="lll", size=10, shade=k.wash),
            k.table(
                [["Description", "Qty", "Rate", "Amount"],
                 ["Delivery, eastern line, daytime window", "148", "1,320", "195,360"],
                 ["Delivery, eastern line, evening window", "62", "1,610", "99,820"],
                 ["Coordinator, named, monthly", "1", "18,000", "18,000"],
                 ["Fuel adjustment outside the boundary", "1,240 km", "12", "14,880"]],
                widths=[52, 12, 16, 20], aligns="lccc", size=10.5),
            k.table(
                [["Subtotal", "328,060"],
                 ["VAT at 15%", "49,209"],
                 ["Total due", "377,269"]],
                widths=[68, 32], aligns="lr", header=False, size=10.5,
                rule=HAIRLINE, stripe=k.wash, shade=BORDERLESS,
                bold_cells=((0, 0), (0, 1), (2, 0), (2, 1)), below=16),
            k.para("Terms", bold=True, size=10, below=2),
            k.para("Payment is due within fourteen days of the date above. Late "
                   "settlement carries the rate in clause 6 of the delivery "
                   "agreement. Please quote the invoice number on the transfer so "
                   "the receipt reaches the right account.", size=10,
                   colour=k.muted, below=10),
            k.note("Prepared by [Your name] · [Day month year]"),
        ))


def purchase_order() -> Template:
    """A purchase order: what is being bought, on what terms, signed for."""
    k = Kit(accent="#7C3A20", wash="#F7EFE9")
    return Template(
        key="purchase-order", name="Purchase Order", group="Business",
        blurb="Buyer and supplier facing each other over a ruled grid.",
        detail="The order's own facts sit up top, supplier and destination face "
               "each other, the goods are ruled, and the authorisation line is "
               "left ready to sign.",
        accent="#7C3A20", margin_px=72,
        border={"style": "box", "colour": "#D8CCC4", "width_pt": 0.75},
        blocks=(
            k.title("Purchase Order", size=24, below=2),
            k.facts([["Order number", "[PO 0000]"],
                     ["Requisition", "[RQ 0000]"],
                     ["Date raised", "[Day month year]"],
                     ["Currency", "Bangladeshi taka"]], label_width=30),
            k.table(
                [["Supplier", "Deliver to"],
                 ["Acme Stationers Ltd\nKarwan Bazar, Dhaka 1215\n+880 9111 111",
                  "Northbridge Distribution\n12 Kingsway, Dhaka 1205\n"
                  "Attn: stores, 09:00 to 17:00"]],
                widths=[50, 50], aligns="ll", size=10, shade=k.wash),
            k.table(
                [["Item", "Code", "Qty", "Unit", "Rate", "Amount"],
                 ["Copy paper, A4, 80gsm", "PP-A4-80", "120", "ream", "410", "49,200"],
                 ["Archive box, letter, 80mm", "AB-LTR", "40", "each", "260", "10,400"],
                 ["Toner, black, 2,600 pages", "TN-BLK", "6", "each", "3,950", "23,700"],
                 ["Courier envelope, 250 pack", "CE-250", "2", "pack", "1,480", "2,960"]],
                widths=[30, 14, 8, 10, 16, 22], aligns="llcrrr", size=10),
            k.table([["Goods", "86,260"], ["Delivery", "1,500"],
                     ["Total", "87,760"]],
                    widths=[70, 30], aligns="lr", header=False, size=10.5,
                    rule=HAIRLINE, stripe=k.wash, shade=BORDERLESS,
                    bold_cells=((2, 0), (2, 1)), below=14),
            k.note("Delivery required by [date]. Goods received in the condition "
                   "of sale will be paid within thirty days of the month end."),
            k.gap(16),
            k.table([["Authorised by", "Date", "Signature"],
                     ["[Name, role]", "", ""]],
                    widths=[40, 20, 40], aligns="lll", size=10, shade=k.wash),
        ))


def resume() -> Template:
    """A résumé that holds one page: name, then what you did, dates on the right."""
    k = Kit(accent="#243B53", spacing=1.06, space_body=6.0)
    return Template(
        key="resume", name="Résumé", group="Business",
        blurb="One page: name tracked out, dates on the right, rules between.",
        detail="Half-inch margins so the page holds, section labels in the "
               "design's slate, each role a borderless row with its dates kept "
               "off the left edge.",
        accent="#243B53", margin_px=48, body_size=10.5, spacing=1.06,
        space_body=6.0,
        blocks=(
            k.title("[Your name]", size=25, below=1),
            k.para("Head of Operations · Eastern corridor", size=12,
                   colour=k.accent, below=1),
            k.para("Dhaka 1205 · +880 9000 0000 · you@example.com · example.com/me",
                   size=9.5, colour=k.muted, below=8),
            k.rule(colour=k.accent, weight=2.0, above=0, below=10),
            k.h1("Profile"),
            k.para("Operations lead with eleven years behind a delivery network: "
                   "two depots, 340 stores, 19,000 orders a quarter. I have "
                   "redrawn a route map while the trucks were running, taken cost "
                   "per order down for three quarters together, and hired the "
                   "people who had to live with the change.", below=10),
            k.h1("Experience"),
            k.table([["Head of Operations · Northbridge Distribution",
                      "Mar 2019 — present"],
                     ["Depot manager, Kingsway · Northbridge",
                      "Jul 2014 — Feb 2019"],
                     ["Transport planner · Karwan Logistics",
                      "Aug 2011 — Jun 2014"]],
                    widths=[76, 24], aligns="lr", header=False,
                    rule=BORDERLESS, shade=BORDERLESS, size=11,
                    bold_cells=((0, 0), (1, 0), (2, 0)), pad=1, above=0,
                    below=2),
            k.gap(4),
            k.label("Northbridge · Head of Operations · since 2019",
                    colour=k.muted),
            k.bullets([
                "Cut cost per order from 45.00 to 41.20 taka across three "
                "quarters by redrawing the eastern and western routes together.",
                "Held on-time delivery at 97.4 per cent through a nine per cent "
                "volume rise, without adding a vehicle.",
                "Contracted and started a second carrier on the eastern line in "
                "six weeks.",
            ], size=10.5, below=8),
            k.label("Northbridge · Depot manager · 2014 to 2019", colour=k.muted),
            k.bullets([
                "Grew the depot from 41 to 96 staff and opened the Saturday "
                "window without a pay dispute.",
                "Took receiving errors from 3.1 per cent to 0.8 per cent in "
                "eighteen months.",
            ], size=10.5, below=8),
            k.h1("Education"),
            k.table([["BSc (Eng), Industrial · [University]", "2007 — 2011"],
                     ["Diploma, Supply Chain · [Institute]", "2013"]],
                    widths=[76, 24], aligns="lr", header=False,
                    rule=BORDERLESS, shade=BORDERLESS, size=10.5, pad=1,
                    above=0, below=8),
            k.h1("Skills"),
            k.facts([["Languages", "Bangla (native) · English (professional)"],
                     ["Systems", "Dispatch, routing, the spreadsheets between them"],
                     ["Also", "Shift rotas, incident review, hiring drivers"]],
                    label_width=20),
        ))


# --------------------------------------------------------------------------- #
# plans                                                                       #
# --------------------------------------------------------------------------- #

def meeting_minutes() -> Template:
    """Minutes that answer who, when, and what is owed by whom."""
    k = Kit(accent="#1B4B43", wash="#E9F2F0")
    return Template(
        key="meeting-minutes", name="Meeting Minutes", group="Plans",
        blurb="Attendance, agenda, decisions, and an actions grid.",
        detail="The facts of the meeting sit in a label-and-value block up top, "
               "the decisions follow as numbered headings, and everything owed "
               "lands in an owner-and-date table.",
        accent="#1B4B43",
        bands={"header": {"left": "Operations board · minutes"},
               "footer": {"centre": "Page {PAGE} of {PAGES}"},
               "show_first_page": True},
        blocks=(
            k.title("Operations Board — minutes", size=22, below=1),
            k.para("Second meeting of the quarter · Kingsway depot, room 2",
                   size=10, colour=k.muted, below=10),
            k.facts([["Date", "[Day month year], 10:00 to 11:35"],
                     ["Chair", "[Name], Operations Director"],
                     ["Present", "[Four to six names]; apologies [Name]"]],
                    label_width=22),
            k.h1("1.  Matters held over", above=11),
            k.para("The board took the two items left open in December first. The "
                   "carrier review is now contracted, and the second depot's "
                   "Saturday opening was confirmed for the peak.", align="justify"),
            k.h1("2.  Performance", above=11),
            k.para("February figures were tabled: on-time delivery reached 97.4 "
                   "per cent and cost per order fell to 41.20 taka. The chair "
                   "asked whether the eastern line could hold the same figures "
                   "with a second carrier.", align="justify"),
            k.h1("3.  Decisions", above=11),
            k.bullets([
                "A second eastern line is to be contracted for April.",
                "The Saturday opening stays until the end of June, then reviews.",
            ]),
            k.h1("4.  Actions", above=11),
            k.table(
                [["Action", "Owner", "By", "Status"],
                 ["Issue the second carrier's contract for signature", "[Name]",
                  "14 Mar", "In progress"],
                 ["Table the Saturday costs at the March meeting", "[Name]",
                  "20 Mar", "Not started"],
                 ["Close the February returns note", "[Name]", "06 Mar", "Done"]],
                widths=[52, 14, 12, 22], aligns="llcl", size=10, pad=4),
            k.h1("5.  Next meeting", above=11),
            k.para("Thursday [date], 10:00, same room. Papers by the Monday "
                   "before.", below=2),
            k.note("Minutes by [Your name], Head of Operations. These minutes are "
                   "accepted as a true record at the following meeting."),
        ))


def project_plan() -> Template:
    """A plan a team can be held to: scope, milestones, owners, risks."""
    k = Kit(accent="#3B4CCA", wash="#ECEFFB")
    return Template(
        key="project-plan", name="Project Plan", group="Plans",
        blurb="Scope, milestones, who owns what, and what could go wrong.",
        detail="Headings carry a number so the plan can be quoted from, the "
               "milestone grid holds dates and owners, and the risk table is left "
               "open for the weekly review.",
        accent="#3B4CCA",
        bands={"header": {"left": "[Project] · plan", "right": "v1.0"},
               "footer": {"centre": "Page {PAGE} of {PAGES}"},
               "show_first_page": False},
        blocks=(
            k.label("Plan · version 1.0 · [Day month year]"),
            k.title("Eastern line: the second carrier", size=24, below=2),
            k.rule(colour=k.accent, weight=2.2, below=8),
            k.h1("1.  Scope", above=12),
            k.para("One contracted line of six vehicles on the Narayanganj route, "
                   "a named coordinator, and weekly reporting against the three "
                   "board measures.", align="justify"),
            k.h1("2.  Milestones", above=12),
            k.table(
                [["Milestone", "Owner", "Date", "Depends on"],
                 ["Terms agreed and signed", "[Name]", "14 Mar", "—"],
                 ["Vehicles assigned at the depot", "[Name]", "28 Mar",
                  "Signed terms"],
                 ["Drivers briefed, first paid run", "[Name]", "07 Apr",
                  "Assignment"]],
                widths=[42, 16, 14, 28], aligns="llcl", size=10, pad=4),
            k.h1("3.  Who is accountable", above=12),
            k.facts([["Carrier contract", "[Name], accountable · Finance consulted"],
                     ["Depot readiness", "[Name], accountable · Stores consulted"],
                     ["Reporting", "[Name], accountable · Board office"]]),
            k.h1("4.  Risks", above=12),
            k.table(
                [["Risk", "If it happens", "Owner", "Review"],
                 ["Second source arrives late", "Hold the old line a month",
                  "[Name]", "Weekly"],
                 ["Drivers unavailable at depot", "Relief pool at peak rate",
                  "[Name]", "Weekly"],
                 ["Fuel above the boundary rate", "Pass it through at tariff",
                  "[Name]", "Monthly"]],
                widths=[31, 39, 14, 16], aligns="llcc", size=10, pad=4),
            k.note("Done is four full weeks with on-time delivery above 96 per "
                   "cent, and two weekly reports the board did not ask for."),
        ))


def status_report() -> Template:
    """The weekly note: three numbers, what moved, what is stuck."""
    k = Kit(accent="#0E6E4F", wash="#E7F3EE")
    return Template(
        key="status-report", name="Weekly Status", group="Plans",
        blurb="Three figures, wins, blockers, next week's promises.",
        detail="Built to be read in a minute: the key numbers sit in a band of "
               "three cells, wins and blockers face each other, and the plan for "
               "next week is a promise per row.",
        accent="#0E6E4F",
        bands={"header": {"left": "[Team] · week [00]", "right": "[Day month]"},
               "footer": {"centre": "Page {PAGE} of {PAGES}"},
               "show_first_page": True},
        blocks=(
            k.title("Weekly status", size=21, below=1),
            k.para("Eastern line rollout · week [00] · [Day month year] · "
                   "[Your name]", size=10, colour=k.muted, below=12),
            k.table(
                [["ON TIME", "COST / ORDER", "VEHICLES LIVE"],
                 ["97.4%", "41.20", "4 of 6"]],
                widths=[34, 33, 33], aligns="ccc", size=15, shade=k.accent,
                head_ink="#FFFFFF", head_bold=True,
                bold_cells=((1, 0), (1, 1), (1, 2)), ink=k.accent,
                rule=k.accent, below=14),
            k.h2("Went well"),
            k.bullets([
                "Two of the six vehicles were assigned a fortnight early.",
                "The depot's stores team booked their own receiving window.",
                "Driver briefing materials were signed off without a change.",
            ]),
            k.h2("Stuck"),
            k.bullets([
                "The contract is with legal for its second read; it has been "
                "there nine days against a stated five.",
                "The relief pool has quoted a rate above the boundary figure in "
                "the plan.",
            ]),
            k.h2("Next week"),
            k.table(
                [["Promise", "Owner", "By"],
                 ["Signed terms in hand", "[Name]", "Wed"],
                 ["Relief pool rate agreed or replaced", "[Name]", "Thu"],
                 ["First Friday report drafted", "[Name]", "Fri"]],
                widths=[62, 20, 18], aligns="llc", size=10.5),
            k.gap(8),
            k.note("Amber on the contract, green on everything else. Nothing here "
                   "needs a decision this week."),
        ))


# --------------------------------------------------------------------------- #
# editorial and academic                                                       #
# --------------------------------------------------------------------------- #

def newsletter() -> Template:
    """A masthead, a lead story, and the space the rest of the page needs."""
    k = Kit(accent="#8E2334", head=SERIF_CHAIN, wash="#F7EDEF", spacing=1.18)
    return Template(
        key="newsletter", name="Newsletter", group="Editorial",
        blurb="A masthead band, a lead story, and a pull quote.",
        detail="The band carries the publication's name in the design's own red; "
               "the lead runs under a rule, and the quote is set off centre so "
               "the page has somewhere to breathe.",
        accent="#8E2334", body_family=SANS_CHAIN, head_family=SERIF_CHAIN,
        margin_px=72, spacing=1.18,
        bands={"footer": {"left": "[Publication] · [issue]",
                          "right": "Page {PAGE} of {PAGES}"},
               "show_first_page": True},
        blocks=(
            k.band("THE KINGSWAY BULLETIN", size=15, align="centre", height=14),
            k.para("Volume 4 · Issue 3 · [Day month year] · for the people of "
                   "three depots", size=9.5, colour=k.muted, align="centre",
                   below=14),
            k.h1("The line that took a fortnight"),
            k.lead("A second carrier for the eastern route was agreed in a "
                   "meeting, then waited nine days in legal, then arrived."),
            k.para("Nobody planned for the eastern line to become the story of "
                   "the quarter. It started as a scheduling question in January: "
                   "one carrier, two windows, and a February in which both were "
                   "missed. By the third week of that month the question had "
                   "become whether a route carrying a fifth of the network's "
                   "volume should rest on a single source at all.", align="justify"),
            k.para("The answer, when it came, came from the depot rather than the "
                   "boardroom. Stores booked their own receiving window before "
                   "anyone asked them to, and the two vehicles that arrived a "
                   "fortnight early were assigned by a line manager who had "
                   "already decided to make the week work.", align="justify"),
            *k.quote("We stopped waiting for the schedule to be fixed and went "
                     "and looked at the actual trucks.",
                     "Ruma Rahman, Kingsway depot"),
            k.h2("Also this issue"),
            k.numbers([
                "Saturday opening at the second depot, and what it cost.",
                "The redrawn routes, published to customers at last.",
                "Nine risks carried forward, two of them still open.",
                "A word from the new coordinator on the eastern line.",
            ]),
            k.gap(10),
            k.rule(colour=k.accent, weight=1.6),
            k.para("Written up by [name]. Corrections and items for the next "
                   "issue to bulletin@example.com by the Friday of the second "
                   "week.", size=9.5, colour=k.muted),
        ))


def press_release() -> Template:
    """The one page a newsroom needs: headline, quote, boilerplate, contact."""
    k = Kit(accent="#111827", wash="#F3F4F6")
    return Template(
        key="press-release", name="Press Release", group="Editorial",
        blurb="FOR IMMEDIATE RELEASE, one quote, and the closing mark.",
        detail="Sets the release flag at the top, headline and standfirst "
               "together, one quoted voice in the middle, and the about block and "
               "contact below the rule where a newsroom expects them.",
        accent="#111827",
        border={"style": "box", "colour": "#D1D5DB", "width_pt": 0.5},
        blocks=(
            k.label("For immediate release", colour=k.muted),
            k.title("Northbridge opens a second eastern delivery line", size=21,
                    below=3),
            k.lead("The route carries a fifth of the network's volume and has "
                   "been held by a single carrier since 2019.", below=10),
            k.para("DHAKA, [Day month year] — Northbridge Distribution today "
                   "contracted a second carrier for its Narayanganj line, "
                   "bringing six vehicles and a named coordinator to a route the "
                   "company has run alone since 2019.", align="justify"),
            k.para("The change follows two missed delivery windows in February, "
                   "which cost three stores a week of shelf time. The first paid "
                   "run is scheduled for the week beginning [date].",
                   align="justify"),
            k.para("“We were carrying a fifth of the network on one source, and "
                   "in February we felt it,” said [Name], Northbridge's head of "
                   "operations. “This is not a bigger fleet for its own sake. It "
                   "is the same volume with somewhere to go when a week goes "
                   "badly.”", align="justify"),
            k.para("The line will be reviewed weekly against three measures: "
                   "on-time delivery, cost per order, and the number of runs that "
                   "leave the depot on schedule. Northbridge will publish those "
                   "figures to customers with the redrawn route schedule later "
                   "this month.", align="justify"),
            k.gap(6),
            k.rule(colour=k.accent, weight=1.6),
            k.h2("About Northbridge Distribution"),
            k.para("Northbridge moves 19,000 orders a quarter from two depots to "
                   "340 stores across the eastern corridor. It employs 214 "
                   "people.", size=10),
            k.h2("Media contact"),
            k.facts([["Name", "[Journalist contact]"],
                     ["Contact", "+880 9000 0000 · press@example.com"]],
                    label_width=22),
            k.gap(2),
            k.para("###", align="centre", bold=True, colour=k.muted),
        ))


def essay() -> Template:
    """The academic page: serif, double-spaced, counted in the top corner."""
    k = Kit(accent="#111827", head=SERIF_CHAIN, body=SERIF_CHAIN, spacing=2.0,
            space_body=0.0)
    return Template(
        key="essay", name="Academic Essay", group="Academic",
        blurb="Double-spaced serif, indented paragraphs, numbered sheets.",
        detail="Word's manuscript page: a heading block at the top left, the "
               "title centred, first lines indented, and the sheet number in the "
               "header where a marker reads it.",
        body_family=SERIF_CHAIN, head_family=SERIF_CHAIN, body_size=12,
        accent="#111827", spacing=2.0, space_body=0.0,
        bands={"header": {"right": "{PAGE}"}, "footer": {},
               "show_first_page": True},
        blocks=(
            k.para("[Your name] · [Course code]: [Course title]", size=12,
                   below=0),
            k.para("[Supervisor] · [Day month year]", size=12, below=8),
            k.para("Word count: [0,000]", size=12, below=8),
            k.title("The cartographic eye: mapping the eastern corridor, "
                    "1880 to 1930", size=15, align="centre", below=8),
            k.para("The surveys run along the eastern river between 1880 and 1930 "
                   "are usually read as records of what was there. This essay "
                   "argues that they are better read as records of how it was "
                   "thought about: their sheets change not when the channel moved "
                   "but when the department that drew them did.", first=36,
                   align="justify"),
            k.para("The first series, drawn between 1880 and 1893, fixes the "
                   "channel in a single line and letters it as a settled thing. "
                   "The second draws the same reach as a band of soundings with "
                   "the line pushed to one side. The river did not move by a "
                   "furlong in the interval.", first=36, align="justify"),
            k.h2("Reading the sheets against each other"),
            k.para("Where a survey is taken as a picture of the ground, its "
                   "silences are accidents. Taken as a document of an office, "
                   "they become evidence. The 1901 sheets omit the river market "
                   "at Narayanganj, which those of 1898 had drawn twice.",
                   first=36, align="justify"),
            k.para("That is a change of interest rather than of geography, and it "
                   "is legible only when the sheets are laid against one another.",
                   first=36, align="justify"),
        ))


#: Every design the gallery holds, in the order its tiles appear.
DOCUMENT_TEMPLATES: Tuple[Template, ...] = (
    cover_page(),
    business_report(),
    draft_report(),
    business_letter(),
    proposal(),
    invoice(),
    purchase_order(),
    resume(),
    meeting_minutes(),
    project_plan(),
    status_report(),
    newsletter(),
    press_release(),
    essay(),
)


def template_named(key: str) -> Optional[Template]:
    """The design called *key*, or nothing when the gallery answered wrongly."""
    for each in DOCUMENT_TEMPLATES:
        if each.key == key:
            return each
    return None
