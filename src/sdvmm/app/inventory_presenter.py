from __future__ import annotations

from sdvmm.app.shell_service import DiscoveryContextCorrelation, IntakeUpdateCorrelation
from sdvmm.domain.dependency_codes import (
    MISSING_REQUIRED_DEPENDENCY,
    OPTIONAL_DEPENDENCY_MISSING,
    SATISFIED,
    UNRESOLVED_DEPENDENCY_CONTEXT,
)
from sdvmm.domain.environment_codes import (
    GAME_PATH_DETECTED,
    INVALID_GAME_PATH,
    MODS_PATH_DETECTED,
    SMAPI_DETECTED,
    SMAPI_NOT_DETECTED,
)
from sdvmm.domain.models import (
    ArchivedModEntry,
    ArchiveDeleteResult,
    ArchiveRestoreResult,
    DependencyPreflightFinding,
    DownloadsIntakeResult,
    DownloadsWatchPollResult,
    GameEnvironmentStatus,
    ModDiscoveryEntry,
    ModDiscoveryResult,
    ModRemovalResult,
    ModRollbackPlan,
    ModRollbackResult,
    ModUpdateReport,
    ModsInventory,
    PackageInspectionResult,
    RemoteRequirementGuidance,
    SmapiLogReport,
    SmapiUpdateStatus,
    SandboxInstallPlan,
    SandboxInstallResult,
)
from sdvmm.domain.remote_requirement_codes import (
    NO_REMOTE_LINK_FOR_REQUIREMENTS,
    REQUIREMENTS_ABSENT,
    REQUIREMENTS_PRESENT,
    REQUIREMENTS_UNAVAILABLE,
)
from sdvmm.domain.smapi_codes import (
    SMAPI_DETECTED_VERSION_KNOWN,
    SMAPI_NOT_DETECTED_FOR_UPDATE,
    SMAPI_UNABLE_TO_DETERMINE,
    SMAPI_UP_TO_DATE,
    SMAPI_UPDATE_AVAILABLE,
)
from sdvmm.domain.smapi_log_codes import (
    SMAPI_LOG_ERROR,
    SMAPI_LOG_FAILED_MOD,
    SMAPI_LOG_MISSING_DEPENDENCY,
    SMAPI_LOG_NOT_FOUND,
    SMAPI_LOG_PARSED,
    SMAPI_LOG_RUNTIME_ISSUE,
    SMAPI_LOG_SOURCE_AUTO_DETECTED,
    SMAPI_LOG_SOURCE_MANUAL,
    SMAPI_LOG_SOURCE_NONE,
    SMAPI_LOG_UNABLE_TO_DETERMINE,
    SMAPI_LOG_WARNING,
)


def build_findings_text(inventory: ModsInventory) -> str:
    lines: list[str] = []
    lines.append("Installed Mods Scan Summary")
    lines.append(f"- Installed mods detected: {len(inventory.mods)}")
    lines.append(f"- Parse warnings: {len(inventory.parse_warnings)}")
    lines.append(f"- Duplicate UniqueIDs: {len(inventory.duplicate_unique_ids)}")
    lines.append(f"- Missing required dependencies: {len(inventory.missing_required_dependencies)}")
    lines.append("")

    if inventory.scan_entry_findings:
        lines.append("Folder scan findings:")
        for finding in inventory.scan_entry_findings:
            kind = _scan_entry_kind_label(finding.kind)
            lines.append(
                f"- {kind}: {finding.entry_path.name}: {finding.message} (code: {finding.kind})"
            )
    else:
        lines.append("Folder scan findings: none")

    lines.append("")

    if inventory.parse_warnings:
        lines.append("Manifest warnings:")
        for warning in inventory.parse_warnings:
            lines.append(
                f"- {_warning_code_label(warning.code)}: {warning.mod_path.name}: "
                f"{warning.message} (code: {warning.code})"
            )
    else:
        lines.append("Manifest warnings: none")

    if inventory.duplicate_unique_ids:
        lines.append("")
        lines.append("Duplicate UniqueID findings:")
        for finding in inventory.duplicate_unique_ids:
            folders = ", ".join(path.name for path in finding.folder_paths)
            lines.append(f"- {finding.unique_id} ({folders})")
    else:
        lines.append("")
        lines.append("Duplicate UniqueID findings: none")

    if inventory.missing_required_dependencies:
        lines.append("")
        lines.append("Missing required dependencies:")
        for finding in inventory.missing_required_dependencies:
            lines.append(
                "- "
                f"{finding.required_by_unique_id} requires {finding.missing_unique_id}"
                f" (folder: {finding.required_by_folder.name})"
            )
    else:
        lines.append("")
        lines.append("Missing required dependencies: none")

    lines.append("")
    lines.append("Recommended next step:")
    if inventory.missing_required_dependencies:
        lines.append("- Install missing required dependencies first, then scan again.")
    elif inventory.parse_warnings:
        lines.append("- Review manifest warnings and replace or fix broken mod folders.")
    else:
        lines.append("- Run update check to see if newer versions are available.")

    return "\n".join(lines)


