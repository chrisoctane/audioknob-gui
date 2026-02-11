# Knob System Parity Audit Map (Draft)

## Purpose
This document is the system map for a full code audit of AudioKnob GUI. It defines:
- every major system that touches knob behavior
- each system's subsystems
- parity rules that keep knobs consistent
- audit checks for errors, conflicts, and improvement opportunities

Use this as the blueprint before making broad cleanup or parity changes.

## Scope
This draft covers runtime systems and supporting contracts for all knob paths:
- knob metadata and schema
- worker preview/apply/reset/status behavior
- GUI queue, status, config, tooltips, and conflict workflows
- simple mode inclusion and ownership locks
- transactions, presets, and diagnostics
- docs and consistency gates

## Non-goals (for this document)
- No behavior changes are made directly from this map.
- No speculative feature additions are treated as required parity work until approved.
- No large refactors are implied without a separate implementation plan.

## Audit principles
1. Evidence over intuition: every finding needs concrete proof.
2. Conservative safety: unknown or ambiguous states are treated as risk, not pass.
3. Reproducibility: another reviewer should be able to reproduce each finding.
4. Traceability: every finding ties to file references, knob IDs, and system rules.
5. Minimal-change remediation: fix scope should match finding scope unless explicitly expanded.

## Required evidence standard
Each finding should include all of the following:
1. Affected knob(s) and implementation kind(s).
2. Reproduction steps or static proof method.
3. Code reference(s) and, when relevant, command output summary.
4. Risk impact statement (user impact + rollback safety impact).
5. Proposed fix class:
   - contract/docs only
   - code-only
   - code + docs
   - cross-system parity batch

## Current inventory snapshot (for audit baseline)
- Knobs: `48`
- Categories: `10`
- Implementation kinds: `17`
- Conflict-map source families: `4`

## Coverage target matrix
For each knob, audit should explicitly classify pass/fail for these parity dimensions:
1. Registry/schema parity
2. Preview parity
3. Apply/reset parity
4. Status parity
5. Partial-reason parity
6. Config surface parity
7. Tooltip/info/requirements parity
8. Conflict/dependency parity
9. Transaction/preset parity
10. Test/docs parity

## Global parity contract (applies to all systems)
1. A knob must have one canonical definition in `config/registry.json`, synced to `audioknob_gui/data/registry.json`.
2. Every implementation kind used in registry must have deterministic status behavior (`applied`/`not_applied`/`partial`/`unknown`/`pending_reboot`/`not_applicable` where relevant).
3. Reset behavior must be surgical for shared files (remove only knob-owned content).
4. Queue behavior must be explicit (no hidden apply/reset).
5. Conflicts must be handled by warning and optional queued reset, never silent auto-disable.
6. Config-driven knobs must have a clear configured vs unconfigured status path.
7. Info text, status detail, and action behavior must not contradict each other.
8. Risk ranking and simple-mode eligibility must be documented and evidence-based.
9. Any behavior-affecting code change must update `PROJECT_STATE.md`; workflow-facing changes must update `PLAN.md`.
10. Consistency gate must pass before merge: `python3 scripts/check_repo_consistency.py` and `python3 -m compileall -q audioknob_gui`.

## Parity levels
- `Full parity`: preview + apply + reset + status + partial reason + info/tooltip + conflict integration + test coverage.
- `Special-case parity`: intentionally different UX path; exception must be documented with rationale and constraints.

## Finding severity and disposition
Use this scale for triage and remediation ordering.

| Severity | Definition | Required action |
|---|---|---|
| Blocker | Safety/data integrity risk or privilege model violation | Fix before any release work |
| Critical | High-probability functional regression or unrecoverable mismatch | Fix in immediate batch |
| High | Significant parity gap with realistic user impact | Fix in current audit cycle |
| Medium | Moderate gap or ambiguous behavior | Fix or explicitly defer with rationale |
| Low | Minor drift, copy mismatch, or maintainability issue | Queue as cleanup |

