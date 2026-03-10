from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sdvmm.domain.models import (
    DuplicateUniqueIdFinding,
    InstalledMod,
    ManifestParseResult,
    MissingDependencyFinding,
    ModManifest,
    ModsInventory,
    ParseWarning,
    ScanEntryFinding,
)
from sdvmm.domain.scan_codes import (
    AMBIGUOUS_ENTRY,
    DIRECT_MOD,
    INVALID_MANIFEST_ENTRY,
    MISSING_MANIFEST_ENTRY,
    MULTI_MOD_CONTAINER,
    NESTED_MOD_CONTAINER,
)
from sdvmm.domain.unique_id import canonicalize_unique_id
from sdvmm.domain.warning_codes import MISSING_MANIFEST
from sdvmm.services.manifest_parser import parse_manifest_file


def scan_mods_directory(
    mods_dir: Path,
    *,
    excluded_paths: tuple[Path, ...] = tuple(),
) -> ModsInventory:
    installed_mods: list[InstalledMod] = []
    warnings: list[ParseWarning] = []
    scan_entry_findings: list[ScanEntryFinding] = []
    ignored_entries: list[Path] = []
    excluded_resolved = tuple(_resolve_path_for_match(path) for path in excluded_paths)

    for entry in sorted(mods_dir.iterdir(), key=lambda item: item.name.lower()):
        if not entry.is_dir():
            ignored_entries.append(entry)
            continue
        if _is_excluded_entry(entry, excluded_resolved):
            ignored_entries.append(entry)
            continue

        entry_mods, entry_warnings, entry_findings = _scan_top_level_entry(entry)
        installed_mods.extend(entry_mods)
        warnings.extend(entry_warnings)
        scan_entry_findings.extend(entry_findings)

    installed_mods.sort(
        key=lambda mod: (canonicalize_unique_id(mod.unique_id), mod.folder_path.name.lower())
    )

    duplicates = _detect_duplicate_unique_ids(installed_mods)
    missing_required_dependencies = _find_missing_required_dependencies(installed_mods)

    return ModsInventory(
        mods=tuple(installed_mods),
        parse_warnings=tuple(
            sorted(warnings, key=lambda warning: (warning.code, str(warning.mod_path).lower()))
        ),
        duplicate_unique_ids=duplicates,
        missing_required_dependencies=missing_required_dependencies,
        scan_entry_findings=tuple(
            sorted(
                scan_entry_findings,
                key=lambda finding: (finding.kind, str(finding.entry_path).lower()),
            )
        ),
        ignored_entries=tuple(sorted(ignored_entries, key=lambda path: path.name.lower())),
    )


def _scan_top_level_entry(
    entry: Path,
) -> tuple[list[InstalledMod], list[ParseWarning], list[ScanEntryFinding]]:
    installed_mods: list[InstalledMod] = []
    warnings: list[ParseWarning] = []
    findings: list[ScanEntryFinding] = []

    direct_result = _parse_manifest_if_present(entry)

    if direct_result is not None:
        warnings.extend(direct_result.warnings)

        if direct_result.manifest is not None:
            installed_mods.append(_to_installed_mod(entry, direct_result.manifest))
            findings.append(
                ScanEntryFinding(
                    kind=DIRECT_MOD,
                    entry_path=entry,
                    mod_paths=(entry,),
                    message="Top-level folder is a direct mod.",
                )
            )

            nested_manifest_dirs = _discover_nested_manifest_dirs(entry)
            if nested_manifest_dirs:
                findings.append(
                    ScanEntryFinding(
                        kind=AMBIGUOUS_ENTRY,
                        entry_path=entry,
                        mod_paths=tuple(nested_manifest_dirs),
                        message="Direct manifest found; nested manifests under this folder were ignored.",
                    )
                )

            return installed_mods, warnings, findings

    nested_results = _parse_nested_manifest_dirs(entry)
    nested_manifest_dirs = [mod_dir for mod_dir, _ in nested_results]

    nested_valid_mods: list[InstalledMod] = []
    nested_invalid_warnings: list[ParseWarning] = []

    for mod_dir, parse_result in nested_results:
        warnings.extend(parse_result.warnings)

        if parse_result.manifest is None:
            nested_invalid_warnings.extend(parse_result.warnings)
            continue

        nested_valid_mods.append(_to_installed_mod(mod_dir, parse_result.manifest))

    installed_mods.extend(nested_valid_mods)

    if len(nested_valid_mods) == 1:
        findings.append(
            ScanEntryFinding(
                kind=NESTED_MOD_CONTAINER,
                entry_path=entry,
                mod_paths=(nested_valid_mods[0].folder_path,),
                message="Container with one nested mod discovered.",
            )
        )
        return installed_mods, warnings, findings

    if len(nested_valid_mods) > 1:
        findings.append(
            ScanEntryFinding(
                kind=MULTI_MOD_CONTAINER,
                entry_path=entry,
                mod_paths=tuple(mod.folder_path for mod in nested_valid_mods),
                message=f"Container with {len(nested_valid_mods)} nested mods discovered.",
            )
        )
        return installed_mods, warnings, findings

    invalid_warnings = []
    if direct_result is not None and direct_result.manifest is None:
        invalid_warnings.extend(direct_result.warnings)
    invalid_warnings.extend(nested_invalid_warnings)

    if invalid_warnings:
        findings.append(
            ScanEntryFinding(
                kind=INVALID_MANIFEST_ENTRY,
                entry_path=entry,
                mod_paths=tuple(sorted(nested_manifest_dirs, key=lambda path: path.name.lower())),
                message=_summarize_invalid_manifest(invalid_warnings),
            )
        )
        return installed_mods, warnings, findings

    warning = ParseWarning(
        code=MISSING_MANIFEST,
        message="No manifest.json found at top level or within two nested levels",
        mod_path=entry,
        manifest_path=entry / "manifest.json",
    )
    warnings.append(warning)
    findings.append(
        ScanEntryFinding(
            kind=MISSING_MANIFEST_ENTRY,
            entry_path=entry,
            mod_paths=tuple(),
            message="No usable mod manifest found in allowed scan depth.",
        )
    )

    return installed_mods, warnings, findings


