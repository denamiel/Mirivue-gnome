# Mirivue GNOME 0.6.18

- « Nouveau dossier » propose désormais un nom valide par défaut (le champ contenait auparavant un espace, refusé à la validation).
- Lorsque le système de fichiers refuse le renommage sans écrasement (certains montages FUSE ou réseau), les déplacements utilisent une méthode de repli qui n'écrase jamais un élément existant : lien physique puis retrait de l'ancien nom pour les fichiers et liens, contrôle d'existence puis renommage pour les dossiers et les supports sans liens physiques.
- Huit tests ajoutés (tests/test_rename_fallback.py).
