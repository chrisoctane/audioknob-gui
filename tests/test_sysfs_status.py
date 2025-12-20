"""Tests for sysfs status parsing."""

import re
import pytest


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
