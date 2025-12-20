#!/bin/bash
# Install desktop launcher for audioknob-gui (development mode)
#
# This script generates a .desktop file tailored to THIS repo checkout,
# including venv activation and AUDIOKNOB_DEV_REPO.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
INSTALL_DIR="$HOME/.local/share/applications"
DESKTOP_FILE="$INSTALL_DIR/audioknob-gui.desktop"

# Detect Python interpreter (prefer venv if present)
if [ -x "$REPO_ROOT/.venv/bin/python3" ]; then
    PYTHON="$REPO_ROOT/.venv/bin/python3"
    echo "Using venv Python: $PYTHON"
else
    PYTHON="$(command -v python3)"
    echo "Using system Python: $PYTHON"
    echo "⚠️  Warning: No venv found at $REPO_ROOT/.venv"
    echo "   Consider: python3 -m venv $REPO_ROOT/.venv && $REPO_ROOT/.venv/bin/pip install -e $REPO_ROOT"
fi

# Create the .desktop file with correct paths
mkdir -p "$INSTALL_DIR"

cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Name=AudioKnob GUI
Comment=Linux realtime audio configuration tool (dev mode)
Exec=/usr/bin/env AUDIOKNOB_DEV_REPO=$REPO_ROOT $PYTHON -m audioknob_gui.gui.app
Icon=audio-card
Terminal=false
Type=Application
Categories=AudioVideo;Audio;Settings;
Keywords=audio;realtime;latency;pipewire;jack;tuning;
TryExec=$PYTHON
EOF

echo ""
echo "✅ Desktop launcher installed to $DESKTOP_FILE"
echo ""
echo "Configuration:"
echo "  AUDIOKNOB_DEV_REPO=$REPO_ROOT"
echo "  Python: $PYTHON"
echo ""
echo "You should now see 'AudioKnob GUI' in your application menu."
echo "If not, try: update-desktop-database ~/.local/share/applications"
