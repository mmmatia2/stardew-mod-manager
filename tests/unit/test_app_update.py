from __future__ import annotations

from sdvmm.services.app_update import check_app_update_status
from sdvmm.services.update_metadata import MetadataFetchError, REQUEST_FAILURE


def test_check_app_update_status_reports_update_available() -> None:
    fetcher = _FakeFetcher(
        payload={"tag_name": "v1.1.6", "html_url": "https://example.test/cinderleaf/releases/1.1.6"}
    )

    status = check_app_update_status(current_version="1.1.5", fetcher=fetcher)

    assert status.state == "update_available"
    assert status.current_version == "1.1.5"
    assert status.latest_version == "1.1.6"


def test_check_app_update_status_reports_up_to_date() -> None:
    fetcher = _FakeFetcher(payload={"tag_name": "1.1.5"})

    status = check_app_update_status(current_version="1.1.5", fetcher=fetcher)

    assert status.state == "up_to_date"
    assert status.current_version == "1.1.5"
    assert status.latest_version == "1.1.5"


def test_check_app_update_status_reports_unable_when_remote_check_fails() -> None:
    fetcher = _FakeFetcher(error=MetadataFetchError(REQUEST_FAILURE, "network unavailable"))

    status = check_app_update_status(current_version="1.1.5", fetcher=fetcher)

    assert status.state == "unable_to_determine"
    assert status.current_version == "1.1.5"
    assert status.latest_version is None


def test_check_app_update_status_reports_unable_when_current_version_invalid() -> None:
    status = check_app_update_status(current_version="unknown")

    assert status.state == "unable_to_determine"
    assert status.current_version is None


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
