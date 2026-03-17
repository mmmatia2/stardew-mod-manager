from __future__ import annotations

from pathlib import Path
import re
from zipfile import ZipFile
from typing import Literal

import pytest

import sdvmm.app.shell_service as shell_service_module
import sdvmm.services.sandbox_installer as sandbox_installer_module
from sdvmm.app.shell_service import (
    ARCHIVE_SOURCE_REAL,
    ARCHIVE_SOURCE_SANDBOX,
    INSTALL_TARGET_CONFIGURED_REAL_MODS,
    INSTALL_TARGET_SANDBOX_MODS,
    SCAN_TARGET_CONFIGURED_REAL_MODS,
    SCAN_TARGET_SANDBOX_MODS,
    AppShellError,
    AppShellService,
)
from sdvmm.domain.models import (
    AppConfig,
    InstallExecutionSummary,
    InstallOperationEntryRecord,
    InstallOperationRecord,
    ModDiscoveryEntry,
    ModDiscoveryResult,
    ModUpdateReport,
    ModUpdateStatus,
    NexusIntegrationStatus,
    PackageInspectionBatchEntry,
    PackageInspectionBatchResult,
    PackageFinding,
    PackageWarning,
    RemoteModLink,
    SandboxInstallPlan,
    SandboxInstallPlanEntry,
    SmapiLogReport,
    SmapiUpdateStatus,
    UpdateSourceIntentOverlay,
    UpdateSourceIntentRecord,
)
from sdvmm.domain.install_codes import BLOCKED, INSTALL_NEW, OVERWRITE_WITH_ARCHIVE
from sdvmm.domain.package_codes import DIRECT_SINGLE_MOD_PACKAGE
from sdvmm.domain.update_codes import UpdateState
from sdvmm.domain.warning_codes import INVALID_MANIFEST
from sdvmm.services.app_state_store import (
    AppStateStoreError,
    save_app_config,
    save_update_source_intent_overlay,
    update_source_intent_overlay_file,
)


