"""Tests for registry loading and validation."""

import json
import tempfile
from pathlib import Path

import pytest

from audioknob_gui.registry import load_registry, Knob, Impl


class TestLoadRegistry:
    """Tests for load_registry()."""

    def test_load_valid_registry(self, tmp_path: Path) -> None:
        """Valid registry loads correctly."""
        registry_data = {
            "schema": 1,
            "knobs": [
                {
                    "id": "test_knob",
                    "title": "Test Knob",
                    "description": "A test knob",
                    "category": "cpu",
                    "risk_level": "low",
                    "requires_root": False,
                    "requires_reboot": False,
                    "requires_groups": [],
                    "requires_commands": [],
                    "capabilities": {"read": True, "apply": True, "restore": True},
                    "impl": {"kind": "read_only", "params": {}},
                }
            ],
        }
        
        registry_file = tmp_path / "registry.json"
        registry_file.write_text(json.dumps(registry_data))
        
        knobs = load_registry(str(registry_file))
        
        assert len(knobs) == 1
        assert knobs[0].id == "test_knob"
        assert knobs[0].title == "Test Knob"
        assert knobs[0].requires_root is False

    def test_load_registry_with_null_impl(self, tmp_path: Path) -> None:
        """Registry with impl=null (placeholder) loads correctly."""
        registry_data = {
            "schema": 1,
            "knobs": [
                {
                    "id": "placeholder_knob",
                    "title": "Placeholder",
                    "description": "Not yet implemented",
                    "category": "cpu",
                    "risk_level": "low",
                    "requires_root": False,
                    "requires_reboot": False,
                    "requires_groups": [],
                    "requires_commands": [],
                    "capabilities": {"read": True, "apply": False, "restore": False},
                    "impl": None,
                }
            ],
        }
        
        registry_file = tmp_path / "registry.json"
        registry_file.write_text(json.dumps(registry_data))
        
        knobs = load_registry(str(registry_file))
        
        assert len(knobs) == 1
        assert knobs[0].impl is None

    def test_load_registry_missing_file(self) -> None:
        """Missing registry file raises error."""
        with pytest.raises(FileNotFoundError):
            load_registry("/nonexistent/path/registry.json")

    def test_load_registry_invalid_json(self, tmp_path: Path) -> None:
        """Invalid JSON raises error."""
        registry_file = tmp_path / "registry.json"
        registry_file.write_text("not valid json {{{")
        
        with pytest.raises(json.JSONDecodeError):
            load_registry(str(registry_file))

    def test_load_real_registry(self) -> None:
        """The actual project registry loads without error."""
        from audioknob_gui.core.paths import get_registry_path
        
        registry_path = get_registry_path()
        knobs = load_registry(registry_path)
        
        # Should have all 22 knobs
        assert len(knobs) >= 20
        
        # All knobs should have required fields
        for k in knobs:
            assert k.id
            assert k.title
            assert k.description
            assert k.category
            assert k.risk_level in ("low", "medium", "high")
