# Mirivue GNOME GTK4 0.6.0 RC8

- Icônes des dossiers personnels GNOME (Bureau, Documents, Téléchargements, Musique, Images, Vidéos, Modèles et Public), du dossier personnel et des dossiers portant une icône personnalisée GIO. Les vues, les emplacements réseau et l'icône de glisser utilisent des objets `Gio.Icon` du thème actif.
- Calcul de qualité aligné sur KDE 1.0.0 RC21 : détail, bruit, compression, contraste et cadence, sans critère de définition. Cinq niveaux qualitatifs indépendants, profil Standard ou Personnalisé et six profondeurs de 5 à 30 images.
- Commande unique d'analyse prenant les préférences en compte. Nouvelle signature de cache : les scores antérieurs et ceux d'un autre profil deviennent non analysés, sans effacer les autres données.
- Aucun composant Qt, PySide, KIO ou KDE ajouté ; décodage FFmpeg existant, GIO, GTK4 et libadwaita.