def build_environment_status_text(status: GameEnvironmentStatus) -> str:
    lines: list[str] = []
    lines.append("Environment Detection")
    lines.append(f"- Selected game path: {status.game_path}")

    for state in status.state_codes:
        lines.append(f"- {_environment_state_label(state)} (code: {state})")

    if status.mods_path is not None:
        lines.append(f"- Detected Mods path: {status.mods_path}")
    else:
        lines.append("- Detected Mods path: <not detected>")

    if status.smapi_path is not None:
        lines.append(f"- Detected SMAPI path: {status.smapi_path}")
    else:
        lines.append("- Detected SMAPI path: <not detected>")

    for note in status.notes:
        lines.append(f"- note: {note}")

    lines.append("")
    if INVALID_GAME_PATH in status.state_codes:
        lines.append("Environment summary: invalid game path")
    elif GAME_PATH_DETECTED in status.state_codes:
        parts: list[str] = []
        if MODS_PATH_DETECTED in status.state_codes:
            parts.append("Mods detected")
        else:
            parts.append("Mods not detected")
        if SMAPI_DETECTED in status.state_codes:
            parts.append("SMAPI detected")
        elif SMAPI_NOT_DETECTED in status.state_codes:
            parts.append("SMAPI not detected")
        lines.append(f"Environment summary: {', '.join(parts)}")
    else:
        lines.append("Environment summary: incomplete detection state")

    lines.append("")
    lines.append("Recommended next step:")
    if INVALID_GAME_PATH in status.state_codes:
        lines.append("- Pick the Stardew Valley install folder (not only a random folder with Mods).")
    elif MODS_PATH_DETECTED not in status.state_codes:
        lines.append("- Create or select a valid Mods folder before scanning.")
    elif SMAPI_DETECTED not in status.state_codes:
        lines.append("- SMAPI not detected. Install/verify SMAPI if your mods require it.")
    else:
        lines.append("- Environment looks usable. Save config and run Scan.")

    return "\n".join(lines)


def build_smapi_update_status_text(status: SmapiUpdateStatus) -> str:
    lines: list[str] = []
    lines.append("SMAPI Update Awareness")
    lines.append(f"- Game path: {status.game_path}")
    lines.append(f"- SMAPI entrypoint: {status.smapi_path or '<not detected>'}")
    lines.append(f"- Installed SMAPI version: {status.installed_version or '<unknown>'}")
    lines.append(f"- Latest known SMAPI version: {status.latest_version or '<unknown>'}")
    lines.append(f"- Update source page: {status.update_page_url}")
    lines.append(f"- Status: {_smapi_update_state_label(status.state)} (code: {status.state})")
    lines.append(f"- Message: {status.message}")

    lines.append("")
    lines.append("Recommended next step:")
    if status.state == SMAPI_NOT_DETECTED_FOR_UPDATE:
        lines.append("- Install SMAPI first if you plan to launch with SMAPI mods.")
    elif status.state == SMAPI_UPDATE_AVAILABLE:
        lines.append("- Open the SMAPI page and update SMAPI manually.")
    elif status.state == SMAPI_UP_TO_DATE:
        lines.append("- SMAPI is current. Continue normal mod workflows.")
    elif status.state == SMAPI_DETECTED_VERSION_KNOWN:
        lines.append("- SMAPI version is known; retry check later for latest remote version.")
    elif status.state == SMAPI_UNABLE_TO_DETERMINE:
        lines.append("- Fix game path/SMAPI detection, then run SMAPI check again.")
    else:
        lines.append("- Re-run SMAPI check if environment changed.")

    return "\n".join(lines)


def build_smapi_log_report_text(report: SmapiLogReport) -> str:
    lines: list[str] = []
    lines.append("SMAPI Log Troubleshooting")
    lines.append(f"- Status: {_smapi_log_state_label(report.state)} (code: {report.state})")
    lines.append(f"- Source: {_smapi_log_source_label(report.source)}")
    lines.append(f"- Log path: {report.log_path or '<not loaded>'}")
    lines.append(f"- Game path context: {report.game_path or '<none>'}")

    if report.message:
        lines.append(f"- Summary: {report.message}")

    lines.append("")
    if report.findings:
        counts = _smapi_log_findings_count(report)
        lines.append(
            "- Parsed findings: "
            f"errors={counts[SMAPI_LOG_ERROR]}, "
            f"warnings={counts[SMAPI_LOG_WARNING]}, "
            f"failed mods={counts[SMAPI_LOG_FAILED_MOD]}, "
            f"missing dependencies={counts[SMAPI_LOG_MISSING_DEPENDENCY]}, "
            f"runtime issues={counts[SMAPI_LOG_RUNTIME_ISSUE]}"
        )
        lines.append("")
        lines.append("Finding details:")
        for finding in report.findings:
            lines.append(
                f"- line {finding.line_number} | {_smapi_log_finding_kind_label(finding.kind)}: {finding.message}"
            )
    else:
        lines.append("- Parsed findings: none")

    if report.notes:
        lines.append("")
        lines.append("Notes:")
        for note in report.notes:
            lines.append(f"- {note}")

    lines.append("")
    lines.append("Recommended next step:")
    if report.state == SMAPI_LOG_NOT_FOUND:
        lines.append("- Launch the game with SMAPI once, then run 'Check SMAPI log' again or load a log manually.")
    elif report.state == SMAPI_LOG_UNABLE_TO_DETERMINE:
        lines.append("- Load a specific SMAPI log file manually and re-check.")
    else:
        counts = _smapi_log_findings_count(report)
        if counts[SMAPI_LOG_MISSING_DEPENDENCY] > 0:
            lines.append("- Install missing dependencies first, then launch SMAPI and re-check.")
        elif counts[SMAPI_LOG_FAILED_MOD] > 0:
            lines.append("- Review failed-mod entries and update/remove the failing mods.")
        elif counts[SMAPI_LOG_ERROR] > 0 or counts[SMAPI_LOG_RUNTIME_ISSUE] > 0:
            lines.append("- Review error/runtime entries and verify mod compatibility with current SMAPI/game versions.")
        elif counts[SMAPI_LOG_WARNING] > 0:
            lines.append("- Review warnings and monitor if they repeat after next launch.")
        else:
            lines.append("- No obvious issues parsed. Re-check after reproducing a problem if needed.")

    return "\n".join(lines)


