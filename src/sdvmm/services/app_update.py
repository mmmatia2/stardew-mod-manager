from __future__ import annotations

import re
from typing import Mapping

from sdvmm.domain.models import AppUpdateStatus
from sdvmm.services.update_metadata import (
    JsonMetadataFetcher,
    MetadataFetchError,
    UrllibJsonMetadataFetcher,
    compare_versions,
)

APP_RELEASES_LATEST_URL = "https://api.github.com/repos/meiameiameia/stardew-mod-manager/releases/latest"
APP_RELEASES_PAGE_URL = "https://github.com/meiameiameia/stardew-mod-manager/releases"

_VERSION_TEXT_PATTERN = re.compile(r"([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)")


def check_app_update_status(
    *,
    current_version: str,
    fetcher: JsonMetadataFetcher | None = None,
    timeout_seconds: float = 8.0,
) -> AppUpdateStatus:
    normalized_current_version = _normalize_version(current_version)
    if not normalized_current_version:
        return AppUpdateStatus(
            state="unable_to_determine",
            current_version=None,
            latest_version=None,
            update_page_url=APP_RELEASES_PAGE_URL,
            message="Current Cinderleaf version is unavailable; cannot compare against the latest release.",
        )

    active_fetcher = fetcher or UrllibJsonMetadataFetcher()
    try:
        payload = active_fetcher.fetch_json(APP_RELEASES_LATEST_URL, timeout_seconds)
    except MetadataFetchError as exc:
        return AppUpdateStatus(
            state="unable_to_determine",
            current_version=normalized_current_version,
            latest_version=None,
            update_page_url=APP_RELEASES_PAGE_URL,
            message=(
                f"Cinderleaf {normalized_current_version} is running, but the latest release could not be checked: {exc.message}"
            ),
        )

    latest_version = _extract_latest_app_version(payload)
    release_page_url = _extract_release_page_url(payload)
    if not latest_version:
        return AppUpdateStatus(
            state="unable_to_determine",
            current_version=normalized_current_version,
            latest_version=None,
            update_page_url=release_page_url,
            message=(
                f"Cinderleaf {normalized_current_version} is running, but the latest release version is unavailable."
            ),
        )

    comparison = compare_versions(normalized_current_version, latest_version)
    if comparison is None:
        return AppUpdateStatus(
            state="unable_to_determine",
            current_version=normalized_current_version,
            latest_version=latest_version,
            update_page_url=release_page_url,
            message=(
                "Current and latest Cinderleaf versions were detected, but the version formats are not comparable."
            ),
        )

    if comparison < 0:
        return AppUpdateStatus(
            state="update_available",
            current_version=normalized_current_version,
            latest_version=latest_version,
            update_page_url=release_page_url,
            message=(
                f"Cinderleaf update available: installed {normalized_current_version}, latest {latest_version}."
            ),
        )

    return AppUpdateStatus(
        state="up_to_date",
        current_version=normalized_current_version,
        latest_version=latest_version,
        update_page_url=release_page_url,
        message=(
            f"Cinderleaf is up to date (installed {normalized_current_version}, latest {latest_version})."
        ),
    )


def default_app_update_page_url() -> str:
    return APP_RELEASES_PAGE_URL


def _extract_latest_app_version(payload: Mapping[str, object]) -> str | None:
    for key in ("tag_name", "version", "name"):
        value = payload.get(key)
        if not isinstance(value, str):
            continue
        normalized = _normalize_version(value)
        if normalized:
            return normalized
    return None


def _extract_release_page_url(payload: Mapping[str, object]) -> str:
    html_url = payload.get("html_url")
    if isinstance(html_url, str) and html_url.strip():
        return html_url.strip()
    return APP_RELEASES_PAGE_URL


def _normalize_version(raw_value: str) -> str | None:
    value = raw_value.strip()
    if not value:
        return None

    if value.startswith(("v", "V")):
        value = value[1:]

    match = _VERSION_TEXT_PATTERN.search(value)
    if not match:
        return None

    version = match.group(1).strip()
    parts = [part for part in version.split(".") if part]
    while len(parts) > 3 and parts[-1] == "0":
        parts.pop()
    if not parts:
        return None
    return ".".join(parts)
