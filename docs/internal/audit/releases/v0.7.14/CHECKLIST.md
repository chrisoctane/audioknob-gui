# Release Checklist

Release version: 0.7.14
Release date: 2026-03-17
Branch: master
Commit: TBD
PR: n/a
Tag: v0.7.14

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
- Requirement: `CHANGELOG.md` contains heading `[0.7.14]`
- Result: PASS

5. Contract docs check
- Requirement: user/technical contract docs updated if release behavior changed
- Files: `PLAN.md`, `PROJECT_STATE.md`, `docs/KNOB_INTERACTIONS.md`, `docs/knobs.md`
- Result: PASS

6. Packaging/build artifacts (if applicable)
- Artifacts: audioknob-gui-0.7.14-0.noarch.rpm
- Result: PASS

## Notes
- Waivers (if any): none
- Residual risks: none

Final status: PASS
