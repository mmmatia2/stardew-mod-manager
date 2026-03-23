# Private Testing Guide (`0.3.0`)

This guide is for close-friend/private testing of the current portable build.

## Recommended setup

- configure both your real `Mods` path and a separate sandbox `Mods` path
- keep sandbox as the default install and test destination
- set sandbox and real archive paths before testing live-write flows
- if you plan to test update checks, add your Nexus API key if relevant

## Safe workflow

1. Scan the current target (`real Mods` or `sandbox Mods`).
2. Check updates and open provider pages manually when needed.
3. Download zip files manually.
4. In `Packages & Intake`, inspect one or more zip files.
5. Review per-package results.
6. Stage exactly one package into `Plan & Install`.
7. Build and review the plan before executing.
8. Prefer sandbox install first.
9. Use `real -> sandbox` sync and `sandbox -> real` promotion explicitly; do not treat promotion as casual sync-back.

## What to test

- basic startup and setup persistence
- scan/update/open-remote flow
- multi-zip selection in `Packages & Intake`
- whether per-package inspection remains understandable when one zip fails and another succeeds
- whether single-package staging from the inspected-package selector feels explicit
- sandbox install planning/execution
- selected-mod real->sandbox sync
- sandbox->real promotion preview/review and archive-aware replace
- install history and recovery inspection after changes

## Known limitations

- multi-zip intake currently ends at batch inspection plus single-package staging
- there is no true multi-package install planning or batch execution yet
- downloads remain manual
- this is a portable build, not an installer
- Windows reputation prompts/code-signing gaps are still expected
