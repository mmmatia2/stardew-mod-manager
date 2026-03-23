# Product Brief

## Problem statement

Stardew Valley players still manage many SMAPI mods through a fragmented manual workflow:

- inspect installed mods locally
- check whether updates exist
- open a mod page manually
- download a zip manually
- inspect that package
- install it safely
- recover from mistakes when something goes wrong

The failure modes are predictable:

- duplicate mods
- missing dependencies
- malformed or unsafe packages
- unclear live-Mods risk
- hard-to-explain update failures
- poor rollback visibility

The product is intended to make that manual workflow safer, clearer, and more reversible without resorting to scraping, browser automation, or one-click remote install behavior.

## Target user

Primary user:
- a Stardew Valley player using SMAPI mods who wants a local-first desktop tool to scan, inspect, install, and recover mods safely

Secondary user:
- a technically comfortable mod author or heavy mod user who wants stronger update visibility, recovery history, and guarded live-Mods workflows

## Current product goals

- Show a reliable local inventory of installed mods.
- Detect duplicate IDs, dependency problems, and package issues from local metadata.
- Support manual-download-assisted installation from local zip files.
- Preserve safe-by-default install semantics, with sandbox remaining the recommended path.
- Record install and recovery history with enough data for inspection and recovery execution.
- Support read-only update checks using allowed metadata flows only.
- Explain update-source failures clearly enough that users understand why a mod cannot be updated through the guided flow.
- Keep behavior deterministic, inspectable, and reversible where possible.

## Explicit non-goals

- Automatic downloading from remote providers.
- Browser automation, scraping, or premium/gated-download bypass.
- One-click install from discovery/search.
- Cloud sync or online account dependence.
- Database-backed persistence without a concrete product need.
- Full compatibility resolution beyond explicit local metadata and approved heuristics.
- Broad game-management features outside mods and related diagnostics.

## Core user flows

1. User configures game path, scan paths, and safe install destinations.
2. User scans installed mods and reviews duplicates, dependencies, update state, and warnings.
3. User checks updates using allowed metadata only.
4. User opens a selected remote page manually and downloads a package outside the app.
5. User inspects or intakes a local zip package.
6. User stages that package into `Plan & Install`.
7. User builds an install plan, reviews safety/warnings/facts, and executes it into sandbox or guarded real Mods.
8. User inspects recovery readiness and executes recovery when needed.

## Implemented product baseline

- Initial configuration for game path, Mods path, archive paths, downloads watcher path, and app-state file.
- Local inventory scan using manifest metadata.
- Duplicate mod detection and dependency visibility.
- Manual zip inspection and downloads intake.
- Safe local install planning and execution with archive-first replacement behavior.
- Explicit execution review for live-Mods installs.
- Install history, recovery plan derivation, recovery review, and recovery execution.
- Recovery history with stable operation IDs.
- Guided update checks using approved metadata flow only.
- Discovery/search surface for provider-backed search without install automation.

## Major product risks

- Mod packaging remains inconsistent and hard to normalize.
- Installed metadata is often incomplete, stale, malformed, or provider-specific.
- `no_remote_link` and `metadata_unavailable` failures need better structured diagnostics.
- Live-Mods workflows are safer than before but still need more UX hardening before public release.
- The UI is functionally coherent but visually dense, which will require a dedicated consolidation phase later.
