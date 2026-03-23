# Architecture Note

## Current stack decision

### Recommendation

Keep the current stack:

- Python 3.12
- PySide6
- file-based local persistence
- `pytest`

### Why this is still the right choice

- The product is dominated by local filesystem, archive, manifest, install, and recovery workflows.
- Python handles that problem space well with low ceremony.
- PySide6 is mature enough for a desktop utility app without introducing a browser-shell architecture.
- File-backed persistence is currently sufficient for config, install history, and recovery history.
- There is still no concrete product need that justifies a database.

### Explicit non-decision

Do not introduce:

- a database
- a browser-based desktop shell
- a split frontend/backend architecture

unless a later roadmap phase produces a concrete product need.

## Current module boundaries

- `app`
  - bootstrap, app wiring, orchestration helpers, shell service
- `domain`
  - immutable data contracts and literal code sets
- `services`
  - scan, package inspection, intake, dependency preflight, install execution, update metadata, persistence
- `ui`
  - Qt surfaces and workflow composition

These boundaries are intentionally boring. The domain layer stays UI-agnostic, and Qt is not supposed to be the source of truth for workflow policy.

## Current architectural strengths

- Immutable `@dataclass(frozen=True, slots=True)` domain models
- Clear `AppShellService` workflow boundary for install/recovery logic
- Safe-by-default install review contract
- Recorded install and recovery history with stable IDs
- Recovery derivation and live review below the UI
- Strong GUI regression coverage for `MainWindow`

## Current architectural risks

### 1. `MainWindow` remains a dense integration point

`MainWindow` still coordinates:

- selected-row guidance
- tab-local outputs
- intake staging
- plan/review summary/explanation/facts
- recovery selector state
- update-source diagnostics presentation

This is acceptable for now because product-facing workflow completion has been prioritized over more decomposition, but it remains the most likely place for UX wiring regressions.

### 2. Some diagnostics are still inferred too close to the UI

The current roadmap needs to promote update-source diagnostics into a typed contract below the UI instead of inferring them from user-facing strings.

That promotion is the next important architecture move because it reduces one of the few remaining brittle seams.

### 3. The app has multiple information surfaces

The current UX uses:

- global status strip
- tab-local output boxes
- selected-row guidance
- structured review summaries/facts
- a legacy bottom details region

This is workable, but it must be consolidated later once the current workflow semantics stop moving.

## Persistence model

The app currently uses file-backed local state, not a database.

Current persisted concerns include:

- app configuration
- install operation history
- recovery execution history

This is the right current tradeoff:

- local-first
- inspectable
- low operational complexity

The main future risk is schema evolution and migration discipline, not query complexity.

## Current install/update/recovery model

### Install

1. User selects or stages a local package.
2. The app builds an install plan.
3. The app reviews that plan for execution safety.
4. Sandbox is the recommended path.
5. Real Mods execution requires explicit confirmation.
6. Install execution records operation history.

### Recovery

1. Recovery plan is derived from recorded install history.
2. Recovery plan is reviewed against the current filesystem.
3. Recovery execution runs only from an allowed review.
4. Recovery execution is recorded separately and linked to the originating install operation when possible.

### Update checks

1. Update checks are awareness-only.
2. The app may use approved metadata providers to compare versions.
3. The app does not download archives automatically.
4. The user remains in control of the browser/download step.

## Architectural guidance for the next phases

- Prefer promoting typed diagnostics below the UI before adding more UI-specific explanation layers.
- Prefer product-facing workflow completion over broad extraction work.
- Do not remove narrative output boxes until structured UI surfaces have clearly replaced their user-facing value.
- Defer broad UI/UX consolidation until update-source diagnostics and remaining workflow semantics stabilize.
