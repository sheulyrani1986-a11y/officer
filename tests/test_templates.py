"""Starting a document or a deck from one of OfficeR's own designs.

Two things are checked here and both have bitten before. A design has to *fit*:
WriteR's sheets have to come out as one page of paper and PresentR's marks have
to stay on the sheet and clear one another, which only a measurement made from
the real font metrics can say. And the gallery that offers them has to be wired:
a wall of previews that leads nowhere, or a filter that filters nothing, is a
worse answer than no gallery at all.
"""

import pytest
from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QDialog, QMessageBox

from officer.core.ui.template_gallery import ALL_GROUPS, TemplateGalleryDialog
from officer.presentr.deck_templates import (DECK_TEMPLATES, build_deck_tiles,
                                             deck_named)
from officer.presentr.slide_deck import TextObject
from officer.presentr.window import PresentRWindow
from officer.writer.document_templates import (DOCUMENT_TEMPLATES,
                                               template_named)
from officer.writer.window import WriteRWindow

#: PresentR's sheet, and how far from its edge a mark may reach.
SHEET = (960, 540)
EDGE = 8


def _lines(text: str, font: QFont, width: float) -> int:
    """How many lines *text* takes when wrapped to *width* by *font*."""
    metrics = QFontMetricsF(font)
    total = 0
    for paragraph in text.split("\n"):
        taken, count = "", 1
        for word in paragraph.split(" "):
            trial = word if not taken else taken + " " + word
            if metrics.horizontalAdvance(trial) <= width or not taken:
                # A word too long for the column still stands on its one line:
                # it overflows the box rather than starting a second.
                taken = trial
            else:
                count += 1
                taken = word
        total += count
    return total


def _block(obj: TextObject):
    """Where a text mark really stands, measured with its own font."""
    font = QFont(obj.font_family)
    font.setPointSizeF(obj.font_size)
    font.setBold(obj.bold)
    font.setItalic(obj.italic)
    lines = _lines(obj.text, font, obj.width)
    tall = lines * QFontMetricsF(font).lineSpacing() * obj.line_spacing
    return obj.x, obj.y, obj.x + obj.width, obj.y + tall


@pytest.fixture(scope="module")
def writer_tiles(q_app):
    """Every WriteR design's tile, photographed once for the whole module."""
    from officer.writer.templates import build_tiles
    return build_tiles(DOCUMENT_TEMPLATES)


# -- the two walls ------------------------------------------------------------ #

def test_each_app_offers_at_least_nine_designs():
    assert len(DOCUMENT_TEMPLATES) >= 9
    assert len(DECK_TEMPLATES) >= 9


def test_every_design_is_named_and_keyed():
    for each in DOCUMENT_TEMPLATES + DECK_TEMPLATES:
        assert each.key and each.name and each.group and each.blurb
        assert each.detail
    keys = [each.key for each in DOCUMENT_TEMPLATES + DECK_TEMPLATES]
    assert len(keys) == len(set(keys))


def test_a_wall_shows_every_design_and_filters_them(q_app, writer_tiles):
    entries = gallery_entries_for(writer_tiles)
    wall = TemplateGalleryDialog("Choose a design to start from", entries)
    assert wall.tiles.count() == len(entries)
    assert wall.ok_button.text() == "Open"
    assert wall.categories.currentText() == ALL_GROUPS
    # A wall that opens with its first design picked is never a dead end: the
    # details say what it is, and Open answers with it.
    assert wall.tiles.currentRow() == 0
    assert wall.ok_button.isEnabled()
    assert wall.chosen() is None, "a wall answers only when it is accepted"
    assert wall.details.text().startswith(f"<b>{entries[0].name}</b>")
    wall.tiles.setCurrentRow(1)
    assert wall.details.text().startswith(f"<b>{entries[1].name}</b>")

    wall.search.setText("invoice")
    shown = [row for row in range(wall.tiles.count())
             if not wall.tiles.item(row).isHidden()]
    assert shown and len(shown) < len(entries)

    wall.search.setText("")
    wall.categories.setCurrentText(entries[0].group)
    assert [row for row in range(wall.tiles.count())
            if not wall.tiles.item(row).isHidden()]

    wall.tiles.clearSelection()
    assert not wall.ok_button.isEnabled(), "Open stayed live with nothing picked"


def test_a_cancelled_wall_answers_with_nothing(q_app, writer_tiles):
    wall = TemplateGalleryDialog("Choose a design",
                                 gallery_entries_for(writer_tiles))
    wall.reject()
    assert wall.chosen() is None


def gallery_entries_for(tiles):
    """The WriteR wall, from the tiles its own builder photographed."""
    from officer.writer.templates import gallery_entries
    return gallery_entries(DOCUMENT_TEMPLATES, tiles)


# -- WriteR's sheets ---------------------------------------------------------- #

def test_a_tile_photographs_the_sheet_it_promises(q_app, writer_tiles):
    assert set(writer_tiles) == {each.key for each in DOCUMENT_TEMPLATES}
    for key, tile in writer_tiles.items():
        assert not tile.isNull(), key
        # A sheet of paper is taller than it is wide, and the caption's room
        # belongs to the wall rather than to the picture.
        assert tile.height() > tile.width(), key


@pytest.mark.parametrize("key", [each.key for each in DOCUMENT_TEMPLATES])
def test_a_design_fills_exactly_one_sheet(q_app, key):
    win = WriteRWindow()
    template_named(key).apply_to(win.page)
    assert win.page.document().characterCount() > 200, key
    assert win.page.page_count() == 1, key


