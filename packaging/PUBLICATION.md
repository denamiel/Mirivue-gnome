# Publication de Mirivue GNOME

## État et responsabilités

Les [sources GNOME](https://github.com/denamiel/Mirivue-gnome) sont déjà hébergées
sur GitHub. Le [dépôt Pacman signé](https://github.com/denamiel/mirivue-arch) est
publié. Il n'est pas nécessaire de recréer ces dépôts pour chaque version.

| Circuit | Sources et déclenchement | Distribution |
| --- | --- | --- |
| GitHub Actions GNOME | `main`, pull requests, tags `v*`, lancement manuel | Validation ; une Release est créée pour un tag conforme après réussite |
| Dépôt Pacman Mirivue | Commit courant de `main` validé par le workflow GNOME requis | Paquet signé Arch/CachyOS x86_64 |
| COPR | Sources SCM et webhook configurés dans le projet COPR | RPM pour les environnements Fedora effectivement construits |
| AUR | Soumission distincte du mainteneur | Aucun envoi automatique configuré |

La configuration SCM et les webhooks COPR ne sont pas des fichiers de ce dépôt.
Leur activation doit être vérifiée dans les services concernés. Un push, un
tag ou la présence d'un fichier `.spec` ne prouvent pas une publication Fedora.

## Licence et validation

GPL-3.0-or-later figure dans LICENSE, COPYING, les métadonnées Python et les
recettes Fedora/Arch. La page À propos emploie l'affichage légal de libadwaita.

```bash
/usr/bin/python3 packaging/check_release.py --require-license
xvfb-run -a dbus-run-session -- bash packaging/verify.sh
```

Installer les dépendances natives avant ces contrôles. Les tests utilisent des
répertoires XDG temporaires ; ils ne constituent pas une comparaison visuelle
avec Nautilus dans une session GNOME/Wayland réelle.

Le workflow [GNOME — tests et paquets](../.github/workflows/checks.yml) vérifie
GTK sous Ubuntu 24.04, construit des RPM Fedora 44/45 et un paquet Arch, puis
teste les applications installées. Les erreurs natives ne sont pas ignorées.
Les résultats actuels sont ceux des exécutions Actions du commit concerné,
pas les résultats historiques d'une ancienne version.

## Publier une version applicative

1. Mettre à jour de façon cohérente `mirivue_gtk4/__init__.py`, `pyproject.toml`,
   le conditionnement Fedora et les références de version de l'installateur
   historique conservé. Adapter le modèle Arch si son format l'exige.
2. Compléter `CHANGELOG.md` et la note de version ; vérifier les formes de
   version avec `packaging/check_release.py`.
3. Envoyer les changements sur une branche de travail, attendre les contrôles
   et intégrer à `main`.
4. Pour une Release applicative, créer le tag correspondant, par exemple
   `v1.0.0-beta.2` uniquement pour les sources portant `1.0.0-beta.2`.
   Ne pas déplacer un tag déjà publié.
5. Attendre les jobs GTK, Fedora et Arch. Le job de publication vérifie le tag
   et la licence, puis joint les sources et paquets à la Release.

Le format visible, Python, RPM et Arch diffère ; voir
[la note de bêta](../BETA-1.0.0.md). Le jeton Actions standard suffit à publier
la Release applicative. La signature du dépôt Pacman est gérée séparément.

Pour une correction documentaire seule, conserver la version de l'application.
Le dépôt Pacman peut augmenter sa révision `pkgrel` lors d'une reconstruction
des mêmes sources applicatives avec une documentation actualisée.

## Dépôt Pacman — Arch/CachyOS

Le workflow de `mirivue-arch` examine les deux éditions chaque heure. Il retient
uniquement le commit courant de `main` dont le workflow requis est terminé avec
succès. Il fige ces sources par SHA, construit, vérifie l'installation des deux
éditions et leur lancement hors écran, puis signe et publie.

Un échec bloque la publication. Sans nouveau commit, une exécution planifiée
ne reconstruit pas les paquets. Une nouvelle version repart à `pkgrel=1` ;
une reconstruction de la même version augmente `pkgrel`.

Le catalogue est servi par la Release fixe `repository` de `mirivue-arch`,
avec paquets et catalogues signés, manifeste signé et archives sources.
Une Release propre à l'application et un compte AUR ne sont pas nécessaires
à ce circuit. Les clés privées restent réservées au mainteneur et à son
job de publication ; elles ne doivent pas être copiées sur les ordinateurs clients.

Les utilisateurs suivent le
[guide du dépôt](https://github.com/denamiel/mirivue-arch#installation-sur-arch--cachyos-x86_64),
puis installent avec `sudo pacman -Syu mirivue-gnome`.
Les mises à jour suivantes passent par `sudo pacman -Syu`.

## Fedora / COPR

Conserver le projet COPR GNOME déjà utilisé. Pour vérifier ou recréer sa
configuration, contrôler :

- Source SCM : Git ; URL `https://github.com/denamiel/Mirivue-gnome.git`.
- Committish : la branche ou le tag explicitement choisi pour ce projet.
  Avec `main`, un webhook actif peut reconstruire avant la fin d'Actions :
  il n'existe pas de verrou GitHub Actions → COPR dans ce dépôt.
- Sous-dossier : vide ; recette `packaging/fedora/mirivue-gnome.spec`.
- Méthode `make srpm`, qui utilise `.copr/Makefile` depuis la racine.
- Environnements Fedora souhaités et disponibles, puis résultats réellement
  réussis avant de les annoncer aux utilisateurs.
- Option de reconstruction automatique et webhook GitHub, si ce suivi est voulu.
  Ne jamais publier l'URL secrète du webhook.

`make srpm` prépare les sources depuis le checkout courant ; une archive
GitHub préexistante n'est pas nécessaire. Le `.spec` exécute les tests GTK.

Une réussite Actions ne prouve pas une réussite COPR. Vérifier séparément le
commit construit dans COPR, les environnements, la version du RPM et son
installation. Après activation du projet sur le poste Fedora :

```bash
sudo dnf install mirivue-gnome
sudo dnf upgrade --refresh mirivue-gnome
```

## AUR et artefacts

`packaging/make_source.py` génère les sources et la recette AUR avec son SHA-256 ;
le job Arch produit aussi `.SRCINFO`. Ces fichiers se trouvent dans l'artefact
`arch-package`, dont la durée de conservation Actions est limitée.

Leur présence n'est pas une publication AUR. Une soumission demande un compte
mainteneur, une clé SSH et les contrôles requis par l'AUR. Le dépôt Pacman Mirivue
fonctionne indépendamment de cette démarche.

## Références officielles

- https://docs.copr.fedorainfracloud.org/user_documentation.html#webhooks
- https://docs.copr.fedorainfracloud.org/user_documentation.html#scm
- https://docs.fedoraproject.org/en-US/packaging-guidelines/Python/
- https://man.archlinux.org/man/PKGBUILD.5.en
- https://wiki.archlinux.org/title/AUR_submission_guidelines
- https://docs.github.com/en/actions