def test_load_startup_config_returns_none_when_state_absent(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    state = service.load_startup_config()

    assert state.config is None
    assert state.message is not None
    assert "No saved configuration found" in state.message


def test_load_startup_config_reports_invalid_state_file(tmp_path: Path) -> None:
    state_file = tmp_path / "app-state.json"
    state_file.write_text("{invalid", encoding="utf-8")
    service = AppShellService(state_file=state_file)

    state = service.load_startup_config()

    assert state.config is None
    assert state.message is not None
    assert "Could not load saved config" in state.message


def test_save_mods_directory_bootstraps_config_when_missing(tmp_path: Path) -> None:
    mods_path = tmp_path / "Mods"
    mods_path.mkdir()

    state_file = tmp_path / "state" / "app-state.json"
    service = AppShellService(state_file=state_file)

    config = service.save_mods_directory(str(mods_path), existing_config=None)

    assert config.mods_path == mods_path
    assert config.game_path == mods_path.parent
    assert config.app_data_path == state_file.parent


def test_save_mods_directory_preserves_existing_non_mod_paths(tmp_path: Path) -> None:
    first_mods = tmp_path / "ModsA"
    second_mods = tmp_path / "ModsB"
    first_mods.mkdir()
    second_mods.mkdir()

    existing = AppConfig(
        game_path=tmp_path / "Game",
        mods_path=first_mods,
        app_data_path=tmp_path / "AppData",
    )

    state_file = tmp_path / "state" / "app-state.json"
    save_app_config(state_file, existing)

    service = AppShellService(state_file=state_file)
    updated = service.save_mods_directory(str(second_mods), existing_config=existing)

    assert updated.mods_path == second_mods
    assert updated.game_path == existing.game_path
    assert updated.app_data_path == existing.app_data_path


def test_load_update_source_intent_overlay_returns_empty_when_state_absent(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    assert service.load_update_source_intent_overlay() == UpdateSourceIntentOverlay(records=tuple())


def test_set_update_source_intent_persists_local_private_and_no_tracking_states(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")

    first = service.set_update_source_intent("Sample.Private", "local_private_mod")
    second = service.set_update_source_intent("Sample.Untracked", "no_tracking")

    assert len(first.records) == 1
    assert len(second.records) == 2
    assert second.records[0].normalized_unique_id == "sample.private"
    assert second.records[0].intent_state == "local_private_mod"
    assert second.records[1].normalized_unique_id == "sample.untracked"
    assert second.records[1].intent_state == "no_tracking"

    loaded = service.load_update_source_intent_overlay()
    assert loaded == second
    assert service.get_update_source_intent("sample.private") == second.records[0]
    assert service.get_update_source_intent("SAMPLE.UNTRACKED") == second.records[1]


def test_set_update_source_intent_updates_existing_record_by_canonical_unique_id(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")
    service.set_update_source_intent("Sample.Mod", "local_private_mod")

    updated = service.set_update_source_intent(
        " sample.mod ",
        "manual_source_association",
        manual_provider="nexus",
        manual_source_key="12345",
        manual_source_page_url="https://example.test/mods/12345",
    )

    assert len(updated.records) == 1
    record = updated.records[0]
    assert record.unique_id == "sample.mod"
    assert record.normalized_unique_id == "sample.mod"
    assert record.intent_state == "manual_source_association"
    assert record.manual_provider == "nexus"
    assert record.manual_source_key == "12345"
    assert record.manual_source_page_url == "https://example.test/mods/12345"


def test_clear_update_source_intent_removes_matching_record(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")
    save_update_source_intent_overlay(
        update_source_intent_overlay_file(service.state_file),
        UpdateSourceIntentOverlay(
            records=(
                UpdateSourceIntentRecord(
                    unique_id="Sample.Private",
                    normalized_unique_id="sample.private",
                    intent_state="local_private_mod",
                ),
                UpdateSourceIntentRecord(
                    unique_id="Sample.Keep",
                    normalized_unique_id="sample.keep",
                    intent_state="no_tracking",
                ),
            )
        ),
    )

    updated = service.clear_update_source_intent(" SAMPLE.PRIVATE ")

    assert updated.records == (
        UpdateSourceIntentRecord(
            unique_id="Sample.Keep",
            normalized_unique_id="sample.keep",
            intent_state="no_tracking",
        ),
    )
    assert service.get_update_source_intent("sample.private") is None
    assert service.get_update_source_intent("sample.keep") == updated.records[0]


def test_scan_rejects_missing_mods_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    with pytest.raises(AppShellError, match="does not exist"):
        service.scan(str(tmp_path / "missing"))


def test_scan_returns_inventory_for_valid_mods_path(tmp_path: Path, mods_case_path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    inventory = service.scan(str(mods_case_path("valid_manifest")))

    assert len(inventory.mods) == 1
    assert inventory.mods[0].unique_id == "Sample.VisibleFish"


def test_scan_with_target_uses_configured_real_mods_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    configured_mods = tmp_path / "ConfiguredMods"
    sandbox_mods = tmp_path / "SandboxMods"
    _create_mod(configured_mods, "ConfiguredMod", "Real.Mod")
    _create_mod(sandbox_mods, "SandboxMod", "Sandbox.Mod")

    result = service.scan_with_target(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(configured_mods),
        sandbox_mods_path_text=str(sandbox_mods),
    )

    assert result.target_kind == SCAN_TARGET_CONFIGURED_REAL_MODS
    assert result.scan_path == configured_mods
    assert len(result.inventory.mods) == 1
    assert result.inventory.mods[0].unique_id == "Real.Mod"


def test_scan_with_target_uses_sandbox_mods_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    configured_mods = tmp_path / "ConfiguredMods"
    sandbox_mods = tmp_path / "SandboxMods"
    _create_mod(configured_mods, "ConfiguredMod", "Real.Mod")
    _create_mod(sandbox_mods, "SandboxMod", "Sandbox.Mod")

    result = service.scan_with_target(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(configured_mods),
        sandbox_mods_path_text=str(sandbox_mods),
    )

    assert result.target_kind == SCAN_TARGET_SANDBOX_MODS
    assert result.scan_path == sandbox_mods
    assert len(result.inventory.mods) == 1
    assert result.inventory.mods[0].unique_id == "Sandbox.Mod"


def test_launch_game_vanilla_uses_saved_game_path_when_input_empty(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Game"
    game_path.mkdir()
    executable = game_path / "Stardew Valley"
    executable.write_text("", encoding="utf-8")
    config = AppConfig(
        game_path=game_path,
        mods_path=tmp_path / "Mods",
        app_data_path=tmp_path / "AppData",
    )
    captured: dict[str, object] = {}

    def _fake_launch(command):
        captured["command"] = command
        return 31337

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(shell_service_module, "launch_game_process", _fake_launch)
    try:
        result = service.launch_game_vanilla(game_path_text="", existing_config=config)
    finally:
        monkeypatch.undo()

    command = captured.get("command")
    assert command is not None
    assert result.mode == "vanilla"
    assert result.game_path == game_path
    assert result.executable_path == executable
    assert result.pid == 31337


def test_launch_game_smapi_is_blocked_when_not_detected(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Game"
    game_path.mkdir()
    (game_path / "Stardew Valley").write_text("", encoding="utf-8")

    with pytest.raises(AppShellError, match="SMAPI launch is unavailable"):
        service.launch_game_smapi(game_path_text=str(game_path), existing_config=None)


def test_get_sandbox_dev_launch_readiness_reports_missing_game_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    readiness = service.get_sandbox_dev_launch_readiness(
        game_path_text="",
        sandbox_mods_path_text="",
        configured_mods_path_text="",
        existing_config=None,
    )

    assert readiness.ready is False
    assert readiness.message == "Game directory is required"


def test_get_sandbox_dev_launch_readiness_reports_smapi_unavailable(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Game"
    sandbox_mods = tmp_path / "SandboxMods"
    _create_launchable_game_install(game_path, with_smapi=False)
    sandbox_mods.mkdir()

    readiness = service.get_sandbox_dev_launch_readiness(
        game_path_text=str(game_path),
        sandbox_mods_path_text=str(sandbox_mods),
        configured_mods_path_text="",
        existing_config=None,
    )

    assert readiness.ready is False
    assert "SMAPI launch is unavailable" in readiness.message


def test_get_sandbox_dev_launch_readiness_blocks_matching_real_mods_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Game"
    mods_path = tmp_path / "Mods"
    _create_launchable_game_install(game_path)
    mods_path.mkdir()

    readiness = service.get_sandbox_dev_launch_readiness(
        game_path_text=str(game_path),
        sandbox_mods_path_text=str(mods_path),
        configured_mods_path_text=str(mods_path),
        existing_config=None,
    )

    assert readiness.ready is False
    assert "matches the configured real Mods path" in readiness.message


def test_launch_game_sandbox_dev_uses_smapi_with_sandbox_mods_override(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Game"
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    smapi_executable = _create_launchable_game_install(game_path)
    real_mods.mkdir()
    sandbox_mods.mkdir()
    captured: dict[str, object] = {}

    def _fake_launch(command):
        captured["command"] = command
        return 42424

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(shell_service_module, "launch_game_process", _fake_launch)
    try:
        result = service.launch_game_sandbox_dev(
            game_path_text=str(game_path),
            sandbox_mods_path_text=str(sandbox_mods),
            configured_mods_path_text=str(real_mods),
            existing_config=None,
        )
    finally:
        monkeypatch.undo()

    command = captured.get("command")
    assert command is not None
    assert command.argv == (
        str(smapi_executable),
        "--mods-path",
        str(sandbox_mods),
    )
    assert result.mode == "sandbox_dev_smapi"
    assert result.game_path == game_path
    assert result.pid == 42424
    assert result.executable_path == smapi_executable
    assert result.mods_path_override == sandbox_mods


def test_get_sandbox_mods_sync_readiness_requires_selection(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()

    readiness = service.get_sandbox_mods_sync_readiness(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        selected_mod_folder_paths_text=tuple(),
        existing_config=None,
    )

    assert readiness.ready is False
    assert readiness.message == "Select at least one installed mod row to sync to sandbox."


def test_sync_installed_mods_to_sandbox_copies_selected_real_mod(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    source_mod = _create_mod(real_mods, "SampleMod", "Sample.Mod")
    (source_mod / "config.json").write_text('{"ok": true}', encoding="utf-8")

    result = service.sync_installed_mods_to_sandbox(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        selected_mod_folder_paths_text=(str(source_mod),),
        existing_config=None,
    )

    target_mod = sandbox_mods / "SampleMod"
    assert result.real_mods_path == real_mods
    assert result.sandbox_mods_path == sandbox_mods
    assert result.source_mod_paths == (source_mod,)
    assert result.synced_target_paths == (target_mod,)
    assert (target_mod / "manifest.json").exists()
    assert (target_mod / "config.json").read_text(encoding="utf-8") == '{"ok": true}'


def test_get_sandbox_mods_sync_readiness_reports_conflict(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    source_mod = _create_mod(real_mods, "SampleMod", "Sample.Mod")
    _create_mod(sandbox_mods, "SampleMod", "Sample.Mod")

    readiness = service.get_sandbox_mods_sync_readiness(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        selected_mod_folder_paths_text=(str(source_mod),),
        existing_config=None,
    )

    assert readiness.ready is False
    assert "sandbox target already exists for SampleMod" in readiness.message


def test_sync_installed_mods_to_sandbox_rejects_mod_outside_real_mods(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    external_mods = tmp_path / "OtherMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    external_mods.mkdir()
    external_mod = _create_mod(external_mods, "OutsideMod", "Outside.Mod")

    with pytest.raises(
        AppShellError,
        match="Selected mod folder must be a direct child of the selected Mods destination.",
    ):
        service.sync_installed_mods_to_sandbox(
            configured_mods_path_text=str(real_mods),
            sandbox_mods_path_text=str(sandbox_mods),
            selected_mod_folder_paths_text=(str(external_mod),),
            existing_config=None,
        )


def test_get_sandbox_mods_promotion_readiness_requires_selection(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()

    readiness = service.get_sandbox_mods_promotion_readiness(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        selected_mod_folder_paths_text=tuple(),
        existing_config=None,
    )

    assert readiness.ready is False
    assert readiness.message == "Select at least one installed sandbox mod row to promote."


def test_build_sandbox_mods_promotion_preview_reports_non_conflicting_real_write_review(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    source_mod = _create_mod(sandbox_mods, "SampleMod", "Sample.Mod")

    preview = service.build_sandbox_mods_promotion_preview(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        selected_mod_folder_paths_text=(str(source_mod),),
        existing_config=None,
    )

    assert preview.real_mods_path == real_mods
    assert preview.sandbox_mods_path == sandbox_mods
    assert preview.archive_path == real_mods.parent / ".sdvmm-real-archive"
    assert preview.source_mod_paths == (source_mod,)
    assert preview.review.allowed is True
    assert preview.review.requires_explicit_approval is True
    assert preview.review.summary.has_existing_targets_to_replace is False
    assert preview.review.summary.has_archive_writes is False
    assert len(preview.plan.entries) == 1
    assert preview.plan.entries[0].action == INSTALL_NEW
    assert preview.plan.entries[0].target_exists is False
    assert preview.plan.entries[0].archive_path is None


def test_promote_installed_mods_from_sandbox_to_real_copies_and_records_history(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    source_mod = _create_mod(sandbox_mods, "SampleMod", "Sample.Mod")
    (source_mod / "dev.txt").write_text("sandbox", encoding="utf-8")

    result = service.promote_installed_mods_from_sandbox_to_real(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        selected_mod_folder_paths_text=(str(source_mod),),
        existing_config=None,
    )

    promoted_target = real_mods / "SampleMod"
    assert result.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert result.real_mods_path == real_mods
    assert result.sandbox_mods_path == sandbox_mods
    assert result.archive_path == real_mods.parent / ".sdvmm-real-archive"
    assert result.source_mod_paths == (source_mod,)
    assert result.promoted_target_paths == (promoted_target,)
    assert result.scan_context_path == real_mods
    assert (promoted_target / "manifest.json").exists()
    assert (promoted_target / "dev.txt").read_text(encoding="utf-8") == "sandbox"

    history = service.load_install_operation_history()
    assert len(history.operations) == 1
    operation = history.operations[0]
    assert operation.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert operation.destination_mods_path == real_mods
    assert operation.archive_path == real_mods.parent / ".sdvmm-real-archive"
    assert operation.installed_targets == (promoted_target,)
    assert operation.archived_targets == tuple()
    assert len(operation.entries) == 1
    assert operation.entries[0].action == INSTALL_NEW
    assert operation.entries[0].source_root_path == str(source_mod)
    assert operation.entries[0].target_path == promoted_target


def test_get_sandbox_mods_promotion_readiness_reports_archive_aware_replace_review_for_conflict(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    source_mod = _create_mod(sandbox_mods, "SampleMod", "Sample.Mod")
    _create_mod(real_mods, "SampleMod", "Sample.Mod")

    readiness = service.get_sandbox_mods_promotion_readiness(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        selected_mod_folder_paths_text=(str(source_mod),),
        existing_config=None,
    )

    assert readiness.ready is True
    assert readiness.replace_count == 1
    assert "archive-aware live replacement" in readiness.message


def test_promote_installed_mods_from_sandbox_to_real_replaces_conflicting_target_with_archive(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    source_mod = _create_mod(sandbox_mods, "SampleMod", "Sample.Mod")
    (source_mod / "dev.txt").write_text("sandbox", encoding="utf-8")
    existing_target = _create_mod(real_mods, "SampleMod", "Sample.Mod")
    (existing_target / "dev.txt").write_text("live", encoding="utf-8")

    result = service.promote_installed_mods_from_sandbox_to_real(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        selected_mod_folder_paths_text=(str(source_mod),),
        existing_config=None,
    )

    promoted_target = real_mods / "SampleMod"
    assert result.promoted_target_paths == (promoted_target,)
    assert result.replaced_target_paths == (promoted_target,)
    assert len(result.archived_target_paths) == 1
    archived_target = result.archived_target_paths[0]
    assert archived_target.parent == real_mods.parent / ".sdvmm-real-archive"
    assert archived_target.name.startswith("SampleMod__sdvmm_archive_")
    assert (promoted_target / "dev.txt").read_text(encoding="utf-8") == "sandbox"
    assert (archived_target / "dev.txt").read_text(encoding="utf-8") == "live"
    assert any(mod.folder_path == promoted_target for mod in result.inventory.mods)

    history = service.load_install_operation_history()
    assert len(history.operations) == 1
    operation = history.operations[0]
    assert operation.installed_targets == (promoted_target,)
    assert operation.archived_targets == (archived_target,)
    assert len(operation.entries) == 1
    assert operation.entries[0].action == OVERWRITE_WITH_ARCHIVE
    assert operation.entries[0].target_exists_before is True
    assert operation.entries[0].archive_path == archived_target


def test_promote_installed_mods_from_sandbox_to_real_rolls_back_earlier_live_writes_on_later_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    alpha_source = _create_mod(sandbox_mods, "AlphaMod", "Alpha.Mod")
    beta_source = _create_mod(sandbox_mods, "BetaMod", "Beta.Mod")
    original_rename = Path.rename

    def fake_rename(self: Path, target: Path):
        if self.name == "BetaMod" and target == real_mods / "BetaMod":
            raise OSError("simulated beta promotion failure")
        return original_rename(self, target)

    monkeypatch.setattr(Path, "rename", fake_rename)

    with pytest.raises(
        AppShellError,
        match="Promotion rollback restored prior REAL Mods state",
    ):
        service.promote_installed_mods_from_sandbox_to_real(
            configured_mods_path_text=str(real_mods),
            sandbox_mods_path_text=str(sandbox_mods),
            real_archive_path_text="",
            selected_mod_folder_paths_text=(str(alpha_source), str(beta_source)),
            existing_config=None,
        )

    assert not (real_mods / "AlphaMod").exists()
    assert not (real_mods / "BetaMod").exists()
    history = service.load_install_operation_history()
    assert history.operations == tuple()


def test_promote_installed_mods_from_sandbox_to_real_records_partial_history_when_rollback_cannot_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    alpha_source = _create_mod(sandbox_mods, "AlphaMod", "Alpha.Mod")
    beta_source = _create_mod(sandbox_mods, "BetaMod", "Beta.Mod")
    original_rename = Path.rename
    original_remove = shell_service_module._remove_path_for_promotion_rollback

    def fake_rename(self: Path, target: Path):
        if self.name == "BetaMod" and target == real_mods / "BetaMod":
            raise OSError("simulated beta promotion failure")
        return original_rename(self, target)

    def fake_remove(path: Path) -> None:
        if path == real_mods / "AlphaMod":
            raise OSError("simulated rollback removal failure")
        return original_remove(path)

    monkeypatch.setattr(Path, "rename", fake_rename)
    monkeypatch.setattr(shell_service_module, "_remove_path_for_promotion_rollback", fake_remove)

    with pytest.raises(
        AppShellError,
        match="Remaining live changes were recorded in install history for recovery inspection",
    ):
        service.promote_installed_mods_from_sandbox_to_real(
            configured_mods_path_text=str(real_mods),
            sandbox_mods_path_text=str(sandbox_mods),
            real_archive_path_text="",
            selected_mod_folder_paths_text=(str(alpha_source), str(beta_source)),
            existing_config=None,
        )

    alpha_target = real_mods / "AlphaMod"
    assert alpha_target.exists()
    assert not (real_mods / "BetaMod").exists()

    history = service.load_install_operation_history()
    assert len(history.operations) == 1
    operation = history.operations[0]
    assert operation.installed_targets == (alpha_target,)
    assert operation.archived_targets == tuple()
    assert len(operation.entries) == 1
    assert operation.entries[0].target_path == alpha_target
    assert operation.entries[0].action == INSTALL_NEW
    assert any(
        "Partial sandbox promotion failure" in warning
        for warning in operation.entries[0].warnings
    )


def test_promote_installed_mods_from_sandbox_to_real_rejects_mod_outside_sandbox(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    external_mods = tmp_path / "OtherMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    external_mods.mkdir()
    external_mod = _create_mod(external_mods, "OutsideMod", "Outside.Mod")

    with pytest.raises(
        AppShellError,
        match="Selected mod folder must be a direct child of the selected Mods destination.",
    ):
        service.promote_installed_mods_from_sandbox_to_real(
            configured_mods_path_text=str(real_mods),
            sandbox_mods_path_text=str(sandbox_mods),
            real_archive_path_text="",
            selected_mod_folder_paths_text=(str(external_mod),),
            existing_config=None,
        )


def test_check_smapi_update_status_uses_saved_game_path_when_input_empty(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Game"
    game_path.mkdir()
    config = AppConfig(
        game_path=game_path,
        mods_path=tmp_path / "Mods",
        app_data_path=tmp_path / "AppData",
    )

    expected = SmapiUpdateStatus(
        state="up_to_date",
        game_path=game_path,
        smapi_path=game_path / "StardewModdingAPI",
        installed_version="4.5.1",
        latest_version="4.5.1",
        update_page_url="https://example.test/smapi",
        message="SMAPI is up to date.",
    )

    captured: dict[str, Path] = {}

    def _fake_check_smapi_update_status(*, game_path: Path) -> SmapiUpdateStatus:
        captured["game_path"] = game_path
        return expected

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        shell_service_module,
        "check_smapi_update_status_service",
        _fake_check_smapi_update_status,
    )
    try:
        result = service.check_smapi_update_status(game_path_text="", existing_config=config)
    finally:
        monkeypatch.undo()

    assert captured["game_path"] == game_path
    assert result == expected


def test_resolve_smapi_update_page_url_uses_status_url_when_available(tmp_path: Path) -> None:
    _ = tmp_path
    status = SmapiUpdateStatus(
        state="update_available",
        game_path=Path("/tmp/game"),
        smapi_path=Path("/tmp/game/StardewModdingAPI"),
        installed_version="4.4.0",
        latest_version="4.5.1",
        update_page_url="https://example.test/releases/latest",
        message="Update available",
    )

    assert AppShellService.resolve_smapi_update_page_url(status) == "https://example.test/releases/latest"


def test_check_smapi_log_troubleshooting_accepts_manual_log_without_game_path(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    log_path = tmp_path / "SMAPI-latest.txt"
    log_path.write_text("[SMAPI] test log\n", encoding="utf-8")

    expected = SmapiLogReport(
        state="parsed",
        source="manual",
        log_path=log_path,
        game_path=None,
        findings=tuple(),
        notes=("ok",),
        message="parsed",
    )

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        shell_service_module,
        "check_smapi_log_troubleshooting_service",
        lambda *, game_path, manual_log_path: expected,
    )
    try:
        result = service.check_smapi_log_troubleshooting(
            game_path_text="",
            log_path_text=str(log_path),
            existing_config=None,
        )
    finally:
        monkeypatch.undo()

    assert result == expected


def test_check_smapi_log_troubleshooting_requires_game_path_for_auto_lookup(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    with pytest.raises(AppShellError, match="Game directory is required"):
        service.check_smapi_log_troubleshooting(
            game_path_text="",
            log_path_text="",
            existing_config=None,
        )


def test_inspect_zip_rejects_missing_package_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    with pytest.raises(AppShellError, match="does not exist"):
        service.inspect_zip(str(tmp_path / "missing.zip"))


def test_inspect_zip_rejects_non_zip_file(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    text_file = tmp_path / "not_zip.txt"
    text_file.write_text("hello", encoding="utf-8")

    with pytest.raises(AppShellError, match="not a .zip package"):
        service.inspect_zip(str(text_file))


def test_inspect_zip_returns_package_result(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    package = tmp_path / "single.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    result = service.inspect_zip(str(package))

    assert len(result.mods) == 1
    assert result.mods[0].unique_id == "Pkg.Zip"


def test_inspect_zip_with_inventory_context_resolves_content_pack_for_dependency(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    package = tmp_path / "cp_pack.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "[CP] Pack/manifest.json",
            (
                "{"
                '"Name":"CP Pack",'
                '"UniqueID":"Sample.ContentPack",'
                '"Version":"1.0.0",'
                '"ContentPackFor":{"UniqueID":"Pathoschild.ContentPatcher"}'
                "}"
            ),
        )

    result = service.inspect_zip_with_inventory_context(
        str(package),
        _inventory_with_mod("Pathoschild.ContentPatcher"),
    )

    assert any(
        finding.dependency_unique_id == "Pathoschild.ContentPatcher"
        and finding.state == "satisfied"
        for finding in result.dependency_findings
    )


def test_inspect_zip_with_inventory_context_includes_remote_requirement_guidance(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    package = tmp_path / "simple.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Simple/manifest.json",
            '{"Name":"Simple","UniqueID":"Sample.Simple","Version":"1.0.0"}',
        )

    result = service.inspect_zip_with_inventory_context(str(package), _empty_inventory())

    assert len(result.remote_requirements) == 1
    assert result.remote_requirements[0].unique_id == "Sample.Simple"
    assert result.remote_requirements[0].state == "no_remote_link"


def test_inspect_zip_batch_with_inventory_context_returns_per_package_results(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    first_package = tmp_path / "first.zip"
    second_package = tmp_path / "second.zip"

    with ZipFile(first_package, "w") as archive:
        archive.writestr(
            "First/manifest.json",
            '{"Name":"First","UniqueID":"Pkg.First","Version":"1.0.0"}',
        )
    with ZipFile(second_package, "w") as archive:
        archive.writestr(
            "Second/manifest.json",
            '{"Name":"Second","UniqueID":"Pkg.Second","Version":"2.0.0"}',
        )

    result = service.inspect_zip_batch_with_inventory_context(
        (str(first_package), str(second_package)),
        _empty_inventory(),
    )

    assert isinstance(result, PackageInspectionBatchResult)
    assert len(result.entries) == 2
    assert result.entries[0] == PackageInspectionBatchEntry(
        package_path=first_package,
        inspection=result.entries[0].inspection,
    )
    assert result.entries[1] == PackageInspectionBatchEntry(
        package_path=second_package,
        inspection=result.entries[1].inspection,
    )
    assert result.entries[0].inspection is not None
    assert result.entries[0].inspection.mods[0].unique_id == "Pkg.First"
    assert result.entries[1].inspection is not None
    assert result.entries[1].inspection.mods[0].unique_id == "Pkg.Second"


def test_inspect_zip_batch_with_inventory_context_keeps_partial_failures_visible(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    valid_package = tmp_path / "valid.zip"
    broken_package = tmp_path / "broken.zip"

    with ZipFile(valid_package, "w") as archive:
        archive.writestr(
            "Valid/manifest.json",
            '{"Name":"Valid","UniqueID":"Pkg.Valid","Version":"1.0.0"}',
        )
    broken_package.write_bytes(b"not a real zip")

    result = service.inspect_zip_batch_with_inventory_context(
        (str(valid_package), str(broken_package)),
        _empty_inventory(),
    )

    assert len(result.entries) == 2
    assert result.entries[0].inspection is not None
    assert result.entries[0].error_message is None
    assert result.entries[1].inspection is None
    assert result.entries[1].package_path == broken_package
    assert result.entries[1].error_message == f"File is not a valid zip package: {broken_package}"


def test_inspect_zip_rejects_invalid_zip_content(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    package = tmp_path / "broken.zip"
    package.write_bytes(b"not a real zip")

    with pytest.raises(AppShellError, match="not a valid zip package"):
        service.inspect_zip(str(package))


def test_build_sandbox_install_plan_rejects_missing_sandbox_dir(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="Sandbox Mods directory does not exist"):
        service.build_sandbox_install_plan(
            str(package),
            str(tmp_path / "missing_sandbox"),
            str(tmp_path / "SandboxArchive"),
            allow_overwrite=False,
        )


def test_build_sandbox_install_plan_blocks_target_matching_configured_real_mods(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    real_mods.mkdir()
    package = tmp_path / "single.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="matches configured real Mods path"):
        service.build_sandbox_install_plan(
            str(package),
            str(real_mods),
            str(tmp_path / "SandboxArchive"),
            allow_overwrite=False,
            configured_real_mods_path=real_mods,
        )


def test_build_sandbox_install_plan_blocks_target_matching_configured_real_mods_via_symlink(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    real_mods.mkdir()

    symlink_target = tmp_path / "AliasMods"
    try:
        symlink_target.symlink_to(real_mods, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlink not available for deterministic path-match test: {exc}")

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="matches configured real Mods path"):
        service.build_sandbox_install_plan(
            str(package),
            str(symlink_target),
            str(tmp_path / "SandboxArchive"),
            allow_overwrite=False,
            configured_real_mods_path=real_mods,
        )


def test_build_sandbox_install_plan_allows_safe_custom_target(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox.mkdir()
    archive_root.mkdir()

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        str(archive_root),
        allow_overwrite=False,
        configured_real_mods_path=real_mods,
    )

    assert len(plan.entries) == 1
    assert plan.sandbox_mods_path == sandbox
    assert len(plan.remote_requirements) == 1
    assert plan.remote_requirements[0].state == "no_remote_link"


def test_build_install_plan_supports_configured_real_mods_destination(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox.mkdir()

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    plan = service.build_install_plan(
        package_path_text=str(package),
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox),
        real_archive_path_text="",
        sandbox_archive_path_text="",
        allow_overwrite=False,
        configured_real_mods_path=real_mods,
    )

    assert plan.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert plan.sandbox_mods_path == real_mods
    assert plan.sandbox_archive_path == real_mods.parent / ".sdvmm-real-archive"
    assert len(plan.entries) == 1
    assert plan.entries[0].action == "install_new"


def test_build_install_plan_uses_archive_overwrite_for_real_mods_destination(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox.mkdir()
    (real_mods / "Mod").mkdir()

    package = tmp_path / "update.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"2.0.0"}',
        )

    plan = service.build_install_plan(
        package_path_text=str(package),
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox),
        real_archive_path_text="",
        sandbox_archive_path_text="",
        allow_overwrite=True,
        configured_real_mods_path=real_mods,
    )

    assert len(plan.entries) == 1
    assert plan.entries[0].action == "overwrite_with_archive"
    assert plan.entries[0].archive_path is not None
    assert plan.entries[0].archive_path.parent == real_mods.parent / ".sdvmm-real-archive"


def test_build_install_execution_summary_for_sandbox_destination(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    plan = _summary_plan(tmp_path, destination_kind=INSTALL_TARGET_SANDBOX_MODS)

    summary = service.build_install_execution_summary(plan)

    assert summary.destination_kind == INSTALL_TARGET_SANDBOX_MODS
    assert summary.destination_mods_path == plan.sandbox_mods_path
    assert summary.archive_path == plan.sandbox_archive_path
    assert summary.total_entry_count == 1
    assert _summary_action_counts(summary) == {
        INSTALL_NEW: 1,
        OVERWRITE_WITH_ARCHIVE: 0,
        BLOCKED: 0,
    }
    assert summary.has_existing_targets_to_replace is False
    assert summary.has_archive_writes is False
    assert summary.requires_explicit_confirmation is False
    assert summary.review_warnings == ("Plan review warning", "Package warning message")


def test_build_install_execution_summary_for_real_destination_requires_confirmation(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    plan = _summary_plan(tmp_path, destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS)

    summary = service.build_install_execution_summary(plan)

    assert summary.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert summary.requires_explicit_confirmation is True
    assert summary.destination_mods_path == plan.sandbox_mods_path
    assert summary.archive_path == plan.sandbox_archive_path


def test_build_install_execution_summary_marks_overwrite_and_archive_behavior(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    plan = _summary_plan(
        tmp_path,
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        entries=(
            _summary_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                target_exists=True,
                archive_path=tmp_path / "SandboxArchive" / "Existing Mod-old",
                warnings=("Archive existing target before overwrite.",),
            ),
        ),
    )

    summary = service.build_install_execution_summary(plan)

    assert _summary_action_counts(summary)[OVERWRITE_WITH_ARCHIVE] == 1
    assert summary.has_existing_targets_to_replace is True
    assert summary.has_archive_writes is True
    assert "Existing Mod: Archive existing target before overwrite." in summary.review_warnings


def test_build_install_execution_summary_includes_blocked_entries_in_action_counts(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    plan = _summary_plan(
        tmp_path,
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        entries=(
            _summary_entry(tmp_path, name="Install New", unique_id="Sample.New", action=INSTALL_NEW),
            _summary_entry(
                tmp_path,
                name="Blocked Mod",
                unique_id="Sample.Blocked",
                action=BLOCKED,
                can_install=False,
                warnings=("Dependency missing.",),
            ),
        ),
    )

    summary = service.build_install_execution_summary(plan)

    assert summary.total_entry_count == 2
    assert _summary_action_counts(summary) == {
        INSTALL_NEW: 1,
        OVERWRITE_WITH_ARCHIVE: 0,
        BLOCKED: 1,
    }
    assert "Blocked Mod: Dependency missing." in summary.review_warnings


def test_review_install_execution_allows_sandbox_plan_without_explicit_approval(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    plan = _summary_plan(tmp_path, destination_kind=INSTALL_TARGET_SANDBOX_MODS)

    review = service.review_install_execution(plan)

    assert review.allowed is True
    assert review.requires_explicit_approval is False
    assert review.decision_code == "sandbox_allowed"
    assert "Sandbox install can proceed" in review.message
    assert review.summary == service.build_install_execution_summary(plan)


def test_review_install_execution_requires_explicit_approval_for_real_destination(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    plan = _summary_plan(tmp_path, destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS)

    review = service.review_install_execution(plan)

    assert review.allowed is True
    assert review.requires_explicit_approval is True
    assert review.decision_code == "real_approval_required"
    assert "Explicit approval is required" in review.message
    assert str(plan.sandbox_mods_path) in review.message
    assert review.summary.requires_explicit_confirmation is True


def test_review_install_execution_blocks_plan_with_blocked_entries(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    plan = _summary_plan(
        tmp_path,
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        entries=(
            _summary_entry(tmp_path, name="Install New", unique_id="Sample.New", action=INSTALL_NEW),
            _summary_entry(
                tmp_path,
                name="Blocked Mod",
                unique_id="Sample.Blocked",
                action=BLOCKED,
                can_install=False,
                warnings=("Dependency missing.",),
            ),
        ),
    )

    review = service.review_install_execution(plan)

    assert review.allowed is False
    assert review.requires_explicit_approval is False
    assert review.decision_code == "blocked_entries_present"
    assert "blocked" in review.message.casefold()
    assert review.summary.total_entry_count == 2
    assert _summary_action_counts(review.summary)[BLOCKED] == 1


def test_review_install_execution_allows_mixed_action_plan_when_no_entries_blocked(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    plan = _summary_plan(
        tmp_path,
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        entries=(
            _summary_entry(tmp_path, name="New Mod", unique_id="Sample.New", action=INSTALL_NEW),
            _summary_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                target_exists=True,
                archive_path=tmp_path / "SandboxArchive" / "Existing Mod-old",
                warnings=("Archive existing target before overwrite.",),
            ),
        ),
    )

    review = service.review_install_execution(plan)

    assert review.allowed is True
    assert review.requires_explicit_approval is False
    assert review.decision_code == "sandbox_allowed"
    assert review.summary.has_existing_targets_to_replace is True
    assert review.summary.has_archive_writes is True
    assert "archive/replace actions" in review.message


def test_review_install_execution_aligns_with_existing_summary_fields(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    plan = _summary_plan(
        tmp_path,
        destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        entries=(
            _summary_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                target_exists=True,
                archive_path=tmp_path / "RealArchive" / "Existing Mod-old",
            ),
        ),
    )

    summary = service.build_install_execution_summary(plan)
    review = service.review_install_execution(plan)

    assert review.summary == summary
    assert review.requires_explicit_approval == summary.requires_explicit_confirmation
    assert review.allowed is True
    assert review.summary.has_existing_targets_to_replace is True
    assert review.summary.has_archive_writes is True


def test_execute_sandbox_install_plan_blocks_blocked_entry_plan_using_review_message(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    plan = _summary_plan(
        tmp_path,
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        entries=(
            _summary_entry(tmp_path, name="Install New", unique_id="Sample.New", action=INSTALL_NEW),
            _summary_entry(
                tmp_path,
                name="Blocked Mod",
                unique_id="Sample.Blocked",
                action=BLOCKED,
                can_install=False,
                warnings=("Dependency missing.",),
            ),
        ),
    )
    review = service.review_install_execution(plan)
    assert review.allowed is False

    with pytest.raises(AppShellError, match=re.escape(review.message)):
        service.execute_sandbox_install_plan(plan)


def test_execute_real_mods_plan_requires_explicit_confirmation(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox.mkdir()

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )
        archive.writestr("Mod/file.txt", "hello")

    plan = service.build_install_plan(
        package_path_text=str(package),
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox),
        real_archive_path_text="",
        sandbox_archive_path_text="",
        allow_overwrite=False,
        configured_real_mods_path=real_mods,
    )

    review = service.review_install_execution(plan)
    assert review.allowed is True
    assert review.requires_explicit_approval is True

    with pytest.raises(AppShellError, match=re.escape(review.message)):
        service.execute_sandbox_install_plan(plan)

    result = service.execute_sandbox_install_plan(
        plan,
        confirm_real_destination=True,
    )
    assert result.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert result.scan_context_path == real_mods
    assert (real_mods / "Mod" / "file.txt").read_text(encoding="utf-8") == "hello"


def test_execute_sandbox_install_plan_matches_review_for_allowed_sandbox_plan(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    sandbox.mkdir()
    archive_root.mkdir()
    package = tmp_path / "single.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )
        archive.writestr("Mod/file.txt", "hello")

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        str(archive_root),
        allow_overwrite=False,
    )
    review = service.review_install_execution(plan)

    assert review.allowed is True
    assert review.requires_explicit_approval is False

    result = service.execute_sandbox_install_plan(plan)

    assert result.destination_kind == INSTALL_TARGET_SANDBOX_MODS
    assert result.scan_context_path == sandbox


def test_execute_sandbox_install_plan_surfaces_install_history_recording_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    sandbox.mkdir()
    archive_root.mkdir()
    package = tmp_path / "single.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )
        archive.writestr("Mod/file.txt", "hello")

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        str(archive_root),
        allow_overwrite=False,
    )
    monkeypatch.setattr(
        shell_service_module,
        "append_install_operation_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AppStateStoreError("disk full")),
    )

    with pytest.raises(AppShellError, match="Install completed, but recording install history failed"):
        service.execute_sandbox_install_plan(plan)

    assert (sandbox / "Mod" / "file.txt").read_text(encoding="utf-8") == "hello"
    assert service.load_install_operation_history().operations == tuple()


def test_execute_sandbox_install_plan_surfaces_lock_like_overwrite_failure_with_clear_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    sandbox.mkdir()
    archive_root.mkdir()
    _create_mod(sandbox, "Existing", "Sample.Exists")
    package = tmp_path / "update.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Existing/manifest.json",
            '{"Name":"Existing","UniqueID":"Sample.Exists","Version":"2.0.0"}',
        )
        archive.writestr("Existing/file.txt", "updated")

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        str(archive_root),
        allow_overwrite=True,
    )
    target_path = plan.entries[0].target_path
    archive_path = plan.entries[0].archive_path
    assert archive_path is not None
    original_move_path = sandbox_installer_module._move_path

    def fake_move_path(source: Path, destination: Path) -> None:
        if source == target_path and destination == archive_path:
            raise PermissionError(
                32,
                "The process cannot access the file because it is being used by another process",
                str(source),
            )
        original_move_path(source, destination)

    monkeypatch.setattr(sandbox_installer_module, "_move_path", fake_move_path)

    with pytest.raises(AppShellError) as exc_info:
        service.execute_sandbox_install_plan(plan)

    exc = exc_info.value
    assert "Windows is still using files in the target mod folder" in str(exc)
    assert "Explorer windows or preview panes" in str(exc)
    assert exc.detail_message.startswith("Could not archive existing target before overwrite:")
    assert str(target_path) in exc.detail_message
    assert str(archive_path) in exc.detail_message
    assert "being used by another process" in exc.detail_message


def test_execute_real_mods_plan_with_approval_matches_review_and_executes(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox.mkdir()
    package = tmp_path / "single.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )
        archive.writestr("Mod/file.txt", "hello")

    plan = service.build_install_plan(
        package_path_text=str(package),
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox),
        real_archive_path_text="",
        sandbox_archive_path_text="",
        allow_overwrite=False,
        configured_real_mods_path=real_mods,
    )
    review = service.review_install_execution(plan)

    assert review.allowed is True
    assert review.requires_explicit_approval is True

    result = service.execute_sandbox_install_plan(
        plan,
        confirm_real_destination=True,
    )

    assert result.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert result.scan_context_path == real_mods


def test_build_mod_removal_plan_for_sandbox_destination(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "ToRemove", "Sample.Remove")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(sandbox_mods / "ToRemove"),
    )

    assert plan.destination_kind == SCAN_TARGET_SANDBOX_MODS
    assert plan.mods_path == sandbox_mods
    assert plan.archive_path == sandbox_archive
    assert plan.target_mod_path == sandbox_mods / "ToRemove"


def test_build_mod_removal_plan_for_real_destination_uses_real_archive_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    _create_mod(real_mods, "ToRemove", "Sample.Remove")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        mod_folder_path_text=str(real_mods / "ToRemove"),
    )

    assert plan.destination_kind == SCAN_TARGET_CONFIGURED_REAL_MODS
    assert plan.mods_path == real_mods
    assert plan.archive_path == real_archive
    assert plan.target_mod_path == real_mods / "ToRemove"


def test_execute_mod_removal_requires_explicit_confirmation(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "ToRemove", "Sample.Remove")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(sandbox_mods / "ToRemove"),
    )

    with pytest.raises(AppShellError, match="Explicit confirmation is required"):
        service.execute_mod_removal(plan, confirm_removal=False)


def test_execute_mod_removal_moves_sandbox_mod_to_archive_and_rescans(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "ToRemove", "Sample.Remove")
    _create_mod(sandbox_mods, "Keep", "Sample.Keep")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(sandbox_mods / "ToRemove"),
    )
    result = service.execute_mod_removal(plan, confirm_removal=True)

    assert result.destination_kind == SCAN_TARGET_SANDBOX_MODS
    assert result.removed_target == sandbox_mods / "ToRemove"
    assert not (sandbox_mods / "ToRemove").exists()
    assert result.archived_target.parent == sandbox_archive
    assert result.archived_target.exists()
    assert (result.archived_target / "manifest.json").exists()
    assert result.scan_context_path == sandbox_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Keep"}


def test_execute_mod_removal_moves_real_mod_to_archive_and_rescans(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    _create_mod(real_mods, "ToRemove", "Sample.Remove")
    _create_mod(real_mods, "Keep", "Sample.Keep")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        mod_folder_path_text=str(real_mods / "ToRemove"),
    )
    result = service.execute_mod_removal(plan, confirm_removal=True)

    assert result.destination_kind == SCAN_TARGET_CONFIGURED_REAL_MODS
    assert result.removed_target == real_mods / "ToRemove"
    assert not (real_mods / "ToRemove").exists()
    assert result.archived_target.parent == real_archive
    assert result.archived_target.exists()
    assert result.scan_context_path == real_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Keep"}


def test_execute_mod_removal_surfaces_lock_like_archive_failure_with_clear_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "ToRemove", "Sample.Remove")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(sandbox_mods / "ToRemove"),
    )
    original_move_path = sandbox_installer_module._move_path

    def fake_move_path(source: Path, destination: Path) -> None:
        if source == plan.target_mod_path:
            raise PermissionError(5, "Access is denied", str(source))
        original_move_path(source, destination)

    monkeypatch.setattr(sandbox_installer_module, "_move_path", fake_move_path)

    with pytest.raises(AppShellError) as exc_info:
        service.execute_mod_removal(plan, confirm_removal=True)

    exc = exc_info.value
    assert "Windows is still using files in the target mod folder" in str(exc)
    assert "editor or terminal" in str(exc)
    assert exc.detail_message.startswith("Could not move mod folder to archive:")
    assert str(plan.target_mod_path) in exc.detail_message
    assert "Access is denied" in exc.detail_message


def test_execute_mod_removal_keeps_non_lock_failures_honest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "ToRemove", "Sample.Remove")

    plan = service.build_mod_removal_plan(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(sandbox_mods / "ToRemove"),
    )

    def fake_move_path(_source: Path, _destination: Path) -> None:
        raise FileNotFoundError("archive volume disappeared")

    monkeypatch.setattr(sandbox_installer_module, "_move_path", fake_move_path)

    with pytest.raises(AppShellError) as exc_info:
        service.execute_mod_removal(plan, confirm_removal=True)

    exc = exc_info.value
    assert "Windows is still using files in the target mod folder" not in str(exc)
    assert str(exc).startswith("Could not move mod folder to archive:")
    assert "archive volume disappeared" in str(exc)
    assert exc.detail_message == str(exc)


def test_list_archived_entries_includes_real_archive_entries(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    archived = real_archive / "RealMod__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Real Mod","UniqueID":"Sample.RealArchived","Version":"2.1.0"}',
        encoding="utf-8",
    )

    entries = service.list_archived_entries(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
    )

    real_entries = [item for item in entries if item.source_kind == ARCHIVE_SOURCE_REAL]
    assert len(real_entries) == 1
    item = real_entries[0]
    assert item.archived_folder_name == "RealMod__sdvmm_archive_001"
    assert item.target_folder_name == "RealMod"
    assert item.mod_name == "Real Mod"
    assert item.unique_id == "Sample.RealArchived"
    assert item.version == "2.1.0"


def test_list_archived_entries_includes_sandbox_archive_entries(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    archived = sandbox_archive / "SandboxMod__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Sandbox Mod","UniqueID":"Sample.SandboxArchived","Version":"1.2.3"}',
        encoding="utf-8",
    )

    entries = service.list_archived_entries(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
    )

    sandbox_entries = [item for item in entries if item.source_kind == ARCHIVE_SOURCE_SANDBOX]
    assert len(sandbox_entries) == 1
    item = sandbox_entries[0]
    assert item.archived_folder_name == "SandboxMod__sdvmm_archive_001"
    assert item.target_folder_name == "SandboxMod"
    assert item.mod_name == "Sandbox Mod"
    assert item.unique_id == "Sample.SandboxArchived"
    assert item.version == "1.2.3"


def test_execute_archive_restore_requires_explicit_confirmation(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    archived = sandbox_archive / "RestoreMe__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Me","UniqueID":"Sample.RestoreMe","Version":"1.0.0"}',
        encoding="utf-8",
    )

    plan = service.build_archive_restore_plan(
        source_kind=ARCHIVE_SOURCE_SANDBOX,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
    )

    with pytest.raises(AppShellError, match="Explicit confirmation is required"):
        service.execute_archive_restore(plan, confirm_restore=False)


def test_execute_archive_restore_to_sandbox_moves_entry_and_rescans(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "Keep", "Sample.Keep")
    archived = sandbox_archive / "RestoreMe__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Me","UniqueID":"Sample.RestoreMe","Version":"1.0.0"}',
        encoding="utf-8",
    )

    plan = service.build_archive_restore_plan(
        source_kind=ARCHIVE_SOURCE_SANDBOX,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
    )
    result = service.execute_archive_restore(plan, confirm_restore=True)

    assert result.destination_kind == INSTALL_TARGET_SANDBOX_MODS
    assert result.restored_target == sandbox_mods / "RestoreMe"
    assert result.restored_target.exists()
    assert not archived.exists()
    assert result.scan_context_path == sandbox_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {
        "Sample.Keep",
        "Sample.RestoreMe",
    }


def test_execute_archive_restore_to_real_moves_entry_and_rescans(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    _create_mod(real_mods, "Keep", "Sample.Keep")
    archived = real_archive / "RestoreReal__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Real","UniqueID":"Sample.RestoreReal","Version":"3.0.0"}',
        encoding="utf-8",
    )

    plan = service.build_archive_restore_plan(
        source_kind=ARCHIVE_SOURCE_REAL,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
    )
    result = service.execute_archive_restore(plan, confirm_restore=True)

    assert result.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert result.restored_target == real_mods / "RestoreReal"
    assert result.restored_target.exists()
    assert not archived.exists()
    assert result.scan_context_path == real_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {
        "Sample.Keep",
        "Sample.RestoreReal",
    }


def test_execute_archive_delete_requires_explicit_confirmation(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    archived = sandbox_archive / "DeleteMe__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Delete Me","UniqueID":"Sample.DeleteMe","Version":"1.0.0"}',
        encoding="utf-8",
    )

    plan = service.build_archive_delete_plan(
        source_kind=ARCHIVE_SOURCE_SANDBOX,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
    )

    with pytest.raises(AppShellError, match="Explicit confirmation is required"):
        service.execute_archive_delete(plan, confirm_delete=False)


def test_execute_archive_delete_permanently_removes_real_archive_entry(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    archived = real_archive / "DeleteReal__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Delete Real","UniqueID":"Sample.DeleteReal","Version":"3.0.0"}',
        encoding="utf-8",
    )

    plan = service.build_archive_delete_plan(
        source_kind=ARCHIVE_SOURCE_REAL,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
    )
    result = service.execute_archive_delete(plan, confirm_delete=True)

    assert result.deleted_path == archived
    assert not archived.exists()


def test_execute_archive_delete_permanently_removes_sandbox_archive_entry(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    archived = sandbox_archive / "DeleteSandbox__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Delete Sandbox","UniqueID":"Sample.DeleteSandbox","Version":"2.0.0"}',
        encoding="utf-8",
    )

    plan = service.build_archive_delete_plan(
        source_kind=ARCHIVE_SOURCE_SANDBOX,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
    )
    result = service.execute_archive_delete(plan, confirm_delete=True)

    assert result.deleted_path == archived
    assert not archived.exists()


def test_archive_listing_reflects_permanent_delete_after_execution(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    archived_keep = real_archive / "Keep__sdvmm_archive_001"
    archived_delete = real_archive / "Delete__sdvmm_archive_001"
    _create_archived_entry(archived_keep, unique_id="Sample.KeepArchived", version="1.0.0")
    _create_archived_entry(archived_delete, unique_id="Sample.DeleteArchived", version="1.0.0")

    before = service.list_archived_entries(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
    )
    assert {entry.archived_path for entry in before} == {archived_keep, archived_delete}

    plan = service.build_archive_delete_plan(
        source_kind=ARCHIVE_SOURCE_REAL,
        archived_path_text=str(archived_delete),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
    )
    service.execute_archive_delete(plan, confirm_delete=True)

    after = service.list_archived_entries(
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
    )
    assert {entry.archived_path for entry in after} == {archived_keep}


def test_build_archive_restore_plan_inferrs_real_destination_even_if_saved_install_target_is_sandbox(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    archived = real_archive / "RestoreReal__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Real","UniqueID":"Sample.RestoreReal","Version":"3.0.0"}',
        encoding="utf-8",
    )
    existing_config = AppConfig(
        game_path=tmp_path / "Game",
        mods_path=real_mods,
        app_data_path=tmp_path / "appdata",
        sandbox_mods_path=sandbox_mods,
        real_archive_path=real_archive,
        install_target=INSTALL_TARGET_SANDBOX_MODS,
    )

    plan = service.build_archive_restore_plan(
        source_kind=ARCHIVE_SOURCE_REAL,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        existing_config=existing_config,
    )

    assert plan.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert plan.destination_mods_path == real_mods
    assert plan.destination_target_path == real_mods / "RestoreReal"


def test_build_archive_restore_plan_inferrs_sandbox_destination_even_if_saved_install_target_is_real(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    archived = sandbox_archive / "RestoreSandbox__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Sandbox","UniqueID":"Sample.RestoreSandbox","Version":"1.0.0"}',
        encoding="utf-8",
    )
    existing_config = AppConfig(
        game_path=tmp_path / "Game",
        mods_path=real_mods,
        app_data_path=tmp_path / "appdata",
        sandbox_mods_path=sandbox_mods,
        sandbox_archive_path=sandbox_archive,
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
    )

    plan = service.build_archive_restore_plan(
        source_kind=ARCHIVE_SOURCE_SANDBOX,
        archived_path_text=str(archived),
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        existing_config=existing_config,
    )

    assert plan.destination_kind == INSTALL_TARGET_SANDBOX_MODS
    assert plan.destination_mods_path == sandbox_mods
    assert plan.destination_target_path == sandbox_mods / "RestoreSandbox"


def test_build_archive_restore_plan_blocks_when_restore_target_exists(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    archived = real_archive / "RestoreReal__sdvmm_archive_001"
    archived.mkdir()
    (archived / "manifest.json").write_text(
        '{"Name":"Restore Real","UniqueID":"Sample.RestoreReal","Version":"3.0.0"}',
        encoding="utf-8",
    )
    _create_mod(real_mods, "RestoreReal", "Sample.Existing")

    with pytest.raises(AppShellError, match="Restore target already exists"):
        service.build_archive_restore_plan(
            source_kind=ARCHIVE_SOURCE_REAL,
            archived_path_text=str(archived),
            configured_mods_path_text=str(real_mods),
            sandbox_mods_path_text=str(sandbox_mods),
            real_archive_path_text=str(real_archive),
            sandbox_archive_path_text="",
        )


def test_list_mod_rollback_candidates_matches_real_destination_by_unique_id_and_folder(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()

    _create_mod(real_mods, "SampleMod", "Sample.Mod")
    _create_archived_entry(
        real_archive / "SampleMod__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="1.0.0",
    )
    _create_archived_entry(
        real_archive / "OtherFolder__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="0.9.0",
    )
    _create_archived_entry(
        real_archive / "SampleMod__sdvmm_archive_002",
        unique_id="Different.Mod",
        version="1.0.0",
    )
    existing_config = AppConfig(
        game_path=tmp_path / "Game",
        mods_path=real_mods,
        app_data_path=tmp_path / "AppData",
        sandbox_mods_path=sandbox_mods,
        install_target=INSTALL_TARGET_SANDBOX_MODS,
    )

    candidates = service.list_mod_rollback_candidates(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        mod_folder_path_text=str(real_mods / "SampleMod"),
        mod_unique_id_text="Sample.Mod",
        existing_config=existing_config,
    )

    assert len(candidates) == 1
    assert candidates[0].archived_path == real_archive / "SampleMod__sdvmm_archive_001"


def test_list_mod_rollback_candidates_matches_sandbox_destination_by_unique_id_and_folder(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()

    _create_mod(sandbox_mods, "SampleMod", "Sample.Mod")
    _create_archived_entry(
        sandbox_archive / "SampleMod__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="1.0.0",
    )
    _create_archived_entry(
        sandbox_archive / "SampleMod__sdvmm_archive_002",
        unique_id="Different.Mod",
        version="1.0.0",
    )
    existing_config = AppConfig(
        game_path=tmp_path / "Game",
        mods_path=real_mods,
        app_data_path=tmp_path / "AppData",
        sandbox_mods_path=sandbox_mods,
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
    )

    candidates = service.list_mod_rollback_candidates(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(sandbox_mods / "SampleMod"),
        mod_unique_id_text="Sample.Mod",
        existing_config=existing_config,
    )

    assert len(candidates) == 1
    assert candidates[0].archived_path == sandbox_archive / "SampleMod__sdvmm_archive_001"


def test_execute_mod_rollback_requires_explicit_confirmation(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    _create_mod(real_mods, "SampleMod", "Sample.Mod")
    candidate = _create_archived_entry(
        real_archive / "SampleMod__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="1.0.0",
    )

    plan = service.build_mod_rollback_plan(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        mod_folder_path_text=str(real_mods / "SampleMod"),
        mod_unique_id_text="Sample.Mod",
        mod_version_text="2.0.0",
        archived_candidate_path_text=str(candidate),
    )

    with pytest.raises(AppShellError, match="Explicit confirmation is required"):
        service.execute_mod_rollback(plan, confirm_rollback=False)


def test_execute_mod_rollback_archives_current_then_restores_archived_version_and_rescans(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_archive = tmp_path / "RealArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    real_archive.mkdir()
    current = _create_mod(real_mods, "SampleMod", "Sample.Mod")
    (current / "version-marker.txt").write_text("current-2.0.0", encoding="utf-8")
    candidate = _create_archived_entry(
        real_archive / "SampleMod__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="1.0.0",
    )
    (candidate / "version-marker.txt").write_text("archived-1.0.0", encoding="utf-8")
    _create_mod(real_mods, "Keep", "Sample.Keep")

    plan = service.build_mod_rollback_plan(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(real_archive),
        sandbox_archive_path_text="",
        mod_folder_path_text=str(current),
        mod_unique_id_text="Sample.Mod",
        mod_version_text="2.0.0",
        archived_candidate_path_text=str(candidate),
    )
    result = service.execute_mod_rollback(plan, confirm_rollback=True)

    assert result.destination_kind == SCAN_TARGET_CONFIGURED_REAL_MODS
    assert result.archived_current_target.parent == real_archive
    assert result.archived_current_target.exists()
    assert (result.archived_current_target / "version-marker.txt").read_text(encoding="utf-8") == "current-2.0.0"
    assert result.restored_target == current
    assert (result.restored_target / "version-marker.txt").read_text(encoding="utf-8") == "archived-1.0.0"
    assert result.scan_context_path == real_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Mod", "Sample.Keep"}


def test_execute_mod_rollback_for_sandbox_destination_rescans_sandbox(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = tmp_path / "SandboxArchive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    current = _create_mod(sandbox_mods, "SampleMod", "Sample.Mod")
    candidate = _create_archived_entry(
        sandbox_archive / "SampleMod__sdvmm_archive_001",
        unique_id="Sample.Mod",
        version="1.0.0",
    )
    _create_mod(sandbox_mods, "Keep", "Sample.Keep")

    plan = service.build_mod_rollback_plan(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text="",
        sandbox_archive_path_text=str(sandbox_archive),
        mod_folder_path_text=str(current),
        mod_unique_id_text="Sample.Mod",
        mod_version_text="2.0.0",
        archived_candidate_path_text=str(candidate),
    )
    result = service.execute_mod_rollback(plan, confirm_rollback=True)

    assert result.destination_kind == SCAN_TARGET_SANDBOX_MODS
    assert result.scan_context_path == sandbox_mods
    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Mod", "Sample.Keep"}


def test_build_install_plan_blocks_real_destination_mismatch(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    configured_real_mods = tmp_path / "ConfiguredRealMods"
    different_mods = tmp_path / "DifferentMods"
    sandbox = tmp_path / "SandboxMods"
    configured_real_mods.mkdir()
    different_mods.mkdir()
    sandbox.mkdir()

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="must exactly match the configured real Mods path"):
        service.build_install_plan(
            package_path_text=str(package),
            install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
            configured_mods_path_text=str(different_mods),
            sandbox_mods_path_text=str(sandbox),
            real_archive_path_text="",
            sandbox_archive_path_text="",
            allow_overwrite=False,
            configured_real_mods_path=configured_real_mods,
        )


def test_build_install_plan_blocks_archive_inside_real_mods_tree(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="must be outside the active Mods directory"):
        service.build_install_plan(
            package_path_text=str(package),
            install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
            configured_mods_path_text=str(real_mods),
            sandbox_mods_path_text=str(sandbox_mods),
            real_archive_path_text=str(real_mods / ".sdvmm-archive"),
            sandbox_archive_path_text="",
            allow_overwrite=True,
            configured_real_mods_path=real_mods,
        )


def test_build_install_plan_blocks_archive_inside_sandbox_mods_tree(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    with pytest.raises(AppShellError, match="must be outside the active Mods directory"):
        service.build_install_plan(
            package_path_text=str(package),
            install_target=INSTALL_TARGET_SANDBOX_MODS,
            configured_mods_path_text=str(real_mods),
            sandbox_mods_path_text=str(sandbox_mods),
            real_archive_path_text="",
            sandbox_archive_path_text=str(sandbox_mods / ".sdvmm-archive"),
            allow_overwrite=True,
            configured_real_mods_path=real_mods,
        )


def test_scan_with_target_excludes_configured_archive_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    archive_root = real_mods / ".sdvmm-archive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    archive_root.mkdir()
    _create_mod(real_mods, "Visible", "Sample.Visible")
    _create_mod(archive_root, "Archived", "Sample.Archived")

    result = service.scan_with_target(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        real_archive_path_text=str(archive_root),
    )

    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Visible"}


def test_scan_with_target_excludes_legacy_archive_path_by_default(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    archive_root = real_mods / ".sdvmm-archive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    archive_root.mkdir()
    _create_mod(real_mods, "Visible", "Sample.Visible")
    _create_mod(archive_root, "Archived", "Sample.Archived")

    result = service.scan_with_target(
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
    )

    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Visible"}


def test_scan_with_target_excludes_sandbox_archive_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    sandbox_archive = sandbox_mods / ".sdvmm-archive"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    sandbox_archive.mkdir()
    _create_mod(sandbox_mods, "Visible", "Sample.Visible")
    _create_mod(sandbox_archive, "Archived", "Sample.Archived")

    result = service.scan_with_target(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(real_mods),
        sandbox_mods_path_text=str(sandbox_mods),
        sandbox_archive_path_text=str(sandbox_archive),
    )

    assert {mod.unique_id for mod in result.inventory.mods} == {"Sample.Visible"}


def test_build_sandbox_install_plan_includes_dependency_preflight_warnings(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    sandbox.mkdir()
    archive_root.mkdir()
    package = tmp_path / "missing_dep.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "NeedsDep/manifest.json",
            (
                "{"
                '"Name":"NeedsDep",'
                '"UniqueID":"Pkg.NeedsDep",'
                '"Version":"1.0.0",'
                '"Dependencies":[{"UniqueID":"Pkg.Required","IsRequired":true}]'
                "}"
            ),
        )

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        str(archive_root),
        allow_overwrite=False,
    )

    assert len(plan.entries) == 1
    assert plan.entries[0].can_install is False
    assert plan.entries[0].action == "blocked"
    assert any("Missing required dependencies" in item for item in plan.entries[0].warnings)
    assert any("missing required dependency" in item.casefold() for item in plan.plan_warnings)
    assert any(
        finding.state == "missing_required_dependency"
        for finding in plan.dependency_findings
    )


def test_build_sandbox_install_plan_satisfies_content_pack_for_when_provider_exists(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    sandbox.mkdir()
    archive_root.mkdir()
    provider = sandbox / "ContentPatcher"
    provider.mkdir()
    (provider / "manifest.json").write_text(
        '{"Name":"Content Patcher","UniqueID":"Pathoschild.ContentPatcher","Version":"2.0.0"}',
        encoding="utf-8",
    )

    package = tmp_path / "cp_pack.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "[CP] Pack/manifest.json",
            (
                "{"
                '"Name":"CP Pack",'
                '"UniqueID":"Sample.ContentPack",'
                '"Version":"1.0.0",'
                '"ContentPackFor":{"UniqueID":"Pathoschild.ContentPatcher"}'
                "}"
            ),
        )

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        str(archive_root),
        allow_overwrite=False,
    )

    assert len(plan.entries) == 1
    assert plan.entries[0].can_install is True
    assert not any("Missing required dependencies" in item for item in plan.entries[0].warnings)
    assert any(
        finding.dependency_unique_id == "Pathoschild.ContentPatcher"
        and finding.state == "satisfied"
        for finding in plan.dependency_findings
    )


def test_build_and_execute_sandbox_install_plan(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    sandbox.mkdir()
    archive_root.mkdir()
    package = tmp_path / "single.zip"

    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )
        archive.writestr("Mod/file.txt", "hello")

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        str(archive_root),
        allow_overwrite=False,
    )
    result = service.execute_sandbox_install_plan(plan)

    assert len(result.installed_targets) == 1
    assert result.installed_targets[0] == sandbox / "Mod"
    assert result.archived_targets == ()
    assert result.scan_context_path == sandbox
    assert (sandbox / "Mod" / "file.txt").read_text(encoding="utf-8") == "hello"
    assert len(result.inventory.mods) == 1

    history = service.load_install_operation_history()
    assert len(history.operations) == 1
    operation = history.operations[0]
    assert operation.operation_id is not None
    assert operation.package_path == package
    assert operation.destination_kind == INSTALL_TARGET_SANDBOX_MODS
    assert operation.destination_mods_path == sandbox
    assert operation.archive_path == archive_root
    assert operation.installed_targets == result.installed_targets
    assert operation.archived_targets == result.archived_targets
    assert operation.timestamp.endswith("Z")
    assert len(operation.entries) == 1
    assert operation.entries[0].action == "install_new"
    assert operation.entries[0].target_path == sandbox / "Mod"

    follow_up_scan = service.scan_with_target(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(tmp_path / "ConfiguredMods"),
        sandbox_mods_path_text=str(sandbox),
    )
    assert follow_up_scan.scan_path == result.scan_context_path


def test_load_install_operation_history_returns_preexisting_records(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")
    operation = InstallOperationRecord(
        operation_id="install_existing",
        timestamp="2026-03-13T12:00:00Z",
        package_path=tmp_path / "Downloads" / "sample.zip",
        destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        destination_mods_path=tmp_path / "RealMods",
        archive_path=tmp_path / "RealArchive",
        installed_targets=(tmp_path / "RealMods" / "SampleMod",),
        archived_targets=(tmp_path / "RealArchive" / "SampleMod-old",),
        entries=(
            InstallOperationEntryRecord(
                name="Sample Mod",
                unique_id="Sample.Mod",
                version="2.0.0",
                action="overwrite_with_archive",
                target_path=tmp_path / "RealMods" / "SampleMod",
                archive_path=tmp_path / "RealArchive" / "SampleMod-old",
                source_manifest_path=r"C:\package\SampleMod\manifest.json",
                source_root_path=r"C:\package\SampleMod",
                target_exists_before=True,
                can_install=True,
                warnings=("Archived previous version before overwrite.",),
            ),
        ),
    )
    shell_service_module.append_install_operation_record(
        shell_service_module.install_operation_history_file(service.state_file),
        operation,
    )

    history = service.load_install_operation_history()

    assert history.operations == (operation,)


def test_load_recovery_execution_history_returns_preexisting_records(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")
    operation = shell_service_module.RecoveryExecutionRecord(
        recovery_execution_id="recovery_existing",
        timestamp="2026-03-13T15:00:00Z",
        related_install_operation_id="install_existing",
        related_install_operation_timestamp="2026-03-13T12:00:00Z",
        related_install_package_path=tmp_path / "Downloads" / "sample.zip",
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        destination_mods_path=tmp_path / "SandboxMods",
        executed_entry_count=1,
        removed_target_paths=(tmp_path / "SandboxMods" / "SampleMod",),
        restored_target_paths=tuple(),
        outcome_status="completed",
        failure_message=None,
    )
    shell_service_module.append_recovery_execution_record(
        shell_service_module.recovery_execution_history_file(service.state_file),
        operation,
    )

    history = service.load_recovery_execution_history()

    assert history.operations == (operation,)


def test_inspect_install_recovery_by_operation_id_returns_composed_result(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="New Mod",
                unique_id="Sample.New",
                action=INSTALL_NEW,
            ),
        ),
    )
    shell_service_module.append_install_operation_record(
        shell_service_module.install_operation_history_file(service.state_file),
        operation,
    )
    linked_record = shell_service_module.RecoveryExecutionRecord(
        recovery_execution_id="recovery_linked",
        timestamp="2026-03-13T15:00:00Z",
        related_install_operation_id=operation.operation_id,
        related_install_operation_timestamp=operation.timestamp,
        related_install_package_path=operation.package_path,
        destination_kind=operation.destination_kind,
        destination_mods_path=operation.destination_mods_path,
        executed_entry_count=1,
        removed_target_paths=(operation.entries[0].target_path,),
        restored_target_paths=tuple(),
        outcome_status="completed",
        failure_message=None,
    )
    unrelated_record = shell_service_module.RecoveryExecutionRecord(
        recovery_execution_id="recovery_unrelated",
        timestamp="2026-03-13T16:00:00Z",
        related_install_operation_id="install_other",
        related_install_operation_timestamp="2026-03-13T14:00:00Z",
        related_install_package_path=tmp_path / "Downloads" / "other.zip",
        destination_kind=operation.destination_kind,
        destination_mods_path=operation.destination_mods_path,
        executed_entry_count=0,
        removed_target_paths=tuple(),
        restored_target_paths=tuple(),
        outcome_status="failed",
        failure_message="other",
    )
    shell_service_module.append_recovery_execution_record(
        shell_service_module.recovery_execution_history_file(service.state_file),
        linked_record,
    )
    shell_service_module.append_recovery_execution_record(
        shell_service_module.recovery_execution_history_file(service.state_file),
        unrelated_record,
    )

    inspection = service.inspect_install_recovery_by_operation_id(operation.operation_id or "")

    assert inspection.operation == operation
    assert inspection.recovery_plan.operation == operation
    assert inspection.recovery_review.plan == inspection.recovery_plan
    assert inspection.recovery_plan.summary.total_recovery_entry_count == 1
    assert inspection.recovery_review.summary.total_entry_count == 1
    assert inspection.linked_recovery_history == (linked_record,)


def test_inspect_install_recovery_by_operation_id_fails_for_missing_id(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")

    with pytest.raises(AppShellError, match="Install operation ID not found"):
        service.inspect_install_recovery_by_operation_id("install_missing")


def test_inspect_install_recovery_by_operation_id_ignores_legacy_records_without_ids(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "state" / "app-state.json")
    legacy_operation = InstallOperationRecord(
        operation_id=None,
        timestamp="2026-03-13T12:00:00Z",
        package_path=tmp_path / "Downloads" / "legacy.zip",
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        destination_mods_path=tmp_path / "SandboxMods",
        archive_path=tmp_path / "SandboxArchive",
        installed_targets=(tmp_path / "SandboxMods" / "LegacyMod",),
        archived_targets=tuple(),
        entries=(
            InstallOperationEntryRecord(
                name="Legacy Mod",
                unique_id="Sample.Legacy",
                version="1.0.0",
                action=INSTALL_NEW,
                target_path=tmp_path / "SandboxMods" / "LegacyMod",
                archive_path=None,
                source_manifest_path=r"C:\package\LegacyMod\manifest.json",
                source_root_path=r"C:\package\LegacyMod",
                target_exists_before=False,
                can_install=True,
                warnings=tuple(),
            ),
        ),
    )
    shell_service_module.append_install_operation_record(
        shell_service_module.install_operation_history_file(service.state_file),
        legacy_operation,
    )

    with pytest.raises(AppShellError, match="Install operation ID not found"):
        service.inspect_install_recovery_by_operation_id("install_legacy_missing")


def test_derive_install_operation_recovery_plan_maps_install_new_to_remove_action(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="New Mod",
                unique_id="Sample.New",
                action=INSTALL_NEW,
            ),
        ),
    )

    plan = service.derive_install_operation_recovery_plan(operation)

    assert plan.summary.total_recovery_entry_count == 1
    assert plan.summary.recoverable_entry_count == 1
    assert plan.summary.non_recoverable_entry_count == 0
    assert plan.summary.involves_archive_restore is False
    assert plan.summary.warnings == tuple()
    assert plan.entries[0].action == "remove_installed_target"
    assert plan.entries[0].recoverable is True
    assert "Remove installed target" in plan.entries[0].message


def test_derive_install_operation_recovery_plan_maps_overwrite_to_restore_from_archive(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    archive_path = tmp_path / "Archive" / "Existing Mod-old"
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                archive_path=archive_path,
            ),
        ),
        archived_targets=(archive_path,),
    )

    plan = service.derive_install_operation_recovery_plan(operation)

    assert plan.summary.total_recovery_entry_count == 1
    assert plan.summary.recoverable_entry_count == 1
    assert plan.summary.non_recoverable_entry_count == 0
    assert plan.summary.involves_archive_restore is True
    assert plan.entries[0].action == "restore_from_archive"
    assert plan.entries[0].recoverable is True
    assert plan.entries[0].archive_path == archive_path
    assert "Restore archived target" in plan.entries[0].message


def test_derive_install_operation_recovery_plan_reports_mixed_counts_and_warnings(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    archive_path = tmp_path / "Archive" / "Existing Mod-old"
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="New Mod",
                unique_id="Sample.New",
                action=INSTALL_NEW,
            ),
            _install_operation_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                archive_path=archive_path,
            ),
            _install_operation_entry(
                tmp_path,
                name="Unsupported Mod",
                unique_id="Sample.Blocked",
                action=BLOCKED,
                can_install=False,
                warnings=("Dependency missing.",),
            ),
        ),
        archived_targets=(archive_path,),
    )

    plan = service.derive_install_operation_recovery_plan(operation)

    assert plan.summary.total_recovery_entry_count == 3
    assert plan.summary.recoverable_entry_count == 2
    assert plan.summary.non_recoverable_entry_count == 1
    assert plan.summary.involves_archive_restore is True
    assert len(plan.summary.warnings) == 1
    assert "Unsupported Mod is not safely recoverable" in plan.summary.warnings[0]


def test_derive_install_operation_recovery_plan_marks_unsupported_cases_non_recoverable(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    missing_archive = tmp_path / "Archive" / "Missing-old"
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="Untracked Overwrite",
                unique_id="Sample.MissingArchive",
                action=OVERWRITE_WITH_ARCHIVE,
                archive_path=missing_archive,
            ),
        ),
        archived_targets=tuple(),
    )

    plan = service.derive_install_operation_recovery_plan(operation)

    assert plan.summary.total_recovery_entry_count == 1
    assert plan.summary.recoverable_entry_count == 0
    assert plan.summary.non_recoverable_entry_count == 1
    assert plan.summary.involves_archive_restore is False
    assert plan.entries[0].action == "not_recoverable"
    assert plan.entries[0].recoverable is False
    assert "cannot be matched for restoration" in plan.entries[0].message


def test_review_install_recovery_execution_allows_existing_remove_target(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="New Mod",
                unique_id="Sample.New",
                action=INSTALL_NEW,
            ),
        ),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)
    recovery_plan.entries[0].target_path.mkdir(parents=True, exist_ok=True)

    review = service.review_install_recovery_execution(recovery_plan)

    assert review.allowed is True
    assert review.decision_code == "recovery_ready"
    assert review.summary.total_entry_count == 1
    assert review.summary.executable_entry_count == 1
    assert review.summary.non_executable_entry_count == 0
    assert review.summary.stale_entry_count == 0
    assert review.entries[0].decision_code == "removal_ready"
    assert review.entries[0].executable is True


def test_review_install_recovery_execution_marks_missing_remove_target_stale(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="Missing Mod",
                unique_id="Sample.Missing",
                action=INSTALL_NEW,
            ),
        ),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)

    review = service.review_install_recovery_execution(recovery_plan)

    assert review.allowed is False
    assert review.decision_code == "recovery_blocked"
    assert review.summary.executable_entry_count == 0
    assert review.summary.non_executable_entry_count == 1
    assert review.summary.stale_entry_count == 1
    assert review.entries[0].decision_code == "removal_target_missing"
    assert "Removal target is missing" in review.entries[0].message


def test_review_install_recovery_execution_allows_existing_archive_restore_source(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    archive_path = tmp_path / "Archive" / "Existing Mod-old"
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                archive_path=archive_path,
            ),
        ),
        archived_targets=(archive_path,),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)
    archive_path.mkdir(parents=True, exist_ok=True)

    review = service.review_install_recovery_execution(recovery_plan)

    assert review.allowed is True
    assert review.summary.executable_entry_count == 1
    assert review.summary.non_executable_entry_count == 0
    assert review.summary.stale_entry_count == 0
    assert review.summary.involves_archive_restore is True
    assert review.entries[0].decision_code == "restore_ready"
    assert review.entries[0].executable is True


def test_review_install_recovery_execution_marks_missing_archive_restore_source_stale(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    archive_path = tmp_path / "Archive" / "Missing-old"
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                archive_path=archive_path,
            ),
        ),
        archived_targets=(archive_path,),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)

    review = service.review_install_recovery_execution(recovery_plan)

    assert review.allowed is False
    assert review.summary.executable_entry_count == 0
    assert review.summary.non_executable_entry_count == 1
    assert review.summary.stale_entry_count == 1
    assert review.entries[0].decision_code == "restore_archive_missing"
    assert "Archive source is missing" in review.entries[0].message


def test_review_install_recovery_execution_reports_mixed_counts_and_blocked_state(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    archive_path = tmp_path / "Archive" / "Existing Mod-old"
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="New Mod",
                unique_id="Sample.New",
                action=INSTALL_NEW,
            ),
            _install_operation_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                archive_path=archive_path,
            ),
            _install_operation_entry(
                tmp_path,
                name="Unsupported Mod",
                unique_id="Sample.Unsupported",
                action=BLOCKED,
                can_install=False,
                warnings=("Dependency missing.",),
            ),
        ),
        archived_targets=(archive_path,),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)
    recovery_plan.entries[0].target_path.mkdir(parents=True, exist_ok=True)

    review = service.review_install_recovery_execution(recovery_plan)

    assert review.allowed is False
    assert review.decision_code == "recovery_blocked"
    assert review.summary.total_entry_count == 3
    assert review.summary.executable_entry_count == 1
    assert review.summary.non_executable_entry_count == 2
    assert review.summary.stale_entry_count == 1
    assert review.summary.involves_archive_restore is False
    assert len(review.summary.warnings) == 2
    assert any("Archive source is missing" in warning for warning in review.summary.warnings)
    assert any("not safely recoverable" in warning for warning in review.summary.warnings)


