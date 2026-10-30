# Journal des modifications — Mirivue GNOME GTK4

## 1.0.0-beta.2 — 30 octobre 2026

- Actualisation automatique des dossiers affichés avec les moniteurs natifs GIO, sans interrupteur dans les Préférences.
- Ancien réglage `monitor_external` ignoré au chargement et omis à l'enregistrement, sans modifier les autres préférences.
- Surveillance locale et GIO/GVfs systématique lorsque le backend le permet ; F5 reste disponible en cas d'absence de surveillance.

## 1.0.0-beta.1 — 30 octobre 2026

- Première bêta 1.0 de l'édition GNOME ; identité de l'application et chemins des réglages conservés.
- Sauvegarde du premier original lors des modifications de métadonnées, avec suivi de provenance et contrôle avant réutilisation.
- Les anciennes sauvegardes successives ne sont ni supprimées ni automatiquement adoptées comme premier original.
- Refus des sauvegardes inconnues, incomplètes ou modifiées ; conservation de l'original en cas d'échec ou d'annulation.
- Versions adaptées aux paquets : Fedora `1.0.0~beta.1`, Arch `1.0.0beta1`, Python `1.0.0b1`, avec transition prévue vers la version stable.

## 0.6.24 — 30 octobre 2026

- Protection des racines de volumes avant suppression et vérification de la sélection.
- Glisser-déposer : sous-dossier survolé, dépôt dans le même panneau, touches de copie/déplacement/lien.
- F2 individuel : popover GTK suivant Nautilus ; renommage multiple conservé.
- Annulation des transferts groupée par action ; contrôle des dossiers copiés avant retrait.
- Propriétés : totaux GIO asynchrones pour les dossiers et sélections multiples.
- Recherche récursive sans texte avec critères, recherche de noms GVfs et signalement des erreurs d’accès.
- Raccourcis Nautilus complétés ; la molette des images reste active sans régler le lecteur audio/vidéo.

- Fusion explicite des dossiers, décisions par conflit et conservation des éléments ignorés.
- Menus et réorganisation des signets, disponibilité native des emplacements récents.
- Modèles XDG Templates surveillés par GIO, création sans modifier le modèle.
- Restauration facultative des onglets et des deux panneaux, sans enregistrer les mots de passe d'URI.
- Préférences propres à Mirivue pour les vues par dossier, les légendes et les dates régionales.
- Compteurs incrémentaux et correction du contrôle des formats du presse-papiers.
- Minimum libadwaita déclaré corrigé à 1.5, correspondant aux dialogues natifs déjà utilisés ; aide française/anglaise actualisée.
- Limites et choix encore ouverts documentés dans NATIF-GNOME-0.6.24.md.

## 0.6.23 — 30 octobre 2026

- Onglets natifs Adw.TabView/TabBar : déplacement, détachement, réouverture et aperçu adaptatif.
- Bilan de renommage par ligne : noms inchangés, changements et conflits, sans couleurs imposées.
- Recherche par nom cohérente en mode local/récursif ; résumé limité aux éléments sélectionnés ou affichés.
- Tri des noms GLib ; attributs caché et sauvegarde fournis par GIO.
- Dossiers GVfs dans les vues communes, inventaire et surveillance Gtk.DirectoryList.
- Presse-papiers distant GNOME, conservation des URI ; ouverture de plusieurs emplacements.
- Choix d’application pour une sélection hétérogène avec recherche.
- Réglages, fichiers personnels et anciennes sauvegardes conservés.

## 0.6.22

- Préparation de paquets natifs Fedora/COPR et Arch/CachyOS, sans dépendances KDE.
- Distribution Python construite avec les ressources de langue et d'aide, les icônes et un point d'entrée `mirivue-gnome`.
- Lanceur de paquet portable : suppression du chemin personnel `/home/p`.
- Tests GitHub Actions pour GTK4, la fenêtre réelle, Fedora 44/45 et Arch ; publication d'une version seulement après succès des contrôles.
- Transition explicite et réversible de l'ancien lanceur personnel, sans modifier les réglages.
- GPL-3.0-or-later retenue pour l'édition GNOME, avec texte de licence, métadonnées des paquets et affichage légal natif dans À propos.
- Correction du menu de débordement de la barre de chemin lorsqu'il masque des segments, et contrôle des exceptions des callbacks dans le test de fenêtre.
- La recette Fedora inclut les fichiers compilés générés pour le script de transition.

## 0.6.21

- Les 12 derniers messages destinés à l’utilisateur qui échappaient à la traduction passent par `tr()`/`trf()` : presse-papiers, archives, accès GVfs, aperçu d’image, avertissements de fin de copie distante, progression de l’analyse et de la vérification de lecture ; 9 traductions anglaises ajoutées (les autres existaient déjà).
- Test de traduction strict : tout texte de plusieurs mots passé à une exception, à `notify()`, `report()` ou `progress()` doit passer par `tr()`/`trf()`, quelle que soit sa formulation. L’ancien test, fondé sur la détection d’accents et de mots courants, laissait passer « Type de fichier distant non pris en charge. » ; le nouveau échoue sur les sources 0.6.20.
- Installateur : `zenity` reçoit `--no-markup`. Sans cette option, un message contenant `&` ou `<` (chemin « Films & Séries », par exemple) était remplacé par « An error has occurred. ».
- Installateur : l’en-tête du `.run` utilise `/usr/bin/python3`, comme le reste de l’installation, même si un environnement Python personnel (pyenv, conda) est actif.
- Les six erreurs jusque-là ignorées sans trace (miniatures, aperçus, pochettes, balises audio, nettoyage d’une copie distante, enregistrement d’une erreur d’analyse) sont consignées dans `mirivue.log` ; chaque ligne du journal est désormais datée.
- Limite connue : les libellés de menus et de colonnes restent hors de ce contrôle automatique, car ils sont traduits au moment de l’affichage.

## 0.6.20

- Correction : chaque bouton « Éjecter / Démonter » du panneau latéral applique l’action de son propre volume. Auparavant, tous les boutons reprenaient le choix du dernier volume de la liste : une clé USB pouvait être démontée au lieu d’être éjectée lorsqu’un partage réseau était aussi monté. Défaut présent au moins depuis 0.6.17 ; test de comportement ajouté.
- 51 messages d’erreur qui ne passaient pas par la traduction (archives, annulation/rétablissement, accès GVfs, droits d’accès, sortie audio, presse-papiers, contrôle des dépendances) passent désormais par `tr()`/`trf()` ; 42 traductions anglaises ajoutées. *Rectificatif (0.6.21) : le test ajouté ici reposait sur une heuristique et laissait passer 8 autres messages d’erreur ; remplacé par une règle stricte en 0.6.21.*
- Barre d’état anglaise : les tailles s’affichent en KiB, MiB… au lieu de Kio, Mio….
- L’installateur n’embarque plus `docs/historique/` (archives de notes de version), qui reste dans les sources.
- Rectification du journal de 0.6.19, qui surestimait la couverture des traductions.
- Limite connue : une centaine de chaînes françaises restent hors `tr()` ; la plupart sont des libellés de menus et de colonnes traduits à l’affichage, mais quelques messages (avertissements de copie, notifications) peuvent encore apparaître en français dans l’interface anglaise.

## 0.6.19

Version de maintenance : comportement inchangé, hormis le nom proposé pour un nouveau dossier et la langue de certains messages dans l’interface anglaise.

- Code reformaté automatiquement (ruff format), structure du programme vérifiée identique fichier par fichier ; imports et variables inutilisés retirés.
- Un seul module de traduction : `core/i18n.py`, qui ne traduisait rien, est supprimé. Les messages du cœur qui passaient déjà par `tr()` (déplacements, métadonnées, renommage, remux…) s’affichent désormais en anglais dans l’interface anglaise ; 107 traductions ajoutées. Les identifiants internes ne passent plus par la traduction. *Rectificatif (0.6.20) : environ cinquante messages d’erreur sans `tr()` (archives, annulation, accès GVfs, droits, audio) restaient en français ; ils sont traités en 0.6.20.*
- Traductions anglaises ajoutées pour « Renommer le contenu du dossier… », « Supprimer définitivement… » et « Dossier sans titre ».
- « Nouveau dossier » propose « Dossier sans titre », puis « Dossier sans titre 2 », « 3 »… si le nom est pris ; même règle pour « Nouveau dossier contenant la sélection… ».
- Code Windows et macOS retiré (non utilisé sous GNOME ; la branche Windows était en outre défectueuse).
- Tests : 4 tests désynchronisés du code réparés (objets simulés incomplets), tests d’interface rendus indépendants de la langue du système, tests de traduction et de nommage ajoutés (125 tests).
- Un seul `CHANGELOG.md` ; les 116 anciens fichiers de version et les deux rapports de validation sont archivés dans `docs/historique/`.
- `pyproject.toml` ajouté (configuration de ruff).

