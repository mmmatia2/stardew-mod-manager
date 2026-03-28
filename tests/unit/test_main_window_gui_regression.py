from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sdvmm.app.main import _resolve_app_icon
from sdvmm.app.shell_service import AppShellError
from sdvmm.app.shell_service import AppShellService
from sdvmm.app.shell_service import BackupBundleExportItem
from sdvmm.app.shell_service import BackupBundleExportResult
from sdvmm.app.shell_service import DiscoveryContextCorrelation
from sdvmm.app.shell_service import INSTALL_TARGET_CONFIGURED_REAL_MODS
from sdvmm.app.shell_service import INSTALL_TARGET_SANDBOX_MODS
from sdvmm.app.shell_service import IntakeUpdateCorrelation
from sdvmm.app.shell_service import SCAN_TARGET_CONFIGURED_REAL_MODS
from sdvmm.app.shell_service import SCAN_TARGET_SANDBOX_MODS
from sdvmm.app.shell_service import ScanResult
from sdvmm.domain.install_codes import BLOCKED
from sdvmm.domain.discovery_codes import COMPATIBLE
from sdvmm.domain.discovery_codes import DISCOVERY_SOURCE_NEXUS
from sdvmm.domain.discovery_codes import SMAPI_COMPATIBILITY_LIST_PROVIDER
from sdvmm.domain.install_codes import INSTALL_NEW, OVERWRITE_WITH_ARCHIVE
from sdvmm.domain.package_codes import INVALID_MANIFEST_PACKAGE
from sdvmm.domain.smapi_codes import SMAPI_UP_TO_DATE
from sdvmm.domain.smapi_log_codes import SMAPI_LOG_NOT_FOUND, SMAPI_LOG_SOURCE_AUTO_DETECTED
from sdvmm.domain.update_codes import MISSING_UPDATE_KEY, UNSUPPORTED_UPDATE_KEY_FORMAT
from sdvmm.domain.models import ArchivedModEntry
from sdvmm.domain.models import AppConfig
from sdvmm.domain.models import AppUpdateStatus
from sdvmm.domain.models import BackupBundleInspectionItem
from sdvmm.domain.models import BackupBundleInspectionResult
from sdvmm.domain.models import DownloadsIntakeResult
from sdvmm.domain.models import GameEnvironmentStatus
from sdvmm.domain.models import InstalledMod
from sdvmm.domain.models import InstallOperationEntryRecord
from sdvmm.domain.models import InstallOperationRecord
from sdvmm.domain.models import ModDiscoveryEntry
from sdvmm.domain.models import ModDiscoveryResult
from sdvmm.domain.models import ModsCompareEntry
from sdvmm.domain.models import ModsCompareResult
from sdvmm.domain.models import ModUpdateReport
from sdvmm.domain.models import ModUpdateStatus
from sdvmm.domain.models import ModsInventory
from sdvmm.domain.models import PackageInspectionBatchEntry
from sdvmm.domain.models import PackageInspectionBatchResult
from sdvmm.domain.models import PackageModEntry
from sdvmm.domain.models import PackageFinding
from sdvmm.domain.models import PackageInspectionResult
from sdvmm.domain.models import RestoreImportPlanningItem
from sdvmm.domain.models import RestoreImportPlanningConfigEntry
from sdvmm.domain.models import RestoreImportExecutionReview
from sdvmm.domain.models import RestoreImportExecutionResult
from sdvmm.domain.models import RestoreImportPlanningModEntry
from sdvmm.domain.models import RestoreImportPlanningResult
from sdvmm.domain.models import RecoveryExecutionRecord
from sdvmm.domain.models import SandboxInstallPlan
from sdvmm.domain.models import SandboxInstallPlanEntry
from sdvmm.domain.models import SmapiLogReport
from sdvmm.domain.models import SmapiUpdateStatus
from sdvmm.ui.main_window import MainWindow
from sdvmm.ui.main_window import _ROLE_DISCOVERY_INDEX
from sdvmm.ui.main_window import _ROLE_MOD_UPDATE_STATUS
from sdvmm.services.app_state_store import save_app_config
from sdvmm.ui.main_window import _ROLE_UPDATE_BLOCK_REASON


@pytest.fixture
def qapp(monkeypatch: pytest.MonkeyPatch) -> QApplication:
    # Keep GUI smoke tests runnable in headless environments.
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def main_window(tmp_path: Path, qapp: QApplication) -> MainWindow:
    service = AppShellService(state_file=tmp_path / "app-state.json")
    window = MainWindow(shell_service=service)
    window.show()
    qapp.processEvents()
    yield window
    window.close()
    qapp.processEvents()


def _fake_background_operation_with_real_lifecycle(
    main_window: MainWindow,
    captured: dict[str, object] | None = None,
):
    def _runner(**kwargs: object) -> None:
        operation_name = str(kwargs["operation_name"])
        if captured is not None:
            captured.setdefault("operation_names", []).append(operation_name)
        main_window._active_operation_name = operation_name
        main_window._active_background_task = SimpleNamespace()
        task_result = kwargs["task_fn"]()
        kwargs["on_success"](task_result)
        main_window._finish_background_operation(operation_name, success=True)

    return _runner


def test_main_window_instantiates_in_qt_context(main_window: MainWindow) -> None:
    assert main_window is not None
    assert main_window.windowTitle() != ""


def test_runtime_icon_asset_resolves_for_dev_runtime() -> None:
    icon = _resolve_app_icon()

    assert icon is not None
    assert icon.isNull() is False


