"""What a packaged OfficeR does when the desktop hands it work to do.

Installing an office suite promises two things the tests below keep honest: the
menu entry named *WriteR* opens WriteR, and double-clicking a document opens
*that* document. Both are decided by the command line, so the parsing there is
worth as careful a look as any dialog.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from officer.core.args import file_argument, without_flags

ROOT = Path(__file__).resolve().parent.parent

launch = importlib.util.spec_from_file_location(
    "officer_packaging_launch", str(ROOT / "packaging" / "launch.py"))
launcher = importlib.util.module_from_spec(launch)
launch.loader.exec_module(launcher)


# -- the command line --------------------------------------------------------- #

def test_the_launcher_finds_the_document_among_the_flags(tmp_path):
    note = tmp_path / "note.txt"
    note.write_text("handed over by the file manager")
    argv = ["officer-writer", "--app", "writer", str(note)]
    assert file_argument(argv[1:]) == str(note)
    assert file_argument(["officer-writer", "missing.txt"]) is None
    assert file_argument(["officer-writer"]) is None


def test_the_app_choice_does_not_reach_the_application(monkeypatch):
    monkeypatch.setattr(sys, "argv",
                        ["officer", "--app", "presentr", "deck.pptx"])
    assert without_flags() == ["officer", "deck.pptx"]


@pytest.mark.parametrize("called_as, wanted", [
    ("officer", "hub"), ("officer-writer", "writer"),
    ("officer-rsheet", "rsheet"), ("officer-presentr", "presentr")])
def test_each_menu_entry_names_its_own_application(called_as, wanted):
    assert launcher.requested([called_as]) == wanted


def test_the_flag_wins_over_the_name_and_the_hub_is_the_fallback(tmp_path):
    assert launcher.requested(["officer-writer", "--app", "presentr"]) == "presentr"
    assert launcher.requested([str(tmp_path / "something-else")]) == "hub"


def test_a_double_click_with_nothing_but_the_program_name_opens_the_hub():
    """The desktop can call the binary bare, so that must not be an error."""
    assert launcher.requested(["/opt/officer/officer"]) == "hub"
    assert launcher.requested([]) == "hub"
    assert launcher.requested(["officer", "--app"]) == "hub"


def test_the_callers_own_app_beats_the_wrappers_default():
    """AppRun adds --app hub, and a person asking for WriteR outranks it."""
    argv = ["officer", "--app", "hub", "--app", "writer", "letter.docx"]
    assert launcher.requested(argv) == "writer"
    assert without_flags(argv) == ["officer", "letter.docx"]


# -- opening what was asked for ------------------------------------------------ #

def test_writer_opens_the_text_it_is_pointed_at(q_app, tmp_path):
    from officer.writer.window import WriteRWindow
    note = tmp_path / "letter.txt"
    note.write_text("Four score and seven years.\n")
    win = WriteRWindow()
    assert win.open_path(str(note))
    assert "Four score" in win.page.toPlainText()
    assert win.current_filepath == str(note)


def test_rsheet_opens_the_values_it_is_pointed_at(q_app, tmp_path):
    from officer.rsheet.window import RSheetWindow
    table = tmp_path / "figures.csv"
    table.write_text("month,taken\nMarch,412\nApril,455\n")
    win = RSheetWindow()
    assert win.open_path(str(table))
    assert win.sheets["Sheet1"].get_cell_display(2, 1) == "455"
    assert win.current_filepath == str(table)


def test_presentr_opens_the_deck_it_is_pointed_at(q_app, tmp_path):
    from officer.presentr.window import PresentRWindow
    deck = tmp_path / "deck.pptx"
    first = PresentRWindow()
    first._save_to_path(str(deck))
    assert deck.exists()
    again = PresentRWindow()
    assert again.open_path(str(deck))
    assert again.current_filepath == str(deck)
    assert again.presentation.slides


def test_a_window_handed_nothing_stays_blank(q_app, tmp_path):
    """The entry points ask only when a real file, not a folder, is offered."""
    from officer.writer.window import WriteRWindow
    assert file_argument([str(tmp_path)]) is None
    win = WriteRWindow()
    assert not win.current_filepath
