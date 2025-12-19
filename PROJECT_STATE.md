# audioknob-gui: Project State

## Goal

A GUI app to configure Linux for **professional realtime audio** with:
- **Simple UI** - One button per knob: Apply or Reset
- **Transaction-based** - Every change has undo
- **Distro-aware** - Works on openSUSE, Fedora, Debian, Arch

---

## Progress

| Phase | Status | Summary |
|-------|--------|---------|
| 1. Foundation | ✅ Done | GUI, Worker, Registry, Transactions |
| 2. Essential Knobs | ✅ Done | 8 knobs working |
| 3. UX Refinements | ✅ Done | Per-knob Apply/Reset buttons, status display |
| 4. Audio Config | 🔄 Next | Interface, sample rate, buffer, bit depth |
| 5. Monitoring | 🔲 | Underruns, interrupts, blockers |
| 6. Advanced Knobs | 🔲 | Kernel params, GRUB handling |
| 7. Distro Abstraction | 🔲 | Detect and adapt per distro |
| 8. Packaging | 🔲 | RPM, DEB, proper install |

---

## Current Knobs (8)

| Knob | Type | Root? |
|------|------|-------|
| rt_limits_audio_group | PAM limits | Yes |
| irqbalance_disable | Systemd toggle | Yes |
| cpu_governor_performance_temp | Sysfs write | Yes |
| swappiness | Sysctl.d | Yes |
| thp_mode_madvise | Sysfs write | Yes |
| qjackctl_server_prefix_rt | User config | No |
| stack_detect | Read-only info | No |
| scheduler_jitter_test | Read-only test | No |

---

## UI Summary

| Status | Action Button |
|--------|---------------|
| Not applied | **Apply** |
| ✓ Applied | **Reset** |
| Read-only | **View** or **Test** |

**Top bar**: Undo, Reset All

---

## Quick Reference

### Run the app
```bash
~/audioknob-gui/bin/audioknob-gui
```

### Reinstall worker (after code changes)
```bash
sudo install -D -m 0755 ~/audioknob-gui/packaging/audioknob-gui-worker /usr/local/libexec/audioknob-gui-worker
```

### Key files
- **Registry**: `config/registry.json`
- **GUI**: `audioknob_gui/gui/app.py`
- **Worker**: `audioknob_gui/worker/cli.py`

---

## Known Issues

1. **Hardcoded dev path** in worker - fix before packaging

---

## See Also

- **PLAN.md** - How to add new knobs, implementation patterns

---

*Last updated: 2024-12-19*
