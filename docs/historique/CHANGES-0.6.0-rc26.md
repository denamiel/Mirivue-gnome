# Mirivue GNOME 0.6.0-rc26

- Le vérificateur d'installation lit désormais la version dans les sources livrées et accepte les chemins comportant des espaces.
- Nouveau contrôle explicite `--window-smoke-test` : ouvre une vraie fenêtre GTK dans un état temporaire, attend son affichage, puis ferme l'application sans toucher aux réglages de l'utilisateur. Le vérificateur applique un délai de 25 secondes.
- Vérification des versions minimales GTK 4.12 et libadwaita 1.4 avant mise à jour ; documentation de stabilisation corrigée pour distinguer le contrôle avant remplacement du contrôle graphique après installation.
- Les réglages et fichiers personnels sont préservés pendant la mise à jour.
