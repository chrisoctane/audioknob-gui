# audioknob-gui: Plan

## Quick start (for you)

### Run from a repo checkout (recommended for development)

```bash
cd /path/to/audioknob-gui
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -U pip
python3 -m pip install -e .
bin/audioknob-gui
```

### Desktop launcher (optional, for local testing)

This generates and installs a `.desktop` entry so you can launch from your application menu:

```bash
./scripts/install-desktop.sh
```

The script auto-detects:
- **Repo root**: Uses the script's location to find the repository
- **Python**: Prefers `.venv/bin/python3` if present, falls back to system `python3`
- **Environment**: Sets `AUDIOKNOB_DEV_REPO` so imports work correctly

The generated `.desktop` file is written to `~/.local/share/applications/audioknob-gui.desktop`.

### Install on openSUSE Tumbleweed (RPM, v0.2.2)

For v0.2.2 we support **RPM packaging on openSUSE Tumbleweed**.
Current support is **Tumbleweed only**.

Build a local RPM from this repo:

```bash
cd /home/chris/audioknob-gui
./packaging/opensuse/build-rpm.sh
```

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
- Root operations use polkit + a fixed-path worker wrapper at `/usr/libexec/audioknob-gui-worker`.

### Set up pre-commit hooks (recommended for contributors)

```bash
pip install pre-commit && pre-commit install
```

This runs `scripts/check_repo_consistency.py` before each commit to catch registry drift and doc omissions.

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

### Logs (what the app did and where it failed)

- GUI: `~/.local/state/audioknob-gui/logs/gui.log`
- Worker (user scope): `~/.local/state/audioknob-gui/logs/worker.log`
- Worker (root scope): `/var/lib/audioknob-gui/logs/worker.log`

---

## Working agreement (to prevent drift)

If any agent (including “overseer”) changes behavior, adds a knob, changes packaging, or changes any file path/env var, they MUST:

- Update `PROJECT_STATE.md` (machine reference) and keep it consistent with the code.
- Update `PLAN.md` (user guide) only for user-relevant steps and keep it consistent with the code.
- Sync `config/registry*.json` → `audioknob_gui/data/registry*.json` when touched.
- Prefer conservative behavior: if status cannot be proven, show “unknown/not applied” rather than “applied”.

When in doubt, stop and ask rather than inventing new UX/flows not described here.

## How to Add a New Knob

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

### Step 2: Choose implementation kind

| Kind | When to use | Example |
|------|-------------|---------|
| `pam_limits_audio_group` | PAM limits file | rt_limits |
| `sysctl_conf` | Sysctl.d drop-in | swappiness, inotify |
| `sysfs_glob_kv` | Write to /sys | cpu_governor, thp |
| `systemd_unit_toggle` | Enable/disable service | irqbalance, rtirq |
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

| Knob type | Status | Column 5 (Action) | Column 0 (Details) |
|-----------|--------|-------------------|-----------------|
| Not applied | — | "Apply" button | "?" button |
| Applied | ✓ Applied | "Reset" button | "?" button |
| Not implemented | — | "—" disabled | "?" button |
| Missing groups | 🔒 | "🔒" disabled | "?" button |
| Missing packages | 📦 | "Install" button | "?" button |
| Read-only info | — | "View" button | "?" button |
| Read-only test | — | "Test"/"Scan" button | "?" button |
| Group join knob | — | "Join/Leave" button | "?" button |

**Columns**: Info | Knob | Status | Category | Risk | Action | Config

**Sorting**: Click any column header to sort

---

## Implementation Patterns

### Normal knob (context-sensitive button)
```python
status = self._knob_statuses.get(k.id, "unknown")
if status == "applied":
    btn = QPushButton("Reset")
    btn.clicked.connect(lambda _, kid=k.id: self._on_reset_knob(kid, root))
else:
    btn = QPushButton("Apply")
    btn.clicked.connect(lambda _, kid=k.id: self._on_apply_knob(kid))
self.table.setCellWidget(r, 5, btn)  # Column 5 = Action
```

