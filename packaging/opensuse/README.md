## openSUSE Tumbleweed RPM packaging (v0.1)

This directory contains a local RPM spec for building and installing `audioknob-gui`
on openSUSE Tumbleweed.

### Build dependencies (one-time)

Install tools needed to build an RPM:

```bash
sudo zypper install -y rpm-build python-rpm-macros python3-rpm-macros pyproject-rpm-macros \
  desktop-file-utils polkit
```

Runtime dependencies are handled by the RPM (notably `python3dist(PySide6)`).

### Build (local)

From the repo root:

```bash
./packaging/opensuse/build-rpm.sh
```

The script writes the SRPM/RPM into `~/rpmbuild/` and prints the resulting RPM path.

### Install / uninstall

```bash
sudo zypper install -y ~/rpmbuild/RPMS/noarch/audioknob-gui-*.rpm
sudo zypper remove -y audioknob-gui
```


