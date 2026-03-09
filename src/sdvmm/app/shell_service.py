from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
from collections.abc import Iterable
from typing import Literal
import zipfile

from sdvmm.domain.models import (
    AppConfig,
    DependencyPreflightFinding,
    DownloadsIntakeResult,
    DownloadsWatchPollResult,
    GameEnvironmentStatus,
    ModUpdateReport,
    ModsInventory,
    NexusIntegrationStatus,
    PackageInspectionResult,
    PackageModEntry,
    SandboxInstallPlan,
    SandboxInstallResult,
)
from sdvmm.domain.nexus_codes import (
    NEXUS_CONFIGURED,
    NEXUS_NOT_CONFIGURED,
)
from sdvmm.domain.dependency_codes import (
    MISSING_REQUIRED_DEPENDENCY,
    OPTIONAL_DEPENDENCY_MISSING,
    SATISFIED,
    UNRESOLVED_DEPENDENCY_CONTEXT,
)
from sdvmm.domain.unique_id import canonicalize_unique_id
from sdvmm.services.app_state_store import (
    AppStateStoreError,
    load_app_config,
    save_app_config,
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
    SandboxInstallError,
    build_sandbox_install_plan as build_sandbox_install_plan_service,
    execute_sandbox_install_plan as execute_sandbox_install_plan_service,
)
from sdvmm.services.update_metadata import (
    NEXUS_API_KEY_ENV,
    check_nexus_connection,
    check_updates_for_inventory,
    mask_api_key,
    normalize_nexus_api_key,
)
from sdvmm.services.remote_requirements import evaluate_remote_requirements_for_package_mods


class AppShellError(ValueError):
    """Recoverable UI-facing error for config and scan actions."""


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


@dataclass(frozen=True, slots=True)
class ScanResult:
    target_kind: ScanTargetKind
    scan_path: Path
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
        real_archive_path = self._parse_optional_archive_directory(real_archive_path_text)
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

    def scan(self, mods_dir_text: str) -> ModsInventory:
        mods_path = self._parse_and_validate_mods_path(mods_dir_text)

        try:
            return scan_mods_directory(mods_path)
        except OSError as exc:
            raise AppShellError(f"Could not scan Mods directory: {exc}") from exc

    def scan_with_target(
        self,
        *,
        scan_target: ScanTargetKind,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
    ) -> ScanResult:
        if scan_target == SCAN_TARGET_CONFIGURED_REAL_MODS:
            scan_path = self._parse_and_validate_mods_path(configured_mods_path_text)
        elif scan_target == SCAN_TARGET_SANDBOX_MODS:
            scan_path = self._parse_and_validate_sandbox_mods_path(sandbox_mods_path_text)
        else:
            raise AppShellError(f"Unknown scan target: {scan_target}")

        try:
            inventory = scan_mods_directory(scan_path)
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
        try:
            return check_updates_for_inventory(
                inventory,
                nexus_api_key=nexus_api_key,
            )
        except OSError as exc:
            raise AppShellError(f"Could not check remote metadata: {exc}") from exc

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

    def initialize_downloads_watch(self, watched_downloads_path_text: str) -> tuple[Path, ...]:
        watched_path = self._parse_and_validate_watched_downloads_path(watched_downloads_path_text)

        try:
            return initialize_known_zip_paths(watched_path)
        except OSError as exc:
            raise AppShellError(f"Could not initialize watched downloads directory: {exc}") from exc

    def poll_downloads_watch(
        self,
        *,
        watched_downloads_path_text: str,
        known_zip_paths: tuple[Path, ...],
        inventory: ModsInventory,
        nexus_api_key_text: str = "",
        existing_config: AppConfig | None = None,
    ) -> DownloadsWatchPollResult:
        watched_path = self._parse_and_validate_watched_downloads_path(watched_downloads_path_text)
        nexus_api_key = self._resolve_nexus_api_key(
            nexus_api_key_text=nexus_api_key_text,
            existing_config=existing_config,
        )

        try:
            result = poll_watched_directory(
                watched_path=watched_path,
                known_zip_paths=known_zip_paths,
                inventory=inventory,
            )
            enriched_intakes = tuple(
                replace(
                    intake,
                    remote_requirements=evaluate_remote_requirements_for_package_mods(
                        intake.mods,
                        source="downloads_intake",
                        nexus_api_key=nexus_api_key,
                    ),
                )
                for intake in result.intakes
            )
            return replace(result, intakes=enriched_intakes)
        except OSError as exc:
            raise AppShellError(f"Could not poll watched downloads directory: {exc}") from exc

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
        watcher_running: bool,
    ) -> str:
        watched_path = watched_downloads_path_text.strip() or "<set watched downloads path first>"
        watch_step = (
            "Watcher is running; it will detect new zip files added now."
            if watcher_running
            else "Start watch before downloading, so new zip files are detected."
        )
        return (
            f"Manual update flow for {unique_id}:\n"
            "1. Open remote page and download manually.\n"
            f"2. Save the zip into watched downloads path: {watched_path}\n"
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
            inventory = scan_mods_directory(destination_mods_path)
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
        if (
            plan.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
            and not confirm_real_destination
        ):
            raise AppShellError(
                "Real Mods destination selected. Explicit confirmation is required before execution."
            )

        try:
            result = execute_sandbox_install_plan_service(plan)
            return replace(result, destination_kind=plan.destination_kind)
        except SandboxInstallError as exc:
            raise AppShellError(str(exc)) from exc
        except OSError as exc:
            raise AppShellError(f"Sandbox install failed: {exc}") from exc

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
            )
            return real_mods_path, real_archive_path

        if install_target == INSTALL_TARGET_SANDBOX_MODS:
            sandbox_mods_path = self._parse_and_validate_sandbox_mods_path(sandbox_mods_path_text)
            sandbox_archive_path = self._parse_and_validate_archive_path(
                archive_path_text=sandbox_archive_path_text,
                destination_mods_path=sandbox_mods_path,
                field_label="Sandbox archive path",
            )
            return sandbox_mods_path, sandbox_archive_path

        raise AppShellError(f"Unknown install target: {install_target}")

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
        )

    @staticmethod
    def _parse_and_validate_archive_path(
        *,
        archive_path_text: str,
        destination_mods_path: Path,
        field_label: str,
    ) -> Path:
        raw_value = archive_path_text.strip()
        archive_path = (
            (destination_mods_path / ".sdvmm-archive")
            if not raw_value
            else Path(raw_value).expanduser()
        )

        if archive_path.exists() and not archive_path.is_dir():
            raise AppShellError(f"{field_label} is not a directory: {archive_path}")

        parent = archive_path.parent
        if not parent.exists() or not parent.is_dir():
            raise AppShellError(
                f"{field_label} parent directory is not accessible: {parent}"
            )

        return archive_path

    @staticmethod
    def _parse_and_validate_watched_downloads_path(watched_downloads_path_text: str) -> Path:
        raw_value = watched_downloads_path_text.strip()
        if not raw_value:
            raise AppShellError("Watched downloads directory is required")

        watched_path = Path(raw_value).expanduser()
        if not watched_path.exists():
            raise AppShellError(f"Watched downloads directory does not exist: {watched_path}")
        if not watched_path.is_dir():
            raise AppShellError(
                f"Watched downloads path is not a directory: {watched_path}"
            )

        return watched_path

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


def _sorted_unique_ids(values: Iterable[str]) -> tuple[str, ...]:
    unique = {str(value) for value in values if str(value).strip()}
    return tuple(sorted(unique, key=str.casefold))


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
