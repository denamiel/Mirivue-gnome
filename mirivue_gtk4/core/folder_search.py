"""Cancellable name search beneath one local folder, without an index."""

import os
from pathlib import Path


def matching_paths(folder, needle, cancelled, include_hidden=False, allow_empty=False, warning=lambda text: None):
    needle = needle.casefold().strip()
    if not needle and not allow_empty:
        return

    from gi.repository import Gio

    def visible(path):
        try:
            info = Gio.File.new_for_path(str(path)).query_info(
                'standard::is-hidden,standard::is-backup', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
            return not (info.get_is_hidden() or info.get_is_backup())
        except Exception:
            return not path.name.startswith('.')

    def failed(error):
        warning(str(error))

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


def matching_files(folder, needle, cancellable, include_hidden=False, warning=lambda text: None):
    """Enumerate recursive backend URIs through GIO; never convert to local paths."""
    from gi.repository import Gio, GLib
    from .gio_backend import DIRECTORY_ATTRIBUTES, row_from_info
    stack = [folder]
    while stack and not cancellable.is_cancelled():
        parent = stack.pop()
        try:
            enumerator = parent.enumerate_children(DIRECTORY_ATTRIBUTES,
                Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, cancellable)
            try:
                while not cancellable.is_cancelled():
                    info = enumerator.next_file(cancellable)
                    if info is None:
                        break
                    if not include_hidden and (info.get_is_hidden() or info.get_is_backup()):
                        continue
                    file = parent.get_child(info.get_name())
                    if info.get_file_type() == Gio.FileType.DIRECTORY:
                        stack.append(file)
                    if not needle or needle.casefold() in info.get_display_name().casefold():
                        yield row_from_info(parent, info)
            finally:
                enumerator.close(None)
        except GLib.Error as error:
            if not cancellable.is_cancelled():
                warning(parent.get_parse_name() + ' : ' + error.message)
