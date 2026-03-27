from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from sdvmm.app import main as app_main
from sdvmm.ui import main_window


def test_resolve_app_version_prefers_runtime_version_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    (runtime_root / "app-version.txt").write_text("1.1.5\n", encoding="utf-8")

    monkeypatch.setattr(app_main, "_resolve_runtime_root", lambda: runtime_root)
    monkeypatch.setattr(app_main, "version", lambda _name: "0.2.1")

    assert app_main._resolve_app_version() == "1.1.5"


def test_resolve_app_version_prefers_pyproject_for_source_runs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "repo"
    runtime_root.mkdir()
    (runtime_root / "pyproject.toml").write_text(
        """
[project]
name = "stardew-mod-manager"
    version = "1.1.5"
""".strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(app_main, "_resolve_runtime_root", lambda: runtime_root)
    monkeypatch.setattr(app_main, "version", lambda _name: "0.2.1")

    assert app_main._resolve_app_version() == "1.1.5"


def test_resolve_ui_app_version_prefers_qapplication_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    original_version = app.applicationVersion()
    app.setApplicationVersion("1.1.5")
    try:
        monkeypatch.setattr(main_window, "package_version", lambda _name: "0.2.1")
        monkeypatch.setattr(main_window.Path, "cwd", lambda: Path(r"C:\no-pyproject-here"))
        assert main_window._resolve_ui_app_version() == "1.1.5"
    finally:
        app.setApplicationVersion(original_version)
