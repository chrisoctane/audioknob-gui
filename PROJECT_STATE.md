# audioknob-gui: Technical State Document

> **Purpose**: This is the definitive technical reference for the project. Any AI or developer continuing this work MUST read this document first. It explains not just WHAT we built, but WHY we made each decision.
>
> **For the user-facing guide, see PLAN.md**

---

## 1. Project Vision & Principles

### The Problem We're Solving
Linux audio configuration for professional/realtime work requires many system tweaks spread across different files, services, and kernel parameters. Users must:
- Know which tweaks exist
- Know how to apply them for their specific distro
- Remember what they changed
- Be able to undo changes safely

### Our Solution
A single GUI that:
1. Shows all relevant tweaks in one place
2. Shows current status (applied or not)
3. Applies tweaks with one click
4. Can undo any change
5. Works across distros

### Core Principles (Non-Negotiable)

| Principle | Reasoning |
|-----------|-----------|
| **Transaction-based** | Every change creates a backup BEFORE modifying. This ensures we can always restore. Never modify without backup. |
| **Status visibility** | User must always see current state. No guessing. If applied, show ✓. If not, show —. |
| **One button per action** | Simpler than dropdowns. User sees status, clicks Apply or Reset. No cognitive load. |
| **Distro-aware** | Linux is fragmented. PipeWire vs JACK, systemd-boot vs GRUB, rpm vs deb. Detect and adapt. |
| **Privilege separation** | Root operations MUST go through pkexec (not sudo). Polkit integrates with desktop auth. |
| **Fail-safe defaults** | If we can't determine status, show "—" not "Applied". Conservative is safer. |

---

## 2. Architecture Deep Dive

### Why This Structure?

```
audioknob-gui/
├── bin/audioknob-gui              # Entry point (bash script)
├── config/registry.json           # Knob definitions (declarative)
├── packaging/                     # Deployment files
├── audioknob_gui/
│   ├── gui/app.py                 # UI layer (PySide6)
│   ├── worker/                    # Business logic (can run as root)
│   ├── core/                      # Shared utilities
│   ├── platform/                  # OS detection
│   └── testing/                   # Test tools
```

**Why separate worker from GUI?**
- Worker runs as root via pkexec
- GUI runs as user
- Clean privilege boundary
- Worker can be tested independently via CLI

**Why registry.json?**
- Declarative knob definitions
- Easy to add new knobs without code changes (for simple kinds)
- Single source of truth for what knobs exist
- Can be validated/linted

### Data Flow (Detailed)

#### Apply Flow
```
1. User clicks "Apply" button in GUI
2. GUI finds knob in registry, checks requires_root
3. If requires_root:
   - GUI calls: pkexec /usr/local/libexec/audioknob-gui-worker apply <knob_id>
   - User sees polkit password prompt
   - Worker runs as root
4. If not requires_root:
   - GUI calls: python -m audioknob_gui.worker.cli apply-user <knob_id>
   - Worker runs as current user
5. Worker:
   a. Creates new transaction directory with timestamp-based ID
   b. For each file to modify:
      - Backs up current content to transaction/backups/
      - Records metadata (existed, mode, uid, gid, reset_strategy, package)
   c. Applies the change (write file, run command, etc.)
   d. Writes manifest.json with all metadata
   e. Prints JSON result to stdout
6. GUI parses result, stores txid in state.json
7. GUI calls _refresh_statuses() to re-check all knob states
8. GUI calls _populate() to rebuild table with new status
```

#### Reset Flow
```
1. User clicks "Reset" button
2. GUI calls worker with restore-knob command
3. Worker:
   a. Finds transaction that applied this knob
   b. Reads backup metadata from manifest
   c. Based on reset_strategy:
      - "delete": Remove the file we created
      - "backup": Copy backup file back to original location
      - "package": Call rpm --restore or apt reinstall
   d. For effects (sysfs, systemd): restore previous state
4. GUI refreshes status display
```

### Privilege Model (Why pkexec?)

**Why not sudo?**
- sudo requires terminal or password in env
- pkexec integrates with desktop (graphical prompt)
- polkit policies allow fine-grained control
- User sees clear "application wants to make changes" dialog

