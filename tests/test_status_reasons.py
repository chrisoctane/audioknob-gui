"""Tests for status reason helpers."""

from audioknob_gui.gui import status as status_mod


def test_sysfs_selected_value_extracts_bracket_token() -> None:
    assert status_mod._sysfs_selected_value("always [madvise] never") == "madvise"
    assert status_mod._sysfs_selected_value("[performance] powersave") == "performance"


def test_sysfs_partial_reason_includes_counts() -> None:
    reason = status_mod._sysfs_partial_reason(
        total=4,
        match=2,
        mismatch=1,
        unreadable=1,
        expected_val="performance",
    )
    assert reason is not None
    assert "matched 2/4 paths" in reason
    assert "expected performance" in reason
    assert "mismatched=1" in reason
    assert "unreadable=1" in reason


def test_config_partial_reason_reports_missing_lines() -> None:
    reason = status_mod._config_partial_reason(
        ["foo = 1", "bar = 2"],
        ["foo = 1"],
    )
    assert reason.startswith("missing lines:")
    assert "bar = 2" in reason


def test_config_partial_reason_reports_format_only_difference() -> None:
    reason = status_mod._config_partial_reason(
        ["foo = 1", "bar = 2"],
        ["bar = 2", "foo = 1", ""],
    )
    assert "formatting/order differs" in reason
