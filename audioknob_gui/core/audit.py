from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any


def sanitize_log_value(value: Any, *, limit: int = 4000) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): sanitize_log_value(v, limit=limit) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_log_value(v, limit=limit) for v in value]
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"... [truncated {len(value) - limit} chars]"
    return value


def log_audit_event(logger: logging.Logger, action: str, payload: dict[str, Any]) -> None:
    try:
        entry = {"event": "audit", "action": action, **payload}
        logger.info("audit %s", json.dumps(sanitize_log_value(entry), sort_keys=True, default=str))
    except Exception as exc:
        logger.warning("audit log failed action=%s error=%s", action, exc)
