"""Tests for OfficeR Hub Launcher and file association routing."""

import os
import tempfile
import pytest
from PySide6.QtWidgets import QApplication
from officer.app import OfficeRHubWindow, add_recent_file, load_recent_files
from officer.writer.window import WriteRWindow
from officer.rsheet.window import RSheetWindow
from officer.presentr.window import PresentRWindow


def test_hub_window_instantiation():
    hub = OfficeRHubWindow()
    assert hub.windowTitle() == "OfficeR — Modern Office Suite"
    assert hub.recent_list is not None
    hub.close()


def test_hub_launch_apps():
    hub = OfficeRHubWindow()

    w_win = hub.launch_writer()
    assert isinstance(w_win, WriteRWindow)
    w_win.close()

    r_win = hub.launch_rsheet()
    assert isinstance(r_win, RSheetWindow)
    r_win.close()

    p_win = hub.launch_presentr()
    assert isinstance(p_win, PresentRWindow)
    p_win.close()

    hub.close()


def test_recent_files_tracking(config_sandbox):
    """Recent-document writes must land in the test sandbox, never in ~/.config."""
    from officer.app import CONFIG_DIR, RECENT_FILES_PATH

    assert CONFIG_DIR == os.path.join(config_sandbox, "officer")
    assert RECENT_FILES_PATH.startswith(config_sandbox)

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        tmp_path = f.name

    try:
        add_recent_file(tmp_path, "writer")
        recents = load_recent_files()
        assert any(r.get("path") == tmp_path for r in recents)
        assert os.path.exists(RECENT_FILES_PATH)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