def test_main_window_startup_auto_checks_skip_without_meaningful_game_path(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    window = MainWindow(shell_service=AppShellService(state_file=tmp_path / "app-state.json"))
    captured: list[str] = []
    monkeypatch.setattr(
        window,
        "_run_background_operation",
        lambda **kwargs: captured.append(str(kwargs["operation_name"])),
    )

    window.show()
    qapp.processEvents()
    qapp.processEvents()

    assert captured == []
    assert window._startup_checks_completed is True

    window.close()
    qapp.processEvents()


def test_main_window_startup_auto_checks_run_in_sequence_when_game_path_is_ready(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_path = tmp_path / "Game"
    _create_launchable_game_install_for_ui(game_path)

    window = MainWindow(shell_service=AppShellService(state_file=tmp_path / "app-state.json"))
    window._game_path_input.setText(str(game_path))

    environment_status = GameEnvironmentStatus(
        game_path=game_path,
        mods_path=game_path / "Mods",
        smapi_path=game_path / "StardewModdingAPI.exe",
        state_codes=("game_path_detected", "mods_path_detected", "smapi_detected"),
    )
    smapi_status = SmapiUpdateStatus(
        state=SMAPI_UP_TO_DATE,
        game_path=game_path,
        smapi_path=game_path / "StardewModdingAPI.exe",
        installed_version="4.1.0",
        latest_version="4.1.0",
        update_page_url="https://smapi.io",
        message="SMAPI is up to date.",
    )
    smapi_log_report = SmapiLogReport(
        state=SMAPI_LOG_NOT_FOUND,
        source=SMAPI_LOG_SOURCE_AUTO_DETECTED,
        log_path=None,
        game_path=game_path,
        findings=tuple(),
        notes=tuple(),
        message="No SMAPI log found yet.",
    )
    app_update_status = AppUpdateStatus(
        state="up_to_date",
        current_version="1.1.5",
        latest_version="1.1.5",
        update_page_url="https://example.test/cinderleaf/releases/latest",
        message="Cinderleaf is up to date.",
    )
    captured: list[str] = []

    def _fake_run_background_operation(**kwargs) -> None:
        operation_name = str(kwargs["operation_name"])
        captured.append(operation_name)
        if operation_name == "Startup environment check":
            kwargs["on_success"](environment_status)
            return
        if operation_name == "Startup SMAPI update check":
            kwargs["on_success"](smapi_status)
            return
        if operation_name == "Startup SMAPI log check":
            kwargs["on_success"](smapi_log_report)
            return
        if operation_name == "Startup app update check":
            kwargs["on_success"](app_update_status)
            return
        raise AssertionError(f"Unexpected startup operation: {operation_name}")

    monkeypatch.setattr(window, "_run_background_operation", _fake_run_background_operation)

    window.show()
    for _ in range(6):
        qapp.processEvents()

    assert captured == [
        "Startup environment check",
        "Startup SMAPI update check",
        "Startup SMAPI log check",
        "Startup app update check",
    ]
    assert window._environment_status_label.text() == "mods detected, SMAPI detected"
    assert window._smapi_update_status_label.text() == "Up to date (4.1.0)"
    assert window._smapi_log_status_label.text() == "Log not found"
    assert window._setup_app_update_status_label.text() == "Cinderleaf is up to date."
    assert window._workspace_nav_release_status_label.text() == "App up to date (1.1.5)"
    assert window._status_strip_label.text() == "Cinderleaf is up to date."
    assert window._startup_checks_completed is True

    window.close()
    qapp.processEvents()


def test_main_window_startup_app_update_failure_replaces_temporary_footer_status(
    main_window: MainWindow,
) -> None:
    main_window._set_status("Checking Cinderleaf release status on startup...")

    main_window._on_startup_app_update_check_failed("Could not reach the Cinderleaf release feed.")

    assert main_window._status_strip_label.text() == "Could not reach the Cinderleaf release feed."
    assert main_window._startup_checks_completed is True


def test_main_window_startup_auto_scans_real_and_sandbox_without_switching_selected_source(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_path = tmp_path / "Game"
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    _create_launchable_game_install_for_ui(game_path)
    real_mods.mkdir()
    sandbox_mods.mkdir()

    window = MainWindow(shell_service=AppShellService(state_file=tmp_path / "app-state.json"))
    window._game_path_input.setText(str(game_path))
    window._mods_path_input.setText(str(real_mods))
    window._sandbox_mods_path_input.setText(str(sandbox_mods))
    window._config = AppConfig(
        game_path=game_path,
        mods_path=real_mods,
        app_data_path=tmp_path / "AppData",
        sandbox_mods_path=sandbox_mods,
    )

    environment_status = GameEnvironmentStatus(
        game_path=game_path,
        mods_path=real_mods,
        smapi_path=game_path / "StardewModdingAPI.exe",
        state_codes=("game_path_detected", "mods_path_detected", "smapi_detected"),
    )
    smapi_status = SmapiUpdateStatus(
        state=SMAPI_UP_TO_DATE,
        game_path=game_path,
        smapi_path=game_path / "StardewModdingAPI.exe",
        installed_version="4.1.0",
        latest_version="4.1.0",
        update_page_url="https://smapi.io",
        message="SMAPI is up to date.",
    )
    smapi_log_report = SmapiLogReport(
        state=SMAPI_LOG_NOT_FOUND,
        source=SMAPI_LOG_SOURCE_AUTO_DETECTED,
        log_path=None,
        game_path=game_path,
        findings=tuple(),
        notes=tuple(),
        message="No SMAPI log found yet.",
    )
    app_update_status = AppUpdateStatus(
        state="up_to_date",
        current_version="1.1.5",
        latest_version="1.1.5",
        update_page_url="https://example.test/cinderleaf/releases/latest",
        message="Cinderleaf is up to date.",
    )
    real_scan_result = ScanResult(
        target_kind=SCAN_TARGET_CONFIGURED_REAL_MODS,
        scan_path=real_mods,
        inventory=_mods_inventory(
            _installed_mod_for_update_ui(
                name="Real Alpha",
                unique_id="Sample.RealAlpha",
                folder_name="RealAlpha",
            )
        ),
    )
    sandbox_scan_result = ScanResult(
        target_kind=SCAN_TARGET_SANDBOX_MODS,
        scan_path=sandbox_mods,
        inventory=_mods_inventory(
            _installed_mod_for_update_ui(
                name="Sandbox Beta",
                unique_id="Sample.SandboxBeta",
                folder_name="SandboxBeta",
            )
        ),
    )
    captured: list[str] = []

    def _fake_run_background_operation(**kwargs) -> None:
        operation_name = str(kwargs["operation_name"])
        captured.append(operation_name)
        if operation_name == "Startup environment check":
            kwargs["on_success"](environment_status)
            return
        if operation_name == "Startup SMAPI update check":
            kwargs["on_success"](smapi_status)
            return
        if operation_name == "Startup SMAPI log check":
            kwargs["on_success"](smapi_log_report)
            return
        if operation_name == "Startup app update check":
            kwargs["on_success"](app_update_status)
            return
        if operation_name == "Startup real Mods directory scan":
            kwargs["on_success"](real_scan_result)
            return
        if operation_name == "Startup sandbox Mods directory scan":
            kwargs["on_success"](sandbox_scan_result)
            return
        raise AssertionError(f"Unexpected startup operation: {operation_name}")

    monkeypatch.setattr(window, "_run_background_operation", _fake_run_background_operation)

    window.show()
    for _ in range(8):
        qapp.processEvents()

    assert captured == [
        "Startup environment check",
        "Startup SMAPI update check",
        "Startup SMAPI log check",
        "Startup app update check",
        "Startup real Mods directory scan",
        "Startup sandbox Mods directory scan",
    ]
    assert window._current_scan_target() == SCAN_TARGET_CONFIGURED_REAL_MODS
    assert window._current_inventory is not None
    assert tuple(mod.unique_id for mod in window._current_inventory.mods) == ("Sample.RealAlpha",)
    assert set(window._scan_results_by_target) == {
        SCAN_TARGET_CONFIGURED_REAL_MODS,
        SCAN_TARGET_SANDBOX_MODS,
    }
    assert window._status_strip_label.text() == "Cinderleaf is up to date."
    assert window._startup_checks_completed is True

    captured.clear()
    sandbox_index = window._scan_target_combo.findData(SCAN_TARGET_SANDBOX_MODS)
    assert sandbox_index >= 0
    window._scan_target_combo.setCurrentIndex(sandbox_index)
    qapp.processEvents()

    assert captured == []
    assert window._current_scan_target() == SCAN_TARGET_SANDBOX_MODS
    assert window._current_inventory is not None
    assert tuple(mod.unique_id for mod in window._current_inventory.mods) == (
        "Sample.SandboxBeta",
    )

    real_index = window._scan_target_combo.findData(SCAN_TARGET_CONFIGURED_REAL_MODS)
    assert real_index >= 0
    window._scan_target_combo.setCurrentIndex(real_index)
    qapp.processEvents()

    assert captured == []
    assert window._current_inventory is not None
    assert tuple(mod.unique_id for mod in window._current_inventory.mods) == (
        "Sample.RealAlpha",
    )

    window.close()
    qapp.processEvents()


def test_main_window_switching_to_unscanned_source_keeps_inventory_state_truthful(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    real_mods = Path(r"C:\Game\Mods")
    sandbox_mods = Path(r"C:\Game\SandboxMods")
    main_window._mods_path_input.setText(str(real_mods))
    main_window._sandbox_mods_path_input.setText(str(sandbox_mods))

    main_window._on_scan_completed(
        ScanResult(
            target_kind=SCAN_TARGET_CONFIGURED_REAL_MODS,
            scan_path=real_mods,
            inventory=_mods_inventory(
                _installed_mod_for_update_ui(
                    name="Real Alpha",
                    unique_id="Sample.RealAlpha",
                    folder_name="RealAlpha",
                )
            ),
        )
    )
    qapp.processEvents()

    sandbox_index = main_window._scan_target_combo.findData(SCAN_TARGET_SANDBOX_MODS)
    assert sandbox_index >= 0
    main_window._scan_target_combo.setCurrentIndex(sandbox_index)
    qapp.processEvents()

    assert set(main_window._scan_results_by_target) == {SCAN_TARGET_CONFIGURED_REAL_MODS}
    assert main_window._current_scan_target() == SCAN_TARGET_SANDBOX_MODS
    assert main_window._current_inventory is None
    assert main_window._mods_table.rowCount() == 0
    assert (
        main_window._mods_inventory_state_label.text()
        == "No inventory loaded yet. Scan the selected Mods source to populate the table."
    )


def test_main_window_close_persists_practical_setup_paths_across_restart(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    state_file = tmp_path / "app-state.json"
    game_path = tmp_path / "Stardew Valley"
    mods_path = game_path / "Mods"
    sandbox_mods_path = tmp_path / "SandboxMods"
    sandbox_archive_path = tmp_path / "SandboxArchive"
    real_archive_path = tmp_path / "RealArchive"
    watched_downloads_path = tmp_path / "Downloads"
    secondary_watched_downloads_path = tmp_path / "BuiltZips"
    game_path.mkdir()
    mods_path.mkdir()
    sandbox_mods_path.mkdir()
    sandbox_archive_path.mkdir()
    real_archive_path.mkdir()
    watched_downloads_path.mkdir()
    secondary_watched_downloads_path.mkdir()

    first_window = MainWindow(shell_service=AppShellService(state_file=state_file))
    first_window.show()
    qapp.processEvents()
    qapp.processEvents()
    first_window._game_path_input.setText(str(game_path))
    first_window._mods_path_input.setText(str(mods_path))
    first_window._sandbox_mods_path_input.setText(str(sandbox_mods_path))
    first_window._sandbox_archive_path_input.setText(str(sandbox_archive_path))
    first_window._real_archive_path_input.setText(str(real_archive_path))
    first_window._watched_downloads_path_input.setText(str(watched_downloads_path))
    first_window._secondary_watched_downloads_path_input.setText(
        str(secondary_watched_downloads_path)
    )
    first_window._set_current_scan_target(SCAN_TARGET_SANDBOX_MODS)
    first_window._set_current_install_target(INSTALL_TARGET_CONFIGURED_REAL_MODS)
    qapp.processEvents()

    first_window.close()
    qapp.processEvents()

    reopened_window = MainWindow(shell_service=AppShellService(state_file=state_file))
    reopened_window.show()
    qapp.processEvents()
    qapp.processEvents()

    assert reopened_window._game_path_input.text() == str(game_path)
    assert reopened_window._mods_path_input.text() == str(mods_path)
    assert reopened_window._sandbox_mods_path_input.text() == str(sandbox_mods_path)
    assert reopened_window._sandbox_archive_path_input.text() == str(sandbox_archive_path)
    assert reopened_window._real_archive_path_input.text() == str(real_archive_path)
    assert reopened_window._watched_downloads_path_input.text() == str(watched_downloads_path)
    assert reopened_window._secondary_watched_downloads_path_input.text() == str(
        secondary_watched_downloads_path
    )
    assert reopened_window._game_path_input.cursorPosition() == 0
    assert reopened_window._mods_path_input.cursorPosition() == 0
    assert reopened_window._sandbox_mods_path_input.cursorPosition() == 0
    assert reopened_window._sandbox_archive_path_input.cursorPosition() == 0
    assert reopened_window._real_archive_path_input.cursorPosition() == 0
    assert reopened_window._watched_downloads_path_input.cursorPosition() == 0
    assert reopened_window._secondary_watched_downloads_path_input.cursorPosition() == 0
    assert reopened_window._scan_target_combo.currentData() == SCAN_TARGET_SANDBOX_MODS
    assert (
        reopened_window._install_target_combo.currentData()
        == INSTALL_TARGET_CONFIGURED_REAL_MODS
    )

    reopened_window.close()
    qapp.processEvents()


def test_main_window_keeps_status_strip_and_removes_bottom_details_region(
    main_window: MainWindow,
) -> None:
    status_strip_group = main_window.findChild(QGroupBox, "global_status_strip_group")
    bottom_details_group = main_window.findChild(QGroupBox, "bottom_details_group")

    assert status_strip_group is not None
    assert status_strip_group.isVisible()
    assert bottom_details_group is None


def test_main_window_bottom_details_region_contract_is_removed(
    main_window: MainWindow,
) -> None:
    assert main_window.findChild(QGroupBox, "bottom_details_group") is None
    assert main_window.findChild(QLabel, "bottom_detail_identity_label") is None
    assert main_window.findChild(QLabel, "bottom_detail_help_label") is None
    assert main_window.findChild(QGroupBox, "bottom_summary_details_group") is None
    assert main_window.findChild(QGroupBox, "bottom_setup_group") is None
    assert main_window.findChild(QScrollArea, "bottom_setup_tab") is None
    assert main_window.findChild(QTabWidget, "bottom_details_tabs") is None
    assert main_window.findChild(QWidget, "bottom_summary_tab") is None


def test_main_window_bottom_details_toggle_contract_is_removed(
    main_window: MainWindow,
) -> None:
    assert hasattr(main_window, "_details_toggle") is False
    assert main_window.findChild(QCheckBox, "bottom_details_toggle") is None


def test_main_window_recovery_inspection_controls_exist(main_window: MainWindow) -> None:
    recovery_tab = main_window._recovery_page
    recovery_group = main_window.findChild(QGroupBox, "recovery_inspection_group")
    recovery_output_group = main_window.findChild(QGroupBox, "recovery_output_group")
    recovery_combo = main_window.findChild(QComboBox, "recovery_inspection_operation_combo")
    recovery_filter_combo = main_window.findChild(QComboBox, "recovery_selector_filter_combo")
    recovery_summary_label = main_window.findChild(QLabel, "recovery_selection_summary_label")
    recovery_button = main_window.findChild(QPushButton, "recovery_inspection_button")
    run_recovery_button = main_window.findChild(QPushButton, "recovery_execute_button")

    assert recovery_tab is not None
    assert recovery_group is not None
    assert recovery_output_group is not None
    assert recovery_combo is not None
    assert recovery_filter_combo is not None
    assert recovery_summary_label is not None
    assert recovery_button is not None
    assert run_recovery_button is not None
    assert recovery_group.parentWidget() is not recovery_tab
    assert recovery_output_group.parentWidget() is recovery_group
    assert main_window._install_history_combo is recovery_combo
    assert main_window._install_history_filter_combo is recovery_filter_combo
    assert main_window._recovery_selection_summary_label is recovery_summary_label
    assert main_window._inspect_recovery_button is recovery_button
    assert main_window._run_recovery_button is run_recovery_button
    assert recovery_combo.isEnabled() is False
    assert recovery_button.isEnabled() is False
    assert run_recovery_button.isEnabled() is False


def test_main_window_review_tab_no_longer_hosts_recovery_controls(
    main_window: MainWindow,
) -> None:
    plan_content = main_window.findChild(QWidget, "plan_install_tab_content")
    recovery_group = main_window.findChild(QGroupBox, "recovery_inspection_group")

    assert plan_content is not None
    assert recovery_group is not None
    assert recovery_group.parentWidget() is not plan_content


def test_main_window_recovery_controls_remain_visible_without_bottom_details_region(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _install_operation_record_for_ui(operation_id="install_visibility")

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(operation,)),
    )
    main_window._refresh_install_operation_selector()
    recovery_tab = main_window.findChild(QWidget, "recovery_tab")
    recovery_group = main_window.findChild(QGroupBox, "recovery_inspection_group")

    assert recovery_tab is not None
    assert recovery_group is not None

    main_window._context_tabs.setCurrentWidget(recovery_tab)
    qapp.processEvents()
    assert recovery_group.isVisible() is True
    assert main_window._install_history_combo.isEnabled() is True
    assert main_window._inspect_recovery_button.isEnabled() is True


def test_main_window_recovery_surface_keeps_detail_group_tight_with_review_controls(
    main_window: MainWindow,
) -> None:
    recovery_group = main_window.findChild(QGroupBox, "recovery_inspection_group")
    recovery_output_group = main_window.findChild(QGroupBox, "recovery_output_group")

    assert recovery_group is not None
    assert recovery_output_group is not None
    assert (
        recovery_group.sizePolicy().verticalPolicy()
        == QSizePolicy.Policy.Maximum
    )
    assert recovery_output_group.parentWidget() is recovery_group


def test_main_window_local_detail_groups_start_hidden_until_they_have_useful_text(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    setup_tab = main_window._setup_scroll
    discovery_page = main_window.findChild(QWidget, "discovery_workspace_page")
    compare_tab = main_window.findChild(QWidget, "compare_tab")
    archive_page = main_window.findChild(QWidget, "archive_workspace_page")
    review_tab = main_window.findChild(QWidget, "plan_install_tab")
    recovery_tab = main_window.findChild(QWidget, "recovery_tab")

    assert discovery_page is not None
    assert compare_tab is not None
    assert archive_page is not None
    assert review_tab is not None
    assert recovery_tab is not None

    main_window._context_tabs.setCurrentWidget(discovery_page)
    qapp.processEvents()
    assert main_window._discovery_output_group.isHidden() is True

    main_window._context_tabs.setCurrentWidget(compare_tab)
    qapp.processEvents()
    assert main_window._compare_output_group.isHidden() is True

    main_window._context_tabs.setCurrentWidget(archive_page)
    qapp.processEvents()
    assert main_window._archive_output_group.isHidden() is True

    main_window._context_tabs.setCurrentWidget(setup_tab)
    qapp.processEvents()
    assert main_window._setup_output_group.isHidden() is True

    main_window._context_tabs.setCurrentWidget(review_tab)
    qapp.processEvents()
    assert main_window._review_output_group.isHidden() is True

    main_window._context_tabs.setCurrentWidget(recovery_tab)
    qapp.processEvents()
    assert main_window._recovery_output_group.isHidden() is True


def test_main_window_status_strip_labels_do_not_use_hardcoded_color_stylesheets(
    main_window: MainWindow,
) -> None:
    label_names = (
        "global_status_current_label",
        "global_status_blocking_label",
        "global_status_next_step_label",
    )
    for name in label_names:
        label = main_window.findChild(QLabel, name)
        assert label is not None
        stylesheet = label.styleSheet().strip().casefold()
        assert "color" not in stylesheet
        assert "#" not in stylesheet


def test_main_window_stylesheet_explicitly_themes_message_boxes(
    main_window: MainWindow,
) -> None:
    stylesheet = main_window.styleSheet()

    assert "QMessageBox" in stylesheet
    assert "background: #16191d;" in stylesheet
    assert "QMessageBox QLabel" in stylesheet


def test_main_window_top_context_surface_has_expected_panels(main_window: MainWindow) -> None:
    top_context_group = main_window.findChild(QGroupBox, "top_context_surface_group")
    status_strip_group = main_window.findChild(QGroupBox, "global_status_strip_group")
    brand_panel = main_window.findChild(QWidget, "top_context_brand_panel")
    brand_title = main_window.findChild(QLabel, "top_context_brand_title")
    operations_panel = main_window.findChild(QWidget, "top_context_operational_panel")
    environment_panel = main_window.findChild(QWidget, "top_context_environment_panel")
    runtime_panel = main_window.findChild(QWidget, "top_context_runtime_panel")
    active_context_panel = main_window.findChild(QWidget, "top_context_active_context_panel")

    assert top_context_group is not None
    assert status_strip_group is not None
    assert top_context_group is not status_strip_group
    assert top_context_group.isVisible()
    assert brand_panel is not None
    assert brand_title is not None
    assert operations_panel is not None
    assert environment_panel is not None
    assert runtime_panel is not None
    assert active_context_panel is not None


def test_main_window_uses_custom_workspace_nav_rail_with_hidden_tab_bar(
    main_window: MainWindow,
) -> None:
    context_tabs = main_window._context_tabs
    nav_rail = main_window.findChild(QFrame, "workspace_nav_rail")
    brand_panel = main_window.findChild(QFrame, "workspace_nav_brand_panel")
    brand_title = main_window.findChild(QLabel, "workspace_nav_brand_title")
    brand_subtitle = main_window.findChild(QLabel, "workspace_nav_brand_subtitle")
    brand_version = main_window.findChild(QLabel, "workspace_nav_brand_version")
    brand_release_status = main_window.findChild(QLabel, "workspace_nav_brand_release_status")
    footer_panel = main_window.findChild(QFrame, "workspace_nav_footer_panel")
    setup_button = main_window.findChild(QPushButton, "workspace_nav_button_setup")
    review_button = main_window.findChild(QPushButton, "workspace_nav_button_review")

    assert context_tabs is not None
    assert nav_rail is not None
    assert brand_panel is not None
    assert brand_title is not None
    assert brand_subtitle is not None
    assert brand_version is not None
    assert brand_release_status is not None
    assert footer_panel is not None
    assert setup_button is not None
    assert review_button is not None
    assert context_tabs.tabPosition() == QTabWidget.TabPosition.West
    assert context_tabs.tabBar().isHidden() is True
    assert setup_button.property("navRole") == "workspace"
    assert review_button.property("navRole") == "workspace"
    assert brand_title.text() == "Cinderleaf"
    assert brand_subtitle.text() == "for Stardew Valley"
    assert brand_version.text() == "Version 1.1.5"
    brand_layout = brand_panel.layout()
    assert brand_layout is not None
    assert brand_layout.itemAt(1).widget() is brand_title
    assert brand_layout.itemAt(2).widget() is brand_subtitle
    assert brand_layout.itemAt(3).widget() is brand_version
    assert brand_layout.itemAt(4).widget() is brand_release_status


def test_main_window_workspace_nav_buttons_drive_context_pages(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    context_tabs = main_window._context_tabs
    review_page = main_window._plan_install_tab
    review_button = main_window.findChild(QPushButton, "workspace_nav_button_review")
    compare_button = main_window.findChild(QPushButton, "workspace_nav_button_compare")

    assert context_tabs is not None
    assert review_page is not None
    assert review_button is not None
    assert compare_button is not None

    compare_button.click()
    qapp.processEvents()
    assert context_tabs.currentWidget() is main_window._compare_page
    assert compare_button.isChecked() is True

    review_button.click()
    qapp.processEvents()
    assert context_tabs.currentWidget() is review_page
    assert review_button.isChecked() is True


def test_main_window_top_context_value_labels_exist(main_window: MainWindow) -> None:
    label_names = (
        "top_context_environment_status_value",
        "top_context_runtime_nexus_value",
        "top_context_runtime_sandbox_launch_value",
        "top_context_scan_source_value",
        "top_context_install_destination_value",
    )
    for name in label_names:
        label = main_window.findChild(QLabel, name)
        assert label is not None
        assert label.text().strip() != ""


def test_main_window_scan_target_updates_top_context_scan_source_label(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    scan_target_combo = main_window._scan_target_combo
    scan_source_label = main_window.findChild(QLabel, "top_context_scan_source_value")

    assert scan_source_label is not None

    real_index = scan_target_combo.findData(SCAN_TARGET_CONFIGURED_REAL_MODS)
    sandbox_index = scan_target_combo.findData(SCAN_TARGET_SANDBOX_MODS)
    assert real_index >= 0
    assert sandbox_index >= 0

    main_window._mods_path_input.setText(r"C:\SDV\Mods")
    main_window._sandbox_mods_path_input.setText(r"C:\SDV\SandboxMods")
    qapp.processEvents()

    scan_target_combo.setCurrentIndex(real_index)
    qapp.processEvents()
    assert scan_source_label.text() == "REAL Mods selected"
    assert scan_source_label.toolTip() == r"C:\SDV\Mods"
    assert r"C:\SDV\Mods" not in scan_source_label.text()

    scan_target_combo.setCurrentIndex(sandbox_index)
    qapp.processEvents()
    assert scan_source_label.text() == "Sandbox Mods selected"
    assert scan_source_label.toolTip() == r"C:\SDV\SandboxMods"
    assert r"C:\SDV\SandboxMods" not in scan_source_label.text()


def test_main_window_scan_source_preview_updates_for_active_target_path_changes(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    scan_target_combo = main_window._scan_target_combo
    scan_source_label = main_window.findChild(QLabel, "top_context_scan_source_value")

    assert scan_source_label is not None

    real_index = scan_target_combo.findData(SCAN_TARGET_CONFIGURED_REAL_MODS)
    sandbox_index = scan_target_combo.findData(SCAN_TARGET_SANDBOX_MODS)
    assert real_index >= 0
    assert sandbox_index >= 0

    scan_target_combo.setCurrentIndex(real_index)
    main_window._mods_path_input.setText(r"C:\RealModsA")
    qapp.processEvents()
    assert scan_source_label.text() == "REAL Mods selected"
    assert scan_source_label.toolTip() == r"C:\RealModsA"
    assert r"C:\RealModsA" not in scan_source_label.text()

    scan_target_combo.setCurrentIndex(sandbox_index)
    main_window._sandbox_mods_path_input.setText(r"C:\SandboxModsA")
    qapp.processEvents()
    assert scan_source_label.text() == "Sandbox Mods selected"
    assert scan_source_label.toolTip() == r"C:\SandboxModsA"
    assert r"C:\SandboxModsA" not in scan_source_label.text()


def test_main_window_install_target_updates_context_archive_label_and_status(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    install_target_combo = main_window._install_target_combo
    install_context_label = main_window.findChild(QLabel, "top_context_install_destination_value")
    install_archive_label = main_window.findChild(QLabel, "plan_install_archive_label")
    status_label = main_window.findChild(QLabel, "global_status_current_label")

    assert install_context_label is not None
    assert install_archive_label is not None
    assert status_label is not None

    real_index = install_target_combo.findData(INSTALL_TARGET_CONFIGURED_REAL_MODS)
    sandbox_index = install_target_combo.findData(INSTALL_TARGET_SANDBOX_MODS)
    assert real_index >= 0
    assert sandbox_index >= 0

    main_window._mods_path_input.setText(r"C:\Game\Mods")
    main_window._sandbox_mods_path_input.setText(r"C:\Game\SandboxMods")
    qapp.processEvents()

    install_target_combo.setCurrentIndex(real_index)
    qapp.processEvents()
    install_target_combo.setCurrentIndex(sandbox_index)
    qapp.processEvents()
    assert (
        install_context_label.text()
        == "Sandbox Mods destination selected (recommended/test path)"
    )
    assert r"C:\Game\SandboxMods" not in install_context_label.text()
    assert install_context_label.toolTip() == r"C:\Game\SandboxMods"
    assert install_archive_label.text() == "Archive path for sandbox destination"
    assert "sandbox Mods path" in status_label.text()

    install_target_combo.setCurrentIndex(real_index)
    qapp.processEvents()
    assert (
        install_context_label.text()
        == "REAL game Mods destination selected (confirmation required)"
    )
    assert r"C:\Game\Mods" not in install_context_label.text()
    assert install_context_label.toolTip() == r"C:\Game\Mods"
    assert install_archive_label.text() == "Archive path for real Game Mods destination"
    assert "REAL game Mods path" in status_label.text()


def test_main_window_install_target_combo_uses_readability_contract(
    main_window: MainWindow,
) -> None:
    install_target_combo = main_window.findChild(QComboBox, "plan_install_target_combo")

    assert install_target_combo is not None
    assert 12 <= install_target_combo.minimumContentsLength() <= 24
    assert (
        install_target_combo.sizeAdjustPolicy()
        == QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    assert install_target_combo.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert install_target_combo.view().minimumWidth() > 0
    assert install_target_combo.itemText(0) == "Sandbox Mods destination (safe/test)"
    assert install_target_combo.itemText(1) == "Game Mods destination (real)"


def test_main_window_sandbox_dev_launch_starts_disabled_until_setup_is_sufficient(
    main_window: MainWindow,
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    launch_button = main_window.findChild(QPushButton, "launch_sandbox_dev_button")
    runtime_label = main_window.findChild(QLabel, "top_context_runtime_sandbox_launch_value")

    assert launch_button is not None
    assert runtime_label is not None
    assert launch_button.isEnabled() is False
    assert runtime_label.text() == "Needs game path"

    game_path = tmp_path / "Game"
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    _create_launchable_game_install_for_ui(game_path)
    real_mods.mkdir()
    sandbox_mods.mkdir()

    main_window._game_path_input.setText(str(game_path))
    main_window._mods_path_input.setText(str(real_mods))
    main_window._sandbox_mods_path_input.setText(str(sandbox_mods))
    qapp.processEvents()

    assert launch_button.isEnabled() is True
    assert runtime_label.text() == "Ready"
    assert str(sandbox_mods) in runtime_label.toolTip()


def test_main_window_sandbox_dev_launch_error_sets_status_without_launching(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.critical",
        lambda *args: captured.setdefault("critical_args", args),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "launch_game_sandbox_dev",
        lambda **_: (_ for _ in ()).throw(
            AppShellError("Sandbox Mods directory is required for sandbox dev launch.")
        ),
    )

    main_window._on_launch_sandbox_dev()

    runtime_label = main_window.findChild(QLabel, "top_context_runtime_sandbox_launch_value")
    assert captured.get("critical_args") is not None
    assert main_window._status_strip_label.text() == (
        "Sandbox Mods directory is required for sandbox dev launch."
    )
    assert runtime_label is not None
    assert runtime_label.text() == "Needs sandbox Mods path"


def test_main_window_sandbox_dev_launch_delegates_and_updates_status(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    game_path = tmp_path / "Game"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods = tmp_path / "RealMods"
    smapi_path = game_path / "StardewModdingAPI.exe"
    sandbox_mods.mkdir()
    real_mods.mkdir()
    game_path.mkdir()

    main_window._game_path_input.setText(str(game_path))
    main_window._mods_path_input.setText(str(real_mods))
    main_window._sandbox_mods_path_input.setText(str(sandbox_mods))

    def _fake_launch_game_sandbox_dev(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            pid=5150,
            executable_path=smapi_path,
            mods_path_override=sandbox_mods,
            steam_prelaunch_message="Steam was not running; start was attempted and game launch continued anyway.",
        )

    monkeypatch.setattr(main_window._shell_service, "launch_game_sandbox_dev", _fake_launch_game_sandbox_dev)
    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.critical", lambda *args: None)

    main_window._on_launch_sandbox_dev()

    runtime_label = main_window.findChild(QLabel, "top_context_runtime_sandbox_launch_value")
    assert captured == {
        "game_path_text": str(game_path),
        "sandbox_mods_path_text": str(sandbox_mods),
        "configured_mods_path_text": str(real_mods),
        "steam_auto_start_enabled": True,
        "existing_config": None,
    }
    assert "Sandbox dev launch started" in main_window._status_strip_label.text()
    assert str(sandbox_mods) in main_window._status_strip_label.text()
    assert "Steam was not running; start was attempted" in main_window._status_strip_label.text()
    assert runtime_label is not None
    assert runtime_label.text() == "Started"


def test_main_window_vanilla_launch_updates_status_with_steam_context(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_path = tmp_path / "Game"
    executable_path = game_path / "Stardew Valley.exe"
    game_path.mkdir()
    executable_path.write_text("", encoding="utf-8")
    main_window._game_path_input.setText(str(game_path))

    monkeypatch.setattr(
        main_window._shell_service,
        "launch_game_vanilla",
        lambda **_: SimpleNamespace(
            pid=1111,
            executable_path=executable_path,
            steam_prelaunch_message="Steam was already running.",
        ),
    )
    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.critical", lambda *args: None)

    main_window._on_launch_vanilla()

    assert "Vanilla launch started" in main_window._status_strip_label.text()
    assert "Steam was already running." in main_window._status_strip_label.text()


def test_main_window_vanilla_launch_uses_disabled_steam_toggle(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    game_path = tmp_path / "Game"
    executable_path = game_path / "Stardew Valley.exe"
    game_path.mkdir()
    executable_path.write_text("", encoding="utf-8")
    main_window._game_path_input.setText(str(game_path))
    main_window._steam_auto_start_checkbox.setChecked(False)

    def _fake_launch_game_vanilla(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            pid=3333,
            executable_path=executable_path,
            steam_prelaunch_message=(
                "Steam auto-start assistance is off; game launch continued without Steam prelaunch."
            ),
        )

    monkeypatch.setattr(main_window._shell_service, "launch_game_vanilla", _fake_launch_game_vanilla)
    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.critical", lambda *args: None)

    main_window._on_launch_vanilla()

    assert captured == {
        "game_path_text": str(game_path),
        "steam_auto_start_enabled": False,
        "existing_config": None,
    }
    assert "Steam auto-start assistance is off" in main_window._status_strip_label.text()


def test_main_window_smapi_launch_updates_status_when_steam_prelaunch_is_unavailable(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_path = tmp_path / "Game"
    executable_path = game_path / "StardewModdingAPI.exe"
    game_path.mkdir()
    executable_path.write_text("", encoding="utf-8")
    main_window._game_path_input.setText(str(game_path))

    monkeypatch.setattr(
        main_window._shell_service,
        "launch_game_smapi",
        lambda **_: SimpleNamespace(
            pid=2222,
            executable_path=executable_path,
            steam_prelaunch_message=(
                "Steam running status could not be confirmed; game launch continued anyway."
            ),
        ),
    )
    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.critical", lambda *args: None)

    main_window._on_launch_smapi()

    assert "SMAPI launch started" in main_window._status_strip_label.text()
    assert "Steam running status could not be confirmed" in main_window._status_strip_label.text()


def test_main_window_sandbox_sync_action_is_hidden_and_inert_without_selection(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    sync_actions = main_window.findChild(QWidget, "inventory_sandbox_sync_actions")
    sync_button = main_window.findChild(QPushButton, "inventory_sync_selected_to_sandbox_button")

    assert sync_actions is not None
    assert sync_button is not None
    assert sync_actions.isVisible() is False
    assert sync_button.isEnabled() is False

    main_window._on_sync_selected_mods_to_sandbox()
    qapp.processEvents()

    assert (
        main_window._status_strip_label.text()
        == "Select at least one installed mod row to sync to sandbox."
    )


def test_main_window_sandbox_sync_button_enables_only_for_real_scan_with_valid_paths_and_selection(
    main_window: MainWindow,
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    (real_mods / "AlphaMod").mkdir()

    inventory = _inventory_for_sandbox_sync_ui_tests(real_mods)
    sync_actions = main_window.findChild(QWidget, "inventory_sandbox_sync_actions")
    sync_button = main_window.findChild(QPushButton, "inventory_sync_selected_to_sandbox_button")
    scan_target_combo = main_window._scan_target_combo

    assert sync_actions is not None
    assert sync_button is not None

    main_window._mods_path_input.setText(str(real_mods))
    main_window._sandbox_mods_path_input.setText(str(sandbox_mods))
    main_window._render_inventory(inventory)
    alpha_row = _find_mod_row(main_window._mods_table, "Alpha Mod")
    assert alpha_row >= 0
    main_window._mods_table.setCurrentCell(alpha_row, 0)
    qapp.processEvents()

    assert sync_actions.isVisible() is True
    assert sync_button.isEnabled() is True
    assert "Ready to sync 1 selected mod(s)" in sync_button.toolTip()

    sandbox_index = scan_target_combo.findData(SCAN_TARGET_SANDBOX_MODS)
    assert sandbox_index >= 0
    scan_target_combo.setCurrentIndex(sandbox_index)
    qapp.processEvents()

    assert sync_button.isEnabled() is False
    assert "only works while scanning the configured real Mods path" in sync_button.toolTip()


def test_main_window_sandbox_sync_delegates_and_updates_status_and_details(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    source_mod = real_mods / "AlphaMod"
    target_mod = sandbox_mods / "AlphaMod"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    source_mod.mkdir()
    inventory = _inventory_for_sandbox_sync_ui_tests(real_mods)
    sync_button = main_window.findChild(QPushButton, "inventory_sync_selected_to_sandbox_button")
    captured: dict[str, object] = {}

    assert sync_button is not None

    main_window._mods_path_input.setText(str(real_mods))
    main_window._sandbox_mods_path_input.setText(str(sandbox_mods))
    main_window._render_inventory(inventory)
    alpha_row = _find_mod_row(main_window._mods_table, "Alpha Mod")
    assert alpha_row >= 0
    main_window._mods_table.setCurrentCell(alpha_row, 0)
    qapp.processEvents()

    def _fake_sync_installed_mods_to_sandbox(**kwargs):
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            real_mods_path=real_mods,
            sandbox_mods_path=sandbox_mods,
            source_mod_paths=(source_mod,),
            synced_target_paths=(target_mod,),
        )

    def _run_immediately(
        *,
        operation_name: str,
        running_label: str,
        started_status: str,
        error_title: str,
        task_fn,
        on_success,
    ) -> None:
        captured["operation_name"] = operation_name
        captured["running_label"] = running_label
        captured["started_status"] = started_status
        captured["error_title"] = error_title
        on_success(task_fn())

    monkeypatch.setattr(
        main_window._shell_service,
        "sync_installed_mods_to_sandbox",
        _fake_sync_installed_mods_to_sandbox,
    )
    monkeypatch.setattr(main_window, "_run_background_operation", _run_immediately)

    sync_button.click()
    qapp.processEvents()

    assert captured["operation_name"] == "Sandbox sync"
    assert captured["running_label"] == "Sandbox sync"
    assert captured["error_title"] == "Sandbox sync failed"
    assert "Syncing 1 selected mod(s)" in str(captured["started_status"])
    assert captured["kwargs"] == {
        "configured_mods_path_text": str(real_mods),
        "sandbox_mods_path_text": str(sandbox_mods),
        "selected_mod_folder_paths_text": (str(source_mod),),
        "existing_config": None,
    }
    assert main_window._status_strip_label.text() == "Sandbox sync complete: 1 mod(s) copied."
    assert "Sandbox sync result" in main_window._findings_box.toPlainText()
    assert str(target_mod) in main_window._findings_box.toPlainText()


def test_main_window_sandbox_sync_conflict_sets_clear_status(
    main_window: MainWindow,
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    source_mod = real_mods / "AlphaMod"
    target_mod = sandbox_mods / "AlphaMod"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    source_mod.mkdir()
    target_mod.mkdir()
    inventory = _inventory_for_sandbox_sync_ui_tests(real_mods)
    sync_button = main_window.findChild(QPushButton, "inventory_sync_selected_to_sandbox_button")

    assert sync_button is not None

    main_window._mods_path_input.setText(str(real_mods))
    main_window._sandbox_mods_path_input.setText(str(sandbox_mods))
    main_window._render_inventory(inventory)
    alpha_row = _find_mod_row(main_window._mods_table, "Alpha Mod")
    assert alpha_row >= 0
    main_window._mods_table.setCurrentCell(alpha_row, 0)
    qapp.processEvents()

    assert sync_button.isEnabled() is False

    main_window._on_sync_selected_mods_to_sandbox()
    qapp.processEvents()

    assert "sandbox target already exists for AlphaMod" in main_window._status_strip_label.text()


def test_main_window_sandbox_promotion_button_enables_only_for_sandbox_scan_context(
    main_window: MainWindow,
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    (sandbox_mods / "AlphaMod").mkdir()

    inventory = _inventory_for_sandbox_sync_ui_tests(sandbox_mods)
    sync_button = main_window.findChild(QPushButton, "inventory_sync_selected_to_sandbox_button")
    promote_button = main_window.findChild(
        QPushButton, "inventory_promote_selected_to_real_button"
    )
    scan_target_combo = main_window._scan_target_combo

    assert sync_button is not None
    assert promote_button is not None

    main_window._mods_path_input.setText(str(real_mods))
    main_window._sandbox_mods_path_input.setText(str(sandbox_mods))
    main_window._render_inventory(inventory)
    alpha_row = _find_mod_row(main_window._mods_table, "Alpha Mod")
    assert alpha_row >= 0

    sandbox_index = scan_target_combo.findData(SCAN_TARGET_SANDBOX_MODS)
    assert sandbox_index >= 0
    scan_target_combo.setCurrentIndex(sandbox_index)
    main_window._mods_table.setCurrentCell(alpha_row, 0)
    qapp.processEvents()

    assert sync_button.isEnabled() is False
    assert promote_button.isEnabled() is True
    assert "Ready to review 1 selected mod(s)" in promote_button.toolTip()

    real_index = scan_target_combo.findData(SCAN_TARGET_CONFIGURED_REAL_MODS)
    assert real_index >= 0
    scan_target_combo.setCurrentIndex(real_index)
    qapp.processEvents()

    assert promote_button.isEnabled() is False
    assert "only works while scanning sandbox Mods" in promote_button.toolTip()


def test_main_window_sandbox_promotion_is_inert_without_selection(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    main_window._on_promote_selected_mods_to_real()
    qapp.processEvents()

    assert (
        main_window._status_strip_label.text()
        == "Select at least one installed sandbox mod row to promote."
    )


def test_main_window_sandbox_promotion_delegates_after_confirmation_and_updates_ui(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    source_mod = sandbox_mods / "AlphaMod"
    promoted_target = real_mods / "AlphaMod"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    source_mod.mkdir()
    inventory = _inventory_for_sandbox_sync_ui_tests(sandbox_mods)
    promote_button = main_window.findChild(
        QPushButton, "inventory_promote_selected_to_real_button"
    )
    captured: dict[str, object] = {}

    assert promote_button is not None

    main_window._mods_path_input.setText(str(real_mods))
    main_window._sandbox_mods_path_input.setText(str(sandbox_mods))
    main_window._render_inventory(inventory)
    sandbox_index = main_window._scan_target_combo.findData(SCAN_TARGET_SANDBOX_MODS)
    assert sandbox_index >= 0
    main_window._scan_target_combo.setCurrentIndex(sandbox_index)
    alpha_row = _find_mod_row(main_window._mods_table, "Alpha Mod")
    assert alpha_row >= 0
    main_window._mods_table.setCurrentCell(alpha_row, 0)
    qapp.processEvents()

    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.question",
        lambda parent, title, text: (
            captured.update({"question_title": title, "question_text": text})
            or QMessageBox.StandardButton.Yes
        ),
    )

    def _fake_preview(**kwargs):
        captured["preview_kwargs"] = kwargs
        return SimpleNamespace(
            plan=SimpleNamespace(
                entries=(SimpleNamespace(action="install_new", target_path=promoted_target),)
            ),
            review=SimpleNamespace(
                allowed=True,
                requires_explicit_approval=True,
                message="Real Mods install targets 1 entry in review.",
                summary=SimpleNamespace(
                    total_entry_count=1,
                    destination_mods_path=real_mods,
                    archive_path=real_mods.parent / ".sdvmm-real-archive",
                    has_existing_targets_to_replace=False,
                    has_archive_writes=False,
                ),
            ),
            real_mods_path=real_mods,
            sandbox_mods_path=sandbox_mods,
            archive_path=real_mods.parent / ".sdvmm-real-archive",
            source_mod_paths=(source_mod,),
        )

    def _fake_execute(preview):
        captured["execute_preview"] = preview
        return SimpleNamespace(
            destination_kind=SCAN_TARGET_CONFIGURED_REAL_MODS,
            real_mods_path=real_mods,
            sandbox_mods_path=sandbox_mods,
            archive_path=real_mods.parent / ".sdvmm-real-archive",
            source_mod_paths=(source_mod,),
            promoted_target_paths=(promoted_target,),
            archived_target_paths=tuple(),
            replaced_target_paths=tuple(),
            scan_context_path=real_mods,
            inventory=_inventory_for_sandbox_sync_ui_tests(real_mods),
        )

    def _run_immediately(
        *,
        operation_name: str,
        running_label: str,
        started_status: str,
        error_title: str,
        task_fn,
        on_success,
    ) -> None:
        captured["operation_name"] = operation_name
        captured["running_label"] = running_label
        captured["started_status"] = started_status
        captured["error_title"] = error_title
        on_success(task_fn())

    monkeypatch.setattr(
        main_window._shell_service,
        "build_sandbox_mods_promotion_preview",
        _fake_preview,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_sandbox_mods_promotion_preview",
        _fake_execute,
    )
    monkeypatch.setattr(main_window, "_run_background_operation", _run_immediately)

    promote_button.click()
    qapp.processEvents()

    assert captured["operation_name"] == "Sandbox promotion"
    assert captured["running_label"] == "Sandbox promotion"
    assert captured["error_title"] == "Sandbox promotion failed"
    assert "Promoting 1 selected mod(s)" in str(captured["started_status"])
    assert captured["preview_kwargs"] == {
        "configured_mods_path_text": str(real_mods),
        "sandbox_mods_path_text": str(sandbox_mods),
        "real_archive_path_text": "",
        "selected_mod_folder_paths_text": (str(source_mod),),
        "existing_config": None,
    }
    assert captured["question_title"] == "Review sandbox promotion to REAL Mods"
    assert "Archive-aware replace: 0" in str(captured["question_text"])
    assert main_window._current_scan_target() == SCAN_TARGET_SANDBOX_MODS
    assert main_window._status_strip_label.text() == "Sandbox promotion complete: 1 mod(s) promoted into REAL Mods."
    assert "Sandbox promotion result" in main_window._findings_box.toPlainText()
    assert str(promoted_target) in main_window._findings_box.toPlainText()
    assert "Current scan context was left unchanged" in main_window._findings_box.toPlainText()


def test_main_window_sandbox_promotion_conflict_review_stays_enabled_and_describes_archive_replace(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    real_mods = tmp_path / "RealMods"
    sandbox_mods = tmp_path / "SandboxMods"
    source_mod = sandbox_mods / "AlphaMod"
    promoted_target = real_mods / "AlphaMod"
    real_mods.mkdir()
    sandbox_mods.mkdir()
    source_mod.mkdir()
    promoted_target.mkdir()
    inventory = _inventory_for_sandbox_sync_ui_tests(sandbox_mods)
    promote_button = main_window.findChild(
        QPushButton, "inventory_promote_selected_to_real_button"
    )

    assert promote_button is not None

    main_window._mods_path_input.setText(str(real_mods))
    main_window._sandbox_mods_path_input.setText(str(sandbox_mods))
    main_window._render_inventory(inventory)
    sandbox_index = main_window._scan_target_combo.findData(SCAN_TARGET_SANDBOX_MODS)
    assert sandbox_index >= 0
    main_window._scan_target_combo.setCurrentIndex(sandbox_index)
    alpha_row = _find_mod_row(main_window._mods_table, "Alpha Mod")
    assert alpha_row >= 0
    main_window._mods_table.setCurrentCell(alpha_row, 0)
    qapp.processEvents()

    captured: dict[str, str] = {}

    def fake_question(parent, title, text):
        captured["title"] = title
        captured["text"] = text
        return QMessageBox.StandardButton.No

    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.question", fake_question)

    assert promote_button.isEnabled() is True
    assert "archive-aware live replacement" in promote_button.toolTip()

    main_window._on_promote_selected_mods_to_real()
    qapp.processEvents()

    assert captured["title"] == "Review sandbox promotion to REAL Mods"
    assert "Archive-aware replace: 1" in captured["text"]
    assert "Conflicting live targets" in captured["text"]
    assert "AlphaMod" in captured["text"]
    assert main_window._status_strip_label.text() == "Sandbox promotion cancelled."


def test_main_window_inventory_update_actionability_filter_exists_with_default_all(
    main_window: MainWindow,
) -> None:
    action_filter = main_window.findChild(QComboBox, "inventory_update_actionability_filter_combo")

    assert action_filter is not None
    assert action_filter.count() == 3
    assert action_filter.itemText(0) == "all"
    assert action_filter.itemText(1) == "actionable"
    assert action_filter.itemText(2) == "blocked"
    assert action_filter.currentData() == "all"


def test_main_window_inventory_selected_row_update_guidance_line_exists_and_defaults_neutral(
    main_window: MainWindow,
) -> None:
    guidance_label = main_window.findChild(QLabel, "inventory_update_guidance_label")
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    open_remote_button = main_window.findChild(
        QPushButton, "inventory_open_remote_page_button"
    )

    assert guidance_label is not None
    assert blocked_detail_label is not None
    assert open_remote_button is not None
    assert guidance_label.text() == "Select an installed mod row to see update guidance."
    assert blocked_detail_label.text() == ""
    assert blocked_detail_label.isVisible() is False
    assert open_remote_button.isEnabled() is False


def test_main_window_inventory_selected_row_guidance_shows_actionable_message(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    actionable_row = _find_mod_row(main_window._mods_table, "Alpha Mod")
    assert actionable_row >= 0
    main_window._mods_table.setCurrentCell(actionable_row, 0)
    qapp.processEvents()

    guidance_text = main_window._inventory_update_guidance_label.text()
    open_remote_button = main_window.findChild(
        QPushButton, "inventory_open_remote_page_button"
    )
    assert (
        "Alpha Mod: update available. Next step: use Open remote page for this selected row."
        == guidance_text
    )
    assert open_remote_button is not None
    assert open_remote_button.isEnabled() is True
    assert "Alpha Mod" in open_remote_button.toolTip()


def test_main_window_inventory_selected_row_guidance_shows_blocked_reason(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    guidance_text = main_window._inventory_update_guidance_label.text()
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    open_remote_button = main_window.findChild(
        QPushButton, "inventory_open_remote_page_button"
    )
    assert (
        guidance_text
        == "Beta Mod: No remote link available. Open remote page is unavailable for this row."
    )
    assert blocked_detail_label is not None
    assert blocked_detail_label.isVisible() is True
    assert blocked_detail_label.text() == "Update source diagnostics: missing update key."
    assert open_remote_button is not None
    assert open_remote_button.isEnabled() is False
    assert "No remote link available." in open_remote_button.toolTip()


def test_main_window_inventory_diagnostics_hides_when_blocked_reason_is_generic(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    blocked_row = _find_mod_row(main_window._mods_table, "Alpha Mod")
    assert blocked_row >= 0
    beta_item = main_window._mods_table.item(blocked_row, 0)
    status_item = main_window._mods_table.item(blocked_row, 4)
    assert beta_item is not None
    assert status_item is not None
    status_item.setText("blocked_custom")
    beta_item.setData(_ROLE_UPDATE_BLOCK_REASON, "Temporarily blocked.")
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    assert (
        main_window._inventory_update_guidance_label.text()
        == "Alpha Mod: Temporarily blocked. Open remote page is unavailable for this row."
    )
    assert blocked_detail_label.text() == ""
    assert blocked_detail_label.isVisible() is False


def test_main_window_inventory_diagnostics_shows_update_key_issue_category(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    beta_item = main_window._mods_table.item(blocked_row, 0)
    assert beta_item is not None
    status_data = beta_item.data(_ROLE_MOD_UPDATE_STATUS)
    assert isinstance(status_data, ModUpdateStatus)
    beta_item.setData(
        _ROLE_MOD_UPDATE_STATUS,
        replace(status_data, update_source_diagnostic=UNSUPPORTED_UPDATE_KEY_FORMAT),
    )
    beta_item.setData(
        _ROLE_UPDATE_BLOCK_REASON,
        "Temporarily blocked by update diagnostics.",
    )
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    assert blocked_detail_label.isVisible() is True
    assert (
        blocked_detail_label.text()
        == "Update source diagnostics: unsupported update key format."
    )


def test_main_window_inventory_diagnostics_use_typed_field_not_block_reason_text(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    beta_item = main_window._mods_table.item(blocked_row, 0)
    assert beta_item is not None
    status_data = beta_item.data(_ROLE_MOD_UPDATE_STATUS)
    assert isinstance(status_data, ModUpdateStatus)
    beta_item.setData(
        _ROLE_MOD_UPDATE_STATUS,
        replace(status_data, update_source_diagnostic=MISSING_UPDATE_KEY),
    )
    beta_item.setData(
        _ROLE_UPDATE_BLOCK_REASON,
        "Unsupported update key format: custom://alpha",
    )
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    assert (
        blocked_detail_label.text()
        == "Update source diagnostics: missing update key."
    )


def test_main_window_inventory_guidance_surfaces_persisted_local_private_intent(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    open_remote_button = main_window.findChild(
        QPushButton, "inventory_open_remote_page_button"
    )
    assert blocked_detail_label is not None
    assert open_remote_button is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    main_window._shell_service.set_update_source_intent("Sample.Beta", "local_private_mod")
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    assert (
        main_window._inventory_update_guidance_label.text()
        == "Beta Mod: marked as local/private in saved update-source intent. "
        "Open remote page is unavailable for this row."
    )
    assert blocked_detail_label.isVisible() is True
    assert (
        blocked_detail_label.text()
        == "Update source intent: local/private mod is recorded in app state."
    )
    assert open_remote_button.isEnabled() is False
    assert "local/private" in open_remote_button.toolTip()


def test_main_window_inventory_guidance_surfaces_persisted_no_tracking_intent(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    main_window._shell_service.set_update_source_intent("Sample.Beta", "no_tracking")
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    assert (
        main_window._inventory_update_guidance_label.text()
        == "Beta Mod: update tracking is intentionally disabled in saved update-source intent. "
        "Open remote page is unavailable for this row."
    )
    assert blocked_detail_label.isVisible() is True
    assert (
        blocked_detail_label.text()
        == "Update source intent: no-tracking is recorded in app state."
    )


def test_main_window_inventory_guidance_surfaces_persisted_manual_source_intent(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    main_window._shell_service.set_update_source_intent(
        "Sample.Beta",
        "manual_source_association",
        manual_provider="nexus",
        manual_source_key="12345",
        manual_source_page_url="https://example.test/mods/12345",
    )
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    assert (
        main_window._inventory_update_guidance_label.text()
        == "Beta Mod: manual source association is recorded in saved update-source intent. "
        "Open remote page is unavailable for this row."
    )
    assert blocked_detail_label.isVisible() is True
    assert (
        blocked_detail_label.text()
        == "Update source intent: manual source association is recorded in app state (provider: nexus)."
    )


def test_main_window_inventory_guidance_falls_back_to_typed_diagnostics_without_overlay(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    assert (
        main_window._inventory_update_guidance_label.text()
        == "Beta Mod: No remote link available. Open remote page is unavailable for this row."
    )
    assert blocked_detail_label.isVisible() is True
    assert blocked_detail_label.text() == "Update source diagnostics: missing update key."


def test_main_window_inventory_update_source_intent_actions_are_hidden_and_inert_without_selection(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    actions_widget = main_window.findChild(QWidget, "inventory_update_source_intent_actions")
    mark_local_private_button = main_window.findChild(
        QPushButton, "inventory_mark_local_private_button"
    )
    disable_tracking_button = main_window.findChild(
        QPushButton, "inventory_disable_tracking_button"
    )
    clear_source_intent_button = main_window.findChild(
        QPushButton, "inventory_clear_source_intent_button"
    )

    assert actions_widget is not None
    assert mark_local_private_button is not None
    assert disable_tracking_button is not None
    assert clear_source_intent_button is not None
    assert actions_widget.isVisible() is False

    main_window._on_mark_selected_mod_local_private()
    qapp.processEvents()

    assert main_window._shell_service.get_update_source_intent("Sample.Beta") is None
    assert (
        main_window._status_strip_label.text()
        == "Select a blocked installed mod row to manage saved source intent."
    )


def test_main_window_inventory_selected_row_can_be_marked_local_private(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    actions_widget = main_window.findChild(QWidget, "inventory_update_source_intent_actions")
    mark_local_private_button = main_window.findChild(
        QPushButton, "inventory_mark_local_private_button"
    )
    clear_source_intent_button = main_window.findChild(
        QPushButton, "inventory_clear_source_intent_button"
    )
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    open_remote_button = main_window.findChild(
        QPushButton, "inventory_open_remote_page_button"
    )

    assert actions_widget is not None
    assert mark_local_private_button is not None
    assert clear_source_intent_button is not None
    assert blocked_detail_label is not None
    assert open_remote_button is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    assert actions_widget.isVisible() is True
    assert mark_local_private_button.isEnabled() is True
    assert clear_source_intent_button.isEnabled() is False

    mark_local_private_button.click()
    qapp.processEvents()

    saved_intent = main_window._shell_service.get_update_source_intent("Sample.Beta")
    assert saved_intent is not None
    assert saved_intent.intent_state == "local_private_mod"
    assert (
        main_window._inventory_update_guidance_label.text()
        == "Beta Mod: marked as local/private in saved update-source intent. "
        "Open remote page is unavailable for this row."
    )
    assert blocked_detail_label.isVisible() is True
    assert (
        blocked_detail_label.text()
        == "Update source intent: local/private mod is recorded in app state."
    )
    assert clear_source_intent_button.isEnabled() is True
    assert open_remote_button.isEnabled() is False


def test_main_window_inventory_selected_row_can_disable_tracking(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    disable_tracking_button = main_window.findChild(
        QPushButton, "inventory_disable_tracking_button"
    )
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )

    assert disable_tracking_button is not None
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    assert disable_tracking_button.isEnabled() is True

    disable_tracking_button.click()
    qapp.processEvents()

    saved_intent = main_window._shell_service.get_update_source_intent("Sample.Beta")
    assert saved_intent is not None
    assert saved_intent.intent_state == "no_tracking"
    assert (
        main_window._inventory_update_guidance_label.text()
        == "Beta Mod: update tracking is intentionally disabled in saved update-source intent. "
        "Open remote page is unavailable for this row."
    )
    assert blocked_detail_label.isVisible() is True
    assert (
        blocked_detail_label.text()
        == "Update source intent: no-tracking is recorded in app state."
    )


def test_main_window_inventory_manual_source_action_is_available_only_for_selected_blocked_row(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    actions_widget = main_window.findChild(QWidget, "inventory_update_source_intent_actions")
    manual_source_button = main_window.findChild(
        QPushButton, "inventory_manual_source_association_button"
    )

    assert actions_widget is not None
    assert manual_source_button is not None
    assert actions_widget.isVisible() is False

    main_window._render_inventory(inventory)

    not_checked_row = _find_mod_row(main_window._mods_table, "Gamma Mod")
    assert not_checked_row >= 0
    main_window._mods_table.setCurrentCell(not_checked_row, 0)
    qapp.processEvents()
    assert actions_widget.isVisible() is True
    assert manual_source_button.isEnabled() is False

    main_window._apply_update_report(report)

    actionable_row = _find_mod_row(main_window._mods_table, "Alpha Mod")
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert actionable_row >= 0
    assert blocked_row >= 0

    main_window._mods_table.setCurrentCell(actionable_row, 0)
    qapp.processEvents()
    assert actions_widget.isVisible() is True
    assert manual_source_button.isEnabled() is False

    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()
    assert manual_source_button.isEnabled() is True


def test_main_window_inventory_selected_row_can_save_manual_source_association(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    manual_source_button = main_window.findChild(
        QPushButton, "inventory_manual_source_association_button"
    )
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    open_remote_button = main_window.findChild(
        QPushButton, "inventory_open_remote_page_button"
    )

    assert manual_source_button is not None
    assert blocked_detail_label is not None
    assert open_remote_button is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    monkeypatch.setattr(
        main_window,
        "_prompt_selected_mod_manual_source_intent",
        lambda **_: ("nexus", "12345", "https://example.test/mods/12345"),
    )

    manual_source_button.click()
    qapp.processEvents()

    saved_intent = main_window._shell_service.get_update_source_intent("Sample.Beta")
    assert saved_intent is not None
    assert saved_intent.intent_state == "manual_source_association"
    assert saved_intent.manual_provider == "nexus"
    assert saved_intent.manual_source_key == "12345"
    assert saved_intent.manual_source_page_url == "https://example.test/mods/12345"
    assert (
        main_window._inventory_update_guidance_label.text()
        == "Beta Mod: manual source association is recorded in saved update-source intent. "
        "Open remote page is unavailable for this row."
    )
    assert blocked_detail_label.isVisible() is True
    assert (
        blocked_detail_label.text()
        == "Update source intent: manual source association is recorded in app state (provider: nexus)."
    )
    assert open_remote_button.isEnabled() is False
    assert (
        main_window._status_strip_label.text()
        == "Saved manual source association for Sample.Beta (provider: nexus)."
    )


def test_main_window_inventory_manual_source_association_rejects_empty_required_fields(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    manual_source_button = main_window.findChild(
        QPushButton, "inventory_manual_source_association_button"
    )
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )

    assert manual_source_button is not None
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    monkeypatch.setattr(
        main_window,
        "_prompt_selected_mod_manual_source_intent",
        lambda **_: ("", "12345", None),
    )

    manual_source_button.click()
    qapp.processEvents()

    assert main_window._shell_service.get_update_source_intent("Sample.Beta") is None
    assert (
        main_window._status_strip_label.text()
        == "Manual source association requires provider and source key."
    )
    assert (
        main_window._inventory_update_guidance_label.text()
        == "Beta Mod: No remote link available. Open remote page is unavailable for this row."
    )
    assert blocked_detail_label.isVisible() is True
    assert blocked_detail_label.text() == "Update source diagnostics: missing update key."


def test_main_window_inventory_manual_source_association_can_be_cleared_back_to_typed_diagnostics(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    manual_source_button = main_window.findChild(
        QPushButton, "inventory_manual_source_association_button"
    )
    clear_source_intent_button = main_window.findChild(
        QPushButton, "inventory_clear_source_intent_button"
    )
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )

    assert manual_source_button is not None
    assert clear_source_intent_button is not None
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    monkeypatch.setattr(
        main_window,
        "_prompt_selected_mod_manual_source_intent",
        lambda **_: ("nexus", "12345", None),
    )

    manual_source_button.click()
    qapp.processEvents()
    assert clear_source_intent_button.isEnabled() is True

    clear_source_intent_button.click()
    qapp.processEvents()

    assert main_window._shell_service.get_update_source_intent("Sample.Beta") is None
    assert (
        main_window._inventory_update_guidance_label.text()
        == "Beta Mod: No remote link available. Open remote page is unavailable for this row."
    )
    assert blocked_detail_label.isVisible() is True
    assert blocked_detail_label.text() == "Update source diagnostics: missing update key."
    assert clear_source_intent_button.isEnabled() is False


def test_main_window_inventory_clearing_saved_source_intent_restores_typed_diagnostics(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    clear_source_intent_button = main_window.findChild(
        QPushButton, "inventory_clear_source_intent_button"
    )
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )

    assert clear_source_intent_button is not None
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    main_window._shell_service.set_update_source_intent("Sample.Beta", "local_private_mod")
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()

    assert clear_source_intent_button.isEnabled() is True

    clear_source_intent_button.click()
    qapp.processEvents()

    assert main_window._shell_service.get_update_source_intent("Sample.Beta") is None
    assert (
        main_window._inventory_update_guidance_label.text()
        == "Beta Mod: No remote link available. Open remote page is unavailable for this row."
    )
    assert blocked_detail_label.isVisible() is True
    assert blocked_detail_label.text() == "Update source diagnostics: missing update key."
    assert clear_source_intent_button.isEnabled() is False


def test_main_window_inventory_diagnostics_clears_for_actionable_selection(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    actionable_row = _find_mod_row(main_window._mods_table, "Alpha Mod")
    assert blocked_row >= 0
    assert actionable_row >= 0

    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()
    assert blocked_detail_label.isVisible() is True

    main_window._mods_table.setCurrentCell(actionable_row, 0)
    qapp.processEvents()
    assert blocked_detail_label.text() == ""
    assert blocked_detail_label.isVisible() is False


def test_main_window_inventory_diagnostics_clears_for_not_checked_selection(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    not_checked_row = _find_mod_row(main_window._mods_table, "Gamma Mod")
    assert not_checked_row >= 0
    main_window._mods_table.setCurrentCell(not_checked_row, 0)
    qapp.processEvents()

    assert blocked_detail_label.text() == ""
    assert blocked_detail_label.isVisible() is False


def test_main_window_inventory_diagnostics_clears_when_no_row_selected(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    blocked_detail_label = main_window.findChild(
        QLabel, "inventory_update_blocked_detail_label"
    )
    assert blocked_detail_label is not None

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert blocked_row >= 0
    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()
    assert blocked_detail_label.isVisible() is True

    main_window._mods_table.clearSelection()
    main_window._mods_table.setCurrentCell(-1, -1)
    qapp.processEvents()

    assert blocked_detail_label.text() == ""
    assert blocked_detail_label.isVisible() is False


def test_main_window_inventory_selected_row_guidance_shows_not_checked_prompt(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()

    main_window._render_inventory(inventory)
    not_checked_row = _find_mod_row(main_window._mods_table, "Gamma Mod")
    assert not_checked_row >= 0
    main_window._mods_table.setCurrentCell(not_checked_row, 0)
    qapp.processEvents()

    guidance_text = main_window._inventory_update_guidance_label.text()
    open_remote_button = main_window.findChild(
        QPushButton, "inventory_open_remote_page_button"
    )
    assert (
        guidance_text
        == "Gamma Mod: run Check updates to evaluate update actionability. "
        "Open remote page stays disabled until an actionable row is selected."
    )
    assert open_remote_button is not None
    assert open_remote_button.isEnabled() is False


def test_main_window_inventory_open_remote_button_state_updates_with_selection_changes(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()
    open_remote_button = main_window.findChild(
        QPushButton, "inventory_open_remote_page_button"
    )

    assert open_remote_button is not None
    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    qapp.processEvents()

    actionable_row = _find_mod_row(main_window._mods_table, "Alpha Mod")
    blocked_row = _find_mod_row(main_window._mods_table, "Beta Mod")
    assert actionable_row >= 0
    assert blocked_row >= 0

    main_window._mods_table.setCurrentCell(actionable_row, 0)
    qapp.processEvents()
    assert open_remote_button.isEnabled() is True

    main_window._mods_table.setCurrentCell(blocked_row, 0)
    qapp.processEvents()
    assert open_remote_button.isEnabled() is False

    main_window._mods_table.clearSelection()
    main_window._mods_table.setCurrentCell(-1, -1)
    qapp.processEvents()
    assert open_remote_button.isEnabled() is False


def test_main_window_inventory_update_actionability_filter_modes_show_expected_subsets(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    qapp.processEvents()

    assert _visible_row_count(main_window._mods_table) == 3

    main_window._mods_update_actionability_filter_combo.setCurrentText("actionable")
    qapp.processEvents()
    assert _visible_row_count(main_window._mods_table) == 1
    assert _visible_mod_names(main_window._mods_table) == ("Alpha Mod",)

    main_window._mods_update_actionability_filter_combo.setCurrentText("blocked")
    qapp.processEvents()
    assert _visible_row_count(main_window._mods_table) == 2
    assert set(_visible_mod_names(main_window._mods_table)) == {"Beta Mod", "Gamma Mod"}


def test_main_window_inventory_blocked_update_rows_show_non_empty_reason_tooltip(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    main_window._mods_update_actionability_filter_combo.setCurrentText("blocked")
    qapp.processEvents()

    for row in range(main_window._mods_table.rowCount()):
        if main_window._mods_table.isRowHidden(row):
            continue
        status_item = main_window._mods_table.item(row, 4)
        assert status_item is not None
        assert status_item.toolTip().strip() != ""


def test_main_window_inventory_search_filter_still_works_with_update_actionability_filter(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inventory = _inventory_for_update_actionability_tests()
    report = _update_report_for_update_actionability_tests()

    main_window._render_inventory(inventory)
    main_window._apply_update_report(report)
    qapp.processEvents()

    main_window._mods_filter_input.setText("Alpha")
    qapp.processEvents()
    assert _visible_row_count(main_window._mods_table) == 1
    assert _visible_mod_names(main_window._mods_table) == ("Alpha Mod",)

    main_window._mods_update_actionability_filter_combo.setCurrentText("blocked")
    qapp.processEvents()
    assert _visible_row_count(main_window._mods_table) == 0

    main_window._mods_filter_input.clear()
    qapp.processEvents()
    assert _visible_row_count(main_window._mods_table) == 2
    assert set(_visible_mod_names(main_window._mods_table)) == {"Beta Mod", "Gamma Mod"}


def test_main_window_sandbox_archive_autofill_only_when_empty(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    install_target_combo = main_window._install_target_combo
    sandbox_index = install_target_combo.findData(INSTALL_TARGET_SANDBOX_MODS)
    assert sandbox_index >= 0

    install_target_combo.setCurrentIndex(sandbox_index)
    main_window._sandbox_archive_path_input.clear()
    main_window._sandbox_mods_path_input.setText(r"C:\Game\SandboxMods")
    qapp.processEvents()

    assert main_window._sandbox_archive_path_input.text() == r"C:\Game\.sdvmm-sandbox-archive"

    main_window._sandbox_archive_path_input.setText(r"C:\Custom\SandboxArchive")
    main_window._sandbox_mods_path_input.setText(r"D:\Other\SandboxMods")
    qapp.processEvents()

    assert main_window._sandbox_archive_path_input.text() == r"C:\Custom\SandboxArchive"


def test_main_window_real_archive_autofill_only_when_empty(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    install_target_combo = main_window._install_target_combo
    real_index = install_target_combo.findData(INSTALL_TARGET_CONFIGURED_REAL_MODS)
    assert real_index >= 0

    install_target_combo.setCurrentIndex(real_index)
    main_window._real_archive_path_input.clear()
    main_window._mods_path_input.setText(r"C:\Game\Mods")
    qapp.processEvents()

    assert main_window._real_archive_path_input.text() == r"C:\Game\.sdvmm-real-archive"

    main_window._real_archive_path_input.setText(r"C:\Custom\RealArchive")
    main_window._mods_path_input.setText(r"D:\Other\Mods")
    qapp.processEvents()

    assert main_window._real_archive_path_input.text() == r"C:\Custom\RealArchive"


def test_main_window_setup_surface_group_and_scroll_exist(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    context_tabs = main_window._context_tabs
    setup_group = main_window.findChild(QGroupBox, "setup_surface_group")
    advanced_group = main_window.findChild(QGroupBox, "setup_advanced_group")
    backup_group = main_window.findChild(QGroupBox, "setup_backup_restore_group")
    setup_output_group = main_window.findChild(QGroupBox, "setup_output_group")
    setup_output_box = main_window.findChild(QPlainTextEdit, "setup_output_box")
    setup_scroll = main_window._setup_scroll
    setup_page = main_window._setup_page

    assert context_tabs is not None
    assert setup_group is not None
    assert advanced_group is not None
    assert backup_group is not None
    assert setup_output_group is not None
    assert setup_output_box is not None
    assert setup_scroll is not None
    assert isinstance(setup_scroll, QScrollArea)
    context_tabs.setCurrentWidget(setup_page)
    qapp.processEvents()
    assert setup_group.isVisible()
    assert advanced_group.isVisible()
    assert backup_group.isVisible()
    assert setup_scroll.widget() is not None
    workspace_band = setup_scroll.findChild(QWidget, "setup_surface_workspace_band")
    main_column = setup_scroll.findChild(QWidget, "setup_surface_main_column")
    secondary_column = setup_scroll.findChild(QWidget, "setup_surface_secondary_column")
    secondary_panel = setup_scroll.findChild(QFrame, "setup_secondary_panel")
    quickstart_panel = setup_scroll.findChild(QFrame, "setup_quickstart_panel")
    primary_actions = setup_scroll.findChild(QWidget, "setup_surface_primary_actions")
    save_button = main_window.findChild(QPushButton, "setup_save_config_button")
    detect_button = main_window.findChild(QPushButton, "setup_detect_environment_button")
    setup_readiness_label = main_window.findChild(QLabel, "setup_readiness_label")
    assert workspace_band is not None
    assert main_column is not None
    assert secondary_column is not None
    assert secondary_panel is not None
    assert quickstart_panel is not None
    assert primary_actions is not None
    assert save_button is not None
    assert detect_button is not None
    assert setup_readiness_label is not None
    assert quickstart_panel.parentWidget() is main_column
    assert setup_group.parentWidget() is main_column
    assert advanced_group.parentWidget() is main_column
    assert backup_group.parentWidget() is secondary_panel
    assert setup_output_group.parentWidget() is secondary_panel
    assert save_button.parentWidget() is primary_actions
    assert detect_button.parentWidget() is primary_actions
    assert setup_output_box.parentWidget() is setup_output_group
    assert main_window._setup_group is setup_group
    assert main_window._setup_scroll.advanced_group is advanced_group
    assert main_window._setup_scroll.backup_group is backup_group
    assert main_window._setup_output_group is setup_output_group
    assert main_window._setup_scroll is setup_scroll
    assert main_window._setup_scroll.main_column is main_column
    assert main_window._setup_scroll.secondary_column is secondary_column
    assert setup_scroll.objectName() == "setup_workspace_tab"
    assert setup_scroll.widgetResizable() is True
    assert (
        setup_scroll.sizePolicy().verticalPolicy()
        == QSizePolicy.Policy.Expanding
    )
    assert setup_output_box.isReadOnly() is True
    assert setup_output_box.minimumHeight() >= 70
    assert setup_output_group.isHidden() is True
    setup_index = context_tabs.indexOf(setup_page)
    assert setup_index >= 0
    assert context_tabs.widget(setup_index) is setup_page
    assert "Setup" in {
        context_tabs.tabText(index) for index in range(context_tabs.count())
    }


def test_main_window_top_level_context_tabs_follow_v1_workflow_order(
    main_window: MainWindow,
) -> None:
    context_tabs = main_window._context_tabs

    assert context_tabs is not None
    assert [context_tabs.tabText(index) for index in range(context_tabs.count())] == [
        "Mods",
        "Setup",
        "Packages",
        "Review",
        "Discover",
        "Compare",
        "Archive",
        "Recovery",
    ]


def test_main_window_left_inventory_tabs_are_simplified_for_v1_shell(
    main_window: MainWindow,
) -> None:
    inventory_tabs = main_window._inventory_controls_tabs

    assert inventory_tabs is not None
    assert [inventory_tabs.tabText(index) for index in range(inventory_tabs.count())] == [
        "Installed Mods",
        "Launch",
    ]


def test_main_window_setup_surface_onboarding_copy_is_user_facing(
    main_window: MainWindow,
) -> None:
    main_intro_label = main_window.findChild(QLabel, "setup_main_column_intro_label")
    quickstart_intro_label = main_window.findChild(QLabel, "setup_quickstart_intro_label")
    setup_intro_label = main_window.findChild(QLabel, "setup_local_setup_intro_label")
    backup_intro_label = main_window.findChild(QLabel, "setup_backup_restore_intro_label")
    secondary_intro_label = main_window.findChild(QLabel, "setup_secondary_intro_label")
    app_update_status_label = main_window.findChild(QLabel, "setup_app_update_status_label")
    check_app_update_button = main_window.findChild(QPushButton, "setup_check_app_update_button")
    open_app_release_page_button = main_window.findChild(
        QPushButton,
        "setup_open_app_release_page_button",
    )

    assert main_intro_label is not None
    assert quickstart_intro_label is not None
    assert setup_intro_label is not None
    assert backup_intro_label is not None
    assert secondary_intro_label is not None
    assert app_update_status_label is not None
    assert check_app_update_button is not None
    assert open_app_release_page_button is not None
    assert "confirm that Cinderleaf is ready" in main_intro_label.text()
    assert "common workflow" in quickstart_intro_label.text()
    assert "live game folder plus your real and sandbox Mods folders" in (
        setup_intro_label.text()
    )
    assert "Detect game folders only reads the installed environment" in setup_intro_label.text()
    assert (
        "Inspect stays read-only and prepares restore/import review"
        in backup_intro_label.text()
    )
    assert "Execute restore still writes only into the configured folders." in (
        backup_intro_label.text()
    )
    assert "backup bundle, a restore/import review, or migration detail" in (
        secondary_intro_label.text()
    )
    assert "Check for app updates" in app_update_status_label.text()
    assert check_app_update_button.text() == "Check for app updates"
    assert open_app_release_page_button.text() == "Open release page"


def test_main_window_setup_readiness_label_tracks_minimum_paths(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    readiness_label = main_window.findChild(QLabel, "setup_readiness_label")
    status_label = main_window._status_strip_label

    assert readiness_label is not None
    assert "Minimum to start" in readiness_label.text()
    assert "Minimum setup is empty" in status_label.text()

    main_window._game_path_input.setText(r"C:\Game")
    qapp.processEvents()
    assert "1/3 core paths set" in readiness_label.text()
    assert "Real Mods folder, Sandbox Mods folder" in readiness_label.text()
    assert "Setup is in progress" in status_label.text()

    main_window._mods_path_input.setText(r"C:\Game\Mods")
    qapp.processEvents()
    assert "2/3 core paths set" in readiness_label.text()
    assert "Sandbox Mods folder" in readiness_label.text()

    main_window._sandbox_mods_path_input.setText(r"C:\Sandbox\Mods")
    qapp.processEvents()
    assert "Configured enough to proceed" in readiness_label.text()
    assert "inspect a package in Packages" in readiness_label.text()
    assert "Core paths are ready" in status_label.text()


def test_main_window_setup_surface_key_inputs_and_actions_exist(main_window: MainWindow) -> None:
    input_names = (
        "setup_game_path_input",
        "setup_mods_path_input",
        "setup_sandbox_mods_input",
        "setup_sandbox_archive_input",
        "setup_real_archive_input",
        "setup_watched_downloads_input",
        "setup_secondary_watched_downloads_input",
        "setup_nexus_api_key_input",
    )
    button_names = (
        "setup_save_config_button",
        "setup_detect_environment_button",
        "setup_export_backup_button",
        "setup_inspect_backup_button",
        "setup_execute_restore_import_button",
        "setup_open_mods_button",
        "setup_open_sandbox_mods_button",
        "setup_open_real_archive_button",
        "setup_open_sandbox_archive_button",
        "setup_open_watched_downloads_button",
        "setup_open_secondary_watched_downloads_button",
    )

    for name in input_names:
        control = main_window.findChild(QLineEdit, name)
        assert control is not None

    for name in button_names:
        button = main_window.findChild(QPushButton, name)
        assert button is not None

    active_bundle_label = main_window.findChild(QLabel, "setup_active_backup_bundle_label")
    assert active_bundle_label is not None

    assert main_window.findChild(QPlainTextEdit, "setup_output_box") is not None
    steam_checkbox = main_window.findChild(QCheckBox, "setup_steam_auto_start_checkbox")
    assert steam_checkbox is not None
    assert steam_checkbox.isChecked() is True


def test_main_window_packages_watcher_section_uses_separate_rows_for_paths_and_actions(
    main_window: MainWindow,
) -> None:
    watcher_group = main_window.findChild(QGroupBox, "packages_watcher_group")
    primary_actions_widget = main_window.findChild(
        QWidget,
        "packages_watcher_primary_actions_widget",
    )
    secondary_actions_widget = main_window.findChild(
        QWidget,
        "packages_watcher_secondary_actions_widget",
    )
    runtime_actions_widget = main_window.findChild(
        QWidget,
        "packages_watcher_runtime_actions_widget",
    )
    watcher_scope_label = main_window.findChild(QLabel, "packages_watcher_scope_label")

    assert watcher_group is not None
    assert primary_actions_widget is not None
    assert secondary_actions_widget is not None
    assert runtime_actions_widget is not None
    assert watcher_scope_label is not None

    watcher_layout = watcher_group.layout()
    assert isinstance(watcher_layout, QGridLayout)
    assert watcher_layout.itemAtPosition(0, 1).widget() is main_window._watched_downloads_path_input
    assert (
        watcher_layout.itemAtPosition(1, 1).widget()
        is primary_actions_widget
    )
    assert (
        watcher_layout.itemAtPosition(2, 1).widget()
        is main_window._secondary_watched_downloads_path_input
    )
    assert (
        watcher_layout.itemAtPosition(3, 1).widget()
        is secondary_actions_widget
    )
    assert watcher_layout.itemAtPosition(4, 1).widget() is watcher_scope_label
    assert watcher_layout.itemAtPosition(5, 1).widget() is runtime_actions_widget

    primary_button_texts = {
        button.text() for button in primary_actions_widget.findChildren(QPushButton)
    }
    secondary_button_texts = {
        button.text() for button in secondary_actions_widget.findChildren(QPushButton)
    }
    runtime_button_texts = {
        button.text() for button in runtime_actions_widget.findChildren(QPushButton)
    }
    assert primary_button_texts == {"Choose folder", "Open"}
    assert secondary_button_texts == {"Choose folder 2", "Open"}
    assert runtime_button_texts == {"Start intake watch", "Stop intake watch"}


def test_main_window_packages_surface_uses_guided_intake_composition(
    main_window: MainWindow,
) -> None:
    packages_top_grid = main_window.findChild(QWidget, "packages_top_grid")
    import_group = main_window.findChild(QGroupBox, "packages_import_group")
    watcher_group = main_window.findChild(QGroupBox, "packages_watcher_group")
    review_target_group = main_window.findChild(QGroupBox, "packages_review_target_group")

    assert packages_top_grid is not None
    assert import_group is not None
    assert watcher_group is not None
    assert review_target_group is not None

    top_grid_layout = packages_top_grid.layout()
    assert isinstance(top_grid_layout, QGridLayout)
    assert top_grid_layout.itemAtPosition(0, 0).widget() is import_group
    assert top_grid_layout.itemAtPosition(0, 1).widget() is watcher_group


def test_main_window_install_review_surface_onboarding_copy_is_user_facing(
    main_window: MainWindow,
) -> None:
    intro_label = main_window.findChild(QLabel, "plan_install_intro_label")
    execute_help_label = main_window.findChild(QLabel, "plan_install_execute_help_label")
    review_summary_label = main_window.findChild(
        QLabel,
        "plan_install_review_summary_label",
    )

    assert intro_label is not None
    assert execute_help_label is not None
    assert review_summary_label is not None
    assert "generate the read-only review" in intro_label.text()
    assert "write summary looks right" in intro_label.text()
    assert "Review install is read-only." in execute_help_label.text()
    assert "Apply install stays unavailable until the review is ready." in execute_help_label.text()
    assert (
        review_summary_label.text()
        == "Review summary: no plan yet. Click Review install to inspect changes."
    )


def test_main_window_loads_saved_steam_auto_start_preference(
    tmp_path: Path,
    qapp: QApplication,
) -> None:
    state_file = tmp_path / "app-state.json"
    service = AppShellService(state_file=state_file)
    config = AppConfig(
        game_path=tmp_path / "Game",
        mods_path=tmp_path / "Mods",
        app_data_path=tmp_path / "AppData",
        steam_auto_start_enabled=False,
    )
    config.game_path.mkdir()
    config.mods_path.mkdir()
    save_app_config(state_file, config)

    window = MainWindow(shell_service=service)
    window.show()
    qapp.processEvents()
    try:
        assert window._steam_auto_start_checkbox.isChecked() is False
    finally:
        window.close()
        qapp.processEvents()


def test_main_window_detect_environment_updates_setup_local_output_and_shared_details(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    game_path = tmp_path / "Stardew Valley"
    _create_launchable_game_install_for_ui(game_path)
    environment_status = GameEnvironmentStatus(
        game_path=game_path,
        mods_path=game_path / "Mods",
        smapi_path=game_path / "StardewModdingAPI.exe",
        state_codes=("game_path_detected", "mods_path_detected", "smapi_detected"),
    )

    main_window._game_path_input.setText(str(game_path))
    monkeypatch.setattr(
        main_window._shell_service,
        "detect_game_environment",
        lambda path_text: environment_status,
    )

    main_window._on_detect_environment()

    assert str(game_path) in main_window._setup_output_box.toPlainText()
    assert main_window._setup_output_box.toPlainText() == main_window._findings_box.toPlainText()
    assert main_window._status_strip_label.text() == "Environment detection complete."


def test_main_window_export_backup_bundle_runs_service_and_updates_output(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    export_root = tmp_path / "Exports"
    export_root.mkdir()
    bundle_path = export_root / "sdvmm-backup-20260317-120000Z"
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    result = BackupBundleExportResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        created_at_utc="2026-03-17T12:00:00Z",
        items=(
            BackupBundleExportItem(
                key="app_state",
                label="App state/config",
                kind="file",
                status="copied",
                relative_path=Path("manager-state") / "app-state.json",
                source_path=tmp_path / "state" / "app-state.json",
            ),
        ),
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_export_target",
        lambda: (str(export_root), "directory"),
    )

    def fake_export_backup_bundle(**kwargs: object) -> BackupBundleExportResult:
        captured["service_kwargs"] = kwargs
        return result

    def fake_run_background_operation(**kwargs: object) -> None:
        captured["operation_name"] = kwargs["operation_name"]
        task_result = kwargs["task_fn"]()
        kwargs["on_success"](task_result)

    monkeypatch.setattr(main_window._shell_service, "export_backup_bundle", fake_export_backup_bundle)
    monkeypatch.setattr(main_window, "_run_background_operation", fake_run_background_operation)

    main_window._on_export_backup_bundle()

    assert captured["operation_name"] == "Backup export"
    assert captured["service_kwargs"] == {
        "destination_root_text": str(export_root),
        "bundle_storage_kind": "directory",
        **main_window._current_backup_export_inputs(),
    }
    assert "steam_auto_start_enabled" not in captured["service_kwargs"]
    assert main_window._status_strip_label.text() == (
        f"Backup export complete: 1 item(s) copied to {bundle_path}"
    )
    assert "Cinderleaf backup export" in main_window._setup_output_box.toPlainText()
    assert str(bundle_path) in main_window._setup_output_box.toPlainText()
    assert "Cinderleaf backup export" in main_window._findings_box.toPlainText()
    assert str(bundle_path) in main_window._findings_box.toPlainText()


def test_main_window_export_backup_bundle_cancel_sets_status_without_running(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []
    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_export_target",
        lambda: None,
    )
    monkeypatch.setattr(
        main_window,
        "_run_background_operation",
        lambda **kwargs: captured.append(str(kwargs["operation_name"])),
    )

    main_window._on_export_backup_bundle()

    assert captured == []
    assert main_window._status_strip_label.text() == "Backup export cancelled."


def test_main_window_inspect_backup_bundle_runs_service_and_updates_output(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260318-120000Z"
    bundle_path.mkdir(parents=True)
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    result = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-18T12:00:00Z",
        items=(
            BackupBundleInspectionItem(
                key="app_state",
                label="App state/config",
                kind="file",
                declared_status="copied",
                relative_path=Path("manager-state") / "app-state.json",
                structure_state="present",
            ),
            BackupBundleInspectionItem(
                key="real_mod_configs",
                label="Real Mods config snapshot",
                kind="directory",
                declared_status="copied",
                relative_path=Path("mod-config") / "real-mods",
                structure_state="present",
                note="2 config artifact(s) from 1 mod folder(s).",
            ),
        ),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
        warnings=tuple(),
        intentionally_not_included=(
            "A restore/import workflow. This bundle is export-only in this stage.",
        ),
    )
    planning_result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=result,
        items=(
            RestoreImportPlanningItem(
                key="real_mods",
                label="Real Mods directory",
                state="safe_to_restore_later",
                message="Real Mods directory planning looks straightforward: 1 safe, 0 blocked.",
                bundle_relative_path=Path("mods") / "real-mods",
                local_target_path=Path(r"C:\Local\Mods"),
                bundle_declared_status="copied",
                bundle_structure_state="present",
                safe_mod_count=1,
            ),
        ),
        mod_entries=tuple(),
        config_entries=tuple(),
        safe_item_count=1,
        review_item_count=0,
        blocked_item_count=0,
        safe_mod_count=1,
        review_mod_count=0,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete: 1 item(s) look straightforward.",
    )
    review = RestoreImportExecutionReview(
        allowed=True,
        message="Restore/import is ready to write 1 mod folder(s) and 0 config artifact(s) into the current configured destinations. Existing local content will not be merged.",
        executable_mod_count=1,
        executable_config_count=0,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        lambda: bundle_path,
    )

    def fake_inspect_backup_bundle(**kwargs: object) -> BackupBundleInspectionResult:
        captured["service_kwargs"] = kwargs
        return result

    def fake_plan_restore_import_from_backup_bundle(
        **kwargs: object,
    ) -> RestoreImportPlanningResult:
        captured["plan_service_kwargs"] = kwargs
        return planning_result

    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_backup_bundle",
        fake_inspect_backup_bundle,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "plan_restore_import_from_backup_bundle",
        fake_plan_restore_import_from_backup_bundle,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "review_restore_import_execution",
        lambda planning: review,
    )
    monkeypatch.setattr(
        main_window,
        "_run_background_operation",
        _fake_background_operation_with_real_lifecycle(main_window, captured),
    )

    main_window._on_inspect_backup_bundle()
    qapp.processEvents()

    assert captured["operation_names"] == [
        "Backup bundle inspection",
        "Restore/import planning",
    ]
    assert captured["service_kwargs"] == {"bundle_path_text": str(bundle_path)}
    assert captured["plan_service_kwargs"] == {
        "bundle_path_text": str(bundle_path),
        **main_window._current_restore_import_planning_inputs(),
    }
    assert "steam_auto_start_enabled" not in captured["plan_service_kwargs"]
    assert (
        main_window._status_strip_label.text()
        == "Restore/import planning complete: 1 item(s) look straightforward."
    )
    assert (
        main_window._backup_bundle_inspection_summary_label.text()
        == "Backup bundle looks structurally usable for future restore/import."
    )
    assert (
        main_window._restore_import_planning_summary_label.text()
        == "Restore/import planning complete: 1 item(s) look straightforward."
    )
    assert str(bundle_path) in main_window._active_backup_bundle_label.toolTip()
    assert "planned" in main_window._active_backup_bundle_label.text().casefold()
    assert "restore/import planning" in main_window._setup_output_box.toPlainText().casefold()
    assert str(bundle_path) in main_window._setup_output_box.toPlainText()
    assert "restore/import planning" in main_window._findings_box.toPlainText().casefold()
    assert str(bundle_path) in main_window._findings_box.toPlainText()
    execute_button = main_window.findChild(QPushButton, "setup_execute_restore_import_button")
    assert execute_button is not None
    assert execute_button.isEnabled() is True
    assert "ready to write 1 mod folder" in execute_button.toolTip()


def test_main_window_inspect_backup_bundle_keeps_inspection_visible_when_auto_plan_fails(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260324-120000Z"
    bundle_path.mkdir(parents=True)
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=bundle_path / "manifest.json",
        summary_path=bundle_path / "README.txt",
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-24T12:00:00Z",
        items=tuple(),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        lambda: bundle_path,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_backup_bundle",
        lambda **kwargs: inspection,
    )

    def fake_plan_restore_import_from_backup_bundle(**kwargs: object) -> RestoreImportPlanningResult:
        captured["plan_service_kwargs"] = kwargs
        raise AssertionError("task_fn should not be called directly for failed plan simulation")

    def fake_run_background_operation(**kwargs: object) -> None:
        operation_name = str(kwargs["operation_name"])
        captured.setdefault("operation_names", []).append(operation_name)
        main_window._active_operation_name = operation_name
        main_window._active_background_task = SimpleNamespace()
        if operation_name == "Backup bundle inspection":
            kwargs["on_success"](kwargs["task_fn"]())
            main_window._finish_background_operation(operation_name, success=True)
            return
        kwargs["on_failure"](
            "Restore/import planning failed: current configured destination is unavailable."
        )
        main_window._finish_background_operation(operation_name, success=False)

    monkeypatch.setattr(
        main_window._shell_service,
        "plan_restore_import_from_backup_bundle",
        fake_plan_restore_import_from_backup_bundle,
    )
    monkeypatch.setattr(main_window, "_run_background_operation", fake_run_background_operation)

    main_window._on_inspect_backup_bundle()
    qapp.processEvents()

    assert captured["operation_names"] == [
        "Backup bundle inspection",
        "Restore/import planning",
    ]
    output_text = main_window._setup_output_box.toPlainText()
    assert "backup bundle inspection" in output_text.casefold()
    assert "automatic restore/import planning could not run" in output_text.casefold()
    assert "current configured destination is unavailable" in output_text
    assert (
        main_window._restore_import_planning_summary_label.text()
        == "Automatic restore/import planning could not run."
    )
    assert "inspected" in main_window._active_backup_bundle_label.text().casefold()
    execute_button = main_window.findChild(QPushButton, "setup_execute_restore_import_button")
    assert execute_button is not None
    assert execute_button.isEnabled() is True
    assert "refresh restore/import review" in execute_button.toolTip().casefold()


def test_main_window_inspect_backup_bundle_cancel_sets_status_without_running(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []
    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        lambda: None,
    )
    monkeypatch.setattr(
        main_window,
        "_run_background_operation",
        lambda **kwargs: captured.append(str(kwargs["operation_name"])),
    )

    main_window._on_inspect_backup_bundle()

    assert captured == []
    assert main_window._status_strip_label.text() == "Backup bundle inspection cancelled."


def test_main_window_prompt_for_backup_bundle_path_can_select_zip_bundle(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    zip_path = tmp_path / "Exports" / "sdvmm-backup-20260321-141500Z.zip"

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_storage_kind",
        lambda **kwargs: "zip",
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: (str(zip_path), "Backup bundle zips (*.zip)"),
    )

    assert main_window._prompt_for_backup_bundle_path() == zip_path


def test_main_window_export_backup_bundle_can_request_zip_creation(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    zip_path = tmp_path / "Exports" / "sdvmm-backup-20260321-160000Z.zip"
    result = BackupBundleExportResult(
        bundle_path=zip_path,
        manifest_path=zip_path,
        summary_path=zip_path,
        created_at_utc="2026-03-21T16:00:00Z",
        items=tuple(),
        bundle_storage_kind="zip",
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_export_target",
        lambda: (str(zip_path), "zip"),
    )

    def fake_export_backup_bundle(**kwargs: object) -> BackupBundleExportResult:
        captured["service_kwargs"] = kwargs
        return result

    monkeypatch.setattr(
        main_window._shell_service,
        "export_backup_bundle",
        fake_export_backup_bundle,
    )

    def fake_run_background_operation(**kwargs: object) -> None:
        captured["operation_name"] = kwargs["operation_name"]
        task_result = kwargs["task_fn"]()
        kwargs["on_success"](task_result)

    monkeypatch.setattr(main_window, "_run_background_operation", fake_run_background_operation)

    main_window._on_export_backup_bundle()

    assert captured["operation_name"] == "Backup export"
    assert captured["service_kwargs"] == {
        "destination_root_text": str(zip_path),
        "bundle_storage_kind": "zip",
        **main_window._current_backup_export_inputs(),
    }
    assert "steam_auto_start_enabled" not in captured["service_kwargs"]


def test_main_window_plan_restore_import_reuses_bundle_selected_for_inspection_before_completion(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260321-141500Z"
    bundle_path.mkdir(parents=True)
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-21T14:15:00Z",
        items=tuple(),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    planning_result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=tuple(),
        mod_entries=tuple(),
        config_entries=tuple(),
        safe_item_count=1,
        review_item_count=0,
        blocked_item_count=0,
        safe_mod_count=1,
        review_mod_count=0,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete: 1 item(s) look straightforward.",
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        lambda: bundle_path,
    )

    def fake_run_background_operation_for_inspect(**kwargs: object) -> None:
        captured["inspect_operation_name"] = kwargs["operation_name"]
        captured["inspect_started_task_result_path"] = kwargs["task_fn"]().bundle_path

    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_backup_bundle",
        lambda **kwargs: inspection,
    )
    monkeypatch.setattr(
        main_window,
        "_run_background_operation",
        fake_run_background_operation_for_inspect,
    )

    main_window._on_inspect_backup_bundle()

    assert captured["inspect_operation_name"] == "Backup bundle inspection"
    assert str(bundle_path) in main_window._active_backup_bundle_label.toolTip()
    assert "selected" in main_window._active_backup_bundle_label.text().casefold()

    def fake_plan_restore_import_from_backup_bundle(
        **kwargs: object,
    ) -> RestoreImportPlanningResult:
        captured["plan_service_kwargs"] = kwargs
        return planning_result

    def fake_run_background_operation_for_plan(**kwargs: object) -> None:
        captured["plan_operation_name"] = kwargs["operation_name"]
        kwargs["on_success"](kwargs["task_fn"]())

    monkeypatch.setattr(
        main_window._shell_service,
        "plan_restore_import_from_backup_bundle",
        fake_plan_restore_import_from_backup_bundle,
    )
    monkeypatch.setattr(
        main_window,
        "_run_background_operation",
        fake_run_background_operation_for_plan,
    )

    main_window._on_plan_restore_import()

    assert captured["plan_operation_name"] == "Restore/import planning"
    assert captured["plan_service_kwargs"] == {
        "bundle_path_text": str(bundle_path),
        **main_window._current_restore_import_planning_inputs(),
    }
    assert "steam_auto_start_enabled" not in captured["plan_service_kwargs"]


def test_main_window_plan_restore_import_reuses_active_bundle_after_inspect_without_reprompting(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260324-160000Z"
    bundle_path.mkdir(parents=True)
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=bundle_path / "manifest.json",
        summary_path=bundle_path / "README.txt",
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-24T16:00:00Z",
        items=tuple(),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    auto_plan_result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=tuple(),
        mod_entries=tuple(),
        config_entries=tuple(),
        safe_item_count=1,
        review_item_count=0,
        blocked_item_count=0,
        safe_mod_count=1,
        review_mod_count=0,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete: 1 item(s) look straightforward.",
    )
    manual_plan_result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=tuple(),
        mod_entries=tuple(),
        config_entries=tuple(),
        safe_item_count=1,
        review_item_count=0,
        blocked_item_count=0,
        safe_mod_count=1,
        review_mod_count=0,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete: 1 item(s) still look straightforward.",
    )
    captured: dict[str, object] = {"prompt_calls": 0}

    def fake_prompt_for_backup_bundle_path() -> Path:
        captured["prompt_calls"] = int(captured["prompt_calls"]) + 1
        return bundle_path

    def fake_inspect_backup_bundle(**kwargs: object) -> BackupBundleInspectionResult:
        captured["inspect_kwargs"] = kwargs
        return inspection

    def fake_plan_restore_import_from_backup_bundle(
        **kwargs: object,
    ) -> RestoreImportPlanningResult:
        captured.setdefault("plan_kwargs_list", []).append(kwargs)
        if len(captured["plan_kwargs_list"]) == 1:
            return auto_plan_result
        return manual_plan_result

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        fake_prompt_for_backup_bundle_path,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_backup_bundle",
        fake_inspect_backup_bundle,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "plan_restore_import_from_backup_bundle",
        fake_plan_restore_import_from_backup_bundle,
    )
    monkeypatch.setattr(
        main_window,
        "_run_background_operation",
        _fake_background_operation_with_real_lifecycle(main_window, captured),
    )

    main_window._on_inspect_backup_bundle()
    qapp.processEvents()
    main_window._on_plan_restore_import()

    assert captured["prompt_calls"] == 1
    assert captured["inspect_kwargs"] == {"bundle_path_text": str(bundle_path)}
    assert captured["operation_names"] == [
        "Backup bundle inspection",
        "Restore/import planning",
        "Restore/import planning",
    ]
    assert captured["plan_kwargs_list"] == [
        {
            "bundle_path_text": str(bundle_path),
            **main_window._current_restore_import_planning_inputs(),
        },
        {
            "bundle_path_text": str(bundle_path),
            **main_window._current_restore_import_planning_inputs(),
        },
    ]
    for kwargs in captured["plan_kwargs_list"]:
        assert "steam_auto_start_enabled" not in kwargs


def test_main_window_plan_restore_import_runs_service_and_updates_output(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260318-130000Z"
    bundle_path.mkdir(parents=True)
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-18T13:00:00Z",
        items=(
            BackupBundleInspectionItem(
                key="real_mods",
                label="Real Mods directory",
                kind="directory",
                declared_status="copied",
                relative_path=Path("mods") / "real-mods",
                structure_state="present",
            ),
        ),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=(
            RestoreImportPlanningItem(
                key="real_mods",
                label="Real Mods directory",
                state="needs_review",
                message="Real Mods directory planning found review points: 1 need review, 0 look safe.",
                bundle_relative_path=Path("mods") / "real-mods",
                local_target_path=Path(r"C:\Local\Mods"),
                bundle_declared_status="copied",
                bundle_structure_state="present",
                review_mod_count=1,
            ),
            RestoreImportPlanningItem(
                key="real_mod_configs",
                label="Real Mods config snapshot",
                state="needs_review",
                message="Real Mods config snapshot planning found review points: 1 need review, 0 look safe.",
                bundle_relative_path=Path("mod-config") / "real-mods",
                local_target_path=Path(r"C:\Local\Mods"),
                bundle_declared_status="copied",
                bundle_structure_state="present",
                review_config_count=1,
            ),
        ),
        mod_entries=(
            RestoreImportPlanningModEntry(
                bundle_item_key="real_mods",
                bundle_item_label="Real Mods directory",
                name="Real Alpha",
                unique_id="Sample.RealAlpha",
                bundle_version="1.0.0",
                local_version="2.0.0",
                state="different_version",
                local_target_path=Path(r"C:\Local\Mods"),
                note="Bundle version 1.0.0 differs from local version 2.0.0.",
            ),
        ),
        config_entries=(
            RestoreImportPlanningConfigEntry(
                bundle_item_key="real_mod_configs",
                bundle_item_label="Real Mods config snapshot",
                relative_path=Path("RealAlpha") / "config.json",
                state="different_content",
                local_target_path=Path(r"C:\Local\Mods\RealAlpha\config.json"),
                note="Local config artifact differs from the bundled content.",
            ),
        ),
        safe_item_count=0,
        review_item_count=2,
        blocked_item_count=0,
        safe_mod_count=0,
        review_mod_count=1,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=1,
        blocked_config_count=0,
        message="Restore/import planning complete: 0 item(s) look straightforward, 2 item(s) need review.",
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        lambda: bundle_path,
    )

    def fake_plan_restore_import_from_backup_bundle(
        **kwargs: object,
    ) -> RestoreImportPlanningResult:
        captured["service_kwargs"] = kwargs
        return result

    def fake_run_background_operation(**kwargs: object) -> None:
        captured["operation_name"] = kwargs["operation_name"]
        task_result = kwargs["task_fn"]()
        kwargs["on_success"](task_result)

    monkeypatch.setattr(
        main_window._shell_service,
        "plan_restore_import_from_backup_bundle",
        fake_plan_restore_import_from_backup_bundle,
    )
    monkeypatch.setattr(main_window, "_run_background_operation", fake_run_background_operation)

    main_window._on_plan_restore_import()

    assert captured["operation_name"] == "Restore/import planning"
    assert captured["service_kwargs"] == {
        "bundle_path_text": str(bundle_path),
        **main_window._current_restore_import_planning_inputs(),
    }
    assert "steam_auto_start_enabled" not in captured["service_kwargs"]
    assert (
        main_window._status_strip_label.text()
        == "Restore/import execution is blocked: no clearly restorable missing content is available under the current review model."
    )
    assert (
        main_window._restore_import_planning_summary_label.text()
        == "Restore/import execution is blocked: no clearly restorable missing content is available under the current review model."
    )
    assert str(bundle_path) in main_window._active_backup_bundle_label.toolTip()
    assert "planned" in main_window._active_backup_bundle_label.text().casefold()
    assert "config realalpha\\config.json" in main_window._setup_output_box.toPlainText().casefold()
    assert "restore/import planning" in main_window._setup_output_box.toPlainText().casefold()
    assert "execution readiness:" in main_window._setup_output_box.toPlainText().casefold()
    assert str(bundle_path) in main_window._setup_output_box.toPlainText()
    assert "restore/import planning" in main_window._findings_box.toPlainText().casefold()
    assert str(bundle_path) in main_window._findings_box.toPlainText()


def test_main_window_plan_restore_import_cancel_sets_status_without_running(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []
    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        lambda: None,
    )
    monkeypatch.setattr(
        main_window,
        "_run_background_operation",
        lambda **kwargs: captured.append(str(kwargs["operation_name"])),
    )

    main_window._on_plan_restore_import()

    assert captured == []
    assert main_window._status_strip_label.text() == "Restore/import planning cancelled."


def test_main_window_plan_restore_import_uses_active_inspected_bundle_without_picker(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260321-130000Z"
    bundle_path.mkdir(parents=True)
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-21T13:00:00Z",
        items=tuple(),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    planning_result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=tuple(),
        mod_entries=tuple(),
        config_entries=tuple(),
        safe_item_count=1,
        review_item_count=0,
        blocked_item_count=0,
        safe_mod_count=1,
        review_mod_count=0,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete: 1 item(s) look straightforward.",
    )
    captured: dict[str, object] = {}

    main_window._set_active_backup_bundle_context(bundle_path, label_text="inspected")

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        lambda: pytest.fail("picker should not reopen when an active bundle exists"),
    )

    def fake_plan_restore_import_from_backup_bundle(
        **kwargs: object,
    ) -> RestoreImportPlanningResult:
        captured["service_kwargs"] = kwargs
        return planning_result

    def fake_run_background_operation(**kwargs: object) -> None:
        captured["operation_name"] = kwargs["operation_name"]
        kwargs["on_success"](kwargs["task_fn"]())

    monkeypatch.setattr(
        main_window._shell_service,
        "plan_restore_import_from_backup_bundle",
        fake_plan_restore_import_from_backup_bundle,
    )
    monkeypatch.setattr(main_window, "_run_background_operation", fake_run_background_operation)

    main_window._on_plan_restore_import()

    assert captured["operation_name"] == "Restore/import planning"
    assert captured["service_kwargs"] == {
        "bundle_path_text": str(bundle_path),
        **main_window._current_restore_import_planning_inputs(),
    }
    assert "steam_auto_start_enabled" not in captured["service_kwargs"]


def test_main_window_execute_restore_import_uses_active_bundle_without_picker(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260321-131500Z"
    bundle_path.mkdir(parents=True)
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-21T13:15:00Z",
        items=tuple(),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    planning_result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=tuple(),
        mod_entries=tuple(),
        config_entries=tuple(),
        safe_item_count=1,
        review_item_count=0,
        blocked_item_count=0,
        safe_mod_count=1,
        review_mod_count=0,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete: 1 item(s) look straightforward.",
    )
    review = RestoreImportExecutionReview(
        allowed=True,
        message="Restore/import is ready to write 1 mod folder(s) and 0 config artifact(s) into the current configured destinations. Existing local content will not be merged.",
        executable_mod_count=1,
        executable_config_count=0,
    )
    execution_result = RestoreImportExecutionResult(
        bundle_path=bundle_path,
        restored_mod_paths=(Path(r"C:\Local\Mods\RealAlpha"),),
        restored_config_paths=tuple(),
        restored_mod_count=1,
        restored_config_count=0,
        message="Restore/import execution completed: 1 mod folder(s) and 0 config artifact(s) restored.",
    )
    captured: dict[str, object] = {}

    main_window._set_active_backup_bundle_context(bundle_path, label_text="inspected")

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        lambda: pytest.fail("picker should not reopen when an active bundle exists"),
    )
    def fake_plan_restore_import_from_backup_bundle(
        **kwargs: object,
    ) -> RestoreImportPlanningResult:
        captured["plan_kwargs"] = kwargs
        return planning_result

    def fake_execute_restore_import(
        planning: RestoreImportPlanningResult,
        *,
        confirm_execution: bool = False,
    ) -> RestoreImportExecutionResult:
        captured["execute_args"] = (planning, confirm_execution)
        return execution_result

    def fake_run_background_operation(**kwargs: object) -> None:
        captured.setdefault("operations", []).append(kwargs["operation_name"])
        kwargs["on_success"](kwargs["task_fn"]())

    monkeypatch.setattr(
        main_window._shell_service,
        "plan_restore_import_from_backup_bundle",
        fake_plan_restore_import_from_backup_bundle,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "review_restore_import_execution",
        lambda planning: review,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_restore_import",
        fake_execute_restore_import,
    )
    monkeypatch.setattr(main_window, "_run_background_operation", fake_run_background_operation)
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    main_window._on_execute_restore_import()

    assert captured["operations"] == [
        "Restore/import planning",
        "Restore/import execution",
    ]
    assert captured["plan_kwargs"] == {
        "bundle_path_text": str(bundle_path),
        **main_window._current_restore_import_planning_inputs(),
    }
    assert "steam_auto_start_enabled" not in captured["plan_kwargs"]
    assert captured["execute_args"] == (planning_result, True)


def test_main_window_execute_restore_import_picker_fallback_runs_when_no_active_bundle(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260321-133000Z"
    bundle_path.mkdir(parents=True)
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-21T13:30:00Z",
        items=tuple(),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    planning_result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=tuple(),
        mod_entries=tuple(),
        config_entries=tuple(),
        safe_item_count=1,
        review_item_count=0,
        blocked_item_count=0,
        safe_mod_count=1,
        review_mod_count=0,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete: 1 item(s) look straightforward.",
    )
    review = RestoreImportExecutionReview(
        allowed=True,
        message="Restore/import is ready to write 1 mod folder(s) and 0 config artifact(s) into the current configured destinations. Existing local content will not be merged.",
        executable_mod_count=1,
        executable_config_count=0,
    )
    execution_result = RestoreImportExecutionResult(
        bundle_path=bundle_path,
        restored_mod_paths=(Path(r"C:\Local\Mods\RealAlpha"),),
        restored_config_paths=tuple(),
        restored_mod_count=1,
        restored_config_count=0,
        message="Restore/import execution completed: 1 mod folder(s) and 0 config artifact(s) restored.",
    )
    captured: dict[str, object] = {"picker_calls": 0}

    def fake_get_existing_directory(*args: object, **kwargs: object) -> str:
        captured["picker_calls"] = int(captured["picker_calls"]) + 1
        return str(bundle_path)

    def fake_plan_restore_import_from_backup_bundle(
        **kwargs: object,
    ) -> RestoreImportPlanningResult:
        captured["plan_kwargs"] = kwargs
        return planning_result

    def fake_execute_restore_import(
        planning: RestoreImportPlanningResult,
        *,
        confirm_execution: bool = False,
    ) -> RestoreImportExecutionResult:
        captured["execute_args"] = (planning, confirm_execution)
        return execution_result

    def fake_run_background_operation(**kwargs: object) -> None:
        captured.setdefault("operations", []).append(kwargs["operation_name"])
        kwargs["on_success"](kwargs["task_fn"]())

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        lambda: Path(fake_get_existing_directory()),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "plan_restore_import_from_backup_bundle",
        fake_plan_restore_import_from_backup_bundle,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "review_restore_import_execution",
        lambda planning: review,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_restore_import",
        fake_execute_restore_import,
    )
    monkeypatch.setattr(main_window, "_run_background_operation", fake_run_background_operation)
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    main_window._on_execute_restore_import()

    assert captured["picker_calls"] == 1
    assert captured["operations"] == [
        "Restore/import planning",
        "Restore/import execution",
    ]
    assert captured["plan_kwargs"] == {
        "bundle_path_text": str(bundle_path),
        **main_window._current_restore_import_planning_inputs(),
    }
    assert "steam_auto_start_enabled" not in captured["plan_kwargs"]
    assert captured["execute_args"] == (planning_result, True)


def test_main_window_active_backup_bundle_label_updates_when_context_changes(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first_bundle = tmp_path / "Exports" / "sdvmm-backup-20260321-134500Z"
    second_bundle = tmp_path / "Exports" / "sdvmm-backup-20260321-135000Z"
    first_bundle.mkdir(parents=True)
    second_bundle.mkdir(parents=True)
    first_inspection = BackupBundleInspectionResult(
        bundle_path=first_bundle,
        manifest_path=first_bundle / "manifest.json",
        summary_path=first_bundle / "README.txt",
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-21T13:45:00Z",
        items=tuple(),
        structurally_usable=True,
        message="First bundle ready.",
    )
    second_inspection = BackupBundleInspectionResult(
        bundle_path=second_bundle,
        manifest_path=second_bundle / "manifest.json",
        summary_path=second_bundle / "README.txt",
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-21T13:50:00Z",
        items=tuple(),
        structurally_usable=True,
        message="Second bundle ready.",
    )

    monkeypatch.setattr(
        main_window,
        "_start_restore_import_planning_for_bundle",
        lambda *args, **kwargs: None,
    )
    main_window._on_backup_bundle_inspection_completed(first_inspection)
    first_label = main_window._active_backup_bundle_label.text()

    main_window._on_backup_bundle_inspection_completed(second_inspection)

    assert str(first_bundle.name) in first_label
    assert str(second_bundle) in main_window._active_backup_bundle_label.toolTip()
    assert second_bundle.name in main_window._active_backup_bundle_label.text()
    assert first_bundle.name not in main_window._active_backup_bundle_label.text()


def test_main_window_plan_restore_import_enables_execute_button_when_review_allows(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260318-131500Z"
    bundle_path.mkdir(parents=True)
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-18T13:15:00Z",
        items=(
            BackupBundleInspectionItem(
                key="real_mods",
                label="Real Mods directory",
                kind="directory",
                declared_status="copied",
                relative_path=Path("mods") / "real-mods",
                structure_state="present",
            ),
        ),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=(
            RestoreImportPlanningItem(
                key="real_mods",
                label="Real Mods directory",
                state="safe_to_restore_later",
                message="Real Mods directory planning looks straightforward: 1 safe, 0 blocked.",
                bundle_relative_path=Path("mods") / "real-mods",
                local_target_path=Path(r"C:\Local\Mods"),
                bundle_declared_status="copied",
                bundle_structure_state="present",
                safe_mod_count=1,
            ),
        ),
        mod_entries=(
            RestoreImportPlanningModEntry(
                bundle_item_key="real_mods",
                bundle_item_label="Real Mods directory",
                name="Real Alpha",
                unique_id="Sample.RealAlpha",
                bundle_version="1.0.0",
                local_version=None,
                state="missing_locally",
                local_target_path=Path(r"C:\Local\Mods"),
                note="Present in bundle but missing locally.",
            ),
        ),
        config_entries=tuple(),
        safe_item_count=1,
        review_item_count=0,
        blocked_item_count=0,
        safe_mod_count=1,
        review_mod_count=0,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete: 1 item(s) and 1 bundled mod row(s) plus 0 config artifact(s) look straightforward.",
    )
    review = RestoreImportExecutionReview(
        allowed=True,
        message="Restore/import is ready to write 1 mod folder(s) and 0 config artifact(s) into the current configured destinations. Existing local content will not be merged.",
        executable_mod_count=1,
        executable_config_count=0,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        lambda: bundle_path,
    )

    def fake_plan_restore_import_from_backup_bundle(**kwargs: object) -> RestoreImportPlanningResult:
        captured["service_kwargs"] = kwargs
        return result

    monkeypatch.setattr(
        main_window._shell_service,
        "plan_restore_import_from_backup_bundle",
        fake_plan_restore_import_from_backup_bundle,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "review_restore_import_execution",
        lambda planning_result: review,
    )
    monkeypatch.setattr(
        main_window,
        "_run_background_operation",
        _fake_background_operation_with_real_lifecycle(main_window, captured),
    )

    main_window._on_plan_restore_import()

    execute_button = main_window.findChild(QPushButton, "setup_execute_restore_import_button")
    assert execute_button is not None
    assert captured["operation_names"] == ["Restore/import planning"]
    assert execute_button.isEnabled() is True
    assert "ready to write 1 mod folder" in execute_button.toolTip()


def test_main_window_plan_restore_import_keeps_execute_button_disabled_when_review_blocks(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260318-132000Z"
    bundle_path.mkdir(parents=True)
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-18T13:20:00Z",
        items=tuple(),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=tuple(),
        mod_entries=tuple(),
        config_entries=tuple(),
        safe_item_count=0,
        review_item_count=1,
        blocked_item_count=0,
        safe_mod_count=0,
        review_mod_count=1,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete: 1 item(s) still needs review.",
    )
    review = RestoreImportExecutionReview(
        allowed=False,
        message="Restore/import review is not executable yet. Resolve the remaining review entries first.",
        executable_mod_count=0,
        executable_config_count=0,
        review_entry_count=1,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        main_window,
        "_prompt_for_backup_bundle_path",
        lambda: bundle_path,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "plan_restore_import_from_backup_bundle",
        lambda **kwargs: result,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "review_restore_import_execution",
        lambda planning_result: review,
    )
    monkeypatch.setattr(
        main_window,
        "_run_background_operation",
        _fake_background_operation_with_real_lifecycle(main_window, captured),
    )

    main_window._on_plan_restore_import()

    execute_button = main_window.findChild(QPushButton, "setup_execute_restore_import_button")
    assert execute_button is not None
    assert captured["operation_names"] == ["Restore/import planning"]
    assert execute_button.isEnabled() is False
    assert "not executable yet" in execute_button.toolTip()


def test_main_window_execute_restore_import_runs_service_and_updates_output(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260318-140000Z"
    bundle_path.mkdir(parents=True)
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-18T14:00:00Z",
        items=(
            BackupBundleInspectionItem(
                key="real_mods",
                label="Real Mods directory",
                kind="directory",
                declared_status="copied",
                relative_path=Path("mods") / "real-mods",
                structure_state="present",
            ),
        ),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    planning_result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=(
            RestoreImportPlanningItem(
                key="real_mods",
                label="Real Mods directory",
                state="safe_to_restore_later",
                message="Real Mods directory planning looks straightforward: 1 safe, 0 blocked.",
                bundle_relative_path=Path("mods") / "real-mods",
                local_target_path=Path(r"C:\Local\Mods"),
                bundle_declared_status="copied",
                bundle_structure_state="present",
                safe_mod_count=1,
            ),
        ),
        mod_entries=(
            RestoreImportPlanningModEntry(
                bundle_item_key="real_mods",
                bundle_item_label="Real Mods directory",
                name="Real Alpha",
                unique_id="Sample.RealAlpha",
                bundle_version="1.0.0",
                local_version=None,
                state="missing_locally",
                local_target_path=Path(r"C:\Local\Mods"),
                note="Present in bundle but missing locally.",
            ),
        ),
        config_entries=tuple(),
        safe_item_count=1,
        review_item_count=0,
        blocked_item_count=0,
        safe_mod_count=1,
        review_mod_count=0,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete: 1 item(s) and 1 bundled mod row(s) plus 0 config artifact(s) look straightforward.",
    )
    review = RestoreImportExecutionReview(
        allowed=True,
        message="Restore/import is ready to write 1 mod folder(s) and 0 config artifact(s) into the current configured destinations. Existing local content will not be merged.",
        executable_mod_count=1,
        executable_config_count=0,
    )
    execution_result = RestoreImportExecutionResult(
        bundle_path=bundle_path,
        restored_mod_paths=(Path(r"C:\Local\Mods\RealAlpha"),),
        restored_config_paths=tuple(),
        restored_mod_count=1,
        restored_config_count=0,
        message="Restore/import execution completed: 1 mod folder(s) and 0 config artifact(s) restored.",
    )
    captured: dict[str, object] = {}

    main_window._current_restore_import_planning_result = planning_result
    main_window._current_restore_import_execution_review = review
    main_window._set_active_backup_bundle_context(bundle_path, label_text="planned")
    main_window._refresh_restore_import_execution_state()

    monkeypatch.setattr(
        main_window._shell_service,
        "review_restore_import_execution",
        lambda planning_result: review,
    )

    def fake_execute_restore_import(
        planning: RestoreImportPlanningResult,
        *,
        confirm_execution: bool = False,
    ) -> RestoreImportExecutionResult:
        captured["execute_args"] = (planning, confirm_execution)
        return execution_result

    def fake_run_background_operation(**kwargs: object) -> None:
        captured["operation_name"] = kwargs["operation_name"]
        task_result = kwargs["task_fn"]()
        kwargs["on_success"](task_result)

    monkeypatch.setattr(
        main_window._shell_service,
        "execute_restore_import",
        fake_execute_restore_import,
    )
    monkeypatch.setattr(main_window, "_run_background_operation", fake_run_background_operation)
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    main_window._on_execute_restore_import()

    assert captured["operation_name"] == "Restore/import execution"
    assert captured["execute_args"] == (planning_result, True)
    assert (
        main_window._status_strip_label.text()
        == "Restore/import execution completed: 1 mod folder(s) and 0 config artifact(s) restored."
    )
    assert "restore/import execution" in main_window._setup_output_box.toPlainText().casefold()
    assert r"C:\Local\Mods\RealAlpha" in main_window._setup_output_box.toPlainText()
    execute_button = main_window.findChild(QPushButton, "setup_execute_restore_import_button")
    assert execute_button is not None
    assert execute_button.isEnabled() is True
    assert "refresh restore/import review" in execute_button.toolTip().casefold()


def test_main_window_execute_restore_import_cancel_preserves_no_write(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260318-141000Z"
    bundle_path.mkdir(parents=True)
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-18T14:10:00Z",
        items=tuple(),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    planning_result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=tuple(),
        mod_entries=tuple(),
        config_entries=tuple(),
        safe_item_count=0,
        review_item_count=0,
        blocked_item_count=0,
        safe_mod_count=0,
        review_mod_count=0,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete.",
    )
    review = RestoreImportExecutionReview(
        allowed=True,
        message="Restore/import is ready to write 1 mod folder(s) and 0 config artifact(s) into the current configured destinations. Existing local content will not be merged.",
        executable_mod_count=1,
        executable_config_count=0,
    )
    called: list[bool] = []

    main_window._current_restore_import_planning_result = planning_result
    main_window._current_restore_import_execution_review = review
    main_window._set_active_backup_bundle_context(bundle_path, label_text="planned")
    main_window._refresh_restore_import_execution_state()

    monkeypatch.setattr(
        main_window._shell_service,
        "review_restore_import_execution",
        lambda planning_result: review,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_restore_import",
        lambda *args, **kwargs: called.append(True),
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )

    main_window._on_execute_restore_import()

    assert called == []
    assert main_window._status_strip_label.text() == "Restore/import execution cancelled."


def test_main_window_execute_restore_import_conflict_review_mentions_archive_replace(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_path = tmp_path / "Exports" / "sdvmm-backup-20260321-120000Z"
    bundle_path.mkdir(parents=True)
    manifest_path = bundle_path / "manifest.json"
    summary_path = bundle_path / "README.txt"
    inspection = BackupBundleInspectionResult(
        bundle_path=bundle_path,
        manifest_path=manifest_path,
        summary_path=summary_path,
        bundle_format="sdvmm-local-backup",
        format_version=1,
        created_at_utc="2026-03-21T12:00:00Z",
        items=tuple(),
        structurally_usable=True,
        message="Backup bundle looks structurally usable for future restore/import.",
    )
    planning_result = RestoreImportPlanningResult(
        bundle_path=bundle_path,
        inspection=inspection,
        items=tuple(),
        mod_entries=tuple(),
        config_entries=tuple(),
        safe_item_count=0,
        review_item_count=0,
        blocked_item_count=0,
        safe_mod_count=0,
        review_mod_count=0,
        blocked_mod_count=0,
        safe_config_count=0,
        review_config_count=0,
        blocked_config_count=0,
        message="Restore/import planning complete.",
    )
    review = RestoreImportExecutionReview(
        allowed=True,
        message="Restore/import is ready to write 1 mod folder(s) and 0 config artifact(s) into the current configured destinations. Existing local content will not be merged. 1 mod folder(s) will be archive-and-replaced after explicit review. 1 conflicting config artifact(s) will be resolved by archive-and-replacing the containing mod folder.",
        executable_mod_count=1,
        executable_config_count=0,
        replace_mod_count=1,
        replace_config_count=1,
    )
    captured: dict[str, object] = {}

    main_window._current_restore_import_planning_result = planning_result
    main_window._current_restore_import_execution_review = review
    main_window._set_active_backup_bundle_context(bundle_path, label_text="planned")
    main_window._refresh_restore_import_execution_state()

    monkeypatch.setattr(
        main_window._shell_service,
        "review_restore_import_execution",
        lambda planning_result: review,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_restore_import",
        lambda *args, **kwargs: pytest.fail("execute_restore_import should not run when dialog is cancelled"),
    )

    def fake_question(*args, **kwargs):
        captured["title"] = args[1]
        captured["text"] = args[2]
        return QMessageBox.StandardButton.No

    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.question", fake_question)

    main_window._on_execute_restore_import()

    assert captured["title"] == "Execute restore/import?"
    assert "Archive-and-replace mod folders: 1" in str(captured["text"])
    assert "Conflicting config artifacts resolved by reviewed mod-folder replace: 1" in str(captured["text"])
    assert "archive the current local mod folder before the bundled mod folder is restored" in str(captured["text"])
    assert main_window._status_strip_label.text() == "Restore/import execution cancelled."


@pytest.mark.parametrize(
    ("handler_name", "input_name", "field_label", "button_name"),
    (
        (
            "_on_open_real_mods_folder",
            "setup_mods_path_input",
            "Real Mods folder",
            "setup_open_mods_button",
        ),
        (
            "_on_open_sandbox_mods_folder",
            "setup_sandbox_mods_input",
            "Sandbox Mods folder",
            "setup_open_sandbox_mods_button",
        ),
        (
            "_on_open_real_archive_folder",
            "setup_real_archive_input",
            "Real archive folder",
            "setup_open_real_archive_button",
        ),
        (
            "_on_open_sandbox_archive_folder",
            "setup_sandbox_archive_input",
            "Sandbox archive folder",
            "setup_open_sandbox_archive_button",
        ),
        (
            "_on_open_watched_downloads_folder",
            "setup_watched_downloads_input",
            "Watched downloads path 1",
            "setup_open_watched_downloads_button",
        ),
        (
            "_on_open_secondary_watched_downloads_folder",
            "setup_secondary_watched_downloads_input",
            "Watched downloads path 2",
            "setup_open_secondary_watched_downloads_button",
        ),
    ),
)
def test_main_window_open_folder_actions_delegate_and_update_status(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    handler_name: str,
    input_name: str,
    field_label: str,
    button_name: str,
) -> None:
    target_path = tmp_path / button_name
    target_path.mkdir()
    path_input = main_window.findChild(QLineEdit, input_name)
    assert path_input is not None
    path_input.setText(str(target_path))
    open_button = main_window.findChild(QPushButton, button_name)
    assert open_button is not None

    captured: dict[str, object] = {}
    critical_messages: list[str] = []

    def fake_resolve_configured_folder_for_open(
        *,
        field_label: str,
        path_text: str,
    ) -> Path:
        captured["service"] = (field_label, path_text)
        return target_path

    def fake_open_url(url: object) -> bool:
        captured["opened_url"] = url
        return True

    monkeypatch.setattr(
        main_window._shell_service,
        "resolve_configured_folder_for_open",
        fake_resolve_configured_folder_for_open,
    )
    monkeypatch.setattr("sdvmm.ui.main_window.QDesktopServices.openUrl", fake_open_url)
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.critical",
        lambda *args, **kwargs: critical_messages.append(str(args[2])),
    )

    getattr(main_window, handler_name)()

    assert captured["service"] == (field_label, str(target_path))
    assert Path(captured["opened_url"].toLocalFile()) == target_path
    assert critical_messages == []
    assert main_window._status_strip_label.text() == f"Opened {field_label}: {target_path}"


@pytest.mark.parametrize(
    ("handler_name", "field_label", "error_message"),
    (
        (
            "_on_open_real_mods_folder",
            "Real Mods folder",
            "Real Mods folder is not configured.",
        ),
        (
            "_on_open_secondary_watched_downloads_folder",
            "Watched downloads path 2",
            r"Watched downloads path 2 does not exist: C:\missing\watch-2",
        ),
    ),
)
def test_main_window_open_folder_actions_surface_service_errors(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    handler_name: str,
    field_label: str,
    error_message: str,
) -> None:
    critical_messages: list[str] = []
    open_calls: list[object] = []

    def fake_resolve_configured_folder_for_open(
        *,
        field_label: str,
        path_text: str,
    ) -> Path:
        raise AppShellError(error_message)

    monkeypatch.setattr(
        main_window._shell_service,
        "resolve_configured_folder_for_open",
        fake_resolve_configured_folder_for_open,
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QDesktopServices.openUrl",
        lambda url: open_calls.append(url) or True,
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.critical",
        lambda *args, **kwargs: critical_messages.append(str(args[2])),
    )

    getattr(main_window, handler_name)()

    assert open_calls == []
    assert critical_messages == [error_message]
    assert main_window._status_strip_label.text() == error_message


def test_main_window_open_folder_action_reports_open_failure(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target_path = tmp_path / "Mods"
    target_path.mkdir()
    main_window._mods_path_input.setText(str(target_path))
    critical_messages: list[str] = []

    monkeypatch.setattr(
        main_window._shell_service,
        "resolve_configured_folder_for_open",
        lambda **kwargs: target_path,
    )
    monkeypatch.setattr("sdvmm.ui.main_window.QDesktopServices.openUrl", lambda url: False)
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.critical",
        lambda *args, **kwargs: critical_messages.append(str(args[2])),
    )

    main_window._on_open_real_mods_folder()

    expected_message = f"Could not open Real Mods folder: {target_path}"
    assert critical_messages == [expected_message]
    assert main_window._status_strip_label.text() == expected_message


def test_main_window_start_watch_uses_both_watched_paths_and_updates_status(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_window._watched_downloads_path_input.setText(r"C:\Downloads")
    main_window._secondary_watched_downloads_path_input.setText(r"D:\BuildOutput")

    captured: dict[str, object] = {}

    def fake_initialize_downloads_watch(
        watched_downloads_path_text: str,
        secondary_watched_downloads_path_text: str = "",
    ) -> tuple[Path, ...]:
        captured["initialize"] = (
            watched_downloads_path_text,
            secondary_watched_downloads_path_text,
        )
        return tuple()

    def fake_poll_downloads_watch(**kwargs: object) -> object:
        captured["poll"] = kwargs
        return SimpleNamespace(known_zip_paths=tuple(), intakes=tuple())

    monkeypatch.setattr(
        main_window._shell_service,
        "initialize_downloads_watch",
        fake_initialize_downloads_watch,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "poll_downloads_watch",
        fake_poll_downloads_watch,
    )

    main_window._on_start_watch()

    assert captured["initialize"] == (r"C:\Downloads", r"D:\BuildOutput")
    assert captured["poll"] == {
        "watched_downloads_path_text": r"C:\Downloads",
        "secondary_watched_downloads_path_text": r"D:\BuildOutput",
        "known_zip_paths": tuple(),
        "inventory": main_window._current_inventory_or_empty(),
        "nexus_api_key_text": "",
        "existing_config": main_window._config,
    }
    assert main_window._watch_status_label.text() == "Running | 2 paths | baseline=0 zip(s)"
    assert main_window._watch_status_label.toolTip() == "C:\\Downloads\nD:\\BuildOutput"


def test_main_window_plan_install_surface_has_expected_structure(
    main_window: MainWindow,
) -> None:
    inventory_tabs = main_window._inventory_controls_tabs
    context_tabs = main_window._context_tabs
    mods_page = main_window._mods_page
    plan_tab = main_window.findChild(QWidget, "plan_install_tab")
    plan_scroll = main_window.findChild(QScrollArea, "plan_install_scroll_area")
    plan_content = main_window.findChild(QWidget, "plan_install_tab_content")
    review_top_row = main_window.findChild(QWidget, "plan_install_top_row")
    destination_group = main_window.findChild(QGroupBox, "plan_install_destination_group")
    safety_panel_group = main_window.findChild(QGroupBox, "plan_install_safety_panel_group")
    staged_package_group = main_window.findChild(QGroupBox, "plan_install_staged_package_group")
    execute_group = main_window.findChild(QGroupBox, "plan_install_execute_group")
    plan_review_summary_group = main_window.findChild(QGroupBox, "plan_install_review_summary_group")
    plan_facts_group = main_window.findChild(QGroupBox, "plan_install_facts_group")
    review_output_group = main_window.findChild(QGroupBox, "plan_install_output_group")

    assert inventory_tabs is not None
    assert context_tabs is not None
    assert mods_page is not None
    assert isinstance(inventory_tabs, QTabWidget)
    assert isinstance(context_tabs, QTabWidget)
    assert plan_tab is not None
    assert plan_scroll is not None
    assert plan_content is not None
    assert destination_group is not None
    assert safety_panel_group is not None
    assert staged_package_group is not None
    assert execute_group is not None
    assert plan_review_summary_group is not None
    assert plan_facts_group is not None
    assert review_output_group is not None

    tab_labels = {context_tabs.tabText(index) for index in range(context_tabs.count())}
    assert "Review" in tab_labels
    assert context_tabs.indexOf(main_window._plan_install_tab) >= 0
    assert context_tabs.tabPosition() == QTabWidget.TabPosition.West
    assert inventory_tabs.parentWidget() is mods_page
    assert inventory_tabs.objectName() == "mods_workspace_mode_tabs"
    assert inventory_tabs.tabBar().objectName() == "mods_workspace_mode_tabbar"
    assert inventory_tabs.documentMode() is True
    assert inventory_tabs.tabBar().drawBase() is False

    assert plan_scroll.parentWidget() is plan_tab
    assert plan_scroll.widget() is plan_content

    plan_layout = plan_content.layout()
    intro_label = main_window.findChild(QLabel, "plan_install_intro_label")
    review_state_label = main_window.findChild(QLabel, "plan_install_state_label")
    review_top_row = main_window.findChild(QWidget, "plan_install_top_row")
    review_middle_row = main_window.findChild(QWidget, "plan_install_middle_row")
    assert plan_layout is not None
    assert intro_label is not None
    assert review_state_label is not None
    assert review_top_row is not None
    assert review_middle_row is not None
    assert safety_panel_group.parentWidget() is review_top_row
    assert staged_package_group.parentWidget() is review_top_row
    assert execute_group.parentWidget() is review_middle_row
    assert plan_review_summary_group.parentWidget() is review_middle_row
    assert plan_facts_group.parentWidget() is review_middle_row
    review_top_row_layout = review_top_row.layout()
    assert isinstance(review_top_row_layout, QHBoxLayout)
    assert review_top_row_layout.itemAt(0).widget() is staged_package_group
    assert review_top_row_layout.itemAt(1).widget() is safety_panel_group
    assert plan_layout.indexOf(intro_label) < plan_layout.indexOf(review_state_label)
    assert plan_layout.indexOf(review_state_label) < plan_layout.indexOf(review_top_row)
    assert plan_layout.indexOf(review_top_row) < plan_layout.indexOf(destination_group)
    assert plan_layout.indexOf(destination_group) < plan_layout.indexOf(review_middle_row)
    assert plan_layout.indexOf(review_middle_row) < plan_layout.indexOf(review_output_group)


def test_main_window_plan_install_tab_hosts_scroll_content_for_constrained_height(
    main_window: MainWindow,
) -> None:
    plan_tab = main_window.findChild(QWidget, "plan_install_tab")
    plan_scroll = main_window.findChild(QScrollArea, "plan_install_scroll_area")
    plan_content = main_window.findChild(QWidget, "plan_install_tab_content")

    assert plan_tab is not None
    assert plan_scroll is not None
    assert plan_content is not None
    assert plan_scroll.parentWidget() is plan_tab
    assert plan_scroll.widget() is plan_content
    assert plan_scroll.widgetResizable() is True


def test_main_window_plan_install_safety_panel_exists_and_sandbox_text_is_present(
    main_window: MainWindow,
) -> None:
    panel_group = main_window.findChild(QGroupBox, "plan_install_safety_panel_group")
    panel_text = main_window.findChild(QLabel, "plan_install_safety_panel_text")
    plan_content = main_window.findChild(QWidget, "plan_install_tab_content")
    review_top_row = main_window.findChild(QWidget, "plan_install_top_row")

    assert panel_group is not None
    assert panel_text is not None
    assert plan_content is not None
    assert review_top_row is not None
    assert panel_group.parentWidget() is review_top_row
    assert "Sandbox destination selected (recommended/test path)." in panel_text.text()
    assert "Destination Mods path:" in panel_text.text()
    assert "Archive path:" in panel_text.text()


def test_main_window_mods_workspace_uses_compact_action_band_above_inventory(
    main_window: MainWindow,
) -> None:
    action_band = main_window.findChild(QWidget, "mods_inventory_action_band")
    inventory_tabs = main_window._inventory_controls_tabs

    assert action_band is not None
    assert inventory_tabs is not None
    assert action_band.parentWidget() is inventory_tabs.widget(0)


def test_main_window_key_actions_keep_clear_button_roles(main_window: MainWindow) -> None:
    review_install_button = main_window.findChild(QPushButton, "plan_install_plan_button")
    apply_install_button = main_window.findChild(QPushButton, "plan_install_run_button")

    assert main_window._scan_button.property("buttonRole") == "primary"
    assert main_window._check_updates_button.property("buttonRole") == "secondary"
    assert main_window._open_remote_page_button.property("buttonRole") == "utility"
    assert main_window._search_mods_button.property("buttonRole") == "primary"
    assert main_window._compare_real_vs_sandbox_button.property("buttonRole") == "primary"
    assert main_window._compare_copy_identity_button.property("buttonRole") == "utility"
    assert main_window._refresh_archives_button.property("buttonRole") == "primary"
    assert main_window._restore_archived_button.property("buttonRole") == "secondary"
    assert main_window._delete_archived_button.property("buttonRole") == "danger"
    assert review_install_button is not None
    assert review_install_button.property("buttonRole") == "primary"
    assert review_install_button.isEnabled() is False
    assert apply_install_button is not None
    assert apply_install_button.property("buttonRole") == "secondary"
    assert apply_install_button.isEnabled() is False


def test_main_window_workflow_state_labels_exist(main_window: MainWindow) -> None:
    assert main_window.findChild(QLabel, "mods_inventory_state_label") is main_window._mods_inventory_state_label
    assert (
        main_window.findChild(QLabel, "discovery_results_state_label")
        is main_window._discovery_results_state_label
    )
    assert (
        main_window.findChild(QLabel, "packages_workspace_state_label")
        is main_window._packages_workspace_state_label
    )
    assert (
        main_window.findChild(QLabel, "plan_install_state_label")
        is main_window._plan_install_state_label
    )
    assert (
        main_window.findChild(QLabel, "archive_state_hint_label")
        is main_window._archive_state_hint_label
    )


def test_main_window_workflow_state_labels_reflect_idle_and_ready_states(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    mods_label = main_window._mods_inventory_state_label
    discovery_label = main_window._discovery_results_state_label
    packages_label = main_window._packages_workspace_state_label
    review_label = main_window._plan_install_state_label

    main_window._scan_target_combo.setCurrentIndex(
        main_window._scan_target_combo.findData(SCAN_TARGET_CONFIGURED_REAL_MODS)
    )
    qapp.processEvents()

    assert "Set the Real Mods folder in Setup" in mods_label.text()
    assert "Optional: search by mod name" in discovery_label.text()
    assert "After Setup, choose zip files" in packages_label.text()
    assert "Start in Packages" in review_label.text()

    inventory = _mods_inventory(
        _installed_mod_for_update_ui(
            name="Alpha Mod",
            unique_id="Sample.Alpha",
            folder_name="AlphaMod",
        )
    )
    main_window._render_inventory(inventory)
    qapp.processEvents()
    assert "Run Check for updates" in mods_label.text()

    main_window._discovery_query_input.setText("SMAPI")
    main_window._refresh_workflow_surface_states()
    qapp.processEvents()
    assert "Run Find mods to search this query" in discovery_label.text()

    main_window._set_selected_zip_package_paths(
        (Path(r"C:\Downloads\AlphaPack.zip"),),
        current_path=Path(r"C:\Downloads\AlphaPack.zip"),
    )
    qapp.processEvents()
    assert "Inspect them" in packages_label.text()

    main_window._apply_install_plan_review(_sandbox_install_plan())
    qapp.processEvents()
    assert "Install review is ready" in review_label.text()


def test_main_window_workflow_state_labels_show_running_activity(
    main_window: MainWindow,
) -> None:
    main_window._active_operation_name = "Scan"
    main_window._refresh_workflow_surface_states()
    assert "Scanning the selected Mods source" in main_window._mods_inventory_state_label.text()

    main_window._active_operation_name = "Discovery search"
    main_window._refresh_workflow_surface_states()
    assert "Searching discovery sources" in main_window._discovery_results_state_label.text()

    main_window._active_operation_name = "Archive refresh"
    main_window._refresh_workflow_surface_states()
    assert "Refreshing archive entries" in main_window._archive_empty_state_label.text()
    assert "Restore and delete stay unavailable" in main_window._archive_state_hint_label.text()

    main_window._active_operation_name = None
    main_window._refresh_workflow_surface_states()


def test_main_window_archive_state_hint_updates_for_selection(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    entry = _archived_entry("AlphaMod", "AlphaMod")
    main_window._archived_entries = (entry,)
    main_window._render_archive_entries((entry,))
    qapp.processEvents()

    assert "Select an entry to restore" in main_window._archive_state_hint_label.text()

    main_window._archive_table.selectRow(0)
    qapp.processEvents()

    assert "Archive entry selected" in main_window._archive_state_hint_label.text()


def test_main_window_plan_install_safety_panel_updates_for_real_target(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    panel_text = main_window.findChild(QLabel, "plan_install_safety_panel_text")
    install_target_combo = main_window._install_target_combo
    real_index = install_target_combo.findData(INSTALL_TARGET_CONFIGURED_REAL_MODS)

    assert panel_text is not None
    assert real_index >= 0

    main_window._mods_path_input.setText(r"C:\Game\Mods")
    main_window._real_archive_path_input.setText(r"C:\Game\.sdvmm-real-archive")
    install_target_combo.setCurrentIndex(real_index)
    qapp.processEvents()

    text = panel_text.text()
    assert "REAL game Mods destination selected (live changes warning)." in text
    assert "Destination Mods path: C:\\Game\\Mods" in text
    assert "Archive path: C:\\Game\\.sdvmm-real-archive" in text
    assert "Explicit confirmation is required before execution." in text
    assert "Inspect Recovery after execution if rollback is needed." in text


def test_main_window_plan_install_safety_panel_updates_when_paths_change(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    panel_text = main_window.findChild(QLabel, "plan_install_safety_panel_text")
    install_target_combo = main_window._install_target_combo
    sandbox_index = install_target_combo.findData(INSTALL_TARGET_SANDBOX_MODS)
    real_index = install_target_combo.findData(INSTALL_TARGET_CONFIGURED_REAL_MODS)

    assert panel_text is not None
    assert sandbox_index >= 0
    assert real_index >= 0

    install_target_combo.setCurrentIndex(sandbox_index)
    main_window._sandbox_mods_path_input.setText(r"D:\Sandbox\Mods")
    main_window._sandbox_archive_path_input.setText(r"D:\Sandbox\.sdvmm-sandbox-archive")
    qapp.processEvents()
    sandbox_text = panel_text.text()
    assert "Destination Mods path: D:\\Sandbox\\Mods" in sandbox_text
    assert "Archive path: D:\\Sandbox\\.sdvmm-sandbox-archive" in sandbox_text

    install_target_combo.setCurrentIndex(real_index)
    main_window._mods_path_input.setText(r"E:\Game\Mods")
    main_window._real_archive_path_input.setText(r"E:\Game\.sdvmm-real-archive")
    qapp.processEvents()
    real_text = panel_text.text()
    assert "Destination Mods path: E:\\Game\\Mods" in real_text
    assert "Archive path: E:\\Game\\.sdvmm-real-archive" in real_text


def test_main_window_plan_install_surface_key_controls_exist(
    main_window: MainWindow,
) -> None:
    plan_tab = main_window.findChild(QWidget, "plan_install_tab")
    install_target_combo = main_window.findChild(QComboBox, "plan_install_target_combo")
    overwrite_checkbox = main_window.findChild(QCheckBox, "plan_install_overwrite_checkbox")
    overwrite_help_label = main_window.findChild(QLabel, "plan_install_overwrite_help_label")
    install_archive_label = main_window.findChild(QLabel, "plan_install_archive_label")
    staged_package_group = main_window.findChild(QGroupBox, "plan_install_staged_package_group")
    staged_package_label = main_window.findChild(QLineEdit, "plan_install_staged_package_value")
    plan_review_summary_label = main_window.findChild(QLabel, "plan_install_review_summary_label")
    plan_review_explanation_label = main_window.findChild(
        QLabel, "plan_install_review_explanation_label"
    )
    plan_facts_label = main_window.findChild(QLabel, "plan_install_facts_label")
    plan_button = main_window.findChild(QPushButton, "plan_install_plan_button")
    run_button = main_window.findChild(QPushButton, "plan_install_run_button")

    assert install_target_combo is not None
    assert overwrite_checkbox is not None
    assert overwrite_help_label is not None
    assert install_archive_label is not None
    assert staged_package_group is not None
    assert staged_package_label is not None
    assert plan_review_summary_label is not None
    assert plan_review_explanation_label is not None
    assert plan_facts_label is not None
    assert plan_button is not None
    assert run_button is not None
    assert plan_tab is not None

    main_window._context_tabs.setCurrentWidget(main_window._plan_install_tab)

    assert main_window._install_target_combo is install_target_combo
    assert main_window._overwrite_checkbox is overwrite_checkbox
    assert main_window._install_archive_label is install_archive_label
    assert main_window._staged_package_label is staged_package_label
    assert main_window._plan_review_summary_label is plan_review_summary_label
    assert main_window._plan_review_explanation_label is plan_review_explanation_label
    assert main_window._plan_facts_label is plan_facts_label
    assert staged_package_label.isReadOnly() is True
    assert staged_package_group.title() == "Current package"
    assert overwrite_checkbox.text() == "Enable archive-aware replace"
    assert overwrite_checkbox.isVisible() is True
    assert plan_button.text() == "Review install"
    assert "archive-aware replace" in overwrite_help_label.text().casefold()
    assert (
        plan_review_explanation_label.text()
        == "Review detail: no plan selected."
    )
    assert plan_facts_label.text() == (
        "Entries: -\n"
        "Replace existing: -\n"
        "Archive writes: -\n"
        "Approval required: -\n"
        "Blocked entries: -"
    )


def test_main_window_recovery_selector_uses_readability_contract(
    main_window: MainWindow,
) -> None:
    recovery_combo = main_window.findChild(QComboBox, "recovery_inspection_operation_combo")

    assert recovery_combo is not None
    assert 16 <= recovery_combo.minimumContentsLength() <= 26
    assert (
        recovery_combo.sizeAdjustPolicy()
        == QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    assert recovery_combo.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert recovery_combo.view().minimumWidth() > 0


def test_main_window_plan_and_recovery_output_route_to_local_detail_surfaces(
    main_window: MainWindow,
) -> None:
    main_window._set_plan_install_output_text("Plan output narrative")
    assert main_window._review_output_box.toPlainText() == "Plan output narrative"
    assert main_window._findings_box is main_window._review_output_box
    assert main_window._review_output_group.isHidden() is False
    main_window._set_recovery_output_text("Recovery output narrative")

    assert main_window._recovery_output_box.toPlainText() == "Recovery output narrative"
    assert main_window._findings_box is main_window._recovery_output_box
    assert main_window._recovery_output_group.isHidden() is False


def test_main_window_setup_output_surface_shows_when_text_is_written(
    main_window: MainWindow,
) -> None:
    main_window._set_setup_output_text("Setup output narrative")

    assert main_window._setup_output_box.toPlainText() == "Setup output narrative"
    assert main_window._findings_box is main_window._setup_output_box
    assert main_window._setup_output_group.isHidden() is False


def test_main_window_left_inventory_detail_panel_is_removed_from_visible_shell(
    main_window: MainWindow,
) -> None:
    assert main_window.findChild(QGroupBox, "inventory_output_group") is None

    main_window._set_inventory_output_text("Inventory output narrative")

    assert main_window._inventory_output_box.toPlainText() == "Inventory output narrative"
    assert main_window._findings_box is main_window._inventory_output_box


def test_main_window_local_output_surfaces_exist_without_bottom_detail_region(
    main_window: MainWindow,
) -> None:
    assert main_window.findChild(QGroupBox, "plan_install_detail_access_group") is None
    assert main_window.findChild(QPushButton, "plan_install_view_shared_details_button") is None
    assert main_window.findChild(QCheckBox, "plan_install_show_local_output_toggle") is None
    assert main_window.findChild(QCheckBox, "recovery_show_local_output_toggle") is None
    assert main_window.findChild(QGroupBox, "discovery_output_group") is not None
    assert main_window.findChild(QGroupBox, "compare_output_group") is not None
    assert main_window.findChild(QGroupBox, "archive_output_group") is not None
    assert main_window.findChild(QGroupBox, "plan_install_output_group") is not None
    assert main_window.findChild(QGroupBox, "recovery_output_group") is not None
    assert main_window.findChild(QGroupBox, "packages_intake_detail_access_group") is None
    assert main_window.findChild(QPushButton, "packages_intake_view_shared_details_button") is None
    assert main_window.findChild(QCheckBox, "packages_intake_show_local_output_toggle") is None
    assert main_window.findChild(QGroupBox, "packages_output_group") is not None
    assert main_window.findChild(QGroupBox, "inventory_output_group") is None


def test_main_window_package_inspection_writes_to_packages_detail_surface(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspection = _package_inspection_result("InspectMe.zip", "Sample.InspectMe", mod_count=2)
    batch_result = PackageInspectionBatchResult(
        entries=(
            PackageInspectionBatchEntry(
                package_path=inspection.package_path,
                inspection=inspection,
            ),
        )
    )

    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_zip_batch_with_inventory_context",
        lambda *args, **kwargs: batch_result,
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.build_package_inspection_text",
        lambda payload: "Inspection narrative output" if payload is inspection else "unexpected",
    )

    main_window._zip_path_input.setText(r"C:\Downloads\InspectMe.zip")
    main_window._on_inspect_zip()
    packages_tab = next(
        index
        for index in range(main_window._context_tabs.count())
        if main_window._context_tabs.tabText(index) == "Packages"
    )
    main_window._context_tabs.setCurrentIndex(packages_tab)
    qapp.processEvents()

    assert main_window._packages_output_box.toPlainText() == "Inspection narrative output"
    assert main_window._findings_box is main_window._packages_output_box
    assert (
        main_window._status_strip_label.text()
        == "Zip inspection complete: 2 mod(s) detected. Next step: open Review."
    )
    assert main_window._packages_output_group.isVisible() is True


def test_main_window_browse_zip_accepts_multiple_selected_packages(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected_paths = [
        r"C:\Downloads\Alpha.zip",
        r"C:\Downloads\Beta.zip",
    ]
    first = _package_inspection_result("Alpha.zip", "Sample.Alpha")
    second = _package_inspection_result("Beta.zip", "Sample.Beta")
    batch_result = PackageInspectionBatchResult(
        entries=(
            PackageInspectionBatchEntry(package_path=first.package_path, inspection=first),
            PackageInspectionBatchEntry(package_path=second.package_path, inspection=second),
        )
    )

    monkeypatch.setattr(
        "sdvmm.ui.main_window.QFileDialog.getOpenFileNames",
        lambda *args, **kwargs: (selected_paths, "Zip packages (*.zip)"),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_zip_batch_with_inventory_context",
        lambda *args, **kwargs: batch_result,
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.build_package_inspection_text",
        lambda payload: f"Inspection detail for {payload.package_path.name}",
    )

    main_window._on_browse_zip()

    assert main_window._zip_path_input.text() == selected_paths[0]
    assert main_window._selected_zip_package_paths == tuple(Path(path) for path in selected_paths)
    assert (
        main_window._zip_selection_summary_label.text()
        == "2 zip packages chosen for inspection."
    )
    assert main_window._zip_selection_summary_label.toolTip() == "Alpha.zip\nBeta.zip"
    assert main_window._package_inspection_selector.count() == 2
    assert main_window._package_inspection_selector.isHidden() is False
    assert main_window._package_inspection_selector_label.isHidden() is False
    assert "2 packages inspected" in main_window._package_inspection_summary_label.text()


def test_main_window_zip_selection_summary_reflects_single_manual_path_entry(
    main_window: MainWindow,
) -> None:
    main_window._zip_path_input.setText(r"C:\Downloads\Single.zip")

    assert main_window._selected_zip_package_paths == (Path(r"C:\Downloads\Single.zip"),)
    assert (
        main_window._zip_selection_summary_label.text()
        == "1 zip package chosen: Single.zip"
    )
    assert main_window._zip_selection_summary_label.toolTip() == "Single.zip"


def test_main_window_multi_zip_inspection_keeps_results_per_package(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _package_inspection_result("Alpha.zip", "Sample.Alpha")
    second = _package_inspection_result("Broken.zip", "Sample.Broken")
    batch_result = PackageInspectionBatchResult(
        entries=(
            PackageInspectionBatchEntry(package_path=first.package_path, inspection=first),
            PackageInspectionBatchEntry(
                package_path=second.package_path,
                error_message="File is not a valid zip package: C:\\Downloads\\Broken.zip",
            ),
        )
    )

    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_zip_batch_with_inventory_context",
        lambda *args, **kwargs: batch_result,
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.build_package_inspection_text",
        lambda payload: f"Inspection detail for {payload.package_path.name}",
    )

    main_window._selected_zip_package_paths = (
        first.package_path,
        second.package_path,
    )
    main_window._zip_path_input.setText(str(first.package_path))
    main_window._on_inspect_zip()

    assert main_window._package_inspection_selector.count() == 2
    assert "2 packages inspected" in main_window._package_inspection_summary_label.text()
    assert main_window._package_inspection_result_box.toPlainText() == "Inspection detail for Alpha.zip"
    assert "Package Inspection Batch" in main_window._findings_box.toPlainText()
    assert "- Alpha.zip: 1 mod(s), 0 finding(s), 0 warning(s)" in main_window._findings_box.toPlainText()
    assert "- Broken.zip: failed" in main_window._findings_box.toPlainText()
    assert "select one inspected package at a time for install review" in main_window._findings_box.toPlainText()


def test_main_window_packages_intake_shows_explicit_single_package_review_rule(
    main_window: MainWindow,
) -> None:
    assert (
        main_window._zip_staging_rule_label.text()
        == "Inspect first, then keep one package staged for Review at a time."
    )


def test_main_window_selected_inspected_package_auto_updates_current_review_target(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    first = _package_inspection_result("Alpha.zip", "Sample.Alpha")
    second = _package_inspection_result("Beta.zip", "Sample.Beta")

    main_window._show_package_inspection_results(
        PackageInspectionBatchResult(
            entries=(
                PackageInspectionBatchEntry(package_path=first.package_path, inspection=first),
                PackageInspectionBatchEntry(package_path=second.package_path, inspection=second),
            )
        )
    )
    main_window._package_inspection_selector.setCurrentIndex(1)
    qapp.processEvents()

    qapp.processEvents()

    assert main_window._zip_path_input.text() == str(second.package_path)
    assert main_window._staged_package_label.text() == str(second.package_path)
    assert main_window._staged_package_label.toolTip() == str(second.package_path)
    assert main_window._plan_selected_intake_button.isHidden() is False
    assert main_window._plan_selected_intake_button.isEnabled() is True


def test_main_window_single_valid_inspected_package_hides_selector_and_targets_review(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    failed = PackageInspectionBatchEntry(
        package_path=Path(r"C:\Downloads\Broken.zip"),
        error_message="Bad zip",
    )
    valid = _package_inspection_result("Alpha.zip", "Sample.Alpha")

    main_window._show_package_inspection_results(
        PackageInspectionBatchResult(
            entries=(
                failed,
                PackageInspectionBatchEntry(
                    package_path=valid.package_path,
                    inspection=valid,
                ),
            )
        )
    )
    qapp.processEvents()

    assert main_window._package_inspection_selector.isHidden() is True
    assert main_window._package_inspection_selector_label.isHidden() is True
    assert main_window._zip_path_input.text() == str(valid.package_path)
    assert main_window._staged_package_label.text() == str(valid.package_path)
    assert "Next step: open Review." in main_window._package_inspection_summary_label.text()


def test_main_window_selected_detected_package_auto_updates_current_review_target(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake = _intake_result("AlphaPack.zip", "new_install_candidate", "Alpha Mod", "Sample.Alpha")

    monkeypatch.setattr(
        main_window._shell_service,
        "build_install_plan_from_intake",
        lambda **_: pytest.fail(
            "Selecting a detected package must not build an install plan."
        ),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_sandbox_install_plan",
        lambda *args, **kwargs: pytest.fail("Selecting a detected package must not execute install."),
    )

    main_window._detected_intakes = (intake,)
    main_window._intake_correlations = (_intake_correlation(intake, next_step="Review AlphaPack.zip"),)
    main_window._refresh_intake_selector()
    qapp.processEvents()
    assert main_window._zip_path_input.text() == str(intake.package_path)
    assert main_window._staged_package_label.toolTip() == str(intake.package_path)
    assert main_window._staged_package_label.text() == str(intake.package_path)
    assert main_window._pending_install_plan is None
    assert main_window._plan_selected_intake_button.isHidden() is False
    assert main_window._plan_selected_intake_button.isEnabled() is True


def test_main_window_single_guided_match_auto_selects_detected_package_and_surfaces_message(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matched = _intake_result(
        "MatchedPack.zip",
        "new_install_candidate",
        "Matched Mod",
        "Sample.Matched",
    )
    other = _intake_result(
        "OtherPack.zip",
        "new_install_candidate",
        "Other Mod",
        "Sample.Other",
    )

    def fake_poll_downloads_watch(**_: object) -> object:
        return SimpleNamespace(
            known_zip_paths=(matched.package_path, other.package_path),
            intakes=(matched, other),
        )

    def fake_correlate_intakes_with_updates(**_: object) -> tuple[IntakeUpdateCorrelation, ...]:
        return (
            _intake_correlation(
                matched,
                next_step="Matched package ready",
                matched_guided_update_unique_ids=("Sample.Matched",),
            ),
            _intake_correlation(other, next_step="Review OtherPack.zip"),
        )

    main_window._guided_update_unique_ids = ("Sample.Matched",)
    monkeypatch.setattr(main_window._shell_service, "poll_downloads_watch", fake_poll_downloads_watch)
    monkeypatch.setattr(
        main_window._shell_service,
        "correlate_intakes_with_updates",
        fake_correlate_intakes_with_updates,
    )
    monkeypatch.setattr("sdvmm.ui.main_window.build_downloads_intake_text", lambda result: "watch intake")
    monkeypatch.setattr("sdvmm.ui.main_window.build_intake_correlation_text", lambda correlations: "watch correlations")

    main_window._on_watch_tick()

    expected_message = "Matched update package ready to review: MatchedPack.zip"
    assert main_window._selected_intake_index() == 0
    assert main_window._intake_result_combo.currentData() == 0
    assert "watch intake" in main_window._findings_box.toPlainText()
    assert "watch correlations" in main_window._findings_box.toPlainText()
    assert main_window._status_strip_label.text() == expected_message


def test_main_window_multiple_guided_matches_do_not_guess_and_surface_message(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _intake_result(
        "ExistingPack.zip",
        "new_install_candidate",
        "Existing Mod",
        "Sample.Existing",
    )
    match_a = _intake_result(
        "MatchA.zip",
        "new_install_candidate",
        "Match A",
        "Sample.MatchA",
    )
    match_b = _intake_result(
        "MatchB.zip",
        "new_install_candidate",
        "Match B",
        "Sample.MatchB",
    )

    main_window._detected_intakes = (existing,)
    main_window._intake_correlations = (_intake_correlation(existing, next_step="Keep ExistingPack.zip"),)
    main_window._refresh_intake_selector()
    main_window._intake_result_combo.setCurrentIndex(0)
    main_window._guided_update_unique_ids = ("Sample.MatchA", "Sample.MatchB")

    def fake_poll_downloads_watch(**_: object) -> object:
        return SimpleNamespace(
            known_zip_paths=(existing.package_path, match_a.package_path, match_b.package_path),
            intakes=(match_a, match_b),
        )

    def fake_correlate_intakes_with_updates(**_: object) -> tuple[IntakeUpdateCorrelation, ...]:
        return (
            _intake_correlation(existing, next_step="Keep ExistingPack.zip"),
            _intake_correlation(
                match_a,
                next_step="Review MatchA.zip",
                matched_guided_update_unique_ids=("Sample.MatchA",),
            ),
            _intake_correlation(
                match_b,
                next_step="Review MatchB.zip",
                matched_guided_update_unique_ids=("Sample.MatchB",),
            ),
        )

    monkeypatch.setattr(main_window._shell_service, "poll_downloads_watch", fake_poll_downloads_watch)
    monkeypatch.setattr(
        main_window._shell_service,
        "correlate_intakes_with_updates",
        fake_correlate_intakes_with_updates,
    )
    monkeypatch.setattr("sdvmm.ui.main_window.build_downloads_intake_text", lambda result: "watch intake")
    monkeypatch.setattr("sdvmm.ui.main_window.build_intake_correlation_text", lambda correlations: "watch correlations")

    main_window._on_watch_tick()

    expected_message = (
        "Multiple matched update packages are ready. Choose which package to review in Packages."
    )
    assert main_window._selected_intake_index() == 0
    assert main_window._intake_result_combo.currentData() == 0
    assert "watch intake" in main_window._findings_box.toPlainText()
    assert "watch correlations" in main_window._findings_box.toPlainText()
    assert main_window._status_strip_label.text() == expected_message


def test_main_window_no_actionable_guided_match_leaves_selection_and_output_unchanged(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _intake_result(
        "FirstPack.zip",
        "new_install_candidate",
        "First Mod",
        "Sample.First",
    )
    second = _intake_result(
        "SecondPack.zip",
        "new_install_candidate",
        "Second Mod",
        "Sample.Second",
    )

    main_window._detected_intakes = (first, second)
    main_window._intake_correlations = (
        _intake_correlation(first, next_step="Review FirstPack.zip"),
        _intake_correlation(second, next_step="Review SecondPack.zip"),
    )
    main_window._refresh_intake_selector()
    main_window._intake_result_combo.setCurrentIndex(1)
    main_window._set_intake_output_text("Existing intake output")

    def fake_correlate_intakes_with_updates(**_: object) -> tuple[IntakeUpdateCorrelation, ...]:
        return (
            _intake_correlation(first, next_step="Review FirstPack.zip"),
            _intake_correlation(
                second,
                next_step="Review SecondPack.zip",
                actionable=False,
                matched_guided_update_unique_ids=("Sample.Second",),
            ),
        )

    monkeypatch.setattr(
        main_window._shell_service,
        "correlate_intakes_with_updates",
        fake_correlate_intakes_with_updates,
    )

    main_window._recompute_intake_correlations()

    assert main_window._selected_intake_index() == 1
    assert main_window._intake_result_combo.currentData() == 1
    assert main_window._findings_box.toPlainText() == "Existing intake output"


def test_main_window_staging_auto_selected_guided_match_switches_to_plan_install(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matched = _intake_result(
        "GuidedPack.zip",
        "new_install_candidate",
        "Guided Mod",
        "Sample.Guided",
    )
    other = _intake_result(
        "OtherPack.zip",
        "new_install_candidate",
        "Other Mod",
        "Sample.Other",
    )
    packages_tab = next(
        index
        for index in range(main_window._context_tabs.count())
        if main_window._context_tabs.tabText(index) == "Packages"
    )
    plan_tab = main_window.findChild(QWidget, "plan_install_tab")

    monkeypatch.setattr(
        main_window._shell_service,
        "build_install_plan_from_intake",
        lambda **_: pytest.fail(
            "Opening review must not plan or execute inside Packages."
        ),
    )

    def fake_poll_downloads_watch(**_: object) -> object:
        return SimpleNamespace(
            known_zip_paths=(matched.package_path, other.package_path),
            intakes=(matched, other),
        )

    def fake_correlate_intakes_with_updates(**_: object) -> tuple[IntakeUpdateCorrelation, ...]:
        return (
            _intake_correlation(
                matched,
                next_step="Matched package ready",
                matched_guided_update_unique_ids=("Sample.Guided",),
            ),
            _intake_correlation(other, next_step="Review OtherPack.zip"),
        )

    main_window._context_tabs.setCurrentIndex(packages_tab)
    main_window._guided_update_unique_ids = ("Sample.Guided",)
    main_window._set_current_install_target(INSTALL_TARGET_CONFIGURED_REAL_MODS)
    main_window._overwrite_checkbox.setChecked(True)
    main_window._pending_install_plan = _sandbox_install_plan()
    monkeypatch.setattr(main_window._shell_service, "poll_downloads_watch", fake_poll_downloads_watch)
    monkeypatch.setattr(
        main_window._shell_service,
        "correlate_intakes_with_updates",
        fake_correlate_intakes_with_updates,
    )
    monkeypatch.setattr("sdvmm.ui.main_window.build_downloads_intake_text", lambda result: "watch intake")
    monkeypatch.setattr("sdvmm.ui.main_window.build_intake_correlation_text", lambda correlations: "watch correlations")

    main_window._on_watch_tick()
    main_window._on_plan_selected_intake()
    qapp.processEvents()

    assert plan_tab is not None
    assert main_window._context_tabs.currentWidget() is main_window._plan_install_tab
    assert main_window._zip_path_input.text() == str(matched.package_path)
    assert main_window._staged_package_label.text() == str(matched.package_path)
    assert main_window._staged_package_label.toolTip() == str(matched.package_path)
    assert main_window._current_install_target() == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert main_window._overwrite_checkbox.isChecked() is True
    assert main_window._pending_install_plan is None


def test_main_window_staging_preserves_install_target_and_overwrite_settings_and_clears_stale_plan(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    intake = _intake_result("BetaPack.zip", "new_install_candidate", "Beta Mod", "Sample.Beta")

    main_window._detected_intakes = (intake,)
    main_window._intake_correlations = (_intake_correlation(intake, next_step="Review BetaPack.zip"),)
    main_window._refresh_intake_selector()
    main_window._set_current_install_target(INSTALL_TARGET_CONFIGURED_REAL_MODS)
    main_window._overwrite_checkbox.setChecked(True)
    main_window._pending_install_plan = _sandbox_install_plan()
    qapp.processEvents()

    main_window._on_plan_selected_intake()
    qapp.processEvents()

    assert main_window._current_install_target() == INSTALL_TARGET_CONFIGURED_REAL_MODS
    assert main_window._overwrite_checkbox.isChecked() is True
    assert main_window._zip_path_input.text() == str(intake.package_path)
    assert main_window._pending_install_plan is None


def test_main_window_staging_without_valid_package_surfaces_message_and_keeps_state(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[str] = []
    existing_plan = _sandbox_install_plan()
    packages_tab = next(
        index
        for index in range(main_window._context_tabs.count())
        if main_window._context_tabs.tabText(index) == "Packages"
    )

    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.warning",
        lambda _parent, _title, text: warnings.append(text),
    )

    main_window._detected_intakes = tuple()
    main_window._intake_correlations = tuple()
    main_window._refresh_intake_selector()
    main_window._zip_path_input.setText(r"C:\Packages\Existing.zip")
    main_window._set_package_inspection_result_text(None)
    main_window._pending_install_plan = existing_plan
    main_window._context_tabs.setCurrentIndex(packages_tab)
    qapp.processEvents()

    main_window._on_plan_selected_intake()
    qapp.processEvents()

    expected_message = "Select a detected package or inspect a zip package before opening install review."
    assert warnings == [expected_message]
    assert main_window._findings_box.toPlainText() == expected_message
    assert main_window._status_strip_label.text() == expected_message
    assert main_window._zip_path_input.text() == r"C:\Packages\Existing.zip"
    assert main_window._pending_install_plan is existing_plan
    assert (
        main_window._context_tabs.tabText(main_window._context_tabs.currentIndex())
        == "Packages"
    )


def test_main_window_run_install_without_pending_plan_sets_expected_status(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.warning", lambda *args, **kwargs: None)
    main_window._pending_install_plan = None

    main_window._on_run_install()

    assert main_window._status_strip_label.text() == "Create an install plan before executing install."


def test_main_window_install_related_inputs_invalidate_pending_plan(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    install_target_combo = main_window._install_target_combo
    install_target_next_index = 1 if install_target_combo.currentIndex() == 0 else 0

    invalidation_actions = (
        lambda: install_target_combo.setCurrentIndex(install_target_next_index),
        lambda: main_window._zip_path_input.setText(r"C:\Packages\PlanA.zip"),
        lambda: main_window._sandbox_mods_path_input.setText(r"C:\Sandbox\ModsA"),
        lambda: main_window._sandbox_archive_path_input.setText(r"C:\Sandbox\ArchiveA"),
        lambda: main_window._real_archive_path_input.setText(r"C:\Game\ArchiveA"),
        lambda: main_window._overwrite_checkbox.setChecked(not main_window._overwrite_checkbox.isChecked()),
    )

    for action in invalidation_actions:
        main_window._pending_install_plan = _sandbox_install_plan()
        main_window._set_plan_review_summary_text("Plan review: ready to install.")
        main_window._set_plan_review_explanation_text("Ready: no blocking issues detected.")
        main_window._set_plan_facts_text(
            "Entries: 1\n"
            "Replace existing: no\n"
            "Archive writes: no\n"
            "Approval required: no\n"
            "Blocked entries: 0"
        )
        action()
        qapp.processEvents()
        assert main_window._pending_install_plan is None
        assert main_window._plan_review_summary_label.text() == (
            "Review summary: no plan yet. Click Review install to inspect changes."
        )
        assert main_window._plan_review_explanation_label.text() == "Review detail: no plan selected."
        assert main_window._plan_facts_label.text() == (
            "Entries: -\n"
            "Replace existing: -\n"
            "Archive writes: -\n"
            "Approval required: -\n"
            "Blocked entries: -"
        )


def test_main_window_plan_install_stores_sandbox_plan_and_sets_status(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox_plan = _sandbox_install_plan(destination_kind=INSTALL_TARGET_SANDBOX_MODS)
    build_calls = {"count": 0}
    review = main_window._shell_service.review_install_execution(sandbox_plan)

    def fake_build_install_plan(**_: object) -> SandboxInstallPlan:
        build_calls["count"] += 1
        return sandbox_plan

    monkeypatch.setattr(main_window._shell_service, "build_install_plan", fake_build_install_plan)

    main_window._on_plan_install()

    assert build_calls["count"] == 1
    assert main_window._pending_install_plan is sandbox_plan
    assert main_window._status_strip_label.text() == review.message
    assert main_window._plan_review_summary_label.text() == "Plan review: ready to install."
    assert main_window._plan_review_explanation_label.text() == "Ready: no blocking issues detected."
    assert main_window._plan_facts_label.text() == (
        "Entries: 1\n"
        "Replace existing: no\n"
        "Archive writes: no\n"
        "Approval required: no\n"
        "Blocked entries: 0"
    )
    assert "warning" not in main_window._plan_review_explanation_label.text().casefold()
    assert "blocked" not in main_window._plan_review_explanation_label.text().casefold()
    assert main_window._findings_box.toPlainText().startswith(review.message)
    assert main_window._plan_install_button.property("buttonRole") == "secondary"
    assert main_window._plan_install_button.text() == "Review again"
    assert main_window._run_install_button.property("buttonRole") == "primary"
    assert main_window._run_install_button.isEnabled() is True


def test_main_window_plan_install_stores_real_destination_plan_and_sets_status(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_plan = _sandbox_install_plan(destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS)
    build_calls = {"count": 0}
    review = main_window._shell_service.review_install_execution(real_plan)

    def fake_build_install_plan(**_: object) -> SandboxInstallPlan:
        build_calls["count"] += 1
        return real_plan

    monkeypatch.setattr(main_window._shell_service, "build_install_plan", fake_build_install_plan)

    main_window._on_plan_install()

    assert build_calls["count"] == 1
    assert main_window._pending_install_plan is real_plan
    assert review.requires_explicit_approval is True
    assert main_window._status_strip_label.text() == review.message
    assert main_window._plan_review_explanation_label.text() == "Ready: no blocking issues detected."
    assert "Approval required: yes" in main_window._plan_facts_label.text()
    assert "warning" not in main_window._plan_review_explanation_label.text().casefold()
    assert "blocked" not in main_window._plan_review_explanation_label.text().casefold()
    assert main_window._findings_box.toPlainText().startswith(review.message)


def test_main_window_plan_install_blocked_review_clears_pending_plan_and_sets_status(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked_plan = _sandbox_install_plan(
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        action=BLOCKED,
        can_install=False,
        warnings=("Dependency missing.",),
    )
    review = main_window._shell_service.review_install_execution(blocked_plan)

    monkeypatch.setattr(main_window._shell_service, "build_install_plan", lambda **_: blocked_plan)

    main_window._pending_install_plan = _sandbox_install_plan()
    main_window._on_plan_install()

    assert review.allowed is False
    assert main_window._pending_install_plan is None
    assert main_window._status_strip_label.text() == review.message
    assert main_window._plan_review_summary_label.text() == "Plan review: blocked by dependency issues."
    assert main_window._plan_review_explanation_label.text().startswith("Dependency issue:")
    assert "Blocked entries: 1" in main_window._plan_facts_label.text()
    assert main_window._findings_box.toPlainText().startswith(review.message)


def test_main_window_plan_install_blocked_by_package_issues_sets_summary(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked_package_plan = _sandbox_install_plan(
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        action=BLOCKED,
        can_install=False,
        warnings=("Package manifest invalid.",),
        package_findings=(
            PackageFinding(
                kind=INVALID_MANIFEST_PACKAGE,
                message="Manifest is invalid",
                related_paths=(r"C:\Packages\Sample\manifest.json",),
            ),
        ),
    )
    monkeypatch.setattr(main_window._shell_service, "build_install_plan", lambda **_: blocked_package_plan)

    main_window._on_plan_install()

    assert main_window._pending_install_plan is None
    assert main_window._plan_review_summary_label.text() == "Plan review: blocked by package issues."
    assert main_window._plan_review_explanation_label.text().startswith("Package issue:")


def test_main_window_plan_install_runnable_with_warnings_sets_summary(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning_plan = _sandbox_install_plan(
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        action=INSTALL_NEW,
        can_install=True,
        warnings=("Optional compatibility warning.",),
    )
    monkeypatch.setattr(main_window._shell_service, "build_install_plan", lambda **_: warning_plan)

    main_window._on_plan_install()

    assert main_window._pending_install_plan is warning_plan
    assert main_window._plan_review_summary_label.text() == "Plan review: runnable with warnings."
    assert main_window._plan_review_explanation_label.text().startswith("Warning:")
    assert main_window._plan_facts_label.text() == (
        "Entries: 1\n"
        "Replace existing: no\n"
        "Archive writes: no\n"
        "Approval required: no\n"
        "Blocked entries: 0"
    )


def test_main_window_run_install_uses_confirmation_flow_and_service_gate(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_plan = _sandbox_install_plan(destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS)
    question_calls = {"count": 0}
    execute_calls: list[bool] = []

    def fake_question(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        question_calls["count"] += 1
        return QMessageBox.StandardButton.Yes

    def fake_execute(
        plan: SandboxInstallPlan,
        *,
        confirm_real_destination: bool = False,
    ) -> object:
        assert plan is real_plan
        execute_calls.append(confirm_real_destination)
        raise AppShellError("Execution blocked by review gate.")

    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.question", fake_question)
    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_window._shell_service, "execute_sandbox_install_plan", fake_execute)
    main_window._pending_install_plan = real_plan

    main_window._on_run_install()

    assert question_calls["count"] == 1
    assert execute_calls == [True]
    assert main_window._status_strip_label.text() == "Execution blocked by review gate."
    assert main_window._findings_box.toPlainText() == "Execution blocked by review gate."


def test_main_window_real_install_confirmation_dialog_includes_review_and_summary(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_plan = _sandbox_install_plan(
        destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS,
        action=OVERWRITE_WITH_ARCHIVE,
        target_exists=True,
        archive_path=Path(r"C:\Game\.sdvmm-real-archive\SampleMod-old"),
    )
    review = main_window._shell_service.review_install_execution(real_plan)
    captured: dict[str, str] = {}

    def fake_question(parent: object, title: str, text: str) -> QMessageBox.StandardButton:
        captured["title"] = title
        captured["text"] = text
        return QMessageBox.StandardButton.No

    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.question", fake_question)
    main_window._pending_install_plan = real_plan

    main_window._on_run_install()

    assert captured["title"] == "Confirm REAL Mods install"
    assert review.message in captured["text"]
    assert f"Target: {review.summary.destination_mods_path}" in captured["text"]
    assert f"Archive: {review.summary.archive_path}" in captured["text"]
    assert f"Entries: {review.summary.total_entry_count}" in captured["text"]
    assert "Replace existing targets: yes" in captured["text"]
    assert "Archive writes in plan: yes" in captured["text"]
    assert main_window._status_strip_label.text() == "Install cancelled."


def test_main_window_sandbox_install_confirmation_does_not_use_real_mods_dialog(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox_plan = _sandbox_install_plan(destination_kind=INSTALL_TARGET_SANDBOX_MODS)
    captured: dict[str, str] = {}

    def fake_question(parent: object, title: str, text: str) -> QMessageBox.StandardButton:
        captured["title"] = title
        captured["text"] = text
        return QMessageBox.StandardButton.No

    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.question", fake_question)
    main_window._pending_install_plan = sandbox_plan

    main_window._on_run_install()

    assert captured["title"] == "Confirm sandbox install"
    assert "REAL game Mods directory" not in captured["text"]
    assert main_window._status_strip_label.text() == "Install cancelled."


def test_main_window_run_install_confirm_flow_executes_successfully(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox_plan = _sandbox_install_plan(destination_kind=INSTALL_TARGET_SANDBOX_MODS)
    execute_calls: list[bool] = []

    def fake_question(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        return QMessageBox.StandardButton.Yes

    def fake_execute(
        plan: SandboxInstallPlan,
        *,
        confirm_real_destination: bool = False,
    ) -> object:
        assert plan is sandbox_plan
        execute_calls.append(confirm_real_destination)
        return SimpleNamespace(
            inventory=object(),
            destination_kind=INSTALL_TARGET_SANDBOX_MODS,
            installed_targets=(Path(r"C:\Sandbox\Mods\SampleMod"),),
            archived_targets=tuple(),
            scan_context_path=Path(r"C:\Sandbox\Mods"),
        )

    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.question", fake_question)
    monkeypatch.setattr("sdvmm.ui.main_window.build_sandbox_install_result_text", lambda result: "install ok")
    monkeypatch.setattr(main_window, "_render_inventory", lambda inventory: None)
    monkeypatch.setattr(main_window, "_set_current_scan_target", lambda destination_kind: None)
    monkeypatch.setattr(main_window, "_set_scan_context", lambda path, label: None)
    monkeypatch.setattr(main_window._shell_service, "execute_sandbox_install_plan", fake_execute)
    main_window._pending_install_plan = sandbox_plan

    main_window._on_run_install()

    assert execute_calls == [False]
    assert main_window._status_strip_label.text() == "Sandbox install complete: 1 target(s)"
    assert main_window._findings_box.toPlainText() == "install ok"


def test_main_window_run_install_lock_failure_keeps_dialog_concise_and_details_technical(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox_plan = _sandbox_install_plan(
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
        action=OVERWRITE_WITH_ARCHIVE,
        target_exists=True,
        archive_path=Path(r"C:\Sandbox\.sdvmm-sandbox-archive\SampleMod__sdvmm_archive_001"),
    )
    captured: dict[str, object] = {}
    friendly_message = (
        "Sandbox write failed because Windows is still using files in the target mod folder. "
        "Close Explorer windows or preview panes for that folder, any editor or terminal using the mod, "
        "and the sandbox game or SMAPI if it is still running, then try again."
    )
    technical_detail = (
        "Could not archive existing target before overwrite: "
        r"C:\Sandbox\Mods\SampleMod -> "
        r"C:\Sandbox\.sdvmm-sandbox-archive\SampleMod__sdvmm_archive_001: "
        "[WinError 32] The process cannot access the file because it is being used by another process"
    )

    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.critical",
        lambda *args: captured.setdefault("critical_args", args),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_sandbox_install_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AppShellError(friendly_message, detail_message=technical_detail)
        ),
    )
    main_window._pending_install_plan = sandbox_plan

    main_window._on_run_install()

    assert captured["critical_args"][1:] == ("Install failed", friendly_message)
    assert main_window._status_strip_label.text() == friendly_message
    assert main_window._findings_box.toPlainText() == technical_detail


def test_main_window_successful_install_selects_new_recorded_install_for_recovery(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox_plan = _sandbox_install_plan(destination_kind=INSTALL_TARGET_SANDBOX_MODS)
    old_operation = _install_operation_record_for_ui(operation_id="install_old")
    new_operation = _install_operation_record_for_ui(operation_id="install_new")
    execute_calls: list[bool] = []
    history_call_count = {"count": 0}

    def fake_question(*args: object, **kwargs: object) -> QMessageBox.StandardButton:
        return QMessageBox.StandardButton.Yes

    def fake_execute(
        plan: SandboxInstallPlan,
        *,
        confirm_real_destination: bool = False,
    ) -> object:
        assert plan is sandbox_plan
        execute_calls.append(confirm_real_destination)
        return SimpleNamespace(
            inventory=object(),
            destination_kind=INSTALL_TARGET_SANDBOX_MODS,
            installed_targets=(Path(r"C:\Sandbox\Mods\SampleMod"),),
            archived_targets=tuple(),
            scan_context_path=Path(r"C:\Sandbox\Mods"),
        )

    def fake_load_history() -> object:
        history_call_count["count"] += 1
        if history_call_count["count"] == 1:
            return SimpleNamespace(operations=(old_operation,))
        return SimpleNamespace(operations=(old_operation, new_operation))

    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.question", fake_question)
    monkeypatch.setattr("sdvmm.ui.main_window.build_sandbox_install_result_text", lambda result: "install ok")
    monkeypatch.setattr(main_window, "_render_inventory", lambda inventory: None)
    monkeypatch.setattr(main_window, "_set_current_scan_target", lambda destination_kind: None)
    monkeypatch.setattr(main_window, "_set_scan_context", lambda path, label: None)
    monkeypatch.setattr(main_window._shell_service, "execute_sandbox_install_plan", fake_execute)
    monkeypatch.setattr(main_window._shell_service, "load_install_operation_history", fake_load_history)

    main_window._refresh_install_operation_selector()
    main_window._pending_install_plan = sandbox_plan

    main_window._on_run_install()

    assert execute_calls == [False]
    assert history_call_count["count"] == 2
    assert main_window._status_strip_label.text() == "Sandbox install complete: 1 target(s)"
    assert main_window._findings_box.toPlainText() == "install ok"
    assert main_window._selected_install_operation() is new_operation
    assert main_window._install_history_combo.currentData() == 1
    assert main_window._inspect_recovery_button.isEnabled() is True
    assert main_window._run_recovery_button.isEnabled() is False
    assert main_window._current_recovery_inspection is None


def test_main_window_successful_install_does_not_guess_when_new_record_is_ambiguous(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox_plan = _sandbox_install_plan(destination_kind=INSTALL_TARGET_SANDBOX_MODS)
    old_operation = _install_operation_record_for_ui(operation_id="install_old")
    new_operation_a = _install_operation_record_for_ui(operation_id="install_new_a")
    new_operation_b = _install_operation_record_for_ui(operation_id="install_new_b")
    history_call_count = {"count": 0}

    def fake_load_history() -> object:
        history_call_count["count"] += 1
        if history_call_count["count"] == 1:
            return SimpleNamespace(operations=(old_operation,))
        return SimpleNamespace(operations=(old_operation, new_operation_a, new_operation_b))

    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr("sdvmm.ui.main_window.build_sandbox_install_result_text", lambda result: "install ok")
    monkeypatch.setattr(main_window, "_render_inventory", lambda inventory: None)
    monkeypatch.setattr(main_window, "_set_current_scan_target", lambda destination_kind: None)
    monkeypatch.setattr(main_window, "_set_scan_context", lambda path, label: None)
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_sandbox_install_plan",
        lambda plan, *, confirm_real_destination=False: SimpleNamespace(
            inventory=object(),
            destination_kind=INSTALL_TARGET_SANDBOX_MODS,
            installed_targets=(Path(r"C:\Sandbox\Mods\SampleMod"),),
            archived_targets=tuple(),
            scan_context_path=Path(r"C:\Sandbox\Mods"),
        ),
    )
    monkeypatch.setattr(main_window._shell_service, "load_install_operation_history", fake_load_history)

    main_window._refresh_install_operation_selector()
    main_window._pending_install_plan = sandbox_plan

    main_window._on_run_install()

    assert history_call_count["count"] == 2
    assert main_window._selected_install_operation() is old_operation
    assert main_window._install_history_combo.currentData() == 0
    assert main_window._status_strip_label.text() == "Sandbox install complete: 1 target(s)"
    assert main_window._findings_box.toPlainText() == "install ok"
    assert main_window._run_recovery_button.isEnabled() is False


def test_main_window_background_operation_failure_uses_detailed_output_when_available(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    friendly_message = (
        "Sandbox write failed because Windows is still using files in the target mod folder. "
        "Close Explorer windows or preview panes for that folder, any editor or terminal using the mod, "
        "and the sandbox game or SMAPI if it is still running, then try again."
    )
    technical_detail = (
        "Could not move mod folder to archive: "
        r"C:\Sandbox\Mods\SampleMod -> "
        r"C:\Sandbox\.sdvmm-sandbox-archive\SampleMod__sdvmm_archive_001: "
        "[WinError 5] Access is denied"
    )

    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.critical",
        lambda *args: captured.setdefault("critical_args", args),
    )

    main_window._on_background_operation_failed(
        "Mod removal",
        "Mod removal failed",
        AppShellError(friendly_message, detail_message=technical_detail),
    )

    assert captured["critical_args"][1:] == ("Mod removal failed", friendly_message)
    assert main_window._status_strip_label.text() == friendly_message
    assert main_window._findings_box.toPlainText() == technical_detail


def test_main_window_recovery_selector_labels_are_human_readable_and_newest_first(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    older_operation = _install_operation_record_for_ui(
        operation_id="install_old",
        package_name="OlderPack.zip",
        timestamp="2026-03-12T09:00:00Z",
        destination_kind=INSTALL_TARGET_SANDBOX_MODS,
    )
    newer_operation = _install_operation_record_for_ui(
        operation_id="install_new",
        package_name="NewerPack.zip",
        timestamp="2026-03-13T11:30:00Z",
        destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS,
    )

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(older_operation, newer_operation)),
    )

    main_window._refresh_install_operation_selector()

    assert main_window._install_history_combo.itemText(0) == (
        "NewerPack.zip | 2026-03-13T11:30:00Z | REAL Mods"
    )
    assert main_window._install_history_combo.itemText(1) == (
        "OlderPack.zip | 2026-03-12T09:00:00Z | Sandbox"
    )
    assert main_window._selected_install_operation() is newer_operation


def test_main_window_recovery_selector_labels_mark_legacy_records_clearly(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_operation = _install_operation_record_for_ui(
        operation_id=None,
        package_name="LegacyPack.zip",
        timestamp="2026-03-11T08:00:00Z",
    )

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(legacy_operation,)),
    )

    main_window._refresh_install_operation_selector()

    assert main_window._install_history_combo.itemText(0) == (
        "LegacyPack.zip | 2026-03-11T08:00:00Z | Sandbox | legacy record"
    )


def test_main_window_recovery_selector_filter_modes_show_expected_subsets_and_order(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready_new = _install_operation_record_for_ui(
        operation_id="ready_new",
        package_name="ReadyNew.zip",
        timestamp="2026-03-13T13:00:00Z",
    )
    blocked_mid = _install_operation_record_for_ui(
        operation_id="blocked_mid",
        package_name="BlockedMid.zip",
        timestamp="2026-03-13T12:00:00Z",
        entry_can_install=False,
    )
    legacy_old = _install_operation_record_for_ui(
        operation_id=None,
        package_name="LegacyOld.zip",
        timestamp="2026-03-13T11:00:00Z",
    )
    ready_old = _install_operation_record_for_ui(
        operation_id="ready_old",
        package_name="ReadyOld.zip",
        timestamp="2026-03-13T10:00:00Z",
    )

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(ready_old, legacy_old, blocked_mid, ready_new)),
    )

    main_window._refresh_install_operation_selector()
    qapp.processEvents()
    assert main_window._install_history_combo.itemText(0).startswith("ReadyNew.zip | 2026-03-13T13:00:00Z")
    assert main_window._install_history_combo.itemText(1).startswith("BlockedMid.zip | 2026-03-13T12:00:00Z")
    assert main_window._install_history_combo.itemText(2).startswith("LegacyOld.zip | 2026-03-13T11:00:00Z")
    assert main_window._install_history_combo.itemText(3).startswith("ReadyOld.zip | 2026-03-13T10:00:00Z")

    main_window._install_history_filter_combo.setCurrentText("ready")
    qapp.processEvents()
    assert main_window._install_history_combo.count() == 2
    assert main_window._install_history_combo.itemText(0).startswith("ReadyNew.zip | 2026-03-13T13:00:00Z")
    assert main_window._install_history_combo.itemText(1).startswith("ReadyOld.zip | 2026-03-13T10:00:00Z")

    main_window._install_history_filter_combo.setCurrentText("blocked")
    qapp.processEvents()
    assert main_window._install_history_combo.count() == 1
    assert main_window._install_history_combo.itemText(0).startswith("BlockedMid.zip | 2026-03-13T12:00:00Z")

    main_window._install_history_filter_combo.setCurrentText("legacy")
    qapp.processEvents()
    assert main_window._install_history_combo.count() == 1
    assert main_window._install_history_combo.itemText(0).startswith("LegacyOld.zip | 2026-03-13T11:00:00Z")
    assert "legacy record" in main_window._install_history_combo.itemText(0)


def test_main_window_recovery_selector_filter_fail_soft_when_current_selection_is_hidden(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready_new = _install_operation_record_for_ui(
        operation_id="ready_new",
        package_name="ReadyNew.zip",
        timestamp="2026-03-13T13:00:00Z",
    )
    blocked_mid = _install_operation_record_for_ui(
        operation_id="blocked_mid",
        package_name="BlockedMid.zip",
        timestamp="2026-03-13T12:00:00Z",
        entry_can_install=False,
    )
    legacy_old = _install_operation_record_for_ui(
        operation_id=None,
        package_name="LegacyOld.zip",
        timestamp="2026-03-13T11:00:00Z",
    )

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(legacy_old, blocked_mid, ready_new)),
    )

    main_window._refresh_install_operation_selector()
    blocked_index = main_window._install_history_combo.findData(1)
    assert blocked_index >= 0
    main_window._install_history_combo.setCurrentIndex(blocked_index)
    qapp.processEvents()
    assert main_window._selected_install_operation() is blocked_mid

    main_window._install_history_filter_combo.setCurrentText("legacy")
    qapp.processEvents()

    assert main_window._selected_install_operation() is legacy_old
    summary_text = main_window._recovery_selection_summary_label.text()
    assert "Selected install: LegacyOld.zip" in summary_text
    assert "Legacy record: recovery inspection is unavailable because this entry has no operation ID." in summary_text


def test_main_window_recovery_inspect_run_behavior_remains_intact_for_filtered_visible_entries(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready_operation = _install_operation_record_for_ui(
        operation_id="ready_visible",
        package_name="ReadyVisible.zip",
        timestamp="2026-03-13T13:00:00Z",
    )
    blocked_operation = _install_operation_record_for_ui(
        operation_id="blocked_hidden",
        package_name="BlockedHidden.zip",
        timestamp="2026-03-13T12:00:00Z",
        entry_can_install=False,
    )
    inspection = _install_recovery_inspection_for_ui(
        ready_operation,
        allowed=True,
        review_message="Recovery plan is ready: 2 entries can be executed.",
        executable_count=2,
        non_executable_count=0,
    )
    execute_calls: list[object] = []

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(blocked_operation, ready_operation)),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_install_recovery_by_operation_id",
        lambda operation_id: inspection,
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(main_window, "_render_inventory", lambda inventory: None)
    monkeypatch.setattr(main_window, "_set_current_scan_target", lambda destination_kind: None)
    monkeypatch.setattr(main_window, "_set_scan_context", lambda path, label: None)

    def fake_execute(review: object) -> object:
        execute_calls.append(review)
        return SimpleNamespace(
            review=inspection.recovery_review,
            executed_entry_count=1,
            removed_target_paths=(Path(r"C:\Sandbox\Mods\SampleMod"),),
            restored_target_paths=tuple(),
            destination_kind=INSTALL_TARGET_SANDBOX_MODS,
            destination_mods_path=Path(r"C:\Sandbox\Mods"),
            scan_context_path=Path(r"C:\Sandbox\Mods"),
            inventory=object(),
        )

    monkeypatch.setattr(main_window._shell_service, "execute_install_recovery_review", fake_execute)

    main_window._refresh_install_operation_selector()
    main_window._install_history_filter_combo.setCurrentText("ready")
    qapp.processEvents()
    main_window._on_inspect_selected_install_recovery()
    assert main_window._run_recovery_button.isEnabled() is True

    main_window._on_run_selected_install_recovery()
    qapp.processEvents()

    assert execute_calls == [inspection.recovery_review]
    assert main_window._status_strip_label.text() == "Recovery execution complete: 1 action(s)."


def test_main_window_recovery_summary_updates_for_selection_and_legacy_state(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    newest_operation = _install_operation_record_for_ui(
        operation_id="install_new",
        package_name="NewestPack.zip",
        timestamp="2026-03-13T13:00:00Z",
        destination_kind=INSTALL_TARGET_CONFIGURED_REAL_MODS,
    )
    legacy_operation = _install_operation_record_for_ui(
        operation_id=None,
        package_name="LegacyPack.zip",
        timestamp="2026-03-12T10:00:00Z",
    )

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(legacy_operation, newest_operation)),
    )

    main_window._refresh_install_operation_selector()
    qapp.processEvents()

    summary_text = main_window._recovery_selection_summary_label.text()
    assert "Selected install: NewestPack.zip" in summary_text
    assert "Recorded at: 2026-03-13T13:00:00Z" in summary_text
    assert "Destination: REAL Mods" in summary_text
    assert "Recovery status: not inspected yet." in summary_text

    main_window._install_history_combo.setCurrentIndex(1)
    qapp.processEvents()

    legacy_summary = main_window._recovery_selection_summary_label.text()
    assert "Selected install: LegacyPack.zip" in legacy_summary
    assert "Legacy record: recovery inspection is unavailable because this entry has no operation ID." in legacy_summary


def test_main_window_recovery_inspection_renders_composed_info_and_linked_history(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _install_operation_record_for_ui(operation_id="install_ui_record")
    inspection = _install_recovery_inspection_for_ui(operation)

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(operation,)),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_install_recovery_by_operation_id",
        lambda operation_id: inspection,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_install_recovery_review",
        lambda *args, **kwargs: pytest.fail("Recovery execution must not run during inspection."),
    )

    main_window._refresh_install_operation_selector()
    main_window._install_history_combo.setCurrentIndex(0)
    main_window._on_inspect_selected_install_recovery()
    qapp.processEvents()

    details_text = main_window._findings_box.toPlainText()
    assert main_window._status_strip_label.text() == inspection.recovery_review.message
    assert "Recovery readiness inspection" in details_text
    assert f"Install operation ID: {operation.operation_id}" in details_text
    assert "Recoverable vs non-executable: 2 recoverable / 1 non-executable now" in details_text
    assert "Archive restoration involved: yes" in details_text
    assert "- 2026-03-13T15:00:00Z | completed | executed=1 | removed=1 | restored=0" in details_text
    assert "- 2026-03-13T16:00:00Z | failed_partial | executed=1 | removed=1 | restored=0 | failure=Restore target already exists" in details_text
    summary_text = main_window._recovery_selection_summary_label.text()
    assert "Recovery status: blocked." in summary_text
    assert inspection.recovery_review.message in summary_text
    assert "Latest recovery outcome: failed_partial at 2026-03-13T16:00:00Z (executed=1)." in summary_text


def test_main_window_recovery_inspection_legacy_record_shows_expected_message(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_operation = _install_operation_record_for_ui(operation_id=None)

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(legacy_operation,)),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_install_recovery_by_operation_id",
        lambda operation_id: pytest.fail("Legacy records should not call ID-based inspection."),
    )

    main_window._refresh_install_operation_selector()
    main_window._install_history_combo.setCurrentIndex(0)
    main_window._on_inspect_selected_install_recovery()
    qapp.processEvents()

    expected_message = (
        "Selected install record is legacy and cannot be inspected through the "
        "ID-based recovery path."
    )
    assert main_window._status_strip_label.text() == expected_message
    assert main_window._findings_box.toPlainText() == expected_message


def test_main_window_recovery_inspection_unknown_id_error_is_surfaced_cleanly(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _install_operation_record_for_ui(operation_id="install_missing")

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(operation,)),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_install_recovery_by_operation_id",
        lambda operation_id: (_ for _ in ()).throw(
            AppShellError(f"Install operation ID not found: {operation_id}")
        ),
    )

    main_window._refresh_install_operation_selector()
    main_window._install_history_combo.setCurrentIndex(0)
    main_window._on_inspect_selected_install_recovery()
    qapp.processEvents()

    expected_message = "Install operation ID not found: install_missing"
    assert main_window._status_strip_label.text() == expected_message
    assert main_window._findings_box.toPlainText() == expected_message


def test_main_window_allowed_recovery_inspection_enables_run_and_executes(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _install_operation_record_for_ui(operation_id="install_allowed")
    inspection = _install_recovery_inspection_for_ui(
        operation,
        allowed=True,
        review_message="Recovery plan is ready: 2 entries can be executed.",
        executable_count=2,
        non_executable_count=0,
    )
    execute_calls: list[object] = []

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(operation,)),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_install_recovery_by_operation_id",
        lambda operation_id: inspection,
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(main_window, "_render_inventory", lambda inventory: None)
    monkeypatch.setattr(main_window, "_set_current_scan_target", lambda destination_kind: None)
    monkeypatch.setattr(main_window, "_set_scan_context", lambda path, label: None)

    def fake_execute(review: object) -> object:
        execute_calls.append(review)
        return SimpleNamespace(
            review=inspection.recovery_review,
            executed_entry_count=2,
            removed_target_paths=(Path(r"C:\Sandbox\Mods\SampleMod"),),
            restored_target_paths=(Path(r"C:\Sandbox\Mods\ExistingMod"),),
            destination_kind=INSTALL_TARGET_SANDBOX_MODS,
            destination_mods_path=Path(r"C:\Sandbox\Mods"),
            scan_context_path=Path(r"C:\Sandbox\Mods"),
            inventory=object(),
        )

    monkeypatch.setattr(main_window._shell_service, "execute_install_recovery_review", fake_execute)

    main_window._refresh_install_operation_selector()
    main_window._install_history_combo.setCurrentIndex(0)
    main_window._on_inspect_selected_install_recovery()
    assert main_window._run_recovery_button.isEnabled() is True

    main_window._on_run_selected_install_recovery()
    qapp.processEvents()

    assert execute_calls == [inspection.recovery_review]
    assert main_window._status_strip_label.text() == "Recovery execution complete: 2 action(s)."
    details_text = main_window._findings_box.toPlainText()
    assert "Recovery execution result" in details_text
    assert "Executed actions: 2" in details_text
    assert "Removed targets: 1" in details_text
    assert "Restored targets: 1" in details_text
    assert main_window._run_recovery_button.isEnabled() is False


def test_main_window_blocked_recovery_does_not_execute_and_surfaces_message(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _install_operation_record_for_ui(operation_id="install_blocked")
    inspection = _install_recovery_inspection_for_ui(operation)

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(operation,)),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_install_recovery_by_operation_id",
        lambda operation_id: inspection,
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_install_recovery_review",
        lambda *args, **kwargs: pytest.fail("Blocked recovery must not execute."),
    )

    main_window._refresh_install_operation_selector()
    main_window._install_history_combo.setCurrentIndex(0)
    main_window._on_inspect_selected_install_recovery()
    assert main_window._run_recovery_button.isEnabled() is False

    main_window._on_run_selected_install_recovery()
    qapp.processEvents()

    assert main_window._status_strip_label.text() == inspection.recovery_review.message
    assert "Recovery readiness inspection" in main_window._findings_box.toPlainText()


def test_main_window_legacy_record_cannot_execute_recovery(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy_operation = _install_operation_record_for_ui(operation_id=None)

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(legacy_operation,)),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_install_recovery_review",
        lambda *args, **kwargs: pytest.fail("Legacy records must not execute recovery."),
    )

    main_window._refresh_install_operation_selector()
    main_window._install_history_combo.setCurrentIndex(0)
    main_window._on_run_selected_install_recovery()
    qapp.processEvents()

    expected_message = (
        "Selected install record is legacy and cannot be inspected through the "
        "ID-based recovery path."
    )
    assert main_window._status_strip_label.text() == expected_message
    assert main_window._findings_box.toPlainText() == expected_message


def test_main_window_recovery_confirmation_cancel_leaves_execution_unrun(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation = _install_operation_record_for_ui(operation_id="install_cancel")
    inspection = _install_recovery_inspection_for_ui(
        operation,
        allowed=True,
        review_message="Recovery plan is ready: 2 entries can be executed.",
        executable_count=2,
        non_executable_count=0,
    )
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        main_window._shell_service,
        "load_install_operation_history",
        lambda: SimpleNamespace(operations=(operation,)),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_install_recovery_by_operation_id",
        lambda operation_id: inspection,
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.QMessageBox.question",
        lambda parent, title, text: (
            captured.update({"title": title, "text": text}) or QMessageBox.StandardButton.No
        ),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_install_recovery_review",
        lambda *args, **kwargs: pytest.fail("Cancelled recovery must not execute."),
    )

    main_window._refresh_install_operation_selector()
    main_window._install_history_combo.setCurrentIndex(0)
    main_window._on_inspect_selected_install_recovery()
    main_window._on_run_selected_install_recovery()
    qapp.processEvents()

    assert captured["title"] == "Confirm recovery execution"
    assert inspection.recovery_review.message in captured["text"]
    assert "Executable now: 2/3" in captured["text"]
    assert "Non-executable now: 0" in captured["text"]
    assert "Archive restoration involved: yes" in captured["text"]
    assert main_window._status_strip_label.text() == "Recovery execution cancelled."


def test_main_window_discovery_surface_has_expected_structure(
    main_window: MainWindow,
) -> None:
    context_tabs = main_window._context_tabs
    discovery_page = main_window._discovery_page
    discovery_tab = main_window.findChild(QWidget, "discovery_tab")
    discovery_output_group = main_window.findChild(QGroupBox, "discovery_output_group")
    discovery_search_group = main_window.findChild(QGroupBox, "discovery_search_group")
    discovery_results_group = main_window.findChild(QGroupBox, "discovery_results_group")

    assert context_tabs is not None
    assert isinstance(context_tabs, QTabWidget)
    assert discovery_page is not None
    assert discovery_tab is not None
    assert discovery_output_group is not None
    assert discovery_search_group is not None
    assert discovery_results_group is not None

    tab_labels = {context_tabs.tabText(index) for index in range(context_tabs.count())}
    assert "Discover" in tab_labels
    assert context_tabs.indexOf(discovery_page) >= 0
    assert discovery_tab.parentWidget() is not discovery_page
    assert discovery_output_group.isHidden() is True


def test_main_window_discovery_output_surface_shows_when_text_is_written(
    main_window: MainWindow,
) -> None:
    assert main_window._discovery_output_group.isHidden() is True

    main_window._set_discovery_output_text("Discovery output narrative")

    assert main_window._discovery_output_box.toPlainText() == "Discovery output narrative"
    assert main_window._findings_box is main_window._discovery_output_box
    assert main_window._discovery_output_group.isHidden() is False


def test_main_window_discovery_surface_key_controls_exist(
    main_window: MainWindow,
) -> None:
    discovery_query_input = main_window.findChild(QLineEdit, "discovery_query_input")
    discovery_filter_input = main_window.findChild(QLineEdit, "discovery_filter_input")
    discovery_table = main_window.findChild(QTableWidget, "discovery_results_table")
    discovery_search_button = main_window.findChild(QPushButton, "discovery_search_button")

    assert discovery_query_input is not None
    assert discovery_filter_input is not None
    assert discovery_table is not None
    assert discovery_search_button is not None

    assert main_window._discovery_query_input is discovery_query_input
    assert main_window._discovery_filter_input is discovery_filter_input
    assert main_window._discovery_table is discovery_table
    assert main_window._search_mods_button is discovery_search_button


def test_main_window_compare_surface_has_expected_structure(
    main_window: MainWindow,
) -> None:
    context_tabs = main_window._context_tabs
    compare_tab = main_window.findChild(QWidget, "compare_tab")
    compare_button = main_window.findChild(QPushButton, "compare_run_button")
    compare_filter_combo = main_window.findChild(QComboBox, "compare_category_filter_combo")
    compare_copy_button = main_window.findChild(QPushButton, "compare_copy_identity_button")
    compare_help_label = main_window.findChild(QLabel, "compare_category_help_label")
    compare_table = main_window.findChild(QTableWidget, "compare_results_table")
    compare_summary = main_window.findChild(QLabel, "compare_summary_label")
    compare_output_group = main_window.findChild(QGroupBox, "compare_output_group")

    assert context_tabs is not None
    assert isinstance(context_tabs, QTabWidget)
    assert compare_tab is not None
    assert compare_button is not None
    assert compare_filter_combo is not None
    assert compare_copy_button is not None
    assert compare_help_label is not None
    assert compare_table is not None
    assert compare_summary is not None
    assert compare_output_group is not None

    tab_labels = {context_tabs.tabText(index) for index in range(context_tabs.count())}
    assert "Compare" in tab_labels
    assert context_tabs.indexOf(compare_tab) >= 0
    assert main_window._compare_real_vs_sandbox_button is compare_button
    assert main_window._compare_category_filter_combo is compare_filter_combo
    assert main_window._compare_copy_identity_button is compare_copy_button
    assert main_window._compare_category_help_label is compare_help_label
    assert main_window._compare_results_table is compare_table
    assert main_window._compare_summary_label is compare_summary
    assert compare_filter_combo.currentText() == "Actionable drift"
    assert compare_copy_button.isEnabled() is False
    assert "Ambiguous match means duplicate folders share one UniqueID" in compare_help_label.text()
    assert compare_table.isHidden() is True
    assert compare_output_group.isHidden() is True
    compare_layout = compare_tab.layout()
    assert isinstance(compare_layout, QVBoxLayout)
    assert compare_layout.count() >= 2


def test_main_window_compare_action_renders_real_vs_sandbox_drift(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    compare_button = main_window.findChild(QPushButton, "compare_run_button")
    compare_tab = main_window.findChild(QWidget, "compare_tab")
    captured: dict[str, object] = {}
    result = ModsCompareResult(
        real_mods_path=Path(r"C:\Game\Mods"),
        sandbox_mods_path=Path(r"C:\Sandbox\Mods"),
        real_inventory=_mods_inventory(
            InstalledMod(
                unique_id="Sample.RealOnly",
                name="Real Only",
                version="1.0.0",
                folder_path=Path(r"C:\Game\Mods\RealOnly"),
                manifest_path=Path(r"C:\Game\Mods\RealOnly\manifest.json"),
                dependencies=tuple(),
            ),
            InstalledMod(
                unique_id="Sample.Same",
                name="Same Mod",
                version="1.1.0",
                folder_path=Path(r"C:\Game\Mods\SameMod"),
                manifest_path=Path(r"C:\Game\Mods\SameMod\manifest.json"),
                dependencies=tuple(),
            ),
            InstalledMod(
                unique_id="Sample.Mismatch",
                name="Mismatch Mod",
                version="1.0.0",
                folder_path=Path(r"C:\Game\Mods\MismatchMod"),
                manifest_path=Path(r"C:\Game\Mods\MismatchMod\manifest.json"),
                dependencies=tuple(),
            ),
            InstalledMod(
                unique_id="Sample.Ambiguous",
                name="Ambiguous Mod",
                version="1.0.0",
                folder_path=Path(r"C:\Game\Mods\AmbiguousA"),
                manifest_path=Path(r"C:\Game\Mods\AmbiguousA\manifest.json"),
                dependencies=tuple(),
            ),
        ),
        sandbox_inventory=_mods_inventory(
            InstalledMod(
                unique_id="Sample.SandboxOnly",
                name="Sandbox Only",
                version="2.0.0",
                folder_path=Path(r"C:\Sandbox\Mods\SandboxOnly"),
                manifest_path=Path(r"C:\Sandbox\Mods\SandboxOnly\manifest.json"),
                dependencies=tuple(),
            ),
            InstalledMod(
                unique_id="Sample.Same",
                name="Same Mod",
                version="1.1.0",
                folder_path=Path(r"C:\Sandbox\Mods\SameMod"),
                manifest_path=Path(r"C:\Sandbox\Mods\SameMod\manifest.json"),
                dependencies=tuple(),
            ),
            InstalledMod(
                unique_id="Sample.Mismatch",
                name="Mismatch Mod",
                version="2.0.0",
                folder_path=Path(r"C:\Sandbox\Mods\MismatchMod"),
                manifest_path=Path(r"C:\Sandbox\Mods\MismatchMod\manifest.json"),
                dependencies=tuple(),
            ),
            InstalledMod(
                unique_id="Sample.Ambiguous",
                name="Ambiguous Mod",
                version="1.1.0",
                folder_path=Path(r"C:\Sandbox\Mods\AmbiguousB"),
                manifest_path=Path(r"C:\Sandbox\Mods\AmbiguousB\manifest.json"),
                dependencies=tuple(),
            ),
        ),
        entries=(
            ModsCompareEntry(
                match_key="sample.realonly",
                unique_id="Sample.RealOnly",
                name="Real Only",
                state="only_in_real",
                real_mod=InstalledMod(
                    unique_id="Sample.RealOnly",
                    name="Real Only",
                    version="1.0.0",
                    folder_path=Path(r"C:\Game\Mods\RealOnly"),
                    manifest_path=Path(r"C:\Game\Mods\RealOnly\manifest.json"),
                    dependencies=tuple(),
                ),
                sandbox_mod=None,
            ),
            ModsCompareEntry(
                match_key="sample.sandboxonly",
                unique_id="Sample.SandboxOnly",
                name="Sandbox Only",
                state="only_in_sandbox",
                real_mod=None,
                sandbox_mod=InstalledMod(
                    unique_id="Sample.SandboxOnly",
                    name="Sandbox Only",
                    version="2.0.0",
                    folder_path=Path(r"C:\Sandbox\Mods\SandboxOnly"),
                    manifest_path=Path(r"C:\Sandbox\Mods\SandboxOnly\manifest.json"),
                    dependencies=tuple(),
                ),
            ),
            ModsCompareEntry(
                match_key="sample.same",
                unique_id="Sample.Same",
                name="Same Mod",
                state="same_version",
                real_mod=InstalledMod(
                    unique_id="Sample.Same",
                    name="Same Mod",
                    version="1.1.0",
                    folder_path=Path(r"C:\Game\Mods\SameMod"),
                    manifest_path=Path(r"C:\Game\Mods\SameMod\manifest.json"),
                    dependencies=tuple(),
                ),
                sandbox_mod=InstalledMod(
                    unique_id="Sample.Same",
                    name="Same Mod",
                    version="1.1.0",
                    folder_path=Path(r"C:\Sandbox\Mods\SameMod"),
                    manifest_path=Path(r"C:\Sandbox\Mods\SameMod\manifest.json"),
                    dependencies=tuple(),
                ),
            ),
            ModsCompareEntry(
                match_key="sample.mismatch",
                unique_id="Sample.Mismatch",
                name="Mismatch Mod",
                state="version_mismatch",
                real_mod=InstalledMod(
                    unique_id="Sample.Mismatch",
                    name="Mismatch Mod",
                    version="1.0.0",
                    folder_path=Path(r"C:\Game\Mods\MismatchMod"),
                    manifest_path=Path(r"C:\Game\Mods\MismatchMod\manifest.json"),
                    dependencies=tuple(),
                ),
                sandbox_mod=InstalledMod(
                    unique_id="Sample.Mismatch",
                    name="Mismatch Mod",
                    version="2.0.0",
                    folder_path=Path(r"C:\Sandbox\Mods\MismatchMod"),
                    manifest_path=Path(r"C:\Sandbox\Mods\MismatchMod\manifest.json"),
                    dependencies=tuple(),
                ),
            ),
            ModsCompareEntry(
                match_key="sample.ambiguous",
                unique_id="Sample.Ambiguous",
                name="Ambiguous Mod",
                state="ambiguous_match",
                real_mod=InstalledMod(
                    unique_id="Sample.Ambiguous",
                    name="Ambiguous Mod",
                    version="1.0.0",
                    folder_path=Path(r"C:\Game\Mods\AmbiguousA"),
                    manifest_path=Path(r"C:\Game\Mods\AmbiguousA\manifest.json"),
                    dependencies=tuple(),
                ),
                sandbox_mod=InstalledMod(
                    unique_id="Sample.Ambiguous",
                    name="Ambiguous Mod",
                    version="1.1.0",
                    folder_path=Path(r"C:\Sandbox\Mods\AmbiguousB"),
                    manifest_path=Path(r"C:\Sandbox\Mods\AmbiguousB\manifest.json"),
                    dependencies=tuple(),
                ),
                note="real Mods has 2 folders with this UniqueID.",
            ),
        ),
    )

    assert compare_button is not None
    assert compare_tab is not None

    main_window._mods_path_input.setText(str(result.real_mods_path))
    main_window._sandbox_mods_path_input.setText(str(result.sandbox_mods_path))
    main_window._context_tabs.setCurrentWidget(compare_tab)

    def _fake_compare(**kwargs):
        captured["kwargs"] = kwargs
        return result

    def _run_immediately(
        *,
        operation_name: str,
        running_label: str,
        started_status: str,
        error_title: str,
        task_fn,
        on_success,
    ) -> None:
        captured["operation_name"] = operation_name
        captured["running_label"] = running_label
        captured["started_status"] = started_status
        captured["error_title"] = error_title
        on_success(task_fn())

    monkeypatch.setattr(main_window._shell_service, "compare_real_and_sandbox_mods", _fake_compare)
    monkeypatch.setattr(main_window, "_run_background_operation", _run_immediately)

    compare_button.click()
    qapp.processEvents()

    assert captured["operation_name"] == "Compare real vs sandbox"
    assert captured["running_label"] == "Compare real vs sandbox"
    assert captured["error_title"] == "Compare failed"
    assert "Comparing configured real Mods against sandbox Mods" in str(
        captured["started_status"]
    )
    assert captured["kwargs"] == {
        "configured_mods_path_text": str(result.real_mods_path),
        "sandbox_mods_path_text": str(result.sandbox_mods_path),
        "real_archive_path_text": main_window._real_archive_path_input.text(),
        "sandbox_archive_path_text": main_window._sandbox_archive_path_input.text(),
        "existing_config": None,
    }
    assert main_window._compare_results_table.rowCount() == 5
    assert _visible_row_count(main_window._compare_results_table) == 4
    same_row = _find_mod_row(main_window._compare_results_table, "Same Mod")
    assert same_row >= 0
    assert main_window._compare_results_table.isRowHidden(same_row) is True
    assert "1 only in real" in main_window._compare_summary_label.text()
    assert "1 only in sandbox" in main_window._compare_summary_label.text()
    assert "1 same version" in main_window._compare_summary_label.text()
    assert "1 version mismatch" in main_window._compare_summary_label.text()
    assert "1 ambiguous" in main_window._compare_summary_label.text()
    assert "Showing actionable drift by default." in main_window._compare_summary_label.text()
    assert "select a drift row" in main_window._compare_summary_label.text().casefold()
    assert main_window._compare_results_table.item(0, 0) is not None
    assert "Real vs sandbox Mods compare" in main_window._findings_box.toPlainText()
    assert "Category guide:" in main_window._findings_box.toPlainText()
    rendered_rows = {
        main_window._compare_results_table.item(row, 0).text(): (
            main_window._compare_results_table.item(row, 1).text(),
            main_window._compare_results_table.item(row, 2).text(),
            main_window._compare_results_table.item(row, 3).text(),
            main_window._compare_results_table.item(row, 4).text(),
        )
        for row in range(main_window._compare_results_table.rowCount())
    }
    assert rendered_rows["Real Only"] == ("Only in real", "1.0.0", "-", "-")
    assert rendered_rows["Sandbox Only"] == ("Only in sandbox", "-", "2.0.0", "-")
    assert rendered_rows["Same Mod"] == ("Same version", "1.1.0", "1.1.0", "-")
    assert rendered_rows["Mismatch Mod"] == ("Version mismatch", "1.0.0", "2.0.0", "-")
    assert rendered_rows["Ambiguous Mod"] == (
        "Ambiguous",
        "1.0.0",
        "1.1.0",
        "real Mods has 2 folders with this UniqueID.",
    )
    assert (
        main_window._status_strip_label.text()
        == "Compare complete: 5 row(s) across real and sandbox Mods."
    )


def test_main_window_compare_filter_and_copy_identity_controls_work(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    result = ModsCompareResult(
        real_mods_path=Path(r"C:\Game\Mods"),
        sandbox_mods_path=Path(r"C:\Sandbox\Mods"),
        real_inventory=_mods_inventory(),
        sandbox_inventory=_mods_inventory(),
        entries=(
            ModsCompareEntry(
                match_key="sample.same",
                unique_id="Sample.Same",
                name="Same Mod",
                state="same_version",
                real_mod=InstalledMod(
                    unique_id="Sample.Same",
                    name="Same Mod",
                    version="1.1.0",
                    folder_path=Path(r"C:\Game\Mods\SameMod"),
                    manifest_path=Path(r"C:\Game\Mods\SameMod\manifest.json"),
                    dependencies=tuple(),
                ),
                sandbox_mod=InstalledMod(
                    unique_id="Sample.Same",
                    name="Same Mod",
                    version="1.1.0",
                    folder_path=Path(r"C:\Sandbox\Mods\SameMod"),
                    manifest_path=Path(r"C:\Sandbox\Mods\SameMod\manifest.json"),
                    dependencies=tuple(),
                ),
            ),
            ModsCompareEntry(
                match_key="sample.mismatch",
                unique_id="Sample.Mismatch",
                name="Mismatch Mod",
                state="version_mismatch",
                real_mod=InstalledMod(
                    unique_id="Sample.Mismatch",
                    name="Mismatch Mod",
                    version="1.0.0",
                    folder_path=Path(r"C:\Game\Mods\MismatchMod"),
                    manifest_path=Path(r"C:\Game\Mods\MismatchMod\manifest.json"),
                    dependencies=tuple(),
                ),
                sandbox_mod=InstalledMod(
                    unique_id="Sample.Mismatch",
                    name="Mismatch Mod",
                    version="2.0.0",
                    folder_path=Path(r"C:\Sandbox\Mods\MismatchMod"),
                    manifest_path=Path(r"C:\Sandbox\Mods\MismatchMod\manifest.json"),
                    dependencies=tuple(),
                ),
            ),
        ),
    )

    main_window._on_compare_real_and_sandbox_completed(result)
    qapp.processEvents()

    assert _visible_mod_names(main_window._compare_results_table) == ("Mismatch Mod",)

    main_window._compare_category_filter_combo.setCurrentText("Same version")
    qapp.processEvents()

    assert _visible_mod_names(main_window._compare_results_table) == ("Same Mod",)

    row = _find_mod_row(main_window._compare_results_table, "Same Mod")
    assert row >= 0
    main_window._compare_results_table.selectRow(row)
    qapp.processEvents()

    assert main_window._compare_copy_identity_button.isEnabled() is True
    assert "Same Mod already matches on both sides" in main_window._compare_summary_label.text()
    main_window._compare_copy_identity_button.click()

    assert QApplication.clipboard().text() == "Same Mod | Sample.Same"


def test_main_window_discovery_render_updates_filter_stats_label(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    entries = (
        _discovery_entry("Alpha Mod", "Sample.Alpha"),
        _discovery_entry("Beta Mod", "Sample.Beta"),
        _discovery_entry("Gamma Mod", "Sample.Gamma"),
    )
    discovery_result = ModDiscoveryResult(
        query="sample",
        provider=SMAPI_COMPATIBILITY_LIST_PROVIDER,
        results=entries,
    )
    correlations = tuple(
        _discovery_correlation(entry, context_summary=f"Context {index + 1}")
        for index, entry in enumerate(entries)
    )

    main_window._render_discovery_results(discovery_result, correlations)
    qapp.processEvents()

    assert main_window._discovery_filter_stats_label.text() == "3/3 shown"


def test_main_window_discovery_filter_text_updates_visible_row_counts(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    entries = (
        _discovery_entry("Alpha Mod", "Sample.Alpha"),
        _discovery_entry("Beta Mod", "Sample.Beta"),
        _discovery_entry("Gamma Mod", "Sample.Gamma"),
    )
    discovery_result = ModDiscoveryResult(
        query="sample",
        provider=SMAPI_COMPATIBILITY_LIST_PROVIDER,
        results=entries,
    )
    correlations = tuple(
        _discovery_correlation(entry, context_summary=f"Context {index + 1}")
        for index, entry in enumerate(entries)
    )
    main_window._render_discovery_results(discovery_result, correlations)
    qapp.processEvents()

    main_window._discovery_filter_input.setText("Beta")
    qapp.processEvents()
    assert main_window._discovery_filter_stats_label.text() == "1/3 shown"
    assert _visible_row_count(main_window._discovery_table) == 1

    main_window._discovery_filter_input.setText("NoSuchMod")
    qapp.processEvents()
    assert main_window._discovery_filter_stats_label.text() == "0/3 shown"
    assert _visible_row_count(main_window._discovery_table) == 0

    main_window._discovery_filter_input.clear()
    qapp.processEvents()
    assert main_window._discovery_filter_stats_label.text() == "3/3 shown"
    assert _visible_row_count(main_window._discovery_table) == 3


def test_main_window_selected_discovery_correlation_resolves_selected_row(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    entries = (
        _discovery_entry("Alpha Mod", "Sample.Alpha"),
        _discovery_entry("Beta Mod", "Sample.Beta"),
    )
    discovery_result = ModDiscoveryResult(
        query="sample",
        provider=SMAPI_COMPATIBILITY_LIST_PROVIDER,
        results=entries,
    )
    correlations = (
        _discovery_correlation(entries[0], context_summary="Context Alpha"),
        _discovery_correlation(entries[1], context_summary="Context Beta"),
    )
    main_window._discovery_correlations = correlations
    main_window._render_discovery_results(discovery_result, correlations)
    qapp.processEvents()

    main_window._discovery_table.selectRow(1)
    qapp.processEvents()

    selected_row = main_window._discovery_table.currentRow()
    selected_item = main_window._discovery_table.item(selected_row, 0)
    assert selected_item is not None
    selected_index = selected_item.data(_ROLE_DISCOVERY_INDEX)
    assert isinstance(selected_index, int)
    assert 0 <= selected_index < len(correlations)
    assert main_window._selected_discovery_correlation() is correlations[selected_index]


def test_main_window_open_discovered_page_no_results_sets_expected_status(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.warning", lambda *args, **kwargs: None)
    main_window._current_discovery_result = None

    main_window._on_open_discovered_page()

    assert main_window._status_strip_label.text() == "Run Find mods first."


def test_main_window_open_discovered_page_no_selection_sets_expected_status(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.warning", lambda *args, **kwargs: None)
    entries = (
        _discovery_entry("Alpha Mod", "Sample.Alpha"),
        _discovery_entry("Beta Mod", "Sample.Beta"),
    )
    discovery_result = ModDiscoveryResult(
        query="sample",
        provider=SMAPI_COMPATIBILITY_LIST_PROVIDER,
        results=entries,
    )
    correlations = (
        _discovery_correlation(entries[0], context_summary="Context Alpha"),
        _discovery_correlation(entries[1], context_summary="Context Beta"),
    )
    main_window._current_discovery_result = discovery_result
    main_window._discovery_correlations = correlations
    main_window._render_discovery_results(discovery_result, correlations)
    qapp.processEvents()
    main_window._discovery_table.clearSelection()
    main_window._discovery_table.setCurrentCell(-1, -1)
    qapp.processEvents()

    main_window._on_open_discovered_page()

    assert main_window._status_strip_label.text() == "Select a discovery result row first."


def test_main_window_archive_surface_has_expected_structure(
    main_window: MainWindow,
) -> None:
    context_tabs = main_window._context_tabs
    archive_page = main_window._archive_page
    archive_tab = main_window.findChild(QWidget, "archive_tab")
    archive_empty_state_label = main_window.findChild(QLabel, "archive_empty_state_label")
    archive_state_panel = main_window.findChild(QWidget, "archive_state_panel")
    archive_output_group = main_window.findChild(QGroupBox, "archive_output_group")
    archive_controls_group = main_window.findChild(QGroupBox, "archive_controls_group")
    archive_results_group = main_window.findChild(QGroupBox, "archive_results_group")

    assert context_tabs is not None
    assert isinstance(context_tabs, QTabWidget)
    assert archive_page is not None
    assert archive_tab is not None
    assert archive_empty_state_label is not None
    assert archive_state_panel is not None
    assert archive_output_group is not None
    assert archive_controls_group is not None
    assert archive_results_group is not None

    tab_labels = {context_tabs.tabText(index) for index in range(context_tabs.count())}
    assert "Archive" in tab_labels
    assert context_tabs.indexOf(archive_page) >= 0
    assert archive_tab.parentWidget() is not archive_page
    assert archive_empty_state_label.isHidden() is False
    assert archive_empty_state_label.parentWidget() is archive_state_panel
    assert archive_results_group.isHidden() is True
    assert archive_output_group.isHidden() is True
    archive_page_layout = archive_page.layout()
    assert isinstance(archive_page_layout, QVBoxLayout)
    assert archive_page_layout.count() >= 2


def test_main_window_archive_surface_key_controls_exist(
    main_window: MainWindow,
) -> None:
    archive_filter_input = main_window.findChild(QLineEdit, "archive_filter_input")
    archive_table = main_window.findChild(QTableWidget, "archive_results_table")
    refresh_button = main_window.findChild(QPushButton, "archive_refresh_button")
    restore_button = main_window.findChild(QPushButton, "archive_restore_button")
    delete_button = main_window.findChild(QPushButton, "archive_delete_button")

    assert archive_filter_input is not None
    assert archive_table is not None
    assert refresh_button is not None
    assert restore_button is not None
    assert delete_button is not None

    assert main_window._archive_filter_input is archive_filter_input
    assert main_window._archive_table is archive_table
    assert main_window._refresh_archives_button is refresh_button
    assert main_window._restore_archived_button is restore_button
    assert main_window._delete_archived_button is delete_button


def test_main_window_recovery_surface_has_expected_structure(
    main_window: MainWindow,
) -> None:
    context_tabs = main_window._context_tabs
    recovery_tab = main_window._recovery_page
    recovery_group = main_window.findChild(QGroupBox, "recovery_inspection_group")
    recovery_output_group = main_window.findChild(QGroupBox, "recovery_output_group")

    assert context_tabs is not None
    assert isinstance(context_tabs, QTabWidget)
    assert recovery_tab is not None
    assert recovery_group is not None
    assert recovery_output_group is not None

    tab_labels = {context_tabs.tabText(index) for index in range(context_tabs.count())}
    assert "Recovery" in tab_labels
    assert context_tabs.indexOf(recovery_tab) >= 0


def test_main_window_archive_surface_uses_tighter_spacing_between_actions_and_results(
    main_window: MainWindow,
) -> None:
    archive_controls_group = main_window.findChild(QGroupBox, "archive_controls_group")
    archive_results_group = main_window.findChild(QGroupBox, "archive_results_group")
    archive_tab = main_window.findChild(QWidget, "archive_tab")
    archive_filter_row = main_window.findChild(QWidget, "archive_filter_row")
    archive_actions_row = main_window.findChild(QWidget, "archive_actions_row")

    assert archive_controls_group is not None
    assert archive_results_group is not None
    assert archive_tab is not None
    assert archive_filter_row is not None
    assert archive_actions_row is not None
    assert (
        archive_controls_group.sizePolicy().verticalPolicy()
        == QSizePolicy.Policy.Maximum
    )
    archive_layout = archive_tab.layout()
    assert isinstance(archive_layout, QVBoxLayout)
    assert archive_layout.itemAt(archive_layout.count() - 1).spacerItem() is not None

    results_layout = archive_results_group.layout()
    assert isinstance(results_layout, QVBoxLayout)
    margins = results_layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (10, 10, 10, 10)
    assert results_layout.spacing() == 6


def test_main_window_archive_buttons_toggle_with_row_selection(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    restore_button = main_window._restore_archived_button
    delete_button = main_window._delete_archived_button

    assert restore_button.isEnabled() is False
    assert delete_button.isEnabled() is False

    entries = (
        _archived_entry("AlphaMod", "mods/AlphaMod"),
        _archived_entry("BetaMod", "mods/BetaMod"),
    )
    main_window._archived_entries = entries
    main_window._render_archive_entries(entries)
    qapp.processEvents()

    main_window._archive_table.selectRow(0)
    qapp.processEvents()
    assert restore_button.isEnabled() is True
    assert delete_button.isEnabled() is True

    main_window._archive_table.clearSelection()
    main_window._archive_table.setCurrentCell(-1, -1)
    main_window._on_archive_selection_changed()
    qapp.processEvents()
    assert restore_button.isEnabled() is False
    assert delete_button.isEnabled() is False


def test_main_window_archive_filter_updates_stats_label(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    entries = (
        _archived_entry("AlphaMod", "mods/AlphaMod"),
        _archived_entry("BetaMod", "mods/BetaMod"),
        _archived_entry("GammaMod", "mods/GammaMod"),
    )
    main_window._archived_entries = entries
    main_window._render_archive_entries(entries)
    qapp.processEvents()

    stats_label = main_window._archive_filter_stats_label
    assert stats_label.text() == "3/3 shown"

    main_window._archive_filter_input.setText("BetaMod")
    qapp.processEvents()
    assert stats_label.text() == "1/3 shown"

    main_window._archive_filter_input.setText("NoSuchMod")
    qapp.processEvents()
    assert stats_label.text() == "0/3 shown"

    main_window._archive_filter_input.clear()
    qapp.processEvents()
    assert stats_label.text() == "3/3 shown"


def test_main_window_intake_selector_empty_state_disables_combo_and_plan_button(
    main_window: MainWindow,
) -> None:
    main_window._detected_intakes = tuple()
    main_window._intake_correlations = tuple()
    main_window._refresh_intake_selector()

    assert main_window._intake_result_combo.count() == 1
    assert main_window._intake_result_combo.itemText(0) == "<no detected packages>"
    assert main_window._intake_result_combo.currentData() == -1
    assert main_window._intake_result_combo.isEnabled() is False
    assert main_window._plan_selected_intake_button.isEnabled() is False


def test_main_window_rendering_intakes_updates_filter_stats_label(
    main_window: MainWindow,
) -> None:
    intakes = (
        _intake_result("AlphaPack.zip", "new_install_candidate", "Alpha Mod", "Sample.Alpha"),
        _intake_result("BetaPack.zip", "new_install_candidate", "Beta Mod", "Sample.Beta"),
        _intake_result("GammaPack.zip", "new_install_candidate", "Gamma Mod", "Sample.Gamma"),
    )
    main_window._detected_intakes = intakes
    main_window._intake_correlations = tuple(
        _intake_correlation(intake, next_step=f"Review {intake.package_path.name}") for intake in intakes
    )

    main_window._refresh_intake_selector()

    assert main_window._intake_filter_stats_label.text() == "3/3 shown"


def test_main_window_intake_filter_updates_visible_entries_and_stats(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    intakes = (
        _intake_result("AlphaPack.zip", "new_install_candidate", "Alpha Mod", "Sample.Alpha"),
        _intake_result("BetaPack.zip", "new_install_candidate", "Beta Mod", "Sample.Beta"),
        _intake_result("GammaPack.zip", "new_install_candidate", "Gamma Mod", "Sample.Gamma"),
    )
    main_window._detected_intakes = intakes
    main_window._intake_correlations = tuple(
        _intake_correlation(intake, next_step=f"Review {intake.package_path.name}") for intake in intakes
    )
    main_window._refresh_intake_selector()
    qapp.processEvents()

    main_window._intake_filter_input.setText("BetaPack")
    qapp.processEvents()
    assert main_window._intake_filter_stats_label.text() == "1/3 shown"
    assert main_window._intake_result_combo.count() == 1
    assert "BetaPack.zip" in main_window._intake_result_combo.itemText(0)

    main_window._intake_filter_input.setText("NoSuchPackage")
    qapp.processEvents()
    assert main_window._intake_filter_stats_label.text() == "0/3 shown"
    assert main_window._intake_result_combo.count() == 1
    assert main_window._intake_result_combo.itemText(0) == "<no detected packages match filter>"
    assert main_window._intake_result_combo.currentData() == -1
    assert main_window._intake_result_combo.isEnabled() is False

    main_window._intake_filter_input.clear()
    qapp.processEvents()
    assert main_window._intake_filter_stats_label.text() == "3/3 shown"
    assert main_window._intake_result_combo.count() == 3
    assert main_window._intake_result_combo.isEnabled() is True


def test_main_window_selecting_valid_intake_enables_plan_selected_button(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    intakes = (
        _intake_result("AlphaPack.zip", "new_install_candidate", "Alpha Mod", "Sample.Alpha"),
        _intake_result("BetaPack.zip", "new_install_candidate", "Beta Mod", "Sample.Beta"),
    )
    main_window._detected_intakes = intakes
    main_window._intake_correlations = tuple(
        _intake_correlation(intake, next_step=f"Review {intake.package_path.name}") for intake in intakes
    )
    main_window._refresh_intake_selector()
    qapp.processEvents()

    main_window._intake_result_combo.setCurrentIndex(-1)
    main_window._on_intake_selection_changed()
    qapp.processEvents()
    assert main_window._plan_selected_intake_button.isEnabled() is False

    main_window._intake_result_combo.setCurrentIndex(0)
    qapp.processEvents()
    assert main_window._selected_intake_index() >= 0
    assert main_window._plan_selected_intake_button.isEnabled() is True
    assert main_window._plan_selected_intake_button.text() == "Open Review"
    assert "selected detected package" in main_window._plan_selected_intake_button.toolTip()


def test_main_window_intake_selection_does_not_override_global_operation_status(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    intakes = (
        _intake_result("AlphaPack.zip", "new_install_candidate", "Alpha Mod", "Sample.Alpha"),
        _intake_result("BetaPack.zip", "new_install_candidate", "Beta Mod", "Sample.Beta"),
    )
    main_window._detected_intakes = intakes
    main_window._intake_correlations = tuple(
        _intake_correlation(intake, next_step=f"Review {intake.package_path.name}") for intake in intakes
    )
    main_window._refresh_intake_selector()
    qapp.processEvents()

    operation_status = "Update check complete: 2 mod(s)"
    main_window._set_status(operation_status)
    main_window._intake_result_combo.setCurrentIndex(0)
    qapp.processEvents()

    assert main_window._status_strip_label.text() == operation_status
    assert main_window._plan_selected_intake_button.isEnabled() is True


def test_main_window_watched_path_change_clears_intakes_and_stops_active_watcher(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    intakes = (
        _intake_result("AlphaPack.zip", "new_install_candidate", "Alpha Mod", "Sample.Alpha"),
        _intake_result("BetaPack.zip", "new_install_candidate", "Beta Mod", "Sample.Beta"),
    )
    main_window._detected_intakes = intakes
    main_window._intake_correlations = tuple(
        _intake_correlation(intake, next_step=f"Review {intake.package_path.name}") for intake in intakes
    )
    main_window._refresh_intake_selector()
    main_window._watch_status_label.setText("Running")
    main_window._watch_timer.start()
    assert main_window._watch_timer.isActive() is True

    main_window._watched_downloads_path_input.setText(r"C:\Downloads\Observed")
    qapp.processEvents()

    assert main_window._detected_intakes == tuple()
    assert main_window._intake_correlations == tuple()
    assert main_window._intake_result_combo.count() == 1
    assert main_window._intake_result_combo.itemText(0) == "<no detected packages>"
    assert main_window._intake_result_combo.currentData() == -1
    assert main_window._intake_result_combo.isEnabled() is False
    assert main_window._plan_selected_intake_button.isEnabled() is False
    assert main_window._watch_timer.isActive() is False
    assert main_window._watch_status_label.text() == "Stopped (path changed)"


def test_main_window_watched_path_change_sets_expected_status_when_active_watcher_stops(
    main_window: MainWindow,
) -> None:
    main_window._watch_timer.start()
    assert main_window._watch_timer.isActive() is True

    main_window._on_watched_path_changed()

    assert main_window._status_strip_label.text() == "Watcher stopped because watched path changed."


def test_main_window_scan_completion_refreshes_detected_package_state(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    stale_intake = replace(
        _intake_result(
            "UpdatePack.zip",
            "update_replace_candidate",
            "Alpha Mod",
            "Sample.Alpha",
        ),
        matched_installed_unique_ids=("Sample.Alpha",),
    )
    refreshed_intake = replace(
        stale_intake,
        classification="new_install_candidate",
        matched_installed_unique_ids=tuple(),
        message="Package appears to contain a new mod not present in current inventory.",
    )
    calls: dict[str, object] = {}

    def fake_refresh_detected_intakes_against_inventory(
        *,
        intakes: tuple[DownloadsIntakeResult, ...],
        inventory: ModsInventory | None,
    ) -> tuple[DownloadsIntakeResult, ...]:
        calls["intakes"] = intakes
        calls["inventory"] = inventory
        return (refreshed_intake,)

    main_window._detected_intakes = (stale_intake,)
    monkeypatch.setattr(
        main_window._shell_service,
        "refresh_detected_intakes_against_inventory",
        fake_refresh_detected_intakes_against_inventory,
    )

    main_window._on_scan_completed(
        SimpleNamespace(
            inventory=_mods_inventory(),
            scan_path=Path(r"C:\Sandbox\Mods"),
            target_kind=SCAN_TARGET_SANDBOX_MODS,
        )
    )
    qapp.processEvents()

    assert calls["intakes"] == (stale_intake,)
    assert isinstance(calls["inventory"], ModsInventory)
    assert main_window._detected_intakes == (refreshed_intake,)
    assert main_window._intake_correlations[0].intake.classification == "new_install_candidate"
    assert main_window._stage_update_intake_button.isHidden() is True


def test_main_window_stage_update_button_only_appears_for_update_like_detected_package(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    non_update_intake = _intake_result(
        "FreshPack.zip",
        "new_install_candidate",
        "Fresh Mod",
        "Sample.Fresh",
    )
    update_intake = replace(
        _intake_result(
            "UpdatePack.zip",
            "update_replace_candidate",
            "Alpha Mod",
            "Sample.Alpha",
        ),
        matched_installed_unique_ids=("Sample.Alpha",),
    )

    main_window._detected_intakes = (non_update_intake,)
    main_window._intake_correlations = (
        _intake_correlation(
            non_update_intake,
            next_step="Stage for Install / Update review.",
        ),
    )
    main_window._refresh_intake_selector()
    qapp.processEvents()

    assert main_window._plan_selected_intake_button.isEnabled() is True
    assert main_window._plan_selected_intake_button.text() == "Open Review"
    assert main_window._stage_update_intake_button.isHidden() is True

    main_window._detected_intakes = (update_intake,)
    main_window._intake_correlations = (
        _intake_correlation(
            update_intake,
            next_step="Stage update.",
            matched_update_available_unique_ids=("Sample.Alpha",),
        ),
    )
    main_window._refresh_intake_selector()
    qapp.processEvents()

    assert main_window._plan_selected_intake_button.isEnabled() is True
    assert main_window._stage_update_intake_button.isHidden() is False
    assert main_window._stage_update_intake_button.isEnabled() is True


def test_main_window_review_action_hierarchy_leads_with_read_only_step_until_plan_exists(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    main_window._set_selected_zip_package_paths(
        (Path(r"C:\Downloads\AlphaPack.zip"),),
        current_path=Path(r"C:\Downloads\AlphaPack.zip"),
    )
    qapp.processEvents()

    assert main_window._plan_install_button.property("buttonRole") == "primary"
    assert main_window._plan_install_button.isEnabled() is True
    assert main_window._plan_install_button.text() == "Review install"
    assert main_window._run_install_button.property("buttonRole") == "secondary"
    assert main_window._run_install_button.isEnabled() is False

    main_window._apply_install_plan_review(_sandbox_install_plan())
    qapp.processEvents()

    assert main_window._plan_install_button.property("buttonRole") == "secondary"
    assert main_window._plan_install_button.text() == "Review again"
    assert main_window._run_install_button.property("buttonRole") == "primary"
    assert main_window._run_install_button.isEnabled() is True


def test_main_window_stage_update_carries_archive_replace_intent_into_plan(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    update_intake = replace(
        _intake_result(
            "UpdatePack.zip",
            "update_replace_candidate",
            "Alpha Mod",
            "Sample.Alpha",
        ),
        matched_installed_unique_ids=("Sample.Alpha",),
    )
    main_window._detected_intakes = (update_intake,)
    main_window._intake_correlations = (
        _intake_correlation(
            update_intake,
            next_step="Stage update.",
            matched_update_available_unique_ids=("Sample.Alpha",),
        ),
    )
    main_window._refresh_intake_selector()
    qapp.processEvents()

    captured: dict[str, object] = {}

    def fake_build_install_plan(
        *,
        package_path_text: str,
        install_target: str,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        allow_overwrite: bool,
        configured_real_mods_path: Path | None = None,
        nexus_api_key_text: str = "",
        existing_config: object | None = None,
    ) -> SandboxInstallPlan:
        captured["package_path_text"] = package_path_text
        captured["allow_overwrite"] = allow_overwrite
        return _sandbox_install_plan(
            action=OVERWRITE_WITH_ARCHIVE,
            target_exists=True,
            archive_path=Path(r"C:\Sandbox\.sdvmm-sandbox-archive\SampleMod-old"),
            warnings=("Archive existing target before overwrite.",),
        )

    monkeypatch.setattr(main_window._shell_service, "build_install_plan", fake_build_install_plan)

    main_window._overwrite_checkbox.setChecked(False)
    main_window._on_stage_selected_intake_update()
    main_window._on_plan_install()

    assert main_window._overwrite_checkbox.isChecked() is True
    assert captured["package_path_text"] == str(update_intake.package_path)
    assert captured["allow_overwrite"] is True
    assert main_window._pending_install_plan is not None
    assert main_window._pending_install_plan.entries[0].action == OVERWRITE_WITH_ARCHIVE


def test_main_window_normal_staging_does_not_inherit_auto_overwrite_from_stage_update(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    update_intake = replace(
        _intake_result(
            "UpdatePack.zip",
            "update_replace_candidate",
            "Alpha Mod",
            "Sample.Alpha",
        ),
        matched_installed_unique_ids=("Sample.Alpha",),
    )
    normal_intake = _intake_result(
        "FreshPack.zip",
        "new_install_candidate",
        "Fresh Mod",
        "Sample.Fresh",
    )
    main_window._detected_intakes = (update_intake,)
    main_window._intake_correlations = (
        _intake_correlation(
            update_intake,
            next_step="Stage update.",
            matched_update_available_unique_ids=("Sample.Alpha",),
        ),
    )
    main_window._refresh_intake_selector()
    qapp.processEvents()

    main_window._on_stage_selected_intake_update()
    assert main_window._overwrite_checkbox.isChecked() is True

    main_window._detected_intakes = (normal_intake,)
    main_window._intake_correlations = (
        _intake_correlation(
            normal_intake,
            next_step="Stage for Install / Update review.",
        ),
    )
    main_window._refresh_intake_selector()
    qapp.processEvents()

    captured: dict[str, object] = {}

    def fake_build_install_plan(
        *,
        package_path_text: str,
        install_target: str,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        allow_overwrite: bool,
        configured_real_mods_path: Path | None = None,
        nexus_api_key_text: str = "",
        existing_config: object | None = None,
    ) -> SandboxInstallPlan:
        captured["allow_overwrite"] = allow_overwrite
        return _sandbox_install_plan()

    monkeypatch.setattr(main_window._shell_service, "build_install_plan", fake_build_install_plan)

    main_window._on_plan_selected_intake()
    main_window._on_plan_install()

    assert main_window._overwrite_checkbox.isChecked() is False
    assert captured["allow_overwrite"] is False


def test_main_window_manual_overwrite_choice_still_applies_after_stage_update(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
    qapp: QApplication,
) -> None:
    update_intake = replace(
        _intake_result(
            "UpdatePack.zip",
            "update_replace_candidate",
            "Alpha Mod",
            "Sample.Alpha",
        ),
        matched_installed_unique_ids=("Sample.Alpha",),
    )
    normal_intake = _intake_result(
        "FreshPack.zip",
        "new_install_candidate",
        "Fresh Mod",
        "Sample.Fresh",
    )
    main_window._detected_intakes = (update_intake,)
    main_window._intake_correlations = (
        _intake_correlation(
            update_intake,
            next_step="Stage update.",
            matched_update_available_unique_ids=("Sample.Alpha",),
        ),
    )
    main_window._refresh_intake_selector()
    qapp.processEvents()

    main_window._on_stage_selected_intake_update()
    assert main_window._overwrite_checkbox.isChecked() is True

    main_window._overwrite_checkbox.setChecked(False)
    main_window._overwrite_checkbox.setChecked(True)

    main_window._detected_intakes = (normal_intake,)
    main_window._intake_correlations = (
        _intake_correlation(
            normal_intake,
            next_step="Stage for Install / Update review.",
        ),
    )
    main_window._refresh_intake_selector()
    qapp.processEvents()

    captured: dict[str, object] = {}

    def fake_build_install_plan(
        *,
        package_path_text: str,
        install_target: str,
        configured_mods_path_text: str,
        sandbox_mods_path_text: str,
        real_archive_path_text: str,
        sandbox_archive_path_text: str,
        allow_overwrite: bool,
        configured_real_mods_path: Path | None = None,
        nexus_api_key_text: str = "",
        existing_config: object | None = None,
    ) -> SandboxInstallPlan:
        captured["allow_overwrite"] = allow_overwrite
        return _sandbox_install_plan(action=OVERWRITE_WITH_ARCHIVE)

    monkeypatch.setattr(main_window._shell_service, "build_install_plan", fake_build_install_plan)

    main_window._on_plan_selected_intake()
    main_window._on_plan_install()

    assert main_window._overwrite_checkbox.isChecked() is True
    assert captured["allow_overwrite"] is True


def test_main_window_secondary_watched_path_change_stops_active_watcher(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    main_window._watch_timer.start()
    assert main_window._watch_timer.isActive() is True

    main_window._secondary_watched_downloads_path_input.setText(r"D:\BuildOutput")
    qapp.processEvents()

    assert main_window._watch_timer.isActive() is False
    assert main_window._watch_status_label.text() == "Stopped (path changed)"
    assert main_window._status_strip_label.text() == "Watcher stopped because watched path changed."


def test_main_window_package_inspection_result_text_controls_visibility(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inspection_group = main_window._package_inspection_result_group
    inspection_box = main_window._package_inspection_result_box
    package_tab_index = next(
        index
        for index in range(main_window._context_tabs.count())
        if main_window._context_tabs.tabText(index) == "Packages"
    )

    assert inspection_group.isVisible() is False
    assert inspection_box.toPlainText() == ""

    main_window._context_tabs.setCurrentIndex(package_tab_index)
    qapp.processEvents()
    main_window._set_package_inspection_result_text("Detected package details")
    qapp.processEvents()

    assert inspection_group.isHidden() is False
    assert inspection_group.isVisible() is True
    assert inspection_box.toPlainText() == "Detected package details"

    main_window._set_package_inspection_result_text("")
    qapp.processEvents()

    assert inspection_group.isVisible() is False
    assert inspection_box.toPlainText() == ""

    main_window._set_package_inspection_result_text("Detected package details")
    qapp.processEvents()
    main_window._set_package_inspection_result_text(None)
    qapp.processEvents()

    assert inspection_group.isVisible() is False
    assert inspection_box.toPlainText() == ""


def _archived_entry(folder_name: str, target_folder_name: str) -> ArchivedModEntry:
    return ArchivedModEntry(
        source_kind="sandbox",
        archive_root=Path(r"C:\ArchiveRoot"),
        archived_path=Path(r"C:\ArchiveRoot") / folder_name,
        archived_folder_name=folder_name,
        target_folder_name=target_folder_name,
        mod_name=folder_name,
        unique_id=f"Sample.{folder_name}",
        version="1.0.0",
    )


def _install_operation_record_for_ui(
    *,
    operation_id: str | None,
    package_name: str = "SamplePack.zip",
    timestamp: str = "2026-03-13T12:00:00Z",
    destination_kind: str = INSTALL_TARGET_SANDBOX_MODS,
    entry_can_install: bool = True,
) -> InstallOperationRecord:
    destination_mods_path = (
        Path(r"C:\Game\Mods")
        if destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
        else Path(r"C:\Sandbox\Mods")
    )
    archive_path = (
        Path(r"C:\Game\.sdvmm-real-archive")
        if destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
        else Path(r"C:\Sandbox\.sdvmm-sandbox-archive")
    )
    return InstallOperationRecord(
        operation_id=operation_id,
        timestamp=timestamp,
        package_path=Path(r"C:\Packages") / package_name,
        destination_kind=destination_kind,
        destination_mods_path=destination_mods_path,
        archive_path=archive_path,
        installed_targets=(destination_mods_path / "SampleMod",),
        archived_targets=(archive_path / "SampleMod-old",),
        entries=(
            InstallOperationEntryRecord(
                name="Sample Mod",
                unique_id="Sample.Mod",
                version="1.0.0",
                action=INSTALL_NEW if entry_can_install else BLOCKED,
                target_path=destination_mods_path / "SampleMod",
                archive_path=None,
                source_manifest_path=r"C:\Packages\Sample\manifest.json",
                source_root_path=r"C:\Packages\Sample",
                target_exists_before=False,
                can_install=entry_can_install,
                warnings=tuple(),
            ),
        ),
    )


def _install_recovery_inspection_for_ui(
    operation: InstallOperationRecord,
    *,
    allowed: bool = False,
    review_message: str = "Recovery plan is blocked: 1 entry cannot be executed safely.",
    executable_count: int = 2,
    non_executable_count: int = 1,
) -> SimpleNamespace:
    recovery_plan = SimpleNamespace(
        operation=operation,
        summary=SimpleNamespace(
            total_recovery_entry_count=3,
            recoverable_entry_count=2,
            non_recoverable_entry_count=1,
            involves_archive_restore=True,
            warnings=("Unsupported entry cannot be recovered.",),
        ),
    )
    recovery_review = SimpleNamespace(
        plan=recovery_plan,
        allowed=allowed,
        decision_code=("recovery_ready" if allowed else "recovery_blocked"),
        message=review_message,
        summary=SimpleNamespace(
            total_entry_count=3,
            executable_entry_count=executable_count,
            non_executable_entry_count=non_executable_count,
            stale_entry_count=0 if allowed else 1,
            involves_archive_restore=True,
            warnings=(tuple() if allowed else ("Archive source is missing for restoring Existing Mod.",)),
        ),
    )
    linked_history = (
        RecoveryExecutionRecord(
            recovery_execution_id="recovery_1",
            timestamp="2026-03-13T15:00:00Z",
            related_install_operation_id=operation.operation_id,
            related_install_operation_timestamp=operation.timestamp,
            related_install_package_path=operation.package_path,
            destination_kind=operation.destination_kind,
            destination_mods_path=operation.destination_mods_path,
            executed_entry_count=1,
            removed_target_paths=(Path(r"C:\Sandbox\Mods\SampleMod"),),
            restored_target_paths=tuple(),
            outcome_status="completed",
            failure_message=None,
        ),
        RecoveryExecutionRecord(
            recovery_execution_id="recovery_2",
            timestamp="2026-03-13T16:00:00Z",
            related_install_operation_id=operation.operation_id,
            related_install_operation_timestamp=operation.timestamp,
            related_install_package_path=operation.package_path,
            destination_kind=operation.destination_kind,
            destination_mods_path=operation.destination_mods_path,
            executed_entry_count=1,
            removed_target_paths=(Path(r"C:\Sandbox\Mods\SampleMod"),),
            restored_target_paths=tuple(),
            outcome_status="failed_partial",
            failure_message="Restore target already exists",
        ),
    )
    return SimpleNamespace(
        operation=operation,
        recovery_plan=recovery_plan,
        recovery_review=recovery_review,
        linked_recovery_history=linked_history,
    )


def _create_launchable_game_install_for_ui(game_path: Path) -> None:
    game_path.mkdir()
    (game_path / "Mods").mkdir()
    (game_path / "Stardew Valley.exe").write_text("", encoding="utf-8")
    (game_path / "StardewModdingAPI.exe").write_text("", encoding="utf-8")


def _sandbox_install_plan(
    *,
    destination_kind: str = INSTALL_TARGET_SANDBOX_MODS,
    action: str = INSTALL_NEW,
    target_exists: bool = False,
    archive_path: Path | None = None,
    can_install: bool = True,
    warnings: tuple[str, ...] = tuple(),
    package_findings: tuple[PackageFinding, ...] = tuple(),
    package_warnings: tuple[object, ...] = tuple(),
    plan_warnings: tuple[str, ...] = tuple(),
) -> SandboxInstallPlan:
    destination_mods_path = (
        Path(r"C:\Game\Mods")
        if destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
        else Path(r"C:\Sandbox\Mods")
    )
    destination_archive_path = (
        Path(r"C:\Game\.sdvmm-real-archive")
        if destination_kind == INSTALL_TARGET_CONFIGURED_REAL_MODS
        else Path(r"C:\Sandbox\.sdvmm-sandbox-archive")
    )
    entry = SandboxInstallPlanEntry(
        name="Sample Mod",
        unique_id="Sample.Mod",
        version="1.0.0",
        source_manifest_path=r"C:\Packages\Sample\manifest.json",
        source_root_path=r"C:\Packages\Sample",
        target_path=destination_mods_path / "SampleMod",
        action=action,
        target_exists=target_exists,
        archive_path=archive_path,
        can_install=can_install,
        warnings=warnings,
    )
    return SandboxInstallPlan(
        package_path=Path(r"C:\Packages\SamplePack.zip"),
        sandbox_mods_path=destination_mods_path,
        sandbox_archive_path=destination_archive_path,
        entries=(entry,),
        package_findings=package_findings,
        package_warnings=package_warnings,
        plan_warnings=plan_warnings,
        destination_kind=destination_kind,
    )


def _intake_result(
    package_name: str,
    classification: str,
    mod_name: str,
    unique_id: str,
) -> DownloadsIntakeResult:
    mod_entry = PackageModEntry(
        name=mod_name,
        unique_id=unique_id,
        version="1.0.0",
        manifest_path=f"/{mod_name}/manifest.json",
    )
    return DownloadsIntakeResult(
        package_path=Path(r"C:\Downloads") / package_name,
        classification=classification,
        message=f"Detected {package_name}",
        mods=(mod_entry,),
        matched_installed_unique_ids=tuple(),
        warnings=tuple(),
        findings=tuple(),
    )


def _package_inspection_result(
    package_name: str,
    unique_id: str,
    *,
    mod_count: int = 1,
) -> PackageInspectionResult:
    mods = tuple(
        PackageModEntry(
            name=f"{Path(package_name).stem} Mod {index + 1}",
            unique_id=unique_id if index == 0 else f"{unique_id}.{index + 1}",
            version="1.0.0",
            manifest_path=f"/{Path(package_name).stem}/manifest_{index + 1}.json",
        )
        for index in range(mod_count)
    )
    return PackageInspectionResult(
        package_path=Path(r"C:\Downloads") / package_name,
        mods=mods,
        warnings=tuple(),
        findings=tuple(),
    )


def _intake_correlation(
    intake: DownloadsIntakeResult,
    *,
    next_step: str,
    actionable: bool = True,
    matched_guided_update_unique_ids: tuple[str, ...] = tuple(),
    matched_update_available_unique_ids: tuple[str, ...] = tuple(),
) -> IntakeUpdateCorrelation:
    return IntakeUpdateCorrelation(
        intake=intake,
        actionable=actionable,
        matched_update_available_unique_ids=matched_update_available_unique_ids,
        matched_guided_update_unique_ids=matched_guided_update_unique_ids,
        summary=f"Intake summary for {intake.package_path.name}",
        next_step=next_step,
    )


def _discovery_entry(name: str, unique_id: str) -> ModDiscoveryEntry:
    return ModDiscoveryEntry(
        name=name,
        unique_id=unique_id,
        author="Sample Author",
        provider=SMAPI_COMPATIBILITY_LIST_PROVIDER,
        source_provider=DISCOVERY_SOURCE_NEXUS,
        source_page_url=f"https://example.invalid/{unique_id}",
        compatibility_state=COMPATIBLE,
        compatibility_status="Compatible",
        compatibility_summary="Works with current SMAPI.",
    )


def _discovery_correlation(
    entry: ModDiscoveryEntry,
    *,
    context_summary: str,
) -> DiscoveryContextCorrelation:
    return DiscoveryContextCorrelation(
        entry=entry,
        installed_match_unique_id=None,
        update_state=None,
        provider_relation="linked",
        provider_relation_note="Discovery provider relation",
        context_summary=context_summary,
        next_step="Review and decide",
    )


def _visible_row_count(table: QTableWidget) -> int:
    return sum(
        1
        for row in range(table.rowCount())
        if not table.isRowHidden(row)
    )


def _visible_mod_names(table: QTableWidget) -> tuple[str, ...]:
    names: list[str] = []
    for row in range(table.rowCount()):
        if table.isRowHidden(row):
            continue
        item = table.item(row, 0)
        if item is not None:
            names.append(item.text())
    return tuple(names)


def _find_mod_row(table: QTableWidget, mod_name: str) -> int:
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        if item is not None and item.text() == mod_name:
            return row
    return -1


def _inventory_for_update_actionability_tests() -> ModsInventory:
    return ModsInventory(
        mods=(
            _installed_mod_for_update_ui(
                name="Alpha Mod",
                unique_id="Sample.Alpha",
                folder_name="AlphaMod",
            ),
            _installed_mod_for_update_ui(
                name="Beta Mod",
                unique_id="Sample.Beta",
                folder_name="BetaMod",
            ),
            _installed_mod_for_update_ui(
                name="Gamma Mod",
                unique_id="Sample.Gamma",
                folder_name="GammaMod",
            ),
        ),
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )


def _inventory_for_sandbox_sync_ui_tests(real_mods_root: Path) -> ModsInventory:
    folder_path = real_mods_root / "AlphaMod"
    return ModsInventory(
        mods=(
            InstalledMod(
                unique_id="Sample.Alpha",
                name="Alpha Mod",
                version="1.0.0",
                folder_path=folder_path,
                manifest_path=folder_path / "manifest.json",
                dependencies=tuple(),
            ),
        ),
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )


def _update_report_for_update_actionability_tests() -> ModUpdateReport:
    return ModUpdateReport(
        statuses=(
            ModUpdateStatus(
                unique_id="Sample.Alpha",
                name="Alpha Mod",
                folder_path=Path(r"C:\Mods\AlphaMod"),
                installed_version="1.0.0",
                remote_version="1.1.0",
                state="update_available",
                remote_link=None,
                message="Update available.",
            ),
            ModUpdateStatus(
                unique_id="Sample.Beta",
                name="Beta Mod",
                folder_path=Path(r"C:\Mods\BetaMod"),
                installed_version="1.0.0",
                remote_version=None,
                state="no_remote_link",
                remote_link=None,
                update_source_diagnostic=MISSING_UPDATE_KEY,
                message="No remote link available.",
            ),
        )
    )


def _installed_mod_for_update_ui(*, name: str, unique_id: str, folder_name: str) -> InstalledMod:
    folder_path = Path(r"C:\Mods") / folder_name
    return InstalledMod(
        unique_id=unique_id,
        name=name,
        version="1.0.0",
        folder_path=folder_path,
        manifest_path=folder_path / "manifest.json",
        dependencies=tuple(),
    )


def _mods_inventory(*mods: InstalledMod) -> ModsInventory:
    return ModsInventory(
        mods=tuple(mods),
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )
