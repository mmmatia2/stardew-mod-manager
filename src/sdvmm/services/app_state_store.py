from __future__ import annotations

import json
import os
from json import JSONDecodeError
from pathlib import Path
import tempfile

from sdvmm.domain.models import (
    AppConfig,
    InstallOperationEntryRecord,
    InstallOperationHistory,
    InstallOperationRecord,
    RecoveryExecutionHistory,
    RecoveryExecutionRecord,
    UpdateSourceIntentOverlay,
    UpdateSourceIntentRecord,
)
from sdvmm.domain.update_codes import LOCAL_PRIVATE_MOD

APP_STATE_VERSION = 1
INSTALL_OPERATION_HISTORY_VERSION = 1
INSTALL_OPERATION_HISTORY_FILENAME = "install-operation-history.json"
RECOVERY_EXECUTION_HISTORY_VERSION = 1
RECOVERY_EXECUTION_HISTORY_FILENAME = "recovery-execution-history.json"
UPDATE_SOURCE_INTENT_OVERLAY_VERSION = 1
UPDATE_SOURCE_INTENT_OVERLAY_FILENAME = "update-source-intent-overlay.json"
_VALID_UPDATE_SOURCE_INTENT_STATES = {
    LOCAL_PRIVATE_MOD,
    "no_tracking",
    "manual_source_association",
}


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
    secondary_watched_downloads_path = _optional_non_empty_string(
        app_config, "secondary_watched_downloads_path"
    )
    nexus_api_key = _optional_non_empty_string(app_config, "nexus_api_key")
    scan_target = _optional_non_empty_string(app_config, "scan_target") or "configured_real_mods"
    install_target = _optional_non_empty_string(app_config, "install_target") or "sandbox_mods"
    steam_auto_start_enabled = _optional_bool(app_config, "steam_auto_start_enabled")

    return AppConfig(
        game_path=Path(game_path),
        mods_path=Path(mods_path),
        app_data_path=Path(app_data_path),
        sandbox_mods_path=Path(sandbox_mods_path) if sandbox_mods_path else None,
        sandbox_archive_path=Path(sandbox_archive_path) if sandbox_archive_path else None,
        real_archive_path=Path(real_archive_path) if real_archive_path else None,
        watched_downloads_path=Path(watched_downloads_path) if watched_downloads_path else None,
        secondary_watched_downloads_path=(
            Path(secondary_watched_downloads_path) if secondary_watched_downloads_path else None
        ),
        nexus_api_key=nexus_api_key,
        scan_target=scan_target,
        install_target=install_target,
        steam_auto_start_enabled=(
            True if steam_auto_start_enabled is None else steam_auto_start_enabled
        ),
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
            "secondary_watched_downloads_path": (
                str(config.secondary_watched_downloads_path)
                if config.secondary_watched_downloads_path
                else None
            ),
            "nexus_api_key": config.nexus_api_key,
            "scan_target": config.scan_target,
            "install_target": config.install_target,
            "steam_auto_start_enabled": config.steam_auto_start_enabled,
        },
    }

    state_file.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(state_file, payload)


def install_operation_history_file(state_file: Path) -> Path:
    return state_file.parent / INSTALL_OPERATION_HISTORY_FILENAME


def recovery_execution_history_file(state_file: Path) -> Path:
    return state_file.parent / RECOVERY_EXECUTION_HISTORY_FILENAME


def update_source_intent_overlay_file(state_file: Path) -> Path:
    return state_file.parent / UPDATE_SOURCE_INTENT_OVERLAY_FILENAME


