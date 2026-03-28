from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

from sdvmm.domain.models import SmapiLogFinding, SmapiLogReport
from sdvmm.domain.smapi_log_codes import (
    SMAPI_LOG_ERROR,
    SMAPI_LOG_FAILED_MOD,
    SMAPI_LOG_MISSING_DEPENDENCY,
    SMAPI_LOG_NOT_FOUND,
    SMAPI_LOG_PARSED,
    SMAPI_LOG_RUNTIME_ISSUE,
    SMAPI_LOG_SOURCE_AUTO_DETECTED,
    SMAPI_LOG_SOURCE_MANUAL,
    SMAPI_LOG_SOURCE_NONE,
    SMAPI_LOG_UNABLE_TO_DETERMINE,
    SMAPI_LOG_WARNING,
)

_EXPECTED_LOG_FILENAMES = (
    "SMAPI-latest.txt",
    "SMAPI-crash.txt",
    "SMAPI-crash.previous.txt",
)
_MISSING_DEPENDENCY_PATTERNS = (
    "because it needs",
    "missing dependencies",
    "requires mods which aren't installed",
    "requires these mods",
    "which aren't installed",
)
_RUNTIME_ISSUE_PATTERNS = (
    "unhandled exception",
    "nullreferenceexception",
    "typeloadexception",
    "missingmethodexception",
    "could not load file or assembly",
    "steamapi_init() failed",
    "failed to initialize",
    "game has crashed",
)
_SKIPPED_MOD_BULLET_RE = re.compile(
    r"^\s*(?:\[SMAPI\]\s*)?-\s*(?P<name>.+?)\s+because(?P<reason>.*)$",
    re.IGNORECASE,
)
_FAILED_TO_LOAD_RE = re.compile(
    r"^\s*(?:\[SMAPI\]\s*)?(?P<name>.+?)\s+failed to load\b(?P<reason>.*)$",
    re.IGNORECASE,
)
_DEPENDENCY_ID_RE = re.compile(r"\b[A-Za-z0-9_.-]+\.[A-Za-z0-9_.-]+\b")
_MAX_FINDINGS_PER_KIND = 120


def check_smapi_log_troubleshooting(
    *,
    game_path: Path | None,
    manual_log_path: Path | None = None,
) -> SmapiLogReport:
    if manual_log_path is not None:
        return parse_smapi_log_file(
            manual_log_path,
            source=SMAPI_LOG_SOURCE_MANUAL,
            game_path=game_path,
        )

    auto_path = locate_smapi_log(game_path=game_path)
    if auto_path is None:
        return SmapiLogReport(
            state=SMAPI_LOG_NOT_FOUND,
            source=SMAPI_LOG_SOURCE_NONE,
            log_path=None,
            game_path=game_path,
            findings=tuple(),
            notes=(
                "No SMAPI log was found in supported default locations.",
                "Use 'Load SMAPI log' to inspect a specific file manually.",
            ),
            message="SMAPI log not found.",
        )

    return parse_smapi_log_file(
        auto_path,
        source=SMAPI_LOG_SOURCE_AUTO_DETECTED,
        game_path=game_path,
    )


def locate_smapi_log(*, game_path: Path | None) -> Path | None:
    directories = _candidate_log_directories(game_path=game_path)
    for directory in directories:
        expected = _find_expected_log(directory)
        if expected is not None:
            return expected

    candidates: list[Path] = []
    for directory in directories:
        if not directory.exists() or not directory.is_dir():
            continue
        for child in directory.iterdir():
            if not child.is_file():
                continue
            name = child.name.casefold()
            if "smapi" not in name or not name.endswith(".txt"):
                continue
            candidates.append(child)

    if not candidates:
        return None

    candidates.sort(
        key=lambda path: (path.stat().st_mtime, path.name.casefold()),
        reverse=True,
    )
    return candidates[0]


