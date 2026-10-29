"""GNOME file clipboard payloads, independent of GTK for validation."""

from .i18n import tr, trf
from pathlib import Path
from urllib.parse import urlsplit, unquote
import uuid

GNOME_MIME = 'x-special/gnome-copied-files'
LEGACY_MIME = 'x-special/nautilus-clipboard'


def encode_files(paths, cut):
    return (
        ('cut' if cut else 'copy').encode()
        + b'\n'
        + '\n'.join(Path(path).absolute().as_uri() for path in paths).encode('utf-8')
        + b'\n'
    )


def decode_files(data):
    """Accept local file URIs only; never treat pasted text as a file path."""
    if len(data) > 1024 * 1024:
        raise ValueError(tr('Presse-papiers de fichiers trop volumineux.'))
    lines = data.decode('utf-8').splitlines()
    if not lines or lines[0] not in ('copy', 'cut'):
        raise ValueError(tr('Format de presse-papiers non reconnu.'))
    paths = []
    for uri in lines[1:]:
        if not uri or uri.startswith('#'):
            continue
        parsed = urlsplit(uri)
        if parsed.scheme != 'file' or parsed.netloc not in ('', 'localhost') or not parsed.path:
            continue
        paths.append(Path(unquote(parsed.path)))
    return list(dict.fromkeys(paths)), lines[0] == 'cut'


def unique_destination(target):
    """Find a free sibling without overwriting the original or an earlier copy."""
    target = Path(target)
    stem, suffix = (target.name, '') if target.is_dir() else (target.stem, target.suffix)
    number = 1
    while True:
        label = ' — copie' if number == 1 else f' — copie {number}'
        candidate = target.with_name(stem + label + suffix)
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
        number += 1


def replace_existing_file(target, publish):
    """Protect the previous file until publishing succeeds, restoring on failure."""
    target = Path(target)
    if target.is_dir():
        raise IsADirectoryError(str(target))
    backup = target.with_name('.' + target.name + '.mirivue-backup-' + uuid.uuid4().hex)
    target.rename(backup)
    try:
        result = publish()
    except BaseException:
        if not target.exists() and not target.is_symlink():
            backup.rename(target)
        else:
            raise OSError(trf('La destination précédente a été conservée dans \x1f0\x1f.', backup))
        raise
    backup.unlink()
    return result
