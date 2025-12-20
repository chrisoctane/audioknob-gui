# audioknob-gui: Plan

## How to Add a New Knob

### Step 1: Define in registry.json

Add to `config/registry.json` (**canonical source**), inside the top-level `knobs` array:

```json
{
  "schema": 1,
  "knobs": [
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
      "impl": {
        "kind": "...",
        "params": { ... }
      }
    }
  ]
}
```

**⚠️ IMPORTANT: After editing, sync to package data:**
```bash
cp config/registry.json audioknob_gui/data/registry.json
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

| Knob type | Status | Column 4 (Action) | Column 5 (Info) |
|-----------|--------|-------------------|-----------------|
| Not applied | — | "Apply" button | "ℹ" info button |
| Applied | ✓ Applied | "Reset" button | "ℹ" info button |
| Not implemented | — | "—" disabled | "ℹ" info button |
| Missing groups | 🔒 | "🔒" disabled | "ℹ" info button |
| Missing packages | 📦 | "Install" button | "ℹ" info button |
| Read-only info | — | "View" button | "ℹ" info button |
| Read-only test | — | "Test"/"Scan" button | "ℹ" info button |
| Group join knob | — | "Join" button | "ℹ" info button |

**Columns**: Knob | Status | Category | Risk | Action | ℹ

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
self.table.setCellWidget(r, 4, btn)  # Column 4 = Action
```

### Read-only info
```python
btn = QPushButton("View")
btn.clicked.connect(self.on_view_stack)
self.table.setCellWidget(r, 4, btn)  # Column 4 = Action
```

### Read-only test (updates status)
```python
btn = QPushButton("Test")
btn.clicked.connect(lambda _, kid=k.id: self.on_run_test(kid))
self.table.setCellWidget(r, 4, btn)  # Column 4 = Action
```

### With config dialog (via info popup)
```python
# In _show_knob_info(), add config button for knobs that need it:
if k.id == "qjackctl_server_prefix_rt":
    config_btn = QPushButton("Configure CPU Cores...")
    config_btn.clicked.connect(lambda: self.on_configure_knob(k.id))
    layout.addWidget(config_btn)
```

---

## Current Knobs (22) - ALL IMPLEMENTED ✓

### Permissions
| Knob | Kind | Status |
|------|------|--------|
| Join audio groups | group_membership | ✓ |
| Realtime limits for @audio | pam_limits_audio_group | ✓ |

### IRQ
| Knob | Kind | Status |
|------|------|--------|
| Disable irqbalance | systemd_unit_toggle | ✓ |
| Enable rtirq service | systemd_unit_toggle | ✓ |

### CPU
| Knob | Kind | Status |
|------|------|--------|
| CPU governor: performance | sysfs_glob_kv | ✓ |
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

**Why two copies?**
- `config/` is at repo root for easy discovery/editing
- `audioknob_gui/data/` is inside the package so `importlib.resources` can find it when installed via pip

**Sync procedure (after any registry edit):**
```bash
cp config/registry.json audioknob_gui/data/registry.json
git add config/registry.json audioknob_gui/data/registry.json
```

**Pre-commit check (recommended):**
```bash
diff config/registry.json audioknob_gui/data/registry.json || echo "REGISTRY OUT OF SYNC"
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
