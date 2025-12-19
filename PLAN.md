# audioknob-gui: Plan

## How to Add a New Knob

### Step 1: Define in registry.json

Add to `config/registry.json`:

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
  "impl": {
    "kind": "...",
    "params": { ... }
  }
}
```

**New fields:**
- `requires_groups`: User must be in ONE of these groups (e.g., `["audio", "realtime"]`)
- `requires_commands`: Commands that must be available (e.g., `["cyclictest"]`)

### Step 2: Choose implementation kind

| Kind | When to use | Example |
|------|-------------|---------|
| `pam_limits_audio_group` | PAM limits file | rt_limits |
| `sysctl_conf` | Sysctl.d drop-in | swappiness |
| `sysfs_glob_kv` | Write to /sys | cpu_governor, thp |
| `systemd_unit_toggle` | Enable/disable service | irqbalance |
| `qjackctl_server_prefix` | QjackCtl config | jackd flags |
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

## Current Knobs (22)

### Implemented ✓
| Knob | Category | Status |
|------|----------|--------|
| Join audio groups | permissions | ✓ |
| Realtime limits | permissions | ✓ |
| Disable irqbalance | irq | ✓ |
| CPU governor: performance | cpu | ✓ |
| Reduce swappiness | vm | ✓ |
| THP: madvise | vm | ✓ |
| QjackCtl: realtime flags | stack | ✓ |
| Audio stack info | testing | ✓ |
| Scheduler jitter test | testing | ✓ |
| RT config scan | testing | ✓ |

### Placeholders (Need Implementation)
| Knob | Category | Notes |
|------|----------|-------|
| Enable rtirq | irq | Needs rtirq package |
| CPU DMA latency udev | cpu | Needs group check |
| Increase inotify | vm | sysctl.d |
| Reduce dirty writeback | vm | sysctl.d |
| Disable USB autosuspend | power | udev rule |
| Threaded IRQs | kernel | cmdline edit |
| Disable audit | kernel | cmdline edit |
| Disable mitigations | kernel | cmdline edit, HIGH RISK |
| PipeWire quantum | stack | user config |
| PipeWire sample rate | stack | user config |
| Disable GNOME tracker | services | user service |
| Disable KDE Baloo | services | user service |

### Future Phases
**Phase 4: Audio Hardware**
- Interface selection, sample rate, buffer, bit depth

**Phase 5: Monitoring**  
- Underrun counter, interrupt inspector

---

## Distro Notes

### Boot loader handling
| Distro | Method |
|--------|--------|
| openSUSE TW | Edit `/etc/kernel/cmdline`, run `sdbootutil update-all-entries` |
| openSUSE Leap | Edit `/etc/default/grub`, run `grub2-mkconfig` |
| Fedora | Edit `/etc/default/grub`, run `grub2-mkconfig` |
| Debian/Ubuntu | Edit `/etc/default/grub`, run `update-grub` |

### Audio group
- Most distros: `audio`
- Arch: `realtime` (from `realtime-privileges` package)

---

## Guardrails

1. **Everything undoable** - Transactions with backups
2. **Distro-aware** - Don't assume one way works everywhere
3. **User knows best** - Show status, let them choose
4. **One click actions** - No dropdowns, no batch mode, no preview step
5. **Lock until ready** - Missing groups? 🔒. Missing packages? 📦 Install.

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

*Last updated: 2025-06-20*
