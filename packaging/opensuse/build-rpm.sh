#!/usr/bin/env bash
set -euo pipefail

# Build a local RPM for openSUSE Tumbleweed using rpmbuild.
#
# Output:
#   ~/rpmbuild/RPMS/noarch/audioknob-gui-<ver>-<rel>.noarch.rpm
#
# Notes:
# - This is intended for local builds (not OBS).
# - The spec uses pyproject macros to build/install the wheel.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

name="audioknob-gui"
version="$(python3 -c "import tomllib, pathlib; d=tomllib.loads(pathlib.Path('pyproject.toml').read_text()); print(d['project']['version'])")"

topdir="${HOME}/rpmbuild"
spec="${repo_root}/packaging/opensuse/${name}.spec"
tar="${topdir}/SOURCES/${name}-${version}.tar.gz"

mkdir -p "${topdir}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

echo "Building ${name} version ${version}"
echo "Using spec: ${spec}"

# Create a source tarball from the current git HEAD.
git archive --format=tar --prefix="${name}-${version}/" HEAD | gzip -9 > "${tar}"

rpmbuild --define "_topdir ${topdir}" -ba "${spec}"

echo ""
echo "Built RPM(s):"
ls -1 "${topdir}/RPMS/"**/*.rpm 2>/dev/null || true


