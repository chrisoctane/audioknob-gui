# audioknob-gui: Plan

## Quick start (for you)

### Run from a repo checkout (recommended for development)

```bash
cd /path/to/audioknob-gui
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e .
sudo ./packaging/install-polkit.sh
bin/audioknob-gui
```

For repo runs that apply root/system knobs, `sudo ./packaging/install-polkit.sh` is required so the pkexec worker points at the same checkout. The app now refuses privileged actions in dev mode if the GUI repo and root worker repo do not match.

### Desktop launcher (optional, for local testing)

This generates and installs a `.desktop` entry so you can launch from your application menu:

```bash
./scripts/install-desktop.sh
```

The script auto-detects:
- **Repo root**: Uses the script's location to find the repository
- **Python**: Prefers `.venv/bin/python3` if present, falls back to system `python3`
- **Environment**: Sets `AUDIOKNOB_DEV_REPO` so imports work correctly

Root/system knobs still need `sudo ./packaging/install-polkit.sh` so the fixed-path pkexec worker uses the same repo checkout.

The generated `.desktop` file is written to `~/.local/share/applications/audioknob-gui.desktop`.

### Install on openSUSE Tumbleweed (RPM)

We support **RPM packaging on openSUSE Tumbleweed**.
Current support is **Tumbleweed only**.

Build a local RPM from this repo:

```bash
cd /home/chris/audioknob-gui
./packaging/opensuse/build-rpm.sh
```

Local RPM builds package the tracked working tree, so modified tracked files are included even if they are not committed yet. Untracked files are excluded; `git add` any new runtime file before building.

Install it:

```bash
sudo zypper --no-gpg-checks install -y ~/rpmbuild/RPMS/noarch/audioknob-gui-*.rpm
```

Uninstall it:

```bash
sudo zypper remove -y audioknob-gui
```

Notes:
- This installs the GUI launcher `audioknob-gui` and the worker `audioknob-worker`.
- Root knob/system operations use polkit + fixed-path worker wrapper at `/usr/libexec/audioknob-gui-worker`.
- A small set of explicit GUI maintenance actions (group membership, package install, bootloader follow-up, reboot, root-log clear) use allowlisted direct pkexec commands via `audioknob_gui/gui/worker_api.py`.

### Install on Debian/Ubuntu (DEB)

Build a local DEB from this repo:

```bash
cd /home/chris/audioknob-gui
./packaging/debian/build-deb.sh
```

Install it:

```bash
sudo apt-get install -y ~/debbuild/audioknob-gui_*_all.deb
```

Uninstall it:

```bash
sudo apt-get remove -y audioknob-gui
```

### Set up pre-commit hooks (recommended for contributors)

```bash
pip install pre-commit && pre-commit install
```

This runs `scripts/check_repo_consistency.py` before each commit to catch registry/doc drift, verify release-version/knob-count/status-label contracts (including `pyproject.toml`/`audioknob_gui.__version__`/`PROJECT_STATE.md` sync), and require `docs/KNOB_INTERACTIONS.md` updates when conflict/knob behavior paths change.

### Run the worker CLI directly (debugging)

```bash
python3 -m audioknob_gui.worker.cli --help
python3 -m audioknob_gui.worker.cli status
python3 -m audioknob_gui.worker.cli preview rt_limits_audio_group

# Reset/transactions debugging helpers:
python3 -m audioknob_gui.worker.cli list-changes   # historical audit (all transactions ever)
python3 -m audioknob_gui.worker.cli list-pending   # current-state preview (what still needs reset)
python3 -m audioknob_gui.worker.cli reset-defaults --scope user
# root phase (requires pkexec):
pkexec /usr/libexec/audioknob-gui-worker reset-defaults --scope root
```

## v0.7.0 plan: Simple AudioKnob mode

This section tracks v0.7.0 simple mode. Core mode switch + dial queue behavior are implemented as the release baseline; further ranking/polish refinements remain iterative.

### Goal

- Add a simple, musician-first home page with one large dial (**AudioKnob**) that composes an action queue (apply/reset).
- Keep the current full app and advanced workflows available.
- Dial includes a non-occluding center graphic slot (brand/art image).
- Dial visual rotation is decoupled from queue recomposition so turning remains smooth while the setting list catches up.
- Dial pointer is an extra-wide square-ended radial rectangle (no outline) that starts inside the center cap and extends just beyond knob edge for clear level reading.
- Dial finish is flat (no gradients): grey-black body with a white center cap + matching white pointer.

### User workflow (planned)

1. App opens in **Simple mode** by default.
2. User turns the dial to a level from **0 to 11** (`0` = Off, `1..11` = risk tiers).
3. That dial value builds a visible action queue (no hidden changes).
4. User clicks **Apply** (same existing queue/apply engine).
5. User can switch between simple/basic and full UI via the far-left **View** button.

### Current simple inclusion set

- `audio_group_membership` (special-case immediate Join/Leave prerequisite; visible in simple mode but not sent through worker queue apply/reset)
- `inotify_max_watches`
- `swappiness`
- `dirty_bytes`
- `usb_autosuspend_disable`
- `cpu_dma_latency_udev`
- `realtime_clock_access` (fixed preset: readable `/dev/rtc*` + `/dev/hpet` via udev rule)
- `power_profile_performance` (fixed preset: backend `auto`)
- `cpu_governor_performance_persistent` (skipped when power backend resolves to tuned)
- `Safety Latch: Safe RT` at level `10`:
  - `rt_limits_audio_group`
  - `pipewire_rt_setup` (fixed Safe RT bundle)
