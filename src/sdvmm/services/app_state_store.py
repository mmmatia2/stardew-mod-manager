from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path

from sdvmm.domain.models import AppConfig

APP_STATE_VERSION = 1


class AppStateStoreError(ValueError):
    """Raised when app-state file content is invalid."""


def load_app_config(state_file: Path) -> AppConfig | None:
    if not state_file.exists():
        return None

    try:
        raw = json.loads(state_file.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise AppStateStoreError(f"Invalid JSON in app-state file: {exc.msg}") from exc
    except OSError as exc:
        raise AppStateStoreError(f"Could not read app-state file: {exc}") from exc

    if not isinstance(raw, dict):
        raise AppStateStoreError("App-state root must be a JSON object")

    version = raw.get("version")
    if version != APP_STATE_VERSION:
        raise AppStateStoreError(
            f"Unsupported app-state version: {version!r}; expected {APP_STATE_VERSION}"
        )

    app_config = raw.get("app_config")
    if not isinstance(app_config, dict):
        raise AppStateStoreError("app_config must be an object")

    game_path = _require_non_empty_string(app_config, "game_path")
    mods_path = _require_non_empty_string(app_config, "mods_path")
    app_data_path = _require_non_empty_string(app_config, "app_data_path")
    sandbox_mods_path = _optional_non_empty_string(app_config, "sandbox_mods_path")
    sandbox_archive_path = _optional_non_empty_string(app_config, "sandbox_archive_path")
    real_archive_path = _optional_non_empty_string(app_config, "real_archive_path")
    watched_downloads_path = _optional_non_empty_string(app_config, "watched_downloads_path")
    nexus_api_key = _optional_non_empty_string(app_config, "nexus_api_key")
    scan_target = _optional_non_empty_string(app_config, "scan_target") or "configured_real_mods"
    install_target = _optional_non_empty_string(app_config, "install_target") or "sandbox_mods"

    return AppConfig(
        game_path=Path(game_path),
        mods_path=Path(mods_path),
        app_data_path=Path(app_data_path),
        sandbox_mods_path=Path(sandbox_mods_path) if sandbox_mods_path else None,
        sandbox_archive_path=Path(sandbox_archive_path) if sandbox_archive_path else None,
        real_archive_path=Path(real_archive_path) if real_archive_path else None,
        watched_downloads_path=Path(watched_downloads_path) if watched_downloads_path else None,
        nexus_api_key=nexus_api_key,
        scan_target=scan_target,
        install_target=install_target,
    )


def save_app_config(state_file: Path, config: AppConfig) -> None:
    payload = {
        "version": APP_STATE_VERSION,
        "app_config": {
            "game_path": str(config.game_path),
            "mods_path": str(config.mods_path),
            "app_data_path": str(config.app_data_path),
            "sandbox_mods_path": str(config.sandbox_mods_path) if config.sandbox_mods_path else None,
            "sandbox_archive_path": (
                str(config.sandbox_archive_path) if config.sandbox_archive_path else None
            ),
            "real_archive_path": (
                str(config.real_archive_path) if config.real_archive_path else None
            ),
            "watched_downloads_path": (
                str(config.watched_downloads_path) if config.watched_downloads_path else None
            ),
            "nexus_api_key": config.nexus_api_key,
            "scan_target": config.scan_target,
            "install_target": config.install_target,
        },
    }

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _require_non_empty_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AppStateStoreError(f"app_config.{key} must be a non-empty string")
    return value


def _optional_non_empty_string(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AppStateStoreError(f"app_config.{key} must be a non-empty string when provided")
    return value
