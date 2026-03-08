from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
from typing import Literal

import pytest

from sdvmm.app.shell_service import (
    SCAN_TARGET_CONFIGURED_REAL_MODS,
    SCAN_TARGET_SANDBOX_MODS,
    AppShellError,
    AppShellService,
)
from sdvmm.domain.models import AppConfig, ModUpdateReport, ModUpdateStatus
from sdvmm.domain.update_codes import UpdateState
from sdvmm.services.app_state_store import save_app_config


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

    follow_up_scan = service.scan_with_target(
        scan_target=SCAN_TARGET_SANDBOX_MODS,
        configured_mods_path_text=str(tmp_path / "ConfiguredMods"),
        sandbox_mods_path_text=str(sandbox),
    )
    assert follow_up_scan.scan_path == result.scan_context_path


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

    assert plan.sandbox_archive_path == sandbox / ".sdvmm-archive"
    assert plan.entries[0].archive_path == (sandbox / ".sdvmm-archive" / "Mod__sdvmm_archive_001")


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


def test_save_operational_config_persists_paths_and_scan_target(tmp_path: Path) -> None:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    mods = tmp_path / "Mods"
    sandbox = tmp_path / "SandboxMods"
    archive = tmp_path / "SandboxArchive"
    downloads = tmp_path / "Downloads"
    mods.mkdir()
    sandbox.mkdir()
    archive.mkdir()
    downloads.mkdir()

    saved = service.save_operational_config(
        mods_dir_text=str(mods),
        sandbox_mods_path_text=str(sandbox),
        sandbox_archive_path_text=str(archive),
        watched_downloads_path_text=str(downloads),
        scan_target="sandbox_mods",
        existing_config=None,
    )

    assert saved.mods_path == mods
    assert saved.sandbox_mods_path == sandbox
    assert saved.sandbox_archive_path == archive
    assert saved.watched_downloads_path == downloads
    assert saved.scan_target == "sandbox_mods"

    reloaded = AppShellService(state_file=tmp_path / "app-state.json").load_startup_config()
    assert reloaded.config is not None
    assert reloaded.config.sandbox_mods_path == sandbox
    assert reloaded.config.sandbox_archive_path == archive
    assert reloaded.config.watched_downloads_path == downloads
    assert reloaded.config.scan_target == "sandbox_mods"


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


def _create_mod(mods_root: Path, folder_name: str, unique_id: str) -> None:
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
