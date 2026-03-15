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
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sdvmm.app.shell_service import AppShellError
from sdvmm.app.shell_service import AppShellService
from sdvmm.app.shell_service import DiscoveryContextCorrelation
from sdvmm.app.shell_service import INSTALL_TARGET_CONFIGURED_REAL_MODS
from sdvmm.app.shell_service import INSTALL_TARGET_SANDBOX_MODS
from sdvmm.app.shell_service import IntakeUpdateCorrelation
from sdvmm.app.shell_service import SCAN_TARGET_CONFIGURED_REAL_MODS
from sdvmm.app.shell_service import SCAN_TARGET_SANDBOX_MODS
from sdvmm.domain.install_codes import BLOCKED
from sdvmm.domain.discovery_codes import COMPATIBLE
from sdvmm.domain.discovery_codes import DISCOVERY_SOURCE_NEXUS
from sdvmm.domain.discovery_codes import SMAPI_COMPATIBILITY_LIST_PROVIDER
from sdvmm.domain.install_codes import INSTALL_NEW, OVERWRITE_WITH_ARCHIVE
from sdvmm.domain.package_codes import INVALID_MANIFEST_PACKAGE
from sdvmm.domain.update_codes import MISSING_UPDATE_KEY, UNSUPPORTED_UPDATE_KEY_FORMAT
from sdvmm.domain.models import ArchivedModEntry
from sdvmm.domain.models import DownloadsIntakeResult
from sdvmm.domain.models import InstalledMod
from sdvmm.domain.models import InstallOperationEntryRecord
from sdvmm.domain.models import InstallOperationRecord
from sdvmm.domain.models import ModDiscoveryEntry
from sdvmm.domain.models import ModDiscoveryResult
from sdvmm.domain.models import ModUpdateReport
from sdvmm.domain.models import ModUpdateStatus
from sdvmm.domain.models import ModsInventory
from sdvmm.domain.models import PackageModEntry
from sdvmm.domain.models import PackageFinding
from sdvmm.domain.models import RecoveryExecutionRecord
from sdvmm.domain.models import SandboxInstallPlan
from sdvmm.domain.models import SandboxInstallPlanEntry
from sdvmm.ui.main_window import MainWindow
from sdvmm.ui.main_window import _ROLE_DISCOVERY_INDEX
from sdvmm.ui.main_window import _ROLE_MOD_UPDATE_STATUS
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


def test_main_window_instantiates_in_qt_context(main_window: MainWindow) -> None:
    assert main_window is not None
    assert main_window.windowTitle() != ""


def test_main_window_has_separate_status_strip_and_bottom_details_region(
    main_window: MainWindow,
) -> None:
    status_strip_group = main_window.findChild(QGroupBox, "global_status_strip_group")
    bottom_details_group = main_window.findChild(QGroupBox, "bottom_details_group")

    assert status_strip_group is not None
    assert bottom_details_group is not None
    assert status_strip_group is not bottom_details_group
    assert status_strip_group.isVisible()
    assert bottom_details_group.isVisible()


def test_main_window_bottom_details_surface_is_output_only(
    main_window: MainWindow,
) -> None:
    bottom_details_group = main_window.findChild(QGroupBox, "bottom_details_group")
    detail_identity_label = main_window.findChild(QLabel, "bottom_detail_identity_label")
    details_group = main_window.findChild(QGroupBox, "bottom_summary_details_group")

    assert bottom_details_group is not None
    assert detail_identity_label is not None
    assert details_group is not None

    assert bottom_details_group.title() == "Operational Detail"
    assert detail_identity_label.text() == "Detailed output"
    assert details_group.parentWidget() is bottom_details_group
    assert main_window.findChild(QGroupBox, "bottom_setup_group") is None
    assert main_window.findChild(QScrollArea, "bottom_setup_tab") is None
    assert main_window.findChild(QTabWidget, "bottom_details_tabs") is None
    assert main_window.findChild(QWidget, "bottom_summary_tab") is None


