#!/bin/bash
# Integration smoke test for audioknob-gui
# Runs without root or GUI - safe for CI

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$REPO_ROOT"

echo "=== Integration Smoke Test ==="
echo ""

echo "1. Testing worker CLI status..."
python3 -m audioknob_gui.worker.cli status > /dev/null
echo "   ✅ status command works"

echo ""
echo "2. Testing worker CLI preview (PipeWire knobs)..."
python3 -m audioknob_gui.worker.cli preview pipewire_quantum pipewire_sample_rate > /dev/null
echo "   ✅ preview command works"

echo ""
echo "3. Testing worker CLI preview (RT limits)..."
python3 -m audioknob_gui.worker.cli preview rt_limits_audio_group > /dev/null
echo "   ✅ preview for root knob works"

echo ""
echo "4. Testing apply-user (PipeWire quantum - safe user-local file)..."
# This creates a file in ~/.config/pipewire/ which is safe
python3 -m audioknob_gui.worker.cli apply-user pipewire_quantum > /dev/null
echo "   ✅ apply-user works"

echo ""
echo "5. Testing list-changes..."
python3 -m audioknob_gui.worker.cli list-changes > /dev/null
echo "   ✅ list-changes works"

echo ""
echo "6. Testing list-pending..."
python3 -m audioknob_gui.worker.cli list-pending > /dev/null
echo "   ✅ list-pending works"

echo ""
echo "7. Testing reset-defaults --scope user (dry run - should have no errors)..."
# This resets only user-scope transactions; safe without root
python3 -m audioknob_gui.worker.cli reset-defaults --scope user > /dev/null
echo "   ✅ reset-defaults --scope user works"

echo ""
echo "=============================================="
echo "All smoke tests passed!"
echo "=============================================="
