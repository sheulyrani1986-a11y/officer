"""Installed font families and the substitution chains OfficeR asks Qt for.

Word names a font and lets the machine pick a face; OfficeR does the same by
keeping the requested family first and appending metric-compatible substitutes
that are actually installed. A document therefore still saves as "Calibri",
while the screen shows a real typeface on a machine that has no Calibri.
"""

from typing import List, Sequence, Tuple

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QAbstractItemView, QComboBox

#: Listed at the top of the font box when installed, the way Office pins the
#: faces a document is likely to use.
PREFERRED_FIRST: Tuple[str, ...] = (
    "Calibri", "Cambria", "Candara", "Arial", "Times New Roman",
)

#: Word's body face and the clones that stand in for it.
BODY_CHAIN: Tuple[str, ...] = (
    "Calibri", "Carlito", "Candara", "Aptos", "Liberation Sans", "DejaVu Sans",
)

#: Word's equation face, followed by the OpenType math fonts free systems carry.
MATH_CHAIN: Tuple[str, ...] = (
    "Cambria Math", "Noto Sans Math", "STIX Two Math", "Latin Modern Math",
    "DejaVu Serif",
)


def installed_families() -> List[str]:
    """Every family fontconfig knows about, Office's favourites first."""
    families = sorted(QFontDatabase.families(), key=str.casefold)
    known = {family.casefold(): family for family in families}
    leading = [known[name.casefold()] for name in PREFERRED_FIRST if name.casefold() in known]
    pinned = set(leading)
    return leading + [family for family in families if family not in pinned]


def fill_font_list(combo: QComboBox) -> None:
    """Load *combo* with every family the machine has, each name in its own face.

    A list of a thousand names is only readable if each one is drawn by the font
    it names, the way Office's font box is.
    """
    combo.clear()
    for family in installed_families():
        combo.addItem(family)
        preview = QFont(family)
        preview.setPointSizeF(10)
        combo.setItemData(combo.count() - 1, preview, Qt.ItemDataRole.FontRole)


def family_chain(preferred: Sequence[str]) -> List[str]:
    """*preferred* with its uninstalled names kept and only real faces after.

    The head of the list is what a saved file records, so the requested font is
    never dropped even when nothing on this machine can render it.
    """
    names = [name for name in preferred if name]
    if not names:
        return []
    known = {family.casefold(): family for family in QFontDatabase.families()}
    chain = [names[0]]
    chain += [known[name.casefold()] for name in names[1:] if name.casefold() in known]
    return chain


def chain_font(families: Sequence[str], point_size: float = 11.0) -> QFont:
    """A :class:`QFont` carrying *families* as a substitution chain."""
    font = QFont()
    font.setFamilies(family_chain(families))
    font.setPointSizeF(point_size)
    return font


def body_font(point_size: float = 11.0) -> QFont:
    """The font a blank Word document starts with, resolved for this machine."""
    return chain_font(BODY_CHAIN, point_size)


def math_font(point_size: float = 12.0) -> QFont:
    """The face WriteR sets an equation in: Word's Cambria Math, or its substitute."""
    return chain_font(MATH_CHAIN, point_size)


class FontListComboBox(QComboBox):
    """A font box that opens on the face in use and lights it.

    The list carries every family the machine has, so a popup that starts at the
    top shows the wrong end of it. An editable box is worse still: naming a face
    in its line edit never moves the current index, so nothing is lit. Both are
    put right the moment the popup opens.
    """

    def showPopup(self) -> None:  # noqa: N802 - Qt's own name
        row = self._row_in_use()
        super().showPopup()
        if row < 0:
            return
        index = self.model().index(row, 0)
        view = self.view()
        view.setCurrentIndex(index)
        view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _row_in_use(self) -> int:
        """The list's row for whatever the box is showing, or ``-1``."""
        named = self.findText(self.currentText(), Qt.MatchFlag.MatchFixedString)
        return named if named >= 0 else self.currentIndex()
