from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import os
from pathlib import Path
from collections.abc import Iterable
from collections import Counter
import shutil
from typing import Literal
from uuid import uuid4
import zipfile

from sdvmm.domain.models import (
    ArchivedModEntry,
    ArchiveDeletePlan,
    ArchiveDeleteResult,
    ArchiveRestorePlan,
    ArchiveRestoreResult,
    AppConfig,
    DependencyPreflightFinding,
    DownloadsIntakeResult,
    DownloadsWatchPollResult,
    GameEnvironmentStatus,
    InstallExecutionActionCount,
    InstallExecutionReview,
    InstallExecutionSummary,
    InstallOperationEntryRecord,
    InstallOperationHistory,
    InstallOperationRecord,
    InstallRecoveryExecutionReview,
    InstallRecoveryExecutionResult,
    InstallRecoveryInspectionResult,
    InstallRecoveryExecutionReviewEntry,
    InstallRecoveryExecutionReviewSummary,
    InstallRecoveryPlan,
    InstallRecoveryPlanEntry,
    InstallRecoveryPlanSummary,
    RecoveryExecutionHistory,
    RecoveryExecutionRecord,
    ModDiscoveryEntry,
    ModDiscoveryResult,
    ModRemovalPlan,
    ModRemovalResult,
    ModRollbackPlan,
    ModRollbackResult,
    ModUpdateReport,
    UpdateSourceIntentOverlay,
    UpdateSourceIntentRecord,
    UpdateSourceIntentState,
    ModsInventory,
    NexusIntegrationStatus,
    PackageInspectionBatchEntry,
    PackageInspectionBatchResult,
    PackageInspectionResult,
    PackageModEntry,
    SmapiLogReport,
    SmapiUpdateStatus,
    SandboxInstallPlan,
    SandboxInstallPlanEntry,
    SandboxInstallResult,
)
from sdvmm.domain.nexus_codes import (
    NEXUS_CONFIGURED,
    NEXUS_NOT_CONFIGURED,
)
from sdvmm.domain.install_codes import BLOCKED, INSTALL_NEW, OVERWRITE_WITH_ARCHIVE
from sdvmm.domain.dependency_codes import (
    MISSING_REQUIRED_DEPENDENCY,
    OPTIONAL_DEPENDENCY_MISSING,
    SATISFIED,
    UNRESOLVED_DEPENDENCY_CONTEXT,
)
from sdvmm.domain.unique_id import canonicalize_unique_id
from sdvmm.services.app_state_store import (
    AppStateStoreError,
    append_install_operation_record,
    append_recovery_execution_record,
    install_operation_history_file,
    load_install_operation_history,
    load_recovery_execution_history,
    load_app_config,
    recovery_execution_history_file,
    save_app_config,
    load_update_source_intent_overlay,
    save_update_source_intent_overlay,
    update_source_intent_overlay_file,
)
from sdvmm.services.mod_scanner import scan_mods_directory
from sdvmm.services.package_inspector import inspect_zip_package
from sdvmm.services.downloads_intake import initialize_known_zip_paths, poll_watched_directory
from sdvmm.services.environment_detection import detect_game_environment as detect_game_environment_service
from sdvmm.services.environment_detection import derive_mods_path
from sdvmm.services.dependency_preflight import (
    evaluate_installed_dependencies,
    evaluate_package_dependencies,
    summarize_missing_required_dependencies,
)
from sdvmm.services.sandbox_installer import (
    SandboxFileLockError,
    SandboxInstallError,
    _build_archive_destination as _build_archive_destination_service,
    _ensure_archive_root as _ensure_archive_root_service,
    _overwrite_target_with_archive as _overwrite_target_with_archive_service,
    build_sandbox_install_plan as build_sandbox_install_plan_service,
    execute_sandbox_install_plan as execute_sandbox_install_plan_service,
    remove_mod_to_archive as remove_mod_to_archive_service,
)
from sdvmm.services.archive_manager import (
    allocate_archive_destination,
    ArchiveManagerError,
    delete_archived_mod_entry,
    list_archived_mod_entries,
    rollback_installed_mod_from_archive,
    restore_archived_mod_entry,
)
from sdvmm.services.update_metadata import (
    NEXUS_API_KEY_ENV,
    check_nexus_connection,
    check_updates_for_inventory,
    mask_api_key,
    normalize_nexus_api_key,
)
from sdvmm.services.remote_requirements import evaluate_remote_requirements_for_package_mods
from sdvmm.services.mod_discovery import (
    DiscoveryServiceError,
    search_discoverable_mods,
)
from sdvmm.services.game_launcher import (
    GameLaunchError,
    LaunchCommand,
    launch_game_process,
    resolve_launch_command,
)
from sdvmm.services.smapi_update import (
    check_smapi_update_status as check_smapi_update_status_service,
    default_smapi_update_page_url,
)
from sdvmm.services.smapi_log import (
    check_smapi_log_troubleshooting as check_smapi_log_troubleshooting_service,
)


class AppShellError(ValueError):
    """Recoverable UI-facing error for config and scan actions."""

    def __init__(self, message: str, *, detail_message: str | None = None) -> None:
        super().__init__(message)
        self.detail_message = detail_message or message


@dataclass(frozen=True, slots=True)
class StartupConfigState:
    config: AppConfig | None
    message: str | None


ScanTargetKind = Literal["configured_real_mods", "sandbox_mods"]
SCAN_TARGET_CONFIGURED_REAL_MODS: ScanTargetKind = "configured_real_mods"
SCAN_TARGET_SANDBOX_MODS: ScanTargetKind = "sandbox_mods"
InstallTargetKind = ScanTargetKind
INSTALL_TARGET_CONFIGURED_REAL_MODS: InstallTargetKind = SCAN_TARGET_CONFIGURED_REAL_MODS
INSTALL_TARGET_SANDBOX_MODS: InstallTargetKind = SCAN_TARGET_SANDBOX_MODS
_DEFAULT_REAL_ARCHIVE_DIRNAME = ".sdvmm-real-archive"
_DEFAULT_SANDBOX_ARCHIVE_DIRNAME = ".sdvmm-sandbox-archive"
_LEGACY_ARCHIVE_DIRNAME = ".sdvmm-archive"
ArchiveSourceKind = Literal["real_archive", "sandbox_archive"]
ARCHIVE_SOURCE_REAL: ArchiveSourceKind = "real_archive"
ARCHIVE_SOURCE_SANDBOX: ArchiveSourceKind = "sandbox_archive"


@dataclass(frozen=True, slots=True)
class ScanResult:
    target_kind: ScanTargetKind
    scan_path: Path
    inventory: ModsInventory


@dataclass(frozen=True, slots=True)
class LaunchStartResult:
    mode: str
    game_path: Path
    executable_path: Path
    pid: int
    mods_path_override: Path | None = None


@dataclass(frozen=True, slots=True)
class SandboxDevLaunchReadiness:
    ready: bool
    message: str
    game_path: Path | None = None
    sandbox_mods_path: Path | None = None
    executable_path: Path | None = None


@dataclass(frozen=True, slots=True)
class SandboxModsSyncReadiness:
    ready: bool
    message: str
    real_mods_path: Path | None = None
    sandbox_mods_path: Path | None = None
    selected_count: int = 0


@dataclass(frozen=True, slots=True)
class SandboxModsSyncResult:
    real_mods_path: Path
    sandbox_mods_path: Path
    source_mod_paths: tuple[Path, ...]
    synced_target_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class SandboxModsPromotionReadiness:
    ready: bool
    message: str
    real_mods_path: Path | None = None
    sandbox_mods_path: Path | None = None
    archive_path: Path | None = None
    selected_count: int = 0
    replace_count: int = 0


@dataclass(frozen=True, slots=True)
class SandboxModsPromotionPreview:
    plan: SandboxInstallPlan
    review: InstallExecutionReview
    real_mods_path: Path
    sandbox_mods_path: Path
    archive_path: Path
    source_mod_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class SandboxModsPromotionResult:
    destination_kind: InstallTargetKind
    real_mods_path: Path
    sandbox_mods_path: Path
    archive_path: Path
    source_mod_paths: tuple[Path, ...]
    promoted_target_paths: tuple[Path, ...]
    archived_target_paths: tuple[Path, ...]
    replaced_target_paths: tuple[Path, ...]
    scan_context_path: Path
    inventory: ModsInventory


@dataclass(frozen=True, slots=True)
class InstallTargetSafetyDecision:
    allowed: bool
    message: str | None
    requires_explicit_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class IntakeUpdateCorrelation:
    intake: DownloadsIntakeResult
    actionable: bool
    matched_update_available_unique_ids: tuple[str, ...]
    matched_guided_update_unique_ids: tuple[str, ...]
    summary: str
    next_step: str


@dataclass(frozen=True, slots=True)
class DiscoveryContextCorrelation:
    entry: ModDiscoveryEntry
    installed_match_unique_id: str | None
    update_state: str | None
    provider_relation: str
    provider_relation_note: str | None
    context_summary: str
    next_step: str


_ACTIONABLE_INTAKE_CLASSIFICATIONS = {
    "new_install_candidate",
    "update_replace_candidate",
    "multi_mod_package",
}


