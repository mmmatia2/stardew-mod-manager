from __future__ import annotations

from pathlib import Path

from sdvmm.domain.models import (
    DownloadsIntakeResult,
    DownloadsWatchPollResult,
    ModsInventory,
)
from sdvmm.domain.unique_id import canonicalize_unique_id
from sdvmm.services.dependency_preflight import evaluate_package_dependencies
from sdvmm.services.package_inspector import inspect_zip_package


def initialize_known_zip_paths(watched_path: Path) -> tuple[Path, ...]:
    return tuple(_list_zip_files(watched_path))


def poll_watched_directory(
    *,
    watched_path: Path,
    known_zip_paths: tuple[Path, ...],
    inventory: ModsInventory,
) -> DownloadsWatchPollResult:
    current_zip_paths = _list_zip_files(watched_path)
    known_set = {path.resolve() for path in known_zip_paths}

    new_paths = [path for path in current_zip_paths if path.resolve() not in known_set]

    intakes: list[DownloadsIntakeResult] = []
    for package_path in new_paths:
        intakes.append(inspect_downloads_intake_package(package_path=package_path, inventory=inventory))

    return DownloadsWatchPollResult(
        watched_path=watched_path,
        known_zip_paths=tuple(current_zip_paths),
        intakes=tuple(intakes),
    )


def inspect_downloads_intake_package(
    *, package_path: Path, inventory: ModsInventory
) -> DownloadsIntakeResult:
    try:
        inspection = inspect_zip_package(package_path)
    except Exception as exc:
        return DownloadsIntakeResult(
            package_path=package_path,
            classification="unusable_package",
            message=f"Could not inspect zip package: {exc}",
            mods=tuple(),
            matched_installed_unique_ids=tuple(),
            warnings=tuple(),
            findings=tuple(),
        )

    if not inspection.mods:
        return DownloadsIntakeResult(
            package_path=package_path,
            classification="unusable_package",
            message="Package has no usable manifests in supported depth.",
            mods=inspection.mods,
            matched_installed_unique_ids=tuple(),
            warnings=inspection.warnings,
            findings=inspection.findings,
            dependency_findings=tuple(),
        )

    dependency_findings = evaluate_package_dependencies(
        package_mods=inspection.mods,
        installed_mods=inventory.mods,
        source="downloads_intake",
    )

    installed_keys = {canonicalize_unique_id(mod.unique_id): mod.unique_id for mod in inventory.mods}
    matched: list[str] = []
    for mod in inspection.mods:
        key = canonicalize_unique_id(mod.unique_id)
        if key in installed_keys:
            matched.append(installed_keys[key])

    matched = sorted(set(matched), key=str.casefold)

    if len(inspection.mods) > 1:
        return DownloadsIntakeResult(
            package_path=package_path,
            classification="multi_mod_package",
            message=f"Detected {len(inspection.mods)} mods in one package.",
            mods=inspection.mods,
            matched_installed_unique_ids=tuple(matched),
            warnings=inspection.warnings,
            findings=inspection.findings,
            dependency_findings=dependency_findings,
        )

    if matched:
        return DownloadsIntakeResult(
            package_path=package_path,
            classification="update_replace_candidate",
            message="Package appears to match an already installed mod by UniqueID.",
            mods=inspection.mods,
            matched_installed_unique_ids=tuple(matched),
            warnings=inspection.warnings,
            findings=inspection.findings,
            dependency_findings=dependency_findings,
        )

    return DownloadsIntakeResult(
        package_path=package_path,
        classification="new_install_candidate",
        message="Package appears to contain a new mod not present in current inventory.",
        mods=inspection.mods,
        matched_installed_unique_ids=tuple(),
        warnings=inspection.warnings,
        findings=inspection.findings,
        dependency_findings=dependency_findings,
    )


def _list_zip_files(watched_path: Path) -> list[Path]:
    zip_paths = [
        item
        for item in sorted(
            watched_path.rglob("*"),
            key=lambda path: str(path.relative_to(watched_path)).lower(),
        )
        if item.is_file() and item.suffix.lower() == ".zip"
    ]
    return zip_paths
