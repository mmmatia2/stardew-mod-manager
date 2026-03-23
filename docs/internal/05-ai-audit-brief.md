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
  - latest verified result in this thread: `526 passed, 1 skipped`
  - UI startup smoke also passes offscreen
- Shipped baseline in this brief: `1.1.0` (the first post-v1 workflow expansion, including compare follow-up ergonomics on top of the stable `1.0.0` baseline: actionable drift default, compare category filtering, inline category explanation, and copy mod name / UniqueID convenience)
- Product posture:
  - local-first
  - safe-by-default
  - reversible where possible
  - sandbox remains the recommended path
  - no scraping, no browser automation, no premium-bypass behavior
  - strongest near-term lane is safe local workflow, dev-loop trust, and migration trust
  - not aiming to become a one-click downloader or broad profile manager in the near term

## Current Product Shape

The app is no longer just a scanner. It now has a coherent local workflow:

1. scan installed mods
2. check update metadata
3. open the selected mod's remote page manually
4. download zip manually
5. choose one or more zip packages for intake
6. inspect selected packages immediately
7. let the current valid package become the Review target automatically, or choose one when multiple valid packages exist
8. review current package and destination
9. review/confirm execution
10. record install history
11. derive/review/execute recovery
12. inspect linked recovery history
13. launch Stardew/SMAPI against sandbox Mods only
14. sync selected real Mods into sandbox Mods
15. promote selected sandbox Mods into real Mods through an explicit managed flow
16. compare configured real Mods vs sandbox Mods in a dedicated drift view before sync/promotion decisions

The product is now at its first stable user-facing release baseline, while still intentionally leaving some post-v1 areas unfinished.

The product direction now explicitly includes a mod-development workflow, not only general end-user mod management.
The shipped `1.1.0` build includes the `1.0.0` baseline plus the first compare follow-up pass: actionable drift default, compare category filtering, inline explanation for compare states, and copy mod name / UniqueID convenience, while intentionally stopping short of compare-driven write shortcuts, blind multi-package planning/install behavior, file-level merge restore behavior, and background Steam management.

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

- `Packages` now starts intake/inspection directly for the normal zip-install path
- `Packages` can inspect multiple selected zips while preserving per-package visibility
- watcher intake can monitor two configured paths into the same detected-packages flow
- `Review` owns install review/execution
- `Recovery` is now its own dedicated workflow surface
- install completion now links back into recovery selection
- sandbox launch/sync/promotion now make the app directly useful for mod-development iteration, not just mod curation

### UI composition progress

The app has already corrected several structural UI mistakes:

- shared bottom console-style output is gone
- the old left-side `Current detail` panel is also gone
- setup/configuration now lives in the main workspace
- local detail panels are now hidden until they have useful content
- sparse tabs (`Compare`, `Archive`, `Recovery`) have been compacted to reduce empty-state drift

The UI is still dense, but further generic decomposition is no longer the highest-value track.

## Current Weak Spots

### 1. Backup / restore / migration foundation is now coherent but still intentionally review-first

State is durable and atomic, and the app now has explicit config-aware backup export, folder/zip bundle compatibility, bundle inspection, restore/import planning, restore/import execution for clearly missing content, and reviewed conflict handling through archive-aware mod-folder replacement, but file-level merge restore ergonomics are not yet established.

The next question is:

> When, if ever, should restore/import move beyond archive-aware folder replacement into file-level merge behavior?

### 2. Sandbox promotion policy is intentionally conservative

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

The next unresolved product question remains:

> How should the app improve promotion speed and clarity now that preview + archive-aware replace already exists, without making live promotion feel casual or opaque?

### 3. Compare is now a stronger read-only drift surface, but still intentionally constrained

The app now has actionable-drift-first compare defaults, category filtering, inline category explanation, and compare-row copy convenience. The remaining question is how much further compare should go without turning into an implicit write surface.

The next question is:

> What compare improvements, if any, are still worth doing after `1.1.0` without creating compare-driven write shortcuts?

### 4. `MainWindow` is still the densest integration point

The app has improved ownership boundaries, but `MainWindow` still carries substantial UI workflow logic and cross-surface coordination.

This is acceptable for now because product-facing workflow completion was correctly prioritized, but it remains a maintenance risk.

### 5. Desktop interaction density is improved, not solved

The app is cleaner than before, but workflow surfaces are still dense. The most likely post-v1 UI work is no longer general shell renaming; it is compact empty states, clearer launch ownership, and reducing the remaining “form-heavy” feel in high-frequency tabs.

### 6. Public-release readiness work has barely started

Notably still pending:

- packaging/installer strategy
- code signing strategy
- release docs
- contributor run scripts / simpler launch ergonomics
- CI/release hardening
- migration discipline for public users

### 7. Multi-package planning is intentionally not solved yet

The app can now inspect multiple zip files in one explicit batch, and the normal single-package path is much more direct than before, but it still does not build or execute a true multi-package install plan.

That limitation is intentional:

- per-package inspection is already useful for private testing and download triage
- the current planner remains clearer and safer when reviewing exactly one chosen package at a time
- pushing straight into batch execution now would create review ambiguity

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
- intake -> `Review`
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

### Recently completed

#### 5. Sandbox Dev Loop Foundation

Already completed or effectively implemented:

