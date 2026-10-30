# Mirivue GNOME 0.6.23 — composants et portée

## Implémentation

- Onglets : `Adw.TabView`, `Adw.TabBar`, `Adw.TabOverview`, `Adw.TabButton`.
  Réorganisation, détachement et raccourcis de navigation gérés par libadwaita.
  Un seul groupe reçoit les raccourcis natifs en mode deux panneaux.
  Ctrl+Maj+T rouvre un onglet fermé dans cette session, avec son historique.
  Fermer une fenêtre ne quitte plus les autres fenêtres de l'application.
- Renommage : nom actuel, nouveau nom et résultat par ligne, avec un bilan
  des changements, noms inchangés et conflits. Aucun gras intégral ni couleur
  imposée ne sont présentés comme une convention Nautilus. F2 individuel et
  renommage multiple restent des actions distinctes selon la sélection.
- Recherche : le texte recherche les noms dans les deux modes local/récursif.
  Les critères multimédias restent explicites. Le résumé utilise la sélection,
  sinon le modèle filtré, et non l'inventaire non filtré.
- Collation des noms : `GLib.utf8_collate_key_for_filename`. Visibilité :
  attributs GIO `standard::is-hidden` et `standard::is-backup`.
- GVfs : `Gtk.DirectoryList` fournit l'inventaire asynchrone ; `Gio.FileMonitor`
  assure la surveillance.
  Le même modèle de sélection, la même liste et la même grille affichent les
  éléments. Chaque ligne conserve son vrai `Gio.File` : aucune URI n'est
  utilisée comme chemin local pour les opérations.
- Ouverture, presse-papiers et transferts : GIO/GDK, avec le format de
  presse-papiers GNOME et les URI distantes conservées. Choix d'application
  hétérogène sans imposer le type du premier fichier ; filtre des applications.
- Création et renommage distants : API GIO asynchrones. Les capacités du
  backend conditionnent les actions. Les suppressions passent par GIO en
  arrière-plan ; un refus de corbeille n'entraîne jamais un effacement définitif.
- Plusieurs emplacements reçus par `Gio.Application` sont tous traités.
- Les compteurs des autres panneaux ne sont plus recalculés à chaque sélection
  active ; une miniature non sélectionnée ne relance plus l'aperçu sélectionné.

## Références officielles consultées

Les documents sont lus dans les miroirs officiels GNOME, documentation intégrée
aux sources comprise. Il ne s'agit pas d'une observation du bureau utilisateur.

- https://github.com/GNOME/libadwaita/blob/main/src/adw-tab-view.c
- https://github.com/GNOME/libadwaita/blob/main/src/adw-tab-overview.c
- https://github.com/GNOME/gtk/blob/main/gtk/gtkdirectorylist.c
- https://github.com/GNOME/nautilus/blob/main/src/nautilus-window.c
- https://github.com/GNOME/nautilus/blob/main/src/nautilus-batch-rename-dialog.c
- https://github.com/GNOME/nautilus/blob/main/src/nautilus-file.c
- https://github.com/GNOME/nautilus/blob/main/src/nautilus-app-chooser.c
- https://github.com/GNOME/gnome-user-docs/blob/master/gnome-help/C/files-search.page

## Limites explicites

Les deux panneaux, les outils multimédias et les sauvegardes de métadonnées
sont propres à Mirivue. Nautilus n'a pas d'équivalent exact à ces ensembles.
La réouverture d'onglet n'ajoute pas de restauration complète de session.
Les analyses, métadonnées et renommages multiples restent locaux ; la recherche
distante filtre le dossier affiché. Les propriétés distantes montrent les
informations disponibles, sans grille Unix supposée applicable à tout serveur.
Les opérations GIO distantes n'ajoutent pas une garantie d'annulation Ctrl+Z.
Les conflits de transferts distants restent conservateurs : pas d'écrasement.

Les tests exercent de vrais composants GTK/Adwaita/GIO avec des fichiers
jetables sous Xvfb. Ils contrôlent les URI SMB/SFTP sans serveur réel. Ils ne
valident donc ni l'authentification réseau réelle ni les gestes physiques sous
GNOME/Wayland, et ne prouvent pas une identité visuelle intégrale avec Nautilus.

Aucune dépendance KDE/KIO/Qt/PySide ou nouvelle dépendance système n'est ajoutée.
Les préférences Nautilus ne sont pas écrites. Les anciennes sauvegardes et
la politique d'écriture des métadonnées sont conservées.

## Surveillance GIO

Le moniteur interne de `Gtk.DirectoryList` est désactivé. Les essais ont révélé
un accès mémoire invalide lors de sa destruction avec une requête de moniteur
en attente (trace native : `g_file_query_info_finish`, puis `handle_events`).
Le code officiel GTK conserve ces événements dans une file libérée à la
destruction. Mirivue utilise donc `Gio.FileMonitor` séparément pour demander
un nouvel inventaire GTK après les changements. Aucun moniteur de fichiers
n'est réimplémenté en Python. La recherche active est conservée au rafraîchissement.
