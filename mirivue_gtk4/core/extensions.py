'Conservative container detection and Linux no-overwrite extension correction.'

from ..i18n import tr, trf

from dataclasses import dataclass
from pathlib import Path
from .platform_services import services
import os
import stat
import uuid


def suggest_extension(general, current):
    fmt = str(general.get('Format', '')).strip().casefold()
    profile = str(general.get('Format_Profile', '')).casefold()
    brand = str(general.get('CodecID', '')).strip().casefold()
    mapping = {
        'matroska': ('.mkv', {'.mkv'}),
        'webm': ('.webm', {'.webm'}),
        'avi': ('.avi', {'.avi', '.divx'}),
        'quicktime': ('.mov', {'.mov', '.qt'}),
        'flash video': ('.flv', {'.flv'}),
        'flv': ('.flv', {'.flv'}),
        'ogg': ('.ogv', {'.ogv', '.ogg'}),
        'mxf': ('.mxf', {'.mxf'}),
        'windows media': ('.asf', {'.asf', '.wmv'}),
        'asf': ('.asf', {'.asf', '.wmv'}),
    }
    if fmt == 'mpeg-4':
        if 'quicktime' in profile or brand == 'qt':
            preferred, valid = ('.mov', {'.mov', '.qt'})
        elif brand.startswith('3g2') or '3gpp2' in profile:
            preferred, valid = ('.3g2', {'.3g2'})
        elif brand.startswith(('3gp', '3ge', '3gg')) or '3gpp' in profile:
            preferred, valid = ('.3gp', {'.3gp'})
        else:
            preferred, valid = ('.mp4', {'.mp4', '.m4v', '.f4v'})
    elif fmt in mapping:
        preferred, valid = mapping[fmt]
    else:
        return ('', tr('Conteneur non reconnu ou correspondance trop ambiguë pour proposer une correction.'))
    if current.lower() in valid:
        return (
            current.lower(),
            trf('Extension compatible avec le conteneur détecté : \x1f0\x1f.', general.get('Format', '')),
        )
    return (
        preferred,
        trf(
            'Conteneur détecté : \x1f0\x1f ; extension recommandée : \x1f1\x1f.',
            general.get('Format', ''),
            preferred,
        ),
    )


def fingerprint(path):
    info = path.lstat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


@dataclass(frozen=True)
class Rename:
    source: Path
    destination: Path
    signature: tuple | None
    issue: str = ''


def prepare_renames(rows):
    plans = []
    for row in rows:
        if row.error or not row.suggested_extension or row.path.suffix.lower() == row.suggested_extension:
            continue
        target = row.path.with_suffix(row.suggested_extension)
        issue = ''
        try:
            mode = row.path.lstat().st_mode
            if not stat.S_ISREG(mode):
                issue = tr('Seuls les fichiers ordinaires sont renommés (pas les liens ni les dossiers).')
            elif row.file_signature is None or fingerprint(row.path) != row.file_signature:
                issue = tr('Fichier modifié depuis l’analyse : actualisez le dossier.')
            elif os.path.lexists(target):
                issue = tr('Le nom de destination existe déjà.')
        except OSError as error:
            issue = str(error)
        plans.append(Rename(row.path, target, row.file_signature, issue))
    counts = {}
    for plan in plans:
        counts[plan.destination] = counts.get(plan.destination, 0) + 1
    return [
        Rename(
            p.source,
            p.destination,
            p.signature,
            p.issue or (tr('Plusieurs fichiers auraient le même nom.') if counts[p.destination] > 1 else ''),
        )
        for p in plans
    ]


def rename_no_replace(source, destination):
    services.rename_no_replace(Path(source), Path(destination))


def _temporary_rename_path(path):
    while True:
        candidate = path.parent / ('.mirivue-renaming-' + uuid.uuid4().hex + path.suffix)
        if not os.path.lexists(candidate):
            return candidate