## 0.6.18

- « Nouveau dossier » propose désormais un nom valide par défaut (le champ contenait auparavant un espace, refusé à la validation).
- Lorsque le système de fichiers refuse le renommage sans écrasement (certains montages FUSE ou réseau), les déplacements utilisent une méthode de repli qui n'écrase jamais un élément existant : lien physique puis retrait de l'ancien nom pour les fichiers et liens, contrôle d'existence puis renommage pour les dossiers et les supports sans liens physiques.
- Huit tests ajoutés (tests/test_rename_fallback.py).

## 0.6.17

- L'aperçu de glisser-déposer empile les icônes ou vignettes des quatre premiers fichiers sélectionnés, selon leur contenu, comme Nautilus 51.1.
- Lorsque plusieurs éléments sont sélectionnés, une pastille affiche leur nombre total, même si seuls quatre aperçus sont visibles.
- Les icônes proviennent du thème GIO et la pastille utilise les classes de style d'Adwaita, sans couleurs codées en dur.
- La sélection, la destination et les règles de copie ou déplacement ne changent pas.

## 0.6.16

- Après F2, le nom affiché reste le nom réel du fichier pendant l'opération asynchrone.
- Si le nom demandé existe déjà ou que le renommage échoue, l'interface ne montre plus à tort le nom proposé.
- Après succès, la mise à jour du dossier affiche le nouveau nom comme auparavant.
- Aucun réglage ou fichier utilisateur n'est modifié par cette mise à jour.

## 0.6.15

- Un clic simple dans la zone vide d’un panneau termine sans valider l’édition F2 et désélectionne les fichiers après le geste GTK.
- Le clic est écouté sur toute la zone défilante, y compris sous la dernière ligne ; cliquer sur un fichier conserve le comportement de sélection GTK.
- Le retour du focus après F2 n’est plus appliqué lorsque le clic sur le fond annule l’édition.
- Le renommage en masse par F2 sur plusieurs fichiers reste inchangé.

## 0.6.14

- Pendant un renommage F2, la saisie dans l’éditeur GTK natif ne déclenche plus la recherche de fichiers.
- Une seule demande de démarrage d’édition est conservée par ligne ; les demandes devenues obsolètes après recyclage d’une ligne sont ignorées.
- À la fermeture de l’éditeur, le focus revient à la vue seulement s’il se trouve encore dans l’éditeur. Un éditeur recyclé annule proprement son édition.
- F2 sur une sélection multiple conserve le renommage en masse.

## 0.6.13

- Pour le renommage d’un seul fichier par F2, l’éditeur GTK sélectionne le nom avant la dernière extension. Le nom complet reste librement modifiable.
- Un dossier ou un fichier sans extension est sélectionné en entier.
- Pour une sélection de plusieurs fichiers, F2 continue d’ouvrir le renommage en masse sans modification de son comportement.

## 0.6.12

- Les vues liste et grille sont des choix de Mirivue, enregistrés séparément pour les panneaux gauche et droit et restaurés au prochain lancement.
- Mirivue ne lit plus la préférence de vue ni le tri « dossiers avant les fichiers » de GNOME Files. Ce dernier conserve le réglage Mirivue déjà enregistré.
- Aucun fichier multimédia, signet ou autre préférence n'est modifié par la mise à jour.

## 0.6.11

- Les poignées de réorganisation des barres d’outils et des colonnes utilisent l’icône GNOME `list-drag-handle-symbolic` lorsqu’elle est fournie par le thème, avec un repli symbolique thématisé pour éviter l’icône manquante.
- Aucun changement à la disposition enregistrée ou aux gestes de déplacement.

## 0.6.10

- La barre de chemin possède une surface distincte de l’en-tête, selon la règle graphique du code de GNOME Files. Le mélange de couleur utilise `currentColor` fourni par le thème, sans couleur codée en dur.
- La classe `linked`, incompatible avec les boutons `flat` selon la documentation libadwaita, est retirée de cette barre.
- Les actions de navigation, le menu du dossier et les réglages existants restent inchangés.

## 0.6.9

- Le panneau d’emplacements utilise une plage de largeur plus proche de celle de GNOME Files, tout en réservant de la place au titre « Mirivue ».
- Aucun autre réglage, menu ou contenu utilisateur n’est modifié.

## 0.6.8

- Le volume non monté s’ouvre par activation de sa ligne dans Emplacements, sans bouton « Monter » redondant.
- Le bouton natif d’éjection ou de démontage des volumes montés reste disponible.
- La largeur du panneau est réduite en préservant la place nécessaire au titre « Mirivue » dans l’en-tête.
- Les réglages et les données existants sont conservés.

## 0.6.7

- Deux en-têtes natifs libadwaita : celui des emplacements comprend les commandes de fenêtre, Recherche, le titre Mirivue et le menu principal, dans la zone stylée par Adwaita.
- Largeur minimale du panneau d’emplacements augmentée pour afficher le titre complet.
- Recherche et menu principal restent accessibles et sortent de la personnalisation de la barre d’outils ; les autres choix de l’utilisateur sont conservés.
- Aucun changement aux données ou aux fichiers vidéo.

## 0.6.6

- Un glisser commencé sur un fichier donne temporairement la priorité à la source de glisser-déposer GTK, puis rétablit la sélection rectangulaire à la fin du geste.
- La sélection rectangulaire reste disponible lorsque le glisser commence dans un espace vide.
- En vue détaillée, chaque cellule visible de la ligne peut servir de point de départ au glisser-déposer.
- Les réglages et fichiers personnels ne sont pas modifiés.

## 0.6.5

- Le réglage « Réutiliser la fenêtre existante » est présenté sous la forme « Autoriser plusieurs instances de Mirivue ».
- Le commutateur inverse uniquement l'affichage et l'écriture de la préférence existante `reuse_window`. La préférence enregistrée et son effet restent inchangés après la mise à jour.
- Le changement s'applique au prochain lancement.

## 0.6.4

Le menu contextuel d’une sélection multiple propose une seule entrée
« Renommer », comme GNOME Files. Elle et F2 ouvrent le même éditeur de
renommage en masse. Le renommage d’un élément et celui du contenu immédiat
d’un dossier conservent leurs comportements distincts.

Les réglages utilisateur ne sont pas modifiés.

## 0.6.3

Les Préférences s’ouvrent dans une fenêtre libadwaita indépendante, non modale,
plutôt que dans une couche de la fenêtre principale. Les pages, la recherche et
les réglages existants sont conservés. Cette fenêtre peut être déplacée par le
gestionnaire de fenêtres.

## 0.6.2

Corrige le contrôle de conformité des menus de 0.6.1 : la nouvelle action
« Renommer le contenu du dossier… » est désormais attendue par le test.
Les fonctions et les réglages de 0.6.1 sont conservés.

## 0.6.1

- Menu contextuel d’un dossier : **Organiser → Renommer le contenu du dossier…**. F2 continue de renommer le dossier lui-même.
- Le contenu immédiat inclut fichiers masqués et sous-dossiers ordinaires, sans descendre dans ces derniers ; les liens symboliques ne sont pas transmis au renommage.
- La commande utilise l’outil intégré ou le programme externe configuré, vérifie les noms dans l’éditeur intégré et conserve le suivi des renommages.
- Une analyse de vignette terminée après la modification de son fichier ne remplace plus la vignette de la nouvelle version.

L’installateur conserve les réglages et l’ancienne version pour un retour arrière avec `--rollback`.

Tests ciblés réussis. Les tests GTK complets doivent être exécutés sur une session équipée de PyGObject ; l’environnement de préparation ne dispose pas du module `gi`.

