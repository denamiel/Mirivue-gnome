"""Native GTK breadcrumb navigation."""

from pathlib import Path
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib, Gio, Pango
from .i18n import tr

PATHBAR_MENU_SECTIONS = (
    (("Ouvrir avec…", "folder-open-with"), ("Ouvrir un terminal ici", "terminal")),
    (("Actualiser", "refresh"), ("Copier l’emplacement", "copy-location")),
    (("Coller", "paste"), ("Tout sélectionner", "select-all")),
    (("Propriétés", "folder-properties"),),
)


def _all_breadcrumb_segments(path):
    """Full breadcrumb targets; Home itself is not a shortcut."""
    path = Path(path)
    home = Path.home()
    base = home if path == home or home in path.parents else Path('/')
    segments = [base]
    current = base
    for name in path.relative_to(base).parts:
        current = current / name
        segments.append(current)
    return segments


def breadcrumb_segments(path):
    """Visible breadcrumb targets; Home itself is a label, not a shortcut."""
    segments = _all_breadcrumb_segments(path)
    return segments if len(segments) <= 5 else [segments[0], None, *segments[-3:]]


def breadcrumb_visible_start(widths, available, overflow_width):
    """Keep the newest path segments visible when the header becomes narrow."""
    if not widths or sum(widths) <= available:
        return 0
    budget = max(0, available - overflow_width)
    first = len(widths) - 1
    used = min(widths[-1], budget)
    for index in range(len(widths) - 2, -1, -1):
        if used + widths[index] > budget:
            break
        used += widths[index]
        first = index
    return first


