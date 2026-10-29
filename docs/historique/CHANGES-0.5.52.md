Version 0.5.52

- Decoupled thumbnail visibility from file-row refreshes and folder-count values; changing the thumbnail setting no longer repaints or alters folder metadata. Folder rows are excluded from thumbnail extraction.
- Kept thumbnail preference and toolbar state synchronized; visible modes and toggles now use themed GTK toggle-button states.
- Made the path bar adapt to available header width: it keeps the current location visible and folds older ancestors behind a native popover, while labels ellipsize in the middle.
