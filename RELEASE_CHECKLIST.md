# Release Checklist

Use this checklist for every public Cinderleaf release.

## Core rule

Do not publish a version until the packaged app, the public docs, and the release assets all agree on the same version and user-visible behavior.

## Before the version bump

- confirm the release scope is narrow enough to explain clearly
- confirm any write-path changes have been manually exercised:
  - install / review
  - promote / real-`Mods` writes
  - backup export
  - restore / import
  - recovery
- identify whether the public screenshots or Nexus header need refresh

## Required version-alignment updates

Update these together when shipping a new version:

- `pyproject.toml`
- user-visible version labels in the packaged app
- `CHANGELOG.md`
- `README.md` if behavior, screenshots, or download instructions changed
- release asset name expectations:
  - `cinderleaf-X.Y.Z-windows-portable.zip`

## Required validation

Run these before release:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
.\.venv\Scripts\python.exe scripts\build_windows_portable.py
```

Also do a real packaged-app check for the shipped build:

- launch `dist\cinderleaf-X.Y.Z-windows-portable\Cinderleaf.exe`
- confirm the visible shell shows the correct version
- confirm any release-scope workflow changes behave correctly in the packaged app
- verify the release checksum file exists:
  - `dist\cinderleaf-X.Y.Z-windows-portable.zip.sha256`

## Docs and media pass

Before publishing:

- update `README.md` if the current screenshots or workflow text are stale
- update `CONTRIBUTING.md` / feedback guidance if repo policy changed
- update `CHANGELOG.md` with user-facing release notes
- refresh `media/nexus-screenshots/` if the visible UI changed meaningfully
- refresh the Nexus header image if the current header no longer fits the app or page layout

## GitHub release steps

1. commit the final release state
2. push `main`
3. create and push tag `vX.Y.Z`
4. run the GitHub Actions release workflow from `main` with:
   - `release_ref = vX.Y.Z`
5. if Authenticode signing is available, sign `dist\cinderleaf-X.Y.Z-windows-portable\Cinderleaf.exe` before the final zip/checksum that will be published
6. verify the GitHub Release exists
7. verify the release asset exists:
   - `cinderleaf-X.Y.Z-windows-portable.zip`
8. verify the published checksum matches:
   - `cinderleaf-X.Y.Z-windows-portable.zip.sha256`

## Nexus release steps

For each public release:

- upload the matching portable zip
- set the file version to the exact app version
- keep the mod description aligned with the current app behavior
- update screenshots if the UI has changed enough to make older shots misleading
- replace the header image if a cleaner one is available
- confirm the Nexus file page points users to the same current release line

## Public trust checks

Before announcing a release:

- the packaged app should not show stale version text
- the packaged `Cinderleaf.exe` should expose normal Windows product/file version metadata
- disabled actions should look disabled
- blocked write actions should show a clear reason
- any scan or trust caveats in the public description should be truthful and calm
- if the app is unsigned, say so plainly; reputation prompts and heuristic warnings cannot be fully solved without code signing

## After publishing

- verify the GitHub Release page and Nexus file page both show the correct version
- verify the public README still matches the current release
- monitor first user reports before starting the next risky workflow change
