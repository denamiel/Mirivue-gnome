# Rapport fonctionnel — Mirivue Qt 0.5.37

Rapport établi en lisant la version Qt installée (0.5.37), la base GTK installée (0.4.39), puis la copie de travail GTK préparée en 0.5.37. Il distingue les fonctions disponibles des manques ; partager le numéro de version ne signifie pas que les deux éditions ont déjà une parité complète.

## Fonctions de Mirivue Qt 0.5.37

### Navigation et présentation des fichiers

- Gestionnaire de fichiers à un ou deux panneaux, avec navigation indépendante, onglets, historique précédent/suivant, dossier parent, accueil, chemins éditables, recherche dans le dossier et raccourcis clavier.
- Emplacements KDE sous Plasma, volumes et périphériques, réseau KIO, corbeille, fichiers récents et ouverture avec les applications associées.
- Vues Détails et Icônes ; colonnes masquables, profils (dont Médiathèque), tri, ordre et largeur mémorisés séparément pour chaque panneau, largeur automatique, remplissage de la vue et redimensionnement.
- Affichage des fichiers cachés, des miniatures, panneau d’aperçu, aperçu automatique du premier fichier et suivi sélectif des changements externes.
- Colonnes de base (nom, taille, dates, type) et données audio/vidéo (durée, dimensions, débit, état et autres informations disponibles).
- Sélection multiple, sélection rectangulaire, glisser-déposer, menus contextuels de fichier, de dossier, de panneau vide et d’en-tête.
- Informations par panneau sous chaque vue (éléments affichés, erreurs et espace libre), tandis que la barre d’état reste réservée à l’état général.

### Opérations sur les fichiers

- Création de dossier, ouverture et ouverture avec, renommage F2, renommage en masse, copie, couper/coller, duplication, déplacement, déplacement vers un nouveau dossier, glisser-déposer et copie du chemin.
- Envoi à la corbeille, restauration, vidage, suppression définitive avec confirmation, ouverture du terminal et propriétés.
- Transferts en arrière-plan avec progression, annulation, suspension/reprise et historique des opérations.
- Opérations distantes et inter-volumes par KIO ; annulation et rétablissement KIO ; dialogues de conflit laissés au traitement natif KIO.
- Rafraîchissement et arrêt du chargement ; protection contre les opérations concurrentes sur les mêmes fichiers.

### Aperçus et médias

- Aperçu intégré des images, vidéos, sons et documents pour lesquels un greffon Plasma/KIO est disponible.
- Lecture multimédia dans le panneau, commandes de lecture, recherche temporelle, volume, navigation dans une sélection et présentation en plein écran.
- Vignettes, y compris celles fournies par KIO pour les documents ; résultat dépendant des greffons installés et des vignettes intégrées.
- Métadonnées visibles/éditables pour les formats pris en charge ; colonnes vidéo informées rapidement par FFprobe et résultats conservés avec la signature du fichier.
- Historique de lecture local, optionnel et effaçable ; récents optionnels ; aucun envoi automatique des fichiers en ligne.

### Analyse et organisation des médias

- Lecture des informations courantes d’un fichier ; lecture explicite des métadonnées manquantes plutôt qu’une analyse profonde globale au démarrage.
- Calcul de durée totale, mesure du débit vidéo et comparaison, vérification de lecture/décodage, mesure de netteté, correction suggérée d’extension et recherche de doublons exacts.
- Écriture éventuelle des débits calculés, sauvegarde de l’original, métadonnées, notes, étiquettes, qualité personnelle, collections et organisation en sous-dossiers.
- Résumés, résultats d’analyse, export CSV, erreurs détaillées et file d’opérations consultable.

### Configuration et intégration Plasma

- Langue, thème système, colonnes, aperçus/lecture, dossier de démarrage, affichage, barre d’outils et outils externes configurables.
- Apparence Plasma laissée au thème, icônes du thème système, menus et boîtes de dialogue KDE/KIO, emplacements partagés avec Dolphin, volumes et opérations suivis par les services KDE.
- L’application Qt est installée séparément ; elle doit rester intacte pendant la mise à niveau GTK.

