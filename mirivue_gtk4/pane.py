"""Independent browser pane; model updates never rebuild unaffected rows."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os, re, threading, time, shutil
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, Gio, GLib, GObject, Pango
from .i18n import tr
from .backend import column_initial_width
from .core import metadata, gio_backend, folder_search, renaming, trash as trash_service
from .core.panel_status import summarize
from .navigation import LocationBar


def natural_key(text):
    return GLib.utf8_collate_key_for_filename(text, -1)


def apply_folder_count(row, count):
    """Apply the inexpensive, non-recursive child count to a directory row."""
    label = tr('élément') if count == 1 else tr('éléments')
    row.values[1] = f'{count} {label}'
    row.sort_values[1] = count


class Item(GObject.Object):
    revision = GObject.Property(type=int, default=0)
    editing = GObject.Property(type=bool, default=False)
    thumbnail = GObject.Property(type=str, default='')
    thumbnail_visible = GObject.Property(type=bool, default=False)

    def __init__(self, row):
        super().__init__()
        self.row = row
        self.pending = ''
        self.pending_column = 10
        self.folder_count = None
        self.folder_size_known = False
        self.search_parent = ''

    def update(self, row):
        for name in ('file_icon', 'content_type', 'file_hidden'):
            if not hasattr(row, name) and hasattr(self.row, name):
                setattr(row, name, getattr(self.row, name))
        self.row = row
        self.revision += 1

    @property
    def file(self):
        return getattr(self.row, 'gio_file', None) or Gio.File.new_for_path(str(self.path))

    @property
    def name(self):
        return str(self.row.values[0]) if getattr(self.row, 'gio_file', None) else self.path.name

    @property
    def path(self):
        return self.row.path


class Pane(Gtk.Box):
    def set_tab_title(self, title):
        if not hasattr(self, 'tabs'):
            return
        page = self.tabs.view.get_page(self)
        page.set_title(title)
        page.set_tooltip(self.remote_file.get_parse_name() if self.remote_file is not None else str(self.folder))

    def __init__(self, window, width_slot='left'):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True, vexpand=True)
        self.width_slot = width_slot
        self.add_css_class('browser-pane')
        self.window = window
        self.folder = Path.home()
        self.remote_file = None
        self.remote_entries = []
        self.remote_model = None
        self.remote_can_write = False
        self.local_view = window.state.settings['pane_views'][width_slot]
        self.is_trash = False
        self.is_starred = False
        self.generation = 0
        self.cancel = threading.Event()
        self.monitor = None
        self.inline_editor = None
        self.history = []
        self.history_position = -1
        self.items = {}
        self.changed = set()
        self.change_timer = 0
        self.restore_selection = set()
        self.closed = False
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='directory')
        self.folder_size_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='folder-size')
        self.folder_count_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='folder-count')
        self.folder_size_cancel = threading.Event()
        self.futures = []
        self.delivery_slots = threading.Semaphore(4)
        self.model_timer = 0
        self.drop_widget = None
        self.location = Gtk.Entry(hexpand=True)
        self.location.connect('activate', self.open_location)
        self.location.set_tooltip_text(tr('Emplacement'))
        self.location_bar = LocationBar(self, self.location)
        self.location_bar.set_hexpand(True)
        self.search_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.search_box.set_margin_start(8)
        self.search_box.set_margin_end(8)
        self.search_box.set_margin_top(4)
        search_line = Gtk.Box(spacing=8)
        self.search = Gtk.SearchEntry(
            placeholder_text=tr('Rechercher des fichiers et dossiers'), hexpand=True
        )
        search_line.append(self.search)
        self.search_box.append(search_line)
        options_line = Gtk.Box(spacing=8)
        self.search_subfolders = Gtk.CheckButton(label=tr('Inclure les sous-dossiers'), active=True)
        self.search_subfolders.connect('toggled', lambda *_: self.search_changed())
        options_line.append(self.search_subfolders)
        filters_button = Gtk.Button(label=tr('Filtres de recherche…'))
        filters_button.connect('clicked', lambda *_: self.window.open_search_filters(self))
        options_line.append(filters_button)
        self.search_box.append(options_line)
        self.duplicates_button = Gtk.Button(
            label=tr('Doublons exacts (dossier et sous-dossiers)…'), halign=Gtk.Align.START
        )
        self.duplicates_button.set_tooltip_text(
            tr('Compare tous les fichiers du dossier, indépendamment des filtres affichés.')
        )
        self.duplicates_button.connect('clicked', lambda *_: self.window.find_duplicates(folder=self.folder))
        self.search_box.append(self.duplicates_button)
        self.search_scope = Gtk.Label(
            label=tr('Recherche par nom depuis le dossier affiché'),
            xalign=0,
            wrap=True,
            css_classes=['dim-label'],
        )
        self.search_box.append(self.search_scope)
        self.search_filters = Gtk.Label(xalign=0, wrap=True, css_classes=['dim-label'])
        self.search_box.append(self.search_filters)
        self.clear_filters_button = Gtk.Button(label=tr('Effacer les filtres'), halign=Gtk.Align.START)
        self.clear_filters_button.connect('clicked', lambda *_: self.clear_search_filters())
        self.search_box.append(self.clear_filters_button)
        self.search_box.set_visible(False)
        self.append(self.search_box)
        self.search_timer = 0
        self.search_serial = 0
        self.search_cancel = threading.Event()
        self.search_recursive_active = False
        self.search_finished = False
        self.type_filter = 'all'
        self.collection = None
        self.criteria = {}
        self.selection_anchor = -1
        self.store = Gio.ListStore.new(Item)
        self.filter = Gtk.CustomFilter.new(self.matches)
        self.filtered = Gtk.FilterListModel.new(self.store, self.filter)
        self.sorted = Gtk.SortListModel.new(self.filtered, None)
        self.selection = Gtk.MultiSelection.new(self.sorted)
        self.selection.connect('selection-changed', self.selection_changed)
        self.search.connect('search-changed', lambda *_: self.search_changed())
        self.search.connect(
            'stop-search', lambda *_: self.window.toggle_search() if self.search_box.get_visible() else None
        )
        # Let GtkColumnView own the complete header drag gesture, including
        # its themed drag preview and native column insertion behavior.
        self.view = Gtk.ColumnView(model=self.selection, enable_rubberband=True, hexpand=True, vexpand=True)
        # Set after construction as well: the reorderable property is not
        # implied by setting individual GtkColumnViewColumn properties.
        self.view.set_reorderable(True)
        self.view.set_single_click_activate(False)
        self.view.add_css_class('data-table')
        self.columns = []
        # GTK's row activation is the native double-click / Return path used
        # by GNOME Files; ColumnView rows are activatable by default.
        for index, title in enumerate(metadata.HEADERS + ['Étiquette']):
            factory = Gtk.SignalListItemFactory()
            factory.connect('setup', self.cell_setup, index)
            factory.connect('bind', self.cell_bind, index)
            factory.connect('unbind', self.cell_unbind)
            col = Gtk.ColumnViewColumn(title=tr(title), factory=factory, resizable=True, expand=False)
            # Répété explicitement pour les versions GTK qui n'appliquent pas
            # toujours la valeur passée au constructeur avant l'affichage.
            col.set_resizable(True)
            # Keep labels and ordinary metadata legible at first launch. A
            # previously persisted narrow width must not hide a whole column.
            saved = (
                window.state.settings['pane_column_widths']
                .get(self.width_slot, {})
                .get(str(index), window.state.settings['column_widths'].get(str(index)))
            )
            col.set_fixed_width(column_initial_width(index, saved))
            col.set_sorter(Gtk.CustomSorter.new(lambda a, b, _data=None, i=index: self.compare(a, b, i)))
            col.set_header_menu(window.column_header_menu())
            col.set_visible(index not in (12, 15, 16, 36) and index in window.state.settings['columns'])
            self.view.append_column(col)
            self.columns.append(col)
        for position, index in enumerate(
            window.state.settings['pane_column_orders'].get(
                self.width_slot, window.state.settings['column_order']
            )
        ):
            if isinstance(index, int) and 0 <= index < len(self.columns):
                column = self.columns[index]
                self.view.remove_column(column)
                self.view.insert_column(position, column)
        self.applying_column_order = False
        self.column_order_save_timer = 0
        self.view.get_columns().connect('items-changed', self.columns_changed)
        for column in self.columns:
            column.connect('notify::fixed-width', self.column_width_changed)
        self.width_save_timer = 0
        # Keep directory grouping ahead of the column sorter so descending
        # column order never moves folders below files.
        self.folder_sorter = Gtk.CustomSorter.new(self.compare_folder)
        self.combined_sorter = Gtk.MultiSorter.new()
        self.combined_sorter.append(self.folder_sorter)
        self.combined_sorter.append(self.view.get_sorter())
        self.sorted.set_sorter(self.combined_sorter)
        self.view.sort_by_column(self.columns[0], Gtk.SortType.ASCENDING)
        self.view.connect('activate', self.activate)
        preview_keys = Gtk.EventControllerKey()
        preview_keys.connect('key-pressed', self.quick_preview_key)
        self.view.add_controller(preview_keys)
        search_keys = Gtk.EventControllerKey()
        search_keys.connect('key-pressed', self.type_to_search)
        self.view.add_controller(search_keys)
        self.stack = Gtk.Stack(hexpand=True, vexpand=True)
        self.detail_scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.detail_scroll.set_child(self.view)
        self.rubberband_paused = None
        details = Gtk.Overlay(hexpand=True, vexpand=True)
        details.set_child(self.detail_scroll)
        self.loading_details = self.make_loading_indicator()
        details.add_overlay(self.loading_details)
        self.no_results_details = self.make_no_results()
        details.add_overlay(self.no_results_details)
        # GTK's native header drag doesn't expose an insertion-slot widget.
        # Observe its `.dnd` state without claiming the gesture, then draw a
        # theme-colored marker at the nearest insertion boundary.
        self.column_drop_indicator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.column_drop_indicator.add_css_class('accent')
        self.column_drop_indicator.add_css_class('dnd')
        self.column_drop_indicator.set_halign(Gtk.Align.START)
        self.column_drop_indicator.set_valign(Gtk.Align.START)
        self.column_drop_indicator.set_can_target(False)
        self.column_drop_indicator.set_visible(False)
        details.add_overlay(self.column_drop_indicator)
        self.stack.add_named(details, 'details')
        self.column_drag_watch_timer = 0
        self.column_drag_x = 0
        factory = Gtk.SignalListItemFactory()
        factory.connect('setup', self.grid_setup)
        factory.connect('bind', self.grid_bind)
        factory.connect('unbind', self.cell_unbind)
        self.grid = Gtk.GridView(
            model=self.selection, factory=factory, min_columns=1, max_columns=12, enable_rubberband=True
        )
        self.grid.set_single_click_activate(False)
        preview_keys = Gtk.EventControllerKey()
        preview_keys.connect('key-pressed', self.quick_preview_key)
        self.grid.add_controller(preview_keys)
        search_keys = Gtk.EventControllerKey()
        search_keys.connect('key-pressed', self.type_to_search)
        self.grid.add_controller(search_keys)
        self.grid.add_css_class('media-grid')
        self.grid.connect('activate', self.activate)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_child(self.grid)
        # Capture before the list's built-in rubberband gesture. A drag that
        # starts on a file belongs to Gtk.DragSource; one that starts in empty
        # space remains GTK's native rectangular selection.
        for container, view in ((self.detail_scroll, self.view), (scroll, self.grid)):
            press = Gtk.GestureClick(button=1)
            press.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            press.connect('pressed', self.file_drag_pressed, container, view)
            press.connect('released', self.file_drag_released)
            press.connect('cancel', self.file_drag_cancelled)
            container.add_controller(press)
            background = Gtk.GestureClick(button=1)
            background.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            background.connect('pressed', self.background_pressed, container)
            container.add_controller(background)
        icons = Gtk.Overlay(hexpand=True, vexpand=True)
        icons.set_child(scroll)
        self.loading_icons = self.make_loading_indicator()
        icons.add_overlay(self.loading_icons)
        self.no_results_icons = self.make_no_results()
        icons.add_overlay(self.no_results_icons)
        self.stack.add_named(icons, 'icons')
        self.append(self.stack)
        remote_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.remote_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE, vexpand=True)
        self.remote_list.connect('row-activated', self.activate_remote)
        remote_menu = Gtk.GestureClick(button=3)
        remote_menu.connect('pressed', self.remote_context_menu)
        self.remote_list.add_controller(remote_menu)
        remote_focus = Gtk.EventControllerFocus()
        remote_focus.connect('enter', lambda *_: self.window.activate_pane(self, from_focus=True))
        self.remote_list.add_controller(remote_focus)
        remote_scroll = Gtk.ScrolledWindow(vexpand=True)
        remote_scroll.set_child(self.remote_list)
        self.remote_content = Gtk.Stack(vexpand=True)
        self.remote_content.add_named(remote_scroll, 'listing')
        empty = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER
        )
        empty_icon = Gtk.Image.new_from_icon_name('network-workgroup-symbolic')
        empty_icon.set_pixel_size(96)
        empty.append(empty_icon)
        self.remote_empty_title = Gtk.Label(css_classes=['title-1'])
        empty.append(self.remote_empty_title)
        self.remote_empty_detail = Gtk.Label(
            css_classes=['dim-label'], wrap=True, justify=Gtk.Justification.CENTER
        )
        empty.append(self.remote_empty_detail)
        self.remote_content.add_named(empty, 'empty')
        remote_box.append(self.remote_content)
        self.remote_connect = Gtk.Box(spacing=8)
        self.remote_address = Gtk.Entry(placeholder_text=tr('Adresse du serveur'), hexpand=True)
        self.remote_address.connect('activate', lambda *_: self.connect_remote_address())
        self.remote_connect.append(self.remote_address)
        connect = Gtk.Button(label=tr('Se connecter'), css_classes=['suggested-action'])
        connect.connect('clicked', lambda *_: self.connect_remote_address())
        self.remote_connect.append(connect)
        remote_box.append(self.remote_connect)
        self.stack.add_named(remote_box, 'remote')
        self.zoom = 96
        # GridView normally uses every item's natural width.  A long filename
        # would therefore reduce the number of columns.  Nautilus instead
        # chooses fixed-size grid cells from the icon size, then wraps text.
        self.grid.connect('notify::width', lambda *_: self.update_grid_columns())
        self.stack.connect('notify::visible-child-name', self.grid_view_changed)
        self.stack.set_visible_child_name(self.local_view)
        self.panel_status = Gtk.Box(spacing=8, css_classes=['dim-label'])
        self.panel_status.set_margin_start(8)
        self.panel_status.set_margin_end(8)
        self.panel_status.set_margin_top(3)
        self.panel_status.set_margin_bottom(3)
        self.panel_count = Gtk.Label(xalign=0, hexpand=True)
        self.panel_status.append(self.panel_count)
        self.panel_free = Gtk.Label(xalign=1)
        self.panel_status.append(self.panel_free)
        self.append(self.panel_status)
        self.status_folder = None
        self.cached_free = '—'
        self.connect('notify::width', lambda *_: self.update_grid_columns())
        # The row list is a child inside ColumnView. Keep row gestures there so
        # the header's built-in capture-phase drag gesture receives the press.
        self.detail_rows = self.view.get_last_child() or self.view
        for view in (self.detail_rows, self.grid):
            focus = Gtk.EventControllerFocus()
            focus.connect('enter', lambda *_: self.window.activate_pane(self, from_focus=True))
            view.add_controller(focus)
            # Keep only the empty-area double-click behavior here. For rows,
            # let Gtk.ColumnView/GridView emit their native activation signal,
            # which matches GNOME Files' standard open gesture.
            activate_click = Gtk.GestureClick(button=1)
            activate_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            activate_click.connect('pressed', self.pointer_activate, view)
            view.add_controller(activate_click)
            context_keys = Gtk.EventControllerKey()
            context_keys.connect('key-pressed', self.context_key_pressed, view)
            view.add_controller(context_keys)
            gesture = Gtk.GestureClick(button=3)
            gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            gesture.connect('pressed', self.context, view)
            view.add_controller(gesture)
            # File dragging is attached to item widgets below, away from GTK's
            # native header drag controller so the two gestures cannot compete.
            target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
            target.connect('drop', self.drop, view)
            target.connect('motion', self.drop_motion, view)
            target.connect('leave', lambda *_: self.clear_drop())
            view.add_controller(target)
            wheel = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
            wheel.connect('scroll', self.wheel)
            view.add_controller(wheel)
        focus = Gtk.EventControllerFocus()
        focus.connect('enter', lambda *_: self.window.activate_pane(self, from_focus=True))
        self.add_controller(focus)
        # Motion observation does not participate in the header's gesture
        # arbitration; GTK remains responsible for the actual drag and drop.
        self.header_motion = Gtk.EventControllerMotion()
        self.header_motion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self.header_motion.connect('motion', self.column_drag_motion)
        self.view.add_controller(self.header_motion)

    def value(self, item, index):
        if index == 37:
            return item.row.personal_label
        if item.pending and index in (10, item.pending_column):
            return item.pending
        return str(item.row.values[index])

    def columns_changed(self, *_):
        if self.applying_column_order:
            return
        # GtkColumnView may report a native move as remove+insert. Deferring
        # persistence until the current event finishes avoids saving/applying
        # the transient order with one column temporarily absent.
        if not self.column_order_save_timer:
            self.column_order_save_timer = GLib.idle_add(self.persist_column_order_idle)

    def persist_column_order_idle(self):
        self.column_order_save_timer = 0
        self.persist_column_order()
        return GLib.SOURCE_REMOVE

    def persist_column_order(self):
        model = self.view.get_columns()
        order = [self.columns.index(model.get_item(index)) for index in range(model.get_n_items())]
        orders = self.window.state.settings['pane_column_orders']
        if order != orders.get(self.width_slot):
            orders[self.width_slot] = order
            self.window.state.save()
            # Tabs belonging to the same side keep its layout. The opposite
            # pane deliberately retains its own column sequence.
            for pane in getattr(self.window, 'panes', []):
                if pane is not self and pane.width_slot == self.width_slot:
                    pane.apply_column_order(order)

    def apply_column_order(self, order):
        current = [
            self.columns.index(self.view.get_columns().get_item(i))
            for i in range(self.view.get_columns().get_n_items())
        ]
        if current == order:
            return
        self.applying_column_order = True
        try:
            for column in self.columns:
                self.view.remove_column(column)
            for index in order:
                self.view.append_column(self.columns[index])
        finally:
            self.applying_column_order = False

    def column_width_changed(self, column, *_):
        """Persist native resizing and keep the paired file pane aligned."""
        if column not in self.columns:
            return
        index = self.columns.index(column)
        width = max(48, min(900, column.get_fixed_width()))
        widths = self.window.state.settings['pane_column_widths'].setdefault(self.width_slot, {})
        if widths.get(str(index)) == width:
            return
        widths[str(index)] = width
        # GTK can emit several width notifications while it lays out a large
        # directory.  Save once after the gesture has settled, never once per
        # visible row. Tabs within the same pane share their layout; the other
        # side of a split view deliberately remains independent.
        if not self.width_save_timer:
            self.width_save_timer = GLib.timeout_add(250, self.save_column_widths)
        for pane in getattr(self.window, 'panes', []):
            if pane is self or pane.width_slot != self.width_slot or index >= len(pane.columns):
                continue
            peer = pane.columns[index]
            if peer.get_fixed_width() != width:
                peer.set_fixed_width(width)

    def save_column_widths(self):
        self.width_save_timer = 0
        self.window.state.save()
        return False

    def header_columns(self):
        header = self.view.get_first_child()
        if header is None:
            return []
        model = self.view.get_columns()
        columns = []
        title = header.get_first_child()
        position = 0
        while title and position < model.get_n_items():
            column = model.get_item(position)
            if column.get_visible():
                valid, bounds = title.compute_bounds(self.view)
                if valid:
                    columns.append(
                        (
                            column,
                            title,
                            bounds.get_x(),
                            bounds.get_y(),
                            bounds.get_width(),
                            bounds.get_height(),
                        )
                    )
            title = title.get_next_sibling()
            position += 1
        return columns

    def header_column_at(self, x):
        for column, title, left, top, width, height in self.header_columns():
            if left <= x < left + width:
                return column, title, left, top, width, height
        return None, None, None, None, None, None

    def column_drag_motion(self, _controller, x, y):
        self.column_drag_x = x
        dragged = any(title.has_css_class('dnd') for _column, title, *_bounds in self.header_columns())
        if dragged:
            self.update_column_drop_marker(x)
            if not self.column_drag_watch_timer:
                self.column_drag_watch_timer = GLib.timeout_add(40, self.watch_column_drag)

    def update_column_drop_marker(self, x):
        columns = self.header_columns()
        stationary = [entry for entry in columns if not entry[1].has_css_class('dnd')]
        if not stationary:
            self.column_drop_indicator.set_visible(False)
            return
        line = None
        for _column, _title, left, _top, width, _height in stationary:
            if x < left + width / 2:
                line = left
                break
            line = left + width
        header = self.view.get_first_child()
        if line is None or header is None:
            self.column_drop_indicator.set_visible(False)
            return
        self.column_drop_indicator.set_margin_start(max(0, round(line) - 1))
        self.column_drop_indicator.set_margin_top(0)
        self.column_drop_indicator.set_size_request(3, max(1, header.get_height()))
        self.column_drop_indicator.set_visible(True)

    def watch_column_drag(self):
        active = any(title.has_css_class('dnd') for _column, title, *_bounds in self.header_columns())
        if active:
            self.update_column_drop_marker(self.column_drag_x)
            return True
        self.column_drop_indicator.set_visible(False)
        self.column_drag_watch_timer = 0
        return False

    def compare_folder(self, a, b, *_):
        if not self.window.state.settings['folders_first'] or a.row.is_dir == b.row.is_dir:
            return Gtk.Ordering.EQUAL
        return Gtk.Ordering.SMALLER if a.row.is_dir else Gtk.Ordering.LARGER

    def compare(self, a, b, index):
        def key(item):
            if index == 0:
                return natural_key(getattr(item, 'name', item.path.name))
            if index == 37:
                return item.row.personal_label.casefold()
            value = item.row.sort_values[index]
            return (0, value) if isinstance(value, (float, int)) else (1, str(value).casefold())

        x, y = key(a), key(b)
        return Gtk.Ordering.SMALLER if x < y else Gtk.Ordering.LARGER if x > y else Gtk.Ordering.EQUAL

    def matches(self, item, *_):
        if not self.window.hidden and getattr(item.row, 'file_hidden', item.path.name.startswith('.')):
            return False
        row = item.row
        if self.type_filter != 'all' and (row.is_dir or row.media_type != self.type_filter):
            return False
        if self.collection is not None and str(item.path) not in self.collection:
            return False
        for key, column in [('duration', 2), ('width', 3)]:
            minimum = self.criteria.get(key, 0)
            value = row.sort_values[column] if key != 'width' else row.media_technical.get('width', 0) or 0
            if minimum and (not isinstance(value, (int, float)) or value < minimum):
                return False
        minimum_size = self.criteria.get('size_mib', 0)
        size = row.sort_values[1]
        if minimum_size and (
            row.is_dir or not isinstance(size, (int, float)) or size < minimum_size * 1024 * 1024
        ):
            return False
        if self.criteria.get('errors') and not any(
            getattr(row, field, None) for field in ('error', 'validation_error')
        ):
            return False
        if (
            self.criteria.get('label')
            and self.criteria['label'].casefold() not in row.personal_label.casefold()
        ):
            return False
        needle = self.search.get_text().casefold().strip()
        return not needle or needle in item.path.name.casefold()

    def make_no_results(self):
        label = Gtk.Label(
            label=tr('Aucun résultat. Modifiez la recherche ou effacez les filtres.'),
            wrap=True,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            css_classes=['dim-label'],
        )
        label.set_can_target(False)
        label.set_visible(False)
        return label

    def update_search_labels(self):
        scope = (
            tr(
                'Saisissez un nom pour chercher dans les sous-dossiers ; les filtres seuls concernent ce dossier'
            )
            if self.search_subfolders.get_active() and not self.search.get_text().strip()
            else tr('Recherche par nom dans le dossier et ses sous-dossiers')
            if self.search_subfolders.get_active()
            else tr('Recherche dans le dossier affiché')
        )
        if self.remote_file is not None:
            scope = tr('Recherche par nom dans le dossier affiché')
        self.search_scope.set_label(scope)
        labels = []
        if self.type_filter != 'all':
            labels.append(tr({'video': 'Vidéo', 'audio': 'Audio', 'image': 'Images'}[self.type_filter]))
        for key, title in [
            ('duration', 'Durée minimale'),
            ('width', 'Largeur minimale'),
            ('size_mib', 'Taille minimale (Mio)'),
        ]:
            if self.criteria.get(key):
                labels.append(f'{tr(title)} : {self.criteria[key]}')
        if self.criteria.get('label'):
            labels.append(f'{tr("Étiquette")} : {self.criteria["label"]}')
        if self.criteria.get('errors'):
            labels.append(tr('Fichiers avec erreur connue'))
        self.search_filters.set_label(tr('Filtres actifs') + ' : ' + ', '.join(labels) if labels else '')
        self.search_filters.set_visible(bool(labels))
        self.clear_filters_button.set_visible(bool(labels))

    def update_search_empty(self):
        empty = (
            self.search_box.get_visible()
            and bool(self.search.get_text().strip() or self.criteria or self.type_filter != 'all')
            and self.filtered.get_n_items() == 0
            and self.search_finished
        )
        for widget in (self.no_results_details, self.no_results_icons):
            widget.set_visible(empty)

    def clear_search_filters(self):
        self.type_filter = 'all'
        self.criteria = {}
        self.update_search_labels()
        self.filter.changed(Gtk.FilterChange.DIFFERENT)
        self.update_search_empty()

    def set_search_visible(self, visible):
        if visible and (self.is_trash or self.is_starred or self.remote_file is not None and self.remote_file.get_uri().rstrip('/') == 'network:'):
            self.window.notify(tr('La recherche dans les sous-dossiers nécessite un dossier local.'))
            return
        self.search_box.set_visible(visible)
        if visible:
            self.update_search_labels()
            self.search.grab_focus()
        else:
            self.search_cancel.set()
            self.search_serial += 1
            if self.search_timer:
                GLib.source_remove(self.search_timer)
                self.search_timer = 0
            self.search.set_text('')
            self.type_filter = 'all'
            self.criteria = {}
            self.update_search_labels()
            if self.search_recursive_active:
                self.search_recursive_active = False
                self.open(self.folder, False)
            else:
                self.filter.changed(Gtk.FilterChange.DIFFERENT)
            self.update_search_empty()

    def type_to_search(self, _controller, keyval, _keycode, state):
        if self.remote_file is not None or self.is_trash or self.is_starred:
            return False
        if state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SUPER_MASK):
            return False
        focused = self.window.get_focus()
        # EditableLabel gives keyboard focus to its internal Gtk.Text while
        # editing. Do not interpret typed rename characters as a new search.
        if isinstance(focused, Gtk.Editable):
            return False
        code = Gdk.keyval_to_unicode(keyval)
        if not code or not chr(code).isprintable() or chr(code).isspace():
            return False
        self.window.activate_pane(self)
        previous = self.search.get_text() if self.search_box.get_visible() else ''
        self.set_search_visible(True)
        self.search.set_text(previous + chr(code))
        self.search.set_position(-1)
        return True

    def reset_search_for_navigation(self, keep_search=False):
        self.search_cancel.set()
        self.search_serial += 1
        self.search_recursive_active = False
        if self.search_timer:
            GLib.source_remove(self.search_timer)
            self.search_timer = 0
        if not keep_search:
            self.search_box.set_visible(False)
            self.search.set_text('')
            self.type_filter = 'all'
            self.criteria = {}
            self.update_search_labels()
        self.search_finished = False

    def search_changed(self):
        if not self.search_box.get_visible():
            return
        self.update_search_labels()
        self.search_cancel.set()
        self.search_serial += 1
        if self.search_timer:
            GLib.source_remove(self.search_timer)
        self.search_finished = False
        self.update_search_empty()
        if self.remote_file is None and self.search_subfolders.get_active() and self.search.get_text().strip():
            self.search_timer = GLib.timeout_add(200, self.start_recursive_search, self.search_serial)
        else:
            self.search_timer = 0
            if self.search_recursive_active:
                self.search_recursive_active = False
                self.open(self.folder, False, keep_search=True)
            else:
                self.search_finished = True
                self.filter.changed(Gtk.FilterChange.DIFFERENT)
                self.update_search_empty()

    def start_recursive_search(self, serial):
        self.search_timer = 0
        if serial != self.search_serial or not self.search_box.get_visible():
            return GLib.SOURCE_REMOVE
        self.cancel.set()
        self.cancel = threading.Event()
        self.search_cancel = threading.Event()
        cancel = self.search_cancel
        self.search_recursive_active = True
        self.search_finished = False
        self.items.clear()
        self.store.remove_all()
        self.set_loading(True)
        generation = self.generation
        folder = self.folder
        needle = self.search.get_text()

        def run():
            batch = []
            found = []
            for path in folder_search.matching_paths(folder, needle, cancel.is_set, self.window.hidden):
                if cancel.is_set():
                    return
                try:
                    row = metadata.basic_entry(path, path.is_dir())
                    gio_backend.enrich_file_info(row)
                    batch.append(row)
                    found.append(path)
                except OSError:
                    continue
                if len(batch) >= 24:
                    self.deliver(self.add_search_rows, cancel, generation, serial, batch)
                    batch = []
            if batch:
                self.deliver(self.add_search_rows, cancel, generation, serial, batch)
            for path in found:
                if cancel.is_set():
                    return
                try:
                    row = self.window.service.inspect(path, cancel.is_set)
                except (OSError, ValueError, InterruptedError):
                    continue
                except Exception:
                    continue
                self.deliver(self.add_search_enriched, cancel, generation, serial, path, row)
            self.deliver(self.finish_search, cancel, generation, serial)

        self.executor.submit(run)
        return GLib.SOURCE_REMOVE

    def add_search_rows(self, generation, serial, rows):
        if self.closed or generation != self.generation or serial != self.search_serial:
            return False
        additions = []
        for row in rows:
            key = str(row.path)
            if key not in self.items:
                item = Item(row)
                item.search_parent = str(row.path.parent.relative_to(self.folder))
                self.items[key] = item
                additions.append(item)
        if additions:
            self.store.splice(self.store.get_n_items(), 0, additions)
        self.update_panel_status()
        return False

    def add_search_enriched(self, generation, serial, path, row):
        if self.closed or generation != self.generation or serial != self.search_serial:
            return False
        item = self.items.get(str(path))
        if item:
            item.update(row)
            self.filter.changed(Gtk.FilterChange.DIFFERENT)
            self.update_panel_status()
        return False

    def finish_search(self, generation, serial):
        if self.closed or generation != self.generation or serial != self.search_serial:
            return False
        self.search_finished = True
        self.set_loading(False)
        self.update_search_empty()
        self.update_panel_status()
        return False

    def make_loading_indicator(self):
        box = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        spinner = Gtk.Spinner()
        spinner.start()
        box.append(spinner)
        box.append(Gtk.Label(label=tr('Chargement du dossier…'), css_classes=['dim-label']))
        box.set_can_target(False)
        box.set_visible(False)
        return box

    def set_loading(self, loading):
        for widget in (self.loading_details, self.loading_icons):
            widget.set_visible(loading)

    def finish_loading(self, generation):
        if self.search_recursive_active:
            return False
        if generation == self.generation and not self.closed:
            self.set_loading(False)
            self.search_finished = True
            self.update_search_empty()
            if self.window.navigation_pane is self:
                self.window.activate_pane(self)
                self.window.navigation_pane = None
        return False

    def cell_setup(self, _factory, li, index):
        if index == 0:
            child = Gtk.Box(spacing=6)
            child.append(Gtk.Image())
            names = Gtk.Stack(hexpand=True)
            display = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
            editor = Gtk.EditableLabel(xalign=0, hexpand=True)
            editor.set_editable(False)
            editor.view_mode = 'details'
            editor.name_stack = names
            editor.display_label = display
            editor.connect('notify::editing', self.inline_edit_finished)
            names.add_named(display, 'display')
            names.add_named(editor, 'edit')
            child.append(names)
        else:
            child = Gtk.Label(xalign=0, ellipsize=3)
        # A file row can be dragged from any visible column, not only its name.
        self.add_file_drag_source(child, self.view)
        child.set_margin_start(6)
        child.set_margin_end(6)
        li.set_child(child)

    def cell_bind(self, _factory, li, index):
        item = li.get_item()
        child = li.get_child()
        child.record = item

        def paint(*_):
            value = self.value(item, index)
            if index in (7, 10, 17):
                value = tr(value)
            if index == 1:
                from .i18n import size_text

                value = size_text(value)
            if index == 14:
                from .i18n import date_text

                value = date_text(item.row.modified_ns)
            if index == 0:
                names = child.get_last_child()
                display = names.get_child_by_name('display')
                label = names.get_child_by_name('edit')
                display.record = item
                label.record = item
                origin = item.search_parent
                display.set_label(f'{value}  —  {origin}' if origin and origin != '.' else value)
                display.set_tooltip_text(str(item.path) if self.search_recursive_active else value)
                label.set_tooltip_text(value)
                if not label.get_editing():
                    label.set_text(value)
                    if not item.editing:
                        names.set_visible_child_name('display')
                widgets = (display, label)
            else:
                label = child
                label.set_label(value)
                tooltip = value
                label.set_tooltip_text(tooltip)
                widgets = (label,)
            for widget in widgets:
                for css in ('error', 'success', 'accent', 'duplicate'):
                    widget.remove_css_class(css)
                if item.row.error:
                    widget.add_css_class('error')
                elif item.pending:
                    widget.add_css_class('success')
                elif item.row.duplicate_group:
                    widget.add_css_class('duplicate')
            if index == 0:
                image = child.get_first_child()
                thumbnail = item.thumbnail if item.thumbnail_visible else ''
                if thumbnail:
                    image.set_from_file(thumbnail)
                else:
                    image.set_from_gicon(self.icon(item))
                image.set_pixel_size(max(16, self.zoom // 4))
                if (
                    item.editing
                    and self.stack.get_visible_child_name() == 'details'
                    and not label.get_editing()
                ):
                    label.set_editable(True)
                    names.set_visible_child_name('edit')
                    self.queue_inline_edit(label, item)

        signals = [item.connect('notify::revision', paint)]
        if index == 0:
            signals.extend(
                [item.connect('notify::thumbnail', paint), item.connect('notify::thumbnail-visible', paint)]
            )
        paint()
        li.binding = (item, signals)

    def cell_unbind(self, _factory, li):
        if getattr(li, 'binding', None):
            item, signals = li.binding
            for signal in signals:
                item.disconnect(signal)
            li.binding = None
        child = li.get_child()
        if child:
            child.record = None
            label = child.get_last_child() if isinstance(child, Gtk.Box) else child
            if isinstance(label, Gtk.Stack):
                label = label.get_child_by_name('edit')
            if isinstance(label, Gtk.EditableLabel):
                if self.inline_editor is label:
                    self.inline_editor = None
                if label.get_editing():
                    bound_item = label.record
                    label.record = None
                    label.stop_editing(False)
                    if bound_item is not None:
                        bound_item.editing = False
                label.record = None
                label.was_editing = False
                label.rename_pending_item = None

    def icon(self, item):
        icon = getattr(item.row, 'file_icon', None)
        if icon is not None:
            return icon
        if item.row.is_dir:
            return Gio.ThemedIcon.new('folder')
        content_type = Gio.content_type_guess(item.path.name, None)[0] or 'application/octet-stream'
        return Gio.content_type_get_icon(content_type)

    def grid_setup(self, _factory, li):
        # These margins remain genuine empty grid space: a right click there
        # reaches the view, not an item, as it does in Nautilus.
        li.set_activatable(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_margin_start(14)
        box.set_margin_end(14)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_halign(Gtk.Align.CENTER)
        stack = Gtk.Stack()
        stack.add_named(Gtk.Image(), 'icon')
        stack.add_named(Gtk.Picture(can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN), 'image')
        box.append(stack)
        # Like Nautilus, names use two centred lines below an icon and only
        # then end in an ellipsis.  The editor is shown solely for F2, so it
        # does not impose the single-line layout of Gtk.EditableLabel.
        names = Gtk.Stack()
        display = Gtk.Label(xalign=0.5, halign=Gtk.Align.CENTER, justify=Gtk.Justification.CENTER)
        # The image dictates the cell width.  Giving the label a one-character
        # natural width prevents a long filename from widening its grid cell;
        # allocated width still follows the image, then text wraps to two
        # lines and ellipsizes.
        display.set_wrap(True)
        display.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        display.set_natural_wrap_mode(Pango.WrapMode.WORD_CHAR)
        display.set_lines(2)
        display.set_ellipsize(Pango.EllipsizeMode.END)
        display.set_width_chars(1)
        display.set_max_width_chars(1)
        editor = Gtk.EditableLabel(xalign=0.5, halign=Gtk.Align.CENTER)
        editor.set_editable(False)
        editor.set_visible(False)
        editor.view_mode = 'icons'
        editor.set_width_chars(1)
        editor.set_max_width_chars(1)
        editor.name_stack = names
        editor.display_label = display
        editor.connect('notify::editing', self.inline_edit_finished)
        names.add_named(display, 'display')
        names.add_named(editor, 'edit')
        box.append(names)
        self.add_file_drag_source(box, self.grid)
        li.set_child(box)

    def grid_bind(self, _factory, li):
        item = li.get_item()
        box = li.get_child()
        box.record = item

        def paint(*_):
            stack = box.get_first_child()
            box.set_size_request(self.zoom, -1)
            stack.set_size_request(self.zoom, self.zoom)
            image = stack.get_child_by_name('icon')
            image.set_from_gicon(self.icon(item))
            image.set_pixel_size(self.zoom)
            thumbnail = item.thumbnail if item.thumbnail_visible else ''
            if thumbnail:
                stack.get_child_by_name('image').set_filename(thumbnail)
            stack.set_visible_child_name('image' if thumbnail else 'icon')
            names = box.get_last_child()
            display = names.get_child_by_name('display')
            label = names.get_child_by_name('edit')
            names.set_halign(Gtk.Align.CENTER)
            names.set_hexpand(False)
            names.set_size_request(self.zoom, -1)
            display.set_size_request(self.zoom, -1)
            label.set_size_request(self.zoom, -1)
            label.record = item
            display.record = item
            text = str(item.row.values[0]) if self.is_trash or self.remote_file is not None else item.path.name
            if not label.get_editing():
                label.set_text(text)
                display.set_label(
                    f'{text}\n{item.search_parent}'
                    if item.search_parent and item.search_parent != '.'
                    else text
                )
                display.set_tooltip_text(str(item.path) if self.search_recursive_active else text)
                label.set_visible(False)
                names.set_visible_child_name('display')
            if (
                item.editing
                and self.stack.get_visible_child_name() == label.view_mode
                and not label.get_editing()
            ):
                label.set_visible(True)
                names.set_visible_child_name('edit')
                label.set_editable(True)
                self.queue_inline_edit(label, item)
            for cls in ('error', 'duplicate'):
                box.remove_css_class(cls)
            if item.row.error:
                box.add_css_class('error')
            elif item.row.duplicate_group:
                box.add_css_class('duplicate')

        signals = [
            item.connect('notify::revision', paint),
            item.connect('notify::thumbnail', paint),
            item.connect('notify::thumbnail-visible', paint),
        ]
        paint()
        li.binding = (item, signals)

    def inline_edit_finished(self, label, _property):
        editing = label.get_editing()
        was = getattr(label, 'was_editing', False)
        label.was_editing = editing
        item = getattr(label, 'record', None)
        if was and not editing and item:
            if self.inline_editor is label:
                self.inline_editor = None
            label.set_editable(False)
            item.editing = False
            self.window.finish_inline_rename(item, label.get_text())
            if hasattr(label, 'display_label'):
                # The editor contains a proposal, not a completed rename. Keep
                # the existing name until the job refreshes the row on success.
                label.set_visible(False)
                label.name_stack.set_visible_child_name('display')
            # Keep keyboard navigation on the file view after Enter or Escape,
            # without stealing focus from another widget clicked by the user.
            if not getattr(label, 'suppress_focus_restore', False):
                GLib.idle_add(self.restore_focus_after_inline_edit, label)
            label.suppress_focus_restore = False

    def restore_focus_after_inline_edit(self, label):
        focused = self.window.get_focus()
        if focused is label or (focused and focused.get_ancestor(Gtk.EditableLabel) is label):
            (self.view if label.view_mode == 'details' else self.grid).grab_focus()
        return False

    def queue_inline_edit(self, label, item):
        if getattr(label, 'rename_pending_item', None) is item:
            return
        label.rename_pending_item = item
        GLib.idle_add(self.begin_inline_edit, label, item)

    def begin_inline_edit(self, label, item):
        if getattr(label, 'rename_pending_item', None) is item:
            label.rename_pending_item = None
        if getattr(label, 'record', None) is not item or not item.editing or label.get_editing():
            return False
        label.start_editing()
        self.inline_editor = label
        # GtkEditable works in character offsets, including Unicode names.
        label.select_region(0, renaming.single_name_selection_end(label.get_text(), item.row.is_dir))
        return False

    def start_inline_rename(self, item):
        item.editing = True
        item.revision += 1

    def wheel(self, controller, dx, dy):
        if not controller.get_current_event_state() & Gdk.ModifierType.CONTROL_MASK:
            return False
        self.set_zoom(self.zoom + (-12 if dy > 0 else 12))
        return True

    def set_zoom(self, value):
        self.zoom = max(48, min(240, value))
        self.update_grid_columns()
        for item in self.items.values():
            item.revision += 1

    def update_grid_columns(self):
        """Fit fixed icon cells; a name must never choose the column count."""
        width = self.grid.get_width()
        if width <= 0:
            return
        cell_width = self.zoom + 28  # icon width plus the permanent empty margin
        columns = max(1, min(12, width // cell_width))
        self.grid.set_min_columns(columns)
        self.grid.set_max_columns(columns)

    def grid_view_changed(self, *_args):
        mode = self.stack.get_visible_child_name()
        if mode in ('icons', 'details'):
            self.local_view = mode
            views = self.window.state.settings['pane_views']
            if views[self.width_slot] != mode:
                views[self.width_slot] = mode
                self.window.state.save()
        if mode == 'icons':
            GLib.idle_add(self.update_grid_columns)

    def selected(self):
        bits = self.selection.get_selection()
        return [self.selection.get_item(bits.get_nth(i)) for i in range(bits.get_size())]

    def quick_preview_key(self, _controller, key, _code, state):
        if key != Gdk.KEY_space or state & (
            Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.SHIFT_MASK
        ):
            return False
        if isinstance(self.window.get_focus(), Gtk.Editable) or not self.selected():
            return False
        self.window.activate_pane(self)
        self.window.toggle_preview()
        return True

    def select_paths(self, paths):
        paths = set(map(str, paths))
        for i in range(self.sorted.get_n_items()):
            if str(self.sorted.get_item(i).path) in paths:
                self.selection.select_item(i, False)

    def selection_changed(self, *_):
        bits = self.selection.get_selection()
        if bits.get_size() == 1:
            self.selection_anchor = bits.get_nth(0)
        self.update_panel_status()
        if self.window.active is self:
            self.window.selection_changed()

    def update_panel_status(self):
        """Keep each pane's count, error total, and free space with its own view."""
        if self.remote_file is not None:
            directories = sum(self.filtered.get_item(i).row.is_dir for i in range(self.filtered.get_n_items()))
            self.panel_count.set_label(
                f'{directories} {tr("dossier" if directories == 1 else "dossiers")}, '
                f'{self.filtered.get_n_items() - directories} {tr("fichier" if self.filtered.get_n_items() - directories == 1 else "fichiers")}'
            )
            self.panel_free.set_label(self.remote_file.get_uri())
            return
        rows = [self.filtered.get_item(index).row for index in range(self.filtered.get_n_items())]
        self.panel_count.set_label(summarize(rows, [item.row for item in self.selected()]))
        self.update_search_empty()
        folder = str(self.folder)
        if folder != self.status_folder:
            self.status_folder = folder
            try:
                mount = self.folder
                while mount.parent != mount and not os.path.ismount(mount):
                    mount = mount.parent
                self.cached_free = f'{mount} — {self.window.readable_size(shutil.disk_usage(self.folder).free)} {tr("libres")}'
            except (OSError, TypeError):
                self.cached_free = '—'
        self.panel_free.set_label(self.cached_free)

    def activate(self, _view, index):
        # Native Gtk.ListBase activation: double-click or keyboard activation.
        item = self.selection.get_item(index)
        if item is not None:
            self.activate_item(item)

    def activate_item(self, item):
        if self.remote_file is not None:
            self.window.open_items([item])
            return
        # Open folders in this pane; delegate files to the desktop default app.
        if item is None:
            return
        self.window.activate_pane(self)
        if self.is_trash:
            self.window.open_trash_item(item)
            return
        if item.row.is_dir:
            self.open(item.path)
        else:
            self.window.open_items([item])

    def pointer_activate(self, gesture, n_press, x, y, view):
        # Focus follows the first press, as it does in a native file manager.
        self.window.navigation_pane = self
        self.window.activate_pane(self)
        GLib.idle_add(self.clear_pointer_activation, self.generation)
        item = self.picked(view, x, y)
        if n_press == 1 and item is None:
            # The enclosing scrolled window handles empty-area clicks,
            # including the space below the last row.
            return
        if n_press != 2:
            return
        # Gtk.ColumnView and Gtk.GridView activate rows natively. Intercept only
        # empty space for Mirivue's parent-folder shortcut.
        if item is None:
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self.up()

    def clear_pointer_activation(self, generation):
        if generation == self.generation and self.window.navigation_pane is self:
            self.window.navigation_pane = None
        return GLib.SOURCE_REMOVE

    def picked(self, view, x, y):
        child = view.pick(x, y, Gtk.PickFlags.DEFAULT)
        while child and child != view:
            item = getattr(child, 'record', None)
            if item:
                return item
            child = child.get_parent()
        return None

    def background_pressed(self, gesture, n_press, x, y, container):
        if n_press != 1 or self.picked(container, x, y) is not None:
            return
        modifiers = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        if gesture.get_current_event_state() & modifiers:
            return
        editor = self.inline_editor
        if editor is not None and editor.get_editing():
            editor.suppress_focus_restore = True
            editor.stop_editing(False)
        # GTK's list gesture also runs during this press. Clear its selection
        # after the native event rather than before it can select a row again.
        GLib.idle_add(self.clear_background_selection, self.generation)

    def clear_background_selection(self, generation):
        if generation == self.generation and not self.closed:
            self.selection.unselect_all()
        return False

    def file_drag_pressed(self, _gesture, n_press, x, y, container, view):
        if n_press != 1 or self.picked(container, x, y) is None:
            return
        if self.rubberband_paused is not None:
            self.resume_rubberband()
        view.set_enable_rubberband(False)
        self.rubberband_paused = view

    def file_drag_released(self, *_args):
        self.resume_rubberband()

    def file_drag_cancelled(self, *_args):
        self.resume_rubberband()

    def resume_rubberband(self):
        view = self.rubberband_paused
        self.rubberband_paused = None
        if view is not None:
            view.set_enable_rubberband(True)

    def context_key_pressed(self, _controller, keyval, _keycode, state, view):
        # Match GNOME's keyboard-accessible context menu entry points.
        if keyval != Gdk.KEY_Menu and not (keyval == Gdk.KEY_F10 and state & Gdk.ModifierType.SHIFT_MASK):
            return False
        self.window.activate_pane(self)
        self.window.context_menu(
            view, max(0, view.get_width() // 2), max(0, view.get_height() // 2), not bool(self.selected())
        )
        return True

    def context(self, gesture, _count, x, y, view):
        # Let the column header keep its own sort/column menu. File rows use
        # Mirivue's complete action menu before child widgets see right-click.
        self.window.activate_pane(self)
        item = self.picked(view, x, y)
        if item and item not in self.selected():
            self.selection.unselect_all()
            self.select_paths([item.path])
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.window.context_menu(view, x, y, item is None)

    def add_file_drag_source(self, widget, view):
        source = Gtk.DragSource(actions=Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
        source.connect('prepare', self.item_drag_prepare, view)
        source.connect('drag-begin', self.drag_begin)
        source.connect('drag-end', self.drag_end)
        source.connect('drag-cancel', self.drag_cancel)
        widget.add_controller(source)

    def item_drag_prepare(self, source, _x, _y, view):
        if self.is_trash:
            return None
        item = getattr(source.get_widget(), 'record', None)
        if item is None:
            return None
        content = self.prepare_selected_drag(item)
        # Remember the origin: a drop in the other pane transfers directly to
        # its displayed directory, while a drop on the same pane is ignored.
        self.window.drag_source_pane = self if content is not None else None
        return content

    def prepare_selected_drag(self, item):
        """The native payload retains all GFile URIs, including GVfs locations."""
        if item and item not in self.selected():
            self.selection.unselect_all()
            for index in range(self.sorted.get_n_items()):
                if self.sorted.get_item(index) is item:
                    self.selection.select_item(index, False)
                    break
        files = [getattr(item.row, 'gio_file', None) or Gio.File.new_for_path(str(item.path))
                 for item in self.selected()] if item else []
        return Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_list(files)) if files else None

    def drag_begin(self, source, drag):
        items = self.selected()
        if not items:
            return
        # Nautilus 51 stacks up to four actual item icons or thumbnails. The
        # count refers to the entire selection, not just the visible stack.
        shown = items[:4]
        stack = Gtk.Overlay()
        for index in reversed(range(len(shown))):
            item = shown[index]
            thumbnail = item.thumbnail if item.thumbnail_visible else ''
            if thumbnail:
                image = Gtk.Picture.new_for_filename(thumbnail)
                image.set_content_fit(Gtk.ContentFit.CONTAIN)
                image.set_size_request(48, 48)
            else:
                image = Gtk.Image.new_from_gicon(self.icon(item))
                image.set_pixel_size(48)
            if index == len(shown) - 1:
                base = Gtk.Box()
                base.set_margin_start(index * 4)
                base.set_margin_top(index * 4)
                base.append(image)
                stack.set_child(base)
            else:
                image.set_halign(Gtk.Align.START)
                image.set_valign(Gtk.Align.START)
                image.set_margin_start(index * 4)
                image.set_margin_top(index * 4)
                stack.add_overlay(image)
        preview = stack
        if len(items) > 1:
            preview = Gtk.Overlay()
            preview.set_child(stack)
            count = f'{min(len(items), 9999)}+' if len(items) > 9999 else str(len(items))
            badge = Gtk.Button(
                label=count, css_classes=['suggested-action', 'circular' if len(count) == 1 else 'pill']
            )
            badge.set_halign(Gtk.Align.END)
            badge.set_valign(Gtk.Align.END)
            badge.set_can_target(False)
            badge.set_focusable(False)
            preview.add_overlay(badge)
        Gtk.DragIcon.get_for_drag(drag).set_child(preview)

    def drag_end(self, *_args):
        self.window.drag_source_pane = None
        self.resume_rubberband()

    def drag_cancel(self, *_args):
        self.drag_end()
        return False

    def drop_action_for(self, paths):
        """Match Files/Nautilus: move on one volume, copy to another."""
        try:
            destination_device = self.folder.stat().st_dev
            return (
                Gdk.DragAction.MOVE
                if all(path.stat().st_dev == destination_device for path in paths)
                else Gdk.DragAction.COPY
            )
        except OSError:
            # An unreadable mount must never cause a destructive default.
            return Gdk.DragAction.COPY

    def drop(self, target, files, x, y, view):
        if self.is_trash:
            return False
        self.clear_drop()
        # The other pane is always the destination.  Same-volume drops move;
        # a different mounted volume receives a copy, without a dialog.
        if getattr(self.window, 'drag_source_pane', None) is self:
            return False
        sources = list(files.get_files())
        if self.remote_file is not None or any(not f.is_native() for f in sources):
            source = getattr(self.window, 'drag_source_pane', None)
            drag = target.get_current_drop().get_drag() if target.get_current_drop() else None
            action = drag.get_selected_action() if drag else Gdk.DragAction.COPY
            destination = self.remote_file or Gio.File.new_for_path(str(self.folder))
            self.window.gio_transfer(sources, destination, move=action == Gdk.DragAction.MOVE)
            return True
        paths = [Path(f.get_path()) for f in sources if f.get_path()]
        if not paths:
            return False
        action = self.drop_action_for(paths)
        self.window.transfer(paths, self.folder, copy=action == Gdk.DragAction.COPY)
        return True

    def clear_drop(self):
        if self.drop_widget:
            self.drop_widget.remove_css_class('drop-destination')
            self.drop_widget = None

    def drop_motion(self, target, x, y, view):
        # Highlight the complete destination pane.  It makes the target just
        # as clear in Details and Icons views, even over empty space.
        if getattr(self.window, 'drag_source_pane', None) is self:
            return Gdk.DragAction(0)
        if view != self.drop_widget:
            self.clear_drop()
            self.drop_widget = view
            self.drop_widget.add_css_class('drop-destination')
        source = getattr(self.window, 'drag_source_pane', None)
        paths = [item.path for item in source.selected()] if source is not None else []
        return Gdk.DragAction.COPY if self.remote_file is not None else self.drop_action_for(paths) if paths else Gdk.DragAction.COPY

    def up(self):
        if self.remote_file is not None:
            parent = self.remote_file.get_parent()
            if parent:
                self.open_remote(parent)
            return
        if self.is_starred:
            self.open(Path.home())
            return
        if self.is_trash:
            self.open(Path.home())
            return
        old = self.folder
        self.open(old.parent)
        self.restore_selection = {str(old)}

    def back(self, delta):
        pos = self.history_position + delta
        if 0 <= pos < len(self.history):
            self.history_position = pos
            target = self.history[pos]
            if target == trash_service.URI:
                self.open_trash(False)
            elif target == 'starred:///':
                self.window.open_starred(self, False)
            elif isinstance(target, str) and '://' in target:
                self.open_remote(Gio.File.new_for_uri(target), False)
            else:
                self.open(target, False)

    def open_location(self, entry):
        text = entry.get_text().strip()
        if text == trash_service.URI:
            self.open_trash()
        elif '://' in text:
            self.window.open_gio_location(Gio.File.new_for_uri(text), self)
        else:
            self.open(Path(text).expanduser())

    def open(self, folder, remember=True, keep_search=False):
        folder = Path(folder).expanduser().absolute()
        if not folder.is_dir():
            self.window.notify(tr('Ce dossier n’existe pas ou n’est pas accessible.'))
            return
        self.stop_remote_listing()
        self.search_subfolders.set_sensitive(True)
        self.duplicates_button.set_visible(True)
        self.reset_search_for_navigation(keep_search)
        self.window.navigation_pane = self
        self.set_loading(True)
        self.cancel.set()
        self.cancel = threading.Event()
        self.generation += 1
        generation = self.generation
        for f in self.futures:
            f.cancel()
        self.futures = []
        if self.monitor:
            self.monitor.cancel()
        self.is_trash = False
        self.is_starred = False
        self.remote_file = None
        self.folder = folder
        self.location.set_text(str(folder))
        self.location_bar.update(folder)
        self.items.clear()
        self.store.remove_all()
        self.stack.set_visible_child_name(self.local_view)
        self.update_panel_status()
        self.set_tab_title(folder.name or '/')
        self.restore_selection = set()
        self.changed.clear()
        self.collection = None
        self.selection_anchor = -1
        if remember:
            self.history = self.history[: self.history_position + 1] + [folder]
            self.history_position = len(self.history) - 1
        self.window.state.settings['last_folder'] = str(folder)
        self.window.navigation_pane = self
        self.window.activate_pane(self)
        # GTK can deliver the focus change from the previous pane after row
        # activation. Reassert the pane that actually completed navigation
        # once that event batch has finished, without changing a later browse.
        GLib.idle_add(self.finish_navigation_activation, generation)
        self.update_monitoring()
        self.futures.append(self.executor.submit(self.scan, folder, generation, self.cancel))

    def finish_navigation_activation(self, generation):
        if not self.closed and self.generation == generation and self.window.navigation_pane is self:
            self.window.activate_pane(self)
        return GLib.SOURCE_REMOVE

    def stop_loading(self):
        self.cancel.set()
        self.search_cancel.set()
        self.stop_remote_listing()
        self.set_loading(False)

    def stop_remote_listing(self):
        model = getattr(self, 'remote_model', None)
        self.remote_model = None
        if model is not None:
            model.set_file(None)

    def open_remote(self, file, remember=True, keep_search=False):
        """GIO inventory displayed through the same native list/grid models."""
        self.stop_remote_listing()
        self.reset_search_for_navigation(keep_search)
        self.cancel.set()
        self.cancel = threading.Event()
        self.generation += 1
        generation = self.generation
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        self.is_trash = self.is_starred = False
        self.remote_file = file
        self.remote_entries = []
        self.items.clear()
        self.store.remove_all()
        network_root = file.get_uri().rstrip('/') == 'network:'
        label = tr('Réseau') if network_root else file.get_basename() or file.get_parse_name()
        self.remote_connect.set_visible(network_root)
        self.location_bar.update_virtual(label, file.get_uri())
        self.set_tab_title(label)
        self.search_subfolders.set_sensitive(False)
        self.duplicates_button.set_visible(False)
        self.stack.set_visible_child_name('remote' if network_root else self.local_view)
        self.remote_empty_title.set_label(tr('Chargement…'))
        self.remote_empty_detail.set_label('')
        self.remote_content.set_visible_child_name('empty')
        if remember:
            self.history = self.history[:self.history_position + 1] + [file.get_uri()]
            self.history_position = len(self.history) - 1
        self.window.activate_pane(self)
        model = Gtk.DirectoryList.new(gio_backend.DIRECTORY_ATTRIBUTES, None)
        self.remote_model = model

        def changed(source, position, removed, added):
            if self.closed or generation != self.generation or self.remote_model is not source:
                return
            replacements = []
            for index in range(position, position + added):
                info = source.get_item(index)
                item = Item(gio_backend.row_from_info(file, info))
                if info.get_attribute_boolean('thumbnail::is-valid'):
                    item.thumbnail = info.get_attribute_byte_string('thumbnail::path') or ''
                    item.thumbnail_visible = bool(item.thumbnail and self.window.state.settings['thumbnails'])
                replacements.append(item)
            self.store.splice(position, removed, replacements)
            self.items = {self.store.get_item(i).file.get_uri(): self.store.get_item(i)
                          for i in range(self.store.get_n_items())}
            self.remote_entries = [(item.name, item.file, item.row.is_dir, item.row.sort_values[1],
                                    item.row.file_icon) for item in self.items.values()]
            if network_root:
                while (row := self.remote_list.get_row_at_index(0)) is not None:
                    self.remote_list.remove(row)
                for item in self.items.values():
                    row = Gtk.ListBoxRow()
                    row.gio_file, row.is_directory = item.file, item.row.is_dir
                    line = Gtk.Box(spacing=8)
                    line.append(Gtk.Image.new_from_gicon(self.icon(item)))
                    line.append(Gtk.Label(label=item.name, xalign=0, hexpand=True))
                    row.set_child(line)
                    self.remote_list.append(row)
                self.remote_content.set_visible_child_name('listing' if self.items else 'empty')
            self.update_panel_status()

        def loading(source, _property):
            if self.closed or generation != self.generation or self.remote_model is not source:
                return
            self.set_loading(source.is_loading())
            self.search_finished = not source.is_loading()
            if not source.is_loading():
                error = source.get_error()
                if error:
                    self.window.notify(error.message)
                self.remote_empty_title.set_label(tr('Aucune connexion connue') if network_root
                                                  else tr('Ce dossier est vide'))
                self.remote_empty_detail.set_label(tr('Saisir une adresse pour se connecter à un emplacement réseau.')
                                                   if network_root else file.get_parse_name())
                self.update_panel_status()

        model.connect('items-changed', changed)
        model.connect('notify::loading', loading)
        model.set_file(file)
        loading(model, None)

        def permissions(source, result):
            if self.closed or generation != self.generation:
                return
            try:
                info = source.query_info_finish(result)
                self.remote_can_write = info.get_attribute_boolean('access::can-write')
            except GLib.Error:
                self.remote_can_write = False
            if self.window.active is self:
                self.window.sync_toggle_actions()

        self.remote_can_write = False
        if not network_root:
            file.query_info_async('access::can-write', Gio.FileQueryInfoFlags.NONE,
                                  GLib.PRIORITY_DEFAULT, None, permissions)

    def connect_remote_address(self):
        address = self.remote_address.get_text().strip()
        if '://' not in address or address.split('://', 1)[0].lower() not in (
            'smb',
            'sftp',
            'ftp',
            'ftps',
            'dav',
            'davs',
            'nfs',
        ):
            self.window.notify(
                tr('Saisissez une adresse réseau complète, par exemple smb://serveur/partage.')
            )
            return
        self.window.open_gio_location(Gio.File.new_for_uri(address), self)

    def remote_selected(self):
        if self.remote_file is not None and self.remote_file.get_uri().rstrip('/') == 'network:':
            files = []
            self.remote_list.selected_foreach(lambda _list, row: files.append(row.gio_file))
            return files
        return [item.file for item in self.selected()]

    def remote_context_menu(self, _gesture, _count, x, y):
        row = self.remote_list.get_row_at_y(int(y))
        if row is not None and not row.is_selected():
            self.remote_list.unselect_all()
            self.remote_list.select_row(row)
        self.window.activate_pane(self)
        menu = Gio.Menu()
        if self.remote_selected():
            menu.append(tr('Copier'), 'win.copy')
            menu.append(tr('Couper'), 'win.cut')
        if (
            self.remote_file is not None
            and self.remote_file.get_uri().rstrip('/') != 'network:'
            and self.window.can_paste()
        ):
            menu.append(tr('Coller'), 'win.paste')
        if not menu.get_n_items():
            return
        pop = Gtk.PopoverMenu.new_from_model(menu)
        pop.set_parent(self.remote_list)
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = rect.height = 1
        pop.set_pointing_to(rect)
        pop.connect('closed', lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        pop.popup()

    def activate_remote(self, _list, row):
        if row.is_directory:
            self.open_remote(row.gio_file)
            return

        def finished(_source, result):
            try:
                Gio.AppInfo.launch_default_for_uri_finish(result)
            except GLib.Error as error:
                self.window.notify(error.message)

        Gio.AppInfo.launch_default_for_uri_async(row.gio_file.get_uri(), None, None, finished)

    def open_trash(self, remember=True):
        self.stop_remote_listing()
        self.reset_search_for_navigation(keep_search)
        self.remote_file = None
        self.stack.set_visible_child_name(self.local_view)
        self.cancel.set()
        self.cancel = threading.Event()
        self.generation += 1
        generation = self.generation
        for future in self.futures:
            future.cancel()
        self.futures = []
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        self.set_loading(True)
        self.is_trash = True
        self.is_starred = False
        self.location_bar.update_virtual('Corbeille', trash_service.URI)
        self.items.clear()
        self.store.remove_all()
        self.update_panel_status()
        self.restore_selection = set()
        self.changed.clear()
        self.collection = None
        self.set_tab_title(tr('Corbeille'))
        if remember:
            self.history = self.history[: self.history_position + 1] + [trash_service.URI]
            self.history_position = len(self.history) - 1
        self.window.activate_pane(self)
        self.futures.append(self.executor.submit(self.scan_trash, generation, self.cancel))

    def open_starred(self, remember=True):
        self.stop_remote_listing()
        self.reset_search_for_navigation(keep_search)
        self.remote_file = None
        self.stack.set_visible_child_name(self.local_view)
        self.cancel.set()
        self.cancel = threading.Event()
        self.generation += 1
        generation = self.generation
        for future in self.futures:
            future.cancel()
        self.futures = []
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        self.set_loading(True)
        self.is_trash = False
        self.is_starred = True
        self.folder = Path.home()
        self.location_bar.update_virtual('Favoris', 'starred:///')
        self.items.clear()
        self.store.remove_all()
        self.update_panel_status()
        self.restore_selection = set()
        self.changed.clear()
        self.collection = set()
        self.selection_anchor = -1
        self.set_tab_title(tr('Favoris'))
        if remember:
            self.history = self.history[: self.history_position + 1] + ['starred:///']
            self.history_position = len(self.history) - 1
        self.window.activate_pane(self)
        return generation

    def show_starred_paths(self, generation, paths):
        if generation != self.generation or self.closed or not self.is_starred:
            return False
        normalized = []
        for value in paths:
            file = Gio.File.new_for_uri(value)
            path = file.get_path()
            if path and Path(path).exists():
                normalized.append(Path(path))
        self.collection = {str(path) for path in normalized}
        self.futures.append(self.executor.submit(self.scan_paths, normalized, generation, self.cancel))
        return False

    def scan_paths(self, paths, generation, cancel):
        rows = []
        for path in paths:
            if cancel.is_set():
                return
            try:
                row = metadata.basic_entry(path, path.is_dir())
                gio_backend.enrich_file_info(row)
                rows.append(row)
            except OSError:
                continue
        if rows:
            self.deliver(self.add_rows, cancel, generation, rows)
        self.deliver(self.finish_loading, cancel, generation)
        self.enrich([row.path for row in rows], generation, cancel)

    def scan_trash(self, generation, cancel):
        try:
            self.deliver(self.add_rows, cancel, generation, trash_service.rows(cancel.is_set))
            self.deliver(self.finish_loading, cancel, generation)
        except InterruptedError:
            return
        except Exception as error:
            GLib.idle_add(self.window.notify, str(error))

    def reload_trash(self):
        if not self.is_trash or self.closed:
            return False
        self.open_trash(False)
        return False

    def update_monitoring(self):
        if self.monitor:
            self.monitor.cancel()
            self.monitor = None
        if not self.window.state.settings['monitor_external'] or self.closed:
            return
        try:
            self.monitor = Gio.File.new_for_path(str(self.folder)).monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES, None
            )
            self.monitor.connect('changed', self.changed_event, self.generation)
        except GLib.Error:
            self.monitor = None

    def scan(self, folder, generation, cancel):
        batch = []
        paths = []
        last_delivery = time.monotonic()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if cancel.is_set():
                        return
                    try:
                        row = metadata.basic_entry(Path(entry.path), entry.is_dir())
                        gio_backend.enrich_file_info(row)
                    except OSError:
                        continue
                    batch.append(row)
                    paths.append(row.path)
                    # Surface the first items promptly even in small folders.
                    # A fixed large batch left typical home folders blank until
                    # their entire directory had been enumerated.
                    now = time.monotonic()
                    if len(batch) >= 16 or now - last_delivery >= 0.05:
                        self.deliver(self.add_rows, cancel, generation, batch)
                        batch = []
                        last_delivery = now
            if batch:
                self.deliver(self.add_rows, cancel, generation, batch)
            self.deliver(self.finish_loading, cancel, generation)
            self.enrich(paths, generation, cancel)
        except OSError as error:
            GLib.idle_add(self.finish_loading, generation)
            GLib.idle_add(self.window.notify, str(error))

    def enrich(self, paths, generation, cancel):
        for path in paths:
            if cancel.is_set():
                return
            try:
                row = self.window.service.inspect(path, cancel.is_set)
                thumbnail = (
                    self.window.thumbnails.get(path, row, cancel.is_set)
                    if self.window.state.settings['thumbnails'] and not row.is_dir
                    else ''
                )
                self.deliver(self.enriched, cancel, generation, path, row, thumbnail)
            except InterruptedError:
                return
            except Exception as error:
                try:
                    row = metadata.basic_entry(path, path.is_dir())
                    row.error = str(error)
                    row.values[10] = 'Erreur'
                    self.deliver(self.enriched, cancel, generation, path, row, '')
                except OSError:
                    pass

    def refresh_thumbnails(self):
        """Load only missing file thumbnails; folder rows/counts are untouched."""
        if getattr(self, 'remote_file', None) is not None or not self.window.state.settings.get('thumbnails', False) or self.closed:
            return
        generation = self.generation
        cancel = self.cancel
        for item in tuple(self.items.values()):
            if not item.row.is_dir and not item.thumbnail:
                self.futures.append(
                    self.executor.submit(self.load_thumbnail, item.path, item.row, generation, cancel)
                )

    def set_thumbnail_visibility(self, enabled):
        """Change only icon-preview state; never invalidate file-row metadata."""
        for item in tuple(self.items.values()):
            item.thumbnail_visible = bool(enabled and item.thumbnail and not item.row.is_dir)
        if enabled:
            self.refresh_thumbnails()

    def load_thumbnail(self, path, row, generation, cancel):
        if cancel.is_set():
            return
        try:
            thumbnail = self.window.thumbnails.get(path, row, cancel.is_set)
        except InterruptedError:
            return
        except Exception:
            thumbnail = ''
        self.deliver(self.thumbnail_ready, cancel, generation, str(path), thumbnail)

    def thumbnail_ready(self, generation, path, thumbnail):
        if (
            generation != self.generation
            or self.closed
            or not self.window.state.settings.get('thumbnails', False)
        ):
            return False
        item = self.items.get(path)
        if item and not item.row.is_dir:
            item.thumbnail = thumbnail
            item.thumbnail_visible = bool(thumbnail and self.window.state.settings.get('thumbnails', False))
        return False

    def add_rows(self, generation, rows):
        if generation != self.generation or self.closed:
            return False
        if self.search_recursive_active:
            return False
        additions = []
        for row in rows:
            key = str(row.path)
            if key not in self.items:
                item = Item(row)
                self.items[key] = item
                additions.append(item)
                if row.is_dir:
                    self.folder_count_executor.submit(
                        self.measure_folder_count, row.path, generation, self.cancel
                    )
        if additions:
            self.store.splice(self.store.get_n_items(), 0, additions)
        self.set_loading(False)
        self.select_paths(self.restore_selection)
        self.update_panel_status()
        self.window.update_status()
        return False

    def enriched(self, generation, path, row, thumbnail):
        if self.search_recursive_active:
            return False
        if generation != self.generation or self.closed:
            return False
        item = self.items.get(str(path))
        if item:
            # An older thumbnail job may finish after the file changed. The
            # directory monitor will enqueue fresh metadata for that path.
            if getattr(row, 'file_signature', None) is not None:
                try:
                    if row.file_signature != metadata.fingerprint(path):
                        return False
                except OSError:
                    return False
            item.thumbnail = thumbnail
            item.thumbnail_visible = bool(thumbnail and self.window.state.settings['thumbnails'])
            # A late directory scan must not erase a completed duration
            # analysis of the same unchanged directory.
            if (
                row.is_dir
                and item.row is not None
                and item.row.total_duration is not None
                and row.total_duration is None
                and row.file_signature == item.row.file_signature
            ):
                row.total_duration = item.row.total_duration
                row.values[2] = item.row.values[2]
                row.sort_values[2] = item.row.sort_values[2]
            # Metadata enrichment returns a fresh row. Keep the inexpensive
            # direct-child count that may have completed while metadata was
            # being read, instead of silently replacing it with a dash.
            if row.is_dir and item.folder_count is not None:
                # Always show the cheap count immediately. If full-size mode
                # is enabled, the recursive byte total will replace it later.
                apply_folder_count(row, item.folder_count)
            # Publish the replacement row only after restoring its count. The
            # revision notification repaints bound GTK cells synchronously; if
            # it fires before apply_folder_count(), a count completed earlier
            # can remain stored in the model but invisible in the list.
            item.update(row)
            if row.is_dir and self.window.state.settings.get('folder_sizes', False):
                item.folder_size_known = False
                self.folder_size_executor.submit(
                    self.measure_folder_size, path, generation, self.cancel, self.folder_size_cancel
                )
        if not self.model_timer:
            self.model_timer = GLib.timeout_add(150, self.update_models)
        if self.window.active is self and (item in self.selected() or self.window.state.settings['preview_first']):
            self.window.selection_changed()
        return False

    def measure_folder_count(self, path, generation, cancel):
        # Count only direct children, never recurse: this gives folders a useful
        # value in the Size column without the long scan required for byte size.
        count = 0
        try:
            with os.scandir(path) as entries:
                for _entry in entries:
                    if cancel.is_set():
                        return
                    count += 1
            self.deliver(self.folder_count_ready, cancel, generation, Path(path), count)
        except OSError:
            pass

    def folder_count_ready(self, generation, path, count):
        if generation != self.generation or self.closed:
            return False
        item = self.items.get(str(path))
        if item and item.row.is_dir:
            item.folder_count = count
            # A recursive scan can finish before this shallow count. Never let
            # a late count overwrite the completed byte size.
            if not (self.window.state.settings.get('folder_sizes', False) and item.folder_size_known):
                apply_folder_count(item.row, count)
                item.revision += 1
            self.view.get_sorter().changed(Gtk.SorterChange.DIFFERENT)
        return False

    def schedule_folder_sizes(self):
        if not self.window.state.settings.get('folder_sizes', False):
            return
        self.folder_size_cancel.set()
        self.folder_size_cancel = threading.Event()
        generation = self.generation
        cancel = self.cancel
        size_cancel = self.folder_size_cancel
        for item in tuple(self.items.values()):
            if item.row.is_dir:
                self.folder_size_executor.submit(
                    self.measure_folder_size, item.path, generation, cancel, size_cancel
                )

    def set_folder_sizes(self, enabled):
        if enabled:
            self.schedule_folder_sizes()
        else:
            self.folder_size_cancel.set()
            for item in self.items.values():
                if item.row.is_dir:
                    item.folder_size_known = False
                    if item.folder_count is not None:
                        apply_folder_count(item.row, item.folder_count)
                        item.revision += 1
            self.view.get_sorter().changed(Gtk.SorterChange.DIFFERENT)

    def measure_folder_size(self, path, generation, cancel, size_cancel):
        total = 0
        try:
            for root, dirs, files in os.walk(path, followlinks=False):
                if cancel.is_set() or size_cancel.is_set():
                    return
                dirs[:] = [name for name in dirs if not (Path(root) / name).is_symlink()]
                for name in files:
                    if cancel.is_set() or size_cancel.is_set():
                        return
                    target = Path(root) / name
                    try:
                        if not target.is_symlink():
                            total += target.stat().st_size
                    except OSError:
                        continue
            if not size_cancel.is_set():
                self.deliver(self.folder_size_ready, cancel, generation, Path(path), total, size_cancel)
        except OSError:
            pass

    def folder_size_ready(self, generation, path, total, size_cancel):
        if generation != self.generation or self.closed or size_cancel.is_set():
            return False
        item = self.items.get(str(path))
        if item and item.row.is_dir:
            item.row.values[1] = metadata.quantity(total, ['o', 'Kio', 'Mio', 'Gio', 'Tio'], 1024)
            item.row.sort_values[1] = total
            item.folder_size_known = True
            item.revision += 1
            self.view.get_sorter().changed(Gtk.SorterChange.DIFFERENT)
        return False

    def update_models(self):
        self.model_timer = 0
        if not self.closed:
            selected = [item.path for item in self.selected()]
            self.filter.changed(Gtk.FilterChange.DIFFERENT)
            self.view.get_sorter().changed(Gtk.SorterChange.DIFFERENT)
            self.select_paths(selected)
        return False

    def deliver(self, callback, cancel, *args):
        while not self.delivery_slots.acquire(timeout=0.1):
            if cancel.is_set():
                return
        if cancel.is_set():
            self.delivery_slots.release()
            return

        def receive():
            try:
                return callback(*args)
            finally:
                self.delivery_slots.release()

        GLib.idle_add(receive)

    def changed_event(self, monitor, file, other, event, generation):
        if generation != self.generation:
            return
        for f in (file, other):
            if f and f.get_path():
                self.changed.add(f.get_path())
        if not self.change_timer:
            self.change_timer = GLib.timeout_add(250, self.flush_changes)

    def flush_changes(self):
        self.change_timer = 0
        paths = [Path(p) for p in self.changed]
        self.changed.clear()
        if self.closed:
            return False
        update = []
        for path in paths:
            if path.parent != self.folder:
                continue
            key = str(path)
            if not path.exists():
                item = self.items.pop(key, None)
                if item:
                    found, index = self.store.find(item)
                    if found:
                        self.store.remove(index)
            else:
                if key not in self.items:
                    try:
                        self.add_rows(self.generation, [metadata.basic_entry(path, path.is_dir())])
                    except OSError:
                        continue
                update.append(path)
        if update:
            self.futures.append(self.executor.submit(self.enrich, update, self.generation, self.cancel))
        self.futures = [f for f in self.futures if not f.done()]
        if self.window.active is self:
            self.window.update_status()
        return False

    def touch(self, path):
        if self.is_trash or self.remote_file is not None:
            return
        path = Path(path)
        if path.parent == self.folder:
            self.changed.add(str(path))
            if not self.change_timer:
                self.change_timer = GLib.timeout_add(100, self.flush_changes)

    def close(self):
        if self.closed:
            return
        self.stop_remote_listing()
        self.closed = True
        self.cancel.set()
        self.search_cancel.set()
        if self.search_timer:
            GLib.source_remove(self.search_timer)
        if self.monitor:
            self.monitor.cancel()
        if self.change_timer:
            GLib.source_remove(self.change_timer)
        if self.model_timer:
            GLib.source_remove(self.model_timer)
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.folder_size_executor.shutdown(wait=False, cancel_futures=True)
        self.folder_count_executor.shutdown(wait=False, cancel_futures=True)
