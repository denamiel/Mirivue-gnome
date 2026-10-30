"""Verified, session-local undo for transfers and batch renames."""

from ..i18n import tr, trf
from dataclasses import dataclass
from pathlib import Path
import os
import stat
import uuid
import threading
from functools import wraps
from .extensions import fingerprint
from .file_moves import move_one
from .media import companion
from .platform_services import services


@dataclass
class Record:
    source: Path
    target: Path
    copy: bool
    signature: tuple
    source_signature: tuple | None
    side_signature: tuple | None = None
    source_side_signature: tuple | None = None
    companions: bool = True


@dataclass
class FolderRecord:
    path: Path


@dataclass
class RemovedFolderRecord:
    path: Path
    mode: int
    restored_identity: tuple | None = None


@dataclass
class RenameRecord:
    pairs: tuple
    signatures: tuple


@dataclass
class TrashRecord:
    source: Path
    uri: str
    signature: tuple
    restored_signature: tuple | None = None


@dataclass
class LinkRecord:
    path: Path
    link_target: str
    signature: tuple


@dataclass
class BatchRecord:
    key: object
    entries: list


def record_paths(item):
    if isinstance(item, BatchRecord):
        return [path for child, _applied in item.entries for path in record_paths(child)]
    if isinstance(item, RenameRecord):
        return [path for pair in item.pairs for path in pair]
    if isinstance(item, (FolderRecord, RemovedFolderRecord, LinkRecord)):
        return [item.path]
    if isinstance(item, TrashRecord):
        return [item.source]
    return [item.source, item.target]


def individual_records(item):
    return [child for child, _ in item.entries] if isinstance(item, BatchRecord) else [item]


def synchronized(method):
    @wraps(method)
    def locked(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return locked


def _rename_transaction(pairs, signatures):
    """Move a complete verified batch, including XMP pairs, without overwrites."""
    sources = [source for source, _ in pairs]
    destinations = [target for _, target in pairs]
    if len(set(sources)) != len(sources) or len(set(destinations)) != len(destinations):
        raise ValueError(tr('Noms répétés dans le renommage à annuler.'))
    for (source, target), signature in zip(pairs, signatures):
        if source.parent != target.parent:
            raise ValueError(tr('Renommage hors du dossier initial.'))
        info = source.lstat()
        if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)) or fingerprint(source) != signature:
            raise ValueError(tr('Un fichier renommé a changé : opération interrompue.'))
        if os.path.lexists(target) and target not in sources:
            raise FileExistsError(trf('Un ancien nom est désormais occupé : \x1f0\x1f', str(target)))
    staged = []
    published = []
    try:
        for source, target in pairs:
            temporary = source.with_name('.mirivue-undo-' + uuid.uuid4().hex)
            services.rename_no_replace(source, temporary)
            staged.append((source, temporary, target))
        for source, temporary, target in staged:
            services.rename_no_replace(temporary, target)
            published.append((source, temporary, target))
    except Exception:
        for source, temporary, target in reversed(published):
            services.rename_no_replace(target, temporary)
        for source, temporary, target in reversed(staged):
            if os.path.lexists(temporary):
                services.rename_no_replace(temporary, source)
        raise
    return tuple(fingerprint(target) for _, target in pairs)