def build_dependency_preflight_text(
    *,
    title: str,
    findings: tuple[DependencyPreflightFinding, ...],
) -> str:
    lines: list[str] = [title]
    if not findings:
        lines.append("- none")
        return "\n".join(lines)

    grouped: dict[str, list[DependencyPreflightFinding]] = {
        SATISFIED: [],
        MISSING_REQUIRED_DEPENDENCY: [],
        OPTIONAL_DEPENDENCY_MISSING: [],
        UNRESOLVED_DEPENDENCY_CONTEXT: [],
    }
    for finding in findings:
        grouped.setdefault(finding.state, []).append(finding)

    for state in (
        SATISFIED,
        MISSING_REQUIRED_DEPENDENCY,
        OPTIONAL_DEPENDENCY_MISSING,
        UNRESOLVED_DEPENDENCY_CONTEXT,
    ):
        entries = grouped.get(state, [])
        if not entries:
            continue
        lines.append(f"- {_dependency_state_label(state)}: {len(entries)} (code: {state})")
        for entry in entries:
            requirement = "required" if entry.required else "optional"
            lines.append(
                "  "
                f"{entry.required_by_name} ({entry.required_by_unique_id}) -> "
                f"{entry.dependency_unique_id} ({requirement})"
            )

    return "\n".join(lines)


def build_package_inspection_text(result: PackageInspectionResult) -> str:
    lines: list[str] = []
    lines.append("Package Inspection")
    lines.append(f"- Package: {result.package_path.name}")
    lines.append(f"- Detected mods: {len(result.mods)}")
    lines.append(f"- Findings: {len(result.findings)}")
    lines.append(f"- Warnings: {len(result.warnings)}")

    lines.append("")
    if result.mods:
        lines.append("Detected mods in this zip:")
        for mod in result.mods:
            lines.append(
                f"- {mod.name} | UniqueID: {mod.unique_id} | Version: {mod.version} | {mod.manifest_path}"
            )
    else:
        lines.append("Detected mods in this zip: none")

    lines.append("")
    if result.findings:
        lines.append("Package findings:")
        for finding in result.findings:
            lines.append(
                f"- {_package_finding_label(finding.kind)}: {finding.message} "
                f"(code: {finding.kind})"
            )
    else:
        lines.append("Package findings: none")

    lines.append("")
    if result.warnings:
        lines.append("Package warnings:")
        for warning in result.warnings:
            lines.append(
                f"- {_warning_code_label(warning.code)}: {warning.manifest_path}: "
                f"{warning.message} (code: {warning.code})"
            )
    else:
        lines.append("Package warnings: none")

    lines.append("")
    lines.append(
        build_dependency_preflight_text(
            title="Manifest dependency preflight (blocking/local):",
            findings=result.dependency_findings,
        )
    )
    lines.append("")
    lines.append(
        build_remote_requirement_guidance_text(
            title="Remote requirement guidance (non-blocking/source-declared):",
            guidance=result.remote_requirements,
        )
    )
    lines.append("")
    lines.append("Recommended next step:")
    if not result.mods:
        lines.append("- Package is not ready for install planning. Choose another zip.")
    elif any(
        finding.state == MISSING_REQUIRED_DEPENDENCY for finding in result.dependency_findings
    ):
        lines.append("- Missing required dependencies detected. Install dependencies first.")
    else:
        lines.append("- Package looks plannable. Build an install plan for your selected destination.")

    return "\n".join(lines)


