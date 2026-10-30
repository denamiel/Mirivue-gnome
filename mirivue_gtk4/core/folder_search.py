"""Cancellable name search beneath one local folder, without an index."""

import os
from pathlib import Path


def matching_paths(folder, needle, cancelled, include_hidden=False):
    needle = needle.casefold().strip()
    if not needle:
        return

    from gi.repository import Gio

    def visible(path):
        try:
            info = Gio.File.new_for_path(str(path)).query_info(
                'standard::is-hidden,standard::is-backup', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
            return not (info.get_is_hidden() or info.get_is_backup())
        except Exception:
            return not path.name.startswith('.')

    def failed(_error):
        return None

    for root, dirs, files in os.walk(folder, topdown=True, followlinks=False, onerror=failed):
        if cancelled():
            return
        if not include_hidden:
            dirs[:] = [name for name in dirs if visible(Path(root) / name)]
            files = [name for name in files if visible(Path(root) / name)]
        # Never descend into linked directories, including mounted links.
        dirs[:] = [name for name in dirs if not (Path(root) / name).is_symlink()]
        for name in dirs + files:
            if cancelled():
                return
            if needle in name.casefold():
                yield Path(root) / name
