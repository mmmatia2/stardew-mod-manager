from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pytest

from sdvmm.domain.models import (
    InstalledMod,
    ModsInventory,
    UpdateSourceIntentOverlay,
    UpdateSourceIntentRecord,
)
from sdvmm.domain.update_codes import (
    LOCAL_PRIVATE_MOD,
    METADATA_SOURCE_ISSUE,
    MISSING_UPDATE_KEY,
    NO_PROVIDER_MAPPING,
    REMOTE_METADATA_LOOKUP_FAILED,
    UNSUPPORTED_UPDATE_KEY_FORMAT,
)
from sdvmm.services.update_metadata import (
    AUTH_FAILURE,
    MISSING_API_KEY,
    NEXUS_API_KEY_ENV,
    REQUEST_FAILURE,
    RESPONSE_MISSING_VERSION,
    MetadataFetchError,
    check_nexus_connection,
    check_updates_for_inventory,
    compare_versions,
    resolve_remote_link,
)


class StubFetcher:
    def __init__(
        self,
        payloads: dict[str, dict[str, object]] | None = None,
        *,
        error_by_url: dict[str, MetadataFetchError] | None = None,
    ) -> None:
        self._payloads = payloads or {}
        self._error_by_url = error_by_url or {}
        self.calls: list[tuple[str, dict[str, str]]] = []

    def fetch_json(
        self,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        _ = timeout_seconds
        captured_headers = dict(headers or {})
        self.calls.append((url, captured_headers))

        if url in self._error_by_url:
            raise self._error_by_url[url]

        payload = self._payloads.get(url)
        if payload is None:
            raise MetadataFetchError(REQUEST_FAILURE, f"no payload for {url}")

        return payload


def test_compare_versions_derives_expected_ordering() -> None:
    assert compare_versions("1.0.0", "1.1.0") == -1
    assert compare_versions("1.2.0", "1.2.0") == 0
    assert compare_versions("1.4.0", "1.3.9") == 1


def test_real_nexus_updatekey_forms_are_resolved() -> None:
    assert resolve_remote_link(("Nexus:12345",)).provider == "nexus"
    assert resolve_remote_link(("Nexus: 19508",)).provider == "nexus"
    assert resolve_remote_link(("nexus:15223",)).provider == "nexus"
    assert (
        resolve_remote_link(("Nexus:https://www.nexusmods.com/stardewvalley/mods/541",)).provider
        == "nexus"
    )


def test_nexus_provider_reports_up_to_date_when_remote_equals_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(NEXUS_API_KEY_ENV, raising=False)

    mod = _mod(unique_id="Sample.Nexus", version="3.2.1", update_keys=("Nexus:12345",))
    inventory = _inventory((mod,))
    url = "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json"
    fetcher = StubFetcher(
        payloads={
            url: {
                "version": "3.2.1",
                "url": "https://www.nexusmods.com/stardewvalley/mods/12345",
            }
        }
    )

    report = check_updates_for_inventory(inventory, fetcher=fetcher, nexus_api_key="test-api-key")

    status = report.statuses[0]
    assert status.state == "up_to_date"
    assert status.remote_version == "3.2.1"
    assert status.remote_requirements_state == "requirements_absent"
    assert status.remote_requirements == ()
    assert fetcher.calls[0][0] == url
    assert fetcher.calls[0][1].get("apikey") == "test-api-key"


def test_nexus_provider_reports_update_available_when_remote_is_newer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(NEXUS_API_KEY_ENV, raising=False)

    mod = _mod(unique_id="Sample.Nexus", version="1.0.0", update_keys=("Nexus:12345",))
    inventory = _inventory((mod,))
    fetcher = StubFetcher(
        payloads={
            "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json": {
                "version": "1.2.0",
                "url": "https://www.nexusmods.com/stardewvalley/mods/12345",
            }
        }
    )

    report = check_updates_for_inventory(inventory, fetcher=fetcher, nexus_api_key="test-api-key")

    status = report.statuses[0]
    assert status.state == "update_available"
    assert status.remote_version == "1.2.0"
    assert status.remote_requirements_state == "requirements_absent"


def test_nexus_missing_api_key_is_reported_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(NEXUS_API_KEY_ENV, raising=False)

    mod = _mod(unique_id="Sample.Nexus", version="1.0.0", update_keys=("Nexus:12345",))
    inventory = _inventory((mod,))

    report = check_updates_for_inventory(inventory, fetcher=StubFetcher())

    status = report.statuses[0]
    assert status.state == "metadata_unavailable"
    assert status.update_source_diagnostic == REMOTE_METADATA_LOOKUP_FAILED
    assert f"[{MISSING_API_KEY}]" in (status.message or "")
    assert NEXUS_API_KEY_ENV in (status.message or "")
    assert status.remote_requirements_state == "requirements_unavailable"


def test_malformed_nexus_updatekey_is_reported_explicitly() -> None:
    mod = _mod(
        unique_id="Sample.BadNexus",
        version="1.0.0",
        update_keys=("Nexus:not-a-mod-id",),
    )
    inventory = _inventory((mod,))

    report = check_updates_for_inventory(inventory, fetcher=StubFetcher())

    status = report.statuses[0]
    assert status.state == "metadata_unavailable"
    assert status.update_source_diagnostic == UNSUPPORTED_UPDATE_KEY_FORMAT
    assert "[malformed_update_key]" in (status.message or "")
    assert status.remote_requirements_state == "requirements_unavailable"


def test_nexus_auth_or_request_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(NEXUS_API_KEY_ENV, raising=False)

    mod = _mod(unique_id="Sample.Nexus", version="1.0.0", update_keys=("Nexus:12345",))
    inventory = _inventory((mod,))
    url = "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json"

    report = check_updates_for_inventory(
        inventory,
        fetcher=StubFetcher(
            error_by_url={
                url: MetadataFetchError(AUTH_FAILURE, "HTTP 401: Please provide a valid API Key")
            }
        ),
        nexus_api_key="test-api-key",
    )

    status = report.statuses[0]
    assert status.state == "metadata_unavailable"
    assert status.update_source_diagnostic == REMOTE_METADATA_LOOKUP_FAILED
    assert f"[{AUTH_FAILURE}]" in (status.message or "")
    assert status.remote_requirements_state == "requirements_unavailable"


def test_nexus_response_missing_version_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(NEXUS_API_KEY_ENV, raising=False)

    mod = _mod(unique_id="Sample.Nexus", version="1.0.0", update_keys=("Nexus:12345",))
    inventory = _inventory((mod,))

    report = check_updates_for_inventory(
        inventory,
        fetcher=StubFetcher(
            payloads={
                "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json": {
                    "name": "Example Mod"
                }
            }
        ),
        nexus_api_key="test-api-key",
    )

    status = report.statuses[0]
    assert status.state == "metadata_unavailable"
    assert status.update_source_diagnostic == METADATA_SOURCE_ISSUE
    assert f"[{RESPONSE_MISSING_VERSION}]" in (status.message or "")
    assert status.remote_requirements_state == "requirements_absent"


def test_no_regression_for_json_provider() -> None:
    mod = _mod(
        unique_id="Sample.Json",
        version="1.0.0",
        update_keys=("Json:https://example.test/mod-a.json",),
    )
    inventory = _inventory((mod,))
    fetcher = StubFetcher(
        payloads={"https://example.test/mod-a.json": {"version": "1.1.0"}}
    )

    report = check_updates_for_inventory(inventory, fetcher=fetcher, nexus_api_key="test-api-key")

    assert report.statuses[0].state == "update_available"
    assert report.statuses[0].update_source_diagnostic is None


def test_no_regression_for_github_provider() -> None:
    mod = _mod(
        unique_id="Sample.GitHub",
        version="2.5.0",
        update_keys=("GitHub:owner/repo",),
    )
    inventory = _inventory((mod,))
    fetcher = StubFetcher(
        payloads={
            "https://api.github.com/repos/owner/repo/releases/latest": {
                "tag_name": "v2.5.0"
            }
        }
    )

    report = check_updates_for_inventory(
        inventory,
        fetcher=fetcher,
        nexus_api_key="test-api-key",
    )

    assert report.statuses[0].state == "up_to_date"
    assert report.statuses[0].update_source_diagnostic is None


def test_missing_update_key_sets_typed_no_link_diagnostic() -> None:
    mod = _mod(unique_id="Sample.NoLink", version="1.0.0", update_keys=tuple())
    inventory = _inventory((mod,))

    report = check_updates_for_inventory(inventory, fetcher=StubFetcher())

    assert report.statuses[0].state == "no_remote_link"
    assert report.statuses[0].update_source_diagnostic == MISSING_UPDATE_KEY
    assert report.statuses[0].remote_link is None
    assert report.statuses[0].remote_requirements_state == "no_remote_link"


def test_local_private_update_source_sets_typed_no_link_diagnostic() -> None:
    mod = _mod(unique_id="Sample.Private", version="1.0.0", update_keys=("Private:Sample.Mod",))
    inventory = _inventory((mod,))

    report = check_updates_for_inventory(inventory, fetcher=StubFetcher())

    status = report.statuses[0]
    assert status.state == "no_remote_link"
    assert status.update_source_diagnostic == LOCAL_PRIVATE_MOD
    assert status.remote_link is None
    assert "[local_private_mod]" in (status.message or "")


def test_unknown_provider_mapping_produces_distinct_diagnostic_code() -> None:
    mod = _mod(unique_id="Sample.Custom", version="1.0.0", update_keys=("CustomProvider:abc123",))
    inventory = _inventory((mod,))

    report = check_updates_for_inventory(inventory, fetcher=StubFetcher())

    status = report.statuses[0]
    assert status.state == "metadata_unavailable"
    assert status.update_source_diagnostic == NO_PROVIDER_MAPPING
    assert "[unsupported_provider]" in (status.message or "")
    assert "CustomProvider".casefold() in (status.message or "").casefold()


def test_manual_source_association_override_uses_supported_provider_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(NEXUS_API_KEY_ENV, raising=False)

    mod = _mod(unique_id="Sample.Override", version="1.0.0", update_keys=("GitHub:owner/repo",))
    inventory = _inventory((mod,))
    fetcher = StubFetcher(
        payloads={
            "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json": {
                "version": "1.2.0",
                "url": "https://www.nexusmods.com/stardewvalley/mods/12345",
            }
        }
    )
    overlay = UpdateSourceIntentOverlay(
        records=(
            UpdateSourceIntentRecord(
                unique_id="Sample.Override",
                normalized_unique_id="sample.override",
                intent_state="manual_source_association",
                manual_provider="nexus",
                manual_source_key="12345",
                manual_source_page_url="https://example.test/manual-page",
            ),
        )
    )

    report = check_updates_for_inventory(
        inventory,
        fetcher=fetcher,
        nexus_api_key="test-api-key",
        update_source_intent_overlay=overlay,
    )

    status = report.statuses[0]
    assert status.state == "update_available"
    assert status.remote_link is not None
    assert status.remote_link.provider == "nexus"
    assert status.remote_link.key == "stardewvalley:12345"
    assert fetcher.calls == [
        (
            "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json",
            {"apikey": "test-api-key"},
        )
    ]


def test_no_overlay_preserves_manifest_derived_update_resolution() -> None:
    mod = _mod(
        unique_id="Sample.ManifestOnly",
        version="2.5.0",
        update_keys=("GitHub:owner/repo",),
    )
    inventory = _inventory((mod,))
    fetcher = StubFetcher(
        payloads={
            "https://api.github.com/repos/owner/repo/releases/latest": {
                "tag_name": "v2.5.0"
            }
        }
    )

    report = check_updates_for_inventory(
        inventory,
        fetcher=fetcher,
        nexus_api_key="test-api-key",
    )

    status = report.statuses[0]
    assert status.state == "up_to_date"
    assert status.remote_link is not None
    assert status.remote_link.provider == "github"
    assert fetcher.calls == [
        (
            "https://api.github.com/repos/owner/repo/releases/latest",
            {},
        )
    ]


def test_unsupported_manual_source_provider_produces_typed_metadata_issue() -> None:
    mod = _mod(unique_id="Sample.Override", version="1.0.0", update_keys=("GitHub:owner/repo",))
    inventory = _inventory((mod,))
    overlay = UpdateSourceIntentOverlay(
        records=(
            UpdateSourceIntentRecord(
                unique_id="Sample.Override",
                normalized_unique_id="sample.override",
                intent_state="manual_source_association",
                manual_provider="unsupported-provider",
                manual_source_key="abc123",
            ),
        )
    )

    report = check_updates_for_inventory(
        inventory,
        fetcher=StubFetcher(),
        update_source_intent_overlay=overlay,
    )

    status = report.statuses[0]
    assert status.state == "metadata_unavailable"
    assert status.update_source_diagnostic == NO_PROVIDER_MAPPING
    assert status.remote_link is None
    assert "[unsupported_provider]" in (status.message or "")


def test_incomplete_manual_source_association_degrades_predictably_without_crashing() -> None:
    mod = _mod(unique_id="Sample.Override", version="1.0.0", update_keys=("GitHub:owner/repo",))
    inventory = _inventory((mod,))
    overlay = UpdateSourceIntentOverlay(
        records=(
            UpdateSourceIntentRecord(
                unique_id="Sample.Override",
                normalized_unique_id="sample.override",
                intent_state="manual_source_association",
                manual_provider="nexus",
                manual_source_key=None,
            ),
        )
    )

    report = check_updates_for_inventory(
        inventory,
        fetcher=StubFetcher(),
        update_source_intent_overlay=overlay,
    )

    status = report.statuses[0]
    assert status.state == "metadata_unavailable"
    assert status.update_source_diagnostic == METADATA_SOURCE_ISSUE
    assert status.remote_link is None
    assert "[incomplete_manual_source_association]" in (status.message or "")


def test_provider_fallback_uses_nexus_when_github_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(NEXUS_API_KEY_ENV, raising=False)

    mod = _mod(
        unique_id="Sample.Mixed",
        version="1.0.0",
        update_keys=("GitHub:owner/repo", "Nexus:12345"),
    )
    inventory = _inventory((mod,))
    fetcher = StubFetcher(
        payloads={
            "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json": {
                "version": "1.1.0"
            }
        },
        error_by_url={
            "https://api.github.com/repos/owner/repo/releases/latest": MetadataFetchError(
                AUTH_FAILURE,
                "HTTP 403: rate limited",
            )
        },
    )

    report = check_updates_for_inventory(
        inventory,
        fetcher=fetcher,
        nexus_api_key="test-api-key",
    )

    status = report.statuses[0]
    assert status.state == "update_available"
    assert status.update_source_diagnostic is None
    assert status.remote_link is not None
    assert status.remote_link.provider == "nexus"
    assert status.remote_requirements_state == "requirements_absent"


def test_remote_requirements_are_exposed_when_provider_payload_includes_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(NEXUS_API_KEY_ENV, raising=False)

    mod = _mod(unique_id="Sample.Nexus", version="1.0.0", update_keys=("Nexus:12345",))
    inventory = _inventory((mod,))
    fetcher = StubFetcher(
        payloads={
            "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json": {
                "version": "1.0.0",
                "requirements": ["SMAPI", "Content Patcher"],
            }
        }
    )

    report = check_updates_for_inventory(inventory, fetcher=fetcher, nexus_api_key="test-api-key")

    status = report.statuses[0]
    assert status.state == "up_to_date"
    assert status.remote_requirements_state == "requirements_present"
    assert status.remote_requirements == ("Content Patcher", "SMAPI")


def test_nexus_explicit_key_overrides_environment_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(NEXUS_API_KEY_ENV, "env-key")
    mod = _mod(unique_id="Sample.Nexus", version="1.0.0", update_keys=("Nexus:12345",))
    inventory = _inventory((mod,))
    fetcher = StubFetcher(
        payloads={
            "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json": {
                "version": "1.0.0",
            }
        }
    )

    _ = check_updates_for_inventory(inventory, fetcher=fetcher, nexus_api_key="persisted-key")

    assert fetcher.calls
    assert fetcher.calls[0][1].get("apikey") == "persisted-key"


def test_nexus_connection_status_not_configured_when_key_missing() -> None:
    status = check_nexus_connection(nexus_api_key=None, fetcher=StubFetcher())

    assert status.state == "not_configured"


def test_nexus_connection_status_reports_invalid_auth() -> None:
    status = check_nexus_connection(
        nexus_api_key="test-api-key",
        fetcher=StubFetcher(
            error_by_url={
                "https://api.nexusmods.com/v1/users/validate.json": MetadataFetchError(
                    AUTH_FAILURE,
                    "HTTP 401",
                )
            }
        ),
    )

    assert status.state == "invalid_auth_failure"


def test_nexus_connection_status_reports_working_when_validate_endpoint_succeeds() -> None:
    status = check_nexus_connection(
        nexus_api_key="test-api-key",
        fetcher=StubFetcher(
            payloads={
                "https://api.nexusmods.com/v1/users/validate.json": {"name": "tester"},
            }
        ),
    )

    assert status.state == "working_validated"



def _inventory(mods: tuple[InstalledMod, ...]) -> ModsInventory:
    return ModsInventory(
        mods=mods,
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )


def _mod(unique_id: str, version: str, update_keys: tuple[str, ...]) -> InstalledMod:
    base = Path("/tmp") / unique_id.replace(".", "_")
    return InstalledMod(
        unique_id=unique_id,
        name=unique_id,
        version=version,
        folder_path=base,
        manifest_path=base / "manifest.json",
        dependencies=tuple(),
        update_keys=update_keys,
    )
