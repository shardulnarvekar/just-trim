# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets'],
    noarchive=False,
    optimize=0,
)
# Qt uses Windows' system ICU ABI. Never bundle a different ICU from PATH.
# Windows 10/11 already supply the Universal CRT and API-set DLLs.
def keep_binary(entry):
    name = entry[0].replace('\\', '/').rsplit('/', 1)[-1].lower()
    return not (name in ('icuuc.dll', 'ucrtbase.dll') or name.startswith(('icudt', 'api-ms-', 'ext-ms-')))
a.binaries = [entry for entry in a.binaries if keep_binary(entry)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Just Trim',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(Path(SPECPATH) / 'version_info.txt'),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Just Trim',
)
