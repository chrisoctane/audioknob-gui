%global pkg_version 0.2.0

Name:           audioknob-gui
Version:        %{pkg_version}
Release:        0
Summary:        GUI-first realtime audio tuning app (transactions + preview/apply/undo)
License:        MIT
URL:            https://github.com/chrisoctane/audioknob-gui
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

# On Tumbleweed the devel packages are versioned (python313-devel, python312-devel, ...).
# The %python3_pkgversion macro is not guaranteed to exist in all build environments,
# so we pin to the current Tumbleweed python used by this repo/tooling.
BuildRequires:  python313
BuildRequires:  python313-devel
BuildRequires:  python313-pip
BuildRequires:  python313-setuptools
BuildRequires:  python313-wheel
BuildRequires:  python-rpm-macros
BuildRequires:  python3-rpm-macros
BuildRequires:  desktop-file-utils
BuildRequires:  fdupes

Requires:       polkit
Requires:       desktop-file-utils
# openSUSE provides PySide6 as python313-pyside6 (no python3dist()/python313dist() virtual provides).
Requires:       python313-pyside6 >= 6.9.0

%description
audioknob-gui is a GUI-first realtime audio tuning tool.
It applies system tweaks as "knobs" with transaction-based apply/undo/reset.

Security model:
- The GUI runs unprivileged.
- Privileged changes are performed via pkexec/polkit using a fixed-path root worker.

%prep
%autosetup -n %{name}-%{version}

%build
%{__python3} -m pip wheel --progress-bar off --disable-pip-version-check \
  --use-pep517 --no-build-isolation --no-deps \
  --wheel-dir dist .

%install
%{__python3} -m pip install --progress-bar off --disable-pip-version-check \
  --root %{buildroot} --prefix %{_prefix} \
  --no-compile --ignore-installed --no-deps \
  --no-warn-script-location \
  dist/*.whl

# Root worker wrapper + polkit policy + desktop entry
install -D -m 0755 packaging/audioknob-gui-worker %{buildroot}%{_libexecdir}/audioknob-gui-worker
install -D -m 0644 polkit/org.audioknob-gui.policy %{buildroot}%{_datadir}/polkit-1/actions/org.audioknob-gui.policy
install -D -m 0644 packaging/audioknob-gui.desktop %{buildroot}%{_datadir}/applications/audioknob-gui.desktop

%fdupes %{buildroot}%{python3_sitelib}

%post
%desktop_database_post

%postun
%desktop_database_postun

%files
%license LICENSE
%doc PROJECT_STATE.md

%{_bindir}/audioknob-gui
%{_bindir}/audioknob-worker

%{_libexecdir}/audioknob-gui-worker
%{_datadir}/polkit-1/actions/org.audioknob-gui.policy
%{_datadir}/applications/audioknob-gui.desktop

%{python3_sitelib}/audioknob_gui
%{python3_sitelib}/audioknob_gui-%{version}.dist-info
