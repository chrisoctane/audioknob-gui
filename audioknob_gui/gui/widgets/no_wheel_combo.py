from __future__ import annotations

try:
    from PySide6.QtCore import QEvent, QObject
    from PySide6.QtWidgets import QComboBox
except Exception:  # pragma: no cover - exercised in CI/runtime environments without Qt libs
    QEvent = None

    class QObject:  # type: ignore[no-redef]
        pass

    class QComboBox:  # type: ignore[no-redef]
        pass


def should_ignore_combo_wheel(*, popup_visible: bool) -> bool:
    """Ignore combo wheel changes unless the popup menu is open."""
    return not popup_visible


class ComboWheelGuard(QObject):
    """App-wide wheel guard for combo boxes."""

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt API naming)
        if QEvent is None:
            return False
        if event is None or event.type() != QEvent.Wheel:
            return False
        if not isinstance(obj, QComboBox):
            return False
        if should_ignore_combo_wheel(popup_visible=obj.view().isVisible()):
            event.ignore()
            return True
        return False