**Security boundary:**
- GUI (untrusted, user-level) → communicates via subprocess + JSON
- Worker (trusted, can run as root) → validates all inputs
- Worker is installed to /usr/local/libexec/ (not in user's PATH)
- Polkit policy explicitly allows this specific binary

**Development workaround:**
- Worker has hardcoded `/home/chris/audioknob-gui` path added to sys.path
- This is a development convenience, MUST be removed for packaging
- Production: package should install into system Python or bundle dependencies

---

## 3. Transaction System

### Why Transactions?

Without transactions:
- User applies change
- Something breaks
- User doesn't remember what file was changed
- Original content is lost
- System is in unknown state

With transactions:
- Every change is recorded
- Original content is preserved
- Undo is always possible
- User can see history

### Transaction Structure

```
/var/lib/audioknob-gui/transactions/1a2b3c4d5e6f7890/
├── manifest.json
└── backups/
    └── etc__security__limits.d__99-audioknob-gui.conf
```

**manifest.json example:**
```json
{
  "schema": 1,
  "txid": "1a2b3c4d5e6f7890",
  "applied": ["rt_limits_audio_group"],
  "backups": [
    {
      "path": "/etc/security/limits.d/99-audioknob-gui.conf",
      "existed": false,
      "we_created": true,
      "mode": null,
      "uid": null,
      "gid": null,
      "backup_key": "etc__security__limits.d__99-audioknob-gui.conf",
      "reset_strategy": "delete",
      "package": null
    }
  ],
  "effects": [
    {
      "kind": "sysfs_write",
      "path": "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor",
      "before": "schedutil",
      "after": "performance"
    }
  ]
}
```

### Reset Strategies (Critical Logic)

| Strategy | When Used | Action |
|----------|-----------|--------|
| `delete` | File didn't exist before, we created it | Delete the file |
| `backup` | File existed, we modified it, it's a user file | Restore from our backup |
| `package` | File existed, owned by a package (rpm/deb) | Use package manager to restore |

**How we determine strategy (in backup_file()):**
```python
if not file_existed or we_created:
    strategy = "delete"
elif path.startswith(home_dir):
    strategy = "backup"  # User files always use backup
else:
    pkg_info = get_package_owner(path)
    if pkg_info.owned:
        strategy = "package"
    else:
        strategy = "backup"
```

**Why this matters:**
- If user updates their system and package restores a file, our backup is stale
- Package manager has the "true" default for system files
- User files (like ~/.config/*) aren't package-managed, so backup is correct

---

## 4. Registry Schema

### Full Knob Definition

```json
{
  "id": "rt_limits_audio_group",
  "title": "Realtime limits for audio group",
  "description": "Allows audio group to use realtime scheduling",
  "category": "permissions",
  "risk_level": "low",
  "requires_root": true,
  "requires_reboot": false,
  "requires_groups": ["audio", "realtime"],
  "requires_commands": [],
  "capabilities": {
    "read": true,
    "apply": true,
    "restore": true
  },
  "impl": {
    "kind": "pam_limits_audio_group",
    "params": {
      "path": "/etc/security/limits.d/99-audioknob-gui.conf",
      "lines": [
        "@audio - rtprio 95",
        "@audio - memlock unlimited", 
        "@audio - nice -10"
      ]
    }
  }
}
```

### Field Explanations

| Field | Type | Purpose |
|-------|------|---------|
| `id` | string | Unique identifier, used in code and transactions |
| `title` | string | Human-readable name shown in GUI |
| `description` | string | Shown in info popup (ℹ button) |
| `category` | enum | Grouping: permissions, cpu, irq, vm, kernel, stack, services, power, testing |
| `risk_level` | enum | low/medium/high - shown in Risk column |
| `requires_root` | bool | If true, apply uses pkexec |
| `requires_reboot` | bool | If true, show warning (not enforced) |
| `requires_groups` | array | User must be in ONE of these groups (e.g. ["audio", "realtime"]) |
| `requires_commands` | array | Commands that must be available (e.g. ["cyclictest"]) |
| `capabilities.read` | bool | Can we check current status? |
| `capabilities.apply` | bool | Can we apply this knob? |
| `capabilities.restore` | bool | Can we restore to original? |
| `impl.kind` | string | Which implementation handler to use |
| `impl.params` | object | Parameters passed to handler |

### Dependency System

**Group Requirements (requires_groups):**
- If user is NOT in any of the listed groups, knob is locked (🔒)
- User must be in at least ONE of the groups (OR logic)
- "Join audio groups" knob adds user to all available audio groups
- Requires logout/login after joining

**Package Requirements (requires_commands):**
- If any command is missing, knob shows 📦 and "Install" button
- Clicking Install uses pkexec + package manager (zypper/dnf/apt/pacman)
- Package mappings in `platform/packages.py`:
  ```python
  PACKAGE_MAPPINGS = {
      "cyclictest": {"rpm": "rt-tests", "dpkg": "rt-tests", "pacman": "rt-tests"},
      "rtirq": {"rpm": "rtirq", "dpkg": "rtirq-init", "pacman": "rtirq"},
  }
  ```

### Implementation Kinds

| Kind | What It Does | Status Check |
|------|--------------|--------------|
| `pam_limits_audio_group` | Appends lines to a limits.d file | Check if all lines present |
| `sysctl_conf` | Appends lines to sysctl.d file | Check if all lines present |
| `sysfs_glob_kv` | Writes value to /sys paths matching glob | Read current values |
| `systemd_unit_toggle` | Enable/disable a systemd unit | Check is-enabled |
| `qjackctl_server_prefix` | Modify QjackCtl Server command | Parse config, check -R flag |
| `read_only` | No changes, just info/test | Returns "read_only" status |

---

## 5. GUI Implementation Details

### State Management

**state.json** (`~/.local/state/audioknob-gui/state.json`):
```json
{
  "schema": 1,
  "last_txid": null,
  "last_user_txid": "abc123",
  "last_root_txid": "def456",
  "font_size": 11,
  "qjackctl_cpu_cores": [2, 3]
}
```

**Why store txids?**
- Undo button needs to know which transaction to restore
- Separate user/root txids because they're in different directories
- `last_txid` is legacy compatibility

**Why store qjackctl_cpu_cores?**
- CPU core selection is a GUI-level preference
- Applied via override when worker runs
- Not stored in registry (that's static)

### Status Refresh Flow

```python
def _refresh_statuses(self):
    # Call worker CLI to check all knob statuses
    p = subprocess.run([...worker..., "status"], capture_output=True)
    data = json.loads(p.stdout)
    for item in data["statuses"]:
        self._knob_statuses[item["knob_id"]] = item["status"]

def _populate(self):
    for row, knob in enumerate(self.registry):
        status = self._knob_statuses.get(knob.id, "unknown")
        # Create button based on status
        if status == "applied":
            btn = QPushButton("Reset")
        else:
            btn = QPushButton("Apply")
        # ... set up click handler
```

**Why refresh before populate?**
- Status might have changed externally (user ran command manually)
- Ensures UI always reflects reality
- Called after every apply/reset action

### Button Click Handlers

```python
def _on_apply_knob(self, knob_id):
    # 1. Find knob to check requires_root
    k = next(k for k in self.registry if k.id == knob_id)
    
    # 2. Call appropriate worker
    if k.requires_root:
        result = _run_worker_apply_pkexec([knob_id])
        self.state["last_root_txid"] = result["txid"]
    else:
        result = _run_worker_apply_user([knob_id])
        self.state["last_user_txid"] = result["txid"]
    
    # 3. Save state for undo
    save_state(self.state)
    
    # 4. CRITICAL: Refresh UI
    self._refresh_statuses()
    self._populate()
```

**Why immediate action (not batch)?**
- Simpler mental model for user
- No need to remember what was selected
- Status updates immediately
- Undo is per-transaction anyway

---

## 6. Learnings & Decisions

### Design Decisions with Reasoning

| Decision | Reasoning |
|----------|-----------|
| Per-knob buttons instead of dropdown | Dropdowns require selecting, then clicking Apply. Two steps vs one. Users found it confusing when "Keep current" was selected for an already-applied knob. |
| No "Keep current" option | If it's applied, you might want to reset. If not applied, you might want to apply. "Keep current" is the absence of action - just don't click anything. |
| No batch preview | Original design had: select multiple → preview → apply. Too complex. Now: click Apply, it happens. Click Undo if wrong. |
| Test results in status column | Originally showed popup. But user wanted to see "how good is my system" at a glance. Status column shows "12 µs" - instant visibility. |
| Check user services for PipeWire | Bug: Originally checked `systemctl is-active pipewire.service` which is system scope. PipeWire runs as user: `systemctl --user is-active pipewire.service`. Wasted 30 min debugging. |
| Preserve prefixes in QjackCtl | Bug: When adding taskset, we were removing `nice -n -10` prefix. Users had carefully configured commands. Now we preserve everything except taskset. |
| Smart reset strategies | Original: always restore from backup. Problem: if user updated system, package restored original file, our backup was stale. Solution: for package-owned files, use package manager to restore. |

### Bugs Fixed (Prevent Regression)

| Bug | Root Cause | Fix |
|-----|------------|-----|
| Stack detection always false | Checking system services, PipeWire is user service | Use `systemctl --user` |
| QjackCtl lost nice prefix | Rebuild logic only kept jackd and after | Parse and preserve all tokens before jackd |
| Cyclictest returned null | `-h400` flag outputs histogram, not summary | Removed histogram flag |
| UI not updating after reset | Missing refresh calls | Added `_refresh_statuses()` + `_populate()` after every action |
| Unused QFont import | Copy-paste error | Removed |

### What We Tried That Didn't Work

| Approach | Why It Failed |
|----------|---------------|
| "Type YES to confirm" | Too friction. User already enters pkexec password. Redundant. |
| Preview dialog for every action | Slows down workflow. Users just wanted to apply quickly. |
| Dropdown with Default/Apply/Restore | Confusing when current state was "applied" and dropdown showed "Default". Users didn't know what "Default" meant. |
| System service checks for audio | PipeWire is user-scoped on modern systems. Old approach would never find it. |

---

## 7. Status Checking Logic

### How We Determine If a Knob Is Applied

Each implementation kind has specific logic in `check_knob_status()`:

**pam_limits_audio_group / sysctl_conf:**
```python
# Read file content
# For each expected line, check if present
# All present → "applied"
# Some present → "partial"
# None present → "not_applied"
```

**systemd_unit_toggle:**
```python
# Run: systemctl is-enabled <unit>
# If action was "disable_now":
#   "disabled" → "applied"
#   "enabled" → "not_applied"
```

**sysfs_glob_kv:**
```python
# For each path matching glob:
#   Read current value
#   Handle selector format: "[madvise] always never" → extract "madvise"
#   Compare to expected value
# All match → "applied"
# Some match → "partial"  
# None match → "not_applied"
```

**qjackctl_server_prefix:**
```python
# Read QjackCtl config
# Parse Server line
# Check if "-R" flag present
# Present → "applied", else "not_applied"
```

**read_only:**
```python
return "read_only"  # Special case, not apply/reset-able
```

---

## 8. Error Handling

### GUI Error Display

```python
try:
    result = _run_worker_apply_pkexec([knob_id])
except Exception as e:
    QMessageBox.critical(self, "Failed", str(e))
    return
```

**Philosophy:**
- Show error, don't crash
- Error message should explain what failed
- Don't leave UI in inconsistent state (refresh after error too)

### Worker Error Handling

```python
def cmd_apply(args):
    for kid in args.knob:
        k = by_id.get(kid)
        if k is None:
            raise SystemExit(f"Unknown knob id: {kid}")
        # ... apply logic
```

**Philosophy:**
- Validate inputs early
- Fail fast with clear message
- Use SystemExit for user-facing errors
- Use exceptions for unexpected errors

### Transaction Safety

```python
def backup_file(tx, abs_path):
    # 1. Check if file exists
    existed = Path(abs_path).exists()
    
    # 2. If exists, copy to backup BEFORE any modification
    if existed:
        shutil.copy2(p, dest)
    
    # 3. Record all metadata
    return meta
```

**Order matters:**
1. Create transaction directory
2. Backup file
3. Write manifest (partial - in case of crash)
4. Apply change
5. Update manifest (complete)

If crash occurs:
- Before backup: no backup exists, original intact
- After backup, before apply: backup exists, original intact
- After apply: backup exists, change applied, manifest records it

---

## 9. Future Development

### Phase 4: Audio Configuration

**Goal:** Let user configure interface, sample rate, buffer, bit depth

**Approach:**
1. Add single knob: `audio_config`
2. Kind: `audio_config` (new)
3. GUI shows "Config" button in column 6
4. Config button opens `AudioConfigDialog`
5. Dialog shows:
   - Interface dropdown (populated from `aplay -l`)
   - Sample rate dropdown (44100, 48000, 96000)
   - Buffer size dropdown (64, 128, 256, 512, 1024)
   - Bit depth dropdown (16, 24, 32)
   - Calculated latency display
6. Apply writes to appropriate config:
   - PipeWire: `~/.config/pipewire/pipewire.conf.d/99-audioknob.conf`
   - JACK/QjackCtl: Modify Server line parameters

**Detection needed:**
```python
def list_audio_interfaces():
    # Parse aplay -l output
    # Return list of: {"card": 0, "device": 0, "name": "..."}
```

### Phase 5: Monitoring

**Goal:** Real-time visibility into audio system health

**Features:**
- Underrun counter (xruns)
- Interrupt inspector
- **RT Config Scanner** ✓ IMPLEMENTED

### RT Config Scanner (rtcheck.py)

Comprehensive realtime readiness scan inspired by `realtimeconfigquickscan` but improved:

**Checks performed (18 total):**
| Check | What it detects | Fix knob |
|-------|-----------------|----------|
| Not root | Audio apps shouldn't run as root | — |
| Audio group | User in audio/realtime group | audio_group_membership |
| RT priority | Can use chrt, rtprio limit | rt_limits_audio_group |
| Memory lock | memlock limit sufficient | rt_limits_audio_group |
| CPU governor | All CPUs on 'performance' | cpu_governor_performance_temp |
| Swappiness | vm.swappiness ≤ 10 | swappiness |
| Inotify watches | ≥ 524288 for DAWs | inotify_max_watches |
| Kernel RT | PREEMPT_RT or threadirqs | kernel_threadirqs |
| High-res timers | CONFIG_HIGH_RES_TIMERS | — |
| Tickless | NO_HZ kernel config | — |
| IRQ balance | irqbalance not running | irqbalance_disable |
| THP | madvise or never mode | thp_mode_madvise |
| USB autosuspend | Disabled for audio devices | usb_autosuspend_disable |
| HPET | /dev/hpet readable | — |
| RTC | /dev/rtc readable | — |
| Filesystems | No reiserfs/fuseblk for audio | — |
| Audio services | Detects PipeWire/JACK/etc | — |
| cyclictest | Tool available for testing | (install rt-tests) |

**Score calculation:**
- 0-100% based on passed/(passed+warnings+failed)
- Warnings count as 0.5

**Output:**
```
=== Realtime Configuration Scan ===
Score: 88% (13 passed, 4 warnings, 0 failed)

✓ Audio group membership: User is in 'audio' group
⚠ CPU governor: Not all CPUs on 'performance'
    Fix: Use 'cpu_governor_performance_temp' knob
...
```

**Why we built our own instead of calling realtimeconfigquickscan:**
1. Native Python (no Perl dependency)
2. Structured output for GUI integration
3. Links checks to our knobs (can fix automatically)
4. More checks (USB autosuspend, THP, memlock)
5. Cleaner code for maintenance

### Guardrails for AI Continuation

When continuing this project, DO NOT:

1. **Add dropdown menus** - We explicitly removed them for simplicity
2. **Add batch operations** - Each knob acts independently
3. **Skip status refresh** - Always refresh after any state change
4. **Assume system services** - PipeWire/WirePlumber are user-scoped
5. **Modify without backup** - Transaction system is non-negotiable
6. **Ignore distro differences** - Test on multiple distros or detect
7. **Add "are you sure" dialogs** - pkexec password is enough friction
8. **Break existing patterns** - New code should look like existing code

When continuing this project, DO:

1. **Read this document first** - Understand before modifying
2. **Update this document** - Keep learnings current
3. **Follow existing code patterns** - Consistency matters
4. **Test manually** - The checklist in section 10
5. **Refresh UI after changes** - `_refresh_statuses()` + `_populate()`
6. **Handle errors gracefully** - Show message, don't crash

---

## 10. Distro-Specific Implementation

### Development Focus

**Primary target: openSUSE Tumbleweed** (current dev environment)

We focus on openSUSE first because:
1. It's the development environment
2. It has unique characteristics (GRUB2-BLS, sdbootutil)
3. Better to get one distro right than many half-working

Other distros have **placeholders** until we can verify on real systems.

---

### openSUSE Tumbleweed (PRIMARY)

#### Boot System: GRUB2-BLS with sdbootutil

**What this means:**
- openSUSE Tumbleweed uses Boot Loader Specification (BLS)
- Kernel entries are in `/boot/loader/entries/*.conf`
- **NOT** traditional GRUB with `/etc/default/grub`
- YaST bootloader module may show GRUB2, but the underlying system is BLS

**Kernel cmdline modification:**
```bash
# File to edit
/etc/kernel/cmdline

# After editing, MUST run:
sudo sdbootutil update-all-entries

# This regenerates boot entries from /etc/kernel/cmdline
```

**VERIFIED:** This works on Tumbleweed. Tested with `threadirqs` parameter.

**CAUTION:**
- YaST bootloader module does NOT update `/etc/kernel/cmdline` correctly
- Manual edit + sdbootutil is required
- YaST may be retired in future openSUSE versions

#### Package Manager: zypper + rpm

```bash
# Install package
sudo zypper install -y <package>

# Restore package file to default
sudo rpm --restore <package-name>

# Query file owner
rpm -qf /path/to/file
```

**VERIFIED:** `rpm --restore` works for resetting package-owned config files.

#### System Files & Permissions

| File/Directory | Notes |
|----------------|-------|
| `/etc/security/limits.d/` | Writable by root, standard PAM location |
| `/etc/sysctl.d/` | Writable by root, standard sysctl.d |
| `/etc/modprobe.d/` | May need for some audio drivers |
| `/sys/devices/system/cpu/` | Standard sysfs, writable by root |
| `/sys/kernel/mm/transparent_hugepage/` | Standard sysfs |
| `/etc/kernel/cmdline` | **openSUSE-specific**, not on other distros |

**Locked-down folders (Tumbleweed):**
- `/usr/` is read-only on transactional systems (MicroOS)
- Standard Tumbleweed: `/usr/` is writable by root
- Some security policies may restrict `/etc/` modifications

#### Audio Services (User Scope)

```bash
# PipeWire and WirePlumber run as USER services
systemctl --user status pipewire.service
systemctl --user status wireplumber.service

# NOT system services (these will show inactive)
systemctl status pipewire.service  # WRONG - will show inactive
```

**VERIFIED:** Must use `--user` flag for audio service detection.

#### PipeWire Configuration

```bash
# User override directory (preferred)
~/.config/pipewire/pipewire.conf.d/

# System default (don't modify directly)
/usr/share/pipewire/pipewire.conf

# System override (requires root)
/etc/pipewire/pipewire.conf.d/
```

**Approach:** Write to `~/.config/pipewire/pipewire.conf.d/99-audioknob.conf`

#### QjackCtl Configuration

```bash
~/.config/rncbc.org/QjackCtl.conf
```

**VERIFIED:** Standard location, INI format with escaped keys.

#### rtirq Configuration

```bash
# If rtirq is installed
/etc/sysconfig/rtirq  # openSUSE location (NOT /etc/rtirq.conf)
```

**TODO:** Verify rtirq package name and config location on Tumbleweed.

#### cpupower Configuration

```bash
# Service config
/etc/sysconfig/cpupower

# Command
cpupower frequency-set -g performance
```

**TODO:** Verify cpupower is installed by default or needs package.

---

### openSUSE Leap (PLACEHOLDER)

#### Key Differences from Tumbleweed

| Aspect | Tumbleweed | Leap |
|--------|------------|------|
| Boot system | GRUB2-BLS (sdbootutil) | Traditional GRUB2 |
| Kernel cmdline | `/etc/kernel/cmdline` | `/etc/default/grub` |
| Update command | `sdbootutil update-all-entries` | `grub2-mkconfig -o /boot/grub2/grub.cfg` |
| Rolling release | Yes | No (fixed versions) |

**NOT TESTED:** These are assumptions based on documentation. Need to verify on real Leap system.

#### GRUB2 Traditional (Leap)

```bash
# File to edit
/etc/default/grub
# Look for: GRUB_CMDLINE_LINUX_DEFAULT="..."

# After editing:
sudo grub2-mkconfig -o /boot/grub2/grub.cfg
```

---

### Fedora (PLACEHOLDER)

**NOT TESTED:** Need to verify on real Fedora system.

#### Assumed Configuration

| Aspect | Expected |
|--------|----------|
| Package manager | dnf + rpm |
| Boot system | GRUB2 |
| Kernel cmdline | `/etc/default/grub` |
| Update command | `grub2-mkconfig -o /boot/grub2/grub.cfg` |
| Audio stack | PipeWire (user service) |
| Audio group | audio |
| rtirq config | `/etc/sysconfig/rtirq` (if installed) |

#### Files to Verify

```bash
# Kernel cmdline
/etc/default/grub  # GRUB_CMDLINE_LINUX_DEFAULT

# PAM limits
/etc/security/limits.d/  # Should be standard

# sysctl
/etc/sysctl.d/  # Should be standard

# PipeWire config
~/.config/pipewire/pipewire.conf.d/  # User
/etc/pipewire/pipewire.conf.d/  # System
```

---

### Debian / Ubuntu (PLACEHOLDER)

**NOT TESTED:** Need to verify on real Debian/Ubuntu system.

#### Assumed Configuration

| Aspect | Expected |
|--------|----------|
| Package manager | apt + dpkg |
| Boot system | GRUB2 |
| Kernel cmdline | `/etc/default/grub` |
| Update command | `update-grub` |
| Audio stack | PipeWire (Ubuntu 22.04+) or PulseAudio |
| Audio group | audio |
| rtirq config | `/etc/default/rtirq` (if installed) |
| cpupower config | `/etc/default/cpupower` |

#### Package Restore

```bash
# Reinstall package to restore config files
sudo apt-get install --reinstall <package>

# Or use dpkg
sudo dpkg --purge <package>  # Remove including configs
sudo apt-get install <package>
```

**Note:** apt doesn't have equivalent of `rpm --restore`. May need to reinstall package.

---

### Arch Linux (PLACEHOLDER)

**NOT TESTED:** Need to verify on real Arch system.

#### Assumed Configuration

| Aspect | Expected |
|--------|----------|
| Package manager | pacman |
| Boot system | Varies (GRUB2 or systemd-boot) |
| Audio group | **realtime** (not audio!) |
| Realtime package | `realtime-privileges` (AUR or community) |

#### Key Difference: Audio Group

```bash
# Arch uses 'realtime' group, not 'audio'
# From realtime-privileges package

# PAM limits file
/etc/security/limits.d/99-realtime-privileges.conf
# Content:
# @realtime - rtprio 99
# @realtime - memlock unlimited
# @realtime - nice -20
```

**CRITICAL:** Detection needed to use correct group name.

#### Boot System Detection

```bash
# Check for systemd-boot
if [ -d /boot/loader/entries ]; then
    # systemd-boot
    # Edit /boot/loader/entries/*.conf directly
    # Or use bootctl
else
    # GRUB2
    # Edit /etc/default/grub
    # Run grub-mkconfig -o /boot/grub/grub.cfg
fi
```

---

### Distro Detection Strategy

#### Phase 1: Current Implementation

We currently detect:
- Package manager (rpm/dpkg/pacman) in `platform/packages.py`
- Audio stack (PipeWire/JACK) in `platform/detect.py`

#### Phase 2: Needed Detection

```python
def detect_distro() -> dict:
    """Detect distro and relevant configuration."""
    info = {
        "distro": None,           # opensuse-tumbleweed, fedora, etc.
        "boot_system": None,      # grub2, grub2-bls, systemd-boot
        "kernel_cmdline_file": None,
        "kernel_cmdline_update_cmd": None,
        "audio_group": "audio",   # or "realtime" for Arch
        "package_manager": None,  # zypper, dnf, apt, pacman
        "rtirq_config": None,
        "cpupower_config": None,
    }
    
    # Detect distro from /etc/os-release
    os_release = parse_os_release()
    
    if "opensuse-tumbleweed" in os_release.get("ID", ""):
        info["distro"] = "opensuse-tumbleweed"
        info["boot_system"] = "grub2-bls"
        info["kernel_cmdline_file"] = "/etc/kernel/cmdline"
        info["kernel_cmdline_update_cmd"] = ["sdbootutil", "update-all-entries"]
        info["rtirq_config"] = "/etc/sysconfig/rtirq"
        info["cpupower_config"] = "/etc/sysconfig/cpupower"
    
    elif "opensuse-leap" in os_release.get("ID", ""):
        info["distro"] = "opensuse-leap"
        info["boot_system"] = "grub2"
        info["kernel_cmdline_file"] = "/etc/default/grub"
        info["kernel_cmdline_update_cmd"] = ["grub2-mkconfig", "-o", "/boot/grub2/grub.cfg"]
        # ... etc
    
    # ... other distros
    
    return info
```

#### Phase 3: Boot System Detection

```python
def detect_boot_system() -> str:
    """Detect boot system independent of distro."""
    
    # Check for BLS (Boot Loader Specification)
    if Path("/etc/kernel/cmdline").exists() and shutil.which("sdbootutil"):
        return "grub2-bls"  # openSUSE Tumbleweed style
    
    # Check for systemd-boot
    if Path("/boot/loader/loader.conf").exists():
        return "systemd-boot"  # Arch with systemd-boot
    
    # Check for GRUB2
    if Path("/etc/default/grub").exists():
        if Path("/boot/grub2/grub.cfg").exists():
            return "grub2-opensuse"  # openSUSE style path
        elif Path("/boot/grub/grub.cfg").exists():
            return "grub2-standard"  # Debian/Arch style path
    
    return "unknown"
```

---

### Research Needed

| Item | Status | Notes |
|------|--------|-------|
| openSUSE Tumbleweed boot system | ✅ Verified | GRUB2-BLS with sdbootutil |
| openSUSE Tumbleweed audio stack | ✅ Verified | PipeWire (user service) |
| openSUSE Leap boot system | ❓ Assumed | Traditional GRUB2 - needs verification |
| Fedora boot system | ❓ Assumed | GRUB2 - needs verification |
| Debian/Ubuntu boot system | ❓ Assumed | GRUB2 with update-grub |
| Arch boot system | ❓ Varies | Could be GRUB2 or systemd-boot |
| Arch realtime group | ❓ Assumed | Uses 'realtime' not 'audio' |
| rtirq package availability | ❓ | Need to check each distro |
| cpupower default installation | ❓ | Need to check each distro |
| YaST retirement timeline | ❓ | openSUSE considering Agama/Cockpit |

---

### Implementation Priority

1. **Now:** openSUSE Tumbleweed works with current code
2. **Phase 4-5:** Add distro detection function
3. **Phase 6:** Add kernel cmdline knobs with distro-aware paths
4. **Phase 7:** Test on other distros, fill in placeholders
5. **Phase 8:** Package for each distro

---

## 11. Testing Checklist

### Before Each Session
```bash
# Reinstall worker if code changed
sudo install -D -m 0755 ~/audioknob-gui/packaging/audioknob-gui-worker /usr/local/libexec/audioknob-gui-worker

# Run app
~/audioknob-gui/bin/audioknob-gui
```

### Manual Tests

- [ ] **Apply root knob** (rt_limits): Click Apply → password prompt → status shows ✓
- [ ] **Reset root knob**: Click Reset → password prompt → status shows —
- [ ] **Apply user knob** (qjackctl): Click Apply → no password → status shows ✓
- [ ] **Config dialog**: Click Config on qjackctl → select cores → save → Apply
- [ ] **View button**: Click View on stack_detect → shows PipeWire/JACK status
- [ ] **Test button**: Click Test on jitter → runs 5s → status shows "XX µs"
- [ ] **Undo**: Apply something → click Undo → restored
- [ ] **Reset All**: Apply multiple → Reset All → all restored

### Verification Commands
```bash
# Check PAM limits
cat /etc/security/limits.d/99-audioknob-gui.conf

# Check sysctl
cat /etc/sysctl.d/99-audioknob-gui.conf

# Check irqbalance
systemctl is-enabled irqbalance

# Check QjackCtl (look for Server line with -R)
grep -A1 "\\\\Server" ~/.config/rncbc.org/QjackCtl.conf

# Check transactions
ls -la /var/lib/audioknob-gui/transactions/
ls -la ~/.local/state/audioknob-gui/transactions/
```

---

## 12. Quick Reference

### Commands

```bash
# Run GUI
~/audioknob-gui/bin/audioknob-gui

# Reinstall worker
sudo install -D -m 0755 ~/audioknob-gui/packaging/audioknob-gui-worker /usr/local/libexec/audioknob-gui-worker

# Check knob status (CLI)
python -m audioknob_gui.worker.cli status

# Preview a knob
python -m audioknob_gui.worker.cli preview rt_limits_audio_group

# List all changes
python -m audioknob_gui.worker.cli list-changes

# Apply root knob (via pkexec)
pkexec /usr/local/libexec/audioknob-gui-worker apply rt_limits_audio_group

# Restore a knob
pkexec /usr/local/libexec/audioknob-gui-worker restore-knob rt_limits_audio_group
```

### Key Files

| File | Purpose |
|------|---------|
| `config/registry.json` | Knob definitions |
| `audioknob_gui/gui/app.py` | Main GUI |
| `audioknob_gui/worker/cli.py` | Worker CLI |
| `audioknob_gui/worker/ops.py` | Preview/status logic |
| `audioknob_gui/core/transaction.py` | Backup/restore |
| `audioknob_gui/platform/detect.py` | Audio stack detection |
| `~/.local/state/audioknob-gui/state.json` | GUI state |

### Environment

| Item | Value |
|------|-------|
| OS | openSUSE Tumbleweed |
| Boot | GRUB2-BLS (sdbootutil) |
| Audio | PipeWire + WirePlumber |
| Python | 3.13 |
| GUI | PySide6 |

---

*Last updated: 2024-12-19*
*This document is the technical source of truth. Any AI continuing this project must read and follow it.*
