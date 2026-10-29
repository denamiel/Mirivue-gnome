Name:           mirivue-gnome
Version:        0.6.22
Release:        1%{?dist}
Summary:        GNOME file and media manager with two panes
License:        GPL-3.0-or-later
URL:            https://github.com/denamiel/Mirivue-gnome
Source0:        %{url}/releases/download/v%{version}/%{name}-%{version}.tar.gz
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
BuildRequires:  libadwaita >= 1.4
BuildRequires:  gnome-desktop4
BuildRequires:  poppler-glib
BuildRequires:  xorg-x11-server-Xvfb
BuildRequires:  xorg-x11-xauth
BuildRequires:  dbus-daemon

Requires:       python3-gobject
Requires:       python3-cairo
Requires:       gtk4 >= 4.12
Requires:       libadwaita >= 1.4
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
%autosetup

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files mirivue_gtk4
desktop-file-validate %{buildroot}%{_datadir}/applications/org.pdenams.Mirivue.Gtk4.desktop

%check
xvfb-run -a dbus-run-session -- bash packaging/verify.sh

%files -f %{pyproject_files}
%doc CHANGELOG.md README.md
%license LICENSE COPYING
%{_bindir}/mirivue-gnome
%{_datadir}/applications/org.pdenams.Mirivue.Gtk4.desktop
%{_datadir}/icons/hicolor/scalable/apps/org.pdenams.Mirivue.Gtk4.svg
%{_datadir}/icons/hicolor/256x256/apps/org.pdenams.Mirivue.Gtk4.png
%{_datadir}/mirivue-gnome/

%changelog
* Fri Oct 30 2026 Mirivue contributors - 0.6.22-1
- Prepare independent GTK4 packages under GPL-3.0-or-later.
