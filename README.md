# Stardew Mod Manager

Local-first Stardew Valley mod workflow manager with a sandbox-first safety model.

## Project status

This app is now the **first stable user-facing release** of the local desktop workflow manager in this repository.

In this repo, **semi-automatic** means:
- the app automates local scan, update awareness, intake detection, install planning, install execution, and recovery planning/execution
- the user still controls critical steps like opening provider pages, downloading files manually, choosing destinations, and confirming live (real Mods) writes

Current maturity is best described as:
- stable for careful local users who want a clear, safety-first Stardew mod workflow
- safety-oriented and increasingly test-covered
- still evolving beyond v1 in packaging, polish, and post-release ergonomics

Current workflow emphasis:
- safe local mod workflow over broad platform-management ambitions
- sandbox-first mod development and validation
- migration trust through explicit local backup/export, bundle inspection, restore/import planning, restore/import execution, and first-baseline restore conflict handling
- explicit, user-triggered movement between sandbox and real Mods
- no hidden mirroring or blind overwrite of live Mods
- explicit batch package inspection with single-package staging for planning

Near-term product identity:
- strongest at safe local workflow, dev-loop trust, and migration trust
- not trying to become a one-click downloader in the near term
- not trying to become a broad profile or instance manager in the near term

## Current supported workflow

1. Scan installed mods (`configured real Mods` or `sandbox Mods` target).
2. Check updates for installed mods.
3. Optionally sync selected installed mods from `real Mods -> sandbox Mods`.
4. Launch the game through SMAPI against the sandbox Mods path only.
5. Open remote provider page for actionable rows.
6. Download mod archives manually.
7. Select one or more zip packages for batch inspection, or let watcher/package intake detect new zip files from one or two configured watch paths.
8. Review per-package inspection results; the current valid selection becomes the Review target automatically.
9. Build the install review, confirm the safety context, then run install.
10. Promote selected sandbox mods into real Mods through an explicit managed action when ready.
11. Inspect recovery readiness and run recovery from recorded install history when allowed.

Recommended path:
- use **Sandbox Mods** as the default destination for testing
- move to **real Mods** only when the plan is understood and explicit confirmation is accepted

Live Mods safety expectations:
- real destination requires explicit confirmation before execution
- archive/recovery data is recorded for reversibility workflows
- destructive operations are intentionally constrained and surfaced

## Feature summary (current)

- **v1 shell structure**
  - the main workspace now reads as three journeys: install/update, sandbox compare/archive, and backup/restore
  - right-side tabs now use simple product-facing names (`Setup`, `Discover`, `Compare`, `Packages`, `Review`, `Recovery`, `Archive`) instead of overloaded prefixed labels
  - `Review` now focuses only on install review/apply, while `Recovery` is its own separate tab
  - the left-side shell is reduced to `Installed Mods` and `Launch`, with selected-mod archive actions moved back into the installed-mod workflow
  - the old bottom detail/log panel is gone, and the old left-side `Current detail` panel is gone too; detail now lives only in the relevant workflow surface instead of shared console-style panels
  - setup and review surfaces now spell out real Mods vs sandbox and distinguish read-only review steps from actions that write files
  - empty local detail panels stay collapsed until that workflow actually has useful detail to show
  - this is a user-facing shell consolidation step, not a backend workflow rewrite
- **Inventory + update awareness**
  - installed mod scan/inventory view
  - update checks across supported providers
  - actionable vs blocked update status, with typed diagnostics
- **Install / Update**
  - discovery surface with provider/context correlation signals
  - choosing zip packages now kicks off inspection directly for the normal flow
  - multi-zip selection and batch inspection
  - per-package inspection results with explicit selection
  - watcher-based downloads intake from up to two configured watch paths
  - the current valid package selection drives Install / Update review directly, without a separate user-facing staging step
- **Session persistence ergonomics**
  - practical setup/session fields survive restart
  - watcher paths, key Mods/archive paths, and active scan/install targets reload automatically
- **Install / Update review**
  - destination selection (sandbox vs real)
  - plan review summary/explanation/facts
  - controlled execution flow
- **Recovery**
  - install operation history
  - derived recovery plan + execution review
  - constrained recovery execution and recording
