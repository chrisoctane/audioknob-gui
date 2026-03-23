from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidgetItem,
    QWidget,
)

from audioknob_gui.gui.knobs.registry import (
    RowContext,
    allow_config_when_row_dim,
    get_action_override,
    get_config_widget_builder,
)
from audioknob_gui.gui.knobs import scx as scx_knob
from audioknob_gui.gui.conflicts import (
    filtered_active_conflicts,
    prune_power_profile_conflicts,
)
from audioknob_gui.gui.widgets.cell_container import CellContainer
from audioknob_gui.knob_ids import (
    AUDIO_GROUP_MEMBERSHIP,
    PIPEWIRE_MLOCK_POLICY,
    PIPEWIRE_PULSE_APP_RULES,
    PIPEWIRE_RT_MODULE_TUNING,
    PIPEWIRE_RT_SETUP,
    POWER_PROFILE_PERFORMANCE,
    SCX_SCHEDULER,
)

TABLE_CONTROL_MIN_HEIGHT = 26
TABLE_CONTROL_BORDER_RADIUS = 10
TABLE_CELL_H_MARGIN = 6
TABLE_CELL_V_MARGIN = 4
TABLE_FLUSH_SURFACE_H_MARGIN = 4
TABLE_FLUSH_SURFACE_V_MARGIN = 3


def compute_table_row_min_height(font_height: int) -> int:
    base_height = TABLE_CONTROL_MIN_HEIGHT + (TABLE_CELL_V_MARGIN * 2) + 4
    return max(base_height, int(font_height) + 18)


def cell_widget_uses_flush_surface(widget: QWidget) -> bool:
    if isinstance(widget, QPushButton):
        return True
    return bool(widget.property("table_surface_fill"))