## 0.6.0

Version stable de la série 0.6.0, issue de RC29. Cette livraison ne modifie pas les fonctions ni les réglages de RC29 : seule la version affichée et la documentation changent.

### Validation

- 87 tests unitaires et contrôle de création de fenêtre réussis sur CachyOS GNOME avec RC28, selon le résultat fourni par l’utilisateur.
- Essais pratiques et visuels de RC29 déclarés validés par l’utilisateur.
- Compilation, syntaxe, contrôles d’archives et tests sans interface exécutés sur le paquet final dans l’environnement de préparation.
- Les essais sur Debian, Ubuntu et Fedora ne sont pas encore réalisés : aucun paquet pour ces distributions n’est annoncé comme compatible.

### Installation

Fermer Mirivue, puis lancer `Mettre-a-jour-Mirivue-GNOME-vers-0.6.0.run`. L’installateur vérifie l’archive avant de remplacer l’application, conserve la version précédente et ne remplace pas les réglages sous `~/.local/state/mirivue-gtk4`.

Après l’installation, `~/.local/share/mirivue-gtk4/Verifier-installation-GNOME.sh` vérifie la version, le lanceur, l’icône, les composants GTK et l’affichage d’une fenêtre temporaire.

### Retour arrière

Le même fichier `.run` avec `--rollback` restaure la version précédente. Fermer Mirivue avant l’opération.

## 0.6.0-rc29

- Laisse GTK déterminer la taille minimale de la fenêtre et libadwaita celle du panneau d'aperçu ; conserve la taille initiale et les bornes adaptatives du conteneur libadwaita.
- Préférences → Composants précise les fonctions affectées lorsqu'un outil facultatif est absent et inclut `pactl` ; le diagnostic local le mentionne aussi.
- Les actions de vérification de lecture et de copie MKV sont désactivées, avec explication, si `ffmpeg` manque.
- Ajoute une grille de validation pratique GNOME limitée à des fichiers d'essai.
- Ne change pas les réglages de l'utilisateur ni les fichiers multimédias.

## 0.6.0-rc28

- Refuse les retours à la ligne dans le nouveau nom d'un signet avant de retirer les espaces extérieurs. Le renommage invalide ne modifie pas le fichier partagé des signets GTK4.
- Conserve la correction RC27 des droits d'exécution du vérificateur.
- Aucun réglage ni fichier personnel modifié pendant la mise à jour.

## 0.6.0-rc27

- Rend `Verifier-installation-GNOME.sh` exécutable après extraction de la mise à jour.
- Ajoute un test de ce droit d'exécution dans le scénario d'installation et de retour arrière.
- Aucun réglage ni fichier utilisateur modifié.

## 0.6.0-rc26

- Le vérificateur d'installation lit désormais la version dans les sources livrées et accepte les chemins comportant des espaces.
- Nouveau contrôle explicite `--window-smoke-test` : ouvre une vraie fenêtre GTK dans un état temporaire, attend son affichage, puis ferme l'application sans toucher aux réglages de l'utilisateur. Le vérificateur applique un délai de 25 secondes.
- Vérification des versions minimales GTK 4.12 et libadwaita 1.4 avant mise à jour ; documentation de stabilisation corrigée pour distinguer le contrôle avant remplacement du contrôle graphique après installation.
- Les réglages et fichiers personnels sont préservés pendant la mise à jour.

## 0.6.0-rc25

- Raccourcit le menu principal en conservant Nouveau dossier, Annuler/Rétablir, outils multimédias, diagnostic, arrêt du chargement, médias récents et collections lorsqu'ils existent, ainsi que les entrées GNOME standard.
- Les options de colonnes et de personnalisation de la barre d'outils se trouvent dans Préférences > Apparence ; la recherche et les vues restent dans l'en-tête ou leurs raccourcis.
- Les actions des opérations restent accessibles au moyen du bouton dédié et de sa fenêtre.
- Préserve tous les réglages de l'utilisateur pendant la mise à jour.

## 0.6.0-rc24

- Corrige le popover des opérations vides : le message utilise un libellé GTK sans retour à la ligne, dont la largeur naturelle empêche l'affichage vertical des caractères.
- Aucun réglage ni fichier utilisateur modifié par cette correction.

## 0.6.0-rc23

- Lorsque la file et l'historique des opérations sont vides, le bouton Opérations ouvre un `Gtk.Popover` ancré au bouton visible, avec une `Adw.StatusPage` compacte indiquant « Aucune opération en cours ».
- Dès qu'une opération ou une entrée d'historique existe, la fenêtre des opérations actuelle reste accessible. Une fenêtre déjà ouverte n'est pas remplacée.
- Aucun réglage, fichier utilisateur, couleur ou dimension d'interface n'est modifié.

## 0.6.0-rc22

- Les nouveaux onglets affichent le nom du dossier sans l'ellipse produite par une contrainte de largeur. `Gtk.Notebook` conserve sa gestion native du débordement des onglets.
- Le titre des onglets est mis à jour lors de la navigation locale, distante, dans la corbeille et dans les favoris, y compris pour le premier onglet à en-tête simple.
- Le nom complet est également disponible dans l'infobulle de l'onglet.

## 0.6.0-rc21

- En mode deux panneaux, le compteur de dossiers et fichiers du panneau actif emploie la classe `.accent` de libadwaita. Le compteur de l'autre panneau garde le style normal.
- Le marqueur suit les changements de panneau, d'onglet et de visibilité du second panneau. Hors mode deux panneaux, les deux compteurs gardent le style normal.
- Aucune couleur, bordure ni dimension personnalisée n'est ajoutée. Les réglages et les données restent inchangés.

## 0.6.0-rc20

- Le clic droit sur un segment du chemin utilise un menu GIO/GTK contextuel à la position du pointeur : nouvel onglet, nouvelle fenêtre, propriétés, copie du nom et copie du chemin. Chaque action vise le dossier cliqué.
- Le libellé de chaque segment n'a plus de limite arbitraire de caractères ; la mesure GTK existante garde les segments récents visibles lorsque la barre se rétrécit.
- Le mode texte par clic sur le dossier courant ou Ctrl+L et le retour aux boutons après perte du focus sont conservés.
- La mise en évidence du panneau actif dans la vue à deux panneaux reste une proposition distincte : GNOME Files n'a pas d'équivalent natif direct de cette vue.

## 0.6.0-rc19

- Le menu contextuel d'un signet, y compris local, propose « Renommer… » et « Retirer des signets ». Le renommage ne touche qu'au libellé du signet GTK4, sans renommer le dossier.
- La zone des signets accepte le dépôt de dossiers locaux ; « Nouveau signet » apparaît pendant le survol. Les signets existants et leur ordre sont conservés.
- Un volume distant monté est transmis au navigateur GIO existant pour pouvoir être ouvert dans Mirivue.
- L'apparence du panneau continue à utiliser les classes et icônes du thème GTK. Une comparaison visuelle directe avec GNOME Files reste nécessaire sur une session GNOME.

## 0.6.0-rc18

- La lecture du schéma de préférences de GNOME Files emploie `GObject.Object.get_property('settings-schema')`, conformément à PyGObject, au lieu d'un attribut direct inexistant sur `Gio.Settings`.
- Un test vérifie les changements de vue dans les deux panneaux et la prise en compte du tri après modification de la préférence GNOME Files.
- Le contrôle préalable de l'installateur reste limité au chargement des composants : le lancement réel de l'interface doit être vérifié après installation dans la session GNOME.

## 0.6.0-rc17

- Le contrôle préalable de l'installateur vérifie GTK4, libadwaita et le chargement des composants Mirivue sans ouvrir une fenêtre complète ni lancer des tâches de fond.
- La fenêtre complète reste à vérifier lors du lancement de l'application dans une session GNOME ; le contrôle préalable ne prétend plus la valider.
- Cette correction permet de poursuivre l'installation lorsque le contrôle RC16 restait bloqué et expirait au bout de 40 secondes. L'installateur conserve la version précédente pour le retour arrière.

## 0.6.0-rc16