def build_sandbox_install_plan_text(plan: SandboxInstallPlan) -> str:
    lines: list[str] = []
    blocked_count = sum(1 for entry in plan.entries if not entry.can_install)
    installable_count = sum(1 for entry in plan.entries if entry.can_install)
    destination_label = _install_destination_label(plan.destination_kind)
    lines.append("Install Plan")
    lines.append(f"- Destination type: {destination_label}")
    lines.append(f"- Destination Mods path: {plan.sandbox_mods_path}")
    lines.append(f"- Destination archive path: {plan.sandbox_archive_path}")
    lines.append(f"- Source package: {plan.package_path.name}")
    lines.append(
        f"- Plan status: {'BLOCKED' if blocked_count else 'READY'} "
        f"(installable={installable_count}, blocked={blocked_count})"
    )
    lines.append("")

    if plan.entries:
        lines.append("Install plan entries:")
        for entry in plan.entries:
            status = "new target" if not entry.target_exists else "target already exists"
            action = _install_action_label(entry.action)
            executable = "ready" if entry.can_install else "blocked"
            lines.append(
                "- "
                f"{entry.name} | UniqueID: {entry.unique_id} | Version: {entry.version}"
                f" -> {entry.target_path.name} ({status}, action={action}, {executable})"
            )
            if entry.archive_path is not None:
                lines.append(f"  archive: {entry.archive_path}")
            for warning in entry.warnings:
                lines.append(f"  warning: {warning}")
    else:
        lines.append("Install plan entries: none")

    lines.append("")
    if plan.plan_warnings:
        lines.append("Plan warnings:")
        for warning in plan.plan_warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("Plan warnings: none")

    lines.append("")
    if plan.package_findings:
        lines.append("Package findings:")
        for finding in plan.package_findings:
            lines.append(
                f"- {_package_finding_label(finding.kind)}: {finding.message} "
                f"(code: {finding.kind})"
            )
    else:
        lines.append("Package findings: none")

    lines.append("")
    lines.append(
        build_dependency_preflight_text(
            title="Manifest dependency preflight (blocking/local):",
            findings=plan.dependency_findings,
        )
    )
    lines.append("")
    lines.append(
        build_remote_requirement_guidance_text(
            title="Remote requirement guidance (non-blocking/source-declared):",
            guidance=plan.remote_requirements,
        )
    )
    lines.append("")
    lines.append("Recommended next step:")
    if blocked_count:
        lines.append("- Plan is blocked. Resolve warnings (especially missing required dependencies) and rebuild plan.")
    else:
        lines.append("- Plan is ready. Review target/archive actions, then run install explicitly.")

    return "\n".join(lines)


def build_sandbox_install_result_text(result: SandboxInstallResult) -> str:
    lines: list[str] = []
    destination_label = _install_destination_label(result.destination_kind)
    lines.append("Install completed.")
    lines.append(f"- Destination type: {destination_label}")
    lines.append(f"- Scan context: {result.scan_context_path}")
    lines.append(f"Installed targets: {len(result.installed_targets)}")

    for target in result.installed_targets:
        lines.append(f"- {target}")

    lines.append("")
    lines.append(f"Archived targets: {len(result.archived_targets)}")
    for target in result.archived_targets:
        lines.append(f"- {target}")

    lines.append("")
    lines.append(build_findings_text(result.inventory))
    return "\n".join(lines)


def build_mod_removal_result_text(result: ModRemovalResult) -> str:
    lines: list[str] = []
    destination_label = _install_destination_label(result.destination_kind)
    lines.append("Mod removal completed.")
    lines.append(f"- Destination type: {destination_label}")
    lines.append(f"- Removed from active Mods path: {result.removed_target}")
    lines.append(f"- Archived to: {result.archived_target}")
    lines.append(f"- Scan context: {result.scan_context_path}")
    lines.append("")
    lines.append("Recommended next step:")
    lines.append("- Review scan findings and dependencies after removal.")
    lines.append("")
    lines.append(build_findings_text(result.inventory))
    return "\n".join(lines)


def build_mod_rollback_plan_text(plan: ModRollbackPlan) -> str:
    lines: list[str] = []
    destination_label = _install_destination_label(plan.destination_kind)
    entry = plan.rollback_entry
    lines.append("Rollback Plan")
    lines.append(f"- Destination type: {destination_label}")
    lines.append(f"- Current installed folder: {plan.current_mod_path}")
    lines.append(f"- Current installed version: {plan.current_version}")
    lines.append(
        f"- Current installed UniqueID: {plan.current_unique_id}"
    )
    lines.append(
        "- Archived rollback candidate: "
        f"{entry.mod_name or '<unknown>'} | "
        f"UniqueID: {entry.unique_id or '<unknown>'} | "
        f"Version: {entry.version or '<unknown>'}"
    )
    lines.append(f"- Archived candidate folder: {entry.archived_path}")
    lines.append(f"- Current version will be archived to: {plan.current_archive_path}")
    lines.append("")
    lines.append("Recommended next step:")
    lines.append("- Confirm rollback explicitly to archive current version and restore selected archived version.")
    return "\n".join(lines)


def build_mod_rollback_result_text(result: ModRollbackResult) -> str:
    lines: list[str] = []
    destination_label = _install_destination_label(result.destination_kind)
    lines.append("Mod rollback completed.")
    lines.append(f"- Destination type: {destination_label}")
    lines.append(f"- Previous current version archived to: {result.archived_current_target}")
    lines.append(f"- Restored archived version to active Mods: {result.restored_target}")
    lines.append(f"- Scan context: {result.scan_context_path}")
    lines.append("")
    lines.append("Recommended next step:")
    lines.append("- Review scan findings and dependency warnings after rollback.")
    lines.append("")
    lines.append(build_findings_text(result.inventory))
    return "\n".join(lines)


def build_archive_listing_text(entries: tuple[ArchivedModEntry, ...]) -> str:
    lines: list[str] = []
    real_count = sum(1 for entry in entries if entry.source_kind == "real_archive")
    sandbox_count = sum(1 for entry in entries if entry.source_kind == "sandbox_archive")
    lines.append("Archive Browser")
    lines.append(f"- Archived entries: {len(entries)}")
    lines.append(f"- Real archive entries: {real_count}")
    lines.append(f"- Sandbox archive entries: {sandbox_count}")
    lines.append("")

    if not entries:
        lines.append("No archived entries found.")
    else:
        lines.append("Archived entries:")
        for entry in entries:
            lines.append(
                "- "
                f"[{_archive_source_label(entry.source_kind)}] "
                f"{entry.archived_folder_name} -> restore target '{entry.target_folder_name}'"
            )
            if entry.mod_name or entry.unique_id or entry.version:
                lines.append(
                    "  "
                    f"mod: {entry.mod_name or '<unknown>'} | "
                    f"UniqueID: {entry.unique_id or '<unknown>'} | "
                    f"Version: {entry.version or '<unknown>'}"
                )
            else:
                lines.append("  mod: <manifest summary unavailable>")
            lines.append(f"  path: {entry.archived_path}")
            if entry.note:
                lines.append(f"  note: {entry.note}")

    lines.append("")
    lines.append("Recommended next step:")
    if entries:
        lines.append("- Select an archived entry, choose destination context, then restore explicitly.")
    else:
        lines.append("- Use remove/update overwrite flows to generate archived entries first.")

    return "\n".join(lines)


