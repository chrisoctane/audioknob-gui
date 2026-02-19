from __future__ import annotations

import html as html_lib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from audioknob_gui.gui.app_info import _app_title
from audioknob_gui.gui import actions as actions
from audioknob_gui.gui import requirements as requirements
from audioknob_gui.gui import status as status
from audioknob_gui.gui.actions import QueueTaskWorker
from audioknob_gui.gui.logging_utils import _get_gui_logger, _log_gui_audit
from audioknob_gui.gui.state import _state_path, load_state, save_state
from audioknob_gui.gui import simple_mode
from audioknob_gui.gui.system_info import (
    _kernel_cmdline_tokens,
    _kernel_is_rt,
    _param_present,
    _read_interrupts_map,
)
from audioknob_gui.gui.table import TableMixin
from audioknob_gui.gui.worker_api import (
    _PKEXEC_CANCELLED,
    _is_force_reset_error,
    _is_no_transaction_error,
    _registry_path,
    _run_pkexec_command,
    _run_worker_apply_pkexec,
    _run_worker_apply_user,
    _run_worker_history_pkexec,
    _run_worker_history_user,
    _run_worker_restore_many_pkexec,
    _run_worker_restore_many_user,
    _run_worker_restore_pkexec,
    _run_worker_restore_user,
    _worker_log_path,
)
from audioknob_gui.gui.dialogs.confirm import ConfirmDialog
from audioknob_gui.gui.dialogs.jitter_monitor import JitterMonitorDialog
from audioknob_gui.gui.dialogs.tests import jitter_test_summary
from audioknob_gui.gui.dialogs.xrun import XrunMonitorDialog
from audioknob_gui.gui.conflicts import (
    CONFLICT_MAP,
    build_conflict_details,
    filtered_active_conflicts,
    find_conflicts,
    prune_power_profile_conflicts,
)
from audioknob_gui.gui.knobs.registry import (
    InfoHelpers,
    add_info_buttons,
    apply_info_param_overrides,
    build_info_extra_html,
    handle_configure_knob,
)
from audioknob_gui.gui.widgets.numbered_dial import NumberedDial
from audioknob_gui.gui.widgets.no_wheel_combo import ComboWheelGuard
from audioknob_gui.platform.packages import which_command
from audioknob_gui.registry import load_registry

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabBar,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

