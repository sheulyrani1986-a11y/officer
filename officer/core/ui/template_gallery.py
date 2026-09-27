"""Office's *New from Template*: a wall of previews to start a document from.

WriteR and PresentR both build the tiles and both hand them here, because what
a gallery has to be certain of is that the picture in the tile is the thing the
caller will apply. So the dialog is given finished previews and knows nothing
about pages or slides: it filters, selects and answers.
"""

from typing import List, Optional, Sequence

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QVBoxLayout
)

#: How wide a tile's picture is, and how much room its type gets underneath:
#: a name on one line and a blurb that may well take three.
TILE_WIDTH = 188
CAPTION_HEIGHT = 78

#: The wording of the gallery's own "everything" filter.
ALL_GROUPS = "All designs"


class GalleryEntry:
    """One template as the gallery sees it: a name, a use, and a picture."""

    def __init__(self, key: str, name: str, blurb: str, group: str,
                 preview: QPixmap, detail: str = ""):
        self.key = key
        self.name = name
        self.blurb = blurb
        self.group = group
        self.preview = preview
        self.detail = detail or blurb


class TemplateGalleryDialog(QDialog):
    """Pick one of *entries*; :meth:`chosen` answers with what was picked."""

    def __init__(self, heading: str, entries: Sequence[GalleryEntry],
                 parent=None):
        super().__init__(parent)
        self._entries = list(entries)
        self._picked: Optional[GalleryEntry] = None

        self.setWindowTitle(heading)
        self.resize(960, 660)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel(heading, self)
        title.setObjectName("GalleryHeading")
        font = title.font()
        font.setPointSizeF(font.pointSizeF() + 3)
        font.setBold(True)
        title.setFont(font)
        root.addWidget(title)

        # A gallery worth its name opens on a search line and a category, and
        # both have to narrow the wall: a filter that filters nothing is worse
        # than no filter at all.
        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search the gallery")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._refilter)
        filters.addWidget(self.search, 1)

        self.categories = QComboBox(self)
        self.categories.addItem(ALL_GROUPS)
        for group in self._groups():
            self.categories.addItem(group)
        self.categories.setMinimumWidth(168)
        self.categories.currentTextChanged.connect(self._refilter)
        filters.addWidget(self.categories)
        root.addLayout(filters)

        self.tiles = QListWidget(self)
        self.tiles.setViewMode(QListWidget.ViewMode.IconMode)
        self.tiles.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.tiles.setMovement(QListWidget.Movement.Static)
        self.tiles.setWordWrap(True)
        self.tiles.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.tiles.setSpacing(14)
        self.tiles.setUniformItemSizes(True)
        # One icon size for the wall: the tallest picture sets the row, so no
        # tile is asked to crop the thing it is showing.
        self.tiles.setIconSize(QSize(TILE_WIDTH, self._tallest()))
        self.tiles.currentItemChanged.connect(self._show_details)
        self.tiles.itemDoubleClicked.connect(
            lambda item: self._choose())
        self.tiles.itemSelectionChanged.connect(self._sync_ok)
        for row, entry in enumerate(self._entries):
            item = QListWidgetItem(QIcon(entry.preview),
                                   f"{entry.name}\n{entry.blurb}", self.tiles)
            item.setData(Qt.ItemDataRole.UserRole, row)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter
                                  | Qt.AlignmentFlag.AlignTop)
            item.setSizeHint(QSize(TILE_WIDTH,
                                   self.tiles.iconSize().height() + CAPTION_HEIGHT))
            item.setToolTip(f"{entry.name} — {entry.blurb}")
        root.addWidget(self.tiles, 1)

        self.details = QLabel(" ", self)
        self.details.setObjectName("GalleryDetails")
        self.details.setWordWrap(True)
        root.addWidget(self.details)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self)
        self.buttons.accepted.connect(self._choose)
        self.buttons.rejected.connect(self.reject)
        self.ok_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.ok_button.setText("Open")
        self.ok_button.setEnabled(False)
        root.addWidget(self.buttons)

        if self._entries:
            self.tiles.setCurrentRow(0)

    # -- the wall ------------------------------------------------------------ #

    def _groups(self) -> List[str]:
        """Every category the gallery holds, in the order its tiles do."""
        seen: List[str] = []
        for entry in self._entries:
            if entry.group not in seen:
                seen.append(entry.group)
        return seen

    def _tallest(self) -> int:
        """The pictures share one width, so the tallest of them sets the row."""
        return max((entry.preview.height() for entry in self._entries),
                   default=TILE_WIDTH)

    def _refilter(self, _text: str = "") -> None:
        """Hide the tiles that answer neither the search nor the category."""
        wanted = self.search.text().strip().casefold()
        group = self.categories.currentText()
        for row in range(self.tiles.count()):
            item = self.tiles.item(row)
            entry = self._entries[item.data(Qt.ItemDataRole.UserRole)]
            matches_group = group == ALL_GROUPS or entry.group == group
            haystack = f"{entry.name} {entry.blurb} {entry.group}".casefold()
            item.setHidden(not (matches_group and (not wanted or wanted in haystack)))

    def _sync_ok(self) -> None:
        self.ok_button.setEnabled(bool(self.tiles.selectedItems()))

    def _show_details(self) -> None:
        entry = self._entry_at(self.tiles.currentRow())
        if entry is None:
            self.details.setText(" ")
            return
        self.details.setText(f"<b>{entry.name}</b> — {entry.detail}")

    def _entry_at(self, row: int) -> Optional[GalleryEntry]:
        if row < 0 or row >= len(self._entries):
            return None
        return self._entries[row]

    # -- the answer ---------------------------------------------------------- #

    def chosen(self) -> Optional[GalleryEntry]:
        """The picked template, or nothing when the gallery was cancelled."""
        return self._picked

    def _choose(self) -> Optional[GalleryEntry]:
        selected = self.tiles.selectedItems()
        if not selected:
            return None
        self._picked = self._entry_at(
            selected[0].data(Qt.ItemDataRole.UserRole))
        self.accept()
        return self._picked
