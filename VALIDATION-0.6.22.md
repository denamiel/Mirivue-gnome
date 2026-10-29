# Vérifications de Mirivue GNOME 0.6.22

Base : sources GNOME 0.6.21. Préparation : 30 octobre 2026.

## Validation GitHub réussie

Commit testé : a71d653032b2b02e6ae9187d34411fcbda9b2b51.

Exécution :
https://github.com/denamiel/Mirivue-gnome/actions/runs/40974896412

Les quatre jobs ont réussi :

- Ubuntu 24.04 : suite complète de 137 tests, construction Python et fenêtre GTK réelle sous Xvfb.
- Fedora 44 : construction du RPM, tests, installation du paquet et ouverture de la fenêtre hors des sources.
- Fedora 45 : mêmes contrôles de construction, installation et fenêtre.
- Arch / CachyOS : construction avec makepkg, tests, installation et lancement hors des sources.

Les tests emploient des répertoires temporaires pour les réglages. Le rendu Cairo
est imposé uniquement dans les conteneurs sans GPU. D-Bus est lancé après Xvfb
afin que les services de test connaissent l'affichage virtuel.

## Défauts corrigés pendant la préparation

- Ajout des fichiers Python compilés du script de transition à la liste du RPM.
- Correction du menu des segments masqués dans la barre de chemin.
- Le test de fenêtre détecte maintenant les exceptions Python des callbacks.
- Adaptation de l'installation dans les images Fedora minimales lorsque GVfs
  requiert udev et que l'image contient systemd-standalone-tmpfiles.
- Construction Python avec licence SPDX et textes de licence embarqués.

## Licence et publication

La licence choisie est GPL-3.0-or-later. Elle figure dans LICENSE, COPYING,
REUSE.toml, les métadonnées Python, les recettes Fedora et Arch et la page À propos.

Les sources sont dans https://github.com/denamiel/Mirivue-gnome.
Les paquets de test sont disponibles dans les artefacts de l'exécution GitHub.

Aucun projet COPR, webhook ou paquet AUR n'a encore été ajouté et aucun tag de
version n'a été publié. Ces étapes de distribution restent à configurer.

## Limites

Ces contrôles ne constituent pas une comparaison visuelle intégrale avec
Nautilus, ni une validation sur tous les matériels, supports amovibles et
serveurs réseau. Une fenêtre sous Xvfb valide le lancement GTK, pas chaque
interaction dans une session GNOME physique.
