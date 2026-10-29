# Mirivue GNOME GTK4 0.6.0 RC6

- Recherche de doublons exacts à partir du dossier actif ou du menu contextuel d'un dossier, récursive dans tous les sous-dossiers.
- Le parcours se fait dans une tâche annulable, ignore les liens symboliques et suit le réglage d'affichage des fichiers cachés. Les noms et extensions peuvent différer : seules les données strictement identiques sont regroupées.
- La fenêtre de résultats montre les chemins relatifs et un choix exclusif du fichier à conserver pour chaque groupe. Une confirmation et une nouvelle vérification précèdent toute mise à la corbeille.
- Tests des doublons entre sous-dossiers, de l'annulation et de la conservation du fichier choisi. Aucune nouvelle dépendance.