class UndoManager:
    def __init__(self):
        self.undo_stack = []
        self.redo_stack = []
        self.lock = threading.RLock()

    def prepare_record(self, source, target, copy, companions=True):
        source, target = Path(source), Path(target)
        # The complete tree signature is checked before removing a copied tree.
        if not (target.is_symlink() or target.is_file() or target.is_dir()):
            return False
        target_side = companion(target)
        source_side = companion(source)
        if companions and target_side.exists() and (target_side.is_symlink() or not target_side.is_file()):
            return False
        if companions and source_side.exists() and (source_side.is_symlink() or not source_side.is_file()):
            return False
        item = Record(
            source,
            target,
            bool(copy),
            _signature(target),
            _signature(source) if copy and source.exists() else None,
            fingerprint(target_side) if companions and target_side.is_file() else None,
            fingerprint(source_side) if companions and copy and source_side.is_file() else None,
            companions,
        )
        return item

    @synchronized
    def record_prepared(self, item, group=None):
        if not item:
            return False
        if group is None:
            self.undo_stack.append(item)
        elif self.undo_stack and isinstance(self.undo_stack[-1], BatchRecord) and self.undo_stack[-1].key == group:
            self.undo_stack[-1].entries.append((item, True))
        else:
            self.undo_stack.append(BatchRecord(group, [(item, True)]))
        self.undo_stack = self.undo_stack[-30:]
        self.redo_stack.clear()
        return True

    @synchronized
    def discard_group(self, key):
        self.undo_stack[:] = [item for item in self.undo_stack
                              if not isinstance(item, BatchRecord) or item.key != key]

    def record(self, source, target, copy, group=None):
        return self.record_prepared(self.prepare_record(source, target, copy), group)

    @synchronized
    def record_new_folder(self, path):
        path = Path(path)
        if not path.is_dir() or any(path.iterdir()):
            return False
        self.undo_stack.append(FolderRecord(path))
        self.undo_stack = self.undo_stack[-30:]
        self.redo_stack.clear()
        return True

    @synchronized
    def record_rename(self, pairs):
        pairs = tuple((Path(source), Path(target)) for source, target in pairs)
        if not pairs:
            return False
        try:
            signatures = tuple(fingerprint(target) for _, target in pairs)
        except OSError:
            return False
        self.undo_stack.append(RenameRecord(pairs, signatures))
        self.undo_stack = self.undo_stack[-30:]
        self.redo_stack.clear()
        return True

    @synchronized
    def undo(self):
        if not self.undo_stack:
            raise ValueError(tr('Aucune opération de fichier à annuler.'))
        item = self.undo_stack[-1]
        if isinstance(item, BatchRecord):
            self._reverse_batch(item, False)
            self.undo_stack.pop()
            self.redo_stack.append(item)
            return item
        if isinstance(item, LinkRecord):
            if fingerprint(item.path) != item.signature or not item.path.is_symlink():
                raise ValueError(tr('Un élément de l’opération a changé ; annulation ou rétablissement interrompu.'))
            item.path.unlink()
            self.undo_stack.pop()
            self.redo_stack.append(item)
            return item
        if isinstance(item, RemovedFolderRecord):
            from . import gio_backend
            Gio = gio_backend._gio()
            file = Gio.File.new_for_path(str(item.path))
            file.make_directory(None)
            file.set_attribute_uint32('unix::mode', item.mode, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
            item.restored_identity = fingerprint(item.path)[:2]
            self.undo_stack.pop()
            self.redo_stack.append(item)
            return item
        if isinstance(item, TrashRecord):
            if not item.uri:
                raise ValueError(tr('Le fichier est dans la corbeille, mais son suivi n’est pas disponible.'))
            from . import trash
            trash.restore_tracked(item.uri, item.source, item.signature)
            item.restored_signature = _signature(item.source)
            self.undo_stack.pop()
            self.redo_stack.append(item)
            return item
        if isinstance(item, FolderRecord):
            item.path.rmdir()
            self.undo_stack.pop()
            self.redo_stack.append(item)
            return item
        if isinstance(item, RenameRecord):
            inverse = tuple((target, source) for source, target in item.pairs)
            item.signatures = _rename_transaction(inverse, item.signatures)
            self.undo_stack.pop()
            self.redo_stack.append(item)
            return item
        if _signature(item.target) != item.signature or _side_signature(item.target, item.companions) != item.side_signature:
            raise ValueError(tr('Le fichier a changé : annulation interrompue.'))
        if item.copy:
            if item.target.is_dir():
                from . import gio_backend
                Gio = gio_backend._gio()
                gio_backend.remove(Gio.File.new_for_path(str(item.target)), True)
            else:
                item.target.unlink()
            if item.side_signature is not None:
                companion(item.target).unlink()
        else:
            if (
                os.path.lexists(item.source)
                or item.side_signature is not None
                and os.path.lexists(companion(item.source))
            ):
                raise FileExistsError(tr('Le nom source est déjà occupé.'))
            _move_record(item, item.target, item.source)
            item.source_signature = _signature(item.source)
            item.source_side_signature = _side_signature(item.source, item.companions)
        self.undo_stack.pop()
        self.redo_stack.append(item)
        return item

    @synchronized
    def redo(self):
        if not self.redo_stack:
            raise ValueError(tr('Aucune opération à rétablir.'))
        item = self.redo_stack[-1]
        if isinstance(item, BatchRecord):
            self._reverse_batch(item, True)
            self.redo_stack.pop()
            self.undo_stack.append(item)
            return item
        if isinstance(item, LinkRecord):
            from . import gio_backend
            Gio = gio_backend._gio()
            Gio.File.new_for_path(str(item.path)).make_symbolic_link(item.link_target, None)
            item.signature = fingerprint(item.path)
            self.redo_stack.pop()
            self.undo_stack.append(item)
            return item
        if isinstance(item, RemovedFolderRecord):
            if fingerprint(item.path)[:2] != item.restored_identity:
                raise ValueError(tr('Le dossier restauré a changé ; opération interrompue.'))
            item.path.rmdir()
            self.redo_stack.pop()
            self.undo_stack.append(item)
            return item
        if isinstance(item, TrashRecord):
            from . import trash
            from .file_safety import check_removal
            if _signature(item.source) != item.restored_signature:
                raise ValueError(tr('Le fichier restauré a changé ; rétablissement interrompu.'))
            check_removal(item.source, recursive=True)
            uri = trash.trash_tracked(item.source, previous_uri=item.uri)
            item.uri = uri
            item.signature = trash.entry_signature(uri) if uri else None
            self.redo_stack.pop()
            self.undo_stack.append(item)
            return item
        if isinstance(item, FolderRecord):
            item.path.mkdir()
            self.redo_stack.pop()
            self.undo_stack.append(item)
            return item
        if isinstance(item, RenameRecord):
            item.signatures = _rename_transaction(item.pairs, item.signatures)
            self.redo_stack.pop()
            self.undo_stack.append(item)
            return item
        if (
            os.path.lexists(item.target)
            or item.source_side_signature is not None
            and os.path.lexists(companion(item.target))
        ):
            raise FileExistsError(tr('Le nom de destination est déjà occupé.'))
        if (
            not os.path.lexists(item.source)
            or _signature(item.source) != item.source_signature
            or _side_signature(item.source, item.companions) != item.source_side_signature
        ):
            raise ValueError(tr('Le fichier source a changé : rétablissement interrompu.'))
        _move_record(item, item.source, item.target, item.copy)
        item.signature = _signature(item.target)
        item.side_signature = _side_signature(item.target, item.companions)
        self.redo_stack.pop()
        self.undo_stack.append(item)
        return item

    def _reverse_batch(self, batch, redo):
        candidates = [(index, item) for index, (item, applied) in enumerate(batch.entries) if applied != redo]
        # Check the complete action before changing any child. If an I/O error
        # still occurs later, per-child flags retain the exact completed state.
        for _index, item in candidates:
            if isinstance(item, RemovedFolderRecord):
                if not redo and os.path.lexists(item.path):
                    raise FileExistsError(tr('Le dossier source a été recréé ; annulation interrompue.'))
                if redo and fingerprint(item.path)[:2] != item.restored_identity:
                    raise ValueError(tr('Le dossier restauré a changé ; opération interrompue.'))
                continue
            if isinstance(item, LinkRecord):
                if redo and os.path.lexists(item.path) or not redo and fingerprint(item.path) != item.signature:
                    raise ValueError(tr('Un élément de l’opération a changé ; annulation ou rétablissement interrompu.'))
                continue
            if isinstance(item, TrashRecord):
                from . import trash
                if redo:
                    if _signature(item.source) != item.restored_signature:
                        raise ValueError(tr('Le fichier restauré a changé ; rétablissement interrompu.'))
                elif not item.uri or os.path.lexists(item.source) or trash.entry_signature(item.uri) != item.signature:
                    raise ValueError(tr('La restauration de la sélection n’est plus possible.'))
                continue
            if not isinstance(item, Record):
                continue
            path = item.source if redo else item.target
            expected = item.source_signature if redo else item.signature
            side_expected = item.source_side_signature if redo else item.side_signature
            if _signature(path) != expected or _side_signature(path, item.companions) != side_expected:
                raise ValueError(tr('Un élément de l’opération a changé ; annulation ou rétablissement interrompu.'))
            occupied = item.target if redo else item.source
            if (redo or not item.copy) and os.path.lexists(occupied):
                raise FileExistsError(tr('Un nom de destination est déjà occupé.'))
        for index, item in (candidates if redo else reversed(candidates)):
            manager = UndoManager()
            (manager.redo_stack if redo else manager.undo_stack).append(item)
            if redo:
                manager.redo()
            else:
                manager.undo()
            batch.entries[index] = (item, redo)


def _move_record(item, source, target, copy=False):
    if item.companions:
        return move_one(source, target, copy_only=copy)
    from . import gio_backend
    Gio = gio_backend._gio()
    gio_backend.transfer([Gio.File.new_for_path(str(source))],
                         Gio.File.new_for_path(str(target.parent)), move=not copy,
                         names={Gio.File.new_for_path(str(source)).get_uri(): target.name})


def _side_signature(path, enabled=True):
    if not enabled:
        return None
    side = companion(path)
    return fingerprint(side) if side.is_file() else None


def _signature(path):
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        return fingerprint(path)
    # A moved tree must still have exactly the same members when reversed.
    # A fixed bound keeps this check responsive in the GTK event loop.
    entries = []
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in sorted(dirs + files):
            child = Path(root) / name
            entries.append((str(child.relative_to(path)), fingerprint(child)))
            if len(entries) > 100000:
                raise ValueError(tr('Dossier trop volumineux pour l’historique.'))
    return tuple(entries)
