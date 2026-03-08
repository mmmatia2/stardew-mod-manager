from __future__ import annotations

from typing import Mapping

import pytest

from sdvmm.domain.models import ManifestDependency, PackageModEntry
from sdvmm.services.dependency_preflight import evaluate_package_dependencies
from sdvmm.services.remote_requirements import evaluate_remote_requirements_for_package_mods
from sdvmm.services.update_metadata import (
    NEXUS_API_KEY_ENV,
    REQUEST_FAILURE,
    MetadataFetchError,
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

    def fetch_json(
        self,
        url: str,
        timeout_seconds: float,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, object]:
        _ = timeout_seconds
        _ = headers

        if url in self._error_by_url:
            raise self._error_by_url[url]

        payload = self._payloads.get(url)
        if payload is None:
            raise MetadataFetchError(REQUEST_FAILURE, f"no payload for {url}")
        return payload


def test_remote_requirements_present_for_supported_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(NEXUS_API_KEY_ENV, "test-api-key")
    package_mod = PackageModEntry(
        name="Sample Mod",
        unique_id="Sample.Mod",
        version="1.0.0",
        manifest_path="Sample/manifest.json",
        dependencies=tuple(),
        update_keys=("Nexus:12345",),
    )
    fetcher = StubFetcher(
        payloads={
            "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json": {
                "version": "1.0.0",
                "requirements": ["SMAPI", "Content Patcher"],
            }
        }
    )

    guidance = evaluate_remote_requirements_for_package_mods(
        (package_mod,),
        source="package_inspection",
        fetcher=fetcher,
    )

    assert len(guidance) == 1
    assert guidance[0].state == "requirements_present"
    assert guidance[0].requirements == ("Content Patcher", "SMAPI")
    assert guidance[0].provider == "nexus"


def test_remote_requirements_absent_when_provider_has_no_requirements(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(NEXUS_API_KEY_ENV, "test-api-key")
    package_mod = PackageModEntry(
        name="Sample Mod",
        unique_id="Sample.Mod",
        version="1.0.0",
        manifest_path="Sample/manifest.json",
        dependencies=tuple(),
        update_keys=("Nexus:12345",),
    )
    fetcher = StubFetcher(
        payloads={
            "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json": {
                "version": "1.0.0"
            }
        }
    )

    guidance = evaluate_remote_requirements_for_package_mods(
        (package_mod,),
        source="downloads_intake",
        fetcher=fetcher,
    )

    assert len(guidance) == 1
    assert guidance[0].state == "requirements_absent"
    assert guidance[0].requirements == ()


def test_remote_requirements_unavailable_on_fetch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(NEXUS_API_KEY_ENV, "test-api-key")
    package_mod = PackageModEntry(
        name="Sample Mod",
        unique_id="Sample.Mod",
        version="1.0.0",
        manifest_path="Sample/manifest.json",
        dependencies=tuple(),
        update_keys=("Nexus:12345",),
    )
    fetcher = StubFetcher(
        error_by_url={
            "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json": MetadataFetchError(
                REQUEST_FAILURE,
                "network down",
            )
        }
    )

    guidance = evaluate_remote_requirements_for_package_mods(
        (package_mod,),
        source="sandbox_plan",
        fetcher=fetcher,
    )

    assert len(guidance) == 1
    assert guidance[0].state == "requirements_unavailable"
    assert "network down" in (guidance[0].message or "")


def test_manifest_dependency_blocking_is_separate_from_remote_requirement_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(NEXUS_API_KEY_ENV, "test-api-key")
    package_mod = PackageModEntry(
        name="Needs Dependency",
        unique_id="Sample.NeedsDep",
        version="1.0.0",
        manifest_path="NeedsDep/manifest.json",
        dependencies=(ManifestDependency(unique_id="Sample.Required", required=True),),
        update_keys=("Nexus:12345",),
    )
    fetcher = StubFetcher(
        payloads={
            "https://api.nexusmods.com/v1/games/stardewvalley/mods/12345.json": {
                "version": "1.0.0",
                "requirements": ["SMAPI"],
            }
        }
    )

    dependency_findings = evaluate_package_dependencies(
        package_mods=(package_mod,),
        installed_mods=tuple(),
        source="sandbox_plan",
    )
    guidance = evaluate_remote_requirements_for_package_mods(
        (package_mod,),
        source="sandbox_plan",
        fetcher=fetcher,
    )

    assert dependency_findings[0].state == "missing_required_dependency"
    assert guidance[0].state == "requirements_present"
    assert guidance[0].requirements == ("SMAPI",)