def build_archive_restore_result_text(result: ArchiveRestoreResult) -> str:
    lines: list[str] = []
    destination_label = _install_destination_label(result.destination_kind)
    lines.append("Archive restore completed.")
    lines.append(f"- Destination type: {destination_label}")
    lines.append(f"- Restored from archive: {result.plan.entry.archived_path}")
    lines.append(f"- Restored to active Mods: {result.restored_target}")
    lines.append(f"- Scan context: {result.scan_context_path}")
    lines.append("")
    lines.append("Recommended next step:")
    lines.append("- Review scan findings and dependency warnings after restore.")
    lines.append("")
    lines.append(build_findings_text(result.inventory))
    return "\n".join(lines)


def build_archive_delete_result_text(result: ArchiveDeleteResult) -> str:
    lines: list[str] = []
    lines.append("Archive permanent delete completed.")
    lines.append(f"- Archive source: {_archive_source_label(result.plan.entry.source_kind)}")
    lines.append(f"- Deleted archived folder: {result.deleted_path}")
    lines.append("")
    lines.append("Recommended next step:")
    lines.append("- Refresh archives and continue restore/rollback planning with remaining entries if needed.")
    return "\n".join(lines)


def build_update_report_text(report: ModUpdateReport) -> str:
    lines: list[str] = []
    lines.append("Update Awareness")
    lines.append("Manifest dependency preflight (blocking) is separate from remote requirement guidance (non-blocking).")

    if not report.statuses:
        lines.append("- No installed mods in current inventory.")
        return "\n".join(lines)

    update_available_count = sum(1 for status in report.statuses if status.state == "update_available")
    up_to_date_count = sum(1 for status in report.statuses if status.state == "up_to_date")
    no_link_count = sum(1 for status in report.statuses if status.state == "no_remote_link")
    unavailable_count = sum(1 for status in report.statuses if status.state == "metadata_unavailable")
    lines.append(
        f"- Summary: update available={update_available_count}, up to date={up_to_date_count}, "
        f"no remote link={no_link_count}, metadata unavailable={unavailable_count}"
    )
    lines.append("")

    for status in report.statuses:
        remote_version = status.remote_version or "unknown"
        lines.append(
            "- "
            f"{status.name} | UniqueID: {status.unique_id} | "
            f"installed={status.installed_version} | remote={remote_version} | "
            f"state={_update_state_label(status.state)} (code: {status.state})"
        )
        if status.remote_link is not None:
            lines.append(f"  remote: {status.remote_link.page_url}")
        if status.message:
            lines.append(f"  note: {status.message}")
        lines.append(
            f"  remote requirements [{_remote_requirements_state_label(status.remote_requirements_state)} "
            f"/ code: {status.remote_requirements_state}]: "
            f"{_format_remote_requirements_inline(status.remote_requirements, status.remote_requirements_message)}"
        )

    lines.append("")
    lines.append("Recommended next step:")
    if update_available_count:
        lines.append("- Select an 'Update available' mod row and click Open remote page, then use intake + install planning.")
    elif unavailable_count:
        lines.append("- Metadata unavailable for some mods. Check API key/network and try Check updates again.")
    else:
        lines.append("- No immediate update action is required.")

    return "\n".join(lines)


def build_discovery_search_text(
    result: ModDiscoveryResult,
    correlations: tuple[DiscoveryContextCorrelation, ...] = tuple(),
) -> str:
    lines: list[str] = []
    lines.append("Mod Discovery")
    lines.append("- Source: SMAPI compatibility index")
    lines.append(f"- Query: {result.query}")
    lines.append(f"- Results: {len(result.results)}")

    if result.notes:
        for note in result.notes:
            lines.append(f"- note: {note}")

    lines.append("")
    if not result.results:
        lines.append("No matching mods found.")
        lines.append("")
        lines.append("Recommended next step:")
        lines.append("- Try a broader search term (mod name, UniqueID, or author).")
        return "\n".join(lines)

    lines.append("Search results:")
    for entry in result.results:
        correlation = _match_discovery_correlation(correlations, entry.unique_id)
        lines.append(
            "- "
            f"{entry.name} | UniqueID: {entry.unique_id} | "
            f"source={_discovery_source_provider_label(entry.source_provider)} | "
            f"compatibility={_discovery_compatibility_label(entry.compatibility_state)} "
            f"(code: {entry.compatibility_state})"
        )
        lines.append(f"  author: {entry.author}")
        lines.append(f"  source context: {_discovery_source_context_text(entry)}")
        if entry.compatibility_summary:
            lines.append(f"  compatibility note: {entry.compatibility_summary}")
        if correlation is not None:
            lines.append(f"  app context: {correlation.context_summary}")
            if correlation.provider_relation_note:
                lines.append(f"  provider relation: {correlation.provider_relation_note}")
            lines.append(f"  next-step hint: {correlation.next_step}")
        if entry.source_page_url:
            lines.append(f"  page: {entry.source_page_url}")
        else:
            lines.append("  page: <not available>")

    lines.append("")
    lines.append("Recommended next step:")
    lines.append("- Select a discovery result row and click Open discovered page.")
    lines.append("- Follow manual flow: open page -> download zip -> watcher detects -> review intake -> plan/apply safely.")
    return "\n".join(lines)


