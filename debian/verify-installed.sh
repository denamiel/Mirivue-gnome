#!/usr/bin/env bash
set -euo pipefail
report=/tmp/mirivue-validation
exec > >(tee "$report/installation.log") 2>&1
dpkg-query -W mirivue-gnome
mirivue-gnome --version
GSK_RENDERER=cairo mirivue-gnome --window-smoke-test
export GSK_RENDERER=cairo
gtk-launch org.pdenams.Mirivue.Gtk4
timeout 40 xdotool search --sync --onlyvisible --name 'Mirivue'
import -window root "$report/fenetre.png"
