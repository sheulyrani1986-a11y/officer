"""Word's *Printed Watermark* dialog: the mark a sheet wears behind its writing.

A word set across the paper, or a picture washed into it. The dialog changes
nothing on its own: it answers with the mark the user chose, and the window
hands that to the page -- which sets it under every word on every sheet and
passes it to the printer.
"""

from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QGroupBox,
                               QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QRadioButton, QSlider, QSpinBox, QToolButton,
                               QVBoxLayout, QWidget)
from officer.core.ui.fonts import fill_font_list
from officer.writer.page_color import clamp_opacity, load_picture
from officer.writer.page_preview import PICTURE_FILTER, SheetPreview
from officer.writer.watermark import (MAX_MARK_SIZE_PT, MIN_MARK_SIZE_PT,
                                     MARK_COLOURS, MARK_LAYOUTS, MARK_PRESETS,
                                     clamp_scale, mark_description,
                                     watermark_mark)

#: How the two kinds of mark are named, as Word's dialog radios name them.
MARK_CHOICES = (("none", "None"), ("text", "Text Watermark"),
                ("picture", "Picture Watermark"))


class WatermarkDialog(QDialog):
    """Choose the mark: nothing, a word across the paper, or a picture in it."""

    def __init__(self, mark: Optional[dict] = None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Printed Watermark")
        self.resize(720, 470)
        self._mark = watermark_mark(mark)
        self._image = load_picture(self._mark["image_path"])
        #: Filling the boxes is not the writer changing them: without this a
        #: text box would turn a sheet wearing nothing into one wearing a word.
        self._loading = True

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
        self._loading = False
        self._refresh()

    # -- the choices ------------------------------------------------------- #

    def _build_choices(self) -> QWidget:
        box = QWidget(self)
        column = QVBoxLayout(box)

        self.kinds = {}
        for kind, caption in MARK_CHOICES:
            radio = QRadioButton(caption, box)
            radio.clicked.connect(
                lambda _=False, k=kind: self._choose_kind(k))
            column.addWidget(radio)
            self.kinds[kind] = radio

        self.text_group = self._build_text_group(box)
        column.addWidget(self.text_group)
        self.picture_group = self._build_picture_group(box)
        column.addWidget(self.picture_group)

        fade = QHBoxLayout()
        fade.addWidget(QLabel("Mark strength:", box))
        self.opacity = QSlider(Qt.Orientation.Horizontal, box)
        self.opacity.setRange(10, 100)
        self.opacity.valueChanged.connect(
            lambda value: self._choose_opacity(value / 100.0))
        fade.addWidget(self.opacity, 1)
        self.opacity_value = QLabel(box)
        self.opacity_value.setFixedWidth(42)
        fade.addWidget(self.opacity_value)
        column.addLayout(fade)
        column.addStretch(1)
        return box

    def _build_text_group(self, box: QWidget) -> QGroupBox:
        group = QGroupBox("Text", box)
        form = QVBoxLayout(group)

        self.text_edit = QComboBox(group)
        self.text_edit.setEditable(True)
        for name, value in MARK_PRESETS:
            self.text_edit.addItem(name, value)
        self.text_edit.editTextChanged.connect(self._choose_text)
        row = QHBoxLayout()
        row.addWidget(QLabel("Words:", group))
        row.addWidget(self.text_edit, 1)
        form.addLayout(row)

        face = QHBoxLayout()
        face.addWidget(QLabel("Font:", group))
        self.font_combo = QComboBox(group)
        self.font_combo.setEditable(True)
        fill_font_list(self.font_combo)
        self.font_combo.editTextChanged.connect(self._choose_family)
        face.addWidget(self.font_combo, 1)
        face.addWidget(QLabel("Size:", group))
        self.size_box = QSpinBox(group)
        self.size_box.setRange(MIN_MARK_SIZE_PT, MAX_MARK_SIZE_PT)
        self.size_box.setSuffix(" pt")
        self.size_box.valueChanged.connect(self._choose_size)
        face.addWidget(self.size_box)
        form.addLayout(face)

        colour = QHBoxLayout()
        colour.addWidget(QLabel("Colour:", group))
        self._swatches = {}
        for hex_value in MARK_COLOURS:
            tile = QToolButton(group)
            tile.setCheckable(True)
            tile.setAutoRaise(True)
            tile.setFixedSize(22, 22)
            tile.setToolTip(hex_value)
            tile.setAccessibleName(hex_value)
            tile.setStyleSheet(
                f"QToolButton {{ background: {hex_value}; "
                "border: 1px solid #9CA3AF; } }")
            tile.clicked.connect(
                lambda _=False, c=hex_value: self._choose_colour(c))
            colour.addWidget(tile)
            self._swatches[hex_value.lower()] = tile
        self.more_colours = QPushButton("More…", group)
        self.more_colours.clicked.connect(self._more_colours)
        colour.addWidget(self.more_colours)
        colour.addStretch(1)
        form.addLayout(colour)

        layout_row = QHBoxLayout()
        self.layouts = {}
        for name in MARK_LAYOUTS:
            radio = QRadioButton(name.capitalize(), group)
            radio.clicked.connect(
                lambda _=False, k=name: self._choose_layout(k))
            layout_row.addWidget(radio)
            self.layouts[name] = radio
        layout_row.addStretch(1)
        form.addLayout(layout_row)
        return group

    def _build_picture_group(self, box: QWidget) -> QGroupBox:
        group = QGroupBox("Picture", box)
        form = QVBoxLayout(group)
        chosen = QHBoxLayout()
        self.pick_picture = QPushButton("Picture…", group)
        self.pick_picture.clicked.connect(self._choose_picture)
        chosen.addWidget(self.pick_picture)
        self.picture_name = QLabel(group)
        chosen.addWidget(self.picture_name, 1)
        form.addLayout(chosen)
        scale = QHBoxLayout()
        scale.addWidget(QLabel("Scale:", group))
        self.scale_box = QSpinBox(group)
        self.scale_box.setRange(5, 100)
        self.scale_box.setSuffix("% of the sheet")
        self.scale_box.valueChanged.connect(self._choose_scale)
        scale.addWidget(self.scale_box)
        scale.addStretch(1)
        form.addLayout(scale)
        return group

    def _load_choices(self) -> None:
        """Put the boxes where the sheet's mark already is."""
        mark = self._mark
        self.text_edit.setEditText(mark["text"])
        if mark["family"]:
            self.font_combo.setEditText(mark["family"])
        self.size_box.setValue(int(mark["size_pt"]))
        self.scale_box.setValue(mark["scale"])
        self.opacity.setValue(int(round(mark["opacity"] * 100)))

    # -- answers ------------------------------------------------------------ #

    def _choose_kind(self, kind: str) -> None:
        """Put the sheet into the state the writer asked for.

        A picture mark cannot be chosen without a picture, so picking that radio
        opens the file box first and leaves the mark alone if nothing readable
        comes back.
        """
        if kind == "picture" and self._image is None:
            self._choose_picture()
            if self._image is None:
                self._refresh()
                return
        self._mark["kind"] = kind
        self._refresh()

    def _choose_text(self, text: str) -> None:
        self._mark["text"] = text
        if text.strip() and self._mark["kind"] == "none" and not self._loading:
            # Word's dialog: a sheet wearing nothing gains a word mark the
            # moment one is typed. A sheet already wearing a picture keeps it.
            self._mark["kind"] = "text"
        self._refresh()

    def _choose_family(self, family: str) -> None:
        self._mark["family"] = family
        self._refresh()

    def _choose_size(self, points: float) -> None:
        self._mark["size_pt"] = float(points)
        self._refresh()

    def _choose_colour(self, colour: str) -> None:
        self._mark["colour"] = colour
        self._refresh()

    def _choose_layout(self, layout: str) -> None:
        self._mark["layout"] = layout
        self._refresh()

    def _choose_scale(self, percent: int) -> None:
        self._mark["scale"] = clamp_scale(percent)
        self._refresh()

    def _choose_opacity(self, strength: float) -> None:
        self._mark["opacity"] = clamp_opacity(strength)
        self._refresh()

    def _more_colours(self) -> None:
        colour = QColorDialog.getColor(QColor(self._mark["colour"]), self,
                                       "Watermark Colour")
        if colour.isValid():
            self._choose_colour(colour.name())

    def _choose_picture(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Picture for Watermark",
                                              "", PICTURE_FILTER)
        if not path:
            return
        image = load_picture(path)
        if image is None:
            QMessageBox.warning(self, "Picture for Watermark",
                                f"{path} could not be read as a picture.")
            return
        self._image = image
        self._mark["image_path"] = path
        self._mark["kind"] = "picture"
        self._refresh()

    def _refresh(self) -> None:
        kind = self._mark["kind"]
        for name, radio in self.kinds.items():
            radio.setChecked(name == kind)
        for name, radio in self.layouts.items():
            radio.setChecked(kind == "text" and self._mark["layout"] == name)
        self.text_group.setEnabled(kind == "text")
        self.picture_group.setEnabled(kind == "picture")
        self.opacity.setEnabled(kind != "none")
        self.opacity_value.setEnabled(kind != "none")
        self.opacity_value.setText(f"{self.opacity.value()}%")
        self.picture_name.setText(
            self._mark["image_path"].rsplit("/", 1)[-1] or "none chosen")
        for key, tile in self._swatches.items():
            tile.setChecked(key == self._mark["colour"].lower())
        self.preview.show_page(mark=self._mark, mark_image=self._image)
        self.summary.setText(mark_description(self._mark))

    def mark(self) -> dict:
        """The chosen mark, in the shape the page and the printer want."""
        return dict(self._mark)