- Le tri des dossiers avant les fichiers suit la préférence globale de GNOME Files lorsque son schéma GSettings est installé, y compris ses changements pendant l'exécution.
- La vue par défaut en liste ou en icônes suit la préférence globale de GNOME Files, sans ajouter de dépendance à Nautilus. Les dispositions propres à un dossier, la largeur et l'ordre des colonnes restent gérés par Mirivue.
- Les périphériques du panneau Emplacements utilisent leurs icônes symboliques GIO. L'action Monter porte son libellé réel ; les actions Éjecter et Démonter ne sont proposées que si le montage les autorise.
- Audit des couleurs : aucun code hexadécimal n'habille l'interface. Le blanc d'une page PDF est une surface de document et les couleurs de l'icône d'application relèvent de son identité visuelle.

La comparaison visuelle et les tests qui importent GTK nécessitent une session GNOME avec PyGObject. Les emplacements de GNOME Files ne sont pas tous reproduits : voir le compte rendu de l'audit.

## 0.6.0-rc15

- La barre de chemin laisse GTK et le thème dessiner sa surface ; le style de carte ajouté par Mirivue est retiré.
- Le bouton de débordement de la barre de chemin utilise une icône du thème et sa place est calculée à partir d’une mesure GTK, sans largeur fixée en pixels.
- Le clic droit sur un segment utilise un menu `Gio.Menu` / `Gtk.PopoverMenu` et conserve la copie du nom et du chemin.
- Les fonds particuliers des panneaux actif et inactif sont supprimés ; sélection et focus restent dessinés par GTK/libadwaita.
- L’icône d’une commande absente du thème ne devient plus artificiellement « trois points » : son libellé est affiché. À la taille normale, les icônes de la barre d’outils prennent la taille du thème ; les tailles explicitement choisies par l’utilisateur restent disponibles.
- Le damier de transparence et la bordure de la page PDF prennent leurs couleurs dans le thème. Le blanc du papier PDF reste volontairement blanc, conformément au choix d’aperçu de document.

La comparaison visuelle avec GNOME Files et la suite GTK complète doivent être exécutées dans une session GNOME avec PyGObject.

## 0.6.0-rc14

- Le tri des dossiers avant les fichiers est désactivé à la première installation, conformément au réglage initial de GNOME Files. Le choix déjà enregistré par l’utilisateur reste conservé.
- Le choix de l’application pour un seul fichier utilise `Gtk.FileLauncher` quand l’API GTK est disponible ; le cas de plusieurs fichiers reste inchangé.
- Les déplacements de fichiers via GIO utilisent son repli natif entre supports et propagent les erreurs de permission ou de réseau.
- Quand GIO ne peut pas déplacer directement un dossier entre supports, Mirivue copie son contenu dans un emplacement temporaire, contrôle la source et la copie, publie le dossier, puis supprime l’original par GIO. Si la source change pendant la copie, l’original est conservé. Une erreur de suppression est signalée.
- Aucun réglage personnel ou fichier média n’est modifié par la mise à jour.

Les tests ciblés GIO passent. Le contrôle de l’interface et la suite GTK complète restent à exécuter dans une session GNOME avec PyGObject.

## 0.6.0-rc13

- Au bas du panneau Emplacements, l’accès « Opérations » devient une icône plate à trois points alignée à gauche, avec infobulle.
- La ligne de séparation au-dessus du pied est supprimée. Le bouton d’annulation d’une analyse reste à côté lorsqu’il est utile.
- L’accès et la progression de repli dans l’en-tête, ainsi que les réglages et les fichiers personnels, sont préservés.

## 0.6.0-rc12

- La barre d’état globale est remplacée par un pied fixe sous la liste des Emplacements. Il montre la sélection, les tâches en cours, leur progression, l’annulation des analyses et le bouton Opérations.
- Lorsque la barre latérale se replie, un bouton Opérations et une progression compacte demeurent accessibles dans l’en-tête. Le menu principal conserve son accès aux opérations.
- La préférence « Afficher la barre d’état » est supprimée ; les autres réglages et les résumés propres à chaque panneau sont conservés.
- L’aide et la vérification graphique du démarrage sont mises à jour.

## 0.6.0-rc11

Le test d’enrichissement des dossiers simule désormais l’état `search_recursive_active` présent sur tous les panneaux réels. Cela corrige l’erreur `AttributeError` relevée dans `test_folder_count` sous PyGObject. Aucune logique applicative, donnée utilisateur ou fichier média n’est changé.

## 0.6.0-rc10

- Correction de l’import GIO manquant lors des copies et déplacements vers un emplacement réseau.
- Retrait du calcul expérimental de débit, du code devenu inaccessible d’écriture du débit et d’anciens adaptateurs d’historique d’une architecture précédente ; maintien des contrôles MKV toujours utilisés.
- Retrait d’imports inutilisés et de traductions exclusivement liées aux anciens écrans de qualité, de netteté et d’écriture du débit.
- Mise à jour du test de recherche après suppression du filtre « Qualité » et ajout d’un contrôle statique des symboles globaux.
- Les anciens champs de cache et le marqueur de migration sont conservés pour lire les données existantes. Aucun média, compagnon XMP ou réglage de l’utilisateur n’est modifié par ce nettoyage.

La validation GTK et le test du lanceur nécessitent un système GNOME équipé de PyGObject.

## 0.6.0-rc9

Alignement de l’interface GTK4 sur les simplifications KDE 1.0.0 RC22–RC30, avec GIO/libadwaita et les conventions de GNOME Files.

- Retrait du score subjectif de qualité, de la colonne et de ses profils ; migration sélective du cache en conservant métadonnées, étiquettes et autres préférences.
- Retrait des calculs et écritures de débit ; seul le débit déclaré par le média est présenté. Durée des dossiers dans Organisation ; opérations en arrière-plan dans Opérations.
- Propriétés avec pages Général et Droits d’accès, contrôle GIO des neuf droits Unix et vérification du résultat ; refus de modifier la cible d’un lien symbolique.
- Métadonnées : bouton compact de suggestions et choix explicite entre écriture dans le fichier compatible et compagnon XMP.
- Menu « Créer un nouveau » avec dossier ou fichier texte créé sans écrasement. Terminal GNOME avec icône du thème et Alt+Maj+F4.
- Aide et traductions mises à jour, tests de migration et d’opérations locales. Aucun composant KDE/Qt/KIO requis.

L’installateur .run réalise une vérification de la fenêtre GTK avant remplacement, conserve une version précédente pour le retour arrière et préserve les réglages de l’utilisateur.

## 0.6.0-rc8

- Icônes des dossiers personnels GNOME (Bureau, Documents, Téléchargements, Musique, Images, Vidéos, Modèles et Public), du dossier personnel et des dossiers portant une icône personnalisée GIO. Les vues, les emplacements réseau et l'icône de glisser utilisent des objets `Gio.Icon` du thème actif.
- Calcul de qualité aligné sur KDE 1.0.0 RC21 : détail, bruit, compression, contraste et cadence, sans critère de définition. Cinq niveaux qualitatifs indépendants, profil Standard ou Personnalisé et six profondeurs de 5 à 30 images.
- Commande unique d'analyse prenant les préférences en compte. Nouvelle signature de cache : les scores antérieurs et ceux d'un autre profil deviennent non analysés, sans effacer les autres données.
- Aucun composant Qt, PySide, KIO ou KDE ajouté ; décodage FFmpeg existant, GIO, GTK4 et libadwaita.

## 0.6.0-rc7

- Icônes des fichiers locaux déterminées par GIO à partir du type de contenu réellement détecté, dans la tâche d'inventaire du dossier.
- Icônes GIO des emplacements réseau et de la corbeille conservées ; la liste et la grille respectent le thème GNOME et les miniatures restent prioritaires.
- Lors de l'enrichissement des métadonnées, l'icône détectée reste associée au fichier. Les entrées sans icône GIO utilisent le type MIME déduit du nom comme repli.
- Aucune nouvelle dépendance et aucun changement des réglages de l'utilisateur.

## 0.6.0-rc6

- Recherche de doublons exacts à partir du dossier actif ou du menu contextuel d'un dossier, récursive dans tous les sous-dossiers.
- Le parcours se fait dans une tâche annulable, ignore les liens symboliques et suit le réglage d'affichage des fichiers cachés. Les noms et extensions peuvent différer : seules les données strictement identiques sont regroupées.
- La fenêtre de résultats montre les chemins relatifs et un choix exclusif du fichier à conserver pour chaque groupe. Une confirmation et une nouvelle vérification précèdent toute mise à la corbeille.
- Tests des doublons entre sous-dossiers, de l'annulation et de la conservation du fichier choisi. Aucune nouvelle dépendance.

