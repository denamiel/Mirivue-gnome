# Mirivue GNOME 0.6.0 RC15

- La barre de chemin laisse GTK et le thème dessiner sa surface ; le style de carte ajouté par Mirivue est retiré.
- Le bouton de débordement de la barre de chemin utilise une icône du thème et sa place est calculée à partir d’une mesure GTK, sans largeur fixée en pixels.
- Le clic droit sur un segment utilise un menu `Gio.Menu` / `Gtk.PopoverMenu` et conserve la copie du nom et du chemin.
- Les fonds particuliers des panneaux actif et inactif sont supprimés ; sélection et focus restent dessinés par GTK/libadwaita.
- L’icône d’une commande absente du thème ne devient plus artificiellement « trois points » : son libellé est affiché. À la taille normale, les icônes de la barre d’outils prennent la taille du thème ; les tailles explicitement choisies par l’utilisateur restent disponibles.
- Le damier de transparence et la bordure de la page PDF prennent leurs couleurs dans le thème. Le blanc du papier PDF reste volontairement blanc, conformément au choix d’aperçu de document.

La comparaison visuelle avec GNOME Files et la suite GTK complète doivent être exécutées dans une session GNOME avec PyGObject.
