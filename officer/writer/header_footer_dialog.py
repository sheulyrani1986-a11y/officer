"""Word's *Header & Footer*: the line of paper above and below the writing.

Three places in each band -- against the left margin, in the middle, against
the right -- and the page's own number available to any of them. The dialog
changes nothing on its own: it answers with the bands the user wrote, and the
window hands them to the page, which wears them on every sheet and passes them
to the printer.
"""

from typing import Optional
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget
)
from officer.writer.header_footer import (BAND_KINDS, BAND_SIDES, FIELDS,
                                          PAGE_FIELD, TOTAL_FIELD,
                                          bands_setting)
from officer.writer.page_preview import SheetPreview

#: Where a band's three places are put, in the words the dialog labels them.
SIDE_LABELS = {"left": "Left", "centre": "Centre", "right": "Right"}

#: What each place is for, until the writer says otherwise.
FIELD_HINTS = {
    ("header", "left"): "Document title",
    ("header", "centre"): "Chapter",
    ("header", "right"): "Author",
    ("footer", "left"): "Date",
    ("footer", "centre"): "Page {PAGE} of {PAGES}",
    ("footer", "right"): "",
}


class HeaderFooterDialog(QDialog):
    """Write what the top and the bottom of every sheet are to carry."""

    def __init__(self, bands: Optional[dict] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Header and Footer")
        self.resize(720, 440)
        self._bands = bands_setting(bands)
        #: The box the page-number buttons write into: the last one touched,
        #: which is the one the user means.
        self._target: Optional[QLineEdit] = None
        self._fields = {kind: {} for kind in BAND_KINDS}

        outer = QHBoxLayout(self)
        outer.addWidget(self._build_choices(), 3)
        right = QVBoxLayout()
        self.preview = SheetPreview(self)
        right.addWidget(self.preview, 3)
        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        right.addWidget(self.summary)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel,
                                   parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)
        outer.addLayout(right, 2)

        self._load_choices()
        self._refresh()

    # -- the choices ------------------------------------------------------- #

    def _build_choices(self) -> QWidget:
        box = QWidget(self)
        column = QVBoxLayout(box)
        # A line edit has no focus signal of its own, so the dialog watches the
        # six it owns: this is how the page-number buttons know which box the
        # writer is standing in.
        for kind in BAND_KINDS:
            group = QGroupBox(kind.capitalize(), box)
            form = QVBoxLayout(group)
            for side in BAND_SIDES:
                row = QHBoxLayout()
                row.addWidget(QLabel(f"{SIDE_LABELS[side]}:", group))
                field = QLineEdit(group)
                field.setPlaceholderText(FIELD_HINTS.get((kind, side), ""))
                field.textChanged.connect(
                    lambda text, k=kind, s=side: self._choose_text(k, s, text))
                field.installEventFilter(self)
                row.addWidget(field, 1)
                form.addLayout(row)
                self._fields[kind][side] = field
            column.addWidget(group)

        insert = QHBoxLayout()
        self.page_number = QPushButton("Insert Page Number", box)
        self.page_number.clicked.connect(
            lambda: self._insert_field(PAGE_FIELD))
        insert.addWidget(self.page_number)
        self.page_count = QPushButton("Insert Page Count", box)
        self.page_count.clicked.connect(
            lambda: self._insert_field(TOTAL_FIELD))
        insert.addWidget(self.page_count)
        insert.addStretch(1)
        column.addLayout(insert)
        hint = QLabel("The two buttons write a field into the box you are "
                      "editing: it prints that sheet's own number, and the "
                      "length of the whole document.", box)
        hint.setWordWrap(True)
        column.addWidget(hint)

        self.first_page = QCheckBox("Show on the first page", box)
        self.first_page.toggled.connect(self._choose_first_page)
        column.addWidget(self.first_page)
        column.addStretch(1)
        return box

    def _load_choices(self) -> None:
        """Put the boxes where the sheet's bands already are."""
        for kind in BAND_KINDS:
            for side in BAND_SIDES:
                field = self._fields[kind][side]
                field.blockSignals(True)
                field.setText(self._bands[kind][side])
                field.blockSignals(False)
        self.first_page.setChecked(bool(self._bands["show_first_page"]))

    # -- answers ------------------------------------------------------------ #

    def eventFilter(self, watched, event) -> bool:  # type: ignore[override]
        if (event.type() == QEvent.Type.FocusIn
                and isinstance(watched, QLineEdit)):
            self._target = watched
        return super().eventFilter(watched, event)

    def _insert_field(self, token: str) -> None:
        """Drop a page-number field into the box being edited, at the caret."""
        field = self._target or self._fields["footer"]["centre"]
        start, end = field.selectionStart(), field.selectionEnd()
        if start < 0:
            start = end = field.cursorPosition()
        field.setText(field.text()[:start] + token + field.text()[end:])
        field.setCursorPosition(start + len(token))
        field.setFocus()

    def _choose_text(self, kind: str, side: str, text: str) -> None:
        self._bands[kind][side] = text
        self._refresh()

    def _choose_first_page(self, shown: bool) -> None:
        self._bands["show_first_page"] = shown
        self._refresh()

    def _refresh(self) -> None:
        self.preview.show_page(bands=self._bands, page=1, total=3)
        self.summary.setText(self.description())

    def description(self) -> str:
        """What the bands now carry, in the words the status line shows."""
        written = [kind for kind in BAND_KINDS
                   if any(self._bands[kind][side].strip()
                          for side in BAND_SIDES)]
        if not written:
            return "No header and no footer: the sheets keep their margins empty."
        fields = sum(1 for kind in BAND_KINDS for side in BAND_SIDES
                     if any(field in self._bands[kind][side]
                            for field in FIELDS))
        said = (f"{' and '.join(written).capitalize()} on every sheet"
                f" -- {fields} page number field(s).")
        if not self._bands["show_first_page"]:
            said += " The first sheet keeps them empty."
        return said

    def bands(self) -> dict:
        """The bands, in the shape the page and the printer want."""
        return dict(self._bands)
