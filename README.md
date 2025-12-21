# audioknob-gui

GUI-first realtime audio tuning tool for Linux.

## Install (openSUSE Tumbleweed, local RPM)

This is the **v0.1** install path we validated on openSUSE Tumbleweed.

### 0) (Optional) Remove old dev install artifacts

If you previously installed a dev polkit worker/policy under `/usr/local`, remove them:

```bash
sudo rm -f /usr/local/libexec/audioknob-gui-worker \
           /usr/share/polkit-1/actions/org.audioknob-gui.policy
rm -f ~/.local/share/applications/audioknob-gui.desktop
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

### 1) Clone + build prerequisites

```bash
git clone https://github.com/chrisoctane/audioknob-gui.git
cd audioknob-gui
```

Install build and runtime prerequisites:

```bash
sudo zypper install -y \
  git \
  rpm-build \
  python313 python313-devel python313-pip python313-setuptools python313-wheel \
  python313-pyside6 \
  python-rpm-macros \
  desktop-file-utils \
  polkit
```

### 2) Build the RPM (local)

```bash
./packaging/opensuse/build-rpm.sh
```

Expected output includes:

- `Built RPM(s):`
- `~/rpmbuild/RPMS/noarch/audioknob-gui-0.1.0-0.noarch.rpm`

### 3) Install the RPM (unsigned local build)

Local RPMs are typically **unsigned**, and `zypper` will refuse them unless you opt in:

```bash
sudo zypper --no-gpg-checks install -y ~/rpmbuild/RPMS/noarch/audioknob-gui-*.rpm
```

### 4) Verify install

```bash
rpm -q audioknob-gui
command -v audioknob-gui
ls -l /usr/libexec/audioknob-gui-worker /usr/share/polkit-1/actions/org.audioknob-gui.policy
```

Launch:

```bash
audioknob-gui
```

### 5) Uninstall

```bash
sudo zypper remove -y audioknob-gui
```

### 6) Cleanup (optional)

Remove local build scratch (keeps the produced RPMs):

```bash
rm -rf ~/rpmbuild/BUILD ~/rpmbuild/BUILDROOT ~/rpmbuild/SOURCES ~/rpmbuild/OTHER ~/rpmbuild/SPECS
```

### Notes

- Root operations are performed via polkit using a fixed-path worker at:
  - `/usr/libexec/audioknob-gui-worker`
- For a signed RPM and repo-based install (no `--no-gpg-checks`), the next step is publishing via **OBS** (future).

## Development

See `PLAN.md` (quick start) and `PROJECT_STATE.md` (architecture + operator contract).


