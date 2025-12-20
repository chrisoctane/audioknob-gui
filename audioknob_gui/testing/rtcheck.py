"""Realtime configuration scanner.

Inspired by realtimeconfigquickscan from GeekOSDAW, but improved:
- Native Python (no Perl dependency)
- More checks (IRQ affinity, kernel params, limits.conf)
- Integrated with our knob system (can fix issues automatically)
- Structured output for GUI display
"""

from __future__ import annotations

import grp
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class CheckStatus(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class CheckResult:
    """Result of a single check."""
    id: str
    name: str
    status: CheckStatus
    message: str
    detail: str = ""
    fix_knob: str | None = None  # Knob ID that can fix this issue
    fix_command: str | None = None  # Manual fix command


@dataclass
class ScanResult:
    """Complete scan results."""
    checks: list[CheckResult] = field(default_factory=list)
    
    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.PASS)
    
    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.WARN)
    
    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAIL)
    
    @property
    def score(self) -> int:
        """Score 0-100 based on checks."""
        total = len([c for c in self.checks if c.status != CheckStatus.SKIP])
        if total == 0:
            return 100
        passed = self.passed + (self.warnings * 0.5)
        return int((passed / total) * 100)


def _read_file(path: str | Path) -> str | None:
    """Read file contents, return None if not readable."""
    try:
        return Path(path).read_text().strip()
    except (OSError, IOError):
        return None


