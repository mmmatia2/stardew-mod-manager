from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sdvmm.domain.discovery_codes import (
    DiscoveryCompatibilityState,
    DiscoveryProvider,
    DiscoverySourceProvider,
)
from sdvmm.domain.dependency_codes import DependencyState
from sdvmm.domain.environment_codes import EnvironmentState
from sdvmm.domain.install_codes import SandboxInstallAction
from sdvmm.domain.nexus_codes import NexusCredentialSource, NexusIntegrationState
from sdvmm.domain.package_codes import PackageFindingKind
from sdvmm.domain.remote_requirement_codes import RemoteRequirementState
from sdvmm.domain.scan_codes import ScanEntryKind
from sdvmm.domain.smapi_log_codes import (
    SmapiLogFindingKind,
    SmapiLogSourceKind,
    SmapiLogStatusState,
)
from sdvmm.domain.smapi_codes import SmapiUpdateState
from sdvmm.domain.update_codes import RemoteLinkProvider, UpdateState
from sdvmm.domain.warning_codes import ParseWarningCode


@dataclass(frozen=True, slots=True)
class AppConfig:
    game_path: Path
    mods_path: Path
    app_data_path: Path
    sandbox_mods_path: Path | None = None
    sandbox_archive_path: Path | None = None
    real_archive_path: Path | None = None
    watched_downloads_path: Path | None = None
    nexus_api_key: str | None = None
    scan_target: str = "configured_real_mods"
    install_target: str = "sandbox_mods"


@dataclass(frozen=True, slots=True)
class NexusIntegrationStatus:
    state: NexusIntegrationState
    source: NexusCredentialSource
    masked_key: str | None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class GameEnvironmentStatus:
    game_path: Path
    mods_path: Path | None
    smapi_path: Path | None
    state_codes: tuple[EnvironmentState, ...]
    notes: tuple[str, ...] = tuple()


@dataclass(frozen=True, slots=True)
class SmapiUpdateStatus:
    state: SmapiUpdateState
    game_path: Path
    smapi_path: Path | None
    installed_version: str | None
    latest_version: str | None
    update_page_url: str
    message: str


@dataclass(frozen=True, slots=True)
class SmapiLogFinding:
    kind: SmapiLogFindingKind
    line_number: int
    message: str


@dataclass(frozen=True, slots=True)
class SmapiLogReport:
    state: SmapiLogStatusState
    source: SmapiLogSourceKind
    log_path: Path | None
    game_path: Path | None
    findings: tuple[SmapiLogFinding, ...]
    notes: tuple[str, ...] = tuple()
    message: str | None = None


@dataclass(frozen=True, slots=True)
class PathValidationIssue:
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class AppConfigValidationResult:
    is_valid: bool
    issues: tuple[PathValidationIssue, ...]


@dataclass(frozen=True, slots=True)
class ManifestDependency:
    unique_id: str
    required: bool


@dataclass(frozen=True, slots=True)
class ModManifest:
    unique_id: str
    name: str
    version: str
    dependencies: tuple[ManifestDependency, ...]
    update_keys: tuple[str, ...] = tuple()


@dataclass(frozen=True, slots=True)
class ParseWarning:
    code: ParseWarningCode
    message: str
    mod_path: Path
    manifest_path: Path | None = None


@dataclass(frozen=True, slots=True)
class ManifestParseResult:
    manifest: ModManifest | None
    warnings: tuple[ParseWarning, ...]


@dataclass(frozen=True, slots=True)
class InstalledMod:
    unique_id: str
    name: str
    version: str
    folder_path: Path
    manifest_path: Path
    dependencies: tuple[ManifestDependency, ...]
    update_keys: tuple[str, ...] = tuple()


@dataclass(frozen=True, slots=True)
class RemoteModLink:
    provider: RemoteLinkProvider
    key: str
    page_url: str
    metadata_url: str | None


@dataclass(frozen=True, slots=True)
class ModUpdateStatus:
    unique_id: str
    name: str
    folder_path: Path
    installed_version: str
    remote_version: str | None
    state: UpdateState
    remote_link: RemoteModLink | None
    message: str | None = None
    remote_requirements_state: RemoteRequirementState = "requirements_unavailable"
    remote_requirements: tuple[str, ...] = tuple()
    remote_requirements_message: str | None = None


@dataclass(frozen=True, slots=True)
class ModUpdateReport:
    statuses: tuple[ModUpdateStatus, ...]


@dataclass(frozen=True, slots=True)
class ModDiscoveryEntry:
    name: str
    unique_id: str
    author: str
    provider: DiscoveryProvider
    source_provider: DiscoverySourceProvider
    source_page_url: str | None
    compatibility_state: DiscoveryCompatibilityState
    compatibility_status: str
    compatibility_summary: str | None = None
    alternate_names: tuple[str, ...] = tuple()
    alternate_unique_ids: tuple[str, ...] = tuple()


