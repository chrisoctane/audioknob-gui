from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


KnobCategory = Literal[
    "permissions",
    "stack",
    "device",
    "irq",
    "cpu",
    "power",
    "services",
    "vm",
    "testing",
]


RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Capabilities:
    read: bool
    apply: bool
    restore: bool


@dataclass(frozen=True)
class Impl:
    kind: str
    params: dict[str, Any]


@dataclass(frozen=True)
class Knob:
    id: str
    title: str
    description: str
    category: KnobCategory
    risk_level: RiskLevel
    requires_root: bool
    requires_reboot: bool
    capabilities: Capabilities
    impl: Impl | None


def load_registry(path: str | Path) -> list[Knob]:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("Unsupported registry schema")

    knobs_raw = data.get("knobs")
    if not isinstance(knobs_raw, list):
        raise ValueError("registry.knobs must be a list")

    out: list[Knob] = []
    seen: set[str] = set()
    for k in knobs_raw:
        if not isinstance(k, dict):
            raise ValueError("knob must be object")

        kid = str(k.get("id", ""))
        if not kid or kid in seen:
            raise ValueError(f"invalid/duplicate knob id: {kid!r}")
        seen.add(kid)

        caps_raw = k.get("capabilities")
        if not isinstance(caps_raw, dict):
            raise ValueError(f"knob {kid}: capabilities must be object")
        caps = Capabilities(
            read=bool(caps_raw.get("read")),
            apply=bool(caps_raw.get("apply")),
            restore=bool(caps_raw.get("restore")),
        )

        impl_raw = k.get("impl")
        impl: Impl | None
        if impl_raw is None:
            impl = None
        else:
            if not isinstance(impl_raw, dict) or "kind" not in impl_raw:
                raise ValueError(f"knob {kid}: impl must be object with kind")
            params = impl_raw.get("params")
            if params is None:
                params = {}
            if not isinstance(params, dict):
                raise ValueError(f"knob {kid}: impl.params must be object")
            impl = Impl(kind=str(impl_raw["kind"]), params=params)

        out.append(
            Knob(
                id=kid,
                title=str(k.get("title", "")),
                description=str(k.get("description", "")),
                category=k.get("category"),
                risk_level=k.get("risk_level"),
                requires_root=bool(k.get("requires_root")),
                requires_reboot=bool(k.get("requires_reboot")),
                capabilities=caps,
                impl=impl,
            )
        )

    return out
