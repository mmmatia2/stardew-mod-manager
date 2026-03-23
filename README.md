# Stardew Mod Manager

Local-first Stardew Valley mod workflow manager for careful Windows users who want a safer way to install, test, compare, back up, and recover SMAPI mods.

`1.1.0` is the current stable portable release.

## What It Does

Stardew Mod Manager is built around three jobs:

- keep your installed mods visible and understandable
- give you a sandbox-first workflow for testing changes before touching live mods
- make backup, restore, and recovery steps explicit and reviewable

It is not a one-click downloader, profile manager, or cloud sync tool.

## Key Features

- scan installed mods and surface update status, duplicates, and dependency issues
- inspect downloaded zip packages before install
- review installs before any write happens
- keep sandbox work separate from live `Mods`
- compare real vs sandbox mod sets with actionable drift shown first
- export backup bundles as folders or zip files
- inspect, plan, and execute restore/import with review-first behavior
- archive and recover managed changes instead of overwriting blindly
- launch vanilla, SMAPI, or sandbox-dev with optional best-effort Steam start assistance

## Recommended Workflow

1. Set your game folder, real `Mods`, and sandbox `Mods` in `Setup`.
2. Use `Discover` and `Packages` to inspect downloaded zips.
3. Review the current package in `Review` before applying anything.
4. Install to the sandbox first.
5. Use `Compare` to see what drift exists between real and sandbox.
6. Promote selected sandbox mods into real `Mods` only when you are ready.
7. Use `Backup / Restore` features before larger changes or machine migration.

If you are not sure which destination to use, use the sandbox.

## Download And Use The Portable Build

The supported public build is a Windows portable zip published to GitHub Releases.

1. Go to the repository's GitHub Releases page.
2. Download `stardew-mod-manager-1.1.0-windows-portable.zip`.
3. Extract it to a normal folder.
4. Run `Stardew Mod Manager.exe`.

Release publishing baseline:

- the repo publishes a GitHub Release when a matching version tag such as `v1.1.0` is pushed
- the release asset is the zipped Windows portable build

Current portable-build caveats:

- this is a portable folder, not an installer
- Windows reputation prompts are still expected because code signing is not in place yet
- auto-update is not implemented yet

## Build From Source

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe scripts\build_windows_portable.py
```

The build script produces:

```text
dist\stardew-mod-manager-1.1.0-windows-portable\
```

The GitHub release workflow then zips that folder for distribution.

## Current Limitations

- downloads are still manual
- Compare is intentionally read-only; it does not sync, promote, or write
- restore/import conflict handling is archive-aware and folder-oriented; file-level merge is not implemented
- there is no one-click "sync everything back to real" flow
- profile and instance management are out of scope
- installer, signing, and auto-update work are still deferred
- Windows is the primary supported desktop path today

## Safety Model

- sandbox is the recommended destination for testing
- writes to live `Mods` stay explicit and reviewable
- archive/recovery paths are used to preserve reversibility where supported
- the app does not scrape providers or automate gated download flows

## Project Files

- [CHANGELOG](CHANGELOG.md)
- [CONTRIBUTING](CONTRIBUTING.md)
- [License](LICENSE)
