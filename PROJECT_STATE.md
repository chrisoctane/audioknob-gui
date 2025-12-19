# audioknob-gui: Technical State Document

> **Purpose**: This is the definitive technical reference for the project. It documents architecture, implementation patterns, learnings, and constraints. Use this to understand the codebase and continue development without drift.
>
> **For the user-facing guide, see PLAN.md**

---

## 1. Project Overview

### Goal
A PySide6 GUI application that configures Linux systems for professional realtime audio. Users see a list of "knobs" (system tweaks) and can apply or reset each one with a single button click.

### Core Principles (Non-Negotiable)
1. **Transaction-based changes** - Every modification creates a backup before changing anything
2. **Undo always works** - Any applied change can be reverted
3. **Status visibility** - User always sees current state of each knob
4. **Distro-aware** - Don't assume one Linux distro; detect and adapt
5. **Privilege separation** - Root operations go through pkexec, user operations don't

### Current State
- **8 knobs implemented** and working
- **Per-knob Apply/Reset buttons** - simplified from dropdown
- **Status column** shows applied/not-applied state
- **Test results in status** - jitter test shows "12 µs" in status column
- **Smart reset** - uses backup, package manager, or deletion as appropriate

---

## 2. Architecture

### File Structure
```
audioknob-gui/
├── bin/
│   └── audioknob-gui          # Launcher script (sets PYTHONPATH)
├── config/
│   └── registry.json          # Knob definitions (THE source of truth for knobs)
├── packaging/
│   ├── audioknob-gui-worker   # Root worker script (installed to /usr/local/libexec/)
│   ├── install-polkit.sh      # Installs polkit policy
│   └── org.audioknob.worker.policy
├── audioknob_gui/
│   ├── gui/
│   │   ├── app.py             # Main GUI (PySide6)
│   │   └── tests_dialog.py    # Jitter test wrapper
│   ├── worker/
│   │   ├── cli.py             # Worker CLI (preview, apply, restore, status)
│   │   └── ops.py             # Operations (preview logic, status checking)
│   ├── core/
│   │   ├── transaction.py     # Backup/restore logic
│   │   ├── qjackctl.py        # QjackCtl config manipulation
│   │   ├── paths.py           # Standard paths
│   │   ├── runner.py          # Subprocess wrapper
│   │   └── diffutil.py        # Unified diff generation
│   ├── platform/
│   │   ├── detect.py          # Audio stack detection
│   │   └── packages.py        # Package manager detection
│   ├── testing/
│   │   ├── cyclictest.py      # Cyclictest wrapper
│   │   └── latencycalc.py     # Latency calculations
│   └── registry.py            # Registry loader
├── PROJECT_STATE.md           # THIS FILE - technical reference
└── PLAN.md                    # User-facing guide
```

### Data Flow
```
User clicks Apply → GUI calls worker CLI → Worker creates transaction → Worker applies change → GUI refreshes status
User clicks Reset → GUI calls worker CLI → Worker finds transaction → Worker restores from backup → GUI refreshes status
```

### Privilege Model
- **User knobs** (requires_root: false): Run directly via `python -m audioknob_gui.worker.cli`
- **Root knobs** (requires_root: true): Run via `pkexec /usr/local/libexec/audioknob-gui-worker`

### Transaction Storage
- **Root transactions**: `/var/lib/audioknob-gui/transactions/<txid>/`
- **User transactions**: `~/.local/state/audioknob-gui/transactions/<txid>/`

Each transaction contains:
- `manifest.json` - What was changed, which knobs, backup metadata
- `backups/` - Original file contents before modification

---

## 3. Implementation Patterns

### Adding a New Knob

1. **Define in registry.json**:
```json
{
  "id": "my_knob",
  "title": "My Knob",
  "description": "What it does",
  "category": "cpu",
  "risk_level": "low",
  "requires_root": true,
  "requires_reboot": false,
  "capabilities": { "read": true, "apply": true, "restore": true },
  "impl": { "kind": "...", "params": {...} }
}
```

