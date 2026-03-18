# Roadmap

## Shipped through `0.4.0`

### Core workflow and trust baseline

Shipped:

- setup/config + inventory scan
- update awareness + guided manual remote-page flow
- package inspection/intake -> plan/review -> explicit execution
- install history + recovery derivation/review/execution
- guarded real-Mods writes with archive/recovery semantics

### Update-source intent and diagnostics

Shipped:

- typed update-source diagnostics
- persisted update-source intent overlay (`local/private`, `no-tracking`, `manual source association`)
- manual source association participation in update checks
- atomic app-state/history writes and explicit critical history-failure handling

### Sandbox dev loop + intake ergonomics

Shipped:

- sandbox-only launch (SMAPI with sandbox Mods path)
- explicit selected-mod `real -> sandbox` sync
- explicit selected-mod `sandbox -> real` promotion with preview/review
- archive-aware replace on live conflicts (no blind overwrite)
- partial-failure safety handling for promotion paths
- multi-zip batch inspection with per-package visibility
- explicit single-package staging (no opaque batch install)
- second watcher-path support feeding the same intake flow

### Real vs sandbox compare baseline

Shipped:

- dedicated compare surface for configured `real Mods` vs `sandbox Mods`
- clear baseline categories:
  - only in real
  - only in sandbox
  - same version
  - version mismatch
  - ambiguous match for duplicate/unclear UniqueID grouping
- compare remains visibility-first in this stage (no compare-driven writes)

### Information architecture simplification (paused)

Implemented enough for now:

- bottom area is output-only
- setup moved into main workspace ownership
- duplicated detail scaffolding reduced

Still paused because product-facing usability/trust gaps now outweigh more decomposition.

## Critical next priorities (near-term)

### 1. Session persistence ergonomics

- preserve practical working context between launches (active targets, last-used intake/watch context, recent selections where safe)
- reduce repetitive setup/check clicks for everyday usage
- keep state explicit and user-controllable

### 2. Backup / restore / migration foundation

- add explicit user-facing backup/export and restore/import baseline for file-backed state/history
- include pragmatic migration guardrails for personal-machine changes
- keep trust/recovery semantics transparent and inspectable

### 3. Steam prelaunch best-effort behavior

- support best-effort launch behavior that works with Steam ownership constraints without implying guaranteed automation
- keep launch intent explicit and sandbox-safe
- surface when fallback/manual launch is required

### 4. Compare follow-up (deferred after baseline ship)

- keep the shipped compare view readable and trustworthy as a first-class drift/orientation surface
- defer richer compare actions (for example direct compare-driven sync/promotion shortcuts) until safety semantics are explicitly designed
- preserve compare-first visibility discipline; no blind merge/write behavior

## Near-term but lower priority

### Icon/taskbar refinement follow-up

- continue icon/taskbar sizing polish only after critical workflow usability items above
- treat as quality polish, not a workflow blocker

## Later priorities

### Recovery/promotion hardening follow-up

- stronger multi-mod live-write review/audit surfaces
- clearer recovery inspectability for more complex real-write scenarios

### Public release hardening

- installer/signing/distribution hardening
- CI/release gating maturity
- migration discipline for broader audience rollout

### Provider-compliant automation (still constrained)

- official provider mechanisms only
- explicit user-owned auth
- no scraping, no premium bypass, no one-click install-from-search until explicitly approved

## Guardrails that remain non-negotiable

- preserve asymmetry: `real -> sandbox` sync vs managed `sandbox -> real` promotion
- no raw bidirectional mirroring
- no blind overwrite into real Mods
- no profile/instance broadening unless explicitly approved
