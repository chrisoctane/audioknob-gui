# audioknob-gui

GUI-first realtime audio tuning tool for Linux.

![audioknob-gui screenshot](docs/audioknobv1.png)

## Install (openSUSE Tumbleweed, local RPM)

This is the **v0.3.0** install path validated on openSUSE Tumbleweed.
Currently supported on **Tumbleweed only**.

### 1) Install prerequisites (including git)

```bash
sudo zypper install -y \
  git-core \
  rpm-build \
  python313 python313-devel python313-pip python313-setuptools python313-wheel \
  python313-pyside6 \
  python-rpm-macros \
  desktop-file-utils \
  polkit
```

### 2) Clone the repo

```bash
git clone https://github.com/chrisoctane/audioknob-gui.git
cd audioknob-gui
```

### 3) Build the RPM (local)

```bash
./packaging/opensuse/build-rpm.sh
```

Expected output includes:

- `Built RPM(s):`
- `~/rpmbuild/RPMS/noarch/audioknob-gui-0.3.0-0.noarch.rpm`

### 4) Install the RPM (unsigned local build)

Local RPMs are typically **unsigned**, and `zypper` will refuse them unless you opt in:

```bash
sudo zypper --no-gpg-checks install -y ~/rpmbuild/RPMS/noarch/audioknob-gui-*.rpm
```

### 5) Verify install

```bash
rpm -q audioknob-gui
command -v audioknob-gui
ls -l /usr/libexec/audioknob-gui-worker /usr/share/polkit-1/actions/org.audioknob-gui.policy
```

Launch:

```bash
audioknob-gui
```

Or launch it from your desktop environment’s application menu:

- **Name**: “AudioKnob GUI”
- **Desktop entry**: `/usr/share/applications/audioknob-gui.desktop`

### 6) Optional: Refresh & rebuild (pull latest)

```bash
cd ~/audioknob-gui
git pull
./packaging/opensuse/build-rpm.sh
sudo zypper --no-gpg-checks install -y ~/rpmbuild/RPMS/noarch/audioknob-gui-*.rpm
```

### 7) Uninstall

```bash
sudo zypper remove -y audioknob-gui
```

### 8) Cleanup old dev artifacts (optional)

If you previously installed a dev polkit worker/policy under `/usr/local`, remove them:

```bash
sudo rm -f /usr/local/libexec/audioknob-gui-worker \
           /usr/share/polkit-1/actions/org.audioknob-gui.policy
rm -f ~/.local/share/applications/audioknob-gui.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

### 9) Cleanup (optional)

Remove user GUI state (this does **not** remove any system changes you applied; use the app’s “Reset All” for that):

```bash
rm -f "${XDG_STATE_HOME:-$HOME/.local/state}/audioknob-gui/state.json"
```

Remove local build scratch (keeps the produced RPMs):

```bash
rm -rf ~/rpmbuild/BUILD ~/rpmbuild/BUILDROOT ~/rpmbuild/SOURCES ~/rpmbuild/OTHER ~/rpmbuild/SPECS
```

### Notes

- Root operations are performed via polkit using a fixed-path worker at:
  - `/usr/libexec/audioknob-gui-worker`

## Backlog

Nothing here is committed work until it is moved into `PLAN.md` and implemented. Full list lives in `BUGFEAT.md`.

### Features

- UI refresh pass for layout/spacing polish (after stability)
- Continuous jitter monitor dialog
  - Add a "Monitor" action on the jitter test row that opens a popup.
  - Runs cyclictest continuously (or long duration) and parses output periodically.
  - Live per-thread table: thread id, current max/avg, running best/worst.
  - Stop button writes a final summary into the jitter knob info pane and logs the raw output.
  - Goal: help users identify lowest-jitter cores for JACK pinning.

### Bugfix Backlog (Next Release)

- ~~Test bug: "this is a test, bug. fix me."~~ (fixed)
- Kernel cmdline knobs should allow restoring to Tumbleweed defaults even if they were set before audioknob:
  - threadirqs
  - kernel audit
  - cpu mitigations
- RT limits still not surfacing a reboot/log-out requirement; investigate why banner/prompt can be missed.
- QjackCtl cores popup should read the actual config and pre-select cores (default 0,1 after apply).
- Status check UI should not reserve space before use; consider popup or moving controls into main table.

## Signed RPM via OBS (future)

The local-RPM flow above is great for development, but it requires `--no-gpg-checks` because the RPM is unsigned.
The production path is to publish a **signed** RPM via the openSUSE **Open Build Service (OBS)** so users can install from a repo.

### High-level steps

- **Create OBS project + package**: e.g. `home:<you>:audioknob-gui` and package `audioknob-gui`
- **Upload sources or use a source service**:
  - Upload release tarballs (what `rpmbuild` consumes), or
  - Configure an OBS service to pull from Git and generate the tarball
- **Use our spec**: `packaging/opensuse/audioknob-gui.spec`
- **Publish repo + sign**: OBS generates a repository users can add and verify
- **Install becomes**:
  - `sudo zypper ar -f <repo_url> audioknob-gui`
  - `sudo zypper install -y audioknob-gui`

### Non-goals (for now)

- We are **not** attempting to GPG-sign local RPM builds.
- We are **not** publishing to the official openSUSE distribution repos yet.

## Development

See `PLAN.md` (quick start) and `PROJECT_STATE.md` (architecture + operator contract).
