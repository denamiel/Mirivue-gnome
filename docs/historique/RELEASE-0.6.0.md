# Mirivue GNOME GTK4 0.6.0

Version stable de la série 0.6.0, issue de RC29. Cette livraison ne modifie pas les fonctions ni les réglages de RC29 : seule la version affichée et la documentation changent.

## Validation

- 87 tests unitaires et contrôle de création de fenêtre réussis sur CachyOS GNOME avec RC28, selon le résultat fourni par l’utilisateur.
- Essais pratiques et visuels de RC29 déclarés validés par l’utilisateur.
- Compilation, syntaxe, contrôles d’archives et tests sans interface exécutés sur le paquet final dans l’environnement de préparation.
- Les essais sur Debian, Ubuntu et Fedora ne sont pas encore réalisés : aucun paquet pour ces distributions n’est annoncé comme compatible.

## Installation

Fermer Mirivue, puis lancer `Mettre-a-jour-Mirivue-GNOME-vers-0.6.0.run`. L’installateur vérifie l’archive avant de remplacer l’application, conserve la version précédente et ne remplace pas les réglages sous `~/.local/state/mirivue-gtk4`.

Après l’installation, `~/.local/share/mirivue-gtk4/Verifier-installation-GNOME.sh` vérifie la version, le lanceur, l’icône, les composants GTK et l’affichage d’une fenêtre temporaire.

## Retour arrière

Le même fichier `.run` avec `--rollback` restaure la version précédente. Fermer Mirivue avant l’opération.