## 0.6.0-rc5

- La fenêtre autonome « Nettoyage guidé » est retirée des menus.
- La recherche propose une taille minimale en Mio et un filtre des erreurs déjà connues.
- Le bouton « Rechercher les doublons exacts… » analyse explicitement le contenu des fichiers actuellement affichés par la recherche. Il est désactivé pendant le chargement ou si moins de deux fichiers sont visibles.
- La recherche de doublons conserve le choix du fichier à garder, une nouvelle vérification des contenus et la confirmation avant la mise à la corbeille.
- Les tests de filtrage et du périmètre de l'analyse ont été complétés. Les réglages et médias restent conservés par la mise à jour.

## 0.6.0-rc4

- « Nettoyage guidé » examine les fichiers affichés dans le dossier, même lorsqu'une sélection existe.
- Son bouton de recherche des doublons est désactivé si le dossier contient moins de deux fichiers, avec une explication visible.
- Les compteurs précisent qu'ils reflètent les doublons et erreurs déjà repérés.
- La commande reste accessible dans « Outils multimédias » même sans sélection.
- Test du périmètre de recherche lancé depuis le bilan.

## 0.6.0-rc3

- La loupe, Ctrl+F et la saisie directe dans la liste ouvrent la recherche du panneau actif. La recherche par nom inclut les sous-dossiers locaux par défaut, avec une option visible pour limiter la recherche au dossier affiché. Les résultats arrivent progressivement et indiquent leur dossier parent.
- Les filtres multimédias appartiennent à la même recherche. Leur état est visible et peut être effacé ; une recherche sans résultat est signalée. Changer de dossier quitte la recherche.
- Le menu principal ne présente plus une seconde « Recherche avancée ». Le menu contextuel des médias met en avant les commandes courantes et regroupe les autres outils. La fenêtre d'outils affiche les actions applicables à la sélection.
- Libellés du terminal, de la copie d'emplacement, de l'analyse du débit vidéo et de la suspension des opérations harmonisés.
- Parcours des dossiers annulable sans suivre les liens symboliques ; tests supplémentaires pour la recherche et ses filtres.
- Mise à jour restaurable conservant les réglages et les données utilisateur. Aucun fichier média n'est modifié par la recherche.

## 0.6.0-rc2

- La navigation garde actif le panneau qui ouvre un dossier pendant le chargement de sa liste. Les événements de focus retardés de l'autre panneau ne changent plus la barre de chemin.
- L'ouverture d'un fichier ne maintient pas inutilement ce verrou de navigation.
- Test de la navigation, du focus et de la fin du chargement ajouté. Les réglages restent conservés par l'installateur.

## 0.6.0-rc1

- Gel des ajouts fonctionnels pendant la validation de stabilité GNOME.
- Contrôle graphique avant installation, vérification des actions de menu et script de contrôle après installation.
- Installation utilisateur restaurable avec `--rollback`, somme SHA-256, refus de remplacer Mirivue ouvert et conservation des réglages.
- États Annuler/Rétablir synchronisés avec l’historique ; « Détails de qualité » réservé aux vidéos analysées.
- Matrice de validation avant une éventuelle version stable dans `STABILISATION-GNOME.md`.

## 0.5.103

- Corrige la synchronisation du panneau actif après ouverture d’un dossier par une ligne : la barre de chemin suit immédiatement le panneau parcouru, sans clic dans l’espace libre.
- L’activation est confirmée après les notifications de focus de GTK, tout en laissant une navigation plus récente choisir son panneau.
- Le clic sur la barre pour saisir un chemin et la copie du nom au clic droit restent disponibles. Les réglages personnels sont conservés.

## 0.5.102

- Corrige la barre de chemin après navigation : chaque ouverture de dossier restaure d’abord le mode boutons, puis affiche les segments du nouveau dossier.
- Le clic pour saisir le chemin, Ctrl+L et le menu de copie du nom du dossier restent disponibles.
- Les réglages personnels sont conservés.

## 0.5.101

- Le clic sur le dossier courant de la barre de chemin, ou sur l’espace disponible de cette barre, affiche le champ de saisie du chemin. Ctrl+L reste disponible.
- Quand le champ perd le focus, les boutons de navigation reviennent et une saisie non validée est abandonnée. Échap ferme également le champ.
- Les segments parents conservent leur navigation au clic gauche et le menu au clic droit permet toujours de copier le nom du dossier ou son chemin.
- Les réglages personnels sont conservés.

## 0.5.100

- Le menu contextuel d’un dossier propose « Ouvrir dans un nouvel onglet ». Le dossier cliqué est conservé comme cible même si la sélection change pendant l’ouverture du menu.
- Ctrl+T continue d’ouvrir un nouvel onglet sur l’emplacement courant.
- Les réglages personnels restent conservés par l’installateur ; aucun composant KDE ou Qt ajouté.

## 0.5.99

- Corrige l’ouverture de la fenêtre « Raccourcis clavier » sous libadwaita 1.8 : chaque entrée transmet désormais son libellé et sa combinaison au constructeur natif.
- Conserve les nouveautés de 0.5.98 et les réglages de l’utilisateur.

## 0.5.98

- Fenêtre de raccourcis GNOME avec recherche et catégories sur libadwaita 1.8 ou version ultérieure ; repli GTK4 sur les versions antérieures.
- Création locale d’archives ZIP et TAR gzip à partir de la sélection, avec publication sans remplacement et annulation avant publication.
- Annulation et rétablissement étendus aux déplacements de dossiers, aux transferts de médias accompagnés de XMP et à la création de dossiers vides. Les dossiers copiés, suppressions, remplacements et opérations externes ne sont pas enregistrés dans cet historique.
- Aucun ajout de bibliothèque KDE, KIO ou Qt ; les préférences restent conservées par l’installateur.

## 0.5.97

- Sélecteur facultatif de sortie audio dans les contrôles d'aperçu des sons et vidéos, lorsque `pactl` et un serveur compatible sont disponibles.
- Le flux identifié par le PID de Mirivue est déplacé vers la sortie choisie. La sortie par défaut du système et les flux des autres applications ne sont pas modifiés.
- Le choix est mémorisé dans les préférences de Mirivue et réappliqué au prochain lancement d'un aperçu, si le périphérique reste disponible.
- Sans `pactl` ou sans flux identifiable, la lecture GTK habituelle reste utilisable. Aucun composant KDE/KIO n'est ajouté.

## 0.5.96

- La vue Réseau vide affiche un état centré et une adresse de serveur en bas du panneau, proche de GNOME Files.
- Retire les trois boutons permanents au-dessus du contenu distant.
- Copier, couper et coller sont proposés par le menu contextuel et les raccourcis habituels dans les emplacements distants.
- Les réglages de l'utilisateur sont conservés.

## 0.5.95

- Les emplacements GVfs sans chemin local se parcourent dans le panneau actif, avec navigation arrière, dossier parent, actualisation, onglets et deux panneaux.
- Sélection multiple, ouverture dans l'application par défaut et transferts GIO prudents vers le panneau local ou depuis le presse-papiers de Mirivue.
- Les opérations locales incompatibles avec ce type de dossier sont refusées explicitement. Les dossiers locaux continuent d'utiliser l'affichage et les métadonnées habituels.
- La navigation distante présente actuellement le nom, le type et la taille. Les analyses multimédias, le renommage et la suppression distante ne sont pas encore intégrés à ce panneau.
- Aucun composant KDE ou KIO n'est utilisé. Les réglages sont conservés.

## 0.5.94

- Ctrl+Z annule un renommage par lot complet ; Ctrl+Maj+Z le rétablit.
- Les compagnons XMP sont inclus dans la même opération.
- Une modification du fichier ou un nouveau conflit de nom bloque l'annulation ou le rétablissement sans écraser le contenu existant.
- L'historique reste limité à la session courante. Les réglages utilisateur sont conservés.

## 0.5.93

