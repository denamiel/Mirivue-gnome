# Mirivue GTK 0.5.46

- Restored native double-click activation in details and icon views by removing custom capture-phase label gestures. Files now open through GIO's default URI handler; folders navigate in the active pane.
- Restored the split-view toolbar command in the default layout.
- Reorganized the header toolbar into left and right command groups around one permanent, active-pane path bar.
- Replaced the plural path-bars entry with a fixed, non-hideable “Barre de chemin” anchor. Removed obsolete customizable stretch spacers from settings.
- Replaced repeated up/down controls in toolbar customization with GTK 4 drag-and-drop reordering using `Gtk.DragSource` and `Gtk.DropTarget`.
