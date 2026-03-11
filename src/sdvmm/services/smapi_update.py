from __future__ import annotations

import re
from pathlib import Path
from typing import Mapping

from sdvmm.domain.environment_codes import INVALID_GAME_PATH, SMAPI_DETECTED
from sdvmm.domain.models import SmapiUpdateStatus
from sdvmm.domain.smapi_codes import (
    SMAPI_DETECTED_VERSION_KNOWN,
    SMAPI_NOT_DETECTED_FOR_UPDATE,
    SMAPI_UNABLE_TO_DETERMINE,
    SMAPI_UP_TO_DATE,
    SMAPI_UPDATE_AVAILABLE,
)
from sdvmm.services.environment_detection import detect_game_environment
from sdvmm.services.update_metadata import (
    JsonMetadataFetcher,
    MetadataFetchError,
    UrllibJsonMetadataFetcher,
    compare_versions,
)

SMAPI_RELEASES_LATEST_URL = "https://api.github.com/repos/Pathoschild/SMAPI/releases/latest"
SMAPI_RELEASES_PAGE_URL = "https://github.com/Pathoschild/SMAPI/releases"

_SEMVER_WITH_COMMIT_PATTERN = re.compile(rb"\b([0-9]+\.[0-9]+\.[0-9]+)\+[0-9a-f]{7,40}\b")
_TOOLKIT_ASSEMBLY_PATTERN = re.compile(
    rb"SMAPI\.Toolkit,\s*Version=([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)"
)
_VERSION_TEXT_PATTERN = re.compile(r"([0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?)")


def check_smapi_update_status(
    *,
    game_path: Path,
    fetcher: JsonMetadataFetcher | None = None,
    timeout_seconds: float = 8.0,
) -> SmapiUpdateStatus:
    environment = detect_game_environment(game_path)
    if INVALID_GAME_PATH in environment.state_codes:
        return SmapiUpdateStatus(
            state=SMAPI_UNABLE_TO_DETERMINE,
            game_path=environment.game_path,
            smapi_path=environment.smapi_path,
            installed_version=None,
            latest_version=None,
            update_page_url=SMAPI_RELEASES_PAGE_URL,
            message="Game path is invalid; cannot determine SMAPI version/update state.",
        )

    if SMAPI_DETECTED not in environment.state_codes or environment.smapi_path is None:
        return SmapiUpdateStatus(
            state=SMAPI_NOT_DETECTED_FOR_UPDATE,
            game_path=environment.game_path,
            smapi_path=None,
            installed_version=None,
            latest_version=None,
            update_page_url=SMAPI_RELEASES_PAGE_URL,
            message="SMAPI is not detected in the selected game path.",
        )

    installed_version = detect_installed_smapi_version(
        game_path=environment.game_path,
        smapi_path=environment.smapi_path,
    )
    if not installed_version:
        return SmapiUpdateStatus(
            state=SMAPI_UNABLE_TO_DETERMINE,
            game_path=environment.game_path,
            smapi_path=environment.smapi_path,
            installed_version=None,
            latest_version=None,
            update_page_url=SMAPI_RELEASES_PAGE_URL,
            message=(
                "SMAPI entrypoint is present, but installed version could not be derived from local files."
            ),
        )

    active_fetcher = fetcher or UrllibJsonMetadataFetcher()
    try:
        payload = active_fetcher.fetch_json(SMAPI_RELEASES_LATEST_URL, timeout_seconds)
    except MetadataFetchError as exc:
        return SmapiUpdateStatus(
            state=SMAPI_DETECTED_VERSION_KNOWN,
            game_path=environment.game_path,
            smapi_path=environment.smapi_path,
            installed_version=installed_version,
            latest_version=None,
            update_page_url=SMAPI_RELEASES_PAGE_URL,
            message=f"Installed SMAPI version detected ({installed_version}), but remote check failed: {exc.message}",
        )

    latest_version = _extract_latest_smapi_version(payload)
    release_page_url = _extract_release_page_url(payload)
    if not latest_version:
        return SmapiUpdateStatus(
            state=SMAPI_DETECTED_VERSION_KNOWN,
            game_path=environment.game_path,
            smapi_path=environment.smapi_path,
            installed_version=installed_version,
            latest_version=None,
            update_page_url=release_page_url,
            message=(
                f"Installed SMAPI version detected ({installed_version}), but latest release version is unavailable."
            ),
        )

    comparison = compare_versions(installed_version, latest_version)
    if comparison is None:
        return SmapiUpdateStatus(
            state=SMAPI_DETECTED_VERSION_KNOWN,
            game_path=environment.game_path,
            smapi_path=environment.smapi_path,
            installed_version=installed_version,
            latest_version=latest_version,
            update_page_url=release_page_url,
            message=(
                "Installed and latest SMAPI versions were detected, but version formats are not comparable."
            ),
        )

    if comparison < 0:
        return SmapiUpdateStatus(
            state=SMAPI_UPDATE_AVAILABLE,
            game_path=environment.game_path,
            smapi_path=environment.smapi_path,
            installed_version=installed_version,
            latest_version=latest_version,
            update_page_url=release_page_url,
            message=f"SMAPI update available: installed {installed_version}, latest {latest_version}.",
        )

    return SmapiUpdateStatus(
        state=SMAPI_UP_TO_DATE,
        game_path=environment.game_path,
        smapi_path=environment.smapi_path,
        installed_version=installed_version,
        latest_version=latest_version,
        update_page_url=release_page_url,
        message=f"SMAPI is up to date (installed {installed_version}, latest {latest_version}).",
    )


def detect_installed_smapi_version(*, game_path: Path, smapi_path: Path | None = None) -> str | None:
    candidates = _candidate_smapi_binary_paths(game_path=game_path, smapi_path=smapi_path)
    for candidate in candidates:
        version = _extract_smapi_version_from_binary(candidate)
        if version:
            return version
    return None


def default_smapi_update_page_url() -> str:
    return SMAPI_RELEASES_PAGE_URL


def _candidate_smapi_binary_paths(*, game_path: Path, smapi_path: Path | None) -> tuple[Path, ...]:
    candidates: list[Path] = []
    if smapi_path is not None:
        normalized_smapi_path = smapi_path.expanduser()
        if normalized_smapi_path.suffix.casefold() == ".dll":
            candidates.append(normalized_smapi_path)
        else:
            candidates.append(normalized_smapi_path.with_suffix(".dll"))
            candidates.append(normalized_smapi_path)

    candidates.extend(
        (
            game_path / "StardewModdingAPI.dll",
            game_path / "StardewModdingAPI",
            game_path / "StardewModdingAPI.exe",
        )
    )

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved_key = str(candidate.expanduser().resolve(strict=False))
        if resolved_key in seen:
            continue
        seen.add(resolved_key)
        if candidate.exists() and candidate.is_file():
            deduped.append(candidate)
    return tuple(deduped)


def _extract_smapi_version_from_binary(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None

    for pattern in (_SEMVER_WITH_COMMIT_PATTERN, _TOOLKIT_ASSEMBLY_PATTERN):
        match = pattern.search(data)
        if not match:
            continue
        raw_version = match.group(1).decode("utf-8", errors="ignore").strip()
        normalized = _normalize_version(raw_version)
        if normalized:
            return normalized
    return None


def _extract_latest_smapi_version(payload: Mapping[str, object]) -> str | None:
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
    return SMAPI_RELEASES_PAGE_URL


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
