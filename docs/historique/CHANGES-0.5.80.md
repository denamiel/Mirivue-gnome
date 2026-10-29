# Mirivue GTK4 0.5.80

- Add GNOME shortcuts for help (F1), preferences (Ctrl+,), keyboard shortcuts (Ctrl+?), properties (Alt+Enter), reload (Ctrl+R alongside F5), Home (Alt+Home), and bookmarking the current folder (Ctrl+D).
- Add Ctrl+Page Up / Down for tab navigation and Ctrl++ / Ctrl+- / Ctrl+0 for icon zoom, including common equal and numeric keypad keys.
- Ctrl+W now requests window closure when the active pane has only one tab; ongoing operations keep their existing confirmation.
- Update the keyboard shortcuts window with scrolling and both language help pages.

Verification: Python compilation and the 7 GTK-independent tests pass. GUI verification requires GTK/PyGObject on the user's GNOME system.
