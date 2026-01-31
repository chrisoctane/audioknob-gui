#!/usr/bin/env bash
set -euo pipefail

# Build a local Debian package using dpkg-deb.
#
# Output:
#   ~/debbuild/audioknob-gui_<ver>_all.deb

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

name="audioknob-gui"
version="$(python3 -c "import tomllib, pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); print(d['project']['version'])")"
arch="$(dpkg --print-architecture 2>/dev/null || true)"
if [ -z "${arch}" ]; then
  arch="$(uname -m)"
  case "${arch}" in
    x86_64) arch="amd64" ;;
    aarch64) arch="arm64" ;;
  esac
fi

build_root="$(mktemp -d)"
pkg_root="${build_root}/${name}_${version}_all"
wheel_dir="${build_root}/wheel"
out_dir="${HOME}/debbuild"

mkdir -p "${pkg_root}/DEBIAN" "${wheel_dir}" "${out_dir}"

echo "Building ${name} version ${version}"

python3 -m pip wheel --progress-bar off --disable-pip-version-check \
  --use-pep517 --no-build-isolation --no-deps \
  --wheel-dir "${wheel_dir}" .

python3 -m pip install --progress-bar off --disable-pip-version-check \
  --root "${pkg_root}" --prefix /usr \
  --no-compile --ignore-installed --only-binary=:all: \
  --no-warn-script-location \
  "${wheel_dir}"/*.whl

# Debian/Ubuntu use dist-packages on sys.path; relocate from site-packages.
deb_root="${pkg_root}/usr/lib/python3/dist-packages"
mkdir -p "${deb_root}"
for base in "${pkg_root}/usr/lib" "${pkg_root}/usr/lib64"; do
  [ -d "${base}" ] || continue
  while IFS= read -r site_root; do
    if [ -n "$(ls -A "${site_root}")" ]; then
      mv "${site_root}"/* "${deb_root}/"
    fi
    rmdir "${site_root}" 2>/dev/null || true
    rmdir "$(dirname "${site_root}")" 2>/dev/null || true
  done < <(find "${base}" -type d -name site-packages -print)
done

# Root worker wrapper + polkit policy + desktop entry
install -d \
  "${pkg_root}/usr/libexec" \
  "${pkg_root}/usr/share/polkit-1/actions" \
  "${pkg_root}/usr/share/applications" \
  "${pkg_root}/usr/share/icons/hicolor/1024x1024/apps"
install -m 0755 packaging/audioknob-gui-worker "${pkg_root}/usr/libexec/audioknob-gui-worker"
install -m 0644 polkit/org.audioknob-gui.policy "${pkg_root}/usr/share/polkit-1/actions/org.audioknob-gui.policy"
install -m 0644 packaging/audioknob-gui.desktop "${pkg_root}/usr/share/applications/audioknob-gui.desktop"
install -m 0644 packaging/icons/audioknob-gui.png "${pkg_root}/usr/share/icons/hicolor/1024x1024/apps/audioknob-gui.png"

sed -e "s/@VERSION@/${version}/g" -e "s/@ARCH@/${arch}/g" packaging/debian/control > "${pkg_root}/DEBIAN/control"
install -m 0755 packaging/debian/postinst "${pkg_root}/DEBIAN/postinst"
install -m 0755 packaging/debian/postrm "${pkg_root}/DEBIAN/postrm"

dpkg-deb --root-owner-group --build "${pkg_root}" "${out_dir}/${name}_${version}_all.deb"

echo ""
echo "Built DEB:"
ls -1 "${out_dir}/${name}_${version}_all.deb"
