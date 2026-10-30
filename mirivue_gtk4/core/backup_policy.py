"""One original per media path, with an explicit record of its provenance.

Never reuse a backup solely because its name matches: a different file may
have taken the place of the original since the last Mirivue edit.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import logging

from .extensions import fingerprint
from ..i18n import tr


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def record_tool_failure(operation, detail):
    logging.getLogger('mirivue-gtk4').warning('%s: %s', operation, detail)



def _signature(path):
    """A bounded content sample, independent of mount device and inode IDs.

    This is an accidental-replacement check, not a full-file checksum.
    Both the original and the latest published media are tracked separately.
    """
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(tr('Sauvegarde réservée aux fichiers ordinaires.'))
    with os.fdopen(os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise ValueError(tr('Le fichier a changé pendant sa vérification.'))
        block = 1 << 20
        size = before.st_size
        offsets = {0, max(0, (size - block) // 2), max(0, size - block)}
        digest = hashlib.sha256()
        for offset in sorted(offsets):
            stream.seek(offset)
            data = stream.read(min(block, size - offset))
            digest.update(offset.to_bytes(8, 'big'))
            digest.update(len(data).to_bytes(8, 'big'))
            digest.update(data)
        after = os.fstat(stream.fileno())
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
            raise ValueError(tr('Le fichier a changé pendant sa vérification.'))
    latest = path.lstat()
    if (latest.st_dev, latest.st_ino, latest.st_size, latest.st_mtime_ns) != (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns):
        raise ValueError(tr('Le fichier a changé pendant sa vérification.'))
    return [before.st_size, before.st_mtime_ns, digest.hexdigest()]


def _names(path):
    path = Path(path)
    return Path(str(path) + '.mirivue-original'), path.with_name('.' + path.name + '.mirivue-backup.json')


def legacy_backups(path):
    """Expose older backups without deleting or silently claiming them."""
    path = Path(path)
    old = set(path.parent.glob(path.name + '.mirivue-original-*'))
    old.update(path.parent.glob(path.name + '.mirivue-original.bak'))
    return sorted(item for item in old if item.is_file() and not item.is_symlink())


def _write_record(marker, data):
    fd, name = tempfile.mkstemp(prefix='.mirivue-backup-', dir=marker.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, separators=(',', ':'))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, marker)
        fsync_directory(marker.parent)
    finally:
        temporary.unlink(missing_ok=True)


def reserve_backup(path, cancelled=lambda: False):
    """Return (backup, created); reject a stale or unverified existing backup."""
    path = Path(path)
    backup, marker = _names(path)
    current = _signature(path)
    if os.path.lexists(marker) or os.path.lexists(backup):
        if marker.is_symlink() or backup.is_symlink() or not marker.is_file() or not backup.is_file():
            raise ValueError(tr('Sauvegarde existante incomplète ou non reconnue ; vérifiez-la avant de modifier ce fichier.'))
        try:
            if marker.stat().st_size > 4096:
                raise ValueError(tr('Données de sauvegarde trop volumineuses.'))
            record = json.loads(marker.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError(tr('Impossible de vérifier la sauvegarde existante.')) from error
        if not isinstance(record, dict):
            raise ValueError(tr('Suivi de la sauvegarde non reconnu ; aucune donnée ne sera écrasée.'))
        if (record.get('version') != 2 or record.get('current') != current
                or record.get('original') != _signature(backup)):
            raise ValueError(tr('Le fichier ne correspond plus à sa sauvegarde initiale ; aucune sauvegarde ne sera écrasée.'))
        return backup, False

    created = False
    identity = None
    try:
        if shutil.disk_usage(path.parent).free < current[0] + 16 * 1024 * 1024:
            raise ValueError(tr('Espace insuffisant pour sauvegarder l’original.'))
        with path.open('rb') as source, backup.open('xb') as destination:
            created = True
            identity = fingerprint(backup)[:2]
            while True:
                if cancelled():
                    raise InterruptedError()
                block = source.read(1024 * 1024)
                if not block:
                    break
                destination.write(block)
            destination.flush()
            os.fsync(destination.fileno())
        shutil.copystat(path, backup)
        if _signature(path) != current or _signature(backup) != current:
            raise ValueError(tr('Le fichier a changé pendant la sauvegarde ; original conservé.'))
        _write_record(marker, {'version': 2, 'original': _signature(backup), 'current': current})
        return backup, True
    except BaseException:
        # Only remove the file this reservation actually created. No existing
        # backup or provenance record is deleted on a failed reservation.
        if created and not os.path.lexists(marker) and os.path.lexists(backup) and fingerprint(backup)[:2] == identity:
            backup.unlink()
        raise


def record_backup(path, backup):
    """Bind the preserved original to the newly published file."""
    _, marker = _names(path)
    try:
        if marker.is_symlink() or backup.is_symlink():
            raise ValueError(tr('Sauvegarde remplacée pendant la publication.'))
        record = json.loads(marker.read_text(encoding='utf-8'))
        if record['original'] != _signature(backup):
            raise ValueError(tr('Sauvegarde modifiée pendant la publication.'))
        record['current'] = _signature(path)
        _write_record(marker, record)
    except (OSError, ValueError, KeyError, TypeError) as error:
        # The media was already committed: report the incident, then block
        # later edits via the stale record rather than claim this edit failed.
        record_tool_failure('suivi de la sauvegarde', f'{path}: {error}')


def discard_new_backup(path, backup, created, expected=None):
    """Discard only an unchanged new reservation after failed publication."""
    if not created:
        return
    _, marker = _names(path)
    try:
        if expected is None or (_signature(backup), fingerprint(marker)) != expected:
            record_tool_failure('sauvegarde conservée', str(backup))
            return
        marker.unlink()
        backup.unlink()
    except (OSError, ValueError) as error:
        record_tool_failure('nettoyage de la sauvegarde', f'{backup}: {error}')
