# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import tomllib

from PyInstaller.utils.hooks import copy_metadata


ROOT = Path(SPECPATH).resolve().parent
PYPROJECT = ROOT / "pyproject.toml"
PROJECT = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
VERSION = PROJECT["version"]
DIST_NAME = f"cinderleaf-{VERSION}-windows-portable"
APP_ICON = ROOT / "assets" / "stardew-mod-manager.ico"

datas = copy_metadata("stardew-mod-manager") + [(str(APP_ICON), "assets")]

a = Analysis(
    [str(ROOT / "src" / "sdvmm" / "app" / "main.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "pyi_rth_qt_paths.py")],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Cinderleaf",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(APP_ICON),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=DIST_NAME,
    contents_directory="_internal",
)