class MainWindow(TableMixin, QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(_app_title())
        self.resize(980, 640)

        self._task_threads: list[QThread] = []
        self.state = load_state()
        self.registry = load_registry(_registry_path())
        self._knob_preset_matches: dict[str, str] = {}
        self._knob_preset_flags: dict[str, dict[str, bool]] = {}
        build_dep = getattr(self, "_build_dependency_index", None)
        if callable(build_dep):
            self._dependency_index = build_dep()
        else:
            index: dict[str, list[str]] = {}
            for knob in self.registry:
                for dep in getattr(knob, "depends_on", ()):
                    index.setdefault(dep, []).append(knob.id)
            self._dependency_index = index
        self._prune_dependency_conflicts()
        _get_gui_logger().info("gui started")
        self._ensure_system_profile()
        self._baseline_ready = self._baseline_available()
        self._baseline_busy = False
        self._ensure_baseline_state()
        self._queued_actions = self._sanitize_queue_actions(self.state.get("queued_actions"))
        if self._queued_actions != self.state.get("queued_actions"):
            self.state["queued_actions"] = dict(self._queued_actions)
            save_state(self.state)
        self._queue_busy = False
        self._queue_needs_reboot = False
        self._queue_inflight: list[tuple[str, str]] = []
        self._queue_origin = "full"
        self._ui_mode = str(self.state.get("ui_mode", "simple"))
        if self._ui_mode not in ("simple", "full"):
            self._ui_mode = "simple"
        self.state["ui_mode"] = self._ui_mode
        
        # Apply saved font size
        self._apply_font_size(self.state.get("font_size", 11))

        # Apply modern stylesheet
        self._apply_stylesheet()

        w = QWidget()
        self.setCentralWidget(w)
        root = QVBoxLayout(w)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Header
        top = QHBoxLayout()
        self.header_layout = top
        top.setSpacing(6)
        self.btn_view = QPushButton("View")
        self.btn_view.setToolTip("Switch between Basic and Full views")
        self.btn_view.clicked.connect(self._on_toggle_view)
        top.addWidget(self.btn_view)
        top.addSpacing(6)
        self.font_label = QLabel("Font:")
        top.addWidget(self.font_label)
        self.font_spinner = QSpinBox()
        self.font_spinner.setRange(8, 24)
        self.font_spinner.setValue(self.state.get("font_size", 11))
        self.font_spinner.setToolTip("Adjust font size")
        self.font_spinner.valueChanged.connect(self._on_font_change)
        top.addWidget(self.font_spinner)
        top.addSpacing(12)

        # Global reboot-required banner (shown when any knob is pending reboot).
        self.reboot_banner = QLabel("")
        self.reboot_banner.setStyleSheet("color: #f57c00; font-weight: bold;")
        self.reboot_banner.setWordWrap(True)
        self.reboot_banner.setVisible(False)

        top.addStretch(1)

        self.queue_label = QLabel("")
        self.queue_label.setToolTip("Queued changes waiting to apply")
        self.queue_label.setVisible(False)
        top.addWidget(self.queue_label)

        self.btn_apply_queue = QPushButton("Apply")
        self.btn_apply_queue.setToolTip("Apply queued changes")
        self.btn_apply_queue.clicked.connect(
            lambda _checked=False: self._on_apply_queue(reboot_after=False)
        )
        self.btn_apply_queue.setVisible(False)
        top.addWidget(self.btn_apply_queue)

        self.btn_apply_queue_reboot = QPushButton("Apply & Reboot")
        self.btn_apply_queue_reboot.setToolTip("Apply queued changes and reboot after")
        self.btn_apply_queue_reboot.clicked.connect(
            lambda _checked=False: self._on_apply_queue(reboot_after=True)
        )
        self.btn_apply_queue_reboot.setVisible(False)
        top.addWidget(self.btn_apply_queue_reboot)

        self.reboot_button = QPushButton("Reboot")
        self.reboot_button.setToolTip("Restart the system to apply pending changes")
        self.reboot_button.clicked.connect(self._on_reboot_now)
        self.reboot_button.setVisible(False)
        top.addWidget(self.reboot_button)

        self.btn_conflicts = QPushButton("Conflicts")
        self.btn_conflicts.setToolTip("Show detected conflicts")
        self.btn_conflicts.clicked.connect(self._on_show_conflicts)
        self.btn_conflicts.setVisible(True)
        top.addWidget(self.btn_conflicts)

        top.addSpacing(8)

        self.btn_tools_menu = QPushButton("Tools")
        self.btn_tools_menu.setToolTip("Diagnostics, presets, and history")
        tools_menu = QMenu(self.btn_tools_menu)
        self.locks_menu = tools_menu.addMenu("Locks")
        self.act_lock_reboot = self.locks_menu.addAction("Reboot-required changes")
        self.act_lock_reboot.setCheckable(True)
        self.act_lock_reboot.setChecked(bool(self.state.get("enable_reboot_knobs", False)))
        self.act_lock_reboot.setToolTip("Unlock knobs that require a reboot/log-out to take effect")
        self.act_lock_reboot.toggled.connect(self._on_reboot_toggle)
        self.act_lock_advanced = self.locks_menu.addAction("Advanced knobs")
        self.act_lock_advanced.setCheckable(True)
        self.act_lock_advanced.setChecked(bool(self.state.get("advanced_mode_enabled", False)))
        self.act_lock_advanced.setToolTip("Unlock advanced knobs that can impact system performance")
        self.act_lock_advanced.toggled.connect(self._on_advanced_mode_toggle)
        self.act_lock_technical = self.locks_menu.addAction("Technical columns")
        self.act_lock_technical.setCheckable(True)
        self.act_lock_technical.setChecked(bool(self.state.get("show_technical_columns", False)))
        self.act_lock_technical.setToolTip("Show or hide Req/Risk/CLI columns")
        self.act_lock_technical.toggled.connect(self._on_technical_columns_toggle)
        self.locks_menu.addSeparator()
        self.act_release_simple_locks = self.locks_menu.addAction("Release AudioKnob Locks")
        self.act_release_simple_locks.triggered.connect(self._on_release_simple_locks)
        tools_menu.addSeparator()
        self.act_clear_queue = tools_menu.addAction("Clear Queue")
        self.act_clear_queue.triggered.connect(self._on_clear_queue)
        tools_menu.addSeparator()
        self.act_discover_system = tools_menu.addAction("Scan System Profile...")
        self.act_discover_system.triggered.connect(self._on_discover_system)
        self.act_jitter_monitor = tools_menu.addAction("Jitter Monitor...")
        self.act_jitter_monitor.triggered.connect(self.on_open_jitter_monitor)
        self.act_jitter_snapshot = tools_menu.addAction("Jitter Test Snapshot...")
        self.act_jitter_snapshot.triggered.connect(self.on_tests)
        self.act_latencytop = tools_menu.addAction("Latencytop (Terminal)...")
        self.act_latencytop.triggered.connect(self._on_launch_latencytop)
        self.act_cyclictest = tools_menu.addAction("Cyclictest (Terminal)...")
        self.act_cyclictest.triggered.connect(self._on_launch_cyclictest_terminal)
        tools_menu.addSeparator()
        presets_menu = tools_menu.addMenu("Presets")
        baseline_menu = presets_menu.addMenu(status.REFERENCE_PRESET_LABEL)
        self.act_baseline_capture = baseline_menu.addAction(f"Capture {status.REFERENCE_PRESET_LABEL}...")
        self.act_baseline_import = baseline_menu.addAction(f"Import {status.REFERENCE_PRESET_LABEL}...")
        self.act_baseline_export = baseline_menu.addAction(f"Export {status.REFERENCE_PRESET_LABEL}...")
        self.act_baseline_restore = baseline_menu.addAction(f"Queue Restore {status.REFERENCE_PRESET_LABEL}...")
        self.act_baseline_capture.triggered.connect(self._on_capture_baseline)
        self.act_baseline_import.triggered.connect(self._on_import_baseline)
        self.act_baseline_export.triggered.connect(self._on_export_baseline)
        self.act_baseline_restore.triggered.connect(self._on_restore_baseline)
        factory_menu = presets_menu.addMenu(status.FACTORY_PRESET_LABEL)
        self.act_factory_capture = factory_menu.addAction(f"Capture {status.FACTORY_PRESET_LABEL}...")
        self.act_factory_import = factory_menu.addAction(f"Import {status.FACTORY_PRESET_LABEL}...")
        self.act_factory_export = factory_menu.addAction(f"Export {status.FACTORY_PRESET_LABEL}...")
        self.act_factory_restore = factory_menu.addAction(f"Queue Restore {status.FACTORY_PRESET_LABEL}...")
        factory_menu.addSeparator()
        self.act_factory_reset = factory_menu.addAction(f"{status.FACTORY_PRESET_LABEL} (Reset All)...")
        self.act_factory_capture.triggered.connect(self._on_capture_factory)
        self.act_factory_import.triggered.connect(self._on_import_factory)
        self.act_factory_export.triggered.connect(self._on_export_factory)
        self.act_factory_restore.triggered.connect(self._on_restore_factory)
        self.act_factory_reset.triggered.connect(self.on_reset_defaults)
        self._apply_preset_menu_icons(baseline_menu, factory_menu)
        self.act_tx_history = tools_menu.addAction("Tx History...")
        self.act_tx_history.triggered.connect(self._on_show_tx_history)
        self._ensure_menu_width(tools_menu)
        self._ensure_menu_width(self.locks_menu)
        self._ensure_menu_width(presets_menu)
        self._ensure_menu_width(baseline_menu)
        self._ensure_menu_width(factory_menu)
        self.btn_tools_menu.setMenu(tools_menu)
        self._set_baseline_buttons_enabled(not self._baseline_busy)
        top.addWidget(self.btn_tools_menu)

        self.btn_recheck = QPushButton("Re-check State")
        self.btn_recheck.setToolTip("Re-scan current system state")
        self.btn_recheck.clicked.connect(self._on_recheck_state)
        top.addWidget(self.btn_recheck)

        self.btn_logs = QPushButton("Logs")
        self.btn_logs.setToolTip("Open logs for copy/paste")
        self.btn_logs.clicked.connect(self._on_show_logs)
        top.addWidget(self.btn_logs)
        root.addLayout(top)
        root.addWidget(self.reboot_banner)

        self.simple_panel = self._build_simple_panel()
        root.addWidget(self.simple_panel)

        advanced_note = QLabel(
            "Advanced settings can reduce performance in other intensive workloads. "
            "Use Tools -> Locks -> Advanced knobs to make changes; reboot may be required."
        )
        self.advanced_note = advanced_note
        advanced_note.setWordWrap(True)
        root.addWidget(advanced_note)

        self._view_mode = str(self.state.get("view_tab", "all"))
        self.view_tabs = QTabBar()
        self.view_tabs.addTab("Main")
        self.view_tabs.addTab("Cores & IRQ")
        self.view_tabs.addTab("Dev")
        if self._view_mode == "cores":
            self.view_tabs.setCurrentIndex(1)
        elif self._view_mode == "dev":
            self.view_tabs.setCurrentIndex(2)
        else:
            self.view_tabs.setCurrentIndex(0)
        self.view_tabs.currentChanged.connect(self._on_view_tab_changed)
        root.addWidget(self.view_tabs)

        self.cores_panel = self._build_cores_panel()
        root.addWidget(self.cores_panel)
        self._update_cores_panel_visibility()

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["Info", "Knob", "Action", "Config", "Req.", "Status", "Category", "Risk", "CLI"]
        )
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setSortingEnabled(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMouseTracking(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setMinimumSectionSize(60)
        info_header = self.table.horizontalHeaderItem(0)
        if info_header is not None:
            info_header.setToolTip("Show details")
        req_header = self.table.horizontalHeaderItem(4)
        if req_header is not None:
            req_header.setToolTip(self._requirements_key_tooltip())
        # Make every column user-resizable (Interactive). We also set reasonable defaults.
        # NOTE: ResizeToContents does NOT reliably account for cell widgets (buttons/combos),
        # which causes text clipping like "Apply" -> "Annlv".
        for c in range(self.table.columnCount()):
            header.setSectionResizeMode(c, QHeaderView.Interactive)
        self._sort_column: int | None = None
        self._sort_descending = False
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self._on_header_sort)
        header.sectionResized.connect(self._on_section_resized)
        self._min_column_widths: dict[int, int] = {}
        self._apply_default_column_widths()
        self._apply_technical_column_visibility()
        root.addWidget(self.table)

        self._knob_statuses: dict[str, str] = {}
        self._busy_knobs: set[str] = set()
        self._install_busy = False
        self._logs_busy = False
        self._reboot_busy = False
        self._status_busy = False
        self._user_groups: set[str] = set()
        self._refresh_user_groups()
        self._refresh_statuses()
        self._populate()
        self._sync_ui_mode(initial=True)
        QTimer.singleShot(0, self._apply_window_constraints)

        self.table.cellEntered.connect(self._on_row_hover)
        self.table.viewport().installEventFilter(self)
        self.table.horizontalHeader().installEventFilter(self)
        self.table.installEventFilter(self)
        self.installEventFilter(self)

    def _advanced_knob_ids(self) -> set[str]:
        return set(
            [
                "irqbalance_disable",
                "rtirq_enable",
                "irq_pinning",
                "cpu_governor_performance_persistent",
                "power_profile_performance",
                "kernel_threadirqs",
                "kernel_rt_throttling_off",
                "kernel_cstate_limit",
                "kernel_intel_idle_cstate_limit",
                "kernel_audit_off",
                "kernel_mitigations_off",
                "kernel_isolcpus",
                "kernel_nohz_full",
                "kernel_rcu_nocbs",
                "kernel_irqaffinity",
                "kernel_workqueue_cpumask",
                "cgroup_user_slice_allowed_cpus",
                "kernel_preempt_full",
                "kernel_clocksource_tsc",
                "kernel_tsc_reliable",
                "kernel_nmi_watchdog_off",
                "kernel_nosoftlockup",
                "kernel_nosmt",
                "systemd_pipewire_service_rt",
                "systemd_wireplumber_service_rt",
                "irqbalance_banned_cpulist",
                "pipewire_clock_constraints",
                "pipewire_mlock_policy",
                "pipewire_rt_setup",
                "pipewire_data_loop_affinity",
                "wireplumber_alsa_usb_tuning",
                "pipewire_pro_audio_profile",
                "pipewire_pulse_latency",
                "pipewire_pulse_app_rules",
                "pipewire_profiler_enable",
                "rtkit_daemon_tuning",
            ]
        )

    def _dev_knob_ids(self) -> set[str]:
        return {
            "kernel_preempt_full",
            "kernel_clocksource_tsc",
            "kernel_tsc_reliable",
            "kernel_nmi_watchdog_off",
            "kernel_nosoftlockup",
            "kernel_nosmt",
            "kernel_workqueue_cpumask",
            "cgroup_user_slice_allowed_cpus",
            "systemd_pipewire_service_rt",
            "systemd_wireplumber_service_rt",
            "irqbalance_banned_cpulist",
            "pipewire_clock_constraints",
            "pipewire_mlock_policy",
            "pipewire_data_loop_affinity",
            "wireplumber_alsa_usb_tuning",
            "pipewire_pro_audio_profile",
            "pipewire_pulse_latency",
            "pipewire_pulse_app_rules",
            "pipewire_profiler_enable",
            "rtkit_daemon_tuning",
        }

    def _hidden_knob_ids(self) -> set[str]:
        return {
            "pipewire_rt_limits_group",
            "pipewire_rt_module_tuning",
        }

    def _core_knob_ids(self) -> set[str]:
        return {
            "qjackctl_server_prefix_rt",
            "irq_pinning",
            "kernel_rt_throttling_off",
            "kernel_cstate_limit",
            "kernel_intel_idle_cstate_limit",
            "kernel_isolcpus",
            "kernel_nohz_full",
            "kernel_rcu_nocbs",
            "kernel_irqaffinity",
        }

    def _on_view_tab_changed(self, index: int) -> None:
        if index == 1:
            mode = "cores"
        elif index == 2:
            mode = "dev"
        else:
            mode = "all"
        if mode == self._view_mode:
            return
        self._view_mode = mode
        self.state["view_tab"] = mode
        save_state(self.state)
        self._update_cores_panel_visibility()
        self._populate()

    def _update_cores_panel_visibility(self) -> None:
        if hasattr(self, "cores_panel") and self.cores_panel is not None:
            self.cores_panel.setVisible(self._view_mode == "cores")
        self._sync_core_plan_controls()

    def _build_cores_panel(self) -> QWidget:
        from audioknob_gui.platform.detect import get_cpu_count

        cpu_count = get_cpu_count()
        panel = QWidget()
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 0)

        expanded = bool(self.state.get("audio_core_plan_expanded", True))
        header_row = QHBoxLayout()
        self.core_plan_toggle = QToolButton()
        self.core_plan_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.core_plan_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.core_plan_toggle.setText("Audio Core Plan")
        self.core_plan_toggle.setCheckable(True)
        self.core_plan_toggle.setChecked(expanded)
        self.core_plan_toggle.setAutoRaise(True)
        self.core_plan_toggle.toggled.connect(self._on_core_plan_toggle)
        header_row.addWidget(self.core_plan_toggle)
        self.btn_irq_overview = QPushButton("IRQ Overview")
        self.btn_irq_overview.clicked.connect(self._show_irq_overview)
        header_row.addWidget(self.btn_irq_overview)
        header_row.addStretch(1)
        root.addLayout(header_row)

        self.core_plan_body = QWidget()
        body = QVBoxLayout(self.core_plan_body)

        hint = QLabel(
            "Auto-set chooses audio cores and updates per-knob core selections. "
            "With Linked core plan enabled, audio-role and housekeeping-role core knobs stay in sync."
        )
        hint.setWordWrap(True)
        body.addWidget(hint)

        row = QHBoxLayout()
        row.addWidget(QLabel("Audio cores"))
        self.core_plan_count = QSpinBox()
        self.core_plan_count.setRange(1, max(1, int(cpu_count)))
        self.core_plan_count.setValue(int(self.state.get("audio_core_plan_count", 4)))
        self.core_plan_count.valueChanged.connect(self._on_core_plan_count_changed)
        row.addWidget(self.core_plan_count)
        self.btn_core_plan_auto = QPushButton("Auto-set")
        self.btn_core_plan_auto.clicked.connect(self._on_core_plan_auto)
        row.addWidget(self.btn_core_plan_auto)
        row.addStretch(1)
        body.addLayout(row)

        self.core_plan_auto_housekeeping = QCheckBox("Auto housekeeping (invert audio cores)")
        self.core_plan_auto_housekeeping.setChecked(bool(self.state.get("irq_housekeeping_auto", True)))
        self.core_plan_auto_housekeeping.setToolTip(
            "Use IRQ Pinning audio cores to invert the housekeeping set for irqaffinity."
        )
        self.core_plan_auto_housekeeping.toggled.connect(self._on_housekeeping_auto_toggled)
        body.addWidget(self.core_plan_auto_housekeeping)

        self.core_plan_linked = QCheckBox("Linked core plan (recommended)")
        self.core_plan_linked.setChecked(bool(self.state.get("core_plan_linked", True)))
        self.core_plan_linked.setToolTip(
            "Keep all audio-role core knobs on one shared audio core set and "
            "derive housekeeping knobs as the inverse."
        )
        self.core_plan_linked.toggled.connect(self._on_core_plan_linked_toggled)
        body.addWidget(self.core_plan_linked)

        self.core_plan_summary = QLabel("")
        self.core_plan_summary.setWordWrap(True)
        body.addWidget(self.core_plan_summary)

        self.core_plan_body.setVisible(expanded)
        root.addWidget(self.core_plan_body)

        return panel

    def _on_core_plan_toggle(self, expanded: bool) -> None:
        self.state["audio_core_plan_expanded"] = bool(expanded)
        save_state(self.state)
        if hasattr(self, "core_plan_body"):
            self.core_plan_body.setVisible(expanded)
        if hasattr(self, "core_plan_toggle"):
            self.core_plan_toggle.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)

    def _on_core_plan_count_changed(self, value: int) -> None:
        self.state["audio_core_plan_count"] = int(value)
        save_state(self.state)
        self._sync_core_plan_controls()

    def _on_housekeeping_auto_toggled(self, enabled: bool) -> None:
        self.state["irq_housekeeping_auto"] = bool(enabled)
        save_state(self.state)
        self._sync_core_plan_controls()
        status = self._knob_statuses.get("kernel_irqaffinity")
        if status in ("applied", "pending_reboot"):
            _get_gui_logger().info("irq housekeeping mode updated; reapplying")
            self._on_apply_knob("kernel_irqaffinity")
            return
        QMessageBox.information(
            self,
            "Saved",
            "Saved IRQ housekeeping mode. Apply IRQ Housekeeping (irqaffinity) to take effect.",
        )

    def _on_core_plan_linked_toggled(self, enabled: bool) -> None:
        self.state["core_plan_linked"] = bool(enabled)
        if enabled:
            audio_seed = self._core_plan_audio_from_state()
            if audio_seed:
                self._apply_linked_core_plan(source="audio", cores=audio_seed)
        save_state(self.state)
        self._sync_core_plan_controls()
        self._refresh_statuses()
        self._populate()

    def _audio_core_state_keys(self) -> tuple[str, ...]:
        return (
            "irq_pinning_cpu_cores",
            "qjackctl_cpu_cores",
            "kernel_isolcpus_cores",
            "kernel_nohz_full_cores",
            "kernel_rcu_nocbs_cores",
            "irqbalance_banned_cpulist_cores",
        )

    def _housekeeping_core_state_keys(self) -> tuple[str, ...]:
        return (
            "kernel_irqaffinity_cores",
            "kernel_workqueue_cpumask_cores",
            "cgroup_user_slice_allowed_cores",
        )

    def _core_plan_role_for_knob(self, knob_id: str) -> str | None:
        if knob_id in (
            "irq_pinning",
            "qjackctl_server_prefix_rt",
            "kernel_isolcpus",
            "kernel_nohz_full",
            "kernel_rcu_nocbs",
            "irqbalance_banned_cpulist",
        ):
            return "audio"
        if knob_id in (
            "kernel_irqaffinity",
            "kernel_workqueue_cpumask",
            "cgroup_user_slice_allowed_cpus",
        ):
            return "housekeeping"
        return None

    def _cpu_core_universe(self) -> list[int]:
        try:
            from audioknob_gui.core.irq import read_cpu_present

            cores = sorted(read_cpu_present())
            if cores:
                return cores
        except Exception:
            pass
        try:
            from audioknob_gui.platform.detect import get_cpu_count

            count = max(1, int(get_cpu_count()))
        except Exception:
            count = 1
        return list(range(count))

    def _sanitize_core_plan_list(self, cores: list[int] | None) -> list[int]:
        if not isinstance(cores, list):
            return []
        allowed = set(self._cpu_core_universe())
        return sorted({int(core) for core in cores if isinstance(core, int) and int(core) in allowed})

    def _invert_core_selection(self, selected: list[int]) -> list[int]:
        all_cores = set(self._cpu_core_universe())
        return sorted(all_cores - set(selected))

    def _core_plan_audio_from_state(self) -> list[int]:
        for key in self._audio_core_state_keys():
            raw = self.state.get(key)
            if not isinstance(raw, list):
                continue
            cores = self._sanitize_core_plan_list(raw)
            if cores:
                return cores
        for key in self._housekeeping_core_state_keys():
            raw = self.state.get(key)
            if not isinstance(raw, list):
                continue
            housekeeping = self._sanitize_core_plan_list(raw)
            if housekeeping:
                return self._invert_core_selection(housekeeping)
        return self._sanitize_core_plan_list(self._irq_pinning_cpu_cores_from_state() or [])

    def _linked_core_plan_enabled(self) -> bool:
        return bool(self.state.get("core_plan_linked", True))

    def _apply_linked_core_plan(self, *, source: str, cores: list[int]) -> bool:
        if not self._linked_core_plan_enabled():
            return False
        source_norm = str(source).strip().lower()
        if source_norm not in ("audio", "housekeeping"):
            return False
        selected = self._sanitize_core_plan_list(cores)
        if source_norm == "audio":
            audio = selected
            housekeeping = self._invert_core_selection(audio)
        else:
            housekeeping = selected
            audio = self._invert_core_selection(housekeeping)

        changed = False
        for key in self._audio_core_state_keys():
            if self.state.get(key) != audio:
                self.state[key] = list(audio)
                changed = True
        for key in self._housekeeping_core_state_keys():
            if self.state.get(key) != housekeeping:
                self.state[key] = list(housekeeping)
                changed = True
        return changed

    def _suggest_audio_cores(self, count: int) -> list[int]:
        from audioknob_gui.core.irq import (
            is_irq_affinity_writable,
            list_irqs,
            parse_cpu_list,
            read_cpu_present,
            read_irq_effective_affinity_list,
            read_thread_sibling_groups,
        )

        desired = max(1, int(count))
        cores = sorted(read_cpu_present())
        if not cores:
            return []
        scores = {c: 0 for c in cores}
        for irq in list_irqs():
            if is_irq_affinity_writable(irq):
                continue
            raw = read_irq_effective_affinity_list(irq)
            if not raw:
                continue
            for core in parse_cpu_list(raw):
                if core in scores:
                    scores[core] += 1

        groups = read_thread_sibling_groups() or [[c] for c in cores]
        avoid = {0, 1}
        groups_no01 = [g for g in groups if avoid.isdisjoint(g)]
        filtered = False
        if sum(len(g) for g in groups_no01) >= desired:
            groups = groups_no01
            filtered = True

        entries: list[tuple[int, int, list[int]]] = []
        for group in groups:
            group_score = sum(scores.get(c, 0) for c in group)
            entries.append((group_score, min(group), group))
        entries.sort(key=lambda item: (item[0], item[1]))

        selected: set[int] = set()
        for _, _, group in entries:
            selected.update(group)
            if len(selected) >= desired:
                break

        if len(selected) < desired and filtered:
            entries = []
            for group in read_thread_sibling_groups() or [[c] for c in cores]:
                group_score = sum(scores.get(c, 0) for c in group)
                entries.append((group_score, min(group), group))
            entries.sort(key=lambda item: (item[0], item[1]))
            selected.clear()
            for _, _, group in entries:
                selected.update(group)
                if len(selected) >= desired:
                    break

        return sorted(selected)

    def _on_core_plan_auto(self) -> None:
        count = int(self.core_plan_count.value())
        audio_cores = self._suggest_audio_cores(count)
        if not audio_cores:
            QMessageBox.warning(self, "Auto-set", "No audio cores could be selected.")
            return
        audio_cores = sorted(set(audio_cores))
        selected_count = len(audio_cores)
        if self._linked_core_plan_enabled():
            self._apply_linked_core_plan(source="audio", cores=audio_cores)
        else:
            self.state["irq_pinning_cpu_cores"] = audio_cores
            self.state["qjackctl_cpu_cores"] = audio_cores
            self.state["kernel_isolcpus_cores"] = audio_cores
            self.state["kernel_nohz_full_cores"] = audio_cores
            self.state["kernel_rcu_nocbs_cores"] = audio_cores
        self.state["irq_housekeeping_auto"] = True
        save_state(self.state)

        if self._linked_core_plan_enabled():
            affected = [
                "irq_pinning",
                "qjackctl_server_prefix_rt",
                "kernel_isolcpus",
                "kernel_nohz_full",
                "kernel_rcu_nocbs",
                "kernel_irqaffinity",
                "kernel_workqueue_cpumask",
                "cgroup_user_slice_allowed_cpus",
                "irqbalance_banned_cpulist",
            ]
        else:
            affected = [
                "irq_pinning",
                "qjackctl_server_prefix_rt",
                "kernel_isolcpus",
                "kernel_nohz_full",
                "kernel_rcu_nocbs",
                "kernel_irqaffinity",
            ]
        by_id = {k.id: k for k in self.registry}
        queued: list[str] = []
        skipped: list[str] = []
        for kid in affected:
            self._knob_statuses[kid] = "not_applied"
            knob = by_id.get(kid)
            if knob is None:
                continue
            allowed, reason = self._queue_apply_allowed(knob)
            if not allowed:
                if reason:
                    skipped.append(f"{knob.title} ({reason})")
                else:
                    skipped.append(knob.title)
                continue
            if self._queued_actions.get(kid) != "apply":
                self._queued_actions[kid] = "apply"
                queued.append(knob.title)
        self._save_queue()
        self._update_queue_ui()
        self._refresh_statuses()
        self._populate()
        extra = ""
        if selected_count != count:
            extra = (
                f"\n\nRequested {count} cores; selected {selected_count} to keep SMT siblings together."
            )
        if queued:
            extra += "\n\nQueued apply for:\n" + "\n".join(f"- {name}" for name in queued)
        if skipped:
            extra += "\n\nSkipped (locked/unavailable):\n" + "\n".join(f"- {name}" for name in skipped)
        QMessageBox.information(
            self,
            "Auto-set complete",
            "Core selections updated. Apply the queued changes to take effect." + extra,
        )

    def _sync_core_plan_controls(self) -> None:
        auto = bool(self.state.get("irq_housekeeping_auto", True))
        if hasattr(self, "core_plan_auto_housekeeping") and self.core_plan_auto_housekeeping is not None:
            if self.core_plan_auto_housekeeping.isChecked() != auto:
                self.core_plan_auto_housekeeping.blockSignals(True)
                self.core_plan_auto_housekeeping.setChecked(auto)
                self.core_plan_auto_housekeeping.blockSignals(False)
        linked = self._linked_core_plan_enabled()
        if hasattr(self, "core_plan_linked") and self.core_plan_linked is not None:
            if self.core_plan_linked.isChecked() != linked:
                self.core_plan_linked.blockSignals(True)
                self.core_plan_linked.setChecked(linked)
                self.core_plan_linked.blockSignals(False)
        self._refresh_core_plan_summary()

    def _refresh_core_plan_summary(self) -> None:
        if not hasattr(self, "core_plan_summary") or self.core_plan_summary is None:
            return
        try:
            from audioknob_gui.core.irq import read_cpu_present, read_thread_sibling_groups
        except Exception:
            return
        audio = sorted(set(self._core_plan_audio_from_state() or []))
        audio_text = ",".join(str(c) for c in audio) if audio else "unset"
        auto = bool(self.state.get("irq_housekeeping_auto", True))
        if auto:
            housekeeping = sorted(set(self._cpu_core_universe()) - set(audio))
        else:
            housekeeping = sorted(set(self._kernel_cores_from_state("kernel_irqaffinity") or []))
        hk_text = ",".join(str(c) for c in housekeeping) if housekeeping else "unset"
        linked_mode = "on" if self._linked_core_plan_enabled() else "off"
        mode = "auto" if auto else "manual"
        summary = (
            f"Audio cores: {audio_text} | Housekeeping ({mode}): {hk_text} | "
            f"Linked core plan: {linked_mode}"
        )

        groups = read_thread_sibling_groups()
        logical = len(read_cpu_present() or [])
        physical = len(groups)
        smt = any(len(g) > 1 for g in groups)
        if smt and logical:
            summary += f"\nSMT detected: {physical} physical / {logical} logical. Auto-set keeps sibling cores together."
        self.core_plan_summary.setText(summary)

    def _show_irq_overview(self) -> None:
        try:
            from audioknob_gui.core.irq import (
                is_irq_affinity_writable,
                list_irqs,
                parse_cpu_list,
                read_cpu_present,
                read_irq_affinity_list,
                read_irq_effective_affinity_list,
            )
        except Exception as exc:
            QMessageBox.warning(self, "IRQ Overview", f"Failed to load IRQ helpers: {exc}")
            return

        cores = sorted(read_cpu_present())
        audio = sorted(set(self._core_plan_audio_from_state() or []))
        auto = bool(self.state.get("irq_housekeeping_auto", True))
        if auto:
            housekeeping = sorted(set(cores) - set(audio))
        else:
            housekeeping = sorted(set(self._kernel_cores_from_state("kernel_irqaffinity") or []))

        dialog = QDialog(self)
        dialog.setStyleSheet(self.styleSheet())
        dialog.setWindowTitle("IRQ Overview")
        dialog.resize(720, 520)
        layout = QVBoxLayout(dialog)

        overview_font_row = QHBoxLayout()
        overview_font_label = QLabel("Overview font:")
        overview_font_spinner = QSpinBox(dialog)
        overview_font_spinner.setRange(7, 24)
        overview_font_spinner.setValue(max(7, min(24, dialog.font().pointSize() - 1)))
        overview_font_spinner.setToolTip("Adjust font size for IRQ Overview only")
        overview_font_row.addWidget(overview_font_label)
        overview_font_row.addWidget(overview_font_spinner)
        overview_font_row.addStretch(1)
        layout.addLayout(overview_font_row)

        audio_text = ",".join(str(c) for c in audio) if audio else "unset"
        hk_text = ",".join(str(c) for c in housekeeping) if housekeeping else "unset"
        mode = "auto" if auto else "manual"
        summary = QLabel(
            f"Audio cores: {audio_text} | Housekeeping ({mode}): {hk_text}"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        grid_box = QGroupBox("Core map")
        grid_layout = QGridLayout(grid_box)
        grid_layout.setHorizontalSpacing(6)
        grid_layout.setVerticalSpacing(6)
        cols = 8
        base_style = (
            "padding: 4px 6px; border-radius: 3px; background-color: #2b2b2b; color: #e0e0e0;"
        )
        max_core = max(cores) if cores else 0
        core_digits = max(2, len(str(max_core)))
        grid_fm = grid_box.fontMetrics()
        core_cell_w = grid_fm.horizontalAdvance("0" * core_digits) + 18
        core_cell_h = grid_fm.height() + 10
        core_map_labels: list[QLabel] = []
        for idx, core in enumerate(cores):
            label = QLabel(str(core))
            label.setAlignment(Qt.AlignCenter)
            label.setFixedSize(core_cell_w, core_cell_h)
            style = base_style
            if core in housekeeping:
                style += " background-color: #1f4f2b;"
            if core in audio:
                style += " border: 2px solid #4a90e2;"
            label.setStyleSheet(style)
            core_map_labels.append(label)
            grid_layout.addWidget(label, idx // cols, idx % cols)
        layout.addWidget(grid_box)

        legend = QLabel("Legend: green fill = housekeeping cores, blue outline = audio cores.")
        legend.setWordWrap(True)
        layout.addWidget(legend)

        irq_lines = _read_interrupts_map()
        irq_rows: list[tuple[int, str, str, list[str], str]] = []
        max_visible_count_digits = 5

        def _split_irq_counts_and_desc(raw_line: str) -> tuple[list[str], str]:
            text = (raw_line or "").strip()
            if not text:
                return (["0"] * len(cores), "")
            parts = text.split()
            if not parts:
                return (["0"] * len(cores), "")
            count_cols = min(len(parts), len(cores))
            counts = [str(x) for x in parts[:count_cols]]
            if len(counts) < len(cores):
                counts.extend(["0"] * (len(cores) - len(counts)))
            desc = " ".join(parts[count_cols:]).strip()
            return counts, desc

        def _compact_count_text(raw_count: str) -> tuple[str, str | None]:
            text = (raw_count or "0").strip() or "0"
            if len(text) <= max_visible_count_digits:
                return text, None
            return f"{text[:max_visible_count_digits]}…", text

        for irq in list_irqs():
            affinity = read_irq_effective_affinity_list(irq)
            if not affinity:
                affinity = read_irq_affinity_list(irq) or "unknown"
            mode = "RO" if not is_irq_affinity_writable(irq) else "RW"
            counts, desc = _split_irq_counts_and_desc(irq_lines.get(irq, ""))
            irq_rows.append((irq, affinity, mode, counts, desc or "—"))

        table: QTableWidget | None = None
        guide_hint: QLabel | None = None
        desc_col = -1
        if irq_rows:
            class _IrqOverviewTable(QTableWidget):
                def __init__(self, rows: int, cols: int, parent=None) -> None:
                    super().__init__(rows, cols, parent)
                    self._guide_locked = False
                    self._guide_pos: tuple[int, int] | None = None
                    self.setMouseTracking(True)
                    self.viewport().setMouseTracking(True)
                    self._guide_row = QWidget(self.viewport())
                    self._guide_col = QWidget(self.viewport())
                    for guide in (self._guide_row, self._guide_col):
                        guide.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                        guide.setStyleSheet("background-color: rgba(90, 130, 190, 42);")
                        guide.hide()

                def _hide_guide(self) -> None:
                    self._guide_row.hide()
                    self._guide_col.hide()

                def _refresh_guide(self) -> None:
                    if self._guide_pos is None:
                        self._hide_guide()
                        return
                    row, col = self._guide_pos
                    if row < 0 or col < 0 or row >= self.rowCount() or col >= self.columnCount():
                        self._hide_guide()
                        return
                    row_rect = self.visualRect(self.model().index(row, 0))
                    col_rect = self.visualRect(self.model().index(0, col))
                    if (
                        not row_rect.isValid()
                        or row_rect.height() <= 0
                        or not col_rect.isValid()
                        or col_rect.width() <= 0
                    ):
                        self._hide_guide()
                        return
                    vp = self.viewport().rect()
                    self._guide_row.setGeometry(0, row_rect.y(), vp.width(), row_rect.height())
                    self._guide_col.setGeometry(col_rect.x(), 0, col_rect.width(), vp.height())
                    self._guide_row.show()
                    self._guide_col.show()
                    self._guide_row.raise_()
                    self._guide_col.raise_()

                def mouseMoveEvent(self, event) -> None:
                    if not self._guide_locked:
                        idx = self.indexAt(event.pos())
                        self._guide_pos = (idx.row(), idx.column()) if idx.isValid() else None
                        self._refresh_guide()
                    super().mouseMoveEvent(event)

                def leaveEvent(self, event) -> None:
                    if not self._guide_locked:
                        self._guide_pos = None
                        self._hide_guide()
                    super().leaveEvent(event)

                def mousePressEvent(self, event) -> None:
                    if event.button() == Qt.LeftButton:
                        idx = self.indexAt(event.pos())
                        if self._guide_locked:
                            self._guide_locked = False
                            self._guide_pos = (idx.row(), idx.column()) if idx.isValid() else None
                            self._refresh_guide()
                            event.accept()
                            return
                        if idx.isValid():
                            self._guide_locked = True
                            self._guide_pos = (idx.row(), idx.column())
                            self._refresh_guide()
                            event.accept()
                            return
                    super().mousePressEvent(event)

                def scrollContentsBy(self, dx: int, dy: int) -> None:
                    super().scrollContentsBy(dx, dy)
                    self._refresh_guide()

                def resizeEvent(self, event) -> None:
                    super().resizeEvent(event)
                    self._refresh_guide()

            core_headers = [str(core) for core in cores]
            desc_col = 3 + len(core_headers)
            headers = ["IRQ", "Affinity", "Mode", *core_headers, "Description"]
            table = _IrqOverviewTable(len(irq_rows), len(headers), dialog)
            table.setHorizontalHeaderLabels(headers)
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.setSelectionMode(QAbstractItemView.NoSelection)
            table.setFocusPolicy(Qt.NoFocus)
            table.setAlternatingRowColors(True)
            table.setWordWrap(False)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
            table.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
            table.verticalHeader().setMinimumSectionSize(12)

            guide_hint = QLabel("Guide: hover a cell to show a row/column crosshair; click to lock, click again to unlock.")
            guide_hint.setWordWrap(True)
            layout.addWidget(guide_hint)

            for row, (irq, affinity, mode, counts, desc) in enumerate(irq_rows):
                irq_item = QTableWidgetItem(str(irq))
                irq_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(row, 0, irq_item)
                table.setItem(row, 1, QTableWidgetItem(affinity))
                mode_item = QTableWidgetItem(mode)
                mode_item.setTextAlignment(Qt.AlignCenter)
                table.setItem(row, 2, mode_item)
                for idx, value in enumerate(counts):
                    display_value, tooltip_value = _compact_count_text(value)
                    core_item = QTableWidgetItem(display_value)
                    core_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    if tooltip_value:
                        core_item.setToolTip(tooltip_value)
                    table.setItem(row, 3 + idx, core_item)
                table.setItem(row, desc_col, QTableWidgetItem(desc))

            layout.addWidget(table)
        else:
            empty = QLabel("No IRQs found.")
            empty.setWordWrap(True)
            layout.addWidget(empty)

        def _apply_overview_font_size(size: int) -> None:
            point_size = max(7, min(24, int(size)))
            overview_font = dialog.font()
            overview_font.setPointSize(point_size)
            dialog.setFont(overview_font)
            summary.setFont(overview_font)
            grid_box.setFont(overview_font)
            legend.setFont(overview_font)
            overview_font_label.setFont(overview_font)
            overview_font_spinner.setFont(overview_font)
            if guide_hint is not None:
                guide_hint.setFont(overview_font)

            max_core_local = max(cores) if cores else 0
            core_digits_local = max(2, len(str(max_core_local)))
            fm = QFontMetrics(overview_font)
            core_w = fm.horizontalAdvance("0" * core_digits_local) + 18
            core_h = fm.height() + 10
            for label in core_map_labels:
                label.setFont(overview_font)
                label.setFixedSize(core_w, core_h)

            if table is None or desc_col < 0:
                return

            table.setFont(overview_font)
            table.horizontalHeader().setFont(overview_font)
            table_fm = QFontMetrics(overview_font)
            irq_col_w_local = max(
                table_fm.horizontalAdvance("0000") + 14,
                min(
                    140,
                    max(
                        table_fm.horizontalAdvance("IRQ"),
                        max(
                            (
                                table_fm.horizontalAdvance(str(irq))
                                for irq, _aff, _mode, _counts, _desc in irq_rows
                            ),
                            default=0,
                        ),
                    )
                    + 20,
                ),
            )
            aff_col_w_local = max(
                44,
                min(
                    260,
                    max(
                        table_fm.horizontalAdvance("Affinity"),
                        max(
                            (
                                table_fm.horizontalAdvance(aff or "")
                                for _irq, aff, _mode, _counts, _desc in irq_rows
                            ),
                            default=0,
                        ),
                    )
                    + 14,
                ),
            )
            mode_col_w_local = max(
                40,
                min(
                    110,
                    max(
                        table_fm.horizontalAdvance("Mode"),
                        max(
                            (
                                table_fm.horizontalAdvance(mode or "")
                                for _irq, _aff, mode, _counts, _desc in irq_rows
                            ),
                            default=0,
                        ),
                    )
                    + 14,
                ),
            )
            max_count_width_local = max(
                (
                    table_fm.horizontalAdvance(_compact_count_text(value)[0])
                    for _irq, _aff, _mode, counts, _desc in irq_rows
                    for value in counts
                ),
                default=table_fm.horizontalAdvance("0"),
            )
            core_col_w_local = max(
                20,
                min(
                    84,
                    max(
                        table_fm.horizontalAdvance("0"),
                        max_count_width_local,
                        max((table_fm.horizontalAdvance(str(core)) for core in cores), default=0),
                    )
                    + 10,
                ),
            )
            desc_col_w_local = max(
                100,
                min(
                    920,
                    max(
                        table_fm.horizontalAdvance("Description"),
                        max(
                            (
                                table_fm.horizontalAdvance(desc or "")
                                for _irq, _aff, _mode, _counts, desc in irq_rows
                            ),
                            default=0,
                        ),
                    )
                    + 18,
                ),
            )
            header_local = table.horizontalHeader()
            header_local.setMinimumSectionSize(12)
            header_local.setSectionResizeMode(0, QHeaderView.Fixed)
            header_local.setSectionResizeMode(1, QHeaderView.Fixed)
            header_local.setSectionResizeMode(2, QHeaderView.Fixed)
            for core_col in range(3, desc_col):
                header_local.setSectionResizeMode(core_col, QHeaderView.Fixed)
            header_local.setSectionResizeMode(desc_col, QHeaderView.Fixed)
            table.setColumnWidth(0, irq_col_w_local)
            table.setColumnWidth(1, aff_col_w_local)
            table.setColumnWidth(2, mode_col_w_local)
            for core_col in range(3, desc_col):
                table.setColumnWidth(core_col, core_col_w_local)
            table.setColumnWidth(desc_col, desc_col_w_local)
            row_height_local = max(14, table_fm.height() + 4)
            for row in range(table.rowCount()):
                table.setRowHeight(row, row_height_local)
            # Header sections use stylesheet padding, so include extra height to prevent clipping.
            table.horizontalHeader().setFixedHeight(max(22, table_fm.height() + 14))
            table.viewport().update()
            table.update()
            refresh_guide = getattr(table, "_refresh_guide", None)
            if callable(refresh_guide):
                refresh_guide()

        overview_font_spinner.valueChanged.connect(_apply_overview_font_size)
        _apply_overview_font_size(int(overview_font_spinner.value()))

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dialog.reject)
        btns.accepted.connect(dialog.accept)
        layout.addWidget(btns)
        dialog.exec()

    def _smt_hint_line(self) -> str | None:
        try:
            from audioknob_gui.core.irq import read_cpu_present, read_thread_sibling_groups
        except Exception:
            return None
        groups = read_thread_sibling_groups()
        smt = any(len(g) > 1 for g in groups)
        if not smt:
            return None
        logical = len(read_cpu_present() or [])
        physical = len(groups)
        return (
            f"SMT detected: {physical} physical / {logical} logical. "
            "Select both siblings of a physical core for best isolation."
        )

    def _visible_knobs(self) -> list:
        mode = getattr(self, "_view_mode", "all")
        core_ids = self._core_knob_ids()
        dev_ids = self._dev_knob_ids()
        hidden_ids = self._hidden_knob_ids()
        if mode == "cores":
            return [k for k in self.registry if k.id in core_ids and k.id not in hidden_ids]
        if mode == "dev":
            return [k for k in self.registry if k.id in dev_ids and k.id not in hidden_ids]
        return [k for k in self.registry if k.id not in core_ids and k.id not in dev_ids and k.id not in hidden_ids]

    def _build_simple_panel(self) -> QWidget:
        panel = QWidget()
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(10)

        self.simple_title_label = QLabel("AudioKnob")
        self.simple_title_label.setAlignment(Qt.AlignCenter)
        self.simple_title_label.setStyleSheet("font-weight: 700;")
        root.addWidget(self.simple_title_label)

        hint = QLabel(
            "Turn the dial to build the queue. Apply runs the existing pipeline with checks and prompts."
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        root.addWidget(hint)

        content_row = QHBoxLayout()
        content_row.setSpacing(24)
        content_row.setContentsMargins(0, 2, 0, 0)

        self.simple_list_label = QLabel("")
        self.simple_list_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.simple_list_label.setWordWrap(True)
        self.simple_list_label.setTextFormat(Qt.RichText)
        self.simple_list_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.simple_list_label.setMinimumWidth(280)
        content_row.addWidget(self.simple_list_label, 3)

        dial_col = QVBoxLayout()
        dial_col.setSpacing(6)
        self.simple_dial = NumberedDial()
        self.simple_dial.setRange(simple_mode.MIN_LEVEL, simple_mode.MAX_LEVEL)
        self.simple_dial.setValue(simple_mode.clamp_level(self.state.get("simple_level", 1)))
        self._load_simple_dial_center_graphic()
        self.simple_dial.valueChanged.connect(self._on_simple_level_changed)
        self.simple_dial.sliderReleased.connect(self._commit_pending_simple_level)
        dial_col.addWidget(self.simple_dial, alignment=Qt.AlignCenter)

        self._simple_level_pending = simple_mode.clamp_level(self.state.get("simple_level", 1))
        self._simple_level_commit_timer = QTimer(self)
        self._simple_level_commit_timer.setSingleShot(True)
        self._simple_level_commit_timer.setInterval(110)
        self._simple_level_commit_timer.timeout.connect(self._commit_pending_simple_level)

        self.simple_level_label = QLabel("")
        self.simple_level_label.setAlignment(Qt.AlignCenter)
        dial_col.addWidget(self.simple_level_label)

        self.simple_summary_label = QLabel("")
        self.simple_summary_label.setAlignment(Qt.AlignCenter)
        self.simple_summary_label.setWordWrap(True)
        dial_col.addWidget(self.simple_summary_label)
        dial_col.addStretch(1)

        content_row.addLayout(dial_col, 2)
        root.addLayout(content_row)

        return panel

    def _load_simple_dial_center_graphic(self) -> None:
        if not hasattr(self, "simple_dial"):
            return
        configured = str(self.state.get("simple_knob_center_image") or "").strip()
        if configured and self.simple_dial.set_center_image(configured):
            return
        self.simple_dial.clear_center_image()

    def _current_simple_level(self) -> int:
        return simple_mode.clamp_level(self.state.get("simple_level", simple_mode.MIN_LEVEL))

    def _on_simple_level_changed(self, value: int) -> None:
        level = simple_mode.clamp_level(value)
        self._simple_level_pending = level
        if level == 0:
            self.simple_level_label.setText(f"Risk level: 0/{simple_mode.MAX_LEVEL} (Off)")
        else:
            self.simple_level_label.setText(f"Risk level: {level}/{simple_mode.MAX_LEVEL}")
        self.simple_summary_label.setText("Updating queue...")
        if hasattr(self, "_simple_level_commit_timer"):
            self._simple_level_commit_timer.start()
        else:
            self._apply_simple_level(level)

    def _commit_pending_simple_level(self) -> None:
        level = simple_mode.clamp_level(getattr(self, "_simple_level_pending", self._current_simple_level()))
        if hasattr(self, "_simple_level_commit_timer") and self._simple_level_commit_timer.isActive():
            self._simple_level_commit_timer.stop()
        self._apply_simple_level(level)

    def _apply_simple_level(self, level: int) -> None:
        level = simple_mode.clamp_level(level)
        self._simple_level_pending = level
        if hasattr(self, "_simple_level_commit_timer") and self._simple_level_commit_timer.isActive():
            self._simple_level_commit_timer.stop()
        if hasattr(self, "simple_dial"):
            self.simple_dial.blockSignals(True)
            self.simple_dial.setValue(level)
            self.simple_dial.blockSignals(False)
        self.state["simple_level"] = level
        simple_mode.apply_fixed_presets(self.state, level=level)
        queued_actions = self._simple_planned_actions(level)
        self._queued_actions, dropped_non_queue, dropped_applied = self._normalize_simple_queue_actions(
            queued_actions
        )
        if dropped_non_queue or dropped_applied:
            _get_gui_logger().info(
                "simple queue normalized non_queue=%s already_applied=%s",
                ",".join(dropped_non_queue) or "-",
                ",".join(dropped_applied) or "-",
            )
        self._save_queue()
        save_state(self.state)
        self._update_queue_ui()
        self._populate()

    def _simple_planned_actions(self, level: int) -> dict[str, str]:
        backend_is_tuned = self._power_profile_backend_is_tuned()
        return simple_mode.compose_queue_actions(
            level,
            backend_is_tuned=backend_is_tuned,
            managed_knob_ids=self._simple_owned_knob_ids(),
        )

    def _simple_non_queue_knob_ids(self) -> set[str]:
        out: set[str] = set(simple_mode.NON_QUEUE_KNOB_IDS)
        for knob in self.registry:
            if knob.id not in simple_mode.ORDERED_QUEUE_KNOBS:
                continue
            kind = knob.impl.kind if knob.impl is not None else ""
            if kind in ("group_membership", "read_only"):
                out.add(knob.id)
        return out

    def _simple_skip_apply_knob_ids(self) -> set[str]:
        skip: set[str] = set()
        for knob in self.registry:
            if knob.id not in simple_mode.ORDERED_QUEUE_KNOBS:
                continue
            status = self._knob_statuses.get(knob.id, "unknown")
            if status in ("applied", "pending_reboot", "not_applicable"):
                skip.add(knob.id)
                continue
            if not self._knob_commands_ok(knob):
                skip.add(knob.id)
        return skip

    def _simple_excluded_apply_reasons(self, actions: dict[str, str]) -> dict[str, str]:
        non_queue_knob_ids = self._simple_non_queue_knob_ids()
        skip_apply_knob_ids = self._simple_skip_apply_knob_ids()
        reasons: dict[str, str] = {}
        by_id = {k.id: k for k in self.registry}
        for kid, action in actions.items():
            if action != "apply":
                continue
            status = self._knob_statuses.get(kid, "unknown")
            knob = by_id.get(kid)
            if kid in non_queue_knob_ids:
                if status in ("applied", "pending_reboot"):
                    reasons[kid] = "already active"
                elif kid == "audio_group_membership":
                    reasons[kid] = "manual action"
                else:
                    reasons[kid] = "not queued"
                continue
            if knob is not None and not self._knob_commands_ok(knob):
                missing = self._knob_missing_commands(knob)
                if missing:
                    reasons[kid] = f"install: {', '.join(missing)}"
                else:
                    reasons[kid] = "missing commands"
                continue
            if status == "not_applicable":
                reasons[kid] = "not available"
                continue
            if kid in skip_apply_knob_ids:
                reasons[kid] = "already active"
        return reasons

    def _simple_excluded_reset_reasons(self, level: int, actions: dict[str, str]) -> dict[str, str]:
        if level != 0:
            return {}
        reasons: dict[str, str] = {}
        planned_reset = {kid for kid, action in actions.items() if action == "reset"}
        for knob in self.registry:
            kid = knob.id
            if kid not in simple_mode.ORDERED_QUEUE_KNOBS:
                continue
            if kid in planned_reset:
                continue
            status = self._knob_statuses.get(kid, "unknown")
            if kid in simple_mode.NON_QUEUE_KNOB_IDS:
                reasons[kid] = "manual action"
                continue
            if status in ("applied", "pending_reboot", "partial"):
                reasons[kid] = "set outside AudioKnob"
            else:
                reasons[kid] = "already off"
        return reasons

    def _normalize_simple_queue_actions(self, actions: dict[str, str]) -> tuple[dict[str, str], list[str], list[str]]:
        non_queue_knob_ids = self._simple_non_queue_knob_ids()
        skip_apply_knob_ids = self._simple_skip_apply_knob_ids()
        normalized = simple_mode.normalize_queue_actions(
            actions,
            non_queue_knob_ids=non_queue_knob_ids,
            skip_apply_knob_ids=skip_apply_knob_ids,
        )
        dropped_non_queue = sorted(
            kid for kid in actions if kid in non_queue_knob_ids
        )
        dropped_applied = sorted(
            kid
            for kid, action in actions.items()
            if action == "apply" and kid in skip_apply_knob_ids and kid not in non_queue_knob_ids
        )
        return normalized, dropped_non_queue, dropped_applied

    def _simple_display_apply_ids(self, level: int) -> tuple[list[str], dict[str, str]]:
        planned = self._simple_planned_actions(level)
        excluded = self._simple_excluded_apply_reasons(planned)
        ordered = [kid for kid in simple_mode.ORDERED_QUEUE_KNOBS if planned.get(kid) == "apply"]
        extras = [
            kid
            for kid, action in planned.items()
            if action == "apply" and kid not in ordered
        ]
        ordered.extend(sorted(extras))
        return ordered, excluded

    def _simple_display_reset_ids(self, level: int) -> tuple[list[str], dict[str, str]]:
        planned = self._simple_planned_actions(level)
        excluded = self._simple_excluded_reset_reasons(level, planned)
        ordered = [kid for kid in simple_mode.ORDERED_QUEUE_KNOBS if planned.get(kid) == "reset"]
        for kid in simple_mode.ORDERED_QUEUE_KNOBS:
            if kid in excluded and kid not in ordered:
                ordered.append(kid)
        extras = [
            kid
            for kid, action in planned.items()
            if action == "reset" and kid not in ordered
        ]
        ordered.extend(sorted(extras))
        return ordered, excluded

    def _simple_group_prereq_ready(self, queued: list[tuple[str, str]]) -> bool:
        by_id = {k.id: k for k in self.registry}
        apply_knobs = [
            by_id[kid]
            for kid, action in queued
            if action == "apply" and kid in by_id and by_id[kid].requires_groups
        ]
        if not apply_knobs:
            return True

        group_status = self._knob_statuses.get("audio_group_membership", "unknown")
        if group_status == "pending_reboot":
            QMessageBox.information(
                self,
                "Groups Pending Reboot",
                "Audio groups are configured but not active yet.\n\n"
                "Log out/in or reboot, then apply this level again.",
            )
            return False

        missing = [k for k in apply_knobs if not self._knob_group_ok(k)]
        if not missing:
            return True

        titles = sorted({k.title for k in missing})
        msg = (
            "This level includes settings that require audio groups:\n\n"
            + "\n".join(f"• {title}" for title in titles)
            + "\n\nJoin audio groups now?"
        )
        if QMessageBox.question(
            self,
            "Join Audio Groups Required",
            msg,
            QMessageBox.Ok | QMessageBox.Cancel,
        ) == QMessageBox.Ok:
            self._on_join_groups()
        return False

    def _refresh_simple_summary(
        self,
        level: int,
        apply_queue_ids: list[str],
        reset_queue_ids: list[str] | None = None,
        *,
        excluded_apply_reasons: dict[str, str] | None = None,
        excluded_reset_reasons: dict[str, str] | None = None,
    ) -> None:
        by_id = {k.id: k.title for k in self.registry}
        reset_queue_ids = list(reset_queue_ids or [])
        excluded_apply_reasons = dict(excluded_apply_reasons or {})
        excluded_reset_reasons = dict(excluded_reset_reasons or {})
        if level == 0:
            self.simple_level_label.setText(f"Risk level: 0/{simple_mode.MAX_LEVEL} (Off)")
        else:
            self.simple_level_label.setText(f"Risk level: {level}/{simple_mode.MAX_LEVEL}")
        skipped_apply_count = sum(1 for kid in apply_queue_ids if kid in excluded_apply_reasons)
        skipped_reset_count = sum(1 for kid in reset_queue_ids if kid in excluded_reset_reasons)
        apply_count = len(apply_queue_ids) - skipped_apply_count
        reset_count = len(reset_queue_ids) - skipped_reset_count
        total = apply_count + reset_count
        if reset_count:
            summary = (
                f"Queued actions: {total} ({apply_count} apply, {reset_count} reset)"
            )
            skipped_total = skipped_apply_count + skipped_reset_count
            if skipped_total:
                summary += f" • {skipped_total} skipped"
            self.simple_summary_label.setText(summary)
        else:
            summary = f"Queued apply knobs: {apply_count}"
            skipped_total = skipped_apply_count + skipped_reset_count
            if skipped_total:
                summary += f" ({skipped_total} skipped)"
            self.simple_summary_label.setText(summary)
        if apply_queue_ids or reset_queue_ids:
            lines: list[str] = []
            if apply_queue_ids:
                lines.append("<b>Apply queue</b>")
                for kid in apply_queue_ids:
                    title = by_id.get(kid, kid)
                    reason = excluded_apply_reasons.get(kid, "")
                    if reason:
                        lines.append(
                            "<span style='color: #8f8f8f;'>"
                            f"• {html_lib.escape(title)} ({html_lib.escape(reason)})"
                            "</span>"
                        )
                    else:
                        lines.append(f"• {html_lib.escape(title)}")
            if reset_queue_ids:
                if lines:
                    lines.append("")
                lines.append("<b>Reset queue</b>")
                for kid in reset_queue_ids:
                    title = by_id.get(kid, kid)
                    reason = excluded_reset_reasons.get(kid, "")
                    if reason:
                        lines.append(
                            "<span style='color: #8f8f8f;'>"
                            f"• {html_lib.escape(title)} ({html_lib.escape(reason)})"
                            "</span>"
                        )
                    else:
                        lines.append(f"• {html_lib.escape(title)}")
            self.simple_list_label.setText("<br>".join(lines))
        else:
            self.simple_list_label.setText("No settings queued.")

    def _ordered_queue_ids_for_action(self, action: str) -> list[str]:
        ordered = [kid for kid in simple_mode.ORDERED_QUEUE_KNOBS if self._queued_actions.get(kid) == action]
        extras = [
            kid
            for kid, queued_action in self._queued_actions.items()
            if queued_action == action and kid not in ordered
        ]
        ordered.extend(sorted(extras))
        return ordered

    def _on_toggle_view(self) -> None:
        next_mode = "full" if self._ui_mode == "simple" else "simple"
        self._set_ui_mode(next_mode)

    def _set_ui_mode(self, mode: str) -> None:
        mode = str(mode).strip().lower()
        if mode not in ("simple", "full"):
            mode = "simple"
        if mode == self._ui_mode:
            return
        if self._ui_mode == "simple" and mode == "full":
            self._commit_pending_simple_level()
        self._ui_mode = mode
        self.state["ui_mode"] = mode
        save_state(self.state)
        self._sync_ui_mode(initial=False)

    def _sync_ui_mode(self, *, initial: bool) -> None:
        simple = self._ui_mode == "simple"
        if hasattr(self, "simple_panel"):
            self.simple_panel.setVisible(simple)
        if hasattr(self, "advanced_note"):
            self.advanced_note.setVisible(not simple)
        if hasattr(self, "view_tabs"):
            self.view_tabs.setVisible(not simple)
        if hasattr(self, "table"):
            self.table.setVisible(not simple)
        if hasattr(self, "btn_view"):
            self.btn_view.setVisible(True)
            self.btn_view.setToolTip("Switch to Full view" if simple else "Switch to Basic view")
        if hasattr(self, "cores_panel"):
            if simple:
                self.cores_panel.setVisible(False)
            else:
                self._update_cores_panel_visibility()
        if hasattr(self, "act_lock_reboot"):
            self.act_lock_reboot.setVisible(not simple)
        if hasattr(self, "act_lock_advanced"):
            self.act_lock_advanced.setVisible(not simple)
        if hasattr(self, "act_lock_technical"):
            self.act_lock_technical.setVisible(not simple)
        if hasattr(self, "locks_menu"):
            self.locks_menu.menuAction().setVisible(not simple)
        if hasattr(self, "act_release_simple_locks"):
            self.act_release_simple_locks.setEnabled(bool(self._simple_owned_knob_ids()))
        if simple:
            self._apply_simple_level(self._current_simple_level())
        else:
            if not initial:
                self._populate()
            self._update_queue_ui()

    def _simple_owned_knob_ids(self) -> set[str]:
        raw = self.state.get("simple_owned_knobs")
        if not isinstance(raw, list):
            return set()
        allowed = set(simple_mode.SIMPLE_MANAGED_KNOB_IDS)
        return {str(x) for x in raw if isinstance(x, (str, int)) and str(x) in allowed}

    def _set_simple_owned_knob_ids(self, knob_ids: set[str]) -> None:
        allowed = set(simple_mode.SIMPLE_MANAGED_KNOB_IDS)
        filtered = {str(x) for x in knob_ids if str(x) in allowed}
        self.state["simple_owned_knobs"] = sorted(filtered)
        save_state(self.state)
        if hasattr(self, "act_release_simple_locks"):
            self.act_release_simple_locks.setEnabled(bool(filtered))

    def _simple_owned_lock_reason(self, knob_id: str, status: str) -> str:
        if self._ui_mode != "full":
            return ""
        if knob_id not in self._simple_owned_knob_ids():
            return ""
        if status not in ("applied", "pending_reboot", "partial"):
            return ""
        return "Managed by AudioKnob. Use Tools -> Locks -> Release AudioKnob Locks."

    def _on_release_simple_locks(self) -> None:
        owned = self._simple_owned_knob_ids()
        if not owned:
            QMessageBox.information(self, "Release AudioKnob Locks", "No AudioKnob locks are active.")
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Release AudioKnob Locks")
        box.setText("Release managed locks for AudioKnob-applied settings?")
        box.setInformativeText(
            "This only clears lock metadata. It does not apply or reset any system settings."
        )
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Ok)
        if box.exec() != QMessageBox.Ok:
            return
        self._set_simple_owned_knob_ids(set())
        self._populate()

    def _on_clear_queue(self) -> None:
        if self._queue_busy:
            QMessageBox.information(
                self,
                "Clear Queue",
                "Queue is running. Wait for current apply/reset operations to finish.",
            )
            return
        if not self._queued_actions:
            QMessageBox.information(self, "Clear Queue", "Queue is already empty.")
            return
        if QMessageBox.question(self, "Clear Queue", "Clear all queued Apply/Reset actions?") != QMessageBox.Yes:
            return
        self._queued_actions = {}
        if hasattr(self, "_simple_level_commit_timer") and self._simple_level_commit_timer.isActive():
            self._simple_level_commit_timer.stop()
        self._save_queue()
        self._update_queue_ui()
        self._populate()

    def _refresh_user_groups(self) -> None:
        requirements.refresh_user_groups(self)

    def _detect_desktop(self) -> str:
        """Return 'gnome', 'kde', or 'unknown' based on session env vars."""
        raw = " ".join(
            v
            for v in (
                os.environ.get("XDG_CURRENT_DESKTOP", ""),
                os.environ.get("XDG_SESSION_DESKTOP", ""),
                os.environ.get("DESKTOP_SESSION", ""),
            )
            if v
        ).lower()
        if "gnome" in raw or "ubuntu" in raw:
            return "gnome"
        if "kde" in raw or "plasma" in raw:
            return "kde"
        # Fallback: infer from common session processes.
        try:
            ps_cmd = shutil.which("ps")
            if not ps_cmd:
                for candidate in ("/bin/ps", "/usr/bin/ps"):
                    if Path(candidate).exists():
                        ps_cmd = candidate
                        break
            if not ps_cmd:
                return "unknown"
            p = subprocess.run(
                [ps_cmd, "-e", "-o", "comm="],
                capture_output=True,
                text=True,
                timeout=2,
            )
            names = set(p.stdout.split())
            if "gnome-shell" in names or any(n.startswith("gnome-session") for n in names):
                return "gnome"
            if {"plasmashell", "ksmserver", "ksplashqml"} & names or any(n.startswith("plasma") for n in names):
                return "kde"
        except Exception:
            pass
        return "unknown"

    def _knob_group_ok(self, k) -> bool:
        return requirements.knob_group_ok(self, k)

    def _knob_commands_ok(self, k) -> bool:
        return requirements.knob_commands_ok(self, k)

    def _knob_missing_commands(self, k) -> list[str]:
        return requirements.knob_missing_commands(self, k)

    def _queue_apply_allowed(self, k) -> tuple[bool, str]:
        if not self._baseline_ready:
            return False, "Reference preset scan pending"
        status = self._knob_statuses.get(k.id, "unknown")
        simple_lock_reason = self._simple_owned_lock_reason(k.id, status)
        if simple_lock_reason:
            return False, "Managed by AudioKnob"
        if status == "not_applicable":
            return False, "Not available on this system"
        reboot_gate_enabled = bool(self.state.get("enable_reboot_knobs", False))
        advanced_enabled = bool(self.state.get("advanced_mode_enabled", False))
        group_pending = self._knob_statuses.get("audio_group_membership") == "pending_reboot"
        group_ok = self._knob_group_ok(k)
        if group_pending and k.requires_groups:
            group_ok = False
        commands_ok = self._knob_commands_ok(k)
        reboot_gate_lock = (
            bool(k.requires_reboot)
            and not reboot_gate_enabled
            and status not in ("applied", "pending_reboot")
        )
        advanced_gate_lock = (
            k.id in self._advanced_knob_ids()
            and not advanced_enabled
            and status not in ("applied", "pending_reboot")
        )
        reboot_dep_lock = (not reboot_gate_enabled) and bool(k.requires_groups)
        if group_pending:
            return False, f"Groups pending reboot: {', '.join(k.requires_groups)}"
        if reboot_dep_lock:
            return (
                False,
                f"Requires groups: {', '.join(k.requires_groups)} "
                "(Turn on Tools -> Locks -> Reboot-required changes)",
            )
        if not group_ok:
            return False, f"Join groups: {', '.join(k.requires_groups)}"
        if reboot_gate_lock:
            return False, f"Reboot required: {k.title}"
        if advanced_gate_lock:
            return False, "Turn on Tools -> Locks -> Advanced knobs"
        if not commands_ok:
            missing = self._knob_missing_commands(k)
            return False, f"Install: {', '.join(missing)}" if missing else "Missing commands"
        return True, ""

    def _collect_log_text(self) -> str:
        gui_log = _state_path().parent / "logs" / "gui.log"
        user_worker_log = Path(_worker_log_path(is_root=False))
        root_worker_log = Path(_worker_log_path(is_root=True))

        entries: list[tuple[str, str, Path]] = [
            ("GUI log", "GUI", gui_log),
            ("Worker log (user)", "WORKER-USER", user_worker_log),
            ("Worker log (root)", "WORKER-ROOT", root_worker_log),
        ]

        lines: list[str] = []
        for label, tag, path in entries:
            lines.append(f"=== {label} ===")
            lines.append(f"Path: {path}")

            if not path.exists():
                lines.append(f"[{tag}] [not found]")
                lines.append("")
                continue

            if label.endswith("(root)") and not os.access(path, os.R_OK):
                lines.append(f"[{tag}] [not readable: requires root]")
                lines.append("")
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except Exception as exc:
                lines.append(f"[{tag}] [error reading log: {exc}]")
                lines.append("")
                continue

            if content.strip():
                for line in content.rstrip("\n").splitlines():
                    lines.append(f"[{tag}] {line}")
            else:
                lines.append(f"[{tag}] [empty]")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def _on_show_logs(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Logs")
        dialog.resize(720, 520)

        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QTextEdit.NoWrap)
        text.setPlainText(self._collect_log_text())
        layout.addWidget(text)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(text.toPlainText()))
        btn_row.addWidget(copy_btn)
        clear_btn = QPushButton("Clear Logs")
        clear_btn.clicked.connect(lambda: self._on_clear_logs(text, clear_btn))
        btn_row.addWidget(clear_btn)
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        dialog.exec()

    def _on_discover_system(self) -> None:
        dialog = QDialog(self)
        dialog.setStyleSheet(self.styleSheet())
        dialog.setWindowTitle("System Discovery")
        dialog.resize(760, 560)

        layout = QVBoxLayout(dialog)
        summary = QLabel("Running system discovery...")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(text)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        copy_btn = QPushButton("Copy to Clipboard")
        save_btn = QPushButton("Save...")
        close_btn = QPushButton("Close")
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(save_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        current_profile: dict[str, Any] | None = None
        busy = {"scan": False}

        def _format_summary(profile: dict[str, Any] | None) -> str:
            if not profile:
                return "No system profile available."
            distro = profile.get("pretty_name") or profile.get("distro_id") or "unknown"
            boot = profile.get("boot_system") or "unknown"
            scanned = profile.get("scanned_at") or "unknown"
            cmdline = profile.get("paths", {}).get("kernel_cmdline_file", "unknown")
            return f"Distro: {distro} | Boot: {boot} | Cmdline: {cmdline} | Scanned: {scanned}"

        def _update_view(profile: dict[str, Any] | None) -> None:
            nonlocal current_profile
            current_profile = profile
            summary.setText(_format_summary(profile))
            if not profile:
                text.setPlainText("No system profile data.")
                return
            payload = json.dumps(profile, indent=2, sort_keys=True) + "\n"
            text.setPlainText(payload)

        def _run_scan() -> None:
            if busy["scan"]:
                return
            busy["scan"] = True
            refresh_btn.setEnabled(False)
            summary.setText("Running system discovery...")

            def _task() -> tuple[bool, object, str]:
                try:
                    from audioknob_gui.worker.ops import scan_system_profile
                    profile = scan_system_profile(self.registry)
                    return True, profile, ""
                except Exception as exc:
                    return False, {}, str(exc)

            worker = QueueTaskWorker(_task, parent=self)

            def _on_done(success: bool, payload: object, message: str) -> None:
                busy["scan"] = False
                refresh_btn.setEnabled(True)
                if not success or not isinstance(payload, dict):
                    summary.setText("System discovery failed.")
                    QMessageBox.warning(
                        dialog,
                        "System Discovery",
                        message or "System discovery failed.",
                    )
                    return
                self.state["system_profile"] = payload
                save_state(self.state)
                _get_gui_logger().info(
                    "system profile scanned distro=%s boot=%s",
                    payload.get("distro_id"),
                    payload.get("boot_system"),
                )
                _update_view(payload)

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

        def _on_copy() -> None:
            QApplication.clipboard().setText(text.toPlainText())

        def _on_save() -> None:
            if not current_profile:
                QMessageBox.information(dialog, "Save System Profile", "No profile to save yet.")
                return
            base_dir = _state_path().parent
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            default_path = str(base_dir / f"system-profile-{stamp}.json")
            path, _ = QFileDialog.getSaveFileName(
                dialog,
                "Save System Profile",
                default_path,
                "JSON Files (*.json)",
            )
            if not path:
                return
            try:
                payload = json.dumps(current_profile, indent=2, sort_keys=True) + "\n"
                Path(path).write_text(payload, encoding="utf-8")
            except Exception as exc:
                QMessageBox.warning(dialog, "Save System Profile", f"Failed to save:\n{exc}")
                return
            QMessageBox.information(dialog, "Save System Profile", f"Saved to:\n{path}")

        refresh_btn.clicked.connect(_run_scan)
        copy_btn.clicked.connect(_on_copy)
        save_btn.clicked.connect(_on_save)
        close_btn.clicked.connect(dialog.reject)

        existing = self.state.get("system_profile")
        _update_view(existing if isinstance(existing, dict) else None)
        _run_scan()
        dialog.exec()

    def _on_clear_logs(
        self,
        text: QTextEdit | None = None,
        clear_btn: QPushButton | None = None,
    ) -> None:
        if self._logs_busy:
            QMessageBox.information(self, "Clear Logs", "Log clearing is already running.")
            return
        reply = QMessageBox.question(
            self,
            "Clear Logs",
            "Clear GUI, user worker, and root worker logs?\n\nRoot worker log requires pkexec.",
            QMessageBox.Ok | QMessageBox.Cancel,
        )
        if reply != QMessageBox.Ok:
            return
        self._logs_busy = True
        if clear_btn is not None:
            clear_btn.setEnabled(False)

        gui_log = _state_path().parent / "logs" / "gui.log"
        user_worker_log = Path(_worker_log_path(is_root=False))
        root_worker_log = Path(_worker_log_path(is_root=True))

        def _task() -> tuple[bool, object, str]:
            cleared: list[str] = []
            errors: list[str] = []

            for path in (gui_log, user_worker_log):
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("", encoding="utf-8")
                    cleared.append(str(path))
                except Exception as exc:
                    errors.append(f"{path}: {exc}")

            if root_worker_log.exists():
                try:
                    _run_pkexec_command(["truncate", "--size", "0", str(root_worker_log)])
                    cleared.append(str(root_worker_log))
                except Exception as exc:
                    errors.append(f"{root_worker_log}: {exc}")

            payload = {
                "cleared": cleared,
                "errors": errors,
                "root_log": str(root_worker_log) if root_worker_log.exists() else None,
            }
            return True, payload, ""

        worker = QueueTaskWorker(_task, parent=self)

        def _on_done(success: bool, payload: object, message: str) -> None:
            self._logs_busy = False
            if clear_btn is not None:
                clear_btn.setEnabled(True)
            if not isinstance(payload, dict):
                payload = {
                    "cleared": [],
                    "errors": [message or "Log clear failed"],
                    "root_log": str(root_worker_log),
                }
            errors = payload.get("errors") or []
            _log_gui_audit("clear-logs", payload)
            if errors:
                details = "\n".join(str(e) for e in errors)
                QMessageBox.warning(self, "Logs Cleared (with warnings)", details)
            else:
                QMessageBox.information(self, "Logs Cleared", "Logs cleared successfully.")
            if text is not None:
                text.setPlainText(self._collect_log_text())

        worker.finished.connect(_on_done)
        worker.finished.connect(worker.deleteLater)
        self._task_threads.append(worker)
        worker.start()

    def _summarize_effect(self, effect: dict[str, Any]) -> str:
        kind = str(effect.get("kind", ""))
        if kind == "kernel_cmdline":
            param = str(effect.get("param", "")).strip()
            path = str(effect.get("file") or effect.get("path") or "").strip()
            if param and path:
                return f"kernel_cmdline: {param} ({path})"
            if param:
                return f"kernel_cmdline: {param}"
            if path:
                return f"kernel_cmdline ({path})"
            return "kernel_cmdline"
        if kind == "sysfs_write":
            path = str(effect.get("path", "")).strip()
            return f"sysfs_write: {path}" if path else "sysfs_write"
        if kind == "systemd_unit_toggle":
            unit = str(effect.get("unit", "")).strip()
            return f"systemd_unit_toggle: {unit}" if unit else "systemd_unit_toggle"
        if kind == "user_service_mask":
            services = effect.get("services", [])
            units: list[str] = []
            if isinstance(services, list):
                for svc in services:
                    if isinstance(svc, dict):
                        unit = str(svc.get("unit", "")).strip()
                    else:
                        unit = str(svc).strip()
                    if unit:
                        units.append(unit)
            if units:
                suffix = "..." if len(units) > 3 else ""
                return f"user_service_mask: {', '.join(units[:3])}{suffix}"
            return "user_service_mask"
        if kind == "pipewire_restart":
            return "pipewire_restart"
        if kind == "baloo_disable":
            return "baloo_disable"
        if kind == "power_profile":
            backend = str(effect.get("backend", "")).strip()
            before = str(effect.get("before", "")).strip()
            after = str(effect.get("after", "")).strip()
            detail = " -> ".join([x for x in (before, after) if x])
            if backend and detail:
                return f"power_profile: {backend} ({detail})"
            if backend:
                return f"power_profile: {backend}"
            return "power_profile"
        return kind or "effect"

    def _format_tx_preview(self, item: dict[str, Any], titles: dict[str, str]) -> str:
        txid = str(item.get("txid", ""))
        scope = str(item.get("scope", "unknown"))
        ts = item.get("timestamp")
        if isinstance(ts, (int, float)) and ts > 0:
            when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        else:
            when = "-"
        lines = [f"txid: {txid}", f"scope: {scope}", f"time: {when}"]

        applied = item.get("applied") or []
        if isinstance(applied, list) and applied:
            lines.append("")
            lines.append("knobs:")
            for kid in applied:
                if not isinstance(kid, str):
                    continue
                title = titles.get(kid, kid)
                if title and title != kid:
                    lines.append(f"- {title} ({kid})")
                else:
                    lines.append(f"- {kid}")

        backups = item.get("backups") or []
        file_paths: list[str] = []
        if isinstance(backups, list):
            for meta in backups:
                if isinstance(meta, dict):
                    path = meta.get("path")
                    if isinstance(path, str) and path not in file_paths:
                        file_paths.append(path)
        if file_paths:
            lines.append("")
            lines.append("files:")
            for path in file_paths:
                lines.append(f"- {path}")

        effects = item.get("effects") or []
        if isinstance(effects, list) and effects:
            lines.append("")
            lines.append("effects:")
            for effect in effects:
                if isinstance(effect, dict):
                    lines.append(f"- {self._summarize_effect(effect)}")

        return "\n".join(lines)

    def _on_show_tx_history(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Tx History")
        dialog.resize(780, 520)
        layout = QVBoxLayout(dialog)

        baseline_ts = self.state.get("baseline_captured_at") or "-"
        baseline_user = self.state.get("baseline_txid_user") or "-"
        baseline_root = self.state.get("baseline_txid_root") or "-"
        baseline_label = QLabel(
            f"{status.REFERENCE_PRESET_LABEL}: {baseline_ts} (user txid: {baseline_user}, root txid: {baseline_root})"
        )
        layout.addWidget(baseline_label)
        factory_ts = self.state.get("factory_captured_at") or "-"
        factory_source = self.state.get("factory_source") or "-"
        factory_label = QLabel(
            f"{status.FACTORY_PRESET_LABEL}: {factory_ts} (source: {factory_source})"
        )
        layout.addWidget(factory_label)

        table = QTableWidget(0, 8)
        table.setHorizontalHeaderLabels(
            ["TxID", "Scope", "When", "Knobs", "Knob IDs", "Files", "Effects", "Restore"]
        )
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.setTextElideMode(Qt.ElideRight)
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        titles = {k.id: k.title for k in self.registry}

        def _render(items: list[dict[str, Any]]) -> None:
            table.setRowCount(0)
            for row, item in enumerate(items):
                txid = str(item.get("txid", ""))
                scope = str(item.get("scope", "unknown"))
                ts = item.get("timestamp")
                if isinstance(ts, (int, float)) and ts > 0:
                    when = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    when = "-"

                applied = item.get("applied") or []
                applied_names = [
                    titles.get(kid, kid)
                    for kid in applied
                    if isinstance(kid, str)
                ]
                knobs_text = ", ".join(applied_names) if applied_names else "-"
                knob_ids = [
                    kid
                    for kid in applied
                    if isinstance(kid, str)
                ]
                knob_ids_text = ", ".join(knob_ids) if knob_ids else "-"

                backups = item.get("backups") or []
                file_paths = sorted({
                    meta.get("path")
                    for meta in backups
                    if isinstance(meta, dict) and isinstance(meta.get("path"), str)
                })
                files_text = "-"
                if file_paths:
                    sample = file_paths[:2]
                    files_text = ", ".join(sample)
                    if len(file_paths) > 2:
                        files_text += f" (+{len(file_paths) - 2} more)"

                effects = item.get("effects") or []
                effects_text = "-"
                if isinstance(effects, list) and effects:
                    summaries = [
                        self._summarize_effect(effect)
                        for effect in effects
                        if isinstance(effect, dict)
                    ]
                    if summaries:
                        sample = summaries[:2]
                        effects_text = "; ".join(sample)
                        if len(summaries) > 2:
                            effects_text += f" (+{len(summaries) - 2} more)"

                preview = self._format_tx_preview(item, titles)

                table.insertRow(row)
                tx_item = QTableWidgetItem(txid)
                tx_item.setToolTip(preview)
                table.setItem(row, 0, tx_item)
                scope_item = QTableWidgetItem(scope)
                scope_item.setToolTip(preview)
                table.setItem(row, 1, scope_item)
                when_item = QTableWidgetItem(when)
                when_item.setToolTip(preview)
                table.setItem(row, 2, when_item)
                knobs_item = QTableWidgetItem(knobs_text)
                knobs_item.setToolTip(preview)
                table.setItem(row, 3, knobs_item)
                knob_ids_item = QTableWidgetItem(knob_ids_text)
                knob_ids_item.setToolTip(preview)
                table.setItem(row, 4, knob_ids_item)
                files_item = QTableWidgetItem(files_text)
                files_item.setToolTip(preview)
                table.setItem(row, 5, files_item)
                effects_item = QTableWidgetItem(effects_text)
                effects_item.setToolTip(preview)
                table.setItem(row, 6, effects_item)

                restore_btn = QPushButton("Restore")
                restore_btn.setToolTip(preview)

                def _restore(_checked=False, *, tx=txid, sc=scope, details=preview):
                    msg = "Restore this transaction?\n\n" + details
                    if QMessageBox.question(self, "Restore Transaction", msg) != QMessageBox.Yes:
                        return

                    def _task():
                        if sc == "root":
                            result = _run_worker_restore_pkexec(tx)
                        else:
                            result = _run_worker_restore_user(tx)
                        return True, result, ""

                    worker = QueueTaskWorker(_task, parent=self)

                    def _on_done(success: bool, payload: object, message: str) -> None:
                        if not isValid(dialog) or not dialog.isVisible():
                            return
                        if not success:
                            if message == _PKEXEC_CANCELLED:
                                return
                            QMessageBox.warning(
                                dialog,
                                "Restore Failed",
                                message or "Restore failed",
                            )
                            return
                        QMessageBox.information(dialog, "Restore", "Transaction restored.")
                        self._refresh_statuses()
                        _refresh_history()

                    worker.finished.connect(_on_done)
                    worker.finished.connect(worker.deleteLater)
                    self._task_threads.append(worker)
                    worker.start()

                restore_btn.clicked.connect(_restore)
                table.setCellWidget(row, 7, restore_btn)

            table.resizeColumnsToContents()

        def _refresh_history() -> None:
            refresh_btn.setEnabled(False)

            def _task():
                payload = {
                    "user": None,
                    "root": None,
                    "errors": [],
                    "root_cancelled": False,
                }
                try:
                    payload["user"] = _run_worker_history_user()
                except Exception as exc:
                    payload["errors"].append(str(exc))
                try:
                    payload["root"] = _run_worker_history_pkexec()
                except Exception as exc:
                    if str(exc) == _PKEXEC_CANCELLED:
                        payload["root_cancelled"] = True
                    else:
                        payload["errors"].append(str(exc))
                if not payload["user"] and not payload["root"]:
                    return False, payload, "No history data"
                return True, payload, ""

            worker = QueueTaskWorker(_task, parent=self)

            def _on_done(success: bool, payload: object, message: str) -> None:
                if not isValid(dialog) or not dialog.isVisible():
                    return
                refresh_btn.setEnabled(True)
                if not success:
                    QMessageBox.warning(dialog, "Tx History", message or "History load failed")
                    return
                if not isinstance(payload, dict):
                    return
                items: list[dict[str, Any]] = []
                user_data = payload.get("user") or {}
                root_data = payload.get("root") or {}
                for item in user_data.get("items") or []:
                    if isinstance(item, dict):
                        item.setdefault("scope", "user")
                        items.append(item)
                for item in root_data.get("items") or []:
                    if isinstance(item, dict):
                        item.setdefault("scope", "root")
                        items.append(item)
                items.sort(key=lambda i: float(i.get("timestamp") or 0), reverse=True)
                _render(items)
                errors = payload.get("errors") or []
                if errors:
                    details = "\n".join(str(e) for e in errors)
                    QMessageBox.warning(dialog, "Tx History (warnings)", details)

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

        refresh_btn.clicked.connect(_refresh_history)
        _refresh_history()
        dialog.exec()

    def _ensure_system_profile(self) -> None:
        if not self._system_profile_needs_scan():
            return
        self._scan_system_profile()

    def _scan_system_profile(self) -> dict[str, Any] | None:
        try:
            from audioknob_gui.worker.ops import scan_system_profile
            profile = scan_system_profile(self.registry)
            self.state["system_profile"] = profile
            save_state(self.state)
            _get_gui_logger().info(
                "system profile scanned distro=%s boot=%s",
                profile.get("distro_id"),
                profile.get("boot_system"),
            )
            return profile
        except Exception as exc:
            _get_gui_logger().warning("System profile scan failed: %s", exc)
            return None

    def _system_profile_needs_scan(self) -> bool:
        profile = self.state.get("system_profile")
        if not isinstance(profile, dict) or not profile:
            return True
        if profile.get("schema") != 1:
            return True
        try:
            from audioknob_gui.worker.ops import detect_distro
        except Exception:
            return True
        try:
            distro = detect_distro()
        except Exception:
            return True
        if profile.get("distro_id") != distro.distro_id:
            return True
        if profile.get("boot_system") != distro.boot_system:
            return True
        return False

    def _build_dependency_index(self) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for knob in self.registry:
            for dep in getattr(knob, "depends_on", ()):
                index.setdefault(dep, []).append(knob.id)
        return index

    def _prune_dependency_conflicts(self) -> None:
        """A dependency pair cannot also be an interactive conflict pair."""
        removed_pairs = 0
        for knob in self.registry:
            for dep in getattr(knob, "depends_on", ()) or ():
                targets = CONFLICT_MAP.get(knob.id)
                if targets and dep in targets:
                    targets.discard(dep)
                    removed_pairs += 1
                reverse = CONFLICT_MAP.get(dep)
                if reverse and knob.id in reverse:
                    reverse.discard(knob.id)
                    removed_pairs += 1
        if removed_pairs:
            _get_gui_logger().info("pruned dependency conflicts pairs=%s", removed_pairs // 2)

    def _missing_dependencies(self, k) -> list[str]:
        depends = getattr(k, "depends_on", ()) or ()
        if not depends:
            return []
        queued_actions = getattr(self, "_queued_actions", {}) or {}
        missing: list[str] = []
        for dep in depends:
            if queued_actions.get(dep) == "apply":
                continue
            status = self._knob_statuses.get(dep, "unknown")
            if status in ("applied", "pending_reboot"):
                continue
            missing.append(dep)
        return missing

    def _order_apply_ids_by_dependency(self, apply_ids: list[str]) -> list[str]:
        """Topologically order queued apply IDs so dependencies run before dependents."""
        if len(apply_ids) < 2:
            return list(apply_ids)
        ordered: list[str] = []
        seen: set[str] = set()
        for kid in apply_ids:
            if kid not in seen:
                seen.add(kid)
                ordered.append(kid)
        by_id = {k.id: k for k in self.registry}
        apply_set = set(ordered)
        dependents: dict[str, set[str]] = {kid: set() for kid in ordered}
        indegree: dict[str, int] = {kid: 0 for kid in ordered}
        for kid in ordered:
            knob = by_id.get(kid)
            if knob is None:
                continue
            for dep in getattr(knob, "depends_on", ()) or ():
                if dep not in apply_set or dep == kid:
                    continue
                if kid in dependents[dep]:
                    continue
                dependents[dep].add(kid)
                indegree[kid] += 1
        index = {kid: pos for pos, kid in enumerate(ordered)}
        ready = [kid for kid in ordered if indegree[kid] == 0]
        out: list[str] = []
        while ready:
            ready.sort(key=lambda kid: index.get(kid, 0))
            kid = ready.pop(0)
            out.append(kid)
            for child in dependents.get(kid, set()):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if len(out) == len(ordered):
            return out
        # Defensive fallback for unexpected cycles: preserve original relative order.
        remaining = [kid for kid in ordered if kid not in out]
        return out + remaining

    def _collect_dependent_resets(self, knob_ids: list[str]) -> list[str]:
        dependents: list[str] = []
        pending = list(knob_ids)
        seen = set(knob_ids)
        while pending:
            base = pending.pop()
            for child in self._dependency_index.get(base, []):
                if child in seen:
                    continue
                action = self._queued_actions.get(child)
                status = self._knob_statuses.get(child, "unknown")
                if action == "apply" or status in ("applied", "pending_reboot"):
                    dependents.append(child)
                    seen.add(child)
                    pending.append(child)
        return dependents

    def _confirm_dependency_reset(self, reset_ids: list[str]) -> list[str] | None:
        dependents = self._collect_dependent_resets(reset_ids)
        if not dependents:
            return []
        by_id = {k.id: k for k in self.registry}
        reset_titles = [by_id[k].title for k in reset_ids if k in by_id]
        dep_titles = [by_id[k].title for k in dependents if k in by_id]
        msg = (
            "Resetting these knobs will also reset dependent knobs:\n\n"
            + "\n".join(f"- {title}" for title in dep_titles)
            + "\n\nContinue?"
        )
        if reset_titles:
            msg = (
                "Resetting:\n"
                + "\n".join(f"- {title}" for title in reset_titles)
                + "\n\n"
                + msg
            )
        if QMessageBox.question(self, "Reset Dependencies", msg) != QMessageBox.Yes:
            return None
        return dependents

    def _baseline_available(self) -> bool:
        return status.baseline_available(self)

    def _baseline_is_manual(self) -> bool:
        return status.baseline_is_manual(self)

    def _set_baseline_buttons_enabled(self, enabled: bool) -> None:
        status.set_baseline_buttons_enabled(self, enabled)

    def _set_baseline_state(
        self,
        statuses: dict[str, str],
        *,
        checks: dict[str, list[str]] | None = None,
        captured_at: str | None = None,
        source: str = "initial",
    ) -> None:
        status.set_baseline_state(
            self,
            statuses,
            checks=checks,
            captured_at=captured_at,
            source=source,
        )

    def _baseline_snapshot(self) -> dict[str, object]:
        return status.baseline_snapshot(self)

    def _write_baseline_snapshot(self, path: str, snapshot: dict[str, object]) -> bool:
        return status.write_baseline_snapshot(self, path, snapshot)

    def _load_baseline_snapshot(self, path: str) -> dict[str, object] | None:
        return status.load_baseline_snapshot(self, path)

    def _confirm_baseline_overwrite(self, summary: str) -> bool:
        return status.confirm_baseline_overwrite(self, summary)

    def _start_baseline_scan(
        self,
        *,
        on_success: Callable[[dict[str, str]], None],
        on_cancel_title: str = f"{status.REFERENCE_PRESET_LABEL} Required",
        on_cancel_message: str | None = None,
        on_error_title: str = status.REFERENCE_PRESET_LABEL,
        on_error_message: str | None = None,
    ) -> None:
        status.start_baseline_scan(
            self,
            on_success=on_success,
            on_cancel_title=on_cancel_title,
            on_cancel_message=on_cancel_message,
            on_error_title=on_error_title,
            on_error_message=on_error_message,
        )

    def _ensure_baseline_state(self) -> None:
        status.ensure_baseline_state(self)

    def _build_baseline_checks(self, statuses: dict[str, str]) -> dict[str, list[str]]:
        return status.build_baseline_checks(self, statuses)

    def _on_capture_baseline(self) -> None:
        status.on_capture_baseline(self)

    def _on_import_baseline(self) -> None:
        status.on_import_baseline(self)

    def _on_export_baseline(self) -> None:
        status.on_export_baseline(self)

    def _on_restore_baseline(self) -> None:
        status.on_restore_baseline(self)

    def _on_capture_factory(self) -> None:
        status.on_capture_factory(self)

    def _on_import_factory(self) -> None:
        status.on_import_factory(self)

    def _on_export_factory(self) -> None:
        status.on_export_factory(self)

    def _on_restore_factory(self) -> None:
        status.on_restore_factory(self)

    def _sanitize_queue_actions(self, raw: object) -> dict[str, str]:
        if not isinstance(raw, dict):
            return {}
        valid_ids = {k.id for k in self.registry}
        out: dict[str, str] = {}
        for knob_id, action in raw.items():
            if knob_id in valid_ids and action in ("apply", "reset"):
                out[knob_id] = action
        return out

    def _save_queue(self) -> None:
        self.state["queued_actions"] = dict(self._queued_actions)
        save_state(self.state)

    def _queue_requires_reboot(self) -> bool:
        queued = set(self._queued_actions.keys())
        return any(k.requires_reboot for k in self.registry if k.id in queued)

    def _queue_requires_root(self) -> bool:
        queued = set(self._queued_actions.keys())
        return any(k.requires_root for k in self.registry if k.id in queued)

    def _prune_queue_from_statuses(self) -> None:
        status.prune_queue_from_statuses(self)

    def _update_queue_ui(self) -> None:
        count = len(self._queued_actions)
        if count:
            self.queue_label.setText(f"Queued: {count}")
            self.queue_label.setVisible(True)
            tip = "Apply queued changes"
            tip_reboot = "Apply queued changes and reboot after"
            if self._queue_requires_root():
                tip += " (password prompt may appear)"
                tip_reboot += " (password prompt may appear)"
            requires_reboot = self._queue_requires_reboot()
            if requires_reboot:
                tip += " (reboot required to take effect)"
            self.btn_apply_queue.setToolTip(tip)
            self.btn_apply_queue_reboot.setToolTip(tip_reboot)
            self.btn_apply_queue.setVisible(True)
            self.btn_apply_queue_reboot.setVisible(requires_reboot)
        else:
            self.queue_label.setVisible(False)
            self.btn_apply_queue.setVisible(False)
            self.btn_apply_queue_reboot.setVisible(False)
        enabled = count > 0 and not self._queue_busy
        if not self._baseline_ready:
            enabled = False
        self.btn_apply_queue.setEnabled(enabled)
        self.btn_apply_queue_reboot.setEnabled(enabled and self._queue_requires_reboot())
        if self._ui_mode == "simple" and hasattr(self, "simple_list_label"):
            ordered_apply, excluded_apply_reasons = self._simple_display_apply_ids(self._current_simple_level())
            ordered_reset, excluded_reset_reasons = self._simple_display_reset_ids(self._current_simple_level())
            self._refresh_simple_summary(
                self._current_simple_level(),
                ordered_apply,
                ordered_reset,
                excluded_apply_reasons=excluded_apply_reasons,
                excluded_reset_reasons=excluded_reset_reasons,
            )

    def _apply_queue_button_state(
        self, btn: QPushButton, knob_id: str, action: str, *, row_dim: bool = False
    ) -> None:
        if self._queued_actions.get(knob_id) == action:
            btn.setStyleSheet(
                "QPushButton {"
                " background-color: #5f8f6b;"
                " color: #e0e0e0;"
                " border: 1px solid #6b9a76;"
                "}"
                "QPushButton:hover {"
                " background-color: #699a76;"
                "}"
                "QPushButton:pressed {"
                " background-color: #4e7a5a;"
                "}"
            )
            tip = "Queued to apply. Click to remove from queue."
            if action == "reset":
                tip = "Queued to reset. Click to remove from queue."
            btn.setToolTip(tip)
        else:
            self._style_table_button(btn, row_dim=row_dim)

    def _on_recheck_state(self) -> None:
        status.on_recheck_state(self)

    def _refresh_statuses(self) -> None:
        status.refresh_statuses(self)

    def _apply_session_dependent_statuses(self) -> None:
        status.apply_session_dependent_statuses(self)

    def _apply_baseline_statuses(self) -> None:
        status.apply_baseline_statuses(self)

    def _rt_limits_active(self) -> bool:
        return status.rt_limits_active(self)

    def _audio_groups_active(self) -> bool:
        return status.audio_groups_active(self)

    def _is_process_running(self, names: list[str]) -> bool:
        if shutil.which("pgrep"):
            for name in names:
                r = subprocess.run(["pgrep", "-x", name], capture_output=True, text=True)
                if r.returncode == 0:
                    return True
        r = subprocess.run(["ps", "-eo", "comm"], capture_output=True, text=True)
        if r.returncode != 0:
            return False
        for line in r.stdout.splitlines():
            cmd = line.strip()
            if cmd in names:
                return True
        return False

    def _prime_qjackctl_preset(self) -> None:
        logger = _get_gui_logger()
        path = Path("~/.config/rncbc.org/QjackCtl.conf").expanduser()
        if path.exists():
            return
        logger.info("qjackctl config missing; will be created on apply")

    def _update_reboot_banner(self) -> None:
        needs_reboot = any(v == "pending_reboot" for v in self._knob_statuses.values())
        self._needs_reboot = needs_reboot
        self.reboot_banner.setText("Reboot required for pending changes." if needs_reboot else "")
        self.reboot_banner.setVisible(needs_reboot)
        self.reboot_button.setVisible(needs_reboot)
        self.reboot_button.setEnabled(needs_reboot)

    def _apply_font_size(self, size: int) -> None:
        """Apply font size to the application."""
        font = QApplication.instance().font()
        font.setPointSize(size)
        QApplication.instance().setFont(font)
        # Force-propagate the font to all existing widgets.
        # (On some platforms/styles, changing QApplication font alone misses already-built widgets.)
        try:
            self.setFont(font)
            for widget in self.findChildren(QWidget):
                widget.setFont(font)
            for r in range(self.table.rowCount()):
                for c in range(self.table.columnCount()):
                    it = self.table.item(r, c)
                    if it is not None:
                        it.setFont(font)
                    w = self.table.cellWidget(r, c)
                    if w is not None:
                        w.setFont(font)

            # Reflow rows so widgets/text don't clip at larger font sizes.
            self._apply_default_column_widths()
            self.table.resizeRowsToContents()
            self.table.viewport().update()
            self._apply_window_constraints()
        except Exception:
            pass

    def _apply_window_constraints(self) -> None:
        """Allow resizing up to the available screen size."""
        try:
            from PySide6.QtGui import QGuiApplication

            screen = QGuiApplication.primaryScreen()
            avail = screen.availableGeometry() if screen else None
            if not avail:
                return
            self.setMaximumSize(avail.width(), avail.height())
        except Exception:
            return

    def _apply_stylesheet(self) -> None:
        """Apply clean dark theme."""
        self.setStyleSheet("""
            QMainWindow, QDialog {
                background-color: #1f1f1f;
                color: #e0e0e0;
            }
            QWidget {
                color: #e0e0e0;
            }
            QTableWidget {
                background-color: #1f1f1f;
                alternate-background-color: #353535;
                gridline-color: #1f1f1f;
                border: 1px solid #1f1f1f;
            }
            QTableWidget::item {
                background-color: #2f2f2f;
                padding: 4px;
                font-weight: normal;
            }
            QTableWidget::item:alternate {
                background-color: #353535;
            }
            QTableWidget::item:disabled {
                background-color: #1f1f1f;
                color: #cfcfcf;
            }
            QTableWidget::item:selected {
                background-color: #46525d;
                color: #e0e0e0;
            }
            QHeaderView::section {
                background-color: #1f1f1f;
                color: #e0e0e0;
                padding: 6px;
                font-weight: normal;
                border: none;
                border-bottom: 1px solid #2a2a2a;
            }
            QHeaderView {
                background-color: #1f1f1f;
            }
            QTableCornerButton::section {
                background-color: #1f1f1f;
                border: 1px solid #1f1f1f;
            }
            QTabBar::tab {
                background-color: #2b2b2b;
                color: #cfcfcf;
                padding: 6px 10px;
                border: 1px solid #1f1f1f;
                border-bottom: none;
            }
            QTabBar::tab:selected {
                background-color: #353535;
                color: #e0e0e0;
            }
            QTabBar::tab:!selected {
                margin-top: 2px;
            }
            QTextEdit, QPlainTextEdit, QLineEdit, QAbstractScrollArea {
                background-color: #1f1f1f;
                color: #e0e0e0;
                border: 1px solid #2a2a2a;
            }
            QLineEdit {
                selection-background-color: #333333;
                selection-color: #e0e0e0;
            }
            QScrollArea {
                background-color: #1f1f1f;
            }
            QAbstractScrollArea::viewport {
                background-color: #1f1f1f;
            }
            QGroupBox {
                background-color: #1f1f1f;
                border: 1px solid #2a2a2a;
                margin-top: 8px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                color: #cfcfcf;
            }
            QMenu {
                background-color: #1f1f1f;
                color: #e0e0e0;
                border: 1px solid #2a2a2a;
            }
            QMenu::item {
                background-color: #1f1f1f;
                padding: 4px 10px;
            }
            QMenu::item:selected {
                background-color: #333333;
            }
            QMenu::separator {
                height: 1px;
                background: #2a2a2a;
                margin: 4px 0;
            }
            QPushButton, QToolButton {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #1f1f1f;
                padding: 2px 6px;
                border-radius: 6px;
            }
            QPushButton:hover, QToolButton:hover {
                background-color: #333333;
            }
            QPushButton:pressed, QToolButton:pressed {
                background-color: #1f1f1f;
            }
            QPushButton:disabled, QToolButton:disabled {
                background-color: #1f1f1f;
                color: #7a7a7a;
                border: 1px solid #2a2a2a;
            }
            QToolButton:checked {
                background-color: #2a2a2a;
            }
            QToolButton:checked:hover {
                background-color: #333333;
            }
            QToolButton:focus {
                outline: none;
            }
            QAbstractSpinBox {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #1f1f1f;
                padding: 2px 6px;
                border-radius: 6px;
                selection-background-color: #333333;
                selection-color: #e0e0e0;
            }
            QAbstractSpinBox:disabled {
                background-color: #1f1f1f;
                color: #7a7a7a;
                border: 1px solid #2a2a2a;
            }
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                border: 1px solid #1f1f1f;
                background-color: #2a2a2a;
            }
            QComboBox, QSpinBox {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #1f1f1f;
                padding: 2px 6px;
                border-radius: 6px;
            }
            QComboBox:disabled, QSpinBox:disabled {
                background-color: #1f1f1f;
                color: #7a7a7a;
                border: 1px solid #2a2a2a;
            }
            QComboBox::drop-down, QSpinBox::up-button, QSpinBox::down-button {
                border: 1px solid #1f1f1f;
                background-color: #2a2a2a;
            }
            QComboBox QLineEdit, QSpinBox QLineEdit {
                background-color: #2a2a2a;
                selection-background-color: #333333;
                selection-color: #e0e0e0;
            }
            QComboBox QAbstractItemView {
                background-color: #2a2a2a;
                color: #e0e0e0;
                selection-background-color: #333333;
            }
            QCheckBox {
                color: #e0e0e0;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #2a2a2a;
                background-color: #1f1f1f;
            }
            QCheckBox::indicator:checked {
                background-color: #2f2f2f;
                border: 1px solid #6a6a6a;
                image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 14 14'><path d='M3 7l2 2 6-6' stroke='%23e0e0e0' stroke-width='2' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>");
            }
            QScrollBar:vertical {
                background-color: #333333;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background-color: #555555;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background-color: #333333;
            }
            QScrollBar:horizontal {
                background-color: #333333;
                height: 10px;
            }
            QScrollBar::handle:horizontal {
                background-color: #555555;
                min-width: 20px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background-color: #333333;
            }
        """)

    def _on_font_change(self, size: int) -> None:
        """Handle font size change from spinner."""
        self._apply_font_size(size)
        self.state["font_size"] = size
        save_state(self.state)

    def _on_reboot_toggle(self, enabled: bool) -> None:
        """Handle reboot-required knob toggle."""
        self.state["enable_reboot_knobs"] = bool(enabled)
        save_state(self.state)
        v_scroll = None
        try:
            v_scroll = self.table.verticalScrollBar().value()
            self.table.clearSelection()
            self._clear_dim_hover()
        except Exception:
            v_scroll = None
        self._populate()
        if v_scroll is not None:
            try:
                self.table.verticalScrollBar().setValue(v_scroll)
            except Exception:
                pass

    def _on_reboot_now(self, *, force: bool = False) -> None:
        if not force and not getattr(self, "_needs_reboot", False):
            return
        if self._reboot_busy:
            return
        msg = (
            "Restart now to apply pending changes?\n\n"
            "Unsaved work in other apps may be lost."
        )
        if QMessageBox.question(self, "Reboot", msg) != QMessageBox.Yes:
            return
        self._reboot_busy = True
        self.reboot_button.setEnabled(False)

        def _task() -> tuple[bool, object, str]:
            try:
                _run_pkexec_command(["systemctl", "reboot"])
            except Exception as e:
                return False, {}, str(e)
            return True, {}, ""

        worker = QueueTaskWorker(_task, parent=self)

        def _on_done(success: bool, payload: object, message: str) -> None:
            self._reboot_busy = False
            self.reboot_button.setEnabled(True)
            if not success and message != _PKEXEC_CANCELLED:
                QMessageBox.warning(self, "Reboot Failed", message or "Reboot failed")

        worker.finished.connect(_on_done)
        worker.finished.connect(worker.deleteLater)
        self._task_threads.append(worker)
        worker.start()

    def _qjackctl_cpu_cores_from_state(self) -> list[int] | None:
        raw = self.state.get("qjackctl_cpu_cores")
        if raw is None:
            return None
        if isinstance(raw, list) and all(isinstance(x, int) for x in raw):
            return [int(x) for x in raw]
        return None

    def _pipewire_quantum_from_state(self) -> int | None:
        raw = self.state.get("pipewire_quantum")
        if raw is None:
            return None
        try:
            v = int(raw)
        except Exception:
            return None
        if v in (32, 64, 128, 256, 512, 1024):
            return v
        return None

    def _pipewire_sample_rate_from_state(self) -> int | None:
        raw = self.state.get("pipewire_sample_rate")
        if raw is None:
            return None
        try:
            v = int(raw)
        except Exception:
            return None
        if v in (44100, 48000, 88200, 96000, 192000):
            return v
        return None

    def _power_profile_backend_from_state(self) -> str:
        raw = str(self.state.get("power_profile_backend") or "").strip().lower()
        if raw in ("powerprofilesctl", "tuned"):
            return raw
        return "auto"

    def _tuned_conflict_ids(self) -> list[str]:
        return [
            "cpu_governor_performance_persistent",
            "kernel_cstate_limit",
            "kernel_intel_idle_cstate_limit",
        ]

    def _irq_pinning_devices_from_state(self) -> list[str]:
        raw = self.state.get("irq_pinning_devices")
        if not isinstance(raw, list):
            return []
        return [str(x) for x in raw if isinstance(x, (str, int)) and str(x).strip()]

    def _irq_pinning_cpu_cores_from_state(self) -> list[int] | None:
        raw = self.state.get("irq_pinning_cpu_cores")
        if raw is None:
            return None
        if isinstance(raw, list) and all(isinstance(x, int) for x in raw):
            return [int(x) for x in raw]
        return None

    def _kernel_core_key(self, knob_id: str) -> str | None:
        mapping = {
            "kernel_isolcpus": "kernel_isolcpus_cores",
            "kernel_nohz_full": "kernel_nohz_full_cores",
            "kernel_rcu_nocbs": "kernel_rcu_nocbs_cores",
            "kernel_irqaffinity": "kernel_irqaffinity_cores",
            "kernel_workqueue_cpumask": "kernel_workqueue_cpumask_cores",
            "cgroup_user_slice_allowed_cpus": "cgroup_user_slice_allowed_cores",
            "irqbalance_banned_cpulist": "irqbalance_banned_cpulist_cores",
        }
        return mapping.get(knob_id)

    def _kernel_cores_from_state(self, knob_id: str) -> list[int] | None:
        key = self._kernel_core_key(knob_id)
        if not key:
            return None
        raw = self.state.get(key)
        if raw is None:
            return None
        if isinstance(raw, list) and all(isinstance(x, int) for x in raw):
            return [int(x) for x in raw]
        return None

    def _kernel_cmdline_param_for_state(self, knob_id: str) -> str | None:
        key = self._kernel_core_key(knob_id)
        if not key:
            return None
        cores = None
        if knob_id == "kernel_irqaffinity" and self.state.get("irq_housekeeping_auto", True):
            try:
                from audioknob_gui.core.irq import cpu_list_from_cores, read_cpu_present
            except Exception:
                return None
            audio = set(self._core_plan_audio_from_state() or [])
            housekeeping = read_cpu_present() - audio
            if not housekeeping:
                return None
            cpu_list = cpu_list_from_cores(sorted(housekeeping))
        else:
            cores = self._kernel_cores_from_state(knob_id)
            if not cores:
                return None
            try:
                from audioknob_gui.core.irq import cpu_list_from_cores
            except Exception:
                return None
            cpu_list = cpu_list_from_cores(cores)
        if not cpu_list:
            return None
        prefixes = {
            "kernel_isolcpus": "isolcpus",
            "kernel_nohz_full": "nohz_full",
            "kernel_rcu_nocbs": "rcu_nocbs",
            "kernel_irqaffinity": "irqaffinity",
        }
        prefix = prefixes.get(knob_id)
        if not prefix:
            return None
        return f"{prefix}={cpu_list}"

    def on_configure_knob(self, knob_id: str) -> None:
        if handle_configure_knob(self, knob_id):
            self._update_queue_ui()
            self._populate()
        return

    def on_tests(self) -> None:
        headline, detail, payload = jitter_test_summary(duration_s=5, use_pkexec=True)
        self.state["jitter_test_last"] = payload
        save_state(self.state)
        QMessageBox.information(self, headline, detail)

    def on_run_test(self, knob_id: str, *, refresh_dialog=None) -> None:
        """Run a test and update the status column with results."""
        if knob_id == "scheduler_jitter_test":
            if knob_id in self._busy_knobs:
                return
            if refresh_dialog is not None and isValid(refresh_dialog):
                refresh_dialog.accept()
            self._busy_knobs.add(knob_id)
            # Show a brief "running" indicator
            self._update_knob_status(knob_id, "running", "⏳ Running...")
            self._populate()

            def _task() -> tuple[bool, object, str]:
                headline, detail, payload = jitter_test_summary(duration_s=5, use_pkexec=False)
                return True, {"headline": headline, "detail": detail, "payload": payload}, ""

            worker = QueueTaskWorker(_task, parent=self)

            def _on_done(success: bool, payload: object, message: str) -> None:
                self._busy_knobs.discard(knob_id)
                if not success or not isinstance(payload, dict):
                    self._knob_statuses[knob_id] = "error"
                    self._populate()
                    QMessageBox.warning(self, "Jitter Test Failed", message or "Jitter test failed")
                    return

                detail = str(payload.get("detail", ""))
                result = payload.get("payload")
                if isinstance(result, dict):
                    self.state["jitter_test_last"] = result
                    save_state(self.state)
                    max_us = result.get("max_us")
                    if isinstance(max_us, int):
                        self._knob_statuses[knob_id] = f"result:{max_us} µs"
                    else:
                        self._knob_statuses[knob_id] = "error"
                        QMessageBox.warning(self, "Jitter Test Failed", detail or "No results")
                else:
                    self._knob_statuses[knob_id] = "error"
                    QMessageBox.warning(self, "Jitter Test Failed", detail or "No results")

                self._populate()
                if refresh_dialog is not None:
                    self._show_knob_info(knob_id)

            worker.finished.connect(_on_done)
            worker.finished.connect(worker.deleteLater)
            self._task_threads.append(worker)
            worker.start()

    def on_open_xrun_monitor(self) -> None:
        dialog = getattr(self, "_xrun_dialog", None)
        if dialog is not None and isValid(dialog):
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return
        dialog = XrunMonitorDialog(parent=self)
        dialog.setModal(False)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.finished.connect(lambda _=None: setattr(self, "_xrun_dialog", None))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._xrun_dialog = dialog

    def on_open_jitter_monitor(self) -> None:
        dialog = getattr(self, "_jitter_dialog", None)
        if dialog is not None and isValid(dialog):
            dialog.show()
            dialog.raise_()
            dialog.activateWindow()
            return
        dialog = JitterMonitorDialog(parent=self)
        dialog.setModal(False)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        dialog.finished.connect(lambda _=None: setattr(self, "_jitter_dialog", None))
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._jitter_dialog = dialog

    def _stop_monitor_dialog(self, dialog: object | None) -> None:
        if dialog is None:
            return

        # Ensure modeless monitor dialogs stop polling when closed/hidden.
        stop = getattr(dialog, "_stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                pass

        timer = getattr(dialog, "_timer", None)
        stop_timer = getattr(timer, "stop", None)
        if callable(stop_timer):
            try:
                stop_timer()
            except Exception:
                pass

        if hasattr(dialog, "_running"):
            try:
                setattr(dialog, "_running", False)
            except Exception:
                pass

    def closeEvent(self, event) -> None:
        for attr_name in ("_xrun_dialog", "_jitter_dialog"):
            dialog = getattr(self, attr_name, None)
            if dialog is None:
                continue
            try:
                if isValid(dialog):
                    self._stop_monitor_dialog(dialog)
                    dialog.close()
            except Exception:
                pass
            setattr(self, attr_name, None)
        super().closeEvent(event)

    def _launch_in_terminal(self, command: list[str]) -> bool:
        candidates: list[tuple[str, list[str]]] = [
            ("x-terminal-emulator", ["-e"]),
            ("gnome-terminal", ["--"]),
            ("konsole", ["-e"]),
            ("xterm", ["-e"]),
            ("alacritty", ["-e"]),
            ("kitty", ["-e"]),
            ("wezterm", ["start", "--"]),
        ]
        for exe, prefix in candidates:
            path = shutil.which(exe)
            if not path:
                continue
            try:
                subprocess.Popen(
                    [path, *prefix, *command],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
            except Exception:
                continue
        return False

    def _on_launch_latencytop(self) -> None:
        latencytop = which_command("latencytop")
        if not latencytop:
            QMessageBox.warning(
                self,
                "Latencytop not found",
                "latencytop is not installed. Install the 'latencytop' package and try again.",
            )
            return
        if not self._launch_in_terminal([latencytop]):
            QMessageBox.warning(
                self,
                "No terminal available",
                "Could not find a terminal emulator to launch latencytop.",
            )

    def _on_launch_cyclictest_terminal(self) -> None:
        cyclictest = which_command("cyclictest")
        if not cyclictest:
            QMessageBox.warning(
                self,
                "cyclictest not found",
                "cyclictest is not installed. Install the 'cyclictest' package and try again.",
            )
            return
        if not self._launch_in_terminal([cyclictest]):
            QMessageBox.warning(
                self,
                "No terminal available",
                "Could not find a terminal emulator to launch cyclictest.",
            )

    def _collect_conflict_pairs(self) -> list[tuple[str, str]]:
        if not hasattr(self, "_knob_statuses"):
            return []
        pairs: set[tuple[str, str]] = set()
        statuses = self._knob_statuses
        backend_is_tuned = self._power_profile_backend_is_tuned()
        for k in self.registry:
            conflict_ids = filtered_active_conflicts(
                k.id, self._queued_actions, statuses, state=self.state
            )
            conflict_ids = prune_power_profile_conflicts(
                k.id, conflict_ids, backend_is_tuned=backend_is_tuned
            )
            for other_id in conflict_ids:
                pair = tuple(sorted((k.id, other_id)))
                pairs.add(pair)
        return sorted(pairs)

    def _queue_conflict_resets(self, conflict_ids: set[str]) -> int:
        apply_set = {kid for kid, action in self._queued_actions.items() if action == "apply"}
        reset_targets: set[str] = set()
        for kid in conflict_ids:
            if kid in apply_set:
                continue
            status = self._knob_statuses.get(kid, "unknown")
            if status in ("applied", "pending_reboot", "partial", "running"):
                reset_targets.add(kid)
        if not reset_targets:
            return 0
        for kid in reset_targets:
            self._queued_actions[kid] = "reset"
        self._save_queue()
        self._update_queue_ui()
        self._populate()
        return len(reset_targets)

    def _on_show_conflicts(self) -> None:
        pairs = self._collect_conflict_pairs()
        if not pairs:
            QMessageBox.information(self, "Conflicts", "No conflicts detected.")
            return
        by_id = {k.id: k for k in self.registry}
        lines: list[str] = []
        conflict_ids: set[str] = set()
        for left, right in pairs:
            left_title = by_id.get(left).title if left in by_id else left
            right_title = by_id.get(right).title if right in by_id else right
            left_status = self._knob_statuses.get(left, "unknown")
            right_status = self._knob_statuses.get(right, "unknown")
            lines.append(f"{left_title} ({left_status}) ↔ {right_title} ({right_status})")
            conflict_ids.update((left, right))
        dialog = QDialog(self)
        dialog.setWindowTitle("Conflicts")
        dialog.resize(680, 520)
        layout = QVBoxLayout(dialog)
        summary = QTextEdit()
        summary.setReadOnly(True)
        summary.setPlainText("Current conflicts:\n\n" + "\n".join(lines))
        layout.addWidget(summary)

        pick_label = QLabel("Choose knobs to reset (unchecked knobs will be kept):")
        layout.addWidget(pick_label)
        pick_list = QListWidget()
        pick_list.setSelectionMode(QAbstractItemView.NoSelection)
        for kid in sorted(conflict_ids):
            title = by_id.get(kid).title if kid in by_id else kid
            status = self._knob_statuses.get(kid, "unknown")
            item = QListWidgetItem(f"{title} ({status})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, kid)
            pick_list.addItem(item)
        layout.addWidget(pick_list)
        btns = QDialogButtonBox()
        reset_btn = btns.addButton("Queue selected resets", QDialogButtonBox.AcceptRole)
        detail_btn = btns.addButton("See details", QDialogButtonBox.ActionRole)
        close_btn = btns.addButton(QDialogButtonBox.Close)
        layout.addWidget(btns)

        def _queue_resets() -> None:
            selected: set[str] = set()
            for i in range(pick_list.count()):
                item = pick_list.item(i)
                if item.checkState() == Qt.Checked:
                    kid = item.data(Qt.UserRole)
                    if isinstance(kid, str):
                        selected.add(kid)
            if not selected:
                QMessageBox.information(self, "Conflicts", "No knobs selected for reset.")
                return
            count = self._queue_conflict_resets(selected)
            if count == 0:
                QMessageBox.information(self, "Conflicts", "No applicable conflicts to reset.")
            dialog.accept()

        reset_btn.clicked.connect(_queue_resets)
        detail_btn.clicked.connect(lambda: self._show_conflict_details(conflict_ids))
        close_btn.clicked.connect(dialog.reject)
        dialog.exec()

    def _update_conflict_indicator(self) -> None:
        if not hasattr(self, "btn_conflicts"):
            return
        pairs = self._collect_conflict_pairs()
        self._conflict_pairs = pairs
        if not pairs:
            self.btn_conflicts.setText("Conflicts: 0")
            self.btn_conflicts.setToolTip("No conflicts detected")
            self.btn_conflicts.setStyleSheet("")
            return
        self.btn_conflicts.setText(f"Conflicts: {len(pairs)}")
        self.btn_conflicts.setToolTip("Open conflict resolutions")
        self.btn_conflicts.setStyleSheet(
            "QPushButton { color: #d32f2f; }"
        )

    def _update_knob_status(self, knob_id: str, status: str, display: str) -> None:
        """Update the status cell for a specific knob."""
        # Keep backing store in sync so subsequent _populate() reflects the new state.
        self._knob_statuses[knob_id] = status
        self._apply_baseline_statuses()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            if item is None:
                continue
            if item.data(Qt.UserRole) == knob_id:
                status_item = QTableWidgetItem(display)
                status_item.setForeground(QColor("#1976d2"))
                # Status column is col 5 (col 1 is knob title).
                self.table.setItem(r, 5, status_item)
                break

    def on_view_stack(self) -> None:
        """Show detected audio stack information."""
        try:
            from audioknob_gui.platform.detect import detect_stack, list_alsa_playback_devices
            
            stack = detect_stack()
            devices = list_alsa_playback_devices()
            
            html_lines = [
                "<h3>Audio Stack Detection</h3>",
                "<table style='width:100%'>",
                f"<tr><td><b>PipeWire:</b></td><td>{'✓ Active' if stack.pipewire_active else '○ Not active'}</td></tr>",
                f"<tr><td><b>WirePlumber:</b></td><td>{'✓ Active' if stack.wireplumber_active else '○ Not active'}</td></tr>",
                f"<tr><td><b>JACK:</b></td><td>{'✓ Active' if stack.jack_active else '○ Not active'}</td></tr>",
                "</table>",
                "<hr/>",
                f"<h4>ALSA Playback Devices ({len(devices)})</h4>",
                "<table style='width:100%'>",
            ]
            
            # Show ALL devices - no truncation
            for dev in devices:
                name = dev.get("name", "")
                desc = dev.get("desc", dev.get("raw", "Unknown"))
                html_lines.append(f"<tr><td><b>{name}</b></td><td>{desc}</td></tr>")
            
            html_lines.append("</table>")
            
            if not devices:
                html_lines.append("<p style='color:#666'>No ALSA devices found.</p>")
            
            html = "".join(html_lines)
            
            # Show in resizable dialog
            dialog = QDialog(self)
            dialog.setWindowTitle("Audio Stack Detection")
            dialog.resize(600, 450)
            layout = QVBoxLayout(dialog)
            
            text = QTextEdit()
            text.setReadOnly(True)
            text.setHtml(html)
            layout.addWidget(text)
            
            # Button row
            btn_layout = QHBoxLayout()
            
            def copy_to_clipboard():
                # Plain text version for clipboard
                plain = []
                plain.append("Audio Stack Detection")
                plain.append(f"PipeWire: {'Active' if stack.pipewire_active else 'Not active'}")
                plain.append(f"WirePlumber: {'Active' if stack.wireplumber_active else 'Not active'}")
                plain.append(f"JACK: {'Active' if stack.jack_active else 'Not active'}")
                plain.append("")
                plain.append(f"ALSA Playback Devices ({len(devices)}):")
                for dev in devices:
                    plain.append(f"  {dev.get('name', '')} - {dev.get('desc', dev.get('raw', ''))}")
                QApplication.clipboard().setText("\n".join(plain))
            
            copy_btn = QPushButton("Copy to Clipboard")
            copy_btn.clicked.connect(copy_to_clipboard)
            btn_layout.addWidget(copy_btn)
            btn_layout.addStretch()
            
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.reject)
            btn_layout.addWidget(close_btn)
            layout.addLayout(btn_layout)
            
            dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "Detection Failed", f"Could not detect audio stack: {e}")

    def _show_knob_info(self, knob_id: str) -> None:
        """Show detailed information about a knob."""
        k = next((k for k in self.registry if k.id == knob_id), None)
        if not k:
            return

        def _shell_single_quote(value: str) -> str:
            return "'" + value.replace("'", "'\"'\"'") + "'"

        def _fmt_jitter_value(value: object) -> str:
            if isinstance(value, float):
                return f"{value:.1f}"
            if isinstance(value, int):
                return str(value)
            return "—"
        
        # Build detailed info
        status = self._knob_statuses.get(k.id, "unknown")
        status_text, _ = self._status_display(status)
        preset_match = ""
        if isinstance(self._knob_preset_matches, dict):
            value = self._knob_preset_matches.get(k.id)
            if isinstance(value, str):
                preset_match = value

        impl_info = "Not implemented yet"
        if k.impl:
            kind_label = k.impl.kind
            if k.id == "pipewire_rt_setup":
                kind_label = "composite (queues PipeWire RT Limits + PipeWire RT Module)"
            impl_info = f"<b>Kind:</b> {kind_label}<br/>"
            # For configurable knobs, show current configured values rather than registry defaults.
            params = dict(k.impl.params)
            apply_info_param_overrides(self, k, params)

            for key, val in params.items():
                if isinstance(val, list):
                    impl_info += f"<b>{key}:</b><br/>"
                    for item in val:
                        impl_info += f"  • {item}<br/>"
                else:
                    impl_info += f"<b>{key}:</b> {val}<br/>"

        registry_path = _registry_path()
        reg_q = _shell_single_quote(registry_path)
        status_py = (
            "import json,subprocess; "
            f"data=json.loads(subprocess.check_output([\"python3\",\"-m\",\"audioknob_gui.worker.cli\",\"--registry\",\"{registry_path}\",\"status\"])); "
            f"print([s for s in data.get(\"statuses\",[]) if s.get(\"knob_id\")==\"{k.id}\"][0])"
        )
        status_cmd = f"python3 -c {_shell_single_quote(status_py)}"
        if k.capabilities.apply:
            if k.requires_root:
                apply_cmd = f"pkexec /usr/libexec/audioknob-gui-worker --registry {reg_q} apply {k.id}"
                reset_cmd = f"pkexec /usr/libexec/audioknob-gui-worker --registry {reg_q} restore-knob {k.id}"
            else:
                apply_cmd = f"python3 -m audioknob_gui.worker.cli --registry {reg_q} apply-user {k.id}"
                reset_cmd = f"python3 -m audioknob_gui.worker.cli --registry {reg_q} restore-knob {k.id}"
        else:
            apply_cmd = "N/A (read-only)"
            reset_cmd = "N/A (read-only)"

        cli_html = (
            "<hr/>"
            "<p><b>CLI sanity checks:</b></p>"
            f"<pre>{html_lib.escape(status_cmd)}\n"
            f"{html_lib.escape(apply_cmd)}\n"
            f"{html_lib.escape(reset_cmd)}</pre>"
        )
        
        helpers = InfoHelpers(
            kernel_cmdline_tokens=_kernel_cmdline_tokens,
            param_present=_param_present,
            kernel_is_rt=_kernel_is_rt,
            read_interrupts_map=_read_interrupts_map,
            fmt_jitter_value=_fmt_jitter_value,
            html_escape=html_lib.escape,
        )
        extra_html = build_info_extra_html(self, k, helpers)

        def _requirements_info_line() -> str | None:
            parts: list[str] = []
            if k.requires_root:
                parts.append("root access")
            if k.requires_reboot:
                parts.append("reboot")
            if k.requires_groups:
                parts.append(f"group membership: {', '.join(k.requires_groups)}")
            if k.requires_commands:
                parts.append(f"commands: {', '.join(k.requires_commands)}")
            if k.depends_on:
                by_id = {knob.id: knob.title for knob in self.registry}
                dep_titles = [by_id.get(dep, dep) for dep in k.depends_on]
                parts.append(f"depends on: {', '.join(dep_titles)}")
            if k.id in self._advanced_knob_ids():
                parts.append("advanced mode")
            if not parts:
                return None
            return "requires " + "; ".join(parts)

        def _format_description(desc: str) -> str:
            lines = [ln.strip() for ln in desc.splitlines() if ln.strip()]
            tagged = any(ln.startswith("[") and len(ln) > 2 and ln[2] == "]" for ln in lines)
            if not tagged:
                return f"<p>{html_lib.escape(desc)}</p>"
            groups: dict[str, list[str]] = {"i": [], "r": [], "+": [], "-": [], "?": []}
            for line in lines:
                tag = None
                text = line
                if line.startswith("[") and len(line) > 2 and line[2] == "]":
                    tag = line[1].lower()
                    text = line[3:].strip()
                if tag in ("i", "r", "+", "-"):
                    groups[tag].append(text)
                else:
                    groups["?"].append(text)
            req_line = _requirements_info_line()
            if req_line:
                groups["r"].insert(0, req_line)
            parts_html: list[str] = []
            for line in groups["i"]:
                parts_html.append(f"<p><b>[i]</b> {html_lib.escape(line)}</p>")
            for line in groups["r"]:
                parts_html.append(f"<p><b>[r]</b> {html_lib.escape(line)}</p>")
            for line in groups["+"]:
                parts_html.append(f"<p><b>[+]</b> {html_lib.escape(line)}</p>")
            for line in groups["-"]:
                parts_html.append(f"<p><b>[-]</b> {html_lib.escape(line)}</p>")
            for line in groups["?"]:
                parts_html.append(f"<p>{html_lib.escape(line)}</p>")
            return "\n".join(parts_html)

        description_html = _format_description(k.description)

        html = f"""
        <h3>{k.title}</h3>
        {description_html}
        <hr/>
        <table>
        <tr><td><b>ID:</b></td><td>{k.id}</td></tr>
        <tr><td><b>Status:</b></td><td>{status_text}</td></tr>
        <tr><td><b>Preset match:</b></td><td>{preset_match or '—'}</td></tr>
        <tr><td><b>Category:</b></td><td>{k.category}</td></tr>
        <tr><td><b>Risk:</b></td><td>{k.risk_level}</td></tr>
        <tr><td><b>Requires root:</b></td><td>{'Yes' if k.requires_root else 'No'}</td></tr>
        <tr><td><b>Requires reboot:</b></td><td>{'Yes' if k.requires_reboot else 'No'}</td></tr>
        </table>
        <hr/>
        <p><b>Implementation:</b></p>
        <p>{impl_info}</p>
        {extra_html}
        {cli_html}
        """
        
        dialog = QDialog(self)
        dialog.setWindowTitle(k.title)
        dialog.resize(500, 400)
        layout = QVBoxLayout(dialog)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(html)
        layout.addWidget(text)

        # Add config/sample buttons for knobs that support them.
        add_info_buttons(self, k, dialog, layout)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)

        dialog.exec()

    def _show_jitter_samples(self, samples: list[dict]) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Jitter Test Samples")
        dialog.resize(640, 420)
        layout = QVBoxLayout(dialog)

        text = QTextEdit()
        text.setReadOnly(True)
        lines: list[str] = []
        for item in sorted(samples, key=lambda t: t.get("thread", 0)):
            thread_id = item.get("thread")
            values = item.get("samples")
            if not isinstance(thread_id, int) or not isinstance(values, list):
                continue
            lines.append(f"Thread {thread_id} ({len(values)} samples):")
            lines.append("  " + ", ".join(str(v) for v in values))
            lines.append("")
        if not lines:
            lines.append("No samples captured.")
        text.setPlainText("\n".join(lines))
        layout.addWidget(text)

        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)

        dialog.exec()

    def _collect_live_checks(self, knob, *, status_override: str | None = None) -> list[str]:
        return status.collect_live_checks(self, knob, status_override=status_override)

    def _show_cli_status(self, knob_id: str) -> None:
        status.show_cli_status(self, knob_id)

    def on_check_blockers(self) -> None:
        """Run comprehensive realtime configuration scan."""
        dialog = QDialog(self)
        dialog.setWindowTitle("RT Config Scan")
        dialog.resize(600, 400)
        layout = QVBoxLayout(dialog)
        status_label = QLabel("Running scan...")
        layout.addWidget(status_label)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText("Collecting system info...")
        layout.addWidget(text)

        # Button row with Show Full Scan option
        btn_layout = QHBoxLayout()

        full_html: dict[str, str] = {}
        def show_full_scan() -> None:
            html = full_html.get("full")
            if html:
                text.setHtml(html)
                dialog.setWindowTitle(full_html.get("title", "RT Config Scan (Full)"))

        full_btn = QPushButton("Show Full Scan")
        full_btn.setEnabled(False)
        full_btn.clicked.connect(show_full_scan)
        btn_layout.addWidget(full_btn)
        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        def _task() -> tuple[bool, object, str]:
            from audioknob_gui.testing.rtcheck import run_full_scan, format_scan_html, CheckStatus

            result = run_full_scan()

            actionable_checks = [c for c in result.checks if c.fix_knob is not None]
            actionable_issues = [
                c for c in actionable_checks if c.status not in (CheckStatus.PASS, CheckStatus.SKIP)
            ]

            html = ["<h3>RT Configuration Issues You Can Fix</h3>"]

            if actionable_issues:
                html.append(f"<p>Found {len(actionable_issues)} issue(s) with available fixes.</p>")
                html.append("<table style='width:100%'>")
                for c in actionable_issues:
                    color = {"warn": "#f57c00", "fail": "#d32f2f"}.get(c.status.value, "#000")
                    icon = {"warn": "⚠", "fail": "✗"}.get(c.status.value, "?")
                    html.append(f"<tr><td style='color:{color}'>{icon}</td>")
                    html.append(f"<td><b>{c.name}</b></td>")
                    html.append(f"<td>{c.message}</td></tr>")
                    html.append("<tr><td></td><td colspan='2' style='color:#666; font-size:0.9em'>")
                    if c.detail:
                        html.append(f"{c.detail}<br/>")
                    html.append(f"<i>Fix: Use '{c.fix_knob}' knob in the main menu</i>")
                    html.append("</td></tr>")
                html.append("</table>")
            else:
                html.append("<p style='color:#2e7d32'>✓ All fixable checks passed!</p>")

            html.append("<hr/>")
            html.append(
                f"<p style='color:#666; font-size:0.9em'>Full scan: {result.passed} passed, "
                f"{result.warnings} warnings, {result.failed} failed (score: {result.score}%)</p>"
            )

            return True, {
                "summary_html": "".join(html),
                "full_html": format_scan_html(result),
                "score": result.score,
            }, ""

        worker = QueueTaskWorker(_task, parent=self)

        def _on_done(success: bool, payload: object, message: str) -> None:
            if not isValid(dialog) or not dialog.isVisible():
                return
            if not success or not isinstance(payload, dict):
                status_label.setText("Scan failed")
                text.setPlainText(message or "Scan failed")
                return
            status_label.setText("Scan complete")
            text.setHtml(payload.get("summary_html", ""))
            score = payload.get("score")
            full_html["full"] = payload.get("full_html", "")
            if isinstance(score, int):
                full_html["title"] = f"RT Config Scan (Full) - Score: {score}%"
            full_btn.setEnabled(bool(full_html.get("full")))

        worker.finished.connect(_on_done)
        worker.finished.connect(worker.deleteLater)
        self._task_threads.append(worker)
        worker.start()

        dialog.exec()

    def _on_join_groups(self) -> None:
        requirements.on_join_groups(self)

    def _on_leave_groups(self) -> None:
        requirements.on_leave_groups(self)

    def _on_install_packages(self, commands: list[str]) -> None:
        requirements.on_install_packages(self, commands)

    def _on_apply_knob(self, knob_id: str) -> None:
        actions.on_apply_knob(self, knob_id)

    def _on_queue_knob(self, knob_id: str, action: str) -> None:
        actions.on_queue_knob(self, knob_id, action)

    def _ensure_menu_width(self, menu: QMenu) -> None:
        try:
            from PySide6.QtGui import QFontMetrics
        except Exception:
            return
        fm = QFontMetrics(menu.font())
        width = 0
        for action in menu.actions():
            text = action.text().replace("&", "")
            width = max(width, fm.horizontalAdvance(text))
        if width:
            menu.setMinimumWidth(width + 48)

    def _preset_dot_icon(self, color: str) -> QIcon:
        pixmap = QPixmap(12, 12)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QColor("#1f1f1f"))
        painter.setBrush(QColor(color))
        painter.drawEllipse(1, 1, 9, 9)
        painter.end()
        return QIcon(pixmap)

    def _apply_preset_menu_icons(self, baseline_menu: QMenu, factory_menu: QMenu) -> None:
        ref_icon = self._preset_dot_icon(status.REFERENCE_PRESET_DOT_COLOR)
        factory_icon = self._preset_dot_icon(status.FACTORY_PRESET_DOT_COLOR)
        baseline_menu.menuAction().setIcon(ref_icon)
        factory_menu.menuAction().setIcon(factory_icon)
        for action in baseline_menu.actions():
            if action.isSeparator():
                continue
            action.setIcon(ref_icon)
        for action in factory_menu.actions():
            if action.isSeparator():
                continue
            action.setIcon(factory_icon)

    def _apply_technical_column_visibility(self) -> None:
        show = bool(self.state.get("show_technical_columns", False))
        for col in (4, 7, 8):
            self.table.setColumnHidden(col, not show)

    def _on_technical_columns_toggle(self, enabled: bool) -> None:
        self.state["show_technical_columns"] = bool(enabled)
        save_state(self.state)
        self._apply_technical_column_visibility()

    def _on_advanced_mode_toggle(self, enabled: bool) -> None:
        self.state["advanced_mode_enabled"] = bool(enabled)
        save_state(self.state)
        v_scroll = None
        try:
            v_scroll = self.table.verticalScrollBar().value()
            self.table.clearSelection()
            self._clear_dim_hover()
        except Exception:
            v_scroll = None
        self._populate()
        if v_scroll is not None:
            try:
                self.table.verticalScrollBar().setValue(v_scroll)
            except Exception:
                pass

    def _power_profile_backend_is_tuned(self) -> bool:
        pref = self._power_profile_backend_from_state()
        if pref == "tuned":
            return True
        if pref == "powerprofilesctl":
            return False
        try:
            from audioknob_gui.worker.ops import select_power_profile_backend

            params = {"backend": "auto"}
            backend = select_power_profile_backend(params)
            return bool(backend) and backend.get("backend") == "tuned"
        except Exception:
            return False

    def _show_conflict_details(self, conflict_ids: set[str]) -> None:
        from PySide6.QtWidgets import QTextEdit

        repo_root = Path(__file__).resolve().parents[2]
        details = build_conflict_details(conflict_ids, interactions_path=repo_root / "docs" / "KNOB_INTERACTIONS.md")
        dialog = QDialog(self)
        dialog.setWindowTitle("Conflict details")
        dialog.resize(640, 460)
        layout = QVBoxLayout(dialog)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(details)
        layout.addWidget(text)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)
        dialog.exec()

    def _prompt_conflicts(self, conflicts: dict[str, set[str]]) -> str:
        by_id = {k.id: k for k in self.registry}
        lines: list[str] = []
        conflict_ids: set[str] = set()

        def _state_label(knob_id: str) -> str:
            action = self._queued_actions.get(knob_id)
            if action == "apply":
                return "queued apply"
            if action == "reset":
                return "queued reset"
            return self._knob_statuses.get(knob_id, "unknown")

        for src_id, targets in conflicts.items():
            src_title = by_id.get(src_id).title if src_id in by_id else src_id
            src_state = _state_label(src_id)
            target_titles = []
            for target_id in sorted(targets):
                target_title = by_id.get(target_id).title if target_id in by_id else target_id
                target_titles.append(f"{target_title} ({_state_label(target_id)})")
            if target_titles:
                lines.append(f"{src_title} ({src_state}) ↔ {', '.join(target_titles)}")
            conflict_ids.update(targets)
        msg = "Potential conflicts detected:\n\n" + "\n".join(lines)
        msg += (
            "\n\nChoose how to proceed:\n"
            "• Conflicts are based on active/queued knobs (applied, pending reboot, partial, running)\n"
            "• Apply + reset conflicts: queue resets for the conflicting knobs\n"
            "• Apply anyway: keep current settings (may override)\n"
        )
        while True:
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Conflicts detected")
            box.setText(msg)
            reset_btn = box.addButton("Apply + reset conflicts", QMessageBox.AcceptRole)
            apply_btn = box.addButton("Apply anyway", QMessageBox.DestructiveRole)
            details_btn = box.addButton("See conflicts detail", QMessageBox.ActionRole)
            cancel_btn = box.addButton(QMessageBox.Cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked == details_btn:
                self._show_conflict_details(conflict_ids)
                continue
            if clicked == reset_btn:
                return "reset"
            if clicked == apply_btn:
                return "apply"
            if clicked == cancel_btn:
                return "cancel"
            return "cancel"

    def _on_apply_queue(self, reboot_after: bool) -> bool:
        if (
            self._ui_mode == "simple"
            and hasattr(self, "_simple_level_commit_timer")
            and self._simple_level_commit_timer.isActive()
        ):
            self._commit_pending_simple_level()
        if self._ui_mode == "simple":
            normalized, dropped_non_queue, dropped_applied = self._normalize_simple_queue_actions(
                self._queued_actions
            )
            if normalized != self._queued_actions:
                self._queued_actions = normalized
                self._save_queue()
                self._update_queue_ui()
                self._populate()
            if dropped_non_queue or dropped_applied:
                _get_gui_logger().info(
                    "simple apply preflight normalized non_queue=%s already_applied=%s",
                    ",".join(dropped_non_queue) or "-",
                    ",".join(dropped_applied) or "-",
                )
        if not self._queued_actions or self._queue_busy:
            if self._ui_mode == "simple" and not self._queue_busy:
                QMessageBox.information(
                    self,
                    "Nothing to Apply",
                    "No new simple-mode changes need apply.\n\n"
                    "Queued knobs were already active or are manual-only actions.",
                )
            return False
        if self._busy_knobs:
            QMessageBox.information(
                self,
                "Busy",
                "Finish current operations before applying queued changes.",
            )
            return False
        by_id = {k.id: k for k in self.registry}
        queued = [(kid, action) for kid, action in self._queued_actions.items() if kid in by_id]
        if not queued:
            return False
        if self._ui_mode == "simple" and not self._simple_group_prereq_ready(queued):
            return False
        conflicts = find_conflicts(self._queued_actions, self._knob_statuses, state=self.state)
        if conflicts and not self._power_profile_backend_is_tuned():
            filtered: dict[str, set[str]] = {}
            for src_id, targets in conflicts.items():
                if src_id == "power_profile_performance":
                    continue
                new_targets = {t for t in targets if t != "power_profile_performance"}
                if new_targets:
                    filtered[src_id] = new_targets
            conflicts = filtered
        if conflicts:
            choice = self._prompt_conflicts(conflicts)
            if choice == "cancel":
                return False
            if choice == "reset":
                apply_set = {kid for kid, action in queued if action == "apply"}
                reset_targets: set[str] = set()
                for targets in conflicts.values():
                    reset_targets.update(targets)
                reset_targets -= apply_set
                for cid in reset_targets:
                    self._queued_actions[cid] = "reset"
                self._save_queue()
                self._update_queue_ui()
                self._populate()
                queued = [(kid, action) for kid, action in self._queued_actions.items() if kid in by_id]
                if not queued:
                    return False
        if any(kid == "qjackctl_server_prefix_rt" for kid, _ in queued) and self._is_process_running(
            ["qjackctl", "qjackctl6"]
        ):
            QMessageBox.information(
                self,
                "Close QjackCtl First",
                "Quit QjackCtl before applying QjackCtl RT.\n\n"
                "QjackCtl rewrites its config on exit, which can undo changes.",
            )
            return False
        reset_ids = [kid for kid, action in queued if action == "reset"]
        if reset_ids:
            dependents = self._confirm_dependency_reset(reset_ids)
            if dependents is None:
                return False
            if dependents:
                for kid in dependents:
                    self._queued_actions[kid] = "reset"
                self._save_queue()
                self._update_queue_ui()
                self._populate()
                queued = [(kid, action) for kid, action in self._queued_actions.items() if kid in by_id]
                if not queued:
                    return False
        titles = []
        for kid, action in queued:
            verb = "Apply" if action == "apply" else "Reset"
            titles.append(f"{verb}: {by_id[kid].title}")
        confirm = ConfirmDialog(titles, parent=self)
        confirm.exec()
        if not confirm.ok:
            return False

        _get_gui_logger().info(
            "apply queue start reboot_after=%s actions=%s",
            reboot_after,
            ",".join(f"{kid}:{action}" for kid, action in queued),
        )

        self._queue_origin = self._ui_mode
        self._queue_needs_reboot = reboot_after
        self._queue_busy = True
        self._queue_inflight = list(queued)
        for kid, _ in queued:
            self._busy_knobs.add(kid)
            self._knob_statuses[kid] = "running"
        self._update_queue_ui()
        self._populate()

        apply_ids = [kid for kid, action in queued if action == "apply"]
        apply_ids = self._order_apply_ids_by_dependency(apply_ids)
        reset_ids = [kid for kid, action in queued if action == "reset"]
        apply_root_ids = [kid for kid in apply_ids if by_id[kid].requires_root]
        apply_user_ids = [kid for kid in apply_ids if not by_id[kid].requires_root]
        reset_root_ids = [kid for kid in reset_ids if by_id[kid].requires_root]
        reset_user_ids = [kid for kid in reset_ids if not by_id[kid].requires_root]

        def _task():
            payload: dict[str, object] = {
                "apply_user": None,
                "apply_root": None,
                "reset_user": None,
                "reset_root": None,
            }
            errors: list[str] = []
            if apply_user_ids:
                try:
                    if "qjackctl_server_prefix_rt" in apply_user_ids:
                        self._prime_qjackctl_preset()
                    payload["apply_user"] = _run_worker_apply_user(apply_user_ids)
                except Exception as e:
                    errors.append(str(e))
            if apply_root_ids:
                try:
                    payload["apply_root"] = _run_worker_apply_pkexec(apply_root_ids)
                except Exception as e:
                    errors.append(str(e))
            if reset_user_ids:
                try:
                    result = _run_worker_restore_many_user(reset_user_ids)
                    payload["reset_user"] = result
                    if not result.get("success", True):
                        errs = result.get("errors") or []
                        if not errs:
                            errs = [result.get("error") or "restore failed"]
                        errors.extend(errs)
                except Exception as e:
                    errors.append(str(e))
            if reset_root_ids:
                try:
                    result = _run_worker_restore_many_pkexec(reset_root_ids)
                    payload["reset_root"] = result
                    if not result.get("success", True):
                        errs = result.get("errors") or []
                        if not errs:
                            errs = [result.get("error") or "restore failed"]
                        errors.extend(errs)
                except Exception as e:
                    errors.append(str(e))
            if errors:
                if _PKEXEC_CANCELLED in errors and len(errors) == 1:
                    return False, payload, _PKEXEC_CANCELLED
                return False, payload, "\n".join(errors)
            return True, payload, ""

        worker = QueueTaskWorker(_task, parent=self)
        worker.finished.connect(self._on_apply_queue_finished)
        worker.finished.connect(worker.deleteLater)
        self._task_threads.append(worker)
        worker.start()
        return True

    def _on_reset_knob(self, knob_id: str, requires_root: bool) -> None:
        """Reset a single knob to original."""
        def _task():
            success, msg = self._restore_knob_internal(knob_id, requires_root)
            return success, {"message": msg}, msg

        self._run_knob_task(knob_id, "reset", _task)

    def _run_knob_task(self, knob_id: str, action: str, fn) -> None:
        actions.run_knob_task(self, knob_id, action, fn)

    def _prune_task_threads(self) -> None:
        self._task_threads = [
            w for w in self._task_threads
            if isValid(w) and w.isRunning()
        ]

    def _handle_apply_followups(self, result: dict) -> None:
        warnings = result.get("warnings") or []
        if warnings:
            QMessageBox.warning(
                self,
                "Apply Warning",
                "\n\n".join(str(w) for w in warnings),
            )
        followups = result.get("followups") or []
        if followups:
            label = followups[0].get("label", "Run bootloader update")
            cmd = followups[0].get("cmd", [])
            if isinstance(cmd, list) and cmd:
                box = QMessageBox(self)
                box.setIcon(QMessageBox.Warning)
                box.setWindowTitle("Bootloader Update Required")
                box.setText(
                    "Kernel cmdline changes need a bootloader update to take effect."
                )
                box.setInformativeText(label)
                run_btn = box.addButton("Run update now", QMessageBox.AcceptRole)
                box.addButton("Later", QMessageBox.RejectRole)
                box.exec()
                if box.clickedButton() == run_btn:
                    update_cmd = [str(x) for x in cmd]

                    def _task() -> tuple[bool, object, str]:
                        try:
                            _run_pkexec_command(update_cmd)
                        except Exception as e:
                            return False, {"cmd": update_cmd}, str(e)
                        return True, {"cmd": update_cmd}, ""

                    worker = QueueTaskWorker(_task, parent=self)

                    def _on_done(success: bool, payload: object, message: str) -> None:
                        if not success and message != _PKEXEC_CANCELLED:
                            QMessageBox.warning(self, "Update Failed", message or "Update failed")

                    worker.finished.connect(_on_done)
                    worker.finished.connect(worker.deleteLater)
                    self._task_threads.append(worker)
                    worker.start()

    def _on_knob_task_finished(self, knob_id: str, action: str, success: bool, payload: object, message: str) -> None:
        actions.on_knob_task_finished(self, knob_id, action, success, payload, message)

    def _on_apply_queue_finished(self, success: bool, payload: object, message: str) -> None:
        inflight = [kid for kid, _ in self._queue_inflight]
        self._queue_inflight = []
        for kid in inflight:
            self._busy_knobs.discard(kid)
        self._queue_busy = False
        self._prune_task_threads()

        applied_ids: set[str] = set()
        restored_ids: set[str] = set()
        user_result: dict[str, Any] = {}
        root_result: dict[str, Any] = {}
        reset_user: dict[str, Any] = {}
        reset_root: dict[str, Any] = {}
        if isinstance(payload, dict):
            user_result = payload.get("apply_user") or {}
            root_result = payload.get("apply_root") or {}
            reset_user = payload.get("reset_user") or {}
            reset_root = payload.get("reset_root") or {}
            if user_result:
                try:
                    self.state["last_user_txid"] = user_result.get("txid")
                    applied_ids.update(user_result.get("applied") or [])
                except Exception:
                    pass
            if root_result:
                try:
                    self.state["last_root_txid"] = root_result.get("txid")
                    applied_ids.update(root_result.get("applied") or [])
                except Exception:
                    pass
            if reset_user:
                restored_ids.update(reset_user.get("restored") or [])
            if reset_root:
                restored_ids.update(reset_root.get("restored") or [])
            if user_result or root_result:
                try:
                    save_state(self.state)
                except Exception:
                    pass
            if root_result:
                self._handle_apply_followups(root_result)

        if not success:
            if message == _PKEXEC_CANCELLED:
                self._queue_needs_reboot = False
                self._refresh_statuses()
                self._populate()
                return

            missing_user, other_user = self._collect_no_transaction_knobs(reset_user)
            missing_root, other_root = self._collect_no_transaction_knobs(reset_root)
            missing_ids = list(dict.fromkeys(missing_user + missing_root))
            other_errors = other_user + other_root
            unsupported: list[str] = []

            if missing_ids:
                _get_gui_logger().warning(
                    "apply queue missing transactions=%s",
                    ",".join(missing_ids),
                )

            show_error = True
            if missing_ids and not other_errors:
                show_error = False

            if show_error:
                _get_gui_logger().error("apply queue failed error=%s", message)
                QMessageBox.critical(self, "Failed", message or "Unknown error")

            if missing_ids:
                supported = [kid for kid in missing_ids if self._force_reset_supported(kid)]
                unsupported = [kid for kid in missing_ids if kid not in supported]
                if supported:
                    _get_gui_logger().info(
                        "apply queue force reset prompt supported=%s",
                        ",".join(supported),
                    )
                if supported and self._confirm_force_reset_many(supported):
                    _get_gui_logger().info(
                        "apply queue force reset accepted supported=%s",
                        ",".join(supported),
                    )
                    for kid in supported:
                        self._queued_actions.pop(kid, None)
                    self._save_queue()
                    self._update_queue_ui()
                    self._run_force_reset_many(supported)
                elif supported:
                    _get_gui_logger().info("apply queue force reset cancelled")
            if unsupported:
                _get_gui_logger().warning(
                    "apply queue force reset unsupported=%s",
                    ",".join(unsupported),
                )
                msg = (
                    "No transaction was recorded for:\n"
                    + "\n".join(unsupported)
                    + "\n\nForce reset is not supported for these knobs."
                )
                QMessageBox.warning(self, "Force reset unavailable", msg)
        else:
            _get_gui_logger().info(
                "apply queue done applied=%s restored=%s",
                ",".join(sorted(applied_ids)) or "-",
                ",".join(sorted(restored_ids)) or "-",
            )
            if applied_ids or restored_ids:
                pass

        if success and self._queue_origin == "simple":
            owned = self._simple_owned_knob_ids()
            changed = False
            for kid in applied_ids:
                if kid in simple_mode.SIMPLE_MANAGED_KNOB_IDS and kid not in owned:
                    owned.add(kid)
                    changed = True
            if {"pipewire_rt_limits_group", "pipewire_rt_module_tuning", "pipewire_mlock_policy"} & applied_ids:
                if "pipewire_rt_setup" not in owned:
                    owned.add("pipewire_rt_setup")
                    changed = True
            for kid in restored_ids:
                if kid in owned:
                    owned.discard(kid)
                    changed = True
            if {"pipewire_rt_limits_group", "pipewire_rt_module_tuning", "pipewire_mlock_policy"} & restored_ids:
                if "pipewire_rt_setup" in owned:
                    owned.discard("pipewire_rt_setup")
                    changed = True
            if changed:
                self._set_simple_owned_knob_ids(owned)

        queue_reboot = self._queue_needs_reboot
        self._queue_origin = "full"
        self._queue_needs_reboot = False
        if applied_ids or restored_ids:
            updated = False
            for kid in list(self._queued_actions.keys()):
                action = self._queued_actions.get(kid)
                if action == "apply" and kid in applied_ids:
                    self._queued_actions.pop(kid, None)
                    updated = True
                elif action == "reset" and kid in restored_ids:
                    self._queued_actions.pop(kid, None)
                    updated = True
            if updated:
                self._save_queue()
        self._refresh_statuses()
        if "rt_limits_audio_group" in applied_ids and not self._rt_limits_active():
            self._knob_statuses["rt_limits_audio_group"] = "pending_reboot"
            self._update_reboot_banner()
            QMessageBox.information(
                self,
                "Reboot Required",
                "RT Limits were applied, but your session does not have them yet.\n\n"
                "Log out/in or reboot to activate.",
            )
        if success and queue_reboot:
            self._on_reboot_now(force=True)
        self._populate()

    def _confirm_force_reset(self, knob_id: str, *, reason: str | None = None) -> bool:
        k = next((k for k in self.registry if k.id == knob_id), None)
        if not k:
            return False
        if reason == "reset_no_effect":
            msg = (
                "Reset did not revert this knob to defaults.\n\n"
                "Force reset will attempt to revert the setting to system defaults "
                "even if it was not applied by this app.\n\n"
                "Continue?"
            )
        else:
            msg = (
                "No transaction was recorded for this knob.\n\n"
                "Force reset will attempt to revert the setting to system defaults "
                "even if it was not applied by this app.\n\n"
                "Continue?"
            )
        return QMessageBox.question(self, "Force reset", msg) == QMessageBox.Yes

    def _run_force_reset(self, knob_id: str) -> None:
        actions.run_force_reset(self, knob_id)

    def _force_reset_supported(self, knob_id: str) -> bool:
        k = next((k for k in self.registry if k.id == knob_id), None)
        if not k or not k.impl:
            return False
        return k.impl.kind in (
            "systemd_unit_toggle",
            "kernel_cmdline",
            "sysfs_glob_kv",
            "pam_limits_audio_group",
            "sysctl_conf",
            "udev_rule",
            "pipewire_conf",
            "wireplumber_conf",
            "rtirq_config",
            "irq_affinity",
            "power_profile",
            "qjackctl_server_prefix",
            "wpctl_profile",
            "user_service_mask",
            "baloo_disable",
        )

    def _collect_no_transaction_knobs(self, result: dict[str, Any]) -> tuple[list[str], list[str]]:
        no_tx: list[str] = []
        other_errors: list[str] = []
        if not isinstance(result, dict):
            return no_tx, other_errors

        results = result.get("results") or []
        for item in results:
            if not isinstance(item, dict):
                continue
            knob_id = item.get("knob_id")
            errors: list[str] = []
            if item.get("error"):
                errors.append(str(item["error"]))
            errors.extend([str(e) for e in item.get("errors") or []])
            if not errors:
                continue
            if any(_is_no_transaction_error(e) or _is_force_reset_error(e) for e in errors):
                if knob_id and knob_id not in no_tx:
                    no_tx.append(knob_id)
                for err in errors:
                    if not (_is_no_transaction_error(err) or _is_force_reset_error(err)):
                        other_errors.append(err)
            else:
                other_errors.extend(errors)

        for err in result.get("errors") or []:
            err_str = str(err)
            if _is_no_transaction_error(err_str) or _is_force_reset_error(err_str):
                if ":" in err_str:
                    kid = err_str.split(":", 1)[0].strip()
                    if kid and kid not in no_tx:
                        no_tx.append(kid)
            else:
                other_errors.append(err_str)

        return no_tx, other_errors

    def _confirm_force_reset_many(self, knob_ids: list[str]) -> bool:
        by_id = {k.id: k for k in self.registry}
        names = []
        for kid in knob_ids:
            k = by_id.get(kid)
            if k:
                names.append(f"{k.title} ({k.id})")
            else:
                names.append(kid)
        msg = (
            "Force reset recommended for:\n\n"
            + "\n".join(names)
            + "\n\nForce reset will attempt to revert the settings to system defaults "
            "even if they were not applied by this app or if reset did not change them.\n\n"
            "Continue?"
        )
        return QMessageBox.question(self, "Force reset", msg) == QMessageBox.Yes

    def _run_force_reset_many(self, knob_ids: list[str]) -> None:
        actions.run_force_reset_many(self, knob_ids)

    def _restore_knob_internal(self, knob_id: str, requires_root: bool) -> tuple[bool, str]:
        return actions.restore_knob_internal(self, knob_id, requires_root)
    
    def _restore_knob(self, knob_id: str, requires_root: bool) -> tuple[bool, str]:
        """Legacy wrapper for batch restore."""
        return actions.restore_knob(self, knob_id, requires_root)

    def on_reset_defaults(self) -> None:
        actions.on_reset_defaults(self)


def run_app() -> int:
    app = QApplication(sys.argv)
    combo_wheel_guard = ComboWheelGuard(app)
    app.installEventFilter(combo_wheel_guard)
    app._combo_wheel_guard = combo_wheel_guard
    icon = QIcon.fromTheme("audioknob-gui")
    if icon.isNull():
        for path in (
            "/usr/share/icons/hicolor/256x256/apps/audioknob-gui.png",
            "/usr/share/icons/hicolor/128x128/apps/audioknob-gui.png",
            "/usr/share/icons/hicolor/64x64/apps/audioknob-gui.png",
            "/usr/share/icons/hicolor/1024x1024/apps/audioknob-gui.png",
        ):
            if os.path.exists(path):
                icon = QIcon(path)
                break
    if not icon.isNull():
        app.setWindowIcon(icon)
    win = MainWindow()
    win.show()
    return app.exec()
