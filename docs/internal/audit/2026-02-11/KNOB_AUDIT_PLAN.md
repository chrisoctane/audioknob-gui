# Knob Audit Plan (2026-02-11)

## Objective
Execute a full-system parity audit for all knob paths and produce a defensible remediation backlog before finalization.

## Source blueprint
- `docs/KNOB_SYSTEM_AUDIT_MAP.md`
- `PLAN.md`
- `PROJECT_STATE.md`
- `docs/KNOB_INTERACTIONS.md`

## Scope
In-scope:
1. Registry/schema parity
2. Worker preview/apply/reset/status parity
3. GUI queue/conflict/config/tooltip parity
4. Simple-mode composition and ownership-lock parity
5. Transaction/preset and diagnostics parity
6. Test/docs parity

Out-of-scope:
1. New feature implementation (unless required to close a blocker)
2. Broad refactors unrelated to findings

## Phase tracker (resume-friendly)
- `[x]` Phase 0: Audit scaffold/bootstrap (docs + templates)
- `[x]` Phase 1: Baseline freeze and inventory lock
- `[x]` Phase 2: Kind-level parity audit
- `[x]` Phase 3: Knob-level parity audit
- `[x]` Phase 4: Cross-system coherence audit
- `[x]` Phase 5: Remediation batch planning
- `[ ]` Phase 6: Post-fix verification and closeout

Current resume point: `Phase 6`

## Phase details

### Phase 0: Audit scaffold/bootstrap
Goal:
- Ensure the audit package and templates exist before evidence collection.

Inputs:
- `docs/KNOB_SYSTEM_AUDIT_MAP.md`

Tasks:
1. Create audit package directory and core files.
2. Seed inventory/matrix/worksheet from current registry snapshot.
3. Define finding severity/confidence taxonomy.

Outputs:
- `INVENTORY.md`
- `KIND_PARITY_MATRIX.md`
- `KNOB_WORKSHEET.md`
- `FINDINGS_LEDGER.md`
- `REMEDIATION_BATCHES.md`
- `VERIFICATION_REPORT.md`

Exit criteria:
1. All artifact files exist and are non-empty.
2. Inventory totals match registry snapshot.

Status: `Complete`

### Phase 1: Baseline freeze and inventory lock
Goal:
- Lock a reproducible technical baseline before parity judgment starts.

Inputs:
- Current branch + commit metadata
- Existing scaffold files

Tasks:
1. Record branch, commit hash, and timestamp in `INVENTORY.md`.
2. Re-run and confirm knob/category/kind totals.
3. Run baseline gates:
   - `python3 scripts/check_repo_consistency.py`
   - `python3 -m compileall -q audioknob_gui`
4. Note any pre-existing repo drift unrelated to audit findings.

Outputs:
- Updated `INVENTORY.md` baseline block
- Initial entries in `VERIFICATION_REPORT.md`

Exit criteria:
1. Baseline commands pass (or failures explicitly logged with reason).
2. Inventory totals are locked for this cycle.

Resume marker to set when done:
- `Current resume point: Phase 2`

Status: `Complete (2026-02-12)`

### Phase 2: Kind-level parity audit
Goal:
- Determine systemic parity health by implementation kind before per-knob drilling.

Inputs:
- `KIND_PARITY_MATRIX.md`
- Worker and GUI kind handlers

Tasks:
1. For each active kind, mark parity dimensions pass/fail/partial.
2. Capture shared systemic gaps once (avoid repeating per knob).
3. Link each gap to code references and required evidence.

Outputs:
- Completed parity columns in `KIND_PARITY_MATRIX.md`
- Seed systemic findings in `FINDINGS_LEDGER.md`

Exit criteria:
1. All listed kinds have parity disposition.
2. Every failed kind row has at least one evidence-backed finding.

Resume marker to set when done:
- `Current resume point: Phase 3`

Status: `Complete (2026-02-12)`

### Phase 3: Knob-level parity audit
Goal:
- Validate each knob against the full parity contract and detect drift within same-kind knobs.

Inputs:
- `KNOB_WORKSHEET.md`
- Kind-level gaps from Phase 2

Tasks:
1. Review each knob worksheet section and mark parity dimensions.
2. Assign severity + confidence for each finding.
3. Cross-check same-kind knobs for inconsistent behavior or metadata.
4. Confirm status/config/conflict/info/partial-reason parity per knob.

Outputs:
- Filled `KNOB_WORKSHEET.md`
- Expanded `FINDINGS_LEDGER.md`

