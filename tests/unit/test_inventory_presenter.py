from __future__ import annotations

from pathlib import Path

from sdvmm.app.shell_service import DiscoveryContextCorrelation
from sdvmm.app.inventory_presenter import (
    build_archive_restore_result_text,
    build_mod_rollback_result_text,
    build_discovery_search_text,
    build_downloads_intake_text,
    build_environment_status_text,
    build_package_inspection_text,
    build_sandbox_install_plan_text,
    build_smapi_update_status_text,
    build_update_report_text,
)
from sdvmm.domain.models import (
    ArchiveRestorePlan,
    ArchiveRestoreResult,
    ArchivedModEntry,
    DownloadsIntakeResult,
    DownloadsWatchPollResult,
    GameEnvironmentStatus,
    ModDiscoveryEntry,
    ModDiscoveryResult,
    ModsInventory,
    ModUpdateReport,
    ModUpdateStatus,
    ModRollbackPlan,
    ModRollbackResult,
    PackageFinding,
    PackageInspectionResult,
    PackageModEntry,
    PackageWarning,
    SmapiUpdateStatus,
    SandboxInstallPlan,
    SandboxInstallPlanEntry,
)


def test_update_report_text_is_human_readable_and_includes_next_step() -> None:
    report = ModUpdateReport(
        statuses=(
            ModUpdateStatus(
                unique_id="Sample.Mod",
                name="Sample Mod",
                folder_path=Path("/tmp/SampleMod"),
                installed_version="1.0.0",
                remote_version="1.1.0",
                state="update_available",
                remote_link=None,
                message="Remote version is newer than installed version.",
            ),
        )
    )

    text = build_update_report_text(report)

    assert "Update Awareness" in text
    assert "Update available" in text
    assert "Recommended next step" in text
    assert "Open remote page" in text


def test_environment_text_clarifies_invalid_path_next_step() -> None:
    status = GameEnvironmentStatus(
        game_path=Path("/tmp/not-game"),
        mods_path=Path("/tmp/not-game/Mods"),
        smapi_path=None,
        state_codes=("invalid_game_path", "mods_path_detected"),
        notes=tuple(),
    )

    text = build_environment_status_text(status)

    assert "Environment Detection" in text
    assert "Invalid game path" in text
    assert "Recommended next step" in text
    assert "Pick the Stardew Valley install folder" in text


def test_smapi_update_text_highlights_manual_update_guidance() -> None:
    status = SmapiUpdateStatus(
        state="update_available",
        game_path=Path("/tmp/game"),
        smapi_path=Path("/tmp/game/StardewModdingAPI"),
        installed_version="4.4.0",
        latest_version="4.5.1",
        update_page_url="https://github.com/Pathoschild/SMAPI/releases/tag/4.5.1",
        message="SMAPI update available: installed 4.4.0, latest 4.5.1.",
    )

    text = build_smapi_update_status_text(status)

    assert "SMAPI Update Awareness" in text
    assert "Status: SMAPI update available" in text
    assert "Recommended next step" in text
    assert "Open the SMAPI page and update SMAPI manually" in text


def test_downloads_intake_text_shows_classification_summary_and_action() -> None:
    intake = DownloadsIntakeResult(
        package_path=Path("/tmp/broken.zip"),
        classification="unusable_package",
        message="Package has no usable manifests in supported depth.",
        mods=tuple(),
        matched_installed_unique_ids=tuple(),
        warnings=tuple(),
        findings=tuple(),
    )
    result = DownloadsWatchPollResult(
        watched_path=Path("/tmp/Downloads"),
        known_zip_paths=(Path("/tmp/Downloads/broken.zip"),),
        intakes=(intake,),
    )

    text = build_downloads_intake_text(result)

    assert "Downloads Intake" in text
    assert "Intake summary" in text
    assert "Unusable package: 1" in text
    assert "recommended next step" in text
    assert "Not actionable" in text


def test_discovery_search_text_shows_compatibility_and_next_step() -> None:
    result = ModDiscoveryResult(
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
                compatibility_summary="Compatible on latest SMAPI.",
            ),
        ),
    )

    correlation = DiscoveryContextCorrelation(
        entry=result.results[0],
        installed_match_unique_id="spacechase0.SpaceCore",
        update_state="update_available",
        provider_relation="provider_aligned",
        provider_relation_note="Discovery source matches tracked update provider (Nexus).",
        context_summary="Already installed (spacechase0.SpaceCore); update is available in current metadata report",
        next_step="Open source page, download manually, let watcher detect the zip, then plan a safe update/replace.",
    )

    text = build_discovery_search_text(result, (correlation,))

    assert "Mod Discovery" in text
    assert "SMAPI compatibility index" in text
    assert "SpaceCore" in text
    assert "Compatible" in text
    assert "source context" in text
    assert "provider relation" in text
    assert "app context" in text
    assert "Open discovered page" in text


