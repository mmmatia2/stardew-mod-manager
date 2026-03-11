from __future__ import annotations

from pathlib import Path

from sdvmm.services.smapi_update import (
    check_smapi_update_status,
    detect_installed_smapi_version,
)
from sdvmm.services.update_metadata import MetadataFetchError, REQUEST_FAILURE


def test_detect_installed_smapi_version_reads_local_binary_metadata(tmp_path: Path) -> None:
    game_path = tmp_path / "Game"
    game_path.mkdir()
    (game_path / "StardewModdingAPI.dll").write_bytes(
        b"\x00SMAPI.Toolkit, Version=4.5.1.0\x00"
    )

    version = detect_installed_smapi_version(game_path=game_path)

    assert version == "4.5.1"


def test_check_smapi_update_status_reports_not_detected_when_smapi_missing(tmp_path: Path) -> None:
    game_path = tmp_path / "Game"
    game_path.mkdir()
    (game_path / "Stardew Valley").write_text("", encoding="utf-8")

    status = check_smapi_update_status(game_path=game_path)

    assert status.state == "not_detected"
    assert status.installed_version is None
    assert status.latest_version is None


def test_check_smapi_update_status_reports_update_available(tmp_path: Path) -> None:
    game_path = tmp_path / "Game"
    game_path.mkdir()
    (game_path / "Stardew Valley").write_text("", encoding="utf-8")
    (game_path / "StardewModdingAPI").write_text("", encoding="utf-8")
    (game_path / "StardewModdingAPI.dll").write_bytes(
        b"\x004.4.0+abcdef1234567\x00"
    )
    fetcher = _FakeFetcher(
        payload={"tag_name": "4.5.1", "html_url": "https://example.test/smapi-release"}
    )

    status = check_smapi_update_status(game_path=game_path, fetcher=fetcher)

    assert status.state == "update_available"
    assert status.installed_version == "4.4.0"
    assert status.latest_version == "4.5.1"
    assert status.update_page_url == "https://example.test/smapi-release"


def test_check_smapi_update_status_reports_up_to_date(tmp_path: Path) -> None:
    game_path = tmp_path / "Game"
    game_path.mkdir()
    (game_path / "Stardew Valley").write_text("", encoding="utf-8")
    (game_path / "StardewModdingAPI").write_text("", encoding="utf-8")
    (game_path / "StardewModdingAPI.dll").write_bytes(
        b"\x00SMAPI.Toolkit, Version=4.5.1.0\x00"
    )
    fetcher = _FakeFetcher(payload={"tag_name": "4.5.1"})

    status = check_smapi_update_status(game_path=game_path, fetcher=fetcher)

    assert status.state == "up_to_date"
    assert status.installed_version == "4.5.1"
    assert status.latest_version == "4.5.1"


def test_check_smapi_update_status_reports_detected_when_remote_check_fails(tmp_path: Path) -> None:
    game_path = tmp_path / "Game"
    game_path.mkdir()
    (game_path / "Stardew Valley").write_text("", encoding="utf-8")
    (game_path / "StardewModdingAPI").write_text("", encoding="utf-8")
    (game_path / "StardewModdingAPI.dll").write_bytes(
        b"\x00SMAPI.Toolkit, Version=4.5.1.0\x00"
    )
    fetcher = _FakeFetcher(
        error=MetadataFetchError(REQUEST_FAILURE, "network is unavailable")
    )

    status = check_smapi_update_status(game_path=game_path, fetcher=fetcher)

    assert status.state == "detected_version_known"
    assert status.installed_version == "4.5.1"
    assert status.latest_version is None


def test_check_smapi_update_status_reports_detected_when_remote_version_missing(tmp_path: Path) -> None:
    game_path = tmp_path / "Game"
    game_path.mkdir()
    (game_path / "Stardew Valley").write_text("", encoding="utf-8")
    (game_path / "StardewModdingAPI").write_text("", encoding="utf-8")
    (game_path / "StardewModdingAPI.dll").write_bytes(
        b"\x00SMAPI.Toolkit, Version=4.5.1.0\x00"
    )
    fetcher = _FakeFetcher(payload={"html_url": "https://example.test/releases"})

    status = check_smapi_update_status(game_path=game_path, fetcher=fetcher)

    assert status.state == "detected_version_known"
    assert status.installed_version == "4.5.1"
    assert status.latest_version is None


def test_check_smapi_update_status_reports_unable_for_invalid_game_path(tmp_path: Path) -> None:
    status = check_smapi_update_status(game_path=tmp_path / "missing")

    assert status.state == "unable_to_determine"
    assert status.installed_version is None


class _FakeFetcher:
    def __init__(
        self,
        *,
        payload: dict[str, object] | None = None,
        error: MetadataFetchError | None = None,
    ) -> None:
        self._payload = payload or {}
        self._error = error

    def fetch_json(
        self,
        url: str,
        timeout_seconds: float,
        headers: dict[str, str] | None = None,
    ) -> dict[str, object]:
        _ = (url, timeout_seconds, headers)
        if self._error is not None:
            raise self._error
        return dict(self._payload)
