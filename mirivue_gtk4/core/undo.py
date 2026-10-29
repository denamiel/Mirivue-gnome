"""Verified, session-local undo for transfers and batch renames."""

from ..i18n import tr, trf
from dataclasses import dataclass
from pathlib import Path
import os
import stat
import uuid
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


@dataclass
class FolderRecord:
    path: Path


@dataclass
class RenameRecord:
    pairs: tuple
    signatures: tuple


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

    def record(self, source, target, copy):
        source, target = Path(source), Path(target)
        # Moving a directory only relocates it; removing a copied tree would
        # discard later additions, so copied directories stay outside history.
        if target.is_symlink() or not (target.is_file() or target.is_dir()) or target.is_dir() and copy:
            return False
        target_side = companion(target)
        source_side = companion(source)
        if target_side.exists() and (target_side.is_symlink() or not target_side.is_file()):
            return False
        if source_side.exists() and (source_side.is_symlink() or not source_side.is_file()):
            return False
        item = Record(
            source,
            target,
            bool(copy),
            _signature(target),
            _signature(source) if copy and source.exists() else None,
            fingerprint(target_side) if target_side.is_file() else None,
            fingerprint(source_side) if copy and source_side.is_file() else None,
        )
        self.undo_stack.append(item)
        self.undo_stack = self.undo_stack[-30:]
        self.redo_stack.clear()
        return True

    def record_new_folder(self, path):
        path = Path(path)
        if not path.is_dir() or any(path.iterdir()):
            return False
        self.undo_stack.append(FolderRecord(path))
        self.undo_stack = self.undo_stack[-30:]
        self.redo_stack.clear()
        return True

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

    def undo(self):
        if not self.undo_stack:
            raise ValueError(tr('Aucune opération de fichier à annuler.'))
        item = self.undo_stack[-1]
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
        if _signature(item.target) != item.signature or _side_signature(item.target) != item.side_signature:
            raise ValueError(tr('Le fichier a changé : annulation interrompue.'))
        if item.copy:
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
            move_one(item.target, item.source)
            item.source_signature = _signature(item.source)
            item.source_side_signature = _side_signature(item.source)
        self.undo_stack.pop()
        self.redo_stack.append(item)
        return item

    def redo(self):
        if not self.redo_stack:
            raise ValueError(tr('Aucune opération à rétablir.'))
        item = self.redo_stack[-1]
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
            not item.source.exists()
            or _signature(item.source) != item.source_signature
            or _side_signature(item.source) != item.source_side_signature
        ):
            raise ValueError(tr('Le fichier source a changé : rétablissement interrompu.'))
        move_one(item.source, item.target, copy_only=item.copy)
        item.signature = _signature(item.target)
        item.side_signature = _side_signature(item.target)
        self.redo_stack.pop()
        self.undo_stack.append(item)
        return item


def _side_signature(path):
    side = companion(path)
    return fingerprint(side) if side.is_file() else None


def _signature(path):
    path = Path(path)
    if not path.is_dir():
        return fingerprint(path)
    # A moved tree must still have exactly the same members when reversed.
    # A fixed bound keeps this check responsive in the GTK event loop.
    entries = []
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in sorted(dirs + files):
            child = Path(root) / name
            if child.is_symlink():
                raise ValueError(tr('Dossier contenant un lien non pris en charge par l’historique.'))
            entries.append((str(child.relative_to(path)), fingerprint(child)))
            if len(entries) > 1000:
                raise ValueError(tr('Dossier trop volumineux pour l’historique.'))
    return tuple(entries)
