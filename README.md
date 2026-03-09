# Stardew Mod Manager

Minimal local-first foundation for scanning a Stardew Valley `Mods` directory.

## Current implemented scope

- Python 3.12 project bootstrap (`pyproject.toml`)
- Core domain models for:
  - app configuration
  - manifests and dependencies
  - scan inventory and findings
- Services for:
  - path validation
  - manifest parsing
  - deterministic Mods directory scanning (top-level + up to two nested levels)
  - relaxed manifest compatibility for BOM and JSON-with-comments/trailing commas
  - `UniqueId` alias support for `UniqueID`
  - local zip package inspection (no installation/extraction into Mods)
  - sandbox-only install preflight and explicit install execution
  - sandbox overwrite preflight/actions with archive-first replacement
  - initial best-effort overwrite recovery semantics (not full transactional rollback)
  - explicit scan-target semantics (configured Mods vs sandbox Mods)
  - explicit sandbox scan context after sandbox install actions
  - conservative destination safety guard that blocks sandbox installs to configured real Mods path
  - metadata/update awareness checks for installed mods (no auto download/install)
  - provider-aware remote requirement guidance (Nexus first) kept separate from manifest dependency blocking
  - configurable local Downloads watcher for new zip intake (no auto install)
  - dependency preflight awareness for installed mods, inspected packages, intake results, and sandbox plans
  - local game environment detection for game path, Mods path, and SMAPI presence
  - persisted operational UI paths (mods/sandbox/archive/downloads/scan target)
  - duplicate `UniqueID` and missing required dependency visibility
  - explicit scan-entry findings (direct, nested container, multi-container, missing/invalid manifest)
  - file-based local app-state config (`JSON`)
- Minimal PySide6 shell for local config and scan inspection
- Fixture-based pytest coverage for Stage 1 scan scenarios
- Minimal dev CLI for local scan runs (`sdvmm-scan`)

## UniqueID comparison policy

- Scanner preserves manifest `UniqueID` exactly as written for display.
- Duplicate detection and dependency matching use canonical comparison keys:
  - `strip()`
  - `casefold()`
- This keeps behavior deterministic when mod IDs differ only by case.

## Out of scope (not implemented)

- SQLite or any persistence layer
- full installer/update/rollback pipeline for real game Mods
- profile switching implementation
- automatic metadata/download actions
- SMAPI diagnostics flows
- unrestricted deep recursive scan
- automatic install into real game Mods directory
- full rollback/archive/history systems

## Metadata notes

- Metadata checks are awareness-only; they do not download or install mods.
- Nexus API key can be configured in the app and persisted in local app-state.
- `SDVMM_NEXUS_API_KEY` remains supported as fallback.
- Manifest dependency preflight is local/package truth for blocking decisions.
- Remote/source-declared requirements are complementary guidance and are non-blocking by default.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
```

## Dev entry points

```bash
.venv/bin/python -m sdvmm /path/to/Mods
.venv/bin/sdvmm-ui
```
