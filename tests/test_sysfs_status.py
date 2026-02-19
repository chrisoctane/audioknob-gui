"""Tests for sysfs status parsing."""

import re
import pytest
from pathlib import Path

from audioknob_gui.registry import Capabilities, Impl, Knob
from audioknob_gui.worker.ops import check_knob_status, write_sysfs_values


def _extract_sysfs_selector(content: str) -> str | None:
    """Extract the current value from sysfs selector format.
    
    Handles formats like:
    - "always [madvise] never" -> "madvise"
    - "[performance] powersave" -> "performance"
    - "plain_value" -> "plain_value"
    """
    content = content.strip()
    if "[" in content and "]" in content:
        match = re.search(r'\[([^\]]+)\]', content)
        if match:
            return match.group(1)
    return content


class TestSysfsSelectorParsing:
    """Tests for sysfs selector format parsing."""

    def test_bracket_at_start(self) -> None:
        """Bracketed token at start of line."""
        content = "[performance] powersave ondemand"
        assert _extract_sysfs_selector(content) == "performance"

    def test_bracket_in_middle(self) -> None:
        """Bracketed token in middle of line (THP format)."""
        content = "always [madvise] never"
        assert _extract_sysfs_selector(content) == "madvise"

    def test_bracket_at_end(self) -> None:
        """Bracketed token at end of line."""
        content = "always madvise [never]"
        assert _extract_sysfs_selector(content) == "never"

    def test_plain_value(self) -> None:
        """Plain value without brackets."""
        content = "performance"
        assert _extract_sysfs_selector(content) == "performance"

    def test_thp_always(self) -> None:
        """THP enabled (always)."""
        content = "[always] madvise never"
        assert _extract_sysfs_selector(content) == "always"

    def test_thp_madvise(self) -> None:
        """THP madvise mode."""
        content = "always [madvise] never"
        assert _extract_sysfs_selector(content) == "madvise"

    def test_thp_never(self) -> None:
        """THP disabled (never)."""
        content = "always madvise [never]"
        assert _extract_sysfs_selector(content) == "never"

    def test_cpu_governor_performance(self) -> None:
        """CPU governor set to performance."""
        content = "[performance] powersave"
        assert _extract_sysfs_selector(content) == "performance"

    def test_cpu_governor_powersave(self) -> None:
        """CPU governor set to powersave."""
        content = "performance [powersave]"
        assert _extract_sysfs_selector(content) == "powersave"

    def test_whitespace_handling(self) -> None:
        """Whitespace is stripped."""
        content = "  always [madvise] never  \n"
        assert _extract_sysfs_selector(content) == "madvise"


def _cpumask_knob(value: str) -> Knob:
    return Knob(
        id="kernel_workqueue_cpumask",
        title="Workqueue cpumask",
        description="",
        category="kernel",
        risk_level="high",
        requires_root=True,
        requires_reboot=False,
        requires_groups=(),
        requires_commands=(),
        depends_on=(),
        capabilities=Capabilities(read=True, apply=True, restore=True),
        impl=Impl(
            kind="sysfs_glob_kv",
            params={
                "glob": "/sys/devices/virtual/workqueue/cpumask",
                "value": value,
            },
        ),
    )


def test_check_knob_status_cpumask_compares_equivalent_formats(monkeypatch) -> None:
    knob = _cpumask_knob("2-3")

    monkeypatch.setattr(
        "audioknob_gui.worker.ops._expand_sysfs_globs",
        lambda _glob: ["/sys/devices/virtual/workqueue/cpumask"],
    )
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda _self, encoding="utf-8": "2,3\n",
    )

    assert check_knob_status(knob) == "applied"


def test_check_knob_status_cpumask_detects_mismatch(monkeypatch) -> None:
    knob = _cpumask_knob("2-3")

    monkeypatch.setattr(
        "audioknob_gui.worker.ops._expand_sysfs_globs",
        lambda _glob: ["/sys/devices/virtual/workqueue/cpumask"],
    )
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda _self, encoding="utf-8": "4-5\n",
    )

    assert check_knob_status(knob) == "not_applied"


def test_check_knob_status_cpumask_accepts_hex_mask(monkeypatch) -> None:
    knob = _cpumask_knob("2-3")

    monkeypatch.setattr(
        "audioknob_gui.worker.ops._expand_sysfs_globs",
        lambda _glob: ["/sys/devices/virtual/workqueue/cpumask"],
    )
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda _self, encoding="utf-8": "c\n",
    )

    assert check_knob_status(knob) == "applied"


def test_write_sysfs_values_cpumask_converts_cpu_list_to_mask(monkeypatch, tmp_path) -> None:
    cpumask_path = tmp_path / "cpumask"
    cpumask_path.write_text("ffffffff\n", encoding="utf-8")

    monkeypatch.setattr(
        "audioknob_gui.worker.ops._expand_sysfs_globs",
        lambda _glob: [str(cpumask_path)],
    )

    effects = write_sysfs_values("/ignored", "2-3")

    assert cpumask_path.read_text(encoding="utf-8") == "c\n"
    assert effects[0]["path"] == str(cpumask_path)
    assert effects[0]["after"] == "c"