def test_main_window_bottom_details_surface_uses_simple_identity_copy(
    main_window: MainWindow,
) -> None:
    identity_label = main_window.findChild(QLabel, "bottom_detail_identity_label")

    assert identity_label is not None
    assert identity_label.text() == "Detailed output"
    assert main_window.findChild(QLabel, "bottom_detail_help_label") is None


def test_main_window_recovery_inspection_controls_exist(main_window: MainWindow) -> None:
    plan_tab = main_window.findChild(QWidget, "plan_install_tab")
    plan_content = main_window.findChild(QWidget, "plan_install_tab_content")
    recovery_group = main_window.findChild(QGroupBox, "recovery_inspection_group")
    recovery_combo = main_window.findChild(QComboBox, "recovery_inspection_operation_combo")
    recovery_filter_combo = main_window.findChild(QComboBox, "recovery_selector_filter_combo")
    recovery_summary_label = main_window.findChild(QLabel, "recovery_selection_summary_label")
    recovery_button = main_window.findChild(QPushButton, "recovery_inspection_button")
    run_recovery_button = main_window.findChild(QPushButton, "recovery_execute_button")

    assert plan_tab is not None
    assert plan_content is not None
    assert recovery_group is not None
    assert recovery_combo is not None
    assert recovery_filter_combo is not None
    assert recovery_summary_label is not None
    assert recovery_button is not None
    assert run_recovery_button is not None
    assert recovery_group.parentWidget() is plan_content
    assert main_window._install_history_combo is recovery_combo
    assert main_window._install_history_filter_combo is recovery_filter_combo
    assert main_window._recovery_selection_summary_label is recovery_summary_label
    assert main_window._inspect_recovery_button is recovery_button
    assert main_window._run_recovery_button is run_recovery_button
    assert recovery_combo.isEnabled() is False
    assert recovery_button.isEnabled() is False
    assert run_recovery_button.isEnabled() is False


def test_main_window_bottom_details_start_hidden_by_default(main_window: MainWindow) -> None:
    details_group = main_window.findChild(QGroupBox, "bottom_summary_details_group")

    assert details_group is not None
    assert details_group.isVisible() is False
    assert main_window._details_group is details_group
    assert main_window._details_toggle.isChecked() is False
    assert main_window._details_toggle.text() == "Show detailed output"


