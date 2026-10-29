# Mirivue GNOME GTK4 0.6.1

- Menu contextuel d’un dossier : **Organiser → Renommer le contenu du dossier…**. F2 continue de renommer le dossier lui-même.
- Le contenu immédiat inclut fichiers masqués et sous-dossiers ordinaires, sans descendre dans ces derniers ; les liens symboliques ne sont pas transmis au renommage.
- La commande utilise l’outil intégré ou le programme externe configuré, vérifie les noms dans l’éditeur intégré et conserve le suivi des renommages.
- Une analyse de vignette terminée après la modification de son fichier ne remplace plus la vignette de la nouvelle version.

L’installateur conserve les réglages et l’ancienne version pour un retour arrière avec `--rollback`.

Tests ciblés réussis. Les tests GTK complets doivent être exécutés sur une session équipée de PyGObject ; l’environnement de préparation ne dispose pas du module `gi`.
