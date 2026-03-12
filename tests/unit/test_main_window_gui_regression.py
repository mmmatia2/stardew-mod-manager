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