## État de la base GTK 4/libadwaita avant cette correction

La base GTK installée en 0.4.39 possède déjà : deux panneaux, onglets, vues Détails/Icônes, profils et disposition de colonnes propres à chaque côté, sélection multiple, glisser-déposer local, recherche, signets GTK lus, montages visibles, corbeille, opérations en arrière-plan, renommage (simple et en masse), métadonnées/collections/étiquettes, analyses vidéo, lecteur intégré, plein écran et préférences libadwaita.

Les écarts qui empêchent de la déclarer équivalente à Qt sont notamment :

- pas d’aperçu via le registre natif des miniatures GNOME pour PDF et formats bureautiques ; le générateur personnalisé ne traitait que médias/images ;
- la barre d’information n’affiche que le panneau actif, au lieu d’informations stables sous chacun des deux panneaux ;
- les favoris propres à Mirivue restent mêlés aux signets GTK, alors que la base Qt a abandonné son gestionnaire de favoris indépendant ;
- l’exploration et les opérations de fichier passent largement par `pathlib`, donc uniquement par des chemins locaux ; le réseau monté via GVfs est affiché partiellement mais n’est pas navigable comme un vrai emplacement distant ;
- l’historique GTK des tâches ne constitue pas encore un historique d’annulation/rétablissement équivalent à KIO ;
- le panneau Emplacements et les périphériques n’ont pas encore toutes les actions de montage/démontage/éjection et de mise à jour de la liste native ;
- plusieurs commandes et libellés doivent être harmonisés avec la version Qt ; les conventions de placement doivent toutefois rester celles de GNOME.

## Stratégie GNOME retenue

La version GNOME demeure une application GTK 4/libadwaita indépendante, sans Qt, PySide, KDE ou KIO. Les interfaces utilisent `Adw.ApplicationWindow`, `Adw.HeaderBar`, actions `Gio.SimpleAction`, menus `Gio.Menu`/`Gtk.PopoverMenu`, `Gtk.ColumnView`, `Gtk.GridView`, et les couleurs/icônes fournis par GTK et le thème. Les fichiers et volumes doivent être pris en charge par `Gio.File`, `Gio.VolumeMonitor` et GVfs ; les listes par des modèles GTK asynchrones ; les vignettes par la fabrique GNOME et les greffons `.thumbnailer` installés. L’interface peut réutiliser les libellés et fonctions de Mirivue Qt tout en respectant les conventions GNOME de menus, en-tête, préférences et navigation.

