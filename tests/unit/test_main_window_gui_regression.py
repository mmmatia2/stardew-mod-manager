from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QScrollArea, QTabWidget, QWidget

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
