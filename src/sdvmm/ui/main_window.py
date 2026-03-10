from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
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

from sdvmm.app.inventory_presenter import (
    build_archive_listing_text,
    build_archive_restore_result_text,
    build_dependency_preflight_text,
    build_discovery_search_text,
    build_downloads_intake_text,
    build_environment_status_text,
    build_findings_text,
    build_intake_correlation_text,
    build_mod_removal_result_text,
    build_package_inspection_text,
    build_sandbox_install_plan_text,
    build_sandbox_install_result_text,
    build_update_report_text,
)
from sdvmm.app.table_filters import row_matches_filter
from sdvmm.app.shell_service import (
    ARCHIVE_SOURCE_REAL,
    ARCHIVE_SOURCE_SANDBOX,
    DiscoveryContextCorrelation,
    INSTALL_TARGET_CONFIGURED_REAL_MODS,
    INSTALL_TARGET_SANDBOX_MODS,
    SCAN_TARGET_CONFIGURED_REAL_MODS,
    SCAN_TARGET_SANDBOX_MODS,
    AppShellError,
    AppShellService,
    IntakeUpdateCorrelation,
    ScanResult,
)
from sdvmm.domain.models import (
    AppConfig,
    DownloadsIntakeResult,
    GameEnvironmentStatus,
    ModDiscoveryResult,
    ArchiveRestoreResult,
    ArchivedModEntry,
    ModRemovalResult,
    ModUpdateStatus,
    ModUpdateReport,
    ModsInventory,
    SandboxInstallPlan,
)
from sdvmm.domain.unique_id import canonicalize_unique_id
from sdvmm.ui.background_task import BackgroundTask

_ROLE_MOD_UPDATE_STATUS = int(Qt.ItemDataRole.UserRole) + 1
_ROLE_REMOTE_LINK = int(Qt.ItemDataRole.UserRole) + 2
_ROLE_DISCOVERY_INDEX = int(Qt.ItemDataRole.UserRole) + 3
_ROLE_DISCOVERY_LINK = int(Qt.ItemDataRole.UserRole) + 4
_ROLE_MOD_FOLDER_PATH = int(Qt.ItemDataRole.UserRole) + 5
_ROLE_ARCHIVE_INDEX = int(Qt.ItemDataRole.UserRole) + 6


