# Mirivue GNOME 0.6.0 RC10 — nettoyage sûr

- Correction de l’import GIO manquant lors des copies et déplacements vers un emplacement réseau.
- Retrait du calcul expérimental de débit, du code devenu inaccessible d’écriture du débit et d’anciens adaptateurs d’historique d’une architecture précédente ; maintien des contrôles MKV toujours utilisés.
- Retrait d’imports inutilisés et de traductions exclusivement liées aux anciens écrans de qualité, de netteté et d’écriture du débit.
- Mise à jour du test de recherche après suppression du filtre « Qualité » et ajout d’un contrôle statique des symboles globaux.
- Les anciens champs de cache et le marqueur de migration sont conservés pour lire les données existantes. Aucun média, compagnon XMP ou réglage de l’utilisateur n’est modifié par ce nettoyage.

La validation GTK et le test du lanceur nécessitent un système GNOME équipé de PyGObject.
