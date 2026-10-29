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

La suite complète lancée initialement ici indique 97 tests exécutés, dont sept erreurs dues
à l'absence de PyGObject (`gi`) et un test ignoré. Aucune autre erreur ou échec
n'a été observé ; cela ne valide pas les tests GTK qui n'ont pas pu être chargés.

L'environnement local ne dispose pas de `rpmbuild`, `makepkg`, GTK/PyGObject ni
d'un moteur de conteneurs. Les RPM et le paquet Arch n'ont donc pas encore été
construits ici. Les workflows définissent ces constructions ainsi que leurs
tests d'installation et de fenêtre réelle ; ils ne seront exécutés qu'une fois
le dépôt GitHub créé et les fichiers envoyés.

## Premiers résultats GitHub

Le dépôt `denamiel/Mirivue-gnome` a été créé par le propriétaire puis les sources
y ont été importées. Au commit dbd50cdb317874ba215281f1dbb6155bcaaf2854,
135 tests ont réussi sur Ubuntu 24.04 avec GTK, ainsi que le test de fenêtre.
Le paquet Arch a été construit, installé et lancé avec succès.

Les premières constructions Fedora ont relevé un fichier compilé manquant
dans la liste du RPM ; leur journal a aussi révélé une exception dans le menu
des segments masqués de la barre de chemin. Les deux défauts sont corrigés.
Le contrôle de fenêtre refuse désormais les exceptions de callbacks au lieu
de considérer le seul affichage initial comme un succès.

## Publication

La licence choisie est GPL-3.0-or-later. Aucun projet COPR, webhook ou paquet
AUR n'a encore été ajouté. Les constructions finales doivent réussir avant
de publier un tag ou une version installable.

Cette version est une préparation de distribution, pas une déclaration de
stabilité ou d'identité visuelle intégrale avec Nautilus.
