from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdvmm.domain.models import AppConfig
from sdvmm.services.app_state_store import (
    APP_STATE_VERSION,
    AppStateStoreError,
    load_app_config,
    save_app_config,
)


def test_save_and_load_app_config_round_trip(tmp_path: Path) -> None:
    state_file = tmp_path / "state" / "app-state.json"
    config = AppConfig(
        game_path=Path("/games/Stardew Valley"),
        mods_path=Path("/games/Stardew Valley/Mods"),
        app_data_path=Path("/home/user/.local/share/sdvmm"),
        sandbox_mods_path=Path("/tmp/Sandbox/Mods"),
        sandbox_archive_path=Path("/tmp/Sandbox/.archive"),
        real_archive_path=Path("/games/Stardew Valley/Mods/.sdvmm-archive"),
        watched_downloads_path=Path("/tmp/Downloads"),
        nexus_api_key="test-nexus-key",
        scan_target="sandbox_mods",
        install_target="configured_real_mods",
    )

    save_app_config(state_file=state_file, config=config)
    loaded = load_app_config(state_file=state_file)

    assert loaded == config

    payload = json.loads(state_file.read_text(encoding="utf-8"))
    assert payload["version"] == APP_STATE_VERSION
    assert payload["app_config"]["sandbox_mods_path"] == "/tmp/Sandbox/Mods"
    assert payload["app_config"]["watched_downloads_path"] == "/tmp/Downloads"
    assert payload["app_config"]["real_archive_path"] == "/games/Stardew Valley/Mods/.sdvmm-archive"
    assert payload["app_config"]["nexus_api_key"] == "test-nexus-key"
    assert payload["app_config"]["install_target"] == "configured_real_mods"


def test_load_app_config_returns_none_when_file_does_not_exist(tmp_path: Path) -> None:
    state_file = tmp_path / "missing" / "app-state.json"

    assert load_app_config(state_file) is None


def test_load_app_config_rejects_invalid_json(tmp_path: Path) -> None:
    state_file = tmp_path / "app-state.json"
    state_file.write_text("{invalid", encoding="utf-8")

    with pytest.raises(AppStateStoreError, match="Invalid JSON"):
        load_app_config(state_file)


def test_load_app_config_rejects_unsupported_version(tmp_path: Path) -> None:
    state_file = tmp_path / "app-state.json"
    state_file.write_text(
        json.dumps(
            {
                "version": 999,
                "app_config": {
                    "game_path": "/game",
                    "mods_path": "/mods",
                    "app_data_path": "/data",
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AppStateStoreError, match="Unsupported app-state version"):
        load_app_config(state_file)


def test_load_app_config_defaults_optional_fields_when_missing(tmp_path: Path) -> None:
    state_file = tmp_path / "app-state.json"
    state_file.write_text(
        json.dumps(
            {
                "version": APP_STATE_VERSION,
                "app_config": {
                    "game_path": "/game",
                    "mods_path": "/mods",
                    "app_data_path": "/data",
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_app_config(state_file)

    assert loaded is not None
    assert loaded.sandbox_mods_path is None
    assert loaded.sandbox_archive_path is None
    assert loaded.real_archive_path is None
    assert loaded.watched_downloads_path is None
    assert loaded.nexus_api_key is None
    assert loaded.scan_target == "configured_real_mods"
    assert loaded.install_target == "sandbox_mods"
