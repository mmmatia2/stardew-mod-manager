# AI Audit Brief

## Purpose

This brief is for an external AI model to audit the current repository state, challenge the roadmap, and suggest the next highest-value product and architecture moves.

The goal is not to restate the whole codebase. The goal is to give enough high-signal context that another model can:

- assess current product maturity
- identify weak spots in architecture and UX
- challenge the roadmap ordering
- suggest missing risks, gaps, or simplifications

## Repository Snapshot

- Repository: `stardew-mod-manager`
- Platform: Python 3.12 + PySide6 desktop app
- Entry point: `sdvmm-ui` -> [`src/sdvmm/app/main.py`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/app/main.py)
- Current validation baseline:
  - `.\.venv\Scripts\python.exe -m pytest tests\unit -q`
  - latest verified result in this thread: `415 passed, 1 skipped`
  - UI startup smoke also passes offscreen
- Product posture:
  - local-first
  - safe-by-default
  - reversible where possible
  - sandbox remains the recommended path
  - no scraping, no browser automation, no premium-bypass behavior

## Current Product Shape

The app is no longer just a scanner. It now has a coherent local workflow:

1. scan installed mods
2. check update metadata
3. open the selected mod's remote page manually
4. download zip manually
5. intake/inspect detected zips
6. stage a package into `Plan & Install`
7. build an install plan
8. review/confirm execution
9. record install history
10. derive/review/execute recovery
11. inspect linked recovery history
12. launch Stardew/SMAPI against sandbox Mods only
13. sync selected real Mods into sandbox Mods
14. promote selected sandbox Mods into real Mods through an explicit managed flow

The product is not feature-complete for public release, but it is materially beyond prototype state.

The near-term product direction now explicitly includes a mod-development workflow, not only general end-user mod management.

## Current Architecture

### High-level layers

- Domain models and codes:
  - [`src/sdvmm/domain/models.py`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/domain/models.py)
  - `*_codes.py` files under [`src/sdvmm/domain`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/domain)
- App/service orchestration:
  - [`src/sdvmm/app/shell_service.py`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/app/shell_service.py)
- Persistence:
  - [`src/sdvmm/services/app_state_store.py`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/services/app_state_store.py)
- UI shell:
  - [`src/sdvmm/ui/main_window.py`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/ui/main_window.py)
  - composed helper surfaces under [`src/sdvmm/ui`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/ui)

### Architectural direction

The current architecture intentionally keeps:

- policy and execution logic in app/service/domain layers
- Qt as a consumer of service contracts, not the source of truth
- install/recovery safety semantics below the UI
- local file-based persistence instead of a database

### Main seams that matter now

- `MainWindow` is still the largest integration surface and the main UX composition point
- `AppShellService` is the workflow backbone
- install and recovery history are file-backed, versioned, and now include stable IDs
- sandbox dev-loop trust now depends heavily on `AppShellService` path validation and live-write policy

## Current Strengths

### Install / recovery workflow

The strongest part of the app right now is the install/recovery foundation:

- install execution review contract exists
- explicit approval is required for real Mods execution
- install operations are recorded
- recovery plans can be derived from install history
- recovery plans can be reviewed against live filesystem state
- reviewed recovery plans can be executed
- recovery execution is recorded
- install and recovery records have stable IDs
- UI can inspect and execute recovery in a narrow, guarded flow

### Workflow continuity

The previously fragmented workflow has been tightened:

- `Packages & Intake` stages into `Plan & Install`
- `Plan & Install` owns planning/review/execution
- recovery is local to the same workflow surface
- install completion now links back into recovery selection
- sandbox launch/sync/promotion now make the app directly useful for mod-development iteration, not just mod curation

### UI composition progress

The app has already corrected several structural UI mistakes:

- primary controls were moved out of the bottom detail area
- setup/configuration now lives in the main workspace instead of the bottom panel
- the bottom area is now output-only

The UI is still dense, but further generic decomposition is no longer the highest-value track.

## Current Weak Spots

### 1. Sandbox promotion policy is intentionally conservative

The product now has explicit:

- sandbox-only launch
- selected `real -> sandbox` sync
- selected `sandbox -> real` promotion

The remaining question is not whether the dev loop exists. It is how far to extend ergonomics without weakening trust semantics.

Current behavior is intentionally conservative:

- preview/review before live writes
- archive-aware replace for conflicts
- no blind overwrite
- archive/recovery trust preserved for real writes

The next unresolved product question is:

> How should the app improve promotion speed and clarity now that preview + archive-aware replace already exists, without making live promotion feel casual or opaque?

### 2. `MainWindow` is still the densest integration point

The app has improved ownership boundaries, but `MainWindow` still carries substantial UI workflow logic and cross-surface coordination.

This is acceptable for now because product-facing workflow completion was correctly prioritized, but it remains a maintenance risk.

### 3. Desktop interaction density is improved, not solved

The app is cleaner than before, but workflow surfaces are still dense. This is now a secondary concern behind sandbox dev-loop trust and live-write clarity.

### 4. Public-release readiness work has barely started

Notably still pending:

- packaging/installer strategy
- code signing strategy
- release docs
- contributor run scripts / simpler launch ergonomics
- CI/release hardening
- migration discipline for public users

## Roadmap Status

### Completed or effectively closed

#### 1. Core Workflow Foundation

- scanning
- package inspection
- install planning and execution review
- sandbox install execution
- real-Mods guarded execution
- install history
- recovery derivation/review/execution
- recovery history with stable IDs

#### 2. Guided Manual Update Flow

- selected update row -> remote page
- manual download -> intake
- intake staging -> `Plan & Install`
- local workflow output in owning tabs

#### 3. Managed Live Mods Safety Baseline

- persistent live-destination safety panel
- explicit confirmation for real Mods execution
- real-Mods messaging now visible before execution

#### 4. History / Recovery UX Baseline

- readable recovery selector
- newest-first presentation
- linked recovery outcomes
- filterable recovery selector
- safer/no-ID legacy handling

### In progress

#### 5. Sandbox Dev Loop Foundation

Already completed or effectively implemented:

- sandbox-only SMAPI dev launch
- selected `real -> sandbox` sync
- selected `sandbox -> real` managed promotion
- promotion preview/review + archive-aware replace conflict handling
- partial-failure safety handling for archive-aware promotion paths

Current recommendation:

- continue with the next smallest ergonomics increment (orientation and reduced friction)
- preserve explicit confirmation and recovery trust semantics as non-negotiable

### Next likely phase

#### 6. Sandbox Dev Loop Ergonomics

This phase should determine which one small improvement matters most:

- open sandbox / real Mods convenience actions
- auto-rescan / destination-focus after sync or promotion
- clearer promotion preview orientation for multi-mod operations

### Later planned phase

#### 7. Information Architecture Follow-up

The UI simplification track is now intentionally paused until sandbox-dev workflow trust work is no longer the main blocker.

#### 8. Visual Feedback and Polish

This phase should happen after the IA simplification decisions are made, not before.

## Current UX/Product Concerns Worth Challenging

An external model should specifically challenge these points:

### A. Is the current roadmap still in the right order?

The current recommendation is to keep the sandbox dev-loop track ahead of more generic UX consolidation.

Question:

> Is it correct to keep sandbox launch/sync/promotion ergonomics ahead of more UI consolidation and polish?

### B. Should live promotion stay conservative longer?

Question:

> How conservative should `sandbox -> real` remain now that preview/archive-aware replace exists, and what safeguards should be added before any faster promotion path is considered?

### C. What should remain global vs tab-local?

The app now has:

- a global status strip
- tab-local workflow surfaces
- selected-row guidance in `Inventory`
- a bottom detailed-output surface

Question:

> Which of these should remain, collapse, or be retired?

### D. What is the next best sandbox-dev ergonomics increment?

Question:

> Given that the intended near-term audience includes mod developers, what sequence best balances trust and speed: preview + archive-aware replace first, open-folder conveniences second, and broader compare/launch conveniences later?

## Explicit Constraints for the External Audit

The external audit should respect these repository/product constraints:

- no database unless there is a concrete product need
- no scraping or browser automation for downloads
- no premium-bypass behavior
- sandbox remains the recommended path until live flows are fully validated
- destructive or live-Mods operations require archive/recovery semantics
- product-facing workflow completion is favored over refactor churn
- real->sandbox and sandbox->real are intentionally asymmetric workflows

## Recommended Files To Read First

1. [`AGENTS.md`](/Users/darth/Projects/stardew-mod-manager/AGENTS.md)
2. [`README.md`](/Users/darth/Projects/stardew-mod-manager/README.md)
3. [`src/sdvmm/app/shell_service.py`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/app/shell_service.py)
4. [`src/sdvmm/domain/models.py`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/domain/models.py)
5. [`src/sdvmm/services/app_state_store.py`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/services/app_state_store.py)
6. [`src/sdvmm/ui/main_window.py`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/ui/main_window.py)
7. [`src/sdvmm/ui/plan_install_tab_surface.py`](/Users/darth/Projects/stardew-mod-manager/src/sdvmm/ui/plan_install_tab_surface.py)
8. [`tests/unit/test_main_window_gui_regression.py`](/Users/darth/Projects/stardew-mod-manager/tests/unit/test_main_window_gui_regression.py)
9. [`tests/unit/test_app_shell_service.py`](/Users/darth/Projects/stardew-mod-manager/tests/unit/test_app_shell_service.py)
10. [`tests/unit/test_app_state_store.py`](/Users/darth/Projects/stardew-mod-manager/tests/unit/test_app_state_store.py)

## What a Useful External Audit Should Produce

A useful audit response should include:

- architecture risks ordered by severity
- roadmap-order challenges, if any
- whether the sandbox dev-loop track is correctly prioritized
- how preview + archive-aware replace should be introduced without weakening live-write trust
- concrete suggestions for improving sandbox-dev ergonomics without weakening real-Mods safety
- criteria for when the app is ready to resume later UI/UX consolidation work
- the next 3-5 smallest safe increments, ordered by product value
