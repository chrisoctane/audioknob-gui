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
| `description` | string | Shown in tooltip and description column |
| `category` | enum | Grouping: permissions, cpu, irq, vm, stack, testing |
| `risk_level` | enum | low/medium/high - shown in Risk column |
| `requires_root` | bool | If true, apply uses pkexec |
| `requires_reboot` | bool | If true, show warning (not enforced) |
| `capabilities.read` | bool | Can we check current status? |
| `capabilities.apply` | bool | Can we apply this knob? |
| `capabilities.restore` | bool | Can we restore to original? |
| `impl.kind` | string | Which implementation handler to use |
| `impl.params` | object | Parameters passed to handler |

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
- Blocker detection

**Blocker detection approach:**
```python
def check_blockers() -> list[str]:
    blockers = []
    
    # Check group membership
    if "audio" not in [grp.gr_name for grp in grp.getgrall() if os.getuid() in grp.gr_mem]:
        blockers.append("Not in 'audio' group - RT limits won't apply")
    
    # Check RT kernel
    if not Path("/sys/kernel/realtime").exists():
        blockers.append("Not running RT kernel")
    
    # Check cyclictest
    if shutil.which("cyclictest") is None:
        blockers.append("cyclictest not installed")
    
    return blockers
```

**Display:** Show as warning banner in GUI or as a "Blockers" info button

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

## 10. Testing Checklist

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

## 11. Quick Reference

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
