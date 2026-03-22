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
from sdvmm.domain.update_codes import (
    RemoteLinkProvider,
    UpdateSourceDiagnosticCode,
    UpdateState,
)
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
    secondary_watched_downloads_path: Path | None = None
    nexus_api_key: str | None = None
    scan_target: str = "configured_real_mods"
    install_target: str = "sandbox_mods"
    steam_auto_start_enabled: bool = True


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
    update_source_diagnostic: UpdateSourceDiagnosticCode | None = None
    message: str | None = None
    remote_requirements_state: RemoteRequirementState = "requirements_unavailable"
    remote_requirements: tuple[str, ...] = tuple()
    remote_requirements_message: str | None = None


@dataclass(frozen=True, slots=True)
class ModUpdateReport:
    statuses: tuple[ModUpdateStatus, ...]


ModsCompareState = Literal[
    "only_in_real",
    "only_in_sandbox",
    "same_version",
    "version_mismatch",
    "ambiguous_match",
]


@dataclass(frozen=True, slots=True)
class ModsCompareEntry:
    match_key: str
    name: str
    state: ModsCompareState
    real_mod: InstalledMod | None
    sandbox_mod: InstalledMod | None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ModsCompareResult:
    real_mods_path: Path
    sandbox_mods_path: Path
    real_inventory: "ModsInventory"
    sandbox_inventory: "ModsInventory"
    entries: tuple[ModsCompareEntry, ...]


BackupBundleItemKind = Literal["file", "directory"]
BackupBundleDeclaredStatus = Literal[
    "copied",
    "not_present",
    "not_configured",
    "configured_missing",
]
BackupBundleStructureState = Literal[
    "present",
    "absent_as_declared",
    "missing_expected",
    "unexpected_present",
]


@dataclass(frozen=True, slots=True)
class BackupBundleInspectionItem:
    key: str
    label: str
    kind: BackupBundleItemKind
    declared_status: BackupBundleDeclaredStatus
    relative_path: Path
    structure_state: BackupBundleStructureState
    note: str | None = None


@dataclass(frozen=True, slots=True)
class BackupBundleInspectionResult:
    bundle_path: Path
    manifest_path: Path
    summary_path: Path
    bundle_format: str | None
    format_version: int | None
    created_at_utc: str | None
    items: tuple[BackupBundleInspectionItem, ...]
    structurally_usable: bool
    message: str
    warnings: tuple[str, ...] = tuple()
    intentionally_not_included: tuple[str, ...] = tuple()
    bundle_storage_kind: Literal["directory", "zip"] = "directory"
    content_root_path: Path | None = None


RestoreImportPlanningItemState = Literal[
    "safe_to_restore_later",
    "needs_review",
    "blocked",
]
RestoreImportPlanningModState = Literal[
    "missing_locally",
    "same_version",
    "different_version",
    "bundle_unusable",
    "destination_not_ready",
    "ambiguous_match",
]
RestoreImportPlanningConfigState = Literal[
    "missing_locally",
    "same_content",
    "different_content",
    "bundle_unusable",
    "destination_not_ready",
]


@dataclass(frozen=True, slots=True)
class RestoreImportPlanningItem:
    key: str
    label: str
    state: RestoreImportPlanningItemState
    message: str
    bundle_relative_path: Path
    local_target_path: Path | None
    bundle_declared_status: BackupBundleDeclaredStatus
    bundle_structure_state: BackupBundleStructureState
    note: str | None = None
    safe_mod_count: int = 0
    review_mod_count: int = 0
    blocked_mod_count: int = 0
    safe_config_count: int = 0
    review_config_count: int = 0
    blocked_config_count: int = 0


@dataclass(frozen=True, slots=True)
class RestoreImportPlanningModEntry:
    bundle_item_key: str
    bundle_item_label: str
    name: str
    unique_id: str
    bundle_version: str | None
    local_version: str | None
    state: RestoreImportPlanningModState
    local_target_path: Path | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class RestoreImportPlanningConfigEntry:
    bundle_item_key: str
    bundle_item_label: str
    relative_path: Path
    state: RestoreImportPlanningConfigState
    local_target_path: Path | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class RestoreImportPlanningResult:
    bundle_path: Path
    inspection: BackupBundleInspectionResult
    items: tuple[RestoreImportPlanningItem, ...]
    mod_entries: tuple[RestoreImportPlanningModEntry, ...]
    safe_item_count: int
    review_item_count: int
    blocked_item_count: int
    safe_mod_count: int
    review_mod_count: int
    blocked_mod_count: int
    message: str
    config_entries: tuple[RestoreImportPlanningConfigEntry, ...] = tuple()
    safe_config_count: int = 0
    review_config_count: int = 0
    blocked_config_count: int = 0
    warnings: tuple[str, ...] = tuple()