- Corrige l'enrichissement d'un dossier lorsqu'aucune ligne de métadonnées précédente n'existe encore. Le comptage direct des éléments reste affiché pendant l'analyse.
- Inclut les améliorations de la version 0.5.92. Les préférences utilisateur restent conservées.

## 0.5.92

- Pied de chaque panneau : nombres de dossiers et fichiers, taille cumulée et espace libre ; les erreurs ne figurent que lorsqu'elles existent.
- Colonnes simplifiées : durée des médias et durée totale des dossiers dans la même colonne, ancien « Contenu multimédia » masqué, préférence de taille des dossiers explicite.
- Renommage par lot avec conflits isolés et permutations sécurisées.
- Consultation et extraction sélective des archives ZIP et TAR, avec contrôle des chemins et sans écrasement.
- Sélection des fichiers associés, comparaison de deux médias et guide de nettoyage sans suppression automatique.
- Navigation GIO des emplacements distants dans une fenêtre dédiée et transferts prudents ; annulation et rétablissement des transferts simples compatibles.
- Diagnostic local et garde contre les sessions interrompues.

Les fichiers vidéo, les XMP et les préférences de l'utilisateur ne sont pas modifiés par la mise à jour.

## 0.5.91

- Nouveau barème perceptuel de « Qualité estimée », suivant le calcul de Mirivue KDE 0.9.23 : détail, bruit, compression (blocs et banding), contraste, résolution et cadence.
- Les passages les plus faibles comptent davantage, la netteté et la compression limitent la note finale ; la cadence mesurée sur les horodatages ne peut que la réduire.
- Lecture locale de 5 ou 30 images jusqu’à 640 pixels de largeur sans agrandissement ; 3 ou 7 contrôles de cadence. Décodage FFmpeg en niveaux de gris sans Qt ni nouvelle dépendance.
- Catégorie et six composantes dans les détails d’analyse et l’infobulle. Aide et traduction anglaise mises à jour.
- Cache de qualité estimée version « estimated-quality-v3 » : anciennes notes invalidées sans toucher aux vidéos, aux fichiers XMP ni aux réglages personnels.
- Tests du barème, de l’invalidation, de la lecture des images et de l’échantillonnage ajoutés. Tests GTK dépendants de PyGObject non exécutables dans l’environnement de construction.

## 0.5.90

- La colonne « Durée » affiche la durée des médias et la durée cumulée des dossiers analysés, avec un tri numérique commun.
- Les durées de dossiers enregistrées par les versions précédentes sont reprises automatiquement.
- L’ancienne colonne « Durée totale » est masquée et écartée du choix des colonnes et de l’export CSV.

## 0.5.89

- Affiche automatiquement la colonne « Durée totale » et passe en vue liste lorsqu’un calcul de durée de dossier est demandé.
- Conserve le contenu de « Taille » ; le calcul de durée ne le remplace plus par une taille en Go.
- Protège le résultat de durée contre un rafraîchissement tardif de la ligne du dossier.

## 0.5.88

- Ajoute « Coller dans ce dossier » au menu contextuel d’un dossier unique ; Ctrl+V reste associé au dossier ouvert.
- Échange les listes de fichiers coupés ou copiés avec GNOME Fichiers au moyen du format natif du presse-papiers, sans supprimer prématurément les éléments coupés.
- Propose de renommer, ignorer ou remplacer explicitement les fichiers en conflit. Les dossiers existants ne sont jamais remplacés automatiquement.

## 0.5.87

- Intègre l’icône Mirivue GNOME validée : dossier, image, onde audio et symbole de lecture, en SVG et en PNG.
- Le lanceur installé utilise sa variante PNG de 256 pixels pour rester reconnaissable dans GNOME.

## 0.5.86

- Rétablit l’icône propre à Mirivue GNOME utilisée dans les versions 0.5.81 à 0.5.83, distincte de l’icône Mirivue Qt.
- Fournit la même icône en SVG et dans les tailles PNG utilisées par le lanceur GNOME.

## 0.5.85

- Ajoute « Dossiers avant les fichiers » au menu et aux préférences.
- Le réglage est conservé au redémarrage et s’applique aux deux panneaux, en liste comme en grille, même lorsque le tri d’une colonne est descendant.

## 0.5.84

- Rétablit l’icône Mirivue d’origine, commune aux éditions GTK4 et Qt.
- Installe l’icône GNOME en SVG et en PNG et référence son chemin complet dans le lanceur installé.

## 0.5.83

- Affiche l’icône de l’application par défaut et une instruction de double-clic lorsqu’aucun aperçu n’est disponible.
- Conserve le zoom vertical et la navigation horizontale pour les images ; réserve le volume et la recherche dans la lecture aux vidéos et aux sons.

## 0.5.82

- Draw a subtle checkerboard within the displayed image bounds, revealing transparent pixels without changing image data.
- Draw PDF previews on white paper with a thin border in the docked viewer and fullscreen viewer, including already cached transparent PDF page renders.
- Keep media playback backgrounds unchanged.

## 0.5.81

- Add a scalable GNOME application icon and include it in the user installer.
- Expand initial and previously too narrow column widths while retaining resize and per-pane order.
- Offer Space to toggle the quick preview from focused file views; keep text entry and modified Space keys native.
- Use a libadwaita application list for “Open With” instead of the deprecated GTK chooser dialog.
- Accept mounted GVfs paths when exposed to local filesystem access; otherwise forward network locations to the system handler.
- Restrict Estimated Quality context actions to videos, as required by its analyzer.
- Keep the existing libadwaita responsive split views and breakpoints.

## 0.5.80

- Add GNOME shortcuts for help (F1), preferences (Ctrl+,), keyboard shortcuts (Ctrl+?), properties (Alt+Enter), reload (Ctrl+R alongside F5), Home (Alt+Home), and bookmarking the current folder (Ctrl+D).
- Add Ctrl+Page Up / Down for tab navigation and Ctrl++ / Ctrl+- / Ctrl+0 for icon zoom, including common equal and numeric keypad keys.
- Ctrl+W now requests window closure when the active pane has only one tab; ongoing operations keep their existing confirmation.
- Update the keyboard shortcuts window with scrolling and both language help pages.

Verification: Python compilation and the 7 GTK-independent tests pass. GUI verification requires GTK/PyGObject on the user's GNOME system.

## 0.5.78

- Reduces the horizontal space around `/` separators in the breadcrumb path bar from 8 to 4 pixels on each side, keeping GTK theme styling and responsive overflow behavior.
- Image previews and full screen now use the original file through GTK/GDK textures instead of enlarging a cached thumbnail.
- For images only, the vertical wheel zooms the preview and the horizontal wheel browses the images in the active folder. Audio and video retain their playback controls.

Validation: automated tests cover image navigation in the active folder as well as existing GTK4 behavior.

## 0.5.77

- Reduces the horizontal space around `/` separators in the breadcrumb path bar from 8 to 4 pixels on each side, keeping GTK theme styling and responsive overflow behavior.

Validation: all 26 automated tests pass.

## 0.5.76

- Fixes an asynchronous GTK row-update race that could leave folder item counts stored in the model but missing from the Details list. Existing direct counts are restored before the enriched row is published, so the visible cell refreshes reliably.
- Adds a regression test for the exact race.

Validation: all 26 GTK-independent and model/UI-menu tests pass.

## 0.5.75

- Harmonizes GNOME-facing view labels and distinguishes GNOME starred files (“Favoris”) from shared folder bookmarks (“Signets”).
- Groups specialized media analysis, metadata and organization commands in a dedicated Media Tools window; adds a discoverable keyboard shortcuts window and removes Quit from the primary menu.
- Clarifies the folder-size option: direct item counts remain immediate, with optional recursive total-size calculation in the background.
- Starts with common file columns and a less crowded factory toolbar. Migrations update only untouched factory defaults and preserve customized columns, profiles and toolbar layouts.
- Updates French and English help text and translations.
- Keeps the GTK build separate from Mirivue Qt.

Validation: 24 GTK-independent and model/UI-menu tests pass. Full window rendering still needs access to the user's graphical session.

## 0.5.74

Ajoute « Les deux panneaux » au sélecteur de portée de la fenêtre Colonnes : chaque réorganisation ou remise à zéro choisie dans ce mode s'applique simultanément aux deux panneaux. La liste s'appuie sur le dernier panneau individuel sélectionné pour présenter son ordre avant modification.

