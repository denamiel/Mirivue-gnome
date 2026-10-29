"""Local ZIP/TAR browsing and extraction using Python's standard library.

Archives are read without changing the source. Only ordinary files and
directories are accepted; symlinks and unsafe paths never reach the target.
"""

from ..i18n import tr, trf
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import os
import shutil
import stat
import tarfile
import tempfile
import zipfile
from .platform_services import services
from .extensions import fingerprint


@dataclass(frozen=True)
class ArchiveEntry:
    name: str
    size: int
    is_dir: bool


def _safe_name(name):
    while name.startswith('./'):
        name = name[2:]
    if not name or '\\' in name or '\x00' in name or name.startswith('/'):
        raise ValueError(tr('Chemin dangereux dans l’archive.'))
    raw = name.rstrip('/').split('/')
    parts = PurePosixPath(name).parts
    if not parts or any(part in ('..', '.', '') for part in raw) or ':' in parts[0]:
        raise ValueError(tr('Chemin dangereux dans l’archive.'))
    return parts


def _open_archive(path):
    if zipfile.is_zipfile(path):
        return zipfile.ZipFile(path)
    if tarfile.is_tarfile(path):
        return tarfile.open(path, 'r:*')
    raise ValueError(
        tr('Format d’archive non pris en charge directement. Ouvrez-la avec votre gestionnaire d’archives.')
    )


def _members(archive):
    if isinstance(archive, zipfile.ZipFile):
        for info in archive.infolist():
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_IFMT(mode) and not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise ValueError(tr('L’archive contient un type de fichier non pris en charge.'))
            yield info.filename, info.file_size, info.is_dir(), info
    else:
        for info in archive.getmembers():
            if info.name in ('.', './'):
                continue
            if not (info.isfile() or info.isdir()):
                raise ValueError(tr('L’archive contient un lien ou un fichier spécial.'))
            yield info.name, info.size, info.isdir(), info


def list_entries(path):
    with _open_archive(path) as archive:
        entries = []
        seen = set()
        for name, size, is_dir, _ in _members(archive):
            parts = _safe_name(name)
            normalized = '/'.join(parts)
            if normalized in seen:
                raise ValueError(tr('Un nom est présent plusieurs fois dans l’archive.'))
            seen.add(normalized)
            entries.append(ArchiveEntry(normalized, size, is_dir))
        return entries


def extract(path, destination, selected=None, cancelled=lambda: False, progress=lambda done, total: None):
    destination = Path(destination)
    if not destination.is_dir():
        raise ValueError(tr('Dossier de destination inaccessible.'))
    # Validate the entire inventory before creating any output.
    entries = list_entries(path)
    chosen = set(selected) if selected is not None else None
    if chosen is not None and chosen - {entry.name for entry in entries}:
        raise ValueError(tr('La sélection ne correspond plus à l’archive.'))
    included = [
        entry
        for entry in entries
        if chosen is None or entry.name in chosen or any(entry.name.startswith(name + '/') for name in chosen)
    ]
    if not included:
        return []
    roots = {_safe_name(entry.name)[0] for entry in included}
    for root in roots:
        if os.path.lexists(destination / root):
            raise FileExistsError(trf('Ce nom existe déjà : \x1f0\x1f', root))
    total = sum(entry.size for entry in included if not entry.is_dir)
    done = 0
    with tempfile.TemporaryDirectory(prefix='.mirivue-extraction-', dir=destination) as temp:
        stage = Path(temp)
        with _open_archive(path) as archive:
            inventory = {
                ('/'.join(_safe_name(name))): (is_dir, member)
                for name, _, is_dir, member in _members(archive)
            }
            for entry in included:
                if cancelled():
                    raise InterruptedError()
                is_dir, member = inventory[entry.name]
                target = stage.joinpath(*_safe_name(entry.name))
                if is_dir:
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                source = (
                    archive.open(member)
                    if isinstance(archive, zipfile.ZipFile)
                    else archive.extractfile(member)
                )
                if source is None:
                    raise ValueError(tr('Entrée illisible dans l’archive.'))
                with source, target.open('xb') as output:
                    while True:
                        if cancelled():
                            raise InterruptedError()
                        chunk = source.read(256 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        done += len(chunk)
                        progress(done, total)
                if target.stat().st_size != entry.size:
                    raise ValueError(tr('Extraction incomplète.'))
        # Publish only complete top-level entries. Never replace existing data.
        published = []
        try:
            for root in sorted(roots):
                if cancelled():
                    raise InterruptedError()
                services.rename_no_replace(stage / root, destination / root)
                published.append(destination / root)
        except Exception:
            for target in reversed(published):
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            raise
    return [destination / root for root in sorted(roots)]


def create(sources, destination, format='zip', cancelled=lambda: False, progress=lambda done, total: None):
    """Create a ZIP or tar.gz in a private stage, then publish without overwrite."""
    sources = [Path(source) for source in sources]
    destination = Path(destination)
    if format not in ('zip', 'tar.gz'):
        raise ValueError(tr('Format d’archive non pris en charge.'))
    if not sources or not destination.parent.is_dir():
        raise ValueError(tr('Sources ou destination invalides.'))
    if (
        len({source.name for source in sources}) != len(sources)
        or len({source.parent for source in sources}) != 1
    ):
        raise ValueError(tr('Sélectionnez des éléments du même dossier.'))
    if os.path.lexists(destination):
        raise FileExistsError(tr('Cette archive existe déjà.'))
    entries = []

    def visit(path, arcname):
        if cancelled():
            raise InterruptedError()
        mode = path.lstat().st_mode
        if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise ValueError(tr('Un lien ou un fichier spécial ne peut pas être archivé directement.'))
        entries.append((path, arcname, stat.S_ISDIR(mode), fingerprint(path)))
        if stat.S_ISDIR(mode):
            for child in sorted(path.iterdir()):
                visit(child, arcname + '/' + child.name)

    for source in sources:
        if source.is_dir() and (destination.parent == source or source in destination.parent.parents):
            raise ValueError(tr('La destination est à l’intérieur de la source.'))
        visit(source, source.name)
    total = sum(entry[0].stat().st_size for entry in entries if not entry[2])
    done = 0
    fd, name = tempfile.mkstemp(prefix='.mirivue-archive-', suffix='.tmp', dir=destination.parent)
    os.close(fd)
    stage = Path(name)
    try:
        if format == 'zip':
            with zipfile.ZipFile(stage, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for path, arcname, is_dir, signature in entries:
                    if cancelled():
                        raise InterruptedError()
                    if fingerprint(path) != signature:
                        raise ValueError(tr('Un fichier source a changé pendant la création.'))
                    archive.write(path, arcname + '/' if is_dir else arcname)
                    if not is_dir:
                        done += signature[2]
                        progress(done, total)
                    if fingerprint(path) != signature:
                        raise ValueError(tr('Un fichier source a changé pendant la création.'))
        else:
            with tarfile.open(stage, 'w:gz') as archive:
                for path, arcname, is_dir, signature in entries:
                    if cancelled():
                        raise InterruptedError()
                    if fingerprint(path) != signature:
                        raise ValueError(tr('Un fichier source a changé pendant la création.'))
                    archive.add(path, arcname=arcname, recursive=False)
                    if not is_dir:
                        done += signature[2]
                        progress(done, total)
                    if fingerprint(path) != signature:
                        raise ValueError(tr('Un fichier source a changé pendant la création.'))
        if cancelled():
            raise InterruptedError()
        services.rename_no_replace(stage, destination)
        return destination
    finally:
        stage.unlink(missing_ok=True)