- `Safety Latch: Safe IRQ` at level `11`:
  - `kernel_threadirqs`
  - `irqbalance_disable`
  - `rtirq_enable`

### Safety model (planned)

- The dial only manages knobs marked `simple_mode_eligible=true`.
- Config-driven knobs (those needing per-knob values from combos/dialogs/selectors) are excluded unless they have a fixed simple preset contract.
- Dev-tab knobs are excluded by default; only explicitly whitelisted fixed-preset entries may be included.
- **Expert IRQ/core isolation knobs are excluded** from dial control.
- `disable_tracker` and `disable_baloo` are excluded from simple mode due non-audio desktop usability impact.
- Simple mode auto-queues dependency bundles (for example RT setup also queues its required RT limits/module pieces).
- Simple mode normalizes queue actions before apply: non-queue kinds (for example `group_membership`) are removed and already-active knobs are skipped to avoid duplicate apply attempts.
- Simple-mode queue preview updates on every dial move and still shows filtered apply/reset items in the list, dimmed with reason labels (for example `manual action`, `already active`, `handled externally`, `handled by tuned`, `install: ...`, `not available`) so intent remains visible before Apply.
- When the Power Profile level resolves to `tuned`, or a tuned-backed Power Profile will remain active after the current Basic apply, the overlapping tuned-owned settings stay inline in the normal preview list as dimmed `handled by tuned` rows instead of being split into a separate section.
- At dial level `0`, the reset preview lists all simple knobs and explains non-reset entries (for example `manual action` or `already off`) so turn-down intent is explicit. Above `0`, the reset preview still shows managed removals plus any out-of-scope active rows that remain handled externally or still require manual action.
- If a knob was applied by AudioKnob, the same knob row in Full mode is locked as **Managed by AudioKnob** to prevent mixed-workflow edits.
- If a simple queue contains knobs that require audio groups, Apply first enforces the same group prerequisite flow as Full mode (Join action first, then reboot/logout-login if pending).
- Full mode can release these locks only via **Tools → Locks → Release AudioKnob Locks**.
- Dial movement never auto-applies.
- Dial up composes apply actions; dial down composes reset actions for AudioKnob-managed knobs that are no longer in scope.
- Dial level `0` is an explicit off position that composes resets for all AudioKnob-managed knobs.
- Dial input is debounced for queue recomposition to keep rotation smooth under heavier queue/status redraw paths.
- Existing conflict checks and prompts still run at Apply time.

### Risk levels (planned)

- Ranking is evidence-based (blast radius, rollback certainty, conflict pressure, side effects, and payoff).
- Testing/read-only knobs are excluded from dial ranking.
- Config-driven knobs are excluded until they have a fixed simple-safe on/off preset path (current approved presets are documented in `PROJECT_STATE.md`).
- During planning we keep a granular draft score; before release it is compressed to dial `risk_score` (`1..11`).
- Simple mode uses an extra `0` detent as Off (outside risk ranking).
- Included knobs are ordered by risk; when technical risk is equal, lower payoff ranks as higher risk.
- The simple dial queues eligible knobs with `risk_score <= dial_value` after compression.
- Full per-knob evidence and ordering live in `PROJECT_STATE.md` (v0.7.0 design contract).

### Preset behavior (planned)

- Turning the dial does **not** modify Reference/Factory snapshots.
- Reference/Factory restore workflows remain separate under **Tools → Presets**.
- Dial behavior is queue-only; it does not infer or display an “achieved level” in v0.7.0.

### Full app access (planned)

- Header left now has a dedicated **View** button that toggles Simple/Full instantly from either page.
- In Full view, **Tools → Locks** contains the three lock toggles:
  - `Reboot-required changes`
  - `Advanced knobs`
  - `Technical columns`
- `Tools → Locks` also includes `Release AudioKnob Locks` for clearing simple-mode ownership metadata.
- Tools menu includes **Clear Queue** to remove all queued Apply/Reset actions before execution.
- Full app remains the authoritative view for advanced tuning.
- Full-view tab labels are:
  - `Main`
  - `Cores & IRQ`
  - `Dev`

### QjackCtl RT behavior

- Applying **QjackCtl RT** updates the QjackCtl config (active preset if set, plus unscoped mirror), sets **Realtime=true** and **Priority=90**, preserves existing presets, disables **ServerConfig**, and configures a **PostStartupScript** so JACK is re-pinned on each start. It also attempts to pin any running `jackd` process immediately. If JACK is not running, the CPU pinning takes effect the next time you start it.
- **Important:** Quit QjackCtl before applying this knob; QjackCtl rewrites its config on exit.

### IRQ pinning behavior

- **IRQ Pinning** pins IRQs for the selected audio devices to the chosen audio cores.
- It also performs a **housekeeping sweep** to move other IRQs off those audio cores.
- Housekeeping cores come from **IRQ Housekeeping** if configured; otherwise they default to **all cores minus the selected audio cores**.
- **IRQ Housekeeping** supports an **Auto** mode that inverts the selected audio cores.
- Pinning persists across reboots via `/var/lib/audioknob-gui/state.json` and `audioknob-irq-pinning.service`.

### Threaded IRQs + RTIRQ

- **Threaded IRQs** (kernel `threadirqs`) makes IRQ handlers schedulable threads on generic kernels.
- **RTIRQ** raises IRQ thread priorities; it only has effect when IRQs are threaded (RT kernel or `threadirqs`).

### RT throttling

- **RT Throttling** disables `kernel.sched_rt_runtime_us` (sets to `-1`), which prevents periodic throttling of RT threads.
- This can reduce xruns but risks a runaway RT thread starving the system or blocking suspend; reset before sleep if needed.