2. **Choose implementation kind** (or create new one):

| Kind | Files | Apply Logic |
|------|-------|-------------|
| `pam_limits_audio_group` | `/etc/security/limits.d/*` | Append lines if missing |
| `sysctl_conf` | `/etc/sysctl.d/*` | Append lines if missing |
| `sysfs_glob_kv` | `/sys/**` | Write value to matching paths |
| `systemd_unit_toggle` | (none) | Enable/disable systemd unit |
| `qjackctl_server_prefix` | `~/.config/rncbc.org/QjackCtl.conf` | Modify Server line |
| `read_only` | (none) | No changes, info/test only |

3. **If new kind, implement in**:
   - `worker/ops.py` → `preview()` function
   - `worker/cli.py` → `cmd_apply()` function
   - `worker/ops.py` → `check_knob_status()` function

4. **GUI picks up automatically** from registry

### GUI Column Layout

| # | Column | Content |
|---|--------|---------|
| 0 | Title | Knob name |
| 1 | Status | ✓ Applied / — / result value |
| 2 | Description | What it does |
| 3 | Category | Grouping |
| 4 | Risk | low/medium/high |
| 5 | Action | Apply / Reset / View / Test button |
| 6 | Config | Optional config button |

### Action Button Logic (in `_populate()`)
```python
status = self._knob_statuses.get(k.id, "unknown")
if k.id == "stack_detect":
    # Read-only info
    btn = QPushButton("View")
elif k.id == "scheduler_jitter_test":
    # Read-only test (updates status with result)
    btn = QPushButton("Test")
elif status == "applied":
    # Already applied → offer reset
    btn = QPushButton("Reset")
else:
    # Not applied → offer apply
    btn = QPushButton("Apply")
```

### Status Display Logic
```python
def _status_display(self, status: str) -> tuple[str, str]:
    if status.startswith("result:"):
        return (status[7:], "#1976d2")  # Show test result in blue
    mapping = {
        "applied": ("✓ Applied", "#2e7d32"),    # Green
        "not_applied": ("—", "#757575"),         # Gray dash
        "partial": ("◐ Partial", "#f57c00"),     # Orange
        "read_only": ("—", "#9e9e9e"),
        "unknown": ("—", "#9e9e9e"),
    }
    return mapping.get(status, ("—", "#9e9e9e"))
```

---

## 4. Learnings & Decisions

### What Works Well
1. **Per-knob buttons** - Simpler than dropdowns, no "batch apply" complexity
2. **Status in table** - User always knows current state
3. **Test results in status** - Shows "12 µs" instead of needing popup
4. **Smart reset strategies** - Different files need different restore methods:
   - Files we created → delete
   - User configs → restore from backup
   - Package-owned files → `rpm --restore` / `apt reinstall`

### Key Decisions Made
1. **No "Keep current" option** - If it's applied, show Reset. If not, show Apply.
2. **No batch preview** - Each action is immediate and per-knob
3. **pkexec for root** - Not sudo, because polkit integrates with desktop
4. **User services for PipeWire** - Detection must use `systemctl --user`, not system services
5. **Transactions per-knob** - Each apply creates its own transaction for clean undo

### Bugs Fixed (Don't Regress)
1. **Stack detection** - Must check user services (`--user`) for PipeWire/WirePlumber
2. **QjackCtl prefix handling** - Must preserve other prefixes like `nice -n -10` when adding taskset
3. **Cyclictest parsing** - Removed `-h400` histogram flag to get readable Max values
4. **Refresh after actions** - Must call `_refresh_statuses()` + `_populate()` after every apply/reset

### What Doesn't Work Yet
1. **Worker dev path** - Hardcoded `/home/chris/audioknob-gui` in worker script (fix before packaging)
2. **No blocker detection** - Should warn if user not in audio group, etc.

---

## 5. Testing Notes

