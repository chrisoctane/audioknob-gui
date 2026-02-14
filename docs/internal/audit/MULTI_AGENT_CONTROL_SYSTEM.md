# Multi-Agent Control System (Policy-Driven, Self-Limiting)

Purpose:
- Define a reliable multi-agent architecture for software delivery where agents
  stay in scope, self-audit, and iteratively improve process efficiency.
- Keep safety and correctness deterministic by making policy enforcement the
  authority, not any individual model output.

---

## 1) Design goals

1. Build software with bounded risk and predictable output quality.
2. Prevent agent drift, opportunistic edits, and scope expansion loops.
3. Detect and correct faults in both code output and process behavior.
4. Improve execution efficiency over time without weakening safety.
5. Allow role expansion (new agents) only under controlled governance.

## 2) Non-goals

1. Fully autonomous self-modifying system with no human oversight.
2. Unlimited open-ended planning/execution loops.
3. Trust-based operation where policy checks are optional.

---

## 3) Core operating principle

The system is controlled by a deterministic orchestrator and machine-readable
policy. Agents can propose and execute work, but they cannot define success
criteria, broaden scope, or override safety controls.

`Policy + Controller + Verifier` are authoritative.

---

## 4) Reliability invariants (must always hold)

1. No write action occurs without an active task policy.
2. Changed files must remain inside policy allowlist.
3. Change size must remain under policy caps (file count and LOC limits).
4. Required validation commands must run and pass before completion.
5. Every cycle has an evidence packet (inputs, outputs, checks, decision).
6. Unresolved blocker/critical failures cannot be carried forward silently.
7. Agents cannot edit policy artifacts unless policy explicitly permits it.
8. Loop ends at deterministic terminal states: `DONE`, `ESCALATE`, or `ABORT`.

---

## 5) System components

### 5.1 Controller (single authority)
- Runs the finite-state workflow.
- Loads active policy and rejects out-of-policy actions.
- Decides transition at each phase.

### 5.2 Policy store
- Machine-readable policy (batch ID, scope, limits, required checks).
- Versioned and immutable per cycle except via approved policy update path.

### 5.3 Role agents
- `Intake Manager`: normalizes user intent into an actionable task packet.
- `Planner`: proposes minimal steps and target files.
- `Critic`: challenges plan for policy/risk violations before execution.
- `Executor`: performs approved edits only.
- `Verifier`: runs tests/gates and collects execution evidence.
- `Safety Regulator`: validates policy conformance and exception handling.
- `Auditor`: logs defects, root causes, and disposition.
- `Process Optimizer`: proposes process improvements (not direct policy edits).

### 5.4 Evidence ledger
- Append-only cycle artifacts:
  - plan
  - diff summary
  - command outputs
  - gate results
  - transition decision

---

## 6) Finite-state loop

```text
TASK_INTAKE
  -> PLAN
  -> CRITIQUE
  -> EXECUTE
  -> VERIFY
  -> AUDIT
  -> (DONE | NEXT_CYCLE | ESCALATE | ABORT)
```

Transition rules:
1. `PLAN -> CRITIQUE`: only if plan references policy-constrained scope.
2. `CRITIQUE -> EXECUTE`: only if no blocker policy violations.
3. `EXECUTE -> VERIFY`: only if patch applies cleanly and stays in scope.
4. `VERIFY -> AUDIT`: always (audit is mandatory).
5. `AUDIT -> DONE`: only if all required checks pass and no open blockers.
6. `AUDIT -> NEXT_CYCLE`: only if remaining work is explicitly in-scope.
7. `AUDIT -> ESCALATE`: if repeated failure threshold is exceeded.
8. `AUDIT -> ABORT`: safety breach, policy breach, or unrecoverable state.

Loop bounds:
1. `max_cycles` per task (for example: `5`).
2. `max_verify_failures` before escalation (for example: `2`).
3. `max_runtime_minutes` per task batch.

---

## 7) Handoff contract (required between roles)

Each role emits a structured handoff packet:

