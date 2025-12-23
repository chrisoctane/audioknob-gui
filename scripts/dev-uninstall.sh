#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
dev-uninstall.sh [--yes] [--keep-deps]

Dev-only uninstall helper:
  - Resets audioknob-gui changes (user + root)
  - Forces default resets for systemd/kernel knobs when no transactions exist
  - Removes app-created user config files
  - Optionally removes audioknob-gui and its optional dependencies

Options:
  --yes        Run non-interactively
  --keep-deps  Do not remove optional dependencies (only reset knobs/state)
USAGE
}

YES=0
KEEP_DEPS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) YES=1 ;;
    --keep-deps) KEEP_DEPS=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1"; usage; exit 1 ;;
  esac
  shift
done

confirm() {
  local prompt="$1"
  if [[ $YES -eq 1 ]]; then
    return 0
  fi
  read -r -p "$prompt [y/N] " answer
  [[ "${answer}" == "y" || "${answer}" == "Y" ]]
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON="${PYTHON:-python3}"

cd "$REPO_ROOT"

echo "==> Resetting user-scope transactions"
"$PYTHON" -m audioknob_gui.worker.cli reset-defaults --scope user || true

if command -v sudo >/dev/null 2>&1; then
  echo "==> Resetting root-scope transactions"
  sudo -E env PYTHONPATH="$REPO_ROOT" "$PYTHON" -m audioknob_gui.worker.cli reset-defaults --scope root || true
else
  echo "!! sudo not found; skipping root reset"
fi

echo "==> Forcing defaults for root knobs without transactions"
force_knobs="$("$PYTHON" - <<'PY'
from audioknob_gui.registry import load_registry
from audioknob_gui.core.paths import get_registry_path

reg = load_registry(get_registry_path())
for k in reg:
    if not k.impl:
        continue
    if k.impl.kind in ("systemd_unit_toggle", "kernel_cmdline"):
        print(k.id)
PY
)"
if [[ -n "$force_knobs" ]]; then
  if command -v sudo >/dev/null 2>&1; then
    while IFS= read -r kid; do
      [[ -z "$kid" ]] && continue
      sudo -E env PYTHONPATH="$REPO_ROOT" "$PYTHON" -m audioknob_gui.worker.cli force-reset-knob "$kid" || true
    done <<< "$force_knobs"
  else
    echo "!! sudo not found; skipping force reset"
  fi
fi

echo "==> Restoring user service defaults (best-effort)"
services="$("$PYTHON" - <<'PY'
from audioknob_gui.registry import load_registry
from audioknob_gui.core.paths import get_registry_path

reg = load_registry(get_registry_path())
services = []
for k in reg:
    if not k.impl:
        continue
    if k.impl.kind == "user_service_mask":
        services.extend(k.impl.params.get("services", []) or [])
print(" ".join(sorted(set(str(s) for s in services))))
PY
)"
if [[ -n "$services" ]]; then
  systemctl --user unmask $services >/dev/null 2>&1 || true
fi

echo "==> Removing audio groups (best-effort)"
user_name="$(id -un)"
groups_to_remove=()
for g in audio realtime pipewire; do
  if id -nG "$user_name" | grep -qw "$g"; then
    groups_to_remove+=("$g")
  fi
