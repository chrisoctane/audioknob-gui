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
  "capabilities": { "read": true, "apply": true, "restore": true },
  "impl": {
    "kind": "...",
    "params": { ... }
  }
}
```

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

| Knob type | Column 4 (Action) | Column 5 (Info) |
|-----------|-------------------|-----------------|
| Not applied | "Apply" button | "ℹ" info button |
| Applied | "Reset" button | "ℹ" info button |
| Not implemented | "—" disabled | "ℹ" info button |
| Read-only info | "View" button | "ℹ" info button |
| Read-only test | "Test" button | "ℹ" info button |

**Columns**: Knob | Status | Category | Risk | Action | ℹ

---

## Implementation Patterns

### Normal knob (context-sensitive button)
```python
status = self._knob_statuses.get(k.id, "unknown")
if status == "applied":
    btn = QPushButton("Reset")
    btn.clicked.connect(lambda _, kid=k.id: self._on_reset_knob(kid))
else:
    btn = QPushButton("Apply")
    btn.clicked.connect(lambda _, kid=k.id: self._on_apply_knob(kid))
self.table.setCellWidget(r, 5, btn)
```

### Read-only info
```python
btn = QPushButton("View")
btn.clicked.connect(self.on_view_info)
self.table.setCellWidget(r, 5, btn)
```

### Read-only test (updates status)
```python
btn = QPushButton("Test")
btn.clicked.connect(lambda _, kid=k.id: self.on_run_test(kid))
self.table.setCellWidget(r, 5, btn)
```

### With config dialog
```python
btn = QPushButton("Config")
btn.clicked.connect(lambda: self.on_configure(knob_id))
self.table.setCellWidget(r, 6, btn)
```

---

## Planned Knobs

### Phase 4: Audio Configuration
- `audio_interface_select` - Select ALSA device
- `sample_rate` - 44100, 48000, 96000
- `buffer_size` - 64, 128, 256, 512
- `bit_depth` - 16, 24, 32
- `pipewire_quantum` - PipeWire buffer tuning

### Phase 5: Monitoring
- `underrun_monitor` - Count xruns
- `interrupt_inspector` - View audio IRQs
- `blocker_check` - What's preventing optimizations

### Phase 6: User Services
- `disable_tracker` - GNOME file indexer
- `disable_baloo` - KDE file indexer
- `usb_autosuspend_disable`

### Phase 7: Advanced System
- `kernel_threadirqs` - Kernel cmdline
- `kernel_audit_off` - Disable audit
- `cpu_dma_latency_udev` - udev rule
- `rtirq_enable` - IRQ priorities

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

1. **No silent changes** - Always preview first
2. **Everything undoable** - Transactions with backups
3. **Distro-aware** - Don't assume one way works everywhere
4. **User knows best** - Show status, let them choose

---

## Learnings

1. **Status column is essential** - Users need to see what's applied
2. **Per-knob restore** - Global undo isn't enough
3. **Read-only needs UI** - Buttons for info/tests, not dropdowns
4. **pkexec is enough** - No need for "type YES" confirmations
5. **Check user services** - PipeWire runs as user, not system
6. **Smart reset** - Different files need different restore strategies

---

## References

- https://wiki.linuxaudio.org/wiki/system_configuration
- https://wiki.archlinux.org/title/Professional_audio
- https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning

---

*Last updated: 2024-12-19*
