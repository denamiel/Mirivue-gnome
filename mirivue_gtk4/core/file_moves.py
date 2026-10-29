'Explicit, no-overwrite moves. Cross-volume copies are staged before publication.'

from ..i18n import tr

from collections import Counter
import hashlib
import errno
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from .platform_services import services

TECHNICAL = {
    'hdr',
    'sdr',
    'uhd',
    'hd',
    'fhd',
    'hevc',
    'avc',
    'aac',
    'ac',
    'dts',
    'truehd',
    'atmos',
    'bluray',
    'bdrip',
    'brrip',
    'webrip',
    'web',
    'dl',
    'dvdrip',
    'remux',
    'multi',
    'vostfr',
    'vf',
    'vff',
    'vfq',
    'french',
    'eng',
    'mkv',
    'mp4',
    'avi',
    'saison',
    'season',
    'episode',
    'ep',
}


def suggest_folder(paths):
    sequences = []
    for path in paths:
        tokens = re.findall('[^\\W_]+', Path(path).stem, flags=re.UNICODE)
        sequences.append(
            [
                t
                for t in tokens
                if len(t) > 1
                and (not any((c.isdigit() for c in t)))
                and (t.casefold() not in TECHNICAL)
                and (not (t.isupper() and re.fullmatch('[IVXLCDM]+', t)))
            ]
        )
    counts = Counter((word for tokens in sequences for word in {t.casefold() for t in tokens}))
    repeated = {t for t, count in counts.items() if count >= 2}
    if not repeated:
        return tr('Dossier sans titre')
    best = max((counts[t] for t in repeated))
    chosen = {t for t in repeated if counts[t] >= max(2, best - 1)}
    ordered = []
    for tokens in sequences:
        for token in tokens:
            if token.casefold() in chosen and token.casefold() not in {t.casefold() for t in ordered}:
                ordered.append(token)
    return ' '.join(ordered[:6])[:100].strip() or tr('Dossier sans titre')


def available_name(folder, base):
    """Return base, or "base 2", "base 3"… : the first name free in folder."""
    folder = Path(folder)
    if not exists(folder / base):
        return base
    number = 2
    while exists(folder / f'{base} {number}'):
        number += 1
    return f'{base} {number}'


def untitled_folder_name(folder):
    """Default name of a new folder, as in GNOME Files: "Dossier sans titre"."""
    return available_name(folder, tr('Dossier sans titre'))


def valid_name(name):
    return services.validate_portable_name(name) is None


def invalid_name_reason(name):
    return services.validate_portable_name(name) or tr('Nom invalide.')


def exists(path):
    return os.path.lexists(path)


def normalize_sources(paths):
    paths = list(dict.fromkeys((Path(p).absolute() for p in paths)))
    selected = set(paths)
    return [
        p
        for p in paths
        if not any((parent in selected and (not parent.is_symlink()) for parent in p.parents))
    ]


def validate_target(source, target):
    source = Path(source)
    target = Path(target)
    if not exists(source):
        raise OSError(tr('La source n’existe plus.'))
    if not target.parent.is_dir():
        raise OSError(tr('Le dossier de destination est inaccessible.'))
    if source.is_dir() and (not source.is_symlink()):
        resolved = source.resolve()
        parent = target.parent.resolve()
        if parent == resolved or resolved in parent.parents:
            raise OSError(tr('Impossible de déplacer un dossier à l’intérieur de lui-même.'))
    if exists(target):
        raise FileExistsError(tr('Un élément porte déjà ce nom dans la destination.'))


def rename_noreplace(source, target):
    'Atomically rename without replacing a destination on the current OS.'
    services.rename_no_replace(Path(source), Path(target))


def tree_snapshot(path, cancelled=lambda: False):
    output = {}

    def visit(p):
        if cancelled():
            raise InterruptedError()
        st = p.lstat()
        if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode) or stat.S_ISLNK(st.st_mode)):
            raise OSError(tr('Ce dossier contient un élément spécial qui ne peut pas être déplacé.'))
        output[str(p.relative_to(path))] = (
            st.st_dev,
            st.st_ino,
            st.st_mode,
            st.st_size,
            st.st_mtime_ns,
            os.readlink(p) if p.is_symlink() else '',
        )
        if stat.S_ISDIR(st.st_mode):
            for child in p.iterdir():
                visit(child)

    visit(path)
    return output