- **Update-source intent overlay**
  - persisted app-level intent per mod (`local/private`, `no-tracking`, `manual source association`)
  - intent-aware diagnostics in Inventory
  - manual association now participates in update resolution
- **Sandbox dev loop**
  - sandbox-only SMAPI launch using the configured sandbox Mods path
  - best-effort Steam prelaunch assistance for vanilla, SMAPI, and sandbox-dev launch
  - persisted Setup toggle to turn Steam auto-start assistance on or off
  - explicit selected-mod `real -> sandbox` sync
  - explicit selected-mod `sandbox -> real` promotion
  - promotion preview/review with explicit confirmation for live writes
  - archive-aware replace on live-target conflicts (no blind overwrite)
- **Real vs sandbox compare view**
  - dedicated compare tab for drift visibility before sync/promotion decisions
  - clear first-pass categories: only in real, only in sandbox, same version, version mismatch, ambiguous match
  - compare is visibility-first in this baseline (no compare-driven write actions)
- **Backup bundle inspection baseline**
  - explicit export-first backup bundle creation for migration/recovery groundwork
  - backup bundles now support both folder artifacts and `.zip` artifacts
  - inspect exported backup bundles without modifying local data
  - surface manifest format/version, included items, missing expected content, and structural usability
- **Restore/import planning baseline**
  - compare a selected folder or zip backup bundle against the current local setup without changing local files
  - classify what looks safe to restore later, what needs review, and what is blocked or not usable from the current bundle
  - include config-aware visibility for common per-mod config artifacts carried in the backup bundle
  - keep destination mapping and conflicts understandable before broader restore behavior
- **Restore/import execution baseline**
  - explicit `Execute restore/import` action built on the existing planning result
  - restores only clearly missing mod folders and supported missing config artifacts into the currently configured local destinations
  - works from either the current folder bundle or zip bundle artifact
  - rolls back already-restored paths from the current run if a mid-run restore failure occurs
- **Restore/import conflict-resolution baseline**
  - reviewed restore can now resolve:
    - existing mod folder with different version
    - existing config artifact with different content
  - conflict handling is explicit and review-first
  - conflicting local content is handled through archive-aware mod-folder replacement, not file merge
  - ambiguous or structurally blocked restore cases still do not execute
- **Backup flow continuity fix**
  - inspect, plan, and execute now reuse the current active backup bundle context instead of repeatedly asking for the same bundle artifact
  - the active bundle is shown in Backup / Restore so restore/import actions stay explicit about which bundle they will use
- **Config-aware backup baseline**
  - backup export now carries common per-mod config artifacts found inside installed real/sandbox Mods trees
  - bundle inspection reports config snapshot coverage explicitly
  - restore/import planning surfaces config entries as missing locally, same content, different content, or blocked
- **Zip backup bundle support baseline**
  - backup export can now create `.zip` bundle artifacts as a first-class option
  - inspect, plan, and execute support zip bundles without dropping folder-bundle compatibility
  - zip bundles are read through a guarded temporary extraction path; corrupt or unsafe zip bundles are rejected honestly
- **Open-folder conveniences baseline**
  - explicit open-folder actions for the key configured workflow locations
  - quick access to real Mods, sandbox Mods, both archive roots, and both watched-download folders
  - honest feedback when a path is unconfigured, missing, or cannot be opened
- **Setup ergonomics patch**
  - Backup / Restore remains usable at smaller window sizes through a more scroll-friendly layout and less fragile action-row compression
  - setup-local detail output now keeps backup/setup results readable inside Setup without relying on a shared bottom log surface
  - Setup now separates essential live/sandbox folders from lower-priority archive, Nexus, and Steam safety options
- **Compact idle states**
  - Compare and Archive stay compact until they have real results to show, instead of opening on large empty result panes

## Manual source guidance

`Manual source association` is an app-level override used when a mod’s manifest update keys are missing/wrong/unhelpful.

### Terms

- **Provider**: which metadata source adapter to use.
- **Source key**: provider-specific identifier used to resolve metadata.
- **Page URL (optional)**: user-facing reference URL for context; not required for lookup.

### Supported provider/source-key formats

- `github`
  - source key: `owner/repo`
  - example: `Pathoschild/SMAPI`
