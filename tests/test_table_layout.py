from __future__ import annotations

from audioknob_gui.gui.table import (
    TABLE_CELL_V_MARGIN,
    TABLE_CONTROL_MIN_HEIGHT,
    compute_table_row_min_height,
)


def test_compute_table_row_min_height_protects_control_chrome() -> None:
    min_height = compute_table_row_min_height(16)
    assert min_height >= TABLE_CONTROL_MIN_HEIGHT + (TABLE_CELL_V_MARGIN * 2)


def test_compute_table_row_min_height_scales_with_font_height() -> None:
    assert compute_table_row_min_height(32) > compute_table_row_min_height(16)
