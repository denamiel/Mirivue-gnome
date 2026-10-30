"""Dynamic tabs owned and drawn by libadwaita, independently in each pane."""

from gi.repository import Adw, Gtk, Gio, GLib
from .i18n import tr


class TabGroup(Gtk.Box):
    def __init__(self, window, pane):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, hexpand=True, vexpand=True)
        self.window = window
        self.slot = pane.width_slot
        self.context_page = None
        self.closed_tabs = []
        self.placeholder = None
        self.view = Adw.TabView(vexpand=True)
        self.bar = Adw.TabBar(view=self.view, autohide=True)
        self.append(self.bar)
        self.append(self.view)
        self.actions = Gio.SimpleActionGroup()
        menu = Gio.Menu()
        for name, label, callback in (
            ('close', 'Fermer l’onglet', self.close_context),
            ('close-others', 'Fermer les autres onglets', self.close_others),
            ('restore', 'Rouvrir l’onglet fermé', self.restore),
            ('detach', 'Déplacer l’onglet vers une nouvelle fenêtre', self.detach),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', lambda _a, _v, cb=callback: cb())
            self.actions.add_action(action)
            menu.append(tr(label), 'tabs.' + name)
        self.insert_action_group('tabs', self.actions)
        self.view.set_menu_model(menu)
        self.view.connect('setup-menu', self.setup_menu)
        self.view.connect('close-page', self.close_page)
        self.view.connect('page-attached', self.attached)
        self.view.connect('page-detached', self.detached)
        self.view.connect('create-window', self.create_window)
        pane.tabs = self
        self.view.append(pane).set_title(tr('Dossier personnel'))
        self.view.connect('notify::selected-page', self.selected_changed)

    def get_n_pages(self):
        return self.view.get_n_pages()

    def get_current_page(self):
        page = self.view.get_selected_page()
        return self.view.get_page_position(page) if page else -1

    def get_nth_page(self, index):
        return self.view.get_nth_page(index).get_child()

    def page_num(self, pane):
        return self.view.get_page_position(self.view.get_page(pane))

    def set_current_page(self, index):
        self.view.set_selected_page(self.view.get_nth_page(index))

    def append_pane(self, pane, title):
        page = self.view.add_page(pane, self.view.get_selected_page())
        page.set_title(title)
        self.view.set_selected_page(page)
        return page

    def selected_changed(self, *_):
        page = self.view.get_selected_page()
        if page and not self.window.closed:
            self.window.activate_pane(page.get_child())

    def setup_menu(self, _view, page):
        self.context_page = page
        self.actions.lookup_action('restore').set_enabled(bool(self.closed_tabs))
        self.actions.lookup_action('close-others').set_enabled(self.get_n_pages() > 1)
        self.actions.lookup_action('detach').set_enabled(page is not None)

    def selected_page(self):
        return self.context_page or self.view.get_selected_page()

    def close_context(self):
        page = self.selected_page()
        if page:
            self.view.close_page(page)

    def close_others(self):
        page = self.selected_page()
        if page:
            self.view.close_other_pages(page)

    def close_page(self, _view, page):
        pane = page.get_child()
        others = [group for group in getattr(self.window, 'tab_groups', ())
                  if group is not self and group.get_visible() and group.get_n_pages()]
        if self.get_n_pages() == 1 and not others and pane is not self.placeholder:
            self.view.close_page_finish(page, False)
            self.window.request_quit()
            return True
        if pane is not self.placeholder:
            location = (pane.remote_file.get_uri() if pane.remote_file is not None else
                        'trash:///' if pane.is_trash else 'starred:///' if pane.is_starred else
                        str(pane.folder))
            self.closed_tabs.append((location, list(pane.history), pane.history_position))
            self.closed_tabs = self.closed_tabs[-30:]
        pane.close()
        self.view.close_page_finish(page, True)
        return True

    def restore(self):
        if not self.closed_tabs:
            return
        location, history, position = self.closed_tabs.pop()
        self.window.new_tab(location, group=self)
        pane = self.view.get_selected_page().get_child()
        pane.history = history
        pane.history_position = position

    def attached(self, _view, page, _position):
        pane = page.get_child()
        pane.window = self.window
        pane.tabs = self
        if pane not in self.window.panes:
            self.window.panes.append(pane)
        if pane.location_bar.get_parent() is None:
            self.window.path_group.append(pane.location_bar)
        if self.placeholder is not None and pane is not self.placeholder:
            placeholder, self.placeholder = self.placeholder, None
            # Do not add a synthetic startup tab to the closed-tab history.
            self.placeholder = placeholder
            self.view.close_page(self.view.get_page(placeholder))
            self.placeholder = None
        if hasattr(self.window, 'preview'):
            GLib.idle_add(self.selected_changed)

    def detached(self, _view, page, _position):
        pane = page.get_child()
        if self.context_page is page:
            self.context_page = None
        if pane in self.window.panes:
            self.window.panes.remove(pane)
        if pane.location_bar.get_parent() is self.window.path_group:
            self.window.path_group.remove(pane.location_bar)
        if not self.window.closed:
            GLib.idle_add(self.after_detach)

    def after_detach(self):
        if self.window.closed:
            return False
        if self.get_n_pages():
            if self.window.active not in self.window.panes or self.window.active.tabs is self:
                self.selected_changed()
        else:
            others = [g for g in self.window.tab_groups if g is not self and g.get_visible()
                      and g.get_n_pages()]
            if others:
                self.set_visible(False)
                if self is self.window.tab_groups[0]:
                    # Closing the last left tab keeps the remaining pane as
                    # the main pane. Native tab transfer never closes its child.
                    other = others[0]
                    self.window.paned.set_start_child(None)
                    self.window.paned.set_end_child(None)
                    self.window.tab_groups = [other, self]
                    self.window.paned.set_start_child(other)
                    self.window.paned.set_end_child(self)
                self.window.activate_pane(others[0].view.get_selected_page().get_child())
            else:
                self.window.request_quit()
        return False

    def create_window(self, _view):
        from .app import MirivueWindow
        window = MirivueWindow(self.window.get_application(), state=self.window.state)
        group = window.tab_groups[0]
        group.placeholder = group.get_nth_page(0)
        # A detached tab is a new window, with one browser pane.
        window.tab_groups[1].set_visible(False)
        window.present()
        return group.view

    def detach(self):
        page = self.selected_page()
        if page:
            other_view = self.create_window(self.view)
            self.view.transfer_page(page, other_view, other_view.get_n_pages())