class TableMixin:
    def _dependency_titles(self, k) -> list[str]:
        depends = getattr(k, "depends_on", ()) or ()
        if not depends:
            return []
        titles = {knob.id: knob.title for knob in self.registry}
        return [titles.get(dep, dep) for dep in depends]

    def _missing_dependencies(self, k) -> list[str]:
        depends = getattr(k, "depends_on", ()) or ()
        if not depends:
            return []
        missing: list[str] = []
        for dep in depends:
            status = self._knob_statuses.get(dep, "unknown")
            if status in ("applied", "pending_reboot", "active_external"):
                continue
            missing.append(dep)
        return missing

    def _confirm_conflict_reset(self, knob_id: str) -> None:
        titles = {knob.id: knob.title for knob in self.registry}
        title = titles.get(knob_id, knob_id)
        msg = (
            f"Reset '{title}' to match saved preset/default state?\n\n"
            "This will queue a Reset for this knob."
        )
        if QMessageBox.question(self, "Resolve Conflict", msg) != QMessageBox.Yes:
            return
        self._on_queue_knob(knob_id, "reset")

    def _requirements_label(self, k, advanced_knobs: set[str]) -> str:
        parts: list[str] = []
        if k.id in advanced_knobs:
            parts.append("A")
        if k.requires_reboot:
            parts.append("R")
        if k.requires_groups or getattr(k, "depends_on", ()):
            parts.append("D")
        if not parts:
            return ""
        return " ".join(parts)


    def _requirements_key_tooltip(self) -> str:
        return "A=Advanced, R=Reboot required, D=Depends on prerequisites"


    def _requirements_tooltip(self, k, advanced_knobs: set[str]) -> str:
        legend = self._requirements_key_tooltip()
        req_parts: list[str] = []
        if k.id in advanced_knobs:
            req_parts.append("Advanced")
        if k.requires_reboot:
            req_parts.append("Reboot required")
        if k.requires_groups:
            req_parts.append(f"Groups: {', '.join(k.requires_groups)}")
        dep_titles = self._dependency_titles(k)
        if not req_parts and not dep_titles:
            return f"{legend}\nNo requirements"
        lines = [legend]
        if req_parts:
            lines.append(f"Requires: {', '.join(req_parts)}")
        if dep_titles:
            lines.append(f"Depends on: {', '.join(dep_titles)}")
        return "\n".join(lines)


    def _requirements_group_tooltip(self, label: str) -> str:
        legend = self._requirements_key_tooltip()
        if not label or label == "—":
            return f"{legend}\nNo requirements"
        parts: list[str] = []
        for letter in label.split():
            if letter == "A":
                parts.append("Advanced")
            elif letter == "R":
                parts.append("Reboot required")
            elif letter == "D":
                parts.append("Depends on prerequisites")
        if not parts:
            return legend
        return f"{legend}\nRequires: {', '.join(parts)}"


    def _grouping_mode(self) -> str | None:
        if self._sort_column is None or self._sort_column == 6:
            return "category"
        if self._sort_column == 4:
            return "requirements"
        if self._sort_column == 5:
            return "status"
        if self._sort_column == 7:
            return "risk"
        return None


    def _category_label(self, key: str) -> str:
        mapping = {
            "cpu": "CPU",
            "irq": "IRQ",
            "kernel": "Kernel",
            "permissions": "Permissions",
            "power": "Power",
            "services": "Services",
            "stack": "Stack",
            "testing": "Testing",
            "vm": "Memory",
        }
        if key in mapping:
            return mapping[key]
        cleaned = key.replace("_", " ").strip()
        return cleaned.title() if cleaned else key


    def _sys_label_for_knob(self, k) -> str:
        if k.impl is None:
            return "—"
        kind = k.impl.kind
        params = k.impl.params or {}

        if kind == "kernel_cmdline":
            param = self._kernel_cmdline_param_for_state(k.id)
            if not param:
                param = str(params.get("param", "")).strip()
            if param:
                return param.split("=", 1)[0].strip() or param
            return "cmdline"

        if kind == "sysctl_conf":
            lines = params.get("lines") or []
            keys: list[str] = []
            for line in lines:
                raw = str(line).strip()
                if not raw or raw.startswith("#") or "=" not in raw:
                    continue
                key = raw.split("=", 1)[0].strip()
                if key and key not in keys:
                    keys.append(key)
            return ",".join(keys) if keys else "sysctl"

        if kind == "sysfs_glob_kv":
            glob = str(params.get("glob", "")).strip()
            return Path(glob).name if glob else "sysfs"

        if kind == "udev_rule":
            path = str(params.get("path", "")).strip()
            return Path(path).name if path else "udev"

        if kind == "pam_limits_audio_group":
            path = str(params.get("path", "")).strip()
            return Path(path).name if path else "limits"

        if kind == "power_profile":
            backend = self._power_profile_backend_from_state()
            if backend == "powerprofilesctl":
                return "powerprofilesctl"
            if backend == "tuned":
                return "tuned-adm"
            return "powerprofilesctl/tuned"

        if kind == "qjackctl_server_prefix":
            return "QjackCtl.conf"

        if kind == "pipewire_conf":
            return "pipewire.conf.d"

        if kind == "wireplumber_conf":
            return "wireplumber.conf.d"

        if kind == "wpctl_profile":
            return "wpctl"

        if kind == "alsa_xrun_debug":
            return "/proc/asound"

        if kind == "read_only":
            what = str(params.get("what", "")).strip()
            return what or "read-only"

        if kind == "systemd_unit_toggle":
            unit = str(params.get("unit", "")).strip()
            return unit or "systemd"

        if kind == "rtirq_config":
            profile = self.state.get("system_profile")
            if isinstance(profile, dict):
                paths = profile.get("paths")
                if isinstance(paths, dict):
                    rtirq_path = str(paths.get("rtirq_config") or "")
                    if rtirq_path:
                        return Path(rtirq_path).name
            return "rtirq.conf"

        if kind == "scx_scheduler":
            return "scx.service"

        if kind == "irq_affinity":
            return "/proc/irq"

        if kind == "group_membership":
            return "groups"

        if kind == "user_service_mask":
            if k.id == "disable_tracker":
                return "tracker"
            services = params.get("services")
            if isinstance(services, list):
                items = [str(s) for s in services if s]
                if items:
                    return ",".join(items)
            unit = str(params.get("unit", "")).strip()
            return unit or "user service"

        if kind == "baloo_disable":
            return "balooctl"

        if kind == "read_only":
            what = str(params.get("what", "")).strip()
            return what or "read_only"

        return kind


    def _make_apply_button(self, text: str = "Apply") -> QPushButton:
        """Create an Apply button."""
        btn = QPushButton(text)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setMinimumHeight(TABLE_CONTROL_MIN_HEIGHT)
        btn.setMinimumWidth(0)
        btn.setFocusPolicy(Qt.NoFocus)
        self._style_table_button(btn)
        return btn


    def _make_reset_button(self, text: str = "Reset") -> QPushButton:
        """Create a Reset button."""
        btn = QPushButton(text)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setMinimumHeight(TABLE_CONTROL_MIN_HEIGHT)
        btn.setMinimumWidth(0)
        btn.setFocusPolicy(Qt.NoFocus)
        self._style_table_button(btn)
        return btn


    def _make_action_button(self, text: str) -> QPushButton:
        """Create an action button."""
        btn = QPushButton(text)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setMinimumHeight(TABLE_CONTROL_MIN_HEIGHT)
        btn.setMinimumWidth(0)
        btn.setFocusPolicy(Qt.NoFocus)
        self._style_table_button(btn)
        return btn


    def _style_table_button(self, btn: QPushButton, *, row_dim: bool = False) -> None:
        bg = "#20242b" if row_dim else "#262c34"
        border = "#2c343e" if row_dim else "#34404c"
        hover_bg = "#2c333d" if row_dim else "#313b47"
        pressed_bg = "#1d2228" if row_dim else "#232930"
        btn.setStyleSheet(
            "QPushButton {"
            f" background-color: {bg};"
            " color: #edf1f7;"
            f" border: 1px solid {border};"
            f" border-radius: {TABLE_CONTROL_BORDER_RADIUS}px;"
            " padding: 2px 10px;"
            f" min-height: {TABLE_CONTROL_MIN_HEIGHT}px;"
            " font-weight: 500;"
            "}"
            "QPushButton:hover {"
            f" background-color: {hover_bg};"
            " border-color: #617997;"
            "}"
            "QPushButton:pressed {"
            f" background-color: {pressed_bg};"
            "}"
            "QPushButton:disabled {"
            " color: #7d8796;"
            " background-color: #1c2026;"
            " border-color: #2a3038;"
            "}"
        )


    def _style_table_combo(self, widget: QWidget) -> None:
        widget.setStyleSheet(
            f"""
            QComboBox, QSpinBox {{
                background-color: #262c34;
                color: #edf1f7;
                border: 1px solid #34404c;
                padding: 2px 8px;
                border-radius: {TABLE_CONTROL_BORDER_RADIUS}px;
                min-height: {TABLE_CONTROL_MIN_HEIGHT}px;
            }}
            QComboBox:hover, QSpinBox:hover {{
                background-color: #2b3139;
                border-color: #617997;
            }}
            QComboBox:focus, QSpinBox:focus {{
                border-color: #6b93bf;
            }}
            QComboBox:disabled, QSpinBox:disabled {{
                background-color: #1c2026;
                color: #7d8796;
                border: 1px solid #2a3038;
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border: none;
                border-left: 1px solid #313844;
                background-color: transparent;
                margin: 1px 1px 1px 0;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                border: none;
                border-left: 1px solid #313844;
                background-color: transparent;
                width: 18px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #262c34;
                color: #edf1f7;
                selection-background-color: #313b47;
            }}
            """
        )


    def _apply_busy_state(self, btn: QPushButton, *, busy: bool) -> None:
        if busy:
            btn.setText("Working...")
            btn.setEnabled(False)


    def _apply_baseline_lock(self, btn: QPushButton) -> None:
        if self._baseline_ready:
            return
        if bool(btn.property("baseline_exempt")):
            return
        label = btn.text().strip().lower()
        if label == "install":
            return
        if label not in ("apply", "reset", "install", "join", "leave"):
            return
        btn.setEnabled(False)
        btn.setToolTip("Initial state scan pending. Finish reference preset scan before changes.")



    def _install_hover_tracking(self, widget: QWidget, row: int) -> None:
        widget.setProperty("hover_row", row)
        widget.setMouseTracking(True)
        widget.installEventFilter(self)


    def _row_bg_color(self, row: int) -> QColor:
        row_dim = False
        if getattr(self, "_row_dim", None) and row < len(self._row_dim):
            row_dim = self._row_dim[row]
        if row_dim:
            return QColor("#1f1f1f")
        return QColor("#353535" if row % 2 else "#2f2f2f")


    def _ensure_widget_cell_bg(self, row: int, col: int) -> None:
        item = self.table.item(row, col)
        if item is None:
            item = QTableWidgetItem("")
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self.table.setItem(row, col, item)
        item.setBackground(self._row_bg_color(row))


    def _clear_row_widgets(self, row: int) -> None:
        for col in range(self.table.columnCount()):
            if self.table.cellWidget(row, col) is not None:
                self.table.setCellWidget(row, col, None)


    def _wrap_cell_widget(self, row: int, col: int, widget: QWidget) -> None:
        self._ensure_widget_cell_bg(row, col)
        container = CellContainer(self._row_bg_color(row))
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QHBoxLayout(container)
        if cell_widget_uses_flush_surface(widget):
            layout.setContentsMargins(
                TABLE_FLUSH_SURFACE_H_MARGIN,
                TABLE_FLUSH_SURFACE_V_MARGIN,
                TABLE_FLUSH_SURFACE_H_MARGIN,
                TABLE_FLUSH_SURFACE_V_MARGIN,
            )
        else:
            layout.setContentsMargins(
                TABLE_CELL_H_MARGIN,
                TABLE_CELL_V_MARGIN,
                TABLE_CELL_H_MARGIN,
                TABLE_CELL_V_MARGIN,
            )
        layout.setSpacing(0)
        if widget.sizePolicy().horizontalPolicy() in (QSizePolicy.Expanding, QSizePolicy.MinimumExpanding):
            layout.setAlignment(Qt.AlignVCenter)
            layout.addWidget(widget, 1)
        else:
            layout.setAlignment(Qt.AlignCenter)
            layout.addWidget(widget)
        self._install_hover_tracking(container, row)
        self.table.setCellWidget(row, col, container)


    def _status_button_stylesheet(self, text_color: str, *, row_dim: bool = False, accent: str | None = None) -> str:
        background = "#20242b" if row_dim else "#222934"
        hover_background = "#2b333f" if row_dim else "#2d3846"
        border = accent or "#3d4b5f"
        disabled_background = "#1c2026"
        return (
            "QPushButton {"
            " text-align: center;"
            f" color: {text_color};"
            f" background-color: {background};"
            f" border: 1px solid {border};"
            f" border-radius: {TABLE_CONTROL_BORDER_RADIUS}px;"
            " padding: 2px 10px;"
            f" min-height: {TABLE_CONTROL_MIN_HEIGHT}px;"
            " font-weight: 600;"
            "}"
            "QPushButton:hover {"
            f" background-color: {hover_background};"
            " border-color: #6f8fb7;"
            "}"
            "QPushButton:disabled {"
            " color: #8e96a3;"
            f" background-color: {disabled_background};"
            " border-color: #313844;"
            "}"
        )


    def _set_action_cell(self, row: int, widget: QWidget) -> None:
        self._install_hover_tracking(widget, row)
        if isinstance(widget, QPushButton):
            self._apply_baseline_lock(widget)
        self._wrap_cell_widget(row, 2, widget)


    def _set_config_cell(self, row: int, widget: QWidget) -> None:
        self._install_hover_tracking(widget, row)
        if isinstance(widget, (QComboBox, QSpinBox)):
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setMinimumHeight(TABLE_CONTROL_MIN_HEIGHT)
            widget.setProperty("table_surface_fill", True)
            self._style_table_combo(widget)
        self._wrap_cell_widget(row, 3, widget)


    def _set_status_cell(self, row: int, widget: QWidget) -> None:
        self._install_hover_tracking(widget, row)
        self._wrap_cell_widget(row, 5, widget)


    def _table_row_min_height(self) -> int:
        try:
            return compute_table_row_min_height(self.table.fontMetrics().height())
        except Exception:
            return compute_table_row_min_height(TABLE_CONTROL_MIN_HEIGHT)


    def _enforce_table_row_heights(self) -> None:
        min_height = self._table_row_min_height()
        try:
            header = self.table.verticalHeader()
            header.setMinimumSectionSize(0)
            header.setDefaultSectionSize(min_height)
        except Exception:
            pass
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None or item.flags() == Qt.NoItemFlags:
                continue
            try:
                if self.table.rowHeight(row) < min_height:
                    self.table.setRowHeight(row, min_height)
            except Exception:
                continue


    def _preset_match_flags(self, knob_id: str) -> tuple[bool, bool]:
        flags = getattr(self, "_knob_preset_flags", {})
        if not isinstance(flags, dict):
            return False, False
        row = flags.get(knob_id)
        if not isinstance(row, dict):
            return False, False
        return bool(row.get("reference")), bool(row.get("factory"))


    def _preset_dot_widget(self, color: str, tooltip: str) -> QWidget:
        dot = QWidget()
        dot.setFixedSize(10, 10)
        dot.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        dot.setToolTip(tooltip)
        dot.setStyleSheet(
            "QWidget {"
            f" background-color: {color};"
            " border: 1px solid #1f1f1f;"
            " border-radius: 5px;"
            "}"
        )
        return dot


    def _status_display(self, status: str) -> tuple[str, str]:
        """Return (display_text, color) for a status."""
        # Handle test results: "result:12 µs" → "12 µs"
        if status.startswith("result:"):
            return (status[7:], "#1976d2")  # Blue
        
        mapping = {
            "applied": ("✓ Applied", "#2e7d32"),      # Green
            "configured": ("○ Configured", "#7cb342"),  # Olive - config synced, runtime stopped
            "active_external": ("~ External", "#4a90e2"),  # Blue - set outside audioknob
            "not_applied": ("—", "#757575"),          # Gray dash
            "not_applicable": ("N/A", "#9e9e9e"),     # Gray N/A
            "partial": ("◐ Partial", "#f6c343"),      # Pastel yellow
            "pending_reboot": ("⟳ Reboot", "#f57c00"), # Orange - needs reboot
            "read_only": ("—", "#9e9e9e"),            # Gray dash
            "unknown": ("—", "#9e9e9e"),              # Gray dash
            "running": ("⏳ Updating", "#1976d2"),    # Blue spinner
            "done": ("✓", "#2e7d32"),                 # Green check
            "error": ("✗", "#d32f2f"),                # Red X
            "sys_default": ("—", "#757575"),
            "deviated": ("—", "#757575"),
        }
        return mapping.get(status, ("—", "#9e9e9e"))


    def _populate(self) -> None:
        # Repopulating the table rebuilds all rows/cell widgets, which can reset the
        # scroll position (and even force a scroll-to-current-item). Preserve the
        # user's view so config tweaks don't jump the UI away from where they're
        # working.
        v_scroll = None
        h_scroll = None
        try:
            v_scroll = self.table.verticalScrollBar().value()
            h_scroll = self.table.horizontalScrollBar().value()
            self.table.clearSelection()
            self.table.setCurrentCell(-1, -1)
            self._clear_dim_hover()
        except Exception:
            v_scroll = None
            h_scroll = None

        # Disable sorting during population to avoid issues
        self.table.setSortingEnabled(False)
        self.table.clearSpans()
        self.table.clearContents()
        try:
            if hasattr(self, "_apply_baseline_statuses"):
                self._apply_baseline_statuses()
        except Exception:
            pass
        self._refresh_core_plan_summary()
        reboot_gate_enabled = bool(self.state.get("enable_reboot_knobs", False))
        advanced_enabled = bool(self.state.get("advanced_mode_enabled", False))
        group_pending = self._knob_statuses.get(AUDIO_GROUP_MEMBERSHIP) == "pending_reboot"
        desktop_kind = self._detect_desktop()
        advanced_knobs = self._advanced_knob_ids()
        visible_knobs = self._visible_knobs()
        ordered: list[object] = []
        grouping_mode = self._grouping_mode()

        def _sort_key(k, col: int) -> tuple:
            status = self._knob_statuses.get(k.id, "unknown")
            status_order = {
                "applied": 0,
                "configured": 1,
                "active_external": 2,
                "pending_reboot": 3,
                "partial": 4,
                "not_applied": 5,
                "not_applicable": 6,
                "unknown": 7,
                "sys_default": 4,
                "deviated": 4,
            }
            risk_order = {"low": 0, "medium": 1, "high": 2}

            if col == 4:
                req = self._requirements_label(k, advanced_knobs).lower()
                return (req, k.title.lower())
            if col == 5:
                return (status_order.get(status, 99), k.title.lower())
            if col == 6:
                return (str(k.category).lower(), k.title.lower())
            if col == 7:
                return (risk_order.get(str(k.risk_level), 99), k.title.lower())
            if col == 8:
                sys_label = self._sys_label_for_knob(k).lower()
                return (sys_label, k.title.lower())
            if col in (0, 1, 2, 3):
                return (k.title.lower(),)
            return (status_order.get(status, 99), k.title.lower())

        category_order = [
            "cpu",
            "irq",
            "kernel",
            "permissions",
            "power",
            "services",
            "stack",
            "vm",
            "testing",
        ]

        def _sorted_items(items: list[object], *, force_title: bool = False) -> list[object]:
            if self._sort_column is None:
                return items
            if force_title:
                return sorted(items, key=lambda k: k.title.lower(), reverse=self._sort_descending)
            col = int(self._sort_column)
            return sorted(items, key=lambda k: _sort_key(k, col), reverse=self._sort_descending)

        CATEGORY_HEADER = object()
        CATEGORY_SEPARATOR = object()
        if grouping_mode is None:
            ordered = _sorted_items(list(visible_knobs))
        elif grouping_mode == "category":
            by_category: dict[str, list[object]] = {}
            for k in visible_knobs:
                key = str(getattr(k, "category", "uncategorized"))
                by_category.setdefault(key, []).append(k)
            known_categories = set(category_order)
            extra_categories = sorted(set(by_category.keys()) - known_categories)
            ordered_categories = (
                [(c, self._category_label(c)) for c in category_order]
                + [(c, self._category_label(c)) for c in extra_categories]
            )
            if self._sort_column == 6 and self._sort_descending:
                ordered_categories = list(reversed(ordered_categories))
            for cat_key, cat_label in ordered_categories:
                items = by_category.get(cat_key, [])
                if not items:
                    continue
                ordered.append((CATEGORY_HEADER, cat_label))
                ordered.extend(_sorted_items(items, force_title=self._sort_column is not None))
                ordered.append(CATEGORY_SEPARATOR)
            if ordered and ordered[-1] is CATEGORY_SEPARATOR:
                ordered.pop()
        elif grouping_mode == "requirements":
            by_req: dict[str, list[object]] = {}
            for k in visible_knobs:
                label = self._requirements_label(k, advanced_knobs)
                by_req.setdefault(label, []).append(k)
            req_order = ["", "A", "R", "G", "A R", "A G", "R G", "A R G"]
            extra_labels = sorted(set(by_req.keys()) - set(req_order))
            ordered_labels = req_order + extra_labels
            if self._sort_descending:
                ordered_labels = list(reversed(ordered_labels))
            for label in ordered_labels:
                items = by_req.get(label, [])
                if not items:
                    continue
                header_label = label or "None"
                ordered.append((CATEGORY_HEADER, header_label, self._requirements_group_tooltip(label)))
                ordered.extend(_sorted_items(items, force_title=True))
                ordered.append(CATEGORY_SEPARATOR)
            if ordered and ordered[-1] is CATEGORY_SEPARATOR:
                ordered.pop()
        elif grouping_mode == "status":
            status_labels = {
                "applied": "Applied",
                "configured": "Configured",
                "active_external": "External",
                "pending_reboot": "Reboot Required",
                "partial": "Partial",
                "not_applied": "Not Applied",
                "not_applicable": "N/A",
                "read_only": "Read Only",
                "unknown": "Unknown",
            }
            status_order = [
                "applied",
                "configured",
                "active_external",
                "pending_reboot",
                "partial",
                "not_applied",
                "not_applicable",
                "read_only",
                "unknown",
            ]
            by_status: dict[str, list[object]] = {}
            for k in visible_knobs:
                status = self._knob_statuses.get(k.id, "unknown")
                key = status if status in status_labels else "unknown"
                by_status.setdefault(key, []).append(k)
            extra_statuses = sorted(set(by_status.keys()) - set(status_order))
            ordered_statuses = status_order + extra_statuses
            if self._sort_descending:
                ordered_statuses = list(reversed(ordered_statuses))
            for key in ordered_statuses:
                items = by_status.get(key, [])
                if not items:
                    continue
                label = status_labels.get(key, key)
                ordered.append((CATEGORY_HEADER, label))
                ordered.extend(_sorted_items(items, force_title=True))
                ordered.append(CATEGORY_SEPARATOR)
            if ordered and ordered[-1] is CATEGORY_SEPARATOR:
                ordered.pop()
        elif grouping_mode == "risk":
            risk_labels = {"low": "Low", "medium": "Medium", "high": "High", "unknown": "Unknown"}
            risk_order = ["low", "medium", "high", "unknown"]
            by_risk: dict[str, list[object]] = {}
            for k in visible_knobs:
                risk = str(getattr(k, "risk_level", "unknown")).lower()
                key = risk if risk in risk_labels else "unknown"
                by_risk.setdefault(key, []).append(k)
            extra_risks = sorted(set(by_risk.keys()) - set(risk_order))
            ordered_risks = risk_order + extra_risks
            if self._sort_descending:
                ordered_risks = list(reversed(ordered_risks))
            for key in ordered_risks:
                items = by_risk.get(key, [])
                if not items:
                    continue
                ordered.append((CATEGORY_HEADER, risk_labels.get(key, key.title())))
                ordered.extend(_sorted_items(items, force_title=True))
                ordered.append(CATEGORY_SEPARATOR)
            if ordered and ordered[-1] is CATEGORY_SEPARATOR:
                ordered.pop()

        self.table.setRowCount(len(ordered))
        self._row_dim = [False] * len(ordered)

        for r, k in enumerate(ordered):
            self._clear_row_widgets(r)
            if isinstance(k, tuple) and k and k[0] is CATEGORY_HEADER:
                label = str(k[1])
                tooltip = str(k[2]) if len(k) > 2 and k[2] else ""
                header_bg = QColor("#181c22")
                for c in range(self.table.columnCount()):
                    self.table.removeCellWidget(r, c)
                self.table.setSpan(r, 0, 1, self.table.columnCount())
                header_item = QTableWidgetItem(label)
                header_item.setFlags(Qt.NoItemFlags)
                header_item.setForeground(QColor("#e5ebf5"))
                header_item.setBackground(header_bg)
                header_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
                header_font = header_item.font()
                header_font.setBold(True)
                header_font.setPointSize(max(header_font.pointSize(), 11))
                header_item.setFont(header_font)
                if tooltip:
                    header_item.setToolTip(tooltip)
                self.table.setItem(r, 0, header_item)
                for c in range(1, self.table.columnCount()):
                    filler = QTableWidgetItem("")
                    filler.setFlags(Qt.NoItemFlags)
                    filler.setBackground(header_bg)
                    self.table.setItem(r, c, filler)
                try:
                    self.table.setRowHeight(r, 34)
                except Exception:
                    pass
                continue
            if k is CATEGORY_SEPARATOR:
                sep_bg = QColor("#161a20")
                for c in range(self.table.columnCount()):
                    self.table.removeCellWidget(r, c)
                sep = QTableWidgetItem("")
                sep.setFlags(Qt.NoItemFlags)
                sep.setForeground(QColor("#576272"))
                sep.setBackground(sep_bg)
                sep.setTextAlignment(Qt.AlignCenter)
                self.table.setSpan(r, 0, 1, self.table.columnCount())
                self.table.setItem(r, 0, sep)
                for c in range(1, self.table.columnCount()):
                    filler = QTableWidgetItem("")
                    filler.setFlags(Qt.NoItemFlags)
                    filler.setBackground(sep_bg)
                    self.table.setItem(r, c, filler)
                try:
                    self.table.setRowHeight(r, 14)
                except Exception:
                    pass
                continue
            status = self._knob_statuses.get(k.id, "unknown")
            busy = k.id in self._busy_knobs
            display_status = "running" if busy else status
            not_applicable = (status == "not_applicable")
            not_applicable_reason = "Not available on this system"
            if k.id == "disable_tracker" and desktop_kind == "kde":
                not_applicable = True
                not_applicable_reason = "Requires GNOME desktop"
            elif k.id == "disable_baloo" and desktop_kind == "gnome":
                not_applicable = True
                not_applicable_reason = "Requires KDE desktop"
            elif k.id == POWER_PROFILE_PERFORMANCE and not_applicable:
                backend = self._power_profile_backend_from_state()
                if backend == "powerprofilesctl":
                    not_applicable_reason = "Requires powerprofilesctl"
                elif backend == "tuned":
                    not_applicable_reason = "Requires tuned-adm"
                else:
                    not_applicable_reason = "Requires powerprofilesctl or tuned-adm"
            locked_bg = QColor("#1f1f1f")
            locked_fg = QColor("#7a7a7a")
            locked_style = (
                "QPushButton {"
                " background-color: #20252c;"
                " color: #7d8796;"
                " border: 1px solid #313844;"
                f" border-radius: {TABLE_CONTROL_BORDER_RADIUS}px;"
                " padding: 2px 10px;"
                f" min-height: {TABLE_CONTROL_MIN_HEIGHT}px;"
                "}"
                "QPushButton:hover {"
                " background-color: #20252c;"
                " color: #7d8796;"
                " border: 1px solid #313844;"
                "}"
                "QPushButton:pressed {"
                " background-color: #20252c;"
                " color: #7d8796;"
                " border: 1px solid #313844;"
                "}"
            )

            # Check requirements
            group_ok = self._knob_group_ok(k)
            group_pending_lock = bool(k.requires_groups) and group_pending
            if group_pending_lock:
                group_ok = False
            commands_ok = self._knob_commands_ok(k)
            missing_cmds = self._knob_missing_commands(k)
            reboot_gate_lock = bool(k.requires_reboot) and not reboot_gate_enabled and status not in ("applied", "pending_reboot", "active_external")
            advanced_gate_lock = k.id in advanced_knobs and not advanced_enabled and status not in ("applied", "pending_reboot", "active_external")
            reboot_dep_lock = (not reboot_gate_enabled) and bool(k.requires_groups)
            missing_deps = self._missing_dependencies(k)
            dependency_lock = bool(missing_deps) and status not in ("applied", "pending_reboot", "active_external")
            locked = not group_ok or not commands_ok or reboot_gate_lock or reboot_dep_lock or advanced_gate_lock or dependency_lock
            simple_owned_reason = ""
            lock_fn = getattr(self, "_simple_owned_lock_reason", None)
            if callable(lock_fn):
                try:
                    simple_owned_reason = str(lock_fn(k.id, status) or "")
                except Exception:
                    simple_owned_reason = ""
            if simple_owned_reason:
                locked = True
            tuned_managed_reason = ""
            tuned_fn = getattr(self, "_tuned_managed_lock_reason", None)
            if callable(tuned_fn):
                try:
                    tuned_managed_reason = str(tuned_fn(k.id) or "")
                except Exception:
                    tuned_managed_reason = ""
            if tuned_managed_reason:
                locked = True
            scx_managed_reason = ""
            scx_fn = getattr(self, "_scx_managed_lock_reason", None)
            if callable(scx_fn):
                try:
                    scx_managed_reason = str(scx_fn(k.id) or "")
                except Exception:
                    scx_managed_reason = ""
            if scx_managed_reason:
                locked = True
            requires_config = False
            if (
                k.impl is not None
                and k.impl.kind == "pipewire_conf"
                and status not in ("applied", "pending_reboot", "active_external")
            ):
                if k.id == "pipewire_clock_constraints":
                    state_keys = (
                        "pipewire_clock_allowed_rates",
                        "pipewire_clock_min_quantum",
                        "pipewire_clock_max_quantum",
                        "pipewire_clock_quantum_limit",
                        "pipewire_clock_quantum_floor",
                        "pipewire_clock_power_of_two",
                    )
                    requires_config = not any(self.state.get(key) is not None for key in state_keys)
                elif k.id == PIPEWIRE_MLOCK_POLICY:
                    requires_config = not (
                        isinstance(self.state.get("pipewire_mlock_allow"), bool)
                        or isinstance(self.state.get("pipewire_mlock_all"), bool)
                    )
                elif k.id == PIPEWIRE_RT_MODULE_TUNING:
                    state_keys = (
                        "pipewire_rt_prio",
                        "pipewire_rt_time_soft",
                        "pipewire_rt_time_hard",
                        "pipewire_nice_level",
                        "pipewire_rlimits_enabled",
                        "pipewire_rtkit_enabled",
                        "pipewire_rtportal_enabled",
                        "pipewire_uclamp_min",
                        "pipewire_uclamp_max",
                        "pipewire_cpu_zero_denormals",
                    )
                    requires_config = not any(self.state.get(key) is not None for key in state_keys)
                elif k.id == "pipewire_pulse_latency":
                    requires_config = not (
                        isinstance(self.state.get("pipewire_pulse_min_req"), str)
                        and bool(str(self.state.get("pipewire_pulse_min_req")).strip())
                        or isinstance(self.state.get("pipewire_pulse_default_req"), str)
                        and bool(str(self.state.get("pipewire_pulse_default_req")).strip())
                        or isinstance(self.state.get("pipewire_pulse_min_quantum"), str)
                        and bool(str(self.state.get("pipewire_pulse_min_quantum")).strip())
                    )
                elif k.id == PIPEWIRE_PULSE_APP_RULES:
                    raw_rules = self.state.get(PIPEWIRE_PULSE_APP_RULES)
                    requires_config = not (
                        isinstance(raw_rules, list)
                        and any(isinstance(item, dict) for item in raw_rules)
                    )
                elif k.id == "pipewire_data_loop_affinity":
                    requires_config = not (
                        isinstance(self.state.get("pipewire_num_data_loops"), int)
                        or isinstance(self.state.get("pipewire_data_loops"), list)
                    )
            if status not in ("applied", "pending_reboot", "active_external"):
                if k.id == SCX_SCHEDULER:
                    requires_config = scx_knob.effective_scheduler(self) is None
                elif k.id == "kernel_workqueue_cpumask":
                    cores = self.state.get("kernel_workqueue_cpumask_cores")
                    requires_config = not (
                        isinstance(cores, list) and any(isinstance(x, int) for x in cores)
                    )
                elif k.id == "cgroup_user_slice_allowed_cpus":
                    cores = self.state.get("cgroup_user_slice_allowed_cores")
                    requires_config = not (
                        isinstance(cores, list) and any(isinstance(x, int) for x in cores)
                    )
                elif k.id == "irqbalance_banned_cpulist":
                    cores = self.state.get("irqbalance_banned_cpulist_cores")
                    requires_config = not (
                        isinstance(cores, list) and any(isinstance(x, int) for x in cores)
                    )
                elif k.id in ("systemd_pipewire_service_rt", "systemd_wireplumber_service_rt"):
                    prefix = k.id
                    requires_config = not any(
                        self.state.get(key) is not None
                        for key in (
                            f"{prefix}_policy",
                            f"{prefix}_priority",
                            f"{prefix}_cpus",
                        )
                    )

            conflict_ids = set()
            try:
                conflict_ids = filtered_active_conflicts(
                    k.id, self._queued_actions, self._knob_statuses, state=self.state
                )
                conflict_ids = prune_power_profile_conflicts(
                    k.id,
                    conflict_ids,
                    backend_is_tuned=self._power_profile_backend_is_tuned(),
                )
            except Exception:
                conflict_ids = set()
            conflict_lock = bool(conflict_ids) and status not in ("applied", "pending_reboot", "active_external")

            row_dim = locked or not_applicable or requires_config
            self._row_dim[r] = row_dim
            
            # Determine lock reason
            lock_reason = ""
            if simple_owned_reason:
                lock_reason = simple_owned_reason
            elif tuned_managed_reason:
                lock_reason = tuned_managed_reason
            elif scx_managed_reason:
                lock_reason = scx_managed_reason
            elif group_pending_lock:
                lock_reason = f"Groups pending reboot: {', '.join(k.requires_groups)}"
            elif reboot_dep_lock:
                lock_reason = f"Requires groups: {', '.join(k.requires_groups)} (Turn on Reboot-required changes)"
            elif not group_ok:
                lock_reason = f"Join groups: {', '.join(k.requires_groups)}"
            elif reboot_gate_lock:
                lock_reason = f"Reboot required: {k.title}"
            elif advanced_gate_lock:
                lock_reason = "Turn on Advanced knobs"
            elif not commands_ok:
                lock_reason = f"Install: {', '.join(missing_cmds)}"
            elif dependency_lock:
                titles = {knob.id: knob.title for knob in self.registry}
                dep_titles = [titles.get(dep, dep) for dep in missing_deps]
                lock_reason = f"Depends on: {', '.join(dep_titles)}"
            elif requires_config:
                lock_reason = "Configure this knob before applying"
            if conflict_ids:
                by_id = {knob.id: knob.title for knob in self.registry}
                conflict_titles: list[str] = []
                for cid in sorted(conflict_ids):
                    title = by_id.get(cid, cid)
                    action = self._queued_actions.get(cid)
                    if action == "apply":
                        state_desc = "queued apply"
                    elif action == "reset":
                        state_desc = "queued reset"
                    else:
                        state_desc = self._knob_statuses.get(cid, "unknown")
                    conflict_titles.append(f"{title} ({state_desc})")
                conflict_tip = (
                    "Conflicts with active/queued knobs: "
                    + ", ".join(conflict_titles)
                    + ". Resolve by resetting one side or use queue apply options."
                )
                lock_reason = conflict_tip if not lock_reason else f"{lock_reason}\n{conflict_tip}"
            
            self._ensure_widget_cell_bg(r, 0)

            # Column 1: Knob title (gray if locked)
            title_item = QTableWidgetItem(k.title)
            title_item.setData(Qt.UserRole, k.id)  # Store ID for lookup
            title_item.setBackground(self._row_bg_color(r))
            if row_dim:
                title_item.setForeground(locked_fg)
            if locked:
                title_item.setToolTip(lock_reason)
            elif not_applicable:
                title_item.setToolTip(not_applicable_reason)
            self.table.setItem(r, 1, title_item)

            # Column 4: Requirements
            req_item = QTableWidgetItem(self._requirements_label(k, advanced_knobs))
            req_item.setToolTip(self._requirements_tooltip(k, advanced_knobs))
            req_item.setBackground(self._row_bg_color(r))
            req_item.setTextAlignment(Qt.AlignCenter)
            if row_dim:
                req_item.setForeground(locked_fg)
            self.table.setItem(r, 4, req_item)

            # Column 5: Status (with color)
            status_tip = ""
            if locked:
                if tuned_managed_reason:
                    status_text = "via tuned"
                elif scx_managed_reason:
                    status_text = "via scx"
                else:
                    status_text = "Locked"
                status_color = locked_fg.name()
                status_tip = lock_reason
            elif not_applicable:
                status_text = "N/A"
                status_color = locked_fg.name()
                status_tip = not_applicable_reason
            else:
                status_text, status_color = self._status_display(display_status)
                if conflict_ids:
                    status_color = "#d32f2f"
                tooltip_map = {
                    "applied": "Applied.",
                    "active_external": "Set outside AudioKnob.",
                    "configured": "Config is synced, but runtime is currently stopped.",
                    "partial": "Partially applied. Click status to view exact reasons.",
                    "pending_reboot": "Applied in boot config; reboot required.",
                    "not_applied": "Not applied.",
                    "not_applicable": "Not available on this system.",
                    "read_only": "Read-only check.",
                    "unknown": "Status unknown. Click status to run live checks.",
                    "running": "Updating...",
                    "done": "Completed.",
                    "error": "Error during operation.",
                }
                if display_status.startswith("result:"):
                    status_tip = "Test result."
                else:
                    status_tip = tooltip_map.get(display_status, "")
                if conflict_ids:
                    status_tip = lock_reason if not status_tip else f"{status_tip}\n{lock_reason}"
            status_item = QTableWidgetItem("")
            status_item.setData(Qt.UserRole, status_text)
            status_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            status_item.setBackground(self._row_bg_color(r))
            if status_tip:
                status_item.setToolTip(status_tip)
            self.table.setItem(r, 5, status_item)
            status_btn = QPushButton(status_text)
            status_btn.setFocusPolicy(Qt.NoFocus)
            status_btn.setFlat(False)
            status_btn.setProperty("status_button", True)
            status_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            status_btn.setMinimumHeight(TABLE_CONTROL_MIN_HEIGHT)
            status_btn.setCursor(Qt.PointingHandCursor)
            accent_color = "#d32f2f" if conflict_ids else status_color
            status_btn.setStyleSheet(
                self._status_button_stylesheet(
                    status_color,
                    row_dim=row_dim,
                    accent=accent_color,
                )
            )
            if not status_tip and status == "active_external":
                status_tip = "Set outside audioknob (e.g. by distro config or another tool)"
            if status_tip:
                status_btn.setToolTip(status_tip)
            status_btn.setMinimumWidth(0)
            if k.impl and k.impl.kind == "read_only" and k.id != PIPEWIRE_RT_SETUP:
                status_btn.setEnabled(False)
                status_btn.setToolTip("Not applicable for read-only tests")
            else:
                status_btn.clicked.connect(lambda _, kid=k.id: self._show_cli_status(kid))
            reference_match, factory_match = self._preset_match_flags(k.id)
            if tuned_managed_reason or scx_managed_reason:
                reference_match = factory_match = False
            if reference_match or factory_match:
                status_wrap = QWidget()
                status_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                status_wrap.setMinimumHeight(TABLE_CONTROL_MIN_HEIGHT)
                status_wrap.setProperty("table_surface_fill", True)
                wrap_layout = QHBoxLayout(status_wrap)
                wrap_layout.setContentsMargins(0, 0, 0, 0)
                wrap_layout.setSpacing(4)
                wrap_layout.addWidget(status_btn, 1)
                if reference_match:
                    wrap_layout.addWidget(
                        self._preset_dot_widget("#4a90e2", "Matches Reference Preset")
                    )
                if factory_match:
                    wrap_layout.addWidget(
                        self._preset_dot_widget("#2fbf71", "Matches Factory Preset")
                    )
                self._set_status_cell(r, status_wrap)
            else:
                self._set_status_cell(r, status_btn)

            # Column 6: Category
            cat_item = QTableWidgetItem(self._category_label(str(k.category)))
            cat_item.setBackground(self._row_bg_color(r))
            cat_item.setTextAlignment(Qt.AlignCenter)
            if row_dim:
                cat_item.setForeground(locked_fg)
            self.table.setItem(r, 6, cat_item)

            # Column 7: Risk
            risk_item = QTableWidgetItem(str(k.risk_level))
            risk_item.setBackground(self._row_bg_color(r))
            risk_item.setTextAlignment(Qt.AlignCenter)
            if row_dim:
                risk_item.setForeground(locked_fg)
            self.table.setItem(r, 7, risk_item)

            # Column 8: CLI
            sys_item = QTableWidgetItem(self._sys_label_for_knob(k))
            sys_item.setBackground(self._row_bg_color(r))
            if row_dim:
                sys_item.setForeground(locked_fg)
            self.table.setItem(r, 8, sys_item)

            ctx = RowContext(
                row=r,
                status=status,
                busy=busy,
                locked=locked,
                row_dim=row_dim,
                lock_reason=lock_reason,
                not_applicable=not_applicable,
                not_applicable_reason=not_applicable_reason,
                group_pending_lock=group_pending_lock,
                reboot_dep_lock=reboot_dep_lock,
                reboot_gate_lock=reboot_gate_lock,
                advanced_gate_lock=advanced_gate_lock,
                commands_ok=commands_ok,
                missing_cmds=list(missing_cmds),
            )

            # Column 2: Action button (context-sensitive)
            action_priority, action_override = get_action_override(k.id)
            if action_override and action_priority == "pre_lock":
                btn = action_override(self, k, ctx)
                self._set_action_cell(r, btn)
            elif group_pending_lock:
                btn = self._make_action_button("🔒")
                btn.setEnabled(False)
                btn.setToolTip(lock_reason)
                btn.setStyleSheet(locked_style)
                self._set_action_cell(r, btn)
            elif reboot_dep_lock:
                btn = self._make_action_button("🔒")
                btn.setEnabled(False)
                btn.setToolTip(lock_reason)
                btn.setStyleSheet(locked_style)
                self._set_action_cell(r, btn)
            elif not group_ok:
                # Locked: user needs to join groups first
                btn = self._make_action_button("🔒")
                btn.setEnabled(False)
                btn.setToolTip(lock_reason)
                btn.setStyleSheet(locked_style)
                self._set_action_cell(r, btn)
            elif reboot_gate_lock:
                btn = self._make_action_button("🔒")
                btn.setEnabled(False)
                btn.setToolTip(lock_reason)
                btn.setStyleSheet(locked_style)
                self._set_action_cell(r, btn)
            elif advanced_gate_lock:
                btn = self._make_action_button("🔒")
                btn.setEnabled(False)
                btn.setToolTip(lock_reason)
                btn.setStyleSheet(locked_style)
                self._set_action_cell(r, btn)
            elif not commands_ok:
                # Locked: needs package install
                btn = self._make_action_button("Install")
                btn.setToolTip(f"Install: {', '.join(missing_cmds)}")
                cmds = list(missing_cmds)
                btn.setProperty("install_cmds", cmds)
                btn.clicked.connect(lambda _, cmds=cmds: self._on_install_packages(cmds))
                btn.setProperty("baseline_exempt", True)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet(locked_style)
                self._set_action_cell(r, btn)
            elif not_applicable:
                btn = self._make_action_button("N/A")
                btn.setEnabled(False)
                btn.setToolTip(not_applicable_reason)
                btn.setStyleSheet(locked_style)
                self._set_action_cell(r, btn)
            elif dependency_lock:
                btn = self._make_action_button("🔒")
                btn.setEnabled(False)
                btn.setToolTip(lock_reason)
                btn.setStyleSheet(locked_style)
                self._set_action_cell(r, btn)
            elif requires_config:
                btn = self._make_action_button("🔒")
                btn.setEnabled(False)
                btn.setToolTip(lock_reason)
                btn.setStyleSheet(locked_style)
                self._set_action_cell(r, btn)
            elif simple_owned_reason or tuned_managed_reason or scx_managed_reason:
                btn = self._make_action_button("🔒")
                btn.setEnabled(False)
                btn.setToolTip(lock_reason)
                btn.setStyleSheet(locked_style)
                self._set_action_cell(r, btn)
            elif conflict_lock:
                btn = self._make_action_button("Conflict")
                btn.setToolTip(lock_reason)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setStyleSheet(
                    "QPushButton {"
                    " color: #ff8f8f;"
                    " background-color: #2b2124;"
                    " border: 1px solid #92434d;"
                    f" border-radius: {TABLE_CONTROL_BORDER_RADIUS}px;"
                    " padding: 3px 10px;"
                    f" min-height: {TABLE_CONTROL_MIN_HEIGHT}px;"
                    " font-weight: 600;"
                    "}"
                    "QPushButton:hover {"
                    " background-color: #38282c;"
                    " border-color: #c96a76;"
                    "}"
                )
                btn.clicked.connect(lambda _, kid=k.id: self._confirm_conflict_reset(kid))
                self._set_action_cell(r, btn)
            else:
                if action_override and action_priority == "post_lock":
                    btn = action_override(self, k, ctx)
                    self._set_action_cell(r, btn)
                elif k.impl is None:
                    # Placeholder knob - not implemented yet
                    btn = self._make_action_button("—")
                    btn.setEnabled(False)
                    btn.setToolTip("Not implemented yet")
                    self._set_action_cell(r, btn)
                else:
                    # Normal knob: show Apply or Reset based on current status
                    status = self._knob_statuses.get(k.id, "unknown")
                    if status in ("applied", "pending_reboot", "partial", "active_external"):
                        btn = self._make_reset_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "reset"))
                        self._apply_queue_button_state(btn, k.id, "reset", row_dim=row_dim)
                    else:
                        btn = self._make_apply_button()
                        btn.clicked.connect(lambda _, kid=k.id: self._on_queue_knob(kid, "apply"))
                        self._apply_queue_button_state(btn, k.id, "apply", row_dim=row_dim)
                    self._apply_busy_state(btn, busy=busy)
                    self._set_action_cell(r, btn)

            # Column 3: Config widgets
            config_builder = get_config_widget_builder(k.id)
            config_widget = None
            allow_config_row_dim = (
                allow_config_when_row_dim(k.id, ctx)
                and not bool(simple_owned_reason)
                and not bool(tuned_managed_reason)
                and not bool(scx_managed_reason)
            )
            if config_builder:
                config_widget = config_builder(self, k, ctx)
            if config_widget is not None:
                if locked and isinstance(config_widget, QPushButton) and not allow_config_row_dim:
                    config_widget.setEnabled(False)
                    config_widget.setStyleSheet(locked_style)
                self._set_config_cell(r, config_widget)
            else:
                self.table.removeCellWidget(r, 3)
            self._ensure_widget_cell_bg(r, 3)

            if row_dim:
                allow_config = allow_config_row_dim
                for col in range(self.table.columnCount()):
                    cell_widget = self.table.cellWidget(r, col)
                    if cell_widget is None:
                        continue
                    widget = cell_widget
                    if isinstance(widget, CellContainer):
                        content = widget.content_widget()
                        if content is None:
                            continue
                        widget = content
                    if widget.property("status_button"):
                        continue
                    if col == 3 and allow_config:
                        if isinstance(widget, (QComboBox, QPushButton)):
                            continue
                        continue
                    if isinstance(widget, QPushButton):
                        widget.setStyleSheet(locked_style)
                    else:
                        widget.setEnabled(False)
        
        # Keep built-in sorting disabled; we handle per-category sorting.
        self.table.setSortingEnabled(False)
        # Reflow row heights so text/widgets don't clip when font size changes.
        try:
            self.table.resizeRowsToContents()
        except Exception:
            pass
        self._enforce_table_row_heights()
        if hasattr(self, "_update_conflict_indicator"):
            self._update_conflict_indicator()
        if hasattr(self, "_refresh_info_panel_selection"):
            self._refresh_info_panel_selection()

        if v_scroll is not None or h_scroll is not None:
            # Restore on the next tick so Qt's internal scroll adjustments (caused by
            # rebuilding the model/widgets) don't override our intended position.
            def _restore() -> None:
                try:
                    if v_scroll is not None:
                        self.table.verticalScrollBar().setValue(v_scroll)
                    if h_scroll is not None:
                        self.table.horizontalScrollBar().setValue(h_scroll)
                except Exception:
                    pass

            try:
                QTimer.singleShot(0, _restore)
            except Exception:
                _restore()


    def _apply_default_column_widths(self) -> None:
        try:
            from PySide6.QtGui import QFontMetrics
        except Exception:
            return

        fm = QFontMetrics(self.table.font())

        def _w(text: str, pad: int = 24) -> int:
            return fm.horizontalAdvance(text) + pad

        knob_titles = [k.title for k in self.registry] or ["Knob"]
        knob_width = max([_w("Knob")] + [_w(t) for t in knob_titles])

        status_texts = [
            "Locked",
            "✓ Applied",
            "⟳ Reboot",
            "◐ Partial",
            "N/A",
            "⏳ Updating",
            "—",
        ]
        status_width = max([_w("Status")] + [_w(t) for t in status_texts])

        requirements_texts = [
            "Requirements",
            "A",
            "R",
            "G",
            "A R",
            "A G",
            "R G",
            "A R G",
            "—",
        ]
        requirements_width = max(_w(t) for t in requirements_texts)

        category_texts = [str(k.category) for k in self.registry] + ["Category"]
        category_width = max(_w(t) for t in category_texts)

        risk_texts = [str(k.risk_level) for k in self.registry] + ["Risk"]
        risk_width = max(_w(t) for t in risk_texts)

        sys_texts = [self._sys_label_for_knob(k) for k in self.registry] + ["CLI"]
        sys_width = max(_w(t[:24] + ("..." if len(t) > 24 else "")) for t in sys_texts)

        action_texts = ["Apply", "Reset", "Install", "Conflict", "View", "Test", "Scan", "Join", "Leave", "Action"]
        action_width = max(_w(t, pad=40) for t in action_texts)
        action_width = max(action_width, 116)

        config_texts = ["Config", "Cores", "Devices", "44100 Hz", "192000 Hz", "pipewire", "4194304", "1024"]
        config_width = max(_w(t, pad=44) for t in config_texts)
        config_width = max(config_width, 152)

        status_width = max(status_width, _w("Status", pad=72))

        self._min_column_widths = {
            2: action_width,
            3: config_width,
            5: status_width,
        }

        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, max(knob_width, 220))
        self.table.setColumnWidth(2, action_width)
        self.table.setColumnWidth(3, config_width)
        self.table.setColumnWidth(4, requirements_width)
        self.table.setColumnWidth(5, status_width)
        self.table.setColumnWidth(6, max(category_width, 110))
        self.table.setColumnWidth(7, risk_width)
        self.table.setColumnWidth(8, sys_width)
        self._enforce_min_column_widths()
        if hasattr(self, "_update_conflict_indicator"):
            self._update_conflict_indicator()


    def _enforce_min_column_widths(self) -> None:
        header = self.table.horizontalHeader()
        for col, min_w in self._min_column_widths.items():
            if header.sectionSize(col) < min_w:
                header.resizeSection(col, min_w)


    def _on_section_resized(self, logical: int, _old: int, new: int) -> None:
        min_w = self._min_column_widths.get(int(logical))
        if min_w and new < min_w:
            self.table.horizontalHeader().resizeSection(logical, min_w)


    def _on_header_sort(self, column: int) -> None:
        if self._sort_column == column:
            self._sort_descending = not self._sort_descending
        else:
            self._sort_column = column
            self._sort_descending = False
        order = Qt.DescendingOrder if self._sort_descending else Qt.AscendingOrder
        self.table.horizontalHeader().setSortIndicator(column, order)
        self._populate()


    def _on_row_hover(self, row: int, _column: int) -> None:
        if row >= 0:
            self._set_dim_hover_row(row)
            self.table.selectRow(row)


    def eventFilter(self, obj, event):
        if obj is self and event.type() in (QEvent.Leave, QEvent.WindowDeactivate, QEvent.FocusOut):
            self.table.clearSelection()
            self._clear_dim_hover()
            return False
        if obj in (self.table.viewport(), self.table.horizontalHeader(), self.table) and event.type() == QEvent.Leave:
            pos = self.table.mapFromGlobal(QCursor.pos())
            if not self.table.rect().contains(pos):
                self.table.clearSelection()
                self._clear_dim_hover()
            return False
        hover_row = obj.property("hover_row")
        if isinstance(hover_row, int):
            if event.type() in (QEvent.Enter, QEvent.MouseMove):
                self._set_dim_hover_row(hover_row)
                self.table.selectRow(hover_row)
            elif event.type() == QEvent.Leave:
                pos = self.table.mapFromGlobal(QCursor.pos())
                if not self.table.rect().contains(pos):
                    self.table.clearSelection()
                    self._clear_dim_hover()
            return False
        return super().eventFilter(obj, event)


    def _set_dim_hover_row(self, row: int) -> None:
        prev = getattr(self, "_hover_row", None)
        if prev == row:
            return
        if prev is not None:
            self._restore_dim_row(prev)
        self._hover_row = row
        self._clear_dim_row(row)


    def _clear_dim_hover(self) -> None:
        prev = getattr(self, "_hover_row", None)
        if prev is None:
            return
        self._restore_dim_row(prev)
        self._hover_row = None


    def _clear_dim_row(self, row: int) -> None:
        if getattr(self, "_row_dim", None) is None:
            return
        if row >= len(self._row_dim) or not self._row_dim[row]:
            return
        bg = self._row_bg_color(row)
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item is not None:
                item.setBackground(bg)
            widget = self.table.cellWidget(row, col)
            if isinstance(widget, CellContainer):
                widget.set_bg(bg)


    def _restore_dim_row(self, row: int) -> None:
        if getattr(self, "_row_dim", None) is None:
            return
        if row >= len(self._row_dim) or not self._row_dim[row]:
            return
        dim_bg = self._row_bg_color(row)
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item is not None:
                item.setBackground(dim_bg)
            widget = self.table.cellWidget(row, col)
            if isinstance(widget, CellContainer):
                widget.set_bg(dim_bg)