@dataclass(frozen=True, slots=True)
class RestoreImportExecutionReview:
    allowed: bool
    message: str
    executable_mod_count: int
    executable_config_count: int
    replace_mod_count: int = 0
    replace_config_count: int = 0
    covered_config_count: int = 0
    review_entry_count: int = 0
    blocked_entry_count: int = 0
    deferred_item_count: int = 0
    requires_explicit_confirmation: bool = True
    warnings: tuple[str, ...] = tuple()


@dataclass(frozen=True, slots=True)
class RestoreImportExecutionResult:
    bundle_path: Path
    restored_mod_paths: tuple[Path, ...]
    restored_config_paths: tuple[Path, ...]
    restored_mod_count: int
    restored_config_count: int
    archived_target_paths: tuple[Path, ...] = tuple()
    replaced_mod_count: int = 0
    replaced_config_count: int = 0
    covered_config_count: int = 0
    skipped_review_entry_count: int = 0
    skipped_blocked_entry_count: int = 0
    deferred_item_count: int = 0
    message: str = ""
    warnings: tuple[str, ...] = tuple()


UpdateSourceIntentState = Literal[
    "local_private_mod",
    "no_tracking",
    "manual_source_association",
]


@dataclass(frozen=True, slots=True)
class UpdateSourceIntentRecord:
    unique_id: str
    normalized_unique_id: str
    intent_state: UpdateSourceIntentState
    manual_provider: str | None = None
    manual_source_key: str | None = None
    manual_source_page_url: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateSourceIntentOverlay:
    records: tuple[UpdateSourceIntentRecord, ...]


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


@dataclass(frozen=True, slots=True)
class PackageInspectionBatchEntry:
    package_path: Path
    inspection: PackageInspectionResult | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class PackageInspectionBatchResult:
    entries: tuple[PackageInspectionBatchEntry, ...]


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

InstallRecoveryReviewDecisionCode = Literal[
    "removal_ready",
    "removal_target_missing",
    "restore_ready",
    "restore_archive_missing",
    "entry_not_recoverable",
]

RecoveryExecutionOutcome = Literal["completed", "failed", "failed_partial"]


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
    operation_id: str | None
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
class InstallRecoveryExecutionReviewEntry:
    plan_entry: InstallRecoveryPlanEntry
    executable: bool
    decision_code: InstallRecoveryReviewDecisionCode
    message: str


@dataclass(frozen=True, slots=True)
class InstallRecoveryExecutionReviewSummary:
    total_entry_count: int
    executable_entry_count: int
    non_executable_entry_count: int
    stale_entry_count: int
    involves_archive_restore: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InstallRecoveryExecutionReview:
    plan: InstallRecoveryPlan
    allowed: bool
    decision_code: Literal["recovery_ready", "recovery_blocked"]
    message: str
    entries: tuple[InstallRecoveryExecutionReviewEntry, ...]
    summary: InstallRecoveryExecutionReviewSummary


@dataclass(frozen=True, slots=True)
class InstallRecoveryExecutionResult:
    review: InstallRecoveryExecutionReview
    executed_entry_count: int
    removed_target_paths: tuple[Path, ...]
    restored_target_paths: tuple[Path, ...]
    destination_kind: str
    destination_mods_path: Path
    scan_context_path: Path
    inventory: ModsInventory


@dataclass(frozen=True, slots=True)
class InstallRecoveryInspectionResult:
    operation: InstallOperationRecord
    recovery_plan: InstallRecoveryPlan
    recovery_review: InstallRecoveryExecutionReview
    linked_recovery_history: tuple[RecoveryExecutionRecord, ...]


@dataclass(frozen=True, slots=True)
class RecoveryExecutionRecord:
    recovery_execution_id: str | None
    timestamp: str
    related_install_operation_id: str | None
    related_install_operation_timestamp: str | None
    related_install_package_path: Path | None
    destination_kind: str
    destination_mods_path: Path
    executed_entry_count: int
    removed_target_paths: tuple[Path, ...]
    restored_target_paths: tuple[Path, ...]
    outcome_status: RecoveryExecutionOutcome
    failure_message: str | None = None


@dataclass(frozen=True, slots=True)
class RecoveryExecutionHistory:
    operations: tuple[RecoveryExecutionRecord, ...]


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