def _run_cmd(cmd: list[str], timeout: int = 5) -> tuple[int, str]:
    """Run command, return (returncode, stdout)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return -1, ""


def check_not_root() -> CheckResult:
    """Check that we're not running as root (audio apps shouldn't)."""
    if os.geteuid() == 0:
        return CheckResult(
            id="not_root",
            name="Not running as root",
            status=CheckStatus.WARN,
            message="Running as root",
            detail="Audio applications should run as regular user, not root."
        )
    return CheckResult(
        id="not_root",
        name="Not running as root",
        status=CheckStatus.PASS,
        message="Running as regular user"
    )


def check_audio_group() -> CheckResult:
    """Check if user is in audio group."""
    try:
        audio_gid = grp.getgrnam("audio").gr_gid
        if audio_gid in os.getgroups():
            return CheckResult(
                id="audio_group",
                name="Audio group membership",
                status=CheckStatus.PASS,
                message="User is in 'audio' group"
            )
        return CheckResult(
            id="audio_group",
            name="Audio group membership",
            status=CheckStatus.FAIL,
            message="Not in 'audio' group",
            detail="RT limits won't apply. Logout/login after joining.",
            fix_knob="audio_group_membership",
            fix_command="sudo usermod -aG audio $USER"
        )
    except KeyError:
        # Check for 'realtime' group (Arch)
        try:
            rt_gid = grp.getgrnam("realtime").gr_gid
            if rt_gid in os.getgroups():
                return CheckResult(
                    id="audio_group",
                    name="Audio group membership",
                    status=CheckStatus.PASS,
                    message="User is in 'realtime' group"
                )
        except KeyError:
            pass
        return CheckResult(
            id="audio_group",
            name="Audio group membership",
            status=CheckStatus.FAIL,
            message="No audio group exists",
            detail="Neither 'audio' nor 'realtime' group found.",
            fix_knob="audio_group_membership"
        )


def check_cpu_governor() -> CheckResult:
    """Check CPU frequency governors."""
    governor_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    if not governor_path.exists():
        return CheckResult(
            id="cpu_governor",
            name="CPU governor",
            status=CheckStatus.SKIP,
            message="CPU frequency scaling not available"
        )
    
    governors = {}
    for cpu_path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_governor"):
        gov = _read_file(cpu_path) or "unknown"
        governors[gov] = governors.get(gov, 0) + 1
    
    if not governors:
        return CheckResult(
            id="cpu_governor",
            name="CPU governor",
            status=CheckStatus.SKIP,
            message="No CPU governors found"
        )
    
    if "performance" in governors and len(governors) == 1:
        return CheckResult(
            id="cpu_governor",
            name="CPU governor",
            status=CheckStatus.PASS,
            message="All CPUs set to 'performance'"
        )
    
    gov_summary = ", ".join(f"{g}: {n}" for g, n in governors.items())
    return CheckResult(
        id="cpu_governor",
        name="CPU governor",
        status=CheckStatus.WARN,
        message=f"Not all CPUs on 'performance'",
        detail=gov_summary,
        fix_knob="cpu_governor_performance_temp",
        fix_command="cpupower frequency-set -g performance"
    )


def check_swappiness() -> CheckResult:
    """Check vm.swappiness setting."""
    val = _read_file("/proc/sys/vm/swappiness")
    if val is None:
        return CheckResult(
            id="swappiness",
            name="Swappiness",
            status=CheckStatus.SKIP,
            message="Cannot read swappiness"
        )
    
    try:
        swap = int(val)
        if swap <= 10:
            return CheckResult(
                id="swappiness",
                name="Swappiness",
                status=CheckStatus.PASS,
                message=f"vm.swappiness={swap} (low)"
            )
        elif swap <= 30:
            return CheckResult(
                id="swappiness",
                name="Swappiness",
                status=CheckStatus.WARN,
                message=f"vm.swappiness={swap}",
                detail="Consider lowering to 10 for audio work",
                fix_knob="swappiness"
            )
        return CheckResult(
            id="swappiness",
            name="Swappiness",
            status=CheckStatus.WARN,
            message=f"vm.swappiness={swap} (high)",
            detail="High swappiness can cause latency spikes",
            fix_knob="swappiness"
        )
    except ValueError:
        return CheckResult(
            id="swappiness",
            name="Swappiness",
            status=CheckStatus.SKIP,
            message=f"Invalid swappiness: {val}"
        )


def check_inotify_watches() -> CheckResult:
    """Check inotify max_user_watches."""
    val = _read_file("/proc/sys/fs/inotify/max_user_watches")
    if val is None:
        return CheckResult(
            id="inotify",
            name="Inotify watches",
            status=CheckStatus.SKIP,
            message="Cannot read inotify settings"
        )
    
    try:
        watches = int(val)
        if watches >= 524288:
            return CheckResult(
                id="inotify",
                name="Inotify watches",
                status=CheckStatus.PASS,
                message=f"{watches:,} watches available"
            )
        return CheckResult(
            id="inotify",
            name="Inotify watches",
            status=CheckStatus.WARN,
            message=f"Only {watches:,} watches",
            detail="DAWs with many files may hit this limit",
            fix_knob="inotify_max_watches"
        )
    except ValueError:
        return CheckResult(
            id="inotify",
            name="Inotify watches",
            status=CheckStatus.SKIP,
            message=f"Invalid value: {val}"
        )


def check_hpet() -> CheckResult:
    """Check access to High Precision Event Timer."""
    hpet = Path("/dev/hpet")
    if not hpet.exists():
        return CheckResult(
            id="hpet",
            name="HPET access",
            status=CheckStatus.WARN,
            message="HPET device not found",
            detail="/dev/hpet doesn't exist"
        )
    
    if os.access(hpet, os.R_OK):
        return CheckResult(
            id="hpet",
            name="HPET access",
            status=CheckStatus.PASS,
            message="HPET readable"
        )
    return CheckResult(
        id="hpet",
        name="HPET access",
        status=CheckStatus.WARN,
        message="HPET not readable",
        detail="Some apps may need read access to /dev/hpet"
    )


def check_rtc() -> CheckResult:
    """Check access to Real-Time Clock."""
    rtc = Path("/dev/rtc0")
    if not rtc.exists():
        rtc = Path("/dev/rtc")
    
    if not rtc.exists():
        return CheckResult(
            id="rtc",
            name="RTC access",
            status=CheckStatus.WARN,
            message="RTC device not found"
        )
    
    if os.access(rtc, os.R_OK):
        return CheckResult(
            id="rtc",
            name="RTC access",
            status=CheckStatus.PASS,
            message="RTC readable"
        )
    return CheckResult(
        id="rtc",
        name="RTC access",
        status=CheckStatus.WARN,
        message="RTC not readable"
    )


def check_rtprio() -> CheckResult:
    """Check if user can set realtime priority."""
    # Try to check with chrt
    rc, out = _run_cmd(["chrt", "-f", "-p", "1", str(os.getpid())])
    
    # chrt will fail but the error message tells us if we have permission
    if rc == 0:
        return CheckResult(
            id="rtprio",
            name="RT priority capability",
            status=CheckStatus.PASS,
            message="Can set RT priority"
        )
    
    # Check ulimit
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_RTPRIO)
        if hard > 0:
            return CheckResult(
                id="rtprio",
                name="RT priority capability",
                status=CheckStatus.PASS,
                message=f"rtprio limit: {soft}/{hard}"
            )
        return CheckResult(
            id="rtprio",
            name="RT priority capability",
            status=CheckStatus.FAIL,
            message="No RT priority capability",
            detail="Check /etc/security/limits.d/ for @audio rtprio",
            fix_knob="rt_limits_audio_group"
        )
    except (ImportError, OSError):
        return CheckResult(
            id="rtprio",
            name="RT priority capability",
            status=CheckStatus.SKIP,
            message="Cannot check RT priority limits"
        )


def check_memlock() -> CheckResult:
    """Check memlock limits."""
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_MEMLOCK)
        
        # -1 or very large = unlimited
        if hard == resource.RLIM_INFINITY or hard > 1024 * 1024 * 1024:
            return CheckResult(
                id="memlock",
                name="Memory lock capability",
                status=CheckStatus.PASS,
                message="memlock unlimited or very high"
            )
        
        # Convert to MB for display
        hard_mb = hard / (1024 * 1024)
        if hard >= 256 * 1024 * 1024:  # 256MB
            return CheckResult(
                id="memlock",
                name="Memory lock capability",
                status=CheckStatus.PASS,
                message=f"memlock: {hard_mb:.0f}MB"
            )
        return CheckResult(
            id="memlock",
            name="Memory lock capability",
            status=CheckStatus.WARN,
            message=f"memlock: {hard_mb:.0f}MB (low)",
            detail="Audio apps may need more locked memory",
            fix_knob="rt_limits_audio_group"
        )
    except (ImportError, OSError):
        return CheckResult(
            id="memlock",
            name="Memory lock capability",
            status=CheckStatus.SKIP,
            message="Cannot check memlock limits"
        )


def check_kernel_rt() -> CheckResult:
    """Check for RT kernel or threadirqs parameter."""
    # Check for full RT kernel
    if Path("/sys/kernel/realtime").exists():
        return CheckResult(
            id="kernel_rt",
            name="Realtime kernel",
            status=CheckStatus.PASS,
            message="Running PREEMPT_RT kernel"
        )
    
    # Check for threadirqs parameter
    cmdline = _read_file("/proc/cmdline") or ""
    if "threadirqs" in cmdline:
        return CheckResult(
            id="kernel_rt",
            name="Realtime kernel",
            status=CheckStatus.PASS,
            message="threadirqs enabled"
        )
    
    return CheckResult(
        id="kernel_rt",
        name="Realtime kernel",
        status=CheckStatus.WARN,
        message="No RT kernel or threadirqs",
        detail="Consider adding 'threadirqs' to kernel cmdline",
        fix_knob="kernel_threadirqs"
    )


def check_high_res_timers() -> CheckResult:
    """Check for high resolution timer support."""
    timer_list = _read_file("/proc/timer_list")
    if timer_list and ".hres_active" in timer_list and ": 1" in timer_list:
        return CheckResult(
            id="hrtimers",
            name="High-res timers",
            status=CheckStatus.PASS,
            message="High-resolution timers active"
        )
    
    # Alternative check via config
    config_path = Path(f"/boot/config-{os.uname().release}")
    config = _read_file(config_path) or ""
    if "CONFIG_HIGH_RES_TIMERS=y" in config:
        return CheckResult(
            id="hrtimers",
            name="High-res timers",
            status=CheckStatus.PASS,
            message="High-res timers compiled in"
        )
    
    return CheckResult(
        id="hrtimers",
        name="High-res timers",
        status=CheckStatus.WARN,
        message="High-res timers not confirmed"
    )


def check_nohz() -> CheckResult:
    """Check for tickless (NO_HZ) kernel."""
    config_path = Path(f"/boot/config-{os.uname().release}")
    config = _read_file(config_path) or ""
    
    if "CONFIG_NO_HZ_FULL=y" in config:
        return CheckResult(
            id="nohz",
            name="Tickless kernel",
            status=CheckStatus.PASS,
            message="NO_HZ_FULL enabled"
        )
    if "CONFIG_NO_HZ=y" in config or "CONFIG_NO_HZ_IDLE=y" in config:
        return CheckResult(
            id="nohz",
            name="Tickless kernel",
            status=CheckStatus.PASS,
            message="NO_HZ enabled"
        )
    
    cmdline = _read_file("/proc/cmdline") or ""
    if "nohz" in cmdline:
        return CheckResult(
            id="nohz",
            name="Tickless kernel",
            status=CheckStatus.PASS,
            message="nohz in cmdline"
        )
    
    return CheckResult(
        id="nohz",
        name="Tickless kernel",
        status=CheckStatus.SKIP,
        message="Cannot determine NO_HZ status"
    )


def check_irqbalance() -> CheckResult:
    """Check if irqbalance is running."""
    rc, _ = _run_cmd(["systemctl", "is-active", "irqbalance.service"])
    if rc == 0:
        return CheckResult(
            id="irqbalance",
            name="IRQ balancing",
            status=CheckStatus.WARN,
            message="irqbalance is running",
            detail="Can cause IRQ thread migration during playback",
            fix_knob="irqbalance_disable"
        )
    return CheckResult(
        id="irqbalance",
        name="IRQ balancing",
        status=CheckStatus.PASS,
        message="irqbalance not running"
    )


def check_filesystem_types() -> CheckResult:
    """Check for problematic filesystem types."""
    rc, mount_output = _run_cmd(["mount"])
    if rc != 0:
        return CheckResult(
            id="filesystems",
            name="Filesystem types",
            status=CheckStatus.SKIP,
            message="Cannot check mount points"
        )
    
    problems = []
    for line in mount_output.splitlines():
        if " type reiserfs " in line or " type fuseblk " in line:
            # Skip /media mounts (removable)
            if "/media/" not in line:
                mount_point = line.split(" on ")[1].split(" type ")[0] if " on " in line else "?"
                problems.append(mount_point)
    
    if problems:
        return CheckResult(
            id="filesystems",
            name="Filesystem types",
            status=CheckStatus.WARN,
            message=f"Problematic FS: {', '.join(problems)}",
            detail="reiserfs/fuseblk not ideal for audio"
        )
    return CheckResult(
        id="filesystems",
        name="Filesystem types",
        status=CheckStatus.PASS,
        message="No problematic filesystems"
    )


def check_usb_autosuspend() -> CheckResult:
    """Check if USB autosuspend is enabled."""
    # Our knob enforces `power/control=on` via a udev rule. The autosuspend delay value
    # (power/autosuspend) is not a reliable indicator of whether autosuspend is active.
    rule_path = Path("/etc/udev/rules.d/99-usb-no-autosuspend.rules")

    controls = list(Path("/sys/bus/usb/devices").glob("*/power/control"))
    if not controls:
        return CheckResult(
            id="usb_autosuspend",
            name="USB autosuspend",
            status=CheckStatus.SKIP,
            message="No USB power controls found"
        )

    auto = 0
    on = 0
    unknown = 0
    for p in controls:
        v = (_read_file(p) or "").strip().lower()
        if v == "auto":
            auto += 1
        elif v == "on":
            on += 1
        else:
            unknown += 1

    if auto > 0:
        detail = f"Devices: on={on}, auto={auto}, unknown={unknown}"
        if rule_path.exists():
            detail += "\nRule is installed, but some devices are still in 'auto'. Try replugging the interface or running: sudo udevadm trigger"
        return CheckResult(
            id="usb_autosuspend",
            name="USB autosuspend",
            status=CheckStatus.WARN,
            message="Some USB devices are autosuspending ('auto')",
            detail=detail,
            fix_knob="usb_autosuspend_disable"
        )

    return CheckResult(
        id="usb_autosuspend",
        name="USB autosuspend",
        status=CheckStatus.PASS,
        message="USB autosuspend disabled (all devices 'on')"
    )


def check_thp() -> CheckResult:
    """Check Transparent Huge Pages setting."""
    val = _read_file("/sys/kernel/mm/transparent_hugepage/enabled")
    if not val:
        return CheckResult(
            id="thp",
            name="Transparent Huge Pages",
            status=CheckStatus.SKIP,
            message="THP not available"
        )
    
    # Parse [always] madvise never or always [madvise] never
    current = re.search(r'\[(\w+)\]', val)
    if current:
        mode = current.group(1)
        if mode in ("madvise", "never"):
            return CheckResult(
                id="thp",
                name="Transparent Huge Pages",
                status=CheckStatus.PASS,
                message=f"THP: {mode}"
            )
        return CheckResult(
            id="thp",
            name="Transparent Huge Pages",
            status=CheckStatus.WARN,
            message=f"THP: {mode}",
            detail="'madvise' or 'never' recommended for RT",
            fix_knob="thp_mode_madvise"
        )
    return CheckResult(
        id="thp",
        name="Transparent Huge Pages",
        status=CheckStatus.SKIP,
        message=f"Cannot parse: {val}"
    )


def check_audio_services() -> CheckResult:
    """Check which audio services are running."""
    services = []
    
    # Check user services
    for svc in ["pipewire.service", "pipewire-pulse.service", "wireplumber.service"]:
        rc, _ = _run_cmd(["systemctl", "--user", "is-active", svc])
        if rc == 0:
            services.append(svc.replace(".service", ""))
    
    # Check system services
    for svc in ["jackd.service", "jack.service", "pulseaudio.service"]:
        rc, _ = _run_cmd(["systemctl", "is-active", svc])
        if rc == 0:
            services.append(svc.replace(".service", ""))
    
    if not services:
        return CheckResult(
            id="audio_services",
            name="Audio services",
            status=CheckStatus.WARN,
            message="No audio services detected"
        )
    
    return CheckResult(
        id="audio_services",
        name="Audio services",
        status=CheckStatus.PASS,
        message=", ".join(services)
    )


def check_cyclictest_available() -> CheckResult:
    """Check if cyclictest is available."""
    if shutil.which("cyclictest"):
        return CheckResult(
            id="cyclictest",
            name="cyclictest available",
            status=CheckStatus.PASS,
            message="cyclictest is installed"
        )
    return CheckResult(
        id="cyclictest",
        name="cyclictest available",
        status=CheckStatus.WARN,
        message="cyclictest not installed",
        detail="Needed for latency testing (rt-tests package)",
        fix_command="sudo zypper install rt-tests"
    )


def run_full_scan() -> ScanResult:
    """Run all realtime configuration checks."""
    result = ScanResult()
    
    # Run all checks
    checks = [
        check_not_root,
        check_audio_group,
        check_rtprio,
        check_memlock,
        check_cpu_governor,
        check_swappiness,
        check_inotify_watches,
        check_kernel_rt,
        check_high_res_timers,
        check_nohz,
        check_irqbalance,
        check_thp,
        check_usb_autosuspend,
        check_hpet,
        check_rtc,
        check_filesystem_types,
        check_audio_services,
        check_cyclictest_available,
    ]
    
    for check_fn in checks:
        try:
            result.checks.append(check_fn())
        except Exception as e:
            result.checks.append(CheckResult(
                id=check_fn.__name__,
                name=check_fn.__name__,
                status=CheckStatus.SKIP,
                message=f"Error: {e}"
            ))
    
    return result


def format_scan_text(result: ScanResult) -> str:
    """Format scan results as plain text."""
    lines = [
        "=== Realtime Configuration Scan ===",
        f"Score: {result.score}% ({result.passed} passed, {result.warnings} warnings, {result.failed} failed)",
        ""
    ]
    
    for c in result.checks:
        icon = {
            CheckStatus.PASS: "✓",
            CheckStatus.WARN: "⚠",
            CheckStatus.FAIL: "✗",
            CheckStatus.SKIP: "○",
        }.get(c.status, "?")
        
        lines.append(f"{icon} {c.name}: {c.message}")
        if c.detail:
            lines.append(f"    {c.detail}")
        if c.fix_knob:
            lines.append(f"    Fix: Use '{c.fix_knob}' knob")
        elif c.fix_command:
            lines.append(f"    Fix: {c.fix_command}")
    
    return "\n".join(lines)


def format_scan_html(result: ScanResult) -> str:
    """Format scan results as HTML for GUI display."""
    html = [
        f"<h3>Realtime Configuration Score: {result.score}%</h3>",
        f"<p>✓ {result.passed} passed &nbsp; ⚠ {result.warnings} warnings &nbsp; ✗ {result.failed} failed</p>",
        "<hr/>",
        "<table style='width:100%'>",
    ]
    
    for c in result.checks:
        color = {
            CheckStatus.PASS: "#2e7d32",
            CheckStatus.WARN: "#f57c00",
            CheckStatus.FAIL: "#d32f2f",
            CheckStatus.SKIP: "#9e9e9e",
        }.get(c.status, "#000")
        
        icon = {
            CheckStatus.PASS: "✓",
            CheckStatus.WARN: "⚠",
            CheckStatus.FAIL: "✗",
            CheckStatus.SKIP: "○",
        }.get(c.status, "?")
        
        html.append(f"<tr><td style='color:{color}'>{icon}</td>")
        html.append(f"<td><b>{c.name}</b></td>")
        html.append(f"<td>{c.message}</td></tr>")
        
        if c.detail or c.fix_knob or c.fix_command:
            html.append("<tr><td></td><td colspan='2' style='color:#666; font-size:0.9em'>")
            if c.detail:
                html.append(f"{c.detail}<br/>")
            if c.fix_knob:
                html.append(f"<i>Fix: Use '{c.fix_knob}' knob</i>")
            elif c.fix_command:
                html.append(f"<i>Fix: <code>{c.fix_command}</code></i>")
            html.append("</td></tr>")
    
    html.append("</table>")
    return "".join(html)


if __name__ == "__main__":
    result = run_full_scan()
    print(format_scan_text(result))
