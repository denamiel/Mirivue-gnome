# Publication de Mirivue GNOME

## 1. Licence retenue

Le titulaire a délégué le choix de licence. GPL-3.0-or-later a été retenue
pour cette édition GNOME. Les fichiers LICENSE et COPYING, les métadonnées
Python et les recettes Fedora et Arch contiennent cette licence.
La page À propos utilise l'affichage légal natif de libadwaita.

Le contrôle de cohérence doit réussir avant publication :

```bash
/usr/bin/python3 packaging/check_release.py --require-license
```

## 2. Créer le dépôt GitHub

Compte : `denamiel`. Nom proposé : `Mirivue-gnome`.
Créer un dépôt vide, sans README ou licence générés par GitHub, puis y importer
le contenu de ce dossier. La branche principale est `main`.

Les outils connectés permettent de lire et écrire dans un dépôt déjà accessible,
mais n'exposent pas la création d'un dépôt ni de ses webhooks. Cette première
création doit être réalisée par le propriétaire du compte.

Les fichiers dans `.github/workflows/` doivent être importés avec Git ou l'API
GitHub, pas oubliés lors d'un glisser-déposer qui masque les dossiers cachés.
Une fois le dépôt accessible, ces fichiers pourront y être envoyés directement.

## 3. Attendre la validation GitHub Actions

Le workflow `GNOME — tests et paquets` est lancé pour `main`, les pull requests
et les tags `v*`. Il vérifie la fenêtre GTK et la suite entière, construit des
RPM Fedora 44/45 et un paquet Arch, puis teste les applications installées.
Les erreurs de dépendance native ne sont pas transformées en succès.

Les opérations courantes sur le code pourront ensuite être envoyées au dépôt
connecté. La mise à jour sur l'ordinateur reste gérée par DNF ou le gestionnaire
de paquets choisi ; un simple dépôt GitHub ne met pas à jour l'ordinateur.

## 4. Ajouter Mirivue GNOME dans COPR

Créer un projet `mirivue-gnome` distinct du projet KDE, ou un paquet
`mirivue-gnome` dans un projet existant si c'est le choix de l'administrateur.

- Sélectionner `fedora-44-x86_64` et `fedora-45-x86_64` si ces environnements
  sont proposés par COPR ; d'autres architectures ne sont pas encore validées.
- Source type : `SCM` ; type de dépôt : `git`.
- Clone URL : `https://github.com/denamiel/Mirivue-gnome.git`.
- Committish : `main` pour le suivi des commits, ou le tag de la version validée.
- Méthode de construction : `make srpm` (Makefile : `.copr/Makefile`).
- Activer le rebuild par webhook ; récupérer l'URL affichée par COPR.
- Dans GitHub, `Settings` > `Webhooks` : ajouter cette URL avec le contenu
  `application/json` et les événements souhaités.

Ne pas confondre le secret d'un webhook avec un mot de passe public. Ne pas le
placer dans Git. Les webhooks et projets COPR ne sont pas créés par ce dossier.
Le `.spec` lance tous les tests GTK avant qu'un RPM puisse être accepté.

Le processus `make srpm` fabrique ses sources depuis le checkout courant : il
ne dépend pas de l'existence préalable d'une archive de version sur GitHub.

## 5. Publier une version

Incrémenter la version Python, celle de l'ancien installateur conservé et celle
du `.spec`, puis compléter `CHANGELOG.md`. Pousser un tag correspondant, par
exemple `v0.6.23`, sur le commit validé.

Après succès des trois jobs, le workflow crée une version GitHub avec les
sources et les paquets. Le tag et la licence sont contrôlés avant publication.
Le jeton GitHub Actions standard suffit ; aucun secret COPR ou AUR n'est demandé
par ce workflow.

## 6. CachyOS / AUR

`packaging/make_source.py` génère l'archive et un `dist/aur/PKGBUILD` avec sa vraie
empreinte SHA-256. Le job Arch en déduit `.SRCINFO` avec `makepkg --printsrcinfo`.
Les deux fichiers sont fournis dans l'artefact GitHub `arch-package`.

L'AUR nécessite un compte et une clé SSH du mainteneur, ainsi qu'une vérification
préalable que le nom du paquet est libre. Rien n'est envoyé à l'AUR par défaut.
Une automatisation de cet envoi pourra être ajoutée après la première publication
et la configuration explicite des droits du mainteneur.

## Références officielles

- https://docs.copr.fedorainfracloud.org/user_documentation.html#webhooks
- https://docs.copr.fedorainfracloud.org/user_documentation.html#scm
- https://docs.fedoraproject.org/en-US/packaging-guidelines/Python/
- https://wiki.archlinux.org/title/PKGBUILD
- https://wiki.archlinux.org/title/AUR_submission_guidelines
- https://docs.github.com/en/actions
