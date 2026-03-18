from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from PySide6.QtCore import QTimer
from PySide6.QtCore import QThreadPool
from PySide6.QtCore import QUrl
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtGui import QFont
from PySide6.QtGui import QPalette

from sdvmm.app.inventory_presenter import (
    build_archive_listing_text,
    build_archive_delete_result_text,
    build_archive_restore_result_text,
    build_dependency_preflight_text,
    build_mod_rollback_plan_text,
    build_mod_rollback_result_text,
    build_discovery_search_text,
    build_downloads_intake_text,
    build_environment_status_text,
    build_findings_text,
    build_intake_correlation_text,
    build_mod_removal_result_text,
    build_package_inspection_text,
    build_sandbox_install_plan_text,
    build_sandbox_install_result_text,
    build_smapi_log_report_text,
    build_smapi_update_status_text,
    build_update_report_text,
)
from sdvmm.app.table_filters import row_matches_filter
from sdvmm.app.shell_service import (
    ARCHIVE_SOURCE_REAL,
    ARCHIVE_SOURCE_SANDBOX,
    BackupBundleExportResult,
    DiscoveryContextCorrelation,
    INSTALL_TARGET_CONFIGURED_REAL_MODS,
    INSTALL_TARGET_SANDBOX_MODS,
    SCAN_TARGET_CONFIGURED_REAL_MODS,
    SCAN_TARGET_SANDBOX_MODS,
    AppShellError,
    AppShellService,
    IntakeUpdateCorrelation,
    ScanResult,
    SandboxModsPromotionPreview,
    SandboxModsPromotionResult,
    SandboxModsSyncResult,
    build_backup_bundle_export_text,
    build_mods_compare_text,
)
from sdvmm.domain.models import (
    AppConfig,
    DownloadsIntakeResult,
    DownloadsWatchPollResult,
    GameEnvironmentStatus,
    InstallExecutionReview,
    InstallOperationRecord,
    InstallRecoveryExecutionResult,
    InstallRecoveryInspectionResult,
    ModDiscoveryResult,
    ModsCompareResult,
    ArchiveRestoreResult,
    ArchiveDeleteResult,
    ArchivedModEntry,
    ModRemovalResult,
    ModRollbackResult,
    RecoveryExecutionRecord,
    SmapiLogReport,
    ModUpdateStatus,
    ModUpdateReport,
    ModsInventory,
    PackageInspectionBatchEntry,
    PackageInspectionBatchResult,
    SmapiUpdateStatus,
    SandboxInstallPlan,
)
from sdvmm.domain.unique_id import canonicalize_unique_id
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
    SMAPI_LOG_RUNTIME_ISSUE,
    SMAPI_LOG_UNABLE_TO_DETERMINE,
    SMAPI_LOG_WARNING,
)
from sdvmm.domain.update_codes import (
    LOCAL_PRIVATE_MOD,
    METADATA_SOURCE_ISSUE,
    MISSING_UPDATE_KEY,
    NO_PROVIDER_MAPPING,
    REMOTE_METADATA_LOOKUP_FAILED,
    UNSUPPORTED_UPDATE_KEY_FORMAT,
)
from sdvmm.ui.background_task import BackgroundTask
from sdvmm.ui.archive_tab_surface import ArchiveTabSurface
from sdvmm.ui.bottom_details_region import BottomDetailsRegion
from sdvmm.ui.discovery_tab_surface import DiscoveryTabSurface
from sdvmm.ui.global_status_strip import GlobalStatusStrip
from sdvmm.ui.plan_install_tab_surface import PlanInstallTabSurface
from sdvmm.ui.setup_configuration_surface import SetupConfigurationSurface
from sdvmm.ui.top_context_surface import TopContextSurface

_ROLE_MOD_UPDATE_STATUS = int(Qt.ItemDataRole.UserRole) + 1
_ROLE_REMOTE_LINK = int(Qt.ItemDataRole.UserRole) + 2
_ROLE_DISCOVERY_INDEX = int(Qt.ItemDataRole.UserRole) + 3
_ROLE_DISCOVERY_LINK = int(Qt.ItemDataRole.UserRole) + 4
_ROLE_MOD_FOLDER_PATH = int(Qt.ItemDataRole.UserRole) + 5
_ROLE_ARCHIVE_INDEX = int(Qt.ItemDataRole.UserRole) + 6
_ROLE_UPDATE_ACTIONABLE = int(Qt.ItemDataRole.UserRole) + 7
_ROLE_UPDATE_BLOCK_REASON = int(Qt.ItemDataRole.UserRole) + 8

_NO_PLAN_REVIEW_SUMMARY_TEXT = "Plan review: no plan yet. Click Plan install to review."
_NO_PLAN_REVIEW_EXPLANATION_TEXT = "Plan detail: no plan selected."
_NO_PLAN_FACTS_TEXT = (
    "Entries: -\n"
    "Replace existing: -\n"
    "Archive writes: -\n"
    "Approval required: -\n"
    "Blocked entries: -"
)