def build_downloads_intake_text(result: DownloadsWatchPollResult) -> str:
    lines: list[str] = []
    lines.append("Downloads Intake")
    lines.append(f"- Watched downloads path: {result.watched_path}")
    lines.append(f"- Known zip files: {len(result.known_zip_paths)}")
    lines.append("- Manifest dependency preflight stays blocking; remote requirements are guidance only.")
    lines.append("")

    if not result.intakes:
        lines.append("No new zip packages detected.")
        lines.append("Recommended next step: keep watcher running, then add new zip files.")
        return "\n".join(lines)

    lines.append(
        "- Intake summary: "
        + _intake_classification_summary(result.intakes)
    )
    lines.append("")
    lines.append("New package intake results:")
    for intake in result.intakes:
        lines.extend(_format_single_intake(intake))

    return "\n".join(lines)


def _format_single_intake(intake: DownloadsIntakeResult) -> list[str]:
    lines: list[str] = []
    lines.append(
        "- "
        f"{intake.package_path.name} | classification={_intake_classification_label(intake.classification)} "
        f"(code: {intake.classification})"
    )
    lines.append(f"  message: {intake.message}")
    lines.append(f"  recommended next step: {_intake_next_action(intake.classification)}")

    if intake.mods:
        for mod in intake.mods:
            lines.append(f"  mod: {mod.name} | {mod.unique_id} | {mod.version}")
    else:
        lines.append("  mod: <none>")

    if intake.matched_installed_unique_ids:
        matches = ", ".join(intake.matched_installed_unique_ids)
        lines.append(f"  installed-match: {matches}")

    for warning in intake.warnings:
        lines.append(
            f"  warning [{_warning_code_label(warning.code)} / code: {warning.code}]: {warning.message}"
        )

    for finding in intake.findings:
        lines.append(
            f"  finding [{_package_finding_label(finding.kind)} / code: {finding.kind}]: {finding.message}"
        )

    dependency_summary = _dependency_summary(intake.dependency_findings)
    if dependency_summary:
        lines.append(f"  dependency-summary: {dependency_summary}")
        for detail in _intake_dependency_details(intake.dependency_findings):
            lines.append(f"  dependency: {detail}")

    remote_summary = _remote_requirements_summary(intake.remote_requirements)
    if remote_summary:
        lines.append(f"  remote-requirements-summary: {remote_summary}")
        for detail in _remote_requirement_details(intake.remote_requirements):
            lines.append(f"  remote-requirement: {detail}")

    return lines


def _intake_next_action(classification: str) -> str:
    if classification == "unusable_package":
        return "Not actionable. Inspect/fix this package or choose a different zip."
    if classification == "multi_mod_package":
        return "Actionable. Plan install and review every entry before executing."
    if classification == "update_replace_candidate":
        return "Actionable. Use Stage update to preselect archive-aware replace, then review the plan."
    return "Actionable. Plan install for the selected destination."


def _dependency_summary(findings: tuple[DependencyPreflightFinding, ...]) -> str:
    if not findings:
        return ""

    required_missing = sum(
        1 for finding in findings if finding.state == MISSING_REQUIRED_DEPENDENCY
    )
    optional_missing = sum(
        1 for finding in findings if finding.state == OPTIONAL_DEPENDENCY_MISSING
    )
    unresolved = sum(
        1 for finding in findings if finding.state == UNRESOLVED_DEPENDENCY_CONTEXT
    )
    satisfied = sum(1 for finding in findings if finding.state == SATISFIED)

    return (
        f"satisfied={satisfied}, "
        f"missing_required={required_missing}, "
        f"optional_missing={optional_missing}, "
        f"unresolved={unresolved}"
    )


def _intake_dependency_details(
    findings: tuple[DependencyPreflightFinding, ...],
) -> tuple[str, ...]:
    details: list[str] = []
    for finding in findings:
        if finding.state == MISSING_REQUIRED_DEPENDENCY:
            details.append(
                f"{finding.required_by_unique_id} missing required {finding.dependency_unique_id}; install dependency first"
            )
        elif finding.state == OPTIONAL_DEPENDENCY_MISSING:
            details.append(
                f"{finding.required_by_unique_id} missing optional {finding.dependency_unique_id}"
            )
        elif finding.state == UNRESOLVED_DEPENDENCY_CONTEXT:
            details.append(
                f"{finding.required_by_unique_id} unresolved dependency context for {finding.dependency_unique_id}"
            )

    return tuple(details)