- `nexus`
  - source key: `12345`
  - source key: `stardewvalley:12345`
  - source key: full Nexus mod URL
    - example: `https://www.nexusmods.com/stardewvalley/mods/12345`
- `json`
  - source key: direct metadata URL
  - example: `https://example.com/mod/update.json`

### What manual source does now

- persisted as a local app-state overlay record
- used during update check as an override for lookup resolution when supported and valid
- does **not** edit `manifest.json`

## Safety and non-goals

- no scraping
- no browser automation for downloads
- no premium-bypass behavior
- no one-click install-from-search
- sandbox remains the recommended testing path
- no raw bidirectional mirroring between real and sandbox Mods
- live writes should remain explicit, reviewable, and recoverable

## Practical local usage (Windows)

### 1) Create environment and install

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

### 2) Launch UI

```powershell
.\.venv\Scripts\sdvmm-ui.exe
```

Alternative:

```powershell
.\.venv\Scripts\python.exe -m sdvmm.app.main
```

### 3) Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

You can still run focused suites when iterating:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_main_window_gui_regression.py -q
```

### 4) Build Windows portable folder (`1.0.0`)

Packaging baseline in this repo uses **PyInstaller one-folder** output because it is the smallest practical Windows desktop packaging path here without introducing installer/signing work.

Install the packaging dependency:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .[build]
```

Build the portable folder:

```powershell
.\.venv\Scripts\python.exe scripts\build_windows_portable.py
```

Output folder:

```text
dist\stardew-mod-manager-1.0.0-windows-portable\
```

Launch the packaged app:

```powershell
.\dist\stardew-mod-manager-1.0.0-windows-portable\Stardew Mod Manager.exe
```

Current caveats:
- this is a portable folder build, not an installer
- no code signing yet, so Windows reputation prompts are still expected
- no auto-update or installer/signing hardening yet
- packaged runtime is pinned to bundled Qt plugin paths (`_internal\PySide6\plugins`) to avoid host Qt path conflicts

## Known limitations (current)

- no automated provider-compliant download pipeline yet (manual download remains required)
- multi-zip intake currently stops at batch inspection plus explicit single-package staging; it does not build or execute blind multi-package install plans
- sandbox->real promotion is intentionally explicit and safety-first; there is no casual one-click "sync back all" workflow
- no broad history browser UX; recovery is available through focused inspection/execution paths
- no profiles/instances workflow
- no packaging/installer/release hardening yet
- no cross-platform polish emphasis yet (Windows workflow is the primary dev path)
- restore/import now handles reviewed version/content conflicts through archive-aware mod-folder replacement; file-level merge behavior is still deferred
- Steam prelaunch help is now shipped as best-effort launch assistance with a persisted user-controlled toggle; it does not do background Steam management or retry loops
- near-term usability priorities are now:
  - compare follow-up after the current restore/import and Steam-assisted launch baselines
  - restore/import file-level merge follow-up only if safety/review semantics are explicitly designed
- downloader automation, profile systems, and broad UI polish remain lower priority than restore/import trust work

## Data and persistence notes

- local file-based app state (JSON), no database
- install and recovery history are recorded for audit/recovery workflows
- update-source intent overlay is persisted separately and merged at app-layer update check time
- `Export backup bundle` creates a local backup artifact using the current validated setup values, not just the last saved `app-state.json`
- the export bundle can include app state/config, install/recovery history, update-source intent overlay, real/sandbox Mods, and app-managed archive roots when they exist
- export now also includes common per-mod config artifacts found inside installed Mods trees under `mod-config\real-mods\...` and `mod-config\sandbox-mods\...`
- export supports both folder bundles and `.zip` bundles; folder bundles remain fully supported for compatibility
- `Inspect backup bundle` reads an exported folder or zip bundle and reports structure/usability without applying restore changes
- `Plan restore/import` compares the current active backup bundle against the current local machine and reports what looks safe later, what needs review, and what is blocked, including config artifact visibility
- `Execute restore/import` now restores clearly missing content and reviewed conflict cases into the current configured destinations, reusing the current active bundle context when available
- reviewed conflicts use archive-aware mod-folder replacement; file-level merge behavior for conflicting local content is still intentionally not implemented