- sandbox-only SMAPI dev launch
- selected `real -> sandbox` sync
- selected `sandbox -> real` managed promotion
- promotion preview/review + archive-aware replace conflict handling
- partial-failure safety handling for archive-aware promotion paths

#### 6. Multi-Zip Intake + Second Watcher Path Baseline

Implemented for `0.3.0`/`0.3.1`:

- multi-file zip selection in `Packages & Intake`
- batch inspection with per-package result visibility
- automatic Review targeting for the normal single-package path
- dual watcher paths feeding one intake detection flow
- no blind batch planning/install

Current recommendation:

- use private testing to validate whether batch inspection + direct Review targeting feels clear enough before expanding planner semantics
- preserve explicit plan review as a non-negotiable constraint for any later multi-package work

#### 7. Real vs Sandbox Compare Baseline

Implemented for `0.4.0`:

- dedicated compare surface for configured real Mods vs sandbox Mods
- baseline drift categories:
  - only in real
  - only in sandbox
  - same version
  - version mismatch
  - ambiguous match
- compare is intentionally visibility-first in this stage (no compare-driven write behavior)

#### 8. Backup Bundle Inspection + Restore/Import Planning + Execution + Open-Folder Baseline

Implemented through `1.1.0`:

- explicit local backup export baseline for migration/recovery groundwork
- explicit read-only inspection of exported backup bundle folders
- explicit zip backup bundle support alongside folder-bundle compatibility
- manifest/version/item-status visibility before any restore behavior exists
- structural usability reporting for future restore/import work
- explicit read-only restore/import planning against the current local machine
- safe later / needs review / blocked planning visibility
- explicit restore/import execution for clearly missing mod folders and supported config artifacts into the currently configured destinations
- explicit reviewed conflict handling for different-version mod folders and different-content config artifacts
- archive-aware mod-folder replacement for restore conflicts (no file merge behavior)
- rollback of already-restored paths from the current run if execution fails mid-way
- inspect/plan/execute compatibility across both folder bundles and zip bundles
- explicit open-folder actions for real Mods, sandbox Mods, both archive roots, and both watched-download paths
- best-effort Steam prelaunch assistance for vanilla, SMAPI, and sandbox-dev launch
- persisted user-controlled Setup toggle for Steam auto-start assistance
- no background Steam management or retry loops in this baseline
- no file-level merge restore behavior in this baseline

### Post-v1 likely phases (real-world usability first)

#### 9. Restore/Import File-Level Merge Follow-up

- keep the shipped conflict-resolution baseline folder-oriented and trustworthy
- do not introduce file-level merge semantics until review, safety, and recovery semantics are explicitly designed
- no casual overwrite shortcuts

#### 10. Further Compare Ergonomics Only If They Stay Read-Only

- treat `1.1.0` as the shipped compare-orientation baseline
- only pursue future compare work if it improves decision speed without becoming a write surface
- keep compare visibility trustworthy and avoid implicit write shortcuts

### Later planned phase

#### 14. Information Architecture Follow-up

The broad shell simplification pass is now good enough through `1.1.0`. Post-v1 information architecture work should focus on compact empty states, launch-surface clarity, and reducing passive form density rather than reopening generic decomposition.

#### 15. Visual Feedback and Polish

Icon/taskbar refinement remains a lower-priority polish item compared with session, backup/migration, compare, and Steam prelaunch usability.

This phase should happen after the IA simplification decisions are made, not before.

## Current UX/Product Concerns Worth Challenging

An external model should specifically challenge these points:

### A. Is the updated roadmap still in the right order?

The current recommendation is to prioritize real-world usability and trust ergonomics first:

- restore/import file-level merge follow-up only if safety semantics are designed clearly
- any further compare work only if it remains clearly read-only and high value
- then broader polish/refactor work

Question:

> Is it correct to keep migration-trust follow-up ahead of more UI consolidation and polish now that the first compare follow-up is already shipped?

### B. Should live promotion stay conservative longer?

Question:

> How conservative should `sandbox -> real` remain now that preview/archive-aware replace exists, and what safeguards should be added before any faster promotion path is considered?

### C. What should remain global vs tab-local?

The app now has:

- a global status strip
- tab-local workflow surfaces
- selected-row guidance in `Inventory`
- local detail surfaces that appear only when useful

Question:

> Which of these should remain, collapse, or be retired?

### D. What is the next best daily-use ergonomics increment?

Question:

> Given that the intended near-term audience includes mod developers and careful local users, what sequence best balances trust and speed now that the first compare follow-up is already shipped?

### E. When should multi-package planning be allowed?

Question:

> What review surface and safety constraints would be required before moving from multi-zip batch inspection and direct single-package Review targeting to a true multi-package plan?

### F. What are the highest-value post-v1 UX fixes?

The app is now shipped, and the remaining visible issues are narrower:

- compacting empty-state tabs so content feels intentionally grouped instead of sparse
- making `Launch` feel like its own surface instead of “Inventory plus launch buttons”
- reducing remaining density in `Review` and `Setup` without weakening safety semantics

Question:

> Which 3-5 smallest post-v1 UX increments would most improve daily-use clarity without reopening risky shell churn?

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
- criteria for which post-v1 UI/UX work is worth doing next versus leaving alone
- the next 3-5 smallest safe increments, ordered by product value