### CPU C-States

- **CPU C-States** adds `processor.max_cstate=1` to the kernel cmdline to limit idle states (higher power/heat, lower latency jitter; may affect suspend).
- **Intel C-States** adds `intel_idle.max_cstate=1` for systems using the Intel `intel_idle` driver (same tradeoffs).

### Power profile

- **Power Profile** sets the system power profile to performance via power-profiles-daemon or tuned (latency-performance).
- Reset restores the previous profile.
  - If power-profiles-daemon does not expose a performance profile, the knob warns and makes no change.
- The backend is configurable (Auto / powerprofilesctl / tuned). Auto uses the active backend.
- When tuned is applied, the app masks `power-profiles-daemon.service` so D-Bus activation cannot restart ppd and stop tuned behind the scenes; reset unmasks ppd before restoring it.
- tuned can override CPU governor and C-state knobs; the app warns and offers to queue resets for conflicts.

### Main + Cores & IRQ views

- The **Main** tab shows all knobs except the advanced core/IRQ set (to avoid duplicates).
- The **Main** tab also includes the TSC kernel timing knobs (`kernel_clocksource_tsc`, `kernel_tsc_reliable`) behind the Advanced lock.
- Use the **Cores & IRQ** tab to focus on core/IRQ tuning plus RT throttling, C-state limiters, core partition policy knobs (`kernel_workqueue_cpumask`, `cgroup_user_slice_allowed_cpus`, `irqbalance_banned_cpulist`), and PipeWire/WirePlumber affinity controls (`pipewire_data_loop_affinity`, `systemd_pipewire_service_rt`, `systemd_wireplumber_service_rt`).
- The **Dev** tab exposes experimental knobs that are not primarily about core placement (PipeWire/WirePlumber advanced tuning, PipeWire pulse latency/rules, PipeWire profiler module, kernel RT extras excluding TSC timing knobs, RTKit placeholder). These are optional and may require manual configuration.
- PipeWire **RT** is the single guided entry point for PipeWire realtime setup. The dialog leads with `Safe RT`, `Full RT`, and `Custom` presets in plain language, keeps advanced limits/module fields behind an explicit reveal, and points CPU-affinity tuning back to **Cores & IRQ**.
- Several **Cores & IRQ** knobs are intentionally config-required before Apply (workqueue cpumask, user.slice AllowedCPUs, irqbalance banned CPUs).
- Several **Dev** knobs are intentionally config-required before Apply (PipeWire pulse latency/rules).
- The **Audio Core Plan** panel lets you pick an audio core count and run **Auto-set** to choose cores with the fewest read-only IRQ bindings (prefers cores 2+ when possible).
- **Linked core plan** is enabled by default and ties core-selection knobs to one shared model:
  - audio-role knobs use the selected audio cores
  - housekeeping-role knobs use the inverse set
- Clearing cores and applying now performs an explicit clear/reset for core-policy knobs instead of reusing default values (kernel core cmdline params are removed, IRQ pinning resets to kernel defaults, irqbalance banned CPU policy line is removed, `user.slice` cpuset drop-in is removed, and workqueue cpumask resets to all present CPUs).
- Disable linked mode only for expert per-knob overrides.
- The **Audio Core Plan** panel is collapsible to save space in the Cores & IRQ view.
- The **IRQ Overview** button sits in the Audio Core Plan header (to the right of the title), so it stays available even when the plan body is collapsed.
- Auto-set keeps SMT/Hyper-Threading sibling cores together so physical cores stay intact.
- **Auto housekeeping** inverts the selected audio cores to derive IRQ housekeeping cores; manual mode uses the IRQ housekeeping core selection.
- Auto-set updates core selections and queues Apply for affected knobs, so the global Apply button can be used.
- **IRQ Overview** shows a core map (housekeeping vs audio cores) and an aligned IRQ table with one fixed-width per-core count column (`0..N-1`) plus a separate `Description` column, with horizontal scrolling for wide systems. Rows are compacted for denser scanning, very large per-core counts are truncated in-cell with full values on hover tooltips, a hover crosshair (row + column) can be click-locked/unlocked to trace IRQ-to-core relationships, and a dialog-local font spinner lets users zoom this view only.
- Use **Tools → Presets** to manage **Reference Preset** and **Factory Preset** snapshots.
- **Technical columns** in **Tools → Locks** shows/hides Req/Risk/CLI; default is off for a simpler musician-first view.

### Logs (what the app did and where it failed)

- GUI: `~/.local/state/audioknob-gui/logs/gui.log`
- Worker (user scope): `~/.local/state/audioknob-gui/logs/worker.log`
- Worker (root scope): `/var/lib/audioknob-gui/logs/worker.log`
- Worker logs include JSON audit entries (prefixed `audit`) with txid, files
  changed, effects, and command output/errors. GUI-only actions (group changes,
  package installs) also emit audit entries into the user-scope worker log.
- The header includes **Logs** (view + copy) and **Clear Logs** (clears GUI +
  user worker logs) to keep test runs clean.
- The PipeWire XRUN monitor streams live `pw-top` data into the app (with a pw-dump fallback for QUANT/RATE when batch output is blank).
- The ALSA XRUN monitor reads per-card xrun counts from `/proc/asound/cardN/pcm*/sub0/status`. It supports compact and full table views, always-on-top, and a card selector. Enabling xrun_debug logging (apply) writes to `/proc/asound` via pkexec (non-persistent, resets on reboot).
- The jitter monitor is modeless, supports Always‑on‑top, and shows a live per‑thread table with rolling Act samples (min/median/avg/p95/max). A snapshot refresh action in the knob details panel runs the classic cyclictest run.