class MainWindow(QMainWindow):
    def __init__(self, shell_service: AppShellService) -> None:
        super().__init__()
        self._shell_service = shell_service
        self._config: AppConfig | None = None
        self._pending_install_plan: SandboxInstallPlan | None = None
        self._current_inventory: ModsInventory | None = None
        self._current_update_report: ModUpdateReport | None = None
        self._current_discovery_result: ModDiscoveryResult | None = None
        self._discovery_correlations: tuple[DiscoveryContextCorrelation, ...] = tuple()
        self._known_watched_zip_paths: tuple[Path, ...] = tuple()
        self._detected_intakes: tuple[DownloadsIntakeResult, ...] = tuple()
        self._intake_correlations: tuple[IntakeUpdateCorrelation, ...] = tuple()
        self._archived_entries: tuple[ArchivedModEntry, ...] = tuple()
        self._guided_update_unique_ids: tuple[str, ...] = tuple()
        self._last_environment_status: GameEnvironmentStatus | None = None
        self._thread_pool = QThreadPool.globalInstance()
        self._active_operation_name: str | None = None
        self._active_background_task: BackgroundTask | None = None
        self._background_action_buttons: tuple[QPushButton, ...] = tuple()

        self.setWindowTitle("Stardew Mod Manager (Sandbox-first)")
        self.resize(950, 600)

        self._game_path_input = QLineEdit()
        self._game_path_input.setPlaceholderText("/path/to/Stardew Valley")
        self._mods_path_input = QLineEdit()
        self._mods_path_input.setPlaceholderText("/path/to/Stardew/Mods")
        self._zip_path_input = QLineEdit()
        self._zip_path_input.setPlaceholderText("/path/to/package.zip")
        self._sandbox_mods_path_input = QLineEdit()
        self._sandbox_mods_path_input.setPlaceholderText("/path/to/Sandbox/Mods")
        self._sandbox_archive_path_input = QLineEdit()
        self._sandbox_archive_path_input.setPlaceholderText("/path/to/.sdvmm-sandbox-archive")
        self._real_archive_path_input = QLineEdit()
        self._real_archive_path_input.setPlaceholderText("/path/to/.sdvmm-real-archive")
        self._watched_downloads_path_input = QLineEdit()
        self._watched_downloads_path_input.setPlaceholderText("/path/to/Downloads")
        self._discovery_query_input = QLineEdit()
        self._discovery_query_input.setPlaceholderText(
            "Search by mod name, UniqueID, or author"
        )
        self._mods_filter_input = QLineEdit()
        self._mods_filter_input.setPlaceholderText("Filter installed mods")
        self._mods_filter_input.setClearButtonEnabled(True)
        self._mods_filter_input.setMinimumWidth(240)
        self._discovery_filter_input = QLineEdit()
        self._discovery_filter_input.setPlaceholderText("Filter discovery results")
        self._discovery_filter_input.setClearButtonEnabled(True)
        self._discovery_filter_input.setMinimumWidth(240)
        self._intake_filter_input = QLineEdit()
        self._intake_filter_input.setPlaceholderText("Filter detected packages")
        self._intake_filter_input.setClearButtonEnabled(True)
        self._intake_filter_input.setMinimumWidth(240)
        self._archive_filter_input = QLineEdit()
        self._archive_filter_input.setPlaceholderText("Filter archived entries")
        self._archive_filter_input.setClearButtonEnabled(True)
        self._archive_filter_input.setMinimumWidth(240)
        self._mods_filter_stats_label = QLabel("0/0 shown")
        self._discovery_filter_stats_label = QLabel("0/0 shown")
        self._intake_filter_stats_label = QLabel("0/0 shown")
        self._archive_filter_stats_label = QLabel("0/0 shown")
        for stats_label in (
            self._mods_filter_stats_label,
            self._discovery_filter_stats_label,
            self._intake_filter_stats_label,
            self._archive_filter_stats_label,
        ):
            stats_label.setStyleSheet("color: #4b5563;")
        self._nexus_api_key_input = QLineEdit()
        self._nexus_api_key_input.setPlaceholderText("Nexus API key")
        self._nexus_api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._overwrite_checkbox = QCheckBox("Allow overwrite with archive")
        self._install_target_combo = QComboBox()
        self._install_target_combo.addItem(
            "Sandbox Mods destination (safe/test)",
            INSTALL_TARGET_SANDBOX_MODS,
        )
        self._install_target_combo.addItem(
            "Game Mods destination (real)",
            INSTALL_TARGET_CONFIGURED_REAL_MODS,
        )
        self._scan_target_combo = QComboBox()
        self._scan_target_combo.addItem("Real Mods path (scan only)", SCAN_TARGET_CONFIGURED_REAL_MODS)
        self._scan_target_combo.addItem("Sandbox Mods path (scan only)", SCAN_TARGET_SANDBOX_MODS)
        self._intake_result_combo = QComboBox()
        self._plan_selected_intake_button = QPushButton("Plan selected intake")
        self._install_archive_label = QLabel("Archive path for selected install destination")

        self._mods_table = QTableWidget(0, 6)
        self._mods_table.setHorizontalHeaderLabels(
            ["Name", "UniqueID", "Installed ver.", "Remote ver.", "Update status", "Folder"]
        )
        self._mods_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._mods_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._mods_table.verticalHeader().setDefaultSectionSize(20)
        self._mods_table.verticalHeader().setVisible(False)
        self._mods_table.setAlternatingRowColors(True)
        self._mods_table.setSortingEnabled(True)

        self._discovery_table = QTableWidget(0, 8)
        self._discovery_table.setHorizontalHeaderLabels(
            ["Name", "UniqueID", "Author", "Source", "Compatibility", "App context", "Provider relation", "Page"]
        )
        self._discovery_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._discovery_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._discovery_table.verticalHeader().setDefaultSectionSize(20)
        self._discovery_table.verticalHeader().setVisible(False)
        self._discovery_table.setAlternatingRowColors(True)
        self._discovery_table.setSortingEnabled(True)

        self._archive_table = QTableWidget(0, 6)
        self._archive_table.setHorizontalHeaderLabels(
            ["Archive source", "Archived folder", "Restore target", "Mod name", "UniqueID", "Version"]
        )
        self._archive_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._archive_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._archive_table.verticalHeader().setDefaultSectionSize(20)
        self._archive_table.verticalHeader().setVisible(False)
        self._archive_table.setAlternatingRowColors(True)
        self._archive_table.setSortingEnabled(True)

        self._findings_box = QPlainTextEdit()
        self._findings_box.setReadOnly(True)
        self._findings_box.setMinimumHeight(140)

        self._status_label = QLabel()
        self._blocking_issues_label = QLabel("No blocking issues detected.")
        self._next_step_label = QLabel("Run Scan to refresh installed inventory.")
        self._scan_context_label = QLabel("Not set")
        self._install_context_label = QLabel("Not set")
        self._environment_status_label = QLabel("Not checked")
        self._nexus_status_label = QLabel("Not configured")
        self._watch_status_label = QLabel("Stopped")
        self._operation_state_label = QLabel("Idle")
        self._status_label.setWordWrap(False)
        self._blocking_issues_label.setWordWrap(False)
        self._next_step_label.setWordWrap(False)
        self._next_step_label.setStyleSheet(
            "font-weight: 600; padding: 3px 5px; border: 1px solid #b8c8e8; background: #eef4ff;"
        )
        self._blocking_issues_label.setStyleSheet(
            "padding: 3px 5px; border: 1px solid #e0d1a5; background: #fff8e6;"
        )
        self._status_label.setStyleSheet(
            "padding: 3px 5px; border: 1px solid #d9d9d9; background: #f6f6f6;"
        )
        self._details_toggle = QCheckBox("Show detailed output")
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(2000)
        self._watch_timer.timeout.connect(self._on_watch_tick)

        self._zip_path_input.textChanged.connect(self._invalidate_pending_plan)
        self._sandbox_mods_path_input.textChanged.connect(self._invalidate_pending_plan)
        self._sandbox_archive_path_input.textChanged.connect(self._invalidate_pending_plan)
        self._real_archive_path_input.textChanged.connect(self._invalidate_pending_plan)
        self._overwrite_checkbox.toggled.connect(self._invalidate_pending_plan)
        self._scan_target_combo.currentIndexChanged.connect(self._refresh_scan_context_preview)
        self._install_target_combo.currentIndexChanged.connect(self._on_install_target_changed)
        self._game_path_input.textChanged.connect(self._on_game_path_changed)
        self._mods_path_input.textChanged.connect(self._refresh_scan_context_preview)
        self._mods_path_input.textChanged.connect(self._refresh_install_destination_preview)
        self._sandbox_mods_path_input.textChanged.connect(self._refresh_scan_context_preview)
        self._sandbox_mods_path_input.textChanged.connect(self._refresh_install_destination_preview)
        self._watched_downloads_path_input.textChanged.connect(self._on_watched_path_changed)
        self._nexus_api_key_input.textChanged.connect(self._on_nexus_key_changed)
        self._intake_result_combo.currentIndexChanged.connect(self._on_intake_selection_changed)
        self._discovery_query_input.returnPressed.connect(self._on_search_discovery)
        self._details_toggle.toggled.connect(self._on_toggle_details_panel)
        self._mods_filter_input.textChanged.connect(self._apply_mods_filter)
        self._discovery_filter_input.textChanged.connect(self._apply_discovery_filter)
        self._intake_filter_input.textChanged.connect(self._refresh_intake_selector)
        self._archive_filter_input.textChanged.connect(self._apply_archive_filter)

        self._build_layout()
        self._refresh_intake_selector()
        self._load_startup_state()

    def _build_layout(self) -> None:
        container = QWidget()
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(8, 6, 8, 6)
        root_layout.setSpacing(6)

        context_group = QGroupBox("Context")
        context_layout = QGridLayout(context_group)
        context_layout.setContentsMargins(8, 6, 8, 6)
        context_layout.setHorizontalSpacing(10)
        context_layout.setVerticalSpacing(4)
        context_layout.addWidget(QLabel("Environment"), 0, 0)
        context_layout.addWidget(self._environment_status_label, 0, 1)
        context_layout.addWidget(QLabel("Nexus"), 0, 2)
        context_layout.addWidget(self._nexus_status_label, 0, 3)
        context_layout.addWidget(QLabel("Watcher"), 0, 4)
        context_layout.addWidget(self._watch_status_label, 0, 5)
        context_layout.addWidget(QLabel("Operation"), 0, 6)
        context_layout.addWidget(self._operation_state_label, 0, 7)
        context_layout.addWidget(QLabel("Scan source"), 1, 0)
        context_layout.addWidget(self._scan_context_label, 1, 1, 1, 2)
        context_layout.addWidget(QLabel("Install destination"), 1, 3)
        context_layout.addWidget(self._install_context_label, 1, 4, 1, 4)
        context_layout.setColumnStretch(1, 1)
        context_layout.setColumnStretch(3, 1)
        context_layout.setColumnStretch(5, 1)
        context_layout.setColumnStretch(7, 1)
        root_layout.addWidget(context_group)

        self._setup_toggle = QCheckBox("Show setup and path configuration")
        self._setup_toggle.toggled.connect(self._on_toggle_setup_panel)
        root_layout.addWidget(self._setup_toggle)

        setup_group = QGroupBox("Setup and Configuration")
        setup_layout = QGridLayout(setup_group)
        setup_layout.setContentsMargins(8, 6, 8, 6)
        setup_layout.setHorizontalSpacing(8)
        setup_layout.setVerticalSpacing(4)
        setup_layout.addWidget(QLabel("Game directory (real install)"), 0, 0)
        setup_layout.addWidget(self._game_path_input, 0, 1)
        browse_game_button = QPushButton("Browse game")
        browse_game_button.clicked.connect(self._on_browse_game)
        setup_layout.addWidget(browse_game_button, 0, 2)

        setup_layout.addWidget(QLabel("Mods directory (real path)"), 1, 0)
        setup_layout.addWidget(self._mods_path_input, 1, 1)
        browse_mods_button = QPushButton("Browse Mods")
        browse_mods_button.clicked.connect(self._on_browse)
        setup_layout.addWidget(browse_mods_button, 1, 2)

        setup_layout.addWidget(QLabel("Sandbox Mods target"), 2, 0)
        setup_layout.addWidget(self._sandbox_mods_path_input, 2, 1)
        browse_sandbox_button = QPushButton("Browse sandbox")
        browse_sandbox_button.clicked.connect(self._on_browse_sandbox_mods)
        setup_layout.addWidget(browse_sandbox_button, 2, 2)

        setup_layout.addWidget(QLabel("Sandbox archive path"), 3, 0)
        setup_layout.addWidget(self._sandbox_archive_path_input, 3, 1)
        browse_sandbox_archive_button = QPushButton("Browse archive")
        browse_sandbox_archive_button.clicked.connect(self._on_browse_sandbox_archive)
        setup_layout.addWidget(browse_sandbox_archive_button, 3, 2)

        setup_layout.addWidget(QLabel("Real Mods archive path"), 4, 0)
        setup_layout.addWidget(self._real_archive_path_input, 4, 1)
        browse_real_archive_button = QPushButton("Browse real archive")
        browse_real_archive_button.clicked.connect(self._on_browse_real_archive)
        setup_layout.addWidget(browse_real_archive_button, 4, 2)

        setup_layout.addWidget(QLabel("Nexus API key"), 5, 0)
        setup_layout.addWidget(self._nexus_api_key_input, 5, 1)
        check_nexus_button = QPushButton("Check Nexus")
        check_nexus_button.clicked.connect(self._on_check_nexus_connection)
        setup_layout.addWidget(check_nexus_button, 5, 2)

        setup_actions = QHBoxLayout()
        save_button = QPushButton("Save config")
        save_button.clicked.connect(self._on_save_config)
        setup_actions.addWidget(save_button)
        detect_environment_button = QPushButton("Detect environment")
        detect_environment_button.clicked.connect(self._on_detect_environment)
        setup_actions.addWidget(detect_environment_button)
        setup_actions.addStretch(1)
        setup_layout.addLayout(setup_actions, 6, 0, 1, 3)

        setup_group.setVisible(False)
        self._setup_group = setup_group
        root_layout.addWidget(setup_group)

        workspace_splitter = QSplitter()
        workspace_splitter.setChildrenCollapsible(False)
        workspace_splitter.setHandleWidth(6)

        inventory_group = QGroupBox("Installed Mods Workspace")
        inventory_layout = QVBoxLayout(inventory_group)
        inventory_layout.setContentsMargins(8, 6, 8, 6)
        inventory_layout.setSpacing(5)
        inventory_controls = QHBoxLayout()
        inventory_controls.setSpacing(6)
        inventory_controls.addWidget(QLabel("Scan source"))
        inventory_controls.addWidget(self._scan_target_combo)
        self._scan_button = QPushButton("Scan")
        self._scan_button.clicked.connect(self._on_scan)
        inventory_controls.addWidget(self._scan_button)
        self._check_updates_button = QPushButton("Check updates")
        self._check_updates_button.clicked.connect(self._on_check_updates)
        inventory_controls.addWidget(self._check_updates_button)
        open_remote_button = QPushButton("Open remote page")
        open_remote_button.clicked.connect(self._on_open_remote_page)
        inventory_controls.addWidget(open_remote_button)
        self._remove_mod_button = QPushButton("Remove selected (archive)")
        self._remove_mod_button.clicked.connect(self._on_remove_selected_mod)
        inventory_controls.addWidget(self._remove_mod_button)
        inventory_controls.addWidget(QLabel("Filter"))
        inventory_controls.addWidget(self._mods_filter_input, 1)
        inventory_controls.addWidget(self._mods_filter_stats_label)
        inventory_controls.addStretch(1)
        inventory_layout.addLayout(inventory_controls)
        flow_hint_label = QLabel(
            "Flow: Scan -> Check updates -> Open remote page -> manual download -> watcher intake -> plan/install."
        )
        flow_hint_label.setWordWrap(False)
        flow_hint_label.setStyleSheet("color: #4b5563;")
        flow_hint_label.setToolTip(
            "Workflow: Scan -> Check updates -> Open remote page -> manual download -> watcher intake -> plan/install."
        )
        inventory_layout.addWidget(flow_hint_label)
        inventory_layout.addWidget(self._mods_table)
        workspace_splitter.addWidget(inventory_group)

        context_tabs = QTabWidget()

        discovery_tab = QWidget()
        discovery_layout = QVBoxLayout(discovery_tab)
        discovery_layout.setContentsMargins(6, 6, 6, 6)
        discovery_layout.setSpacing(6)
        discovery_search_group = QGroupBox("Search and Source")
        discovery_search_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        discovery_search_layout = QHBoxLayout(discovery_search_group)
        discovery_search_layout.setContentsMargins(8, 6, 8, 6)
        discovery_search_layout.setSpacing(6)
        discovery_search_layout.addWidget(QLabel("Search query"))
        discovery_search_layout.addWidget(self._discovery_query_input)
        self._search_mods_button = QPushButton("Search mods")
        self._search_mods_button.clicked.connect(self._on_search_discovery)
        discovery_search_layout.addWidget(self._search_mods_button)
        open_discovered_button = QPushButton("Open discovered page")
        open_discovered_button.clicked.connect(self._on_open_discovered_page)
        discovery_search_layout.addWidget(open_discovered_button)
        discovery_layout.addWidget(discovery_search_group)
        discovery_results_group = QGroupBox("Results")
        discovery_results_layout = QVBoxLayout(discovery_results_group)
        discovery_results_layout.setContentsMargins(8, 6, 8, 6)
        discovery_filter_layout = QHBoxLayout()
        discovery_filter_layout.setSpacing(6)
        discovery_filter_layout.addWidget(QLabel("Filter"))
        discovery_filter_layout.addWidget(self._discovery_filter_input, 1)
        discovery_filter_layout.addWidget(self._discovery_filter_stats_label)
        discovery_results_layout.addLayout(discovery_filter_layout)
        discovery_results_layout.addWidget(self._discovery_table)
        discovery_layout.addWidget(discovery_results_group)
        discovery_layout.setStretch(1, 1)
        context_tabs.addTab(discovery_tab, "Discovery")

        intake_tab = QWidget()
        intake_layout = QVBoxLayout(intake_tab)
        intake_layout.setContentsMargins(6, 6, 6, 6)
        intake_layout.setSpacing(6)
        inspect_group = QGroupBox("Package Review")
        inspect_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        inspect_layout = QGridLayout(inspect_group)
        inspect_layout.setContentsMargins(8, 6, 8, 6)
        inspect_layout.setHorizontalSpacing(8)
        inspect_layout.setVerticalSpacing(4)
        inspect_layout.addWidget(QLabel("Zip package"), 0, 0)
        inspect_layout.addWidget(self._zip_path_input, 0, 1)
        browse_zip_button = QPushButton("Browse zip")
        browse_zip_button.clicked.connect(self._on_browse_zip)
        inspect_layout.addWidget(browse_zip_button, 0, 2)
        inspect_button = QPushButton("Inspect zip")
        inspect_button.clicked.connect(self._on_inspect_zip)
        inspect_layout.addWidget(inspect_button, 0, 3)
        intake_layout.addWidget(inspect_group)

        watcher_group = QGroupBox("Watcher")
        watcher_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        watcher_layout = QGridLayout(watcher_group)
        watcher_layout.setContentsMargins(8, 6, 8, 6)
        watcher_layout.setHorizontalSpacing(8)
        watcher_layout.setVerticalSpacing(4)
        watcher_layout.addWidget(QLabel("Watched downloads path"), 0, 0)
        watcher_layout.addWidget(self._watched_downloads_path_input, 0, 1)
        browse_downloads_button = QPushButton("Browse downloads")
        browse_downloads_button.clicked.connect(self._on_browse_watched_downloads)
        watcher_layout.addWidget(browse_downloads_button, 0, 2)
        watch_actions = QHBoxLayout()
        start_watch_button = QPushButton("Start watch")
        start_watch_button.clicked.connect(self._on_start_watch)
        watch_actions.addWidget(start_watch_button)
        stop_watch_button = QPushButton("Stop watch")
        stop_watch_button.clicked.connect(self._on_stop_watch)
        watch_actions.addWidget(stop_watch_button)
        watch_actions.addStretch(1)
        watcher_layout.addLayout(watch_actions, 0, 3)
        intake_layout.addWidget(watcher_group)

        detected_group = QGroupBox("Detected Packages")
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
        detected_layout.addWidget(self._plan_selected_intake_button, 1, 3)
        intake_layout.addWidget(detected_group)
        intake_layout.addStretch(1)
        context_tabs.addTab(intake_tab, "Packages & Intake")

        archive_tab = QWidget()
        archive_layout = QVBoxLayout(archive_tab)
        archive_layout.setContentsMargins(6, 6, 6, 6)
        archive_layout.setSpacing(6)
        archive_controls_group = QGroupBox("Archive Browser")
        archive_controls_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        archive_controls_layout = QGridLayout(archive_controls_group)
        archive_controls_layout.setContentsMargins(8, 6, 8, 6)
        archive_controls_layout.setHorizontalSpacing(8)
        archive_controls_layout.setVerticalSpacing(4)
        archive_controls_layout.addWidget(QLabel("Filter"), 0, 0)
        archive_controls_layout.addWidget(self._archive_filter_input, 0, 1, 1, 2)
        archive_controls_layout.addWidget(self._archive_filter_stats_label, 0, 3)
        self._refresh_archives_button = QPushButton("Refresh archives")
        self._refresh_archives_button.clicked.connect(self._on_refresh_archives)
        archive_controls_layout.addWidget(self._refresh_archives_button, 1, 1)
        self._restore_archived_button = QPushButton("Restore selected")
        self._restore_archived_button.clicked.connect(self._on_restore_selected_archive)
        self._restore_archived_button.setEnabled(False)
        archive_controls_layout.addWidget(self._restore_archived_button, 1, 2)
        archive_layout.addWidget(archive_controls_group)
        archive_table_group = QGroupBox("Archived Entries (real + sandbox)")
        archive_table_layout = QVBoxLayout(archive_table_group)
        archive_table_layout.setContentsMargins(8, 6, 8, 6)
        archive_table_layout.addWidget(self._archive_table)
        archive_layout.addWidget(archive_table_group)
        archive_layout.setStretch(1, 1)
        self._archive_table.itemSelectionChanged.connect(self._on_archive_selection_changed)
        context_tabs.addTab(archive_tab, "Archive")

        plan_tab = QWidget()
        plan_tab_layout = QVBoxLayout(plan_tab)
        plan_tab_layout.setContentsMargins(6, 6, 6, 6)
        plan_tab_layout.setSpacing(6)
        destination_group = QGroupBox("Destination and Safety Context")
        destination_group.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
        )
        destination_layout = QGridLayout(destination_group)
        destination_layout.setContentsMargins(8, 6, 8, 6)
        destination_layout.setHorizontalSpacing(8)
        destination_layout.setVerticalSpacing(4)
        destination_layout.addWidget(QLabel("Install destination"), 0, 0)
        destination_layout.addWidget(self._install_target_combo, 0, 1)
        destination_layout.addWidget(self._overwrite_checkbox, 0, 2)
        destination_layout.addWidget(self._install_archive_label, 1, 0, 1, 3)
        plan_tab_layout.addWidget(destination_group)

        execute_group = QGroupBox("Plan and Execute")
        execute_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        execute_layout = QVBoxLayout(execute_group)
        execute_layout.setContentsMargins(8, 6, 8, 6)
        execute_layout.setSpacing(5)
        plan_actions = QHBoxLayout()
        plan_actions.setSpacing(6)
        plan_install_button = QPushButton("Plan install")
        plan_install_button.clicked.connect(self._on_plan_install)
        plan_actions.addWidget(plan_install_button)
        run_install_button = QPushButton("Run install")
        run_install_button.clicked.connect(self._on_run_install)
        plan_actions.addWidget(run_install_button)
        plan_actions.addStretch(1)
        execute_layout.addLayout(plan_actions)
        caution_label = QLabel(
            "No automatic install: review plan details and warnings before running install."
        )
        caution_label.setWordWrap(True)
        caution_label.setStyleSheet("color: #4b5563;")
        execute_layout.addWidget(caution_label)
        plan_tab_layout.addWidget(execute_group)
        plan_tab_layout.addStretch(1)
        context_tabs.addTab(plan_tab, "Plan & Install")

        workspace_splitter.addWidget(context_tabs)
        workspace_splitter.setStretchFactor(0, 3)
        workspace_splitter.setStretchFactor(1, 4)
        root_layout.addWidget(workspace_splitter, 1)

        guidance_group = QGroupBox("Guidance and Status")
        guidance_layout = QVBoxLayout(guidance_group)
        guidance_layout.setContentsMargins(8, 6, 8, 6)
        guidance_layout.setSpacing(4)
        summary_layout = QGridLayout()
        summary_layout.setHorizontalSpacing(8)
        summary_layout.setVerticalSpacing(4)
        summary_layout.addWidget(QLabel("Current status"), 0, 0)
        summary_layout.addWidget(self._status_label, 0, 1)
        summary_layout.addWidget(QLabel("Blocking issues"), 1, 0)
        summary_layout.addWidget(self._blocking_issues_label, 1, 1)
        summary_layout.addWidget(QLabel("Recommended next step"), 2, 0)
        summary_layout.addWidget(self._next_step_label, 2, 1)
        summary_layout.setColumnStretch(1, 1)
        guidance_layout.addLayout(summary_layout)
        guidance_layout.addWidget(self._details_toggle)
        details_group = QGroupBox("Detailed output")
        details_layout = QVBoxLayout(details_group)
        details_layout.setContentsMargins(8, 6, 8, 6)
        details_layout.addWidget(self._findings_box)
        details_group.setVisible(False)
        self._details_group = details_group
        self._guidance_group = guidance_group
        guidance_layout.addWidget(details_group)
        root_layout.addWidget(guidance_group)
        self._apply_guidance_compact_mode(details_visible=False)
        self._background_action_buttons = (
            self._scan_button,
            self._check_updates_button,
            self._search_mods_button,
            self._remove_mod_button,
            self._refresh_archives_button,
            self._restore_archived_button,
        )

        self.setCentralWidget(container)

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
            if state.config.nexus_api_key is not None:
                self._nexus_api_key_input.setText(state.config.nexus_api_key)
            self._set_current_scan_target(state.config.scan_target)
            self._set_current_install_target(state.config.install_target)
            self._set_status(f"Loaded saved config from {self._shell_service.state_file}")

        if state.message:
            self._set_details_text(state.message)
            self._set_status(state.message)
            self._setup_toggle.setChecked(True)

        self._refresh_scan_context_preview()
        self._refresh_install_destination_preview()
        self._refresh_nexus_status(validated=False)

    def _on_browse_game(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select game directory",
            self._game_path_input.text() or "",
        )
        if selected:
            self._game_path_input.setText(selected)

    def _on_toggle_setup_panel(self, checked: bool) -> None:
        self._setup_group.setVisible(checked)

    def _on_toggle_details_panel(self, checked: bool) -> None:
        self._details_group.setVisible(checked)
        self._apply_guidance_compact_mode(details_visible=checked)
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
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Select zip package",
            self._zip_path_input.text() or "",
            "Zip packages (*.zip)",
        )
        if selected:
            self._pending_install_plan = None
            self._zip_path_input.setText(selected)

    def _on_browse_sandbox_mods(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select sandbox Mods directory",
            self._sandbox_mods_path_input.text() or "",
        )
        if selected:
            self._pending_install_plan = None
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
            self._pending_install_plan = None
            self._sandbox_archive_path_input.setText(selected)

    def _on_browse_real_archive(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select real Mods archive directory",
            self._real_archive_path_input.text() or "",
        )
        if selected:
            self._pending_install_plan = None
            self._real_archive_path_input.setText(selected)

    def _on_browse_watched_downloads(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Select watched downloads directory",
            self._watched_downloads_path_input.text() or "",
        )
        if selected:
            self._watched_downloads_path_input.setText(selected)

    def _on_save_config(self) -> None:
        try:
            self._config = self._shell_service.save_operational_config(
                game_path_text=self._game_path_input.text(),
                mods_dir_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
                sandbox_archive_path_text=self._sandbox_archive_path_input.text(),
                watched_downloads_path_text=self._watched_downloads_path_input.text(),
                real_archive_path_text=self._real_archive_path_input.text(),
                nexus_api_key_text=self._nexus_api_key_input.text(),
                scan_target=self._current_scan_target(),
                install_target=self._current_install_target(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            self._set_status(str(exc))
            return

        self._refresh_nexus_status(validated=False)
        self._set_status(f"Saved config to {self._shell_service.state_file}")

    def _on_detect_environment(self) -> None:
        try:
            status = self._shell_service.detect_game_environment(self._game_path_input.text())
        except AppShellError as exc:
            QMessageBox.critical(self, "Environment detect failed", str(exc))
            self._set_status(str(exc))
            return

        self._last_environment_status = status
        if status.mods_path is not None and not self._mods_path_input.text().strip():
            self._mods_path_input.setText(str(status.mods_path))

        self._environment_status_label.setText(_environment_summary_label(status))
        self._set_details_text(build_environment_status_text(status))
        self._set_status("Environment detection complete.")

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

    def _on_inspect_zip(self) -> None:
        try:
            inspection = self._shell_service.inspect_zip_with_inventory_context(
                self._zip_path_input.text(),
                self._current_inventory,
                nexus_api_key_text=self._nexus_api_key_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Zip inspection failed", str(exc))
            self._set_status(str(exc))
            return

        self._pending_install_plan = None
        self._set_details_text(build_package_inspection_text(inspection))
        self._set_status(f"Zip inspection complete: {len(inspection.mods)} mod(s) detected")

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
            self._pending_install_plan = None
            QMessageBox.critical(self, "Install plan failed", str(exc))
            self._set_status(str(exc))
            return

        self._pending_install_plan = plan
        self._set_details_text(build_sandbox_install_plan_text(plan))
        destination = "real Mods" if plan.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS else "sandbox"
        self._set_status(f"Install plan ready for {destination}: {len(plan.entries)} entry(ies)")

    def _on_run_install(self) -> None:
        if self._pending_install_plan is None:
            message = "Create an install plan before executing install."
            QMessageBox.warning(self, "No install plan", message)
            self._set_status(message)
            return

        is_real_destination = (
            self._pending_install_plan.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
        )

        yes = QMessageBox.question(
            self,
            ("Confirm REAL Mods install" if is_real_destination else "Confirm sandbox install"),
            (
                ("You are about to write to the REAL game Mods directory.\n\n" if is_real_destination else "")
                + "Execute install now?\n"
                + f"Target: {self._pending_install_plan.sandbox_mods_path}\n"
                + f"Archive: {self._pending_install_plan.sandbox_archive_path}\n"
                "Overwrite operations in plan: "
                f"{'yes' if any(entry.action == 'overwrite_with_archive' for entry in self._pending_install_plan.entries) else 'no'}\n"
                f"Entries: {len(self._pending_install_plan.entries)}"
            ),
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
            self._set_status(str(exc))
            return

        self._render_inventory(result.inventory)
        self._set_details_text(build_sandbox_install_result_text(result))
        self._set_current_scan_target(result.destination_kind)
        self._set_scan_context(result.scan_context_path, self._scan_target_label(result.destination_kind))
        if is_real_destination:
            self._set_status(f"Real Mods install complete: {len(result.installed_targets)} target(s)")
        else:
            self._set_status(f"Sandbox install complete: {len(result.installed_targets)} target(s)")

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
                watcher_running=self._watch_timer.isActive(),
            )
            self._set_details_text(hint)
            self._set_status(
                f"Opened discovered page for {correlation.entry.unique_id}. Follow manual flow guidance."
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
                watcher_running=self._watch_timer.isActive(),
            )
            self._set_details_text(hint)
            self._set_status(
                f"Opened remote page for update target {status.unique_id}. Follow guided steps."
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
        restored_source = result.plan.entry.archived_path
        self._archived_entries = tuple(
            entry for entry in self._archived_entries if entry.archived_path != restored_source
        )
        self._render_archive_entries(self._archived_entries)
        destination_label = (
            "REAL Mods"
            if result.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
            else "Sandbox Mods"
        )
        self._set_status(
            f"Archive restore complete to {destination_label}: {result.restored_target.name}"
        )

    def _on_archive_selection_changed(self) -> None:
        self._restore_archived_button.setEnabled(self._selected_archive_entry() is not None)

    def _on_start_watch(self) -> None:
        try:
            self._known_watched_zip_paths = self._shell_service.initialize_downloads_watch(
                self._watched_downloads_path_input.text()
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Watch start failed", str(exc))
            self._set_status(str(exc))
            return

        self._watch_timer.start()
        baseline_count = len(self._known_watched_zip_paths)
        watched_path = self._watched_downloads_path_input.text().strip()
        self._watch_status_label.setText(
            f"Running | {watched_path} | baseline={baseline_count} zip(s)"
        )
        self._set_status(
            "Downloads watcher started. Only zip files added after start are detected."
        )

    def _on_stop_watch(self) -> None:
        self._watch_timer.stop()
        self._watch_status_label.setText("Stopped")
        self._set_status("Downloads watcher stopped.")

    def _on_watch_tick(self) -> None:
        try:
            result = self._shell_service.poll_downloads_watch(
                watched_downloads_path_text=self._watched_downloads_path_input.text(),
                known_zip_paths=self._known_watched_zip_paths,
                inventory=self._current_inventory_or_empty(),
                nexus_api_key_text=self._nexus_api_key_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            self._watch_timer.stop()
            self._watch_status_label.setText("Stopped (error)")
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
        self._detected_intakes = self._detected_intakes + result.intakes
        self._recompute_intake_correlations()
        self._set_details_text(
            "\n\n".join(
                (
                    build_downloads_intake_text(result),
                    build_intake_correlation_text(new_correlations),
                )
            )
        )
        self._set_status(f"Detected {len(result.intakes)} new package(s) in watched downloads.")

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
            self._mods_table.setItem(row, 0, name_item)
            self._mods_table.setItem(row, 1, QTableWidgetItem(mod.unique_id))
            self._mods_table.setItem(row, 2, QTableWidgetItem(mod.version))
            self._mods_table.setItem(row, 3, QTableWidgetItem("-"))
            self._mods_table.setItem(row, 4, QTableWidgetItem("not_checked"))
            self._mods_table.setItem(row, 5, QTableWidgetItem(mod.folder_path.name))

        self._mods_table.setSortingEnabled(was_sorting)
        self._mods_table.resizeColumnsToContents()
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
                self._mods_table.setItem(row, 4, QTableWidgetItem("metadata_unavailable"))
                name_item.setData(_ROLE_MOD_UPDATE_STATUS, None)
                name_item.setData(_ROLE_REMOTE_LINK, "")
                continue

            self._mods_table.setItem(row, 3, QTableWidgetItem(status.remote_version or "-"))
            self._mods_table.setItem(row, 4, QTableWidgetItem(status.state))
            name_item.setData(_ROLE_MOD_UPDATE_STATUS, status)
            name_item.setData(
                _ROLE_REMOTE_LINK,
                status.remote_link.page_url if status.remote_link is not None else "",
            )
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
        self._discovery_table.resizeColumnsToContents()
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
        self._archive_table.resizeColumnsToContents()
        self._apply_archive_filter()
        self._on_archive_selection_changed()

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)
        self._status_label.setToolTip(text)

    def _run_background_operation(
        self,
        *,
        operation_name: str,
        running_label: str,
        started_status: str,
        error_title: str,
        task_fn: Callable[[], object],
        on_success: Callable[[object], None],
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
            lambda exc, _name=operation_name, _title=error_title: self._on_background_operation_failed(
                _name,
                _title,
                exc,
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
    ) -> None:
        message = str(exc)
        QMessageBox.critical(self, error_title, message)
        self._set_details_text(message)
        self._set_status(message)
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

    def _set_details_text(self, text: str) -> None:
        self._findings_box.setPlainText(text)
        blocking_issue, next_step = _summarize_details_text(text)
        self._blocking_issues_label.setText(blocking_issue)
        self._next_step_label.setText(next_step)
        self._blocking_issues_label.setToolTip(blocking_issue)
        self._next_step_label.setToolTip(next_step)

    def _set_scan_context(self, path: Path, label: str) -> None:
        path_text = str(path)
        self._scan_context_label.setText(f"{label}: {_compact_path_text(path_text)}")
        self._scan_context_label.setToolTip(path_text)

    def _invalidate_pending_plan(self, *_: object) -> None:
        self._pending_install_plan = None

    def _on_watched_path_changed(self, *_: object) -> None:
        self._known_watched_zip_paths = tuple()
        self._detected_intakes = tuple()
        self._intake_correlations = tuple()
        self._refresh_intake_selector()
        if self._watch_timer.isActive():
            self._watch_timer.stop()
            self._watch_status_label.setText("Stopped (path changed)")
            self._set_status("Watcher stopped because watched path changed.")

    def _on_game_path_changed(self, *_: object) -> None:
        self._last_environment_status = None
        self._environment_status_label.setText("Not checked")

    def _on_nexus_key_changed(self, *_: object) -> None:
        self._refresh_nexus_status(validated=False)

    def _on_install_target_changed(self, *_: object) -> None:
        self._pending_install_plan = None
        self._refresh_install_destination_preview()
        if self._current_install_target() == INSTALL_TARGET_CONFIGURED_REAL_MODS:
            self._set_status("Install destination set to REAL game Mods path. Review carefully before executing.")
        else:
            self._set_status("Install destination set to sandbox Mods path.")

    def _on_plan_selected_intake(self) -> None:
        selected_index = self._selected_intake_index()
        try:
            intake = self._shell_service.select_intake_result(
                intakes=self._detected_intakes,
                selected_index=selected_index,
            )
        except AppShellError as exc:
            QMessageBox.warning(self, "No package selected", str(exc))
            self._set_status(str(exc))
            return

        self._zip_path_input.setText(str(intake.package_path))
        if not self._shell_service.is_actionable_intake_result(intake):
            message = (
                "Selected package cannot be planned for install "
                f"({intake.classification})."
            )
            self._pending_install_plan = None
            QMessageBox.information(self, "Package not actionable", message)
            self._set_status(message)
            return

        try:
            plan = self._shell_service.build_install_plan_from_intake(
                intake=intake,
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
            self._pending_install_plan = None
            QMessageBox.critical(self, "Install plan failed", str(exc))
            self._set_status(str(exc))
            return

        self._pending_install_plan = plan
        self._set_details_text(build_sandbox_install_plan_text(plan))
        correlation = self._selected_intake_correlation()
        if correlation is not None and correlation.matched_update_available_unique_ids:
            self._set_status(
                "Install plan ready for detected update package. "
                "Review overwrite/archive actions before execution."
            )
            return
        destination = "real Mods" if plan.destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS else "sandbox"
        self._set_status(
            f"Install plan ready for {destination} from intake package: {plan.package_path.name}"
        )

    def _on_intake_selection_changed(self, *_: object) -> None:
        self._plan_selected_intake_button.setEnabled(self._selected_intake_index() >= 0)
        correlation = self._selected_intake_correlation()
        if correlation is not None:
            self._set_status(correlation.next_step)

    def _apply_mods_filter(self, *_: object) -> None:
        filter_text = self._mods_filter_input.text()
        visible_count = 0
        for row in range(self._mods_table.rowCount()):
            row_values = []
            for col in range(self._mods_table.columnCount()):
                item = self._mods_table.item(row, col)
                row_values.append(item.text() if item is not None else "")
            matches = row_matches_filter(row_values, filter_text)
            self._mods_table.setRowHidden(row, not matches)
            if matches:
                visible_count += 1
        self._set_filter_stats(
            self._mods_filter_stats_label,
            shown_count=visible_count,
            total_count=self._mods_table.rowCount(),
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
        compact = _compact_path_text(path_text)
        self._scan_context_label.setText(f"{target_label}: {compact}")
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
            self._install_context_label.setText(
                f"REAL game Mods: {_compact_path_text(path_text)} (explicit confirmation required)"
            )
            self._install_context_label.setToolTip(path_text)
            if not self._real_archive_path_input.text().strip() and self._mods_path_input.text().strip():
                self._real_archive_path_input.setText(
                    str(Path(self._mods_path_input.text().strip()).parent / ".sdvmm-real-archive")
                )
            return

        self._install_archive_label.setText("Archive path for sandbox destination")
        path_text = self._sandbox_mods_path_input.text().strip() or "<unset>"
        self._install_context_label.setText(f"Sandbox Mods: {_compact_path_text(path_text)}")
        self._install_context_label.setToolTip(path_text)
        if (
            not self._sandbox_archive_path_input.text().strip()
            and self._sandbox_mods_path_input.text().strip()
        ):
            self._sandbox_archive_path_input.setText(
                str(Path(self._sandbox_mods_path_input.text().strip()).parent / ".sdvmm-sandbox-archive")
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
            self._plan_selected_intake_button.setEnabled(False)
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
            self._plan_selected_intake_button.setEnabled(False)
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
        self._plan_selected_intake_button.setEnabled(self._selected_intake_index() >= 0)
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

    @staticmethod
    def _scan_target_label(target: str) -> str:
        if target == SCAN_TARGET_CONFIGURED_REAL_MODS:
            return "real Mods directory"
        return "sandbox Mods directory"

    def _apply_guidance_compact_mode(self, *, details_visible: bool) -> None:
        if details_visible:
            self._guidance_group.setMaximumHeight(16777215)
            return
        self._guidance_group.setMaximumHeight(210)

    @staticmethod
    def _set_filter_stats(label: QLabel, *, shown_count: int, total_count: int) -> None:
        label.setText(f"{shown_count}/{total_count} shown")


def _discovery_source_label(provider: str) -> str:
    labels = {
        "nexus": "Nexus",
        "github": "GitHub",
        "custom_url": "Custom source",
        "none": "No source link",
    }
    return labels.get(provider, provider)


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
