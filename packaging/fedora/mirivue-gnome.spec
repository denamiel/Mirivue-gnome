Name:           mirivue-gnome
%global upstream_version 1.0.0-beta.2
Version:        1.0.0~beta.2
Release:        2%{?dist}
Summary:        GNOME file and media manager with two panes
License:        GPL-3.0-or-later
URL:            https://github.com/denamiel/Mirivue-gnome
Source0:        %{url}/releases/download/v%{upstream_version}/%{name}-%{upstream_version}.tar.gz
BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools >= 77.0.3
BuildRequires:  python3-wheel
BuildRequires:  pyproject-rpm-macros
BuildRequires:  desktop-file-utils
BuildRequires:  python3-gobject
BuildRequires:  python3-cairo
BuildRequires:  python3-pillow
BuildRequires:  python3-mutagen
BuildRequires:  gtk4 >= 4.12
BuildRequires:  libadwaita >= 1.5
BuildRequires:  gnome-desktop4
BuildRequires:  poppler-glib
BuildRequires:  xorg-x11-server-Xvfb
BuildRequires:  xorg-x11-xauth
BuildRequires:  dbus-daemon
BuildRequires:  gvfs

Requires:       python3-gobject
Requires:       python3-cairo
Requires:       gtk4 >= 4.12
Requires:       libadwaita >= 1.5
Requires:       gnome-desktop4
Requires:       poppler-glib
Requires:       hicolor-icon-theme
Requires:       gvfs
Requires:       mediainfo
Requires:       /usr/bin/ffmpeg
Requires:       /usr/bin/ffprobe
Requires:       gstreamer1-plugins-good
Recommends:     gvfs-smb
Recommends:     pulseaudio-utils
Recommends:     perl-Image-ExifTool
Suggests:       mkvtoolnix

%description
Mirivue GNOME is a GTK4 and libadwaita file manager with two panes,
tabs, media information, previews and background file operations.

%prep
%autosetup -n %{name}-%{upstream_version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files mirivue_gtk4
desktop-file-validate %{buildroot}%{_datadir}/applications/org.pdenams.Mirivue.Gtk4.desktop

bash packaging/install_docs.sh "%{buildroot}%{_docdir}/%{name}"

%check
xvfb-run -a dbus-run-session -- bash packaging/verify.sh

%files -f %{pyproject_files}
%doc %{_docdir}/%{name}/
%license LICENSE COPYING
%{_bindir}/mirivue-gnome
%{_datadir}/applications/org.pdenams.Mirivue.Gtk4.desktop
%{_datadir}/icons/hicolor/scalable/apps/org.pdenams.Mirivue.Gtk4.svg
%{_datadir}/icons/hicolor/256x256/apps/org.pdenams.Mirivue.Gtk4.png
%{_datadir}/mirivue-gnome/

%changelog
* Sat Oct 31 2026 Mirivue contributors - 1.0.0~beta.2-2
- Ship and verify updated installation and publication guides.

* Fri Oct 30 2026 Mirivue contributors - 1.0.0~beta.2-1
- Always monitor displayed folders with GIO; remove redundant preference.

* Fri Oct 30 2026 Mirivue contributors - 1.0.0~beta.1-1
- First 1.0 beta; preserve the first original with verified provenance.

* Fri Oct 30 2026 Mirivue contributors - 0.6.24-1
- Prepare independent GTK4 packages under GPL-3.0-or-later.
