from __future__ import annotations

import os
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from sdvmm.app.paths import default_app_state_file
from sdvmm.app.shell_service import AppShellService
from sdvmm.ui.main_window import MainWindow

APP_PACKAGE_NAME = "stardew-mod-manager"
APP_DISPLAY_NAME = "Cinderleaf"
APP_VERSION_FALLBACK = "0.3.1"
APP_RUNTIME_ICON_NAMES = ("app-icon.png", "stardew-mod-manager.ico")
WINDOWS_APP_USER_MODEL_ID = "local.sdvmm.cinderleaf"


def _resolve_app_version() -> str:
    try:
        return version(APP_PACKAGE_NAME)
    except PackageNotFoundError:
        return APP_VERSION_FALLBACK


def _resolve_runtime_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        return Path(bundle_root)
    return Path(__file__).resolve().parents[3]


def _resolve_app_icon() -> QIcon | None:
    assets_root = _resolve_runtime_root() / "assets"
    for icon_name in APP_RUNTIME_ICON_NAMES:
        icon_path = assets_root / icon_name
        if not icon_path.exists():
            continue
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            return icon
    return None


def _configure_frozen_qt_plugin_paths() -> None:
    if getattr(sys, "_MEIPASS", None) is None:
        return

    runtime_root = _resolve_runtime_root()
    pyside_root = runtime_root / "PySide6"
    plugins_dir = pyside_root / "plugins"
    platforms_dir = plugins_dir / "platforms"

    if plugins_dir.is_dir():
        os.environ["QT_PLUGIN_PATH"] = str(plugins_dir)
    if platforms_dir.is_dir():
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms_dir)


def _configure_windows_app_identity() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(  # type: ignore[attr-defined]
            WINDOWS_APP_USER_MODEL_ID
        )
    except Exception:
        return


def main() -> int:
    _configure_windows_app_identity()
    _configure_frozen_qt_plugin_paths()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(_resolve_app_version())
    app_icon = _resolve_app_icon()
    if app_icon is not None:
        app.setWindowIcon(app_icon)

    shell_service = AppShellService(state_file=default_app_state_file())
    window = MainWindow(shell_service=shell_service)
    if app_icon is not None:
        window.setWindowIcon(app_icon)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
