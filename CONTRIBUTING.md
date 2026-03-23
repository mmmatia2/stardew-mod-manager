# Contributing

Thanks for contributing.

## Before You Open A Pull Request

- keep changes small and focused
- avoid mixing feature work with unrelated cleanup
- preserve the app's safety-first behavior, especially around live `Mods` writes
- do not add scraping, browser automation for downloads, or premium-bypass behavior

## Local Setup

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

## Scope Expectations

- sandbox remains the recommended test path
- compare should stay read-only unless an approved stage explicitly changes that
- real-Mods operations should remain explicit, reviewable, and recoverable
- provider-compliant manual download flow remains the default

## Reporting Issues

When filing a bug, include:

- app version
- Windows version
- what you expected
- what happened instead
- whether the issue happened in real `Mods`, sandbox `Mods`, or restore/import flow