Confirme le geste natif GTK de réordonnancement des entêtes : un clic ordinaire reste disponible pour le tri, et GTK ne démarre le déplacement qu'après le seuil de mouvement horizontal du système. Aucun délai de clic prolongé personnalisé n'est ajouté.

## 0.5.73

Fusionne la visibilité, les profils et le réordonnancement des colonnes dans une fenêtre unique accessible depuis le menu contextuel des entêtes et les préférences. La visibilité reste partagée entre les deux panneaux ; l'ordre et sa remise à zéro sont propres au panneau choisi. Les poignées de glissement et le repère de destination utilisent GTK et les couleurs du thème.

## 0.5.72

Recherche plus poussée des interférences du glissement natif : les gestes de sélection, de clic droit et de dépôt de fichiers restent exclusivement sur la liste des lignes, sœur de l'en-tête GTK. L'ordre natif est sauvegardé après la fin de la séquence GTK pour éviter d'appliquer un état intermédiaire remove/insert aux autres onglets.

Ajoute une fenêtre « Réorganiser les colonnes… » accessible depuis le menu d'en-tête et la personnalisation des colonnes. Elle reprend le glisser-déposer GTK déjà utilisé pour les commandes de barre d'outils, rend la destination visible avec les couleurs du thème et permet de choisir le panneau gauche ou droit. Chaque panneau conserve son propre ordre.

## 0.5.71

Rétablit le glissement natif des colonnes de GtkColumnView. Les gestes de sélection et de menu contextuel sont attachés à la liste des lignes afin de ne plus intercepter les gestes de l'en-tête. Pendant un réordonnancement GTK, un repère de destination non interactif signale la frontière d'insertion avec les couleurs du thème. Chaque panneau conserve son propre ordre de colonnes.

## 0.5.70

Remplace le réordonnancement natif non fonctionnel dans les panneaux Mirivue par un geste de glissement limité aux en-têtes. Pendant le déplacement, l’en-tête suit le pointeur sous forme de peinture GTK et une séparation GTK marque la destination. Les couleurs et états restent fournis par le thème. L’ordre continue d’être sauvegardé indépendamment pour le panneau gauche et le panneau droit.

## 0.5.69

Retire les contrôleurs de clic personnalisés posés sur les en-têtes. Le redimensionnement automatique reste disponible via le double-clic natif sur la limite d'une colonne ; le clic et le glissement des en-têtes sont ainsi laissés à Gtk.ColumnView.

## 0.5.68

Le glissement des fichiers est désormais attaché aux éléments de la liste et aux cartes de la vue icônes plutôt qu'à la vue entière. Cela évite qu'il entre en concurrence avec le glissement natif des en-têtes de colonnes GTK. Les gestes de clic de Mirivue ignorent également les en-têtes.

## 0.5.66

- Added a theme-transparent expanding spacer inside the continuous location-bar surface so the current-folder menu stays flush to the far right, as in GNOME Files.

## 0.5.65

- Harmonized the whole location-bar surface: a single Adwaita `card` surface now sits behind theme-flat breadcrumb and overflow buttons. The theme supplies the background, border, and shape consistently across every path segment.

## 0.5.64

- The breadcrumb now shows the path relative to the home folder, including “Dossier personnel” and native slash separators, following GNOME Files. Parent segments use GTK's dim-label styling; the current folder remains prominent.

## 0.5.63

- Replaced the breadcrumb pencil with a trailing current-folder menu inspired by GNOME Files. The menu exposes folder creation, open-with, terminal, refresh, copy-location, paste, select-all, and folder properties using GTK/GIO actions. Ctrl+L remains the native shortcut for typing a location.
- Kept the menu and breadcrumb buttons theme-drawn; no custom colors or Nautilus/Qt/Plasma dependencies were added.

## 0.5.62

- The location bar now uses regular GTK buttons in a linked group, allowing the active GTK/Adwaita theme to draw the breadcrumb surface and its state. Removed the flat styling that made the path blend into the header bar; no colors are hard-coded.

## 0.5.61

- A plain left click on empty panel space now clears the current selection in both Details and Icons views. Ctrl/Shift-modified clicks retain their selection semantics; right-click background behavior is unchanged.

## 0.5.60

- The Details view displays filenames with a passive GTK label and uses an editable label only while renaming, allowing double-clicks to reach native file-row activation.
- Right-click on file selections is captured by the pane and opens Mirivue's full action menu instead of a text-editing menu. The native column-header menu is preserved.

## 0.5.59

- Details view now displays filenames with a passive GTK label and creates the editable label only for an active rename, allowing the file view to receive native double-click activation.
- Right-click on file selections is captured by the pane and opens the full Mirivue context menu instead of a text-editing menu. Right-click on column headers remains native.

## 0.5.58

- Opening files and folders on double-click now uses the native activation signals from GTK views, matching GNOME Files and avoiding duplicate custom activation.
- The custom double-click gesture is retained only on empty panel space to navigate to the parent folder.

## 0.5.57

Version 0.5.57

- Stream initial folder rows in small batches (at most 16 entries or about 50 ms apart) so both panels begin showing their contents during enumeration instead of waiting for the whole folder.
- Preserve the configured startup folder independently in each visible panel.
- Keep the native selection, keyboard context menu, file clipboard, and empty-space parent navigation behavior from 0.5.56.

## 0.5.56

Version 0.5.56

- Add the standard Ctrl+Shift+N shortcut for creating a folder.
- Open the file context menu from the keyboard with Menu or Shift+F10 in both Details and Icons views.
- Keep native GTK multi-selection behavior in both views and retain the same Ctrl+C/X/V file operations.

## 0.5.55

Version 0.5.55

- Make a panel become active on the first pointer press, so its theme-derived active surface follows the panel being used instead of remaining on the first pane.
- Apply active and inactive Adwaita surface styles directly to each file view for reliable per-pane updates.
- Save a typed startup-folder path immediately so it is available on the next launch.
- Keep the configured startup folder loading independently in both visible panels.

## 0.5.54

Version 0.5.54

- Make active and inactive file views visibly distinct using Adwaita's theme-provided card and view surfaces plus the native frame style; no fixed colors are introduced.
- Show a native spinner and “Chargement du dossier…” while a panel enumerates its startup folder, hiding it as soon as rows arrive or enumeration completes.
- Keep both split panels initialized to the startup location and preserve independent navigation.

## 0.5.53

Version 0.5.53

- Show each folder's direct item count in the Size column as soon as it is available, including while optional recursive byte-size calculation is running. A completed recursive size replaces the count; disabling that option restores the count.
- Mark the active file view with Adwaita's theme-provided card surface, so the active pane has a subtle background distinction in both light and dark themes without a fixed color.

## 0.5.52

Version 0.5.52

- Decoupled thumbnail visibility from file-row refreshes and folder-count values; changing the thumbnail setting no longer repaints or alters folder metadata. Folder rows are excluded from thumbnail extraction.
- Kept thumbnail preference and toolbar state synchronized; visible modes and toggles now use themed GTK toggle-button states.
- Made the path bar adapt to available header width: it keeps the current location visible and folds older ancestors behind a native popover, while labels ellipsize in the middle.

## 0.5.51

Version 0.5.51

- Removed the broad grey block in the Places sidebar by placing native GTK separators between separate navigation lists, rather than inside styled list rows.
- Kept the fixed locations, shared GTK bookmarks, mounted devices, and their existing actions intact.

## 0.5.50

Version 0.5.50

- Thumbnail toggling remains independent from metadata enrichment, keeping folder item counts stable.
- Added GNOME Files' separate “Favoris” view by querying its LocalSearch starred-file tag; this reads GNOME's star state without introducing Mirivue-owned favorites.
- The Places sidebar follows GTK 4 shared bookmarks and GIO-mounted devices, and refreshes bookmark changes made by GNOME Files.
- Mirivue-specific collections remain available from the main menu.

## 0.5.49

Version 0.5.49

