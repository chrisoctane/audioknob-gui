from __future__ import annotations

from audioknob_gui.gui.main_window import MainWindow, resolve_info_panel_knob_id
from audioknob_gui.gui.table import (
    TABLE_CELL_H_MARGIN,
    TABLE_CELL_V_MARGIN,
    TABLE_CONTROL_MIN_HEIGHT,
    TABLE_FLUSH_SURFACE_H_MARGIN,
    TABLE_FLUSH_SURFACE_V_MARGIN,
    compute_table_row_min_height,
)


def test_compute_table_row_min_height_protects_control_chrome() -> None:
    min_height = compute_table_row_min_height(16)
    assert min_height >= TABLE_CONTROL_MIN_HEIGHT + (TABLE_CELL_V_MARGIN * 2)


def test_compute_table_row_min_height_scales_with_font_height() -> None:
    assert compute_table_row_min_height(32) > compute_table_row_min_height(16)


def test_flush_surface_insets_stay_smaller_than_standard_cell_padding() -> None:
    assert TABLE_FLUSH_SURFACE_H_MARGIN < TABLE_CELL_H_MARGIN
    assert TABLE_FLUSH_SURFACE_V_MARGIN < TABLE_CELL_V_MARGIN
    assert TABLE_FLUSH_SURFACE_V_MARGIN >= 1


def test_resolve_info_panel_knob_id_prefers_selected_row() -> None:
    assert resolve_info_panel_knob_id("pipewire_rt_setup", ["pipewire_rt_setup"], None) == "pipewire_rt_setup"


def test_resolve_info_panel_knob_id_reuses_current_when_visible() -> None:
    assert resolve_info_panel_knob_id(None, ["irq_pinning", "rtirq_enable"], "rtirq_enable") == "rtirq_enable"


def test_resolve_info_panel_knob_id_falls_back_to_first_visible() -> None:
    assert resolve_info_panel_knob_id(None, ["irq_pinning", "rtirq_enable"], "missing") == "irq_pinning"


def test_open_info_panel_dialog_uses_dialog_path() -> None:
    calls: list[str] = []

    class Dummy:
        _info_panel_knob_id = "pipewire_rt_setup"

        def _open_knob_info_dialog(self, knob_id: str) -> None:
            calls.append(knob_id)

    MainWindow._open_info_panel_dialog(Dummy())
    assert calls == ["pipewire_rt_setup"]


def test_show_knob_info_prefers_panel_focus_before_dialog() -> None:
    calls: list[str] = []

    class Dummy:
        def _focus_knob_in_full_view(self, knob_id: str) -> bool:
            calls.append(f"focus:{knob_id}")
            return True

        def _open_knob_info_dialog(self, knob_id: str) -> None:
            calls.append(f"dialog:{knob_id}")

    MainWindow._show_knob_info(Dummy(), "pipewire_rt_setup")
    assert calls == ["focus:pipewire_rt_setup"]


def test_show_knob_info_falls_back_to_dialog_when_focus_unavailable() -> None:
    calls: list[str] = []

    class Dummy:
        def _focus_knob_in_full_view(self, knob_id: str) -> bool:
            calls.append(f"focus:{knob_id}")
            return False

        def _open_knob_info_dialog(self, knob_id: str) -> None:
            calls.append(f"dialog:{knob_id}")

    MainWindow._show_knob_info(Dummy(), "pipewire_rt_setup")
    assert calls == ["focus:pipewire_rt_setup", "dialog:pipewire_rt_setup"]