## Finding confidence scale
| Confidence | Meaning |
|---|---|
| High | Reproduced directly with deterministic evidence |
| Medium | Strong static evidence, runtime repro pending |
| Low | Plausible risk requiring targeted validation |

## Audit artifact structure
Use a stable structure so findings remain reusable for technical manuals.

Recommended artifact folders:
- `docs/internal/audit/<date>/inventory/`
- `docs/internal/audit/<date>/findings/`
- `docs/internal/audit/<date>/remediation-plan/`
- `docs/internal/audit/<date>/verification/`

Minimum artifacts:
1. Knob inventory snapshot (ID, kind, category, risk, simple eligibility).
2. Kind-level parity report.
3. Knob-level findings ledger.
4. Remediation batch plan with severity ordering.
5. Post-fix verification report.

Current audit package (this cycle):
- `docs/internal/audit/2026-02-11/KNOB_AUDIT_PLAN.md`
- `docs/internal/audit/2026-02-11/INVENTORY.md`
- `docs/internal/audit/2026-02-11/KIND_PARITY_MATRIX.md`
- `docs/internal/audit/2026-02-11/KNOB_WORKSHEET.md`

## System 1: Registry and Schema
### Subsystems
- Canonical knob registry: `config/registry.json`
- Packaged mirror registry: `audioknob_gui/data/registry.json`
- Schema definitions: `config/registry.schema.json`, `audioknob_gui/data/registry.schema.json`
- Runtime model loader: `audioknob_gui/registry.py`

### Rules
1. Registry files must remain byte-synced between canonical and packaged copies.
2. Every knob must define complete metadata fields required by schema.
3. Category and kind values must be valid schema enums.
4. `requires_root`, `requires_reboot`, `requires_groups`, and `requires_commands` must match real runtime behavior.
5. Any knob addition/removal requires knob-count contract update in `PROJECT_STATE.md`.

### Audit checks
- Errors: schema drift, invalid enum values, unsynced registry copies.
- Conflicts: metadata says one requirement; runtime uses another.
- Improvements: normalize inconsistent descriptions, command requirements, and category placement.

## System 2: Worker implementation core
### Subsystems
- Worker operations primitives: `audioknob_gui/worker/ops.py`
- Root/user command handlers: `audioknob_gui/worker/cli.py`
- Worker API bridge from GUI: `audioknob_gui/gui/worker_api.py`

### Rules
1. Queueable kinds must support apply and status paths.
2. Preview output must reflect actual apply behavior and targets.
3. Restore must use transaction data by default; force-reset must be explicit and conservative.
4. Root operations must only execute via pkexec wrapper path in GUI flows.
5. Unsupported kind handling must be explicit and logged.

### Audit checks
- Errors: kind present in registry but missing in apply/status/preview branch.
- Conflicts: apply path mutates resources not represented in preview or status.
- Improvements: reduce duplicated kind branching and align root/user paths.

## System 3: Kind-level parity matrix
### Subsystems
- Registry `impl.kind` usage set
- Kind handlers in `ops.py` and `cli.py`
- Force-reset support in `cli.py`

### Rules
1. Each active kind must be classified as either full parity or special-case parity.
2. Special-case kinds must document why they do not follow full queue parity.
3. If a kind is used by multiple knobs, consistency expectations apply across all knobs of that kind.

### Draft classification
| Kind | Parity class | Notes |
|---|---|---|
| `pam_limits_audio_group` | Full | queue/apply/status/restore/force-reset paths present |
| `sysctl_conf` | Full | shared-file surgical-line rules apply |
| `systemd_unit_toggle` | Full | service pre/post state effects tracked |
| `sysfs_glob_kv` | Full | not_applicable/unknown handling must stay conservative |
| `qjackctl_server_prefix` | Full | user-scope with runtime/process safeguards |
| `udev_rule` | Full | file presence + expected content status path |
| `rtirq_config` | Full | config + service dual-state partial reasons |
| `irq_affinity` | Full | multi-resource effects and partial reasons |
| `kernel_cmdline` | Full | boot config vs running kernel state split |
| `power_profile` | Full | backend resolution and conflict gating |
| `pipewire_conf` | Full | configured-vs-unconfigured handling required |
| `wireplumber_conf` | Full | configured-vs-unconfigured handling required |
| `wpctl_profile` | Full | device selection parity required |
| `user_service_mask` | Full | multi-service partial state handling |
| `baloo_disable` | Full | best-effort runtime command checks |
| `read_only` | Special-case | N/A apply/reset by design |
| `group_membership` | Special-case | join/leave action flow, not standard queue/apply path |

