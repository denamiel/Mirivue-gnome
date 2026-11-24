#!/usr/bin/env bash
set -euo pipefail
edition=$1
pkg=mirivue-$edition
export LC_ALL=C.UTF-8
export DEBIAN_FRONTEND=noninteractive
cd "$HOME/source"
sudo apt-get update
sudo apt-get install -y --no-install-recommends build-essential devscripts equivs libgtk-3-bin \
  dbus-user-session udisks2 python3-pyatspi fonts-dejavu-core pipewire-audio
case "$edition" in
  gnome)
    desktop=org.pdenams.Mirivue.Gtk4
    manager=gdm3
    sudo apt-get install -y gdm3 gnome-session gnome-shell nautilus
    for config in /etc/gdm3/custom.conf /etc/gdm3/daemon.conf; do
      if [[ -f "$config" ]]; then
        sudo sed -i '/^\[daemon\]/a AutomaticLoginEnable=true\nAutomaticLogin=validation' "$config"
      fi
    done
    ;;
  kde)
    desktop=org.pdenams.Mirivue.Qt
    manager=sddm
    sudo apt-get install -y plasma-desktop plasma-workspace kwin-wayland sddm dolphin
    sudo install -d /etc/sddm.conf.d
    printf '[Autologin]\nUser=validation\nSession=plasma.desktop\n' | sudo tee /etc/sddm.conf.d/99-validation.conf
    ;;
  *) exit 2 ;;
esac
sudo systemctl restart "$manager"
sudo mk-build-deps --install --remove --tool 'apt-get -y --no-install-recommends' debian/control
dpkg-buildpackage --build=binary --no-sign
sudo apt-get install -y ../"$pkg"_*.deb
dpkg-query -W "$pkg"
"$pkg" --version

# The SSH login also has a session. Select only the graphical session on seat0.
session=
for ((attempt=0; attempt<120; attempt++)); do
  while read -r id _; do
    if [[ "$(loginctl show-session "$id" -p Name --value)" == validation &&
          "$(loginctl show-session "$id" -p Seat --value)" == seat0 &&
          "$(loginctl show-session "$id" -p Type --value)" =~ ^(wayland|x11)$ ]]; then
      session=$id
      break
    fi
  done < <(loginctl list-sessions --no-legend)
  if [[ -n "$session" ]] && systemctl --user show-environment | grep -Eq '^(WAYLAND_DISPLAY|DISPLAY)='; then break; fi
  sleep 2
done
test -n "$session"
loginctl show-session "$session" -p Type -p Desktop -p Active
test -b /dev/disk/by-label/MIRIVUE_USB
lsblk -o NAME,FSTYPE,LABEL,TRAN,MOUNTPOINTS
systemd-run --user --wait --pipe --collect bash -s -- "$pkg" "$desktop" <<'SESSION'
set -euo pipefail
pkg=$1
desktop=$2
if [[ "$pkg" == mirivue-gnome ]]; then
  gsettings set org.gnome.desktop.interface toolkit-accessibility true
  gsettings set org.gnome.desktop.session idle-delay 0
  timeout 60 "$pkg" --window-smoke-test
else
  export QT_LINUX_ACCESSIBILITY_ALWAYS_ON=1
  timeout 90 "$pkg" --native-places-contract
  timeout 90 "$pkg" --ui-contract
fi
gtk-launch "$desktop"
timeout 45 /usr/bin/python3 - <<'CHECK'
import time

import pyatspi

desktop = pyatspi.Registry.getDesktop(0)
for _ in range(40):
    for app in desktop:
        try:
            for window in app:
                if window.getRole() == pyatspi.ROLE_FRAME and "mirivue" in window.name.casefold():
                    print("Fenêtre Mirivue ouverte dans la session graphique :", window.name)
                    raise SystemExit(0)
        except (LookupError, RuntimeError):
            continue
    time.sleep(1)
raise SystemExit("Fenêtre Mirivue introuvable dans l’arbre d’accessibilité.")
CHECK
SESSION
