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


def allocate_archive_destination(*, archive_root: Path, target_folder_name: str) -> Path:
    if not archive_root.exists() or not archive_root.is_dir():
        raise ArchiveManagerError(f"Archive path is not accessible: {archive_root}")
    return _build_archive_destination(archive_root=archive_root, target_folder_name=target_folder_name)


def rollback_installed_mod_from_archive(
    *,
    current_mod_path: Path,
    mods_root: Path,
    archive_root: Path,
    archived_candidate_path: Path,
) -> tuple[Path, Path]:
    if not mods_root.exists() or not mods_root.is_dir():
        raise ArchiveManagerError(f"Mods directory is not accessible: {mods_root}")
    if not archive_root.exists() or not archive_root.is_dir():
        raise ArchiveManagerError(f"Archive path is not accessible: {archive_root}")
    if not current_mod_path.exists() or not current_mod_path.is_dir():
        raise ArchiveManagerError(f"Current installed mod folder is not accessible: {current_mod_path}")
    if not archived_candidate_path.exists() or not archived_candidate_path.is_dir():
        raise ArchiveManagerError(f"Archived rollback folder is not accessible: {archived_candidate_path}")

    mods_root_resolved = mods_root.resolve()
    current_resolved = current_mod_path.resolve()
    archive_root_resolved = archive_root.resolve()
    candidate_resolved = archived_candidate_path.resolve()

    if current_resolved.parent != mods_root_resolved:
        raise ArchiveManagerError(
            "Current mod folder must be a direct child of the selected Mods destination."
        )
    if candidate_resolved.parent != archive_root_resolved:
        raise ArchiveManagerError(
            "Archived rollback folder must be a direct child of the selected archive root."
        )

    current_archive_path = _build_archive_destination(
        archive_root=archive_root,
        target_folder_name=current_mod_path.name,
    )

    try:
        current_mod_path.rename(current_archive_path)
    except Exception as exc:
        raise ArchiveManagerError(
            f"Could not archive current installed mod before rollback: "
            f"{current_mod_path} -> {current_archive_path}: {exc}"
        ) from exc

    try:
        archived_candidate_path.rename(current_mod_path)
    except Exception as rollback_exc:
        recovered = False
        recovery_error: str | None = None
        try:
            current_archive_path.rename(current_mod_path)
            recovered = True
        except Exception as restore_exc:
            recovery_error = str(restore_exc)

        if recovered:
            raise ArchiveManagerError(
                "Rollback restore failed after archiving current mod. "
                "Best-effort recovery restored original installed folder. "
                f"Restore error: {rollback_exc}"
            ) from rollback_exc

        detail = f"; recovery failed: {recovery_error}" if recovery_error else ""
        raise ArchiveManagerError(
            "Rollback restore failed after archiving current mod and best-effort recovery "
            f"could not restore original folder. Restore error: {rollback_exc}{detail}"
        ) from rollback_exc

    return current_archive_path, current_mod_path


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


def _build_archive_destination(archive_root: Path, target_folder_name: str) -> Path:
    for idx in range(1, 10_000):
        candidate = archive_root / f"{target_folder_name}__sdvmm_archive_{idx:03d}"
        if not candidate.exists():
            return candidate

    raise ArchiveManagerError(
        f"Could not allocate archive path for target '{target_folder_name}' under {archive_root}."
    )
