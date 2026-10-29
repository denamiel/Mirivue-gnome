# Mirivue GNOME 0.6.14

- Pendant un renommage F2, la saisie dans l’éditeur GTK natif ne déclenche plus la recherche de fichiers.
- Une seule demande de démarrage d’édition est conservée par ligne ; les demandes devenues obsolètes après recyclage d’une ligne sont ignorées.
- À la fermeture de l’éditeur, le focus revient à la vue seulement s’il se trouve encore dans l’éditeur. Un éditeur recyclé annule proprement son édition.
- F2 sur une sélection multiple conserve le renommage en masse.