### Startup system profile scan (first run)

On first GUI launch, the app records the detected distro, package commands, and
per-knob locations in `~/.local/state/audioknob-gui/state.json`. This confirms
distro-specific paths (e.g., kernel cmdline handling on Tumbleweed vs
Ubuntu/Fedora) and ensures each knob has a resolved location entry. If the file
is removed, the schema changes, or the distro/boot system changes, the scan runs again.

**Manual discovery:** Use **Tools → Scan System Profile...** to re-run the system
profile scan on demand, view the resolved paths/commands, and optionally save
the JSON snapshot to a file. This does not change system settings.
**Tools menu:** Also includes **Clear Queue**, **Presets** actions (Reference Preset + Factory Preset capture/import/export/restore), **Tx History**, plus quick access to **Jitter Monitor**, **Jitter Test Snapshot**, and terminal launchers for **Latencytop** and **Cyclictest**.
Tx History includes expanded columns (Knobs, Knob IDs, Files, Effects) for quicker audit detail without opening each row.
Preset menus/actions include color-dot markers (**blue = Reference**, **green = Factory**) for quick visual identification.

### Presets (first run)

On first launch, the app captures an initial **Reference Preset** using pkexec so
root-only knobs are included. It also auto-captures a **Factory Preset** from that
same initial scan when none exists. A **Re-check State** button in the header
re-runs current status checks for development/testing. Apply/reset actions are
disabled until the initial reference scan completes.
Package install actions remain available so missing dependencies can be installed
before presets are captured.

Use **Tools → Presets → Reference Preset** to manage reference snapshots:
- **Capture/Import/Export/Queue Restore Reference Preset...** manage the active reference snapshot.
- Reference snapshots also capture per‑knob config values (core selections, PipeWire settings) for restore.
- Reference files include system profile metadata; if the profile doesn’t match the current system, import offers a **portable** mode that strips config overrides and normalizes unknown/partial statuses to not_applied.
- When restoring a mismatched import, the app warns about incompatibilities, captures a **pre‑import backup** (saved in `~/Documents/audioknob/ak-pre-<import>-YYYYMMDD-HHMMSS.json`), applies what it can, and skips incompatible knobs.

Use **Tools → Presets → Factory Preset** to manage factory snapshots:
- **Factory Preset** is immutable once set (initial capture, manual capture, or import); capture/import are blocked after that.
- Factory capture/import actions remain visible and show **(Locked)** with an explanation dialog when clicked.
- **Export/Queue Restore Factory Preset...** remain available.
- **Factory Preset (Reset All)...** performs a full “leave no trace” reset of all Audioknob changes.
- Factory preset snapshots are date-stamped (`factory_captured_at`) and include profile metadata.

### Info vs Status panels

- **Info** uses a simple tag format: `[i]` summary, `[r]` requirements, `[+]` benefits, `[-]` tradeoffs.
- **Status/Check** shows live technical details (service states, group gaps, sysctl/sysfs values, PipeWire runtime settings, etc.); when status is **partial**, it includes a short reason line and raw checks below.
- Partial reasons are explicit for mixed states (for example: masked/unmasked user services, partial group membership activation, sysfs match counts, and WirePlumber/PipeWire config drift).
- Status column is operational only (`Applied`, `Not applied`, `Partial`, `Reboot`, `Unknown`, `N/A`).
- When a knob is **Partial**, the row action queues a **Reset** (revert to defaults). Apply again after reset if you want to re-enable it.
- Preset matches are shown as color dots beside the status button (**blue = matches Reference Preset**, **green = matches Factory Preset**).

### Conflicts and blockers

- The app warns on known conflicts and offers an optional **Queue resets** action.
- The app never auto-disables knobs without explicit confirmation.
- Conflict prompt options: **Apply + reset conflicts**, **Apply anyway**, **Cancel**, or **See conflicts detail**.
- Conflict prompts and row tooltips include active/queued state labels so users can see exactly why a conflict is flagged.
- Conflicting knobs are gated; the Action column shows a red **Conflict** button that queues a reset for that knob.
- Known conflicts, dependencies, and blockers are documented in `docs/KNOB_INTERACTIONS.md`.
- TSC-related kernel knobs show a pre-flight warning if safety checks look risky.
- Status labels include a conflict indicator when a knob is currently conflicting.
- Conflict indicator counts only active/queued knobs (applied/pending/running/partial or queued apply), so idle defaults do not appear as conflicts.
- The row-level **Conflict** button uses the same active/queued rules as the header counter, so row badges and header counts stay consistent.
- Conflict warnings cover power profile vs governor/C-states, active irqbalance service vs IRQ pinning (not the `irqbalance_disable` dependency knob), PipeWire clock constraints vs quantum/rate, data loop affinity vs CPU/IRQ isolation, and CPU isolation core mismatches.
- In simple mode, when power profile resolves to `tuned`, or tuned-backed Power Profile will remain active after the current Basic apply, the queue skips CPU governor/swappiness/dirty-bytes and keeps those rows visible inline as dimmed `handled by tuned` preview entries so the hidden coverage is still visible.
- Combo-box settings ignore mouse-wheel changes unless the dropdown menu is open, preventing accidental value flips while scrolling.
- Simple mode shows one plain-text list on the left with **Apply queue** and **Reset queue** sections (no pane, no separate selected-settings list).
- The font size selector applies universally across existing widgets so simple/full text tracks the selected size.

---

## Working agreement (to prevent drift)