class MainWindow(QMainWindow):
    def __init__(self, shell_service: AppShellService) -> None:
        super().__init__()
        self._shell_service = shell_service
        self._config: AppConfig | None = None
        self._pending_install_plan: SandboxInstallPlan | None = None
        self._current_inventory: ModsInventory | None = None
        self._current_update_report: ModUpdateReport | None = None
        self._current_mods_compare_result: ModsCompareResult | None = None
        self._current_discovery_result: ModDiscoveryResult | None = None
        self._discovery_correlations: tuple[DiscoveryContextCorrelation, ...] = tuple()
        self._known_watched_zip_paths: tuple[Path, ...] = tuple()
        self._detected_intakes: tuple[DownloadsIntakeResult, ...] = tuple()
        self._intake_correlations: tuple[IntakeUpdateCorrelation, ...] = tuple()
        self._selected_zip_package_paths: tuple[Path, ...] = tuple()
        self._package_inspection_batch_result: PackageInspectionBatchResult | None = None
        self._archived_entries: tuple[ArchivedModEntry, ...] = tuple()
        self._install_operation_history: tuple[InstallOperationRecord, ...] = tuple()
        self._install_operation_display_indexes: tuple[int, ...] = tuple()
        self._current_recovery_inspection: InstallRecoveryInspectionResult | None = None
        self._guided_update_unique_ids: tuple[str, ...] = tuple()
        self._last_environment_status: GameEnvironmentStatus | None = None
        self._last_smapi_log_report: SmapiLogReport | None = None
        self._last_smapi_update_status: SmapiUpdateStatus | None = None
        self._thread_pool = QThreadPool.globalInstance()
        self._active_operation_name: str | None = None
        self._active_background_task: BackgroundTask | None = None
        self._background_action_buttons: tuple[QPushButton, ...] = tuple()
        self._startup_checks_scheduled = False
        self._startup_checks_completed = False
        self._preserve_package_selection_on_zip_path_change = False
        self._preserve_package_inspection_on_zip_path_change = False
        self._auto_overwrite_package_path: str | None = None
        self._syncing_auto_overwrite_checkbox = False

        self.setWindowTitle("Stardew Mod Manager (Sandbox-first)")
        self.setMinimumSize(980, 640)
        self.resize(1360, 860)

        self._game_path_input = QLineEdit()
        self._game_path_input.setObjectName("setup_game_path_input")
        self._game_path_input.setPlaceholderText("/path/to/Stardew Valley")
        self._mods_path_input = QLineEdit()
        self._mods_path_input.setObjectName("setup_mods_path_input")
        self._mods_path_input.setPlaceholderText("/path/to/Stardew/Mods")
        self._zip_path_input = QLineEdit()
        self._zip_path_input.setPlaceholderText("/path/to/package.zip")
        self._sandbox_mods_path_input = QLineEdit()
        self._sandbox_mods_path_input.setObjectName("setup_sandbox_mods_input")
        self._sandbox_mods_path_input.setPlaceholderText("/path/to/Sandbox/Mods")
        self._sandbox_archive_path_input = QLineEdit()
        self._sandbox_archive_path_input.setObjectName("setup_sandbox_archive_input")
        self._sandbox_archive_path_input.setPlaceholderText("/path/to/.sdvmm-sandbox-archive")
        self._real_archive_path_input = QLineEdit()
        self._real_archive_path_input.setObjectName("setup_real_archive_input")
        self._real_archive_path_input.setPlaceholderText("/path/to/.sdvmm-real-archive")
        self._watched_downloads_path_input = QLineEdit()
        self._watched_downloads_path_input.setObjectName("setup_watched_downloads_input")
        self._watched_downloads_path_input.setPlaceholderText("/path/to/Downloads")
        self._secondary_watched_downloads_path_input = QLineEdit()
        self._secondary_watched_downloads_path_input.setObjectName(
            "setup_secondary_watched_downloads_input"
        )
        self._secondary_watched_downloads_path_input.setPlaceholderText("/path/to/BuiltZips")
        self._discovery_query_input = QLineEdit()
        self._discovery_query_input.setObjectName("discovery_query_input")
        self._discovery_query_input.setPlaceholderText(
            "Search by mod name, UniqueID, or author"
        )
        self._mods_filter_input = QLineEdit()
        self._mods_filter_input.setPlaceholderText("Filter installed mods")
        self._mods_filter_input.setClearButtonEnabled(True)
        self._mods_filter_input.setMinimumWidth(180)
        self._mods_update_actionability_filter_combo = QComboBox()
        self._mods_update_actionability_filter_combo.setObjectName(
            "inventory_update_actionability_filter_combo"
        )
        self._mods_update_actionability_filter_combo.addItem("all", "all")
        self._mods_update_actionability_filter_combo.addItem("actionable", "actionable")
        self._mods_update_actionability_filter_combo.addItem("blocked", "blocked")
        self._discovery_filter_input = QLineEdit()
        self._discovery_filter_input.setObjectName("discovery_filter_input")
        self._discovery_filter_input.setPlaceholderText("Filter discovery results")
        self._discovery_filter_input.setClearButtonEnabled(True)
        self._discovery_filter_input.setMinimumWidth(180)
        self._intake_filter_input = QLineEdit()
        self._intake_filter_input.setPlaceholderText("Filter detected packages")
        self._intake_filter_input.setClearButtonEnabled(True)
        self._intake_filter_input.setMinimumWidth(180)
        self._archive_filter_input = QLineEdit()
        self._archive_filter_input.setObjectName("archive_filter_input")
        self._archive_filter_input.setPlaceholderText("Filter archived entries")
        self._archive_filter_input.setClearButtonEnabled(True)
        self._archive_filter_input.setMinimumWidth(180)
        self._mods_filter_stats_label = QLabel("0/0 shown")
        self._discovery_filter_stats_label = QLabel("0/0 shown")
        self._intake_filter_stats_label = QLabel("0/0 shown")
        self._archive_filter_stats_label = QLabel("0/0 shown")
        self._inventory_update_guidance_label = QLabel(
            "Select an installed mod row to see update guidance."
        )
        self._inventory_update_guidance_label.setObjectName(
            "inventory_update_guidance_label"
        )
        self._inventory_update_guidance_label.setWordWrap(True)
        self._inventory_blocked_detail_label = QLabel("")
        self._inventory_blocked_detail_label.setObjectName(
            "inventory_update_blocked_detail_label"
        )
        self._inventory_blocked_detail_label.setWordWrap(True)
        self._inventory_blocked_detail_label.setVisible(False)
        _set_auxiliary_label_style(self._inventory_blocked_detail_label)
        self._inventory_source_intent_actions_label = QLabel("Saved source intent")
        _set_auxiliary_label_style(self._inventory_source_intent_actions_label)
        self._mark_local_private_button = QPushButton("Mark local/private")
        self._mark_local_private_button.setObjectName("inventory_mark_local_private_button")
        self._disable_tracking_button = QPushButton("Disable tracking")
        self._disable_tracking_button.setObjectName("inventory_disable_tracking_button")
        self._manual_source_intent_button = QPushButton("Manual source...")
        self._manual_source_intent_button.setObjectName(
            "inventory_manual_source_association_button"
        )
        self._clear_source_intent_button = QPushButton("Clear saved intent")
        self._clear_source_intent_button.setObjectName("inventory_clear_source_intent_button")
        for button in (
            self._mark_local_private_button,
            self._disable_tracking_button,
            self._manual_source_intent_button,
            self._clear_source_intent_button,
        ):
            _set_secondary_button_style(button)
        self._inventory_source_intent_actions_widget = QWidget()
        self._inventory_source_intent_actions_widget.setObjectName(
            "inventory_update_source_intent_actions"
        )
        inventory_source_intent_actions_layout = QHBoxLayout(self._inventory_source_intent_actions_widget)
        inventory_source_intent_actions_layout.setContentsMargins(0, 0, 0, 0)
        inventory_source_intent_actions_layout.setSpacing(6)
        inventory_source_intent_actions_layout.addWidget(self._inventory_source_intent_actions_label)
        inventory_source_intent_actions_layout.addWidget(self._mark_local_private_button)
        inventory_source_intent_actions_layout.addWidget(self._disable_tracking_button)
        inventory_source_intent_actions_layout.addWidget(self._manual_source_intent_button)
        inventory_source_intent_actions_layout.addWidget(self._clear_source_intent_button)
        inventory_source_intent_actions_layout.addStretch(1)
        self._inventory_source_intent_actions_widget.setVisible(False)
        self._inventory_sandbox_sync_actions_label = QLabel("Sandbox dev")
        _set_auxiliary_label_style(self._inventory_sandbox_sync_actions_label)
        self._sync_selected_to_sandbox_button = QPushButton("Sync selected to sandbox")
        self._sync_selected_to_sandbox_button.setObjectName(
            "inventory_sync_selected_to_sandbox_button"
        )
        _set_secondary_button_style(self._sync_selected_to_sandbox_button)
        self._promote_selected_to_real_button = QPushButton("Promote selected to real Mods")
        self._promote_selected_to_real_button.setObjectName(
            "inventory_promote_selected_to_real_button"
        )
        _set_secondary_button_style(self._promote_selected_to_real_button)
        self._inventory_sandbox_sync_actions_widget = QWidget()
        self._inventory_sandbox_sync_actions_widget.setObjectName(
            "inventory_sandbox_sync_actions"
        )
        inventory_sandbox_sync_actions_layout = QHBoxLayout(
            self._inventory_sandbox_sync_actions_widget
        )
        inventory_sandbox_sync_actions_layout.setContentsMargins(0, 0, 0, 0)
        inventory_sandbox_sync_actions_layout.setSpacing(6)
        inventory_sandbox_sync_actions_layout.addWidget(
            self._inventory_sandbox_sync_actions_label
        )
        inventory_sandbox_sync_actions_layout.addWidget(self._sync_selected_to_sandbox_button)
        inventory_sandbox_sync_actions_layout.addWidget(self._promote_selected_to_real_button)
        inventory_sandbox_sync_actions_layout.addStretch(1)
        self._inventory_sandbox_sync_actions_widget.setVisible(False)
        self._compare_real_vs_sandbox_button = QPushButton("Compare real vs sandbox")
        self._compare_real_vs_sandbox_button.setObjectName("compare_run_button")
        _set_primary_button_style(self._compare_real_vs_sandbox_button)
        self._compare_summary_label = QLabel(
            "Run compare to see drift between the configured real Mods path and sandbox Mods path."
        )
        self._compare_summary_label.setObjectName("compare_summary_label")
        self._compare_summary_label.setWordWrap(True)
        _set_auxiliary_label_style(self._compare_summary_label)
        self._compare_summary_label.setToolTip(
            "Run compare after changing either Mods path or archive exclusion path."
        )
        self._compare_results_table = QTableWidget(0, 5)
        self._compare_results_table.setObjectName("compare_results_table")
        self._compare_results_table.setHorizontalHeaderLabels(
            ["Mod", "Compare", "Real ver.", "Sandbox ver.", "Notes"]
        )
        self._compare_results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._compare_results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._compare_results_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._compare_results_table.verticalHeader().setDefaultSectionSize(20)
        self._compare_results_table.verticalHeader().setVisible(False)
        self._compare_results_table.setAlternatingRowColors(True)
        self._compare_results_table.setSortingEnabled(True)
        compare_header = self._compare_results_table.horizontalHeader()
        compare_header.setMinimumSectionSize(64)
        compare_header.setStretchLastSection(False)
        compare_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        compare_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        compare_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        compare_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        compare_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._open_remote_page_button = QPushButton("Open remote page")
        self._open_remote_page_button.setObjectName("inventory_open_remote_page_button")
        self._open_remote_page_button.setEnabled(False)
        self._open_remote_page_button.setToolTip(
            "Select an actionable mod row to open its remote page."
        )
        for stats_label in (
            self._mods_filter_stats_label,
            self._discovery_filter_stats_label,
            self._intake_filter_stats_label,
            self._archive_filter_stats_label,
        ):
            _set_auxiliary_label_style(stats_label)
        self._nexus_api_key_input = QLineEdit()
        self._nexus_api_key_input.setObjectName("setup_nexus_api_key_input")
        self._nexus_api_key_input.setPlaceholderText("Nexus API key")
        self._nexus_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._overwrite_checkbox = QCheckBox("Enable archive-aware replace")
        self._overwrite_checkbox.setObjectName("plan_install_overwrite_checkbox")
        self._overwrite_checkbox.setToolTip(
            "Archive the existing target before replacing it during planning."
        )
        self._install_target_combo = QComboBox()
        self._install_target_combo.setObjectName("plan_install_target_combo")
        self._install_target_combo.addItem(
            "Sandbox Mods destination (safe/test)",
            INSTALL_TARGET_SANDBOX_MODS,
        )
        self._install_target_combo.addItem(
            "Game Mods destination (real)",
            INSTALL_TARGET_CONFIGURED_REAL_MODS,
        )
        _configure_combo_box_readability(
            self._install_target_combo,
            minimum_contents_length=24,
            sample_text="Sandbox Mods destination (safe/test)",
        )
        self._scan_target_combo = QComboBox()
        self._scan_target_combo.addItem("Real Mods path (scan only)", SCAN_TARGET_CONFIGURED_REAL_MODS)
        self._scan_target_combo.addItem("Sandbox Mods path (scan only)", SCAN_TARGET_SANDBOX_MODS)
        self._intake_result_combo = QComboBox()
        self._package_inspection_selector = QComboBox()
        self._package_inspection_selector.setObjectName("packages_intake_inspection_selector")
        _configure_combo_box_readability(
            self._package_inspection_selector,
            minimum_contents_length=24,
            sample_text="ExamplePack.zip [1 mod, ready to stage]",
        )
        self._plan_selected_intake_button = QPushButton("Stage for Plan & Install")
        self._stage_update_intake_button = QPushButton("Stage update")
        self._stage_update_intake_button.setObjectName("packages_intake_stage_update_button")
        self._stage_update_intake_button.setVisible(False)
        self._install_archive_label = QLabel("Archive path for selected install destination")
        self._install_archive_label.setObjectName("plan_install_archive_label")
        self._staged_package_label = QLineEdit()
        self._staged_package_label.setObjectName("plan_install_staged_package_value")
        self._staged_package_label.setReadOnly(True)
        self._install_history_combo = QComboBox()
        self._install_history_combo.setObjectName("recovery_inspection_operation_combo")
        _configure_combo_box_readability(
            self._install_history_combo,
            minimum_contents_length=26,
            sample_text="ExamplePack.zip | 2026-03-15T12:00:00Z | REAL Mods",
        )
        self._install_history_filter_combo = QComboBox()
        self._install_history_filter_combo.setObjectName("recovery_selector_filter_combo")
        self._install_history_filter_combo.addItem("all", "all")
        self._install_history_filter_combo.addItem("ready", "ready")
        self._install_history_filter_combo.addItem("blocked", "blocked")
        self._install_history_filter_combo.addItem("legacy", "legacy")
        self._recovery_selection_summary_label = QLabel(
            "Select a recorded install to inspect recovery readiness."
        )
        self._recovery_selection_summary_label.setObjectName(
            "recovery_selection_summary_label"
        )
        self._recovery_selection_summary_label.setWordWrap(True)
        _set_auxiliary_label_style(self._recovery_selection_summary_label)
        self._inspect_recovery_button = QPushButton("Inspect recovery readiness")
        self._inspect_recovery_button.setObjectName("recovery_inspection_button")
        self._run_recovery_button = QPushButton("Run recovery")
        self._run_recovery_button.setObjectName("recovery_execute_button")
        self._plan_review_summary_label = QLabel(
            "Plan review: no plan yet. Click Plan install to review."
        )
        self._plan_review_summary_label.setObjectName("plan_install_review_summary_label")
        self._plan_review_summary_label.setWordWrap(True)
        _set_auxiliary_label_style(self._plan_review_summary_label)
        self._plan_review_explanation_label = QLabel(_NO_PLAN_REVIEW_EXPLANATION_TEXT)
        self._plan_review_explanation_label.setObjectName(
            "plan_install_review_explanation_label"
        )
        self._plan_review_explanation_label.setWordWrap(True)
        _set_auxiliary_label_style(self._plan_review_explanation_label)
        self._plan_facts_label = QLabel(_NO_PLAN_FACTS_TEXT)
        self._plan_facts_label.setObjectName("plan_install_facts_label")
        self._plan_facts_label.setWordWrap(True)
        _set_auxiliary_label_style(self._plan_facts_label)

        for control in (
            self._game_path_input,
            self._mods_path_input,
            self._zip_path_input,
            self._sandbox_mods_path_input,
            self._sandbox_archive_path_input,
            self._real_archive_path_input,
            self._watched_downloads_path_input,
            self._secondary_watched_downloads_path_input,
            self._discovery_query_input,
            self._mods_filter_input,
            self._discovery_filter_input,
            self._intake_filter_input,
            self._archive_filter_input,
            self._mods_update_actionability_filter_combo,
            self._nexus_api_key_input,
            self._scan_target_combo,
            self._install_target_combo,
            self._intake_result_combo,
            self._install_history_combo,
            self._install_history_filter_combo,
        ):
            control.setMinimumHeight(26)

        self._mods_table = QTableWidget(0, 6)
        self._mods_table.setHorizontalHeaderLabels(
            ["Name", "UniqueID", "Installed ver.", "Remote ver.", "Update status", "Folder"]
        )
        self._mods_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._mods_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._mods_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._mods_table.verticalHeader().setDefaultSectionSize(20)
        self._mods_table.verticalHeader().setVisible(False)
        self._mods_table.setAlternatingRowColors(True)
        self._mods_table.setSortingEnabled(True)
        self._mods_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._mods_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        mods_header = self._mods_table.horizontalHeader()
        mods_header.setMinimumSectionSize(64)
        mods_header.setStretchLastSection(False)
        mods_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        mods_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        mods_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        mods_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        mods_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        mods_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        self._discovery_table = QTableWidget(0, 8)
        self._discovery_table.setObjectName("discovery_results_table")
        self._discovery_table.setHorizontalHeaderLabels(
            ["Name", "UniqueID", "Author", "Source", "Compatibility", "App context", "Provider relation", "Page"]
        )
        self._discovery_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._discovery_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._discovery_table.verticalHeader().setDefaultSectionSize(20)
        self._discovery_table.verticalHeader().setVisible(False)
        self._discovery_table.setAlternatingRowColors(True)
        self._discovery_table.setSortingEnabled(True)
        self._discovery_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._discovery_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        discovery_header = self._discovery_table.horizontalHeader()
        discovery_header.setMinimumSectionSize(72)
        discovery_header.setStretchLastSection(False)
        discovery_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        discovery_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        discovery_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        discovery_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        discovery_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        discovery_header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        discovery_header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        discovery_header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)
        self._discovery_table.setColumnWidth(7, 180)

        self._archive_table = QTableWidget(0, 6)
        self._archive_table.setObjectName("archive_results_table")
        self._archive_table.setHorizontalHeaderLabels(
            ["Archive source", "Archived folder", "Restore target", "Mod name", "UniqueID", "Version"]
        )
        self._archive_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._archive_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._archive_table.verticalHeader().setDefaultSectionSize(20)
        self._archive_table.verticalHeader().setVisible(False)
        self._archive_table.setAlternatingRowColors(True)
        self._archive_table.setSortingEnabled(True)
        self._archive_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._archive_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        archive_header = self._archive_table.horizontalHeader()
        archive_header.setMinimumSectionSize(64)
        archive_header.setStretchLastSection(False)
        archive_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        archive_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        archive_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        archive_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        archive_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        archive_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

        self._findings_box = QPlainTextEdit()
        self._findings_box.setReadOnly(True)
        self._findings_box.setMinimumHeight(120)
        self._findings_box.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._package_inspection_result_box = QPlainTextEdit()
        self._package_inspection_result_box.setReadOnly(True)
        self._package_inspection_result_box.setMinimumHeight(92)
        self._package_inspection_result_box.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._package_inspection_summary_label = QLabel("")
        self._package_inspection_summary_label.setObjectName(
            "packages_intake_inspection_summary_label"
        )
        self._package_inspection_summary_label.setWordWrap(True)
        _set_auxiliary_label_style(self._package_inspection_summary_label)
        self._zip_selection_summary_label = QLabel("No zip packages selected.")
        self._zip_selection_summary_label.setObjectName(
            "packages_intake_zip_selection_summary_label"
        )
        self._zip_selection_summary_label.setWordWrap(True)
        _set_auxiliary_label_style(self._zip_selection_summary_label)
        self._zip_staging_rule_label = QLabel(
            "Inspection supports multiple packages. Staging remains one package at a time."
        )
        self._zip_staging_rule_label.setObjectName(
            "packages_intake_staging_rule_label"
        )
        self._zip_staging_rule_label.setWordWrap(True)
        _set_auxiliary_label_style(self._zip_staging_rule_label)

        self._status_strip_group = GlobalStatusStrip()
        self._status_strip_label = self._status_strip_group.current_status_label
        self._blocking_issues_strip_label = self._status_strip_group.blocking_issues_label
        self._next_step_strip_label = self._status_strip_group.next_step_label
        self._scan_context_label = QLabel("Not set")
        self._scan_context_label.setObjectName("top_context_scan_source_value")
        self._install_context_label = QLabel("Not set")
        self._install_context_label.setObjectName("top_context_install_destination_value")
        self._environment_status_label = QLabel("Not checked")
        self._environment_status_label.setObjectName("top_context_environment_status_value")
        self._smapi_update_status_label = QLabel("Not checked")
        self._smapi_log_status_label = QLabel("Not checked")
        self._nexus_status_label = QLabel("Not configured")
        self._nexus_status_label.setObjectName("top_context_runtime_nexus_value")
        self._watch_status_label = QLabel("Stopped")
        self._operation_state_label = QLabel("Idle")
        self._sandbox_launch_status_label = QLabel("Needs sandbox setup")
        self._sandbox_launch_status_label.setObjectName(
            "top_context_runtime_sandbox_launch_value"
        )
        self._scan_context_label.setWordWrap(True)
        self._install_context_label.setWordWrap(True)
        self._details_toggle = QCheckBox("Show detailed output")
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(2000)
        self._watch_timer.timeout.connect(self._on_watch_tick)

        self._zip_path_input.textChanged.connect(self._invalidate_pending_plan)
        self._zip_path_input.textChanged.connect(self._on_zip_path_changed)
        self._sandbox_mods_path_input.textChanged.connect(self._invalidate_pending_plan)
        self._sandbox_archive_path_input.textChanged.connect(self._invalidate_pending_plan)
        self._sandbox_archive_path_input.textChanged.connect(self._refresh_install_safety_panel)
        self._sandbox_archive_path_input.textChanged.connect(self._clear_mods_compare_result)
        self._real_archive_path_input.textChanged.connect(self._invalidate_pending_plan)
        self._real_archive_path_input.textChanged.connect(self._refresh_install_safety_panel)
        self._real_archive_path_input.textChanged.connect(self._clear_mods_compare_result)
        self._real_archive_path_input.textChanged.connect(
            self._refresh_inventory_sandbox_sync_action_state
        )
        self._overwrite_checkbox.toggled.connect(self._invalidate_pending_plan)
        self._overwrite_checkbox.toggled.connect(self._on_overwrite_checkbox_toggled)
        self._scan_target_combo.currentIndexChanged.connect(self._refresh_scan_context_preview)
        self._scan_target_combo.currentIndexChanged.connect(
            self._refresh_inventory_sandbox_sync_action_state
        )
        self._install_target_combo.currentIndexChanged.connect(self._on_install_target_changed)
        self._game_path_input.textChanged.connect(self._on_game_path_changed)
        self._mods_path_input.textChanged.connect(self._refresh_scan_context_preview)
        self._mods_path_input.textChanged.connect(self._refresh_install_destination_preview)
        self._mods_path_input.textChanged.connect(self._refresh_sandbox_dev_launch_state)
        self._mods_path_input.textChanged.connect(self._refresh_inventory_sandbox_sync_action_state)
        self._mods_path_input.textChanged.connect(self._clear_mods_compare_result)
        self._sandbox_mods_path_input.textChanged.connect(self._refresh_scan_context_preview)
        self._sandbox_mods_path_input.textChanged.connect(self._refresh_install_destination_preview)
        self._sandbox_mods_path_input.textChanged.connect(self._refresh_sandbox_dev_launch_state)
        self._sandbox_mods_path_input.textChanged.connect(
            self._refresh_inventory_sandbox_sync_action_state
        )
        self._sandbox_mods_path_input.textChanged.connect(self._clear_mods_compare_result)
        self._game_path_input.textChanged.connect(self._refresh_sandbox_dev_launch_state)
        self._watched_downloads_path_input.textChanged.connect(self._on_watched_path_changed)
        self._secondary_watched_downloads_path_input.textChanged.connect(
            self._on_watched_path_changed
        )
        self._nexus_api_key_input.textChanged.connect(self._on_nexus_key_changed)
        self._intake_result_combo.currentIndexChanged.connect(self._on_intake_selection_changed)
        self._package_inspection_selector.currentIndexChanged.connect(
            self._on_package_inspection_selection_changed
        )
        self._discovery_query_input.returnPressed.connect(self._on_search_discovery)
        self._details_toggle.toggled.connect(self._on_toggle_details_panel)
        self._mods_filter_input.textChanged.connect(self._apply_mods_filter)
        self._mods_update_actionability_filter_combo.currentIndexChanged.connect(
            self._apply_mods_filter
        )
        self._mods_table.itemSelectionChanged.connect(
            self._refresh_selected_mod_update_guidance
        )
        self._mods_table.itemSelectionChanged.connect(
            self._refresh_inventory_sandbox_sync_action_state
        )
        self._mark_local_private_button.clicked.connect(self._on_mark_selected_mod_local_private)
        self._disable_tracking_button.clicked.connect(self._on_disable_selected_mod_tracking)
        self._manual_source_intent_button.clicked.connect(
            self._on_set_selected_mod_manual_source_intent
        )
        self._clear_source_intent_button.clicked.connect(self._on_clear_selected_mod_source_intent)
        self._sync_selected_to_sandbox_button.clicked.connect(
            self._on_sync_selected_mods_to_sandbox
        )
        self._promote_selected_to_real_button.clicked.connect(
            self._on_promote_selected_mods_to_real
        )
        self._discovery_filter_input.textChanged.connect(self._apply_discovery_filter)
        self._intake_filter_input.textChanged.connect(self._refresh_intake_selector)
        self._archive_filter_input.textChanged.connect(self._apply_archive_filter)

        self._build_layout()
        self._refresh_intake_selector()
        self._load_startup_state()

    def _build_workspace_tabs_shell(
        self,
        tabs: QTabWidget,
        *,
        object_name: str,
        top_margin: int = 4,
    ) -> QWidget:
        tabs.setStyleSheet(
            "QTabWidget::pane { margin-top: 4px; }"
            "QTabBar::tab {"
            " padding: 5px 12px;"
            " margin-right: 3px;"
            " border: 1px solid palette(mid);"
            " border-bottom: none;"
            " border-top-left-radius: 4px;"
            " border-top-right-radius: 4px;"
            " background: palette(button);"
            " font-weight: 600;"
            "}"
            "QTabBar::tab:selected {"
            " background: palette(base);"
            "}"
            "QTabBar::tab:!selected {"
            " margin-top: 2px;"
            "}"
        )
        shell = QWidget()
        shell.setObjectName(object_name)
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, top_margin, 0, 0)
        shell_layout.setSpacing(0)
        shell_layout.addWidget(tabs)
        return shell

    def _build_layout(self) -> None:
        container = QWidget()
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(6, 4, 6, 4)
        root_layout.setSpacing(4)

        context_group = TopContextSurface(
            environment_status_label=self._environment_status_label,
            smapi_update_status_label=self._smapi_update_status_label,
            smapi_log_status_label=self._smapi_log_status_label,
            nexus_status_label=self._nexus_status_label,
            watch_status_label=self._watch_status_label,
            operation_state_label=self._operation_state_label,
            sandbox_launch_status_label=self._sandbox_launch_status_label,
            scan_context_label=self._scan_context_label,
            install_context_label=self._install_context_label,
        )
        self._context_group = context_group
        root_layout.addWidget(context_group)

        browse_game_button = QPushButton("Browse game")
        browse_game_button.clicked.connect(self._on_browse_game)
        browse_mods_button = QPushButton("Browse Mods")
        browse_mods_button.clicked.connect(self._on_browse)
        browse_sandbox_button = QPushButton("Browse sandbox")
        browse_sandbox_button.clicked.connect(self._on_browse_sandbox_mods)
        browse_sandbox_archive_button = QPushButton("Browse archive")
        browse_sandbox_archive_button.clicked.connect(self._on_browse_sandbox_archive)
        browse_real_archive_button = QPushButton("Browse real archive")
        browse_real_archive_button.clicked.connect(self._on_browse_real_archive)
        check_nexus_button = QPushButton("Check Nexus")
        check_nexus_button.clicked.connect(self._on_check_nexus_connection)
        save_button = QPushButton("Save config")
        save_button.setObjectName("setup_save_config_button")
        save_button.clicked.connect(self._on_save_config)
        detect_environment_button = QPushButton("Detect environment")
        detect_environment_button.setObjectName("setup_detect_environment_button")
        detect_environment_button.clicked.connect(self._on_detect_environment)
        export_backup_button = QPushButton("Export backup bundle")
        export_backup_button.setObjectName("setup_export_backup_button")
        export_backup_button.clicked.connect(self._on_export_backup_bundle)

        setup_scroll = SetupConfigurationSurface(
            game_path_input=self._game_path_input,
            mods_path_input=self._mods_path_input,
            sandbox_mods_path_input=self._sandbox_mods_path_input,
            sandbox_archive_path_input=self._sandbox_archive_path_input,
            real_archive_path_input=self._real_archive_path_input,
            nexus_api_key_input=self._nexus_api_key_input,
            browse_game_button=browse_game_button,
            browse_mods_button=browse_mods_button,
            browse_sandbox_button=browse_sandbox_button,
            browse_sandbox_archive_button=browse_sandbox_archive_button,
            browse_real_archive_button=browse_real_archive_button,
            check_nexus_button=check_nexus_button,
            save_button=save_button,
            detect_environment_button=detect_environment_button,
            export_backup_button=export_backup_button,
        )
        setup_scroll.setObjectName("setup_workspace_tab")
        self._setup_group = setup_scroll.setup_group
        self._setup_scroll = setup_scroll

        workspace_splitter = QSplitter()
        workspace_splitter.setChildrenCollapsible(False)
        workspace_splitter.setHandleWidth(8)
        workspace_splitter.setOpaqueResize(True)
        workspace_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._workspace_splitter = workspace_splitter

        inventory_group = QWidget()
        inventory_group.setMinimumWidth(460)
        inventory_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        inventory_layout = QVBoxLayout(inventory_group)
        inventory_layout.setContentsMargins(6, 0, 6, 4)
        inventory_layout.setSpacing(4)

        inventory_controls_tabs = QTabWidget()
        inventory_controls_tabs.setDocumentMode(True)
        inventory_controls_tabs.setUsesScrollButtons(True)
        inventory_controls_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._inventory_controls_tabs = inventory_controls_tabs

        inventory_tab = QWidget()
        inventory_tab_layout = QGridLayout(inventory_tab)
        inventory_tab_layout.setContentsMargins(8, 6, 8, 6)
        inventory_tab_layout.setHorizontalSpacing(8)
        inventory_tab_layout.setVerticalSpacing(4)
        inventory_tab_layout.addWidget(QLabel("Scan source"), 0, 0)
        inventory_tab_layout.addWidget(self._scan_target_combo, 0, 1, 1, 3)
        self._scan_button = QPushButton("Scan")
        self._scan_button.clicked.connect(self._on_scan)
        _set_primary_button_style(self._scan_button)
        inventory_tab_layout.addWidget(self._scan_button, 1, 0)
        self._check_updates_button = QPushButton("Check updates")
        self._check_updates_button.clicked.connect(self._on_check_updates)
        _set_primary_button_style(self._check_updates_button)
        inventory_tab_layout.addWidget(self._check_updates_button, 1, 1)
        self._open_remote_page_button.clicked.connect(self._on_open_remote_page)
        _set_secondary_button_style(self._open_remote_page_button)
        inventory_tab_layout.addWidget(self._open_remote_page_button, 1, 2)
        inventory_tab_layout.setColumnStretch(1, 1)
        inventory_tab_layout.setColumnStretch(2, 1)
        inventory_controls_tabs.addTab(inventory_tab, "Inventory")

        game_smapi_tab = QWidget()
        game_smapi_layout = QGridLayout(game_smapi_tab)
        game_smapi_layout.setContentsMargins(8, 6, 8, 6)
        game_smapi_layout.setHorizontalSpacing(8)
        game_smapi_layout.setVerticalSpacing(4)
        self._check_smapi_update_button = QPushButton("Check SMAPI")
        self._check_smapi_update_button.clicked.connect(self._on_check_smapi_update)
        _set_primary_button_style(self._check_smapi_update_button)
        game_smapi_layout.addWidget(self._check_smapi_update_button, 0, 0)
        self._check_smapi_log_button = QPushButton("Check SMAPI log")
        self._check_smapi_log_button.clicked.connect(self._on_check_smapi_log)
        _set_secondary_button_style(self._check_smapi_log_button)
        game_smapi_layout.addWidget(self._check_smapi_log_button, 0, 1)
        self._load_smapi_log_button = QPushButton("Load SMAPI log")
        self._load_smapi_log_button.clicked.connect(self._on_load_smapi_log)
        _set_secondary_button_style(self._load_smapi_log_button)
        game_smapi_layout.addWidget(self._load_smapi_log_button, 0, 2)
        self._open_smapi_page_button = QPushButton("Open SMAPI page")
        self._open_smapi_page_button.clicked.connect(self._on_open_smapi_page)
        _set_secondary_button_style(self._open_smapi_page_button)
        game_smapi_layout.addWidget(self._open_smapi_page_button, 1, 0)
        self._launch_vanilla_button = QPushButton("Launch vanilla")
        self._launch_vanilla_button.clicked.connect(self._on_launch_vanilla)
        _set_primary_button_style(self._launch_vanilla_button)
        game_smapi_layout.addWidget(self._launch_vanilla_button, 1, 1)
        self._launch_smapi_button = QPushButton("Launch with SMAPI")
        self._launch_smapi_button.clicked.connect(self._on_launch_smapi)
        _set_primary_button_style(self._launch_smapi_button)
        game_smapi_layout.addWidget(self._launch_smapi_button, 1, 2)
        self._launch_sandbox_dev_button = QPushButton("Launch sandbox dev")
        self._launch_sandbox_dev_button.setObjectName("launch_sandbox_dev_button")
        self._launch_sandbox_dev_button.clicked.connect(self._on_launch_sandbox_dev)
        _set_primary_button_style(self._launch_sandbox_dev_button)
        game_smapi_layout.addWidget(self._launch_sandbox_dev_button, 2, 0, 1, 3)
        game_smapi_layout.setColumnStretch(1, 1)
        game_smapi_layout.setColumnStretch(2, 1)
        inventory_controls_tabs.addTab(game_smapi_tab, "Game / SMAPI")

        inventory_archive_tab = QWidget()
        inventory_archive_tab_layout = QVBoxLayout(inventory_archive_tab)
        inventory_archive_tab_layout.setContentsMargins(8, 6, 8, 6)
        inventory_archive_tab_layout.setSpacing(4)
        archive_actions_layout = QHBoxLayout()
        archive_actions_layout.setContentsMargins(0, 0, 0, 0)
        archive_actions_layout.setSpacing(8)
        self._remove_mod_button = QPushButton("Remove selected (archive)")
        self._remove_mod_button.clicked.connect(self._on_remove_selected_mod)
        _set_secondary_button_style(self._remove_mod_button)
        archive_actions_layout.addWidget(self._remove_mod_button)
        self._rollback_mod_button = QPushButton("Rollback selected")
        self._rollback_mod_button.clicked.connect(self._on_rollback_selected_mod)
        _set_secondary_button_style(self._rollback_mod_button)
        archive_actions_layout.addWidget(self._rollback_mod_button)
        archive_actions_layout.addStretch(1)
        inventory_archive_tab_layout.addLayout(archive_actions_layout)
        inventory_archive_tab_layout.addStretch(1)
        inventory_controls_tabs.addTab(inventory_archive_tab, "Archive")

        inventory_filter_row = QHBoxLayout()
        inventory_filter_row.setSpacing(6)
        inventory_filter_row.addWidget(QLabel("Filter"))
        inventory_filter_row.addWidget(self._mods_filter_input, 1)
        inventory_filter_row.addWidget(QLabel("Updates"))
        inventory_filter_row.addWidget(self._mods_update_actionability_filter_combo)
        inventory_filter_row.addWidget(self._mods_filter_stats_label)

        flow_hint_label = QLabel(
            "Flow: Scan -> Check updates -> Open remote page -> manual download -> watcher intake -> plan/install."
        )
        flow_hint_label.setWordWrap(True)
        _set_auxiliary_label_style(flow_hint_label)
        flow_hint_label.setToolTip(
            "Workflow: Scan -> Check updates -> Open remote page -> manual download -> watcher intake -> plan/install."
        )
        flow_hint_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        self._inventory_flow_hint_label = flow_hint_label

        inventory_tabs_shell = self._build_workspace_tabs_shell(
            inventory_controls_tabs,
            object_name="inventory_tabs_shell_container",
            top_margin=4,
        )
        self._inventory_tabs_shell = inventory_tabs_shell
        inventory_layout.addWidget(inventory_tabs_shell)
        inventory_layout.addLayout(inventory_filter_row)
        inventory_layout.addWidget(self._inventory_update_guidance_label)
        inventory_layout.addWidget(self._inventory_blocked_detail_label)
        inventory_layout.addWidget(self._inventory_source_intent_actions_widget)
        inventory_layout.addWidget(self._inventory_sandbox_sync_actions_widget)
        inventory_layout.addWidget(flow_hint_label)
        inventory_layout.addWidget(self._mods_table, 1)
        workspace_splitter.addWidget(inventory_group)

        context_tabs = QTabWidget()
        context_tabs.setMinimumWidth(380)
        context_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        context_tabs.setUsesScrollButtons(True)
        context_tabs.setDocumentMode(True)
        self._context_tabs = context_tabs
        context_tabs.addTab(setup_scroll, "Setup")

        self._search_mods_button = QPushButton("Search mods")
        self._search_mods_button.setObjectName("discovery_search_button")
        self._search_mods_button.clicked.connect(self._on_search_discovery)
        _set_primary_button_style(self._search_mods_button)
        open_discovered_button = QPushButton("Open discovered page")
        open_discovered_button.clicked.connect(self._on_open_discovered_page)
        _set_secondary_button_style(open_discovered_button)
        discovery_tab = DiscoveryTabSurface(
            discovery_query_input=self._discovery_query_input,
            discovery_filter_input=self._discovery_filter_input,
            discovery_filter_stats_label=self._discovery_filter_stats_label,
            discovery_table=self._discovery_table,
            discovery_search_button=self._search_mods_button,
            open_discovered_button=open_discovered_button,
        )
        context_tabs.addTab(discovery_tab, "Discovery")

        compare_tab = QWidget()
        compare_tab.setObjectName("compare_tab")
        compare_layout = QVBoxLayout(compare_tab)
        compare_layout.setContentsMargins(6, 6, 6, 6)
        compare_layout.setSpacing(6)
        compare_intro_label = QLabel(
            "Compare configured real Mods and sandbox Mods by UniqueID before sync or promotion."
        )
        compare_intro_label.setObjectName("compare_intro_label")
        compare_intro_label.setWordWrap(True)
        _set_auxiliary_label_style(compare_intro_label)
        compare_layout.addWidget(compare_intro_label)
        compare_actions_widget = QWidget()
        compare_actions_layout = QHBoxLayout(compare_actions_widget)
        compare_actions_layout.setContentsMargins(0, 0, 0, 0)
        compare_actions_layout.setSpacing(6)
        compare_actions_layout.addWidget(self._compare_real_vs_sandbox_button)
        compare_actions_layout.addStretch(1)
        compare_layout.addWidget(compare_actions_widget)
        compare_layout.addWidget(self._compare_summary_label)
        compare_layout.addWidget(self._compare_results_table, 1)
        self._compare_real_vs_sandbox_button.clicked.connect(self._on_compare_real_and_sandbox)
        context_tabs.addTab(compare_tab, "Compare")

        intake_tab = QWidget()
        intake_layout = QVBoxLayout(intake_tab)
        intake_layout.setContentsMargins(6, 6, 6, 6)
        intake_layout.setSpacing(6)
        inspect_group = QGroupBox("Package Review")
        inspect_group.setFlat(True)
        inspect_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        inspect_layout = QGridLayout(inspect_group)
        inspect_layout.setContentsMargins(8, 6, 8, 6)
        inspect_layout.setHorizontalSpacing(8)
        inspect_layout.setVerticalSpacing(4)
        inspect_layout.addWidget(QLabel("Zip package(s)"), 0, 0)
        inspect_layout.addWidget(self._zip_path_input, 0, 1)
        browse_zip_button = QPushButton("Browse zips")
        browse_zip_button.clicked.connect(self._on_browse_zip)
        _set_secondary_button_style(browse_zip_button)
        inspect_layout.addWidget(browse_zip_button, 0, 2)
        inspect_button = QPushButton("Inspect selected")
        inspect_button.clicked.connect(self._on_inspect_zip)
        _set_primary_button_style(inspect_button)
        inspect_layout.addWidget(inspect_button, 0, 3)
        inspect_layout.addWidget(self._zip_selection_summary_label, 1, 1, 1, 3)
        inspect_layout.addWidget(self._zip_staging_rule_label, 2, 1, 1, 3)
        intake_layout.addWidget(inspect_group)

        watcher_group = QGroupBox("Watcher")
        watcher_group.setFlat(True)
        watcher_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        watcher_layout = QGridLayout(watcher_group)
        watcher_layout.setContentsMargins(8, 6, 8, 6)
        watcher_layout.setHorizontalSpacing(8)
        watcher_layout.setVerticalSpacing(4)
        watcher_layout.addWidget(QLabel("Watched downloads path 1"), 0, 0)
        watcher_layout.addWidget(self._watched_downloads_path_input, 0, 1)
        browse_downloads_button = QPushButton("Browse downloads")
        browse_downloads_button.clicked.connect(self._on_browse_watched_downloads)
        _set_secondary_button_style(browse_downloads_button)
        watcher_layout.addWidget(browse_downloads_button, 0, 2)
        watcher_layout.addWidget(QLabel("Watched downloads path 2 (optional)"), 1, 0)
        watcher_layout.addWidget(self._secondary_watched_downloads_path_input, 1, 1)
        browse_secondary_downloads_button = QPushButton("Browse path 2")
        browse_secondary_downloads_button.clicked.connect(
            self._on_browse_secondary_watched_downloads
        )
        _set_secondary_button_style(browse_secondary_downloads_button)
        watcher_layout.addWidget(browse_secondary_downloads_button, 1, 2)
        watcher_scope_label = QLabel(
            "Both watcher paths feed the same detected packages list."
        )
        watcher_scope_label.setWordWrap(True)
        _set_auxiliary_label_style(watcher_scope_label)
        watcher_layout.addWidget(watcher_scope_label, 2, 1, 1, 3)
        watch_actions = QHBoxLayout()
        start_watch_button = QPushButton("Start watch")
        start_watch_button.clicked.connect(self._on_start_watch)
        _set_primary_button_style(start_watch_button)
        watch_actions.addWidget(start_watch_button)
        stop_watch_button = QPushButton("Stop watch")
        stop_watch_button.clicked.connect(self._on_stop_watch)
        _set_secondary_button_style(stop_watch_button)
        watch_actions.addWidget(stop_watch_button)
        watch_actions.addStretch(1)
        watcher_layout.addLayout(watch_actions, 0, 3, 2, 1)
        intake_layout.addWidget(watcher_group)

        inspection_result_group = QGroupBox("Inspection Results")
        inspection_result_group.setFlat(True)
        inspection_result_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        inspection_result_layout = QGridLayout(inspection_result_group)
        inspection_result_layout.setContentsMargins(8, 6, 8, 6)
        inspection_result_layout.setHorizontalSpacing(8)
        inspection_result_layout.setVerticalSpacing(4)
        inspection_result_layout.addWidget(self._package_inspection_summary_label, 0, 0, 1, 2)
        inspection_result_layout.addWidget(QLabel("Inspected package"), 1, 0)
        inspection_result_layout.addWidget(self._package_inspection_selector, 1, 1)
        inspection_result_layout.addWidget(self._package_inspection_result_box, 2, 0, 1, 2)
        inspection_result_group.setVisible(False)
        self._package_inspection_result_group = inspection_result_group
        intake_layout.addWidget(inspection_result_group)

        detected_group = QGroupBox("Detected Packages")
        detected_group.setFlat(True)
        detected_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        detected_layout = QGridLayout(detected_group)
        detected_layout.setContentsMargins(8, 6, 8, 6)
        detected_layout.setHorizontalSpacing(8)
        detected_layout.setVerticalSpacing(4)
        detected_layout.addWidget(QLabel("Filter"), 0, 0)
        detected_layout.addWidget(self._intake_filter_input, 0, 1, 1, 2)
        detected_layout.addWidget(self._intake_filter_stats_label, 0, 3)
        detected_layout.addWidget(QLabel("Detected packages"), 1, 0)
        detected_layout.addWidget(self._intake_result_combo, 1, 1, 1, 2)
        self._plan_selected_intake_button.clicked.connect(self._on_plan_selected_intake)
        self._stage_update_intake_button.clicked.connect(self._on_stage_selected_intake_update)
        _set_primary_button_style(self._plan_selected_intake_button)
        _set_secondary_button_style(self._stage_update_intake_button)
        detected_actions_widget = QWidget()
        detected_actions_layout = QHBoxLayout(detected_actions_widget)
        detected_actions_layout.setContentsMargins(0, 0, 0, 0)
        detected_actions_layout.setSpacing(6)
        detected_actions_layout.addStretch(1)
        detected_actions_layout.addWidget(self._stage_update_intake_button)
        detected_actions_layout.addWidget(self._plan_selected_intake_button)
        detected_layout.addWidget(detected_actions_widget, 2, 1, 1, 3)
        intake_layout.addWidget(detected_group)

        intake_layout.addStretch(1)
        context_tabs.addTab(intake_tab, "Packages & Intake")

        self._refresh_archives_button = QPushButton("Refresh archives")
        self._refresh_archives_button.setObjectName("archive_refresh_button")
        self._refresh_archives_button.clicked.connect(self._on_refresh_archives)
        _set_primary_button_style(self._refresh_archives_button)
        self._restore_archived_button = QPushButton("Restore selected")
        self._restore_archived_button.setObjectName("archive_restore_button")
        self._restore_archived_button.clicked.connect(self._on_restore_selected_archive)
        _set_primary_button_style(self._restore_archived_button)
        self._restore_archived_button.setEnabled(False)
        self._delete_archived_button = QPushButton("Delete permanently")
        self._delete_archived_button.setObjectName("archive_delete_button")
        self._delete_archived_button.clicked.connect(self._on_delete_selected_archive)
        _set_danger_button_style(self._delete_archived_button)
        self._delete_archived_button.setEnabled(False)
        archive_tab = ArchiveTabSurface(
            archive_filter_input=self._archive_filter_input,
            archive_filter_stats_label=self._archive_filter_stats_label,
            archive_table=self._archive_table,
            refresh_archives_button=self._refresh_archives_button,
            restore_archived_button=self._restore_archived_button,
            delete_archived_button=self._delete_archived_button,
        )
        self._archive_table.itemSelectionChanged.connect(self._on_archive_selection_changed)
        context_tabs.addTab(archive_tab, "Archive")

        plan_install_button = QPushButton("Plan install")
        plan_install_button.setObjectName("plan_install_plan_button")
        plan_install_button.clicked.connect(self._on_plan_install)
        _set_primary_button_style(plan_install_button)
        run_install_button = QPushButton("Run install")
        run_install_button.setObjectName("plan_install_run_button")
        run_install_button.clicked.connect(self._on_run_install)
        _set_primary_button_style(run_install_button)
        plan_tab = PlanInstallTabSurface(
            install_target_combo=self._install_target_combo,
            overwrite_checkbox=self._overwrite_checkbox,
            install_archive_label=self._install_archive_label,
            plan_install_button=plan_install_button,
            run_install_button=run_install_button,
        )
        plan_tab_layout = plan_tab.content_layout
        if isinstance(plan_tab_layout, QVBoxLayout):
            safety_group = QGroupBox("Install Destination Safety")
            safety_group.setObjectName("plan_install_safety_panel_group")
            safety_group.setFlat(True)
            safety_group.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
            )
            safety_layout = QVBoxLayout(safety_group)
            safety_layout.setContentsMargins(8, 6, 8, 6)
            safety_layout.setSpacing(4)
            safety_label = QLabel("Install safety context unavailable.")
            safety_label.setObjectName("plan_install_safety_panel_text")
            safety_label.setWordWrap(True)
            safety_layout.addWidget(safety_label)
            self._install_safety_panel_group = safety_group
            self._install_safety_panel_label = safety_label
            plan_tab_layout.insertWidget(1, safety_group)

            staged_package_group = QGroupBox("Staged Package")
            staged_package_group.setObjectName("plan_install_staged_package_group")
            staged_package_group.setFlat(True)
            staged_package_group.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
            )
            staged_package_layout = QVBoxLayout(staged_package_group)
            staged_package_layout.setContentsMargins(8, 6, 8, 6)
            staged_package_layout.setSpacing(4)
            staged_package_layout.addWidget(QLabel("Current package ready for planning"))
            staged_package_layout.addWidget(self._staged_package_label)
            plan_tab_layout.insertWidget(2, staged_package_group)

            plan_review_summary_group = QGroupBox("Plan Review Summary")
            plan_review_summary_group.setObjectName("plan_install_review_summary_group")
            plan_review_summary_group.setFlat(True)
            plan_review_summary_group.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
            )
            plan_review_summary_layout = QVBoxLayout(plan_review_summary_group)
            plan_review_summary_layout.setContentsMargins(8, 6, 8, 6)
            plan_review_summary_layout.setSpacing(4)
            plan_review_summary_layout.addWidget(self._plan_review_summary_label)
            plan_review_summary_layout.addWidget(self._plan_review_explanation_label)
            plan_tab_layout.insertWidget(4, plan_review_summary_group)

            plan_facts_group = QGroupBox("Plan Facts")
            plan_facts_group.setObjectName("plan_install_facts_group")
            plan_facts_group.setFlat(True)
            plan_facts_group.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
            )
            plan_facts_layout = QVBoxLayout(plan_facts_group)
            plan_facts_layout.setContentsMargins(8, 6, 8, 6)
            plan_facts_layout.setSpacing(4)
            plan_facts_layout.addWidget(self._plan_facts_label)
            plan_tab_layout.insertWidget(5, plan_facts_group)

            recovery_group = QGroupBox("Recovery")
            recovery_group.setObjectName("recovery_inspection_group")
            recovery_group.setFlat(True)
            recovery_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
            recovery_layout = QVBoxLayout(recovery_group)
            recovery_layout.setContentsMargins(8, 6, 8, 6)
            recovery_layout.setSpacing(6)
            recovery_controls = QGridLayout()
            recovery_controls.setHorizontalSpacing(6)
            recovery_controls.setVerticalSpacing(4)
            recovery_controls.setColumnStretch(1, 1)
            recovery_controls.addWidget(QLabel("Recorded install"), 0, 0)
            recovery_controls.addWidget(self._install_history_combo, 0, 1)
            recovery_controls.addWidget(QLabel("Filter"), 0, 2)
            recovery_controls.addWidget(self._install_history_filter_combo, 0, 3)
            self._install_history_combo.currentIndexChanged.connect(
                self._on_selected_install_operation_changed
            )
            self._install_history_filter_combo.currentIndexChanged.connect(
                self._refresh_install_operation_selector
            )
            self._inspect_recovery_button.clicked.connect(self._on_inspect_selected_install_recovery)
            _set_secondary_button_style(self._inspect_recovery_button)
            recovery_controls.addWidget(self._inspect_recovery_button, 1, 2)
            self._run_recovery_button.clicked.connect(self._on_run_selected_install_recovery)
            _set_primary_button_style(self._run_recovery_button)
            self._run_recovery_button.setEnabled(False)
            recovery_controls.addWidget(self._run_recovery_button, 1, 3)
            recovery_layout.addLayout(recovery_controls)
            recovery_layout.addWidget(self._recovery_selection_summary_label)
            plan_tab_layout.insertWidget(6, recovery_group)
        context_tabs.addTab(plan_tab, "Plan & Install")
        self._plan_install_tab = plan_tab

        context_tabs_shell = self._build_workspace_tabs_shell(
            context_tabs,
            object_name="context_tabs_shell_container",
            top_margin=5,
        )
        self._context_tabs_shell = context_tabs_shell

        workspace_splitter.addWidget(context_tabs_shell)
        workspace_splitter.setCollapsible(0, False)
        workspace_splitter.setCollapsible(1, False)
        workspace_splitter.setSizes([800, 540])
        workspace_splitter.setStretchFactor(0, 6)
        workspace_splitter.setStretchFactor(1, 5)
        root_layout.addWidget(workspace_splitter, 1)

        root_layout.addWidget(self._status_strip_group)

        bottom_details_region = BottomDetailsRegion(
            details_toggle=self._details_toggle,
            findings_box=self._findings_box,
        )
        self._guidance_group = bottom_details_region
        self._secondary_group = bottom_details_region
        self._details_group = bottom_details_region.details_group
        root_layout.addWidget(bottom_details_region)
        self._apply_guidance_compact_mode(details_visible=False)
        self._background_action_buttons = (
            self._scan_button,
            self._check_updates_button,
            self._check_smapi_update_button,
            self._check_smapi_log_button,
            self._load_smapi_log_button,
            self._search_mods_button,
            self._remove_mod_button,
            self._rollback_mod_button,
            self._refresh_archives_button,
            self._restore_archived_button,
            self._delete_archived_button,
            self._compare_real_vs_sandbox_button,
            self._launch_vanilla_button,
            self._launch_smapi_button,
            self._launch_sandbox_dev_button,
            self._sync_selected_to_sandbox_button,
            self._promote_selected_to_real_button,
        )

        self.setCentralWidget(container)
        self._refresh_responsive_panel_bounds()
        self._refresh_staged_package_preview()
        self._refresh_install_operation_selector()

    def _load_startup_state(self) -> None:
        state = self._shell_service.load_startup_config()
        self._config = state.config

        if state.config is not None:
            self._game_path_input.setText(str(state.config.game_path))
            self._mods_path_input.setText(str(state.config.mods_path))
            if state.config.sandbox_mods_path is not None:
                self._sandbox_mods_path_input.setText(str(state.config.sandbox_mods_path))
            if state.config.sandbox_archive_path is not None:
                self._sandbox_archive_path_input.setText(str(state.config.sandbox_archive_path))
            if state.config.real_archive_path is not None:
                self._real_archive_path_input.setText(str(state.config.real_archive_path))
            if state.config.watched_downloads_path is not None:
                self._watched_downloads_path_input.setText(str(state.config.watched_downloads_path))
            if state.config.secondary_watched_downloads_path is not None:
                self._secondary_watched_downloads_path_input.setText(
                    str(state.config.secondary_watched_downloads_path)
                )
            if state.config.nexus_api_key is not None:
                self._nexus_api_key_input.setText(state.config.nexus_api_key)
            self._set_current_scan_target(state.config.scan_target)
            self._set_current_install_target(state.config.install_target)
            self._set_status(f"Loaded saved config from {self._shell_service.state_file}")

        if state.message:
            self._set_details_text(state.message)
            self._set_status(state.message)
            self._context_tabs.setCurrentWidget(self._setup_scroll)

        self._refresh_scan_context_preview()
        self._refresh_install_destination_preview()
        self._refresh_nexus_status(validated=False)
        self._refresh_sandbox_dev_launch_state()
        self._refresh_inventory_sandbox_sync_action_state()
        self._refresh_responsive_panel_bounds()

    def _current_operational_config_inputs(self) -> dict[str, object]:
        return {
            "game_path_text": self._game_path_input.text(),
            "mods_dir_text": self._mods_path_input.text(),
            "sandbox_mods_path_text": self._sandbox_mods_path_input.text(),
            "sandbox_archive_path_text": self._sandbox_archive_path_input.text(),
            "watched_downloads_path_text": self._watched_downloads_path_input.text(),
            "secondary_watched_downloads_path_text": (
                self._secondary_watched_downloads_path_input.text()
            ),
            "real_archive_path_text": self._real_archive_path_input.text(),
            "nexus_api_key_text": self._nexus_api_key_input.text(),
            "scan_target": self._current_scan_target(),
            "install_target": self._current_install_target(),
            "existing_config": self._config,
        }

    def _persist_session_config_on_close(self) -> None:
        result = self._shell_service.persist_session_config_if_valid(
            **self._current_operational_config_inputs()
        )
        if result.config is not None:
            self._config = result.config

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._startup_checks_scheduled:
            return
        self._startup_checks_scheduled = True
        QTimer.singleShot(0, self._run_startup_checks_if_meaningful)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._persist_session_config_on_close()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._refresh_responsive_panel_bounds()

    def _run_startup_checks_if_meaningful(self) -> None:
        if self._startup_checks_completed:
            return
        if self._active_operation_name is not None:
            QTimer.singleShot(150, self._run_startup_checks_if_meaningful)
            return
        if not self._has_meaningful_startup_game_path():
            self._startup_checks_completed = True
            return

        self._run_background_operation(
            operation_name="Startup environment check",
            running_label="Startup environment check",
            started_status="Running startup environment checks...",
            error_title="Startup environment check failed",
            task_fn=lambda: self._shell_service.detect_game_environment(
                self._game_path_input.text()
            ),
            on_success=self._on_startup_environment_check_completed,
            on_failure=self._on_startup_environment_check_failed,
            show_error_dialog=False,
        )

    def _has_meaningful_startup_game_path(self) -> bool:
        raw_game_path = self._game_path_input.text().strip()
        if not raw_game_path:
            return False
        game_path = Path(raw_game_path).expanduser()
        return game_path.exists() and game_path.is_dir()

    def _on_startup_environment_check_completed(
        self,
        status: GameEnvironmentStatus,
    ) -> None:
        self._apply_environment_status(status)
        self._set_status("Startup environment check complete.")
        if "invalid_game_path" in status.state_codes:
            self._startup_checks_completed = True
            return
        QTimer.singleShot(0, self._run_startup_smapi_update_check)

    def _on_startup_environment_check_failed(self, message: str) -> None:
        self._set_status(message)
        self._startup_checks_completed = True

    def _run_startup_smapi_update_check(self) -> None:
        if not self._has_meaningful_startup_game_path():
            self._startup_checks_completed = True
            return
        self._run_background_operation(
            operation_name="Startup SMAPI update check",
            running_label="Startup SMAPI update check",
            started_status="Checking SMAPI update status on startup...",
            error_title="Startup SMAPI update check failed",
            task_fn=lambda: self._shell_service.check_smapi_update_status(
                game_path_text=self._game_path_input.text(),
                existing_config=self._config,
            ),
            on_success=self._on_startup_smapi_update_check_completed,
            on_failure=self._on_startup_smapi_update_check_failed,
            show_error_dialog=False,
        )

    def _on_startup_smapi_update_check_completed(self, status: SmapiUpdateStatus) -> None:
        self._on_check_smapi_update_completed(status)
        QTimer.singleShot(0, self._run_startup_smapi_log_check)

    def _on_startup_smapi_update_check_failed(self, message: str) -> None:
        self._set_status(message)
        QTimer.singleShot(0, self._run_startup_smapi_log_check)

    def _run_startup_smapi_log_check(self) -> None:
        if not self._has_meaningful_startup_game_path():
            self._startup_checks_completed = True
            return
        self._run_background_operation(
            operation_name="Startup SMAPI log check",
            running_label="Startup SMAPI log check",
            started_status="Checking SMAPI log on startup...",
            error_title="Startup SMAPI log check failed",
            task_fn=lambda: self._shell_service.check_smapi_log_troubleshooting(
                game_path_text=self._game_path_input.text(),
                existing_config=self._config,
            ),
            on_success=self._on_startup_smapi_log_check_completed,
            on_failure=self._on_startup_smapi_log_check_failed,
            show_error_dialog=False,
        )

    def _on_startup_smapi_log_check_completed(self, report: SmapiLogReport) -> None:
        self._on_check_smapi_log_completed(report)
        self._startup_checks_completed = True

    def _on_startup_smapi_log_check_failed(self, message: str) -> None:
        self._set_status(message)
        self._startup_checks_completed = True

    def _on_browse_game(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select game directory",
            self._game_path_input.text() or "",
        )
        if selected:
            self._game_path_input.setText(selected)

    def _on_toggle_details_panel(self, checked: bool) -> None:
        self._details_group.setVisible(checked)
        self._apply_guidance_compact_mode(details_visible=checked)
        self._refresh_responsive_panel_bounds()
        if checked:
            self._details_toggle.setText("Hide detailed output")
        else:
            self._details_toggle.setText("Show detailed output")

    def _on_browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select Mods directory",
            self._mods_path_input.text() or "",
        )
        if selected:
            self._mods_path_input.setText(selected)

    def _on_browse_zip(self) -> None:
        selected_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select zip package(s)",
            self._zip_path_input.text() or "",
            "Zip packages (*.zip)",
        )
        if selected_paths:
            self._invalidate_pending_plan()
            self._set_selected_zip_package_paths(tuple(Path(path) for path in selected_paths))

    def _on_zip_path_changed(self, _: str) -> None:
        if not self._preserve_package_selection_on_zip_path_change:
            path_text = self._zip_path_input.text().strip()
            self._selected_zip_package_paths = (Path(path_text),) if path_text else tuple()
        self._sync_auto_overwrite_intent_with_staged_package(self._zip_path_input.text())
        self._refresh_zip_selection_summary()
        if not self._preserve_package_inspection_on_zip_path_change:
            self._clear_package_inspection_results()
        self._refresh_staged_package_preview()
        self._refresh_stage_package_action_state()

    def _on_browse_sandbox_mods(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select sandbox Mods directory",
            self._sandbox_mods_path_input.text() or "",
        )
        if selected:
            self._invalidate_pending_plan()
            self._sandbox_mods_path_input.setText(selected)
            if not self._sandbox_archive_path_input.text().strip():
                self._sandbox_archive_path_input.setText(
                    str(Path(selected).parent / ".sdvmm-sandbox-archive")
                )

    def _on_browse_sandbox_archive(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select sandbox archive directory",
            self._sandbox_archive_path_input.text() or "",
        )
        if selected:
            self._invalidate_pending_plan()
            self._sandbox_archive_path_input.setText(selected)

    def _on_browse_real_archive(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select real Mods archive directory",
            self._real_archive_path_input.text() or "",
        )
        if selected:
            self._invalidate_pending_plan()
            self._real_archive_path_input.setText(selected)

    def _on_browse_watched_downloads(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select watched downloads directory",
            self._watched_downloads_path_input.text() or "",
        )
        if selected:
            self._watched_downloads_path_input.setText(selected)

    def _on_browse_secondary_watched_downloads(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select second watched downloads directory",
            self._secondary_watched_downloads_path_input.text() or "",
        )
        if selected:
            self._secondary_watched_downloads_path_input.setText(selected)

    def _on_save_config(self) -> None:
        try:
            self._config = self._shell_service.save_operational_config(
                **self._current_operational_config_inputs()
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            self._set_status(str(exc))
            return

        self._refresh_nexus_status(validated=False)
        self._refresh_sandbox_dev_launch_state()
        self._refresh_inventory_sandbox_sync_action_state()
        self._set_status(f"Saved config to {self._shell_service.state_file}")

    def _on_detect_environment(self) -> None:
        try:
            status = self._shell_service.detect_game_environment(self._game_path_input.text())
        except AppShellError as exc:
            QMessageBox.critical(self, "Environment detect failed", str(exc))
            self._set_status(str(exc))
            return

        self._apply_environment_status(status)
        self._set_details_text(build_environment_status_text(status))
        self._refresh_sandbox_dev_launch_state()
        self._set_status("Environment detection complete.")

    def _on_export_backup_bundle(self) -> None:
        destination_root = QFileDialog.getExistingDirectory(
            self,
            "Select backup export destination",
            self._mods_path_input.text() or str(self._shell_service.state_file.parent),
        )
        if not destination_root:
            self._set_status("Backup export cancelled.")
            return

        self._run_background_operation(
            operation_name="Backup export",
            running_label="Backup export",
            started_status="Creating local backup bundle...",
            error_title="Backup export failed",
            task_fn=lambda: self._shell_service.export_backup_bundle(
                destination_root_text=destination_root,
                **self._current_operational_config_inputs(),
            ),
            on_success=self._on_backup_bundle_export_completed,
        )

    def _on_backup_bundle_export_completed(self, result: BackupBundleExportResult) -> None:
        copied_count = sum(1 for item in result.items if item.status == "copied")
        self._set_details_text(build_backup_bundle_export_text(result))
        self._set_status(
            f"Backup export complete: {copied_count} item(s) copied to {result.bundle_path}"
        )

    def _on_launch_vanilla(self) -> None:
        try:
            result = self._shell_service.launch_game_vanilla(
                game_path_text=self._game_path_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Vanilla launch failed", str(exc))
            self._set_status(str(exc))
            return

        self._set_status(
            f"Vanilla launch started (PID {result.pid}): {result.executable_path}"
        )

    def _on_launch_smapi(self) -> None:
        try:
            result = self._shell_service.launch_game_smapi(
                game_path_text=self._game_path_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "SMAPI launch failed", str(exc))
            self._set_status(str(exc))
            return

        self._set_status(
            f"SMAPI launch started (PID {result.pid}): {result.executable_path}"
        )

    def _on_launch_sandbox_dev(self) -> None:
        try:
            result = self._shell_service.launch_game_sandbox_dev(
                game_path_text=self._game_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                configured_mods_path_text=self._mods_path_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            message = str(exc)
            QMessageBox.critical(self, "Sandbox dev launch failed", message)
            self._sandbox_launch_status_label.setText(
                _sandbox_dev_launch_summary_label(False, message)
            )
            self._sandbox_launch_status_label.setToolTip(message)
            self._set_status(message)
            return

        launch_message = (
            "Sandbox dev launch started "
            f"(PID {result.pid}) via {result.executable_path} using sandbox Mods path "
            f"{result.mods_path_override}."
        )
        self._sandbox_launch_status_label.setText("Started")
        self._sandbox_launch_status_label.setToolTip(launch_message)
        self._set_status(launch_message)

    def _on_scan(self) -> None:
        self._run_background_operation(
            operation_name="Scan",
            running_label="Scan",
            started_status="Scanning selected Mods directory...",
            error_title="Scan failed",
            task_fn=lambda: self._shell_service.scan_with_target(
                scan_target=self._current_scan_target(),
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                existing_config=self._config,
            ),
            on_success=self._on_scan_completed,
        )

    def _on_scan_completed(self, result: ScanResult) -> None:
        self._render_inventory(result.inventory)
        self._set_scan_context(result.scan_path, self._scan_target_label(result.target_kind))
        self._set_status(f"Scan complete: {len(result.inventory.mods)} mods")

    def _on_compare_real_and_sandbox(self) -> None:
        self._run_background_operation(
            operation_name="Compare real vs sandbox",
            running_label="Compare real vs sandbox",
            started_status="Comparing configured real Mods against sandbox Mods...",
            error_title="Compare failed",
            task_fn=lambda: self._shell_service.compare_real_and_sandbox_mods(
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                existing_config=self._config,
            ),
            on_success=self._on_compare_real_and_sandbox_completed,
        )

    def _on_compare_real_and_sandbox_completed(self, result: ModsCompareResult) -> None:
        self._current_mods_compare_result = result
        self._render_mods_compare_result(result)
        self._set_details_text(build_mods_compare_text(result))
        self._set_status(
            f"Compare complete: {len(result.entries)} row(s) across real and sandbox Mods."
        )

    def _on_inspect_zip(self) -> None:
        selected_paths = self._selected_zip_package_paths
        if not selected_paths:
            path_text = self._zip_path_input.text().strip()
            selected_paths = (Path(path_text),) if path_text else tuple()

        try:
            batch_result = self._shell_service.inspect_zip_batch_with_inventory_context(
                tuple(str(path) for path in selected_paths),
                self._current_inventory,
                nexus_api_key_text=self._nexus_api_key_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Zip inspection failed", str(exc))
            self._set_intake_output_text(str(exc))
            self._set_status(str(exc))
            return

        self._invalidate_pending_plan()
        self._show_package_inspection_results(batch_result)
        if len(batch_result.entries) == 1:
            entry = batch_result.entries[0]
            if entry.inspection is not None:
                self._set_intake_output_text(build_package_inspection_text(entry.inspection))
                self._set_status(
                    f"Zip inspection complete: {len(entry.inspection.mods)} mod(s) detected"
                )
                return

        self._set_intake_output_text(_build_package_inspection_batch_text(batch_result))
        self._set_status(_batch_inspection_status_text(batch_result))

    def _on_plan_install(self) -> None:
        try:
            plan = self._shell_service.build_install_plan(
                package_path_text=self._zip_path_input.text(),
                install_target=self._current_install_target(),
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                allow_overwrite=self._overwrite_checkbox.isChecked(),
                configured_real_mods_path=None,
                nexus_api_key_text=self._nexus_api_key_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            self._invalidate_pending_plan()
            QMessageBox.critical(self, "Install plan failed", str(exc))
            self._set_plan_install_output_text(str(exc))
            self._set_status(str(exc))
            return

        self._apply_install_plan_review(plan)

    def _on_run_install(self) -> None:
        if self._pending_install_plan is None:
            message = "Create an install plan before executing install."
            QMessageBox.warning(self, "No install plan", message)
            self._set_status(message)
            return

        review = self._shell_service.review_install_execution(self._pending_install_plan)
        is_real_destination = (
            self._pending_install_plan.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
        )

        yes = QMessageBox.question(
            self,
            ("Confirm REAL Mods install" if is_real_destination else "Confirm sandbox install"),
            self._build_install_confirmation_message(review, is_real_destination=is_real_destination),
        )
        if yes != QMessageBox.StandardButton.Yes:
            self._set_status("Install cancelled.")
            return

        try:
            result = self._shell_service.execute_sandbox_install_plan(
                self._pending_install_plan,
                confirm_real_destination=is_real_destination,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Install failed", str(exc))
            self._set_plan_install_output_text(_error_detail_text(exc))
            self._set_status(str(exc))
            return

        history_before_install = self._install_operation_history
        self._refresh_install_operation_selector()
        self._select_new_install_operation_for_recovery(history_before_install)
        self._render_inventory(result.inventory)
        self._set_plan_install_output_text(build_sandbox_install_result_text(result))
        self._set_current_scan_target(result.destination_kind)
        self._set_scan_context(result.scan_context_path, self._scan_target_label(result.destination_kind))
        if is_real_destination:
            self._set_status(f"Real Mods install complete: {len(result.installed_targets)} target(s)")
        else:
            self._set_status(f"Sandbox install complete: {len(result.installed_targets)} target(s)")

    def _apply_install_plan_review(self, plan: SandboxInstallPlan) -> None:
        review = self._shell_service.review_install_execution(plan)
        self._pending_install_plan = plan if review.allowed else None
        self._set_plan_review_summary_text(_build_plan_review_summary_text(plan, review))
        self._set_plan_review_explanation_text(_build_plan_review_explanation_text(plan, review))
        self._set_plan_facts_text(_build_plan_facts_text(plan, review))
        self._set_plan_install_output_text(
            "\n\n".join(
                (
                    review.message,
                    build_sandbox_install_plan_text(plan),
                )
            )
        )
        self._set_status(review.message)

    def _refresh_install_operation_selector(self) -> None:
        selected_before = self._selected_install_operation()
        try:
            history = self._shell_service.load_install_operation_history()
        except AppShellError:
            self._install_operation_history = tuple()
            self._install_operation_display_indexes = tuple()
            self._current_recovery_inspection = None
            self._install_history_combo.clear()
            self._install_history_combo.addItem("<install history unavailable>")
            self._install_history_combo.setToolTip("<install history unavailable>")
            self._install_history_combo.setEnabled(False)
            self._inspect_recovery_button.setEnabled(False)
            self._run_recovery_button.setEnabled(False)
            self._refresh_recovery_selection_summary()
            return

        self._install_operation_history = history.operations
        self._install_operation_display_indexes = tuple(
            sorted(
                range(len(history.operations)),
                key=lambda index: history.operations[index].timestamp,
                reverse=True,
            )
        )
        self._current_recovery_inspection = None
        self._install_history_combo.clear()
        if not history.operations:
            self._install_history_combo.addItem("<no recorded installs>")
            self._install_history_combo.setToolTip("<no recorded installs>")
            self._install_history_combo.setEnabled(False)
            self._inspect_recovery_button.setEnabled(False)
            self._run_recovery_button.setEnabled(False)
            self._refresh_recovery_selection_summary()
            return

        filter_code = self._current_install_history_filter_code()
        visible_indexes = [
            index
            for index in self._install_operation_display_indexes
            if self._matches_install_history_filter(history.operations[index], filter_code)
        ]
        if not visible_indexes:
            self._install_history_combo.addItem("<no recorded installs match filter>")
            self._install_history_combo.setToolTip("<no recorded installs match filter>")
            self._install_history_combo.setEnabled(False)
            self._inspect_recovery_button.setEnabled(False)
            self._run_recovery_button.setEnabled(False)
            self._refresh_recovery_selection_summary()
            return

        for index in self._install_operation_display_indexes:
            if index not in visible_indexes:
                continue
            operation = history.operations[index]
            self._install_history_combo.addItem(
                _install_operation_selector_text(operation),
                index,
            )
        selected_after = -1
        if selected_before is not None:
            try:
                selected_before_index = self._install_operation_history.index(selected_before)
            except ValueError:
                selected_before_index = -1
            if selected_before_index >= 0:
                selected_after = self._install_history_combo.findData(selected_before_index)
        if selected_after >= 0:
            self._install_history_combo.setCurrentIndex(selected_after)
        else:
            self._install_history_combo.setCurrentIndex(0)
        self._install_history_combo.setEnabled(True)
        self._install_history_combo.setToolTip(self._install_history_combo.currentText())
        self._inspect_recovery_button.setEnabled(True)
        self._run_recovery_button.setEnabled(False)
        self._refresh_recovery_selection_summary()

    def _select_new_install_operation_for_recovery(
        self,
        previous_operations: tuple[InstallOperationRecord, ...],
    ) -> None:
        previous_operation_ids = {
            operation.operation_id
            for operation in previous_operations
            if operation.operation_id is not None
        }
        new_operation_indexes = [
            index
            for index, operation in enumerate(self._install_operation_history)
            if (
                operation.operation_id is not None
                and operation.operation_id not in previous_operation_ids
            )
        ]
        if len(new_operation_indexes) != 1:
            return

        combo_index = self._install_history_combo.findData(new_operation_indexes[0])
        if combo_index < 0:
            return
        self._install_history_combo.setCurrentIndex(combo_index)

    def _selected_install_operation(self) -> InstallOperationRecord | None:
        index = self._install_history_combo.currentData()
        if not isinstance(index, int):
            return None
        if not (0 <= index < len(self._install_operation_history)):
            return None
        return self._install_operation_history[index]

    def _on_selected_install_operation_changed(self, *_: object) -> None:
        self._current_recovery_inspection = None
        self._install_history_combo.setToolTip(self._install_history_combo.currentText())
        self._run_recovery_button.setEnabled(False)
        self._refresh_recovery_selection_summary()

    def _current_install_history_filter_code(self) -> str:
        data = self._install_history_filter_combo.currentData()
        if isinstance(data, str):
            return data
        return "all"

    def _matches_install_history_filter(
        self,
        operation: InstallOperationRecord,
        filter_code: str,
    ) -> bool:
        if filter_code == "legacy":
            return operation.operation_id is None
        if filter_code == "ready":
            return operation.operation_id is not None and all(
                entry.can_install for entry in operation.entries
            )
        if filter_code == "blocked":
            return operation.operation_id is not None and any(
                not entry.can_install for entry in operation.entries
            )
        return True

    def _on_inspect_selected_install_recovery(self) -> None:
        operation = self._selected_install_operation()
        if operation is None:
            message = "Select a recorded install operation first."
            self._current_recovery_inspection = None
            self._show_recovery_inspection_text(message, status_message=message)
            return
        if operation.operation_id is None:
            message = (
                "Selected install record is legacy and cannot be inspected through the "
                "ID-based recovery path."
            )
            self._current_recovery_inspection = None
            self._show_recovery_inspection_text(message, status_message=message)
            return

        try:
            inspection = self._shell_service.inspect_install_recovery_by_operation_id(
                operation.operation_id
            )
        except AppShellError as exc:
            self._current_recovery_inspection = None
            self._show_recovery_inspection_text(str(exc), status_message=str(exc))
            return

        self._current_recovery_inspection = inspection
        self._run_recovery_button.setEnabled(inspection.recovery_review.allowed)
        self._refresh_recovery_selection_summary()
        self._show_recovery_inspection_text(
            _build_install_recovery_inspection_text(inspection),
            status_message=inspection.recovery_review.message,
        )

    def _show_recovery_inspection_text(self, text: str, *, status_message: str) -> None:
        self._set_recovery_output_text(text)
        self._set_status(status_message)

    def _on_run_selected_install_recovery(self) -> None:
        operation = self._selected_install_operation()
        if operation is None:
            message = "Select a recorded install operation first."
            self._show_recovery_inspection_text(message, status_message=message)
            return
        if operation.operation_id is None:
            message = (
                "Selected install record is legacy and cannot be inspected through the "
                "ID-based recovery path."
            )
            self._show_recovery_inspection_text(message, status_message=message)
            return

        inspection = self._current_recovery_inspection
        if (
            inspection is None
            or inspection.operation.operation_id != operation.operation_id
        ):
            message = "Inspect recovery readiness first."
            self._show_recovery_inspection_text(message, status_message=message)
            return

        review = inspection.recovery_review
        if not review.allowed:
            self._show_recovery_inspection_text(
                _build_install_recovery_inspection_text(inspection),
                status_message=review.message,
            )
            return

        yes = QMessageBox.question(
            self,
            "Confirm recovery execution",
            _build_install_recovery_confirmation_message(review),
        )
        if yes != QMessageBox.StandardButton.Yes:
            self._set_status("Recovery execution cancelled.")
            return

        try:
            result = self._shell_service.execute_install_recovery_review(review)
        except AppShellError as exc:
            self._set_status(str(exc))
            self._set_recovery_output_text(str(exc))
            self._run_recovery_button.setEnabled(False)
            return

        self._on_run_selected_install_recovery_completed(result)

    def _on_run_selected_install_recovery_completed(
        self,
        result: InstallRecoveryExecutionResult,
    ) -> None:
        self._render_inventory(result.inventory)
        self._set_current_scan_target(result.destination_kind)
        self._set_scan_context(
            result.scan_context_path,
            self._scan_target_label(result.destination_kind),
        )
        self._set_recovery_output_text(_build_install_recovery_execution_result_text(result))
        self._set_status(
            f"Recovery execution complete: {result.executed_entry_count} action(s)."
        )
        self._refresh_install_operation_selector()
        self._current_recovery_inspection = None

    def _refresh_recovery_selection_summary(self) -> None:
        operation = self._selected_install_operation()
        if operation is None:
            if self._install_operation_history:
                message = "Select a recorded install to inspect recovery readiness."
            else:
                message = "No recorded install history is available for recovery inspection."
            self._recovery_selection_summary_label.setText(message)
            self._recovery_selection_summary_label.setToolTip(message)
            return

        base_text = _build_install_operation_summary_text(operation)
        if operation.operation_id is None:
            summary = (
                f"{base_text}\n"
                "Legacy record: recovery inspection is unavailable because this entry has no operation ID."
            )
            self._recovery_selection_summary_label.setText(summary)
            self._recovery_selection_summary_label.setToolTip(summary)
            return

        inspection = self._current_recovery_inspection
        if inspection is None or inspection.operation.operation_id != operation.operation_id:
            summary = (
                f"{base_text}\n"
                "Recovery status: not inspected yet.\n"
                f"{_latest_recovery_outcome_summary(None)}"
            )
            self._recovery_selection_summary_label.setText(summary)
            self._recovery_selection_summary_label.setToolTip(summary)
            return

        state_text = "ready to run" if inspection.recovery_review.allowed else "blocked"
        summary = (
            f"{base_text}\n"
            f"Recovery status: {state_text}.\n"
            f"{inspection.recovery_review.message}\n"
            f"{_latest_recovery_outcome_summary(inspection.linked_recovery_history)}"
        )
        self._recovery_selection_summary_label.setText(summary)
        self._recovery_selection_summary_label.setToolTip(summary)

    def _build_install_confirmation_message(
        self,
        review: InstallExecutionReview,
        *,
        is_real_destination: bool,
    ) -> str:
        if is_real_destination:
            summary = review.summary
            return (
                "You are about to write to the REAL game Mods directory.\n\n"
                f"{review.message}\n\n"
                "Execute install now?\n"
                f"Target: {summary.destination_mods_path}\n"
                f"Archive: {summary.archive_path}\n"
                f"Entries: {summary.total_entry_count}\n"
                f"Replace existing targets: {'yes' if summary.has_existing_targets_to_replace else 'no'}\n"
                f"Archive writes in plan: {'yes' if summary.has_archive_writes else 'no'}"
            )

        plan = self._pending_install_plan
        assert plan is not None
        return (
            "Execute install now?\n"
            f"Target: {plan.sandbox_mods_path}\n"
            f"Archive: {plan.sandbox_archive_path}\n"
            "Overwrite operations in plan: "
            f"{'yes' if any(entry.action == 'overwrite_with_archive' for entry in plan.entries) else 'no'}\n"
            f"Entries: {len(plan.entries)}"
        )

    def _on_check_updates(self) -> None:
        if self._current_inventory is None:
            message = "Scan a target first before checking metadata/update state."
            QMessageBox.warning(self, "No inventory", message)
            self._set_status(message)
            return

        inventory = self._current_inventory
        nexus_api_key_text = self._nexus_api_key_input.text()
        config = self._config
        self._run_background_operation(
            operation_name="Update check",
            running_label="Update check",
            started_status="Checking remote metadata/update states...",
            error_title="Update check failed",
            task_fn=lambda: self._shell_service.check_updates(
                inventory,
                nexus_api_key_text=nexus_api_key_text,
                existing_config=config,
            ),
            on_success=self._on_check_updates_completed,
        )

    def _on_check_updates_completed(self, report: ModUpdateReport) -> None:
        self._current_update_report = report
        self._apply_update_report(report)
        self._set_details_text(build_update_report_text(report))
        self._recompute_intake_correlations()
        self._refresh_discovery_correlations()
        self._set_status(f"Update check complete: {len(report.statuses)} mod(s)")
        self._sync_guided_update_intake_handoff(
            allow_auto_select=False,
            update_output=False,
            update_status=True,
        )

    def _on_check_smapi_update(self) -> None:
        self._run_background_operation(
            operation_name="SMAPI check",
            running_label="SMAPI check",
            started_status="Checking SMAPI version/update status...",
            error_title="SMAPI check failed",
            task_fn=lambda: self._shell_service.check_smapi_update_status(
                game_path_text=self._game_path_input.text(),
                existing_config=self._config,
            ),
            on_success=self._on_check_smapi_update_completed,
        )

    def _on_check_smapi_update_completed(self, status: SmapiUpdateStatus) -> None:
        self._last_smapi_update_status = status
        self._smapi_update_status_label.setText(_smapi_update_summary_label(status))
        self._smapi_update_status_label.setToolTip(status.message)
        self._set_details_text(build_smapi_update_status_text(status))
        self._set_status(status.message)

    def _on_check_smapi_log(self) -> None:
        self._run_background_operation(
            operation_name="SMAPI log check",
            running_label="SMAPI log check",
            started_status="Locating and parsing SMAPI log...",
            error_title="SMAPI log check failed",
            task_fn=lambda: self._shell_service.check_smapi_log_troubleshooting(
                game_path_text=self._game_path_input.text(),
                existing_config=self._config,
            ),
            on_success=self._on_check_smapi_log_completed,
        )

    def _on_load_smapi_log(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select SMAPI log file",
            "",
            "Log files (*.txt *.log);;Text files (*.txt);;All files (*)",
        )
        if not selected:
            return

        self._run_background_operation(
            operation_name="SMAPI log load",
            running_label="SMAPI log load",
            started_status=f"Parsing selected SMAPI log: {Path(selected).name}",
            error_title="SMAPI log load failed",
            task_fn=lambda _selected=selected: self._shell_service.check_smapi_log_troubleshooting(
                game_path_text=self._game_path_input.text(),
                log_path_text=_selected,
                existing_config=self._config,
            ),
            on_success=self._on_check_smapi_log_completed,
        )

    def _on_check_smapi_log_completed(self, report: SmapiLogReport) -> None:
        self._last_smapi_log_report = report
        summary = _smapi_log_summary_label(report)
        self._smapi_log_status_label.setText(summary)
        self._smapi_log_status_label.setToolTip(report.message or summary)
        self._set_details_text(build_smapi_log_report_text(report))
        self._set_status(report.message or "SMAPI log check complete.")

    def _on_open_smapi_page(self) -> None:
        url = self._shell_service.resolve_smapi_update_page_url(self._last_smapi_update_status)
        if not QDesktopServices.openUrl(QUrl(url)):
            message = f"Could not open SMAPI page: {url}"
            QMessageBox.critical(self, "Open failed", message)
            self._set_status(message)
            return
        self._set_status(f"Opened SMAPI page: {url}")

    def _on_search_discovery(self) -> None:
        query_text = self._discovery_query_input.text()
        self._run_background_operation(
            operation_name="Discovery search",
            running_label="Discovery search",
            started_status="Searching discovery index...",
            error_title="Discovery search failed",
            task_fn=lambda: self._shell_service.search_mod_discovery(
                query_text=query_text,
            ),
            on_success=self._on_search_discovery_completed,
        )

    def _on_search_discovery_completed(self, discovery_result: ModDiscoveryResult) -> None:
        self._current_discovery_result = discovery_result
        self._discovery_correlations = self._shell_service.correlate_discovery_results(
            discovery_result=discovery_result,
            inventory=self._current_inventory,
            update_report=self._current_update_report,
        )
        self._render_discovery_results(discovery_result, self._discovery_correlations)
        self._set_details_text(
            build_discovery_search_text(discovery_result, self._discovery_correlations)
        )
        self._set_status(f"Discovery search complete: {len(discovery_result.results)} result(s)")

    def _on_open_discovered_page(self) -> None:
        if self._current_discovery_result is None:
            message = "Run Search mods first."
            QMessageBox.warning(self, "No discovery results", message)
            self._set_status(message)
            return

        row = self._discovery_table.currentRow()
        if row < 0:
            message = "Select a discovery result row first."
            QMessageBox.warning(self, "No selection", message)
            self._set_status(message)
            return

        if row >= len(self._current_discovery_result.results):
            message = "Selected discovery row is invalid."
            QMessageBox.warning(self, "Invalid selection", message)
            self._set_status(message)
            return

        row_item = self._discovery_table.item(row, 0)
        if row_item is None:
            message = "Selected discovery row is invalid."
            QMessageBox.warning(self, "Invalid selection", message)
            self._set_status(message)
            return

        result_index = row_item.data(_ROLE_DISCOVERY_INDEX)
        if not isinstance(result_index, int) or not (
            0 <= result_index < len(self._current_discovery_result.results)
        ):
            message = "Selected discovery row is invalid."
            QMessageBox.warning(self, "Invalid selection", message)
            self._set_status(message)
            return

        url = row_item.data(_ROLE_DISCOVERY_LINK)
        if isinstance(url, str):
            url = url.strip()
        else:
            url = ""
        if not url:
            entry = self._current_discovery_result.results[result_index]
            try:
                url = self._shell_service.resolve_discovery_source_page_url(entry)
            except AppShellError as exc:
                QMessageBox.information(self, "No source link", str(exc))
                self._set_status(str(exc))
                return

        if not QDesktopServices.openUrl(QUrl(url)):
            message = f"Could not open discovered page: {url}"
            QMessageBox.critical(self, "Open failed", message)
            self._set_status(message)
            return

        correlation = self._selected_discovery_correlation()
        if correlation is not None:
            if (
                correlation.update_state == "update_available"
                and correlation.installed_match_unique_id is not None
            ):
                self._guided_update_unique_ids = self._add_guided_unique_id(
                    self._guided_update_unique_ids,
                    correlation.installed_match_unique_id,
                )
                self._recompute_intake_correlations()

            hint = self._shell_service.build_manual_discovery_flow_hint(
                correlation=correlation,
                watched_downloads_path_text=self._watched_downloads_path_input.text(),
                secondary_watched_downloads_path_text=(
                    self._secondary_watched_downloads_path_input.text()
                ),
                watcher_running=self._watch_timer.isActive(),
            )
            self._set_details_text(hint)
            self._set_status(
                f"Opened discovered page for {correlation.entry.unique_id}. Follow manual flow guidance."
            )
            self._sync_guided_update_intake_handoff(
                allow_auto_select=False,
                update_output=False,
                update_status=True,
            )
            return

        self._set_status(f"Opened discovered page: {url}")

    def _on_check_nexus_connection(self) -> None:
        status = self._shell_service.get_nexus_integration_status(
            nexus_api_key_text=self._nexus_api_key_input.text(),
            existing_config=self._config,
            validate_connection=True,
        )
        self._nexus_status_label.setText(_nexus_status_label(status.state, status.masked_key))
        if status.message:
            self._set_details_text(status.message)
            self._set_status(status.message)
        else:
            self._set_status("Nexus status check complete.")

    def _on_open_remote_page(self) -> None:
        if self._current_update_report is None:
            message = "Run update check first to populate remote links."
            QMessageBox.warning(self, "No metadata", message)
            self._set_status(message)
            return

        row = self._mods_table.currentRow()
        if row < 0:
            message = "Select a mod row first."
            QMessageBox.warning(self, "No selection", message)
            self._set_status(message)
            return

        row_item = self._mods_table.item(row, 0)
        if row_item is None:
            message = "Selected mod row is invalid."
            QMessageBox.warning(self, "Invalid selection", message)
            self._set_status(message)
            return

        url = row_item.data(_ROLE_REMOTE_LINK)
        if isinstance(url, str):
            url = url.strip()
        else:
            url = ""
        if not url:
            message = "No remote page is available for the selected mod."
            QMessageBox.information(self, "No remote link", message)
            self._set_status(message)
            return

        if not QDesktopServices.openUrl(QUrl(url)):
            message = f"Could not open remote page: {url}"
            QMessageBox.critical(self, "Open failed", message)
            self._set_status(message)
            return

        status = row_item.data(_ROLE_MOD_UPDATE_STATUS)
        if isinstance(status, ModUpdateStatus) and status.state == "update_available":
            self._guided_update_unique_ids = self._add_guided_unique_id(
                self._guided_update_unique_ids,
                status.unique_id,
            )
            self._recompute_intake_correlations()
            hint = self._shell_service.build_manual_update_flow_hint(
                unique_id=status.unique_id,
                watched_downloads_path_text=self._watched_downloads_path_input.text(),
                secondary_watched_downloads_path_text=(
                    self._secondary_watched_downloads_path_input.text()
                ),
                watcher_running=self._watch_timer.isActive(),
            )
            self._set_details_text(hint)
            self._set_status(
                f"Opened remote page for update target {status.unique_id}. Follow guided steps."
            )
            self._sync_guided_update_intake_handoff(
                allow_auto_select=False,
                update_output=False,
                update_status=True,
            )
            return

        self._set_status(f"Opened remote page: {url}")

    def _on_remove_selected_mod(self) -> None:
        row = self._mods_table.currentRow()
        if row < 0:
            message = "Select an installed mod row first."
            QMessageBox.warning(self, "No selection", message)
            self._set_status(message)
            return

        row_item = self._mods_table.item(row, 0)
        if row_item is None:
            message = "Selected mod row is invalid."
            QMessageBox.warning(self, "Invalid selection", message)
            self._set_status(message)
            return

        mod_name = row_item.text().strip() or "<unknown>"
        mod_folder_path = row_item.data(_ROLE_MOD_FOLDER_PATH)
        if not isinstance(mod_folder_path, str) or not mod_folder_path.strip():
            message = "Selected mod row does not include a valid folder path."
            QMessageBox.warning(self, "Invalid selection", message)
            self._set_status(message)
            return

        try:
            plan = self._shell_service.build_mod_removal_plan(
                scan_target=self._current_scan_target(),
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                mod_folder_path_text=mod_folder_path,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Removal plan failed", str(exc))
            self._set_status(str(exc))
            return

        destination_label = (
            "REAL game Mods destination"
            if plan.destination_kind == SCAN_TARGET_CONFIGURED_REAL_MODS
            else "Sandbox Mods destination"
        )
        yes = QMessageBox.question(
            self,
            "Confirm removal to archive",
            (
                "Move selected mod folder to archive?\n\n"
                f"Mod: {mod_name}\n"
                f"Destination: {destination_label}\n"
                f"Target folder: {plan.target_mod_path}\n"
                f"Archive root: {plan.archive_path}\n\n"
                "This stage performs archive move only (no permanent delete)."
            ),
        )
        if yes != QMessageBox.StandardButton.Yes:
            self._set_status("Mod removal cancelled.")
            return

        self._run_background_operation(
            operation_name="Mod removal",
            running_label="Mod removal",
            started_status=f"Removing {mod_name} to archive...",
            error_title="Mod removal failed",
            task_fn=lambda _plan=plan: self._shell_service.execute_mod_removal(
                _plan,
                confirm_removal=True,
            ),
            on_success=self._on_remove_selected_mod_completed,
        )

    def _on_remove_selected_mod_completed(self, result: ModRemovalResult) -> None:
        self._render_inventory(result.inventory)
        self._set_current_scan_target(result.destination_kind)
        self._set_scan_context(
            result.scan_context_path,
            self._scan_target_label(result.destination_kind),
        )
        self._set_details_text(build_mod_removal_result_text(result))
        self._set_status(f"Mod removed to archive: {result.archived_target.name}")

    def _on_rollback_selected_mod(self) -> None:
        row = self._mods_table.currentRow()
        if row < 0:
            message = "Select an installed mod row first."
            QMessageBox.warning(self, "No selection", message)
            self._set_status(message)
            return

        name_item = self._mods_table.item(row, 0)
        unique_id_item = self._mods_table.item(row, 1)
        version_item = self._mods_table.item(row, 2)
        if name_item is None or unique_id_item is None or version_item is None:
            message = "Selected mod row is invalid."
            QMessageBox.warning(self, "Invalid selection", message)
            self._set_status(message)
            return

        mod_name = name_item.text().strip() or "<unknown>"
        mod_unique_id = unique_id_item.text().strip()
        mod_version = version_item.text().strip() or "<unknown>"
        mod_folder_path = name_item.data(_ROLE_MOD_FOLDER_PATH)
        if not isinstance(mod_folder_path, str) or not mod_folder_path.strip():
            message = "Selected mod row does not include a valid folder path."
            QMessageBox.warning(self, "Invalid selection", message)
            self._set_status(message)
            return

        try:
            candidates = self._shell_service.list_mod_rollback_candidates(
                scan_target=self._current_scan_target(),
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                mod_folder_path_text=mod_folder_path,
                mod_unique_id_text=mod_unique_id,
                existing_config=self._config,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Rollback candidates failed", str(exc))
            self._set_status(str(exc))
            return

        if not candidates:
            message = (
                "No safe rollback candidates found for selected mod. "
                "Rollback requires matching archived entries by UniqueID and folder."
            )
            QMessageBox.information(self, "No rollback candidates", message)
            self._set_status(message)
            return

        selected_candidate = candidates[0]
        if len(candidates) > 1:
            labels = [
                (
                    f"{entry.version or '<unknown version>'} | "
                    f"{entry.archived_folder_name} | "
                    f"{entry.archived_path.name}"
                )
                for entry in candidates
            ]
            selected_label, accepted = QInputDialog.getItem(
                self,
                "Select rollback candidate",
                "Archived version:",
                labels,
                0,
                False,
            )
            if not accepted:
                self._set_status("Rollback cancelled.")
                return
            selected_index = labels.index(selected_label)
            selected_candidate = candidates[selected_index]

        try:
            plan = self._shell_service.build_mod_rollback_plan(
                scan_target=self._current_scan_target(),
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                mod_folder_path_text=mod_folder_path,
                mod_unique_id_text=mod_unique_id,
                mod_version_text=mod_version,
                archived_candidate_path_text=str(selected_candidate.archived_path),
                existing_config=self._config,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Rollback plan failed", str(exc))
            self._set_status(str(exc))
            return

        destination_label = (
            "REAL game Mods destination"
            if plan.destination_kind == SCAN_TARGET_CONFIGURED_REAL_MODS
            else "Sandbox Mods destination"
        )
        yes = QMessageBox.question(
            self,
            "Confirm rollback from archive",
            (
                "Rollback selected installed mod to archived version?\n\n"
                f"Installed mod: {mod_name}\n"
                f"Installed UniqueID: {mod_unique_id}\n"
                f"Installed version: {mod_version}\n"
                f"Installed folder: {plan.current_mod_path}\n\n"
                f"Archive source: {_archive_source_summary_label(plan.rollback_entry.source_kind)}\n"
                f"Rollback target version: {plan.rollback_entry.version or '<unknown>'}\n"
                f"Rollback target folder: {plan.rollback_entry.archived_path}\n"
                f"Restore destination: {destination_label}\n"
                f"Current version will be archived to: {plan.current_archive_path}\n\n"
                "This stage performs archive-based rollback only (no permanent delete)."
            ),
        )
        if yes != QMessageBox.StandardButton.Yes:
            self._set_status("Rollback cancelled.")
            return

        self._set_details_text(build_mod_rollback_plan_text(plan))
        self._run_background_operation(
            operation_name="Mod rollback",
            running_label="Mod rollback",
            started_status=f"Rolling back {mod_name} from archive...",
            error_title="Mod rollback failed",
            task_fn=lambda _plan=plan: self._shell_service.execute_mod_rollback(
                _plan,
                confirm_rollback=True,
            ),
            on_success=self._on_rollback_selected_mod_completed,
        )

    def _on_rollback_selected_mod_completed(self, result: ModRollbackResult) -> None:
        self._render_inventory(result.inventory)
        self._set_current_scan_target(result.destination_kind)
        self._set_scan_context(
            result.scan_context_path,
            self._scan_target_label(result.destination_kind),
        )
        self._set_details_text(build_mod_rollback_result_text(result))
        destination_label = (
            "REAL Mods" if result.destination_kind == SCAN_TARGET_CONFIGURED_REAL_MODS else "Sandbox Mods"
        )
        self._set_status(
            f"Rollback complete to {destination_label}: {result.restored_target.name}"
        )

        try:
            entries = self._shell_service.list_archived_entries(
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                existing_config=self._config,
            )
        except AppShellError:
            return
        self._archived_entries = entries
        self._render_archive_entries(entries)

    def _on_refresh_archives(self) -> None:
        self._run_background_operation(
            operation_name="Archive refresh",
            running_label="Archive refresh",
            started_status="Refreshing archive entries...",
            error_title="Archive refresh failed",
            task_fn=lambda: self._shell_service.list_archived_entries(
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                existing_config=self._config,
            ),
            on_success=self._on_refresh_archives_completed,
        )

    def _on_refresh_archives_completed(self, entries: tuple[ArchivedModEntry, ...]) -> None:
        self._archived_entries = entries
        self._render_archive_entries(entries)
        self._set_details_text(build_archive_listing_text(entries))
        self._set_status(f"Archive refresh complete: {len(entries)} entr(y/ies)")

    def _on_restore_selected_archive(self) -> None:
        entry = self._selected_archive_entry()
        if entry is None:
            message = "Select an archived entry first."
            QMessageBox.warning(self, "No archive selection", message)
            self._set_status(message)
            return

        try:
            plan = self._shell_service.build_archive_restore_plan(
                source_kind=entry.source_kind,
                archived_path_text=str(entry.archived_path),
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Restore plan failed", str(exc))
            self._set_status(str(exc))
            return

        destination_label = (
            "REAL game Mods destination"
            if plan.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
            else "Sandbox Mods destination"
        )
        source_label = _archive_source_summary_label(entry.source_kind)
        yes = QMessageBox.question(
            self,
            "Confirm archive restore",
            (
                "Restore selected archived folder to active Mods destination?\n\n"
                f"Archive source: {source_label}\n"
                f"Archived folder: {entry.archived_folder_name}\n"
                f"Archive path: {entry.archived_path}\n"
                f"Restore destination: {destination_label}\n"
                f"Restore target path: {plan.destination_target_path}\n\n"
                "This stage performs restore only (no permanent delete, no rollback selection)."
            ),
        )
        if yes != QMessageBox.StandardButton.Yes:
            self._set_status("Archive restore cancelled.")
            return

        self._run_background_operation(
            operation_name="Archive restore",
            running_label="Archive restore",
            started_status=f"Restoring {entry.archived_folder_name}...",
            error_title="Archive restore failed",
            task_fn=lambda _plan=plan: self._shell_service.execute_archive_restore(
                _plan,
                confirm_restore=True,
            ),
            on_success=self._on_restore_selected_archive_completed,
        )

    def _on_restore_selected_archive_completed(self, result: ArchiveRestoreResult) -> None:
        self._render_inventory(result.inventory)
        self._set_current_scan_target(result.destination_kind)
        self._set_scan_context(
            result.scan_context_path,
            self._scan_target_label(result.destination_kind),
        )
        self._set_details_text(build_archive_restore_result_text(result))
        self._refresh_archived_entries_after_change()
        destination_label = (
            "REAL Mods"
            if result.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
            else "Sandbox Mods"
        )
        self._set_status(
            f"Archive restore complete to {destination_label}: {result.restored_target.name}"
        )

    def _on_delete_selected_archive(self) -> None:
        entry = self._selected_archive_entry()
        if entry is None:
            message = "Select an archived entry first."
            QMessageBox.warning(self, "No archive selection", message)
            self._set_status(message)
            return

        try:
            plan = self._shell_service.build_archive_delete_plan(
                source_kind=entry.source_kind,
                archived_path_text=str(entry.archived_path),
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Archive delete plan failed", str(exc))
            self._set_status(str(exc))
            return

        yes = QMessageBox.question(
            self,
            "Confirm permanent archive delete",
            (
                "Permanently delete selected archived item?\n\n"
                f"Archive source: {_archive_source_summary_label(entry.source_kind)}\n"
                f"Archived folder: {entry.archived_folder_name}\n"
                f"Archive path: {entry.archived_path}\n\n"
                "This action is irreversible. The archived item will be deleted forever."
            ),
        )
        if yes != QMessageBox.StandardButton.Yes:
            self._set_status("Permanent archive delete cancelled.")
            return

        self._run_background_operation(
            operation_name="Archive permanent delete",
            running_label="Archive delete",
            started_status=f"Deleting archived item permanently: {entry.archived_folder_name}",
            error_title="Archive permanent delete failed",
            task_fn=lambda _plan=plan: self._shell_service.execute_archive_delete(
                _plan,
                confirm_delete=True,
            ),
            on_success=self._on_delete_selected_archive_completed,
        )

    def _on_delete_selected_archive_completed(self, result: ArchiveDeleteResult) -> None:
        self._set_details_text(build_archive_delete_result_text(result))
        self._refresh_archived_entries_after_change()
        self._set_status(f"Archived item deleted permanently: {result.deleted_path.name}")

    def _on_archive_selection_changed(self) -> None:
        has_selection = self._selected_archive_entry() is not None
        self._restore_archived_button.setEnabled(has_selection)
        self._delete_archived_button.setEnabled(has_selection)

    def _refresh_archived_entries_after_change(self) -> None:
        try:
            entries = self._shell_service.list_archived_entries(
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            self._set_status(f"Archive list refresh warning: {exc}")
            return

        self._archived_entries = entries
        self._render_archive_entries(entries)

    def _on_start_watch(self) -> None:
        try:
            watched_downloads_path_text = self._watched_downloads_path_input.text()
            secondary_watched_downloads_path_text = (
                self._secondary_watched_downloads_path_input.text()
            )
            self._known_watched_zip_paths = self._shell_service.initialize_downloads_watch(
                watched_downloads_path_text,
                secondary_watched_downloads_path_text,
            )
            initial_result = self._shell_service.poll_downloads_watch(
                watched_downloads_path_text=watched_downloads_path_text,
                secondary_watched_downloads_path_text=secondary_watched_downloads_path_text,
                known_zip_paths=tuple(),
                inventory=self._current_inventory_or_empty(),
                nexus_api_key_text=self._nexus_api_key_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Watch start failed", str(exc))
            self._set_status(str(exc))
            return

        self._known_watched_zip_paths = initial_result.known_zip_paths
        self._watch_timer.start()
        baseline_count = len(self._known_watched_zip_paths)
        self._update_watch_runtime_status_label(baseline_count)
        if not initial_result.intakes:
            self._set_status(
                "Downloads watcher started. Watching for new zip files."
            )
            return

        new_correlations = self._shell_service.correlate_intakes_with_updates(
            intakes=initial_result.intakes,
            update_report=self._current_update_report,
            guided_update_unique_ids=self._guided_update_unique_ids,
        )
        self._detected_intakes = self._merge_detected_intakes(
            self._detected_intakes,
            initial_result.intakes,
        )
        self._recompute_intake_correlations()
        self._set_details_text(
            "\n\n".join(self._watch_detail_sections(initial_result, new_correlations))
        )
        self._set_status(self._watch_detection_status_text(len(initial_result.intakes), started=True))
        self._sync_guided_update_intake_handoff(
            allow_auto_select=False,
            update_output=False,
            update_status=True,
        )

    def _on_stop_watch(self) -> None:
        self._watch_timer.stop()
        self._watch_status_label.setText("Stopped")
        self._watch_status_label.setToolTip(self._watch_sources_tooltip())
        self._set_status("Downloads watcher stopped.")

    def _on_watch_tick(self) -> None:
        try:
            result = self._shell_service.poll_downloads_watch(
                watched_downloads_path_text=self._watched_downloads_path_input.text(),
                secondary_watched_downloads_path_text=(
                    self._secondary_watched_downloads_path_input.text()
                ),
                known_zip_paths=self._known_watched_zip_paths,
                inventory=self._current_inventory_or_empty(),
                nexus_api_key_text=self._nexus_api_key_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            self._watch_timer.stop()
            self._watch_status_label.setText("Stopped (error)")
            self._watch_status_label.setToolTip(self._watch_sources_tooltip())
            self._set_status(str(exc))
            self._set_details_text(str(exc))
            return

        self._known_watched_zip_paths = result.known_zip_paths
        if not result.intakes:
            return

        new_correlations = self._shell_service.correlate_intakes_with_updates(
            intakes=result.intakes,
            update_report=self._current_update_report,
            guided_update_unique_ids=self._guided_update_unique_ids,
        )
        self._detected_intakes = self._merge_detected_intakes(
            self._detected_intakes,
            result.intakes,
        )
        self._recompute_intake_correlations()
        self._set_details_text(
            "\n\n".join(self._watch_detail_sections(result, new_correlations))
        )
        self._set_status(self._watch_detection_status_text(len(result.intakes), started=False))
        self._sync_guided_update_intake_handoff(
            allow_auto_select=False,
            update_output=False,
            update_status=True,
        )

    def _render_inventory(self, inventory: ModsInventory) -> None:
        self._current_inventory = inventory
        self._current_update_report = None
        self._guided_update_unique_ids = tuple()
        was_sorting = self._mods_table.isSortingEnabled()
        self._mods_table.setSortingEnabled(False)
        self._mods_table.setRowCount(len(inventory.mods))

        for row, mod in enumerate(inventory.mods):
            name_item = QTableWidgetItem(mod.name)
            name_item.setData(_ROLE_REMOTE_LINK, "")
            name_item.setData(_ROLE_MOD_UPDATE_STATUS, None)
            name_item.setData(_ROLE_MOD_FOLDER_PATH, str(mod.folder_path))
            name_item.setData(_ROLE_UPDATE_ACTIONABLE, False)
            name_item.setData(
                _ROLE_UPDATE_BLOCK_REASON,
                "Run Check updates to evaluate update actionability.",
            )
            self._mods_table.setItem(row, 0, name_item)
            self._mods_table.setItem(row, 1, QTableWidgetItem(mod.unique_id))
            self._mods_table.setItem(row, 2, QTableWidgetItem(mod.version))
            self._mods_table.setItem(row, 3, QTableWidgetItem("-"))
            status_item = QTableWidgetItem("not_checked")
            status_item.setToolTip("Run Check updates to evaluate update actionability.")
            self._mods_table.setItem(row, 4, status_item)
            self._mods_table.setItem(row, 5, QTableWidgetItem(mod.folder_path.name))

        self._mods_table.setSortingEnabled(was_sorting)
        self._apply_mods_filter()
        dependency_findings = self._shell_service.evaluate_installed_dependency_preflight(inventory)
        self._set_details_text(
            "\n\n".join(
                (
                    build_findings_text(inventory),
                    build_dependency_preflight_text(
                        title="Installed dependency preflight:",
                        findings=dependency_findings,
                    ),
                )
            )
        )
        self._refresh_detected_intakes_for_current_inventory()
        self._refresh_discovery_correlations()

    def _apply_update_report(self, report: ModUpdateReport) -> None:
        if self._current_inventory is None:
            return

        by_folder_text = {str(status.folder_path): status for status in report.statuses}
        was_sorting = self._mods_table.isSortingEnabled()
        self._mods_table.setSortingEnabled(False)
        for row in range(self._mods_table.rowCount()):
            name_item = self._mods_table.item(row, 0)
            if name_item is None:
                continue
            folder_path_text = name_item.data(_ROLE_MOD_FOLDER_PATH)
            if not isinstance(folder_path_text, str):
                continue
            status = by_folder_text.get(folder_path_text)
            if status is None:
                self._mods_table.setItem(row, 3, QTableWidgetItem("-"))
                status_item = QTableWidgetItem("metadata_unavailable")
                reason = "Metadata unavailable for this mod in the latest update check."
                status_item.setToolTip(reason)
                self._mods_table.setItem(row, 4, status_item)
                name_item.setData(_ROLE_MOD_UPDATE_STATUS, None)
                name_item.setData(_ROLE_REMOTE_LINK, "")
                name_item.setData(_ROLE_UPDATE_ACTIONABLE, False)
                name_item.setData(_ROLE_UPDATE_BLOCK_REASON, reason)
                continue

            actionable, blocked_reason = _update_status_actionability(status)
            self._mods_table.setItem(row, 3, QTableWidgetItem(status.remote_version or "-"))
            status_item = QTableWidgetItem(status.state)
            status_item.setToolTip(
                blocked_reason
                if not actionable
                else "Actionable: update is available for this mod."
            )
            self._mods_table.setItem(row, 4, status_item)
            name_item.setData(_ROLE_MOD_UPDATE_STATUS, status)
            name_item.setData(
                _ROLE_REMOTE_LINK,
                status.remote_link.page_url if status.remote_link is not None else "",
            )
            name_item.setData(_ROLE_UPDATE_ACTIONABLE, actionable)
            name_item.setData(_ROLE_UPDATE_BLOCK_REASON, blocked_reason)
        self._mods_table.setSortingEnabled(was_sorting)
        self._apply_mods_filter()

    def _render_discovery_results(
        self,
        discovery_result: ModDiscoveryResult,
        correlations: tuple[DiscoveryContextCorrelation, ...],
    ) -> None:
        was_sorting = self._discovery_table.isSortingEnabled()
        self._discovery_table.setSortingEnabled(False)
        self._discovery_table.setRowCount(len(discovery_result.results))

        for result_index, entry in enumerate(discovery_result.results):
            row = result_index
            correlation = correlations[row] if row < len(correlations) else None
            source_label = _discovery_source_label(entry.source_provider)
            compatibility_label = _discovery_compatibility_label(entry.compatibility_state)
            context_text = correlation.context_summary if correlation is not None else "No app context"
            provider_relation = (
                correlation.provider_relation_note
                if correlation is not None and correlation.provider_relation_note
                else "-"
            )
            name_item = QTableWidgetItem(entry.name)
            name_item.setData(_ROLE_DISCOVERY_INDEX, result_index)
            name_item.setData(_ROLE_DISCOVERY_LINK, entry.source_page_url or "")
            self._discovery_table.setItem(row, 0, name_item)
            self._discovery_table.setItem(row, 1, QTableWidgetItem(entry.unique_id))
            self._discovery_table.setItem(row, 2, QTableWidgetItem(entry.author))
            self._discovery_table.setItem(row, 3, QTableWidgetItem(source_label))
            self._discovery_table.setItem(row, 4, QTableWidgetItem(compatibility_label))
            self._discovery_table.setItem(row, 5, QTableWidgetItem(context_text))
            self._discovery_table.setItem(row, 6, QTableWidgetItem(provider_relation))
            page_text = entry.source_page_url or "-"
            self._discovery_table.setItem(row, 7, QTableWidgetItem(page_text))

        self._discovery_table.setSortingEnabled(was_sorting)
        self._apply_discovery_filter()

    def _render_archive_entries(self, entries: tuple[ArchivedModEntry, ...]) -> None:
        was_sorting = self._archive_table.isSortingEnabled()
        self._archive_table.setSortingEnabled(False)
        self._archive_table.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            source_item = QTableWidgetItem(_archive_source_summary_label(entry.source_kind))
            source_item.setData(_ROLE_ARCHIVE_INDEX, row)
            self._archive_table.setItem(row, 0, source_item)
            self._archive_table.setItem(row, 1, QTableWidgetItem(entry.archived_folder_name))
            self._archive_table.setItem(row, 2, QTableWidgetItem(entry.target_folder_name))
            self._archive_table.setItem(row, 3, QTableWidgetItem(entry.mod_name or "-"))
            self._archive_table.setItem(row, 4, QTableWidgetItem(entry.unique_id or "-"))
            self._archive_table.setItem(row, 5, QTableWidgetItem(entry.version or "-"))

        self._archive_table.setSortingEnabled(was_sorting)
        self._apply_archive_filter()
        self._on_archive_selection_changed()

    def _render_mods_compare_result(self, result: ModsCompareResult) -> None:
        was_sorting = self._compare_results_table.isSortingEnabled()
        self._compare_results_table.setSortingEnabled(False)
        self._compare_results_table.setRowCount(len(result.entries))

        for row, entry in enumerate(result.entries):
            real_version = entry.real_mod.version if entry.real_mod is not None else "-"
            sandbox_version = entry.sandbox_mod.version if entry.sandbox_mod is not None else "-"
            note_text = entry.note or "-"
            self._compare_results_table.setItem(row, 0, QTableWidgetItem(entry.name))
            self._compare_results_table.setItem(
                row,
                1,
                QTableWidgetItem(_mods_compare_state_label(entry.state)),
            )
            self._compare_results_table.setItem(row, 2, QTableWidgetItem(real_version))
            self._compare_results_table.setItem(row, 3, QTableWidgetItem(sandbox_version))
            note_item = QTableWidgetItem(note_text)
            note_item.setToolTip(note_text if entry.note else "")
            self._compare_results_table.setItem(row, 4, note_item)

        self._compare_results_table.setSortingEnabled(was_sorting)
        self._compare_summary_label.setText(_mods_compare_summary_text(result))
        self._compare_summary_label.setToolTip(build_mods_compare_text(result))

    def _set_status(self, text: str) -> None:
        self._status_strip_label.setText(text)
        self._status_strip_label.setToolTip(text)

    def _run_background_operation(
        self,
        *,
        operation_name: str,
        running_label: str,
        started_status: str,
        error_title: str,
        task_fn: Callable[[], object],
        on_success: Callable[[object], None],
        on_failure: Callable[[str], None] | None = None,
        show_error_dialog: bool = True,
    ) -> None:
        if self._active_operation_name is not None:
            self._set_status(
                f"{self._active_operation_name} is already running. Wait for it to finish."
            )
            return

        task = BackgroundTask(task_fn)
        self._active_background_task = task
        self._active_operation_name = operation_name
        self._operation_state_label.setText(f"Running: {running_label}")
        self._set_background_actions_enabled(False)
        self._set_status(started_status)

        task.signals.succeeded.connect(
            lambda result, _name=operation_name, _handler=on_success: self._on_background_operation_succeeded(
                _name,
                _handler,
                result,
            )
        )
        task.signals.failed.connect(
            lambda exc, _name=operation_name, _title=error_title, _on_failure=on_failure, _show_error_dialog=show_error_dialog: self._on_background_operation_failed(
                _name,
                _title,
                exc,
                on_failure=_on_failure,
                show_error_dialog=_show_error_dialog,
            )
        )
        self._thread_pool.start(task)

    def _on_background_operation_succeeded(
        self,
        operation_name: str,
        on_success: Callable[[object], None],
        result: object,
    ) -> None:
        try:
            on_success(result)
        except Exception as exc:  # pragma: no cover - unexpected UI-path errors
            message = f"{operation_name} completed, but result handling failed: {exc}"
            QMessageBox.critical(self, f"{operation_name} failed", message)
            self._set_details_text(message)
            self._set_status(message)
            self._finish_background_operation(operation_name, success=False)
            return

        self._finish_background_operation(operation_name, success=True)

    def _on_background_operation_failed(
        self,
        operation_name: str,
        error_title: str,
        exc: object,
        *,
        on_failure: Callable[[str], None] | None = None,
        show_error_dialog: bool = True,
    ) -> None:
        message = str(exc)
        detail_text = _error_detail_text(exc)
        if show_error_dialog:
            QMessageBox.critical(self, error_title, message)
        self._set_details_text(detail_text)
        self._set_status(message)
        if on_failure is not None:
            on_failure(message)
        self._finish_background_operation(operation_name, success=False)

    def _finish_background_operation(self, operation_name: str, *, success: bool) -> None:
        if self._active_operation_name != operation_name:
            return

        self._active_operation_name = None
        self._active_background_task = None
        self._set_background_actions_enabled(True)
        self._on_archive_selection_changed()
        if success:
            self._operation_state_label.setText(f"Last: {operation_name} finished")
            return
        self._operation_state_label.setText(f"Last: {operation_name} failed")

    def _set_background_actions_enabled(self, enabled: bool) -> None:
        for button in self._background_action_buttons:
            button.setEnabled(enabled)
        self._discovery_query_input.setEnabled(enabled)
        self._refresh_sandbox_dev_launch_state()
        self._refresh_inventory_sandbox_sync_action_state()

    def _set_details_text(self, text: str) -> None:
        self._findings_box.setPlainText(text)
        blocking_issue, next_step = _summarize_details_text(text)
        self._blocking_issues_strip_label.setText(blocking_issue)
        self._next_step_strip_label.setText(next_step)
        self._blocking_issues_strip_label.setToolTip(blocking_issue)
        self._next_step_strip_label.setToolTip(next_step)

    def _refresh_sandbox_dev_launch_state(self, *_: object) -> None:
        readiness = self._shell_service.get_sandbox_dev_launch_readiness(
            game_path_text=self._game_path_input.text(),
            sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
            configured_mods_path_text=self._mods_path_input.text(),
            existing_config=self._config,
        )
        summary = _sandbox_dev_launch_summary_label(readiness.ready, readiness.message)
        tooltip = readiness.message
        if readiness.ready:
            tooltip = (
                f"{readiness.message}\n"
                f"Launch target: {readiness.executable_path}\n"
                f"Sandbox Mods path: {readiness.sandbox_mods_path}"
            )
        self._sandbox_launch_status_label.setText(summary)
        self._sandbox_launch_status_label.setToolTip(tooltip)
        button_enabled = readiness.ready and self._active_operation_name is None
        self._launch_sandbox_dev_button.setEnabled(button_enabled)
        self._launch_sandbox_dev_button.setToolTip(
            tooltip if button_enabled else readiness.message
        )

    def _set_recovery_output_text(self, text: str) -> None:
        self._set_details_text(text)

    def _set_intake_output_text(self, text: str) -> None:
        self._set_details_text(text)

    def _clear_mods_compare_result(self, *_: object) -> None:
        self._current_mods_compare_result = None
        self._compare_results_table.setRowCount(0)
        self._compare_summary_label.setText(
            "Run compare to see drift between the configured real Mods path and sandbox Mods path."
        )
        self._compare_summary_label.setToolTip(
            "Run compare after changing either Mods path or archive exclusion path."
        )

    def _set_plan_install_output_text(self, text: str) -> None:
        self._set_details_text(text)

    def _set_plan_review_summary_text(self, text: str) -> None:
        self._plan_review_summary_label.setText(text)
        self._plan_review_summary_label.setToolTip(text)

    def _set_plan_review_explanation_text(self, text: str) -> None:
        self._plan_review_explanation_label.setText(text)
        self._plan_review_explanation_label.setToolTip(text)

    def _set_plan_facts_text(self, text: str) -> None:
        self._plan_facts_label.setText(text)
        self._plan_facts_label.setToolTip(text)

    def _set_package_inspection_result_text(self, text: str | None) -> None:
        has_text = bool(text and text.strip())
        self._package_inspection_result_box.setPlainText(text or "")
        self._package_inspection_result_group.setVisible(has_text)
        self._refresh_stage_package_action_state()
        self._refresh_responsive_panel_bounds()

    def _clear_package_inspection_results(self) -> None:
        self._package_inspection_batch_result = None
        self._package_inspection_summary_label.clear()
        self._package_inspection_selector.clear()
        self._package_inspection_selector.setEnabled(False)
        self._set_package_inspection_result_text(None)

    def _show_package_inspection_results(
        self,
        batch_result: PackageInspectionBatchResult,
    ) -> None:
        self._package_inspection_batch_result = batch_result
        self._package_inspection_summary_label.setText(
            _package_inspection_batch_summary_label_text(batch_result)
        )
        self._package_inspection_summary_label.setToolTip(
            _build_package_inspection_batch_text(batch_result)
        )
        self._package_inspection_selector.blockSignals(True)
        self._package_inspection_selector.clear()
        for index, entry in enumerate(batch_result.entries):
            self._package_inspection_selector.addItem(
                _package_inspection_entry_label(entry),
                index,
            )
        self._package_inspection_selector.setEnabled(len(batch_result.entries) > 1)
        self._package_inspection_selector.setCurrentIndex(0)
        self._package_inspection_selector.blockSignals(False)
        if batch_result.entries:
            self._show_selected_package_inspection_result(0)
        else:
            self._clear_package_inspection_results()

    def _show_selected_package_inspection_result(self, index: int) -> None:
        entry = self._package_inspection_entry_at(index)
        if entry is None:
            self._set_package_inspection_result_text(None)
            return
        self._set_selected_zip_package_paths(
            tuple(batch_entry.package_path for batch_entry in self._package_inspection_batch_result.entries)
            if self._package_inspection_batch_result is not None
            else (entry.package_path,),
            current_path=entry.package_path,
            preserve_inspection=True,
        )
        self._set_package_inspection_result_text(_package_inspection_entry_text(entry))

    def _set_selected_zip_package_paths(
        self,
        package_paths: tuple[Path, ...],
        *,
        current_path: Path | None = None,
        preserve_inspection: bool = False,
    ) -> None:
        self._selected_zip_package_paths = package_paths
        self._refresh_zip_selection_summary()
        if not preserve_inspection:
            self._clear_package_inspection_results()
        path_text = str(current_path or package_paths[0]) if package_paths else ""
        self._preserve_package_selection_on_zip_path_change = True
        self._preserve_package_inspection_on_zip_path_change = preserve_inspection
        self._zip_path_input.setText(path_text)
        self._preserve_package_selection_on_zip_path_change = False
        self._preserve_package_inspection_on_zip_path_change = False

    def _refresh_zip_selection_summary(self) -> None:
        selected_count = len(self._selected_zip_package_paths)
        if selected_count == 0:
            self._zip_selection_summary_label.setText("No zip packages selected.")
            self._zip_selection_summary_label.setToolTip("")
            return

        package_names = [path.name for path in self._selected_zip_package_paths]
        package_list = "\n".join(package_names)
        if selected_count == 1:
            self._zip_selection_summary_label.setText(
                f"1 zip package selected: {package_names[0]}"
            )
            self._zip_selection_summary_label.setToolTip(package_list)
            return

        self._zip_selection_summary_label.setText(
            f"{selected_count} zip packages selected for inspection."
        )
        self._zip_selection_summary_label.setToolTip(package_list)

    def _configured_watch_path_texts(self) -> tuple[str, ...]:
        configured_paths: list[str] = []
        for raw_text in (
            self._watched_downloads_path_input.text().strip(),
            self._secondary_watched_downloads_path_input.text().strip(),
        ):
            if raw_text and raw_text not in configured_paths:
                configured_paths.append(raw_text)
        return tuple(configured_paths)

    def _watch_sources_summary(self) -> str:
        configured_paths = self._configured_watch_path_texts()
        if not configured_paths:
            return "no watch paths"
        if len(configured_paths) == 1:
            return configured_paths[0]
        return f"{len(configured_paths)} paths"

    def _watch_sources_tooltip(self) -> str:
        return "\n".join(self._configured_watch_path_texts())

    def _update_watch_runtime_status_label(self, baseline_count: int) -> None:
        self._watch_status_label.setText(
            f"Running | {self._watch_sources_summary()} | baseline={baseline_count} zip(s)"
        )
        self._watch_status_label.setToolTip(self._watch_sources_tooltip())

    def _watch_detail_sections(
        self,
        result: DownloadsWatchPollResult,
        correlations: tuple[IntakeUpdateCorrelation, ...],
    ) -> tuple[str, ...]:
        sections: list[str] = []
        configured_paths = self._configured_watch_path_texts()
        if len(configured_paths) > 1:
            sections.append("Watcher sources:\n- " + "\n- ".join(configured_paths))
        sections.append(build_downloads_intake_text(result))
        sections.append(build_intake_correlation_text(correlations))
        return tuple(sections)

    def _watch_detection_status_text(self, detected_count: int, *, started: bool) -> str:
        configured_paths = self._configured_watch_path_texts()
        if started and len(configured_paths) <= 1:
            return (
                f"Downloads watcher started. Detected {detected_count} package(s) in watched downloads."
            )
        if started:
            return (
                f"Downloads watcher started. Detected {detected_count} package(s) across watched downloads paths."
            )
        if len(configured_paths) <= 1:
            return f"Detected {detected_count} new package(s) in watched downloads."
        return f"Detected {detected_count} new package(s) across watched downloads paths."

    def _set_scan_context(self, path: Path, label: str) -> None:
        path_text = str(path)
        self._scan_context_label.setText(f"{label} selected")
        self._scan_context_label.setToolTip(path_text)

    def _apply_environment_status(self, status: GameEnvironmentStatus) -> None:
        self._last_environment_status = status
        if status.mods_path is not None and not self._mods_path_input.text().strip():
            self._mods_path_input.setText(str(status.mods_path))

        self._environment_status_label.setText(_environment_summary_label(status))
        self._environment_status_label.setToolTip(str(status.game_path))
        if status.smapi_path is None:
            self._smapi_update_status_label.setText("SMAPI not detected")
            self._smapi_update_status_label.setToolTip(
                "SMAPI entrypoint was not detected for this game path."
            )
        if "invalid_game_path" in status.state_codes:
            self._smapi_log_status_label.setText("Need valid game path")
            self._smapi_log_status_label.setToolTip(
                "SMAPI log auto-detection requires a valid game path context."
            )

    def _invalidate_pending_plan(self, *_: object) -> None:
        self._pending_install_plan = None
        self._set_plan_review_summary_text(_NO_PLAN_REVIEW_SUMMARY_TEXT)
        self._set_plan_review_explanation_text(_NO_PLAN_REVIEW_EXPLANATION_TEXT)
        self._set_plan_facts_text(_NO_PLAN_FACTS_TEXT)

    def _on_watched_path_changed(self, *_: object) -> None:
        self._known_watched_zip_paths = tuple()
        self._detected_intakes = tuple()
        self._intake_correlations = tuple()
        self._refresh_intake_selector()
        if self._watch_timer.isActive():
            self._watch_timer.stop()
            self._watch_status_label.setText("Stopped (path changed)")
            self._watch_status_label.setToolTip(self._watch_sources_tooltip())
            self._set_status("Watcher stopped because watched path changed.")

    def _on_game_path_changed(self, *_: object) -> None:
        self._last_environment_status = None
        self._last_smapi_log_report = None
        self._last_smapi_update_status = None
        self._environment_status_label.setText("Not checked")
        self._smapi_log_status_label.setText("Not checked")
        self._smapi_update_status_label.setText("Not checked")
        self._refresh_sandbox_dev_launch_state()

    def _on_nexus_key_changed(self, *_: object) -> None:
        self._refresh_nexus_status(validated=False)

    def _on_install_target_changed(self, *_: object) -> None:
        self._pending_install_plan = None
        self._set_plan_review_summary_text(_NO_PLAN_REVIEW_SUMMARY_TEXT)
        self._set_plan_review_explanation_text(_NO_PLAN_REVIEW_EXPLANATION_TEXT)
        self._set_plan_facts_text(_NO_PLAN_FACTS_TEXT)
        self._refresh_install_destination_preview()
        if self._current_install_target() == INSTALL_TARGET_CONFIGURED_REAL_MODS:
            self._set_status("Install destination set to REAL game Mods path. Review carefully before executing.")
        else:
            self._set_status("Install destination set to sandbox Mods path.")

    def _on_plan_selected_intake(self) -> None:
        selected_index = self._selected_intake_index()
        if selected_index >= 0:
            try:
                intake = self._shell_service.select_intake_result(
                    intakes=self._detected_intakes,
                    selected_index=selected_index,
                )
            except AppShellError as exc:
                QMessageBox.warning(self, "No package selected", str(exc))
                self._set_intake_output_text(str(exc))
                self._set_status(str(exc))
                return

            if not self._shell_service.is_actionable_intake_result(intake):
                message = (
                    "Selected package cannot be staged for install "
                    f"({intake.classification})."
                )
                QMessageBox.information(self, "Package not actionable", message)
                self._set_intake_output_text(message)
                self._set_status(message)
                return

            self._stage_package_for_plan_install(
                str(intake.package_path),
                status_message=f"Staged package for planning: {intake.package_path.name}",
            )
            return

        if self._has_stageable_inspected_package():
            inspection_entry = self._selected_package_inspection_entry()
            assert inspection_entry is not None
            self._stage_package_for_plan_install(
                str(inspection_entry.package_path),
                status_message=(
                    "Staged package for planning: "
                    f"{inspection_entry.package_path.name}"
                ),
            )
            return

        message = "Select a detected package or inspect a zip package before staging for install."
        QMessageBox.warning(self, "No package to stage", message)
        self._set_intake_output_text(message)
        self._set_status(message)

    def _on_stage_selected_intake_update(self) -> None:
        selected_index = self._selected_intake_index()
        if selected_index < 0 or not self._selected_intake_supports_update_action():
            message = "Select a detected update package first."
            self._set_intake_output_text(message)
            self._set_status(message)
            return

        try:
            intake = self._shell_service.select_intake_result(
                intakes=self._detected_intakes,
                selected_index=selected_index,
            )
        except AppShellError as exc:
            QMessageBox.warning(self, "No package selected", str(exc))
            self._set_intake_output_text(str(exc))
            self._set_status(str(exc))
            return

        self._stage_package_for_plan_install(
            str(intake.package_path),
            apply_update_intent=True,
            status_message=(
                "Staged update package for planning with archive-aware replace enabled: "
                f"{intake.package_path.name}"
            ),
        )

    def _on_intake_selection_changed(self, *_: object) -> None:
        self._refresh_stage_package_action_state()

    def _on_package_inspection_selection_changed(self, *_: object) -> None:
        selected_index = self._selected_package_inspection_index()
        if selected_index < 0:
            self._refresh_stage_package_action_state()
            return
        self._show_selected_package_inspection_result(selected_index)

    def _apply_mods_filter(self, *_: object) -> None:
        filter_text = self._mods_filter_input.text()
        actionability_filter = self._current_mods_update_actionability_filter()
        visible_count = 0
        for row in range(self._mods_table.rowCount()):
            row_values = []
            for col in range(self._mods_table.columnCount()):
                item = self._mods_table.item(row, col)
                row_values.append(item.text() if item is not None else "")
            matches_text = row_matches_filter(row_values, filter_text)
            name_item = self._mods_table.item(row, 0)
            is_actionable = bool(
                name_item is not None and name_item.data(_ROLE_UPDATE_ACTIONABLE) is True
            )
            matches_actionability = True
            if actionability_filter == "actionable":
                matches_actionability = is_actionable
            elif actionability_filter == "blocked":
                matches_actionability = not is_actionable
            matches = matches_text and matches_actionability
            self._mods_table.setRowHidden(row, not matches)
            if matches:
                visible_count += 1
        self._set_filter_stats(
            self._mods_filter_stats_label,
            shown_count=visible_count,
            total_count=self._mods_table.rowCount(),
        )
        self._refresh_selected_mod_update_guidance()

    def _current_mods_update_actionability_filter(self) -> str:
        value = self._mods_update_actionability_filter_combo.currentData()
        if isinstance(value, str):
            return value
        return "all"

    def _refresh_selected_mod_update_guidance(self) -> None:
        row = self._mods_table.currentRow()
        has_selected_items = bool(self._mods_table.selectedItems())
        if row < 0 or self._mods_table.isRowHidden(row) or not has_selected_items:
            message = "Select an installed mod row to see update guidance."
            self._set_inventory_blocked_detail_text(None)
            self._set_open_remote_page_state(
                enabled=False,
                tooltip="Select an actionable mod row to open its remote page.",
            )
            self._refresh_inventory_source_intent_action_state(
                selected_unique_id=None,
                selected=False,
                can_manage_intent=False,
            )
            self._inventory_update_guidance_label.setText(message)
            self._inventory_update_guidance_label.setToolTip(message)
            self._refresh_inventory_sandbox_sync_action_state()
            return

        name_item = self._mods_table.item(row, 0)
        unique_id_item = self._mods_table.item(row, 1)
        status_item = self._mods_table.item(row, 4)
        if name_item is None:
            message = "Select an installed mod row to see update guidance."
            self._set_inventory_blocked_detail_text(None)
            self._set_open_remote_page_state(
                enabled=False,
                tooltip="Select an actionable mod row to open its remote page.",
            )
            self._refresh_inventory_source_intent_action_state(
                selected_unique_id=None,
                selected=False,
                can_manage_intent=False,
            )
            self._inventory_update_guidance_label.setText(message)
            self._inventory_update_guidance_label.setToolTip(message)
            self._refresh_inventory_sandbox_sync_action_state()
            return

        mod_name = name_item.text().strip() or "Selected mod"
        selected_unique_id = unique_id_item.text().strip() if unique_id_item is not None else ""
        status_text = status_item.text().strip() if status_item is not None else ""
        status_data = name_item.data(_ROLE_MOD_UPDATE_STATUS)
        status = status_data if isinstance(status_data, ModUpdateStatus) else None
        is_actionable = name_item.data(_ROLE_UPDATE_ACTIONABLE) is True
        blocked_reason = name_item.data(_ROLE_UPDATE_BLOCK_REASON)
        overlay_intent = self._resolve_inventory_update_source_intent(selected_unique_id)
        has_blocked_state = bool(
            status is not None or (isinstance(blocked_reason, str) and blocked_reason.strip())
        )
        can_manage_intent = bool(
            selected_unique_id
            and not is_actionable
            and has_blocked_state
            and status_text != "not_checked"
        )

        if status is None and status_text == "not_checked":
            message = (
                f"{mod_name}: run Check updates to evaluate update actionability. "
                "Open remote page stays disabled until an actionable row is selected."
            )
            self._set_inventory_blocked_detail_text(None)
            self._set_open_remote_page_state(
                enabled=False,
                tooltip="Run Check updates and select an actionable row first.",
            )
        elif is_actionable:
            message = (
                f"{mod_name}: update available. "
                "Next step: use Open remote page for this selected row."
            )
            self._set_inventory_blocked_detail_text(None)
            self._set_open_remote_page_state(
                enabled=True,
                tooltip=f"Open remote page for selected mod: {mod_name}.",
            )
        elif overlay_intent is not None:
            message, detail_text, tooltip = _inventory_guidance_for_update_source_intent(
                mod_name=mod_name,
                intent_state=overlay_intent.intent_state,
                manual_provider=overlay_intent.manual_provider,
            )
            self._set_inventory_blocked_detail_text(detail_text)
            self._set_open_remote_page_state(
                enabled=False,
                tooltip=tooltip,
            )
        elif isinstance(blocked_reason, str) and blocked_reason.strip():
            message = (
                f"{mod_name}: {blocked_reason.strip()} "
                "Open remote page is unavailable for this row."
            )
            self._set_inventory_blocked_detail_text(
                _diagnostics_text_for_update_source_code(
                    status.update_source_diagnostic if status is not None else None
                )
            )
            self._set_open_remote_page_state(
                enabled=False,
                tooltip=f"Remote-page action unavailable: {blocked_reason.strip()}",
            )
        else:
            message = f"{mod_name}: no update action is currently available."
            self._set_inventory_blocked_detail_text(None)
            self._set_open_remote_page_state(
                enabled=False,
                tooltip="Remote-page action is unavailable for the selected row.",
            )

        self._refresh_inventory_source_intent_action_state(
            selected_unique_id=selected_unique_id,
            selected=True,
            can_manage_intent=can_manage_intent,
        )
        self._inventory_update_guidance_label.setText(message)
        self._inventory_update_guidance_label.setToolTip(message)
        self._refresh_inventory_sandbox_sync_action_state()

    def _resolve_inventory_update_source_intent(self, unique_id: str):
        if not unique_id.strip():
            return None
        try:
            return self._shell_service.get_update_source_intent(unique_id)
        except AppShellError:
            return None

    def _set_inventory_blocked_detail_text(self, text: str | None) -> None:
        has_text = bool(text and text.strip())
        blocked_text = text.strip() if has_text and text is not None else ""
        self._inventory_blocked_detail_label.setText(blocked_text)
        self._inventory_blocked_detail_label.setToolTip(blocked_text)
        self._inventory_blocked_detail_label.setVisible(has_text)

    def _set_open_remote_page_state(self, *, enabled: bool, tooltip: str) -> None:
        self._open_remote_page_button.setEnabled(enabled)
        self._open_remote_page_button.setToolTip(tooltip)

    def _refresh_inventory_source_intent_action_state(
        self,
        *,
        selected_unique_id: str | None,
        selected: bool,
        can_manage_intent: bool,
    ) -> None:
        self._inventory_source_intent_actions_widget.setVisible(selected)
        self._mark_local_private_button.setEnabled(can_manage_intent)
        self._disable_tracking_button.setEnabled(can_manage_intent)
        self._manual_source_intent_button.setEnabled(can_manage_intent)
        has_saved_intent = bool(
            selected_unique_id and self._resolve_inventory_update_source_intent(selected_unique_id) is not None
        )
        self._clear_source_intent_button.setEnabled(can_manage_intent and has_saved_intent)

    def _selected_inventory_row_unique_id(self) -> str | None:
        row = self._mods_table.currentRow()
        if row < 0 or self._mods_table.isRowHidden(row) or not self._mods_table.selectedItems():
            return None
        unique_id_item = self._mods_table.item(row, 1)
        if unique_id_item is None:
            return None
        unique_id = unique_id_item.text().strip()
        return unique_id or None

    def _selected_inventory_source_intent_context(self) -> tuple[str, str] | None:
        row = self._mods_table.currentRow()
        if row < 0 or self._mods_table.isRowHidden(row) or not self._mods_table.selectedItems():
            return None
        name_item = self._mods_table.item(row, 0)
        unique_id_item = self._mods_table.item(row, 1)
        status_item = self._mods_table.item(row, 4)
        if name_item is None or unique_id_item is None:
            return None
        unique_id = unique_id_item.text().strip()
        if not unique_id:
            return None
        status_text = status_item.text().strip() if status_item is not None else ""
        status_data = name_item.data(_ROLE_MOD_UPDATE_STATUS)
        status = status_data if isinstance(status_data, ModUpdateStatus) else None
        is_actionable = name_item.data(_ROLE_UPDATE_ACTIONABLE) is True
        blocked_reason = name_item.data(_ROLE_UPDATE_BLOCK_REASON)
        has_blocked_state = bool(
            status is not None or (isinstance(blocked_reason, str) and blocked_reason.strip())
        )
        if is_actionable or status_text == "not_checked" or not has_blocked_state:
            return None
        mod_name = name_item.text().strip() or "Selected mod"
        return unique_id, mod_name

    def _selected_inventory_mod_folder_paths(self) -> tuple[str, ...]:
        selection_model = self._mods_table.selectionModel()
        if selection_model is None:
            return tuple()

        selected_rows = sorted(
            selection_model.selectedRows(0),
            key=lambda index: index.row(),
        )
        folder_paths: list[str] = []
        seen: set[str] = set()
        for model_index in selected_rows:
            row = model_index.row()
            if row < 0 or self._mods_table.isRowHidden(row):
                continue
            name_item = self._mods_table.item(row, 0)
            if name_item is None:
                continue
            folder_path = name_item.data(_ROLE_MOD_FOLDER_PATH)
            if not isinstance(folder_path, str) or not folder_path.strip():
                continue
            normalized = folder_path.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            folder_paths.append(folder_path)
        return tuple(folder_paths)

    def _refresh_inventory_sandbox_sync_action_state(self, *_: object) -> None:
        selected_mod_folder_paths = self._selected_inventory_mod_folder_paths()
        has_selection = bool(selected_mod_folder_paths)
        self._inventory_sandbox_sync_actions_widget.setVisible(has_selection)
        if not has_selection:
            self._sync_selected_to_sandbox_button.setEnabled(False)
            self._sync_selected_to_sandbox_button.setToolTip(
                "Select one or more installed real-mod rows to sync to sandbox."
            )
            self._promote_selected_to_real_button.setEnabled(False)
            self._promote_selected_to_real_button.setToolTip(
                "Select one or more installed sandbox-mod rows to promote to the configured real Mods path."
            )
            return

        if self._active_operation_name is not None:
            self._sync_selected_to_sandbox_button.setEnabled(False)
            self._sync_selected_to_sandbox_button.setToolTip(
                "Wait for the active operation to finish before syncing to sandbox."
            )
            self._promote_selected_to_real_button.setEnabled(False)
            self._promote_selected_to_real_button.setToolTip(
                "Wait for the active operation to finish before promoting to the configured real Mods path."
            )
            return

        if self._current_scan_target() == SCAN_TARGET_CONFIGURED_REAL_MODS:
            readiness = self._shell_service.get_sandbox_mods_sync_readiness(
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                selected_mod_folder_paths_text=selected_mod_folder_paths,
                existing_config=self._config,
            )
            self._sync_selected_to_sandbox_button.setEnabled(readiness.ready)
            self._sync_selected_to_sandbox_button.setToolTip(readiness.message)
            self._promote_selected_to_real_button.setEnabled(False)
            self._promote_selected_to_real_button.setToolTip(
                "Promote selected to real Mods only works while scanning sandbox Mods."
            )
            return

        if self._current_scan_target() != SCAN_TARGET_SANDBOX_MODS:
            self._sync_selected_to_sandbox_button.setEnabled(False)
            self._sync_selected_to_sandbox_button.setToolTip(
                "Sync selected to sandbox only works while scanning the configured real Mods path."
            )
            self._promote_selected_to_real_button.setEnabled(False)
            self._promote_selected_to_real_button.setToolTip(
                "Promote selected to real Mods only works while scanning sandbox Mods."
            )
            return

        self._sync_selected_to_sandbox_button.setEnabled(False)
        self._sync_selected_to_sandbox_button.setToolTip(
            "Sync selected to sandbox only works while scanning the configured real Mods path."
        )
        promotion_readiness = self._shell_service.get_sandbox_mods_promotion_readiness(
            configured_mods_path_text=self._mods_path_input.text(),
            sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
            real_archive_path_text=self._real_archive_path_input.text(),
            selected_mod_folder_paths_text=selected_mod_folder_paths,
            existing_config=self._config,
        )
        self._promote_selected_to_real_button.setEnabled(promotion_readiness.ready)
        self._promote_selected_to_real_button.setToolTip(promotion_readiness.message)

    def _set_selected_mod_update_source_intent(self, intent_state: str) -> None:
        selected_context = self._selected_inventory_source_intent_context()
        if selected_context is None:
            self._set_status("Select a blocked installed mod row to manage saved source intent.")
            return
        selected_unique_id, _ = selected_context
        try:
            self._shell_service.set_update_source_intent(selected_unique_id, intent_state)
        except AppShellError as exc:
            self._set_status(str(exc))
            return
        self._refresh_selected_mod_update_guidance()
        self._set_status(f"Saved update-source intent for {selected_unique_id}: {intent_state}.")

    def _on_mark_selected_mod_local_private(self) -> None:
        self._set_selected_mod_update_source_intent("local_private_mod")

    def _on_disable_selected_mod_tracking(self) -> None:
        self._set_selected_mod_update_source_intent("no_tracking")

    def _prompt_selected_mod_manual_source_intent(
        self,
        *,
        mod_name: str,
        unique_id: str,
        existing_intent: object | None,
    ) -> tuple[str, str, str | None] | None:
        initial_provider = None
        initial_source_key = None
        initial_page_url = None
        if existing_intent is not None:
            initial_provider = getattr(existing_intent, "manual_provider", None)
            initial_source_key = getattr(existing_intent, "manual_source_key", None)
            initial_page_url = getattr(existing_intent, "manual_source_page_url", None)
        return _prompt_manual_source_association(
            self,
            mod_name=mod_name,
            unique_id=unique_id,
            initial_provider=initial_provider,
            initial_source_key=initial_source_key,
            initial_page_url=initial_page_url,
        )

    def _on_set_selected_mod_manual_source_intent(self) -> None:
        selected_context = self._selected_inventory_source_intent_context()
        if selected_context is None:
            self._set_status("Select a blocked installed mod row to manage saved source intent.")
            return
        selected_unique_id, mod_name = selected_context
        existing_intent = self._resolve_inventory_update_source_intent(selected_unique_id)
        association = self._prompt_selected_mod_manual_source_intent(
            mod_name=mod_name,
            unique_id=selected_unique_id,
            existing_intent=existing_intent,
        )
        if association is None:
            return
        provider, source_key, page_url = association
        provider = provider.strip()
        source_key = source_key.strip()
        normalized_page_url = page_url.strip() if isinstance(page_url, str) else ""
        if not provider or not source_key:
            self._set_status("Manual source association requires provider and source key.")
            return
        try:
            self._shell_service.set_update_source_intent(
                selected_unique_id,
                "manual_source_association",
                manual_provider=provider,
                manual_source_key=source_key,
                manual_source_page_url=normalized_page_url or None,
            )
        except AppShellError as exc:
            self._set_status(str(exc))
            return
        self._refresh_selected_mod_update_guidance()
        self._set_status(
            f"Saved manual source association for {selected_unique_id} (provider: {provider})."
        )

    def _on_clear_selected_mod_source_intent(self) -> None:
        selected_context = self._selected_inventory_source_intent_context()
        if selected_context is None:
            self._set_status("Select a blocked installed mod row to manage saved source intent.")
            return
        selected_unique_id, _ = selected_context
        try:
            self._shell_service.clear_update_source_intent(selected_unique_id)
        except AppShellError as exc:
            self._set_status(str(exc))
            return
        self._refresh_selected_mod_update_guidance()
        self._set_status(f"Cleared saved update-source intent for {selected_unique_id}.")

    def _on_sync_selected_mods_to_sandbox(self) -> None:
        selected_mod_folder_paths = self._selected_inventory_mod_folder_paths()
        if not selected_mod_folder_paths:
            message = "Select at least one installed mod row to sync to sandbox."
            self._set_status(message)
            return

        if self._current_scan_target() != SCAN_TARGET_CONFIGURED_REAL_MODS:
            message = (
                "Sync selected to sandbox only works while scanning the configured real Mods path."
            )
            self._set_status(message)
            return

        readiness = self._shell_service.get_sandbox_mods_sync_readiness(
            configured_mods_path_text=self._mods_path_input.text(),
            sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
            selected_mod_folder_paths_text=selected_mod_folder_paths,
            existing_config=self._config,
        )
        if not readiness.ready:
            self._set_status(readiness.message)
            return

        selected_count = len(selected_mod_folder_paths)
        self._run_background_operation(
            operation_name="Sandbox sync",
            running_label="Sandbox sync",
            started_status=(
                f"Syncing {selected_count} selected mod(s) from real Mods to sandbox..."
            ),
            error_title="Sandbox sync failed",
            task_fn=lambda _paths=selected_mod_folder_paths: self._shell_service.sync_installed_mods_to_sandbox(
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                selected_mod_folder_paths_text=_paths,
                existing_config=self._config,
            ),
            on_success=self._on_sync_selected_mods_to_sandbox_completed,
        )

    def _on_sync_selected_mods_to_sandbox_completed(
        self,
        result: SandboxModsSyncResult,
    ) -> None:
        self._set_details_text(_build_sandbox_mods_sync_result_text(result))
        self._set_status(
            f"Sandbox sync complete: {len(result.synced_target_paths)} mod(s) copied."
        )

    def _on_promote_selected_mods_to_real(self) -> None:
        selected_mod_folder_paths = self._selected_inventory_mod_folder_paths()
        if not selected_mod_folder_paths:
            message = "Select at least one installed sandbox mod row to promote."
            self._set_status(message)
            return

        if self._current_scan_target() != SCAN_TARGET_SANDBOX_MODS:
            message = "Promote selected to real Mods only works while scanning sandbox Mods."
            self._set_status(message)
            return

        try:
            preview = self._shell_service.build_sandbox_mods_promotion_preview(
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                selected_mod_folder_paths_text=selected_mod_folder_paths,
                existing_config=self._config,
            )
        except AppShellError as exc:
            self._set_status(str(exc))
            return

        if not preview.review.allowed:
            self._set_status(preview.review.message)
            return

        yes = QMessageBox.question(
            self,
            "Review sandbox promotion to REAL Mods",
            _build_sandbox_mods_promotion_confirmation_message(preview),
        )
        if yes != QMessageBox.StandardButton.Yes:
            self._set_status("Sandbox promotion cancelled.")
            return

        selected_count = len(selected_mod_folder_paths)
        history_before = self._install_operation_history
        self._run_background_operation(
            operation_name="Sandbox promotion",
            running_label="Sandbox promotion",
            started_status=(
                f"Promoting {selected_count} selected mod(s) from sandbox Mods to REAL Mods..."
            ),
            error_title="Sandbox promotion failed",
            task_fn=lambda _preview=preview: self._shell_service.execute_sandbox_mods_promotion_preview(
                _preview
            ),
            on_success=lambda result, _history_before=history_before: self._on_promote_selected_mods_to_real_completed(
                result,
                history_before=_history_before,
            ),
        )

    def _on_promote_selected_mods_to_real_completed(
        self,
        result: SandboxModsPromotionResult,
        *,
        history_before: tuple[InstallOperationRecord, ...],
    ) -> None:
        self._refresh_install_operation_selector()
        self._select_new_install_operation_for_recovery(history_before)
        self._set_details_text(_build_sandbox_mods_promotion_result_text(result))
        replaced_count = len(result.replaced_target_paths)
        if replaced_count > 0:
            self._set_status(
                "Sandbox promotion complete: "
                f"{len(result.promoted_target_paths)} mod(s) promoted, "
                f"{replaced_count} live target(s) archived and replaced."
            )
            return

        self._set_status(
            f"Sandbox promotion complete: {len(result.promoted_target_paths)} mod(s) promoted into REAL Mods."
        )

    def _apply_discovery_filter(self, *_: object) -> None:
        filter_text = self._discovery_filter_input.text()
        visible_count = 0
        for row in range(self._discovery_table.rowCount()):
            row_values = []
            for col in range(self._discovery_table.columnCount()):
                item = self._discovery_table.item(row, col)
                row_values.append(item.text() if item is not None else "")
            matches = row_matches_filter(row_values, filter_text)
            self._discovery_table.setRowHidden(row, not matches)
            if matches:
                visible_count += 1
        self._set_filter_stats(
            self._discovery_filter_stats_label,
            shown_count=visible_count,
            total_count=self._discovery_table.rowCount(),
        )

    def _apply_archive_filter(self, *_: object) -> None:
        filter_text = self._archive_filter_input.text()
        visible_count = 0
        for row in range(self._archive_table.rowCount()):
            row_values = []
            for col in range(self._archive_table.columnCount()):
                item = self._archive_table.item(row, col)
                row_values.append(item.text() if item is not None else "")
            matches = row_matches_filter(row_values, filter_text)
            self._archive_table.setRowHidden(row, not matches)
            if matches:
                visible_count += 1
        self._set_filter_stats(
            self._archive_filter_stats_label,
            shown_count=visible_count,
            total_count=self._archive_table.rowCount(),
        )

    def _selected_archive_entry(self) -> ArchivedModEntry | None:
        row = self._archive_table.currentRow()
        if row < 0:
            return None
        row_item = self._archive_table.item(row, 0)
        if row_item is None:
            return None
        index = row_item.data(_ROLE_ARCHIVE_INDEX)
        if not isinstance(index, int):
            return None
        if index < 0 or index >= len(self._archived_entries):
            return None
        return self._archived_entries[index]

    def _current_inventory_or_empty(self) -> ModsInventory:
        if self._current_inventory is not None:
            return self._current_inventory

        return ModsInventory(
            mods=tuple(),
            parse_warnings=tuple(),
            duplicate_unique_ids=tuple(),
            missing_required_dependencies=tuple(),
            scan_entry_findings=tuple(),
            ignored_entries=tuple(),
        )

    def _refresh_scan_context_preview(self, *_: object) -> None:
        target = self._current_scan_target()
        if target == SCAN_TARGET_CONFIGURED_REAL_MODS:
            path_text = self._mods_path_input.text().strip() or "<unset>"
            target_label = "REAL Mods"
        else:
            path_text = self._sandbox_mods_path_input.text().strip() or "<unset>"
            target_label = "Sandbox Mods"
        context_text = f"{target_label} selected"
        if path_text == "<unset>":
            context_text = f"{context_text} (path unset)"
        self._scan_context_label.setText(context_text)
        self._scan_context_label.setToolTip(path_text)

    def _refresh_nexus_status(self, *, validated: bool) -> None:
        status = self._shell_service.get_nexus_integration_status(
            nexus_api_key_text=self._nexus_api_key_input.text(),
            existing_config=self._config,
            validate_connection=validated,
        )
        self._nexus_status_label.setText(_nexus_status_label(status.state, status.masked_key))

    def _refresh_install_destination_preview(self) -> None:
        target = self._current_install_target()
        if target == INSTALL_TARGET_CONFIGURED_REAL_MODS:
            self._install_archive_label.setText("Archive path for real Game Mods destination")
            path_text = self._mods_path_input.text().strip() or "<unset>"
            context_text = "REAL game Mods destination selected (confirmation required)"
            if path_text == "<unset>":
                context_text = f"{context_text} (path unset)"
            self._install_context_label.setText(context_text)
            self._install_context_label.setToolTip(path_text)
            if not self._real_archive_path_input.text().strip() and self._mods_path_input.text().strip():
                self._real_archive_path_input.setText(
                    str(Path(self._mods_path_input.text().strip()).parent / ".sdvmm-real-archive")
                )
            self._refresh_install_safety_panel()
            return

        self._install_archive_label.setText("Archive path for sandbox destination")
        path_text = self._sandbox_mods_path_input.text().strip() or "<unset>"
        context_text = "Sandbox Mods destination selected (recommended/test path)"
        if path_text == "<unset>":
            context_text = f"{context_text} (path unset)"
        self._install_context_label.setText(context_text)
        self._install_context_label.setToolTip(path_text)
        if (
            not self._sandbox_archive_path_input.text().strip()
            and self._sandbox_mods_path_input.text().strip()
        ):
            self._sandbox_archive_path_input.setText(
                str(Path(self._sandbox_mods_path_input.text().strip()).parent / ".sdvmm-sandbox-archive")
            )
        self._refresh_install_safety_panel()

    def _refresh_install_safety_panel(self, *_: object) -> None:
        panel_label = getattr(self, "_install_safety_panel_label", None)
        if panel_label is None:
            return

        target = self._current_install_target()
        if target == INSTALL_TARGET_CONFIGURED_REAL_MODS:
            destination_path = self._mods_path_input.text().strip() or "<unset>"
            archive_path = self._real_archive_path_input.text().strip() or "<unset>"
            panel_label.setText(
                "REAL game Mods destination selected (live changes warning).\n"
                "Destination Mods path: "
                f"{destination_path}\n"
                "Archive path: "
                f"{archive_path}\n"
                "Explicit confirmation is required before execution.\n"
                "Inspect Recovery after execution if rollback is needed."
            )
            panel_label.setToolTip(
                f"Destination Mods path: {destination_path}\nArchive path: {archive_path}"
            )
            return

        destination_path = self._sandbox_mods_path_input.text().strip() or "<unset>"
        archive_path = self._sandbox_archive_path_input.text().strip() or "<unset>"
        panel_label.setText(
            "Sandbox destination selected (recommended/test path).\n"
            "Destination Mods path: "
            f"{destination_path}\n"
            "Archive path: "
            f"{archive_path}\n"
            "Use this path to validate changes before live Mods installs."
        )
        panel_label.setToolTip(
            f"Destination Mods path: {destination_path}\nArchive path: {archive_path}"
        )

    def _current_scan_target(self) -> str:
        return str(self._scan_target_combo.currentData())

    def _current_install_target(self) -> str:
        return str(self._install_target_combo.currentData())

    def _set_current_scan_target(self, target: str) -> None:
        index = self._scan_target_combo.findData(target)
        if index >= 0:
            self._scan_target_combo.setCurrentIndex(index)

    def _set_current_install_target(self, target: str) -> None:
        index = self._install_target_combo.findData(target)
        if index >= 0:
            self._install_target_combo.setCurrentIndex(index)

    def _refresh_intake_selector(self, *_: object) -> None:
        selected_before = self._selected_intake_index()
        self._intake_result_combo.clear()

        if not self._detected_intakes:
            self._intake_result_combo.addItem("<no detected packages>", -1)
            self._intake_result_combo.setEnabled(False)
            self._refresh_stage_package_action_state()
            self._set_filter_stats(
                self._intake_filter_stats_label,
                shown_count=0,
                total_count=0,
            )
            return

        filter_text = self._intake_filter_input.text()
        self._intake_result_combo.setEnabled(True)
        visible_count = 0
        for idx, intake in enumerate(self._detected_intakes):
            correlation = self._intake_correlations[idx] if idx < len(self._intake_correlations) else None
            actionable = (
                "actionable"
                if self._shell_service.is_actionable_intake_result(intake)
                else "non-actionable"
            )
            flow_tag = ""
            if correlation is not None and correlation.matched_guided_update_unique_ids:
                flow_tag = ", guided-update-match"
            elif correlation is not None and correlation.matched_update_available_unique_ids:
                flow_tag = ", update-available-match"
            label = (
                f"{intake.package_path.name} "
                f"[{intake.classification}, {actionable}{flow_tag}]"
            )
            search_values = (
                intake.package_path.name,
                intake.classification,
                " ".join(mod.name for mod in intake.mods),
                " ".join(mod.unique_id for mod in intake.mods),
                " ".join(mod.version for mod in intake.mods),
            )
            if not row_matches_filter(search_values, filter_text):
                continue
            self._intake_result_combo.addItem(label, idx)
            visible_count += 1

        if visible_count == 0:
            self._intake_result_combo.clear()
            self._intake_result_combo.addItem("<no detected packages match filter>", -1)
            self._intake_result_combo.setEnabled(False)
            self._refresh_stage_package_action_state()
            self._set_filter_stats(
                self._intake_filter_stats_label,
                shown_count=0,
                total_count=len(self._detected_intakes),
            )
            return

        selected_after = self._intake_result_combo.findData(selected_before)
        if selected_after >= 0:
            self._intake_result_combo.setCurrentIndex(selected_after)
        else:
            self._intake_result_combo.setCurrentIndex(self._intake_result_combo.count() - 1)
        self._refresh_stage_package_action_state()
        self._set_filter_stats(
            self._intake_filter_stats_label,
            shown_count=visible_count,
            total_count=len(self._detected_intakes),
        )

    def _selected_intake_index(self) -> int:
        value = self._intake_result_combo.currentData()
        if isinstance(value, int):
            return value
        return -1

    def _selected_intake_correlation(self) -> IntakeUpdateCorrelation | None:
        idx = self._selected_intake_index()
        if idx < 0 or idx >= len(self._intake_correlations):
            return None
        return self._intake_correlations[idx]

    def _selected_package_inspection_index(self) -> int:
        value = self._package_inspection_selector.currentData()
        if isinstance(value, int):
            return value
        return -1

    def _package_inspection_entry_at(self, index: int) -> PackageInspectionBatchEntry | None:
        if self._package_inspection_batch_result is None:
            return None
        if index < 0 or index >= len(self._package_inspection_batch_result.entries):
            return None
        return self._package_inspection_batch_result.entries[index]

    def _selected_package_inspection_entry(self) -> PackageInspectionBatchEntry | None:
        return self._package_inspection_entry_at(self._selected_package_inspection_index())

    def _has_stageable_inspected_package(self) -> bool:
        entry = self._selected_package_inspection_entry()
        return entry is not None and entry.inspection is not None

    def _refresh_stage_package_action_state(self) -> None:
        self._plan_selected_intake_button.setEnabled(
            self._selected_intake_index() >= 0 or self._has_stageable_inspected_package()
        )
        update_like_selection = self._selected_intake_supports_update_action()
        self._stage_update_intake_button.setVisible(update_like_selection)
        self._stage_update_intake_button.setEnabled(update_like_selection)
        if update_like_selection:
            self._stage_update_intake_button.setToolTip(
                "Stage this detected package as an update and preselect archive-aware replace."
            )
            return
        self._stage_update_intake_button.setToolTip(
            "Select a detected package that clearly replaces an installed mod to stage it as an update."
        )

    def _refresh_staged_package_preview(self) -> None:
        package_path = self._zip_path_input.text().strip()
        if not package_path:
            self._staged_package_label.setText("No package staged for planning.")
            self._staged_package_label.setToolTip("")
            return
        self._staged_package_label.setText(package_path)
        self._staged_package_label.setToolTip(package_path)

    def _stage_package_for_plan_install(
        self,
        package_path: str,
        *,
        status_message: str,
        apply_update_intent: bool = False,
    ) -> None:
        self._set_selected_zip_package_paths((Path(package_path),), current_path=Path(package_path))
        if apply_update_intent:
            self._apply_auto_overwrite_intent_for_package(package_path)
        else:
            self._sync_auto_overwrite_intent_with_staged_package(package_path)
        self._refresh_staged_package_preview()
        self._refresh_stage_package_action_state()
        self._set_intake_output_text(status_message)
        self._context_tabs.setCurrentWidget(self._plan_install_tab)
        self._set_status(status_message)

    def _on_overwrite_checkbox_toggled(self, _: bool) -> None:
        if self._syncing_auto_overwrite_checkbox:
            return
        self._auto_overwrite_package_path = None

    def _apply_auto_overwrite_intent_for_package(self, package_path: str) -> None:
        self._auto_overwrite_package_path = self._normalized_package_path_text(package_path)
        self._set_overwrite_checkbox_checked(True)

    def _sync_auto_overwrite_intent_with_staged_package(self, package_path: str) -> None:
        if self._auto_overwrite_package_path is None:
            return
        normalized_path = self._normalized_package_path_text(package_path)
        if normalized_path and normalized_path == self._auto_overwrite_package_path:
            return
        self._auto_overwrite_package_path = None
        self._set_overwrite_checkbox_checked(False)

    def _set_overwrite_checkbox_checked(self, checked: bool) -> None:
        if self._overwrite_checkbox.isChecked() == checked:
            return
        self._syncing_auto_overwrite_checkbox = True
        try:
            self._overwrite_checkbox.setChecked(checked)
        finally:
            self._syncing_auto_overwrite_checkbox = False

    @staticmethod
    def _normalized_package_path_text(package_path: str) -> str:
        return str(Path(package_path).expanduser()) if package_path.strip() else ""

    def _selected_discovery_correlation(self) -> DiscoveryContextCorrelation | None:
        row = self._discovery_table.currentRow()
        if row < 0:
            return None
        row_item = self._discovery_table.item(row, 0)
        if row_item is None:
            return None
        result_index = row_item.data(_ROLE_DISCOVERY_INDEX)
        if not isinstance(result_index, int):
            return None
        if result_index < 0 or result_index >= len(self._discovery_correlations):
            return None
        return self._discovery_correlations[result_index]

    def _recompute_intake_correlations(self) -> None:
        self._intake_correlations = self._shell_service.correlate_intakes_with_updates(
            intakes=self._detected_intakes,
            update_report=self._current_update_report,
            guided_update_unique_ids=self._guided_update_unique_ids,
        )
        self._refresh_intake_selector()
        self._sync_guided_update_intake_handoff(
            allow_auto_select=True,
            update_output=True,
            update_status=False,
        )

    def _refresh_discovery_correlations(self) -> None:
        if self._current_discovery_result is None:
            self._discovery_correlations = tuple()
            self._discovery_table.setRowCount(0)
            return

        self._discovery_correlations = self._shell_service.correlate_discovery_results(
            discovery_result=self._current_discovery_result,
            inventory=self._current_inventory,
            update_report=self._current_update_report,
        )
        self._render_discovery_results(self._current_discovery_result, self._discovery_correlations)

    @staticmethod
    def _add_guided_unique_id(existing: tuple[str, ...], new_unique_id: str) -> tuple[str, ...]:
        items = {canonicalize_unique_id(value): value for value in existing}
        items[canonicalize_unique_id(new_unique_id)] = new_unique_id
        return tuple(sorted(items.values(), key=str.casefold))

    def _sync_guided_update_intake_handoff(
        self,
        *,
        allow_auto_select: bool,
        update_output: bool,
        update_status: bool,
    ) -> None:
        actionable_matches = self._guided_actionable_intake_indexes()
        if not actionable_matches:
            return

        message: str
        if len(actionable_matches) == 1:
            match_index = actionable_matches[0]
            combo_index = self._intake_result_combo.findData(match_index)
            if combo_index >= 0:
                if allow_auto_select:
                    self._intake_result_combo.setCurrentIndex(combo_index)
                package_name = self._detected_intakes[match_index].package_path.name
                message = f"Matched update package ready to stage: {package_name}"
            else:
                message = (
                    "Matched update package found in detected packages, but the current filter hides it. "
                    "Clear the filter or choose it manually in Packages & Intake."
                )
        else:
            message = (
                "Multiple matched update packages are ready. Choose which package to stage in Packages & Intake."
            )

        if update_output:
            self._set_intake_output_text(message)
        if update_status:
            self._set_status(message)

    def _guided_actionable_intake_indexes(self) -> list[int]:
        return [
            index
            for index, correlation in enumerate(self._intake_correlations)
            if correlation.actionable and correlation.matched_guided_update_unique_ids
        ]

    def _refresh_detected_intakes_for_current_inventory(self) -> None:
        if not self._detected_intakes:
            self._intake_correlations = tuple()
            self._refresh_intake_selector()
            return

        self._detected_intakes = self._shell_service.refresh_detected_intakes_against_inventory(
            intakes=self._detected_intakes,
            inventory=self._current_inventory,
        )
        self._recompute_intake_correlations()

    def _selected_intake_supports_update_action(self) -> bool:
        correlation = self._selected_intake_correlation()
        if correlation is None or not correlation.actionable:
            return False
        return bool(
            correlation.matched_guided_update_unique_ids
            or correlation.matched_update_available_unique_ids
            or correlation.intake.classification == "update_replace_candidate"
        )

    @staticmethod
    def _scan_target_label(target: str) -> str:
        if target == SCAN_TARGET_CONFIGURED_REAL_MODS:
            return "real Mods directory"
        return "sandbox Mods directory"

    def _apply_guidance_compact_mode(self, *, details_visible: bool) -> None:
        self._guidance_group.setProperty("detailsVisible", details_visible)
        self._refresh_responsive_panel_bounds()

    def _refresh_responsive_panel_bounds(self) -> None:
        window_height = max(self.height(), self.minimumHeight())

        context_cap = max(108, min(144, int(window_height * 0.19)))
        inventory_controls_cap = max(132, min(192, int(window_height * 0.25)))
        flow_hint_cap = max(24, min(44, int(window_height * 0.06)))
        intake_result_cap = max(92, min(156, int(window_height * 0.20)))
        status_strip_cap = max(56, min(78, int(window_height * 0.10)))
        details_cap = max(104, min(188, int(window_height * 0.25)))
        guidance_closed_cap = max(118, min(162, int(window_height * 0.21)))
        guidance_open_cap = max(182, min(252, int(window_height * 0.33)))

        if hasattr(self, "_context_group"):
            self._context_group.setMaximumHeight(context_cap)

        if hasattr(self, "_status_strip_group"):
            self._status_strip_group.setMaximumHeight(status_strip_cap)

        if hasattr(self, "_inventory_controls_tabs"):
            self._inventory_controls_tabs.setMaximumHeight(inventory_controls_cap)

        if hasattr(self, "_inventory_flow_hint_label"):
            self._inventory_flow_hint_label.setMaximumHeight(flow_hint_cap)

        if hasattr(self, "_package_inspection_result_box"):
            self._package_inspection_result_box.setMaximumHeight(intake_result_cap)

        if hasattr(self, "_setup_scroll"):
            self._setup_scroll.setMaximumHeight(16777215)

        if hasattr(self, "_findings_box"):
            self._findings_box.setMaximumHeight(details_cap)

        if hasattr(self, "_details_group"):
            secondary_cap = (
                guidance_open_cap if self._details_group.isVisible() else guidance_closed_cap
            )
            if hasattr(self, "_secondary_group"):
                self._secondary_group.setMaximumHeight(secondary_cap)

    @staticmethod
    def _set_filter_stats(label: QLabel, *, shown_count: int, total_count: int) -> None:
        label.setText(f"{shown_count}/{total_count} shown")

    @staticmethod
    def _merge_detected_intakes(
        existing: tuple[DownloadsIntakeResult, ...],
        incoming: tuple[DownloadsIntakeResult, ...],
    ) -> tuple[DownloadsIntakeResult, ...]:
        merged_by_path: dict[str, DownloadsIntakeResult] = {
            str(intake.package_path): intake for intake in existing
        }
        for intake in incoming:
            merged_by_path[str(intake.package_path)] = intake

        ordered: list[DownloadsIntakeResult] = []
        seen_paths: set[str] = set()
        for intake in existing:
            path_key = str(intake.package_path)
            if path_key in seen_paths:
                continue
            ordered.append(merged_by_path[path_key])
            seen_paths.add(path_key)
        for intake in incoming:
            path_key = str(intake.package_path)
            if path_key in seen_paths:
                continue
            ordered.append(merged_by_path[path_key])
            seen_paths.add(path_key)
        return tuple(ordered)


def _install_operation_selector_text(operation: InstallOperationRecord) -> str:
    destination_label = (
        "REAL Mods" if operation.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS else "Sandbox"
    )
    package_name = operation.package_path.name
    if operation.operation_id is None:
        return f"{package_name} | {operation.timestamp} | {destination_label} | legacy record"
    return f"{package_name} | {operation.timestamp} | {destination_label}"


def _build_install_operation_summary_text(operation: InstallOperationRecord) -> str:
    destination_label = (
        "REAL Mods" if operation.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS else "Sandbox"
    )
    return (
        f"Selected install: {operation.package_path.name}\n"
        f"Recorded at: {operation.timestamp}\n"
        f"Destination: {destination_label}"
    )


def _latest_recovery_outcome_summary(
    linked_history: tuple[RecoveryExecutionRecord, ...] | None,
) -> str:
    if not linked_history:
        return "Latest recovery outcome: none recorded yet."

    latest_record = max(linked_history, key=lambda record: record.timestamp)
    return (
        "Latest recovery outcome: "
        f"{latest_record.outcome_status} at {latest_record.timestamp} "
        f"(executed={latest_record.executed_entry_count})."
    )


def _update_status_actionability(status: ModUpdateStatus) -> tuple[bool, str]:
    if status.state == "update_available":
        return True, ""
    if status.state == "up_to_date":
        return False, "Up to date; no update action required."
    if status.state == "no_remote_link":
        return False, status.message or "No remote link is available for this mod."
    if status.state == "metadata_unavailable":
        return False, status.message or "Metadata unavailable for this mod."
    return False, status.message or f"State '{status.state}' is not actionable."


def _diagnostics_text_for_update_source_code(code: str | None) -> str | None:
    if code == LOCAL_PRIVATE_MOD:
        return "Update source diagnostics: local/private mod."
    if code == MISSING_UPDATE_KEY:
        return "Update source diagnostics: missing update key."
    if code == UNSUPPORTED_UPDATE_KEY_FORMAT:
        return "Update source diagnostics: unsupported update key format."
    if code == NO_PROVIDER_MAPPING:
        return "Update source diagnostics: no provider mapping."
    if code == REMOTE_METADATA_LOOKUP_FAILED:
        return "Update source diagnostics: remote metadata lookup failed."
    if code == METADATA_SOURCE_ISSUE:
        return "Update source diagnostics: metadata source issue."
    return None


def _inventory_guidance_for_update_source_intent(
    *,
    mod_name: str,
    intent_state: str,
    manual_provider: str | None,
) -> tuple[str, str, str]:
    if intent_state == "local_private_mod":
        return (
            f"{mod_name}: marked as local/private in saved update-source intent. "
            "Open remote page is unavailable for this row.",
            "Update source intent: local/private mod is recorded in app state.",
            "Remote-page action unavailable: mod is marked local/private in saved update-source intent.",
        )
    if intent_state == "no_tracking":
        return (
            f"{mod_name}: update tracking is intentionally disabled in saved update-source intent. "
            "Open remote page is unavailable for this row.",
            "Update source intent: no-tracking is recorded in app state.",
            "Remote-page action unavailable: update tracking is intentionally disabled in saved update-source intent.",
        )

    provider_text = f" (provider: {manual_provider})" if manual_provider else ""
    return (
        f"{mod_name}: manual source association is recorded in saved update-source intent. "
        "Open remote page is unavailable for this row.",
        f"Update source intent: manual source association is recorded in app state{provider_text}.",
        "Remote-page action unavailable: manual source association is recorded in saved update-source intent.",
    )


def _prompt_manual_source_association(
    parent: QWidget,
    *,
    mod_name: str,
    unique_id: str,
    initial_provider: str | None,
    initial_source_key: str | None,
    initial_page_url: str | None,
) -> tuple[str, str, str | None] | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("Manual source association")
    dialog.setModal(True)
    dialog_layout = QVBoxLayout(dialog)
    dialog_layout.setContentsMargins(12, 10, 12, 10)
    dialog_layout.setSpacing(8)

    intro_label = QLabel(
        f"Record a manual source association for {mod_name} ({unique_id})."
    )
    intro_label.setWordWrap(True)
    dialog_layout.addWidget(intro_label)

    form_layout = QGridLayout()
    form_layout.setHorizontalSpacing(8)
    form_layout.setVerticalSpacing(6)
    dialog_layout.addLayout(form_layout)

    provider_input = QComboBox()
    provider_input.setObjectName("inventory_manual_source_provider_input")
    provider_input.setEditable(True)
    for provider_name in ("nexus", "github", "moddrop", "smapi"):
        provider_input.addItem(provider_name)
    if initial_provider:
        existing_index = provider_input.findText(initial_provider)
        if existing_index >= 0:
            provider_input.setCurrentIndex(existing_index)
        else:
            provider_input.setEditText(initial_provider)

    source_key_input = QLineEdit(initial_source_key or "")
    source_key_input.setObjectName("inventory_manual_source_key_input")
    source_key_input.setPlaceholderText("Provider-specific source key")
    page_url_input = QLineEdit(initial_page_url or "")
    page_url_input.setObjectName("inventory_manual_source_page_url_input")
    page_url_input.setPlaceholderText("Optional page URL")

    form_layout.addWidget(QLabel("Provider"), 0, 0)
    form_layout.addWidget(provider_input, 0, 1)
    form_layout.addWidget(QLabel("Source key"), 1, 0)
    form_layout.addWidget(source_key_input, 1, 1)
    form_layout.addWidget(QLabel("Page URL"), 2, 0)
    form_layout.addWidget(page_url_input, 2, 1)

    validation_label = QLabel("")
    validation_label.setObjectName("inventory_manual_source_validation_label")
    validation_label.setWordWrap(True)
    validation_label.setVisible(False)
    _set_auxiliary_label_style(validation_label)
    dialog_layout.addWidget(validation_label)

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    dialog_layout.addWidget(buttons)

    def _validate_before_accept() -> None:
        provider_text = provider_input.currentText().strip()
        source_key_text = source_key_input.text().strip()
        if provider_text and source_key_text:
            validation_label.clear()
            validation_label.setVisible(False)
            dialog.accept()
            return
        validation_label.setText("Provider and source key are required.")
        validation_label.setVisible(True)

    save_button = buttons.button(QDialogButtonBox.StandardButton.Save)
    if save_button is not None:
        save_button.clicked.disconnect()
        save_button.clicked.connect(_validate_before_accept)

    if dialog.exec() != int(QDialog.DialogCode.Accepted):
        return None
    page_url_text = page_url_input.text().strip()
    return (
        provider_input.currentText().strip(),
        source_key_input.text().strip(),
        page_url_text or None,
    )


def _build_plan_review_summary_text(
    plan: SandboxInstallPlan,
    review: InstallExecutionReview,
) -> str:
    has_dependency_block = bool(plan.dependency_findings) or any(
        _contains_dependency_terms(warning)
        for warning in (
            *plan.plan_warnings,
            *[warning for entry in plan.entries for warning in entry.warnings],
        )
    )
    has_package_block = bool(plan.package_findings) or bool(plan.package_warnings)
    has_runnable_warnings = bool(
        plan.plan_warnings
        or plan.package_warnings
        or plan.package_findings
        or review.summary.review_warnings
        or any(entry.warnings for entry in plan.entries)
    )

    if not review.allowed:
        if has_dependency_block:
            return "Plan review: blocked by dependency issues."
        if has_package_block:
            return "Plan review: blocked by package issues."
        return "Plan review: blocked. Review plan details."

    if has_runnable_warnings:
        return "Plan review: runnable with warnings."
    return "Plan review: ready to install."


def _build_plan_review_explanation_text(
    plan: SandboxInstallPlan,
    review: InstallExecutionReview,
) -> str:
    dependency_warning = _first_dependency_warning_text(plan)
    package_issue = _first_package_issue_text(plan)
    runnable_warning = _first_runnable_warning_text(plan, review)

    if not review.allowed:
        if dependency_warning:
            return f"Dependency issue: {dependency_warning}"
        if package_issue:
            return f"Package issue: {package_issue}"
        return "Blocked: this plan contains non-runnable entries."

    if runnable_warning:
        return f"Warning: {runnable_warning}"
    return "Ready: no blocking issues detected."


def _build_plan_facts_text(
    plan: SandboxInstallPlan,
    review: InstallExecutionReview,
) -> str:
    summary = review.summary
    blocked_entry_count = _count_blocked_plan_entries(plan)
    return (
        f"Entries: {summary.total_entry_count}\n"
        f"Replace existing: {'yes' if summary.has_existing_targets_to_replace else 'no'}\n"
        f"Archive writes: {'yes' if summary.has_archive_writes else 'no'}\n"
        f"Approval required: {'yes' if review.requires_explicit_approval else 'no'}\n"
        f"Blocked entries: {blocked_entry_count}"
    )


def _count_blocked_plan_entries(plan: SandboxInstallPlan) -> int:
    return sum(
        1
        for entry in plan.entries
        if (not entry.can_install) or entry.action == "blocked"
    )


def _first_dependency_warning_text(plan: SandboxInstallPlan) -> str | None:
    for finding in plan.dependency_findings:
        message = str(getattr(finding, "message", "")).strip()
        if message:
            return message
    for warning in plan.plan_warnings:
        if _contains_dependency_terms(warning):
            return warning
    for entry in plan.entries:
        for warning in entry.warnings:
            if _contains_dependency_terms(warning):
                return warning
    return None


def _first_package_issue_text(plan: SandboxInstallPlan) -> str | None:
    for finding in plan.package_findings:
        message = str(getattr(finding, "message", "")).strip()
        if message:
            return message
    for warning in plan.package_warnings:
        warning_text = warning.strip()
        if warning_text:
            return warning_text
    return None


def _first_runnable_warning_text(
    plan: SandboxInstallPlan,
    review: InstallExecutionReview,
) -> str | None:
    warning_sources = (
        *plan.plan_warnings,
        *plan.package_warnings,
        *[warning for entry in plan.entries for warning in entry.warnings],
        *review.summary.review_warnings,
    )
    for warning in warning_sources:
        warning_text = warning.strip()
        if warning_text:
            return warning_text
    return None


def _contains_dependency_terms(text: str) -> bool:
    lowered = text.casefold()
    return "dependency" in lowered or "dependencies" in lowered


def _build_install_recovery_inspection_text(
    inspection: InstallRecoveryInspectionResult,
) -> str:
    operation = inspection.operation
    plan_summary = inspection.recovery_plan.summary
    review = inspection.recovery_review
    lines = [
        "Recovery readiness inspection",
        f"Install operation ID: {operation.operation_id or '<legacy>'}",
        f"Recorded at: {operation.timestamp}",
        f"Package: {operation.package_path}",
        f"Destination: {operation.destination_kind} -> {operation.destination_mods_path}",
        "",
        "Current recovery status",
        f"Review: {review.message}",
        (
            "Recoverable vs non-executable: "
            f"{plan_summary.recoverable_entry_count} recoverable / "
            f"{review.summary.non_executable_entry_count} non-executable now"
        ),
        f"Archive restoration involved: {'yes' if plan_summary.involves_archive_restore else 'no'}",
        f"Executable now: {review.summary.executable_entry_count}/{review.summary.total_entry_count}",
        "",
        "Linked prior recovery executions",
    ]
    if inspection.linked_recovery_history:
        lines.extend(
            _format_recovery_execution_record(record)
            for record in inspection.linked_recovery_history
        )
    else:
        lines.append("No linked recovery execution records.")
    if review.summary.warnings:
        lines.append("")
        lines.append("Warnings")
        lines.extend(f"- {warning}" for warning in review.summary.warnings)
    return "\n".join(lines)


def _build_install_recovery_confirmation_message(review: object) -> str:
    return (
        f"{review.message}\n\n"
        "Execute recovery now?\n"
        f"Executable now: {review.summary.executable_entry_count}/{review.summary.total_entry_count}\n"
        f"Non-executable now: {review.summary.non_executable_entry_count}\n"
        f"Archive restoration involved: {'yes' if review.summary.involves_archive_restore else 'no'}"
    )


def _build_install_recovery_execution_result_text(
    result: InstallRecoveryExecutionResult,
) -> str:
    lines = [
        "Recovery execution result",
        f"Outcome: completed",
        f"Executed actions: {result.executed_entry_count}",
        f"Destination: {result.destination_kind} -> {result.destination_mods_path}",
        f"Removed targets: {len(result.removed_target_paths)}",
        f"Restored targets: {len(result.restored_target_paths)}",
    ]
    if result.removed_target_paths:
        lines.append("Removed target paths")
        lines.extend(f"- {path}" for path in result.removed_target_paths)
    if result.restored_target_paths:
        lines.append("Restored target paths")
        lines.extend(f"- {path}" for path in result.restored_target_paths)
    return "\n".join(lines)


def _format_recovery_execution_record(record: RecoveryExecutionRecord) -> str:
    summary = (
        f"- {record.timestamp} | {record.outcome_status} | "
        f"executed={record.executed_entry_count} | "
        f"removed={len(record.removed_target_paths)} | "
        f"restored={len(record.restored_target_paths)}"
    )
    if record.failure_message:
        return f"{summary} | failure={record.failure_message}"
    return summary


def _build_sandbox_mods_sync_result_text(result: SandboxModsSyncResult) -> str:
    lines = [
        "Sandbox sync result",
        f"Direction: real Mods -> sandbox Mods",
        f"Configured real Mods path: {result.real_mods_path}",
        f"Sandbox Mods path: {result.sandbox_mods_path}",
        f"Copied targets: {len(result.synced_target_paths)}",
    ]
    if result.source_mod_paths:
        lines.append("Source mod folders")
        lines.extend(f"- {path}" for path in result.source_mod_paths)
    if result.synced_target_paths:
        lines.append("Sandbox target folders")
        lines.extend(f"- {path}" for path in result.synced_target_paths)
    lines.append("")
    lines.append("Next step: switch scan source to Sandbox Mods and Scan to inspect the copied dev set.")
    return "\n".join(lines)


def _build_sandbox_mods_promotion_confirmation_message(
    preview: SandboxModsPromotionPreview,
) -> str:
    install_new_count = sum(1 for entry in preview.plan.entries if entry.action == "install_new")
    replace_entries = tuple(
        entry for entry in preview.plan.entries if entry.action == "overwrite_with_archive"
    )
    lines = [
        "Review sandbox promotion into the REAL Mods path.",
        "",
        preview.review.message,
        "",
        "Execute promotion now?",
        f"Source: {preview.sandbox_mods_path}",
        f"Destination: {preview.real_mods_path}",
        f"Archive root: {preview.archive_path}",
        f"Entries: {preview.review.summary.total_entry_count}",
        f"New targets: {install_new_count}",
        f"Archive-aware replace: {len(replace_entries)}",
        "",
        "This is an explicit promotion flow, not a raw sync-back.",
        "Conflicts are handled by archiving the live target before replacement.",
        "No blind overwrite is performed.",
    ]
    if replace_entries:
        lines.append("")
        lines.append("Conflicting live targets")
        lines.extend(f"- {entry.target_path.name}" for entry in replace_entries[:5])
        remaining_count = len(replace_entries) - min(len(replace_entries), 5)
        if remaining_count > 0:
            lines.append(f"- ... and {remaining_count} more")
    return "\n".join(lines)


def _build_sandbox_mods_promotion_result_text(result: SandboxModsPromotionResult) -> str:
    lines = [
        "Sandbox promotion result",
        "Direction: sandbox Mods -> REAL Mods",
        f"Sandbox Mods path: {result.sandbox_mods_path}",
        f"REAL Mods path: {result.real_mods_path}",
        f"Recovery archive root: {result.archive_path}",
        f"Promoted targets: {len(result.promoted_target_paths)}",
    ]
    if result.replaced_target_paths:
        lines.append(
            f"Archive-aware replacements: {len(result.replaced_target_paths)}"
        )
    else:
        lines.append("Archive-aware replacements: 0")
    if result.source_mod_paths:
        lines.append("Source sandbox mod folders")
        lines.extend(f"- {path}" for path in result.source_mod_paths)
    if result.promoted_target_paths:
        lines.append("REAL Mods target folders")
        lines.extend(f"- {path}" for path in result.promoted_target_paths)
    if result.replaced_target_paths:
        lines.append("Replaced live REAL Mods targets")
        lines.extend(f"- {path}" for path in result.replaced_target_paths)
    if result.archived_target_paths:
        lines.append("Archived live targets")
        lines.extend(f"- {path}" for path in result.archived_target_paths)
    lines.append("")
    lines.append(
        "Destination was rescanned after promotion. Current scan context was left unchanged."
    )
    lines.append(
        "Recovery history was recorded for this explicit promotion so archive-aware replacements remain inspectable."
    )
    return "\n".join(lines)


def _discovery_source_label(provider: str) -> str:
    labels = {
        "nexus": "Nexus",
        "github": "GitHub",
        "custom_url": "Custom source",
        "none": "No source link",
    }
    return labels.get(provider, provider)


def _set_label_font_weight(label: QLabel, *, bold: bool = False) -> None:
    font = QFont(label.font())
    font.setBold(bold)
    label.setFont(font)


def _apply_label_palette_role(label: QLabel, role: QPalette.ColorRole) -> None:
    palette = label.palette()
    palette.setColor(
        QPalette.ColorRole.WindowText,
        palette.color(role),
    )
    label.setPalette(palette)


def _set_auxiliary_label_style(label: QLabel, *, bold: bool = False) -> None:
    _set_label_font_weight(label, bold=bold)
    _apply_label_palette_role(label, QPalette.ColorRole.WindowText)


def _set_section_label_style(label: QLabel) -> None:
    _set_label_font_weight(label, bold=True)
    _apply_label_palette_role(label, QPalette.ColorRole.WindowText)


def _set_button_emphasis_style(button: QPushButton, *, bold: bool = False) -> None:
    font = QFont(button.font())
    font.setBold(bold)
    button.setFont(font)
    button.setStyleSheet("padding: 3px 9px;")


def _context_caption(text: str) -> QLabel:
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    _set_auxiliary_label_style(label)
    return label


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    _set_section_label_style(label)
    return label


def _set_primary_button_style(button: QPushButton) -> None:
    button.setMinimumHeight(26)
    _set_button_emphasis_style(button, bold=True)


def _set_secondary_button_style(button: QPushButton) -> None:
    button.setMinimumHeight(26)
    _set_button_emphasis_style(button)


def _set_danger_button_style(button: QPushButton) -> None:
    button.setMinimumHeight(26)
    _set_button_emphasis_style(button, bold=True)


def _configure_combo_box_readability(
    combo: QComboBox,
    *,
    minimum_contents_length: int,
    sample_text: str,
) -> None:
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    combo.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    combo.setMinimumContentsLength(minimum_contents_length)
    popup_width = combo.fontMetrics().horizontalAdvance(sample_text) + 72
    combo.view().setMinimumWidth(max(combo.view().minimumWidth(), popup_width))


def _smapi_update_summary_label(status: SmapiUpdateStatus) -> str:
    installed = status.installed_version or "unknown"
    latest = status.latest_version or "unknown"
    if status.state == SMAPI_NOT_DETECTED_FOR_UPDATE:
        return "SMAPI not detected"
    if status.state == SMAPI_UPDATE_AVAILABLE:
        return f"Update available ({installed} -> {latest})"
    if status.state == SMAPI_UP_TO_DATE:
        return f"Up to date ({installed})"
    if status.state == SMAPI_DETECTED_VERSION_KNOWN:
        return f"Detected ({installed})"
    if status.state == SMAPI_UNABLE_TO_DETERMINE:
        return "Unable to determine"
    return status.state.replace("_", " ")


def _smapi_log_summary_label(report: SmapiLogReport) -> str:
    if report.state == SMAPI_LOG_NOT_FOUND:
        return "Log not found"
    if report.state == SMAPI_LOG_UNABLE_TO_DETERMINE:
        return "Unable to determine"

    counts = {
        SMAPI_LOG_ERROR: 0,
        SMAPI_LOG_WARNING: 0,
        SMAPI_LOG_FAILED_MOD: 0,
        SMAPI_LOG_MISSING_DEPENDENCY: 0,
        SMAPI_LOG_RUNTIME_ISSUE: 0,
    }
    for finding in report.findings:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1

    issue_count = (
        counts[SMAPI_LOG_ERROR]
        + counts[SMAPI_LOG_FAILED_MOD]
        + counts[SMAPI_LOG_MISSING_DEPENDENCY]
        + counts[SMAPI_LOG_RUNTIME_ISSUE]
    )
    if issue_count == 0 and counts[SMAPI_LOG_WARNING] == 0:
        return "No obvious issues parsed"

    return (
        f"Issues: err {counts[SMAPI_LOG_ERROR]}, "
        f"fail {counts[SMAPI_LOG_FAILED_MOD]}, "
        f"dep {counts[SMAPI_LOG_MISSING_DEPENDENCY]}, "
        f"warn {counts[SMAPI_LOG_WARNING]}"
    )


def _discovery_compatibility_label(state: str) -> str:
    labels = {
        "compatible": "Compatible",
        "compatible_with_caveat": "Compatible (caveat)",
        "unofficial_update": "Use unofficial update",
        "workaround_available": "Use workaround",
        "incompatible": "Incompatible",
        "abandoned": "Abandoned",
        "obsolete": "Obsolete",
        "compatibility_unknown": "Compatibility unknown",
    }
    return labels.get(state, state.replace("_", " ").title())


def _environment_summary_label(status: GameEnvironmentStatus) -> str:
    if "invalid_game_path" in status.state_codes:
        return "Invalid game path"

    mods_state = "mods detected" if "mods_path_detected" in status.state_codes else "mods not detected"
    smapi_state = "SMAPI detected" if "smapi_detected" in status.state_codes else "SMAPI not detected"
    return f"{mods_state}, {smapi_state}"


def _sandbox_dev_launch_summary_label(ready: bool, message: str) -> str:
    if ready:
        return "Ready"
    lowered = message.casefold()
    if "matches the configured real mods path" in lowered:
        return "Blocked: matches real Mods"
    if "sandbox mods directory" in lowered:
        return "Needs sandbox Mods path"
    if "game directory" in lowered or "game path" in lowered:
        return "Needs game path"
    if "smapi launch is unavailable" in lowered or "smapi executable target" in lowered:
        return "SMAPI unavailable"
    return "Not ready"


def _nexus_status_label(state: str, masked_key: str | None) -> str:
    if state == "not_configured":
        return "Not configured"
    if state == "working_validated":
        return f"Working ({masked_key or 'key set'})"
    if state == "invalid_auth_failure":
        return f"Invalid/auth failed ({masked_key or 'key set'})"
    return f"Configured ({masked_key or 'key set'})"


def _archive_source_summary_label(source_kind: str) -> str:
    if source_kind == ARCHIVE_SOURCE_REAL:
        return "Real archive"
    if source_kind == ARCHIVE_SOURCE_SANDBOX:
        return "Sandbox archive"
    return source_kind.replace("_", " ").title()


def _mods_compare_state_label(state: str) -> str:
    labels = {
        "only_in_real": "Only in real",
        "only_in_sandbox": "Only in sandbox",
        "same_version": "Same version",
        "version_mismatch": "Version mismatch",
        "ambiguous_match": "Ambiguous",
    }
    return labels.get(state, state.replace("_", " ").title())


def _mods_compare_summary_text(result: ModsCompareResult) -> str:
    counts = Counter(entry.state for entry in result.entries)
    summary = (
        "Last compare: "
        f"{counts.get('only_in_real', 0)} only in real, "
        f"{counts.get('only_in_sandbox', 0)} only in sandbox, "
        f"{counts.get('same_version', 0)} same version, "
        f"{counts.get('version_mismatch', 0)} version mismatch, "
        f"{counts.get('ambiguous_match', 0)} ambiguous."
    )
    parse_warning_total = (
        len(result.real_inventory.parse_warnings) + len(result.sandbox_inventory.parse_warnings)
    )
    if parse_warning_total:
        summary += f" Additional scan warnings: {parse_warning_total}."
    return summary


def _summarize_details_text(text: str) -> tuple[str, str]:
    lowered = text.casefold()
    blocking_indicators = (
        ("plan status: blocked", "Install plan has blocked entries."),
        ("missing required dependencies", "Missing required dependencies need resolution."),
        ("invalid game path", "Game environment path is invalid."),
        ("unusable package", "Selected package is unusable for planning."),
        ("failed", "Last operation reported a failure."),
        ("error", "Last operation reported an error."),
    )
    blocking_message = "No blocking issues detected in current view."
    for needle, message in blocking_indicators:
        if needle in lowered:
            blocking_message = message
            break

    next_step = _extract_recommended_next_step(text)
    if not next_step:
        next_step = "Follow workflow tabs: scan/update -> discovery/source -> intake -> plan/install."

    return blocking_message, next_step


def _extract_recommended_next_step(text: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    for idx, line in enumerate(lines):
        if line.casefold() != "recommended next step:":
            continue
        for candidate in lines[idx + 1 :]:
            if not candidate:
                continue
            normalized = candidate.lstrip("- ").strip()
            if normalized:
                return normalized
    return ""


def _compact_path_text(path_text: str, *, max_length: int = 56) -> str:
    if len(path_text) <= max_length:
        return path_text
    return f"...{path_text[-(max_length - 3):]}"


def _package_inspection_entry_label(entry: PackageInspectionBatchEntry) -> str:
    if entry.inspection is None:
        return f"{entry.package_path.name} [inspection failed]"

    mods_label = "1 mod" if len(entry.inspection.mods) == 1 else f"{len(entry.inspection.mods)} mods"
    readiness = "ready to stage" if entry.inspection.mods else "review only"
    return f"{entry.package_path.name} [{mods_label}, {readiness}]"


def _package_inspection_entry_text(entry: PackageInspectionBatchEntry) -> str:
    if entry.inspection is not None:
        return build_package_inspection_text(entry.inspection)

    return (
        "Package Inspection\n"
        f"- Package: {entry.package_path.name}\n"
        "- Status: inspection failed\n"
        f"- Error: {entry.error_message or 'Unknown package inspection error.'}"
    )


def _package_inspection_batch_summary_label_text(
    batch_result: PackageInspectionBatchResult,
) -> str:
    total_count = len(batch_result.entries)
    success_count = sum(1 for entry in batch_result.entries if entry.inspection is not None)
    failure_count = total_count - success_count
    if total_count <= 1:
        return "Inspect one package, then stage it explicitly in Plan & Install."
    return (
        f"{total_count} packages inspected: {success_count} ready to review, "
        f"{failure_count} failed. Stage one selected package at a time."
    )


def _batch_inspection_status_text(batch_result: PackageInspectionBatchResult) -> str:
    total_count = len(batch_result.entries)
    success_count = sum(1 for entry in batch_result.entries if entry.inspection is not None)
    failure_count = total_count - success_count
    if failure_count == 0:
        return f"Zip inspection complete: {total_count} package(s) inspected"
    return (
        f"Zip inspection complete: {total_count} package(s) inspected, "
        f"{failure_count} failed"
    )


def _build_package_inspection_batch_text(batch_result: PackageInspectionBatchResult) -> str:
    total_count = len(batch_result.entries)
    success_count = sum(1 for entry in batch_result.entries if entry.inspection is not None)
    failure_count = total_count - success_count

    lines = [
        "Package Inspection Batch",
        f"- Packages selected: {total_count}",
        f"- Successful inspections: {success_count}",
        f"- Failed inspections: {failure_count}",
    ]
    if total_count > 1:
        lines.append("- Staging: select one inspected package at a time for planning.")

    lines.append("")
    lines.append("Per-package results:")
    for entry in batch_result.entries:
        if entry.inspection is None:
            lines.append(f"- {entry.package_path.name}: failed")
            if entry.error_message:
                lines.append(f"  Error: {entry.error_message}")
            continue

        lines.append(
            f"- {entry.package_path.name}: "
            f"{len(entry.inspection.mods)} mod(s), "
            f"{len(entry.inspection.findings)} finding(s), "
            f"{len(entry.inspection.warnings)} warning(s)"
        )

    return "\n".join(lines)


def _error_detail_text(exc: object) -> str:
    detail_message = getattr(exc, "detail_message", None)
    if isinstance(detail_message, str) and detail_message.strip():
        return detail_message
    return str(exc)
