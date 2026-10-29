# Mirivue GTK 0.5.72

Recherche plus poussée des interférences du glissement natif : les gestes de sélection, de clic droit et de dépôt de fichiers restent exclusivement sur la liste des lignes, sœur de l'en-tête GTK. L'ordre natif est sauvegardé après la fin de la séquence GTK pour éviter d'appliquer un état intermédiaire remove/insert aux autres onglets.

Ajoute une fenêtre « Réorganiser les colonnes… » accessible depuis le menu d'en-tête et la personnalisation des colonnes. Elle reprend le glisser-déposer GTK déjà utilisé pour les commandes de barre d'outils, rend la destination visible avec les couleurs du thème et permet de choisir le panneau gauche ou droit. Chaque panneau conserve son propre ordre.