class LocationBar(Gtk.Box):
    def __init__(self, pane, entry):
        super().__init__(spacing=4, hexpand=True)
        self.pane = pane
        self.entry = entry
        self.mode = 'buttons'
        self._crumb_buttons = []
        self._overflow_button = None
        self._overflow_key = None
        self._syncing_overflow = False
        self.stack = Gtk.Stack(hexpand=True, hhomogeneous=False, vhomogeneous=True)
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.stack.set_halign(Gtk.Align.FILL)
        self.crumbs = Gtk.Box(spacing=0)
        self.crumbs.add_css_class('mirivue-path-surface')
        self.crumbs.set_valign(Gtk.Align.CENTER)
        self.crumbs.connect('notify::width', lambda *_: GLib.idle_add(self.sync_overflow))
        self.stack.add_named(entry, 'text')
        self.stack.add_named(self.crumbs, 'buttons')
        self.append(self.stack)
        # Nautilus puts the current-folder menu at the trailing edge of its
        # linked path bar. Keep the icon flat as in Nautilus; GTK draws the
        # breadcrumb controls and their surface from the active theme.
        self.menu_button = Gtk.MenuButton(
            icon_name='view-more-symbolic', tooltip_text=tr('Menu du dossier courant')
        )
        self.menu_button.add_css_class('flat')
        self.menu_button.set_menu_model(self.path_menu())
        self.trailing_spacer = Gtk.Box(hexpand=True)
        self.crumbs.append(self.trailing_spacer)
        self.crumbs.append(self.menu_button)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self.key)
        entry.add_controller(keys)
        focus = Gtk.EventControllerFocus()
        focus.connect('leave', self.entry_focus_left)
        entry.add_controller(focus)
        click = Gtk.GestureClick(button=1)
        click.connect('released', lambda *_: self.set_mode('text'))
        self.trailing_spacer.add_controller(click)

    @staticmethod
    def path_menu():
        menu = Gio.Menu()
        create = Gio.Menu()
        create.append(tr('Dossier…'), 'win.new-folder')
        create.append(tr('Fichier texte…'), 'win.new-text-file')
        menu.append_submenu(tr('Créer un nouveau'), create)
        for section in PATHBAR_MENU_SECTIONS:
            group = Gio.Menu()
            for label, action in section:
                item = Gio.MenuItem.new(tr(label), 'win.' + action)
                if action == 'terminal':
                    item.set_icon(Gio.ThemedIcon.new('utilities-terminal-symbolic'))
                group.append_item(item)
            menu.append_section(None, group)
        return menu

    def key(self, controller, key, keycode, state):
        if key == Gdk.KEY_Escape:
            self.set_mode('buttons')
            return True
        return False

    def entry_focus_left(self, *_):
        if self.mode == 'text':
            self.set_mode('buttons')

    def set_mode(self, mode):
        if mode == 'buttons':
            if self.pane.is_trash:
                self.entry.set_text('trash:///')
            elif self.pane.is_starred:
                self.entry.set_text('starred:///')
            elif self.pane.remote_file is not None:
                self.entry.set_text(self.pane.remote_file.get_uri())
            else:
                self.entry.set_text(str(self.pane.folder))
        self.mode = mode
        self.stack.set_visible_child_name(mode)
        if mode == 'text':
            self.entry.grab_focus()
            self.entry.select_region(0, -1)
        else:
            GLib.idle_add(self.sync_overflow)

    def sync_overflow(self):
        if self._syncing_overflow or self.mode != 'buttons':
            return False
        available = self.crumbs.get_width()
        if available <= 0 or not self._crumb_buttons:
            return False
        _menu_min, menu_width, _mb, _nb = self.menu_button.measure(Gtk.Orientation.HORIZONTAL, -1)
        available = max(0, available - menu_width)
        widths = []
        for button, _path, _label, separator in self._crumb_buttons:
            _minimum, natural, _mb, _nb = button.measure(Gtk.Orientation.HORIZONTAL, -1)
            if separator is not None:
                _separator_min, separator_width, _smb, _snb = separator.measure(
                    Gtk.Orientation.HORIZONTAL, -1
                )
                natural += separator_width
            widths.append(max(1, natural))
        # Use GTK's themed size rather than reserving a fixed pixel width.
        overflow_width = menu_width
        first = breadcrumb_visible_start(widths, available, overflow_width)
        self._syncing_overflow = True
        try:
            if first == 0:
                if self._overflow_button and self._overflow_button.get_parent() is self.crumbs:
                    self.crumbs.remove(self._overflow_button)
                for button, _path, _label, separator in self._crumb_buttons:
                    button.set_visible(True)
                    if separator is not None:
                        separator.set_visible(True)
                self._overflow_key = None
                return False
            hidden = self._crumb_buttons[:first]
            key = tuple((str(path), label) for _button, path, label, _separator in hidden)
            for index, (button, _path, _label, separator) in enumerate(self._crumb_buttons):
                button.set_visible(index >= first)
                if separator is not None:
                    separator.set_visible(index >= first)
            if self._overflow_button is None:
                self._overflow_button = Gtk.MenuButton(
                    icon_name='view-more-symbolic', tooltip_text=tr('Emplacements précédents')
                )
                self._overflow_button.add_css_class('flat')
            if self._overflow_button.get_parent() is not self.crumbs:
                self.crumbs.prepend(self._overflow_button)
            if key != self._overflow_key:
                pop = Gtk.Popover()
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                for _button, path, label, _separator in hidden:
                    choice = Gtk.Button(label=label)
                    choice.add_css_class('flat')
                    if path is not None:
                        choice.connect(
                            'clicked', lambda _b, p=path, pop=pop: (pop.popdown(), self.pane.open(p))
                        )
                    box.append(choice)
                pop.set_child(box)
                self._overflow_button.set_popover(pop)
                self._overflow_key = key
        finally:
            self._syncing_overflow = False
        return False

    def update(self, path):
        path = Path(path)
        home = Path.home()
        all_segments = _all_breadcrumb_segments(path)
        # Navigation can move focus away from the editable entry while GTK is
        # rebuilding the breadcrumbs. Commit the new display mode first so
        # the old focus-leave callback cannot put Home back on screen.
        self.mode = 'buttons'
        self.stack.set_visible_child_name('buttons')
        while self.crumbs.get_first_child():
            self.crumbs.remove(self.crumbs.get_first_child())
        self._crumb_buttons = []
        self._overflow_button = None
        self._overflow_key = None
        segments = all_segments or [home]
        for index, segment in enumerate(segments):
            label = tr('Dossier personnel') if segment == home else segment.name or '/'
            separator = None
            if index:
                separator = Gtk.Label(label='/')
                separator.add_css_class('dim-label')
                separator.set_margin_start(4)
                separator.set_margin_end(4)
                self.crumbs.append(separator)
            button = Gtk.Button(tooltip_text=str(segment))
            button.set_can_shrink(True)
            button.add_css_class('flat')
            caption = Gtk.Label(label=label, ellipsize=Pango.EllipsizeMode.MIDDLE)
            if segment != path:
                caption.add_css_class('dim-label')
            else:
                attributes = Pango.AttrList.new()
                attributes.insert(Pango.attr_weight_new(Pango.Weight.BOLD))
                caption.set_attributes(attributes)
            button.set_child(caption)
            button.connect(
                'clicked',
                lambda _b, p=segment: self.set_mode('text') if p == self.pane.folder else self.pane.open(p),
            )
            gesture = Gtk.GestureClick(button=3)
            gesture.connect(
                'pressed', lambda _g, _n, x, y, p=segment, b=button: self.segment_menu(b, p, x, y)
            )
            button.add_controller(gesture)
            self.crumbs.append(button)
            self._crumb_buttons.append((button, segment, label, separator))
        self.crumbs.append(self.trailing_spacer)
        self.crumbs.append(self.menu_button)
        GLib.idle_add(self.sync_overflow)
        self.stack.set_visible_child_name(self.mode)

    def update_virtual(self, label, uri):
        self.mode = 'buttons'
        self.stack.set_visible_child_name('buttons')
        while self.crumbs.get_first_child():
            self.crumbs.remove(self.crumbs.get_first_child())
        self._overflow_button = None
        self._overflow_key = None
        title = tr(label)
        button = Gtk.Button(tooltip_text=uri)
        button.set_can_shrink(True)
        button.add_css_class('flat')
        button.set_child(Gtk.Label(label=title, ellipsize=Pango.EllipsizeMode.MIDDLE, max_width_chars=22))
        button.connect('clicked', lambda *_: self.set_mode('text'))
        self.crumbs.append(button)
        self.crumbs.append(self.trailing_spacer)
        self.crumbs.append(self.menu_button)
        self._crumb_buttons = [(button, None, title, None)]
        GLib.idle_add(self.sync_overflow)
        self.entry.set_text(uri)
        self.mode = 'buttons'
        self.stack.set_visible_child_name('buttons')

    def segment_menu(self, button, path, x, y):
        window = self.pane.window
        actions = Gio.SimpleActionGroup()
        menu = Gio.Menu()
        navigation = Gio.Menu()
        for name, title, callback in (
            ('tab', 'Ouvrir dans un nouvel onglet', lambda: window.new_tab(path)),
            ('window', 'Ouvrir dans une nouvelle fenêtre', lambda: window.new_window(path)),
            ('properties', 'Propriétés', lambda: window.show_folder_properties(path)),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', lambda _action, _parameter, run=callback: run())
            actions.add_action(action)
            navigation.append(tr(title), 'path.' + name)
        menu.append_section(None, navigation)
        copy = Gio.Menu()
        for name, title, value in [
            ('name', 'Copier le nom du dossier', path.name or '/'),
            ('location', 'Copier le chemin', str(path)),
        ]:
            action = Gio.SimpleAction.new(name, None)
            action.connect(
                'activate', lambda _action, _parameter, text=value: window.get_clipboard().set(text)
            )
            actions.add_action(action)
            copy.append(tr(title), 'path.' + name)
        menu.append_section(None, copy)
        button.insert_action_group('path', actions)
        pop = Gtk.PopoverMenu.new_from_model(menu)
        pop.set_parent(button)
        pop.set_pointing_to(Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1))
        pop.connect('closed', lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        pop.popup()
