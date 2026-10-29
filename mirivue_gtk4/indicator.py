"""Minimal StatusNotifierItem support for GNOME AppIndicator extensions."""

from pathlib import Path
import json, os
from gi.repository import Gio, GLib

KNOWN_MARKERS = ('appindicator', 'statusnotifier', 'kstatusnotifier')


def appindicator_extension_installed(search_roots=None):
    """Return true only for an installed GNOME extension that hosts SNI items."""
    if search_roots is None:
        override = os.environ.get('MIRIVUE_GNOME_EXTENSION_DIRS', '')
        search_roots = (
            [Path(p) for p in override.split(os.pathsep) if p]
            if override
            else [
                Path.home() / '.local/share/gnome-shell/extensions',
                Path('/usr/share/gnome-shell/extensions'),
            ]
        )
    for root in map(Path, search_roots):
        try:
            files = root.glob('*/metadata.json')
        except OSError:
            continue
        for path in files:
            try:
                metadata = json.loads(path.read_text(encoding='utf-8'))
                identity = ' '.join(
                    str(metadata.get(key, '')) for key in ('uuid', 'name', 'description')
                ).casefold()
                if any(marker in identity for marker in KNOWN_MARKERS):
                    return True
            except (OSError, ValueError, TypeError):
                pass
    return False


def status_notifier_host_available():
    try:
        connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        result = connection.call_sync(
            'org.freedesktop.DBus',
            '/org/freedesktop/DBus',
            'org.freedesktop.DBus',
            'NameHasOwner',
            GLib.Variant('(s)', ('org.kde.StatusNotifierWatcher',)),
            GLib.VariantType.new('(b)'),
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        )
        return bool(result.unpack()[0])
    except GLib.Error:
        return False


def appindicator_available():
    return appindicator_extension_installed() and status_notifier_host_available()


XML = """<node><interface name="org.kde.StatusNotifierItem">
<method name="Activate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="SecondaryActivate"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="ContextMenu"><arg type="i" direction="in"/><arg type="i" direction="in"/></method>
<method name="Scroll"><arg type="i" direction="in"/><arg type="s" direction="in"/></method>
<property name="Category" type="s" access="read"/><property name="Id" type="s" access="read"/>
<property name="Title" type="s" access="read"/><property name="Status" type="s" access="read"/>
<property name="WindowId" type="i" access="read"/><property name="IconName" type="s" access="read"/>
<property name="IconPixmap" type="a(iiay)" access="read"/><property name="OverlayIconName" type="s" access="read"/>
<property name="AttentionIconName" type="s" access="read"/><property name="ToolTip" type="(sa(iiay)ss)" access="read"/>
<property name="ItemIsMenu" type="b" access="read"/><property name="Menu" type="o" access="read"/>
<signal name="NewStatus"><arg type="s"/></signal><signal name="NewIcon"/>
</interface></node>"""


class StatusNotifier:
    def __init__(self, activate):
        self.activate = activate
        self.active = True
        self.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.node = Gio.DBusNodeInfo.new_for_xml(XML)
        interface = self.node.interfaces[0]
        self.registration = self.connection.register_object(
            '/StatusNotifierItem', interface, self._method, self._property, None
        )
        self.watch_id = Gio.bus_watch_name(
            Gio.BusType.SESSION,
            'org.kde.StatusNotifierWatcher',
            Gio.BusNameWatcherFlags.NONE,
            self._watcher_appeared,
            None,
        )

    def _watcher_appeared(self, connection, _name, _owner):
        connection.call(
            'org.kde.StatusNotifierWatcher',
            '/StatusNotifierWatcher',
            'org.kde.StatusNotifierWatcher',
            'RegisterStatusNotifierItem',
            GLib.Variant('(s)', (connection.get_unique_name(),)),
            None,
            Gio.DBusCallFlags.NONE,
            -1,
            None,
            None,
        )

    def _method(self, _connection, _sender, _path, _interface, method, _parameters, invocation):
        if method in ('Activate', 'SecondaryActivate', 'ContextMenu'):
            GLib.idle_add(self.activate)
        invocation.return_value(None)

    def _property(self, _connection, _sender, _path, _interface, name):
        values = {
            'Category': GLib.Variant('s', 'ApplicationStatus'),
            'Id': GLib.Variant('s', 'mirivue'),
            'Title': GLib.Variant('s', 'Mirivue'),
            'Status': GLib.Variant('s', 'Active' if self.active else 'Passive'),
            'WindowId': GLib.Variant('i', 0),
            'IconName': GLib.Variant('s', 'org.pdenams.Mirivue.Gtk4'),
            'IconPixmap': GLib.Variant('a(iiay)', []),
            'OverlayIconName': GLib.Variant('s', ''),
            'AttentionIconName': GLib.Variant('s', ''),
            'ToolTip': GLib.Variant('(sa(iiay)ss)', ('org.pdenams.Mirivue.Gtk4', [], 'Mirivue', '')),
            'ItemIsMenu': GLib.Variant('b', False),
            'Menu': GLib.Variant('o', '/NO_DBUSMENU'),
        }
        return values[name]

    def set_active(self, active):
        self.active = bool(active)
        self.connection.emit_signal(
            None,
            '/StatusNotifierItem',
            'org.kde.StatusNotifierItem',
            'NewStatus',
            GLib.Variant('(s)', ('Active' if self.active else 'Passive',)),
        )

    def close(self):
        self.set_active(False)
        if self.watch_id:
            Gio.bus_unwatch_name(self.watch_id)
            self.watch_id = 0
        if self.registration:
            self.connection.unregister_object(self.registration)
            self.registration = 0
