from __future__ import annotations

import json
from pathlib import Path

import pytest
import sdvmm.app.paths as app_paths
import sdvmm.services.app_state_store as app_state_store

from sdvmm.domain.models import (
    AppConfig,
    InstallOperationEntryRecord,
    InstallOperationHistory,
    InstallOperationRecord,
    RecoveryExecutionHistory,
    RecoveryExecutionRecord,
)
from sdvmm.domain.install_codes import INSTALL_NEW
from sdvmm.services.app_state_store import (
    APP_STATE_VERSION,
    INSTALL_OPERATION_HISTORY_FILENAME,
    INSTALL_OPERATION_HISTORY_VERSION,
    RECOVERY_EXECUTION_HISTORY_FILENAME,
    RECOVERY_EXECUTION_HISTORY_VERSION,
    AppStateStoreError,
    append_install_operation_record,
    append_recovery_execution_record,
    install_operation_history_file,
    load_app_config,
    load_install_operation_history,
    load_recovery_execution_history,
    recovery_execution_history_file,
    save_app_config,
    save_install_operation_history,
    save_recovery_execution_history,
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
    assert payload["app_config"]["sandbox_mods_path"] == str(config.sandbox_mods_path)
    assert payload["app_config"]["watched_downloads_path"] == str(config.watched_downloads_path)
    assert payload["app_config"]["real_archive_path"] == str(config.real_archive_path)
    assert payload["app_config"]["nexus_api_key"] == "test-nexus-key"
    assert payload["app_config"]["install_target"] == "configured_real_mods"


def test_default_app_state_file_uses_platform_default_windows_appdata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    appdata = tmp_path / "AppData" / "Roaming"
    home.mkdir(parents=True)
    appdata.mkdir(parents=True)
    monkeypatch.setattr(app_paths.Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(app_paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    state_file = app_paths.default_app_state_file()

    assert state_file == appdata / "sdvmm" / "app-state.json"


def test_default_app_state_file_prefers_legacy_state_root_when_only_legacy_state_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    appdata = tmp_path / "AppData" / "Roaming"
    legacy_root = home / ".config" / "sdvmm"
    home.mkdir(parents=True)
    appdata.mkdir(parents=True)
    legacy_root.mkdir(parents=True)
    (legacy_root / INSTALL_OPERATION_HISTORY_FILENAME).write_text(
        json.dumps({"version": INSTALL_OPERATION_HISTORY_VERSION, "operations": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_paths.Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(app_paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    state_file = app_paths.default_app_state_file()

    assert state_file == legacy_root / "app-state.json"


def test_default_app_state_file_prefers_new_platform_root_when_both_locations_have_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    appdata = tmp_path / "AppData" / "Roaming"
    legacy_root = home / ".config" / "sdvmm"
    new_root = appdata / "sdvmm"
    home.mkdir(parents=True)
    legacy_root.mkdir(parents=True)
    new_root.mkdir(parents=True)
    (legacy_root / "app-state.json").write_text("{}", encoding="utf-8")
    (new_root / RECOVERY_EXECUTION_HISTORY_FILENAME).write_text(
        json.dumps({"version": RECOVERY_EXECUTION_HISTORY_VERSION, "operations": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_paths.Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(app_paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    state_file = app_paths.default_app_state_file()

    assert state_file == new_root / "app-state.json"


@pytest.mark.parametrize(
    ("target_name", "save_operation"),
    (
        (
            "app-state.json",
            lambda tmp_path, target_file: save_app_config(
                target_file,
                AppConfig(
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
                ),
            ),
        ),
        (
            INSTALL_OPERATION_HISTORY_FILENAME,
            lambda tmp_path, target_file: save_install_operation_history(
                target_file,
                InstallOperationHistory(operations=(_install_operation_record(tmp_path),)),
            ),
        ),
        (
            RECOVERY_EXECUTION_HISTORY_FILENAME,
            lambda tmp_path, target_file: save_recovery_execution_history(
                target_file,
                RecoveryExecutionHistory(operations=(_recovery_execution_record(tmp_path),)),
            ),
        ),
    ),
)
def test_save_operations_write_atomically_in_target_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_name: str,
    save_operation,
) -> None:
    target_file = tmp_path / "state" / target_name
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = app_state_store.os.replace

    def record_replace(source: str | Path, target: str | Path) -> None:
        source_path = Path(source)
        target_path = Path(target)
        replace_calls.append((source_path, target_path))
        assert source_path.parent == target_file.parent
        assert target_path == target_file
        original_replace(source, target)

    monkeypatch.setattr(app_state_store.os, "replace", record_replace)

    save_operation(tmp_path, target_file)

    assert len(replace_calls) == 1
    assert replace_calls[0][1] == target_file
    assert target_file.exists()
    assert sorted(path.name for path in target_file.parent.iterdir()) == [target_file.name]


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


def test_install_operation_history_round_trip(tmp_path: Path) -> None:
    history_file = tmp_path / "state" / INSTALL_OPERATION_HISTORY_FILENAME
    operation = _install_operation_record(tmp_path)
    history = InstallOperationHistory(operations=(operation,))

    save_install_operation_history(history_file, history)
    loaded = load_install_operation_history(history_file)

    assert loaded == history

    payload = json.loads(history_file.read_text(encoding="utf-8"))
    assert payload["version"] == INSTALL_OPERATION_HISTORY_VERSION
    assert payload["operations"][0]["operation_id"] == operation.operation_id
    assert payload["operations"][0]["package_path"] == str(operation.package_path)
    assert payload["operations"][0]["entries"][0]["action"] == INSTALL_NEW


def test_load_install_operation_history_returns_empty_when_file_missing(tmp_path: Path) -> None:
    history_file = tmp_path / "state" / INSTALL_OPERATION_HISTORY_FILENAME

    loaded = load_install_operation_history(history_file)

    assert loaded == InstallOperationHistory(operations=tuple())


def test_append_install_operation_record_appends_in_order(tmp_path: Path) -> None:
    history_file = tmp_path / "state" / INSTALL_OPERATION_HISTORY_FILENAME
    first = _install_operation_record(tmp_path, package_name="first.zip")
    second = _install_operation_record(tmp_path, package_name="second.zip")

    append_install_operation_record(history_file, first)
    updated = append_install_operation_record(history_file, second)

    assert updated.operations == (first, second)


def test_install_operation_history_file_uses_state_directory(tmp_path: Path) -> None:
    state_file = tmp_path / "state" / "app-state.json"

    assert install_operation_history_file(state_file) == tmp_path / "state" / INSTALL_OPERATION_HISTORY_FILENAME


def test_load_install_operation_history_rejects_invalid_json(tmp_path: Path) -> None:
    history_file = tmp_path / INSTALL_OPERATION_HISTORY_FILENAME
    history_file.write_text("{invalid", encoding="utf-8")

    with pytest.raises(AppStateStoreError, match="Invalid JSON"):
        load_install_operation_history(history_file)


def test_load_install_operation_history_rejects_unsupported_version(tmp_path: Path) -> None:
    history_file = tmp_path / INSTALL_OPERATION_HISTORY_FILENAME
    history_file.write_text(
        json.dumps(
            {
                "version": 999,
                "operations": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AppStateStoreError, match="Unsupported install-operation history version"):
        load_install_operation_history(history_file)


def test_load_install_operation_history_without_ids_still_loads_compatibly(tmp_path: Path) -> None:
    history_file = tmp_path / INSTALL_OPERATION_HISTORY_FILENAME
    history_file.write_text(
        json.dumps(
            {
                "version": INSTALL_OPERATION_HISTORY_VERSION,
                "operations": [
                    {
                        "timestamp": "2026-03-13T12:00:00Z",
                        "package_path": str(tmp_path / "sample.zip"),
                        "destination_kind": "sandbox_mods",
                        "destination_mods_path": str(tmp_path / "SandboxMods"),
                        "archive_path": str(tmp_path / "SandboxArchive"),
                        "installed_targets": [str(tmp_path / "SandboxMods" / "SampleMod")],
                        "archived_targets": [str(tmp_path / "SandboxArchive" / "OldSampleMod")],
                        "entries": [
                            {
                                "name": "Sample Mod",
                                "unique_id": "Sample.Mod",
                                "version": "1.0.0",
                                "action": INSTALL_NEW,
                                "target_path": str(tmp_path / "SandboxMods" / "SampleMod"),
                                "archive_path": None,
                                "source_manifest_path": "/tmp/package/SampleMod/manifest.json",
                                "source_root_path": "/tmp/package/SampleMod",
                                "target_exists_before": False,
                                "can_install": True,
                                "warnings": [],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_install_operation_history(history_file)

    assert len(loaded.operations) == 1
    assert loaded.operations[0].operation_id is None


def test_recovery_execution_history_round_trip(tmp_path: Path) -> None:
    history_file = tmp_path / "state" / RECOVERY_EXECUTION_HISTORY_FILENAME
    operation = _recovery_execution_record(tmp_path)
    history = RecoveryExecutionHistory(operations=(operation,))

    save_recovery_execution_history(history_file, history)
    loaded = load_recovery_execution_history(history_file)

    assert loaded == history

    payload = json.loads(history_file.read_text(encoding="utf-8"))
    assert payload["version"] == RECOVERY_EXECUTION_HISTORY_VERSION
    assert payload["operations"][0]["recovery_execution_id"] == operation.recovery_execution_id
    assert payload["operations"][0]["related_install_operation_id"] == operation.related_install_operation_id
    assert payload["operations"][0]["destination_kind"] == operation.destination_kind
    assert payload["operations"][0]["outcome_status"] == "completed"


def test_load_recovery_execution_history_returns_empty_when_file_missing(tmp_path: Path) -> None:
    history_file = tmp_path / "state" / RECOVERY_EXECUTION_HISTORY_FILENAME

    loaded = load_recovery_execution_history(history_file)

    assert loaded == RecoveryExecutionHistory(operations=tuple())


def test_append_recovery_execution_record_appends_in_order(tmp_path: Path) -> None:
    history_file = tmp_path / "state" / RECOVERY_EXECUTION_HISTORY_FILENAME
    first = _recovery_execution_record(tmp_path, timestamp="2026-03-13T12:00:00Z")
    second = _recovery_execution_record(tmp_path, timestamp="2026-03-13T13:00:00Z")

    append_recovery_execution_record(history_file, first)
    updated = append_recovery_execution_record(history_file, second)

    assert updated.operations == (first, second)


def test_recovery_execution_history_file_uses_state_directory(tmp_path: Path) -> None:
    state_file = tmp_path / "state" / "app-state.json"

    assert recovery_execution_history_file(state_file) == (
        tmp_path / "state" / RECOVERY_EXECUTION_HISTORY_FILENAME
    )


def test_load_recovery_execution_history_rejects_invalid_json(tmp_path: Path) -> None:
    history_file = tmp_path / RECOVERY_EXECUTION_HISTORY_FILENAME
    history_file.write_text("{invalid", encoding="utf-8")

    with pytest.raises(AppStateStoreError, match="Invalid JSON"):
        load_recovery_execution_history(history_file)


def test_load_recovery_execution_history_rejects_unsupported_version(tmp_path: Path) -> None:
    history_file = tmp_path / RECOVERY_EXECUTION_HISTORY_FILENAME
    history_file.write_text(
        json.dumps(
            {
                "version": 999,
                "operations": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AppStateStoreError, match="Unsupported recovery-execution history version"):
        load_recovery_execution_history(history_file)


def test_load_recovery_execution_history_rejects_invalid_data(tmp_path: Path) -> None:
    history_file = tmp_path / RECOVERY_EXECUTION_HISTORY_FILENAME
    history_file.write_text(
        json.dumps(
            {
                "version": RECOVERY_EXECUTION_HISTORY_VERSION,
                "operations": [
                    {
                        "timestamp": "2026-03-13T12:00:00Z",
                        "related_install_operation_timestamp": "2026-03-13T11:00:00Z",
                        "related_install_package_path": str(tmp_path / "sample.zip"),
                        "destination_kind": "sandbox_mods",
                        "destination_mods_path": str(tmp_path / "SandboxMods"),
                        "executed_entry_count": "bad",
                        "removed_target_paths": [],
                        "restored_target_paths": [],
                        "outcome_status": "completed",
                        "failure_message": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(AppStateStoreError, match="executed_entry_count must be an integer"):
        load_recovery_execution_history(history_file)


def test_load_recovery_execution_history_without_ids_still_loads_compatibly(tmp_path: Path) -> None:
    history_file = tmp_path / RECOVERY_EXECUTION_HISTORY_FILENAME
    history_file.write_text(
        json.dumps(
            {
                "version": RECOVERY_EXECUTION_HISTORY_VERSION,
                "operations": [
                    {
                        "timestamp": "2026-03-13T14:00:00Z",
                        "related_install_operation_timestamp": "2026-03-13T12:00:00Z",
                        "related_install_package_path": str(tmp_path / "sample.zip"),
                        "destination_kind": "sandbox_mods",
                        "destination_mods_path": str(tmp_path / "SandboxMods"),
                        "executed_entry_count": 1,
                        "removed_target_paths": [str(tmp_path / "SandboxMods" / "SampleMod")],
                        "restored_target_paths": [],
                        "outcome_status": "completed",
                        "failure_message": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    loaded = load_recovery_execution_history(history_file)

    assert len(loaded.operations) == 1
    assert loaded.operations[0].recovery_execution_id is None
    assert loaded.operations[0].related_install_operation_id is None


def _install_operation_record(tmp_path: Path, *, package_name: str = "sample.zip") -> InstallOperationRecord:
    return InstallOperationRecord(
        operation_id="install_123",
        timestamp="2026-03-13T12:00:00Z",
        package_path=tmp_path / package_name,
        destination_kind="sandbox_mods",
        destination_mods_path=tmp_path / "SandboxMods",
        archive_path=tmp_path / "SandboxArchive",
        installed_targets=(tmp_path / "SandboxMods" / "SampleMod",),
        archived_targets=(tmp_path / "SandboxArchive" / "OldSampleMod",),
        entries=(
            InstallOperationEntryRecord(
                name="Sample Mod",
                unique_id="Sample.Mod",
                version="1.0.0",
                action=INSTALL_NEW,
                target_path=tmp_path / "SandboxMods" / "SampleMod",
                archive_path=None,
                source_manifest_path="/tmp/package/SampleMod/manifest.json",
                source_root_path="/tmp/package/SampleMod",
                target_exists_before=False,
                can_install=True,
                warnings=tuple(),
            ),
        ),
    )


def _recovery_execution_record(
    tmp_path: Path,
    *,
    timestamp: str = "2026-03-13T14:00:00Z",
    outcome_status: str = "completed",
    failure_message: str | None = None,
) -> RecoveryExecutionRecord:
    return RecoveryExecutionRecord(
        recovery_execution_id="recovery_123",
        timestamp=timestamp,
        related_install_operation_id="install_123",
        related_install_operation_timestamp="2026-03-13T12:00:00Z",
        related_install_package_path=tmp_path / "sample.zip",
        destination_kind="sandbox_mods",
        destination_mods_path=tmp_path / "SandboxMods",
        executed_entry_count=1,
        removed_target_paths=(tmp_path / "SandboxMods" / "SampleMod",),
        restored_target_paths=tuple(),
        outcome_status=outcome_status,
        failure_message=failure_message,
    )
