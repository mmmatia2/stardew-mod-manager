# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import tomllib

from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo,
    FixedFileInfo,
    StringFileInfo,
    StringTable,
    StringStruct,
    VarFileInfo,
    VarStruct,
)


ROOT = Path(SPECPATH).resolve().parent
PYPROJECT = ROOT / "pyproject.toml"
PROJECT = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
VERSION = PROJECT["version"]
DIST_NAME = f"cinderleaf-{VERSION}-windows-portable"
APP_ICON = ROOT / "assets" / "stardew-mod-manager.ico"
APP_VERSION_FILE = ROOT / "build" / "app-version.txt"
APP_DISPLAY_NAME = "Cinderleaf"
APP_SUBTITLE = "for Stardew Valley"
APP_COPYRIGHT = "Copyright (c) 2026"


def _windows_version_tuple(version_text: str) -> tuple[int, int, int, int]:
    numeric_parts: list[int] = []
    for part in version_text.split("."):
        digits = []
        for character in part:
            if character.isdigit():
                digits.append(character)
            else:
                break
        numeric_parts.append(int("".join(digits) or "0"))

    while len(numeric_parts) < 4:
        numeric_parts.append(0)
    return tuple(numeric_parts[:4])


APP_VERSION_TUPLE = _windows_version_tuple(VERSION)
APP_VERSION_INFO = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=APP_VERSION_TUPLE,
        prodvers=APP_VERSION_TUPLE,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("Comments", "Source-available noncommercial Windows desktop app"),
                        StringStruct("FileDescription", f"{APP_DISPLAY_NAME} {APP_SUBTITLE}"),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("InternalName", APP_DISPLAY_NAME),
                        StringStruct("LegalCopyright", APP_COPYRIGHT),
                        StringStruct("OriginalFilename", f"{APP_DISPLAY_NAME}.exe"),
                        StringStruct("ProductName", APP_DISPLAY_NAME),
                        StringStruct("ProductVersion", VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

APP_VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
APP_VERSION_FILE.write_text(f"{VERSION}\n", encoding="utf-8")

datas = [
    (str(APP_ICON), "assets"),
    (str(APP_VERSION_FILE), "."),
]

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
    version=APP_VERSION_INFO,
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
