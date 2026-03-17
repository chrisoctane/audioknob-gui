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

# Create a source tarball from tracked working-tree files so local modifications
# are included in local RPM builds. Untracked files are intentionally excluded.
if deleted="$(git ls-files --deleted)" && [ -n "${deleted}" ]; then
  echo "Refusing to build RPM with tracked files deleted from the working tree:" >&2
  while IFS= read -r path; do
    [ -n "${path}" ] && echo "  ${path}" >&2
  done <<< "${deleted}"
  echo "Restore or remove those paths from git before building." >&2
  exit 1
fi

if git status --porcelain --untracked-files=normal | grep -q '^\?\? '; then
  echo "Note: untracked files are not included in the RPM source tarball."
fi

tmp_list="$(mktemp)"
trap 'rm -f "${tmp_list}"' EXIT
git ls-files -z > "${tmp_list}"
tar --null --files-from="${tmp_list}" \
  --transform="s,^,${name}-${version}/," \
  -czf "${tar}"
rm -f "${tmp_list}"
trap - EXIT

rpmbuild --define "_topdir ${topdir}" --define "pkg_version ${version}" -ba "${spec}"

echo ""
echo "Built RPM(s):"
ls -1 "${topdir}/RPMS/"**/*.rpm 2>/dev/null || true