def parse_smapi_log_file(
    log_path: Path,
    *,
    source: str,
    game_path: Path | None,
) -> SmapiLogReport:
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return SmapiLogReport(
            state=SMAPI_LOG_UNABLE_TO_DETERMINE,
            source=source,
            log_path=log_path,
            game_path=game_path,
            findings=tuple(),
            notes=(f"Could not read SMAPI log file: {exc}",),
            message="SMAPI log could not be read.",
        )

    return parse_smapi_log_text(
        text,
        log_path=log_path,
        source=source,
        game_path=game_path,
    )


def parse_smapi_log_text(
    text: str,
    *,
    log_path: Path | None,
    source: str,
    game_path: Path | None,
) -> SmapiLogReport:
    lines = text.splitlines()
    if not lines:
        return SmapiLogReport(
            state=SMAPI_LOG_UNABLE_TO_DETERMINE,
            source=source,
            log_path=log_path,
            game_path=game_path,
            findings=tuple(),
            notes=("SMAPI log is empty.",),
            message="SMAPI log is empty; unable to determine troubleshooting status.",
        )

    findings: list[SmapiLogFinding] = []
    counts_by_kind: dict[str, int] = {}
    in_skipped_mods_block = False

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            in_skipped_mods_block = False
            continue

        lowered = line.casefold()

        if "skipped mods" in lowered:
            in_skipped_mods_block = True

        if "[error" in lowered or "[fatal" in lowered:
            _append_finding(
                findings=findings,
                counts_by_kind=counts_by_kind,
                kind=SMAPI_LOG_ERROR,
                line_number=line_number,
                message=_compact_log_line(line),
            )
        if "[warn" in lowered:
            _append_finding(
                findings=findings,
                counts_by_kind=counts_by_kind,
                kind=SMAPI_LOG_WARNING,
                line_number=line_number,
                message=_compact_log_line(line),
            )

        skipped_mod_match = _SKIPPED_MOD_BULLET_RE.match(line)
        if in_skipped_mods_block and skipped_mod_match is not None:
            mod_name = skipped_mod_match.group("name").strip()
            reason = skipped_mod_match.group("reason").strip(" :")
            message = f"{mod_name}: {reason}" if reason else mod_name
            _append_finding(
                findings=findings,
                counts_by_kind=counts_by_kind,
                kind=SMAPI_LOG_FAILED_MOD,
                line_number=line_number,
                message=message,
            )
            _append_missing_dependency_from_line(
                findings=findings,
                counts_by_kind=counts_by_kind,
                line_number=line_number,
                line=line,
            )
            continue

        failed_to_load_match = _FAILED_TO_LOAD_RE.match(line)
        if failed_to_load_match is not None:
            mod_name = failed_to_load_match.group("name").strip()
            reason = failed_to_load_match.group("reason").strip(" :")
            message = f"{mod_name}: failed to load"
            if reason:
                message = f"{message} ({reason})"
            _append_finding(
                findings=findings,
                counts_by_kind=counts_by_kind,
                kind=SMAPI_LOG_FAILED_MOD,
                line_number=line_number,
                message=message,
            )

        _append_missing_dependency_from_line(
            findings=findings,
            counts_by_kind=counts_by_kind,
            line_number=line_number,
            line=line,
        )

        if any(keyword in lowered for keyword in _RUNTIME_ISSUE_PATTERNS):
            _append_finding(
                findings=findings,
                counts_by_kind=counts_by_kind,
                kind=SMAPI_LOG_RUNTIME_ISSUE,
                line_number=line_number,
                message=_compact_log_line(line),
            )

    notes: list[str] = []
    if not findings:
        notes.append(
            "No clear errors/warnings/issues were parsed from this log. That does not guarantee the run was healthy."
        )

    summary = _build_summary_message(findings)
    return SmapiLogReport(
        state=SMAPI_LOG_PARSED,
        source=source,
        log_path=log_path,
        game_path=game_path,
        findings=tuple(findings),
        notes=tuple(notes),
        message=summary,
    )


