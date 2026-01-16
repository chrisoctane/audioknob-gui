# Debian/Ubuntu (local .deb)

Build a local package:

```bash
./packaging/debian/build-deb.sh
```

The build script downloads PySide6 wheels via pip and bundles them into the .deb
(network required). You do **not** need a system `python3-pyside6` package.

Install:

```bash
sudo apt-get install -y ~/debbuild/audioknob-gui_*_all.deb
```

Uninstall:

```bash
sudo apt-get remove -y audioknob-gui
```
