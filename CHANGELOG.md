# Changelog

All notable user-facing changes for this repository are tracked here.

## [1.1.5]

- Fixed Windows dark-theme confirmation dialog readability so confirmation prompts stay legible in the shipped portable app.
- Shipped as a small UI/readability hotfix with no workflow-semantics change.

## [1.1.4]

- Tightened shell chrome and improved workflow emphasis so the main mod workflow reads more clearly than Setup-heavy earlier builds.
- Refined Setup into a lighter configuration surface with backup and restore tools kept visible but visually secondary.
- Improved workflow-page clarity across Mods, Packages, Review, Discover, Compare, and Archive with better idle, active, and next-step guidance.
- Polished action hierarchy, row selection, disabled states, and local interaction feedback across the core workflow surfaces.
- Hardened the Windows portable package with aligned EXE metadata, removed stale bundled package metadata, and added SHA256 checksum output for the release zip.
- Shipped as a UX, packaging-trust, and release-surface polish update with no workflow-semantics change.

## [1.1.3]

- Fixed the restore/import planning regression where the released UI passed an unsupported `steam_auto_start_enabled` argument into restore/import planning.
- `Inspect backup` now automatically runs restore/import planning for the current configured environment when the bundle is structurally usable.
- Removed the extra restore-plan click from the normal UI flow and kept restore review tied to the active inspected bundle.
- Fixed restore/import execution readiness so the write action only appears available when execution is actually allowed under the current review model.
- Kept explicit confirmation in front of restore/import writes.
- Fixed packaged version display so the portable app now truthfully shows `Version 1.1.3` in the shell.
- Shipped as a narrow restore/import and packaging hotfix with no broader workflow-semantics change.

## [1.1.2]

- Fixed the `Backup export` regression where the released UI passed an unsupported `steam_auto_start_enabled` argument into backup/export.
- Fixed the visible background bleed behind the `Installed Mods` / `Launch` sub-tab row in the Mods workspace.
- Shipped as a narrow hotfix with no workflow-semantics change.

## [1.1.1]

- Renamed the public app surface to `Cinderleaf`, with `for Stardew Valley` used only as a secondary descriptor.
- Fixed the remaining top-shell header compression so operational context stays readable without changing workflow behavior.
- Aligned the portable package, public README, and release-ready repo surface for the `1.1.1` patch release.
- Switched the project to a source-available noncommercial license for public distribution.

## [1.1.0]

- Compare now opens on actionable drift by default instead of same-version noise.
- Added compare category filtering, inline category explanations, and copy mod name / UniqueID convenience.
- Shipped the first public-facing `1.1.0` release surface with updated docs and portable build alignment.

## [1.0.0]

- Declared the first stable user-facing release.
- Shipped the core local workflow: scan, inspect, review, install, recovery, backup/export, restore/import, sandbox compare, and managed sandbox promotion.
- Shipped folder and zip backup-bundle support plus the v1 shell cleanup baseline.
