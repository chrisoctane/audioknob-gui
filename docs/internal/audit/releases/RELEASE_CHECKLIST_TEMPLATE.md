# Release Checklist

Release version: <x.y.z>
Release date: <YYYY-MM-DD>
Branch: <branch>
Commit: <sha>
PR: <link-or-id>
Tag: <vX.Y.Z>

## Required checks

1. G1 consistency
- Command: `python3 scripts/check_repo_consistency.py`
- Result: <PASS|FAIL>

2. G1 compile
- Command: `python3 -m compileall -q audioknob_gui tests`
- Result: <PASS|FAIL>

3. G3 full tests
- Command: `.venv/bin/python -m pytest -q`
- Result: <PASS|FAIL>

4. Changelog entry
- Requirement: `CHANGELOG.md` contains heading `[<x.y.z>]`
- Result: <PASS|FAIL>

5. Contract docs check
- Requirement: user/technical contract docs updated if release behavior changed
- Files: `PLAN.md`, `PROJECT_STATE.md`, `docs/KNOB_INTERACTIONS.md` (as applicable)
- Result: <PASS|FAIL|N/A>

6. Packaging/build artifacts (if applicable)
- Artifacts: <list>
- Result: <PASS|FAIL|N/A>

## Notes
- Waivers (if any): <none|details>
- Residual risks: <none|details>

Final status: <PASS|FAIL>
