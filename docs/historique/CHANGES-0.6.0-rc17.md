# Mirivue GNOME 0.6.0 RC17

- Le contrôle préalable de l'installateur vérifie GTK4, libadwaita et le chargement des composants Mirivue sans ouvrir une fenêtre complète ni lancer des tâches de fond.
- La fenêtre complète reste à vérifier lors du lancement de l'application dans une session GNOME ; le contrôle préalable ne prétend plus la valider.
- Cette correction permet de poursuivre l'installation lorsque le contrôle RC16 restait bloqué et expirait au bout de 40 secondes. L'installateur conserve la version précédente pour le retour arrière.
