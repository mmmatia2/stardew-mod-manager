from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_DIRNAME = "sdvmm"
_APP_STATE_FILENAME = "app-state.json"
_INSTALL_HISTORY_FILENAME = "install-operation-history.json"
_RECOVERY_HISTORY_FILENAME = "recovery-execution-history.json"
_PERSISTED_STATE_FILENAMES = (
    _APP_STATE_FILENAME,
    _INSTALL_HISTORY_FILENAME,
    _RECOVERY_HISTORY_FILENAME,
)


def default_app_state_file() -> Path:
    home = Path.home()
    new_state_file = platform_default_app_state_file(home=home)
    legacy_state_file = legacy_app_state_file(home=home)

    if _state_root_contains_persisted_state(new_state_file.parent):
        return new_state_file
    if _state_root_contains_persisted_state(legacy_state_file.parent):
        return legacy_state_file
    return new_state_file


def platform_default_app_state_file(*, home: Path | None = None) -> Path:
    resolved_home = home or Path.home()
    return _platform_default_state_dir(resolved_home) / _APP_STATE_FILENAME


def legacy_app_state_file(*, home: Path | None = None) -> Path:
    resolved_home = home or Path.home()
    return resolved_home / ".config" / _APP_DIRNAME / _APP_STATE_FILENAME


def _platform_default_state_dir(home: Path) -> Path:
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA", "").strip()
        if appdata:
            return Path(appdata) / _APP_DIRNAME
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        if local_appdata:
            return Path(local_appdata) / _APP_DIRNAME
        return home / "AppData" / "Roaming" / _APP_DIRNAME

    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / _APP_DIRNAME

    xdg_state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg_state_home:
        return Path(xdg_state_home) / _APP_DIRNAME
    return home / ".local" / "state" / _APP_DIRNAME


def _state_root_contains_persisted_state(state_root: Path) -> bool:
    return any((state_root / filename).exists() for filename in _PERSISTED_STATE_FILENAMES)