# -- PresentR's sheets -------------------------------------------------------- #

def test_a_deck_tile_is_the_opening_sheet(q_app):
    tiles = build_deck_tiles()
    assert set(tiles) == {each.key for each in DECK_TEMPLATES}
    for key, tile in tiles.items():
        assert not tile.isNull(), key
        assert abs(tile.width() / tile.height() - SHEET[0] / SHEET[1]) < 0.05


def test_every_deck_runs_from_a_cover_to_a_closing(q_app):
    for design in DECK_TEMPLATES:
        slides = design.slides()
        assert len(slides) >= 5, design.key
        assert any(len(s.objects) > 2 for s in slides), design.key


def test_no_mark_leaves_the_sheet_and_no_two_words_collide(q_app):
    for design in DECK_TEMPLATES:
        for index, slide in enumerate(design.slides(), 1):
            where = f"{design.key} sheet {index}"
            marks = []
            for obj in slide.objects:
                assert obj.width > 0 and obj.height > 0, where
                assert obj.x >= -1 and obj.y >= -1, where
                assert obj.x + obj.width <= SHEET[0] + 1, where
                assert obj.y + obj.height <= SHEET[1] + 1, where
                if isinstance(obj, TextObject):
                    marks.append(_block(obj))
            for first in range(len(marks)):
                for second in range(first + 1, len(marks)):
                    a, b = marks[first], marks[second]
                    wide = min(a[2], b[2]) - max(a[0], b[0])
                    tall = min(a[3], b[3]) - max(a[1], b[1])
                    assert not (wide > 24 and tall > 4), \
                        f"{where}: two marks share {wide:.0f}x{tall:.0f} of sheet"
                    assert b[3] <= SHEET[1] + EDGE, f"{where}: writing runs off"


# -- the wiring --------------------------------------------------------------- #

@pytest.mark.parametrize("window, design_named", [
    (WriteRWindow, template_named), (PresentRWindow, deck_named)])
def test_the_wall_is_reachable_and_replaces_the_work(q_app, monkeypatch,
                                                     window, design_named):
    """From a live window: the wall answers, warns about the work, deals it out."""
    win = window()
    assert win.has_templates
    assert win.template_entries(), "the wall showed nothing"
    assert win.template_entries() is win.template_entries(), \
        "the photographs were taken twice"
    if window is WriteRWindow:
        win.page.setPlainText("Writing that the design will cover over.")
        assert win.template_held()

    picked = win.template_entries()[1]
    monkeypatch.setattr(TemplateGalleryDialog, "exec",
                        lambda self: QDialog.Accepted)
    monkeypatch.setattr(TemplateGalleryDialog, "chosen", lambda self: picked)
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or
                        QMessageBox.StandardButton.Discard)
    win.open_template_gallery()
    assert asked and picked.name in asked[0], "work was replaced unasked"
    assert design_named(picked.key) is not None, "the wall offered a dead key"

    if window is WriteRWindow:
        assert win.page.document().characterCount() > 200
        assert win.page.page_count() == 1
    else:
        deck = design_named(picked.key)
        assert len(win.presentation.slides) == len(deck.slides())
        assert win.slide_list.count() == len(win.presentation.slides)


def test_writing_nothing_is_not_warned_about(q_app, monkeypatch):
    """A blank sheet of Word's paper has nothing to lose, so it is not asked."""
    win = WriteRWindow()
    assert not win.template_held(), "a new document already holds work"
    picked = win.template_entries()[0]
    monkeypatch.setattr(TemplateGalleryDialog, "exec",
                        lambda self: QDialog.Accepted)
    monkeypatch.setattr(TemplateGalleryDialog, "chosen", lambda self: picked)
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: pytest.fail("asked to discard nothing"))
    win.open_template_gallery()
    assert win.page.document().characterCount() > 200


def test_a_deck_of_placeholders_is_treated_as_work(q_app, monkeypatch):
    """PresentR's new deck carries a title slide, and that is worth a warning."""
    win = PresentRWindow()
    assert win.template_held()
    asked = []
    monkeypatch.setattr(TemplateGalleryDialog, "exec",
                        lambda self: QDialog.Accepted)
    monkeypatch.setattr(TemplateGalleryDialog, "chosen",
                        lambda self: win.template_entries()[0])
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or
                        QMessageBox.StandardButton.Cancel)
    win.open_template_gallery()
    assert asked, "the placeholders were replaced unasked"
    assert len(win.presentation.slides) == 1, "a cancelled warning still dealt"


def test_a_saved_document_may_be_kept(q_app, monkeypatch, tmp_path):
    """Cancel in the wall's warning leaves the writing exactly where it was."""
    win = WriteRWindow()
    win.page.setPlainText("A letter worth keeping.")
    before = win.page.toPlainText()
    monkeypatch.setattr(TemplateGalleryDialog, "exec",
                        lambda self: QDialog.Accepted)
    monkeypatch.setattr(TemplateGalleryDialog, "chosen",
                        lambda self: win.template_entries()[0])
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: QMessageBox.StandardButton.Cancel)
    win.open_template_gallery()
    assert win.page.toPlainText() == before


def test_the_spreadsheet_has_no_wall_to_show(q_app):
    from officer.rsheet.window import RSheetWindow
    assert not RSheetWindow().has_templates
