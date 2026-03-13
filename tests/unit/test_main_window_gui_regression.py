from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTabWidget,
    QWidget,
)

from sdvmm.app.shell_service import AppShellService
from sdvmm.app.shell_service import INSTALL_TARGET_CONFIGURED_REAL_MODS
from sdvmm.app.shell_service import INSTALL_TARGET_SANDBOX_MODS
from sdvmm.app.shell_service import SCAN_TARGET_CONFIGURED_REAL_MODS
from sdvmm.app.shell_service import SCAN_TARGET_SANDBOX_MODS
from sdvmm.domain.models import ArchivedModEntry
from sdvmm.ui.main_window import MainWindow


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


def test_main_window_bottom_details_tabs_include_summary_and_setup(
    main_window: MainWindow,
) -> None:
    bottom_tabs = main_window.findChild(QTabWidget, "bottom_details_tabs")
    summary_tab = main_window.findChild(QWidget, "bottom_summary_tab")
    setup_tab = main_window.findChild(QScrollArea, "bottom_setup_tab")

    assert bottom_tabs is not None
    assert summary_tab is not None
    assert setup_tab is not None

    tab_labels = {bottom_tabs.tabText(index) for index in range(bottom_tabs.count())}
    assert "Summary" in tab_labels
    assert "Setup" in tab_labels
    assert bottom_tabs.indexOf(summary_tab) >= 0
    assert bottom_tabs.indexOf(setup_tab) >= 0


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

    main_window._secondary_tabs.setCurrentIndex(main_window._summary_tab_index)
    qapp.processEvents()
    main_window._details_toggle.setChecked(True)
    qapp.processEvents()

    assert details_group.isHidden() is False
    assert details_group.isVisible() is True
    assert main_window._details_toggle.text() == "Hide detailed output"

    main_window._details_toggle.setChecked(False)
    qapp.processEvents()

    assert details_group.isVisible() is False
    assert main_window._details_toggle.text() == "Show detailed output"


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
    assert scan_source_label.text().startswith("REAL Mods:")
    assert scan_source_label.toolTip() == r"C:\SDV\Mods"

    scan_target_combo.setCurrentIndex(sandbox_index)
    qapp.processEvents()
    assert scan_source_label.text().startswith("Sandbox Mods:")
    assert scan_source_label.toolTip() == r"C:\SDV\SandboxMods"


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
    assert scan_source_label.text().startswith("REAL Mods:")
    assert scan_source_label.toolTip() == r"C:\RealModsA"

    scan_target_combo.setCurrentIndex(sandbox_index)
    main_window._sandbox_mods_path_input.setText(r"C:\SandboxModsA")
    qapp.processEvents()
    assert scan_source_label.text().startswith("Sandbox Mods:")
    assert scan_source_label.toolTip() == r"C:\SandboxModsA"


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
    assert install_context_label.text().startswith("Sandbox Mods:")
    assert install_archive_label.text() == "Archive path for sandbox destination"
    assert "sandbox Mods path" in status_label.text()

    install_target_combo.setCurrentIndex(real_index)
    qapp.processEvents()
    assert install_context_label.text().startswith("REAL game Mods:")
    assert install_archive_label.text() == "Archive path for real Game Mods destination"
    assert "REAL game Mods path" in status_label.text()


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
    setup_group = main_window.findChild(QGroupBox, "setup_surface_group")
    setup_scroll = main_window._setup_scroll

    assert setup_group is not None
    assert setup_scroll is not None
    assert isinstance(setup_scroll, QScrollArea)
    assert setup_group.isVisible()
    assert setup_scroll.widget() is setup_group
    assert main_window._setup_group is setup_group
    assert main_window._setup_scroll is setup_scroll


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
    context_tabs = main_window._context_tabs
    plan_tab = main_window.findChild(QWidget, "plan_install_tab")
    destination_group = main_window.findChild(QGroupBox, "plan_install_destination_group")
    execute_group = main_window.findChild(QGroupBox, "plan_install_execute_group")

    assert context_tabs is not None
    assert isinstance(context_tabs, QTabWidget)
    assert plan_tab is not None
    assert destination_group is not None
    assert execute_group is not None

    tab_labels = {context_tabs.tabText(index) for index in range(context_tabs.count())}
    assert "Plan & Install" in tab_labels
    assert context_tabs.indexOf(plan_tab) >= 0


def test_main_window_plan_install_surface_key_controls_exist(
    main_window: MainWindow,
) -> None:
    install_target_combo = main_window.findChild(QComboBox, "plan_install_target_combo")
    overwrite_checkbox = main_window.findChild(QCheckBox, "plan_install_overwrite_checkbox")
    install_archive_label = main_window.findChild(QLabel, "plan_install_archive_label")
    plan_button = main_window.findChild(QPushButton, "plan_install_plan_button")
    run_button = main_window.findChild(QPushButton, "plan_install_run_button")

    assert install_target_combo is not None
    assert overwrite_checkbox is not None
    assert install_archive_label is not None
    assert plan_button is not None
    assert run_button is not None

    assert main_window._install_target_combo is install_target_combo
    assert main_window._overwrite_checkbox is overwrite_checkbox
    assert main_window._install_archive_label is install_archive_label


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
