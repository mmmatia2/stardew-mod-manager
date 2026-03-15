from __future__ import annotations

import os
import sys
from pathlib import Path


def _prepend_path(paths: list[Path]) -> None:
    existing = os.environ.get("PATH", "")
    available = [str(path) for path in paths if path.is_dir()]
    if not available:
        return
    prefix = os.pathsep.join(available)
    os.environ["PATH"] = f"{prefix}{os.pathsep}{existing}" if existing else prefix


def _configure_bundled_qt_paths() -> None:
    bundle_root_raw = getattr(sys, "_MEIPASS", None)
    if bundle_root_raw is None:
        return

    bundle_root = Path(bundle_root_raw)
    pyside_root = bundle_root / "PySide6"
    plugins_dir = pyside_root / "plugins"
    platforms_dir = plugins_dir / "platforms"
    shiboken_root = bundle_root / "shiboken6"

    if plugins_dir.is_dir():
        os.environ["QT_PLUGIN_PATH"] = str(plugins_dir)
    if platforms_dir.is_dir():
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms_dir)

    if os.name != "nt":
        return

    _prepend_path([pyside_root, shiboken_root, bundle_root])
    for dll_root in (pyside_root, shiboken_root, bundle_root):
        if not dll_root.is_dir():
            continue
        try:
            os.add_dll_directory(str(dll_root))
        except (AttributeError, FileNotFoundError):
            continue


_configure_bundled_qt_paths()
