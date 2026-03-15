# AGENTS.md

## Purpose

This repository is developed using a direct ARCHITECT / EXECUTOR workflow inside the Codex app.

Both agents have live repository context and both read this file.

This file defines durable repository-level workflow rules, engineering constraints, validation expectations, and scope discipline.

It does not replace the thread-specific role prompt for the ARCHITECT or the EXECUTOR.

---

## Core workflow model

- The ARCHITECT audits executor handoffs, challenges weak assumptions, decides gates, and defines the next smallest safe increment.
- The EXECUTOR performs the approved repo-aware implementation work for the current stage.
- Prefer one active stage at a time per repository.
- Do not run parallel changes that touch the same files or the same feature surface at the same time.
- Prefer small, testable, low-risk increments over broad rewrites.
- Do not expand scope just because adjacent code is visible.

---

## Shared engineering rules

- Do not confuse compile success with real validation.
- Distinguish clearly between:
  - implemented
  - validated
  - assumed
  - pending
  - prepared/scaffolded
- Preserve behavior unless the current stage explicitly authorizes behavior change.
- Do not move logic and layout in the same step unless the stage explicitly authorizes both.
- Prefer narrow seams and reversible changes.
- Do not reconstruct structured diagnostics or policy categories by parsing UI-facing strings when the underlying reason can be exposed as typed service/domain data.
- Do not perform opportunistic cleanup outside the approved stage boundary unless it is strictly required to complete the task safely.
- Keep diffs reviewable.

---

## Product constraints

- Preserve safe-by-default and reversible workflow semantics.
- Sandbox remains the recommended path until managed live-install flows are fully validated.
- Treat `real -> sandbox` sync and `sandbox -> real` promotion as intentionally asymmetric:
  - `real -> sandbox` may be an explicit selected-mod sync
  - `sandbox -> real` must remain a managed promotion flow with real-Mods safety semantics
- Do not introduce raw bidirectional mirroring that bypasses archive/recovery guarantees for live Mods.
- No premium-bypass behavior.
- No scraping or browser automation for downloads.
- Automatic downloads are allowed only when they use official provider mechanisms, valid user credentials, and provider-compliant flows.
- No one-click install-from-search until provider/legal/UX rules are explicitly designed and approved.
- No profile or instance work unless an approved roadmap stage explicitly authorizes it.
- No database introduction without explicit architectural approval and a concrete product need.
- Preserve user-controlled and explainable workflow semantics unless a stage explicitly changes them.

---

## Product roadmap discipline

- Prefer product-facing workflow completion and trust features over further UI decomposition.
- When the sandbox dev loop is blocking real product use, prioritize launch/sync/promotion trust work ahead of more shell polish or decomposition.
- Treat destructive or real-Mods operations as requiring backup/archive and a recovery path.
- Optimize for public-user clarity, not only power-user personal workflow speed.
- Do not reopen paused extraction tracks without a concrete product reason.

---

## Provider / compliance rules

- Respect provider terms and rate limits.
- Use official APIs where available.
- Keep authentication explicit and user-owned.
- Do not design around paid-feature circumvention.

---

## Validation expectations

When repository files change, validate to the level appropriate for the stage.

Default validation expectations:
- run compile checks for touched Python UI files when applicable
- run targeted tests for the touched seam or feature when applicable
- run the full test suite when the stage touches shared UI composition, workflow wiring, or behavior
- run a basic startup smoke check when UI composition or startup paths are touched
- expect CI for changes that affect shared workflow behavior before public-release readiness work is considered complete

Do not claim validation that was not actually performed.

If validation could not be performed, state that clearly.

Always distinguish clearly between validated and assumed behavior in the handoff.

---

## Manual testing rule

Request manual validation only when it is genuinely needed to close a real uncertainty.

Do not ask for manual testing for purely analysis-only stages.

When manual testing is necessary:
- ask for the minimum necessary validation only
- keep steps short and specific
- prefer real workflow checks over cosmetic inspection

---

## Commit discipline

A stage is ready to commit only when it is:
- small
- coherent
- validated to the level appropriate for that stage
- not carrying known risky drift that should be resolved first

Do not recommend bundling unrelated changes into one commit.

Prefer one commit per approved stage.

---

## Handoff discipline

Executor handoffs should be concrete and audit-friendly.

When implementation work was done, handoffs should clearly state:
- what changed
- what intentionally did not change
- what was validated
- what remains assumed or pending
- whether the stage is ready to commit

Analysis-only handoffs should clearly state:
- current repository reading
- concrete risks
- recommendation
- whether no repo files changed

---

## UI refactor / decomposition discipline

For UI decomposition work:
- prefer composition-only extraction before behavior migration
- preserve existing ownership of live widgets unless the stage explicitly changes ownership
- preserve existing object names used by tests unless a stage explicitly changes the test contract
- add structural regression guards before extracting a seam when the seam is non-trivial
- do not treat file-size reduction as success by itself
- prefer product-facing workflow completion over continued decomposition when both compete for the same capacity
- pause a refactor phase when diminishing returns begin

---

## MainWindow-specific rule

For `src/sdvmm/ui/main_window.py`:
- do not assume remaining inline code should always be extracted
- prefer safe stop over bad extraction
- do not mix composition extraction with behavior migration unless explicitly authorized
- preserve responsive layout behavior unless the stage explicitly targets responsive changes

---

## Codex app workflow rule

Because both ARCHITECT and EXECUTOR operate with live repository context in Codex app:
- do not restate large amounts of repository context unless needed for the current decision
- prefer concise, stage-specific prompts
- keep thread continuity focused on the current feature or refactor line
- avoid creating artificial artifacts for analysis-only work

---

## When to reopen a paused extraction track

A paused extraction/refactor track should be reopened only if:
- a new seam becomes clearer and safer after other changes
- a maintenance burden repeatedly points to one remaining mixed block
- a testing or ownership problem creates a concrete reason to separate a surface
- the next step has a clear boundary, acceptable rebinding risk, and a concrete product reason

Do not resume extraction just because a file is still large.
