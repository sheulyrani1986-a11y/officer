"""Pytest shared configuration and global Qt application fixture."""

import os
import sys
import tempfile
import pytest
from PySide6.QtWidgets import QApplication

# Set offscreen platform for headless test execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Keep tests out of the user's real ~/.config/officer (recent documents, etc).
# Must run before any officer module is imported, since officer/app.py resolves
# CONFIG_DIR at import time.
_CONFIG_SANDBOX = tempfile.mkdtemp(prefix="officer-tests-config-")
os.environ["XDG_CONFIG_HOME"] = _CONFIG_SANDBOX

# Initialize global QApplication instance once for the entire test session
_global_q_app = QApplication.instance() or QApplication(["-platform", "offscreen"])


@pytest.fixture(scope="session", autouse=True)
def q_app():
    """Ensure global QApplication is available to all tests."""
    yield _global_q_app


@pytest.fixture(scope="session", autouse=True)
def config_sandbox(q_app):
    """Path to the throwaway config directory used by the session."""
    yield _CONFIG_SANDBOX
