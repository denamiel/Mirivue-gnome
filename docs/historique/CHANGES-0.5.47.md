# Mirivue GTK 0.5.47

- Put toolbar actions in Adw.HeaderBar's native leading and trailing slots so they reach the corresponding ends of the title bar; the active-pane location bar remains the centered title widget.
- Added a GTK-native double-click fallback using Gtk.GestureClick's system click count, while retaining the built-in view activation path for keyboard use and deduplicating activation events.
- Left the separate Qt/KIO launcher and installation untouched.
