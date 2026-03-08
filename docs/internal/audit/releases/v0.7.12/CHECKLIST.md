# Release Checklist

Release version: 0.7.12
Release date: 2026-03-08
Branch: master
Commit: TBD
PR: n/a
Tag: v0.7.12

## Required checks

1. G1 consistency
- Command: `python3 scripts/check_repo_consistency.py`
- Result: PASS

2. G1 compile
- Command: `python3 -m compileall -q audioknob_gui tests`
- Result: PASS

3. G3 full tests
- Command: `.venv/bin/python -m pytest -q`
- Result: PASS (154 passed)

4. Changelog entry
- Requirement: `CHANGELOG.md` contains heading `[0.7.12]`
- Result: PASS

5. Contract docs check
- Requirement: user/technical contract docs updated if release behavior changed
- Files: `PROJECT_STATE.md`, `docs/KNOB_INTERACTIONS.md`
- Result: PASS

6. Packaging/build artifacts (if applicable)
- Artifacts: audioknob-gui_0.7.12_all.deb, audioknob-gui-0.7.12-0.noarch.rpm
- Result: PENDING

## Notes
- Waivers (if any): none
- Residual risks: none

Final status: PASS
