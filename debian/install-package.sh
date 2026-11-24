#!/usr/bin/env bash
set -euo pipefail
dest=$1
app=org.pdenams.Mirivue.Gtk4
install -d "$dest/usr/lib/python3/dist-packages" "$dest/usr/share/doc/mirivue-gnome"
cp -a mirivue_gtk4 "$dest/usr/lib/python3/dist-packages/"
find "$dest/usr/lib/python3/dist-packages" -type d -name __pycache__ -prune -exec rm -r -- {} +
install -Dm755 debian/mirivue-gnome.launcher "$dest/usr/bin/mirivue-gnome"
install -Dm644 "$app.desktop" "$dest/usr/share/applications/$app.desktop"
desktop-file-validate "$dest/usr/share/applications/$app.desktop"
install -Dm644 "icons/hicolor/scalable/apps/$app.svg" "$dest/usr/share/icons/hicolor/scalable/apps/$app.svg"
install -Dm644 "icons/hicolor/256x256/apps/$app.png" "$dest/usr/share/icons/hicolor/256x256/apps/$app.png"
install -Dm644 packaging/transition_user_install.py "$dest/usr/share/mirivue-gnome/transition_user_install.py"
install -m644 LICENSE COPYING "$dest/usr/share/doc/mirivue-gnome/"
bash packaging/install_docs.sh "$dest/usr/share/doc/mirivue-gnome"
