# Mirivue GNOME 0.6.24 — rapprochement fonctionnel et limites

## Modifications

- F2 sur un fichier : `Gtk.Popover`, sélection du nom sans extension, validation du nom et des collisions. F2 multiple garde le dialogue de renommage multiple.
- Transferts : cible du dépôt déterminée par le dossier survolé, dépôt dans le même panneau et actions GDK copie/déplacement/lien. Les liens locaux sont créés avec GIO, sans écraser un nom existant.
- Fusion de dossiers : confirmation explicite et décisions pour les conflits internes. Un dossier source n'est retiré que s'il est vide. Un remplacement explicite de fichier n'est pas présenté comme annulable.
- Historique : une sélection copiée/déplacée correspond à une action ; contrôle de tous les éléments avant annulation. Les dossiers copiés sont vérifiés avant retrait, pour conserver les ajouts ultérieurs de l'utilisateur. Les déplacements fusionnés suivent aussi les dossiers sources retirés.
- Suppression : vérification de l'identité des éléments sélectionnés et refus des racines de volumes et montages imbriqués. Aucun échec de mise à la corbeille ne devient une suppression définitive.
- Corbeille : restauration par l'URI exacte de l'entrée GVfs lorsque son suivi est disponible. Ne pas déduire cette disponibilité de la seule réussite de `Gio.File.trash()`.
- Propriétés : décompte et taille récursifs GIO en arrière-plan pour les dossiers et sélections, sans suivre les liens ni compter deux fois un enfant sélectionné avec son parent. Résultat partiel signalé en cas d'erreur.
- Recherche : critères sans texte en mode récursif, artiste/album en local ; récursion des noms GVfs, annulation native et erreurs d'accès visibles. Il ne s'agit pas d'un moteur de recherche dans le contenu des documents.
- Emplacements : menus d'ouverture dans un nouvel onglet ou une nouvelle fenêtre, propriétés, réorganisation des signets partagés avec GTK ; montages selon leurs capacités GIO. Affichage de Récents conditionné par le réglage GTK et le backend GVfs.
- Création : modèles du dossier XDG Templates, sous-menus et surveillance GIO ; copie sans modifier le modèle. Limites de profondeur et nombre d'entrées alignées sur le code consulté de Nautilus.
- Onglets : déplacement gauche/droite et restauration facultative de la dernière fenêtre, y compris les deux groupes. Les onglets secondaires chargent leur emplacement à leur activation. Les mots de passe d'URI ne sont pas enregistrés. Ce n'est pas une restauration de toutes les fenêtres ni des sélections/défilements.
- Affichage : mémorisation facultative du mode et du tri par dossier, trois légendes facultatives sous les icônes ; tous ces réglages appartiennent à Mirivue. Dates régionales GLib et choix simple/détaillé.
- Compteurs incrémentaux : les changements de sélection ne reparcourent plus tout le modèle.
- Raccourcis complétés, aide de raccourcis actualisée ; la molette des médias ne règle plus le volume ou l'avancement. La molette des images est conservée.
- Presse-papiers : correction du contrôle des formats qui pouvait déclencher une exception avec du texte ordinaire.

## Références et statut

**Vérifié dans le code officiel**, révision Nautilus `283739c868edcceb4e2fde4374b747cd1bf447ab` :

- [Renommage individuel](https://github.com/GNOME/nautilus/blob/283739c868edcceb4e2fde4374b747cd1bf447ab/src/nautilus-rename-file-popover.c)
- [Vues, raccourcis, presse-papiers et modèles](https://github.com/GNOME/nautilus/blob/283739c868edcceb4e2fde4374b747cd1bf447ab/src/nautilus-files-view.c)
- [Opérations de fichiers](https://github.com/GNOME/nautilus/blob/283739c868edcceb4e2fde4374b747cd1bf447ab/src/nautilus-file-operations.c)
- [Nommage des liens](https://github.com/GNOME/nautilus/blob/283739c868edcceb4e2fde4374b747cd1bf447ab/src/nautilus-filename-utilities.c)
- [Panneau des emplacements](https://github.com/GNOME/nautilus/blob/283739c868edcceb4e2fde4374b747cd1bf447ab/src/nautilus-sidebar.c)

API publiques utilisées : [GIO File](https://docs.gtk.org/gio/iface.File.html), [GDK Drag](https://docs.gtk.org/gdk4/class.Drag.html), [GTK Popover](https://docs.gtk.org/gtk4/class.Popover.html), [Adwaita TabView](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/class.TabView.html).

**Déduit/adapté** : les deux panneaux, les critères médias, les légendes et la restauration de session restent des fonctions de Mirivue. Les dates emploient l'API publique GLib ; Nautilus emploie un formateur ICU interne : leur formatage n'est pas garanti identique caractère par caractère. Les composants privés de Nautilus ne sont pas des widgets publics réutilisables.

**Non vérifié sur un bureau réel** : comparaison visuelle et gestes physiques GNOME/Wayland, serveur SMB/SFTP authentifié, droits spécifiques des serveurs et périphériques amovibles réels. Les essais Xvfb ne prouvent pas une identité visuelle ou comportementale intégrale avec Nautilus.

## Points qui restent ouverts

1. Sauvegardes des métadonnées : conserver les sauvegardes successives actuelles, ou adopter la conservation du premier original avec provenance comme KDE ? Aucun ancien fichier de sauvegarde n'est effacé ou migré ici.
2. Recherche de contenu : l'intégration de LocalSearch nécessite un choix explicite sur la disponibilité de ce composant. Aucun indexeur Python n'est ajouté.
3. Archives étendues : une couverture supplémentaire via GNOME Autoar ou un gestionnaire d'archives installé nécessite un choix sur les composants facultatifs. Le traitement actuel des formats supportés reste en place.
4. Aperçus, analyses et métadonnées distants complets, annulation des opérations distantes : non promis ; disponibilité dépendant du backend. La navigation et les transferts utilisent GIO/GVfs.
5. Presse-papiers d'images et création/collage de liens par raccourcis : restant à compléter. Ne pas ajouter le collage arbitraire de texte au nom d'une convention Nautilus non vérifiée.
6. Gestionnaire par défaut / FileManager1 : choix explicite par bureau, sans modifier les associations automatiquement.

Le minimum déclaré est corrigé à libadwaita 1.5 : les dialogues natifs déjà employés nécessitent cette version (documentation officielle Adw.PreferencesDialog et Adw.AlertDialog). Ce n’est pas une bibliothèque supplémentaire.

Pas de dépendance KDE, KIO, Qt ou PySide. Pas de nouvelle dépendance obligatoire de l'application, pas de couleur d'interface imposée. Réglages, vidéos, XMP et anciennes sauvegardes conservés.