Références officielles : [GNOME HIG — panneaux latéraux](https://developer.gnome.org/hig/patterns/nav/sidebars.html), [documentation GTK 4](https://docs.gtk.org/gtk4/), [GIO — fichiers et opérations asynchrones](https://docs.gtk.org/gio/iface.File.html), [GNOME Desktop ThumbnailFactory](https://gnome.pages.gitlab.gnome.org/gnome-desktop/html/gnome-desktop3/gnome-desktop3-GnomeDesktopThumbnailFactory.html), [GtkPlacesSidebar GTK 3](https://gnome.pages.gitlab.gnome.org/gtk/gtk3/class.PlacesSidebar.html). `GtkPlacesSidebar` est un widget GTK 3 ; GTK 4 ne fournit pas ce widget équivalent. Pour se rapprocher de Nautilus en GTK 4, Mirivue garde donc sa liste latérale GTK 4, mais la branche aux signets GTK et aux volumes GIO. Les opérations de navigation et de transfert GIO sur des URI distantes restent à achever avant de revendiquer un comportement Nautilus complet.

## Changements réalisés dans la base GTK 0.5.37

- La liste privée des favoris Mirivue est retirée des réglages. Au premier lancement mis à jour, les anciens favoris locaux sont fusionnés une fois dans le fichier de signets GTK 4 ; les signets GTK existants et leurs URI distantes sont conservés. Un clic droit sur un signet permet de le retirer des emplacements ; « Ajouter aux emplacements » écrit désormais dans la même liste GTK.
- Le panneau latéral regroupe les emplacements, favoris, réseau et périphériques. La liste se reconstruit quand GIO signale l’ajout, le retrait ou le changement d’un volume. Les volumes non montés peuvent être montés ; les volumes montés proposent démontage ou éjection suivant ce que GIO signale.
- Le sélecteur entre « Emplacements » et « Arborescence » a été retiré : le panneau reste en permanence sur les emplacements, comme la navigation latérale de GNOME Files. L’arbre séparé et son scan de dossiers ont été supprimés.
- Les aperçus de formats autres que les médias passent d’abord par la fabrique de vignettes GNOME, qui consulte les greffons `.thumbnailer`. Le code ne dépend ni de KIO ni d’un éditeur bureautique. Poppler-Glib rend les pages PDF en arrière-plan pour le plein écran ; les flèches et la molette verticale parcourent les pages. Le double-clic sur un autre document lance l’application associée par GIO, comme dans Nautilus.
- Chaque panneau possède désormais sa ligne d’information, avec le nombre affiché et les erreurs à gauche et l’espace libre à droite. La barre basse générale garde le fichier sélectionné et les messages d’application.
- Les styles d’état/selection et les couleurs personnalisées de la sélection et du glisser-déposer ont été retirés là où GTK/Adwaita peut peindre nativement ces états. Les préférences ne gèrent plus une copie parallèle des favoris.
- Les chaînes visibles du panneau, de l’action d’ajout et de la boîte À propos sont harmonisées avec « Mirivue » et « Emplacements » ; la version GTK est numérotée 0.5.37. L’installation Qt n’est pas remplacée.

## Limites de parité encore ouvertes

- Le navigateur reste construit autour de `pathlib.Path`, `os.scandir` et d’outils locaux. Les URI GVfs distantes sont préservées dans les signets et visibles dans la liste, mais leur ouverture/navigation/transfert depuis Mirivue n’est pas encore prise en charge. Le véritable équivalent GNOME de KIO est `GFile`/GIO avec GVfs ; ajouter seulement `Gio.File` dans la barre latérale ne suffit pas à remplacer KIO.
- Les opérations locales s’exécutent en file de fond, mais l’annulation/rétablissement n’est pas encore équivalente aux opérations réversibles KIO de Qt. Les conflits et l’intégration aux transferts GNOME doivent eux aussi être repris par les API GIO et dialogues adaptés.
- Le plein écran multipage est ajouté pour PDF avec Poppler-Glib. Les documents bureautiques peuvent recevoir une vignette si le `.thumbnailer` correspondant est installé, mais ils ne sont pas rendus comme pages navigables : GTK/GNOME n’offre pas un moteur de rendu commun pour DOCX/XLSX/PPTX/ODT. Ils s’ouvrent via l’application associée du système.
- La version GTK est donc une édition GNOME native en cours d’alignement, pas encore l’équivalent fonctionnel complet de Qt 0.5.37. Ces limites sont affichées ici pour éviter de masquer une régression de portée.

## Composants système observés sur cette machine

CachyOS a GTK 4.22, libadwaita 1.9, PyGObject, GIO, GVfs, gnome-desktop-4, Poppler-Glib, des greffons GNOME pour PDF et documents bureautiques, ainsi que FFmpeg/FFprobe, MediaInfo et ExifTool. Aucun composant Qt, KDE ou KIO n’est requis pour la variante GTK. Les aperçus de formats additionnels dépendent des greffons `.thumbnailer` que la distribution fournit ; la lecture vidéo dépend des greffons GStreamer disponibles. Il n’y a rien à installer pour ces composants sur cette machine.
