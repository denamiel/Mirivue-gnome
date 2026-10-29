'Internal name validation and safe argument building for external renamers.'

from ..i18n import tr, trf

import os
import shlex
import shutil
import stat
from pathlib import Path
from .extensions import Rename, fingerprint
from .platform_services import services

PRESETS = {'Thunar': ('thunar', '-B'), 'Bulky': ('bulky', '')}


def single_name_selection_end(name, is_directory=False):
    """Select a file's name before its final extension; select folders in full."""
    if is_directory:
        return len(name)
    dot = name.rfind('.')
    return dot if dot > 0 else len(name)


def batch_names(rows, mode, first='', second='', start=1, digits=3):
    'Build portable bulk-rename proposals while preserving file extensions.'
    names = []
    for offset, row in enumerate(rows):
        original = row.path.name
        suffix = '' if getattr(row, 'is_dir', False) else row.path.suffix
        stem = original[: -len(suffix)] if suffix else original
        if mode == 'prefix':
            candidate = str(first) + stem
        elif mode == 'suffix':
            candidate = stem + str(first)
        elif mode == 'replace':
            candidate = stem.replace(str(first), str(second)) if str(first) else stem
        elif mode == 'number':
            candidate = (
                str(first).strip() + ' ' + str(int(start) + offset).zfill(int(digits))
                if str(first).strip()
                else stem
            )
        else:
            candidate = original
        names.append(candidate + suffix if mode != 'manual' else candidate)
    return names


def prepare_names(rows, names):
    if len(rows) != len(names):
        raise ValueError(tr('Le nombre de noms ne correspond pas à la sélection'))
    changed_sources = {row.path for row, name in zip(rows, names) if name != row.path.name}
    plans = []
    for row, name in zip(rows, names):
        if name == row.path.name:
            continue
        issue = ''
        reason = services.validate_portable_name(name)
        if reason:
            issue = reason
            target = row.path
        else:
            target = row.path.parent / name
            try:
                if row.path.is_symlink() or not (row.path.is_file() or row.path.is_dir()):
                    issue = tr('Fichier ordinaire requis.')
                elif row.file_signature is None or fingerprint(row.path) != row.file_signature:
                    issue = tr('Fichier modifié : actualisez le dossier.')
                elif os.path.lexists(target) and target not in changed_sources:
                    issue = tr('Ce nom existe déjà.')
            except OSError as error:
                issue = str(error)
        plans.append(Rename(row.path, target, row.file_signature, issue))
    targets = {}
    for p in plans:
        targets[p.destination] = targets.get(p.destination, 0) + 1
    return [
        Rename(
            p.source,
            p.destination,
            p.signature,
            p.issue or (tr('Nom proposé plusieurs fois.') if targets[p.destination] > 1 else ''),
        )
        for p in plans
    ]


def external_command(program, arguments, paths):
    program = program.strip()
    executable = shutil.which(os.path.expanduser(program))
    if not executable:
        raise ValueError(
            trf(
                'Logiciel introuvable : \x1f0\x1f. Installez-le avec votre logithèque ou choisissez un autre programme.',
                program,
            )
        )
    try:
        args = shlex.split(arguments)
    except ValueError as error:
        raise ValueError(tr('Options invalides : vérifiez les guillemets.')) from error
    if not paths:
        raise ValueError(tr('Sélectionnez au moins un fichier.'))
    for path in paths:
        try:
            mode = path.lstat().st_mode
        except OSError:
            mode = 0
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ValueError(trf('Fichier introuvable : \x1f0\x1f. Actualisez le dossier.', path))
    return (executable, args + [str(path.absolute()) for path in paths])


def folder_rename_rows(folder):
    """Immediate ordinary children, including hidden entries; no recursion."""
    from .metadata import basic_entry

    folder = os.fspath(folder)
    with os.scandir(folder) as entries:
        rows = []
        for entry in entries:
            if entry.is_symlink():
                continue
            if entry.is_file(follow_symlinks=False) or entry.is_dir(follow_symlinks=False):
                rows.append(basic_entry(Path(entry.path), entry.is_dir(follow_symlinks=False)))
    return sorted(rows, key=lambda row: row.path.name.casefold())


def find_external_renames(rows):
    'Follow in-place renames by identity; never guess by similar names.'
    pending = []
    for row in rows:
        try:
            if row.file_signature and fingerprint(row.path) != row.file_signature:
                pending.append(row)
        except OSError:
            pending.append(row)
    directories = {}
    for row in pending:
        if row.path.parent in directories:
            continue
        identities = {}
        try:
            for path in row.path.parent.iterdir():
                try:
                    identities.setdefault(fingerprint(path), []).append(path)
                except OSError:
                    pass
        except OSError:
            pass
        directories[row.path.parent] = identities
    renamed = {}
    for row in pending:
        matches = directories[row.path.parent].get(row.file_signature, [])
        if len(matches) == 1 and matches[0] != row.path:
            renamed[row.path] = matches[0]
    return renamed
