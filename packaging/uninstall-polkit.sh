#!/usr/bin/env bash
set -euo pipefail

# This script performs system changes. Run manually.

rm -f "/usr/share/polkit-1/actions/org.audioknob-gui.policy"
rm -f "/usr/libexec/audioknob-gui-worker"
rm -f "/etc/audioknob-gui/dev.conf"

echo "Removed policy + worker launcher."
