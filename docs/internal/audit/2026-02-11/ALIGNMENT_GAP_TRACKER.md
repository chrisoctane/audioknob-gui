# Alignment Gap Tracker (2026-02-12)

Purpose:
- Centralize extracted mismatches, deferred items, and research tasks
  discovered during the code/docs/audit alignment sweep.
- Keep primary docs clean by tracking unresolved work here with explicit IDs.

Scope of this sweep:
- Runtime code under `audioknob_gui/**` (focus: force-reset parity paths).
- User/technical contracts: `PLAN.md`, `PROJECT_STATE.md`.
- Audit package: `docs/internal/audit/2026-02-11/*.md`.
- Knob research notes: `docs/knobs.md`.

Tracker status:
- `Closed` (2026-02-12): all `AG-*` items resolved or explicitly de-scoped.

## Resolved in this sweep

1. `RES-001` force-reset parity wiring for `wireplumber_conf`:
   - GUI allowlist now includes `wireplumber_conf` to match worker support.
   - Contracts now list `pipewire_conf/wireplumber_conf` together.
2. `RES-002` stale doc reference cleanup:
   - `PROJECT_STATE.md` no longer references non-existent `BUGFEAT.md`.
3. `RES-003` `group_membership` special-case contract closure:
   - `PLAN.md` and `PROJECT_STATE.md` now state `group_membership` as an intentional immediate-action exception.
   - Audit artifacts (`FINDINGS_LEDGER.md`, `REMEDIATION_BATCHES.md`) now mark `AK-AUD-001`/`RB-002` resolved by contract hardening.
4. `RES-004` test execution completeness:
   - `pytest` was executed from `.venv` for both targeted parity tests and the full suite.
   - `VERIFICATION_REPORT.md` now records pass results for `AG-002`.
5. `RES-005` `AG-003` PipeWire RT limits policy closure:
   - `docs/knobs.md` now documents a concrete default policy (`95/-19/4194304`), override behavior, and Safe RT dependency semantics.
6. `RES-006` `AG-004` WirePlumber portability closure:
   - `docs/knobs.md` now documents WirePlumber 0.5+ drop-in path policy and USB match-scoping contract.
   - stale status wording was corrected to match runtime (file-content status model).
7. `RES-007` `AG-005` Pro Audio portability closure:
   - `docs/knobs.md` now defines deterministic `wpctl inspect` + `pactl list cards` fallback rules and name handling (`Pro Audio`/`pro-audio`).
   - Status behavior is covered by `tests/test_wpctl_profile_status.py`.
8. `RES-008` `AG-006` RTKit research gate closure:
   - `docs/knobs.md` now records authoritative-source-backed de-scope for apply/reset (read-only placeholder remains intentional).

## Gap ledger (all extracted items)

| ID | Area | Status | Evidence | Resolution notes | Exit criteria |
|---|---|---|---|---|---|
| `AG-003` | PipeWire RT limits value policy | Resolved | `docs/knobs.md` RT limits decision block | N/A | Met (policy documented and aligned to runtime defaults/overrides). |
| `AG-004` | WirePlumber ALSA USB config portability | Resolved | `docs/knobs.md` WirePlumber decision + status wording fix | N/A | Met (layout + scope contract documented; drift removed). |
| `AG-005` | Pro Audio profile discovery portability | Resolved | `docs/knobs.md` Pro Audio decision + `tests/test_wpctl_profile_status.py` | N/A | Met (fallback/naming/status contract documented and tested). |
| `AG-006` | RTKit tuning research gate | Resolved (de-scoped) | `docs/knobs.md` RTKit decision + source list | N/A | Met (authoritative evidence captured; apply/reset formally de-scoped). |

## Phased execution plan

### Phase A - Contract closure (completed)
1. `AG-001` closed by codifying `group_membership` as an intentional special-case in primary contracts/audit artifacts.

### Phase B - Verification completion (completed)
1. `AG-002` closed by running targeted parity tests and the full suite under `.venv` pytest, with outcomes recorded in `VERIFICATION_REPORT.md`.

### Phase C - Knob research backlog (completed)
1. Resolve `AG-003` through `AG-006` with source-backed decisions.
2. Update `docs/knobs.md`, `PLAN.md`, and `PROJECT_STATE.md` as decisions land.

Closeout:
1. `AG-003` through `AG-006` resolved (with `AG-006` resolved by explicit de-scope).
2. `PLAN.md` / `PROJECT_STATE.md` required no behavior-contract changes in this phase because runtime behavior did not change; `docs/knobs.md` was the primary contract source for these research items.

### Phase D - Final zero-drift sign-off (completed)
1. Re-run consistency and compile gates.
2. Re-run audit drift scan.
3. Close this tracker only when all `AG-*` rows are resolved or explicitly deferred with milestone and owner.

Closeout:
1. Consistency + compile gates re-run and passing.
2. Research-gap rows now all resolved/de-scoped.
3. Tracker closure criteria met.
