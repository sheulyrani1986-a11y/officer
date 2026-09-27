# -*- mode: python ; coding: utf-8 -*-
"""How OfficeR is frozen: one self-contained binary, no Python asked of the user.

The suite is pure Python plus the pictures in ``officer/assets``, so the recipe
below has to carry the interpreter, Qt and its plugins, and the document
libraries. That is what makes the ``.deb``, the tarball and the AppImage run on a
machine that has none of them installed.
"""

import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [(os.path.join(ROOT, "officer", "assets"), "assets")]
hiddenimports = ["officer.app", "officer.writer.app", "officer.rsheet.app",
                 "officer.presentr.app"]
# These three read their own templates and formats out of their packages, which
# a byte-code scan cannot see.
for package in ("docx", "pptx", "odf", "openpyxl"):
    datas += collect_data_files(package)
hiddenimports += collect_submodules("odf")

a = Analysis(
    [os.path.join(ROOT, "packaging", "launch.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="officer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="officer")
