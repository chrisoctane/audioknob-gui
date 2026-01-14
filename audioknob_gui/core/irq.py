from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Iterable


_IRQ_RE = re.compile(r"^\d+$")


def _dedupe(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def cpu_list_from_cores(cores: Iterable[int]) -> str:
    unique = sorted({int(c) for c in cores if isinstance(c, int) or str(c).isdigit()})
    return ",".join(str(c) for c in unique)


def parse_cpu_list(raw: str) -> set[int]:
    out: set[int] = set()
    if not raw:
        return out
    text = str(raw).strip()
    if not text:
        return out
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_str, end_str = token.split("-", 1)
            try:
                start = int(start_str)
                end = int(end_str)
            except Exception:
                continue
            if end < start:
                start, end = end, start
            out.update(range(start, end + 1))
        else:
            try:
                out.add(int(token))
            except Exception:
                continue
    return out


def read_cpu_present() -> set[int]:
    for path_str in (
        "/sys/devices/system/cpu/present",
        "/sys/devices/system/cpu/possible",
    ):
        path = Path(path_str)
        if not path.exists():
            continue
        try:
            raw = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        parsed = parse_cpu_list(raw)
        if parsed:
            return parsed
    count = os.cpu_count() or 1
    return set(range(count))


def list_irqs() -> list[int]:
    base = Path("/proc/irq")
    if not base.exists():
        return []
    irqs: list[int] = []
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        if _IRQ_RE.match(entry.name):
            irqs.append(int(entry.name))
    return sorted(irqs)


def read_irq_affinity_list(irq: int) -> str | None:
    path = Path(f"/proc/irq/{irq}/smp_affinity_list")
    if not path.exists():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return None


def is_irq_affinity_writable(irq: int) -> bool:
    path = Path(f"/proc/irq/{irq}/smp_affinity_list")
    try:
        mode = path.stat().st_mode
    except Exception:
        return False
    return bool(mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def build_irq_pinning_unit(state_dir: str) -> str:
    state_path = Path(state_dir) / "state.json"
    return (
        "[Unit]\n"
        "Description=Apply audioknob IRQ pinning\n"
        "After=multi-user.target\n"
        f"ConditionPathExists={state_path}\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"Environment=AUDIOKNOB_STATE_DIR={state_dir}\n"
        "Environment=AUDIOKNOB_IRQ_PINNING_SERVICE=1\n"
        "ExecStart=/usr/libexec/audioknob-gui-worker apply irq_pinning\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def _parse_asound_cards() -> dict[int, str]:
    cards_path = Path("/proc/asound/cards")
    if not cards_path.exists():
        return {}
    try:
        lines = cards_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return {}
    out: dict[int, str] = {}
    for line in lines:
        if not line or not line[:1].strip():
            continue
        m = re.match(r"\s*(\d+)\s+\[([^\]]+)\]:\s*(.+)", line)
        if not m:
            continue
        try:
            idx = int(m.group(1))
        except Exception:
            continue
        desc = m.group(3).strip()
        out[idx] = desc
    return out


def _pci_device_map() -> dict[Path, str]:
    base = Path("/sys/bus/pci/devices")
    mapping: dict[Path, str] = {}
    if not base.exists():
        return mapping
    for entry in base.iterdir():
        try:
            resolved = entry.resolve()
        except Exception:
            continue
        mapping[resolved] = entry.name
    return mapping


def _usb_device_map() -> dict[Path, str]:
    base = Path("/sys/bus/usb/devices")
    mapping: dict[Path, str] = {}
    if not base.exists():
        return mapping
    for entry in base.iterdir():
        try:
            resolved = entry.resolve()
        except Exception:
            continue
        mapping[resolved] = entry.name
    return mapping


def _find_ancestor(path: Path, candidates: set[Path]) -> Path | None:
    for parent in [path, *path.parents]:
        if parent in candidates:
            return parent
    return None


def _read_irq_numbers(pci_path: Path) -> list[int]:
    irqs: list[int] = []
    msi_dir = pci_path / "msi_irqs"
    if msi_dir.exists() and msi_dir.is_dir():
        for entry in sorted(msi_dir.iterdir(), key=lambda p: p.name):
            if _IRQ_RE.match(entry.name):
                irqs.append(int(entry.name))
        if irqs:
            return irqs
    irq_file = pci_path / "irq"
    if irq_file.exists():
        try:
            raw = irq_file.read_text(encoding="utf-8").strip()
            if raw.isdigit():
                irqs.append(int(raw))
        except Exception:
            pass
    return irqs


def _read_usb_label(usb_path: Path) -> str | None:
    parts: list[str] = []
    for key in ("manufacturer", "product"):
        p = usb_path / key
        if not p.exists():
            continue
        try:
            value = p.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if value:
            parts.append(value)
    if parts:
        return " ".join(parts)
    return None


def list_audio_devices() -> list[dict[str, object]]:
    cards = _parse_asound_cards()
    pci_map = _pci_device_map()
    usb_map = _usb_device_map()
    pci_paths = set(pci_map.keys())
    usb_paths = set(usb_map.keys())

    devices: list[dict[str, object]] = []
    sound_root = Path("/sys/class/sound")
    if not sound_root.exists():
        return devices

    for card in sorted(sound_root.glob("card*"), key=lambda p: p.name):
        card_idx_str = card.name.replace("card", "")
        if not card_idx_str.isdigit():
            continue
        card_idx = int(card_idx_str)
        card_id = None
        try:
            card_id = (card / "id").read_text(encoding="utf-8").strip()
        except Exception:
            card_id = None

        desc = cards.get(card_idx) or card_id or f"card{card_idx}"
        device_link = card / "device"
        if not device_link.exists():
            continue
        try:
            device_path = device_link.resolve()
        except Exception:
            continue

        usb_path = _find_ancestor(device_path, usb_paths)
        pci_path = _find_ancestor(device_path, pci_paths)

        bus = "unknown"
        if usb_path is not None:
            bus = "usb"
        elif pci_path is not None:
            bus = "pci"

        pci_id = pci_map.get(pci_path) if pci_path else None
        usb_id = usb_map.get(usb_path) if usb_path else None

        controller_pci_id = None
        irqs: list[int] = []
        warning = None
        controller_driver = None
        if pci_path is not None:
            irqs = _read_irq_numbers(pci_path)
            driver_path = pci_path / "driver"
            if driver_path.exists() and driver_path.is_symlink():
                try:
                    controller_driver = driver_path.resolve().name
                except Exception:
                    controller_driver = None
        if bus == "usb":
            controller_pci_id = pci_id
            if irqs:
                warning = "Pins USB controller IRQs shared by other devices."
        if bus == "usb":
            usb_label = _read_usb_label(usb_path) if usb_path else None
            if usb_label:
                desc = f"{desc} ({usb_label})"

        if bus == "pci" and pci_id:
            key = f"pci:{pci_id}:card{card_idx}"
        elif bus == "usb" and usb_id:
            key = f"usb:{usb_id}:card{card_idx}"
        else:
            key = f"card:{card_idx}"

        devices.append(
            {
                "key": key,
                "label": desc,
                "bus": bus,
                "card_index": card_idx,
                "card_id": card_id,
                "pci_id": pci_id,
                "usb_id": usb_id,
                "controller_pci_id": controller_pci_id,
                "controller_driver": controller_driver,
                "irqs": sorted(set(irqs)),
                "warning": warning,
            }
        )

    return devices


def resolve_selected_devices(selected_keys: Iterable[str]) -> tuple[list[dict[str, object]], list[str]]:
    devices = list_audio_devices()
    by_key = {str(d.get("key")): d for d in devices if d.get("key")}
    selected: list[dict[str, object]] = []
    missing: list[str] = []
    for key in _dedupe([str(k) for k in selected_keys if k]):
        if key in by_key:
            selected.append(by_key[key])
        else:
            missing.append(key)
    return selected, missing


def collect_target_irqs(devices: Iterable[dict[str, object]]) -> list[int]:
    irqs: set[int] = set()
    for device in devices:
        for irq in device.get("irqs") or []:
            try:
                irqs.add(int(irq))
            except Exception:
                continue
    return sorted(irqs)
