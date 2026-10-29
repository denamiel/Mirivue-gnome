"""Local Unix permissions through GIO, without following symbolic links."""

from ..i18n import tr, trf
import stat
from pathlib import Path

READ = (stat.S_IRUSR, stat.S_IRGRP, stat.S_IROTH)
WRITE = (stat.S_IWUSR, stat.S_IWGRP, stat.S_IWOTH)
EXEC = (stat.S_IXUSR, stat.S_IXGRP, stat.S_IXOTH)


def _gio():
    from gi.repository import Gio

    return Gio


def access_level(mode, category, directory):
    bits = (
        (READ[category] | WRITE[category] | EXEC[category])
        if directory
        else (READ[category] | WRITE[category])
    )
    return mode & bits


def replace_access(mode, category, read, write, execute=None):
    mask = READ[category] | WRITE[category]
    if execute is not None:
        mask |= EXEC[category]
    result = mode & ~mask
    if read:
        result |= READ[category]
    if write:
        result |= WRITE[category]
    if execute:
        result |= EXEC[category]
    return result


def set_executable(mode, enabled):
    bits = EXEC[0] | EXEC[1] | EXEC[2]
    return mode | bits if enabled else mode & ~bits


def apply_permissions(path, requested, expected_identity=None):
    """Reject links and replacement races; verify effective permissions."""
    path = Path(path)
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode):
        raise ValueError(tr('Les droits du lien symbolique ne sont pas modifiés.'))
    if expected_identity is not None and (before.st_dev, before.st_ino) != expected_identity:
        raise ValueError(tr('Le fichier a changé depuis l’ouverture de la fenêtre.'))
    requested = stat.S_IMODE(requested)
    Gio = _gio()
    Gio.File.new_for_path(str(path)).set_attribute_uint32(
        'unix::mode', requested, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None
    )
    after = path.lstat()
    if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
        raise OSError(tr('Le fichier a changé pendant la modification des droits.'))
    actual = stat.S_IMODE(after.st_mode)
    if actual != requested:
        raise OSError(
            trf(
                'Le système de fichiers refuse ces droits (demandés \x1f0\x1f, obtenus \x1f1\x1f).',
                format(requested, '04o'),
                format(actual, '04o'),
            )
        )
    return actual
