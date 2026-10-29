# Mirivue GTK 0.5.78

- Reduces the horizontal space around `/` separators in the breadcrumb path bar from 8 to 4 pixels on each side, keeping GTK theme styling and responsive overflow behavior.
- Image previews and full screen now use the original file through GTK/GDK textures instead of enlarging a cached thumbnail.
- For images only, the vertical wheel zooms the preview and the horizontal wheel browses the images in the active folder. Audio and video retain their playback controls.

Validation: automated tests cover image navigation in the active folder as well as existing GTK4 behavior.
