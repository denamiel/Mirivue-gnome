# Mirivue GNOME 0.6.0 RC14

- Le tri des dossiers avant les fichiers est désactivé à la première installation, conformément au réglage initial de GNOME Files. Le choix déjà enregistré par l’utilisateur reste conservé.
- Le choix de l’application pour un seul fichier utilise `Gtk.FileLauncher` quand l’API GTK est disponible ; le cas de plusieurs fichiers reste inchangé.
- Les déplacements de fichiers via GIO utilisent son repli natif entre supports et propagent les erreurs de permission ou de réseau.
- Quand GIO ne peut pas déplacer directement un dossier entre supports, Mirivue copie son contenu dans un emplacement temporaire, contrôle la source et la copie, publie le dossier, puis supprime l’original par GIO. Si la source change pendant la copie, l’original est conservé. Une erreur de suppression est signalée.
- Aucun réglage personnel ou fichier média n’est modifié par la mise à jour.

Les tests ciblés GIO passent. Le contrôle de l’interface et la suite GTK complète restent à exécuter dans une session GNOME avec PyGObject.
