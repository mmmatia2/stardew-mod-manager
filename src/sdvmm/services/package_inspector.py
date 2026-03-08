from __future__ import annotations

from pathlib import Path, PurePosixPath
import zipfile

from sdvmm.domain.models import (
    PackageFinding,
    PackageInspectionResult,
    PackageModEntry,
    PackageWarning,
)
from sdvmm.domain.package_codes import (
    DIRECT_SINGLE_MOD_PACKAGE,
    INVALID_MANIFEST_PACKAGE,
    MULTI_MOD_PACKAGE,
    NESTED_SINGLE_MOD_PACKAGE,
    NO_USABLE_MANIFEST_FOUND,
    TOO_DEEP_UNSUPPORTED_PACKAGE,
)
from sdvmm.domain.unique_id import canonicalize_unique_id
from sdvmm.services.dependency_preflight import evaluate_package_dependencies
from sdvmm.services.manifest_parser import parse_manifest_text

MAX_PACKAGE_MANIFEST_DEPTH = 3


def inspect_zip_package(package_path: Path) -> PackageInspectionResult:
    with zipfile.ZipFile(package_path, "r") as archive:
        manifest_entries = _find_manifest_entries(archive)
        allowed_entries, too_deep_entries = _split_manifest_depth(manifest_entries)

        mods: list[PackageModEntry] = []
        warnings: list[PackageWarning] = []

        for manifest_entry in allowed_entries:
            parse_result = _parse_manifest_entry(archive, manifest_entry)
            warnings.extend(parse_result[1])

            if parse_result[0] is not None:
                mods.append(parse_result[0])

    mods.sort(key=lambda mod: (canonicalize_unique_id(mod.unique_id), mod.manifest_path.lower()))
    warnings.sort(key=lambda warning: (warning.code, warning.manifest_path.lower()))

    findings = _build_findings(
        mods=mods,
        warnings=warnings,
        too_deep_entries=too_deep_entries,
    )
    dependency_findings = evaluate_package_dependencies(
        package_mods=tuple(mods),
        installed_mods=None,
        source="package_inspection",
    )

    return PackageInspectionResult(
        package_path=package_path,
        mods=tuple(mods),
        warnings=tuple(warnings),
        findings=findings,
        dependency_findings=dependency_findings,
    )


def _find_manifest_entries(archive: zipfile.ZipFile) -> list[str]:
    entries: list[str] = []
    for info in archive.infolist():
        if info.is_dir():
            continue

        path = PurePosixPath(info.filename)
        if path.name != "manifest.json":
            continue

        normalized = str(path).lstrip("/")
        entries.append(normalized)

    entries.sort(key=lambda value: value.lower())
    return entries


def _split_manifest_depth(entries: list[str]) -> tuple[list[str], list[str]]:
    allowed: list[str] = []
    too_deep: list[str] = []

    for manifest_entry in entries:
        depth = _manifest_depth(manifest_entry)
        if depth <= MAX_PACKAGE_MANIFEST_DEPTH:
            allowed.append(manifest_entry)
        else:
            too_deep.append(manifest_entry)

    return allowed, too_deep


def _manifest_depth(manifest_entry: str) -> int:
    return max(len(PurePosixPath(manifest_entry).parts) - 1, 0)


def _parse_manifest_entry(
    archive: zipfile.ZipFile,
    manifest_entry: str,
) -> tuple[PackageModEntry | None, list[PackageWarning]]:
    try:
        raw_bytes = archive.read(manifest_entry)
    except KeyError:
        warning = PackageWarning(
            code="manifest_read_error",
            message="manifest.json entry disappeared while reading zip",
            manifest_path=manifest_entry,
        )
        return None, [warning]
    except OSError as exc:
        warning = PackageWarning(
            code="manifest_read_error",
            message=f"Could not read manifest entry: {exc}",
            manifest_path=manifest_entry,
        )
        return None, [warning]

    try:
        raw_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        warning = PackageWarning(
            code="malformed_manifest",
            message=f"manifest.json is not valid UTF-8 text: {exc}",
            manifest_path=manifest_entry,
        )
        return None, [warning]

    manifest_path = Path(manifest_entry)
    parse_result = parse_manifest_text(
        raw_text=raw_text,
        mod_dir=manifest_path.parent,
        manifest_path=manifest_path,
    )

    warnings = [
        PackageWarning(
            code=warning.code,
            message=warning.message,
            manifest_path=manifest_entry,
        )
        for warning in parse_result.warnings
    ]

    if parse_result.manifest is None:
        return None, warnings

    manifest = parse_result.manifest
    mod_entry = PackageModEntry(
        name=manifest.name,
        unique_id=manifest.unique_id,
        version=manifest.version,
        manifest_path=manifest_entry,
        dependencies=manifest.dependencies,
        update_keys=manifest.update_keys,
    )
    return mod_entry, warnings


def _build_findings(
    mods: list[PackageModEntry],
    warnings: list[PackageWarning],
    too_deep_entries: list[str],
) -> tuple[PackageFinding, ...]:
    findings: list[PackageFinding] = []

    if mods:
        if len(mods) == 1:
            depth = _manifest_depth(mods[0].manifest_path)
            kind = DIRECT_SINGLE_MOD_PACKAGE if depth <= 1 else NESTED_SINGLE_MOD_PACKAGE
            message = (
                "Single mod found at package root layout."
                if kind == DIRECT_SINGLE_MOD_PACKAGE
                else "Single mod found in nested package layout."
            )
            findings.append(
                PackageFinding(
                    kind=kind,
                    message=message,
                    related_paths=(mods[0].manifest_path,),
                )
            )
        else:
            findings.append(
                PackageFinding(
                    kind=MULTI_MOD_PACKAGE,
                    message=f"Package contains {len(mods)} detectable mods.",
                    related_paths=tuple(mod.manifest_path for mod in mods),
                )
            )

        invalid_warning_paths = tuple(
            warning.manifest_path for warning in warnings if warning.code in _INVALID_WARNING_CODES
        )
        if invalid_warning_paths:
            findings.append(
                PackageFinding(
                    kind=INVALID_MANIFEST_PACKAGE,
                    message="Some manifests in package are invalid and were skipped.",
                    related_paths=invalid_warning_paths,
                )
            )

        if too_deep_entries:
            findings.append(
                PackageFinding(
                    kind=TOO_DEEP_UNSUPPORTED_PACKAGE,
                    message="Some manifests are deeper than supported package inspection depth.",
                    related_paths=tuple(too_deep_entries),
                )
            )

        return tuple(findings)

    if any(warning.code in _INVALID_WARNING_CODES for warning in warnings):
        findings.append(
            PackageFinding(
                kind=INVALID_MANIFEST_PACKAGE,
                message="Package has manifest files but none parsed successfully.",
                related_paths=tuple(warning.manifest_path for warning in warnings),
            )
        )

    elif too_deep_entries:
        findings.append(
            PackageFinding(
                kind=TOO_DEEP_UNSUPPORTED_PACKAGE,
                message="Manifest files exist only in unsupported deep paths.",
                related_paths=tuple(too_deep_entries),
            )
        )
    else:
        findings.append(
            PackageFinding(
                kind=NO_USABLE_MANIFEST_FOUND,
                message="No usable manifest.json found in supported package depth.",
                related_paths=tuple(),
            )
        )

    return tuple(findings)


_INVALID_WARNING_CODES = {
    "invalid_manifest",
    "malformed_manifest",
    "manifest_read_error",
}
