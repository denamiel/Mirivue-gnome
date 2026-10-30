# Mirivue GNOME 1.0.0-beta.1

## Numérotation

Première bêta de la série 1.0, sans changement de nom de paquet, d'identifiant
GNOME ou de répertoire des réglages.

| Usage | Version |
| --- | --- |
| Application, sources et tag | `1.0.0-beta.1` / `v1.0.0-beta.1` |
| Fedora / RPM | `1.0.0~beta.1` |
| Arch / CachyOS | `1.0.0beta1` |
| Métadonnées Python | `1.0.0b1` |

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
