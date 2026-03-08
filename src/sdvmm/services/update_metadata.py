from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
import re
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sdvmm.domain.models import (
    InstalledMod,
    ModUpdateReport,
    ModUpdateStatus,
    ModsInventory,
    RemoteModLink,
)
from sdvmm.domain.update_codes import (
    GITHUB_PROVIDER,
    JSON_PROVIDER,
    METADATA_UNAVAILABLE,
    NEXUS_PROVIDER,
    NO_REMOTE_LINK,
    UPDATE_AVAILABLE,
    UP_TO_DATE,
)

NEXUS_API_KEY_ENV = "SDVMM_NEXUS_API_KEY"

MALFORMED_UPDATE_KEY = "malformed_update_key"
MISSING_API_KEY = "missing_api_key"
AUTH_FAILURE = "auth_failure"
REQUEST_FAILURE = "request_failure"
RESPONSE_MISSING_VERSION = "response_missing_version"
UNEXPECTED_PROVIDER_RESPONSE = "unexpected_provider_response"
UNSUPPORTED_PROVIDER = "unsupported_provider"


class MetadataFetchError(ValueError):
    """Raised when remote metadata cannot be retrieved or parsed."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


class JsonMetadataFetcher(Protocol):
    def fetch_json(
        self,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Fetch JSON from a remote URL."""


