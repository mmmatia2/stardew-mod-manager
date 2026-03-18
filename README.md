# Stardew Mod Manager

Local-first Stardew Valley mod workflow manager with a sandbox-first safety model.

## Project status

This app is currently a **working local desktop tool** with meaningful workflow coverage, but it is **not release-hardened consumer software yet**.

In this repo, **semi-automatic** means:
- the app automates local scan, update awareness, intake detection, install planning, install execution, and recovery planning/execution
- the user still controls critical steps like opening provider pages, downloading files manually, choosing destinations, and confirming live (real Mods) writes

Current maturity is best described as:
- useful for technically literate early users and close-friend sharing
- safety-oriented and increasingly test-covered
- still evolving, with some UX and product-completion gaps called out below

Current workflow emphasis:
- sandbox-first mod development and validation
- explicit, user-triggered movement between sandbox and real Mods
- no hidden mirroring or blind overwrite of live Mods
- explicit batch package inspection with single-package staging for planning

## Current supported workflow

1. Scan installed mods (`configured real Mods` or `sandbox Mods` target).
2. Check updates for installed mods.
3. Optionally sync selected installed mods from `real Mods -> sandbox Mods`.
4. Launch the game through SMAPI against the sandbox Mods path only.
5. Open remote provider page for actionable rows.
6. Download mod archives manually.
7. Select one or more zip packages for batch inspection, or let watcher/package intake detect new zip files from one or two configured watch paths.
8. Review per-package inspection results, then stage one selected package into Plan & Install.
9. Build plan, review safety/summary/facts, then run install.
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

- **Inventory + update awareness**
  - installed mod scan/inventory view
  - update checks across supported providers
  - actionable vs blocked update status, with typed diagnostics
- **Discovery/search**
  - discovery tab with provider/context correlation signals
- **Packages & Intake**
  - multi-zip selection and batch inspection
  - per-package inspection results with explicit selection
- watcher-based downloads intake from up to two configured watch paths
  - single-package staging handoff to Plan & Install
- **Plan & Install**
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
  - explicit selected-mod `real -> sandbox` sync
  - explicit selected-mod `sandbox -> real` promotion
  - promotion preview/review with explicit confirmation for live writes
  - archive-aware replace on live-target conflicts (no blind overwrite)
- **Real vs sandbox compare view**
  - dedicated compare tab for drift visibility before sync/promotion decisions
  - clear first-pass categories: only in real, only in sandbox, same version, version mismatch, ambiguous match
  - compare is visibility-first in this baseline (no compare-driven write actions)

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

### 4) Build Windows portable folder (`0.4.0`)

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
dist\stardew-mod-manager-0.4.0-windows-portable\
```

Launch the packaged app:

```powershell
.\dist\stardew-mod-manager-0.4.0-windows-portable\Stardew Mod Manager.exe
```

Current caveats:
- this is a portable folder build, not an installer
- no code signing yet, so Windows reputation prompts are still expected
- no auto-update or release-hardening work yet
- packaged runtime is pinned to bundled Qt plugin paths (`_internal\PySide6\plugins`) to avoid host Qt path conflicts

## Known limitations (current)

- no automated provider-compliant download pipeline yet (manual download remains required)
- multi-zip intake currently stops at batch inspection plus explicit single-package staging; it does not build or execute blind multi-package install plans
- sandbox->real promotion is intentionally explicit and safety-first; there is no casual one-click "sync back all" workflow
- no broad history browser UX; recovery is available through focused inspection/execution paths
- no profiles/instances workflow
- no packaging/installer/release hardening yet
- no cross-platform polish emphasis yet (Windows workflow is the primary dev path)
- restore/import workflow is still deferred; the current backup foundation is export-first
- near-term usability priorities still pending: fuller backup restore/migration workflow, Steam prelaunch best-effort behavior, and richer compare follow-up (for example compare-driven convenience actions) beyond the current visibility-first baseline

## Data and persistence notes

- local file-based app state (JSON), no database
- install and recovery history are recorded for audit/recovery workflows
- update-source intent overlay is persisted separately and merged at app-layer update check time
- `Export backup bundle` creates a local folder snapshot using the current validated setup values, not just the last saved `app-state.json`
- the export bundle can include app state/config, install/recovery history, update-source intent overlay, real/sandbox Mods, and app-managed archive roots when they exist
- the export is intentionally inspectable and non-destructive; restore/import UX is not implemented yet
