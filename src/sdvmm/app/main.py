from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, version

from PySide6.QtWidgets import QApplication

from sdvmm.app.paths import default_app_state_file
from sdvmm.app.shell_service import AppShellService
from sdvmm.ui.main_window import MainWindow

APP_PACKAGE_NAME = "stardew-mod-manager"
APP_DISPLAY_NAME = "Stardew Mod Manager"
APP_VERSION_FALLBACK = "0.2.0"


def _resolve_app_version() -> str:
    try:
        return version(APP_PACKAGE_NAME)
    except PackageNotFoundError:
        return APP_VERSION_FALLBACK


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(_resolve_app_version())

    shell_service = AppShellService(state_file=default_app_state_file())
    window = MainWindow(shell_service=shell_service)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