def load_install_operation_history(history_file: Path) -> InstallOperationHistory:
    if not history_file.exists():
        return InstallOperationHistory(operations=tuple())

    raw = _load_json_object(history_file=history_file, subject="install-operation history")
    version = raw.get("version")
    if version != INSTALL_OPERATION_HISTORY_VERSION:
        raise AppStateStoreError(
            "Unsupported install-operation history version: "
            f"{version!r}; expected {INSTALL_OPERATION_HISTORY_VERSION}"
        )

    operations_raw = raw.get("operations")
    if not isinstance(operations_raw, list):
        raise AppStateStoreError("operations must be an array")

    operations = tuple(_parse_install_operation(item, index) for index, item in enumerate(operations_raw))
    return InstallOperationHistory(operations=operations)


def save_install_operation_history(
    history_file: Path,
    history: InstallOperationHistory,
) -> None:
    payload = {
        "version": INSTALL_OPERATION_HISTORY_VERSION,
        "operations": [_serialize_install_operation(operation) for operation in history.operations],
    }

    history_file.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(history_file, payload)


def append_install_operation_record(
    history_file: Path,
    operation: InstallOperationRecord,
) -> InstallOperationHistory:
    history = load_install_operation_history(history_file)
    updated = InstallOperationHistory(operations=(*history.operations, operation))
    save_install_operation_history(history_file, updated)
    return updated


def load_recovery_execution_history(history_file: Path) -> RecoveryExecutionHistory:
    if not history_file.exists():
        return RecoveryExecutionHistory(operations=tuple())

    raw = _load_json_object(history_file=history_file, subject="recovery-execution history")
    version = raw.get("version")
    if version != RECOVERY_EXECUTION_HISTORY_VERSION:
        raise AppStateStoreError(
            "Unsupported recovery-execution history version: "
            f"{version!r}; expected {RECOVERY_EXECUTION_HISTORY_VERSION}"
        )

    operations_raw = raw.get("operations")
    if not isinstance(operations_raw, list):
        raise AppStateStoreError("operations must be an array")

    operations = tuple(
        _parse_recovery_execution_record(item, index) for index, item in enumerate(operations_raw)
    )
    return RecoveryExecutionHistory(operations=operations)


def save_recovery_execution_history(
    history_file: Path,
    history: RecoveryExecutionHistory,
) -> None:
    payload = {
        "version": RECOVERY_EXECUTION_HISTORY_VERSION,
        "operations": [
            _serialize_recovery_execution_record(operation) for operation in history.operations
        ],
    }

    history_file.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(history_file, payload)


def append_recovery_execution_record(
    history_file: Path,
    operation: RecoveryExecutionRecord,
) -> RecoveryExecutionHistory:
    history = load_recovery_execution_history(history_file)
    updated = RecoveryExecutionHistory(operations=(*history.operations, operation))
    save_recovery_execution_history(history_file, updated)
    return updated


def load_update_source_intent_overlay(overlay_file: Path) -> UpdateSourceIntentOverlay:
    if not overlay_file.exists():
        return UpdateSourceIntentOverlay(records=tuple())

    raw = _load_json_object(history_file=overlay_file, subject="update-source intent overlay")
    version = raw.get("version")
    if version != UPDATE_SOURCE_INTENT_OVERLAY_VERSION:
        raise AppStateStoreError(
            "Unsupported update-source intent overlay version: "
            f"{version!r}; expected {UPDATE_SOURCE_INTENT_OVERLAY_VERSION}"
        )

    records_raw = raw.get("records")
    if not isinstance(records_raw, list):
        raise AppStateStoreError("records must be an array")

    records = tuple(
        _parse_update_source_intent_record(item, index) for index, item in enumerate(records_raw)
    )
    return UpdateSourceIntentOverlay(records=records)


def save_update_source_intent_overlay(
    overlay_file: Path,
    overlay: UpdateSourceIntentOverlay,
) -> None:
    payload = {
        "version": UPDATE_SOURCE_INTENT_OVERLAY_VERSION,
        "records": [
            _serialize_update_source_intent_record(record) for record in overlay.records
        ],
    }

    overlay_file.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(overlay_file, payload)


def write_json_file_atomic(target_file: Path, payload: dict[str, object]) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(target_file, payload)


