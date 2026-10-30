"""XDG Templates menu, populated with native asynchronous GIO enumeration.

Nautilus reference: nautilus-files-view.c (TEMPLATE_LIMIT=30,
MAX_MENU_LEVELS=5). The original template is never modified.
"""
from gi.repository import Gio, GLib
from .i18n import tr


class Templates:
    def __init__(self, window):
        self.window = window
        self.closed = False
        self.menu = Gio.Menu()
        self.cancel = Gio.Cancellable()
        self.monitors = []
        self.timer = 0
        self.reload()

    def reload(self):
        if self.closed:
            return False
        self.timer = 0
        self.cancel.cancel()
        self.cancel = Gio.Cancellable()
        for monitor in self.monitors:
            monitor.cancel()
        self.monitors.clear()
        self.menu.remove_all()
        self.menu.append(tr('Dossier…'), 'win.new-folder')
        self.menu.append(tr('Fichier texte…'), 'win.new-text-file')
        path = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_TEMPLATES)
        if path and path != GLib.get_home_dir():
            section = Gio.Menu()
            self.menu.append_section(None, section)
            cancel = self.cancel
            def finished():
                if not self.closed and not cancel.is_cancelled() and self.cancel is cancel and section.get_n_items():
                    self.menu.remove(1)
            self.read(Gio.File.new_for_path(path), section, 0, cancel, finished)
        return False

    def changed(self, *_):
        if not self.closed and not self.timer:
            self.timer = GLib.timeout_add(100, self.reload)

    def read(self, folder, menu, depth, cancel, finished=lambda: None):
        if depth > 5 or cancel.is_cancelled():
            finished()
            return
        try:
            monitor = folder.monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self.monitors.append(monitor)
            monitor.connect('changed', self.changed)
        except GLib.Error:
            pass
        attributes = 'standard::name,standard::display-name,standard::type,standard::is-hidden,access::can-read'

        def ready(file, result):
            try:
                enumerator = file.enumerate_children_finish(result)
            except GLib.Error:
                finished()
                return
            infos = []
            def batch(source, result):
                try:
                    values = source.next_files_finish(result)
                except GLib.Error:
                    source.close_async(GLib.PRIORITY_DEFAULT, None, None)
                    return
                if values and not cancel.is_cancelled():
                    infos.extend(values)
                    source.next_files_async(64, GLib.PRIORITY_DEFAULT, cancel, batch)
                    return
                source.close_async(GLib.PRIORITY_DEFAULT, None, None)
                if cancel.is_cancelled():
                    return
                infos.sort(key=lambda info: GLib.utf8_collate_key_for_filename(info.get_display_name(), -1))
                shown = 0
                pending = [1]
                def complete():
                    pending[0] -= 1
                    if pending[0] == 0:
                        finished()
                for info in infos:
                    directory = info.get_file_type() == Gio.FileType.DIRECTORY
                    if info.get_is_hidden() and (directory or not self.window.hidden):
                        continue
                    child = folder.get_child(info.get_name())
                    if directory:
                        children = Gio.Menu()
                        menu.append_submenu(info.get_display_name().replace('_', '__'), children)
                        pending[0] += 1
                        def child_done(children=children):
                            if not children.get_n_items():
                                for index in range(menu.get_n_items()):
                                    if menu.get_item_link(index, 'submenu') == children:
                                        menu.remove(index)
                                        break
                            complete()
                        self.read(child, children, depth + 1, cancel, child_done)
                    elif info.get_file_type() == Gio.FileType.REGULAR and info.get_attribute_boolean('access::can-read'):
                        entry = Gio.MenuItem.new(info.get_display_name().replace('_', '__'), None)
                        entry.set_action_and_target_value('win.new-from-template', GLib.Variant('s', child.get_uri()))
                        menu.append_item(entry)
                    else:
                        continue
                    shown += 1
                    if shown == 30:
                        break
                complete()
            enumerator.next_files_async(64, GLib.PRIORITY_DEFAULT, cancel, batch)
        folder.enumerate_children_async(attributes, Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS,
                                        GLib.PRIORITY_DEFAULT, cancel, ready)

    def close(self):
        self.closed = True
        self.cancel.cancel()
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        for monitor in self.monitors:
            monitor.cancel()