### Manual Test Checklist
- [ ] Apply a root knob (e.g., rt_limits) → prompts for password → status shows ✓ Applied
- [ ] Reset same knob → prompts for password → status shows —
- [ ] Apply a user knob (qjackctl) → no password prompt → status shows ✓ Applied
- [ ] Click Test (jitter) → runs for 5 seconds → status shows "XX µs"
- [ ] Click View (stack) → shows PipeWire/JACK status in dialog
- [ ] Undo button → reverts last transaction
- [ ] Reset All → prompts → resets everything

### Known Test Environment
- **OS**: openSUSE Tumbleweed
- **Boot**: GRUB2-BLS with sdbootutil
- **Audio**: PipeWire + WirePlumber (user services)
- **Kernel cmdline**: Already has `threadirqs`

### Commands to Verify Changes
```bash
# Check PAM limits applied
cat /etc/security/limits.d/99-audioknob-gui.conf

# Check sysctl applied
cat /etc/sysctl.d/99-audioknob-gui.conf

# Check irqbalance status
systemctl is-enabled irqbalance

# Check QjackCtl config
grep Server ~/.config/rncbc.org/QjackCtl.conf
```

---

## 6. Blockers & Constraints

### Current Blockers
1. **Development-only worker path** - Worker has hardcoded repo path; must be fixed for distribution

### Constraints
1. **PySide6 required** - Not packaged in all distros; may need pip install or bundling
2. **polkit required** - For privilege escalation
3. **cyclictest optional** - Show warning if missing when Test clicked

### Distro-Specific Notes
| Distro | Package Manager | Boot System | Audio Group |
|--------|-----------------|-------------|-------------|
| openSUSE TW | zypper + rpm | sdbootutil (BLS) | audio |
| openSUSE Leap | zypper + rpm | GRUB2 | audio |
| Fedora | dnf + rpm | GRUB2 | audio |
| Debian/Ubuntu | apt + dpkg | GRUB2 | audio |
| Arch | pacman | varies | realtime |

---

## 7. Future Development Guide

### How to Use These Documents
1. **Read PROJECT_STATE.md first** (this file) - Understand architecture and patterns
2. **Check PLAN.md for next tasks** - User-facing roadmap with checkboxes
3. **Follow existing patterns** - New knobs should look like existing ones
4. **Update both docs** after significant changes

### Next Phase: Audio Configuration (Phase 4)
Add knobs for:
- Audio interface selection (list from `aplay -l`)
- Sample rate (44100, 48000, 96000, etc.)
- Buffer size (64, 128, 256, 512)
- Bit depth (16, 24, 32)

**Implementation approach**:
- Single "Audio Settings" knob with Config button
- Config button opens dialog with all settings
- Apply writes to PipeWire config (`~/.config/pipewire/pipewire.conf.d/`) or QjackCtl

### Next Phase: Monitoring (Phase 5)
- Underrun counter (parse PipeWire/JACK logs)
- Interrupt inspector (parse `/proc/interrupts`)
- Blocker detection (check group membership, RT kernel, etc.)

### Guardrails for AI Continuation
1. **Don't add dropdowns** - We simplified to buttons
2. **Don't add batch operations** - Each knob acts independently
3. **Don't skip status refresh** - Always refresh after any change
4. **Don't assume system services** - PipeWire is user-scope
5. **Don't break existing patterns** - Follow the code structure
6. **Update docs with learnings** - This file must stay current

---

## 8. Quick Reference

### Run App
```bash
~/audioknob-gui/bin/audioknob-gui
```

### Reinstall Worker (after code changes)
```bash
sudo install -D -m 0755 ~/audioknob-gui/packaging/audioknob-gui-worker /usr/local/libexec/audioknob-gui-worker
```

### Worker CLI Commands
```bash
# Check status of all knobs
python -m audioknob_gui.worker.cli status

# Preview a knob
python -m audioknob_gui.worker.cli preview rt_limits_audio_group

# List all changes made
python -m audioknob_gui.worker.cli list-changes

# Apply (root knobs - use pkexec)
pkexec /usr/local/libexec/audioknob-gui-worker apply rt_limits_audio_group
```

---

*Last updated: 2024-12-19*
*This document is the technical source of truth. Keep it current.*