If any agent (including “overseer”) changes behavior, adds a knob, changes packaging, or changes any file path/env var, they MUST:

- Update `PROJECT_STATE.md` (machine reference) and keep it consistent with the code.
- Update `PLAN.md` (user guide) only for user-relevant steps and keep it consistent with the code.
- Sync `config/registry*.json` → `audioknob_gui/data/registry*.json` when touched.
- If stabilization mode is active, follow `docs/internal/audit/STABILIZATION_STATE.md` (allowlist + file-count cap) and keep work in a bounded batch.
- Prefer conservative behavior: if status cannot be proven, show “unknown/not applied” rather than “applied”.
- For broad parity/code audits, use `docs/KNOB_SYSTEM_AUDIT_MAP.md` as the audit blueprint.

When in doubt, stop and ask rather than inventing new UX/flows not described here.

## How to Add a New Knob

Developer note: before implementing, review **New Knob Robustness Checklist** in `PROJECT_STATE.md`
for path discovery and system profile updates.

### Step 1: Define in registry.json

Add a knob object to `config/registry.json` (**canonical source**) inside the top-level `knobs` array.

The file format is:

```json
{
  "schema": 1,
  "knobs": [
    { "id": "example", "title": "…", "description": "…", "category": "cpu", "risk_level": "low",
      "requires_root": false, "requires_reboot": false, "requires_groups": [], "requires_commands": [],
      "capabilities": { "read": true, "apply": true, "restore": true },
      "impl": { "kind": "read_only", "params": {} }
    }
  ]
}
```

Add your new knob object like this:

```json
{
  "id": "my_new_knob",
  "title": "My New Knob",
  "description": "What it does",
  "category": "cpu",
  "risk_level": "low",
  "requires_root": true,
  "requires_reboot": false,
  "requires_groups": [],
  "requires_commands": [],
  "capabilities": { "read": true, "apply": true, "restore": true },
  "impl": { "kind": "...", "params": { ... } }
}
```

**⚠️ IMPORTANT: After editing, sync to package data:**
```bash
cp config/registry.json audioknob_gui/data/registry.json
cp config/registry.schema.json audioknob_gui/data/registry.schema.json
```
Both files must be committed together. See "Registry Sync Policy" below.

**New fields:**
- `requires_groups`: User must be in ONE of these groups (e.g., `["audio", "realtime"]`)
- `requires_commands`: Commands that must be available (e.g., `["cyclictest"]`)
- `depends_on`: Other knob ids that must remain enabled for this knob

### Step 2: Choose implementation kind

| Kind | When to use | Example |
|------|-------------|---------|
| `pam_limits_audio_group` | PAM limits file | rt_limits |
| `sysctl_conf` | Sysctl.d drop-in | swappiness, inotify |
| `sysfs_glob_kv` | Write to /sys | cpu_governor, thp |
| `systemd_unit_toggle` | Enable/disable service | irqbalance |
| `rtirq_config` | Configure rtirq priorities + enable service | rtirq |
| `irq_affinity` | Pin IRQs for selected devices | irq_pinning |
| `qjackctl_server_prefix` | QjackCtl config | jackd flags |
| `udev_rule` | Create udev rule | cpu_dma_latency, usb_autosuspend |
| `kernel_cmdline` | Kernel cmdline param (distro-aware) | threadirqs, audit=0 |
| `pipewire_conf` | PipeWire user config | quantum, sample_rate |
| `user_service_mask` | Mask user systemd services | tracker, baloo |
| `baloo_disable` | Disable KDE Baloo via balooctl | baloo |
| `group_membership` | Add user to groups | audio_group |
| `read_only` | Info/test only | stack_detect |

### Step 3: Add implementation (if new kind)

1. **Preview**: Add to `worker/ops.py` → `preview()` function
2. **Apply**: Add to `worker/cli.py` → `cmd_apply()` function
3. **Status check**: Add to `worker/ops.py` → `check_knob_status()`

### Step 4: Add UI elements (if needed)

In `gui/app.py` → `_populate()`:

| Knob type | Status | Column 2 (Action) | Details surface |
|-----------|--------|-------------------|-----------------|
| Not applied | — | "Apply" button (queues) | persistent side panel |
| Applied | ✓ Applied | "Reset" button | persistent side panel |
| Not implemented | — | "—" disabled | persistent side panel |
| Missing groups | Locked | "🔒" disabled | persistent side panel |
| Missing packages | Locked | "Install" button | persistent side panel |
| Read-only info | — | "View" button | persistent side panel |
| Read-only test | — | "Test"/"Scan" button | persistent side panel |
| Group join knob | — | "Join/Leave" button (immediate) | persistent side panel |

**Columns**: Knob | Action | Config | Status | Category (+ optional Req./Risk/CLI via Technical columns)

**Advanced mode**: Single table; advanced knobs are gated by **Tools → Locks → Advanced knobs**.

**Sorting**: Click any column header to sort. Category/Status sorts show grouped headers; Req./Risk grouping is available when Technical columns are shown.

**Req. column** (Technical columns on): Shows A/R/D markers for Advanced/Reboot/Depends-on; tooltip includes the key and any group/dependency details when present.
**Dependency gating**: If a knob depends on another, it stays locked until the dependency is applied or queued for apply; tooltip shows the required knob name(s).

**CLI column** (Technical columns on): Shows the target command/file/parameter shorthand for each knob.

**Header row**: **View** button at far left, then Font size control; queue status + Conflicts indicator + Apply/Apply & Reboot + Re-check State + Logs on the right

---

## Implementation Patterns

