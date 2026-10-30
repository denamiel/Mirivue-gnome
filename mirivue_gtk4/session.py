"""Optional Mirivue session state; native tabs load locations when selected.

Two-pane sessions have no exact Nautilus counterpart. This feature is opt-in,
keeps Mirivue's own settings, and never saves URI passwords.
"""
from gi.repository import Gio, GLib
from .pane import Pane


def location(pane):
    file = getattr(pane, 'pending_location', None)
    if file is None:
        file = pane.remote_file or (Gio.File.new_for_uri('trash:///') if pane.is_trash else
                Gio.File.new_for_uri('starred:///') if pane.is_starred else Gio.File.new_for_path(str(pane.folder)))
    try:
        uri = GLib.Uri.parse(file.get_uri(), GLib.UriFlags.HAS_PASSWORD | GLib.UriFlags.HAS_AUTH_PARAMS)
        return uri.to_string_partial(GLib.UriHideFlags.PASSWORD | GLib.UriHideFlags.AUTH_PARAMS)
    except GLib.Error:
        return ''


def snapshot(window):
    groups = []
    for group in window.tab_groups:
        groups.append(dict(locations=[location(group.get_nth_page(index)) for index in range(group.get_n_pages())],
                           selected=group.get_current_page()))
    return dict(version=1, groups=groups, split=window.tab_groups[1].get_visible(),
                active=window.tab_groups.index(window.active.tabs))


def restore(window):
    data = window.state.settings.get('tab_session', {})
    if not isinstance(data, dict):
        return False
    groups = data.get('groups', [])
    if data.get('version') != 1 or not isinstance(groups, list) or not groups:
        return False
    supported = {'file', 'smb', 'sftp', 'ftp', 'ftps', 'dav', 'davs', 'nfs', 'trash', 'starred', 'recent'}
    restored = False
    for index, saved in enumerate(groups[:2]):
        if not isinstance(saved, dict) or not isinstance(saved.get('locations'), list):
            continue
        group = window.tab_groups[index]
        first = True
        for uri in saved['locations'][:100]:
            if not isinstance(uri, str) or len(uri) > 16384:
                continue
            file = Gio.File.new_for_uri(uri)
            if file.get_uri_scheme() not in supported:
                continue
            if first:
                pane = group.get_nth_page(0)
                first = False
            else:
                pane = Pane(window, group.slot)
                group.view.append(pane)
            pane.pending_location = file
            page = group.view.get_page(pane)
            page.set_title(file.get_basename() or '/')
            page.set_tooltip(file.get_parse_name())
            restored = True
        selected = saved.get('selected', 0)
        if type(selected) is int and 0 <= selected < group.get_n_pages():
            group.set_current_page(selected)
    window.tab_groups[1].set_visible(data.get('split') is True)
    active = 1 if data.get('active') == 1 and window.tab_groups[1].get_visible() else 0
    target = window.tab_groups[active]
    def finish():
        if not window.closed:
            target.selected_changed()
            window.navigation_pane = window.active
        return False
    GLib.idle_add(finish, priority=GLib.PRIORITY_LOW)
    return restored
