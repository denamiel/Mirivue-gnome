"""Explicit folder merge using GIO transfers and per-item conflict decisions."""
from pathlib import Path
from gi.repository import Gio
from . import gio_backend
from .undo import RemovedFolderRecord
from ..i18n import tr
from .file_safety import check_removal


def merge(source, target, copy, cancelled, decide, history, confirmed=False):
    records = []
    changed = []
    warnings = []
    complete_history = True
    flags = Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS

    def unique(file):
        parent, name = file.get_parent(), file.get_basename()
        path = Path(name)
        index = 2
        while file.query_exists(None):
            file = parent.get_child(path.stem + ' (' + str(index) + ')' + path.suffix)
            index += 1
        return file

    def visit(file, destination, root=False):
        nonlocal complete_history
        if cancelled():
            raise InterruptedError()
        info = file.query_info('standard::type,unix::mode', flags, None)
        directory = info.get_file_type() == Gio.FileType.DIRECTORY
        if not copy and file.get_path():
            check_removal(file.get_path(), recursive=directory)
        exists = destination.query_exists(None)
        target_directory = exists and destination.query_file_type(flags, None) == Gio.FileType.DIRECTORY
        if exists and directory and target_directory:
            policy = 'merge' if root and confirmed else decide(file, destination, False, True)
            if policy == 'cancel':
                raise InterruptedError()
            if policy == 'skip':
                return
            if policy == 'rename':
                visit(file, unique(destination))
                return
            if policy != 'merge':
                raise ValueError(tr('Opération interrompue.'))
            mode = info.get_attribute_uint32('unix::mode') if info.has_attribute('unix::mode') else 0o755
            for _name, child, _directory, _size in gio_backend.browse(file):
                visit(child, destination.get_child(child.get_basename()))
            if not copy:
                # Delete only an empty directory; skipped/conflicting children stay.
                iterator = file.enumerate_children('standard::name', flags, None)
                try:
                    empty = iterator.next_file(None) is None
                finally:
                    iterator.close(None)
                if empty:
                    file.delete(None)
                    if file.get_path():
                        records.append(RemovedFolderRecord(Path(file.get_path()), mode))
                    else:
                        complete_history = False
                    changed.append(file.get_uri())
            return
        if exists:
            policy = decide(file, destination, not directory and not target_directory, False)
            if policy == 'cancel':
                raise InterruptedError()
            if policy == 'skip':
                return
            if policy == 'rename':
                destination = unique(destination)
            elif policy == 'replace':
                # Explicit replace uses GIO. Never replace a directory or
                # silently switch a failed trash operation to permanent delete.
                if directory or target_directory:
                    return
                if copy:
                    file.copy(destination, Gio.FileCopyFlags.OVERWRITE | Gio.FileCopyFlags.NOFOLLOW_SYMLINKS,
                              None, None, None)
                else:
                    file.move(destination, Gio.FileCopyFlags.OVERWRITE, None, None, None)
                complete_history = False
                changed.extend([file.get_uri(), destination.get_uri()])
                return
            else:
                raise ValueError(tr('Opération interrompue.'))
        gio_backend.transfer([file], destination.get_parent(), move=not copy, cancelled=cancelled,
                             names={file.get_uri(): destination.get_basename()})
        changed.extend([file.get_uri(), destination.get_uri()])
        if file.get_path() and destination.get_path():
            try:
                record = history.prepare_record(file.get_path(), destination.get_path(), copy, companions=False)
                if record:
                    records.append(record)
                else:
                    complete_history = False
            except (OSError, ValueError):
                complete_history = False
        else:
            complete_history = False

    try:
        if source.equal(target) or target.has_prefix(source):
            raise ValueError(tr('Destination située dans la source.'))
        visit(source, target, True)
    except Exception as error:
        warnings.append(str(error) or tr('Opération interrompue.'))
    return records if complete_history else [], changed, warnings, complete_history
