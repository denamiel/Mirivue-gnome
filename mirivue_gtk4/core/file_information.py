"""Cancellable GIO property totals for local and GVfs selections."""
from gi.repository import Gio

ATTRIBUTES = 'standard::type,standard::size,standard::content-type,standard::name'


def summarize_files(files, cancellable):
    files = list({file.get_uri(): file for file in files}.values())
    # A selected child must not be counted twice with its selected parent.
    roots = [file for file in files if not any(file.has_prefix(other) for other in files if not file.equal(other))]
    root_uris = {file.get_uri() for file in roots}
    result = dict(files=0, folders=0, bytes=0, types=set(), locations=set(), errors=[])
    stack = list(roots)
    while stack:
        cancellable.set_error_if_cancelled()
        file = stack.pop()
        try:
            info = file.query_info(ATTRIBUTES, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, cancellable)
            if file.get_uri() in root_uris:
                result['types'].add(Gio.content_type_get_description(info.get_content_type() or 'application/octet-stream'))
                parent = file.get_parent()
                result['locations'].add(parent.get_parse_name() if parent else file.get_parse_name())
            if info.get_file_type() != Gio.FileType.DIRECTORY:
                result['files'] += 1
                result['bytes'] += info.get_size()
                continue
            # Nautilus counts the contents, not each selected folder itself.
            if file.get_uri() not in root_uris:
                result['folders'] += 1
            enumerator = file.enumerate_children(ATTRIBUTES, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, cancellable)
            try:
                while True:
                    info = enumerator.next_file(cancellable)
                    if info is None:
                        break
                    stack.append(file.get_child(info.get_name()))
            finally:
                enumerator.close(None)
        except Exception as error:
            if cancellable.is_cancelled():
                raise
            result['errors'].append(file.get_parse_name() + ' : ' + str(error))
    return result