def test_main_window_bottom_details_toggle_shows_and_hides_details_group(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    details_group = main_window.findChild(QGroupBox, "bottom_summary_details_group")

    assert details_group is not None

    main_window._details_toggle.setChecked(True)
    qapp.processEvents()

    assert details_group.isHidden() is False
    assert details_group.isVisible() is True
    assert main_window._details_toggle.text() == "Hide detailed output"

    main_window._details_toggle.setChecked(False)
    qapp.processEvents()

    assert details_group.isVisible() is False
    assert main_window._details_toggle.text() == "Show detailed output"


def test_main_window_recovery_controls_remain_visible_when_details_toggle_changes(
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
    plan_tab = main_window.findChild(QWidget, "plan_install_tab")
    recovery_group = main_window.findChild(QGroupBox, "recovery_inspection_group")
    details_group = main_window.findChild(QGroupBox, "bottom_summary_details_group")

    assert plan_tab is not None
    assert recovery_group is not None
    assert details_group is not None

    main_window._context_tabs.setCurrentWidget(plan_tab)
    qapp.processEvents()
    assert recovery_group.isVisible() is True
    assert main_window._install_history_combo.isEnabled() is True
    assert main_window._inspect_recovery_button.isEnabled() is True

    main_window._details_toggle.setChecked(True)
    qapp.processEvents()
    assert recovery_group.isVisible() is True
    assert main_window._install_history_combo.isEnabled() is True
    assert main_window._inspect_recovery_button.isEnabled() is True

    main_window._details_toggle.setChecked(False)
    qapp.processEvents()
    assert recovery_group.isVisible() is True
    assert main_window._install_history_combo.isEnabled() is True
    assert main_window._inspect_recovery_button.isEnabled() is True


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


def test_main_window_top_context_surface_has_expected_panels(main_window: MainWindow) -> None:
    top_context_group = main_window.findChild(QGroupBox, "top_context_surface_group")
    status_strip_group = main_window.findChild(QGroupBox, "global_status_strip_group")
    environment_panel = main_window.findChild(QWidget, "top_context_environment_panel")
    runtime_panel = main_window.findChild(QWidget, "top_context_runtime_panel")
    active_context_panel = main_window.findChild(QWidget, "top_context_active_context_panel")

    assert top_context_group is not None
    assert status_strip_group is not None
    assert top_context_group is not status_strip_group
    assert top_context_group.isVisible()
    assert environment_panel is not None
    assert runtime_panel is not None
    assert active_context_panel is not None


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
    assert install_target_combo.minimumContentsLength() >= 28
    assert (
        install_target_combo.sizeAdjustPolicy()
        == QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow
    )
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
        )

    monkeypatch.setattr(main_window._shell_service, "launch_game_sandbox_dev", _fake_launch_game_sandbox_dev)
    monkeypatch.setattr("sdvmm.ui.main_window.QMessageBox.critical", lambda *args: None)

    main_window._on_launch_sandbox_dev()

    runtime_label = main_window.findChild(QLabel, "top_context_runtime_sandbox_launch_value")
    assert captured == {
        "game_path_text": str(game_path),
        "sandbox_mods_path_text": str(sandbox_mods),
        "configured_mods_path_text": str(real_mods),
        "existing_config": None,
    }
    assert "Sandbox dev launch started" in main_window._status_strip_label.text()
    assert str(sandbox_mods) in main_window._status_strip_label.text()
    assert runtime_label is not None
    assert runtime_label.text() == "Started"


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


def test_main_window_setup_surface_group_and_scroll_exist(main_window: MainWindow) -> None:
    context_tabs = main_window._context_tabs
    setup_group = main_window.findChild(QGroupBox, "setup_surface_group")
    setup_scroll = main_window._setup_scroll

    assert context_tabs is not None
    assert setup_group is not None
    assert setup_scroll is not None
    assert isinstance(setup_scroll, QScrollArea)
    assert setup_group.isVisible()
    assert setup_scroll.widget() is setup_group
    assert main_window._setup_group is setup_group
    assert main_window._setup_scroll is setup_scroll
    assert setup_scroll.objectName() == "setup_workspace_tab"
    setup_index = context_tabs.indexOf(setup_scroll)
    assert setup_index >= 0
    assert context_tabs.widget(setup_index) is setup_scroll
    assert "Setup" in {
        context_tabs.tabText(index) for index in range(context_tabs.count())
    }


def test_main_window_setup_surface_key_inputs_and_actions_exist(main_window: MainWindow) -> None:
    input_names = (
        "setup_game_path_input",
        "setup_mods_path_input",
        "setup_sandbox_mods_input",
        "setup_sandbox_archive_input",
        "setup_real_archive_input",
        "setup_nexus_api_key_input",
    )
    button_names = (
        "setup_save_config_button",
        "setup_detect_environment_button",
    )

    for name in input_names:
        control = main_window.findChild(QLineEdit, name)
        assert control is not None

    for name in button_names:
        button = main_window.findChild(QPushButton, name)
        assert button is not None


def test_main_window_plan_install_surface_has_expected_structure(
    main_window: MainWindow,
) -> None:
    inventory_tabs = main_window._inventory_controls_tabs
    inventory_shell = main_window.findChild(QWidget, "inventory_tabs_shell_container")
    context_tabs = main_window._context_tabs
    context_shell = main_window.findChild(QWidget, "context_tabs_shell_container")
    plan_tab = main_window.findChild(QWidget, "plan_install_tab")
    plan_scroll = main_window.findChild(QScrollArea, "plan_install_scroll_area")
    plan_content = main_window.findChild(QWidget, "plan_install_tab_content")
    destination_group = main_window.findChild(QGroupBox, "plan_install_destination_group")
    safety_panel_group = main_window.findChild(QGroupBox, "plan_install_safety_panel_group")
    staged_package_group = main_window.findChild(QGroupBox, "plan_install_staged_package_group")
    execute_group = main_window.findChild(QGroupBox, "plan_install_execute_group")
    plan_review_summary_group = main_window.findChild(QGroupBox, "plan_install_review_summary_group")
    plan_facts_group = main_window.findChild(QGroupBox, "plan_install_facts_group")
    recovery_group = main_window.findChild(QGroupBox, "recovery_inspection_group")

    assert inventory_tabs is not None
    assert inventory_shell is not None
    assert context_tabs is not None
    assert context_shell is not None
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
    assert recovery_group is not None

    tab_labels = {context_tabs.tabText(index) for index in range(context_tabs.count())}
    assert "Plan & Install" in tab_labels
    assert context_tabs.indexOf(plan_tab) >= 0
    assert inventory_tabs.parentWidget() is inventory_shell
    assert context_tabs.parentWidget() is context_shell
    inventory_layout = inventory_shell.parentWidget().layout()
    inventory_shell_layout = inventory_shell.layout()
    shell_layout = context_shell.layout()
    assert isinstance(inventory_layout, QVBoxLayout)
    assert isinstance(inventory_shell_layout, QVBoxLayout)
    assert isinstance(shell_layout, QVBoxLayout)
    inventory_root_margins = inventory_layout.contentsMargins()
    inventory_margins = inventory_shell_layout.contentsMargins()
    margins = shell_layout.contentsMargins()
    assert (
        inventory_root_margins.left(),
        inventory_root_margins.top(),
        inventory_root_margins.right(),
        inventory_root_margins.bottom(),
    ) == (6, 0, 6, 4)
    assert (
        inventory_margins.left(),
        inventory_margins.top(),
        inventory_margins.right(),
        inventory_margins.bottom(),
    ) == (0, 4, 0, 0)
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (0, 5, 0, 0)
    assert "QTabWidget::pane { margin-top: 4px; }" in inventory_tabs.styleSheet()
    assert "QTabWidget::pane { margin-top: 4px; }" in context_tabs.styleSheet()

    assert plan_scroll.parentWidget() is plan_tab
    assert plan_scroll.widget() is plan_content

    plan_layout = plan_content.layout()
    assert plan_layout is not None
    assert plan_layout.indexOf(destination_group) < plan_layout.indexOf(safety_panel_group)
    assert plan_layout.indexOf(safety_panel_group) < plan_layout.indexOf(staged_package_group)
    assert plan_layout.indexOf(staged_package_group) < plan_layout.indexOf(execute_group)
    assert plan_layout.indexOf(execute_group) < plan_layout.indexOf(plan_review_summary_group)
    assert plan_layout.indexOf(plan_review_summary_group) < plan_layout.indexOf(plan_facts_group)
    assert plan_layout.indexOf(plan_facts_group) < plan_layout.indexOf(recovery_group)


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

    assert panel_group is not None
    assert panel_text is not None
    assert plan_content is not None
    assert panel_group.parentWidget() is plan_content
    assert "Sandbox destination selected (recommended/test path)." in panel_text.text()
    assert "Destination Mods path:" in panel_text.text()
    assert "Archive path:" in panel_text.text()


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
    install_target_combo = main_window.findChild(QComboBox, "plan_install_target_combo")
    overwrite_checkbox = main_window.findChild(QCheckBox, "plan_install_overwrite_checkbox")
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
    assert install_archive_label is not None
    assert staged_package_group is not None
    assert staged_package_label is not None
    assert plan_review_summary_label is not None
    assert plan_review_explanation_label is not None
    assert plan_facts_label is not None
    assert plan_button is not None
    assert run_button is not None

    assert main_window._install_target_combo is install_target_combo
    assert main_window._overwrite_checkbox is overwrite_checkbox
    assert main_window._install_archive_label is install_archive_label
    assert main_window._staged_package_label is staged_package_label
    assert main_window._plan_review_summary_label is plan_review_summary_label
    assert main_window._plan_review_explanation_label is plan_review_explanation_label
    assert main_window._plan_facts_label is plan_facts_label
    assert staged_package_label.isReadOnly() is True
    assert (
        plan_review_explanation_label.text()
        == "Plan detail: no plan selected."
    )
    assert plan_facts_label.text() == (
        "Entries: -\n"
        "Replace existing: -\n"
        "Archive writes: -\n"
        "Approval required: -\n"
        "Blocked entries: -"
    )


def test_main_window_plan_and_recovery_output_routes_to_shared_detail_surface(
    main_window: MainWindow,
) -> None:
    main_window._set_plan_install_output_text("Plan output narrative")
    assert main_window._findings_box.toPlainText() == "Plan output narrative"
    main_window._set_recovery_output_text("Recovery output narrative")

    assert main_window._findings_box.toPlainText() == "Recovery output narrative"


def test_main_window_removed_detail_access_scaffolding_is_not_present(
    main_window: MainWindow,
) -> None:
    assert main_window.findChild(QGroupBox, "plan_install_detail_access_group") is None
    assert main_window.findChild(QPushButton, "plan_install_view_shared_details_button") is None
    assert main_window.findChild(QCheckBox, "plan_install_show_local_output_toggle") is None
    assert main_window.findChild(QCheckBox, "recovery_show_local_output_toggle") is None
    assert main_window.findChild(QGroupBox, "plan_install_output_group") is None
    assert main_window.findChild(QGroupBox, "recovery_output_group") is None
    assert main_window.findChild(QGroupBox, "packages_intake_detail_access_group") is None
    assert main_window.findChild(QPushButton, "packages_intake_view_shared_details_button") is None
    assert main_window.findChild(QCheckBox, "packages_intake_show_local_output_toggle") is None
    assert main_window.findChild(QGroupBox, "packages_intake_output_group") is None


def test_main_window_package_inspection_writes_to_shared_detail_surface(
    main_window: MainWindow,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inspection = SimpleNamespace(mods=(object(), object()))

    monkeypatch.setattr(
        main_window._shell_service,
        "inspect_zip_with_inventory_context",
        lambda *args, **kwargs: inspection,
    )
    monkeypatch.setattr(
        "sdvmm.ui.main_window.build_package_inspection_text",
        lambda payload: "Inspection narrative output",
    )

    main_window._zip_path_input.setText(r"C:\Downloads\InspectMe.zip")
    main_window._on_inspect_zip()

    assert main_window._findings_box.toPlainText() == "Inspection narrative output"
    assert main_window._status_strip_label.text() == "Zip inspection complete: 2 mod(s) detected"


def test_main_window_staging_valid_intake_switches_to_plan_install_and_updates_display(
    main_window: MainWindow,
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    intake = _intake_result("AlphaPack.zip", "new_install_candidate", "Alpha Mod", "Sample.Alpha")
    packages_tab = next(
        index
        for index in range(main_window._context_tabs.count())
        if main_window._context_tabs.tabText(index) == "Packages & Intake"
    )
    plan_tab = main_window.findChild(QWidget, "plan_install_tab")

    monkeypatch.setattr(
        main_window._shell_service,
        "build_install_plan_from_intake",
        lambda **_: pytest.fail("Staging must not build an install plan in Packages & Intake."),
    )
    monkeypatch.setattr(
        main_window._shell_service,
        "execute_sandbox_install_plan",
        lambda *args, **kwargs: pytest.fail("Staging must not execute install."),
    )

    main_window._detected_intakes = (intake,)
    main_window._intake_correlations = (_intake_correlation(intake, next_step="Review AlphaPack.zip"),)
    main_window._refresh_intake_selector()
    main_window._context_tabs.setCurrentIndex(packages_tab)
    qapp.processEvents()

    main_window._on_plan_selected_intake()
    qapp.processEvents()

    assert plan_tab is not None
    assert main_window._context_tabs.currentWidget() is plan_tab
    assert main_window._zip_path_input.text() == str(intake.package_path)
    assert main_window._staged_package_label.toolTip() == str(intake.package_path)
    assert main_window._staged_package_label.text() == str(intake.package_path)
    assert main_window._findings_box.toPlainText() == "Staged package for planning: AlphaPack.zip"
    assert main_window._status_strip_label.text() == "Staged package for planning: AlphaPack.zip"
    assert main_window._pending_install_plan is None


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

    expected_message = "Matched update package ready to stage: MatchedPack.zip"
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
        "Multiple matched update packages are ready. Choose which package to stage in Packages & Intake."
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
        if main_window._context_tabs.tabText(index) == "Packages & Intake"
    )
    plan_tab = main_window.findChild(QWidget, "plan_install_tab")

    monkeypatch.setattr(
        main_window._shell_service,
        "build_install_plan_from_intake",
        lambda **_: pytest.fail("Staging must not plan or execute inside Packages & Intake."),
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
    assert main_window._context_tabs.currentWidget() is plan_tab
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
        if main_window._context_tabs.tabText(index) == "Packages & Intake"
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

    expected_message = "Select a detected package or inspect a zip package before staging for install."
    assert warnings == [expected_message]
    assert main_window._findings_box.toPlainText() == expected_message
    assert main_window._status_strip_label.text() == expected_message
    assert main_window._zip_path_input.text() == r"C:\Packages\Existing.zip"
    assert main_window._pending_install_plan is existing_plan
    assert main_window._context_tabs.tabText(main_window._context_tabs.currentIndex()) == "Packages & Intake"


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
            "Plan review: no plan yet. Click Plan install to review."
        )
        assert main_window._plan_review_explanation_label.text() == "Plan detail: no plan selected."
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
    discovery_tab = main_window.findChild(QWidget, "discovery_tab")
    discovery_search_group = main_window.findChild(QGroupBox, "discovery_search_group")
    discovery_results_group = main_window.findChild(QGroupBox, "discovery_results_group")

    assert context_tabs is not None
    assert isinstance(context_tabs, QTabWidget)
    assert discovery_tab is not None
    assert discovery_search_group is not None
    assert discovery_results_group is not None

    tab_labels = {context_tabs.tabText(index) for index in range(context_tabs.count())}
    assert "Discovery" in tab_labels
    assert context_tabs.indexOf(discovery_tab) >= 0


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

    assert main_window._status_strip_label.text() == "Run Search mods first."


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
    archive_tab = main_window.findChild(QWidget, "archive_tab")
    archive_controls_group = main_window.findChild(QGroupBox, "archive_controls_group")
    archive_results_group = main_window.findChild(QGroupBox, "archive_results_group")

    assert context_tabs is not None
    assert isinstance(context_tabs, QTabWidget)
    assert archive_tab is not None
    assert archive_controls_group is not None
    assert archive_results_group is not None

    tab_labels = {context_tabs.tabText(index) for index in range(context_tabs.count())}
    assert "Archive" in tab_labels
    assert context_tabs.indexOf(archive_tab) >= 0


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


def test_main_window_package_inspection_result_text_controls_visibility(
    main_window: MainWindow,
    qapp: QApplication,
) -> None:
    inspection_group = main_window._package_inspection_result_group
    inspection_box = main_window._package_inspection_result_box
    package_tab_index = next(
        index
        for index in range(main_window._context_tabs.count())
        if main_window._context_tabs.tabText(index) == "Packages & Intake"
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
