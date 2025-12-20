#!/bin/bash
# Install desktop launcher for audioknob-gui

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
DESKTOP_FILE="$REPO_ROOT/packaging/audioknob-gui.desktop"
INSTALL_DIR="$HOME/.local/share/applications"

mkdir -p "$INSTALL_DIR"
cp "$DESKTOP_FILE" "$INSTALL_DIR/"

echo "✅ Desktop launcher installed to $INSTALL_DIR/audioknob-gui.desktop"
echo ""
echo "You should now see 'AudioKnob GUI' in your application menu."
echo "If not, try logging out and back in, or run: update-desktop-database ~/.local/share/applications"
