# audioknob-gui: Comprehensive Plan

## Goal

Create a cross-distro GUI application that configures Linux systems for **professional realtime audio** work. The app presents system tweaks ("knobs") in a logical, grouped manner with:

- **Preview → Confirm → Apply** workflow (no silent changes)
- **Transaction-based** changes with backup and undo
- **Distro-aware** implementation (openSUSE, Fedora, Debian/Ubuntu, Arch)
- **Audio stack detection** (PipeWire, JACK, ALSA)

## Research Sources

- https://wiki.linuxaudio.org/wiki/system_configuration
- https://wiki.archlinux.org/title/Professional_audio
- https://linuxmusicians.com/viewtopic.php?t=27121 (Fedora PipeWire guide)
- https://gitlab.freedesktop.org/pipewire/pipewire/-/wikis/Performance-tuning
- https://autostatic.com/

---

## Knob Categories & Definitive List

### 1. Permissions & User Setup

| Knob ID | Title | Description | Risk | Root |
|---------|-------|-------------|------|------|
| `audio_group_membership` | Add user to audio group | Ensures user is in `audio` (or `realtime` on Arch) group | low | yes |
| `rt_limits_audio_group` | Realtime limits for audio group | PAM limits: rtprio 95, memlock unlimited, nice -10 | low | yes |

**Distro notes:**
- Arch uses `realtime` group (from `realtime-privileges` package)
- Most distros use `audio` group
- File locations: `/etc/security/limits.d/99-audioknob-gui.conf`

---

### 2. Kernel & Boot Parameters

| Knob ID | Title | Description | Risk | Root | Reboot |
|---------|-------|-------------|------|------|--------|
| `kernel_threadirqs` | Enable threaded IRQs | Adds `threadirqs` to kernel cmdline | medium | yes | yes |
| `kernel_preempt_check` | Check kernel preemption | Read-only: shows CONFIG_PREEMPT status | low | no | no |
| `kernel_mitigations_off` | Disable CPU mitigations | Adds `mitigations=off` (security tradeoff!) | high | yes | yes |
| `kernel_audit_off` | Disable kernel audit | Adds `audit=0` to reduce overhead | medium | yes | yes |
| `kernel_preempt_full` | Force full preemption | Adds `preempt=full` (if not RT kernel) | medium | yes | yes |

**Distro notes:**
- openSUSE Tumbleweed (GRUB2-BLS): edit `/etc/kernel/cmdline`, run `sdbootutil update-all-entries`
- openSUSE Leap/traditional GRUB: edit `/etc/default/grub` → `GRUB_CMDLINE_LINUX_DEFAULT`, run `grub2-mkconfig -o /boot/grub2/grub.cfg`
- Fedora: edit `/etc/default/grub`, run `grub2-mkconfig`
- Debian/Ubuntu: edit `/etc/default/grub`, run `update-grub`
- Arch: edit `/etc/default/grub` or use `kernelstub` for systemd-boot

**Detection needed:**
- Check if system uses BLS (`/boot/loader/entries/` exists, `sdbootutil` present)
- Check if system uses traditional GRUB (`/etc/default/grub` + `grub2-mkconfig`)

---

### 3. CPU & Power Management

| Knob ID | Title | Description | Risk | Root | Persist |
|---------|-------|-------------|------|------|---------|
| `cpu_governor_performance_temp` | CPU governor: performance (temp) | Writes to `/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor` | low | yes | no |
| `cpu_governor_performance_persist` | CPU governor: performance (persist) | Configures cpupower service | medium | yes | yes |
| `cpu_dma_latency_udev` | CPU DMA latency udev rule | Allows audio group write access to `/dev/cpu_dma_latency` | low | yes | yes |
| `cpu_idle_poll` | Disable CPU idle (extreme) | Kernel param `idle=poll` - uses more power, lowest latency | high | yes | yes |
| `cpu_cstate_disable` | Disable deep C-states | Prevents latency from CPU wakeup | medium | yes | yes |

