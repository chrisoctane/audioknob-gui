#!/usr/bin/env bash
set -euo pipefail

# This script performs system changes. Run manually.

rm -f "/usr/share/polkit-1/actions/org.audioknob-gui.policy"
rm -f "/usr/local/libexec/audioknob-gui-worker"

echo "Removed policy + worker launcher."