def _move_one(
    source,
    target,
    cancelled=lambda: False,
    progress=lambda text: None,
    copy_only=False,
    bytes_progress=lambda done, total: None,
):
    source = Path(source)
    target = Path(target)
    validate_target(source, target)
    if cancelled():
        raise InterruptedError()
    if not copy_only:
        try:
            rename_noreplace(source, target)
            return ''
        except OSError as error:
            if error.errno != errno.EXDEV:
                raise
    before = tree_snapshot(source, cancelled)
    total_bytes = 2 * sum((info[3] for info in before.values() if stat.S_ISREG(info[2])))
    transferred = 0
    bytes_progress(0, total_bytes)
    staging = Path(tempfile.mkdtemp(prefix='.mirivue-deplacement-', dir=target.parent))
    staged = staging / source.name

    def copy_file(src, dst):
        nonlocal transferred
        if cancelled():
            raise InterruptedError()
        progress(tr('Copie de ') + Path(src).name)
        digest = hashlib.sha256()
        with open(src, 'rb') as incoming, open(dst, 'xb') as outgoing:
            while True:
                if cancelled():
                    raise InterruptedError()
                data = incoming.read(1024 * 1024)
                if not data:
                    break
                outgoing.write(data)
                digest.update(data)
                transferred += len(data)
                bytes_progress(transferred, total_bytes)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        progress(tr('Vérification de ') + Path(src).name)
        copied = hashlib.sha256()
        with open(dst, 'rb') as stream:
            while True:
                if cancelled():
                    raise InterruptedError()
                data = stream.read(1024 * 1024)
                if not data:
                    break
                copied.update(data)
                transferred += len(data)
                bytes_progress(transferred, total_bytes)
        if copied.digest() != digest.digest():
            raise OSError(tr('La copie ne correspond pas au contenu lu. La source est conservée.'))
        shutil.copystat(src, dst)
        return dst

    try:
        if source.is_symlink():
            os.symlink(os.readlink(source), staged)
        elif source.is_dir():
            shutil.copytree(source, staged, symlinks=True, copy_function=copy_file)
        else:
            copy_file(source, staged)
        if tree_snapshot(source, cancelled) != before:
            raise OSError(tr('La source a changé pendant la copie. Elle a été conservée ; recommencez.'))
        if cancelled():
            raise InterruptedError()
        rename_noreplace(staged, target)
        if copy_only:
            return ''
        try:
            if source.is_dir() and (not source.is_symlink()):
                shutil.rmtree(source)
            else:
                source.unlink()
        except OSError:
            return tr(
                'La copie est disponible à destination, mais la source n’a pas pu être entièrement supprimée. Vérifiez les deux emplacements.'
            )
        return ''
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def move_one(
    source,
    target,
    cancelled=lambda: False,
    progress=lambda text: None,
    copy_only=False,
    bytes_progress=lambda done, total: None,
):
    from .media import companion, AUDIO_EXT, IMAGE_EXT
    from .metadata import EXTENSIONS
    from .extensions import fingerprint

    side = companion(source)
    target_side = companion(target)
    has_side = (
        source.suffix.lower() in EXTENSIONS | AUDIO_EXT | IMAGE_EXT and source.is_file() and side.is_file()
    )
    created = False
    signature = None
    published = None
    if has_side:
        if side.is_symlink() or exists(target_side):
            raise OSError(errno.EEXIST, tr('Conflit de fichier compagnon XMP'), str(target_side))
        signature = fingerprint(side)
        _move_one(side, target_side, cancelled, progress, copy_only=True)
        published = fingerprint(target_side)
        created = True
    try:
        warning = _move_one(source, target, cancelled, progress, copy_only, bytes_progress)
    except BaseException:
        if created and fingerprint(target_side) == published:
            target_side.unlink()
        raise
    if has_side and (not copy_only):
        try:
            if fingerprint(side) == signature:
                side.unlink()
            else:
                warning = (warning or '') + tr(' Le compagnon XMP source a changé et a été conservé.')
        except OSError:
            warning = (warning or '') + tr(' Le compagnon XMP source n’a pas pu être retiré.')
    return warning
