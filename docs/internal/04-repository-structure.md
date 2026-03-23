# Repository Structure

## Current folders

- `docs/`
  - product and architecture notes
  - roadmap
  - external-audit brief
- `src/sdvmm/`
  - application package
- `tests/unit/`
  - regression and service-layer tests
- `.codex/`
  - local Codex app metadata, not part of product code

## Current source layout

### `src/sdvmm/app/`

- app bootstrap
- shell service orchestration
- path helpers
- table filter helpers
- inventory presentation helpers

### `src/sdvmm/domain/`

- immutable domain models
- literal code files for install, update, package, dependency, and related workflow states

### `src/sdvmm/services/`

- file-backed app state
- mod scanning
- package inspection
- downloads intake
- dependency preflight
- install execution
- remote requirement handling
- update metadata
- environment detection

### `src/sdvmm/ui/`

- `main_window.py` as the primary workflow integration surface
- extracted composition helpers for:
  - top context
  - setup configuration
  - discovery tab
  - archive tab
  - global status strip
  - bottom details region
  - plan/install tab surface

## Current test layout

### `tests/unit/`

High-signal files include:

- `test_main_window_gui_regression.py`
- `test_app_shell_service.py`
- `test_app_state_store.py`
- `test_update_metadata.py`
- `test_downloads_intake.py`
- `test_remote_requirements.py`

The repository currently relies on unit/regression coverage plus offscreen UI smoke checks. There is no separate `tests/integration/` tree yet.

## Notable current realities

- The repository is no longer an empty placeholder structure; earlier docs that describe it that way are obsolete.
- There is no database layer or `infra/` subtree today.
- Persistence is currently file-backed.
- `MainWindow` remains large, by design, because product-facing workflow completion has been prioritized over continued extraction.

## Expected near-term additions

- `docs/` may gain more current-state and release-readiness notes
- `scripts/` would be justified for canonical local run/smoke commands
- CI config will eventually be needed for public-release hardening

## What should remain out of version control

- temporary artifacts
- local snapshots
- generated archives
- test outputs
- local Codex metadata not intended as product source
