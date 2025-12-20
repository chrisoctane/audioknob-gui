"""Tests for kernel cmdline parameter detection."""

import pytest


def _param_present(param: str, tokens: list[str]) -> bool:
    """Check if param is present in tokenized cmdline (exact match, no substring)."""
    if not param:
        return False
    if "=" in param:
        return any(t == param for t in tokens)
    # Also treat foo=bar as satisfying "foo" presence
    return any(t == param or t.startswith(param + "=") for t in tokens)


class TestKernelCmdlineTokenPresence:
    """Tests for kernel cmdline parameter detection logic."""

    def test_exact_match(self) -> None:
        """Exact parameter match works."""
        tokens = ["quiet", "splash", "threadirqs"]
        
        assert _param_present("threadirqs", tokens) is True
        assert _param_present("quiet", tokens) is True

    def test_no_substring_false_positive(self) -> None:
        """Substring should NOT match (e.g., 'threadirqs' should not match 'nothreadirqs')."""
        tokens = ["quiet", "splash", "nothreadirqs"]
        
        # "threadirqs" should NOT match "nothreadirqs"
        assert _param_present("threadirqs", tokens) is False

    def test_param_with_value(self) -> None:
        """Parameter with value (key=value) matches exactly."""
        tokens = ["quiet", "audit=0", "mitigations=off"]
        
        assert _param_present("audit=0", tokens) is True
        assert _param_present("mitigations=off", tokens) is True
        
        # Different value should not match
        assert _param_present("audit=1", tokens) is False

    def test_param_key_matches_key_value(self) -> None:
        """Bare param key matches key=value form."""
        tokens = ["quiet", "audit=0", "mitigations=off"]
        
        # "audit" (bare key) should match "audit=0" (key=value)
        assert _param_present("audit", tokens) is True
        assert _param_present("mitigations", tokens) is True

    def test_empty_param(self) -> None:
        """Empty param returns False."""
        tokens = ["quiet", "splash"]
        
        assert _param_present("", tokens) is False

    def test_empty_tokens(self) -> None:
        """Empty tokens list returns False."""
        tokens: list[str] = []
        
        assert _param_present("threadirqs", tokens) is False

    def test_real_cmdline_example(self) -> None:
        """Test with realistic cmdline content."""
        # Simulated /proc/cmdline content, tokenized
        cmdline = "BOOT_IMAGE=/boot/vmlinuz-6.6.0 root=UUID=abc quiet splash threadirqs audit=0"
        tokens = cmdline.split()
        
        assert _param_present("threadirqs", tokens) is True
        assert _param_present("audit=0", tokens) is True
        assert _param_present("quiet", tokens) is True
        
        # Not present
        assert _param_present("mitigations=off", tokens) is False
        assert _param_present("nothreadirqs", tokens) is False