def _candidate_log_directories(*, game_path: Path | None) -> tuple[Path, ...]:
    directories: list[Path] = []
    if game_path is not None:
        directories.append(game_path / "ErrorLogs")

    appdata_raw = os.getenv("APPDATA", "").strip()
    if appdata_raw:
        directories.append(Path(appdata_raw).expanduser() / "StardewValley" / "ErrorLogs")

    local_appdata_raw = os.getenv("LOCALAPPDATA", "").strip()
    if local_appdata_raw:
        directories.append(Path(local_appdata_raw).expanduser() / "StardewValley" / "ErrorLogs")

    xdg_config_home_raw = os.getenv("XDG_CONFIG_HOME", "").strip()
    if xdg_config_home_raw:
        directories.append(Path(xdg_config_home_raw).expanduser() / "StardewValley" / "ErrorLogs")

    home_dir = Path.home()
    directories.append(home_dir / ".config" / "StardewValley" / "ErrorLogs")

    deduped: list[Path] = []
    seen: set[str] = set()
    for directory in directories:
        key = str(directory.expanduser().resolve(strict=False))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(directory)
    return tuple(deduped)


def _find_expected_log(directory: Path) -> Path | None:
    if not directory.exists() or not directory.is_dir():
        return None

    by_name = {child.name.casefold(): child for child in directory.iterdir() if child.is_file()}
    for expected_name in _EXPECTED_LOG_FILENAMES:
        match = by_name.get(expected_name.casefold())
        if match is not None:
            return match
    return None


def _append_missing_dependency_from_line(
    *,
    findings: list[SmapiLogFinding],
    counts_by_kind: dict[str, int],
    line_number: int,
    line: str,
) -> None:
    lowered = line.casefold()
    if not any(pattern in lowered for pattern in _MISSING_DEPENDENCY_PATTERNS):
        return

    dependency_ids = _extract_dependency_ids(line)
    if dependency_ids:
        message = f"{_compact_log_line(line)} | detected IDs: {', '.join(dependency_ids)}"
    else:
        message = _compact_log_line(line)
    _append_finding(
        findings=findings,
        counts_by_kind=counts_by_kind,
        kind=SMAPI_LOG_MISSING_DEPENDENCY,
        line_number=line_number,
        message=message,
    )


def _extract_dependency_ids(line: str) -> tuple[str, ...]:
    ids = {
        match.group(0)
        for match in _DEPENDENCY_ID_RE.finditer(line)
    }
    if not ids:
        return tuple()
    return tuple(sorted(ids, key=str.casefold))


def _append_finding(
    *,
    findings: list[SmapiLogFinding],
    counts_by_kind: dict[str, int],
    kind: str,
    line_number: int,
    message: str,
) -> None:
    current_count = counts_by_kind.get(kind, 0)
    if current_count >= _MAX_FINDINGS_PER_KIND:
        return

    counts_by_kind[kind] = current_count + 1
    findings.append(
        SmapiLogFinding(
            kind=kind,
            line_number=line_number,
            message=message,
        )
    )


def _build_summary_message(findings: Iterable[SmapiLogFinding]) -> str:
    counts = {
        SMAPI_LOG_ERROR: 0,
        SMAPI_LOG_WARNING: 0,
        SMAPI_LOG_FAILED_MOD: 0,
        SMAPI_LOG_MISSING_DEPENDENCY: 0,
        SMAPI_LOG_RUNTIME_ISSUE: 0,
    }
    for finding in findings:
        counts[finding.kind] = counts.get(finding.kind, 0) + 1

    return (
        "Parsed SMAPI log: "
        f"errors={counts[SMAPI_LOG_ERROR]}, "
        f"warnings={counts[SMAPI_LOG_WARNING]}, "
        f"failed_mods={counts[SMAPI_LOG_FAILED_MOD]}, "
        f"missing_dependencies={counts[SMAPI_LOG_MISSING_DEPENDENCY]}, "
        f"runtime_issues={counts[SMAPI_LOG_RUNTIME_ISSUE]}."
    )


def _compact_log_line(line: str, *, max_length: int = 280) -> str:
    compact = " ".join(line.split())
    if len(compact) <= max_length:
        return compact
    return f"{compact[: max_length - 3]}..."
