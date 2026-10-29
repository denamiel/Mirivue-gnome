# Mirivue GNOME GTK4 0.5.91

- Nouveau barème perceptuel de « Qualité estimée », suivant le calcul de Mirivue KDE 0.9.23 : détail, bruit, compression (blocs et banding), contraste, résolution et cadence.
- Les passages les plus faibles comptent davantage, la netteté et la compression limitent la note finale ; la cadence mesurée sur les horodatages ne peut que la réduire.
- Lecture locale de 5 ou 30 images jusqu’à 640 pixels de largeur sans agrandissement ; 3 ou 7 contrôles de cadence. Décodage FFmpeg en niveaux de gris sans Qt ni nouvelle dépendance.
- Catégorie et six composantes dans les détails d’analyse et l’infobulle. Aide et traduction anglaise mises à jour.
- Cache de qualité estimée version « estimated-quality-v3 » : anciennes notes invalidées sans toucher aux vidéos, aux fichiers XMP ni aux réglages personnels.
- Tests du barème, de l’invalidation, de la lecture des images et de l’échantillonnage ajoutés. Tests GTK dépendants de PyGObject non exécutables dans l’environnement de construction.