### Audit checks
- Errors: full-parity kinds missing any mandatory pipeline function.
- Conflicts: special-case kinds unintentionally included in queue paths.
- Improvements: convert safe special-cases to full parity where worthwhile.

## System 4: GUI queue and execution pipeline
### Subsystems
- Queue state persistence: `main_window.py` (`_save_queue`, `_update_queue_ui`)
- Queue action toggles: `actions.py`
- Queue execution and result handling: `_on_apply_queue`, `_on_apply_queue_finished`

### Rules
1. Queue state must survive restart and remain deterministic.
2. Busy state must block overlapping operations.
3. Queue apply/reset must clear only successful actions.
4. Prompt/confirm flows must show exact actions before execution.
5. Queue origin differences (simple/full) must not bypass safety gates.

### Audit checks
- Errors: stale queued action states, busy-state races, mis-cleared queue entries.
- Conflicts: conflict prompt and queue payload disagree on actual execution set.
- Improvements: simplify queue mutation points and add stronger unit coverage.

## System 5: Status and partial-reason diagnostics
### Subsystems
- Status polling and normalization: `audioknob_gui/gui/status.py`
- Worker status computation: `audioknob_gui/worker/ops.py`
- CLI status dialog details: `show_cli_status`

### Rules
1. Status must be conservative (`unknown` when not provable).
2. `partial` must include a concrete `partial_reason` when possible.
3. Status detail should include live evidence paths/values.
4. Configured-vs-unconfigured knobs must not report false applied states.
5. Reboot-sensitive knobs must distinguish running vs boot-config state.

### Audit checks
- Errors: false `applied`, missing partial reasons, inconsistent status label mapping.
- Conflicts: worker and GUI disagreement for same knob state.
- Improvements: standardize partial-reason style and coverage per kind.

## System 6: Conflict and dependency system
### Subsystems
- Conflict map and helpers: `audioknob_gui/gui/conflicts.py`
- Interaction contract: `docs/KNOB_INTERACTIONS.md`
- Conflict UI and queue reset actions: `main_window.py`

### Rules
1. Conflict map and interaction docs must stay aligned.
2. Only active/queued participants should count in conflict indicators.
3. Conflict prompts must provide apply-anyway and queue-reset paths.
4. Dependency resets must be explicit and reversible.
5. Backend-specific conflict pruning must be deterministic and documented.

### Audit checks
- Errors: undocumented conflict logic, stale map entries, missing counterexamples.
- Conflicts: docs say conflict exists but runtime does not flag (or inverse).
- Improvements: expand map coverage where documented interactions are still warning-only.

## System 7: Config and dialog system
### Subsystems
- Knob config routing: `audioknob_gui/gui/knobs/registry.py`
- Dialog implementations: `audioknob_gui/gui/dialogs/*`
- Per-knob config state persistence: `audioknob_gui/gui/state.py`

### Rules
1. If a knob needs pre-apply configuration, UI must expose configure path.
2. Configured values must flow into preview/apply/status consistently.
3. Unconfigured required fields must lock or block apply clearly.
4. Config controls must honor wheel-safety and style parity.
5. New dialog capability in one comparable knob must trigger cross-knob parity review.

### Audit checks
- Errors: configure UI exists but apply/status ignore config.
- Conflicts: dialog defaults conflict with safety or dependency rules.
- Improvements: shared dialog patterns, validation reuse, clearer preset buttons.

## System 8: Info, tooltip, and requirements UX
### Subsystems
- Info popup builders and buttons: `audioknob_gui/gui/knobs/registry.py`
- Requirements checks: `audioknob_gui/gui/requirements.py`
- Table requirement/tooltips/status badges: `audioknob_gui/gui/table.py`