Exit criteria:
1. All knob sections in worksheet are reviewed.
2. Every finding has severity, confidence, and file references.

Resume marker to set when done:
- `Current resume point: Phase 4`

Status: `Complete (2026-02-12)`

### Phase 4: Cross-system coherence audit
Goal:
- Validate that docs, UI, worker behavior, and conflict/dependency rules are aligned.

Inputs:
- Findings from Phases 2-3
- `PLAN.md`, `PROJECT_STATE.md`, `docs/KNOB_INTERACTIONS.md`

Tasks:
1. Validate conflict-map runtime behavior against docs.
2. Validate info/tooltips/requirements against actual worker behavior.
3. Validate simple-mode lock/queue rules against implementation.
4. Raise coherence findings for any contract drift.

Outputs:
- Coherence findings appended to `FINDINGS_LEDGER.md`
- Contract updates list (if required) in `REMEDIATION_BATCHES.md`

Exit criteria:
1. No unresolved doc-vs-runtime mismatches remain untracked.
2. Cross-system drift items are explicitly batched.

Resume marker to set when done:
- `Current resume point: Phase 5`

Status: `Complete (2026-02-12)`

### Phase 5: Remediation batch planning
Goal:
- Convert findings into executable, low-risk implementation batches.

Inputs:
- Final findings ledger

Tasks:
1. Group findings by severity and blast radius.
2. Define batch ordering (Blocker/Critical/High first).
3. Assign verification steps and expected gates for each batch.
4. Record deferred items with rationale and milestone.

Outputs:
- `REMEDIATION_BATCHES.md` finalized

Exit criteria:
1. Every finding is either batched or explicitly deferred.
2. Batch order is release-safe and testable.

Resume marker to set when done:
- `Current resume point: Phase 6`

Status: `Complete (2026-02-12)`

### Phase 6: Post-fix verification and closeout
Goal:
- Verify remediation outcomes and publish final audit disposition.

Inputs:
- Implemented remediation batches

Tasks:
1. Re-validate fixed findings against worksheet evidence paths.
2. Re-run gates:
   - `python3 scripts/check_repo_consistency.py`
   - `python3 -m compileall -q audioknob_gui`
3. Mark findings as resolved/deferred with timestamps.
4. Publish final verification summary and residual risk notes.

Outputs:
- `VERIFICATION_REPORT.md` finalized
- `FINDINGS_LEDGER.md` with final dispositions

Exit criteria:
1. All Blocker/Critical findings resolved.
2. Remaining deferred items include explicit rationale and milestone.
3. Gates pass at closeout (or failures are documented as release blockers).

Resume marker to set when done:
- `Current resume point: Closed`

## Handoff protocol (for pause/resume)
Before ending any session:
1. Update `Current resume point` in this file.
2. Add date-stamped progress notes to:
   - `FINDINGS_LEDGER.md` (new/updated findings)
   - `VERIFICATION_REPORT.md` (commands run + result)
3. Ensure partially reviewed knobs/kinds are tagged `in_progress` in their files.
4. Commit docs if they represent stable progress.

At next session start:
1. Open this file and continue from `Current resume point`.
2. Re-run baseline commands if code changed since last audit note.
3. Continue only one active phase at a time.

## Severity policy
- Blocker: fix immediately before release work continues.
- Critical: fix in next batch; no deferral without explicit approval.
- High: fix in current cycle unless formally deferred.
- Medium/Low: can defer with rationale and owner.

## Evidence policy
Every finding entry must include:
1. Affected knob ID(s)
2. Reproduction/static proof
3. File references
4. Impact statement
5. Proposed fix class

## Recommended execution slices
Use these slices to keep sessions focused and resumable:
1. `Slice A`: permissions + vm + cpu + power
2. `Slice B`: stack + services
3. `Slice C`: irq + kernel
4. `Slice D`: testing/read-only + coherence cleanup

## Baseline commands
1. `python3 scripts/check_repo_consistency.py`
2. `python3 -m compileall -q audioknob_gui`
3. `python3 -m audioknob_gui.worker.cli status`
4. `python3 -m audioknob_gui.worker.cli preview <knob_id>`
5. `python3 -m audioknob_gui.worker.cli list-pending`
6. `python3 -m audioknob_gui.worker.cli list-changes`

## Final audit exit criteria
1. All knobs audited in worksheet.
2. All implementation kinds have parity disposition.
3. All Blocker/Critical findings resolved.
4. Deferred findings documented with rationale and milestone.
5. Consistency and compile gates pass after remediation.