class UrllibJsonMetadataFetcher:
    def fetch_json(
        self,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        request_headers: dict[str, str] = {
            "User-Agent": "sdvmm/0.1 (+local metadata check)",
            "Accept": "application/json",
        }
        if headers:
            request_headers.update({str(key): str(value) for key, value in headers.items()})

        request = Request(url, headers=request_headers)

        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            body_message = _extract_http_error_message(exc)
            reason = AUTH_FAILURE if exc.code in {401, 403} else REQUEST_FAILURE
            message = f"HTTP {exc.code}: {body_message or exc.reason or 'request failed'}"
            raise MetadataFetchError(reason, message) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise MetadataFetchError(REQUEST_FAILURE, str(exc)) from exc

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise MetadataFetchError(
                UNEXPECTED_PROVIDER_RESPONSE,
                f"Invalid metadata JSON: {exc}",
            ) from exc

        if not isinstance(data, dict):
            raise MetadataFetchError(
                UNEXPECTED_PROVIDER_RESPONSE,
                "Metadata payload must be a JSON object",
            )

        return data


class MetadataProviderAdapter(Protocol):
    provider: str

    def build_link(self, raw_value: str) -> RemoteModLink | None:
        """Build a provider-specific remote link from UpdateKeys value."""

    def fetch_payload(
        self,
        link: RemoteModLink,
        *,
        fetcher: JsonMetadataFetcher,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        """Load provider metadata payload for a resolved link."""

    def extract_version(self, payload: Mapping[str, Any]) -> str | None:
        """Extract a comparable remote version from provider payload."""

    def extract_page_url(self, payload: Mapping[str, Any]) -> str | None:
        """Extract a user-facing remote page URL from provider payload, if present."""


class JsonProviderAdapter:
    provider = JSON_PROVIDER

    def build_link(self, raw_value: str) -> RemoteModLink | None:
        url = raw_value.strip()
        if not _looks_like_url(url):
            return None

        return RemoteModLink(
            provider=JSON_PROVIDER,
            key=url,
            page_url=url,
            metadata_url=url,
        )

    def fetch_payload(
        self,
        link: RemoteModLink,
        *,
        fetcher: JsonMetadataFetcher,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        if not link.metadata_url:
            raise MetadataFetchError(UNEXPECTED_PROVIDER_RESPONSE, "JSON provider has no metadata URL")
        return fetcher.fetch_json(link.metadata_url, timeout_seconds)

    def extract_version(self, payload: Mapping[str, Any]) -> str | None:
        return _extract_generic_version(payload)

    def extract_page_url(self, payload: Mapping[str, Any]) -> str | None:
        return _extract_generic_page_url(payload)


class GithubProviderAdapter:
    provider = GITHUB_PROVIDER

    def build_link(self, raw_value: str) -> RemoteModLink | None:
        repo = raw_value.strip()
        if not _looks_like_repo_slug(repo):
            return None

        return RemoteModLink(
            provider=GITHUB_PROVIDER,
            key=repo,
            page_url=f"https://github.com/{repo}",
            metadata_url=f"https://api.github.com/repos/{repo}/releases/latest",
        )

    def fetch_payload(
        self,
        link: RemoteModLink,
        *,
        fetcher: JsonMetadataFetcher,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        if not link.metadata_url:
            raise MetadataFetchError(UNEXPECTED_PROVIDER_RESPONSE, "GitHub provider has no metadata URL")
        return fetcher.fetch_json(link.metadata_url, timeout_seconds)

    def extract_version(self, payload: Mapping[str, Any]) -> str | None:
        tag_name = payload.get("tag_name")
        if isinstance(tag_name, str) and tag_name.strip():
            stripped = tag_name.strip()
            if stripped.startswith(("v", "V")) and len(stripped) > 1 and stripped[1].isdigit():
                return stripped[1:]
            return stripped

        return _extract_generic_version(payload)

    def extract_page_url(self, payload: Mapping[str, Any]) -> str | None:
        return _extract_generic_page_url(payload)


class NexusProviderAdapter:
    provider = NEXUS_PROVIDER

    def build_link(self, raw_value: str) -> RemoteModLink | None:
        parsed = _parse_nexus_key(raw_value)
        if parsed is None:
            return None

        game_domain, mod_id = parsed
        return RemoteModLink(
            provider=NEXUS_PROVIDER,
            key=f"{game_domain}:{mod_id}",
            page_url=f"https://www.nexusmods.com/{game_domain}/mods/{mod_id}",
            metadata_url=f"https://api.nexusmods.com/v1/games/{game_domain}/mods/{mod_id}.json",
        )

    def fetch_payload(
        self,
        link: RemoteModLink,
        *,
        fetcher: JsonMetadataFetcher,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        if not link.metadata_url:
            raise MetadataFetchError(UNEXPECTED_PROVIDER_RESPONSE, "Nexus provider has no metadata URL")

        api_key = os.getenv(NEXUS_API_KEY_ENV, "").strip()
        if not api_key:
            raise MetadataFetchError(
                MISSING_API_KEY,
                (
                    f"Nexus metadata requires {NEXUS_API_KEY_ENV} in the current process environment."
                ),
            )

        return fetcher.fetch_json(
            link.metadata_url,
            timeout_seconds,
            headers={
                "apikey": api_key,
            },
        )

    def extract_version(self, payload: Mapping[str, Any]) -> str | None:
        for key in ("version", "mod_version"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return _extract_generic_version(payload)

    def extract_page_url(self, payload: Mapping[str, Any]) -> str | None:
        value = payload.get("url")
        if isinstance(value, str) and _looks_like_url(value) and "nexusmods.com" in value.casefold():
            return value.strip()
        return None


@dataclass(frozen=True, slots=True)
class LinkResolutionIssue:
    provider: str
    reason: str
    message: str


@dataclass(frozen=True, slots=True)
class ProviderFailure:
    provider: str
    reason: str
    message: str


_PROVIDER_PRIORITY = (JSON_PROVIDER, GITHUB_PROVIDER, NEXUS_PROVIDER)
_PROVIDER_ADAPTERS: tuple[MetadataProviderAdapter, ...] = (
    JsonProviderAdapter(),
    GithubProviderAdapter(),
    NexusProviderAdapter(),
)
_PROVIDERS_BY_NAME = {adapter.provider: adapter for adapter in _PROVIDER_ADAPTERS}


def check_updates_for_inventory(
    inventory: ModsInventory,
    *,
    fetcher: JsonMetadataFetcher | None = None,
    timeout_seconds: float = 8.0,
) -> ModUpdateReport:
    active_fetcher = fetcher or UrllibJsonMetadataFetcher()

    statuses: list[ModUpdateStatus] = []
    for mod in inventory.mods:
        statuses.append(
            _check_single_mod(
                mod=mod,
                fetcher=active_fetcher,
                timeout_seconds=timeout_seconds,
            )
        )

    statuses.sort(key=lambda status: (status.name.casefold(), status.folder_path.name.casefold()))
    return ModUpdateReport(statuses=tuple(statuses))


def compare_versions(installed_version: str, remote_version: str) -> int | None:
    left = _tokenize_version(installed_version)
    right = _tokenize_version(remote_version)

    if not left or not right:
        return None

    max_len = max(len(left), len(right))
    for idx in range(max_len):
        left_token = left[idx] if idx < len(left) else 0
        right_token = right[idx] if idx < len(right) else 0

        if left_token == right_token:
            continue

        left_key = _token_key(left_token)
        right_key = _token_key(right_token)
        if left_key < right_key:
            return -1
        return 1

    return 0


def resolve_remote_link(update_keys: tuple[str, ...]) -> RemoteModLink | None:
    candidates, _ = resolve_remote_link_candidates(update_keys)
    if not candidates:
        return None
    return candidates[0]


def resolve_remote_link_candidates(
    update_keys: tuple[str, ...],
) -> tuple[tuple[RemoteModLink, ...], tuple[LinkResolutionIssue, ...]]:
    candidates: list[RemoteModLink] = []
    issues: list[LinkResolutionIssue] = []

    for raw_key in update_keys:
        provider, value = _parse_update_key(raw_key)
        if provider is None:
            continue

        adapter = _PROVIDERS_BY_NAME.get(provider)
        if adapter is None:
            continue

        link = adapter.build_link(value)
        if link is not None:
            candidates.append(link)
            continue

        issues.append(
            LinkResolutionIssue(
                provider=provider,
                reason=MALFORMED_UPDATE_KEY,
                message=f"Unsupported {provider} UpdateKey format: {raw_key}",
            )
        )

    ordered: list[RemoteModLink] = []
    for provider_name in _PROVIDER_PRIORITY:
        ordered.extend(link for link in candidates if link.provider == provider_name)

    return tuple(ordered), tuple(issues)


def _check_single_mod(
    mod: InstalledMod,
    *,
    fetcher: JsonMetadataFetcher,
    timeout_seconds: float,
) -> ModUpdateStatus:
    links, resolution_issues = resolve_remote_link_candidates(mod.update_keys)
    base_status = ModUpdateStatus(
        unique_id=mod.unique_id,
        name=mod.name,
        folder_path=mod.folder_path,
        installed_version=mod.version,
        remote_version=None,
        state=NO_REMOTE_LINK,
        remote_link=links[0] if links else None,
        message=None,
    )

    if not links:
        if resolution_issues:
            issue = resolution_issues[0]
            return replace(
                base_status,
                state=METADATA_UNAVAILABLE,
                message=f"[{issue.reason}] {issue.message}",
            )
        return base_status

    failures: list[ProviderFailure] = []

    for link in links:
        provider = _PROVIDERS_BY_NAME.get(link.provider)
        if provider is None:
            failures.append(
                ProviderFailure(
                    provider=link.provider,
                    reason=UNSUPPORTED_PROVIDER,
                    message=f"Provider '{link.provider}' is not supported.",
                )
            )
            continue

        try:
            payload = provider.fetch_payload(
                link,
                fetcher=fetcher,
                timeout_seconds=timeout_seconds,
            )
        except MetadataFetchError as exc:
            failures.append(
                ProviderFailure(
                    provider=link.provider,
                    reason=exc.reason,
                    message=exc.message,
                )
            )
            continue

        page_url = provider.extract_page_url(payload)
        if page_url:
            link = replace(link, page_url=page_url)

        remote_version = provider.extract_version(payload)
        if remote_version is None:
            failures.append(
                ProviderFailure(
                    provider=link.provider,
                    reason=RESPONSE_MISSING_VERSION,
                    message="Remote metadata does not provide a usable version field.",
                )
            )
            continue

        comparison = compare_versions(mod.version, remote_version)
        if comparison is None:
            failures.append(
                ProviderFailure(
                    provider=link.provider,
                    reason=UNEXPECTED_PROVIDER_RESPONSE,
                    message="Installed or remote version format is not comparable.",
                )
            )
            continue

        if comparison < 0:
            return replace(
                base_status,
                state=UPDATE_AVAILABLE,
                remote_link=link,
                remote_version=remote_version,
                message="Remote version is newer than installed version.",
            )

        return replace(
            base_status,
            state=UP_TO_DATE,
            remote_link=link,
            remote_version=remote_version,
            message="Installed version is up to date.",
        )

    fallback_link = links[0]
    message = _summarize_failures(failures)
    return replace(
        base_status,
        state=METADATA_UNAVAILABLE,
        remote_link=fallback_link,
        message=message,
    )


def _parse_update_key(raw_key: str) -> tuple[str | None, str]:
    if ":" not in raw_key:
        return None, ""

    prefix, value = raw_key.split(":", 1)
    provider = prefix.strip().casefold()
    return provider, value.strip()


def _parse_nexus_key(raw_value: str) -> tuple[str, str] | None:
    value = raw_value.strip()
    if not value:
        return None

    if value.isdigit():
        return "stardewvalley", value

    match = re.fullmatch(r"([a-z0-9][a-z0-9_-]*):(\d+)", value.casefold())
    if match is not None:
        game_domain, mod_id = match.groups()
        return game_domain, mod_id

    url_match = re.fullmatch(
        r"https?://(?:www\.)?nexusmods\.com/([a-z0-9][a-z0-9_-]*)/mods/(\d+)(?:[/?#].*)?",
        value.casefold(),
    )
    if url_match is not None:
        game_domain, mod_id = url_match.groups()
        return game_domain, mod_id

    return None


def _looks_like_repo_slug(value: str) -> bool:
    return re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value.strip()) is not None


def _tokenize_version(version: str) -> list[int | str]:
    chunks = [chunk for chunk in re.split(r"[^0-9A-Za-z]+", version.strip()) if chunk]
    tokens: list[int | str] = []
    for chunk in chunks:
        if chunk.isdigit():
            tokens.append(int(chunk))
        else:
            tokens.append(chunk.casefold())

    return tokens


def _token_key(value: int | str) -> tuple[int, int | str]:
    if isinstance(value, int):
        return (0, value)
    return (1, value)


def _extract_generic_version(payload: Mapping[str, Any]) -> str | None:
    for key in ("version", "Version", "latest_version", "latestVersion"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _extract_generic_page_url(payload: Mapping[str, Any]) -> str | None:
    for key in ("html_url", "page_url", "url"):
        value = payload.get(key)
        if isinstance(value, str) and _looks_like_url(value):
            return value.strip()
    return None


def _looks_like_url(value: str) -> bool:
    lowered = value.strip().casefold()
    return lowered.startswith("https://") or lowered.startswith("http://")


def _extract_http_error_message(exc: HTTPError) -> str | None:
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        return None

    if not body.strip():
        return None

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()[:240]

    if isinstance(payload, dict):
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()

    return body.strip()[:240]


def _summarize_failures(failures: list[ProviderFailure]) -> str:
    if not failures:
        return "[metadata_unavailable] Metadata provider could not resolve a usable version."

    shown = failures[:2]
    fragments = [
        f"[{failure.reason}] {failure.provider}: {failure.message}"
        for failure in shown
    ]
    if len(failures) > len(shown):
        fragments.append(f"... {len(failures) - len(shown)} more provider failure(s)")
    return "; ".join(fragments)