def write_text_file_atomic(target_file: Path, content: str) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    _write_text_atomic(target_file, content)


def _load_json_object(*, history_file: Path, subject: str) -> dict[str, object]:
    try:
        raw = json.loads(history_file.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise AppStateStoreError(f"Invalid JSON in {subject} file: {exc.msg}") from exc
    except OSError as exc:
        raise AppStateStoreError(f"Could not read {subject} file: {exc}") from exc

    if not isinstance(raw, dict):
        raise AppStateStoreError(f"{subject.capitalize()} root must be a JSON object")
    return raw


def _write_json_atomic(target_file: Path, payload: dict[str, object]) -> None:
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _write_text_atomic(target_file, serialized)


def _write_text_atomic(target_file: Path, content: str) -> None:
    target_file.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=target_file.parent,
            prefix=f".{target_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, target_file)
    except OSError as exc:
        raise AppStateStoreError(f"Could not write file atomically: {exc}") from exc
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass


def _serialize_install_operation(operation: InstallOperationRecord) -> dict[str, object]:
    return {
        "operation_id": operation.operation_id,
        "timestamp": operation.timestamp,
        "package_path": str(operation.package_path),
        "destination_kind": operation.destination_kind,
        "destination_mods_path": str(operation.destination_mods_path),
        "archive_path": str(operation.archive_path),
        "installed_targets": [str(path) for path in operation.installed_targets],
        "archived_targets": [str(path) for path in operation.archived_targets],
        "entries": [
            {
                "name": entry.name,
                "unique_id": entry.unique_id,
                "version": entry.version,
                "action": entry.action,
                "target_path": str(entry.target_path),
                "archive_path": str(entry.archive_path) if entry.archive_path is not None else None,
                "source_manifest_path": entry.source_manifest_path,
                "source_root_path": entry.source_root_path,
                "target_exists_before": entry.target_exists_before,
                "can_install": entry.can_install,
                "warnings": list(entry.warnings),
            }
            for entry in operation.entries
        ],
    }


def _parse_install_operation(data: object, index: int) -> InstallOperationRecord:
    if not isinstance(data, dict):
        raise AppStateStoreError(f"operations[{index}] must be an object")

    entries_raw = data.get("entries")
    if not isinstance(entries_raw, list):
        raise AppStateStoreError(f"operations[{index}].entries must be an array")

    return InstallOperationRecord(
        operation_id=_optional_non_empty_string(data, "operation_id", prefix=f"operations[{index}]"),
        timestamp=_require_non_empty_string(data, "timestamp", prefix=f"operations[{index}]"),
        package_path=Path(
            _require_non_empty_string(data, "package_path", prefix=f"operations[{index}]")
        ),
        destination_kind=_require_non_empty_string(
            data,
            "destination_kind",
            prefix=f"operations[{index}]",
        ),
        destination_mods_path=Path(
            _require_non_empty_string(
                data,
                "destination_mods_path",
                prefix=f"operations[{index}]",
            )
        ),
        archive_path=Path(
            _require_non_empty_string(data, "archive_path", prefix=f"operations[{index}]")
        ),
        installed_targets=_parse_path_array(
            data.get("installed_targets"),
            prefix=f"operations[{index}].installed_targets",
        ),
        archived_targets=_parse_path_array(
            data.get("archived_targets"),
            prefix=f"operations[{index}].archived_targets",
        ),
        entries=tuple(
            _parse_install_operation_entry(entry, operation_index=index, entry_index=entry_index)
            for entry_index, entry in enumerate(entries_raw)
        ),
    )


def _parse_install_operation_entry(
    data: object,
    *,
    operation_index: int,
    entry_index: int,
) -> InstallOperationEntryRecord:
    prefix = f"operations[{operation_index}].entries[{entry_index}]"
    if not isinstance(data, dict):
        raise AppStateStoreError(f"{prefix} must be an object")

    warnings_raw = data.get("warnings")
    if not isinstance(warnings_raw, list) or any(not isinstance(item, str) for item in warnings_raw):
        raise AppStateStoreError(f"{prefix}.warnings must be an array of strings")

    archive_path = _optional_non_empty_string(data, "archive_path", prefix=prefix)
    return InstallOperationEntryRecord(
        name=_require_non_empty_string(data, "name", prefix=prefix),
        unique_id=_require_non_empty_string(data, "unique_id", prefix=prefix),
        version=_require_non_empty_string(data, "version", prefix=prefix),
        action=_require_non_empty_string(data, "action", prefix=prefix),
        target_path=Path(_require_non_empty_string(data, "target_path", prefix=prefix)),
        archive_path=Path(archive_path) if archive_path else None,
        source_manifest_path=_require_non_empty_string(data, "source_manifest_path", prefix=prefix),
        source_root_path=_require_non_empty_string(data, "source_root_path", prefix=prefix),
        target_exists_before=_require_bool(data, "target_exists_before", prefix=prefix),
        can_install=_require_bool(data, "can_install", prefix=prefix),
        warnings=tuple(warnings_raw),
    )


def _serialize_recovery_execution_record(operation: RecoveryExecutionRecord) -> dict[str, object]:
    return {
        "recovery_execution_id": operation.recovery_execution_id,
        "timestamp": operation.timestamp,
        "related_install_operation_id": operation.related_install_operation_id,
        "related_install_operation_timestamp": operation.related_install_operation_timestamp,
        "related_install_package_path": (
            str(operation.related_install_package_path)
            if operation.related_install_package_path is not None
            else None
        ),
        "destination_kind": operation.destination_kind,
        "destination_mods_path": str(operation.destination_mods_path),
        "executed_entry_count": operation.executed_entry_count,
        "removed_target_paths": [str(path) for path in operation.removed_target_paths],
        "restored_target_paths": [str(path) for path in operation.restored_target_paths],
        "outcome_status": operation.outcome_status,
        "failure_message": operation.failure_message,
    }


def _parse_recovery_execution_record(data: object, index: int) -> RecoveryExecutionRecord:
    if not isinstance(data, dict):
        raise AppStateStoreError(f"operations[{index}] must be an object")

    related_install_package_path = _optional_non_empty_string(
        data,
        "related_install_package_path",
        prefix=f"operations[{index}]",
    )
    failure_message = _optional_non_empty_string(
        data,
        "failure_message",
        prefix=f"operations[{index}]",
    )
    executed_entry_count = _require_int(
        data,
        "executed_entry_count",
        prefix=f"operations[{index}]",
    )

    return RecoveryExecutionRecord(
        recovery_execution_id=_optional_non_empty_string(
            data,
            "recovery_execution_id",
            prefix=f"operations[{index}]",
        ),
        timestamp=_require_non_empty_string(data, "timestamp", prefix=f"operations[{index}]"),
        related_install_operation_id=_optional_non_empty_string(
            data,
            "related_install_operation_id",
            prefix=f"operations[{index}]",
        ),
        related_install_operation_timestamp=_optional_non_empty_string(
            data,
            "related_install_operation_timestamp",
            prefix=f"operations[{index}]",
        ),
        related_install_package_path=(
            Path(related_install_package_path) if related_install_package_path else None
        ),
        destination_kind=_require_non_empty_string(
            data,
            "destination_kind",
            prefix=f"operations[{index}]",
        ),
        destination_mods_path=Path(
            _require_non_empty_string(
                data,
                "destination_mods_path",
                prefix=f"operations[{index}]",
            )
        ),
        executed_entry_count=executed_entry_count,
        removed_target_paths=_parse_path_array(
            data.get("removed_target_paths"),
            prefix=f"operations[{index}].removed_target_paths",
        ),
        restored_target_paths=_parse_path_array(
            data.get("restored_target_paths"),
            prefix=f"operations[{index}].restored_target_paths",
        ),
        outcome_status=_require_non_empty_string(
            data,
            "outcome_status",
            prefix=f"operations[{index}]",
        ),
        failure_message=failure_message,
    )


def _serialize_update_source_intent_record(
    record: UpdateSourceIntentRecord,
) -> dict[str, object]:
    if not record.unique_id.strip():
        raise AppStateStoreError("update-source intent record unique_id must be non-empty")
    if not record.normalized_unique_id.strip():
        raise AppStateStoreError("update-source intent record normalized_unique_id must be non-empty")
    if record.intent_state not in _VALID_UPDATE_SOURCE_INTENT_STATES:
        raise AppStateStoreError(
            "update-source intent record intent_state must be one of "
            f"{sorted(_VALID_UPDATE_SOURCE_INTENT_STATES)!r}"
        )
    return {
        "unique_id": record.unique_id,
        "normalized_unique_id": record.normalized_unique_id,
        "intent_state": record.intent_state,
        "manual_provider": record.manual_provider,
        "manual_source_key": record.manual_source_key,
        "manual_source_page_url": record.manual_source_page_url,
    }


def _parse_update_source_intent_record(data: object, index: int) -> UpdateSourceIntentRecord:
    if not isinstance(data, dict):
        raise AppStateStoreError(f"records[{index}] must be an object")

    intent_state = _require_non_empty_string(data, "intent_state", prefix=f"records[{index}]")
    if intent_state not in _VALID_UPDATE_SOURCE_INTENT_STATES:
        raise AppStateStoreError(
            f"records[{index}].intent_state must be one of "
            f"{sorted(_VALID_UPDATE_SOURCE_INTENT_STATES)!r}"
        )

    return UpdateSourceIntentRecord(
        unique_id=_require_non_empty_string(data, "unique_id", prefix=f"records[{index}]"),
        normalized_unique_id=_require_non_empty_string(
            data,
            "normalized_unique_id",
            prefix=f"records[{index}]",
        ),
        intent_state=intent_state,
        manual_provider=_optional_non_empty_string(
            data,
            "manual_provider",
            prefix=f"records[{index}]",
        ),
        manual_source_key=_optional_non_empty_string(
            data,
            "manual_source_key",
            prefix=f"records[{index}]",
        ),
        manual_source_page_url=_optional_non_empty_string(
            data,
            "manual_source_page_url",
            prefix=f"records[{index}]",
        ),
    )


def _parse_path_array(value: object, *, prefix: str) -> tuple[Path, ...]:
    if not isinstance(value, list):
        raise AppStateStoreError(f"{prefix} must be an array")
    paths: list[Path] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise AppStateStoreError(f"{prefix}[{index}] must be a non-empty string")
        paths.append(Path(item))
    return tuple(paths)


def _require_int(
    data: dict[str, object],
    key: str,
    *,
    prefix: str | None = None,
) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        field_name = f"{prefix}.{key}" if prefix else key
        raise AppStateStoreError(f"{field_name} must be an integer")
    return value


def _require_non_empty_string(
    data: dict[str, object],
    key: str,
    *,
    prefix: str = "app_config",
) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AppStateStoreError(f"{prefix}.{key} must be a non-empty string")
    return value


def _optional_non_empty_string(
    data: dict[str, object],
    key: str,
    *,
    prefix: str = "app_config",
) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AppStateStoreError(f"{prefix}.{key} must be a non-empty string when provided")
    return value


def _require_bool(data: dict[str, object], key: str, *, prefix: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise AppStateStoreError(f"{prefix}.{key} must be a boolean")
    return value


def _optional_bool(
    data: dict[str, object],
    key: str,
    *,
    prefix: str = "app_config",
) -> bool | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise AppStateStoreError(f"{prefix}.{key} must be a boolean when provided")
    return value
