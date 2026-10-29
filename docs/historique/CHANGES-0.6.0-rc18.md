# Mirivue GNOME 0.6.0 RC18

- La lecture du schéma de préférences de GNOME Files emploie `GObject.Object.get_property('settings-schema')`, conformément à PyGObject, au lieu d'un attribut direct inexistant sur `Gio.Settings`.
- Un test vérifie les changements de vue dans les deux panneaux et la prise en compte du tri après modification de la préférence GNOME Files.
- Le contrôle préalable de l'installateur reste limité au chargement des composants : le lancement réel de l'interface doit être vérifié après installation dans la session GNOME.