def test_execute_install_recovery_review_blocks_when_review_not_allowed(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="Missing Mod",
                unique_id="Sample.Missing",
                action=INSTALL_NEW,
            ),
        ),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)
    review = service.review_install_recovery_execution(recovery_plan)

    with pytest.raises(AppShellError, match=re.escape(review.message)):
        service.execute_install_recovery_review(review)

    history = service.load_recovery_execution_history()
    assert len(history.operations) == 1
    assert history.operations[0].recovery_execution_id is not None
    assert history.operations[0].related_install_operation_id == operation.operation_id
    assert history.operations[0].outcome_status == "failed"
    assert history.operations[0].executed_entry_count == 0
    assert history.operations[0].failure_message == review.message


def test_execute_install_recovery_review_keeps_blocked_no_op_recording_best_effort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="Missing Mod",
                unique_id="Sample.Missing",
                action=INSTALL_NEW,
            ),
        ),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)
    review = service.review_install_recovery_execution(recovery_plan)
    monkeypatch.setattr(
        shell_service_module,
        "append_recovery_execution_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AppStateStoreError("disk full")),
    )

    with pytest.raises(AppShellError, match=re.escape(review.message)):
        service.execute_install_recovery_review(review)

    assert service.load_recovery_execution_history().operations == tuple()


