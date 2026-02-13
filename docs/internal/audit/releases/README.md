# Release Checklist Artifacts

Purpose:
- Store one auditable release checklist per shipped version.
- Provide a verifiable artifact for release PRs and tag gates.

Required location:
- `docs/internal/audit/releases/v<version>/CHECKLIST.md`

Examples:
- `docs/internal/audit/releases/v0.7.2/CHECKLIST.md`
- `docs/internal/audit/releases/v0.8.0/CHECKLIST.md`

How to use:
1. Copy `docs/internal/audit/releases/RELEASE_CHECKLIST_TEMPLATE.md`
2. Create `docs/internal/audit/releases/v<version>/CHECKLIST.md`
3. Fill command evidence and outcomes.
4. Set `Final status: PASS` only when all required release checks pass.
5. Include this file in the release PR.

Enforcement:
- `scripts/run_quality_gate.py --gate g3 --release-version v<version>` checks:
  - changelog contains `[<version>]`
  - checklist artifact exists at the required path
  - checklist has exact line: `Release version: <version>`
  - checklist has exact line: `Final status: PASS`
