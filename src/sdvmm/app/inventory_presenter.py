from __future__ import annotations

from sdvmm.app.shell_service import IntakeUpdateCorrelation
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
    DependencyPreflightFinding,
    DownloadsIntakeResult,
    DownloadsWatchPollResult,
    GameEnvironmentStatus,
    ModUpdateReport,
    ModsInventory,
    PackageInspectionResult,
    RemoteRequirementGuidance,
    SandboxInstallPlan,
    SandboxInstallResult,
)
from sdvmm.domain.remote_requirement_codes import (
    NO_REMOTE_LINK_FOR_REQUIREMENTS,
    REQUIREMENTS_ABSENT,
    REQUIREMENTS_PRESENT,
    REQUIREMENTS_UNAVAILABLE,
)


def build_findings_text(inventory: ModsInventory) -> str:
    lines: list[str] = []

    if inventory.scan_entry_findings:
        lines.append("Scan entry findings:")
        for finding in inventory.scan_entry_findings:
            kind = finding.kind.replace("_", " ")
            lines.append(f"- [{kind}] {finding.entry_path.name}: {finding.message}")
    else:
        lines.append("Scan entry findings: none")

    lines.append("")

    if inventory.parse_warnings:
        lines.append("Warnings:")
        for warning in inventory.parse_warnings:
            lines.append(
                f"- [{warning.code}] {warning.mod_path.name}: {warning.message}"
            )
    else:
        lines.append("Warnings: none")

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

    return "\n".join(lines)


def build_environment_status_text(status: GameEnvironmentStatus) -> str:
    lines: list[str] = []
    lines.append(f"Game path: {status.game_path}")

    for state in status.state_codes:
        lines.append(f"- [{state}]")

    if status.mods_path is not None:
        lines.append(f"Detected Mods path: {status.mods_path}")
    else:
        lines.append("Detected Mods path: <not detected>")

    if status.smapi_path is not None:
        lines.append(f"Detected SMAPI path: {status.smapi_path}")
    else:
        lines.append("Detected SMAPI path: <not detected>")

    for note in status.notes:
        lines.append(f"- note: {note}")

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
        lines.append(f"- [{state}] {len(entries)}")
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
    lines.append(f"Package: {result.package_path.name}")

    lines.append("")
    if result.mods:
        lines.append("Detected package mods:")
        for mod in result.mods:
            lines.append(
                f"- {mod.name} | {mod.unique_id} | {mod.version} | {mod.manifest_path}"
            )
    else:
        lines.append("Detected package mods: none")

    lines.append("")
    if result.findings:
        lines.append("Package findings:")
        for finding in result.findings:
            kind = finding.kind.replace("_", " ")
            lines.append(f"- [{kind}] {finding.message}")
    else:
        lines.append("Package findings: none")

    lines.append("")
    if result.warnings:
        lines.append("Package warnings:")
        for warning in result.warnings:
            lines.append(f"- [{warning.code}] {warning.manifest_path}: {warning.message}")
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

    return "\n".join(lines)


def build_sandbox_install_plan_text(plan: SandboxInstallPlan) -> str:
    lines: list[str] = []
    lines.append(f"Sandbox target: {plan.sandbox_mods_path}")
    lines.append(f"Sandbox archive: {plan.sandbox_archive_path}")
    lines.append(f"Package: {plan.package_path.name}")
    lines.append("")

    if plan.entries:
        lines.append("Install plan entries:")
        for entry in plan.entries:
            status = "new" if not entry.target_exists else "exists"
            action = entry.action.replace("_", " ")
            executable = "installable" if entry.can_install else "blocked"
            lines.append(
                "- "
                f"{entry.name} | {entry.unique_id} | {entry.version}"
                f" -> {entry.target_path.name} ({status}, {action}, {executable})"
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
            lines.append(f"- [{finding.kind}] {finding.message}")
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

    return "\n".join(lines)


def build_sandbox_install_result_text(result: SandboxInstallResult) -> str:
    lines: list[str] = []
    lines.append("Sandbox install completed.")
    lines.append(f"Scan context: {result.scan_context_path}")
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


def build_update_report_text(report: ModUpdateReport) -> str:
    lines: list[str] = []
    lines.append("Mod metadata/update status:")
    lines.append("Manifest dependency blocking is separate from remote requirement guidance.")

    if not report.statuses:
        lines.append("- No installed mods in current inventory.")
        return "\n".join(lines)

    for status in report.statuses:
        remote_version = status.remote_version or "unknown"
        lines.append(
            "- "
            f"{status.name} | {status.unique_id} | "
            f"installed={status.installed_version} | remote={remote_version} | state={status.state}"
        )
        if status.remote_link is not None:
            lines.append(f"  remote: {status.remote_link.page_url}")
        if status.message:
            lines.append(f"  note: {status.message}")
        lines.append(
            f"  remote-requirements[{status.remote_requirements_state}]: "
            f"{_format_remote_requirements_inline(status.remote_requirements, status.remote_requirements_message)}"
        )

    return "\n".join(lines)


def build_downloads_intake_text(result: DownloadsWatchPollResult) -> str:
    lines: list[str] = []
    lines.append(f"Watched downloads: {result.watched_path}")
    lines.append(f"Known zip files: {len(result.known_zip_paths)}")
    lines.append("Manifest dependency preflight stays blocking; remote requirements are guidance only.")
    lines.append("")

    if not result.intakes:
        lines.append("No new zip packages detected.")
        return "\n".join(lines)

    lines.append("New package intake results:")
    for intake in result.intakes:
        lines.extend(_format_single_intake(intake))

    return "\n".join(lines)


def _format_single_intake(intake: DownloadsIntakeResult) -> list[str]:
    lines: list[str] = []
    lines.append(
        "- "
        f"{intake.package_path.name} | classification={intake.classification}"
    )
    lines.append(f"  message: {intake.message}")
    lines.append(f"  next-action: {_intake_next_action(intake.classification)}")

    if intake.mods:
        for mod in intake.mods:
            lines.append(f"  mod: {mod.name} | {mod.unique_id} | {mod.version}")
    else:
        lines.append("  mod: <none>")

    if intake.matched_installed_unique_ids:
        matches = ", ".join(intake.matched_installed_unique_ids)
        lines.append(f"  installed-match: {matches}")

    for warning in intake.warnings:
        lines.append(f"  warning[{warning.code}]: {warning.message}")

    for finding in intake.findings:
        lines.append(f"  finding[{finding.kind}]: {finding.message}")

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
        return "non-actionable (inspect/fix package)"
    if classification == "multi_mod_package":
        return "actionable (plan install and review all entries)"
    if classification == "update_replace_candidate":
        return "actionable (plan install, review overwrite/archive preflight)"
    return "actionable (plan install)"


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
            f"{item.name} ({item.unique_id}) | provider={provider} | state={item.state}"
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
    lines.append("Intake update-flow guidance:")

    if not correlations:
        lines.append("- none")
        return "\n".join(lines)

    for correlation in correlations:
        lines.append(f"- {correlation.intake.package_path.name}: {correlation.summary}")
        lines.append(f"  next-step: {correlation.next_step}")

    return "\n".join(lines)
