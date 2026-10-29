# Mirivue GNOME 0.6.0 RC16

- Le tri des dossiers avant les fichiers suit la préférence globale de GNOME Files lorsque son schéma GSettings est installé, y compris ses changements pendant l'exécution.
- La vue par défaut en liste ou en icônes suit la préférence globale de GNOME Files, sans ajouter de dépendance à Nautilus. Les dispositions propres à un dossier, la largeur et l'ordre des colonnes restent gérés par Mirivue.
- Les périphériques du panneau Emplacements utilisent leurs icônes symboliques GIO. L'action Monter porte son libellé réel ; les actions Éjecter et Démonter ne sont proposées que si le montage les autorise.
- Audit des couleurs : aucun code hexadécimal n'habille l'interface. Le blanc d'une page PDF est une surface de document et les couleurs de l'icône d'application relèvent de son identité visuelle.

La comparaison visuelle et les tests qui importent GTK nécessitent une session GNOME avec PyGObject. Les emplacements de GNOME Files ne sont pas tous reproduits : voir le compte rendu de l'audit.