def _parse_manifest_if_present(mod_dir: Path) -> ManifestParseResult | None:
    manifest_path = mod_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    return parse_manifest_file(manifest_path=manifest_path, mod_dir=mod_dir)


def _parse_nested_manifest_dirs(entry: Path) -> list[tuple[Path, ManifestParseResult]]:
    nested_results: list[tuple[Path, ManifestParseResult]] = []
    for candidate in _discover_nested_manifest_dirs(entry):
        parse_result = _parse_manifest_if_present(candidate)
        if parse_result is None:
            continue
        nested_results.append((candidate, parse_result))

    return nested_results


def _discover_nested_manifest_dirs(entry: Path) -> tuple[Path, ...]:
    nested_dirs: list[Path] = []

    for child in sorted(entry.iterdir(), key=lambda path: path.name.lower()):
        if not child.is_dir():
            continue
        if _has_manifest(child):
            nested_dirs.append(child)

        for grandchild in sorted(child.iterdir(), key=lambda path: path.name.lower()):
            if not grandchild.is_dir():
                continue
            if _has_manifest(grandchild):
                nested_dirs.append(grandchild)

    return tuple(nested_dirs)


def _has_manifest(mod_dir: Path) -> bool:
    return (mod_dir / "manifest.json").exists()


def _summarize_invalid_manifest(warnings: list[ParseWarning]) -> str:
    first = warnings[0]
    manifest_fragment = f" ({first.manifest_path})" if first.manifest_path else ""
    return f"[{first.code}] {first.message}{manifest_fragment}"


def _to_installed_mod(mod_dir: Path, manifest: ModManifest) -> InstalledMod:
    return InstalledMod(
        unique_id=manifest.unique_id,
        name=manifest.name,
        version=manifest.version,
        folder_path=mod_dir,
        manifest_path=mod_dir / "manifest.json",
        dependencies=manifest.dependencies,
        update_keys=manifest.update_keys,
    )


def _detect_duplicate_unique_ids(
    installed_mods: list[InstalledMod],
) -> tuple[DuplicateUniqueIdFinding, ...]:
    buckets: dict[str, list[InstalledMod]] = defaultdict(list)

    for mod in installed_mods:
        buckets[canonicalize_unique_id(mod.unique_id)].append(mod)

    findings: list[DuplicateUniqueIdFinding] = []
    for grouped_mods in buckets.values():
        if len(grouped_mods) < 2:
            continue

        grouped_mods.sort(key=lambda mod: mod.folder_path.name.lower())
        folder_paths = tuple(mod.folder_path for mod in grouped_mods)
        findings.append(
            DuplicateUniqueIdFinding(
                unique_id=grouped_mods[0].unique_id,
                folder_paths=folder_paths,
            )
        )

    findings.sort(key=lambda finding: canonicalize_unique_id(finding.unique_id))
    return tuple(findings)


def _find_missing_required_dependencies(
    installed_mods: list[InstalledMod],
) -> tuple[MissingDependencyFinding, ...]:
    installed_unique_ids = {canonicalize_unique_id(mod.unique_id) for mod in installed_mods}
    findings: list[MissingDependencyFinding] = []

    for mod in installed_mods:
        for dependency in mod.dependencies:
            if not dependency.required:
                continue
            if canonicalize_unique_id(dependency.unique_id) in installed_unique_ids:
                continue

            findings.append(
                MissingDependencyFinding(
                    required_by_unique_id=mod.unique_id,
                    required_by_folder=mod.folder_path,
                    missing_unique_id=dependency.unique_id,
                )
            )

    findings.sort(
        key=lambda finding: (
            canonicalize_unique_id(finding.required_by_unique_id),
            canonicalize_unique_id(finding.missing_unique_id),
            finding.required_by_folder.name.lower(),
        )
    )
    return tuple(findings)


def _resolve_path_for_match(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_excluded_entry(entry: Path, excluded_resolved: tuple[Path, ...]) -> bool:
    if not excluded_resolved:
        return False

    entry_resolved = _resolve_path_for_match(entry)
    for excluded in excluded_resolved:
        if entry_resolved == excluded:
            return True
    return False