### Normal knob (context-sensitive button)
```python
status = self._knob_statuses.get(k.id, "unknown")
if status == "applied":
    btn = QPushButton("Reset")
    btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "reset"))
else:
    btn = QPushButton("Apply")
    btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "apply"))
self.table.setCellWidget(r, 2, btn)  # Column 2 = Action
```

Apply/Reset runs in the background; the status column shows “⏳ Updating” and the action button is disabled while work is in progress.
Apply and Reset now queue the change. The global header button applies the queued set: "Apply" for non-reboot changes or "Apply & Reboot" if any queued knob requires reboot. "Apply & Reboot" always triggers a reboot prompt after apply, even if pending-reboot status is not yet detected.
Group join/leave actions remain immediate because they require explicit confirmation. `group_membership` is an intentional special-case kind and stays outside the worker preview/apply/reset/force-reset transaction pipeline.
If a reset fails with "No transaction found", the GUI offers a confirmation prompt to force-reset (for both single and queued resets). Force reset is supported where defaults can be inferred or safely removed: `systemd_unit_toggle`, `kernel_cmdline`, `sysfs_glob_kv` (only when sysfs exposes a bracketed default), `pam_limits_audio_group`, `sysctl_conf`, `udev_rule` (only if file matches audioknob content), `pipewire_conf`/`wireplumber_conf` (only if file has audioknob header), `rtirq_config`, `irq_affinity` (generic reset to kernel default IRQ mask + remove audioknob IRQ persistence), `power_profile` (set conservative `balanced` profile when backend supports it), `qjackctl_server_prefix` (strip RT/taskset and clear audioknob post-start hook), `user_service_mask`, and `baloo_disable`. For `wpctl_profile`, force reset is explicit-safe-decline: if a deterministic fallback profile cannot be inferred, the worker refuses to guess and asks for manual profile selection or transaction restore.
Reboot-required knobs are disabled until the user enables **Tools → Locks → Reboot-required changes**.
Knobs requiring audio groups stay locked while group membership is pending reboot.

### Read-only info
```python
btn = QPushButton("View")
btn.clicked.connect(self.on_view_stack)
self.table.setCellWidget(r, 2, btn)  # Column 2 = Action
```

### Read-only test (updates status)
```python
btn = QPushButton("Test")
btn.clicked.connect(lambda _, kid=k.id: self.on_run_test(kid))
self.table.setCellWidget(r, 2, btn)  # Column 2 = Action
```

The jitter test stores the most recent per-thread summary (min/median/avg/p95/max) in the knob details panel, with "Refresh Snapshot" and "Show Sample List" actions available from that panel.
The knob details surface also includes CLI sanity-check commands (status/apply/reset) for copy/paste verification.
Click the Status value in the Status column to run live CLI status checks and command outputs (e.g., systemctl, /proc/cmdline) for cross-comparisons. It also shows reference/factory preset statuses for that knob when available. Read-only test rows show N/A in this column.
The Logs dialog prefixes each line with its source tag (GUI / WORKER-USER / WORKER-ROOT) to make mixed logs easy to read.
The GUI log also records high-level action start/finish entries (apply queue, reset all) so successes are visible in-app.
Force-reset prompts and outcomes are also logged in the GUI log.
If a reset would disable a dependency, the GUI prompts and adds dependent knobs to the reset queue when accepted.
Status remains operational; preset matches are shown as secondary hints in tooltips/details.

### With config dialog
```python
# In the dialog fallback, add a config button for knobs that need it:
if k.id == "qjackctl_server_prefix_rt":
    config_btn = QPushButton("Configure CPU Cores...")
    config_btn.clicked.connect(lambda: self.on_configure_knob(k.id))
    layout.addWidget(config_btn)
```

PipeWire buffer size (quantum) and sample rate are configurable via in-row selectors (saved to `state.json`). QjackCtl CPU pinning is configurable via the Config column "Cores" button (default cores: 0,1). Kernel isolation knobs also use the Config column core selector. The persistent knob details panel shows the same description, status, and CLI guidance that used to live behind the per-row info button while leaving configuration in the row itself, and the table stretches to meet that panel cleanly as the window resizes. Applying QjackCtl RT disables ServerConfig, preserves presets (updates the active preset if set), and configures a PostStartupScript so CPU pinning is re-applied when JACK starts. Applying IRQ pinning writes a system config in `/var/lib/audioknob-gui/state.json` and enables `audioknob-irq-pinning.service` so pinning persists across reboots. Applying PipeWire knobs restarts PipeWire services automatically.

---

## Current Knobs (see registry.json) - ALL IMPLEMENTED ✓

### Permissions
| Knob | Kind | Status |
|------|------|--------|
| Join audio groups | group_membership | ✓ |
| Realtime limits for @audio | pam_limits_audio_group | ✓ |

Note: RT limits require a reboot or logout/login to affect the current session; the UI shows “Reboot required” until the limits are active.

### IRQ
| Knob | Kind | Status |
|------|------|--------|
| Disable irqbalance | systemd_unit_toggle | ✓ |
| RTIRQ priorities + service | rtirq_config | ✓ |
| IRQ pinning | irq_affinity | ✓ |

### CPU
| Knob | Kind | Status |
|------|------|--------|
| CPU Performance (persistent) | sysfs_glob_kv (+ cpupower/cpufrequtils config + service) | ✓ |
| CPU DMA latency udev rule | udev_rule | ✓ |

### VM
| Knob | Kind | Status |
|------|------|--------|
| Reduce swappiness | sysctl_conf | ✓ |
| THP: madvise mode | kernel_cmdline | ✓ |
| Increase inotify watches | sysctl_conf | ✓ |
| Reduce dirty writeback | sysctl_conf | ✓ |

