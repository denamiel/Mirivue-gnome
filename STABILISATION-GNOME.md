# Stabilisation de Mirivue GNOME GTK4

La version GNOME 0.6.0 s’appuie sur GNOME Files (Nautilus) et les GNOME Human Interface Guidelines. Aucun assistant KIO, bibliothèque KDE, Qt ou PySide n’est requis.

## Contrôles avant installation

- Compilation des modules Python et syntaxe des scripts.
- Suite complète des tests unitaires, y compris les cas de menus et de restauration après échec d’installation.
- Import de PyGObject, GTK4, libadwaita et GIO avec `/usr/bin/python3`.
- Somme SHA-256 du contenu embarqué et refus des chemins dangereux, liens et entrées en double.
- Avant remplacement, contrôle borné des imports et des classes GTK, sans création de fenêtre. Après installation, `Verifier-installation-GNOME.sh` ouvre une vraie fenêtre dans un état temporaire, attend son affichage et la referme avec un délai maximal de 25 secondes.
- Références des menus principaux, du menu de chemin, des colonnes et du menu contextuel de fond vérifiées par rapport aux actions enregistrées.

## Installation et retour arrière

L’installateur conserve la version précédente dans `~/.local/share/mirivue-gtk4-previous`. Un échec pendant la publication restaure l’application, le lanceur et les icônes précédents. Les réglages, le cache et le journal sous `~/.local/state/mirivue-gtk4` ne sont ni supprimés ni remplacés.

Fermer Mirivue avant la mise à jour ou la restauration. Le retour arrière s’effectue avec le même fichier `.run` et l’option `--rollback`. L’option `--check-dependencies` permet de vérifier le poste sans installation. `Verifier-installation-GNOME.sh` lit la version dans les sources livrées, puis contrôle le lanceur, les icônes, les imports et la création de la fenêtre après installation. Lancez-le depuis un terminal GNOME avec le répertoire des sources complet à côté du script.

## Conformité des menus GNOME

- Menu principal dans l’en-tête, accès aux préférences, raccourcis, aide et informations ; les vues et réglages à état utilisent des actions GTK avec un état synchronisé.
- Menu du dossier ou du fichier sélectionné : actions liées à la sélection ; « Ouvrir dans un nouvel onglet » uniquement pour un seul dossier ; les commandes subjectives de qualité et de calcul de débit ne sont plus affichées.
- Menu de fond et menu du chemin : actions du dossier courant ; la copie du nom d’un segment par clic droit reste distincte de la copie de son chemin.
- Annuler/Rétablir deviennent indisponibles lorsque leur historique est vide.
- Les interactions à vérifier visuellement restent celles de Nautilus sous GNOME, et non celles des menus Plasma.

## Validation et limites de la version 0.6.0

Les 87 tests ont réussi sur la machine CachyOS GNOME de l’utilisateur avec RC28. L’utilisateur a confirmé la validation des essais pratiques et visuels de RC29. Ces validations ont été rapportées par l’utilisateur ; elles ne constituent pas une certification sur les autres distributions ni une comparaison indépendante de chaque détail avec GNOME Files. La version finale reprend le code fonctionnel de RC29 et ne change que le numéro de version et la documentation de livraison.

Pour toute nouvelle distribution ou modification fonctionnelle, reprendre ces essais :

1. Exécuter `python3 -m unittest discover -s tests -v` sur CachyOS avec PyGObject et les bibliothèques de prévisualisation installées ; aucun test GTK ne doit être ignoré.
2. Exécuter le `.run`, puis `Verifier-installation-GNOME.sh`, vérifier le lanceur, l’icône, le retour arrière et la conservation des réglages.
3. Vérifier les menus, le clavier, les deux panneaux, les onglets, le chemin, la recherche, les aperçus et la navigation avec la même session GNOME que Nautilus. Vérifier en particulier le signalement précédent de chemin « Dossier personnel » jusqu’à confirmation sur la machine cible.
4. Tester copies, déplacements, collisions, annulations, archives, corbeille et restauration sur ext4, NTFS3 et Btrfs, y compris interruption et espace insuffisant.
5. Tester les emplacements réseau GIO/GVfs, la lecture PipeWire, puis une session prolongée avec transferts, aperçus et analyses ; consulter le journal local après la session.

Une perte de données, une mise à jour non restaurable, un menu qui lance une action inapplicable ou une régression de navigation bloquerait une nouvelle publication.