@dataclass(frozen=True, slots=True)
class ModDiscoveryResult:
    query: str
    provider: DiscoveryProvider
    results: tuple[ModDiscoveryEntry, ...]
    notes: tuple[str, ...] = tuple()


RemoteRequirementContextSource = Literal[
    "package_inspection",
    "downloads_intake",
    "sandbox_plan",
]


@dataclass(frozen=True, slots=True)
class RemoteRequirementGuidance:
    source: RemoteRequirementContextSource
    unique_id: str
    name: str
    provider: RemoteLinkProvider | None
    state: RemoteRequirementState
    requirements: tuple[str, ...]
    remote_link: RemoteModLink | None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class DuplicateUniqueIdFinding:
    unique_id: str
    folder_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class MissingDependencyFinding:
    required_by_unique_id: str
    required_by_folder: Path
    missing_unique_id: str


DependencyContextSource = Literal[
    "installed_inventory",
    "package_inspection",
    "downloads_intake",
    "sandbox_plan",
]


@dataclass(frozen=True, slots=True)
class DependencyPreflightFinding:
    source: DependencyContextSource
    state: DependencyState
    required_by_unique_id: str
    required_by_name: str
    dependency_unique_id: str
    required: bool


@dataclass(frozen=True, slots=True)
class ScanEntryFinding:
    kind: ScanEntryKind
    entry_path: Path
    mod_paths: tuple[Path, ...]
    message: str


@dataclass(frozen=True, slots=True)
class PackageModEntry:
    name: str
    unique_id: str
    version: str
    manifest_path: str
    dependencies: tuple[ManifestDependency, ...] = tuple()
    update_keys: tuple[str, ...] = tuple()


@dataclass(frozen=True, slots=True)
class PackageWarning:
    code: ParseWarningCode
    message: str
    manifest_path: str


@dataclass(frozen=True, slots=True)
class PackageFinding:
    kind: PackageFindingKind
    message: str
    related_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PackageInspectionResult:
    package_path: Path
    mods: tuple[PackageModEntry, ...]
    warnings: tuple[PackageWarning, ...]
    findings: tuple[PackageFinding, ...]
    dependency_findings: tuple[DependencyPreflightFinding, ...] = tuple()
    remote_requirements: tuple[RemoteRequirementGuidance, ...] = tuple()


IntakeClassification = Literal[
    "new_install_candidate",
    "update_replace_candidate",
    "multi_mod_package",
    "unusable_package",
]

InstallExecutionDecisionCode = Literal[
    "sandbox_allowed",
    "real_approval_required",
    "blocked_entries_present",
]

InstallRecoveryActionCode = Literal[
    "remove_installed_target",
    "restore_from_archive",
    "not_recoverable",
]


@dataclass(frozen=True, slots=True)
class DownloadsIntakeResult:
    package_path: Path
    classification: IntakeClassification
    message: str
    mods: tuple[PackageModEntry, ...]
    matched_installed_unique_ids: tuple[str, ...]
    warnings: tuple[PackageWarning, ...]
    findings: tuple[PackageFinding, ...]
    dependency_findings: tuple[DependencyPreflightFinding, ...] = tuple()
    remote_requirements: tuple[RemoteRequirementGuidance, ...] = tuple()


@dataclass(frozen=True, slots=True)
class DownloadsWatchPollResult:
    watched_path: Path
    known_zip_paths: tuple[Path, ...]
    intakes: tuple[DownloadsIntakeResult, ...]


@dataclass(frozen=True, slots=True)
class SandboxInstallPlanEntry:
    name: str
    unique_id: str
    version: str
    source_manifest_path: str
    source_root_path: str
    target_path: Path
    action: SandboxInstallAction
    target_exists: bool
    archive_path: Path | None
    can_install: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SandboxInstallPlan:
    package_path: Path
    sandbox_mods_path: Path
    sandbox_archive_path: Path
    entries: tuple[SandboxInstallPlanEntry, ...]
    package_findings: tuple[PackageFinding, ...]
    package_warnings: tuple[PackageWarning, ...]
    plan_warnings: tuple[str, ...]
    dependency_findings: tuple[DependencyPreflightFinding, ...] = tuple()
    remote_requirements: tuple[RemoteRequirementGuidance, ...] = tuple()
    destination_kind: str = "sandbox_mods"


@dataclass(frozen=True, slots=True)
class SandboxInstallResult:
    plan: SandboxInstallPlan
    installed_targets: tuple[Path, ...]
    archived_targets: tuple[Path, ...]
    scan_context_path: Path
    inventory: ModsInventory
    destination_kind: str = "sandbox_mods"


