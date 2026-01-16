# Debian/Ubuntu (local .deb)

Build a local package:

```bash
./packaging/debian/build-deb.sh
```

If `python3-pyside6` is missing on Ubuntu, enable Universe:

```bash
sudo apt-get install -y software-properties-common
sudo add-apt-repository universe
sudo apt-get update
```

Install:

```bash
sudo apt-get install -y ~/debbuild/audioknob-gui_*_all.deb
```

Uninstall:

```bash
sudo apt-get remove -y audioknob-gui
```
