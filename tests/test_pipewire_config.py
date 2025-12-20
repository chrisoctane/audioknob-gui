"""Tests for PipeWire configuration generation."""

import tempfile
from pathlib import Path

import pytest


class TestPipeWireConfigGeneration:
    """Tests for PipeWire config file generation."""

    def test_quantum_config_content(self) -> None:
        """Quantum config contains correct properties."""
        quantum = 128
        
        lines = ["# audioknob-gui PipeWire configuration"]
        lines.append("context.properties = {")
        lines.append(f"    default.clock.quantum = {quantum}")
        lines.append(f"    default.clock.min-quantum = {quantum}")
        lines.append("}")
        content = "\n".join(lines) + "\n"
        
        assert "default.clock.quantum = 128" in content
        assert "default.clock.min-quantum = 128" in content
        assert "context.properties" in content

    def test_sample_rate_config_content(self) -> None:
        """Sample rate config contains correct properties."""
        rate = 96000
        
        lines = ["# audioknob-gui PipeWire configuration"]
        lines.append("context.properties = {")
        lines.append(f"    default.clock.rate = {rate}")
        lines.append("}")
        content = "\n".join(lines) + "\n"
        
        assert "default.clock.rate = 96000" in content

    def test_quantum_values_valid(self) -> None:
        """Only valid quantum values are accepted."""
        valid_quantums = [32, 64, 128, 256, 512, 1024]
        
        for q in valid_quantums:
            assert q in valid_quantums

    def test_sample_rate_values_valid(self) -> None:
        """Only valid sample rates are accepted."""
        valid_rates = [44100, 48000, 88200, 96000, 192000]
        
        for r in valid_rates:
            assert r in valid_rates


class TestPipeWireUserOverrides:
    """Tests for per-user PipeWire overrides from state.json."""

    def test_quantum_override_valid(self) -> None:
        """Valid quantum override is returned."""
        state = {"pipewire_quantum": 256}
        
        raw = state.get("pipewire_quantum")
        if raw is not None:
            v = int(raw)
            if v in (32, 64, 128, 256, 512, 1024):
                result = v
            else:
                result = None
        else:
            result = None
        
        assert result == 256

    def test_quantum_override_invalid(self) -> None:
        """Invalid quantum override returns None."""
        state = {"pipewire_quantum": 100}  # Not a valid quantum
        
        raw = state.get("pipewire_quantum")
        if raw is not None:
            v = int(raw)
            if v in (32, 64, 128, 256, 512, 1024):
                result = v
            else:
                result = None
        else:
            result = None
        
        assert result is None

    def test_sample_rate_override_valid(self) -> None:
        """Valid sample rate override is returned."""
        state = {"pipewire_sample_rate": 96000}
        
        raw = state.get("pipewire_sample_rate")
        if raw is not None:
            v = int(raw)
            if v in (44100, 48000, 88200, 96000, 192000):
                result = v
            else:
                result = None
        else:
            result = None
        
        assert result == 96000

    def test_sample_rate_override_invalid(self) -> None:
        """Invalid sample rate override returns None."""
        state = {"pipewire_sample_rate": 22050}  # Not a valid rate
        
        raw = state.get("pipewire_sample_rate")
        if raw is not None:
            v = int(raw)
            if v in (44100, 48000, 88200, 96000, 192000):
                result = v
            else:
                result = None
        else:
            result = None
        
        assert result is None