**cpupower service locations:**
- openSUSE/Fedora: `/etc/sysconfig/cpupower`
- Debian: `/etc/default/cpupower`

**cpu_dma_latency udev rule:**
```
# /etc/udev/rules.d/99-cpu-dma-latency.rules
KERNEL=="cpu_dma_latency", GROUP="audio", MODE="0660"
```
(From Ardour: https://github.com/Ardour/ardour/blob/master/tools/udev/99-cpu-dma-latency.rules)

---

### 4. IRQ Management

| Knob ID | Title | Description | Risk | Root |
|---------|-------|-------------|------|------|
| `irqbalance_disable` | Disable irqbalance | Stops automatic IRQ rebalancing | low | yes |
| `rtirq_enable` | Enable rtirq service | Prioritizes audio IRQ threads | medium | yes |
| `irq_affinity_audio` | Pin audio IRQs to CPU | Sets IRQ affinity for sound card | medium | yes |

**rtirq config locations:**
- openSUSE: `/etc/rtirq.conf`
- Fedora: `/etc/sysconfig/rtirq`
- Debian: `/etc/default/rtirq`

**Default rtirq priority config:**
```
RTIRQ_NAME_LIST="snd xhci usb ehci"
RTIRQ_PRIO_HIGH=90
RTIRQ_PRIO_DECR=5
RTIRQ_PRIO_LOW=51
```

---

### 5. Memory & VM Settings

| Knob ID | Title | Description | Risk | Root |
|---------|-------|-------------|------|------|
| `swappiness` | Reduce swappiness | `vm.swappiness=10` in sysctl.d | low | yes |
| `thp_mode_madvise` | THP: madvise mode | `/sys/kernel/mm/transparent_hugepage/enabled` | medium | yes |
| `inotify_max_watches` | Increase inotify watches | `fs.inotify.max_user_watches=600000` for DAWs | low | yes |
| `dirty_bytes` | Reduce dirty writeback | Lower writeback thresholds for less I/O latency | low | yes |

**sysctl.d file:** `/etc/sysctl.d/99-audioknob-gui.conf`

**dirty_bytes settings:**
```
vm.dirty_bytes = 50331648
vm.dirty_background_bytes = 16777216
```

---

### 6. Filesystem Tuning

| Knob ID | Title | Description | Risk | Root | Reboot |
|---------|-------|-------------|------|------|--------|
| `fstab_noatime` | Add noatime to fstab | Reduces disk writes | low | yes | yes |
| `scheduler_deadline` | I/O scheduler: deadline | For spinning disks (not needed for NVMe) | low | yes | no |

---

### 7. Timer Settings

| Knob ID | Title | Description | Risk | Root |
|---------|-------|-------------|------|------|
| `rtc_max_freq` | Increase RTC max frequency | `/sys/class/rtc/rtc0/max_user_freq=2048` | low | yes |
| `hpet_max_freq` | Increase HPET max frequency | `/proc/sys/dev/hpet/max-user-freq=2048` | low | yes |

---

### 8. PCI Latency

| Knob ID | Title | Description | Risk | Root |
|---------|-------|-------------|------|------|
| `pci_latency_timer` | Increase PCI latency timer | `setpci -v -d *:* latency_timer=b0` | medium | yes |
| `pci_latency_soundcard` | Max soundcard PCI latency | `setpci -v -s $CARD latency_timer=ff` | medium | yes |

---

### 9. Services & Daemons

| Knob ID | Title | Description | Risk | Root |
|---------|-------|-------------|------|------|
| `disable_tracker` | Disable tracker-miner | File indexer causes latency spikes | low | no |
| `disable_baloo` | Disable baloo (KDE) | KDE file indexer | low | no |
| `disable_packagekit_refresh` | Disable PackageKit auto-refresh | Background package checks | low | yes |
| `usb_autosuspend_disable` | Disable USB autosuspend | Prevents USB audio device dropouts | low | yes |

---

### 10. Audio Stack Configuration

| Knob ID | Title | Description | Risk | Root |
|---------|-------|-------------|------|------|
| `stack_detect` | Detect audio stack | Read-only: PipeWire/JACK/ALSA status | low | no |
| `qjackctl_server_prefix_rt` | QjackCtl realtime flags | Ensure `-R` flag in QjackCtl Server Prefix | low | no |
| `pipewire_quantum` | PipeWire quantum setting | Adjust buffer size in PipeWire config | low | no |
| `pipewire_rt_priority` | PipeWire RT priority | Adjust realtime priority for PipeWire | low | no |

**QjackCtl config:** `~/.config/rncbc.org/QjackCtl.conf`

**PipeWire config:** `~/.config/pipewire/pipewire.conf.d/` or `/etc/pipewire/pipewire.conf.d/`

---

### 11. Testing & Diagnostics (Read-only)

| Knob ID | Title | Description | Risk | Root |
|---------|-------|-------------|------|------|
| `scheduler_jitter_test` | Scheduler jitter (cyclictest) | Run cyclictest, report max latency | low | yes |
| `jack_xrun_test` | JACK xrun test | Monitor xruns over time | low | no |
| `rtcqs_check` | Run rtcqs checks | Comprehensive RT audio readiness check | low | no |

---

## Distro-Specific Implementation

### Package Managers

| Distro Family | Package Manager | Install Command |
|---------------|-----------------|-----------------|
| openSUSE | zypper | `zypper install -y PKG` |
| Fedora/RHEL | dnf | `dnf install -y PKG` |
| Debian/Ubuntu | apt | `apt-get update && apt-get install -y PKG` |
| Arch | pacman | `pacman -S --noconfirm PKG` |

### GRUB/Boot Loader

| Distro | Boot System | Config File | Update Command |
|--------|-------------|-------------|----------------|
| openSUSE TW (BLS) | systemd-boot/sdbootutil | `/etc/kernel/cmdline` | `sdbootutil update-all-entries` |
| openSUSE Leap | GRUB2 | `/etc/default/grub` | `grub2-mkconfig -o /boot/grub2/grub.cfg` |
| Fedora | GRUB2 | `/etc/default/grub` | `grub2-mkconfig -o /boot/grub2/grub.cfg` |
| Debian/Ubuntu | GRUB2 | `/etc/default/grub` | `update-grub` |
| Arch (GRUB) | GRUB2 | `/etc/default/grub` | `grub-mkconfig -o /boot/grub/grub.cfg` |
| Arch (systemd-boot) | systemd-boot | `/boot/loader/entries/*.conf` | `bootctl update` |

### Audio Group

| Distro | Group Name | Package |
|--------|------------|---------|
| Most | `audio` | (built-in) |
| Arch | `realtime` | `realtime-privileges` |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         GUI (PySide6)                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ Knob List   │  │  Preview    │  │   Apply     │              │
│  │ (grouped)   │  │  Dialog     │  │  /Undo      │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
            ┌───────▼───────┐   ┌───────▼───────┐
            │  User Knobs   │   │  Root Knobs   │
            │ (no pkexec)   │   │ (via pkexec)  │
            └───────┬───────┘   └───────┬───────┘
                    │                   │
            ┌───────▼───────┐   ┌───────▼───────┐
            │ User Tx Dir   │   │ Root Tx Dir   │
            │ ~/.local/...  │   │ /var/lib/...  │
            └───────────────┘   └───────────────┘
```

### Transaction Model

- **User knobs**: `~/.local/state/audioknob-gui/transactions/<txid>/`
- **Root knobs**: `/var/lib/audioknob-gui/transactions/<txid>/`
- Each transaction contains:
  - `manifest.json` (what was changed)
  - `backups/` (original file contents)
  - `effects/` (for ephemeral changes like sysfs)

---

## Implementation Phases

### Phase 1: Core Infrastructure ✅
- [x] Repo skeleton
- [x] Registry schema
- [x] Transaction model (backup/restore)
- [x] Privilege model (pkexec)
- [x] Basic GUI

### Phase 2: Essential Knobs ✅
- [x] rt_limits_audio_group
- [x] irqbalance_disable
- [x] cpu_governor_performance_temp
- [x] swappiness
- [x] thp_mode_madvise
- [x] stack_detect (read-only)
- [x] scheduler_jitter_test (read-only)

### Phase 3: User-Space Knobs 🔄
- [x] qjackctl_server_prefix_rt (partial - needs CPU core UI)
- [ ] pipewire_quantum
- [ ] pipewire_rt_priority
- [ ] disable_tracker
- [ ] disable_baloo

### Phase 4: Advanced System Knobs
- [ ] kernel_threadirqs (with distro-aware GRUB handling)
- [ ] kernel_audit_off
- [ ] cpu_dma_latency_udev
- [ ] cpu_cstate_disable
- [ ] rtirq_enable
- [ ] inotify_max_watches
- [ ] dirty_bytes
- [ ] rtc_max_freq / hpet_max_freq
- [ ] pci_latency_timer
- [ ] usb_autosuspend_disable

### Phase 5: Distro Detection & Adaptation
- [ ] Detect distro family (openSUSE/Fedora/Debian/Arch)
- [ ] Detect boot loader type (BLS vs traditional GRUB)
- [ ] Adapt knob implementations per distro
- [ ] Package manager integration for dependencies

### Phase 6: Polish & Testing
- [ ] rtcqs integration
- [ ] Comprehensive testing on multiple distros
- [ ] Documentation
- [ ] Packaging (RPM, DEB, Flatpak?)

---

## Guardrails (Non-negotiable)

1. **No system changes without explicit user confirmation**
2. **Every change is transactional** - backup before, manifest after
3. **Undo is always possible** for applied changes
4. **Preview shows exact changes** before apply
5. **Read-only detection first** - understand before modifying
6. **Distro-aware** - don't assume one way works everywhere

---

## Current System Status (this machine)

- **OS**: openSUSE Tumbleweed
- **Boot**: GRUB2-BLS with sdbootutil
- **Kernel cmdline**: `/etc/kernel/cmdline` (already has `threadirqs`)
- **Audio stack**: (detect at runtime)

---

## References

### Kernel Parameters for Audio
```
threadirqs          # Threaded IRQ handlers
preempt=full        # Full kernel preemption
mitigations=off     # Disable CPU mitigations (security tradeoff)
idle=poll           # Never enter idle state (power tradeoff)
audit=0             # Disable kernel audit subsystem
```

### Sysctl Settings
```
vm.swappiness = 10
fs.inotify.max_user_watches = 600000
vm.dirty_bytes = 50331648
vm.dirty_background_bytes = 16777216
```

### PAM Limits
```
@audio - rtprio 95
@audio - memlock unlimited
@audio - nice -10
```

### Key Tools
- `cyclictest` - scheduler latency testing
- `rtcqs` - RT audio readiness checker (https://codeberg.org/rtcqs/rtcqs)
- `setpci` - PCI configuration
- `chrt` - set realtime priority
- `taskset` - CPU affinity

---

## Learnings from Multi-Agent Comparison

This plan incorporates insights from comparing multiple AI agents (GPT 5.2, Composer, Gemini 3 Pro, Opus 4.5):

### Added from Gemini 3 Pro:
- `audit=0` kernel parameter
- `preempt=full` kernel parameter
- `cpu_cstate_disable` knob
- `dirty_bytes` sysctl settings
- Explicit "Bootloader Abstraction" naming

### Added from Composer:
- `usb_autosuspend_disable` knob
- NetworkManager power management consideration

### Best practices identified:
- Run terminal commands to verify actual system state (not just read docs)
- Name abstraction layers explicitly
- Have concrete, actionable next steps per phase

---

*Document created by Claude Opus 4.5 on 2024-12-19*
*Based on research from Linux Audio Wiki, Arch Wiki, LinuxMusicians forum, and multi-agent comparison*