- Thumbnail toggling no longer reruns file metadata inspection; thumbnail generation is now an independent background operation, so folder item counts remain stable.
- The Places sidebar now reads only GTK 4's shared bookmark list, mirrors Nautilus's fixed locations/bookmark/device ordering, and refreshes when GNOME Files changes that list. The legacy GTK 3 bookmarks file no longer adds stale entries.
- Mirivue collections remain available from the main menu rather than being mixed into the system Places list.

## 0.5.48

Version 0.5.48

- Toolbar customization now displays a theme-accent insertion marker while dragging; fixed GTK drop coordinates so release reorders at the indicated position, including around the fixed path-bar anchor.
- Double-clicking empty space in either file view now opens the parent folder.
- The thumbnail command now uses the standard symbolic image icon and names its action explicitly as “Afficher les miniatures”.

## 0.5.47

- Put toolbar actions in Adw.HeaderBar's native leading and trailing slots so they reach the corresponding ends of the title bar; the active-pane location bar remains the centered title widget.
- Added a GTK-native double-click fallback using Gtk.GestureClick's system click count, while retaining the built-in view activation path for keyboard use and deduplicating activation events.
- Left the separate Qt/KIO launcher and installation untouched.

## 0.5.46

- Restored native double-click activation in details and icon views by removing custom capture-phase label gestures. Files now open through GIO's default URI handler; folders navigate in the active pane.
- Restored the split-view toolbar command in the default layout.
- Reorganized the header toolbar into left and right command groups around one permanent, active-pane path bar.
- Replaced the plural path-bars entry with a fixed, non-hideable “Barre de chemin” anchor. Removed obsolete customizable stretch spacers from settings.
- Replaced repeated up/down controls in toolbar customization with GTK 4 drag-and-drop reordering using `Gtk.DragSource` and `Gtk.DropTarget`.

## 0.5.45

- L’ouverture suit GNOME Files : un clic sélectionne, le double clic active l’élément via les signaux natifs `activate` de GtkColumnView et GtkGridView.
- Une barre de chemin unique suit le panneau actif; les panneaux conservent leurs emplacements indépendants.
- Les chemins des onglets restent synchronisés avec l’onglet actif.

## 0.5.44

- Le double clic ouvre l’élément sous le pointeur ou, si GTK ne permet pas de récupérer précisément la cellule, l’élément sélectionné au premier clic.
- L’activation du double clic est centralisée par panneau pour éviter les conflits entre les gestes des cellules en vue Détails et en vue Icônes.

## 0.5.43

- La vue scindée conserve les deux barres de chemin, chacune liée à son panneau; elles sont réévaluées après la mise en page initiale.
- Le double clic ouvre un dossier ou un fichier depuis toute la ligne en vue détaillée et depuis les éléments en vue icônes.
- Le nombre d’éléments d’un dossier ne disparaît plus lorsqu’une mise à jour de ses métadonnées arrive après le comptage.

## 0.5.42

- Les deux barres de chemins rejoignent la barre d’en-tête et servent de repère fixe dans la personnalisation de la barre d’outils. Elles ne peuvent pas être masquées ; les commandes restent réordonnables autour d’elles.
- En mode scindé, les deux chemins sont visibles dans une fenêtre large. Quand la fenêtre est étroite, le chemin du panneau actif reste affiché.
- La taille récursive des dossiers peut être activée dans les préférences. Elle est calculée en arrière-plan, sans suivre les liens symboliques et sans bloquer la navigation.
- Le menu contextuel conserve « Renommer » pour un fichier ou une sélection ; le clic droit sur un élément non sélectionné le sélectionne avant d’ouvrir le menu.


GNOME follow-up: toolbar search/menu controls and both expandable spacers can now be reordered and toggled in toolbar customization. Path fields stay aligned proportionally to the split-pane divider. The Size column shows a fast, non-recursive direct-item count for folders by default; optional recursive byte-size calculation remains available.


GNOME toolbar refinement: both path fields are back in the titlebar at the same level as the toolbar icons, with their internal divider following the split-pane proportion.


0.5.41 : barres de chemin replacées dans la barre de titre, au même niveau que les icônes. La personnalisation de la barre d’outils conserve les commandes Recherche/Menu et les espaces extensibles déplaçables ; le comptage direct des éléments de dossiers est conservé.


0.5.42 : la saisie du chemin conserve la même géométrie que le fil d’Ariane lors du basculement au crayon. Le segment cliquable « Dossier personnel » est retiré des chemins descendants ; à la racine, il devient un libellé sans action, le bouton Accueil restant le moyen de navigation.

## 0.5.41

- Les deux barres de chemins rejoignent la barre d’en-tête et servent de repère fixe dans la personnalisation de la barre d’outils. Elles ne peuvent pas être masquées ; les commandes restent réordonnables autour d’elles.
- En mode scindé, les deux chemins sont visibles dans une fenêtre large. Quand la fenêtre est étroite, le chemin du panneau actif reste affiché.
- La taille récursive des dossiers peut être activée dans les préférences. Elle est calculée en arrière-plan, sans suivre les liens symboliques et sans bloquer la navigation.
- Le menu contextuel conserve « Renommer » pour un fichier ou une sélection ; le clic droit sur un élément non sélectionné le sélectionne avant d’ouvrir le menu.


GNOME follow-up: toolbar search/menu controls and both expandable spacers can now be reordered and toggled in toolbar customization. Path fields stay aligned proportionally to the split-pane divider. The Size column shows a fast, non-recursive direct-item count for folders by default; optional recursive byte-size calculation remains available.


GNOME toolbar refinement: both path fields are back in the titlebar at the same level as the toolbar icons, with their internal divider following the split-pane proportion.


0.5.41 : barres de chemin replacées dans la barre de titre, au même niveau que les icônes. La personnalisation de la barre d’outils conserve les commandes Recherche/Menu et les espaces extensibles déplaçables ; le comptage direct des éléments de dossiers est conservé.

## 0.5.37

- Align the GTK build's version with the installed Qt build while keeping both installations separate.
- Read and write GTK shared bookmarks; migrate old Mirivue-only favorites on first upgraded launch.
- Group Places and refresh connected-device entries from Gio.VolumeMonitor; mount, unmount, and eject through GIO.
- Keep one persistent GNOME-style Places sidebar and remove the separate folder-tree switcher and its background scan.
- Let one libadwaita header bar position the window controls; keep the configurable application buttons inside its title area.
- Use stable, independent fixed widths for each pane's detail columns and let GTK handle edge resizing. Measure actual title widgets for column reordering and double-click fitting.
- Use GNOME Desktop's thumbnailer registry for document previews and Poppler-Glib for asynchronous, navigable PDF page previews.
- Keep each pane's visible-item/error/free-space information with that pane and allow Adwaita to draw selection and interaction states.
- This release does not yet provide full GVfs remote navigation/transfers, reversible operation history, or paged rendering of office documents.

## 0.4.12

### Vue Icônes et aperçus

La vue Icônes présente des icônes espacées sur un fond uniforme, avec des zones
vides utilisables au clic droit. Le double-clic ouvre aussi les dossiers cachés
lorsqu’ils sont affichés. Le panneau d’aperçu reste fermé au démarrage quand
l’option correspondante est désactivée.

## 0.4.11

### Renommage et déplacements

Le menu contextuel d’une sélection affiche le programme de renommage configuré
par son nom. Une sélection complète peut maintenant être déplacée ou copiée
par glisser-déposer depuis n’importe quelle ligne ou vignette.

## 0.4.10

### Indicateur de position des colonnes

Pendant le déplacement d’un en-tête, un trait vertical de la couleur du thème
indique l’emplacement exact où la colonne sera déposée.

## 0.4.9

### Correction du déplacement des colonnes

Le repérage de la colonne sous le curseur tient désormais compte de la largeur
réelle de la colonne Nom lorsqu’elle occupe l’espace disponible de la fenêtre.

## 0.4.8

### Colonnes en vue Détails

Un clic bref sur un en-tête trie les éléments. Un clic maintenu et déplacé
horizontalement déplace l’en-tête et la colonne correspondante. L’ordre est
enregistré automatiquement.

## 0.4.7

### Correction

Le déplacement direct des en-têtes de colonnes a été corrigé. Le
glisser-déposer des fichiers est maintenant attaché aux lignes de fichiers,
afin de ne plus intercepter le geste de réorganisation des colonnes de GTK.
L’ordre choisi est conservé au prochain démarrage.