def build_remote_requirement_guidance_text(
    *,
    title: str,
    guidance: tuple[RemoteRequirementGuidance, ...],
) -> str:
    lines: list[str] = [title]
    if not guidance:
        lines.append("- none")
        return "\n".join(lines)

    for item in guidance:
        provider = item.provider or "none"
        lines.append(
            "- "
            f"{item.name} ({item.unique_id}) | provider={provider} | "
            f"state={_remote_requirements_state_label(item.state)} (code: {item.state})"
        )
        if item.requirements:
            joined = "; ".join(item.requirements)
            lines.append(f"  requirements: {joined}")
        if item.message:
            lines.append(f"  note: {item.message}")
        if item.remote_link is not None:
            lines.append(f"  remote: {item.remote_link.page_url}")

    return "\n".join(lines)


def _format_remote_requirements_inline(
    requirements: tuple[str, ...],
    message: str | None,
) -> str:
    if requirements:
        return "; ".join(requirements)
    if message:
        return message
    return "unavailable"


def _remote_requirements_summary(guidance: tuple[RemoteRequirementGuidance, ...]) -> str:
    if not guidance:
        return ""

    present = sum(1 for item in guidance if item.state == REQUIREMENTS_PRESENT)
    absent = sum(1 for item in guidance if item.state == REQUIREMENTS_ABSENT)
    unavailable = sum(1 for item in guidance if item.state == REQUIREMENTS_UNAVAILABLE)
    no_link = sum(1 for item in guidance if item.state == NO_REMOTE_LINK_FOR_REQUIREMENTS)
    return (
        f"present={present}, "
        f"absent={absent}, "
        f"unavailable={unavailable}, "
        f"no_link={no_link}"
    )


def _remote_requirement_details(
    guidance: tuple[RemoteRequirementGuidance, ...],
) -> tuple[str, ...]:
    details: list[str] = []
    for item in guidance:
        if item.state == REQUIREMENTS_PRESENT:
            details.append(
                f"{item.unique_id} remote requirements: {', '.join(item.requirements)}"
            )
        elif item.state == REQUIREMENTS_ABSENT:
            details.append(f"{item.unique_id} remote requirements: none declared by source")
        elif item.state == NO_REMOTE_LINK_FOR_REQUIREMENTS:
            details.append(f"{item.unique_id} remote requirements: no remote link")
        elif item.state == REQUIREMENTS_UNAVAILABLE:
            details.append(
                f"{item.unique_id} remote requirements unavailable: {item.message or 'provider error'}"
            )

    return tuple(details)


def build_intake_correlation_text(correlations: tuple[IntakeUpdateCorrelation, ...]) -> str:
    lines: list[str] = []
    lines.append("Intake and Update Correlation")

    if not correlations:
        lines.append("- none")
        return "\n".join(lines)

    for correlation in correlations:
        lines.append(f"- {correlation.intake.package_path.name}: {correlation.summary}")
        lines.append(f"  next-step: {correlation.next_step}")

    return "\n".join(lines)


def _environment_state_label(state: str) -> str:
    labels = {
        GAME_PATH_DETECTED: "Game installation path detected",
        MODS_PATH_DETECTED: "Mods folder detected",
        SMAPI_DETECTED: "SMAPI detected",
        SMAPI_NOT_DETECTED: "SMAPI not detected",
        INVALID_GAME_PATH: "Invalid game path",
    }
    return labels.get(state, state.replace("_", " ").title())


def _smapi_update_state_label(state: str) -> str:
    labels = {
        SMAPI_NOT_DETECTED_FOR_UPDATE: "SMAPI not detected",
        SMAPI_DETECTED_VERSION_KNOWN: "SMAPI detected (version known)",
        SMAPI_UPDATE_AVAILABLE: "SMAPI update available",
        SMAPI_UP_TO_DATE: "SMAPI up to date",
        SMAPI_UNABLE_TO_DETERMINE: "Unable to determine SMAPI status",
    }
    return labels.get(state, state.replace("_", " ").title())


def _smapi_log_state_label(state: str) -> str:
    labels = {
        SMAPI_LOG_NOT_FOUND: "Log not found",
        SMAPI_LOG_PARSED: "Log parsed",
        SMAPI_LOG_UNABLE_TO_DETERMINE: "Unable to determine",
    }
    return labels.get(state, state.replace("_", " ").title())


def _smapi_log_source_label(source: str) -> str:
    labels = {
        SMAPI_LOG_SOURCE_AUTO_DETECTED: "Auto-detected log path",
        SMAPI_LOG_SOURCE_MANUAL: "Manually selected log path",
        SMAPI_LOG_SOURCE_NONE: "No log source",
    }
    return labels.get(source, source.replace("_", " ").title())


def _smapi_log_finding_kind_label(kind: str) -> str:
    labels = {
        SMAPI_LOG_ERROR: "Error",
        SMAPI_LOG_WARNING: "Warning",
        SMAPI_LOG_FAILED_MOD: "Failed mod",
        SMAPI_LOG_MISSING_DEPENDENCY: "Missing dependency",
        SMAPI_LOG_RUNTIME_ISSUE: "Runtime issue",
    }
    return labels.get(kind, kind.replace("_", " ").title())


def _smapi_log_findings_count(report: SmapiLogReport) -> dict[str, int]:
    counts = {
        SMAPI_LOG_ERROR: 0,
        SMAPI_LOG_WARNING: 0,
        SMAPI_LOG_FAILED_MOD: 0,
        SMAPI_LOG_MISSING_DEPENDENCY: 0,
        SMAPI_LOG_RUNTIME_ISSUE: 0,
    }
    for finding in report.findings:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1
    return counts


