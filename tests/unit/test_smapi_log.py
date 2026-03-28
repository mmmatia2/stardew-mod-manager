from __future__ import annotations

from pathlib import Path

import pytest

from sdvmm.services.smapi_log import (
    check_smapi_log_troubleshooting,
    locate_smapi_log,
    parse_smapi_log_text,
)


def test_locate_smapi_log_prefers_expected_latest_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    xdg_config = tmp_path / "xdg"
    logs_dir = xdg_config / "StardewValley" / "ErrorLogs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "SMAPI-crash.txt").write_text("crash", encoding="utf-8")
    latest = logs_dir / "SMAPI-latest.txt"
    latest.write_text("latest", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))

    located = locate_smapi_log(game_path=None)

    assert located == latest


def test_locate_smapi_log_checks_windows_appdata_errorlogs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    logs_dir = appdata / "StardewValley" / "ErrorLogs"
    logs_dir.mkdir(parents=True)
    latest = logs_dir / "SMAPI-latest.txt"
    latest.write_text("latest", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))

    located = locate_smapi_log(game_path=tmp_path / "Game")

    assert located == latest


def test_check_smapi_log_troubleshooting_reports_not_found_when_no_supported_log_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))

    report = check_smapi_log_troubleshooting(game_path=tmp_path / "Game")

    assert report.state == "not_found"
    assert report.findings == tuple()
    assert report.log_path is None


def test_parse_smapi_log_text_extracts_key_troubleshooting_findings() -> None:
    log_text = "\n".join(
        (
            "[SMAPI] SMAPI 4.5.1 with Stardew Valley 1.6.15",
            "[WARN SMAPI] This is a warning for troubleshooting.",
            "[ERROR SMAPI] Unhandled exception in mod loader.",
            "[SMAPI] Skipped mods",
            "[SMAPI]    - Fancy Pack because it needs mods which aren't installed (Pathoschild.ContentPatcher)",
            "[SMAPI] Broken Helper failed to load because an internal error occurred.",
            "[SMAPI] SteamAPI_Init() failed; create pipe failed.",
        )
    )

    report = parse_smapi_log_text(
        log_text,
        log_path=Path("/tmp/SMAPI-latest.txt"),
        source="auto_detected",
        game_path=Path("/tmp/Game"),
    )

    counts = {kind: 0 for kind in ("error", "warning", "failed_mod", "missing_dependency", "runtime_issue")}
    for finding in report.findings:
        counts[finding.kind] += 1

    assert report.state == "parsed"
    assert counts["warning"] >= 1
    assert counts["error"] >= 1
    assert counts["failed_mod"] >= 2
    assert counts["missing_dependency"] >= 1
    assert counts["runtime_issue"] >= 1


def test_parse_smapi_log_text_reports_empty_log_as_unable_to_determine() -> None:
    report = parse_smapi_log_text(
        "",
        log_path=Path("/tmp/SMAPI-latest.txt"),
        source="manual",
        game_path=Path("/tmp/Game"),
    )

    assert report.state == "unable_to_determine"
    assert report.findings == tuple()
