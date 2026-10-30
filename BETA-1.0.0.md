# Mirivue GNOME 1.0.0-beta.2

## Numérotation

Série bêta 1.0, sans changement de nom de paquet, d'identifiant
GNOME ou de répertoire des réglages.

| Usage | Version |
| --- | --- |
| Application, sources et tag | `1.0.0-beta.2` / `v1.0.0-beta.2` |
| Fedora / RPM | `1.0.0~beta.2` |
| Arch / CachyOS | `1.0.0beta2` |
| Métadonnées Python | `1.0.0b2` |

Ces formes préservent l'ordre des mises à jour : 0.6.24, bêta 1, bêta 2,
release candidate, puis 1.0.0 stable. Le workflow de publication marque les
versions alpha/bêta/RC comme préversions lorsqu'un tag est publié.
Le passage à 1.0 bêta ne signifie pas que les limites de 0.6.24 sont levées.

## Premier original des métadonnées

Quand la sauvegarde est activée, la première version existante du fichier
édité est copiée vers `<nom>.mirivue-original`. Un suivi caché
`.<nom>.mirivue-backup.json` relie cet original au dernier fichier publié.
Les éditions suivantes réutilisent cette sauvegarde uniquement si le suivi,
l'original et le fichier courant correspondent.

Le suivi emploie taille, date de modification et SHA-256 d'échantillons de
contenu (début, milieu, fin), indépendamment du numéro de périphérique et
de l'inode. C'est un contrôle de provenance contre les remplacements
accidentels, pas une empreinte intégrale ni une protection contre des
modifications délibérées préservant les échantillons et les dates.

Une sauvegarde inconnue, modifiée ou incomplète n'est jamais écrasée pour
continuer. Les anciennes sauvegardes successives sont conservées et ne sont
pas silencieusement adoptées. Aucun fichier de l'utilisateur n'est migré
pendant l'installation.

L'écriture des métadonnées continue à être préparée dans un fichier temporaire,
relue et vérifiée avant publication. Une annulation ou un échec retire seulement
une nouvelle réservation inchangée de cette opération ; une sauvegarde
antérieure reste en place. Si la publication a réussi mais que l'actualisation
du suivi échoue, le média et l'original sont conservés, l'incident est journalisé
et les éditions ultérieures sont bloquées par le suivi périmé.

Le choix existant de désactiver les sauvegardes est conservé. Pour une édition
XMP, la sauvegarde concerne le compagnon XMP existant ; créer le premier
compagnon XMP ne modifie pas le média et ne sauvegarde pas un fichier inexistant.

## Conformité GNOME

La sauvegarde des métadonnées est une fonction de Mirivue, sans équivalent
exact dans Nautilus. Elle n'ajoute ni dialogue personnalisé ni couleur,
ni préférence Nautilus, ni dépendance KDE/KIO/Qt/PySide.
L'interface et les API GTK4/libadwaita/GIO de la version précédente sont conservées.

## Références de numérotation

- https://packaging.python.org/en/latest/specifications/version-specifiers/
- https://rpm.org/docs/latest/man/rpm-version.7
- https://man.archlinux.org/man/PKGBUILD.5.en

Les tests couvrent les éditions successives, les changements de fichier ou
d'original, les sauvegardes anciennes, l'annulation, l'échec de publication,
l'échec de suivi après publication et les éditions XMP réelles. L'ordre des
versions est vérifié avec RPM et vercmp dans leurs constructions respectives.

## Actualisation automatique — bêta 2

Les dossiers affichés sont surveillés avec `Gio.File.monitor_directory` et
`WATCH_MOVES`, pour les dossiers locaux et les vues GIO/GVfs. L'interrupteur
correspondant est retiré des Préférences. L'ancienne valeur `monitor_external`,
même fausse, est ignorée ; elle disparaît lors du prochain enregistrement des
réglages, dont les autres choix sont conservés. F5 reste disponible.

La disponibilité des notifications dépend du backend. En cas de refus de
surveillance, le dossier reste consultable et actualisable manuellement ;
aucun mécanisme Python de scrutation périodique n'est ajouté.

Références officielles vérifiées :
- https://docs.gtk.org/gio/method.File.monitor_directory.html
- https://docs.gtk.org/gio/flags.FileMonitorFlags.html
- https://docs.gtk.org/gtk4/property.DirectoryList.monitored.html

Le moniteur interne de Gtk.DirectoryList reste désactivé pour la raison de
stabilité documentée dans NATIF-GNOME-0.6.24.md. La surveillance emploie le
moniteur GIO distinct déjà utilisé par l'application. Les tests exercent GIO
réel sur des fichiers temporaires ; un serveur SMB/SFTP réel et le bureau
GNOME/Wayland ne sont pas observés dans cet environnement.