@dataclass(frozen=True, slots=True)
class InstallExecutionActionCount:
    action: SandboxInstallAction
    count: int


@dataclass(frozen=True, slots=True)
class InstallExecutionSummary:
    destination_kind: str
    destination_mods_path: Path
    archive_path: Path
    total_entry_count: int
    action_counts: tuple[InstallExecutionActionCount, ...]
    has_existing_targets_to_replace: bool
    has_archive_writes: bool
    requires_explicit_confirmation: bool
    review_warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InstallExecutionReview:
    summary: InstallExecutionSummary
    allowed: bool
    requires_explicit_approval: bool
    decision_code: InstallExecutionDecisionCode
    message: str


@dataclass(frozen=True, slots=True)
class InstallOperationEntryRecord:
    name: str
    unique_id: str
    version: str
    action: SandboxInstallAction
    target_path: Path
    archive_path: Path | None
    source_manifest_path: str
    source_root_path: str
    target_exists_before: bool
    can_install: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InstallOperationRecord:
    timestamp: str
    package_path: Path
    destination_kind: str
    destination_mods_path: Path
    archive_path: Path
    installed_targets: tuple[Path, ...]
    archived_targets: tuple[Path, ...]
    entries: tuple[InstallOperationEntryRecord, ...]


@dataclass(frozen=True, slots=True)
class InstallOperationHistory:
    operations: tuple[InstallOperationRecord, ...]


@dataclass(frozen=True, slots=True)
class InstallRecoveryPlanEntry:
    name: str
    unique_id: str
    version: str
    action: InstallRecoveryActionCode
    target_path: Path
    archive_path: Path | None
    recoverable: bool
    message: str
    warnings: tuple[str, ...] = tuple()


@dataclass(frozen=True, slots=True)
class InstallRecoveryPlanSummary:
    total_recovery_entry_count: int
    recoverable_entry_count: int
    non_recoverable_entry_count: int
    involves_archive_restore: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InstallRecoveryPlan:
    operation: InstallOperationRecord
    entries: tuple[InstallRecoveryPlanEntry, ...]
    summary: InstallRecoveryPlanSummary


@dataclass(frozen=True, slots=True)
class ModRemovalPlan:
    destination_kind: str
    mods_path: Path
    archive_path: Path
    target_mod_path: Path


@dataclass(frozen=True, slots=True)
class ModRemovalResult:
    plan: ModRemovalPlan
    removed_target: Path
    archived_target: Path
    scan_context_path: Path
    inventory: ModsInventory
    destination_kind: str = "sandbox_mods"


@dataclass(frozen=True, slots=True)
class ArchivedModEntry:
    source_kind: str
    archive_root: Path
    archived_path: Path
    archived_folder_name: str
    target_folder_name: str
    mod_name: str | None = None
    unique_id: str | None = None
    version: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ArchiveRestorePlan:
    entry: ArchivedModEntry
    destination_kind: str
    destination_mods_path: Path
    destination_target_path: Path
    scan_excluded_paths: tuple[Path, ...] = tuple()


@dataclass(frozen=True, slots=True)
class ArchiveRestoreResult:
    plan: ArchiveRestorePlan
    restored_target: Path
    scan_context_path: Path
    inventory: ModsInventory
    destination_kind: str = "sandbox_mods"


@dataclass(frozen=True, slots=True)
class ArchiveDeletePlan:
    entry: ArchivedModEntry


@dataclass(frozen=True, slots=True)
class ArchiveDeleteResult:
    plan: ArchiveDeletePlan
    deleted_path: Path


@dataclass(frozen=True, slots=True)
class ModRollbackPlan:
    destination_kind: str
    mods_path: Path
    archive_path: Path
    current_mod_path: Path
    current_unique_id: str
    current_version: str
    rollback_entry: ArchivedModEntry
    current_archive_path: Path


@dataclass(frozen=True, slots=True)
class ModRollbackResult:
    plan: ModRollbackPlan
    archived_current_target: Path
    restored_target: Path
    scan_context_path: Path
    inventory: ModsInventory
    destination_kind: str = "sandbox_mods"


@dataclass(frozen=True, slots=True)
class ModsInventory:
    mods: tuple[InstalledMod, ...]
    parse_warnings: tuple[ParseWarning, ...]
    duplicate_unique_ids: tuple[DuplicateUniqueIdFinding, ...]
    missing_required_dependencies: tuple[MissingDependencyFinding, ...]
    scan_entry_findings: tuple[ScanEntryFinding, ...]
    ignored_entries: tuple[Path, ...]
