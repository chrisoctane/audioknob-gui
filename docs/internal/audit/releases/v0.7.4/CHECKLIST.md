# Release Checklist

Release version: 0.7.4
Release date: 2026-02-14
Branch: master
Commit: pending-release-commit
PR: n/a
Tag: v0.7.4

## Required checks

1. G1 consistency
- Command: `python3 scripts/check_repo_consistency.py`
- Result: PASS

2. G1 compile
- Command: `python3 -m compileall -q audioknob_gui tests`
- Result: PASS

3. G3 full tests
- Command: `.venv/bin/python -m pytest -q`
- Result: PASS

4. Changelog entry
- Requirement: `CHANGELOG.md` contains heading `[0.7.4]`
- Result: PASS

5. Contract docs check
- Requirement: user/technical contract docs updated if release behavior changed
- Files: `PLAN.md`, `PROJECT_STATE.md`, `docs/KNOB_INTERACTIONS.md` (as applicable)
- Result: PASS

6. Packaging/build artifacts (if applicable)
- Artifacts: n/a
- Result: N/A

## Notes
- Waivers (if any): none
- Residual risks: none

Final status: PASS