done
if [[ ${#groups_to_remove[@]} -gt 0 ]]; then
  if confirm "Remove $user_name from groups: ${groups_to_remove[*]}?"; then
    if command -v sudo >/dev/null 2>&1; then
      for g in "${groups_to_remove[@]}"; do
        sudo gpasswd -d "$user_name" "$g" >/dev/null 2>&1 || true
      done
      echo "Group changes require log out/in or reboot to take effect."
    else
      echo "!! sudo not found; skipping group removal"
    fi
  fi
fi

if command -v balooctl >/dev/null 2>&1 || command -v balooctl6 >/dev/null 2>&1; then
  balooctl enable >/dev/null 2>&1 || balooctl6 enable >/dev/null 2>&1 || true
fi

echo "==> Removing audioknob PipeWire config files"
rm -f \
  "${HOME}/.config/pipewire/pipewire.conf.d/99-audioknob-quantum.conf" \
  "${HOME}/.config/pipewire/pipewire.conf.d/99-audioknob-rate.conf"
systemctl --user restart pipewire.service pipewire-pulse.service >/dev/null 2>&1 || true

echo "==> Resetting QjackCtl RT flags (best-effort)"
"$PYTHON" - <<'PY'
import configparser
import shlex
from pathlib import Path

path = Path("~/.config/rncbc.org/QjackCtl.conf").expanduser()
if not path.exists():
    raise SystemExit(0)

cp = configparser.ConfigParser(interpolation=None)
cp.optionxform = str
cp.read(path, encoding="utf-8")

def_preset = cp.get("Presets", "DefPreset", fallback="").strip()

def _key(base: str) -> str:
    if def_preset:
        return f"{def_preset}\\{base}"
    return base

def _strip_taskset(tokens: list[str]) -> list[str]:
    out = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "taskset" and i + 2 < len(tokens) and tokens[i + 1] == "-c":
            i += 3
            continue
        out.append(tokens[i])
        i += 1
    return out

def _strip_rt_flags(tokens: list[str]) -> list[str]:
    out = []
    for tok in tokens:
        if tok in ("-R", "--realtime"):
            continue
        if tok.startswith("--realtime="):
            continue
        if tok.startswith("-P"):
            continue
        out.append(tok)
    return out

if "Settings" in cp:
    server_key = _key("Server")
    prefix_key = _key("ServerPrefix")

    server_cmd = cp.get("Settings", server_key, fallback="")
    prefix = cp.get("Settings", prefix_key, fallback="")

    if server_cmd:
        try:
            tokens = shlex.split(server_cmd)
        except Exception:
            tokens = server_cmd.split()
        tokens = _strip_taskset(tokens)
        tokens = _strip_rt_flags(tokens)
        cp.set("Settings", server_key, " ".join(tokens))

    if prefix:
        tokens = prefix.split()
        tokens = _strip_taskset(tokens)
        cp.set("Settings", prefix_key, " ".join(tokens))

    with path.open("w", encoding="utf-8") as f:
        cp.write(f, space_around_delimiters=False)
PY

echo "==> Removing state/transaction data"
rm -rf "${XDG_STATE_HOME:-$HOME/.local/state}/audioknob-gui"
if command -v sudo >/dev/null 2>&1; then
  sudo rm -rf /var/lib/audioknob-gui || true
fi

echo "==> Removing dev polkit artifacts (if any)"
if command -v sudo >/dev/null 2>&1; then
  sudo rm -f /usr/local/libexec/audioknob-gui-worker /usr/share/polkit-1/actions/org.audioknob-gui.policy || true
  sudo rm -f /usr/libexec/audioknob-gui-worker /usr/share/polkit-1/actions/org.audioknob-gui.policy || true
fi
rm -f ~/.local/share/applications/audioknob-gui.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true

if [[ $KEEP_DEPS -eq 0 ]]; then
  echo "==> Removing audioknob-gui + optional dependencies"
  pkgs="$("$PYTHON" - <<'PY'
from audioknob_gui.registry import load_registry
from audioknob_gui.core.paths import get_registry_path
from audioknob_gui.platform.packages import get_package_name

reg = load_registry(get_registry_path())
cmds = set()
for k in reg:
    cmds.update(k.requires_commands or [])
pkgs = {"audioknob-gui"}
for cmd in cmds:
    pkg = get_package_name(cmd)
    if pkg:
        pkgs.add(pkg)
print(" ".join(sorted(pkgs)))
PY
)"

  if [[ -n "$pkgs" ]]; then
    echo "Packages to remove: $pkgs"
    if confirm "Remove these packages now?"; then
      if command -v zypper >/dev/null 2>&1; then
        sudo zypper remove -y $pkgs || true
      elif command -v dnf >/dev/null 2>&1; then
        sudo dnf remove -y $pkgs || true
      elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get remove -y $pkgs || true
      elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Rns --noconfirm $pkgs || true
      else
        echo "!! No supported package manager found. Remove packages manually."
      fi
    else
      echo "Skipping package removal."
    fi
  fi
else
  echo "==> Keeping optional dependencies (--keep-deps)."
fi

echo "Done."
