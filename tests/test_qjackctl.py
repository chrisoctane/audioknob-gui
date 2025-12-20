"""Tests for QjackCtl configuration parsing and rewriting."""

import pytest

from audioknob_gui.core.qjackctl import ensure_server_has_flags


class TestEnsureServerHasFlags:
    """Tests for ensure_server_has_flags()."""

    def test_add_rt_flag(self) -> None:
        """RT flag is added if missing."""
        cmd = "/usr/bin/jackd -dalsa -dhw:0 -r48000 -p256"
        result = ensure_server_has_flags(cmd, ensure_rt=True)
        
        assert "-R" in result or "--realtime" in result

    def test_preserve_existing_rt_flag(self) -> None:
        """Existing RT flag is preserved."""
        cmd = "/usr/bin/jackd -R -dalsa -dhw:0"
        result = ensure_server_has_flags(cmd, ensure_rt=True)
        
        assert "-R" in result

    def test_add_cpu_cores(self) -> None:
        """CPU cores are added via taskset."""
        cmd = "/usr/bin/jackd -dalsa"
        result = ensure_server_has_flags(cmd, cpu_cores="2,3")
        
        assert "taskset" in result
        assert "2,3" in result

    def test_update_cpu_cores(self) -> None:
        """Existing CPU cores can be updated."""
        cmd = "taskset -c 0,1 /usr/bin/jackd -dalsa"
        result = ensure_server_has_flags(cmd, cpu_cores="4,5,6")
        
        assert "4,5,6" in result

    def test_remove_cpu_cores(self) -> None:
        """CPU cores can be removed by passing empty string."""
        cmd = "taskset -c 0,1 /usr/bin/jackd -dalsa"
        result = ensure_server_has_flags(cmd, cpu_cores="")
        
        # taskset should be removed, jackd command preserved
        assert "taskset" not in result
        assert "jackd" in result

    def test_with_nice_prefix(self) -> None:
        """Command with nice prefix processes correctly."""
        # Note: the function may strip or preserve nice depending on implementation
        cmd = "/usr/bin/nice -n -10 /usr/bin/jackd -dalsa"
        result = ensure_server_has_flags(cmd, ensure_rt=True)
        
        # At minimum, jackd and RT flag should be present
        assert "jackd" in result
        assert "-R" in result

    def test_complex_command(self) -> None:
        """Complex command with cpu_cores updates works."""
        cmd = "/usr/bin/nice -n -15 taskset -c 0,1 /usr/bin/jackd -R -dalsa -dhw:0 -r48000 -p128 -n2"
        result = ensure_server_has_flags(cmd, ensure_rt=True, cpu_cores="2,3")
        
        # Should have updated cores and jackd command
        assert "2,3" in result
        assert "jackd" in result
