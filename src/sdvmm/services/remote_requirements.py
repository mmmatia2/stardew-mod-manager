from __future__ import annotations

from pathlib import Path
from typing import Literal

from sdvmm.domain.models import (
    InstalledMod,
    ModsInventory,
    PackageModEntry,
    RemoteRequirementGuidance,
)
from sdvmm.services.update_metadata import (
    JsonMetadataFetcher,
    check_updates_for_inventory,
)


def evaluate_remote_requirements_for_package_mods(
    package_mods: tuple[PackageModEntry, ...],
    *,
    source: Literal["package_inspection", "downloads_intake", "sandbox_plan"],
    fetcher: JsonMetadataFetcher | None = None,
    timeout_seconds: float = 8.0,
    nexus_api_key: str | None = None,
) -> tuple[RemoteRequirementGuidance, ...]:
    if not package_mods:
        return tuple()

    synthetic_mods = tuple(_build_synthetic_installed_mod(mod, idx) for idx, mod in enumerate(package_mods))
    synthetic_inventory = ModsInventory(
        mods=synthetic_mods,
        parse_warnings=tuple(),
        duplicate_unique_ids=tuple(),
        missing_required_dependencies=tuple(),
        scan_entry_findings=tuple(),
        ignored_entries=tuple(),
    )

    report = check_updates_for_inventory(
        synthetic_inventory,
        fetcher=fetcher,
        timeout_seconds=timeout_seconds,
        nexus_api_key=nexus_api_key,
    )
    status_by_folder = {status.folder_path: status for status in report.statuses}

    guidance_rows: list[RemoteRequirementGuidance] = []
    for synthetic_mod in synthetic_mods:
        status = status_by_folder.get(synthetic_mod.folder_path)
        if status is None:
            continue

        provider = status.remote_link.provider if status.remote_link is not None else None
        guidance_rows.append(
            RemoteRequirementGuidance(
                source=source,
                unique_id=status.unique_id,
                name=status.name,
                provider=provider,
                state=status.remote_requirements_state,
                requirements=status.remote_requirements,
                remote_link=status.remote_link,
                message=status.remote_requirements_message,
            )
        )

    guidance_rows.sort(key=lambda item: (item.name.casefold(), item.unique_id.casefold()))
    return tuple(guidance_rows)


def _build_synthetic_installed_mod(mod: PackageModEntry, idx: int) -> InstalledMod:
    synthetic_root = Path(f"/__sdvmm_pkg_remote_req__/{idx:04d}/{mod.unique_id}")
    return InstalledMod(
        unique_id=mod.unique_id,
        name=mod.name,
        version=mod.version,
        folder_path=synthetic_root,
        manifest_path=synthetic_root / "manifest.json",
        dependencies=mod.dependencies,
        update_keys=mod.update_keys,
    )
