"""Cross-platform always-on-top helper for monitor dialogs.

On X11, Qt.WindowStaysOnTopHint works as expected.  On Wayland + KDE Plasma,
the hint is ignored by KWin because xdg-shell does not expose client-side
stacking control.  We work around this by asking KWin directly via its D-Bus
scripting interface to set ``keepAbove`` on the target window.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QCheckBox, QDialog

log = logging.getLogger(__name__)

_WAYLAND_KDE: bool | None = None


def is_wayland_kde() -> bool:
    """Return True when running under Wayland with a KDE compositor."""
    global _WAYLAND_KDE
    if _WAYLAND_KDE is None:
        _WAYLAND_KDE = (
            os.environ.get("XDG_SESSION_TYPE") == "wayland"
            and "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "")
            and shutil.which("qdbus6") is not None
        )
    return _WAYLAND_KDE


def _kwin_set_keep_above(caption: str, enable: bool) -> bool:
    """Ask KWin to set/unset keepAbove on a window matched by *caption*.

    Returns True if the D-Bus call succeeded (does not guarantee the window
    was found — KWin script output goes to the journal only).
    """
    value = "true" if enable else "false"
    safe_caption = caption.replace("\\", "\\\\").replace("'", "\\'")
    js = (
        "var wins = workspace.stackingOrder;\n"
        "for (var i = 0; i < wins.length; i++) {\n"
        f"  if (wins[i].caption === '{safe_caption}') {{\n"
        f"    wins[i].keepAbove = {value};\n"
        "  }\n"
        "}\n"
    )
    script_name = "audioknob_keep_above"
    tmp_path = None
    try:
        subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "unloadScript", script_name],
            capture_output=True, timeout=2,
        )
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", prefix="kwin_keepabove_", delete=False
        ) as f:
            f.write(js)
            tmp_path = f.name
        result = subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "loadScript", tmp_path, script_name],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode != 0:
            log.debug("KWin loadScript failed: rc=%d stderr=%r",
                       result.returncode, result.stderr.strip())
            return False
        script_id = result.stdout.strip()
        subprocess.run(
            ["qdbus6", "org.kde.KWin", f"/Scripting/Script{script_id}", "run"],
            capture_output=True, timeout=2,
        )
        subprocess.run(
            ["qdbus6", "org.kde.KWin", "/Scripting", "unloadScript", script_name],
            capture_output=True, timeout=2,
        )
        return True
    except Exception:
        log.debug("KWin keepAbove failed", exc_info=True)
        return False
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def set_always_on_top(dialog: QDialog, enabled: bool) -> None:
    """Toggle always-on-top for *dialog*, using the best available method.

    On Wayland+KDE this uses KWin scripting via D-Bus.  A short delay is
    needed so the window is fully mapped before KWin can find it.
    On X11 / other platforms, Qt window flags work natively.
    """
    if is_wayland_kde():
        title = dialog.windowTitle()
        # Delay so KWin sees the window after it's mapped.
        QTimer.singleShot(150, lambda: _kwin_set_keep_above(title, enabled))
        return

    # X11 / other platforms: Qt flags work directly.
    flags = dialog.windowFlags()
    if enabled:
        flags |= Qt.Window | Qt.WindowStaysOnTopHint
    else:
        flags &= ~Qt.WindowStaysOnTopHint
    dialog.setWindowFlags(flags)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()


def configure_on_top_checkbox(dialog: QDialog, checkbox: QCheckBox) -> None:
    """Wire up the always-on-top checkbox for *dialog*.

    On Wayland+KDE the checkbox is hidden and keepAbove is set automatically
    when the dialog is shown (via showEvent override not needed — we use a
    QTimer from here after show()).
    On X11 the checkbox toggles the Qt window flag as usual.
    """
    if is_wayland_kde():
        checkbox.hide()
        # Set keepAbove after the dialog is fully shown.
        QTimer.singleShot(300, lambda: _kwin_set_keep_above(dialog.windowTitle(), True))
    else:
        checkbox.toggled.connect(lambda enabled: set_always_on_top(dialog, enabled))