def test_execute_install_recovery_review_removes_existing_target(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    destination_mods = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    destination_mods.mkdir()
    archive_root.mkdir()
    target_path = _create_mod(destination_mods, "New Mod", "Sample.New")
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="New Mod",
                unique_id="Sample.New",
                action=INSTALL_NEW,
            ),
        ),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)
    review = service.review_install_recovery_execution(recovery_plan)

    result = service.execute_install_recovery_review(review)

    assert result.executed_entry_count == 1
    assert result.removed_target_paths == (target_path,)
    assert result.restored_target_paths == tuple()
    assert result.destination_kind == INSTALL_TARGET_SANDBOX_MODS
    assert result.destination_mods_path == destination_mods
    assert result.scan_context_path == destination_mods
    assert target_path.exists() is False
    assert len(result.inventory.mods) == 0

    history = service.load_recovery_execution_history()
    assert len(history.operations) == 1
    assert history.operations[0].recovery_execution_id is not None
    assert history.operations[0].related_install_operation_id == operation.operation_id
    assert history.operations[0].related_install_operation_timestamp == operation.timestamp
    assert history.operations[0].related_install_package_path == operation.package_path
    assert history.operations[0].outcome_status == "completed"
    assert history.operations[0].executed_entry_count == 1
    assert history.operations[0].removed_target_paths == (target_path,)
    assert history.operations[0].restored_target_paths == tuple()
    assert history.operations[0].failure_message is None


