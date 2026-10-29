# Mirivue GTK 0.5.75

- Harmonizes GNOME-facing view labels and distinguishes GNOME starred files (“Favoris”) from shared folder bookmarks (“Signets”).
- Groups specialized media analysis, metadata and organization commands in a dedicated Media Tools window; adds a discoverable keyboard shortcuts window and removes Quit from the primary menu.
- Clarifies the folder-size option: direct item counts remain immediate, with optional recursive total-size calculation in the background.
- Starts with common file columns and a less crowded factory toolbar. Migrations update only untouched factory defaults and preserve customized columns, profiles and toolbar layouts.
- Updates French and English help text and translations.
- Keeps the GTK build separate from Mirivue Qt.

Validation: 24 GTK-independent and model/UI-menu tests pass. Full window rendering still needs access to the user's graphical session.
