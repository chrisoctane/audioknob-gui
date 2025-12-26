#!/usr/bin/env bash
set -euo pipefail

# This script performs system changes. Run manually.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

policy_src="$repo_root/polkit/org.audioknob-gui.policy"
worker_src="$repo_root/packaging/audioknob-gui-worker"

policy_dst="/usr/share/polkit-1/actions/org.audioknob-gui.policy"
worker_dst="/usr/libexec/audioknob-gui-worker"
dev_conf_dir="/etc/audioknob-gui"
dev_conf_path="$dev_conf_dir/dev.conf"

install -D -m 0644 "$policy_src" "$policy_dst"
install -D -m 0755 "$worker_src" "$worker_dst"
install -d -m 0755 "$dev_conf_dir"
printf '%s\n' "$repo_root" > "$dev_conf_path"
chmod 0644 "$dev_conf_path"

echo "Installed: $policy_dst"
echo "Installed: $worker_dst"
echo "Installed: $dev_conf_path"

echo "Note: you may need to restart polkit (or reboot) for policy changes to be picked up."