def test_execute_install_recovery_review_surfaces_completed_recording_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    destination_mods = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    destination_mods.mkdir()
    archive_root.mkdir()
    target_path = _create_mod(destination_mods, "New Mod", "Sample.New")
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="New Mod",
                unique_id="Sample.New",
                action=INSTALL_NEW,
            ),
        ),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)
    review = service.review_install_recovery_execution(recovery_plan)
    monkeypatch.setattr(
        shell_service_module,
        "append_recovery_execution_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AppStateStoreError("disk full")),
    )

    with pytest.raises(AppShellError, match="Recovery completed, but recording recovery history failed"):
        service.execute_install_recovery_review(review)

    assert target_path.exists() is False
    assert service.load_recovery_execution_history().operations == tuple()


def test_execute_install_recovery_review_restores_existing_archive_source(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    destination_mods = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    destination_mods.mkdir()
    archive_root.mkdir()
    archived_path = _create_archived_entry(
        archive_root / "Existing Mod__sdvmm_archive_001",
        unique_id="Sample.Exists",
        version="1.0.0",
    )
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                archive_path=archived_path,
            ),
        ),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)
    review = service.review_install_recovery_execution(recovery_plan)

    result = service.execute_install_recovery_review(review)

    restored_target = destination_mods / "Existing Mod"
    assert result.executed_entry_count == 1
    assert result.removed_target_paths == tuple()
    assert result.restored_target_paths == (restored_target,)
    assert restored_target.exists() is True
    assert archived_path.exists() is False
    assert len(result.inventory.mods) == 1
    assert result.inventory.mods[0].unique_id == "Sample.Exists"

    history = service.load_recovery_execution_history()
    assert len(history.operations) == 1
    assert history.operations[0].recovery_execution_id is not None
    assert history.operations[0].related_install_operation_id == operation.operation_id
    assert history.operations[0].outcome_status == "completed"
    assert history.operations[0].executed_entry_count == 1
    assert history.operations[0].restored_target_paths == (restored_target,)