### Rules
1. Info content must reflect true behavior and constraints.
2. Requirement locks (groups/commands/dependencies) must match backend requirements.
3. Tooltips should explain lock reason and required next action.
4. Info text and conflict docs must not diverge.

### Audit checks
- Errors: stale info text, missing lock rationale, mismatch with real requirements.
- Conflicts: requirement gate allows apply but worker rejects.
- Improvements: unify wording and include quick remediation paths.

## System 9: Simple AudioKnob system
### Subsystems
- Dial level model: `audioknob_gui/gui/simple_mode.py`
- Simple queue composition and summary UI: `main_window.py`
- Simple ownership lock metadata: `main_window.py`

### Rules
1. Dial movement composes queue only; never auto-applies.
2. Dial-up composes apply actions; dial-down composes resets for managed knobs.
3. Safety-latch tiers must remain explicit and documented.
4. Simple-owned locks must only clear via explicit release action.
5. Simple inclusion/risk ordering must be evidence-backed in `PROJECT_STATE.md`.

### Audit checks
- Errors: dial level and queue payload mismatch, lock drift, level summary mismatch.
- Conflicts: simple composition bypasses dependencies/conflict gates.
- Improvements: add stronger tests for level transitions and managed-lock lifecycle.

## System 10: Presets, baseline, and transactions
### Subsystems
- Baseline/reference/factory state model: `gui/state.py`, `main_window.py`
- Transaction engine: `core/transaction.py`
- Restore/default reset flows: worker CLI + GUI actions

### Rules
1. Every reversible change should produce transaction evidence before write.
2. Preset restore must remain explicit and visible to user.
3. Factory/reference semantics must be immutable where specified.
4. Mismatch/import flows must preserve safe fallback behavior.

### Audit checks
- Errors: missing backup before write, incomplete restore paths.
- Conflicts: preset-match metadata overrides operational status.
- Improvements: tighten diff summaries and restore diagnostics.

## System 11: Diagnostics and testing tools
### Subsystems
- RT scanner: `audioknob_gui/testing/rtcheck.py`
- Jitter and XRUN tools: `audioknob_gui/testing/*`, GUI dialogs
- Tests: `tests/*`

### Rules
1. Scanner fix links must point to actionable knobs or explicit manual commands.
2. Read-only checks must never mutate system state.
3. Test-only knobs remain excluded from simple mode risk set.
4. New behavior should add or update focused tests.

### Audit checks
- Errors: stale fix links, false pass/fail criteria, missing test cases.
- Conflicts: scanner recommendation contradicts conflict map/safety model.
- Improvements: add automated parity tests by kind and by simple tier.

## System 12: Packaging, privilege, and deployment
### Subsystems
- Polkit and worker wrapper: `polkit/*`, `/usr/libexec/audioknob-gui-worker`
- Build packaging: `packaging/*`
- Entry points and module install paths

### Rules
1. Root operations must run through pkexec worker path.
2. Packaged entrypoints must import and execute under target distro python layout.
3. Version/release metadata must stay aligned across packaging and docs.

### Audit checks
- Errors: broken imports in packaged builds, privilege path regressions.
- Conflicts: local dev behavior differs from packaged behavior.
- Improvements: expand package smoke-test checklist for rpm/deb parity.

## System 13: Documentation and anti-drift contracts
### Subsystems
- User contract: `PLAN.md`
- Agent technical contract: `PROJECT_STATE.md`
- Interaction map: `docs/KNOB_INTERACTIONS.md`
- Consistency gate: `scripts/check_repo_consistency.py`

### Rules
1. Any behavior/architecture change updates `PROJECT_STATE.md` in same change.
2. Any user workflow/UI change updates `PLAN.md` in same change.
3. Conflict/dependency changes update `docs/KNOB_INTERACTIONS.md`.
4. Contract claims (release version, knob count, status vocabulary) must match code.

