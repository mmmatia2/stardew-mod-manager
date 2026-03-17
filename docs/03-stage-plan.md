# Roadmap

## Completed or effectively closed

### 1. Core Workflow Foundation

Implemented:

- configuration and scan path setup
- local mod inventory scan
- duplicate and dependency visibility
- package inspection and downloads intake
- install planning and execution review
- sandbox install execution
- guarded real-Mods execution
- install history
- recovery derivation, review, and execution
- recovery history with stable IDs

### 2. Guided Manual Update Flow

Implemented:

- update check awareness flow
- selected-row remote-page handoff
- intake staging into `Plan & Install`
- install-to-recovery continuity

### 3. Managed Live Mods Safety Baseline

Implemented baseline:

- persistent destination safety context
- explicit confirmation for real-Mods execution
- stronger live destination messaging before execution
- constrained-height resilience in `Plan & Install`

### 4. History / Recovery UX Baseline

Implemented baseline:

- readable recovery selector
- newest-first recovery record display
- recovery summary cues
- recovery filtering
- recovery execution path with status continuity

### 5. Update Source Diagnostics / Persistence / Repair Foundations

Implemented:

- typed update-source diagnostics below the UI
- Inventory binding to typed diagnostics
- atomic app-state and history writes
- honest handling of critical history-recording failure
- platform-correct app-state path behavior
- durable update-source intent overlay
- local/private and no-tracking intent
- manual source association storage and UI
- manual source association participation in update checks

### 6. Information Architecture Simplification (Paused)

Implemented enough for now:

- bottom area reduced to output-only ownership
- setup moved into a dedicated workspace tab
- duplicate narrative/detail access scaffolding removed
- top context and status ownership reduced
- shell/tab alignment issue driven down to an acceptable stop point

Paused because:

- product-facing sandbox/dev workflow completion is now higher value than more decomposition or shell polish
- additional UI cleanup is hitting diminishing returns relative to workflow gaps

## Current phase

### 7. Sandbox Dev Loop Foundation

Completed:

- sandbox-only SMAPI dev launch using `--mods-path <sandbox>`
- runtime readiness/status for sandbox launch
- explicit selected-mod `real -> sandbox` sync
- explicit selected-mod `sandbox -> real` managed promotion
- promotion preview/review before live writes
- archive-aware replace for live-target conflicts (no blind overwrite)
- explicit confirmation-first live write flow
- safety handling for partial-failure paths so live-write trust/recovery semantics remain coherent

Why this phase is current priority:

- it directly supports the actual personal mod-development loop
- it keeps real personal Mods isolated from dev/test iteration
- it has higher product value than more generic UI decomposition

### 8. Multi-Zip Intake Baseline

Completed for `0.3.0`:

- `Packages & Intake` can now select multiple zip files in one action
- batch inspection preserves per-package visibility instead of collapsing results
- partial batch failures stay visible per package
- staging remains explicit and single-package in this first step

Why this stopped here:

- true multi-package planning/install would be harder to review safely in the current planner
- single-package staging keeps plan review clear and avoids opaque batch execution semantics

## Next phase

### 9. Sandbox Dev Loop Ergonomics

Likely scope:

- open sandbox / real Mods convenience actions
- automatic rescan of the destination after sync/promotion without switching context unless necessary
- clearer launch/readiness and promotion-state orientation for sandbox workflow
- private-testing feedback on multi-zip intake clarity before expanding batch planning behavior

Validation gate:

- repeated dev-loop use feels explicit and low-friction without weakening real-Mods safety

Explicitly out of scope:

- raw bidirectional mirroring
- blind overwrite into real Mods
- profile or instance systems
- build/watch automation

## Later planned phases

### 10. Recovery and Promotion Hardening

Planned scope:

- stronger preview/review surfaces for multi-mod live promotion and recovery
- auditability improvements for live-write workflows

### 11. Information Architecture Follow-up

Revisit only after the sandbox dev loop is no longer the main product blocker.

Planned scope:

- remaining ownership cleanup
- `Plan & Install` / `Recovery` surface simplification if still justified
- progressive disclosure for dense but stable workflows

### 12. Visual Polish and Release UX

Planned scope:

- visual hierarchy cleanup
- warning/disabled-state clarity
- first-run and advanced-mode UX clarity

### 13. Public Release Hardening

Planned scope:

- packaging
- installer strategy
- code signing
- CI
- persistence migration discipline

### 14. Provider-Compliant Automation

Planned scope:

- official provider mechanisms only
- user-owned auth
- no scraping
- no premium bypass
- no one-click install-from-search until explicitly designed and approved