### Power
| Knob | Kind | Status |
|------|------|--------|
| Disable USB autosuspend | udev_rule | ✓ |
| Power profile (performance) | power_profile | ✓ |

### Kernel (requires reboot)
| Knob | Kind | Status |
|------|------|--------|
| Enable threaded IRQs | kernel_cmdline | ✓ |
| CPU C-States | kernel_cmdline | ✓ |
| Intel C-States | kernel_cmdline | ✓ |
| CPU Isolation | kernel_cmdline | ✓ |
| Full Tickless | kernel_cmdline | ✓ |
| RCU Offload | kernel_cmdline | ✓ |
| IRQ Housekeeping | kernel_cmdline | ✓ |
| RT Throttling | sysctl_conf | ✓ (HIGH RISK) |
| Disable kernel audit | kernel_cmdline | ✓ |
| Disable CPU mitigations | kernel_cmdline | ✓ (HIGH RISK) |

### Stack
| Knob | Kind | Status |
|------|------|--------|
| QjackCtl: realtime flags | qjackctl_server_prefix | ✓ |
| PipeWire quantum (buffer) | pipewire_conf | ✓ |
| PipeWire sample rate | pipewire_conf | ✓ |

### Services
| Knob | Kind | Status |
|------|------|--------|
| Disable GNOME tracker | user_service_mask | ✓ |
| Disable KDE Baloo | baloo_disable | ✓ |

### Testing (Read-only)
| Knob | Kind | Status |
|------|------|--------|
| Audio stack info | read_only | ✓ |
| Scheduler jitter test (live monitor + snapshot) | read_only | ✓ |
| RT config scan | read_only | ✓ |

### Future Phases
**Phase 4: Audio Hardware**
- Interface selection, sample rate, buffer, bit depth (via config dialog)

**Phase 5: Monitoring**  
- Underrun counter, interrupt inspector

---

## Distro Notes

### Boot loader handling
| Distro | Method |
|--------|--------|
| openSUSE TW | Edit `/etc/kernel/cmdline`, run `sdbootutil update-all-entries` |
| openSUSE Leap | Edit `/etc/default/grub`, run `grub2-mkconfig -o /boot/grub2/grub.cfg` |
| Fedora | Edit `/etc/default/grub`, run `grub2-mkconfig -o /boot/grub2/grub.cfg` |
| Debian/Ubuntu | Edit `/etc/default/grub`, run `update-grub` |

### Audio group
- Most distros: `audio`
- Arch: `realtime` (from `realtime-privileges` package)

---

## Registry Sync Policy

The registry exists in two locations:

| Location | Purpose |
|----------|---------|
| `config/registry.json` | **Canonical source** — edit here |
| `audioknob_gui/data/registry.json` | Packaged copy for installed builds |
| `config/registry.schema.json` | Schema (canonical) |
| `audioknob_gui/data/registry.schema.json` | Packaged schema copy |

**Why two copies?**
- `config/` is at repo root for easy discovery/editing
- `audioknob_gui/data/` is inside the package so `importlib.resources` can find it when installed via pip

**Sync procedure (after any registry edit):**
```bash
cp config/registry.json audioknob_gui/data/registry.json
cp config/registry.schema.json audioknob_gui/data/registry.schema.json
git add config/registry.json config/registry.schema.json audioknob_gui/data/registry.json audioknob_gui/data/registry.schema.json
```

**Pre-commit check (recommended):**
```bash
diff config/registry.json audioknob_gui/data/registry.json || echo "REGISTRY OUT OF SYNC"
diff config/registry.schema.json audioknob_gui/data/registry.schema.json || echo "REGISTRY SCHEMA OUT OF SYNC"
```

**Resolution order** (in `core/paths.py`):
1. `AUDIOKNOB_REGISTRY` env var (explicit override)
2. `AUDIOKNOB_DEV_REPO/config/registry.json` (dev mode)
3. Package data via `importlib.resources` (production)
4. File-relative fallback (legacy dev mode)

---

## Guardrails

1. **Everything undoable** - Transactions with backups
2. **Distro-aware** - Don't assume one way works everywhere
3. **User knows best** - Show status, let them choose
4. **Explicit actions** - Queue + apply/reset is explicit and user-driven; config selectors are allowed where knobs require parameter input
5. **Lock until ready** - Missing groups? 🔒. Missing packages? 📦 Install.
6. **Docs match code** - `PROJECT_STATE.md` and `PLAN.md` are first-class deliverables
7. **Privileged channels are explicit** - knob/system changes run through the worker wrapper; GUI maintenance pkexec commands are allowlisted and user-initiated.

---

## Scope / Non-goals (to keep the project on course)

We are explicitly NOT doing these unless the docs are updated first:

- An always-on background daemon/service or scheduled auto-tuning loop
- Automatic “apply everything” / batch apply workflows without an explicit queue + apply action
- Auto-modifying system settings without an explicit user click + visible status change
- Complex multi-step wizards or hidden state machines
- Network/cloud features

---

## Testing (how to validate changes)

### Fast checks (no root required)

If you want to run unit tests, install dev deps:

```bash
python3 -m pip install -e .[dev]
```

```bash
python3 scripts/check_repo_consistency.py
python3 scripts/run_quality_gate.py --gate g2 --tests tests/test_<touched_area>.py
python3 -m audioknob_gui.worker.cli status
python3 -m audioknob_gui.worker.cli preview pipewire_quantum pipewire_sample_rate
```

### GUI smoke test (no root required)

```bash
bin/audioknob-gui
```

