#!/usr/bin/env bash
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
version_file="$script_dir/mirivue_gtk4/__init__.py"
[[ -f "$version_file" ]] || { printf 'ÉCHEC — version des sources introuvable\n' >&2; exit 1; }
expected="$(sed -n 's/^__version__ = "\([^"]*\)"$/\1/p' "$version_file")"
[[ -n "$expected" ]] || { printf 'ÉCHEC — version des sources illisible\n' >&2; exit 1; }
data="${XDG_DATA_HOME:-$HOME/.local/share}"
app="$data/mirivue-gtk4"
desktop="$data/applications/org.pdenams.Mirivue.Gtk4.desktop"
svg="$data/icons/hicolor/scalable/apps/org.pdenams.Mirivue.Gtk4.svg"
png="$data/icons/hicolor/256x256/apps/org.pdenams.Mirivue.Gtk4.png"
fail() { printf 'ÉCHEC — %s\n' "$1" >&2; exit 1; }
[[ -x "$app/Lancer.sh" ]] || fail 'lanceur absent'
[[ "$("$app/Lancer.sh" --version)" == "$expected" ]] || fail 'version installée inattendue'
[[ -f "$desktop" && -f "$svg" && -f "$png" ]] || fail 'lanceur GNOME ou icône manquant'
escaped_app="${app// /\\ }"
grep -Fq "Exec=$escaped_app/Lancer.sh %U" "$desktop" || fail 'commande du lanceur GNOME incorrecte'
grep -Fq 'Icon=org.pdenams.Mirivue.Gtk4' "$desktop" || fail 'identité d’icône incorrecte'
"$app/Lancer.sh" --check-dependencies >/dev/null || fail 'GTK4/libadwaita indisponibles'
"$app/Lancer.sh" --smoke-test >/dev/null || fail 'chargement des composants GTK4 impossible'
python3 - "$app/Lancer.sh" <<'PY' || fail 'la fenêtre GTK4 ne démarre pas ou ne se ferme pas'
import subprocess,sys
try:
    result=subprocess.run([sys.argv[1],'--window-smoke-test'],capture_output=True,text=True,timeout=25)
except subprocess.TimeoutExpired:
    print('Délai de 25 secondes dépassé.',file=sys.stderr)
    raise SystemExit(1)
if result.returncode or 'Fenêtre GTK4 affichée : OK' not in result.stdout:
    print((result.stderr or result.stdout)[-1200:],file=sys.stderr)
    raise SystemExit(1)
PY
printf 'RÉUSSI — Mirivue GNOME %s, lanceur, icône, dépendances et fenêtre GTK4\n' "$expected"