def _scan_entry_kind_label(kind: str) -> str:
    labels = {
        "direct_mod": "Direct mod folder",
        "nested_mod_container": "Nested container with mod",
        "multi_mod_container": "Container with multiple mods",
        "missing_manifest": "No usable manifest found",
        "invalid_manifest": "Invalid manifest",
    }
    return labels.get(kind, kind.replace("_", " ").title())


def _warning_code_label(code: str) -> str:
    labels = {
        "missing_manifest": "Missing manifest",
        "malformed_manifest": "Malformed manifest JSON",
        "invalid_manifest": "Invalid manifest data",
        "manifest_read_error": "Manifest read error",
        "invalid_dependency_entry": "Invalid dependency entry",
    }
    return labels.get(code, code.replace("_", " ").title())


def _package_finding_label(kind: str) -> str:
    labels = {
        "direct_single_mod_package": "Direct single-mod package",
        "nested_single_mod_package": "Nested single-mod package",
        "multi_mod_package": "Multi-mod package",
        "invalid_manifest_package": "Invalid manifest package",
        "no_usable_manifest_found": "No usable manifest found",
        "too_deep_unsupported_package": "Unsupported deep package layout",
    }
    return labels.get(kind, kind.replace("_", " ").title())


def _update_state_label(state: str) -> str:
    labels = {
        "up_to_date": "Up to date",
        "update_available": "Update available",
        "no_remote_link": "No remote link",
        "metadata_unavailable": "Metadata unavailable",
    }
    return labels.get(state, state.replace("_", " ").title())


def _dependency_state_label(state: str) -> str:
    labels = {
        SATISFIED: "Satisfied",
        MISSING_REQUIRED_DEPENDENCY: "Missing required dependency",
        OPTIONAL_DEPENDENCY_MISSING: "Optional dependency missing",
        UNRESOLVED_DEPENDENCY_CONTEXT: "Dependency context unresolved",
    }
    return labels.get(state, state.replace("_", " ").title())


def _remote_requirements_state_label(state: str) -> str:
    labels = {
        REQUIREMENTS_PRESENT: "Requirements present",
        REQUIREMENTS_ABSENT: "No requirements declared",
        REQUIREMENTS_UNAVAILABLE: "Requirements unavailable",
        NO_REMOTE_LINK_FOR_REQUIREMENTS: "No remote link",
    }
    return labels.get(state, state.replace("_", " ").title())


def _discovery_compatibility_label(state: str) -> str:
    labels = {
        "compatible": "Compatible",
        "compatible_with_caveat": "Compatible with caveat",
        "unofficial_update": "Use unofficial update",
        "workaround_available": "Use workaround",
        "incompatible": "Incompatible",
        "abandoned": "Abandoned",
        "obsolete": "Obsolete",
        "compatibility_unknown": "Compatibility unknown",
    }
    return labels.get(state, state.replace("_", " ").title())


def _discovery_source_provider_label(provider: str) -> str:
    labels = {
        "nexus": "Nexus",
        "github": "GitHub",
        "custom_url": "Custom URL",
        "none": "No source link",
    }
    return labels.get(provider, provider.replace("_", " ").title())


def _discovery_source_context_text(entry: ModDiscoveryEntry) -> str:
    if entry.source_provider == "nexus":
        return "Nexus listing from compatibility index"
    if entry.source_provider == "github":
        return "GitHub repository from compatibility index"
    if entry.source_provider == "custom_url":
        return "Custom source URL from compatibility index"
    return "No source link listed in compatibility index"


def _match_discovery_correlation(
    correlations: tuple[DiscoveryContextCorrelation, ...],
    unique_id: str,
) -> DiscoveryContextCorrelation | None:
    lookup = unique_id.casefold()
    for item in correlations:
        if item.entry.unique_id.casefold() == lookup:
            return item
    return None


def _install_action_label(action: str) -> str:
    labels = {
        "install_new": "install new",
        "overwrite_with_archive": "overwrite (archive first)",
        "blocked": "blocked",
    }
    return labels.get(action, action.replace("_", " "))


def _install_destination_label(destination_kind: str) -> str:
    labels = {
        "configured_real_mods": "Game Mods destination (real)",
        "sandbox_mods": "Sandbox Mods destination",
    }
    return labels.get(destination_kind, destination_kind.replace("_", " ").title())


def _archive_source_label(source_kind: str) -> str:
    labels = {
        "real_archive": "Real archive",
        "sandbox_archive": "Sandbox archive",
    }
    return labels.get(source_kind, source_kind.replace("_", " ").title())


def _intake_classification_label(classification: str) -> str:
    labels = {
        "new_install_candidate": "New install candidate",
        "update_replace_candidate": "Update/replace candidate",
        "multi_mod_package": "Multi-mod package",
        "unusable_package": "Unusable package",
    }
    return labels.get(classification, classification.replace("_", " ").title())


def _intake_classification_summary(intakes: tuple[DownloadsIntakeResult, ...]) -> str:
    counts: dict[str, int] = {}
    for intake in intakes:
        counts[intake.classification] = counts.get(intake.classification, 0) + 1

    order = (
        "new_install_candidate",
        "update_replace_candidate",
        "multi_mod_package",
        "unusable_package",
    )
    parts = [
        f"{_intake_classification_label(key)}: {counts[key]}"
        for key in order
        if counts.get(key, 0) > 0
    ]
    return ", ".join(parts) if parts else "none"
