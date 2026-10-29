"""The GTK 4 bookmark list shared with GNOME Files."""

from __future__ import annotations

import os
from pathlib import Path

import gi

gi.require_version('Gio', '2.0')
from gi.repository import Gio


def bookmark_file() -> Path:
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    return config / 'gtk-4.0' / 'bookmarks'


def read_bookmarks() -> list[tuple[str, str]]:
    """Return (URI, optional label), preserving remote GVfs locations."""
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    try:
        lines = bookmark_file().read_text(encoding='utf-8').splitlines()
    except OSError:
        return result
    for line in lines:
        value, _, label = line.strip().partition(' ')
        if not value or value in seen:
            continue
        file = Gio.File.new_for_uri(value)
        result.append((value, label.strip() or file.get_basename() or value))
        seen.add(value)
    return result


def write_bookmarks(bookmarks: list[tuple[str, str]]) -> None:
    target = bookmark_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    seen: set[str] = set()
    for uri, label in bookmarks:
        if uri in seen:
            continue
        seen.add(uri)
        lines.append(f'{uri} {label}' if label else uri)
    temp = target.with_suffix('.tmp')
    temp.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')
    os.replace(temp, target)


def rename_bookmark(uri: str, label: str) -> bool:
    """Change only the displayed name, leaving the location and its order intact."""
    if '\n' in label or '\r' in label:
        return False
    label = label.strip()
    if not label:
        return False
    bookmarks = read_bookmarks()
    if not any(value == uri for value, _ in bookmarks):
        return False
    updated = [(value, label if value == uri else old) for value, old in bookmarks]
    if updated != bookmarks:
        write_bookmarks(updated)
    return True


def add_bookmark_folders(folders: list[Path]) -> int:
    bookmarks = read_bookmarks()
    known = {uri for uri, _ in bookmarks}
    added = 0
    for folder in folders:
        if not folder.is_dir():
            continue
        uri = folder.absolute().as_uri()
        if uri not in known:
            bookmarks.append((uri, folder.name or str(folder)))
            known.add(uri)
            added += 1
    if added:
        write_bookmarks(bookmarks)
    return added


def migrate_legacy_favorites(paths: list[str]) -> int:
    """Move old Mirivue-local directory favorites into GTK's shared list."""
    bookmarks = read_bookmarks()
    known = {uri for uri, _ in bookmarks}
    added = 0
    for value in paths:
        path = Path(value).expanduser()
        try:
            if not path.is_dir():
                continue
            uri = path.resolve().as_uri()
            if uri in known:
                continue
            bookmarks.append((uri, path.name or str(path)))
            known.add(uri)
            added += 1
        except OSError:
            continue
    if added:
        write_bookmarks(bookmarks)
    return added
