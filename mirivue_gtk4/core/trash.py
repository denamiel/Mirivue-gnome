"""GVfs trash browsing and safe restore/delete operations."""

from pathlib import Path
from gi.repository import Gio, GLib
from . import metadata
from ..i18n import tr

URI = 'trash:///'
ATTRIBUTES = 'standard::name,standard::display-name,standard::size,standard::type,time::modified,trash::orig-path,standard::icon'


def root():
    return Gio.File.new_for_uri(URI)


def rows(cancelled=lambda: False):
    output = []
    enumerator = root().enumerate_children(ATTRIBUTES, Gio.FileQueryInfoFlags.NONE, None)
    try:
        while True:
            if cancelled():
                raise InterruptedError()
            info = enumerator.next_file(None)
            if info is None:
                break
            name = info.get_name()
            display = info.get_display_name() or name
            is_dir = info.get_file_type() == Gio.FileType.DIRECTORY
            size = None if is_dir else info.get_size()
            modified = info.get_attribute_uint64('time::modified')
            row = metadata.Video(
                Path(name),
                is_dir=is_dir,
                is_video=False,
                media_type='folder' if is_dir else 'other',
                trash_uri=root().get_child(name).get_uri(),
                original_path=info.get_attribute_byte_string('trash::orig-path') or '',
            )
            row.values = (
                [
                    display,
                    metadata.quantity(size, ['o', 'Kio', 'Mio', 'Gio', 'Tio'], 1024),
                ]
                + [''] * 8
                + [tr('Dossier') if is_dir else tr('Dans la corbeille'), '', '', '', '']
            )
            row.sort_values = [
                display.casefold(),
                size or 0,
                -1,
                -1,
                '',
                -1,
                -1,
                '',
                '',
                -1,
                row.values[10],
                '',
                -1,
                -1,
                -1,
            ]
            row.file_icon = info.get_icon()
            row.modified_ns = int(modified) * 1_000_000_000 if modified else None
            row.__post_init__()
            metadata.update_modification(row)
            output.append(row)
    finally:
        enumerator.close(None)
    return output


def icon_name():
    try:
        info = root().query_info('standard::symbolic-icon', Gio.FileQueryInfoFlags.NONE, None)
        icon = info.get_symbolic_icon()
        names = icon.get_names() if isinstance(icon, Gio.ThemedIcon) else []
        if names:
            return names[0]
    except GLib.Error:
        pass
    return 'user-trash-symbolic'


def restore(row):
    if not row.trash_uri or not row.original_path:
        raise ValueError(tr('L’emplacement d’origine est inconnu.'))
    destination = Path(row.original_path)
    if destination.exists():
        raise FileExistsError(tr('Un élément porte déjà ce nom dans le dossier d’origine.'))
    if not destination.parent.is_dir():
        raise FileNotFoundError(tr('Le dossier d’origine n’existe plus.'))
    Gio.File.new_for_uri(row.trash_uri).move(
        Gio.File.new_for_path(str(destination)), Gio.FileCopyFlags.NONE, None, None
    )
    return destination


def delete(row):
    if not row.trash_uri:
        raise ValueError(tr('Élément de corbeille invalide.'))
    Gio.File.new_for_uri(row.trash_uri).delete(None)


def open_item(row):
    if row.trash_uri:
        Gio.AppInfo.launch_default_for_uri(row.trash_uri, None)