def test_execute_install_recovery_review_runs_mixed_executable_plan(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    destination_mods = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    destination_mods.mkdir()
    archive_root.mkdir()
    removable_target = _create_mod(destination_mods, "New Mod", "Sample.New")
    archived_path = _create_archived_entry(
        archive_root / "Existing Mod__sdvmm_archive_001",
        unique_id="Sample.Exists",
        version="1.0.0",
    )
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="New Mod",
                unique_id="Sample.New",
                action=INSTALL_NEW,
            ),
            _install_operation_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                archive_path=archived_path,
            ),
        ),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)
    review = service.review_install_recovery_execution(recovery_plan)

    result = service.execute_install_recovery_review(review)

    restored_target = destination_mods / "Existing Mod"
    assert result.executed_entry_count == 2
    assert result.removed_target_paths == (removable_target,)
    assert result.restored_target_paths == (restored_target,)
    assert result.destination_kind == INSTALL_TARGET_SANDBOX_MODS
    assert result.destination_mods_path == destination_mods
    assert removable_target.exists() is False
    assert restored_target.exists() is True
    assert len(result.inventory.mods) == 1
    assert result.inventory.mods[0].unique_id == "Sample.Exists"


def test_execute_install_recovery_review_records_partial_failure_after_first_action(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    destination_mods = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    destination_mods.mkdir()
    archive_root.mkdir()
    removable_target = _create_mod(destination_mods, "New Mod", "Sample.New")
    archived_path = _create_archived_entry(
        archive_root / "Existing Mod__sdvmm_archive_001",
        unique_id="Sample.Exists",
        version="1.0.0",
    )
    _create_mod(destination_mods, "Existing Mod", "Sample.DestinationConflict")
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="New Mod",
                unique_id="Sample.New",
                action=INSTALL_NEW,
            ),
            _install_operation_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                archive_path=archived_path,
            ),
        ),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)
    review = service.review_install_recovery_execution(recovery_plan)

    with pytest.raises(AppShellError, match="Restore target already exists"):
        service.execute_install_recovery_review(review)

    history = service.load_recovery_execution_history()
    assert len(history.operations) == 1
    assert history.operations[0].recovery_execution_id is not None
    assert history.operations[0].related_install_operation_id == operation.operation_id
    assert history.operations[0].outcome_status == "failed_partial"
    assert history.operations[0].executed_entry_count == 1
    assert history.operations[0].removed_target_paths == (removable_target,)
    assert history.operations[0].restored_target_paths == tuple()
    assert history.operations[0].failure_message is not None
    assert "Restore target already exists" in history.operations[0].failure_message


def test_execute_install_recovery_review_surfaces_partial_change_recording_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    destination_mods = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    destination_mods.mkdir()
    archive_root.mkdir()
    removable_target = _create_mod(destination_mods, "New Mod", "Sample.New")
    archived_path = _create_archived_entry(
        archive_root / "Existing Mod__sdvmm_archive_001",
        unique_id="Sample.Exists",
        version="1.0.0",
    )
    _create_mod(destination_mods, "Existing Mod", "Sample.DestinationConflict")
    operation = _install_operation_record(
        tmp_path,
        entries=(
            _install_operation_entry(
                tmp_path,
                name="New Mod",
                unique_id="Sample.New",
                action=INSTALL_NEW,
            ),
            _install_operation_entry(
                tmp_path,
                name="Existing Mod",
                unique_id="Sample.Exists",
                action=OVERWRITE_WITH_ARCHIVE,
                archive_path=archived_path,
            ),
        ),
    )
    recovery_plan = service.derive_install_operation_recovery_plan(operation)
    review = service.review_install_recovery_execution(recovery_plan)
    monkeypatch.setattr(
        shell_service_module,
        "append_recovery_execution_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AppStateStoreError("disk full")),
    )

    with pytest.raises(
        AppShellError,
        match="Recovery failed after filesystem changes, and recording recovery history also failed",
    ):
        service.execute_install_recovery_review(review)

    assert removable_target.exists() is False
    assert archived_path.exists() is True
    assert service.load_recovery_execution_history().operations == tuple()


def test_build_sandbox_plan_defaults_archive_path_when_empty(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    sandbox = tmp_path / "SandboxMods"
    sandbox.mkdir()
    (sandbox / "Mod").mkdir()

    package = tmp_path / "single.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    plan = service.build_sandbox_install_plan(
        str(package),
        str(sandbox),
        "",
        allow_overwrite=True,
    )

    assert plan.sandbox_archive_path == sandbox.parent / ".sdvmm-sandbox-archive"
    assert plan.entries[0].archive_path == (
        sandbox.parent / ".sdvmm-sandbox-archive" / "Mod__sdvmm_archive_001"
    )


