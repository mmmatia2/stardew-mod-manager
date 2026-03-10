from __future__ import annotations

from pathlib import Path
import re

from sdvmm.domain.models import ArchivedModEntry
from sdvmm.services.manifest_parser import parse_manifest_file

_ARCHIVE_SUFFIX_PATTERN = re.compile(r"^(?P<target>.+)__sdvmm_archive_[0-9]{3}$")


class ArchiveManagerError(ValueError):
    """Raised when archive listing or restore cannot proceed safely."""


def list_archived_mod_entries(
    *,
    archive_root: Path,
    source_kind: str,
) -> tuple[ArchivedModEntry, ...]:
    if not archive_root.exists():
        return tuple()
    if not archive_root.is_dir():
        raise ArchiveManagerError(f"Archive path is not a directory: {archive_root}")

    entries: list[ArchivedModEntry] = []
    for candidate in sorted(archive_root.iterdir(), key=lambda path: path.name.lower()):
        if not candidate.is_dir():
            continue
        entries.append(
            _build_archived_entry(
                archive_root=archive_root,
                archived_path=candidate,
                source_kind=source_kind,
            )
        )

    return tuple(entries)


def restore_archived_mod_entry(
    *,
    archive_root: Path,
    archived_path: Path,
    destination_mods_root: Path,
    destination_folder_name: str,
) -> Path:
    if not destination_mods_root.exists() or not destination_mods_root.is_dir():
        raise ArchiveManagerError(f"Mods directory is not accessible: {destination_mods_root}")
    if not archive_root.exists() or not archive_root.is_dir():
        raise ArchiveManagerError(f"Archive path is not accessible: {archive_root}")

    archived_resolved = archived_path.resolve()
    archive_root_resolved = archive_root.resolve()
    if archived_resolved.parent != archive_root_resolved:
        raise ArchiveManagerError(
            "Archived entry must be a direct child of the selected archive root."
        )
    if not archived_path.exists() or not archived_path.is_dir():
        raise ArchiveManagerError(f"Archived entry is not accessible: {archived_path}")

    target_name = destination_folder_name.strip()
    if not target_name:
        raise ArchiveManagerError("Restore target folder name is required.")

    destination_target = destination_mods_root / target_name
    if destination_target.exists():
        raise ArchiveManagerError(
            f"Restore target already exists in destination Mods directory: {destination_target}"
        )

    archived_path.rename(destination_target)
    return destination_target


def _build_archived_entry(
    *,
    archive_root: Path,
    archived_path: Path,
    source_kind: str,
) -> ArchivedModEntry:
    target_folder_name = _derive_target_folder_name(archived_path.name)
    mod_name: str | None = None
    unique_id: str | None = None
    version: str | None = None
    note: str | None = None

    manifest_path = archived_path / "manifest.json"
    if manifest_path.exists():
        try:
            parse_result = parse_manifest_file(manifest_path=manifest_path, mod_dir=archived_path)
        except OSError as exc:
            note = f"Could not read manifest summary: {exc}"
        else:
            if parse_result.manifest is not None:
                mod_name = parse_result.manifest.name
                unique_id = parse_result.manifest.unique_id
                version = parse_result.manifest.version
            if parse_result.warnings and note is None:
                warning = parse_result.warnings[0]
                note = f"[{warning.code}] {warning.message}"
    else:
        note = "No top-level manifest.json found in archived folder."

    return ArchivedModEntry(
        source_kind=source_kind,
        archive_root=archive_root,
        archived_path=archived_path,
        archived_folder_name=archived_path.name,
        target_folder_name=target_folder_name,
        mod_name=mod_name,
        unique_id=unique_id,
        version=version,
        note=note,
    )


def _derive_target_folder_name(archived_folder_name: str) -> str:
    match = _ARCHIVE_SUFFIX_PATTERN.match(archived_folder_name)
    if match is None:
        return archived_folder_name

    return match.group("target")
