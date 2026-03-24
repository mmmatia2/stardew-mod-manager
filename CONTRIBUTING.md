# Contributing to Cinderleaf

Thanks for contributing.

## Before you open a pull request

- keep changes small and focused
- avoid mixing feature work with unrelated cleanup
- preserve the app's safety-first behavior, especially around live `Mods` writes
- do not add scraping, browser automation for downloads, or premium-bypass behavior

## Local setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,build]"
```

## Validation

Run the unit suite before opening a PR:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit -q
```

If your change affects packaging, also run:

```powershell
.\.venv\Scripts\python.exe scripts\build_windows_portable.py
```

## Scope expectations

- sandbox remains the recommended test path
- Compare stays read-only unless a specifically approved stage changes it
- real-Mods operations should remain explicit, reviewable, and recoverable
- provider-compliant manual download flow remains the default

## Issues and feature requests

Please use the GitHub issue templates and include:

- app version
- Windows version
- expected behavior
- actual behavior
- whether the issue happened in real `Mods`, sandbox `Mods`, compare, or restore/import flow

## License reminder

This repository is source-available under **PolyForm Noncommercial 1.0.0**. Contributions are accepted under that same license model.
