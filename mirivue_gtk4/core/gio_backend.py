"""GVfs-capable file inventory and conservative copy/move operations."""

import logging
from ..i18n import tr, trf
import uuid


def _gio():
    from gi.repository import Gio

    return Gio


def local_icon(path, row=None):
    """Ask the file backend for its actual content icon, off the UI thread."""
    Gio = _gio()
    try:
        from gi.repository import GLib

        info = Gio.File.new_for_path(str(path)).query_info(
            'standard::icon,standard::content-type,standard::type,standard::is-hidden,standard::is-backup,metadata::custom-icon',
            Gio.FileQueryInfoFlags.NONE,
            None,
        )
        if row is not None:
            row.file_hidden = info.get_attribute_boolean('standard::is-hidden') or info.get_attribute_boolean('standard::is-backup')
            row.content_type = info.get_content_type()
        custom = info.get_attribute_string('metadata::custom-icon')
        if custom:
            return Gio.FileIcon.new(Gio.File.new_for_uri(custom))
        if info.get_file_type() == Gio.FileType.DIRECTORY:
            special = {
                'HOME': 'user-home',
                'DESKTOP': 'user-desktop',
                'DOCUMENTS': 'folder-documents',
                'DOWNLOAD': 'folder-download',
                'MUSIC': 'folder-music',
                'PICTURES': 'folder-pictures',
                'VIDEOS': 'folder-videos',
                'TEMPLATES': 'folder-templates',
                'PUBLIC_SHARE': 'folder-publicshare',
            }
            for name, icon_name in special.items():
                if name == 'HOME':
                    location = GLib.get_home_dir()
                else:
                    kind = getattr(GLib.UserDirectory, 'DIRECTORY_' + name, None)
                    location = GLib.get_user_special_dir(kind) if kind is not None else None
                if location and str(path) == location:
                    return Gio.ThemedIcon.new(icon_name)
        return info.get_icon()
    except Exception:
        return None


def enrich_file_info(row):
    row.file_icon = local_icon(row.path, row)


DIRECTORY_ATTRIBUTES = ('standard::name,standard::display-name,standard::type,standard::size,'
                        'standard::icon,standard::content-type,standard::is-hidden,standard::is-backup,'
                        'time::modified,thumbnail::path,thumbnail::is-valid,'
                        'access::can-rename,access::can-delete,access::can-trash')


def row_from_info(folder, info):
    """Keep the actual GFile, including its backend URI; never fabricate a local path."""
    from pathlib import Path
    from .metadata import Video, quantity
    Gio = _gio()
    file = folder.get_child(info.get_name())
    directory = info.get_file_type() == Gio.FileType.DIRECTORY
    # Path supplies only a basename to code that renders names. Every remote
    # operation must use gio_file, and never hand this display-only path to I/O.
    row = Video(Path(info.get_name()), is_dir=directory, is_video=False, media_type='other')
    row.gio_file = file
    row.content_type = (info.get_content_type() if info.has_attribute('standard::content-type') else None) or 'application/octet-stream'
    row.file_icon = info.get_icon() if info.has_attribute('standard::icon') else Gio.content_type_get_icon(row.content_type)
    row.file_hidden = info.get_attribute_boolean('standard::is-hidden') or info.get_attribute_boolean('standard::is-backup')
    row.file_capabilities = {action: info.get_attribute_boolean('access::can-' + action)
                             for action in ('rename', 'delete', 'trash')}
    row.values[0] = info.get_display_name()
    size = info.get_size() if info.has_attribute('standard::size') else 0
    row.values[1] = '' if directory else quantity(size, ['o', 'Kio', 'Mio', 'Gio', 'Tio'], 1024)
    row.sort_values[0] = info.get_display_name()
    row.sort_values[1] = -1 if directory else size
    if info.has_attribute('time::modified'):
        row.modified_ns = info.get_attribute_uint64('time::modified') * 1000000000
        row.sort_values[14] = row.modified_ns
    for kind in ('video', 'audio', 'image'):
        if Gio.content_type_is_a(row.content_type, kind + '/*'):
            row.media_type = kind
            break
    return row


def browse(folder, cancellable=None, include_icons=False):
    Gio = _gio()
    attributes = 'standard::name,standard::display-name,standard::type,standard::size'
    if include_icons:
        attributes += ',standard::icon,standard::content-type'
    enumerator = folder.enumerate_children(attributes, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, cancellable)
    entries = []
    try:
        while True:
            info = enumerator.next_file(cancellable)
            if info is None:
                break
            entry = (
                info.get_display_name(),
                folder.get_child(info.get_name()),
                info.get_file_type() == Gio.FileType.DIRECTORY,
                info.get_size(),
            )
            entries.append(entry + (info.get_icon(),) if include_icons else entry)
    finally:
        enumerator.close(cancellable)
    return sorted(entries, key=lambda item: (not item[2], item[0].casefold()))


def _copy_tree(source, target, cancellable, progress):
    Gio = _gio()
    info = source.query_info(
        'standard::type,standard::size', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, cancellable
    )
    kind = info.get_file_type()
    if kind == Gio.FileType.DIRECTORY:
        target.make_directory(cancellable)
        for _, child, _, _ in browse(source, cancellable):
            _copy_tree(child, target.get_child(child.get_basename()), cancellable, progress)
    elif kind == Gio.FileType.REGULAR:
        source.copy(
            target,
            Gio.FileCopyFlags.NONE,
            cancellable,
            lambda *values: progress(values[0], values[1]) if len(values) > 1 else None,
            None,
        )
        copied = target.query_info('standard::size', Gio.FileQueryInfoFlags.NONE, cancellable).get_size()
        if copied != info.get_size():
            raise IOError(tr('Copie distante incomplète.'))
    else:
        raise ValueError(tr('Type de fichier distant non pris en charge.'))


