from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from audioknob_gui.gui.state import _state_path
from audioknob_gui.gui.worker_api import _worker_log_path


_GUI_LOGGER: logging.Logger | None = None


def _get_gui_logger() -> logging.Logger:
    global _GUI_LOGGER
    if _GUI_LOGGER is not None:
        return _GUI_LOGGER

    log_dir = _state_path().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "gui.log"

    logger = logging.getLogger("audioknob.gui")
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    _GUI_LOGGER = logger
    return logger


_AUDIT_LOGGER: logging.Logger | None = None


def _get_audit_logger() -> logging.Logger:
    global _AUDIT_LOGGER
    if _AUDIT_LOGGER is not None:
        return _AUDIT_LOGGER

    log_path = Path(_worker_log_path(is_root=False))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("audioknob.audit")
    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    _AUDIT_LOGGER = logger
    return logger


def _log_gui_audit(action: str, payload: dict[str, Any]) -> None:
    from audioknob_gui.core.audit import log_audit_event

    log_audit_event(_get_audit_logger(), action, payload)
