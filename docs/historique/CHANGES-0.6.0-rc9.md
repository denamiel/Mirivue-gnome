# Mirivue GNOME 0.6.0 RC9

Alignement de l’interface GTK4 sur les simplifications KDE 1.0.0 RC22–RC30, avec GIO/libadwaita et les conventions de GNOME Files.

- Retrait du score subjectif de qualité, de la colonne et de ses profils ; migration sélective du cache en conservant métadonnées, étiquettes et autres préférences.
- Retrait des calculs et écritures de débit ; seul le débit déclaré par le média est présenté. Durée des dossiers dans Organisation ; opérations en arrière-plan dans Opérations.
- Propriétés avec pages Général et Droits d’accès, contrôle GIO des neuf droits Unix et vérification du résultat ; refus de modifier la cible d’un lien symbolique.
- Métadonnées : bouton compact de suggestions et choix explicite entre écriture dans le fichier compatible et compagnon XMP.
- Menu « Créer un nouveau » avec dossier ou fichier texte créé sans écrasement. Terminal GNOME avec icône du thème et Alt+Maj+F4.
- Aide et traductions mises à jour, tests de migration et d’opérations locales. Aucun composant KDE/Qt/KIO requis.

L’installateur .run réalise une vérification de la fenêtre GTK avant remplacement, conserve une version précédente pour le retour arrière et préserve les réglages de l’utilisateur.