Apply/Reset runs in the background; the status column shows “⏳ Updating” and the action button is disabled while work is in progress.
If a reset fails with "No transaction found", the GUI offers a confirmation prompt to force-reset (supported for `systemd_unit_toggle` and `kernel_cmdline` knobs).

### Read-only info
```python
btn = QPushButton("View")
btn.clicked.connect(self.on_view_stack)
self.table.setCellWidget(r, 5, btn)  # Column 5 = Action
```

### Read-only test (updates status)
```python
btn = QPushButton("Test")
btn.clicked.connect(lambda _, kid=k.id: self.on_run_test(kid))
self.table.setCellWidget(r, 5, btn)  # Column 5 = Action
```

The jitter test also stores the most recent per-thread results in the knob info dialog.
The info dialog also includes CLI sanity-check commands (status/apply/reset) for copy/paste verification,
plus a "Run status check" button that prints live diagnostics for the current knob.

### With config dialog (via info popup)
```python
# In _show_knob_info(), add config button for knobs that need it:
if k.id == "qjackctl_server_prefix_rt":
    config_btn = QPushButton("Configure CPU Cores...")
    config_btn.clicked.connect(lambda: self.on_configure_knob(k.id))
    layout.addWidget(config_btn)
```

PipeWire buffer size (quantum) and sample rate are configurable via in-row selectors or the Info details popup (saved to `state.json`). QjackCtl CPU pinning is configurable via the Config column "Cores" button (default cores: 0,1). Applying PipeWire knobs restarts PipeWire services automatically.

---

## Current Knobs (23) - ALL IMPLEMENTED ✓

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
| Enable rtirq service | systemd_unit_toggle | ✓ |

### CPU
| Knob | Kind | Status |
|------|------|--------|
| CPU Performance (until reboot) | sysfs_glob_kv | ✓ |
| CPU Performance (persistent) | sysfs_glob_kv (+ cpupower config + service) | ✓ |
| CPU DMA latency udev rule | udev_rule | ✓ |

### VM
| Knob | Kind | Status |
|------|------|--------|
| Reduce swappiness | sysctl_conf | ✓ |
| THP: madvise mode | sysfs_glob_kv | ✓ |
| Increase inotify watches | sysctl_conf | ✓ |
| Reduce dirty writeback | sysctl_conf | ✓ |

### Power
| Knob | Kind | Status |
|------|------|--------|
| Disable USB autosuspend | udev_rule | ✓ |

### Kernel (requires reboot)
| Knob | Kind | Status |
|------|------|--------|
| Enable threaded IRQs | kernel_cmdline | ✓ |
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
| Scheduler jitter test | read_only | ✓ |
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
4. **One click actions** - No dropdowns, no batch mode, no preview step
5. **Lock until ready** - Missing groups? 🔒. Missing packages? 📦 Install.
6. **Docs match code** - `PROJECT_STATE.md` and `PLAN.md` are first-class deliverables

---

## Scope / Non-goals (to keep the project on course)

We are explicitly NOT doing these unless the docs are updated first:

- A background daemon or always-on service
- Automatic “apply everything” / batch apply workflows (the UX is per-knob, one-click)
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
python3 -m audioknob_gui.worker.cli status
python3 -m audioknob_gui.worker.cli preview pipewire_quantum pipewire_sample_rate
```

### GUI smoke test (no root required)

```bash
bin/audioknob-gui
```

Verify:
- table loads and status updates
- PipeWire quantum/sample-rate selectors work and reflect in the Info details popup

### Root knobs (manual, last)

Only after non-root testing is stable:
- systemd toggles (irqbalance/rtirq)
- sysfs knobs (CPU governor, THP)
- udev rule knobs
- kernel cmdline knobs (require reboot; do last)


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

See `audioknob_gui/testing/rtcheck.py`

---

## References

- https://wiki.linuxaudio.org/wiki/system_configuration
- https://wiki.archlinux.org/title/Professional_audio
- https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning

---

*Last updated: 2025-12-20*