def apply_renames(plans):
    renamed, errors, entries = ({}, [], [])
    from .media import companion, AUDIO_EXT, IMAGE_EXT
    from .metadata import EXTENSIONS

    for plan in plans:
        try:
            if plan.issue:
                raise ValueError(plan.issue)
            if plan.source.parent != plan.destination.parent:
                raise ValueError(tr('Le renommage doit rester dans le même dossier'))
            if (
                not (stat.S_ISREG(plan.source.lstat().st_mode) or stat.S_ISDIR(plan.source.lstat().st_mode))
                or fingerprint(plan.source) != plan.signature
            ):
                raise ValueError(tr('Fichier modifié depuis l’analyse : actualisez le dossier.'))
            side = companion(plan.source)
            target_side = companion(plan.destination)
            has_side = (
                plan.source.suffix.lower() in EXTENSIONS | AUDIO_EXT | IMAGE_EXT
                and plan.source.is_file()
                and side.is_file()
            )
            if has_side:
                if side.is_symlink():
                    raise ValueError(tr('Le fichier compagnon XMP ne peut pas être renommé sans conflit.'))
            entries.append(
                {
                    'plan': plan,
                    'side': side if has_side else None,
                    'target_side': target_side if has_side else None,
                }
            )
        except (OSError, ValueError) as error:
            errors.append(trf('\x1f0\x1f → \x1f1\x1f: \x1f2\x1f', plan.source, plan.destination, error))

    # A destination may currently be occupied by another member of the same
    # batch.  Keep removing invalid entries until every occupied destination
    # is guaranteed to be freed by an entry that will actually run.
    while entries:
        sources = {entry['plan'].source for entry in entries}
        sources.update((entry['side'] for entry in entries if entry['side'] is not None))
        destinations = {}
        for entry in entries:
            destinations.setdefault(entry['plan'].destination, []).append(entry)
            if entry['target_side'] is not None:
                destinations.setdefault(entry['target_side'], []).append(entry)
        invalid = {}
        for destination, owners in destinations.items():
            if len(owners) > 1:
                for entry in owners:
                    invalid[id(entry)] = tr('Plusieurs fichiers auraient le même nom.')
            elif os.path.lexists(destination) and destination not in sources:
                invalid[id(owners[0])] = tr('Ce nom existe déjà.')
        if not invalid:
            break
        remaining = []
        for entry in entries:
            reason = invalid.get(id(entry))
            if reason:
                plan = entry['plan']
                errors.append(trf('\x1f0\x1f → \x1f1\x1f: \x1f2\x1f', plan.source, plan.destination, reason))
            else:
                remaining.append(entry)
        entries = remaining

    # Move every source to a unique temporary name first.  This makes chains
    # and cycles safe (001→002, 002→003, or 001↔002) without ever overwriting
    # a file.  If one move fails, the whole prepared subset is restored.
    moves = []
    for entry in entries:
        plan = entry['plan']
        moves.append((plan.source, _temporary_rename_path(plan.source), plan.destination, plan))
        if entry['side'] is not None:
            moves.append((entry['side'], _temporary_rename_path(entry['side']), entry['target_side'], plan))
    staged = []
    try:
        for source, temporary, destination, plan in moves:
            rename_no_replace(source, temporary)
            staged.append((source, temporary, destination, plan))
    except OSError as error:
        failed_plan = moves[len(staged)][3]
        errors.append(
            trf('\x1f0\x1f → \x1f1\x1f: \x1f2\x1f', failed_plan.source, failed_plan.destination, error)
        )
        for source, temporary, _, plan in reversed(staged):
            try:
                rename_no_replace(temporary, source)
            except OSError as rollback_error:
                errors.append(trf('Restauration de \x1f0\x1f impossible : \x1f1\x1f', source, rollback_error))
        return (renamed, errors)

    completed = []
    try:
        for source, temporary, destination, plan in moves:
            rename_no_replace(temporary, destination)
            completed.append((source, temporary, destination, plan))
    except OSError as error:
        failed_plan = moves[len(completed)][3]
        errors.append(
            trf('\x1f0\x1f → \x1f1\x1f: \x1f2\x1f', failed_plan.source, failed_plan.destination, error)
        )
        for _, temporary, destination, _ in reversed(completed):
            try:
                rename_no_replace(destination, temporary)
            except OSError as rollback_error:
                errors.append(
                    trf('Restauration de \x1f0\x1f impossible : \x1f1\x1f', destination, rollback_error)
                )
        for source, temporary, _, _ in reversed(moves):
            if os.path.lexists(temporary):
                try:
                    rename_no_replace(temporary, source)
                except OSError as rollback_error:
                    errors.append(
                        trf('Restauration de \x1f0\x1f impossible : \x1f1\x1f', source, rollback_error)
                    )
        return (renamed, errors)

    for source, _, destination, _ in moves:
        renamed[source] = destination
    return (renamed, errors)
