# Vérifications de la préparation 0.6.22

Base : archive GNOME 0.6.21 fournie. Date de préparation : 30 octobre 2026.

## Vérifié localement

- Compilation syntaxique du code Python.
- Cohérence de la version entre Python, la recette RPM et l'ancien installateur.
- Trois nouveaux tests : version et lanceur portable, sauvegarde de l'ancien
  lanceur avec conservation des réglages, conservation d'un lanceur personnalisé.
- Construction de la wheel Python et présence des fichiers JSON, aides, icônes,
  fichier desktop et script de transition.
- Installation de cette wheel dans un dossier temporaire et appel du lanceur
  `mirivue-gnome --version` depuis l'extérieur des sources : 0.6.22.
- Création de l'archive source et du PKGBUILD avec son empreinte ; contrôle des
  inclusions et des scripts shell.
- Workflow YAML chargé et dépendances entre jobs vérifiées.

## Limites de cette vérification

La suite complète lancée ici indique 97 tests exécutés, dont sept erreurs dues
à l'absence de PyGObject (`gi`) et un test ignoré. Aucune autre erreur ou échec
n'a été observé ; cela ne valide pas les tests GTK qui n'ont pas pu être chargés.

Cet environnement ne dispose pas de `rpmbuild`, `makepkg`, GTK/PyGObject ni
d'un moteur de conteneurs. Les RPM et le paquet Arch n'ont donc pas encore été
construits ici. Les workflows définissent ces constructions ainsi que leurs
tests d'installation et de fenêtre réelle ; ils ne seront exécutés qu'une fois
le dépôt GitHub créé et les fichiers envoyés.

## Publication

Le dépôt GitHub GNOME n'a pas été créé par cette préparation. Aucun projet
COPR, webhook ou paquet AUR n'a été ajouté.

La licence des sources doit être confirmée avant activation des publications.
Les marqueurs provisoires des recettes doivent être remplacés avec le vrai texte
de licence ; les contrôles de publication le vérifient.

Cette version est une préparation de distribution, pas une déclaration de
stabilité ou d'identité visuelle intégrale avec Nautilus.