Verify:
- table loads and status updates
- PipeWire quantum/sample-rate selectors work and reflect in the knob details surface

### Root knobs (manual, last)

Only after non-root testing is stable:
- systemd toggles (irqbalance) + rtirq config/service
- IRQ pinning (affinity changes)
- sysfs knobs (CPU governor)
- udev rule knobs
- kernel cmdline knobs (require reboot; do last)

### Tumbleweed VM methodical validation (2026-02-20)

Use this sequence when validating the app against a temporary openSUSE
Tumbleweed VM.

Phase 1: environment prep
- Ensure SSH + sudo access to the VM.
- Sync repo to VM working tree.
- Install validation deps in VM:
  - `jq`, `rt-tests`, `stress-ng`, `pipewire-tools`, `git-core`
- Verify baseline commands:
  - `python3 -m audioknob_gui.worker.cli --registry config/registry.json status`
  - `sudo -n python3 -m audioknob_gui.testing.cyclictest`

Phase 2: per-knob functional sweep
- For each knob in `config/registry.json`, execute:
  - `preview --action apply <knob>`
  - `apply <knob>` (root knobs) or `apply-user <knob>` (user knobs)
  - `status` check for that knob
  - `restore-knob <knob>`
  - `status` check after restore
- Record command return codes, warnings, and status transitions.

Phase 3: profile performance matrix
- Always start each profile from a clean runtime baseline:
  1. `reset-defaults --scope root` + `reset-defaults --scope user`
  2. Reboot
- Apply profile knobs, reboot when kernel cmdline knobs are involved, then
  run benchmark pack:
  - idle cyclictest max latency
  - loaded cyclictest max latency (while stress-ng runs)
  - stress-ng CPU throughput (`bogo ops/s`)

Phase 4: repeatability pass for candidates
- Re-test shortlisted profiles with at least 3 runs each vs clean baseline.
- Compare medians (not single-run outliers) before recommending a default set.

Latest VM snapshot summary (openSUSE Tumbleweed 20260218)
- Functional sweep scope: 56 knobs.
- Functional sweep outcome:
  - apply success: 35
  - apply failures: 16
  - non-apply/read-only knobs: 5
- Main non-app blockers observed in VM:
  - missing backend/service/tooling (`powerprofilesctl`/`tuned-adm`, `rtirq.service`, tracker/baloo)
  - no cpufreq sysfs governor path in this VM
  - knobs that require explicit user config before apply (`pipewire_*` advanced config knobs, pro audio profile selector, IRQ/core selectors)
- One-pass profile matrix (max latency in us):
  - baseline_clean: idle 1049, loaded 100
  - vm_memory: idle 335, loaded 181
  - rt_runtime: idle 1568, loaded 440
  - kernel_threaded: idle 158, loaded 177
  - kernel_threaded_preempt: idle 1368, loaded 172
  - kernel_low_jitter_diag_off: idle 445, loaded 158
  - kernel_aggressive: idle 255, loaded 34
- Repeatability check (3-run medians, cleaner signal):
  - baseline vs aggressive:
    - idle max: 51 -> 57 us (slightly worse)
    - loaded max: 106 -> 77 us (better)
    - stress throughput: 8233.8 -> 8204.9 bogo/s (~flat)
  - baseline vs low-jitter (no mitigations/nosmt/audit-off):
    - idle max: 370 -> 539 us (worse)
    - loaded max: 230 -> 96 us (better)
    - stress throughput: 8234.38 -> 8216.21 bogo/s (~flat)

Interpretation for serious audio goal
- `kernel_rt_throttling_off` alone underperformed in this VM (higher loaded
  and idle latency spikes); treat as bundle-only candidate, not standalone.
- Threaded IRQ/kernel bundles improved loaded-latency behavior more reliably
  than standalone runtime-only knobs.
- `kernel_aggressive` gave the best loaded-latency result in this VM repeat
  pass, with near-flat CPU throughput, but carries higher risk due:
  - `mitigations=off`, `nosmt`, `audit=0`, disabled watchdogs.
- Practical recommendation:
  - default candidate for mixed use: `kernel_low_jitter_diag_off`
  - dedicated session candidate: `kernel_aggressive`
  - keep both as explicit user-selected presets, not auto-applied.

Known VM limitations
- No physical audio interface/JACK/PipeWire real workload.
- Virtual CPU scheduling noise is high; absolute latency values are less
  important than repeated relative deltas.
- Re-run the same matrix on target hardware before making final defaults.


---

## Learnings

1. **Status column is essential** - Users need to see what's applied
2. **Per-knob restore** - Global undo isn't enough
3. **Read-only needs UI** - Buttons for info/tests, not dropdowns
4. **pkexec is enough** - No need for "type YES" confirmations
5. **Check user services** - PipeWire runs as user, not system
6. **Smart reset** - Different files need different restore strategies
7. **On-demand deps** - Install packages when needed, not upfront
8. **Group gating** - Lock knobs until user has required groups
9. **RT scanner** - Better to build our own than shell out to Perl
10. **Sortable table** - Let users organize by category/risk/status

---

## RT Config Scanner

18 checks based on `realtimeconfigquickscan` but improved:
- Native Python (no Perl)
- Structured output for GUI
- Links to fix knobs
- More checks (USB, THP, memlock)
- RTC/HPET checks now link to `realtime_clock_access`

See `audioknob_gui/testing/rtcheck.py`

---

## References

- https://wiki.linuxaudio.org/wiki/system_configuration
- https://wiki.archlinux.org/title/Professional_audio
- https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning

---

*Last updated: 2026-03-04*