```json
{
  "task_id": "T-2026-02-13-001",
  "cycle": 2,
  "batch_id": "STAB-002",
  "policy_version": "v1",
  "requested_scope": ["docs/internal/audit/MULTI_AGENT_CONTROL_SYSTEM.md"],
  "planned_actions": ["add_doc"],
  "changed_files": [],
  "commands_run": [],
  "results": {"checks": []},
  "decision": "approve|revise|reject|done|escalate",
  "reasons": []
}
```

Handoff validity checks:
1. Required fields present.
2. Scope intersects policy allowlist only.
3. Cycle and task IDs are monotonic and consistent.
4. Decision is valid for current state.

---

## 8) Self-correction model

Fault classes:
1. Scope drift (out-of-allowlist files).
2. Hallucinated behavior claims (no evidence in code/tests).
3. Missing or wrong validation commands.
4. Reintroduced defects/regressions.
5. Excessive churn (repeated edits with no convergence).

Automatic correction actions:
1. Reject cycle and rollback to last approved state.
2. Generate corrective task packet with narrowed scope.
3. Require added regression test before retry.
4. Raise severity and trigger escalation threshold.

No cycle may proceed without resolving prior cycle policy violations.

---

## 9) Self-audit model

At the end of every cycle, `Auditor` must produce:
1. Findings list (severity + confidence + evidence).
2. Policy compliance summary.
3. Root-cause classification:
   - prompt ambiguity
   - planning defect
   - execution defect
   - verification gap
   - policy gap
4. Disposition:
   - resolved now
   - deferred with rationale
   - escalated

Audit output is machine-checked, not free-form narrative only.

---

## 10) Controlled self-improvement model

The system improves itself through a separate improvement pipeline:

1. `Process Optimizer` proposes improvement candidates.
2. Candidates are expressed as explicit hypotheses:
   - expected benefit
   - risk level
   - measurable metric
   - rollback plan
3. `Safety Regulator` validates policy impact.
4. Human approval is required for policy changes.
5. Approved changes run as dedicated bounded tasks.

Important:
- Agents may propose policy/process changes.
- Agents may not self-apply policy/process changes without approval.

---

## 11) Dynamic role creation (new agents)

New role creation uses a controlled registration process:
1. Submit role spec:
   - role name
   - permitted actions
   - read/write scope
   - required inputs/outputs
   - failure modes
2. Run sandbox trial on historical tasks.
3. Compare against baseline KPIs.
4. Admit role only if safety and quality do not regress.

Example new roles:
- `Manager`: prioritizes queued tasks by severity and dependency graph.
- `Safety Regulator`: stricter policy interpretation and escalation.
- `Performance Steward`: tracks cycle time and proposes safe efficiency gains.

---

## 12) Efficiency controls (without safety loss)

1. Parallelize read-only analysis stages only.
2. Cache deterministic checks when inputs are unchanged.
3. Keep patch size limits low to reduce review/retest overhead.
4. Prefer smallest viable diff to satisfy task objective.
5. Batch related test selectors, but never skip required checks.

Efficiency KPIs:
1. Pass rate per cycle.
2. Mean cycles-to-done.
3. Reopen rate (regressions after pass).
4. Scope violation rate.
5. Time spent in verify vs fix.

---

## 13) Repo integration baseline

Current repo controls map well to this architecture:
1. Policy/batch scope: `docs/internal/audit/STABILIZATION_STATE.md`
2. Enforcer: `scripts/check_repo_consistency.py`
3. Gate runner: `scripts/run_quality_gate.py`
4. Contracts: `AGENTS.md`, `PLAN.md`, `PROJECT_STATE.md`

Recommended next implementation step:
1. Add explicit machine-readable policy file (`policy.yaml`) mirroring
   `STABILIZATION_STATE.md`.
2. Add a lightweight controller script that enforces:
   - state transitions
   - cycle limits
   - handoff packet validation
3. Store cycle artifacts under `docs/internal/audit/cycles/<task_id>/`.

---

## 14) Definition of reliable operation

The system is considered reliable when:
1. No out-of-scope edits reach final output.
2. Required checks are never skipped silently.
3. Regressions are caught by verification before completion.
4. Cycle count remains bounded and converges on task completion.
5. Process improvements reduce cycle cost without lowering pass quality.

This yields a practical, self-limiting multi-agent software system:
- adaptive in method,
- strict in control,
- auditable in outcomes.
