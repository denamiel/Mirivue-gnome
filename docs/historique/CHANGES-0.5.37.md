# Mirivue GTK 0.5.37

- Align the GTK build's version with the installed Qt build while keeping both installations separate.
- Read and write GTK shared bookmarks; migrate old Mirivue-only favorites on first upgraded launch.
- Group Places and refresh connected-device entries from Gio.VolumeMonitor; mount, unmount, and eject through GIO.
- Keep one persistent GNOME-style Places sidebar and remove the separate folder-tree switcher and its background scan.
- Let one libadwaita header bar position the window controls; keep the configurable application buttons inside its title area.
- Use stable, independent fixed widths for each pane's detail columns and let GTK handle edge resizing. Measure actual title widgets for column reordering and double-click fitting.
- Use GNOME Desktop's thumbnailer registry for document previews and Poppler-Glib for asynchronous, navigable PDF page previews.
- Keep each pane's visible-item/error/free-space information with that pane and allow Adwaita to draw selection and interaction states.
- This release does not yet provide full GVfs remote navigation/transfers, reversible operation history, or paged rendering of office documents.
