%global pkg_version 0.1.0

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
BuildRequires:  python313-devel
BuildRequires:  python-rpm-macros
BuildRequires:  python3-rpm-macros
BuildRequires:  desktop-file-utils
BuildRequires:  fdupes

# The openSUSE pyproject macros build wheels using a python311 "flavor" by default.
# Ensure the build backend exists in that interpreter.
BuildRequires:  python311
BuildRequires:  python311-pip
BuildRequires:  python311-setuptools
BuildRequires:  python311-wheel

Requires:       polkit
Requires:       desktop-file-utils
Requires:       python3dist(PySide6) >= 6.9.0

%description
audioknob-gui is a GUI-first realtime audio tuning tool.
It applies system tweaks as "knobs" with transaction-based apply/undo/reset.

Security model:
- The GUI runs unprivileged.
- Privileged changes are performed via pkexec/polkit using a fixed-path root worker.

%prep
%autosetup -n %{name}-%{version}

%build
%pyproject_wheel

%install
%pyproject_install

# Root worker wrapper + polkit policy + desktop entry
install -D -m 0755 packaging/audioknob-gui-worker %{buildroot}%{_libexecdir}/audioknob-gui-worker
install -D -m 0644 polkit/org.audioknob-gui.policy %{buildroot}%{_datadir}/polkit-1/actions/org.audioknob-gui.policy
install -D -m 0644 packaging/audioknob-gui.desktop %{buildroot}%{_datadir}/applications/audioknob-gui.desktop

%python_expand %fdupes %{buildroot}%{$python_sitelib}

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


