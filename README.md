# Mirivue GNOME

Gestionnaire de fichiers et de médias à deux panneaux pour GNOME, écrit en
Python avec GTK4, libadwaita et GIO. Cette édition ne dépend pas de Qt, PySide,
KIO ou KDE.

## Version et état

**1.0.0-beta.1** inaugure la série bêta 1.0. Les sauvegardes des métadonnées
conservent le premier original avec un suivi de provenance vérifié ; les anciennes
sauvegardes successives sont conservées.

Cette version reprend les améliorations de 0.6.24 et rapproche les opérations de fichiers des conventions de Nautilus :
renommage individuel par popover, transferts et annulation groupés, propriétés
récursives GIO, recherche récursive et modèles de documents. La restauration des
onglets et les préférences par dossier sont facultatives et propres à Mirivue.

Les tests utilisent GTK/GIO sous Xvfb. Les résultats par distribution doivent
être contrôlés dans GitHub Actions avant publication. Une comparaison manuelle
GNOME/Wayland et des serveurs SMB/SFTP réels reste nécessaire.
Voir [BETA-1.0.0.md](BETA-1.0.0.md) pour cette bêta et
[NATIF-GNOME-0.6.24.md](NATIF-GNOME-0.6.24.md) pour la portée du rapprochement avec Nautilus.

## Licence

Mirivue GNOME est publié sous **GPL-3.0-or-later** : GNU GPL version 3 ou toute
version ultérieure. Voir [COPYING](COPYING) pour la déclaration du projet et
[LICENSE](LICENSE) pour le texte intégral. Les bibliothèques installées
séparément conservent leurs licences propres.

## Dépendances

- Python 3.11 ou plus récent ; PyGObject ; GTK 4.12+ ; libadwaita 1.5+.
- GIO/GVfs, GnomeDesktop 4 et Poppler GLib pour les emplacements et aperçus.
- Pillow, Mutagen, MediaInfo, FFmpeg/FFprobe et GStreamer pour les médias.
- ExifTool, MKVToolNix CLI et `pactl` sont utilisés si les fonctions associées
  sont disponibles. Les paquets proposent ces composants sans dépendance KDE.

Les noms précis des paquets diffèrent entre Fedora et Arch ; ils figurent dans
le fichier `.spec` et le modèle `PKGBUILD.in`. Les codecs disponibles dépendent
des paquets multimédias installés sur le système.

## Installation native

Les paquets installent `mirivue-gnome` dans `/usr/bin`, le module Python dans
les bibliothèques Python du système et l'icône dans le thème hicolor.
Le lanceur conserve l'identité `org.pdenams.Mirivue.Gtk4`.

Les chemins des réglages, du cache et des données personnelles restent ceux de
Mirivue GTK4 (`mirivue-gtk4` dans les répertoires XDG). Les deux éditions GNOME et
KDE gardent leurs propres fichiers. Aucune association de fichiers par défaut
ni service `org.freedesktop.FileManager1` n'est installé ou modifié.

Si Mirivue a été installé avec l'ancien `.run`, un lanceur dans votre compte peut
masquer le nouveau lanceur système. Le script suivant détecte le lanceur géré :

```bash
/usr/bin/python3 /usr/share/mirivue-gnome/transition_user_install.py
```

Après installation du paquet, avec votre compte habituel et sans `sudo` :

```bash
/usr/bin/python3 /usr/share/mirivue-gnome/transition_user_install.py --apply
```

Il déplace uniquement le lanceur reconnu dans une sauvegarde datée, conserve
l'ancien programme et ne modifie aucun réglage. Un lanceur personnalisé est
refusé et conservé. L'ancien `.run` ne doit plus servir à mettre à jour
l'installation gérée par DNF ou pacman.

## Tests automatiques

```bash
xvfb-run -a dbus-run-session -- bash packaging/verify.sh
```

Ce contrôle nécessite les dépendances natives GTK installées. Il utilise des
répertoires XDG temporaires et ouvre une vraie fenêtre GTK sous Xvfb, sans
utiliser les réglages ou les fichiers personnels. Il ne compare pas visuellement
Mirivue et Nautilus et ne prouve pas leur identité d'apparence.

GitHub Actions vérifie Ubuntu 24.04, Fedora 44, Fedora 45 et Arch ; les paquets
Fedora et Arch sont installés et leur lanceur est ensuite testé hors des sources.

## Publication

Voir [packaging/PUBLICATION.md](packaging/PUBLICATION.md). GitHub, COPR et AUR
ne sont pas activés par la seule présence de ces fichiers : le dépôt et les
intégrations doivent d'abord être créés et les constructions réussir.
