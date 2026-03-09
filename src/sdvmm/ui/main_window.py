from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QUrl
from PySide6.QtCore import QTimer
from PySide6.QtGui import QDesktopServices

from sdvmm.app.inventory_presenter import (
    build_dependency_preflight_text,
    build_downloads_intake_text,
    build_environment_status_text,
    build_findings_text,
    build_intake_correlation_text,
    build_package_inspection_text,
    build_sandbox_install_plan_text,
    build_sandbox_install_result_text,
    build_update_report_text,
)
from sdvmm.app.shell_service import (
    INSTALL_TARGET_CONFIGURED_REAL_MODS,
    INSTALL_TARGET_SANDBOX_MODS,
    SCAN_TARGET_CONFIGURED_REAL_MODS,
    SCAN_TARGET_SANDBOX_MODS,
    AppShellError,
    AppShellService,
    IntakeUpdateCorrelation,
)
from sdvmm.domain.models import (
    AppConfig,
    DownloadsIntakeResult,
    GameEnvironmentStatus,
    ModUpdateStatus,
    ModUpdateReport,
    ModsInventory,
    SandboxInstallPlan,
)
from sdvmm.domain.unique_id import canonicalize_unique_id


class MainWindow(QMainWindow):
    def __init__(self, shell_service: AppShellService) -> None:
        super().__init__()
        self._shell_service = shell_service
        self._config: AppConfig | None = None
        self._pending_install_plan: SandboxInstallPlan | None = None
        self._current_inventory: ModsInventory | None = None
        self._current_update_report: ModUpdateReport | None = None
        self._row_remote_links: dict[int, str] = {}
        self._row_update_statuses: dict[int, ModUpdateStatus] = {}
        self._known_watched_zip_paths: tuple[Path, ...] = tuple()
        self._detected_intakes: tuple[DownloadsIntakeResult, ...] = tuple()
        self._intake_correlations: tuple[IntakeUpdateCorrelation, ...] = tuple()
        self._guided_update_unique_ids: tuple[str, ...] = tuple()
        self._last_environment_status: GameEnvironmentStatus | None = None

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
        self._sandbox_archive_path_input.setPlaceholderText("/path/to/Sandbox/.sdvmm-archive")
        self._real_archive_path_input = QLineEdit()
        self._real_archive_path_input.setPlaceholderText("/path/to/Real/Mods/.sdvmm-archive")
        self._watched_downloads_path_input = QLineEdit()
        self._watched_downloads_path_input.setPlaceholderText("/path/to/Downloads")
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

        self._findings_box = QPlainTextEdit()
        self._findings_box.setReadOnly(True)

        self._status_label = QLabel()
        self._scan_context_label = QLabel("Current scan source: not set")
        self._environment_status_label = QLabel("Environment: not checked")
        self._nexus_status_label = QLabel("Nexus: not configured")
        self._watch_status_label = QLabel("Downloads watch: stopped")
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

        self._build_layout()
        self._refresh_intake_selector()
        self._load_startup_state()

    def _build_layout(self) -> None:
        container = QWidget()
        root_layout = QVBoxLayout(container)

        path_layout = QGridLayout()
        path_layout.addWidget(QLabel("Game directory (real install)"), 0, 0)
        path_layout.addWidget(self._game_path_input, 0, 1)

        browse_game_button = QPushButton("Browse game")
        browse_game_button.clicked.connect(self._on_browse_game)
        path_layout.addWidget(browse_game_button, 0, 2)

        path_layout.addWidget(QLabel("Mods directory (real path)"), 1, 0)
        path_layout.addWidget(self._mods_path_input, 1, 1)

        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._on_browse)
        path_layout.addWidget(browse_button, 1, 2)

        path_layout.addWidget(QLabel("Zip package"), 2, 0)
        path_layout.addWidget(self._zip_path_input, 2, 1)

        browse_zip_button = QPushButton("Browse zip")
        browse_zip_button.clicked.connect(self._on_browse_zip)
        path_layout.addWidget(browse_zip_button, 2, 2)

        path_layout.addWidget(QLabel("Sandbox Mods target (safe install path)"), 3, 0)
        path_layout.addWidget(self._sandbox_mods_path_input, 3, 1)

        browse_sandbox_button = QPushButton("Browse sandbox")
        browse_sandbox_button.clicked.connect(self._on_browse_sandbox_mods)
        path_layout.addWidget(browse_sandbox_button, 3, 2)

        path_layout.addWidget(QLabel("Sandbox archive path"), 4, 0)
        path_layout.addWidget(self._sandbox_archive_path_input, 4, 1)

        browse_archive_button = QPushButton("Browse archive")
        browse_archive_button.clicked.connect(self._on_browse_sandbox_archive)
        path_layout.addWidget(browse_archive_button, 4, 2)

        path_layout.addWidget(QLabel("Real Mods archive path"), 5, 0)
        path_layout.addWidget(self._real_archive_path_input, 5, 1)

        browse_real_archive_button = QPushButton("Browse real archive")
        browse_real_archive_button.clicked.connect(self._on_browse_real_archive)
        path_layout.addWidget(browse_real_archive_button, 5, 2)

        path_layout.addWidget(self._overwrite_checkbox, 6, 1)
        path_layout.addWidget(QLabel("Watched downloads path"), 7, 0)
        path_layout.addWidget(self._watched_downloads_path_input, 7, 1)

        browse_downloads_button = QPushButton("Browse downloads")
        browse_downloads_button.clicked.connect(self._on_browse_watched_downloads)
        path_layout.addWidget(browse_downloads_button, 7, 2)

        path_layout.addWidget(QLabel("Nexus API key"), 8, 0)
        path_layout.addWidget(self._nexus_api_key_input, 8, 1)
        path_layout.addWidget(self._nexus_status_label, 8, 2)

        path_layout.addWidget(QLabel("Install destination"), 9, 0)
        path_layout.addWidget(self._install_target_combo, 9, 1)
        path_layout.addWidget(self._install_archive_label, 9, 2)

        path_layout.addWidget(QLabel("Scan target"), 10, 0)
        path_layout.addWidget(self._scan_target_combo, 10, 1)
        path_layout.addWidget(QLabel("Detected packages (from watcher)"), 11, 0)
        path_layout.addWidget(self._intake_result_combo, 11, 1)
        path_layout.addWidget(self._plan_selected_intake_button, 11, 2)

        actions_row = QHBoxLayout()
        save_button = QPushButton("Save config")
        save_button.clicked.connect(self._on_save_config)
        actions_row.addWidget(save_button)

        detect_environment_button = QPushButton("Detect environment")
        detect_environment_button.clicked.connect(self._on_detect_environment)
        actions_row.addWidget(detect_environment_button)

        scan_button = QPushButton("Scan")
        scan_button.clicked.connect(self._on_scan)
        actions_row.addWidget(scan_button)

        inspect_button = QPushButton("Inspect zip")
        inspect_button.clicked.connect(self._on_inspect_zip)
        actions_row.addWidget(inspect_button)

        plan_install_button = QPushButton("Plan install")
        plan_install_button.clicked.connect(self._on_plan_install)
        actions_row.addWidget(plan_install_button)

        run_install_button = QPushButton("Run install")
        run_install_button.clicked.connect(self._on_run_install)
        actions_row.addWidget(run_install_button)

        check_updates_button = QPushButton("Check updates")
        check_updates_button.clicked.connect(self._on_check_updates)
        actions_row.addWidget(check_updates_button)

        check_nexus_button = QPushButton("Check Nexus")
        check_nexus_button.clicked.connect(self._on_check_nexus_connection)
        actions_row.addWidget(check_nexus_button)

        open_remote_button = QPushButton("Open remote page")
        open_remote_button.clicked.connect(self._on_open_remote_page)
        actions_row.addWidget(open_remote_button)

        start_watch_button = QPushButton("Start watch")
        start_watch_button.clicked.connect(self._on_start_watch)
        actions_row.addWidget(start_watch_button)

        stop_watch_button = QPushButton("Stop watch")
        stop_watch_button.clicked.connect(self._on_stop_watch)
        actions_row.addWidget(stop_watch_button)
        actions_row.addStretch(1)
        self._plan_selected_intake_button.clicked.connect(self._on_plan_selected_intake)

        root_layout.addLayout(path_layout)
        root_layout.addLayout(actions_row)
        root_layout.addWidget(QLabel("Installed mods"))
        root_layout.addWidget(self._mods_table)
        root_layout.addWidget(QLabel("Summary and guidance"))
        root_layout.addWidget(self._findings_box)
        root_layout.addWidget(self._scan_context_label)
        root_layout.addWidget(self._environment_status_label)
        root_layout.addWidget(self._watch_status_label)
        root_layout.addWidget(self._status_label)

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
            self._findings_box.setPlainText(state.message)
            self._set_status(state.message)

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
                self._sandbox_archive_path_input.setText(str(Path(selected) / ".sdvmm-archive"))

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
        self._findings_box.setPlainText(build_environment_status_text(status))
        self._set_status("Environment detection complete.")

    def _on_scan(self) -> None:
        try:
            result = self._shell_service.scan_with_target(
                scan_target=self._current_scan_target(),
                configured_mods_path_text=self._mods_path_input.text(),
                sandbox_mods_path_text=self._sandbox_mods_path_input.text(),
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Scan failed", str(exc))
            self._set_status(str(exc))
            return

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
        self._findings_box.setPlainText(build_package_inspection_text(inspection))
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
        self._findings_box.setPlainText(build_sandbox_install_plan_text(plan))
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
        self._findings_box.setPlainText(build_sandbox_install_result_text(result))
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

        try:
            report = self._shell_service.check_updates(
                self._current_inventory,
                nexus_api_key_text=self._nexus_api_key_input.text(),
                existing_config=self._config,
            )
        except AppShellError as exc:
            QMessageBox.critical(self, "Update check failed", str(exc))
            self._set_status(str(exc))
            return

        self._current_update_report = report
        self._apply_update_report(report)
        self._findings_box.setPlainText(build_update_report_text(report))
        self._recompute_intake_correlations()
        self._set_status(f"Update check complete: {len(report.statuses)} mod(s)")

    def _on_check_nexus_connection(self) -> None:
        status = self._shell_service.get_nexus_integration_status(
            nexus_api_key_text=self._nexus_api_key_input.text(),
            existing_config=self._config,
            validate_connection=True,
        )
        self._nexus_status_label.setText(_nexus_status_label(status.state, status.masked_key))
        if status.message:
            self._findings_box.setPlainText(status.message)
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

        url = self._row_remote_links.get(row)
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

        status = self._row_update_statuses.get(row)
        if status is not None and status.state == "update_available":
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
            self._findings_box.setPlainText(hint)
            self._set_status(
                f"Opened remote page for update target {status.unique_id}. Follow guided steps."
            )
            return

        self._set_status(f"Opened remote page: {url}")

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
            f"Downloads watch: running ({watched_path}) baseline={baseline_count} existing zip(s)"
        )
        self._set_status(
            "Downloads watcher started. Only zip files added after start are detected."
        )

    def _on_stop_watch(self) -> None:
        self._watch_timer.stop()
        self._watch_status_label.setText("Downloads watch: stopped")
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
            self._watch_status_label.setText("Downloads watch: stopped (error)")
            self._set_status(str(exc))
            self._findings_box.setPlainText(str(exc))
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
        self._findings_box.setPlainText(
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
        self._row_remote_links = {}
        self._row_update_statuses = {}
        self._guided_update_unique_ids = tuple()
        self._mods_table.setRowCount(len(inventory.mods))

        for row, mod in enumerate(inventory.mods):
            self._mods_table.setItem(row, 0, QTableWidgetItem(mod.name))
            self._mods_table.setItem(row, 1, QTableWidgetItem(mod.unique_id))
            self._mods_table.setItem(row, 2, QTableWidgetItem(mod.version))
            self._mods_table.setItem(row, 3, QTableWidgetItem("-"))
            self._mods_table.setItem(row, 4, QTableWidgetItem("not_checked"))
            self._mods_table.setItem(row, 5, QTableWidgetItem(mod.folder_path.name))

        self._mods_table.resizeColumnsToContents()
        dependency_findings = self._shell_service.evaluate_installed_dependency_preflight(inventory)
        self._findings_box.setPlainText(
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

    def _apply_update_report(self, report: ModUpdateReport) -> None:
        if self._current_inventory is None:
            return

        by_folder = {status.folder_path: status for status in report.statuses}
        self._row_remote_links = {}
        self._row_update_statuses = {}

        for row, mod in enumerate(self._current_inventory.mods):
            status = by_folder.get(mod.folder_path)
            if status is None:
                self._mods_table.setItem(row, 3, QTableWidgetItem("-"))
                self._mods_table.setItem(row, 4, QTableWidgetItem("metadata_unavailable"))
                continue

            self._mods_table.setItem(row, 3, QTableWidgetItem(status.remote_version or "-"))
            self._mods_table.setItem(row, 4, QTableWidgetItem(status.state))
            self._row_update_statuses[row] = status
            if status.remote_link is not None:
                self._row_remote_links[row] = status.remote_link.page_url

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def _set_scan_context(self, path: Path, label: str) -> None:
        self._scan_context_label.setText(f"Current scan source: {label} ({path})")

    def _invalidate_pending_plan(self, *_: object) -> None:
        self._pending_install_plan = None

    def _on_watched_path_changed(self, *_: object) -> None:
        self._known_watched_zip_paths = tuple()
        self._detected_intakes = tuple()
        self._intake_correlations = tuple()
        self._refresh_intake_selector()
        if self._watch_timer.isActive():
            self._watch_timer.stop()
            self._watch_status_label.setText("Downloads watch: stopped (path changed)")
            self._set_status("Watcher stopped because watched path changed.")

    def _on_game_path_changed(self, *_: object) -> None:
        self._last_environment_status = None
        self._environment_status_label.setText("Environment: not checked")

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
        self._findings_box.setPlainText(build_sandbox_install_plan_text(plan))
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
        else:
            path_text = self._sandbox_mods_path_input.text().strip() or "<unset>"
        self._scan_context_label.setText(
            f"Selected scan source: {self._scan_target_label(target)} ({path_text})"
        )

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
            if not self._real_archive_path_input.text().strip() and self._mods_path_input.text().strip():
                self._real_archive_path_input.setText(
                    str(Path(self._mods_path_input.text().strip()) / ".sdvmm-archive")
                )
            return

        self._install_archive_label.setText("Archive path for sandbox destination")
        if (
            not self._sandbox_archive_path_input.text().strip()
            and self._sandbox_mods_path_input.text().strip()
        ):
            self._sandbox_archive_path_input.setText(
                str(Path(self._sandbox_mods_path_input.text().strip()) / ".sdvmm-archive")
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

    def _refresh_intake_selector(self) -> None:
        self._intake_result_combo.clear()

        if not self._detected_intakes:
            self._intake_result_combo.addItem("<no detected packages>", -1)
            self._intake_result_combo.setEnabled(False)
            self._plan_selected_intake_button.setEnabled(False)
            return

        self._intake_result_combo.setEnabled(True)
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
            self._intake_result_combo.addItem(label, idx)

        self._intake_result_combo.setCurrentIndex(len(self._detected_intakes) - 1)
        self._plan_selected_intake_button.setEnabled(True)

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

    def _recompute_intake_correlations(self) -> None:
        self._intake_correlations = self._shell_service.correlate_intakes_with_updates(
            intakes=self._detected_intakes,
            update_report=self._current_update_report,
            guided_update_unique_ids=self._guided_update_unique_ids,
        )
        self._refresh_intake_selector()

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


def _environment_summary_label(status: GameEnvironmentStatus) -> str:
    if "invalid_game_path" in status.state_codes:
        return "Environment: invalid game path"

    mods_state = "mods detected" if "mods_path_detected" in status.state_codes else "mods not detected"
    smapi_state = "SMAPI detected" if "smapi_detected" in status.state_codes else "SMAPI not detected"
    return f"Environment: {mods_state}, {smapi_state}"


def _nexus_status_label(state: str, masked_key: str | None) -> str:
    if state == "not_configured":
        return "Nexus: not configured"
    if state == "working_validated":
        return f"Nexus: working ({masked_key or 'key set'})"
    if state == "invalid_auth_failure":
        return f"Nexus: invalid/auth failed ({masked_key or 'key set'})"
    return f"Nexus: configured ({masked_key or 'key set'})"
