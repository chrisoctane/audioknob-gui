# Debian/Ubuntu (local .deb)

Build a local package:

```bash
./packaging/debian/build-deb.sh
```

Install:

```bash
sudo apt-get install -y ~/debbuild/audioknob-gui_*_all.deb
```

Uninstall:

```bash
sudo apt-get remove -y audioknob-gui
```
