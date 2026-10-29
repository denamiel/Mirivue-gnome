# Validation pratique de Mirivue GNOME RC29

Les 87 tests automatisés et le contrôle de création de fenêtre ont réussi sur CachyOS GNOME avec RC28. Ces contrôles ne remplacent pas les essais suivants dans une session GNOME réelle. Ne travailler que sur des fichiers créés pour ces essais ; conserver le dossier de test tant que les résultats ne sont pas vérifiés.

## Préparer les données

Dans GNOME Files, créer un dossier `Validation Mirivue` dans Documents. À l'intérieur, créer deux sous-dossiers `Source` et `Destination`, puis deux petits fichiers texte de noms distincts dans `Source`. Copiez un autre fichier texte dans `Destination` avec le même nom que l'un des fichiers de `Source` pour provoquer un conflit volontaire.

## Essais à noter

| Essai | Résultat attendu | Résultat |
|---|---|---|
| Copier un fichier de Source vers Destination | Copie présente ; original conservé. | |
| Couper puis coller l'autre fichier dans Destination | Fichier déplacé ; original absent de Source. | |
| Coller sur le dossier Destination par son menu contextuel | Collage à l'intérieur du dossier sélectionné. | |
| Copier vers le nom déjà occupé | Dialogue de conflit ; aucune suppression silencieuse. | |
| Annuler puis rétablir copie, déplacement et renommage | Noms et emplacements correspondent à l'action demandée. | |
| Déplacer un fichier vers la corbeille puis restaurer | Fichier rétabli au bon emplacement. | |
| Ouvrir plusieurs onglets, naviguer et revenir | Titres et barres de chemin suivent chaque dossier. | |
| Réduire et agrandir la fenêtre, un puis deux panneaux | Menu, chemins, aperçu et sélection restent utilisables. | |
| Ouvrir le bouton Opérations sans travail en cours | Popover lisible horizontalement et correctement ancré. | |
| Thèmes clair et sombre, comparaison avec GNOME Files | Contrôles lisibles ; noter toute différence précise. | |
| Lire une image, une vidéo, un son et un PDF | Aperçus et messages d'indisponibilité compréhensibles. | |
| Accéder à un emplacement GVfs déjà monté dans GNOME Files | Même emplacement accessible ; copier uniquement un fichier d'essai. | |

Pour les transferts entre systèmes de fichiers, répéter les deux premiers essais sur un volume de test ext4, Btrfs ou NTFS si disponible, sans utiliser de fichiers personnels. Essayer une interruption et un conflit seulement sur ces fichiers d'essai. Vérifier ensuite la conservation des deux versions et l'absence de fichiers de transfert résiduels.

## Dépendances facultatives

Dans Préférences → Composants, noter l'état de `mediainfo`, `ffmpeg`, `ffprobe`, `exiftool`, `mkvpropedit`, `mkvextract` et `pactl`. Si un outil est absent, vérifier uniquement que Mirivue explique l'indisponibilité de la fonction concernée et conserve la navigation dans les dossiers. Le test ne demande aucune désinstallation du système.

## Retour arrière

Après avoir sauvegardé les résultats, fermer Mirivue et tester le retour arrière avec le même fichier de mise à jour et l'option `--rollback` seulement si vous souhaitez réellement revenir à la version précédente. Relancer le vérificateur correspondant à la version restaurée. La conservation des réglages doit être contrôlée avant et après.