def test_package_inspection_text_separates_blocking_and_non_blocking_guidance() -> None:
    inspection = PackageInspectionResult(
        package_path=Path("/tmp/mod.zip"),
        mods=(
            PackageModEntry(
                name="Mod A",
                unique_id="Sample.ModA",
                version="1.0.0",
                manifest_path="ModA/manifest.json",
            ),
        ),
        warnings=(
            PackageWarning(
                code="invalid_manifest",
                message="UniqueID missing",
                manifest_path="ModB/manifest.json",
            ),
        ),
        findings=(
            PackageFinding(
                kind="direct_single_mod_package",
                message="Single mod found at package root layout.",
                related_paths=("ModA/manifest.json",),
            ),
        ),
    )

    text = build_package_inspection_text(inspection)

    assert "Manifest dependency preflight (blocking/local)" in text
    assert "Remote requirement guidance (non-blocking/source-declared)" in text
    assert "Recommended next step" in text


def test_sandbox_plan_text_highlights_blocked_plan() -> None:
    plan = SandboxInstallPlan(
        package_path=Path("/tmp/mod.zip"),
        sandbox_mods_path=Path("/tmp/SandboxMods"),
        sandbox_archive_path=Path("/tmp/SandboxArchive"),
        entries=(
            SandboxInstallPlanEntry(
                name="Mod A",
                unique_id="Sample.ModA",
                version="1.0.0",
                source_manifest_path="ModA/manifest.json",
                source_root_path="ModA",
                target_path=Path("/tmp/SandboxMods/ModA"),
                action="blocked",
                target_exists=False,
                archive_path=None,
                can_install=False,
                warnings=("Missing required dependencies: Sample.Required",),
            ),
        ),
        package_findings=tuple(),
        package_warnings=tuple(),
        plan_warnings=("Plan has blocked entries.",),
    )

    text = build_sandbox_install_plan_text(plan)

    assert "Install Plan" in text
    assert "Sandbox Mods destination" in text
    assert "Plan status: BLOCKED" in text
    assert "Recommended next step" in text
    assert "Resolve warnings" in text


def test_real_destination_plan_text_is_explicit() -> None:
    plan = SandboxInstallPlan(
        package_path=Path("/tmp/mod.zip"),
        sandbox_mods_path=Path("/tmp/RealMods"),
        sandbox_archive_path=Path("/tmp/RealMods/.sdvmm-archive"),
        entries=tuple(),
        package_findings=tuple(),
        package_warnings=tuple(),
        plan_warnings=tuple(),
        destination_kind="configured_real_mods",
    )

    text = build_sandbox_install_plan_text(plan)

    assert "Game Mods destination (real)" in text


def test_archive_restore_result_text_shows_destination_and_target_path() -> None:
    restored_mods = ModsInventory(
        mods=tuple(),
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )
    result = ArchiveRestoreResult(
        plan=ArchiveRestorePlan(
            entry=ArchivedModEntry(
                source_kind="real_archive",
                archive_root=Path("/tmp/RealArchive"),
                archived_path=Path("/tmp/RealArchive/RestoreReal__sdvmm_archive_001"),
                archived_folder_name="RestoreReal__sdvmm_archive_001",
                target_folder_name="RestoreReal",
                mod_name="Restore Real",
                unique_id="Sample.RestoreReal",
                version="3.0.0",
            ),
            destination_kind="configured_real_mods",
            destination_mods_path=Path("/tmp/RealMods"),
            destination_target_path=Path("/tmp/RealMods/RestoreReal"),
        ),
        restored_target=Path("/tmp/RealMods/RestoreReal"),
        scan_context_path=Path("/tmp/RealMods"),
        inventory=restored_mods,
        destination_kind="configured_real_mods",
    )

    text = build_archive_restore_result_text(result)

    assert "Archive restore completed" in text
    assert "Game Mods destination (real)" in text
    assert "/tmp/RealMods/RestoreReal" in text


def test_mod_rollback_result_text_shows_destination_and_paths() -> None:
    inventory = ModsInventory(
        mods=tuple(),
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )
    result = ModRollbackResult(
        plan=ModRollbackPlan(
            destination_kind="sandbox_mods",
            mods_path=Path("/tmp/SandboxMods"),
            archive_path=Path("/tmp/SandboxArchive"),
            current_mod_path=Path("/tmp/SandboxMods/SampleMod"),
            current_unique_id="Sample.Mod",
            current_version="2.0.0",
            rollback_entry=ArchivedModEntry(
                source_kind="sandbox_archive",
                archive_root=Path("/tmp/SandboxArchive"),
                archived_path=Path("/tmp/SandboxArchive/SampleMod__sdvmm_archive_001"),
                archived_folder_name="SampleMod__sdvmm_archive_001",
                target_folder_name="SampleMod",
                mod_name="Sample Mod",
                unique_id="Sample.Mod",
                version="1.0.0",
            ),
            current_archive_path=Path("/tmp/SandboxArchive/SampleMod__sdvmm_archive_002"),
        ),
        archived_current_target=Path("/tmp/SandboxArchive/SampleMod__sdvmm_archive_002"),
        restored_target=Path("/tmp/SandboxMods/SampleMod"),
        scan_context_path=Path("/tmp/SandboxMods"),
        inventory=inventory,
        destination_kind="sandbox_mods",
    )

    text = build_mod_rollback_result_text(result)

    assert "Mod rollback completed." in text
    assert "Sandbox Mods destination" in text
    assert "/tmp/SandboxArchive/SampleMod__sdvmm_archive_002" in text
    assert "/tmp/SandboxMods/SampleMod" in text