class AppShellService:
    def __init__(self, state_file: Path) -> None:
        self._state_file = state_file

    @property
    def state_file(self) -> Path:
        return self._state_file

    def load_startup_config(self) -> StartupConfigState:
        try:
            config = load_app_config(self._state_file)
        except AppStateStoreError as exc:
            return StartupConfigState(config=None, message=f"Could not load saved config: {exc}")

        if config is None:
            return StartupConfigState(
                config=None,
                message="No saved configuration found. Set a Mods directory and save config.",
            )

        mods_path = config.mods_path
        if not mods_path.exists() or not mods_path.is_dir():
            return StartupConfigState(
                config=config,
                message=f"Saved Mods path is not accessible: {mods_path}",
            )

        return StartupConfigState(config=config, message=None)

    def load_install_operation_history(self) -> InstallOperationHistory:
        try:
            return load_install_operation_history(self._install_operation_history_file)
        except AppStateStoreError as exc:
            raise AppShellError(f"Could not load install history: {exc}") from exc

    def load_recovery_execution_history(self) -> RecoveryExecutionHistory:
        try:
            return load_recovery_execution_history(self._recovery_execution_history_file)
        except AppStateStoreError as exc:
            raise AppShellError(f"Could not load recovery history: {exc}") from exc

    def load_update_source_intent_overlay(self) -> UpdateSourceIntentOverlay:
        try:
            return load_update_source_intent_overlay(self._update_source_intent_overlay_file)
        except AppStateStoreError as exc:
            raise AppShellError(f"Could not load update-source intent overlay: {exc}") from exc

    def get_update_source_intent(self, unique_id: str) -> UpdateSourceIntentRecord | None:
        canonical_unique_id = _require_canonical_unique_id(unique_id)
        overlay = self.load_update_source_intent_overlay()
        return next(
            (
                record
                for record in overlay.records
                if record.normalized_unique_id == canonical_unique_id
            ),
            None,
        )

    def set_update_source_intent(
        self,
        unique_id: str,
        intent_state: UpdateSourceIntentState,
        *,
        manual_provider: str | None = None,
        manual_source_key: str | None = None,
        manual_source_page_url: str | None = None,
    ) -> UpdateSourceIntentOverlay:
        normalized_unique_id = _require_canonical_unique_id(unique_id)
        display_unique_id = unique_id.strip()
        record = UpdateSourceIntentRecord(
            unique_id=display_unique_id,
            normalized_unique_id=normalized_unique_id,
            intent_state=intent_state,
            manual_provider=_normalize_optional_text(manual_provider),
            manual_source_key=_normalize_optional_text(manual_source_key),
            manual_source_page_url=_normalize_optional_text(manual_source_page_url),
        )
        overlay = self.load_update_source_intent_overlay()
        updated = UpdateSourceIntentOverlay(
            records=_upsert_update_source_intent_record(overlay.records, record)
        )
        try:
            save_update_source_intent_overlay(self._update_source_intent_overlay_file, updated)
        except AppStateStoreError as exc:
            raise AppShellError(f"Could not save update-source intent overlay: {exc}") from exc
        return updated

    def clear_update_source_intent(self, unique_id: str) -> UpdateSourceIntentOverlay:
        normalized_unique_id = _require_canonical_unique_id(unique_id)
        overlay = self.load_update_source_intent_overlay()
        updated_records = tuple(
            record
            for record in overlay.records
            if record.normalized_unique_id != normalized_unique_id
        )
        updated = UpdateSourceIntentOverlay(records=updated_records)
        try:
            save_update_source_intent_overlay(self._update_source_intent_overlay_file, updated)
        except AppStateStoreError as exc:
            raise AppShellError(f"Could not save update-source intent overlay: {exc}") from exc
        return updated

    def inspect_install_recovery_by_operation_id(
        self,
        operation_id: str,
    ) -> InstallRecoveryInspectionResult:
        requested_operation_id = operation_id.strip()
        if not requested_operation_id:
            raise AppShellError("Install operation ID is required.")

        history = self.load_install_operation_history()
        operation = next(
            (
                item
                for item in history.operations
                if item.operation_id is not None and item.operation_id == requested_operation_id
            ),
            None,
        )
        if operation is None:
            raise AppShellError(
                f"Install operation ID not found: {requested_operation_id}"
            )

        recovery_plan = self.derive_install_operation_recovery_plan(operation)
        recovery_review = self.review_install_recovery_execution(recovery_plan)
        linked_recovery_history = tuple(
            record
            for record in self.load_recovery_execution_history().operations
            if record.related_install_operation_id == requested_operation_id
        )
        return InstallRecoveryInspectionResult(
            operation=operation,
            recovery_plan=recovery_plan,
            recovery_review=recovery_review,
            linked_recovery_history=linked_recovery_history,
        )

    def derive_install_operation_recovery_plan(
        self,
        operation: InstallOperationRecord,
    ) -> InstallRecoveryPlan:
        entries = tuple(
            _derive_install_operation_recovery_entry(operation, entry)
            for entry in operation.entries
        )
        warnings = tuple(entry.message for entry in entries if not entry.recoverable)
        recoverable_entry_count = sum(1 for entry in entries if entry.recoverable)
        non_recoverable_entry_count = len(entries) - recoverable_entry_count
        return InstallRecoveryPlan(
            operation=operation,
            entries=entries,
            summary=InstallRecoveryPlanSummary(
                total_recovery_entry_count=len(entries),
                recoverable_entry_count=recoverable_entry_count,
                non_recoverable_entry_count=non_recoverable_entry_count,
                involves_archive_restore=any(
                    entry.action == "restore_from_archive" and entry.recoverable
                    for entry in entries
                ),
                warnings=warnings,
            ),
        )

    def review_install_recovery_execution(
        self,
        plan: InstallRecoveryPlan,
    ) -> InstallRecoveryExecutionReview:
        entries = tuple(_review_install_recovery_entry(entry) for entry in plan.entries)
        executable_entry_count = sum(1 for entry in entries if entry.executable)
        non_executable_entry_count = len(entries) - executable_entry_count
        stale_entry_count = sum(
            1
            for entry in entries
            if entry.decision_code in {"removal_target_missing", "restore_archive_missing"}
        )
        warnings = tuple(entry.message for entry in entries if not entry.executable)
        allowed = non_executable_entry_count == 0
        if allowed:
            message = (
                f"Recovery plan is ready: {executable_entry_count} "
                f"{_entry_count_label(executable_entry_count)} can be executed."
            )
        else:
            message = (
                f"Recovery plan is blocked: {non_executable_entry_count} "
                f"{_entry_count_label(non_executable_entry_count)} cannot be executed safely."
            )
        return InstallRecoveryExecutionReview(
            plan=plan,
            allowed=allowed,
            decision_code=("recovery_ready" if allowed else "recovery_blocked"),
            message=message,
            entries=entries,
            summary=InstallRecoveryExecutionReviewSummary(
                total_entry_count=len(entries),
                executable_entry_count=executable_entry_count,
                non_executable_entry_count=non_executable_entry_count,
                stale_entry_count=stale_entry_count,
                involves_archive_restore=any(
                    review_entry.plan_entry.action == "restore_from_archive"
                    and review_entry.executable
                    for review_entry in entries
                ),
                warnings=warnings,
            ),
        )

    def execute_install_recovery_review(
        self,
        review: InstallRecoveryExecutionReview,
    ) -> InstallRecoveryExecutionResult:
        if not review.allowed:
            self._record_recovery_execution_attempt(
                review=review,
                outcome_status="failed",
                removed_target_paths=tuple(),
                restored_target_paths=tuple(),
                failure_message=review.message,
                critical=False,
            )
            raise AppShellError(review.message)

        removed_target_paths: list[Path] = []
        restored_target_paths: list[Path] = []
        destination_mods_path = review.plan.operation.destination_mods_path
        destination_kind = review.plan.operation.destination_kind
        archive_path = review.plan.operation.archive_path

        try:
            for entry_review in review.entries:
                if not entry_review.executable:
                    raise AppShellError(entry_review.message)

                plan_entry = entry_review.plan_entry
                try:
                    if plan_entry.action == "remove_installed_target":
                        _remove_recovery_target(plan_entry.target_path)
                        removed_target_paths.append(plan_entry.target_path)
                        continue

                    if plan_entry.action == "restore_from_archive":
                        if plan_entry.archive_path is None:
                            raise AppShellError(
                                f"Archive source is missing for restoring {plan_entry.name}."
                            )
                        restored_target = restore_archived_mod_entry(
                            archive_root=archive_path,
                            archived_path=plan_entry.archive_path,
                            destination_mods_root=destination_mods_path,
                            destination_folder_name=plan_entry.target_path.name,
                        )
                        restored_target_paths.append(restored_target)
                        continue
                except ArchiveManagerError as exc:
                    raise AppShellError(f"Recovery execution failed: {exc}") from exc
                except OSError as exc:
                    raise AppShellError(f"Recovery execution failed: {exc}") from exc

                raise AppShellError(
                    f"Recovery execution failed: unsupported action {plan_entry.action!r}."
                )

            try:
                inventory = scan_mods_directory(
                    destination_mods_path,
                    excluded_paths=(archive_path, destination_mods_path / _LEGACY_ARCHIVE_DIRNAME),
                )
            except OSError as exc:
                raise AppShellError(f"Recovery execution scan failed: {exc}") from exc

            result = InstallRecoveryExecutionResult(
                review=review,
                executed_entry_count=len(review.entries),
                removed_target_paths=tuple(removed_target_paths),
                restored_target_paths=tuple(restored_target_paths),
                destination_kind=destination_kind,
                destination_mods_path=destination_mods_path,
                scan_context_path=destination_mods_path,
                inventory=inventory,
            )
        except AppShellError as exc:
            outcome_status = "failed_partial" if (removed_target_paths or restored_target_paths) else "failed"
            self._record_recovery_execution_attempt(
                review=review,
                outcome_status=outcome_status,
                removed_target_paths=tuple(removed_target_paths),
                restored_target_paths=tuple(restored_target_paths),
                failure_message=str(exc),
                critical=bool(removed_target_paths or restored_target_paths),
            )
            raise

        self._record_recovery_execution_attempt(
            review=review,
            outcome_status="completed",
            removed_target_paths=result.removed_target_paths,
            restored_target_paths=result.restored_target_paths,
            failure_message=None,
            critical=True,
        )
        return result

    def build_install_execution_summary(
        self,
        plan: SandboxInstallPlan,
    ) -> InstallExecutionSummary:
        action_order = (INSTALL_NEW, OVERWRITE_WITH_ARCHIVE, BLOCKED)
        action_totals = Counter(entry.action for entry in plan.entries)
        action_counts = tuple(
            InstallExecutionActionCount(action=action, count=action_totals.get(action, 0))
            for action in action_order
        )
        review_warnings = _collect_install_execution_review_warnings(plan)
        requires_explicit_confirmation = (
            plan.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
        )
        return InstallExecutionSummary(
            destination_kind=plan.destination_kind,
            destination_mods_path=plan.sandbox_mods_path,
            archive_path=plan.sandbox_archive_path,
            total_entry_count=len(plan.entries),
            action_counts=action_counts,
            has_existing_targets_to_replace=any(
                entry.target_exists and entry.action == OVERWRITE_WITH_ARCHIVE
                for entry in plan.entries
            ),
            has_archive_writes=any(entry.archive_path is not None for entry in plan.entries),
            requires_explicit_confirmation=requires_explicit_confirmation,
            review_warnings=review_warnings,
        )

    def review_install_execution(
        self,
        plan: SandboxInstallPlan,
    ) -> InstallExecutionReview:
        summary = self.build_install_execution_summary(plan)
        blocked_count = next(
            (item.count for item in summary.action_counts if item.action == BLOCKED),
            0,
        )

        if blocked_count > 0:
            entry_label = "entry" if blocked_count == 1 else "entries"
            return InstallExecutionReview(
                summary=summary,
                allowed=False,
                requires_explicit_approval=False,
                decision_code="blocked_entries_present",
                message=(
                    f"Install plan is blocked: {blocked_count} {entry_label} cannot be executed. "
                    "Resolve blocked entries before running install."
                ),
            )

        if summary.requires_explicit_confirmation:
            return InstallExecutionReview(
                summary=summary,
                allowed=True,
                requires_explicit_approval=True,
                decision_code="real_approval_required",
                message=_build_real_install_review_message(summary),
            )

        return InstallExecutionReview(
            summary=summary,
            allowed=True,
            requires_explicit_approval=False,
            decision_code="sandbox_allowed",
            message=_build_sandbox_install_review_message(summary),
        )

    def save_mods_directory(
        self,
        mods_dir_text: str,
        existing_config: AppConfig | None,
    ) -> AppConfig:
        mods_path = self._parse_and_validate_mods_path(mods_dir_text)
        game_path = existing_config.game_path if existing_config is not None else mods_path.parent
        config = self._build_config(
            game_path=game_path,
            mods_path=mods_path,
            existing_config=existing_config,
        )

        try:
            save_app_config(state_file=self._state_file, config=config)
        except OSError as exc:
            raise AppShellError(f"Could not save configuration: {exc}") from exc

        return config

    def save_operational_config(
        self,
        *,
        game_path_text: str,
        mods_dir_text: str,
        sandbox_mods_path_text: str,
        sandbox_archive_path_text: str,
        watched_downloads_path_text: str,
        secondary_watched_downloads_path_text: str = "",
        real_archive_path_text: str = "",
        nexus_api_key_text: str = "",
        scan_target: ScanTargetKind,
        install_target: InstallTargetKind = INSTALL_TARGET_SANDBOX_MODS,
        existing_config: AppConfig | None,
    ) -> AppConfig:
        if scan_target not in {SCAN_TARGET_CONFIGURED_REAL_MODS, SCAN_TARGET_SANDBOX_MODS}:
            raise AppShellError(f"Unknown scan target: {scan_target}")
        if install_target not in {INSTALL_TARGET_CONFIGURED_REAL_MODS, INSTALL_TARGET_SANDBOX_MODS}:
            raise AppShellError(f"Unknown install target: {install_target}")

        game_path = self._resolve_game_path(game_path_text, existing_config)
        mods_path = self._resolve_mods_path(mods_dir_text, game_path)

        sandbox_mods_path = self._parse_optional_directory(sandbox_mods_path_text)
        sandbox_archive_path: Path | None = None
        if sandbox_mods_path is not None:
            sandbox_archive_path = self._parse_and_validate_sandbox_archive_path(
                sandbox_archive_path_text=sandbox_archive_path_text,
                sandbox_mods_path=sandbox_mods_path,
            )
        elif sandbox_archive_path_text.strip():
            archive_path = Path(sandbox_archive_path_text.strip()).expanduser()
            if archive_path.exists() and not archive_path.is_dir():
                raise AppShellError(f"Sandbox archive path is not a directory: {archive_path}")
            if not archive_path.parent.exists() or not archive_path.parent.is_dir():
                raise AppShellError(
                    f"Sandbox archive parent directory is not accessible: {archive_path.parent}"
                )
            sandbox_archive_path = archive_path

        watched_downloads_path = self._parse_optional_directory(watched_downloads_path_text)
        secondary_watched_downloads_path = self._parse_optional_directory(
            secondary_watched_downloads_path_text
        )
        if secondary_watched_downloads_path == watched_downloads_path:
            secondary_watched_downloads_path = None
        real_archive_path = self._parse_and_validate_archive_path(
            archive_path_text=real_archive_path_text,
            destination_mods_path=mods_path,
            field_label="Real Mods archive path",
            default_archive_dir_name=_DEFAULT_REAL_ARCHIVE_DIRNAME,
        )
        nexus_api_key = self._resolve_nexus_api_key(
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
            allow_environment_fallback=False,
        )

        config = self._build_config(
            game_path=game_path,
            mods_path=mods_path,
            existing_config=existing_config,
        )
        config = AppConfig(
            game_path=game_path,
            mods_path=config.mods_path,
            app_data_path=config.app_data_path,
            sandbox_mods_path=sandbox_mods_path,
            sandbox_archive_path=sandbox_archive_path,
            real_archive_path=real_archive_path,
            watched_downloads_path=watched_downloads_path,
            secondary_watched_downloads_path=secondary_watched_downloads_path,
            nexus_api_key=nexus_api_key,
            scan_target=scan_target,
            install_target=install_target,
        )

        try:
            save_app_config(state_file=self._state_file, config=config)
        except OSError as exc:
            raise AppShellError(f"Could not save configuration: {exc}") from exc

        return config

    def detect_game_environment(self, game_path_text: str) -> GameEnvironmentStatus:
        game_path = self._parse_game_path_text(game_path_text)
        return detect_game_environment_service(game_path)

    def launch_game_vanilla(
        self,
        *,
        game_path_text: str,
        existing_config: AppConfig | None = None,
    ) -> LaunchStartResult:
        game_path = self._resolve_game_path(game_path_text, existing_config)
        try:
            command = resolve_launch_command(game_path=game_path, mode="vanilla")
            pid = launch_game_process(command)
        except GameLaunchError as exc:
            raise AppShellError(str(exc)) from exc
        return LaunchStartResult(
            mode="vanilla",
            game_path=game_path,
            executable_path=command.executable_path,
            pid=pid,
        )

    def launch_game_smapi(
        self,
        *,
        game_path_text: str,
        existing_config: AppConfig | None = None,
    ) -> LaunchStartResult:
        game_path = self._resolve_game_path(game_path_text, existing_config)
        try:
            command = resolve_launch_command(game_path=game_path, mode="smapi")
            pid = launch_game_process(command)
        except GameLaunchError as exc:
            raise AppShellError(str(exc)) from exc
        return LaunchStartResult(
            mode="smapi",
            game_path=game_path,
            executable_path=command.executable_path,
            pid=pid,
        )

    def get_sandbox_dev_launch_readiness(
        self,
        *,
        game_path_text: str,
        sandbox_mods_path_text: str,
        configured_mods_path_text: str,
        existing_config: AppConfig | None = None,
    ) -> SandboxDevLaunchReadiness:
        try:
            game_path, sandbox_mods_path, command = self._resolve_sandbox_dev_launch_context(
                game_path_text=game_path_text,
                sandbox_mods_path_text=sandbox_mods_path_text,
                configured_mods_path_text=configured_mods_path_text,
                existing_config=existing_config,
            )
        except AppShellError as exc:
            return SandboxDevLaunchReadiness(ready=False, message=str(exc))

        return SandboxDevLaunchReadiness(
            ready=True,
            message=(
                "Ready to launch sandbox dev with SMAPI using the configured sandbox Mods path."
            ),
            game_path=game_path,
            sandbox_mods_path=sandbox_mods_path,
            executable_path=command.executable_path,
        )

    def launch_game_sandbox_dev(
        self,
        *,
        game_path_text: str,
        sandbox_mods_path_text: str,
        configured_mods_path_text: str,
        existing_config: AppConfig | None = None,
    ) -> LaunchStartResult:
        game_path, sandbox_mods_path, command = self._resolve_sandbox_dev_launch_context(
            game_path_text=game_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            configured_mods_path_text=configured_mods_path_text,
            existing_config=existing_config,
        )
        try:
            pid = launch_game_process(command)
        except GameLaunchError as exc:
            raise AppShellError(str(exc)) from exc
        return LaunchStartResult(
            mode="sandbox_dev_smapi",
            game_path=game_path,
            executable_path=command.executable_path,
            pid=pid,
            mods_path_override=sandbox_mods_path,
        )

    def get_sandbox_mods_sync_readiness(
        self,
        *,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        selected_mod_folder_paths_text: Iterable[str],
        existing_config: AppConfig | None = None,
    ) -> SandboxModsSyncReadiness:
        try:
            real_mods_path, sandbox_mods_path, source_paths = self._resolve_sandbox_mod_sync_context(
                configured_mods_path_text=configured_mods_path_text,
                sandbox_mods_path_text=sandbox_mods_path_text,
                selected_mod_folder_paths_text=selected_mod_folder_paths_text,
                existing_config=existing_config,
            )
        except AppShellError as exc:
            return SandboxModsSyncReadiness(ready=False, message=str(exc))

        return SandboxModsSyncReadiness(
            ready=True,
            message=(
                f"Ready to sync {len(source_paths)} selected mod(s) "
                "from real Mods into sandbox Mods."
            ),
            real_mods_path=real_mods_path,
            sandbox_mods_path=sandbox_mods_path,
            selected_count=len(source_paths),
        )

    def sync_installed_mods_to_sandbox(
        self,
        *,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        selected_mod_folder_paths_text: Iterable[str],
        existing_config: AppConfig | None = None,
    ) -> SandboxModsSyncResult:
        real_mods_path, sandbox_mods_path, source_paths = self._resolve_sandbox_mod_sync_context(
            configured_mods_path_text=configured_mods_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            selected_mod_folder_paths_text=selected_mod_folder_paths_text,
            existing_config=existing_config,
        )
        synced_target_paths: list[Path] = []
        for source_path in source_paths:
            target_path = sandbox_mods_path / source_path.name
            shutil.copytree(source_path, target_path)
            synced_target_paths.append(target_path)

        return SandboxModsSyncResult(
            real_mods_path=real_mods_path,
            sandbox_mods_path=sandbox_mods_path,
            source_mod_paths=source_paths,
            synced_target_paths=tuple(synced_target_paths),
        )

    def get_sandbox_mods_promotion_readiness(
        self,
        *,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        selected_mod_folder_paths_text: Iterable[str],
        existing_config: AppConfig | None = None,
    ) -> SandboxModsPromotionReadiness:
        try:
            preview = self.build_sandbox_mods_promotion_preview(
                configured_mods_path_text=configured_mods_path_text,
                sandbox_mods_path_text=sandbox_mods_path_text,
                real_archive_path_text=real_archive_path_text,
                selected_mod_folder_paths_text=selected_mod_folder_paths_text,
                existing_config=existing_config,
            )
        except AppShellError as exc:
            return SandboxModsPromotionReadiness(ready=False, message=str(exc))

        replace_count = sum(
            1 for entry in preview.plan.entries if entry.action == OVERWRITE_WITH_ARCHIVE
        )
        if not preview.review.allowed:
            return SandboxModsPromotionReadiness(
                ready=False,
                message=preview.review.message,
                real_mods_path=preview.real_mods_path,
                sandbox_mods_path=preview.sandbox_mods_path,
                archive_path=preview.archive_path,
                selected_count=len(preview.source_mod_paths),
                replace_count=replace_count,
            )

        if replace_count > 0:
            message = (
                f"Review required: {len(preview.source_mod_paths)} selected mod(s) include "
                f"{replace_count} archive-aware live replacement(s) for REAL Mods."
            )
        else:
            message = (
                f"Ready to review {len(preview.source_mod_paths)} selected mod(s) "
                "for promotion into the configured real Mods path."
            )

        return SandboxModsPromotionReadiness(
            ready=True,
            message=message,
            real_mods_path=preview.real_mods_path,
            sandbox_mods_path=preview.sandbox_mods_path,
            archive_path=preview.archive_path,
            selected_count=len(preview.source_mod_paths),
            replace_count=replace_count,
        )

    def build_sandbox_mods_promotion_preview(
        self,
        *,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        selected_mod_folder_paths_text: Iterable[str],
        existing_config: AppConfig | None = None,
    ) -> SandboxModsPromotionPreview:
        real_mods_path, sandbox_mods_path, archive_path, source_paths, source_inventory = (
            self._resolve_sandbox_mod_promotion_context(
                configured_mods_path_text=configured_mods_path_text,
                sandbox_mods_path_text=sandbox_mods_path_text,
                real_archive_path_text=real_archive_path_text,
                selected_mod_folder_paths_text=selected_mod_folder_paths_text,
                existing_config=existing_config,
            )
        )
        plan = self._build_sandbox_mods_promotion_plan(
            real_mods_path=real_mods_path,
            sandbox_mods_path=sandbox_mods_path,
            archive_path=archive_path,
            source_paths=source_paths,
            source_inventory=source_inventory,
        )
        review = self.review_install_execution(plan)
        return SandboxModsPromotionPreview(
            plan=plan,
            review=review,
            real_mods_path=real_mods_path,
            sandbox_mods_path=sandbox_mods_path,
            archive_path=archive_path,
            source_mod_paths=source_paths,
        )

    def promote_installed_mods_from_sandbox_to_real(
        self,
        *,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        selected_mod_folder_paths_text: Iterable[str],
        existing_config: AppConfig | None = None,
    ) -> SandboxModsPromotionResult:
        preview = self.build_sandbox_mods_promotion_preview(
            configured_mods_path_text=configured_mods_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text=real_archive_path_text,
            selected_mod_folder_paths_text=selected_mod_folder_paths_text,
            existing_config=existing_config,
        )
        return self.execute_sandbox_mods_promotion_preview(preview)

    def execute_sandbox_mods_promotion_preview(
        self,
        preview: SandboxModsPromotionPreview,
    ) -> SandboxModsPromotionResult:
        if not preview.review.allowed:
            raise AppShellError(preview.review.message)

        _ensure_archive_root_service(preview.archive_path)
        staging_root = (
            preview.real_mods_path / f".sdvmm-promotion-stage-{uuid4().hex[:10]}"
        )
        applied_entries: list[SandboxInstallPlanEntry] = []
        installed_targets: list[Path] = []
        archived_targets: list[Path] = []
        replaced_targets: list[Path] = []
        try:
            staging_root.mkdir(parents=False, exist_ok=False)

            for entry in preview.plan.entries:
                staged_target = staging_root / entry.target_path.name
                shutil.copytree(Path(entry.source_root_path), staged_target)

            for entry in preview.plan.entries:
                staged_target = staging_root / entry.target_path.name
                if entry.action == INSTALL_NEW:
                    try:
                        staged_target.rename(entry.target_path)
                    except OSError as exc:
                        raise AppShellError(
                            "Sandbox promotion failed while creating a new REAL Mods target: "
                            f"{entry.target_path}: {exc}"
                        ) from exc
                    installed_targets.append(entry.target_path)
                    applied_entries.append(entry)
                    continue

                if entry.action == OVERWRITE_WITH_ARCHIVE:
                    if entry.archive_path is None:
                        raise AppShellError(
                            "Sandbox promotion preview is invalid: overwrite entry is missing "
                            f"archive path for {entry.target_path}."
                        )
                    try:
                        _overwrite_target_with_archive_service(
                            staged_target=staged_target,
                            target_path=entry.target_path,
                            archive_path=entry.archive_path,
                        )
                    except SandboxInstallError as exc:
                        raise AppShellError(f"Sandbox promotion failed: {exc}") from exc
                    installed_targets.append(entry.target_path)
                    archived_targets.append(entry.archive_path)
                    replaced_targets.append(entry.target_path)
                    applied_entries.append(entry)
                    continue

                raise AppShellError(
                    f"Sandbox promotion preview contains a blocked entry: {entry.target_path}"
                )
            inventory = scan_mods_directory(
                preview.real_mods_path,
                excluded_paths=(
                    preview.archive_path,
                    preview.real_mods_path / _LEGACY_ARCHIVE_DIRNAME,
                ),
            )
            result = SandboxInstallResult(
                plan=preview.plan,
                installed_targets=tuple(
                    sorted(installed_targets, key=lambda path: path.name.lower())
                ),
                archived_targets=tuple(
                    sorted(archived_targets, key=lambda path: path.name.lower())
                ),
                scan_context_path=preview.real_mods_path,
                inventory=inventory,
                destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS,
            )
            self._record_completed_install_operation(plan=preview.plan, result=result)
        except (AppShellError, SandboxInstallError, OSError) as exc:
            if not applied_entries:
                raise _normalize_sandbox_promotion_error(exc) from exc

            rollback_errors = self._rollback_sandbox_mods_promotion_entries(
                tuple(applied_entries)
            )
            (
                remaining_entries,
                remaining_installed_targets,
                remaining_archived_targets,
            ) = self._remaining_sandbox_mods_promotion_state(tuple(applied_entries))
            if not remaining_entries:
                raise AppShellError(
                    f"{_normalize_sandbox_promotion_error(exc)} "
                    "Promotion rollback restored prior REAL Mods state."
                ) from exc

            partial_plan = replace(
                preview.plan,
                entries=remaining_entries,
                plan_warnings=preview.plan.plan_warnings
                + (
                    "Partial sandbox promotion failure left remaining live changes after rollback.",
                    "Recovery inspection depends on this recorded partial promotion state.",
                ),
            )
            partial_record_error: AppShellError | None = None
            try:
                self._record_install_operation_state(
                    plan=partial_plan,
                    installed_targets=remaining_installed_targets,
                    archived_targets=remaining_archived_targets,
                )
            except AppShellError as record_exc:
                partial_record_error = record_exc

            rollback_detail = ""
            if rollback_errors:
                rollback_detail = " Rollback details: " + "; ".join(rollback_errors)

            if partial_record_error is None:
                raise AppShellError(
                    f"{_normalize_sandbox_promotion_error(exc)} "
                    "Promotion rollback could not fully restore prior REAL Mods state. "
                    "Remaining live changes were recorded in install history for recovery inspection."
                    f"{rollback_detail}"
                ) from exc

            raise AppShellError(
                f"{_normalize_sandbox_promotion_error(exc)} "
                "Promotion rollback could not fully restore prior REAL Mods state, and "
                "recording partial install history failed. Manual recovery is required. "
                f"Recording error: {partial_record_error}.{rollback_detail}"
            ) from exc
        finally:
            if staging_root.exists():
                shutil.rmtree(staging_root, ignore_errors=True)

        return SandboxModsPromotionResult(
            destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS,
            real_mods_path=preview.real_mods_path,
            sandbox_mods_path=preview.sandbox_mods_path,
            archive_path=preview.archive_path,
            source_mod_paths=preview.source_mod_paths,
            promoted_target_paths=result.installed_targets,
            archived_target_paths=result.archived_targets,
            replaced_target_paths=tuple(
                sorted(replaced_targets, key=lambda path: path.name.lower())
            ),
            scan_context_path=preview.real_mods_path,
            inventory=inventory,
        )

    def check_smapi_update_status(
        self,
        *,
        game_path_text: str,
        existing_config: AppConfig | None = None,
    ) -> SmapiUpdateStatus:
        game_path = self._resolve_game_path(game_path_text, existing_config)
        try:
            return check_smapi_update_status_service(game_path=game_path)
        except OSError as exc:
            raise AppShellError(f"Could not check SMAPI update status: {exc}") from exc

    @staticmethod
    def resolve_smapi_update_page_url(status: SmapiUpdateStatus | None = None) -> str:
        if status is not None and status.update_page_url.strip():
            return status.update_page_url.strip()
        return default_smapi_update_page_url()

    def check_smapi_log_troubleshooting(
        self,
        *,
        game_path_text: str,
        log_path_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> SmapiLogReport:
        manual_log_path: Path | None = None
        raw_log_path = log_path_text.strip()
        if raw_log_path:
            manual_log_path = Path(raw_log_path).expanduser()
            if not manual_log_path.exists():
                raise AppShellError(f"SMAPI log file does not exist: {manual_log_path}")
            if not manual_log_path.is_file():
                raise AppShellError(f"SMAPI log path is not a file: {manual_log_path}")
            if manual_log_path.suffix.casefold() not in {".txt", ".log"}:
                raise AppShellError(
                    f"SMAPI log file must be .txt or .log: {manual_log_path}"
                )

        resolved_game_path: Path | None = None
        if not manual_log_path:
            resolved_game_path = self._resolve_game_path(game_path_text, existing_config)
        elif game_path_text.strip():
            resolved_game_path = self._parse_and_validate_game_path(game_path_text)

        try:
            return check_smapi_log_troubleshooting_service(
                game_path=resolved_game_path,
                manual_log_path=manual_log_path,
            )
        except OSError as exc:
            raise AppShellError(f"Could not inspect SMAPI log: {exc}") from exc

    def scan(self, mods_dir_text: str) -> ModsInventory:
        mods_path = self._parse_and_validate_mods_path(mods_dir_text)
        excluded_paths = (mods_path / _LEGACY_ARCHIVE_DIRNAME,)

        try:
            return scan_mods_directory(mods_path, excluded_paths=excluded_paths)
        except OSError as exc:
            raise AppShellError(f"Could not scan Mods directory: {exc}") from exc

    def scan_with_target(
        self,
        *,
        scan_target: ScanTargetKind,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str = "",
        sandbox_archive_path_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> ScanResult:
        if scan_target == SCAN_TARGET_CONFIGURED_REAL_MODS:
            scan_path = self._parse_and_validate_mods_path(configured_mods_path_text)
            configured_archive_text = real_archive_path_text
            configured_archive_fallback = (
                existing_config.real_archive_path if existing_config is not None else None
            )
        elif scan_target == SCAN_TARGET_SANDBOX_MODS:
            scan_path = self._parse_and_validate_sandbox_mods_path(sandbox_mods_path_text)
            configured_archive_text = sandbox_archive_path_text
            configured_archive_fallback = (
                existing_config.sandbox_archive_path if existing_config is not None else None
            )
        else:
            raise AppShellError(f"Unknown scan target: {scan_target}")

        excluded_paths = self._resolve_scan_excluded_paths(
            scan_target=scan_target,
            scan_path=scan_path,
            configured_archive_text=configured_archive_text,
            configured_archive_fallback=configured_archive_fallback,
        )
        try:
            inventory = scan_mods_directory(scan_path, excluded_paths=excluded_paths)
        except OSError as exc:
            raise AppShellError(f"Could not scan selected target: {exc}") from exc

        return ScanResult(target_kind=scan_target, scan_path=scan_path, inventory=inventory)

    def inspect_zip(self, package_path_text: str) -> PackageInspectionResult:
        package_path = self._parse_and_validate_zip_path(package_path_text)

        try:
            return inspect_zip_package(package_path)
        except zipfile.BadZipFile as exc:
            raise AppShellError(f"File is not a valid zip package: {package_path}") from exc
        except OSError as exc:
            raise AppShellError(f"Could not inspect package: {exc}") from exc

    def inspect_zip_with_inventory_context(
        self,
        package_path_text: str,
        inventory: ModsInventory | None,
        *,
        nexus_api_key_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> PackageInspectionResult:
        base_result = self.inspect_zip(package_path_text)
        return self._enrich_package_inspection_result(
            base_result,
            inventory=inventory,
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
        )

    def inspect_zip_batch_with_inventory_context(
        self,
        package_path_texts: Iterable[str],
        inventory: ModsInventory | None,
        *,
        nexus_api_key_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> PackageInspectionBatchResult:
        path_texts = tuple(text.strip() for text in package_path_texts if text.strip())
        if not path_texts:
            raise AppShellError("Select one or more zip packages to inspect.")

        entries: list[PackageInspectionBatchEntry] = []
        for package_path_text in path_texts:
            package_path = Path(package_path_text)
            try:
                inspection = self.inspect_zip_with_inventory_context(
                    package_path_text,
                    inventory,
                    nexus_api_key_text=nexus_api_key_text,
                    existing_config=existing_config,
                )
            except AppShellError as exc:
                entries.append(
                    PackageInspectionBatchEntry(
                        package_path=package_path,
                        error_message=str(exc),
                    )
                )
                continue

            entries.append(
                PackageInspectionBatchEntry(
                    package_path=inspection.package_path,
                    inspection=inspection,
                )
            )

        return PackageInspectionBatchResult(entries=tuple(entries))

    @staticmethod
    def evaluate_installed_dependency_preflight(
        inventory: ModsInventory,
    ) -> tuple[DependencyPreflightFinding, ...]:
        return evaluate_installed_dependencies(inventory.mods)

    def check_updates(
        self,
        inventory: ModsInventory,
        *,
        nexus_api_key_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> ModUpdateReport:
        nexus_api_key = self._resolve_nexus_api_key(
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
        )
        update_source_intent_overlay = self.load_update_source_intent_overlay()
        try:
            return check_updates_for_inventory(
                inventory,
                nexus_api_key=nexus_api_key,
                update_source_intent_overlay=update_source_intent_overlay,
            )
        except OSError as exc:
            raise AppShellError(f"Could not check remote metadata: {exc}") from exc

    def _enrich_package_inspection_result(
        self,
        base_result: PackageInspectionResult,
        *,
        inventory: ModsInventory | None,
        nexus_api_key_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> PackageInspectionResult:
        nexus_api_key = self._resolve_nexus_api_key(
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
        )
        dependency_findings = evaluate_package_dependencies(
            package_mods=base_result.mods,
            installed_mods=inventory.mods if inventory is not None else None,
            source="package_inspection",
        )
        remote_requirements = evaluate_remote_requirements_for_package_mods(
            base_result.mods,
            source="package_inspection",
            nexus_api_key=nexus_api_key,
        )
        return replace(
            base_result,
            dependency_findings=dependency_findings,
            remote_requirements=remote_requirements,
        )

    def search_mod_discovery(
        self,
        *,
        query_text: str,
        max_results: int = 50,
    ) -> ModDiscoveryResult:
        try:
            return search_discoverable_mods(
                query_text,
                max_results=max_results,
            )
        except DiscoveryServiceError as exc:
            raise AppShellError(f"Could not search mod discovery index: [{exc.reason}] {exc.message}") from exc
        except OSError as exc:
            raise AppShellError(f"Could not search mod discovery index: {exc}") from exc

    @staticmethod
    def resolve_discovery_source_page_url(entry: ModDiscoveryEntry) -> str:
        if entry.source_page_url:
            return entry.source_page_url
        raise AppShellError(
            f"No source page URL is available for discovered mod: {entry.unique_id}"
        )

    def correlate_discovery_results(
        self,
        *,
        discovery_result: ModDiscoveryResult,
        inventory: ModsInventory | None,
        update_report: ModUpdateReport | None,
    ) -> tuple[DiscoveryContextCorrelation, ...]:
        installed_keys: dict[str, str] = {}
        if inventory is not None:
            for mod in inventory.mods:
                key = canonicalize_unique_id(mod.unique_id)
                installed_keys.setdefault(key, mod.unique_id)

        update_status_by_key: dict[str, object] = {}
        if update_report is not None:
            for status in update_report.statuses:
                key = canonicalize_unique_id(status.unique_id)
                update_status_by_key.setdefault(key, status)

        correlations: list[DiscoveryContextCorrelation] = []
        for entry in discovery_result.results:
            key_candidates = _discovery_entry_unique_id_keys(entry)
            installed_match_unique_id = _first_present(installed_keys, key_candidates)
            update_status = _first_present(update_status_by_key, key_candidates)

            update_state = None
            tracked_provider = None
            if update_status is not None:
                update_state = str(update_status.state)
                if update_status.remote_link is not None:
                    tracked_provider = str(update_status.remote_link.provider)

            provider_relation, provider_relation_note = _build_discovery_provider_relation(
                discovery_source_provider=entry.source_provider,
                tracked_provider=tracked_provider,
            )
            context_summary, next_step = _build_discovery_context_messages(
                installed_match_unique_id=installed_match_unique_id,
                update_state=update_state,
            )

            correlations.append(
                DiscoveryContextCorrelation(
                    entry=entry,
                    installed_match_unique_id=installed_match_unique_id,
                    update_state=update_state,
                    provider_relation=provider_relation,
                    provider_relation_note=provider_relation_note,
                    context_summary=context_summary,
                    next_step=next_step,
                )
            )

        return tuple(correlations)

    @staticmethod
    def build_manual_discovery_flow_hint(
        *,
        correlation: DiscoveryContextCorrelation,
        watched_downloads_path_text: str,
        secondary_watched_downloads_path_text: str = "",
        watcher_running: bool,
    ) -> str:
        watched_path = AppShellService._format_watched_download_paths_for_guidance(
            watched_downloads_path_text=watched_downloads_path_text,
            secondary_watched_downloads_path_text=secondary_watched_downloads_path_text,
        )
        watch_step = (
            "Watcher is running; it will detect new zip files added now."
            if watcher_running
            else "Start watch before downloading, so new zip files are detected."
        )
        relation = (
            f"\nProvider relation: {correlation.provider_relation_note}"
            if correlation.provider_relation_note
            else ""
        )
        return (
            f"Manual discovery flow for {correlation.entry.unique_id}:\n"
            f"Context: {correlation.context_summary}.{relation}\n"
            "1. Open source page and download the zip manually.\n"
            f"2. Save the zip into {watched_path}\n"
            f"3. {watch_step}\n"
            "4. In detected packages, select that zip and click 'Plan selected intake'.\n"
            "5. Review dependency + archive/overwrite warnings, then run install explicitly."
        )

    def get_nexus_integration_status(
        self,
        *,
        nexus_api_key_text: str,
        existing_config: AppConfig | None,
        validate_connection: bool,
    ) -> NexusIntegrationStatus:
        nexus_api_key, source = self._resolve_nexus_api_key_with_source(
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
            allow_environment_fallback=True,
        )

        if not nexus_api_key:
            return NexusIntegrationStatus(
                state=NEXUS_NOT_CONFIGURED,
                source="none",
                masked_key=None,
                message="Nexus API key is not configured.",
            )

        if not validate_connection:
            return NexusIntegrationStatus(
                state=NEXUS_CONFIGURED,
                source=source,
                masked_key=mask_api_key(nexus_api_key),
                message="Nexus key is configured. Run connection check to validate it.",
            )

        status = check_nexus_connection(nexus_api_key=nexus_api_key)
        return replace(status, source=source)

    def initialize_downloads_watch(
        self,
        watched_downloads_path_text: str,
        secondary_watched_downloads_path_text: str = "",
    ) -> tuple[Path, ...]:
        watched_paths = self._parse_and_validate_watched_downloads_path(
            watched_downloads_path_text=watched_downloads_path_text,
            secondary_watched_downloads_path_text=secondary_watched_downloads_path_text,
        )

        try:
            combined_known_zip_paths: list[Path] = []
            seen_paths: set[Path] = set()
            for watched_path in watched_paths:
                for zip_path in initialize_known_zip_paths(watched_path):
                    if zip_path in seen_paths:
                        continue
                    seen_paths.add(zip_path)
                    combined_known_zip_paths.append(zip_path)
            return tuple(combined_known_zip_paths)
        except OSError as exc:
            raise AppShellError(f"Could not initialize watched downloads directories: {exc}") from exc

    def poll_downloads_watch(
        self,
        *,
        watched_downloads_path_text: str,
        secondary_watched_downloads_path_text: str = "",
        known_zip_paths: tuple[Path, ...],
        inventory: ModsInventory,
        nexus_api_key_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> DownloadsWatchPollResult:
        watched_paths = self._parse_and_validate_watched_downloads_path(
            watched_downloads_path_text=watched_downloads_path_text,
            secondary_watched_downloads_path_text=secondary_watched_downloads_path_text,
        )
        nexus_api_key = self._resolve_nexus_api_key(
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
        )

        try:
            poll_results = tuple(
                poll_watched_directory(
                    watched_path=watched_path,
                    known_zip_paths=known_zip_paths,
                    inventory=inventory,
                )
                for watched_path in watched_paths
            )

            enriched_intakes = []
            combined_known_zip_paths: list[Path] = []
            seen_known_zip_paths: set[Path] = set()
            for result in poll_results:
                for zip_path in result.known_zip_paths:
                    if zip_path in seen_known_zip_paths:
                        continue
                    seen_known_zip_paths.add(zip_path)
                    combined_known_zip_paths.append(zip_path)
                for intake in result.intakes:
                    enriched_intakes.append(
                        replace(
                            intake,
                            remote_requirements=evaluate_remote_requirements_for_package_mods(
                                intake.mods,
                                source="downloads_intake",
                                nexus_api_key=nexus_api_key,
                            ),
                        )
                    )

            return DownloadsWatchPollResult(
                watched_path=watched_paths[0],
                known_zip_paths=tuple(combined_known_zip_paths),
                intakes=tuple(enriched_intakes),
            )
        except OSError as exc:
            raise AppShellError(f"Could not poll watched downloads directories: {exc}") from exc

    @staticmethod
    def select_intake_result(
        *,
        intakes: tuple[DownloadsIntakeResult, ...],
        selected_index: int,
    ) -> DownloadsIntakeResult:
        if selected_index < 0 or selected_index >= len(intakes):
            raise AppShellError("Select a detected package first.")
        return intakes[selected_index]

    @staticmethod
    def is_actionable_intake_result(intake: DownloadsIntakeResult) -> bool:
        return intake.classification in _ACTIONABLE_INTAKE_CLASSIFICATIONS

    def build_sandbox_install_plan_from_intake(
        self,
        *,
        intake: DownloadsIntakeResult,
        sandbox_mods_path_text: str,
        sandbox_archive_path_text: str,
        allow_overwrite: bool,
        configured_real_mods_path: Path | None = None,
        nexus_api_key_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> SandboxInstallPlan:
        return self.build_install_plan_from_intake(
            intake=intake,
            install_target=INSTALL_TARGET_SANDBOX_MODS,
            configured_mods_path_text=str(configured_real_mods_path) if configured_real_mods_path else "",
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text="",
            sandbox_archive_path_text=sandbox_archive_path_text,
            allow_overwrite=allow_overwrite,
            configured_real_mods_path=configured_real_mods_path,
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
        )

    def build_install_plan_from_intake(
        self,
        *,
        intake: DownloadsIntakeResult,
        install_target: InstallTargetKind,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        allow_overwrite: bool,
        configured_real_mods_path: Path | None = None,
        nexus_api_key_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> SandboxInstallPlan:
        if not self.is_actionable_intake_result(intake):
            raise AppShellError(
                f"Selected package is not actionable for install planning: {intake.classification}"
            )

        return self.build_install_plan(
            package_path_text=str(intake.package_path),
            install_target=install_target,
            configured_mods_path_text=configured_mods_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text=real_archive_path_text,
            sandbox_archive_path_text=sandbox_archive_path_text,
            allow_overwrite=allow_overwrite,
            configured_real_mods_path=configured_real_mods_path,
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
        )

    def correlate_intakes_with_updates(
        self,
        *,
        intakes: tuple[DownloadsIntakeResult, ...],
        update_report: ModUpdateReport | None,
        guided_update_unique_ids: tuple[str, ...] = tuple(),
    ) -> tuple[IntakeUpdateCorrelation, ...]:
        return tuple(
            self.correlate_intake_with_updates(
                intake=intake,
                update_report=update_report,
                guided_update_unique_ids=guided_update_unique_ids,
            )
            for intake in intakes
        )

    def correlate_intake_with_updates(
        self,
        *,
        intake: DownloadsIntakeResult,
        update_report: ModUpdateReport | None,
        guided_update_unique_ids: tuple[str, ...] = tuple(),
    ) -> IntakeUpdateCorrelation:
        actionable = self.is_actionable_intake_result(intake)

        update_available_keys: dict[str, str] = {}
        if update_report is not None:
            for status in update_report.statuses:
                if status.state != "update_available":
                    continue
                key = canonicalize_unique_id(status.unique_id)
                if key not in update_available_keys:
                    update_available_keys[key] = status.unique_id

        matched_update_available = _sorted_unique_ids(
            unique_id
            for unique_id in intake.matched_installed_unique_ids
            if canonicalize_unique_id(unique_id) in update_available_keys
        )
        guided_keys = {canonicalize_unique_id(value) for value in guided_update_unique_ids}
        matched_guided = _sorted_unique_ids(
            unique_id
            for unique_id in intake.matched_installed_unique_ids
            if canonicalize_unique_id(unique_id) in guided_keys
        )

        summary, next_step = _build_intake_flow_messages(
            intake=intake,
            actionable=actionable,
            matched_update_available=matched_update_available,
            matched_guided=matched_guided,
        )

        return IntakeUpdateCorrelation(
            intake=intake,
            actionable=actionable,
            matched_update_available_unique_ids=matched_update_available,
            matched_guided_update_unique_ids=matched_guided,
            summary=summary,
            next_step=next_step,
        )

    @staticmethod
    def build_manual_update_flow_hint(
        *,
        unique_id: str,
        watched_downloads_path_text: str,
        secondary_watched_downloads_path_text: str = "",
        watcher_running: bool,
    ) -> str:
        watched_path = AppShellService._format_watched_download_paths_for_guidance(
            watched_downloads_path_text=watched_downloads_path_text,
            secondary_watched_downloads_path_text=secondary_watched_downloads_path_text,
        )
        watch_step = (
            "Watcher is running; it will detect new zip files added now."
            if watcher_running
            else "Start watch before downloading, so new zip files are detected."
        )
        return (
            f"Manual update flow for {unique_id}:\n"
            "1. Open remote page and download manually.\n"
            f"2. Save the zip into {watched_path}\n"
            f"3. {watch_step}\n"
            "4. In detected packages, select that zip and click 'Plan selected intake'.\n"
            "5. Review plan warnings/dependencies, then run install explicitly."
        )

    def build_sandbox_install_plan(
        self,
        package_path_text: str,
        sandbox_mods_path_text: str,
        sandbox_archive_path_text: str,
        *,
        allow_overwrite: bool,
        configured_real_mods_path: Path | None = None,
        nexus_api_key_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> SandboxInstallPlan:
        return self.build_install_plan(
            package_path_text=package_path_text,
            install_target=INSTALL_TARGET_SANDBOX_MODS,
            configured_mods_path_text=str(configured_real_mods_path) if configured_real_mods_path else "",
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text="",
            sandbox_archive_path_text=sandbox_archive_path_text,
            allow_overwrite=allow_overwrite,
            configured_real_mods_path=configured_real_mods_path,
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
        )

    def build_install_plan(
        self,
        *,
        package_path_text: str,
        install_target: InstallTargetKind,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        allow_overwrite: bool,
        configured_real_mods_path: Path | None = None,
        nexus_api_key_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> SandboxInstallPlan:
        package_path = self._parse_and_validate_zip_path(package_path_text)
        nexus_api_key = self._resolve_nexus_api_key(
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
        )

        destination_mods_path, destination_archive_path = self._resolve_install_destination_paths(
            install_target=install_target,
            configured_mods_path_text=configured_mods_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text=real_archive_path_text,
            sandbox_archive_path_text=sandbox_archive_path_text,
        )

        effective_real_mods_path = configured_real_mods_path
        if effective_real_mods_path is None and configured_mods_path_text.strip():
            effective_real_mods_path = self._parse_and_validate_mods_path(configured_mods_path_text)

        safety = self.evaluate_install_target_safety(
            install_target=install_target,
            destination_mods_path=destination_mods_path,
            configured_real_mods_path=effective_real_mods_path,
        )
        if not safety.allowed:
            assert safety.message is not None
            raise AppShellError(safety.message)

        try:
            plan = build_sandbox_install_plan_service(
                package_path=package_path,
                sandbox_mods_path=destination_mods_path,
                sandbox_archive_path=destination_archive_path,
                allow_overwrite=allow_overwrite,
            )
            inventory = scan_mods_directory(
                destination_mods_path,
                excluded_paths=(destination_archive_path, destination_mods_path / _LEGACY_ARCHIVE_DIRNAME),
            )
            dependency_findings = _evaluate_sandbox_plan_dependencies(
                plan=plan,
                base_findings=plan.dependency_findings,
                installed_inventory=inventory,
            )
            plan_with_dependency_preflight = _apply_dependency_preflight_to_plan(
                plan,
                dependency_findings,
            )
            inspected_mods = _inspect_package_mod_entries(package_path)
            remote_requirements = evaluate_remote_requirements_for_package_mods(
                inspected_mods,
                source="sandbox_plan",
                nexus_api_key=nexus_api_key,
            )
            return replace(
                plan_with_dependency_preflight,
                remote_requirements=remote_requirements,
                destination_kind=install_target,
            )
        except (SandboxInstallError, zipfile.BadZipFile) as exc:
            raise AppShellError(str(exc)) from exc
        except OSError as exc:
            raise AppShellError(f"Could not build sandbox install plan: {exc}") from exc

    def execute_sandbox_install_plan(
        self,
        plan: SandboxInstallPlan,
        *,
        confirm_real_destination: bool = False,
    ) -> SandboxInstallResult:
        review = self.review_install_execution(plan)
        if not review.allowed:
            raise AppShellError(review.message)
        if review.requires_explicit_approval and not confirm_real_destination:
            raise AppShellError(review.message)

        try:
            result = execute_sandbox_install_plan_service(plan)
            completed_result = replace(result, destination_kind=plan.destination_kind)
            self._record_completed_install_operation(plan=plan, result=completed_result)
            return completed_result
        except SandboxFileLockError as exc:
            raise AppShellError(str(exc), detail_message=exc.technical_detail) from exc
        except SandboxInstallError as exc:
            raise AppShellError(str(exc)) from exc
        except OSError as exc:
            raise AppShellError(f"Sandbox install failed: {exc}") from exc

    def build_mod_removal_plan(
        self,
        *,
        scan_target: ScanTargetKind,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        mod_folder_path_text: str,
    ) -> ModRemovalPlan:
        destination_mods_path, destination_archive_path = self._resolve_install_destination_paths(
            install_target=scan_target,
            configured_mods_path_text=configured_mods_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text=real_archive_path_text,
            sandbox_archive_path_text=sandbox_archive_path_text,
        )

        configured_real_mods_path: Path | None = None
        if configured_mods_path_text.strip():
            configured_real_mods_path = self._parse_and_validate_mods_path(configured_mods_path_text)

        safety = self.evaluate_install_target_safety(
            install_target=scan_target,
            destination_mods_path=destination_mods_path,
            configured_real_mods_path=configured_real_mods_path,
        )
        if not safety.allowed:
            assert safety.message is not None
            raise AppShellError(safety.message)

        raw_target = mod_folder_path_text.strip()
        if not raw_target:
            raise AppShellError("Select an installed mod row first.")

        target_mod_path = Path(raw_target).expanduser()
        if not target_mod_path.exists() or not target_mod_path.is_dir():
            raise AppShellError(f"Selected mod folder is not accessible: {target_mod_path}")

        mods_root_resolved = destination_mods_path.resolve()
        target_resolved = target_mod_path.resolve()
        if target_resolved.parent != mods_root_resolved:
            raise AppShellError(
                "Selected mod folder must be a direct child of the selected Mods destination."
            )

        return ModRemovalPlan(
            destination_kind=scan_target,
            mods_path=destination_mods_path,
            archive_path=destination_archive_path,
            target_mod_path=target_mod_path,
        )

    def execute_mod_removal(
        self,
        plan: ModRemovalPlan,
        *,
        confirm_removal: bool = False,
    ) -> ModRemovalResult:
        if not confirm_removal:
            raise AppShellError("Explicit confirmation is required before mod removal.")

        try:
            archived_target = remove_mod_to_archive_service(
                target_mod_path=plan.target_mod_path,
                mods_root=plan.mods_path,
                archive_root=plan.archive_path,
            )
            inventory = scan_mods_directory(
                plan.mods_path,
                excluded_paths=(plan.archive_path, plan.mods_path / _LEGACY_ARCHIVE_DIRNAME),
            )
        except SandboxFileLockError as exc:
            raise AppShellError(str(exc), detail_message=exc.technical_detail) from exc
        except SandboxInstallError as exc:
            raise AppShellError(str(exc)) from exc
        except OSError as exc:
            raise AppShellError(f"Mod removal failed: {exc}") from exc

        return ModRemovalResult(
            plan=plan,
            removed_target=plan.target_mod_path,
            archived_target=archived_target,
            scan_context_path=plan.mods_path,
            inventory=inventory,
            destination_kind=plan.destination_kind,
        )

    def list_archived_entries(
        self,
        *,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        existing_config: AppConfig | None = None,
    ) -> tuple[ArchivedModEntry, ...]:
        real_mods_path = self._resolve_real_mods_path(
            configured_mods_path_text=configured_mods_path_text,
            existing_config=existing_config,
        )
        real_archive_path = self._resolve_archive_path_for_source(
            source_kind=ARCHIVE_SOURCE_REAL,
            real_mods_path=real_mods_path,
            sandbox_mods_path=None,
            real_archive_path_text=real_archive_path_text,
            sandbox_archive_path_text=sandbox_archive_path_text,
            existing_config=existing_config,
        )

        entries = list(
            list_archived_mod_entries(
                archive_root=real_archive_path,
                source_kind=ARCHIVE_SOURCE_REAL,
            )
        )

        sandbox_mods_path = self._resolve_optional_sandbox_mods_path(
            sandbox_mods_path_text=sandbox_mods_path_text,
            existing_config=existing_config,
        )
        if sandbox_mods_path is not None:
            sandbox_archive_path = self._resolve_archive_path_for_source(
                source_kind=ARCHIVE_SOURCE_SANDBOX,
                real_mods_path=real_mods_path,
                sandbox_mods_path=sandbox_mods_path,
                real_archive_path_text=real_archive_path_text,
                sandbox_archive_path_text=sandbox_archive_path_text,
                existing_config=existing_config,
            )
            entries.extend(
                list_archived_mod_entries(
                    archive_root=sandbox_archive_path,
                    source_kind=ARCHIVE_SOURCE_SANDBOX,
                )
            )

        entries.sort(
            key=lambda entry: (
                0 if entry.source_kind == ARCHIVE_SOURCE_REAL else 1,
                entry.target_folder_name.casefold(),
                entry.archived_folder_name.casefold(),
            )
        )
        return tuple(entries)

    def build_archive_restore_plan(
        self,
        *,
        source_kind: ArchiveSourceKind,
        archived_path_text: str,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        existing_config: AppConfig | None = None,
    ) -> ArchiveRestorePlan:
        if source_kind not in {ARCHIVE_SOURCE_REAL, ARCHIVE_SOURCE_SANDBOX}:
            raise AppShellError(f"Unknown archive source: {source_kind}")

        restore_target = self._infer_restore_target_from_source(source_kind)
        destination_mods_path, destination_archive_path = self._resolve_install_destination_paths(
            install_target=restore_target,
            configured_mods_path_text=configured_mods_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text=real_archive_path_text,
            sandbox_archive_path_text=sandbox_archive_path_text,
        )

        configured_real_mods_path = self._resolve_optional_real_mods_path(
            configured_mods_path_text=configured_mods_path_text,
            existing_config=existing_config,
        )
        safety = self.evaluate_install_target_safety(
            install_target=restore_target,
            destination_mods_path=destination_mods_path,
            configured_real_mods_path=configured_real_mods_path,
        )
        if not safety.allowed:
            assert safety.message is not None
            raise AppShellError(safety.message)

        archived_entry = self._resolve_archived_entry(
            source_kind=source_kind,
            archived_path_text=archived_path_text,
            configured_mods_path_text=configured_mods_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text=real_archive_path_text,
            sandbox_archive_path_text=sandbox_archive_path_text,
            existing_config=existing_config,
        )
        destination_target_path = destination_mods_path / archived_entry.target_folder_name
        if destination_target_path.exists():
            raise AppShellError(
                f"Restore target already exists in destination Mods directory: {destination_target_path}"
            )

        return ArchiveRestorePlan(
            entry=archived_entry,
            destination_kind=restore_target,
            destination_mods_path=destination_mods_path,
            destination_target_path=destination_target_path,
            scan_excluded_paths=(
                destination_archive_path,
                destination_mods_path / _LEGACY_ARCHIVE_DIRNAME,
            ),
        )

    def execute_archive_restore(
        self,
        plan: ArchiveRestorePlan,
        *,
        confirm_restore: bool = False,
    ) -> ArchiveRestoreResult:
        if not confirm_restore:
            raise AppShellError("Explicit confirmation is required before archive restore.")

        try:
            restored_target = restore_archived_mod_entry(
                archive_root=plan.entry.archive_root,
                archived_path=plan.entry.archived_path,
                destination_mods_root=plan.destination_mods_path,
                destination_folder_name=plan.entry.target_folder_name,
            )
            inventory = scan_mods_directory(
                plan.destination_mods_path,
                excluded_paths=plan.scan_excluded_paths,
            )
        except ArchiveManagerError as exc:
            raise AppShellError(str(exc)) from exc
        except OSError as exc:
            raise AppShellError(f"Archive restore failed: {exc}") from exc

        return ArchiveRestoreResult(
            plan=plan,
            restored_target=restored_target,
            scan_context_path=plan.destination_mods_path,
            inventory=inventory,
            destination_kind=plan.destination_kind,
        )

    def build_archive_delete_plan(
        self,
        *,
        source_kind: ArchiveSourceKind,
        archived_path_text: str,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        existing_config: AppConfig | None = None,
    ) -> ArchiveDeletePlan:
        if source_kind not in {ARCHIVE_SOURCE_REAL, ARCHIVE_SOURCE_SANDBOX}:
            raise AppShellError(f"Unknown archive source: {source_kind}")

        archived_entry = self._resolve_archived_entry(
            source_kind=source_kind,
            archived_path_text=archived_path_text,
            configured_mods_path_text=configured_mods_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text=real_archive_path_text,
            sandbox_archive_path_text=sandbox_archive_path_text,
            existing_config=existing_config,
        )
        return ArchiveDeletePlan(entry=archived_entry)

    def execute_archive_delete(
        self,
        plan: ArchiveDeletePlan,
        *,
        confirm_delete: bool = False,
    ) -> ArchiveDeleteResult:
        if not confirm_delete:
            raise AppShellError("Explicit confirmation is required before permanent archive delete.")

        try:
            deleted_path = delete_archived_mod_entry(
                archive_root=plan.entry.archive_root,
                archived_path=plan.entry.archived_path,
            )
        except ArchiveManagerError as exc:
            raise AppShellError(str(exc)) from exc
        except OSError as exc:
            raise AppShellError(f"Permanent archive delete failed: {exc}") from exc

        return ArchiveDeleteResult(
            plan=plan,
            deleted_path=deleted_path,
        )

    def list_mod_rollback_candidates(
        self,
        *,
        scan_target: ScanTargetKind,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        mod_folder_path_text: str,
        mod_unique_id_text: str,
        existing_config: AppConfig | None = None,
    ) -> tuple[ArchivedModEntry, ...]:
        source_kind = self._archive_source_for_scan_target(scan_target)
        mods_path, archive_path = self._resolve_install_destination_paths(
            install_target=scan_target,
            configured_mods_path_text=configured_mods_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text=real_archive_path_text,
            sandbox_archive_path_text=sandbox_archive_path_text,
        )
        target_mod_path = self._parse_and_validate_selected_mod_path(
            mods_path=mods_path,
            mod_folder_path_text=mod_folder_path_text,
        )
        unique_id = mod_unique_id_text.strip()
        if not unique_id:
            raise AppShellError("Selected installed mod does not include a valid UniqueID.")

        all_entries = list_archived_mod_entries(
            archive_root=archive_path,
            source_kind=source_kind,
        )
        unique_key = canonicalize_unique_id(unique_id)
        folder_key = target_mod_path.name.casefold()
        candidates = tuple(
            entry
            for entry in all_entries
            if entry.unique_id is not None
            and canonicalize_unique_id(entry.unique_id) == unique_key
            and entry.target_folder_name.casefold() == folder_key
        )
        return tuple(
            sorted(
                candidates,
                key=lambda entry: (
                    _version_sort_key(entry.version),
                    entry.archived_folder_name.casefold(),
                ),
                reverse=True,
            )
        )

    def build_mod_rollback_plan(
        self,
        *,
        scan_target: ScanTargetKind,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        mod_folder_path_text: str,
        mod_unique_id_text: str,
        mod_version_text: str,
        archived_candidate_path_text: str,
        existing_config: AppConfig | None = None,
    ) -> ModRollbackPlan:
        _ = existing_config
        source_kind = self._archive_source_for_scan_target(scan_target)
        mods_path, archive_path = self._resolve_install_destination_paths(
            install_target=scan_target,
            configured_mods_path_text=configured_mods_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text=real_archive_path_text,
            sandbox_archive_path_text=sandbox_archive_path_text,
        )
        target_mod_path = self._parse_and_validate_selected_mod_path(
            mods_path=mods_path,
            mod_folder_path_text=mod_folder_path_text,
        )
        unique_id = mod_unique_id_text.strip()
        if not unique_id:
            raise AppShellError("Selected installed mod does not include a valid UniqueID.")

        candidate_path_text = archived_candidate_path_text.strip()
        if not candidate_path_text:
            raise AppShellError("Select an archived rollback candidate first.")
        candidate_path = Path(candidate_path_text).expanduser()

        candidates = self.list_mod_rollback_candidates(
            scan_target=scan_target,
            configured_mods_path_text=configured_mods_path_text,
            sandbox_mods_path_text=sandbox_mods_path_text,
            real_archive_path_text=real_archive_path_text,
            sandbox_archive_path_text=sandbox_archive_path_text,
            mod_folder_path_text=str(target_mod_path),
            mod_unique_id_text=unique_id,
        )
        selected_candidate: ArchivedModEntry | None = None
        for candidate in candidates:
            if _paths_deterministically_match(candidate.archived_path, candidate_path):
                selected_candidate = candidate
                break
        if selected_candidate is None:
            raise AppShellError(
                f"Selected archived rollback candidate is not a safe match: {candidate_path}"
            )

        current_archive_path = allocate_archive_destination(
            archive_root=archive_path,
            target_folder_name=target_mod_path.name,
        )
        return ModRollbackPlan(
            destination_kind=scan_target,
            mods_path=mods_path,
            archive_path=archive_path,
            current_mod_path=target_mod_path,
            current_unique_id=unique_id,
            current_version=mod_version_text.strip() or "<unknown>",
            rollback_entry=selected_candidate,
            current_archive_path=current_archive_path,
        )

    def execute_mod_rollback(
        self,
        plan: ModRollbackPlan,
        *,
        confirm_rollback: bool = False,
    ) -> ModRollbackResult:
        if not confirm_rollback:
            raise AppShellError("Explicit confirmation is required before rollback.")

        try:
            archived_current_target, restored_target = rollback_installed_mod_from_archive(
                current_mod_path=plan.current_mod_path,
                mods_root=plan.mods_path,
                archive_root=plan.archive_path,
                archived_candidate_path=plan.rollback_entry.archived_path,
            )
            inventory = scan_mods_directory(
                plan.mods_path,
                excluded_paths=(plan.archive_path, plan.mods_path / _LEGACY_ARCHIVE_DIRNAME),
            )
        except ArchiveManagerError as exc:
            raise AppShellError(str(exc)) from exc
        except OSError as exc:
            raise AppShellError(f"Mod rollback failed: {exc}") from exc

        return ModRollbackResult(
            plan=plan,
            archived_current_target=archived_current_target,
            restored_target=restored_target,
            scan_context_path=plan.mods_path,
            inventory=inventory,
            destination_kind=plan.destination_kind,
        )

    def evaluate_install_target_safety(
        self,
        *,
        install_target: InstallTargetKind,
        destination_mods_path: Path,
        configured_real_mods_path: Path | None,
    ) -> InstallTargetSafetyDecision:
        if install_target not in {INSTALL_TARGET_SANDBOX_MODS, INSTALL_TARGET_CONFIGURED_REAL_MODS}:
            return InstallTargetSafetyDecision(
                allowed=False,
                message=f"Unknown install target: {install_target}",
                requires_explicit_confirmation=False,
            )

        if configured_real_mods_path is None:
            if install_target == INSTALL_TARGET_SANDBOX_MODS:
                return InstallTargetSafetyDecision(
                    allowed=True,
                    message="Sandbox destination selected.",
                    requires_explicit_confirmation=False,
                )
            return InstallTargetSafetyDecision(
                allowed=False,
                message="Configured real Mods path is required for destination safety checks.",
                requires_explicit_confirmation=False,
            )

        if install_target == INSTALL_TARGET_SANDBOX_MODS:
            if _paths_deterministically_match(destination_mods_path, configured_real_mods_path):
                return InstallTargetSafetyDecision(
                    allowed=False,
                    message=(
                        "Sandbox install target matches configured real Mods path. "
                        "Select sandbox destination or choose a different path."
                    ),
                    requires_explicit_confirmation=False,
                )

            return InstallTargetSafetyDecision(
                allowed=True,
                message="Sandbox destination selected.",
                requires_explicit_confirmation=False,
            )

        if not _paths_deterministically_match(destination_mods_path, configured_real_mods_path):
            return InstallTargetSafetyDecision(
                allowed=False,
                message=(
                    "Real install destination must exactly match the configured real Mods path."
                ),
                requires_explicit_confirmation=False,
            )

        return InstallTargetSafetyDecision(
            allowed=True,
            message="Real game Mods destination selected. Explicit confirmation required before install.",
            requires_explicit_confirmation=True,
        )

    def _build_config(
        self,
        *,
        game_path: Path,
        mods_path: Path,
        existing_config: AppConfig | None,
    ) -> AppConfig:
        if existing_config is not None:
            return AppConfig(
                game_path=game_path,
                mods_path=mods_path,
                app_data_path=existing_config.app_data_path,
                sandbox_mods_path=existing_config.sandbox_mods_path,
                sandbox_archive_path=existing_config.sandbox_archive_path,
                real_archive_path=existing_config.real_archive_path,
                watched_downloads_path=existing_config.watched_downloads_path,
                secondary_watched_downloads_path=existing_config.secondary_watched_downloads_path,
                nexus_api_key=existing_config.nexus_api_key,
                scan_target=existing_config.scan_target,
                install_target=existing_config.install_target,
            )

        return AppConfig(
            game_path=game_path,
            mods_path=mods_path,
            app_data_path=self._state_file.parent,
            scan_target=SCAN_TARGET_CONFIGURED_REAL_MODS,
            install_target=INSTALL_TARGET_SANDBOX_MODS,
        )

    @staticmethod
    def _resolve_nexus_api_key(
        *,
        nexus_api_key_text: str,
        existing_config: AppConfig | None,
        allow_environment_fallback: bool = True,
    ) -> str | None:
        api_key, _ = AppShellService._resolve_nexus_api_key_with_source(
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
            allow_environment_fallback=allow_environment_fallback,
        )
        return api_key

    @staticmethod
    def _resolve_nexus_api_key_with_source(
        *,
        nexus_api_key_text: str,
        existing_config: AppConfig | None,
        allow_environment_fallback: bool,
    ) -> tuple[str | None, str]:
        entered = normalize_nexus_api_key(nexus_api_key_text)
        if entered:
            return entered, "entered"

        if existing_config is not None:
            saved = normalize_nexus_api_key(existing_config.nexus_api_key)
            if saved:
                return saved, "saved_config"

        if allow_environment_fallback:
            env_value = normalize_nexus_api_key(os.getenv(NEXUS_API_KEY_ENV, ""))
            if env_value:
                return env_value, "environment"

        return None, "none"

    def _resolve_real_mods_path(
        self,
        *,
        configured_mods_path_text: str,
        existing_config: AppConfig | None,
    ) -> Path:
        if configured_mods_path_text.strip():
            return self._parse_and_validate_mods_path(configured_mods_path_text)
        if existing_config is not None:
            return self._parse_and_validate_existing_directory(
                existing_config.mods_path,
                "Saved configured real Mods path is not accessible",
            )
        raise AppShellError("Configured real Mods directory is required.")

    def _resolve_optional_real_mods_path(
        self,
        *,
        configured_mods_path_text: str,
        existing_config: AppConfig | None,
    ) -> Path | None:
        if configured_mods_path_text.strip():
            return self._parse_and_validate_mods_path(configured_mods_path_text)
        if existing_config is not None:
            return self._parse_and_validate_existing_directory(
                existing_config.mods_path,
                "Saved configured real Mods path is not accessible",
            )
        return None

    def _resolve_optional_sandbox_mods_path(
        self,
        *,
        sandbox_mods_path_text: str,
        existing_config: AppConfig | None,
    ) -> Path | None:
        if sandbox_mods_path_text.strip():
            return self._parse_and_validate_sandbox_mods_path(sandbox_mods_path_text)
        if existing_config is not None and existing_config.sandbox_mods_path is not None:
            return self._parse_and_validate_existing_directory(
                existing_config.sandbox_mods_path,
                "Saved sandbox Mods path is not accessible",
            )
        return None

    def _resolve_sandbox_dev_launch_context(
        self,
        *,
        game_path_text: str,
        sandbox_mods_path_text: str,
        configured_mods_path_text: str,
        existing_config: AppConfig | None,
    ) -> tuple[Path, Path, LaunchCommand]:
        game_path = self._resolve_game_path(game_path_text, existing_config)
        sandbox_mods_path = self._resolve_optional_sandbox_mods_path(
            sandbox_mods_path_text=sandbox_mods_path_text,
            existing_config=existing_config,
        )
        if sandbox_mods_path is None:
            raise AppShellError("Sandbox Mods directory is required for sandbox dev launch.")

        real_mods_path = self._resolve_optional_real_mods_path(
            configured_mods_path_text=configured_mods_path_text,
            existing_config=existing_config,
        )
        if real_mods_path is not None and _paths_deterministically_match(
            sandbox_mods_path,
            real_mods_path,
        ):
            raise AppShellError(
                "Sandbox dev launch is blocked: sandbox Mods path matches the configured real Mods path."
            )

        try:
            command = resolve_launch_command(game_path=game_path, mode="smapi")
        except GameLaunchError as exc:
            raise AppShellError(str(exc)) from exc

        if command.executable_path.suffix.casefold() == ".sh":
            raise AppShellError(
                "Sandbox dev launch requires a direct SMAPI executable target; shell-script SMAPI wrappers are not supported in this stage."
            )

        sandbox_command = LaunchCommand(
            mode=command.mode,
            executable_path=command.executable_path,
            argv=(*command.argv, "--mods-path", str(sandbox_mods_path)),
        )
        return game_path, sandbox_mods_path, sandbox_command

    def _resolve_sandbox_mod_sync_context(
        self,
        *,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        selected_mod_folder_paths_text: Iterable[str],
        existing_config: AppConfig | None,
    ) -> tuple[Path, Path, tuple[Path, ...]]:
        real_mods_path = self._resolve_optional_real_mods_path(
            configured_mods_path_text=configured_mods_path_text,
            existing_config=existing_config,
        )
        if real_mods_path is None:
            raise AppShellError("Configured real Mods directory is required for sandbox sync.")

        sandbox_mods_path = self._resolve_optional_sandbox_mods_path(
            sandbox_mods_path_text=sandbox_mods_path_text,
            existing_config=existing_config,
        )
        if sandbox_mods_path is None:
            raise AppShellError("Sandbox Mods directory is required for sandbox sync.")

        if _paths_deterministically_match(real_mods_path, sandbox_mods_path):
            raise AppShellError(
                "Sandbox sync is blocked: sandbox Mods path matches the configured real Mods path."
            )

        source_paths = self._resolve_selected_real_mod_paths(
            real_mods_path=real_mods_path,
            selected_mod_folder_paths_text=selected_mod_folder_paths_text,
        )

        conflicting_targets = tuple(
            sandbox_mods_path / source_path.name
            for source_path in source_paths
            if (sandbox_mods_path / source_path.name).exists()
        )
        if conflicting_targets:
            conflict_names = ", ".join(target.name for target in conflicting_targets[:3])
            if len(conflicting_targets) == 1:
                raise AppShellError(
                    "Sandbox sync blocked: sandbox target already exists for "
                    f"{conflict_names}. Remove or archive the sandbox copy first."
                )
            raise AppShellError(
                "Sandbox sync blocked: sandbox targets already exist for "
                f"{conflict_names}. Remove or archive those sandbox copies first."
            )

        return real_mods_path, sandbox_mods_path, source_paths

    def _resolve_sandbox_mod_promotion_context(
        self,
        *,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        selected_mod_folder_paths_text: Iterable[str],
        existing_config: AppConfig | None,
    ) -> tuple[Path, Path, Path, tuple[Path, ...], ModsInventory]:
        real_mods_path = self._resolve_optional_real_mods_path(
            configured_mods_path_text=configured_mods_path_text,
            existing_config=existing_config,
        )
        if real_mods_path is None:
            raise AppShellError("Configured real Mods directory is required for sandbox promotion.")

        sandbox_mods_path = self._resolve_optional_sandbox_mods_path(
            sandbox_mods_path_text=sandbox_mods_path_text,
            existing_config=existing_config,
        )
        if sandbox_mods_path is None:
            raise AppShellError("Sandbox Mods directory is required for sandbox promotion.")

        if _paths_deterministically_match(real_mods_path, sandbox_mods_path):
            raise AppShellError(
                "Sandbox promotion is blocked: sandbox Mods path matches the configured real Mods path."
            )

        archive_path = self._parse_and_validate_archive_path(
            archive_path_text=real_archive_path_text,
            destination_mods_path=real_mods_path,
            field_label="Real Mods archive path",
            default_archive_dir_name=_DEFAULT_REAL_ARCHIVE_DIRNAME,
        )

        source_paths = self._resolve_selected_sandbox_mod_paths(
            sandbox_mods_path=sandbox_mods_path,
            selected_mod_folder_paths_text=selected_mod_folder_paths_text,
        )
        source_inventory = scan_mods_directory(
            sandbox_mods_path,
            excluded_paths=(sandbox_mods_path / _LEGACY_ARCHIVE_DIRNAME,),
        )
        return real_mods_path, sandbox_mods_path, archive_path, source_paths, source_inventory

    def _build_sandbox_mods_promotion_plan(
        self,
        *,
        real_mods_path: Path,
        sandbox_mods_path: Path,
        archive_path: Path,
        source_paths: tuple[Path, ...],
        source_inventory: ModsInventory,
    ) -> SandboxInstallPlan:
        selected_mods_by_path = {
            str(mod.folder_path): mod
            for mod in source_inventory.mods
            if str(mod.folder_path) in {str(path) for path in source_paths}
        }
        entries: list[SandboxInstallPlanEntry] = []
        has_replace_entries = False

        for source_path in source_paths:
            target_path = real_mods_path / source_path.name
            target_exists = target_path.exists()
            archive_target_path: Path | None = None
            action = INSTALL_NEW
            warnings = ["Promoted from sandbox Mods selection via explicit managed action."]
            source_mod = selected_mods_by_path.get(str(source_path))

            if target_exists:
                has_replace_entries = True
                action = OVERWRITE_WITH_ARCHIVE
                archive_target_path = _build_archive_destination_service(
                    archive_root=archive_path,
                    target_folder_name=target_path.name,
                )
                warnings.append(
                    "Existing REAL Mods target will be archived before replacement."
                )

            entries.append(
                SandboxInstallPlanEntry(
                    name=source_mod.name if source_mod is not None else source_path.name,
                    unique_id=(
                        source_mod.unique_id if source_mod is not None else source_path.name
                    ),
                    version=source_mod.version if source_mod is not None else "",
                    source_manifest_path=(
                        str(source_mod.manifest_path)
                        if source_mod is not None
                        else str(source_path / "manifest.json")
                    ),
                    source_root_path=str(source_path),
                    target_path=target_path,
                    action=action,
                    target_exists=target_exists,
                    archive_path=archive_target_path,
                    can_install=True,
                    warnings=tuple(warnings),
                )
            )

        entries.sort(key=lambda item: (item.target_path.name.lower(), item.unique_id.casefold()))
        plan_warnings = [
            "Sandbox promotion writes into the configured real Mods path.",
        ]
        if has_replace_entries:
            plan_warnings.append(
                "Conflicting live targets will be archived before replacement."
            )
            plan_warnings.append(
                "Recovery remains per-entry and depends on recorded archive history."
            )

        return SandboxInstallPlan(
            package_path=_promotion_history_source_marker(
                sandbox_mods_path=sandbox_mods_path,
                source_paths=source_paths,
            ),
            sandbox_mods_path=real_mods_path,
            sandbox_archive_path=archive_path,
            entries=tuple(entries),
            package_findings=tuple(),
            package_warnings=tuple(),
            plan_warnings=tuple(plan_warnings),
            dependency_findings=tuple(),
            remote_requirements=tuple(),
            destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        )

    def _rollback_sandbox_mods_promotion_entries(
        self,
        entries: tuple[SandboxInstallPlanEntry, ...],
    ) -> tuple[str, ...]:
        errors: list[str] = []
        for entry in reversed(entries):
            if entry.action == INSTALL_NEW:
                if not entry.target_path.exists():
                    continue
                try:
                    _remove_path_for_promotion_rollback(entry.target_path)
                except OSError as exc:
                    errors.append(
                        f"could not remove promoted target {entry.target_path}: {exc}"
                    )
                continue

            if entry.action == OVERWRITE_WITH_ARCHIVE:
                archive_path = entry.archive_path
                if entry.target_path.exists():
                    try:
                        _remove_path_for_promotion_rollback(entry.target_path)
                    except OSError as exc:
                        errors.append(
                            f"could not remove replaced target {entry.target_path}: {exc}"
                        )
                        continue

                if archive_path is None:
                    errors.append(
                        f"missing archive path for rollback of {entry.target_path}"
                    )
                    continue
                if not archive_path.exists():
                    errors.append(
                        f"archived target is missing for rollback of {entry.target_path}: "
                        f"{archive_path}"
                    )
                    continue
                try:
                    archive_path.rename(entry.target_path)
                except OSError as exc:
                    errors.append(
                        f"could not restore archived target {archive_path} -> "
                        f"{entry.target_path}: {exc}"
                    )
        return tuple(errors)

    def _remaining_sandbox_mods_promotion_state(
        self,
        entries: tuple[SandboxInstallPlanEntry, ...],
    ) -> tuple[
        tuple[SandboxInstallPlanEntry, ...],
        tuple[Path, ...],
        tuple[Path, ...],
    ]:
        remaining_entries: list[SandboxInstallPlanEntry] = []
        installed_targets: list[Path] = []
        archived_targets: list[Path] = []

        for entry in entries:
            if entry.action == INSTALL_NEW:
                if not entry.target_path.exists():
                    continue
                remaining_entries.append(
                    replace(
                        entry,
                        warnings=entry.warnings
                        + (
                            "Partial sandbox promotion failure: rollback did not remove this REAL Mods target.",
                        ),
                    )
                )
                installed_targets.append(entry.target_path)
                continue

            if entry.action != OVERWRITE_WITH_ARCHIVE:
                continue

            archive_exists = entry.archive_path is not None and entry.archive_path.exists()
            target_exists = entry.target_path.exists()
            if not archive_exists and not target_exists:
                continue

            remaining_entries.append(
                replace(
                    entry,
                    warnings=entry.warnings
                    + (
                        "Partial sandbox promotion failure: rollback did not fully restore this REAL Mods target.",
                    ),
                )
            )
            if target_exists:
                installed_targets.append(entry.target_path)
            if archive_exists and entry.archive_path is not None:
                archived_targets.append(entry.archive_path)

        remaining_entries.sort(
            key=lambda item: (item.target_path.name.lower(), item.unique_id.casefold())
        )
        return (
            tuple(remaining_entries),
            tuple(sorted(installed_targets, key=lambda path: path.name.lower())),
            tuple(sorted(archived_targets, key=lambda path: path.name.lower())),
        )

    def _resolve_selected_real_mod_paths(
        self,
        *,
        real_mods_path: Path,
        selected_mod_folder_paths_text: Iterable[str],
    ) -> tuple[Path, ...]:
        deduplicated_paths: list[Path] = []
        seen_keys: set[str] = set()
        for raw_value in selected_mod_folder_paths_text:
            path_text = str(raw_value).strip()
            if not path_text:
                continue
            source_path = Path(path_text).expanduser()
            key = str(source_path.resolve(strict=False))
            if os.name == "nt":
                key = key.casefold()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduplicated_paths.append(source_path)

        if not deduplicated_paths:
            raise AppShellError("Select at least one installed mod row to sync to sandbox.")

        validated_paths = [
            self._parse_and_validate_selected_mod_path(
                mods_path=real_mods_path,
                mod_folder_path_text=str(source_path),
            )
            for source_path in deduplicated_paths
        ]
        return tuple(validated_paths)

    def _resolve_selected_sandbox_mod_paths(
        self,
        *,
        sandbox_mods_path: Path,
        selected_mod_folder_paths_text: Iterable[str],
    ) -> tuple[Path, ...]:
        deduplicated_paths: list[Path] = []
        seen_keys: set[str] = set()
        for raw_value in selected_mod_folder_paths_text:
            path_text = str(raw_value).strip()
            if not path_text:
                continue
            source_path = Path(path_text).expanduser()
            key = str(source_path.resolve(strict=False))
            if os.name == "nt":
                key = key.casefold()
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduplicated_paths.append(source_path)

        if not deduplicated_paths:
            raise AppShellError("Select at least one installed sandbox mod row to promote.")

        validated_paths = [
            self._parse_and_validate_selected_mod_path(
                mods_path=sandbox_mods_path,
                mod_folder_path_text=str(source_path),
            )
            for source_path in deduplicated_paths
        ]
        return tuple(validated_paths)

    def _resolve_archive_path_for_source(
        self,
        *,
        source_kind: ArchiveSourceKind,
        real_mods_path: Path | None,
        sandbox_mods_path: Path | None,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        existing_config: AppConfig | None,
    ) -> Path:
        if source_kind == ARCHIVE_SOURCE_REAL:
            if real_mods_path is None:
                raise AppShellError("Configured real Mods directory is required for real archive operations.")
            archive_text = real_archive_path_text
            if not archive_text.strip() and existing_config is not None and existing_config.real_archive_path:
                archive_text = str(existing_config.real_archive_path)
            return self._parse_and_validate_archive_path(
                archive_path_text=archive_text,
                destination_mods_path=real_mods_path,
                field_label="Real Mods archive path",
                default_archive_dir_name=_DEFAULT_REAL_ARCHIVE_DIRNAME,
            )

        if source_kind == ARCHIVE_SOURCE_SANDBOX:
            if sandbox_mods_path is None:
                raise AppShellError("Sandbox Mods directory is required for sandbox archive operations.")
            archive_text = sandbox_archive_path_text
            if (
                not archive_text.strip()
                and existing_config is not None
                and existing_config.sandbox_archive_path is not None
            ):
                archive_text = str(existing_config.sandbox_archive_path)
            return self._parse_and_validate_archive_path(
                archive_path_text=archive_text,
                destination_mods_path=sandbox_mods_path,
                field_label="Sandbox archive path",
                default_archive_dir_name=_DEFAULT_SANDBOX_ARCHIVE_DIRNAME,
            )

        raise AppShellError(f"Unknown archive source: {source_kind}")

    def _resolve_archived_entry(
        self,
        *,
        source_kind: ArchiveSourceKind,
        archived_path_text: str,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        existing_config: AppConfig | None,
    ) -> ArchivedModEntry:
        raw_archived_path = archived_path_text.strip()
        if not raw_archived_path:
            raise AppShellError("Archived entry path is required.")
        archived_path = Path(raw_archived_path).expanduser()

        real_mods_path = self._resolve_optional_real_mods_path(
            configured_mods_path_text=configured_mods_path_text,
            existing_config=existing_config,
        )
        sandbox_mods_path = self._resolve_optional_sandbox_mods_path(
            sandbox_mods_path_text=sandbox_mods_path_text,
            existing_config=existing_config,
        )
        archive_root = self._resolve_archive_path_for_source(
            source_kind=source_kind,
            real_mods_path=real_mods_path,
            sandbox_mods_path=sandbox_mods_path,
            real_archive_path_text=real_archive_path_text,
            sandbox_archive_path_text=sandbox_archive_path_text,
            existing_config=existing_config,
        )
        entries = list_archived_mod_entries(
            archive_root=archive_root,
            source_kind=source_kind,
        )
        for entry in entries:
            if _paths_deterministically_match(entry.archived_path, archived_path):
                return entry

        raise AppShellError(
            f"Selected archived entry is not available in {source_kind}: {archived_path}"
        )

    def _resolve_install_destination_paths(
        self,
        *,
        install_target: InstallTargetKind,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
    ) -> tuple[Path, Path]:
        if install_target == INSTALL_TARGET_CONFIGURED_REAL_MODS:
            real_mods_path = self._parse_and_validate_mods_path(configured_mods_path_text)
            real_archive_path = self._parse_and_validate_archive_path(
                archive_path_text=real_archive_path_text,
                destination_mods_path=real_mods_path,
                field_label="Real Mods archive path",
                default_archive_dir_name=_DEFAULT_REAL_ARCHIVE_DIRNAME,
            )
            return real_mods_path, real_archive_path

        if install_target == INSTALL_TARGET_SANDBOX_MODS:
            sandbox_mods_path = self._parse_and_validate_sandbox_mods_path(sandbox_mods_path_text)
            sandbox_archive_path = self._parse_and_validate_archive_path(
                archive_path_text=sandbox_archive_path_text,
                destination_mods_path=sandbox_mods_path,
                field_label="Sandbox archive path",
                default_archive_dir_name=_DEFAULT_SANDBOX_ARCHIVE_DIRNAME,
            )
            return sandbox_mods_path, sandbox_archive_path

        raise AppShellError(f"Unknown install target: {install_target}")

    @staticmethod
    def _infer_restore_target_from_source(source_kind: ArchiveSourceKind) -> InstallTargetKind:
        if source_kind == ARCHIVE_SOURCE_REAL:
            return INSTALL_TARGET_CONFIGURED_REAL_MODS
        if source_kind == ARCHIVE_SOURCE_SANDBOX:
            return INSTALL_TARGET_SANDBOX_MODS
        raise AppShellError(
            f"Archive source '{source_kind}' has no reliable restore destination context."
        )

    @staticmethod
    def _resolve_game_path(game_path_text: str, existing_config: AppConfig | None) -> Path:
        raw_value = game_path_text.strip()
        if raw_value:
            return AppShellService._parse_and_validate_game_path(raw_value)
        if existing_config is not None:
            return AppShellService._parse_and_validate_existing_directory(
                existing_config.game_path,
                "Saved game path is not accessible",
            )
        raise AppShellError("Game directory is required")

    @staticmethod
    def _resolve_mods_path(mods_dir_text: str, game_path: Path) -> Path:
        raw_mods_text = mods_dir_text.strip()
        if raw_mods_text:
            return AppShellService._parse_and_validate_mods_path(raw_mods_text)

        derived_mods_path = derive_mods_path(game_path)
        if derived_mods_path.exists() and derived_mods_path.is_dir():
            return derived_mods_path
        raise AppShellError(
            f"Mods directory is required and could not be derived from game path: {derived_mods_path}"
        )

    @staticmethod
    def default_archive_path_for_destination(
        *,
        destination_mods_path: Path,
        default_archive_dir_name: str,
    ) -> Path:
        return destination_mods_path.parent / default_archive_dir_name

    @staticmethod
    def _resolve_scan_excluded_paths(
        *,
        scan_target: ScanTargetKind,
        scan_path: Path,
        configured_archive_text: str,
        configured_archive_fallback: Path | None,
    ) -> tuple[Path, ...]:
        candidates: list[Path] = []

        raw_archive = configured_archive_text.strip()
        if raw_archive:
            candidates.append(Path(raw_archive).expanduser())
        elif configured_archive_fallback is not None:
            candidates.append(configured_archive_fallback)
        else:
            default_archive_name = (
                _DEFAULT_REAL_ARCHIVE_DIRNAME
                if scan_target == SCAN_TARGET_CONFIGURED_REAL_MODS
                else _DEFAULT_SANDBOX_ARCHIVE_DIRNAME
            )
            candidates.append(
                AppShellService.default_archive_path_for_destination(
                    destination_mods_path=scan_path,
                    default_archive_dir_name=default_archive_name,
                )
            )

        # Legacy compatibility: previous versions defaulted archives inside Mods root.
        candidates.append(scan_path / _LEGACY_ARCHIVE_DIRNAME)

        deduped: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            key = str(path.expanduser().resolve(strict=False))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(path)

        return tuple(deduped)

    @staticmethod
    def _archive_source_for_scan_target(scan_target: ScanTargetKind) -> ArchiveSourceKind:
        if scan_target == SCAN_TARGET_CONFIGURED_REAL_MODS:
            return ARCHIVE_SOURCE_REAL
        if scan_target == SCAN_TARGET_SANDBOX_MODS:
            return ARCHIVE_SOURCE_SANDBOX
        raise AppShellError(f"Unknown scan target: {scan_target}")

    @staticmethod
    def _parse_and_validate_selected_mod_path(
        *,
        mods_path: Path,
        mod_folder_path_text: str,
    ) -> Path:
        raw_target = mod_folder_path_text.strip()
        if not raw_target:
            raise AppShellError("Select an installed mod row first.")

        target_mod_path = Path(raw_target).expanduser()
        if not target_mod_path.exists() or not target_mod_path.is_dir():
            raise AppShellError(f"Selected mod folder is not accessible: {target_mod_path}")

        mods_root_resolved = mods_path.resolve()
        target_resolved = target_mod_path.resolve()
        if target_resolved.parent != mods_root_resolved:
            raise AppShellError(
                "Selected mod folder must be a direct child of the selected Mods destination."
            )
        return target_mod_path

    @staticmethod
    def _parse_and_validate_game_path(game_path_text: str) -> Path:
        game_path = AppShellService._parse_game_path_text(game_path_text)
        if not game_path.exists():
            raise AppShellError(f"Game directory does not exist: {game_path}")
        if not game_path.is_dir():
            raise AppShellError(f"Game path is not a directory: {game_path}")

        return game_path

    @staticmethod
    def _parse_game_path_text(game_path_text: str) -> Path:
        raw_value = game_path_text.strip()
        if not raw_value:
            raise AppShellError("Game directory is required")

        game_path = Path(raw_value).expanduser()
        return game_path

    @staticmethod
    def _parse_and_validate_mods_path(mods_dir_text: str) -> Path:
        raw_value = mods_dir_text.strip()
        if not raw_value:
            raise AppShellError("Mods directory is required")

        mods_path = Path(raw_value).expanduser()
        if not mods_path.exists():
            raise AppShellError(f"Mods directory does not exist: {mods_path}")
        if not mods_path.is_dir():
            raise AppShellError(f"Mods path is not a directory: {mods_path}")

        return mods_path

    @staticmethod
    def _parse_and_validate_existing_directory(path: Path, message_prefix: str) -> Path:
        if not path.exists() or not path.is_dir():
            raise AppShellError(f"{message_prefix}: {path}")
        return path

    @staticmethod
    def _parse_and_validate_zip_path(package_path_text: str) -> Path:
        raw_value = package_path_text.strip()
        if not raw_value:
            raise AppShellError("Zip package path is required")

        package_path = Path(raw_value).expanduser()
        if not package_path.exists():
            raise AppShellError(f"Zip package does not exist: {package_path}")
        if not package_path.is_file():
            raise AppShellError(f"Zip package path is not a file: {package_path}")
        if package_path.suffix.lower() != ".zip":
            raise AppShellError(f"File is not a .zip package: {package_path}")

        return package_path

    @staticmethod
    def _parse_and_validate_sandbox_mods_path(sandbox_mods_path_text: str) -> Path:
        raw_value = sandbox_mods_path_text.strip()
        if not raw_value:
            raise AppShellError("Sandbox Mods directory is required")

        sandbox_mods_path = Path(raw_value).expanduser()
        if not sandbox_mods_path.exists():
            raise AppShellError(f"Sandbox Mods directory does not exist: {sandbox_mods_path}")
        if not sandbox_mods_path.is_dir():
            raise AppShellError(
                f"Sandbox Mods directory path is not a directory: {sandbox_mods_path}"
            )

        return sandbox_mods_path

    @staticmethod
    def _parse_and_validate_sandbox_archive_path(
        sandbox_archive_path_text: str,
        sandbox_mods_path: Path,
    ) -> Path:
        return AppShellService._parse_and_validate_archive_path(
            archive_path_text=sandbox_archive_path_text,
            destination_mods_path=sandbox_mods_path,
            field_label="Sandbox archive path",
            default_archive_dir_name=_DEFAULT_SANDBOX_ARCHIVE_DIRNAME,
        )

    @staticmethod
    def _parse_and_validate_archive_path(
        *,
        archive_path_text: str,
        destination_mods_path: Path,
        field_label: str,
        default_archive_dir_name: str,
    ) -> Path:
        raw_value = archive_path_text.strip()
        archive_path = (
            AppShellService.default_archive_path_for_destination(
                destination_mods_path=destination_mods_path,
                default_archive_dir_name=default_archive_dir_name,
            )
            if not raw_value
            else Path(raw_value).expanduser()
        )

        if archive_path.exists() and not archive_path.is_dir():
            raise AppShellError(f"{field_label} is not a directory: {archive_path}")

        if _is_path_within_or_equal(archive_path, destination_mods_path):
            raise AppShellError(
                f"{field_label} must be outside the active Mods directory: {archive_path}"
            )

        parent = archive_path.parent
        if not parent.exists() or not parent.is_dir():
            raise AppShellError(
                f"{field_label} parent directory is not accessible: {parent}"
            )

        return archive_path

    @staticmethod
    def _parse_and_validate_watched_downloads_path(
        *,
        watched_downloads_path_text: str,
        secondary_watched_downloads_path_text: str = "",
    ) -> tuple[Path, ...]:
        watched_paths = []
        for raw_text in (
            watched_downloads_path_text.strip(),
            secondary_watched_downloads_path_text.strip(),
        ):
            if not raw_text:
                continue

            watched_path = Path(raw_text).expanduser()
            if not watched_path.exists():
                raise AppShellError(f"Watched downloads directory does not exist: {watched_path}")
            if not watched_path.is_dir():
                raise AppShellError(
                    f"Watched downloads path is not a directory: {watched_path}"
                )
            watched_paths.append(watched_path)

        if not watched_paths:
            raise AppShellError("At least one watched downloads directory is required")

        distinct_paths: list[Path] = []
        seen_paths: set[Path] = set()
        for watched_path in watched_paths:
            if watched_path in seen_paths:
                continue
            seen_paths.add(watched_path)
            distinct_paths.append(watched_path)
        return tuple(distinct_paths)

    @staticmethod
    def _format_watched_download_paths_for_guidance(
        *,
        watched_downloads_path_text: str,
        secondary_watched_downloads_path_text: str = "",
    ) -> str:
        watched_paths = []
        for raw_text in (
            watched_downloads_path_text.strip(),
            secondary_watched_downloads_path_text.strip(),
        ):
            if raw_text and raw_text not in watched_paths:
                watched_paths.append(raw_text)

        if not watched_paths:
            return "<set a watched downloads path first>"
        if len(watched_paths) == 1:
            return f"watched downloads path: {watched_paths[0]}"
        return "one watched downloads path:\n   - " + "\n   - ".join(watched_paths)

    @staticmethod
    def _parse_optional_directory(path_text: str) -> Path | None:
        raw_value = path_text.strip()
        if not raw_value:
            return None

        path = Path(raw_value).expanduser()
        if not path.exists():
            raise AppShellError(f"Directory does not exist: {path}")
        if not path.is_dir():
            raise AppShellError(f"Path is not a directory: {path}")

        return path

    @staticmethod
    def _parse_optional_archive_directory(path_text: str) -> Path | None:
        raw_value = path_text.strip()
        if not raw_value:
            return None

        path = Path(raw_value).expanduser()
        if path.exists() and not path.is_dir():
            raise AppShellError(f"Real archive path is not a directory: {path}")
        if not path.parent.exists() or not path.parent.is_dir():
            raise AppShellError(
                f"Real archive parent directory is not accessible: {path.parent}"
            )
        return path

    @property
    def _install_operation_history_file(self) -> Path:
        return install_operation_history_file(self._state_file)

    @property
    def _recovery_execution_history_file(self) -> Path:
        return recovery_execution_history_file(self._state_file)

    @property
    def _update_source_intent_overlay_file(self) -> Path:
        return update_source_intent_overlay_file(self._state_file)

    def _record_completed_install_operation(
        self,
        *,
        plan: SandboxInstallPlan,
        result: SandboxInstallResult,
    ) -> None:
        self._record_install_operation_state(
            plan=plan,
            installed_targets=result.installed_targets,
            archived_targets=result.archived_targets,
        )

    def _record_install_operation_state(
        self,
        *,
        plan: SandboxInstallPlan,
        installed_targets: tuple[Path, ...],
        archived_targets: tuple[Path, ...],
    ) -> None:
        operation = InstallOperationRecord(
            operation_id=_new_operation_id("install"),
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            package_path=plan.package_path,
            destination_kind=plan.destination_kind,
            destination_mods_path=plan.sandbox_mods_path,
            archive_path=plan.sandbox_archive_path,
            installed_targets=installed_targets,
            archived_targets=archived_targets,
            entries=tuple(
                InstallOperationEntryRecord(
                    name=entry.name,
                    unique_id=entry.unique_id,
                    version=entry.version,
                    action=entry.action,
                    target_path=entry.target_path,
                    archive_path=entry.archive_path,
                    source_manifest_path=entry.source_manifest_path,
                    source_root_path=entry.source_root_path,
                    target_exists_before=entry.target_exists,
                    can_install=entry.can_install,
                    warnings=entry.warnings,
                )
                for entry in plan.entries
            ),
        )
        try:
            append_install_operation_record(self._install_operation_history_file, operation)
        except (AppStateStoreError, OSError) as exc:
            raise AppShellError(
                "Install completed, but recording install history failed: "
                f"{exc}. Recovery inspection depends on recorded install history."
            ) from exc

    def _record_recovery_execution_attempt(
        self,
        *,
        review: InstallRecoveryExecutionReview,
        outcome_status: str,
        removed_target_paths: tuple[Path, ...],
        restored_target_paths: tuple[Path, ...],
        failure_message: str | None,
        critical: bool,
    ) -> None:
        record = RecoveryExecutionRecord(
            recovery_execution_id=_new_operation_id("recovery"),
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            related_install_operation_id=review.plan.operation.operation_id,
            related_install_operation_timestamp=review.plan.operation.timestamp,
            related_install_package_path=review.plan.operation.package_path,
            destination_kind=review.plan.operation.destination_kind,
            destination_mods_path=review.plan.operation.destination_mods_path,
            executed_entry_count=len(removed_target_paths) + len(restored_target_paths),
            removed_target_paths=removed_target_paths,
            restored_target_paths=restored_target_paths,
            outcome_status=outcome_status,
            failure_message=failure_message,
        )
        try:
            append_recovery_execution_record(self._recovery_execution_history_file, record)
        except (AppStateStoreError, OSError) as exc:
            if not critical:
                # Blocked/no-op recovery paths have not changed files, so the primary
                # review outcome remains the important signal and audit recording can
                # remain best-effort here.
                return

            if outcome_status == "completed":
                raise AppShellError(
                    "Recovery completed, but recording recovery history failed: "
                    f"{exc}. Recovery audit history is required for reversible workflow trust."
                ) from exc

            raise AppShellError(
                "Recovery failed after filesystem changes, and recording recovery history also failed: "
                f"{exc}. Original recovery error: {failure_message or 'unknown'}"
            ) from exc


def _paths_deterministically_match(path_a: Path, path_b: Path) -> bool:
    left = path_a.expanduser()
    right = path_b.expanduser()

    try:
        if left.exists() and right.exists() and left.samefile(right):
            return True
    except OSError:
        pass

    left_resolved = left.resolve(strict=False)
    right_resolved = right.resolve(strict=False)
    if left_resolved == right_resolved:
        return True

    left_text = str(left_resolved)
    right_text = str(right_resolved)
    if os.name == "nt":
        return left_text.casefold() == right_text.casefold()

    return left_text == right_text


def _is_path_within_or_equal(candidate: Path, container: Path) -> bool:
    candidate_resolved = candidate.expanduser().resolve(strict=False)
    container_resolved = container.expanduser().resolve(strict=False)

    if candidate_resolved == container_resolved:
        return True

    try:
        return candidate_resolved.is_relative_to(container_resolved)
    except ValueError:
        return False


def _promotion_history_source_marker(
    *,
    sandbox_mods_path: Path,
    source_paths: tuple[Path, ...],
) -> Path:
    if len(source_paths) == 1:
        return source_paths[0]
    return sandbox_mods_path / ".sdvmm-sandbox-promotion-selection"


def _sorted_unique_ids(values: Iterable[str]) -> tuple[str, ...]:
    unique = {str(value) for value in values if str(value).strip()}
    return tuple(sorted(unique, key=str.casefold))


def _require_canonical_unique_id(unique_id: str) -> str:
    normalized = canonicalize_unique_id(unique_id)
    if not normalized:
        raise AppShellError("UniqueID is required.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _upsert_update_source_intent_record(
    records: tuple[UpdateSourceIntentRecord, ...],
    record: UpdateSourceIntentRecord,
) -> tuple[UpdateSourceIntentRecord, ...]:
    remaining = [
        existing
        for existing in records
        if existing.normalized_unique_id != record.normalized_unique_id
    ]
    remaining.append(record)
    remaining.sort(key=lambda item: item.normalized_unique_id)
    return tuple(remaining)


def _version_sort_key(version: str | None) -> tuple[int, ...]:
    if not version:
        return tuple()
    numbers: list[int] = []
    for token in version.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if not digits:
            numbers.append(0)
            continue
        numbers.append(int(digits))
    return tuple(numbers)


def _discovery_entry_unique_id_keys(entry: ModDiscoveryEntry) -> tuple[str, ...]:
    candidates = [entry.unique_id, *entry.alternate_unique_ids]
    keys: dict[str, str] = {}
    for candidate in candidates:
        normalized = str(candidate).strip()
        if not normalized:
            continue
        key = canonicalize_unique_id(normalized)
        keys.setdefault(key, normalized)
    return tuple(keys.keys())


def _first_present(values_by_key: dict[str, object], keys: tuple[str, ...]) -> object | None:
    for key in keys:
        if key in values_by_key:
            return values_by_key[key]
    return None


def _build_discovery_provider_relation(
    *,
    discovery_source_provider: str,
    tracked_provider: str | None,
) -> tuple[str, str | None]:
    if tracked_provider is None:
        return ("no_update_provider_context", None)

    if discovery_source_provider not in {"nexus", "github"}:
        return (
            "provider_not_comparable",
            "Tracked update provider exists, but discovery source is custom/other.",
        )

    if discovery_source_provider == tracked_provider:
        return (
            "provider_aligned",
            f"Discovery source matches tracked update provider ({_provider_label(tracked_provider)}).",
        )

    return (
        "provider_mismatch",
        "Discovery source differs from tracked update provider "
        f"({_provider_label(discovery_source_provider)} vs {_provider_label(tracked_provider)}).",
    )


def _build_discovery_context_messages(
    *,
    installed_match_unique_id: str | None,
    update_state: str | None,
) -> tuple[str, str]:
    if installed_match_unique_id is None:
        return (
            "Not currently installed in the scanned inventory",
            (
                "Open source page, download manually, let watcher detect the zip, "
                "then plan a safe install."
            ),
        )

    if update_state == "update_available":
        return (
            f"Already installed ({installed_match_unique_id}); update is available in current metadata report",
            (
                "Open source page, download manually, let watcher detect the zip, "
                "then plan a safe update/replace."
            ),
        )

    if update_state == "up_to_date":
        return (
            f"Already installed ({installed_match_unique_id}); currently marked up to date",
            (
                "Open source page only if you intentionally want a manual reinstall or alternate build. "
                "If downloaded, continue via watcher -> intake -> plan."
            ),
        )

    if update_state == "metadata_unavailable":
        return (
            f"Already installed ({installed_match_unique_id}); update metadata currently unavailable",
            (
                "Open source page and continue manual flow if needed. You can also run Check updates again "
                "after fixing metadata/provider issues."
            ),
        )

    if update_state == "no_remote_link":
        return (
            f"Already installed ({installed_match_unique_id}); no tracked remote link in update report",
            (
                "Use discovery source page as manual source. Download manually, then continue via watcher "
                "-> intake -> plan."
            ),
        )

    return (
        f"Already installed ({installed_match_unique_id}); update state not checked yet",
        "Run Check updates for richer context, or continue manual watcher -> intake -> plan flow.",
    )


def _provider_label(provider: str) -> str:
    labels = {
        "nexus": "Nexus",
        "github": "GitHub",
        "json": "JSON",
        "custom_url": "Custom URL",
    }
    return labels.get(provider, provider)


def _collect_install_execution_review_warnings(
    plan: SandboxInstallPlan,
) -> tuple[str, ...]:
    warnings: list[str] = []

    for warning in plan.plan_warnings:
        text = warning.strip()
        if text:
            warnings.append(text)

    for warning in plan.package_warnings:
        text = warning.message.strip()
        if text:
            warnings.append(text)

    for entry in plan.entries:
        for warning in entry.warnings:
            text = warning.strip()
            if text:
                warnings.append(f"{entry.name}: {text}")

    deduped: list[str] = []
    seen: set[str] = set()
    for warning in warnings:
        if warning in seen:
            continue
        seen.add(warning)
        deduped.append(warning)
    return tuple(deduped)


def _build_sandbox_install_review_message(summary: InstallExecutionSummary) -> str:
    message = (
        f"Sandbox install can proceed for {summary.total_entry_count} "
        f"{_entry_count_label(summary.total_entry_count)}."
    )
    if summary.has_existing_targets_to_replace or summary.has_archive_writes:
        message += " Review archive/replace actions before execution."
    else:
        message += " No explicit approval is required."
    return message


def _build_real_install_review_message(summary: InstallExecutionSummary) -> str:
    message = (
        f"Real Mods install targets {summary.total_entry_count} "
        f"{_entry_count_label(summary.total_entry_count)} in {summary.destination_mods_path}. "
        "Explicit approval is required before execution."
    )
    if summary.has_existing_targets_to_replace or summary.has_archive_writes:
        message += " Review archive/replace actions carefully."
    return message


def _entry_count_label(count: int) -> str:
    return "entry" if count == 1 else "entries"


def _normalize_sandbox_promotion_error(
    exc: AppShellError | SandboxInstallError | OSError,
) -> AppShellError:
    if isinstance(exc, AppShellError):
        return exc
    if isinstance(exc, SandboxInstallError):
        return AppShellError(f"Sandbox promotion failed: {exc}")
    return AppShellError(f"Sandbox promotion failed: {exc}")


def _remove_path_for_promotion_rollback(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
        return
    path.unlink()


def _derive_install_operation_recovery_entry(
    operation: InstallOperationRecord,
    entry: InstallOperationEntryRecord,
) -> InstallRecoveryPlanEntry:
    if entry.action == INSTALL_NEW:
        if _operation_record_contains_path(operation.installed_targets, entry.target_path):
            return InstallRecoveryPlanEntry(
                name=entry.name,
                unique_id=entry.unique_id,
                version=entry.version,
                action="remove_installed_target",
                target_path=entry.target_path,
                archive_path=entry.archive_path,
                recoverable=True,
                message=f"Remove installed target recorded for {entry.name}.",
                warnings=entry.warnings,
            )
        return InstallRecoveryPlanEntry(
            name=entry.name,
            unique_id=entry.unique_id,
            version=entry.version,
            action="not_recoverable",
            target_path=entry.target_path,
            archive_path=entry.archive_path,
            recoverable=False,
            message=(
                f"{entry.name} is not safely recoverable: the install history does not "
                "record the installed target for removal."
            ),
            warnings=entry.warnings,
        )

    if entry.action == OVERWRITE_WITH_ARCHIVE:
        if entry.archive_path is None:
            return InstallRecoveryPlanEntry(
                name=entry.name,
                unique_id=entry.unique_id,
                version=entry.version,
                action="not_recoverable",
                target_path=entry.target_path,
                archive_path=entry.archive_path,
                recoverable=False,
                message=(
                    f"{entry.name} is not safely recoverable: no archived target was recorded "
                    "for restoration."
                ),
                warnings=entry.warnings,
            )
        if not _operation_record_contains_path(operation.archived_targets, entry.archive_path):
            return InstallRecoveryPlanEntry(
                name=entry.name,
                unique_id=entry.unique_id,
                version=entry.version,
                action="not_recoverable",
                target_path=entry.target_path,
                archive_path=entry.archive_path,
                recoverable=False,
                message=(
                    f"{entry.name} is not safely recoverable: the recorded archive target "
                    "cannot be matched for restoration."
                ),
                warnings=entry.warnings,
            )
        return InstallRecoveryPlanEntry(
            name=entry.name,
            unique_id=entry.unique_id,
            version=entry.version,
            action="restore_from_archive",
            target_path=entry.target_path,
            archive_path=entry.archive_path,
            recoverable=True,
            message=f"Restore archived target recorded for {entry.name}.",
            warnings=entry.warnings,
        )

    return InstallRecoveryPlanEntry(
        name=entry.name,
        unique_id=entry.unique_id,
        version=entry.version,
        action="not_recoverable",
        target_path=entry.target_path,
        archive_path=entry.archive_path,
        recoverable=False,
        message=(
            f"{entry.name} is not safely recoverable: recorded action "
            f"{entry.action!r} is not supported for recovery."
        ),
        warnings=entry.warnings,
    )


def _operation_record_contains_path(paths: tuple[Path, ...], expected: Path) -> bool:
    return any(_paths_deterministically_match(path, expected) for path in paths)


def _review_install_recovery_entry(
    entry: InstallRecoveryPlanEntry,
) -> InstallRecoveryExecutionReviewEntry:
    if entry.action == "remove_installed_target":
        if entry.target_path.exists():
            return InstallRecoveryExecutionReviewEntry(
                plan_entry=entry,
                executable=True,
                decision_code="removal_ready",
                message=f"Removal target exists for {entry.name}.",
            )
        return InstallRecoveryExecutionReviewEntry(
            plan_entry=entry,
            executable=False,
            decision_code="removal_target_missing",
            message=f"Removal target is missing for {entry.name}.",
        )

    if entry.action == "restore_from_archive":
        if entry.archive_path is not None and entry.archive_path.exists():
            return InstallRecoveryExecutionReviewEntry(
                plan_entry=entry,
                executable=True,
                decision_code="restore_ready",
                message=f"Archive source exists for restoring {entry.name}.",
            )
        return InstallRecoveryExecutionReviewEntry(
            plan_entry=entry,
            executable=False,
            decision_code="restore_archive_missing",
            message=f"Archive source is missing for restoring {entry.name}.",
        )

    return InstallRecoveryExecutionReviewEntry(
        plan_entry=entry,
        executable=False,
        decision_code="entry_not_recoverable",
        message=entry.message,
    )


def _remove_recovery_target(target_path: Path) -> None:
    if target_path.is_dir():
        shutil.rmtree(target_path)
        return
    target_path.unlink()


def _new_operation_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _build_intake_flow_messages(
    *,
    intake: DownloadsIntakeResult,
    actionable: bool,
    matched_update_available: tuple[str, ...],
    matched_guided: tuple[str, ...],
) -> tuple[str, str]:
    if not actionable:
        return (
            "Detected package is unusable for install planning.",
            "Fix or replace this package before planning (non-actionable).",
        )

    if matched_guided:
        joined = ", ".join(matched_guided)
        return (
            f"Detected package likely matches guided update target(s): {joined}.",
            "Select this package and click 'Plan selected intake', then review plan warnings.",
        )

    if matched_update_available:
        joined = ", ".join(matched_update_available)
        return (
            f"Detected package likely matches mod(s) with update available: {joined}.",
            "Select this package and click 'Plan selected intake'.",
        )

    if intake.classification == "update_replace_candidate":
        return (
            "Detected package matches an installed mod by UniqueID.",
            "Select package and plan update after reviewing overwrite/archive actions.",
        )

    if intake.classification == "multi_mod_package":
        return (
            "Detected package contains multiple mods.",
            "Select package and review all sandbox plan entries before execution.",
        )

    return (
        "Detected package appears to be a new install candidate.",
        "Select package and plan install.",
    )


def _evaluate_sandbox_plan_dependencies(
    *,
    plan: SandboxInstallPlan,
    base_findings: tuple[DependencyPreflightFinding, ...],
    installed_inventory: ModsInventory,
) -> tuple[DependencyPreflightFinding, ...]:
    if not base_findings:
        return tuple()

    available_dependency_keys = {
        canonicalize_unique_id(mod.unique_id) for mod in installed_inventory.mods
    }
    available_dependency_keys.update(
        canonicalize_unique_id(entry.unique_id) for entry in plan.entries
    )

    findings: list[DependencyPreflightFinding] = []
    for finding in base_findings:
        dependency_key = canonicalize_unique_id(finding.dependency_unique_id)
        if dependency_key in available_dependency_keys:
            state = SATISFIED
        elif finding.required:
            state = MISSING_REQUIRED_DEPENDENCY
        else:
            state = OPTIONAL_DEPENDENCY_MISSING

        findings.append(
            replace(
                finding,
                source="sandbox_plan",
                state=state,
            )
        )

    findings.sort(
        key=lambda item: (
            item.source,
            item.state,
            canonicalize_unique_id(item.required_by_unique_id),
            canonicalize_unique_id(item.dependency_unique_id),
        )
    )
    return tuple(findings)


def _apply_dependency_preflight_to_plan(
    plan: SandboxInstallPlan,
    dependency_findings: tuple[DependencyPreflightFinding, ...],
) -> SandboxInstallPlan:
    if not dependency_findings:
        return replace(plan, dependency_findings=tuple())

    required_missing_by_mod: dict[str, list[str]] = {}
    optional_missing_by_mod: dict[str, list[str]] = {}
    unresolved_by_mod: dict[str, list[str]] = {}

    for finding in dependency_findings:
        mod_key = canonicalize_unique_id(finding.required_by_unique_id)
        if finding.state == MISSING_REQUIRED_DEPENDENCY:
            required_missing_by_mod.setdefault(mod_key, []).append(finding.dependency_unique_id)
            continue
        if finding.state == OPTIONAL_DEPENDENCY_MISSING:
            optional_missing_by_mod.setdefault(mod_key, []).append(finding.dependency_unique_id)
            continue
        if finding.state == UNRESOLVED_DEPENDENCY_CONTEXT:
            unresolved_by_mod.setdefault(mod_key, []).append(finding.dependency_unique_id)

    updated_entries = []
    for entry in plan.entries:
        entry_warnings = list(entry.warnings)
        mod_key = canonicalize_unique_id(entry.unique_id)
        blocked = False

        missing_required_ids = sorted(set(required_missing_by_mod.get(mod_key, [])), key=str.casefold)
        if missing_required_ids:
            blocked = True
            deps_text = ", ".join(missing_required_ids)
            entry_warnings.append(
                f"Missing required dependencies: {deps_text}. Install dependencies first."
            )

        optional_missing_ids = sorted(set(optional_missing_by_mod.get(mod_key, [])), key=str.casefold)
        if optional_missing_ids:
            deps_text = ", ".join(optional_missing_ids)
            entry_warnings.append(
                f"Optional dependencies missing: {deps_text}. Mod may still load with reduced features."
            )

        unresolved_ids = sorted(set(unresolved_by_mod.get(mod_key, [])), key=str.casefold)
        if unresolved_ids:
            deps_text = ", ".join(unresolved_ids)
            entry_warnings.append(
                f"Dependency context unresolved: {deps_text}. Verify dependencies manually before install."
            )

        updated_entries.append(
            replace(
                entry,
                action=("blocked" if blocked else entry.action),
                can_install=(False if blocked else entry.can_install),
                warnings=tuple(entry_warnings),
            )
        )

    plan_warnings = list(plan.plan_warnings)
    missing_messages = summarize_missing_required_dependencies(dependency_findings)
    if missing_messages:
        plan_warnings.append(
            f"Dependency preflight found {len(missing_messages)} missing required dependency relation(s)."
        )
        for message in missing_messages:
            plan_warnings.append(f"Dependency: {message}")

    optional_missing_count = sum(
        1 for finding in dependency_findings if finding.state == OPTIONAL_DEPENDENCY_MISSING
    )
    if optional_missing_count:
        plan_warnings.append(
            f"Dependency preflight found {optional_missing_count} optional missing dependency relation(s)."
        )

    unresolved_count = sum(
        1 for finding in dependency_findings if finding.state == UNRESOLVED_DEPENDENCY_CONTEXT
    )
    if unresolved_count:
        plan_warnings.append(
            f"Dependency preflight found {unresolved_count} unresolved dependency relation(s)."
        )

    return replace(
        plan,
        entries=tuple(updated_entries),
        plan_warnings=tuple(plan_warnings),
        dependency_findings=dependency_findings,
    )


def _inspect_package_mod_entries(package_path: Path) -> tuple[PackageModEntry, ...]:
    inspection = inspect_zip_package(package_path)
    return inspection.mods