def test_check_updates_returns_no_remote_link_for_unlinked_mod(tmp_path: Path, mods_case_path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    inventory = service.scan(str(mods_case_path("valid_manifest")))

    report = service.check_updates(inventory)

    assert len(report.statuses) == 1
    assert report.statuses[0].state == "no_remote_link"
    assert report.statuses[0].remote_link is None


def test_check_updates_marks_metadata_unavailable_for_nexus_link(
    tmp_path: Path,
    mods_case_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SDVMM_NEXUS_API_KEY", raising=False)
    service = AppShellService(state_file=tmp_path / "app-state.json")
    inventory = service.scan(str(mods_case_path("update_keys_manifest")))

    report = service.check_updates(inventory)

    assert len(report.statuses) == 1
    assert report.statuses[0].state == "metadata_unavailable"
    assert report.statuses[0].remote_link is not None
    assert report.statuses[0].remote_link.provider == "nexus"
    assert "[missing_api_key]" in (report.statuses[0].message or "")


def test_check_updates_passes_resolved_nexus_key_to_metadata_service(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    inventory = _empty_inventory()
    captured: dict[str, object] = {}

    def _fake_check_updates_for_inventory(
        incoming_inventory,
        *,
        fetcher=None,
        timeout_seconds: float = 8.0,
        nexus_api_key: str | None = None,
        update_source_intent_overlay: UpdateSourceIntentOverlay | None = None,
    ) -> ModUpdateReport:
        captured["inventory"] = incoming_inventory
        captured["nexus_api_key"] = nexus_api_key
        captured["update_source_intent_overlay"] = update_source_intent_overlay
        return ModUpdateReport(statuses=tuple())

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(shell_service_module, "check_updates_for_inventory", _fake_check_updates_for_inventory)
    try:
        config = AppConfig(
            game_path=tmp_path,
            mods_path=tmp_path,
            app_data_path=tmp_path,
            nexus_api_key="persisted-nexus-key",
        )
        _ = service.check_updates(
            inventory,
            nexus_api_key_text="",
            existing_config=config,
        )
    finally:
        monkeypatch.undo()

    assert captured["inventory"] is inventory
    assert captured["nexus_api_key"] == "persisted-nexus-key"
    assert captured["update_source_intent_overlay"] == UpdateSourceIntentOverlay(records=tuple())


def test_check_updates_passes_manual_source_association_overlay_to_metadata_service(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    inventory = _empty_inventory()
    captured: dict[str, object] = {}
    saved_overlay = service.set_update_source_intent(
        "Sample.Override",
        "manual_source_association",
        manual_provider="nexus",
        manual_source_key="12345",
        manual_source_page_url="https://example.test/manual-page",
    )

    def _fake_check_updates_for_inventory(
        incoming_inventory,
        *,
        fetcher=None,
        timeout_seconds: float = 8.0,
        nexus_api_key: str | None = None,
        update_source_intent_overlay: UpdateSourceIntentOverlay | None = None,
    ) -> ModUpdateReport:
        captured["inventory"] = incoming_inventory
        captured["nexus_api_key"] = nexus_api_key
        captured["update_source_intent_overlay"] = update_source_intent_overlay
        return ModUpdateReport(statuses=tuple())

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(shell_service_module, "check_updates_for_inventory", _fake_check_updates_for_inventory)
    try:
        _ = service.check_updates(inventory)
    finally:
        monkeypatch.undo()

    assert captured["inventory"] is inventory
    assert captured["nexus_api_key"] is None
    assert captured["update_source_intent_overlay"] == saved_overlay


def test_search_mod_discovery_delegates_to_discovery_service(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    captured: dict[str, object] = {}
    expected = ModDiscoveryResult(
        query="spacecore",
        provider="smapi_compatibility_list",
        results=(
            ModDiscoveryEntry(
                name="SpaceCore",
                unique_id="spacechase0.SpaceCore",
                author="spacechase0",
                provider="smapi_compatibility_list",
                source_provider="nexus",
                source_page_url="https://www.nexusmods.com/stardewvalley/mods/1348",
                compatibility_state="compatible",
                compatibility_status="ok",
            ),
        ),
    )

    def _fake_search_discoverable_mods(
        query: str,
        *,
        fetcher=None,
        timeout_seconds: float = 10.0,
        max_results: int = 50,
    ) -> ModDiscoveryResult:
        _ = fetcher
        _ = timeout_seconds
        captured["query"] = query
        captured["max_results"] = max_results
        return expected

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(shell_service_module, "search_discoverable_mods", _fake_search_discoverable_mods)
    try:
        result = service.search_mod_discovery(query_text="spacecore", max_results=25)
    finally:
        monkeypatch.undo()

    assert captured["query"] == "spacecore"
    assert captured["max_results"] == 25
    assert result == expected


def test_resolve_discovery_source_page_url_requires_url(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    entry_without_url = ModDiscoveryEntry(
        name="No Link",
        unique_id="sample.NoLink",
        author="Sample",
        provider="smapi_compatibility_list",
        source_provider="none",
        source_page_url=None,
        compatibility_state="compatibility_unknown",
        compatibility_status="unknown",
    )

    with pytest.raises(AppShellError, match="No source page URL is available"):
        _ = service.resolve_discovery_source_page_url(entry_without_url)


def test_correlate_discovery_results_marks_installed_update_and_provider_alignment(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    discovery_result = ModDiscoveryResult(
        query="spacecore",
        provider="smapi_compatibility_list",
        results=(
            ModDiscoveryEntry(
                name="SpaceCore",
                unique_id="spacechase0.SpaceCore",
                author="spacechase0",
                provider="smapi_compatibility_list",
                source_provider="nexus",
                source_page_url="https://www.nexusmods.com/stardewvalley/mods/1348",
                compatibility_state="compatible",
                compatibility_status="ok",
            ),
        ),
    )
    inventory = _inventory_with_mod("spacechase0.SpaceCore")
    update_report = ModUpdateReport(
        statuses=(
            ModUpdateStatus(
                unique_id="spacechase0.SpaceCore",
                name="SpaceCore",
                folder_path=Path("/tmp/SpaceCore"),
                installed_version="1.0.0",
                remote_version="1.1.0",
                state="update_available",
                remote_link=RemoteModLink(
                    provider="nexus",
                    key="stardewvalley:1348",
                    page_url="https://www.nexusmods.com/stardewvalley/mods/1348",
                    metadata_url="https://api.nexusmods.com/v1/games/stardewvalley/mods/1348.json",
                ),
            ),
        )
    )

    correlations = service.correlate_discovery_results(
        discovery_result=discovery_result,
        inventory=inventory,
        update_report=update_report,
    )

    assert len(correlations) == 1
    item = correlations[0]
    assert item.installed_match_unique_id == "spacechase0.SpaceCore"
    assert item.update_state == "update_available"
    assert item.provider_relation == "provider_aligned"
    assert "matches tracked update provider" in (item.provider_relation_note or "")


def test_correlate_discovery_results_marks_provider_mismatch(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    discovery_result = ModDiscoveryResult(
        query="sample",
        provider="smapi_compatibility_list",
        results=(
            ModDiscoveryEntry(
                name="Sample Mod",
                unique_id="sample.Mod",
                author="author",
                provider="smapi_compatibility_list",
                source_provider="nexus",
                source_page_url="https://www.nexusmods.com/stardewvalley/mods/100",
                compatibility_state="compatible",
                compatibility_status="ok",
            ),
        ),
    )
    inventory = _inventory_with_mod("sample.Mod")
    update_report = ModUpdateReport(
        statuses=(
            ModUpdateStatus(
                unique_id="sample.Mod",
                name="Sample Mod",
                folder_path=Path("/tmp/SampleMod"),
                installed_version="1.0.0",
                remote_version="1.0.1",
                state="update_available",
                remote_link=RemoteModLink(
                    provider="github",
                    key="owner/repo",
                    page_url="https://github.com/owner/repo",
                    metadata_url="https://api.github.com/repos/owner/repo/releases/latest",
                ),
            ),
        )
    )

    correlations = service.correlate_discovery_results(
        discovery_result=discovery_result,
        inventory=inventory,
        update_report=update_report,
    )

    assert len(correlations) == 1
    item = correlations[0]
    assert item.provider_relation == "provider_mismatch"
    assert "differs from tracked update provider" in (item.provider_relation_note or "")


def test_correlate_discovery_results_marks_installed_without_update_context(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    discovery_result = ModDiscoveryResult(
        query="sample",
        provider="smapi_compatibility_list",
        results=(
            ModDiscoveryEntry(
                name="Sample Mod",
                unique_id="sample.Mod",
                author="author",
                provider="smapi_compatibility_list",
                source_provider="custom_url",
                source_page_url="https://example.test/mod",
                compatibility_state="compatible",
                compatibility_status="ok",
            ),
        ),
    )
    inventory = _inventory_with_mod("sample.Mod")

    correlations = service.correlate_discovery_results(
        discovery_result=discovery_result,
        inventory=inventory,
        update_report=None,
    )

    assert len(correlations) == 1
    item = correlations[0]
    assert item.installed_match_unique_id == "sample.Mod"
    assert item.update_state is None
    assert item.provider_relation == "no_update_provider_context"
    assert "Run Check updates" in item.next_step


def test_get_nexus_status_reports_saved_config_state(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    config = AppConfig(
        game_path=tmp_path,
        mods_path=tmp_path,
        app_data_path=tmp_path,
        nexus_api_key="saved-key",
    )

    status = service.get_nexus_integration_status(
        nexus_api_key_text="",
        existing_config=config,
        validate_connection=False,
    )

    assert status.state == "configured"
    assert status.source == "saved_config"
    assert status.masked_key is not None
    assert "saved-key" not in (status.masked_key or "")


def test_get_nexus_status_uses_environment_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SDVMM_NEXUS_API_KEY", "env-key-123456")
    service = AppShellService(state_file=tmp_path / "app-state.json")

    status = service.get_nexus_integration_status(
        nexus_api_key_text="",
        existing_config=None,
        validate_connection=False,
    )

    assert status.state == "configured"
    assert status.source == "environment"


def test_get_nexus_status_validation_reports_auth_failure(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        shell_service_module,
        "check_nexus_connection",
        lambda *, nexus_api_key: NexusIntegrationStatus(
            state="invalid_auth_failure",
            source="entered",
            masked_key="abcd...1234",
            message="[auth_failure] HTTP 401",
        ),
    )
    try:
        status = service.get_nexus_integration_status(
            nexus_api_key_text="abcd-1234",
            existing_config=None,
            validate_connection=True,
        )
    finally:
        monkeypatch.undo()

    assert status.state == "invalid_auth_failure"


def test_save_operational_config_persists_paths_and_scan_target(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    mods = tmp_path / "Mods"
    sandbox = tmp_path / "SandboxMods"
    archive = tmp_path / "SandboxArchive"
    real_archive = tmp_path / "RealArchive"
    downloads = tmp_path / "Downloads"
    mods.mkdir()
    sandbox.mkdir()
    archive.mkdir()
    real_archive.mkdir()
    downloads.mkdir()

    saved = service.save_operational_config(
        game_path_text=str(mods.parent),
        mods_dir_text=str(mods),
        sandbox_mods_path_text=str(sandbox),
        sandbox_archive_path_text=str(archive),
        watched_downloads_path_text=str(downloads),
        real_archive_path_text=str(real_archive),
        nexus_api_key_text="persisted-key",
        scan_target="sandbox_mods",
        install_target=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        existing_config=None,
    )

    assert saved.mods_path == mods
    assert saved.sandbox_mods_path == sandbox
    assert saved.sandbox_archive_path == archive
    assert saved.real_archive_path == real_archive
    assert saved.watched_downloads_path == downloads
    assert saved.nexus_api_key == "persisted-key"
    assert saved.scan_target == "sandbox_mods"
    assert saved.install_target == INSTALL_TARGET_CONFIGURED_REAL_MODS

    reloaded = AppShellService(state_file=tmp_path / "app-state.json").load_startup_config()
    assert reloaded.config is not None
    assert reloaded.config.sandbox_mods_path == sandbox
    assert reloaded.config.sandbox_archive_path == archive
    assert reloaded.config.real_archive_path == real_archive
    assert reloaded.config.watched_downloads_path == downloads
    assert reloaded.config.nexus_api_key == "persisted-key"
    assert reloaded.config.scan_target == "sandbox_mods"
    assert reloaded.config.install_target == INSTALL_TARGET_CONFIGURED_REAL_MODS


def test_save_operational_config_can_derive_mods_path_from_game_path(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Stardew Valley"
    mods = game_path / "Mods"
    sandbox = tmp_path / "SandboxMods"
    archive = tmp_path / "SandboxArchive"
    downloads = tmp_path / "Downloads"
    game_path.mkdir()
    mods.mkdir()
    sandbox.mkdir()
    archive.mkdir()
    downloads.mkdir()

    saved = service.save_operational_config(
        game_path_text=str(game_path),
        mods_dir_text="",
        sandbox_mods_path_text=str(sandbox),
        sandbox_archive_path_text=str(archive),
        watched_downloads_path_text=str(downloads),
        nexus_api_key_text="",
        scan_target="configured_real_mods",
        existing_config=None,
    )

    assert saved.game_path == game_path
    assert saved.mods_path == mods
    assert saved.install_target == INSTALL_TARGET_SANDBOX_MODS


def test_save_operational_config_defaults_archive_paths_outside_mods_trees(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Stardew Valley"
    mods = game_path / "Mods"
    sandbox = tmp_path / "SandboxMods"
    downloads = tmp_path / "Downloads"
    game_path.mkdir()
    mods.mkdir()
    sandbox.mkdir()
    downloads.mkdir()

    saved = service.save_operational_config(
        game_path_text=str(game_path),
        mods_dir_text=str(mods),
        sandbox_mods_path_text=str(sandbox),
        sandbox_archive_path_text="",
        watched_downloads_path_text=str(downloads),
        real_archive_path_text="",
        nexus_api_key_text="",
        scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
        install_target=INSTALL_TARGET_SANDBOX_MODS,
        existing_config=None,
    )

    assert saved.real_archive_path == mods.parent / ".sdvmm-real-archive"
    assert saved.sandbox_archive_path == sandbox.parent / ".sdvmm-sandbox-archive"


def test_save_operational_config_blocks_archive_inside_active_mods_tree(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Stardew Valley"
    mods = game_path / "Mods"
    sandbox = tmp_path / "SandboxMods"
    downloads = tmp_path / "Downloads"
    game_path.mkdir()
    mods.mkdir()
    sandbox.mkdir()
    downloads.mkdir()

    with pytest.raises(AppShellError, match="must be outside the active Mods directory"):
        service.save_operational_config(
            game_path_text=str(game_path),
            mods_dir_text=str(mods),
            sandbox_mods_path_text=str(sandbox),
            sandbox_archive_path_text=str(sandbox / ".sdvmm-archive"),
            watched_downloads_path_text=str(downloads),
            real_archive_path_text=str(mods / ".sdvmm-archive"),
            nexus_api_key_text="",
            scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
            install_target=INSTALL_TARGET_SANDBOX_MODS,
            existing_config=None,
        )


def test_detect_game_environment_reports_smapi_states(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    game_path = tmp_path / "Stardew Valley"
    mods = game_path / "Mods"
    game_path.mkdir()
    (game_path / "Stardew Valley").write_text("binary", encoding="utf-8")
    mods.mkdir()

    no_smapi_status = service.detect_game_environment(str(game_path))
    assert "smapi_not_detected" in no_smapi_status.state_codes

    smapi = game_path / "StardewModdingAPI"
    smapi.write_text("x", encoding="utf-8")
    smapi_status = service.detect_game_environment(str(game_path))
    assert "smapi_detected" in smapi_status.state_codes
    assert smapi_status.smapi_path == smapi


def test_detect_game_environment_reports_invalid_game_path_state(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    status = service.detect_game_environment(str(tmp_path / "missing-game-path"))

    assert status.state_codes == ("invalid_game_path",)


def test_detect_game_environment_marks_existing_non_game_directory_as_invalid(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    fake_game_path = tmp_path / "NotStardew"
    fake_game_path.mkdir()
    (fake_game_path / "Mods").mkdir()

    status = service.detect_game_environment(str(fake_game_path))

    assert "invalid_game_path" in status.state_codes
    assert "mods_path_detected" in status.state_codes
    assert "game_path_detected" not in status.state_codes


def test_initialize_and_poll_downloads_watch_detects_new_zip(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    downloads = tmp_path / "Downloads"
    downloads.mkdir()

    known = service.initialize_downloads_watch(str(downloads))
    assert known == ()

    package = downloads / "candidate.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    result = service.poll_downloads_watch(
        watched_downloads_path_text=str(downloads),
        known_zip_paths=known,
        inventory=_empty_inventory(),
    )
    assert len(result.intakes) == 1
    assert result.intakes[0].classification == "new_install_candidate"
    assert len(result.intakes[0].remote_requirements) == 1
    assert result.intakes[0].remote_requirements[0].state == "no_remote_link"


def test_select_intake_result_returns_selected_entry(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    package = downloads / "candidate.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Mod/manifest.json",
            '{"Name":"Zip Mod","UniqueID":"Pkg.Zip","Version":"1.0.0"}',
        )

    result = service.poll_downloads_watch(
        watched_downloads_path_text=str(downloads),
        known_zip_paths=tuple(),
        inventory=_empty_inventory(),
    )

    selected = service.select_intake_result(intakes=result.intakes, selected_index=0)
    assert selected.package_path == package


def test_select_intake_result_rejects_invalid_index(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")

    with pytest.raises(AppShellError, match="Select a detected package first"):
        service.select_intake_result(intakes=tuple(), selected_index=0)


def test_build_sandbox_install_plan_from_intake_new_install_candidate(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    downloads = tmp_path / "Downloads"
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    downloads.mkdir()
    sandbox.mkdir()
    archive_root.mkdir()

    package = downloads / "new_mod.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "NewMod/manifest.json",
            '{"Name":"New Mod","UniqueID":"Pkg.NewMod","Version":"1.0.0"}',
        )

    poll_result = service.poll_downloads_watch(
        watched_downloads_path_text=str(downloads),
        known_zip_paths=tuple(),
        inventory=_empty_inventory(),
    )
    intake = service.select_intake_result(intakes=poll_result.intakes, selected_index=0)

    plan = service.build_sandbox_install_plan_from_intake(
        intake=intake,
        sandbox_mods_path_text=str(sandbox),
        sandbox_archive_path_text=str(archive_root),
        allow_overwrite=False,
    )

    assert plan.package_path == package
    assert len(plan.entries) == 1
    assert plan.entries[0].action == "install_new"
    assert plan.entries[0].can_install is True


def test_build_sandbox_install_plan_from_intake_update_replace_candidate(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    downloads = tmp_path / "Downloads"
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    downloads.mkdir()
    sandbox.mkdir()
    archive_root.mkdir()
    (sandbox / "Existing").mkdir()

    package = downloads / "update_mod.zip"
    with ZipFile(package, "w") as archive:
        archive.writestr(
            "Existing/manifest.json",
            '{"Name":"Existing","UniqueID":"Sample.Exists","Version":"2.0.0"}',
        )

    poll_result = service.poll_downloads_watch(
        watched_downloads_path_text=str(downloads),
        known_zip_paths=tuple(),
        inventory=_inventory_with_mod("Sample.Exists"),
    )
    intake = service.select_intake_result(intakes=poll_result.intakes, selected_index=0)
    assert intake.classification == "update_replace_candidate"

    plan = service.build_sandbox_install_plan_from_intake(
        intake=intake,
        sandbox_mods_path_text=str(sandbox),
        sandbox_archive_path_text=str(archive_root),
        allow_overwrite=True,
    )

    assert len(plan.entries) == 1
    assert plan.entries[0].action == "overwrite_with_archive"
    assert plan.entries[0].can_install is True


def test_build_sandbox_install_plan_from_intake_rejects_unusable_package(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    downloads = tmp_path / "Downloads"
    sandbox = tmp_path / "SandboxMods"
    archive_root = tmp_path / "SandboxArchive"
    downloads.mkdir()
    sandbox.mkdir()
    archive_root.mkdir()

    package = downloads / "broken.zip"
    package.write_bytes(b"not zip")

    poll_result = service.poll_downloads_watch(
        watched_downloads_path_text=str(downloads),
        known_zip_paths=tuple(),
        inventory=_empty_inventory(),
    )
    intake = service.select_intake_result(intakes=poll_result.intakes, selected_index=0)
    assert intake.classification == "unusable_package"

    with pytest.raises(AppShellError, match="not actionable for install planning"):
        service.build_sandbox_install_plan_from_intake(
            intake=intake,
            sandbox_mods_path_text=str(sandbox),
            sandbox_archive_path_text=str(archive_root),
            allow_overwrite=False,
        )


def test_correlate_intake_with_updates_marks_update_available_match(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    intake = _intake_result(
        package_path=tmp_path / "update.zip",
        classification="update_replace_candidate",
        matched_installed_unique_ids=("Sample.Exists",),
    )
    report = _update_report(
        _update_status(unique_id="Sample.Exists", state="update_available"),
    )

    correlation = service.correlate_intake_with_updates(
        intake=intake,
        update_report=report,
        guided_update_unique_ids=tuple(),
    )

    assert correlation.actionable is True
    assert correlation.matched_update_available_unique_ids == ("Sample.Exists",)
    assert "update available" in correlation.summary.casefold()
    assert "plan selected intake" in correlation.next_step.casefold()


def test_correlate_intake_with_updates_prefers_guided_update_match(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    intake = _intake_result(
        package_path=tmp_path / "guided_update.zip",
        classification="update_replace_candidate",
        matched_installed_unique_ids=("Sample.Exists",),
    )
    report = _update_report(
        _update_status(unique_id="Sample.Exists", state="update_available"),
    )

    correlation = service.correlate_intake_with_updates(
        intake=intake,
        update_report=report,
        guided_update_unique_ids=("Sample.Exists",),
    )

    assert correlation.matched_guided_update_unique_ids == ("Sample.Exists",)
    assert "guided update target" in correlation.summary.casefold()
    assert correlation.actionable is True


def test_correlate_intake_with_updates_keeps_unusable_non_actionable(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    intake = _intake_result(
        package_path=tmp_path / "broken.zip",
        classification="unusable_package",
        matched_installed_unique_ids=("Sample.Exists",),
    )

    correlation = service.correlate_intake_with_updates(
        intake=intake,
        update_report=None,
        guided_update_unique_ids=tuple(),
    )

    assert correlation.actionable is False
    assert correlation.matched_update_available_unique_ids == ()
    assert "unusable" in correlation.summary.casefold()


def test_correlate_intake_with_updates_new_install_candidate_has_default_flow_message(
    tmp_path: Path,
) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    intake = _intake_result(
        package_path=tmp_path / "new-install.zip",
        classification="new_install_candidate",
        matched_installed_unique_ids=tuple(),
    )

    correlation = service.correlate_intake_with_updates(
        intake=intake,
        update_report=None,
        guided_update_unique_ids=tuple(),
    )

    assert correlation.actionable is True
    assert "new install candidate" in correlation.summary.casefold()
    assert "plan install" in correlation.next_step.casefold()


def _create_launchable_game_install(game_path: Path, *, with_smapi: bool = True) -> Path:
    game_path.mkdir()
    (game_path / "Mods").mkdir()
    (game_path / "Stardew Valley.exe").write_text("", encoding="utf-8")
    smapi_executable = game_path / "StardewModdingAPI.exe"
    if with_smapi:
        smapi_executable.write_text("", encoding="utf-8")
    return smapi_executable


def _empty_inventory():
    from sdvmm.domain.models import ModsInventory

    return ModsInventory(
        mods=tuple(),
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )


def _inventory_with_mod(unique_id: str):
    from sdvmm.domain.models import InstalledMod, ModsInventory

    mod = InstalledMod(
        unique_id=unique_id,
        name=unique_id,
        version="1.0.0",
        folder_path=Path("/tmp") / unique_id,
        manifest_path=Path("/tmp") / unique_id / "manifest.json",
        dependencies=tuple(),
        update_keys=tuple(),
    )
    return ModsInventory(
        mods=(mod,),
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )


def _intake_result(
    *,
    package_path: Path,
    classification: Literal[
        "new_install_candidate",
        "update_replace_candidate",
        "multi_mod_package",
        "unusable_package",
    ],
    matched_installed_unique_ids: tuple[str, ...],
):
    from sdvmm.domain.models import DownloadsIntakeResult

    return DownloadsIntakeResult(
        package_path=package_path,
        classification=classification,
        message="test",
        mods=tuple(),
        matched_installed_unique_ids=matched_installed_unique_ids,
        warnings=tuple(),
        findings=tuple(),
    )


def _update_status(*, unique_id: str, state: UpdateState) -> ModUpdateStatus:
    return ModUpdateStatus(
        unique_id=unique_id,
        name=unique_id,
        folder_path=Path("/tmp") / unique_id,
        installed_version="1.0.0",
        remote_version="2.0.0",
        state=state,
        remote_link=None,
        message=None,
    )


def _update_report(*statuses: ModUpdateStatus) -> ModUpdateReport:
    return ModUpdateReport(statuses=tuple(statuses))


def _create_mod(mods_root: Path, folder_name: str, unique_id: str) -> Path:
    mod_path = mods_root / folder_name
    mod_path.mkdir(parents=True, exist_ok=True)
    (mod_path / "manifest.json").write_text(
        (
            "{"
            f'"Name":"{folder_name}",'
            f'"UniqueID":"{unique_id}",'
            '"Version":"1.0.0"'
            "}"
        ),
        encoding="utf-8",
    )
    return mod_path


def _create_archived_entry(archived_path: Path, *, unique_id: str, version: str) -> Path:
    archived_path.mkdir(parents=True, exist_ok=True)
    (archived_path / "manifest.json").write_text(
        (
            "{"
            f'"Name":"{archived_path.name}",'
            f'"UniqueID":"{unique_id}",'
            f'"Version":"{version}"'
            "}"
        ),
        encoding="utf-8",
    )
    return archived_path


def _install_operation_record(
    tmp_path: Path,
    *,
    entries: tuple[InstallOperationEntryRecord, ...],
    archived_targets: tuple[Path, ...] | None = None,
) -> InstallOperationRecord:
    installed_targets = tuple(entry.target_path for entry in entries)
    recorded_archived_targets = (
        archived_targets
        if archived_targets is not None
        else tuple(entry.archive_path for entry in entries if entry.archive_path is not None)
    )
    return InstallOperationRecord(
        operation_id="install_test_record",
        timestamp="2026-03-13T12:00:00Z",
        package_path=tmp_path / "Downloads" / "sample.zip",
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        destination_mods_path=tmp_path / "SandboxMods",
        archive_path=tmp_path / "SandboxArchive",
        installed_targets=installed_targets,
        archived_targets=recorded_archived_targets,
        entries=entries,
    )


def _install_operation_entry(
    tmp_path: Path,
    *,
    name: str,
    unique_id: str,
    action: str,
    archive_path: Path | None = None,
    can_install: bool = True,
    warnings: tuple[str, ...] = tuple(),
) -> InstallOperationEntryRecord:
    return InstallOperationEntryRecord(
        name=name,
        unique_id=unique_id,
        version="1.0.0",
        action=action,
        target_path=tmp_path / "SandboxMods" / name,
        archive_path=archive_path,
        source_manifest_path=str(tmp_path / "package" / name / "manifest.json"),
        source_root_path=str(tmp_path / "package" / name),
        target_exists_before=action == OVERWRITE_WITH_ARCHIVE,
        can_install=can_install,
        warnings=warnings,
    )


def _summary_action_counts(summary: InstallExecutionSummary) -> dict[str, int]:
    return {item.action: item.count for item in summary.action_counts}


def _summary_plan(
    tmp_path: Path,
    *,
    destination_kind: str,
    entries: tuple[SandboxInstallPlanEntry, ...] | None = None,
) -> SandboxInstallPlan:
    mods_path = (
        tmp_path / "RealMods"
        if destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
        else tmp_path / "SandboxMods"
    )
    archive_path = (
        tmp_path / "RealArchive"
        if destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
        else tmp_path / "SandboxArchive"
    )
    default_entries = (
        _summary_entry(
            tmp_path,
            name="Sample Mod",
            unique_id="Sample.Mod",
            action=INSTALL_NEW,
        ),
    )
    return SandboxInstallPlan(
        package_path=tmp_path / "sample.zip",
        sandbox_mods_path=mods_path,
        sandbox_archive_path=archive_path,
        entries=entries if entries is not None else default_entries,
        package_findings=(
            PackageFinding(
                kind=DIRECT_SINGLE_MOD_PACKAGE,
                message="Single mod package",
                related_paths=("sample.zip",),
            ),
        ),
        package_warnings=(
            PackageWarning(
                code=INVALID_MANIFEST,
                message="Package warning message",
                manifest_path="sample/manifest.json",
            ),
        ),
        plan_warnings=("Plan review warning",),
        dependency_findings=tuple(),
        remote_requirements=tuple(),
        destination_kind=destination_kind,
    )


def _summary_entry(
    tmp_path: Path,
    *,
    name: str,
    unique_id: str,
    action: str,
    target_exists: bool = False,
    archive_path: Path | None = None,
    can_install: bool = True,
    warnings: tuple[str, ...] = tuple(),
) -> SandboxInstallPlanEntry:
    return SandboxInstallPlanEntry(
        name=name,
        unique_id=unique_id,
        version="1.0.0",
        source_manifest_path=str(tmp_path / "package" / name / "manifest.json"),
        source_root_path=str(tmp_path / "package" / name),
        target_path=tmp_path / "target-root" / name,
        action=action,
        target_exists=target_exists,
        archive_path=archive_path,
        can_install=can_install,
        warnings=warnings,
    )