### Audit checks
- Errors: code/doc drift, stale release claims, stale knob counts.
- Conflicts: docs prescribe workflow different from GUI behavior.
- Improvements: promote additional semantic checks into consistency script.

## Cross-system extension rules (when adding features)
Use this mandatory impact checklist for any new knob feature (dialog, status enhancement, conflict logic, etc.):
1. Define feature scope and impacted knob kinds.
2. List all knobs sharing those kinds/categories.
3. Decide parity target: all knobs or documented exception list.
4. Update registry metadata if behavior or requirements change.
5. Update worker preview/apply/reset/status as required.
6. Update GUI config/info/tooltip/lock states.
7. Update conflict map and interaction docs if risk interaction changes.
8. Add or update tests for queue, status, and conflict behavior.
9. Update `PROJECT_STATE.md` and `PLAN.md` contracts.
10. Run consistency and compile gates.

## Audit gating rules
The audit is only considered complete when all are true:
1. Every knob has a completed worksheet entry.
2. Every implementation kind has a parity disposition (`full` or `special-case`) with rationale.
3. All Blocker/Critical findings are resolved.
4. Remaining deferred findings have explicit rationale, owner, and target milestone.
5. Consistency and compile gates pass on final remediation branch.

## Per-knob audit worksheet template
Use this template for each knob during deep audit.

```markdown
### <knob_id>
- Category / kind:
- Risk / simple eligibility:
- Dependencies:
- Conflict entries:
- Config surface:

Checks
- Registry/schema parity: pass/fail/notes
- Preview parity: pass/fail/notes
- Apply/reset parity: pass/fail/notes
- Status + partial reason parity: pass/fail/notes
- Info/tooltip/requirements parity: pass/fail/notes
- Conflict handling parity: pass/fail/notes
- Preset/transaction parity: pass/fail/notes
- Tests/docs parity: pass/fail/notes

Findings
- Errors:
- Potential conflicts:
- Improvements:
```

## Suggested audit execution plan (next step)
Phase 1: Inventory freeze
1. Capture registry snapshot with category/kind counts.
2. Capture conflict-map snapshot and current simple-mode inclusion snapshot.
3. Freeze baseline commit hash for audit reproducibility.

Phase 2: Kind-level parity scan
1. For each implementation kind, verify preview/apply/reset/status coverage.
2. Identify special-case behavior and confirm it is intentional/documented.
3. Log systemic gaps before knob-by-knob review.

Phase 3: Knob-by-knob parity scan
1. Audit by category groups:
   - permissions, vm, cpu, power
   - stack, services
   - irq, kernel
   - testing/read-only
2. Complete worksheet for every knob.
3. Tag each finding with severity + confidence.

Phase 4: Cross-system consistency review
1. Compare info/tooltips/conflict docs against runtime behavior.
2. Compare scanner fix mappings against actionable knob support.
3. Compare simple-mode rule docs against queue composition behavior.

Phase 5: Remediation planning
1. Cluster findings into low-risk and high-risk change batches.
2. Order by severity and blast radius.
3. Define verification steps per batch before implementation.

Phase 6: Verification and closeout
1. Re-run worksheet checks on fixed knobs.
2. Re-run consistency and compile gates.
3. Publish final audit summary with resolved/deferred ledger.

## Audit command baseline
Use these commands repeatedly during audit cycles:
1. `python3 scripts/check_repo_consistency.py`
2. `python3 -m compileall -q audioknob_gui`
3. `python3 -m audioknob_gui.worker.cli status`
4. `python3 -m audioknob_gui.worker.cli preview <knob_id>`
5. `python3 -m audioknob_gui.worker.cli list-pending`
6. `python3 -m audioknob_gui.worker.cli list-changes`

## Initial gap candidates to verify first
These are not final defects; verify during audit.
1. Special-case kinds in simple-mode queue paths should be explicitly reviewed for queueability constraints.
2. Conflict-map runtime coverage vs `docs/KNOB_INTERACTIONS.md` narrative coverage should be audited for intentional vs missing detection.
3. Dialog/config parity should be reviewed for all configurable PipeWire and kernel-core families to ensure consistent lock/status/info behavior.