def _remove_own_tree(target):
    """Clean only an unpublished, uniquely named stage created by this call."""
    Gio = _gio()
    try:
        info = target.query_info('standard::type', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, None)
        if info.get_file_type() == Gio.FileType.DIRECTORY:
            for _, child, _, _ in browse(target):
                _remove_own_tree(child)
        target.delete(None)
    except Exception:
        logging.getLogger('mirivue-gtk4').warning(
            'Nettoyage incomplet de la copie temporaire %s', target.get_uri(), exc_info=True
        )


def _tree_manifest(root, cancellable, with_identity=False):
    """Describe every entry before publishing or removing a copied tree."""
    Gio = _gio()
    entries = {}

    def visit(file, relative):
        info = file.query_info(
            'standard::type,standard::size,time::modified,time::modified-usec,etag::value',
            Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
            cancellable,
        )
        kind = info.get_file_type()
        if kind not in (Gio.FileType.DIRECTORY, Gio.FileType.REGULAR):
            raise ValueError(tr('Type de fichier distant non pris en charge.'))
        identity = (
            (
                info.get_attribute_uint64('time::modified'),
                info.get_attribute_uint32('time::modified-usec'),
                info.get_attribute_string('etag::value'),
            )
            if with_identity
            else ()
        )
        entries[relative] = (kind, info.get_size() if kind == Gio.FileType.REGULAR else 0, *identity)
        if kind == Gio.FileType.DIRECTORY:
            for _, child, _, _ in browse(file, cancellable):
                visit(child, relative + '/' + child.get_basename())

    visit(root, '')
    return entries


def _delete_moved_tree(root, cancellable):
    """Remove the verified source through GIO, children before parents."""
    Gio = _gio()
    info = root.query_info('standard::type', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, cancellable)
    if info.get_file_type() == Gio.FileType.DIRECTORY:
        for _, child, _, _ in browse(root, cancellable):
            _delete_moved_tree(child, cancellable)
    root.delete(cancellable)


def remove(file, permanent=False, cancelled=lambda: False):
    """Use backend trash, or an explicitly confirmed NOFOLLOW recursive delete."""
    Gio = _gio()
    operation = Gio.Cancellable()
    if not permanent:
        if cancelled():
            raise InterruptedError()
        file.trash(operation)
        return

    def visit(source):
        if cancelled():
            operation.cancel()
            raise InterruptedError()
        info = source.query_info('standard::type', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, operation)
        if info.get_file_type() == Gio.FileType.DIRECTORY:
            for _, child, _, _ in browse(source, operation):
                visit(child)
        source.delete(operation)

    visit(file)


def transfer(sources, destination, move=False, cancelled=lambda: False, progress=lambda done, total: None):
    """Never overwrite. Publish a complete tree before removing its source."""
    Gio = _gio()
    results = []
    for source in sources:
        if cancelled():
            raise InterruptedError()
        name = source.get_basename()
        if not name or name in ('.', '..'):
            raise ValueError(tr('Nom de source invalide.'))
        target = destination.get_child(name)
        if target.query_exists(None):
            raise FileExistsError(trf('Un élément porte déjà ce nom dans la destination : \x1f0\x1f', name))
        if source.equal(target) or destination.has_prefix(source):
            raise ValueError(tr('Destination située dans la source.'))
        operation = Gio.Cancellable()

        def update(done, total):
            if cancelled():
                operation.cancel()
            progress(done, total)

        if move:
            try:
                # GIO can perform its own copy/delete fallback for a regular
                # file across backends. It reports the result as one move.
                source.move(target, Gio.FileCopyFlags.NONE, operation, update, None)
                results.append((source, target, ''))
                continue
            except Exception as error:
                if operation.is_cancelled():
                    raise InterruptedError() from error
                if target.query_exists(None):
                    raise
                # Only an unsupported recursive move warrants a staged copy.
                # Permission, I/O, and network errors must reach the caller.
                from gi.repository import GLib

                if not isinstance(error, GLib.Error) or not error.matches(
                    Gio.io_error_quark(), Gio.IOErrorEnum.WOULD_RECURSE
                ):
                    raise
                kind = source.query_info(
                    'standard::type', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, operation
                ).get_file_type()
                if kind != Gio.FileType.DIRECTORY:
                    raise
        before = _tree_manifest(source, operation, True) if move else None
        stage = destination.get_child('.mirivue-transfer-' + uuid.uuid4().hex)
        try:
            _copy_tree(source, stage, operation, update)
            if cancelled():
                raise InterruptedError()
            if move and _tree_manifest(source, operation, True) != before:
                raise IOError(tr('La source a changé pendant la copie ; elle est conservée.'))
            if move and {name: entry[:2] for name, entry in before.items()} != _tree_manifest(
                stage, operation
            ):
                raise IOError(tr('La copie du dossier est incomplète ; la source est conservée.'))
            if target.query_exists(None):
                raise FileExistsError(tr('La destination est devenue occupée.'))
            stage.move(target, Gio.FileCopyFlags.NO_FALLBACK_FOR_MOVE, operation, None, None)
        except Exception as error:
            _remove_own_tree(stage)
            if operation.is_cancelled():
                raise InterruptedError() from error
            raise
        warning = ''
        if move:
            try:
                if _tree_manifest(source, operation, True) != before:
                    warning = tr('Copie terminée ; la source a changé et a été conservée.')
                else:
                    _delete_moved_tree(source, operation)
            except Exception:
                warning = tr(
                    'Copie terminée ; la suppression de la source a échoué. Vérifiez les deux emplacements.'
                )
        results.append((source, target, warning))
    return results
