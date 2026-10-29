# Mirivue GNOME GTK4 0.5.97

- Sélecteur facultatif de sortie audio dans les contrôles d'aperçu des sons et vidéos, lorsque `pactl` et un serveur compatible sont disponibles.
- Le flux identifié par le PID de Mirivue est déplacé vers la sortie choisie. La sortie par défaut du système et les flux des autres applications ne sont pas modifiés.
- Le choix est mémorisé dans les préférences de Mirivue et réappliqué au prochain lancement d'un aperçu, si le périphérique reste disponible.
- Sans `pactl` ou sans flux identifiable, la lecture GTK habituelle reste utilisable. Aucun composant KDE/KIO n'est ajouté.
