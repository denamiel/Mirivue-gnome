"""Native GTK4 / libadwaita presentation, sharing safe toolkit-free media services."""

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os, shutil, subprocess, queue, json, threading
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk, Gio, Gdk, GLib
from . import __version__, i18n
from .i18n import tr, trf
from .backend import State, MediaService, JobQueue
from .tabs import TabGroup
from .templates import Templates
from .pane import Pane
from .preview import Preview, Thumbnails
from .indicator import StatusNotifier, appindicator_available
from .places import (
    bookmark_file,
    read_bookmarks,
    write_bookmarks,
    migrate_legacy_favorites,
    rename_bookmark,
    add_bookmark_folders,
    reorder_bookmark,
)
from .core import (
    metadata,
    media,
    file_moves,
    extensions,
    renaming,
    duplicates,
    remux,
    health,
    archive_backend,
    associated,
    gio_backend,
    directory_merge,
    trash as trash_service,
)
from .core.undo import UndoManager, RenameRecord, FolderRecord, TrashRecord, BatchRecord, record_paths, individual_records
from .core.file_safety import check_removal
from .clipboard_transfer import (
    encode_uris, decode_uris,
    GNOME_MIME,
    LEGACY_MIME,
    encode_files,
    decode_files,
    unique_destination,
    replace_existing_file,
)
from . import dialogs


# Compatibility helpers kept for installer smoke checks.
def readable_size(value):
    return i18n.size_text(metadata.quantity(value, ['o', 'Kio', 'Mio', 'Gio', 'Tio'], 1024))


def archive_backend_supported(path):
    return str(path).lower().endswith(('.zip', '.cbz', '.tar', '.tgz', '.tar.gz', '.tar.xz', '.tar.bz2'))


def standard_thumbnail(path):
    import hashlib

    try:
        root = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'thumbnails'
        name = hashlib.md5(path.absolute().as_uri().encode()).hexdigest() + '.png'
        for size in ('large', 'x-large', 'normal'):
            file = root / size / name
            if file.is_file() and file.stat().st_mtime >= path.stat().st_mtime:
                return file
    except OSError:
        pass
    return None


class MirivueWindow(Adw.ApplicationWindow):
    def __init__(self, application, state=None, restore_session=True):
        super().__init__(application=application, title='Mirivue')
        self.state = state or State()
        i18n.language = self.state.settings['language']
        self.set_default_size(1280, 800)
        # Breakpoint windows require a minimum allocation (libadwaita contract).
        self.set_size_request(360, 240)
        if self.state.legacy_favorites:
            migrate_legacy_favorites(self.state.legacy_favorites)
            self.state.legacy_favorites = []
            self.state.save()
        self.service = MediaService(self.state)
        self.jobs = JobQueue()
        self.undo_manager = UndoManager()
        self.thumbnails = Thumbnails(self.state.root)
        self.starred_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='gnome-starred')
        self.history_path = self.state.root / 'operations.json'
        self.recorded_jobs = set()
        self.past_jobs = []
        self.playback_history_path = self.state.root / 'playback.json'
        if self.state.settings['history']:
            try:
                self.past_jobs = json.loads(self.history_path.read_text())[-100:]
            except (OSError, ValueError, TypeError):
                pass
        self.active = None
        self.navigation_pane = None
        self.panes = []
        self.clipboard_paths = []
        self.clipboard_cut = False
        self.clipboard_provider = None
        self.pending_cut_jobs = []
        self.closed = False
        self.popovers = []
        self.job_window = None
        self.indicator = None
        self.trash_monitor = None
        self.trash_image = None
        self.trash_reload_timer = 0
        self.trash_has_items = False
        self.hidden = self.state.settings['hidden'] and not self.state.settings['hide_on_start']
        self.apply_theme()
        self.install_actions()
        # Selection, focus, and view backgrounds belong to GTK and Adwaita.
        css = Gtk.CssProvider()
        css.load_from_string('''
            .duplicate { font-weight: bold; }
            .media-grid > child { margin: 6px; }
            .mirivue-path-surface {
                background-color: alpha(currentColor, 0.1);
                border-radius: 9px;
            }
            .mirivue-path-surface button {
                margin: 3px;
                border-radius: 7px;
            }
        ''')
        Gtk.StyleContext.add_provider_for_display(
            self.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self.header = header
        self.toolbar_buttons = []
        self.toolbar_compact = True
        self.header_search = self.button('system-search-symbolic', 'Recherche', 'search')
        self.header_search.add_css_class('flat')
        self.menu_button = Gtk.MenuButton(
            icon_name='open-menu-symbolic', menu_model=self.main_menu(), tooltip_text=tr('Menu principal')
        )
        self.menu_button.add_css_class('flat')
        # Each NavigationSplitView page gets its own native toolbar and header.
        # Adwaita supplies the sidebar background and places window controls
        # at the outer edges, following the desktop decoration layout.
        self.places_toolbar = Adw.ToolbarView()
        places_header = Adw.HeaderBar()
        places_header.pack_start(self.header_search)
        places_header.pack_end(self.menu_button)
        self.places_toolbar.add_top_bar(places_header)
        self.toolbar_start = Gtk.Box(spacing=2, hexpand=False)
        self.toolbar_end = Gtk.Box(spacing=2, hexpand=False)
        self.path_group = Gtk.Box(spacing=0, hexpand=True, css_classes=['mirivue-path-bars'])
        # Use HeaderBar's native start/end slots. A single location bar stays
        # in the title slot; controls can therefore reach both header edges.
        header.pack_start(self.toolbar_start)
        header.set_title_widget(self.path_group)
        header.pack_end(self.toolbar_end)
        # The places footer is hidden when the adaptive sidebar folds away.
        # Keep its operations entry and active progress accessible in the header.
        self.compact_operations = self.button('view-list-bullet-symbolic', 'Opérations', 'operations')
        self.compact_operations.add_css_class('flat')
        self.compact_operations.set_visible(False)
        self.compact_progress = Gtk.ProgressBar(width_request=72, valign=Gtk.Align.CENTER)
        self.compact_progress.set_visible(False)
        header.pack_end(self.compact_operations)
        header.pack_end(self.compact_progress)
        self.toolbar.add_top_bar(header)
        self.body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.paned = Gtk.Paned(
            orientation=Gtk.Orientation.HORIZONTAL,
            hexpand=True,
            vexpand=True,
            shrink_start_child=False,
            shrink_end_child=False,
        )
        left = Pane(self, 'left')
        right = Pane(self, 'right')
        self.panes = [left, right]
        self.active = left
        for pane in self.panes:
            self.path_group.append(pane.location_bar)
        self.templates = Templates(self)
        for pane in self.panes:
            pane.location_bar.menu_button.set_menu_model(pane.location_bar.path_menu(self.templates.menu))
        self.tab_groups = []
        for pane in (left, right):
            tabs = TabGroup(self, pane)
            self.tab_groups.append(tabs)
        self.paned.set_start_child(self.tab_groups[0])
        self.paned.set_end_child(self.tab_groups[1])
        self.tab_groups[1].set_visible(self.state.settings['split'])
        self.paned.set_position(450)
        self.sync_path_visibility()
        self.connect('notify::width', lambda *_: self.sync_path_visibility())
        preview_enabled = bool(self.state.settings.get('preview', False))
        self.preview_wanted = preview_enabled
        self.preview = Preview(self)
        self.preview.set_visible(preview_enabled)
        self.preview_split = Adw.OverlaySplitView(
            content=self.paned,
            sidebar=self.preview if preview_enabled else None,
            sidebar_position=Gtk.PackType.END,
            show_sidebar=preview_enabled,
            min_sidebar_width=240,
            max_sidebar_width=420,
        )
        self.preview_split.set_show_sidebar(preview_enabled)
        self.preview_split.connect('notify::show-sidebar', self.preview_sidebar_changed)
        self.rebuild_toolbar()
        self.body.append(self.preview_split)
        self.places_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # GNOME Files keeps Places as a single, persistent sidebar.  The
        # GTK4 port uses GTK bookmarks and GIO volumes in this list; there is
        # no separate tree mode or selector to make the same locations harder
        # to find.
        # Keep separators between sections outside the ListBox rows. A
        # separator embedded in a navigation-sidebar row inherits the row's
        # full hover/selection surface and becomes a conspicuous grey band.
        self.places = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        places_scroll = Gtk.ScrolledWindow(vexpand=True)
        places_scroll.set_child(self.places)
        self.places_box.append(places_scroll)
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        footer.set_margin_start(8)
        footer.set_margin_end(8)
        footer.set_margin_top(8)
        footer.set_margin_bottom(8)
        self.status = Gtk.Label(xalign=0, ellipsize=3)
        self.status.set_visible(False)
        footer.append(self.status)
        self.progress = Gtk.ProgressBar()
        self.progress.set_visible(False)
        footer.append(self.progress)
        actions = Gtk.Box(spacing=6, halign=Gtk.Align.START)
        self.places_operations = self.button('view-more-symbolic', 'Opérations', 'operations')
        self.places_operations.add_css_class('flat')
        actions.append(self.places_operations)
        self.stop_button = self.button('process-stop-symbolic', 'Annuler les analyses', 'cancel')
        self.stop_button.set_visible(False)
        actions.append(self.stop_button)
        footer.append(actions)
        self.places_box.append(footer)
        self.volume_monitor = Gio.VolumeMonitor.get()
        for signal in (
            'mount-added',
            'mount-removed',
            'mount-changed',
            'volume-added',
            'volume-removed',
            'volume-changed',
        ):
            self.volume_monitor.connect(signal, lambda *_: GLib.idle_add(self.fill_places))
        self.bookmark_monitor = None
        self.bookmark_refresh_timer = 0
        self.setup_bookmark_monitor()
        self.fill_places()
        self.places_toolbar.set_content(self.places_box)
        self.toolbar.set_content(self.body)
        self.navigation = Adw.NavigationSplitView(
            sidebar=Adw.NavigationPage.new(self.places_toolbar, 'Mirivue'),
            content=Adw.NavigationPage.new(self.toolbar, tr('Fichiers')),
            min_sidebar_width=260,
            max_sidebar_width=280,
        )
        self.paned.connect('notify::position', lambda *_: self.sync_toolbar_geometry())
        self.sync_toolbar_geometry()
        self.toasts = Adw.ToastOverlay(child=self.navigation)
        self.tab_overview = Adw.TabOverview(child=self.toasts, view=left.tabs.view)
        self.tab_overview.connect('create-tab', self.overview_new_tab)
        self.set_content(self.tab_overview)
        self.tabs_button = Adw.TabButton(view=left.tabs.view, visible=False)
        self.tabs_button.set_tooltip_text(tr('Afficher les onglets'))
        self.tabs_button.connect('clicked', lambda *_: self.tab_overview.set_open(True))
        header.pack_end(self.tabs_button)
        GLib.idle_add(self.apply_preview_startup, priority=GLib.PRIORITY_LOW)
        # Adwaita peut restaurer l’état de la barre latérale lors du premier
        # calcul de géométrie. Une seconde vérification après ce calcul garantit
        # que la préférence de démarrage est respectée.
        GLib.timeout_add(350, self.apply_preview_startup)
        for limit, widget, prop in [
            (850, self.navigation, 'collapsed'),
            (1100, self.preview_split, 'collapsed'),
        ]:
            bp = Adw.Breakpoint.new(
                Adw.BreakpointCondition.new_length(
                    Adw.BreakpointConditionLengthType.MAX_WIDTH, limit, Adw.LengthUnit.SP
                )
            )
            bp.add_setter(widget, prop, True)
            if limit == 850:
                bp.add_setter(self.tabs_button, 'visible', True)
                for group in self.tab_groups:
                    bp.add_setter(group.bar, 'visible', False)
            self.add_breakpoint(bp)
        self.connect('close-request', self.close_requested)
        folder = self.start_folder()
        left.open(folder)
        if self.tab_groups[1].get_visible():
            right.open(folder)
        self.activate_pane(left)
        self.navigation_pane = left
        self.tick_id = GLib.timeout_add(150, self.tick)
        self.sync_indicator()
        if restore_session and self.state.settings['startup'] == 'session':
            from .session import restore
            restore(self)
        if self.state.recovery_notice:
            self.notify(self.state.recovery_notice)

    def start_folder(self):
        choice = self.state.settings['startup']
        raw = (
            self.state.settings['last_folder']
            if choice == 'last'
            else self.state.settings['startup_path']
            if choice == 'custom'
            else str(Path.home())
        )
        if choice == 'session':
            groups = self.state.settings['tab_session'].get('groups', [])
            locations = groups[0].get('locations', []) if isinstance(groups, list) and groups and isinstance(groups[0], dict) else []
            locations = locations if isinstance(locations, list) else []
            raw = Gio.File.new_for_uri(locations[0]).get_path() if locations and isinstance(locations[0], str) else None
            raw = raw or self.state.settings['last_folder'] or self.state.settings['startup_path']
        path = Path(raw or str(Path.home()))
        return path if path.is_dir() else Path.home()

    @staticmethod
    def readable_size(value):
        return readable_size(value)

    def button(self, icon, label, action):
        theme = Gtk.IconTheme.get_for_display(self.get_display())
        if not theme.has_icon(icon):
            return Gtk.Button(label=tr(label), tooltip_text=tr(label), action_name='win.' + action)
        return Gtk.Button(icon_name=icon, tooltip_text=tr(label), action_name='win.' + action)

    TOOLBAR = {
        'home': ('go-home-symbolic', 'Dossier personnel'),
        'up': ('go-up-symbolic', 'Dossier parent'),
        'back': ('go-previous-symbolic', 'Précédent'),
        'forward': ('go-next-symbolic', 'Suivant'),
        'refresh': ('view-refresh-symbolic', 'Actualiser'),
        'details': ('view-list-symbolic', 'Vue en liste'),
        'icons': ('view-grid-symbolic', 'Vue en grille'),
        'split': ('view-dual-symbolic', 'Deux panneaux'),
        'preview': ('view-reveal-symbolic', 'Aperçu'),
        'thumbnails': ('image-x-generic-symbolic', 'Afficher les miniatures'),
        'hidden': ('view-conceal-symbolic', 'Éléments cachés'),
        'paths': ('', 'Barre de chemin'),
    }

    def toolbar_icon_pixels(self):
        # The standard size belongs to GTK; explicit sizes are user choices.
        return {'large': 24, 'huge': 32}.get(self.state.settings.get('toolbar_icon_size', 'normal'))

    def rebuild_toolbar(self):
        for group in (self.toolbar_start, self.toolbar_end):
            while group.get_first_child():
                group.remove(group.get_first_child())
        self.toolbar_buttons = []
        icon_pixels = self.toolbar_icon_pixels()
        group = self.toolbar_start
        for key in self.state.settings['toolbar_order']:
            if key in self.state.settings['toolbar_hidden']:
                continue
            if key == 'paths':
                group = self.toolbar_end
                continue
            icon, label = self.TOOLBAR[key]
            if key in ('details', 'icons', 'split', 'preview', 'hidden', 'thumbnails'):
                button = Gtk.ToggleButton(tooltip_text=tr(label))
                image = Gtk.Image.new_from_icon_name(icon)
                if icon_pixels:
                    image.set_pixel_size(icon_pixels)
                button.set_child(image)
                button.set_action_name('win.' + key)
            else:
                button = self.button(icon, label, key)
            button.add_css_class('flat')
            button.toolbar_key = key
            style = 'icons' if self.toolbar_compact else self.state.settings['toolbar_style']
            if style == 'text':
                button.set_label(tr(label))
            elif style == 'both':
                child = Gtk.Box(spacing=5)
                image = Gtk.Image.new_from_icon_name(icon)
                if icon_pixels:
                    image.set_pixel_size(icon_pixels)
                child.append(image)
                text = Gtk.Label(label=tr(label), ellipsize=3, max_width_chars=12)
                child.append(text)
                button.set_child(child)
            else:
                image = button.get_child()
                if icon_pixels and isinstance(image, Gtk.Image):
                    image.set_pixel_size(icon_pixels)
            group.append(button)
            self.toolbar_buttons.append(button)
        self.sync_toggle_actions()

    def sync_toolbar_geometry(self):
        # A single titlebar location field follows the active pane, as GNOME
        # Files updates its header bar for the current browsing context.
        if self.active and hasattr(self.active, 'location_bar'):
            self.active.location_bar.sync_overflow()
        return False

    def sync_path_visibility(self):
        if not hasattr(self, 'path_group'):
            return
        # One location field avoids misaligned, competing entries in the
        # headerbar. The active-pane change updates its breadcrumb immediately.
        for pane in self.panes:
            pane.location_bar.set_visible(pane is self.active)

    def install_actions(self):
        actions = {
            'home': lambda: self.active.open(Path.home()),
            'up': lambda: self.active.up(),
            'back': lambda: self.active.back(-1),
            'forward': lambda: self.active.back(1),
            'copy-location': self.copy_current_location,
            'folder-properties': self.folder_properties,
            'folder-open-with': self.open_folder_with,
            'refresh': self.refresh_active,
            'search': self.toggle_search,
            'split': self.toggle_split,
            'preview': self.toggle_preview,
            'icons': lambda: self.active.stack.set_visible_child_name('icons'),
            'details': lambda: self.active.stack.set_visible_child_name('details'),
            'open': lambda: self.open_items(self.active.selected()),
            'open-with': self.open_with,
            'rename': self.rename,
            'bulk-rename': self.bulk_rename,
            'external-rename': self.external_rename,
            'copy': lambda: self.copy(False),
            'cut': lambda: self.copy(True),
            'paste': self.paste,
            'duplicate': self.duplicate,
            'copy-path': self.copy_path,
            'new-folder': self.new_folder,
            'group': self.group_folder,
            'trash': self.trash,
            'delete': lambda: self.trash(True),
            'restore-trash': self.restore_trash,
            'delete-trash': self.delete_trash,
            'select-all': lambda: (
                self.active.selection.select_all()
            ),
            'hidden': self.toggle_hidden,
            'folders-first': self.toggle_folders_first,
            'terminal': self.terminal,
            'columns': lambda: dialogs.columns(self),
            'preferences': lambda: dialogs.preferences(self),
            'operations': self.operations,
            'cancel': self.cancel_analyses,
            'pause': self.pause_jobs,
            'test': lambda: self.analyze('test'),
            'total': lambda: self.analyze('total'),
            'metadata': lambda: dialogs.metadata_editor(self),
            'properties': self.properties,
            'error': self.show_error,
            'extension': self.correct_extension,
            'mkv': self.mkv_copy,
            'clear-search': self.clear_search,
            'toolbar': lambda: dialogs.toolbar(self),
            'show-menu': lambda: self.menu_button.popup(),
            'advanced-search': lambda: dialogs.search(self),
            'organize': lambda: dialogs.organize(self),
            'new-tab': self.new_tab,
            'new-window': lambda: self.new_window(self.active.remote_file or self.active.folder),
            'open-folder-tabs': lambda: self.open_selected_folders(False),
            'open-folder-windows': lambda: self.open_selected_folders(True),
            'invert-selection': self.invert_selection,
            'restore-tab': lambda: self.active.tabs.restore(),
            'close-tab': self.close_tab,
            'thumbnails': self.toggle_thumbnails,
            'stop-loading': lambda: self.active.stop_loading(),
            'add-place': self.add_place,
            'remove-place': self.remove_place,
            'rename-place': self.rename_place,
            'collection': self.add_collection,
            'label': self.set_label,
            'export': self.export,
            'summary': lambda: dialogs.media_summary(self),
            'empty-trash': self.empty_trash,
            'quit': self.request_quit,
            'help': lambda: dialogs.help_page(self),
            'shortcuts': lambda: dialogs.shortcuts(self),
            'media-tools': lambda: dialogs.media_tools(self),
            'about': self.about,
            'previous-tab': lambda: self.switch_tab(-1),
            'next-tab': lambda: self.switch_tab(1),
            'zoom-in': lambda: self.active.set_zoom(self.active.zoom + 12),
            'zoom-out': lambda: self.active.set_zoom(self.active.zoom - 12),
            'zoom-normal': lambda: self.active.set_zoom(96),
            'bookmark-current': self.bookmark_current,
            'new-text-file': self.new_text_file,
            'archive-create': self.create_archive_selected,
            'archive-open': self.open_archive_selected,
            'archive-extract-here': lambda: self.extract_selected_archive(here=True),
            'archive-extract-to': self.extract_selected_archive,
            'archive-extract-trash': lambda: self.extract_selected_archive(here=True, trash_after=True),
            'associated': self.select_associated,
            'compare-media': self.compare_media,
            'diagnostics': self.diagnostics,
            'undo-file': lambda: self.reverse_file_operation(False),
            'redo-file': lambda: self.reverse_file_operation(True),
        }
        for name, callback in actions.items():
            action = (
                Gio.SimpleAction.new_stateful(name, None, GLib.Variant('b', False))
                if name in ('hidden', 'preview', 'split', 'thumbnails', 'details', 'icons', 'folders-first')
                else Gio.SimpleAction.new(name, None)
            )
            action.connect(
                'activate',
                lambda _a, _p, cb=callback, n=name: (self.invoke_action(n, cb), self.sync_toggle_actions()),
            )
            self.add_action(action)
        recent = Gio.SimpleAction.new('open-recent', GLib.VariantType.new('s'))
        recent.connect('activate', lambda _a, value: self.open_recent(value.get_string()))
        self.add_action(recent)
        collection = Gio.SimpleAction.new('open-collection', GLib.VariantType.new('s'))
        collection.connect('activate', lambda _a, value: self.open_collection(value.get_string()))
        self.add_action(collection)
        paste_into = Gio.SimpleAction.new('paste-into', GLib.VariantType.new('s'))
        paste_into.connect('activate', lambda _a, value: self.paste(Path(value.get_string())))
        self.add_action(paste_into)
        open_folder_tab = Gio.SimpleAction.new('open-folder-tab', GLib.VariantType.new('s'))
        open_folder_tab.connect('activate', lambda _a, value: self.new_tab(value.get_string()))
        self.add_action(open_folder_tab)
        template = Gio.SimpleAction.new('new-from-template', GLib.VariantType.new('s'))
        template.connect('activate', lambda _a, value: self.new_from_template(Gio.File.new_for_uri(value.get_string())))
        self.add_action(template)
        find_duplicates_folder = Gio.SimpleAction.new('find-duplicates-folder', GLib.VariantType.new('s'))
        find_duplicates_folder.connect(
            'activate', lambda _a, value: self.find_duplicates(folder=Path(value.get_string()))
        )
        self.add_action(find_duplicates_folder)
        rename_folder_contents = Gio.SimpleAction.new('rename-folder-contents', GLib.VariantType.new('s'))
        rename_folder_contents.connect(
            'activate', lambda _a, value: self.rename_folder_contents(Path(value.get_string()))
        )
        self.add_action(rename_folder_contents)
        paste_uri = Gio.SimpleAction.new('paste-into-uri', GLib.VariantType.new('s'))
        paste_uri.connect('activate', lambda _a, value: self.paste_gio(Gio.File.new_for_uri(value.get_string())))
        self.add_action(paste_uri)
        app = self.get_application()
        for name, keys in {
            'show-menu': ['F10'],
            'new-tab': ['<Control>t'],
            'new-window': ['<Control>n'],
            'open-folder-tabs': ['<Control>Return'],
            'open-folder-windows': ['<Shift>Return'],
            'invert-selection': ['<Control><Shift>i'],
            'details': ['<Control>1'],
            'icons': ['<Control>2'],
            'open': ['<Control>o'],
            'delete': ['<Shift>Delete'],
            'close-tab': ['<Control>w'],
            'restore-tab': ['<Control><Shift>t'],
            'refresh': ['F5', '<Control>r'],
            'split': ['F3'],
            'preview': ['F9'],
            'search': ['<Control>f'],
            'copy': ['<Control>c'],
            'cut': ['<Control>x'],
            'paste': ['<Control>v'],
            'undo-file': ['<Control>z'],
            'redo-file': ['<Control><Shift>z'],
            'select-all': ['<Control>a'],
            'new-folder': ['<Control><Shift>n'],
            'terminal': ['<Control>period'],
            'rename': ['F2'],
            'trash': ['Delete'],
            'hidden': ['<Control>h'],
            'quit': ['<Control>q'],
            'back': ['<Alt>Left'],
            'forward': ['<Alt>Right'],
            'up': ['<Alt>Up'],
            'home': ['<Alt>Home'],
            'bookmark-current': ['<Control>d'],
            'properties': ['<Alt>Return', '<Control>i'],
            'help': ['F1'],
            'preferences': ['<Control>comma'],
            'shortcuts': ['<Control>question'],
            'zoom-in': ['<Control>plus', '<Control>equal', '<Control>KP_Add'],
            'zoom-out': ['<Control>minus', '<Control>KP_Subtract'],
            'zoom-normal': ['<Control>0', '<Control>KP_0'],
        }.items():
            app.set_accels_for_action('win.' + name, keys)
        action = Gio.SimpleAction.new('location', None)
        action.connect('activate', lambda *_: self.active.location_bar.set_mode('text'))
        self.add_action(action)
        app.set_accels_for_action('win.location', ['<Control>l'])

    def invoke_action(self, name, callback):
        if self.active.remote_file is not None and name not in {
            'home',
            'up',
            'back',
            'forward',
            'copy-location',
            'refresh',
            'search',
            'split',
            'copy',
            'cut',
            'paste',
            'select-all',
            'hidden',
            'folders-first',
            'columns',
            'preferences',
            'operations',
            'cancel',
            'pause',
            'clear-search',
            'toolbar',
            'show-menu',
            'new-tab',
            'new-window',
            'open-folder-tabs',
            'open-folder-windows',
            'invert-selection',
            'close-tab',
            'restore-tab',
            'icons',
            'details',
            'open',
            'open-with',
            'copy-path',
            'rename',
            'new-folder',
            'trash',
            'delete',
            'properties',
            'stop-loading',
            'quit',
            'help',
            'shortcuts',
            'about',
            'previous-tab',
            'next-tab',
            'diagnostics',
            'undo-file',
            'redo-file',
        }:
            self.notify(tr('Cette action nécessite un dossier local.'))
            return
        callback()

    def sync_toggle_actions(self):
        if not hasattr(self, 'tab_groups'):
            return
        values = {
            'hidden': self.hidden,
            'preview': self.preview_split.get_show_sidebar(),
            'split': self.tab_groups[1].get_visible(),
            'thumbnails': self.state.settings['thumbnails'],
            'folders-first': self.state.settings['folders_first'],
            'details': self.active.stack.get_visible_child_name() == 'details',
            'icons': self.active.stack.get_visible_child_name() == 'icons',
        }
        for key, value in values.items():
            self.lookup_action(key).set_state(GLib.Variant('b', value))
        self.lookup_action('undo-file').set_enabled(bool(self.undo_manager.undo_stack))
        self.lookup_action('redo-file').set_enabled(bool(self.undo_manager.redo_stack))
        local_folder = (
            self.active.remote_file is None and not self.active.is_trash and not self.active.is_starred
        )
        self.lookup_action('search').set_enabled(not self.active.is_trash and not self.active.is_starred
                                                and (self.active.remote_file is None or self.active.remote_file.get_uri().rstrip('/') != 'network:'))
        for name in ('new-text-file', 'media-tools', 'advanced-search'):
            self.lookup_action(name).set_enabled(local_folder)
        remote = self.active.remote_file is not None
        self.lookup_action('new-folder').set_enabled(local_folder or remote and self.active.remote_can_write)
        selected = self.active.selected()
        for name, capability in (('rename', 'rename'), ('trash', 'trash'), ('delete', 'delete')):
            enabled = not remote or bool(selected) and all(
                getattr(item.row, 'file_capabilities', {}).get(capability, False) for item in selected)
            if remote and name == 'rename':
                enabled = enabled and len(selected) == 1
            self.lookup_action(name).set_enabled(enabled)
        active = {
            'hidden': values['hidden'],
            'preview': values['preview'],
            'split': values['split'],
            'thumbnails': values['thumbnails'],
            'details': values['details'],
            'icons': values['icons'],
        }
        for button in getattr(self, 'toolbar_buttons', []):
            classes = ['flat']
            size = self.state.settings.get('toolbar_icon_size', 'normal')
            if size in ('large', 'huge'):
                classes.append('toolbar-' + size)
            button.set_css_classes(classes)
            if isinstance(button, Gtk.ToggleButton):
                button.set_active(active.get(getattr(button, 'toolbar_key', ''), False))

    def column_header_menu(self):
        menu = Gio.Menu()
        menu.append(tr('Colonnes…'), 'win.columns')
        return menu

    def main_menu(self):
        menu = Gio.Menu()
        navigation = Gio.Menu()
        navigation.append(tr('Nouveau dossier…'), 'win.new-folder')
        menu.append_section(None, navigation)
        editing = Gio.Menu()
        for label, action in [
            ('Annuler une opération de fichier', 'undo-file'),
            ('Rétablir une opération de fichier', 'redo-file'),
        ]:
            editing.append(tr(label), 'win.' + action)
        menu.append_section(None, editing)
        tools = Gio.Menu()
        for label, action in [
            ('Outils multimédias…', 'media-tools'),
            ('Diagnostic de Mirivue', 'diagnostics'),
        ]:
            tools.append(tr(label), 'win.' + action)
        menu.append_section(None, tools)
        jobs = Gio.Menu()
        jobs.append(tr('Arrêter le chargement du dossier'), 'win.stop-loading')
        menu.append_section(None, jobs)
        if self.state.settings['recent'] and self.state.settings['recent_paths']:
            recent = Gio.Menu()
            for path in self.state.settings['recent_paths']:
                item = Gio.MenuItem.new(Path(path).name, None)
                item.set_action_and_target_value('win.open-recent', GLib.Variant('s', path))
                recent.append_item(item)
            menu.append_submenu(tr('Médias récents'), recent)
        if self.state.settings['collections']:
            collections = Gio.Menu()
            for name in self.state.settings['collections']:
                item = Gio.MenuItem.new(name, None)
                item.set_action_and_target_value('win.open-collection', GLib.Variant('s', name))
                collections.append_item(item)
            menu.append_submenu(tr('Collections de médias'), collections)
        standard = Gio.Menu()
        standard.append(tr('Préférences…'), 'win.preferences')
        standard.append(tr('Raccourcis clavier'), 'win.shortcuts')
        standard.append(tr('Aide'), 'win.help')
        standard.append(tr('À propos de Mirivue'), 'win.about')
        menu.append_section(None, standard)
        return menu

    def activate_pane(self, pane, from_focus=False):
        if from_focus and self.navigation_pane is not None and self.navigation_pane is not pane:
            return
        self.active = pane
        for group in getattr(self, 'tab_groups', ()):
            group.view.set_shortcuts(Adw.TabViewShortcuts.ALL_SHORTCUTS if group is pane.tabs
                                     else Adw.TabViewShortcuts.NONE)
        if hasattr(self, 'tab_overview'):
            self.tab_overview.set_view(pane.tabs.view)
            self.tabs_button.set_view(pane.tabs.view)
        for current in self.panes:
            current.remove_css_class('inactive-pane')
            current.remove_css_class('active-pane')
            current.view.remove_css_class('inactive-pane')
            current.view.remove_css_class('active-pane')
            current.grid.remove_css_class('inactive-pane')
            current.grid.remove_css_class('active-pane')
            current.view.remove_css_class('frame')
            current.grid.remove_css_class('frame')
        self.sync_active_pane_indicator()
        title = (
            (
                tr('Réseau')
                if pane.remote_file.get_uri().rstrip('/') == 'network:'
                else pane.remote_file.get_basename() or pane.remote_file.get_uri()
            )
            if pane.remote_file is not None
            else tr('Corbeille')
            if pane.is_trash
            else tr('Favoris')
            if pane.is_starred
            else tr('Dossier personnel')
            if pane.folder == Path.home()
            else pane.folder.name or '/'
        )
        self.set_title(f"{title} — Mirivue")
        self.sync_path_visibility()
        self.sync_toolbar_geometry()
        if hasattr(self, 'preview'):
            self.selection_changed()

    def sync_active_pane_indicator(self):
        split = len(getattr(self, 'tab_groups', ())) > 1 and self.tab_groups[1].get_visible()
        for pane in self.panes:
            if split and pane is self.active:
                pane.panel_count.add_css_class('accent')
            else:
                pane.panel_count.remove_css_class('accent')

    def selection_changed(self):
        items = self.active.selected()
        if self.active.is_trash or self.active.remote_file is not None:
            self.preview.show_items([])
            self.update_status()
            self.sync_toggle_actions()
            return
        if not items and self.state.settings['preview_first']:
            for index in range(self.active.sorted.get_n_items()):
                item = self.active.sorted.get_item(index)
                if not item.row.is_dir:
                    items = [item]
                    break
        self.preview.show_items(items)
        self.update_status()
        self.sync_toggle_actions()

    def update_status(self):
        if not hasattr(self, 'status') or not self.active:
            return
        self.active.update_panel_status()
        selected = self.active.selected()
        label = (
            selected[0].path.name
            if len(selected) == 1
            else f'{len(selected)} {tr("éléments sélectionnés")}'
            if selected
            else ''
        )
        self.status.set_label(label)
        self.status.set_tooltip_text(label or None)
        self.status.set_visible(bool(label))

    def notify(self, text):
        if not self.closed:
            self.toasts.add_toast(Adw.Toast(title=tr(str(text))))
        return False

    def toggle_search(self):
        self.active.set_search_visible(not self.active.search_box.get_visible())

    def open_search_filters(self, pane):
        self.activate_pane(pane)
        dialogs.search(self)

    def clear_search(self):
        self.active.search.set_text('')
        self.active.clear_search_filters()

    def refresh_active(self):
        if self.active.search_box.get_visible() and self.active.remote_file is None:
            if self.active.search_recursive_active:
                self.active.search_changed()
            else:
                self.active.open(self.active.folder, False, keep_search=True)
            return
        if self.active.remote_file is not None:
            self.active.open_remote(self.active.remote_file, False, keep_search=True)
        elif self.active.is_trash:
            self.active.open_trash(False)
        else:
            self.active.open(self.active.folder, False)

    def toggle_split(self):
        tabs = self.tab_groups[1]
        tabs.set_visible(not tabs.get_visible())
        if tabs.get_n_pages() == 0:
            right = self.new_tab(self.active.remote_file or self.active.folder, group=tabs)
        else:
            right = tabs.get_nth_page(tabs.get_current_page())
        if tabs.get_visible() and not right.history:
            if self.active.remote_file is not None:
                right.open_remote(self.active.remote_file)
            else:
                right.open(self.active.folder)
        if not tabs.get_visible():
            self.activate_pane(self.tab_groups[0].get_nth_page(self.tab_groups[0].get_current_page()))
        self.sync_active_pane_indicator()
        self.sync_path_visibility()

    def new_tab(self, folder=None, group=None):
        group = group or self.active.tabs
        if folder is None:
            folder = (self.active.remote_file.get_uri() if self.active.remote_file is not None else
                      'trash:///' if self.active.is_trash else
                      'starred:///' if self.active.is_starred else self.active.folder)
        if isinstance(folder, Gio.File):
            file = folder
        elif '://' in str(folder):
            file = Gio.File.new_for_uri(str(folder))
        else:
            file = Gio.File.new_for_path(str(folder))
        path = file.get_path()
        if path and not Path(path).is_dir():
            self.notify(tr('Dossier inaccessible.'))
            return
        slot = group.slot
        pane = Pane(self, slot)
        pane.tabs = group
        group.append_pane(pane, file.get_basename() or '/')
        group.set_visible(True)
        self.navigate_file(pane, file)
        return pane

    def navigate_file(self, pane, file):
        uri = file.get_uri()
        if uri.startswith('trash:'):
            pane.open_trash()
        elif uri.startswith('starred:'):
            pane.open_starred()
        elif file.get_path():
            pane.open(Path(file.get_path()))
        else:
            self.open_gio_location(file, pane)

    def overview_new_tab(self, _overview):
        pane = self.new_tab()
        return pane.tabs.view.get_page(pane) if pane else None

    def new_window(self, folder):
        window = MirivueWindow(self.get_application(), state=self.state, restore_session=False)
        file = folder if isinstance(folder, Gio.File) else (Gio.File.new_for_uri(str(folder))
                if '://' in str(folder) else Gio.File.new_for_path(str(folder)))
        window.navigate_file(window.active, file)
        window.present()

    def show_folder_properties(self, folder):
        try:
            dialogs.properties(self, [folder])
        except (GLib.Error, OSError) as error:
            self.notify(str(error))

    def close_specific_tab(self, pane):
        pane.tabs.view.close_page(pane.tabs.view.get_page(pane))

    def close_tab(self):
        self.close_specific_tab(self.active)

    def switch_tab(self, delta):
        tabs = self.active.tabs
        if tabs.get_n_pages() > 1:
            tabs.set_current_page((tabs.get_current_page() + delta) % tabs.get_n_pages())

    def toggle_thumbnails(self):
        self.state.settings['thumbnails'] = not self.state.settings['thumbnails']
        self.state.save()
        for pane in self.panes:
            pane.set_thumbnail_visibility(self.state.settings['thumbnails'])

    def set_folders_first(self, enabled):
        self.state.settings['folders_first'] = bool(enabled)
        self.state.save()
        for pane in self.panes:
            pane.folder_sorter.changed(Gtk.SorterChange.DIFFERENT)
        self.sync_toggle_actions()

    def toggle_folders_first(self):
        self.set_folders_first(not self.state.settings['folders_first'])

    def set_preview_enabled(self, enabled, persist=False):
        """Single source of truth for the preview sidebar state."""
        enabled = bool(enabled)
        self.preview_wanted = enabled
        self.preview.set_visible(enabled)
        self.preview_split.set_sidebar(self.preview if enabled else None)
        self.preview_split.set_show_sidebar(enabled)
        if persist:
            self.state.settings['preview'] = enabled
            if not enabled:
                self.state.settings['preview_first'] = False
            self.state.save()
        self.sync_toggle_actions()

    def preview_sidebar_changed(self, _split, _property):
        # A late geometry restore must never revive a preview disabled in the
        # saved preferences. The split browser pane remains independent.
        if not self.preview_wanted and self.preview_split.get_show_sidebar():
            GLib.idle_add(lambda: (self.set_preview_enabled(False), False)[1])

    def apply_preview_startup(self):
        self.set_preview_enabled(bool(self.state.settings.get('preview', False)))
        return False

    def toggle_preview(self):
        self.set_preview_enabled(not self.preview_split.get_show_sidebar(), persist=True)

    def toggle_hidden(self):
        self.hidden = not self.hidden
        for pane in self.panes:
            if pane.search_recursive_active:
                pane.search_changed()
            else:
                pane.filter.changed(Gtk.FilterChange.DIFFERENT)
        self.state.settings['hidden'] = self.hidden

    def setup_bookmark_monitor(self):
        """Follow the same GTK4 bookmark file edited by GNOME Files."""
        try:
            directory = bookmark_file().parent
            directory.mkdir(parents=True, exist_ok=True)
            self.bookmark_monitor = Gio.File.new_for_path(str(directory)).monitor_directory(
                Gio.FileMonitorFlags.WATCH_MOVES, None
            )
            self.bookmark_monitor.connect('changed', self.bookmarks_changed)
        except GLib.Error:
            self.bookmark_monitor = None

    def bookmarks_changed(self, _monitor, file, other, _event):
        if not any(candidate and candidate.get_basename() == 'bookmarks' for candidate in (file, other)):
            return
        if self.bookmark_refresh_timer:
            GLib.source_remove(self.bookmark_refresh_timer)
        self.bookmark_refresh_timer = GLib.timeout_add(120, self.reload_bookmarks)

    def reload_bookmarks(self):
        self.bookmark_refresh_timer = 0
        if not self.closed:
            self.fill_places()
        return False

    def fill_places(self):
        while self.places.get_first_child():
            self.places.remove(self.places.get_first_child())

        def new_section():
            listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=['navigation-sidebar'])
            listing.connect('row-activated', self.open_place)
            self.places.append(listing)
            return listing

        fixed_section = new_section()

        def add_row(listing, title, path, icon, bookmark_uri='', volume=None):
            row = Gtk.ListBoxRow()
            row.path = path
            row.bookmark_uri = bookmark_uri
            row.volume = volume
            row.file = (Gio.File.new_for_path(str(path)) if isinstance(path, Path) else Gio.File.new_for_uri(path)) if path is not None else None
            box = Gtk.Box(spacing=8)
            box.set_margin_top(4)
            box.set_margin_bottom(4)
            box.set_margin_start(8)
            box.set_margin_end(8)
            image = (
                Gtk.Image.new_from_gicon(icon)
                if isinstance(icon, Gio.Icon)
                else Gtk.Image.new_from_icon_name(icon)
            )
            box.append(image)
            box.append(Gtk.Label(label=title, xalign=0, ellipsize=3, hexpand=True))
            row.set_child(box)
            listing.append(row)
            if path == trash_service.URI:
                self.trash_image = image
                gesture = Gtk.GestureClick(button=3)
                gesture.connect('pressed', lambda _g, _n, x, y, r=row: self.trash_menu(r, x, y))
                row.add_controller(gesture)
            if isinstance(path, Path):
                target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)
                target.connect(
                    'drop',
                    lambda _t, files, x, y, d=path: (
                        self.sidebar_drop(files, d, _t),
                        True,
                    )[1],
                )
                row.add_controller(target)
            if path != trash_service.URI:
                gesture = Gtk.GestureClick(button=3)
                gesture.connect('pressed', lambda _g, _n, x, y, r=row: self.bookmark_menu(r, x, y))
                row.add_controller(gesture)
            if bookmark_uri:
                drag = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
                drag.connect('prepare', lambda *_args, uri=bookmark_uri: Gdk.ContentProvider.new_for_value(uri))
                row.add_controller(drag)
                reorder = Gtk.DropTarget.new(str, Gdk.DragAction.MOVE)
                reorder.connect('drop', lambda _target, value, _x, y, uri=bookmark_uri, widget=row:
                                reorder_bookmark(value, uri, y > widget.get_height() / 2))
                reorder.connect('enter', lambda *_args, widget=row:
                                (widget.set_state_flags(Gtk.StateFlags.DROP_ACTIVE, False), Gdk.DragAction.MOVE)[1])
                reorder.connect('leave', lambda *_args, widget=row: widget.unset_state_flags(Gtk.StateFlags.DROP_ACTIVE))
                row.add_controller(reorder)
            return row

        def separator():
            rule = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            rule.set_margin_start(8)
            rule.set_margin_end(8)
            rule.set_margin_top(5)
            rule.set_margin_bottom(5)
            self.places.append(rule)

        # These fixed entries precede the GTK 4 bookmark list shared with Files.
        add_row(fixed_section, tr('Dossier personnel'), Path.home(), 'user-home-symbolic')
        if self.get_settings().get_property('gtk-recent-files-enabled') and 'recent' in Gio.Vfs.get_default().get_supported_uri_schemes():
            add_row(fixed_section, tr('Récents'), 'recent:///', 'document-open-recent-symbolic')
        add_row(fixed_section, tr('Favoris'), 'starred:///', 'starred-symbolic')
        add_row(fixed_section, tr('Réseau'), 'network:///', 'network-workgroup-symbolic')
        add_row(fixed_section, tr('Corbeille'), trash_service.URI, 'user-trash-symbolic')
        separator()
        heading = Gtk.Label(label=tr('Signets'), xalign=0, css_classes=['dim-label', 'heading'])
        heading.set_margin_start(12)
        heading.set_margin_top(4)
        heading.set_margin_bottom(4)
        self.places.append(heading)
        bookmark_section = new_section()
        # The GTK 4 bookmark file is Nautilus's source of truth. Do not
        # synthesize XDG folders or deduplicate them against the fixed Home row:
        # Nautilus treats every saved bookmark as an ordinary removable entry.
        for uri, label in read_bookmarks():
            file = Gio.File.new_for_uri(uri)
            local_path = file.get_path()
            value = Path(local_path) if local_path else uri
            add_row(bookmark_section, label, value, 'folder-symbolic', uri)
        new_bookmark = Gtk.ListBoxRow(visible=False, activatable=False, selectable=False)
        new_bookmark.set_child(Gtk.Label(label=tr('Nouveau signet'), xalign=0, css_classes=['dim-label']))
        bookmark_section.append(new_bookmark)
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect('enter', lambda *_: (new_bookmark.set_visible(True), Gdk.DragAction.COPY)[1])
        target.connect('leave', lambda *_: new_bookmark.set_visible(False))
        target.connect(
            'drop',
            lambda _target, files, _x, _y: (
                new_bookmark.set_visible(False),
                self.bookmark_folders_dropped(files),
            )[1],
        )
        bookmark_section.add_controller(target)
        mounts = list(self.volume_monitor.get_mounts())
        device_entries = []
        for mount in mounts:
            root = mount.get_root()
            local = root.get_path()
            path = Path(local) if local else root.get_uri()
            device_entries.append(
                (mount.get_name(), path, mount.get_symbolic_icon() or mount.get_icon(), None, mount)
            )
        for volume in self.volume_monitor.get_volumes():
            if not volume.get_mount():
                device_entries.append(
                    (volume.get_name(), None, volume.get_symbolic_icon() or volume.get_icon(), volume, None)
                )
        if device_entries:
            separator()
            device_section = new_section()
        for title, path, icon, volume, mount in sorted(device_entries, key=lambda entry: entry[0].casefold()):
            row = add_row(device_section, title, path, icon, volume=volume)
            row.mount = mount
            # Activating an unmounted volume row mounts and opens it. Files
            # likewise keeps the row free of a separate Mount button.
            if mount and (mount.can_eject() or mount.can_unmount()):
                row.get_child().append(self.volume_eject_button(mount))
        self.refresh_trash_icon()
        self.setup_trash_monitor()

    def sidebar_drop(self, files, destination, target):
        sources = list(files.get_files())
        file = destination if isinstance(destination, Gio.File) else Gio.File.new_for_path(str(destination))
        action = self.active.negotiated_drop_action(target, sources, file)
        if action == Gdk.DragAction.LINK:
            self.create_file_links(sources, file)
        elif file.get_path() and all(source.get_path() for source in sources):
            self.prepare_paste([Path(source.get_path()) for source in sources], Path(file.get_path()),
                               action == Gdk.DragAction.MOVE)
        else:
            self.gio_transfer(sources, file, action == Gdk.DragAction.MOVE)

    def bookmark_menu(self, row, x, y):
        self.place_to_edit = row.bookmark_uri
        menu = Gio.Menu()
        actions = Gio.SimpleActionGroup()
        file = row.file
        entries = [
            ('tab', 'Ouvrir dans un nouvel onglet', lambda: self.new_tab(file)),
            ('window', 'Ouvrir dans une nouvelle fenêtre', lambda: self.new_window(file)),
            ('properties', 'Propriétés', lambda: self.show_place_properties(file)),
        ] if file is not None else []
        mount = getattr(row, 'mount', None)
        if mount is not None:
            if mount.can_eject():
                entries.append(('eject', 'Éjecter', lambda: self.unmount_volume(mount, True)))
            elif mount.can_unmount():
                entries.append(('unmount', 'Démonter', lambda: self.unmount_volume(mount, False)))
        if row.volume is not None:
            entries.append(('mount', 'Monter', lambda: self.mount_volume(row.volume)))
        if row.bookmark_uri:
            entries.extend([('rename', 'Renommer…', self.rename_place),
                            ('remove', 'Retirer des signets', self.remove_place)])
        for name, title, callback in entries:
            action = Gio.SimpleAction.new(name, None)
            action.connect('activate', lambda _a, _v, cb=callback: cb())
            actions.add_action(action)
            menu.append(tr(title), 'place.' + name)
        row.insert_action_group('place', actions)
        pop = Gtk.PopoverMenu.new_from_model(menu)
        pop.set_parent(row)
        rect = Gdk.Rectangle(x=int(x), y=int(y), width=1, height=1)
        pop.set_pointing_to(rect)
        pop.connect('closed', lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        pop.popup()

    def show_place_properties(self, file):
        if file.get_path():
            self.show_folder_properties(Path(file.get_path()))
        else:
            dialogs.gio_properties(self, [file])

    def rename_place(self):
        uri = getattr(self, 'place_to_edit', '')
        current = next((label for value, label in read_bookmarks() if value == uri), None)
        if current is None:
            return

        def done(label):
            if rename_bookmark(uri, label):
                self.fill_places()

        dialogs.text_input(self, tr('Renommer…'), current, done)

    def remove_place(self):
        uri = getattr(self, 'place_to_edit', '')
        if uri:
            write_bookmarks([(value, label) for value, label in read_bookmarks() if value != uri])
            self.fill_places()

    def bookmark_folders_dropped(self, files):
        folders = [Path(file.get_path()) for file in files.get_files() if file.get_path()]
        if add_bookmark_folders(folders):
            self.fill_places()
            return True
        return False

    def mount_volume(self, volume):
        operation = Gtk.MountOperation.new(self)

        def mounted(source, result):
            try:
                source.mount_finish(result)
                mount = source.get_mount()
                if mount:
                    self.open_gio_location(mount.get_root())
            except GLib.Error as error:
                self.notify(error.message)

        volume.mount(Gio.MountMountFlags.NONE, operation, None, mounted)

    def volume_eject_button(self, mount):
        """Eject or unmount button bound to this mount only.

        Built in its own call so that each button keeps its own mount and its
        own eject/unmount choice (a closure in the sidebar loop used to read
        the last volume's choice).
        """
        eject = mount.can_eject()
        control = Gtk.Button(
            icon_name='media-eject-symbolic',
            has_frame=False,
            valign=Gtk.Align.CENTER,
            tooltip_text=tr('Éjecter') if eject else tr('Démonter'),
        )
        control.connect('clicked', lambda _button: self.unmount_volume(mount, eject))
        return control

    def unmount_volume(self, mount, eject=False):
        operation = Gtk.MountOperation.new(self)

        def finished(source, result):
            try:
                (
                    source.eject_with_operation_finish(result)
                    if eject
                    else source.unmount_with_operation_finish(result)
                )
            except GLib.Error as error:
                self.notify(error.message)

        if eject:
            mount.eject_with_operation(Gio.MountUnmountFlags.NONE, operation, None, finished)
        else:
            mount.unmount_with_operation(Gio.MountUnmountFlags.NONE, operation, None, finished)

    def setup_trash_monitor(self):
        if self.trash_monitor or self.closed:
            return
        try:
            self.trash_monitor = trash_service.root().monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self.trash_monitor.connect('changed', self.trash_changed)
        except GLib.Error:
            self.trash_monitor = None

    def refresh_trash_icon(self):
        if not self.trash_image:
            return
        file = trash_service.root()

        def done(source, result):
            try:
                icon = source.query_info_finish(result).get_symbolic_icon()
                self.trash_image.set_from_gicon(icon)
                self.trash_has_items = 'full' in icon.to_string()
            except GLib.Error:
                self.trash_image.set_from_icon_name('user-trash')
                self.trash_has_items = False
            action = self.lookup_action('empty-trash')
            if action:
                action.set_enabled(self.trash_has_items)

        file.query_info_async(
            'standard::symbolic-icon', Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT, None, done
        )

    def trash_changed(self, *_):
        self.refresh_trash_icon()
        if not self.trash_reload_timer:
            self.trash_reload_timer = GLib.timeout_add(250, self.reload_trash_panes)

    def reload_trash_panes(self):
        self.trash_reload_timer = 0
        for pane in self.panes:
            if pane.is_trash:
                pane.reload_trash()
        return False

    def open_place(self, _list, row):
        if getattr(row, 'volume', None):
            self.mount_volume(row.volume)
            return
        if row.path == 'starred:///':
            self.open_starred(self.active)
            return
        if getattr(row, 'collection', None):
            self.active.collection = set(self.state.settings['collections'][row.collection])
            dialogs.collection_view(self, row.collection)
        elif row.path == trash_service.URI:
            self.active.open_trash()
        elif isinstance(row.path, Path):
            self.active.open(row.path)
        else:
            if row.path:
                self.open_gio_location(Gio.File.new_for_uri(row.path))

    def open_gio_location(self, file, pane=None):
        """Use local mounts in the pane and GIO for remote URI browsing."""
        pane = pane or self.active
        path = file.get_path()
        if path and Path(path).is_dir():
            pane.open(Path(path))
            return

        def handoff():
            pane.open_remote(file)

        def mounted(source, result):
            try:
                source.mount_enclosing_volume_finish(result)
            except GLib.Error:
                pass
            path = file.get_path()
            if path and Path(path).is_dir():
                pane.open(Path(path))
            else:
                handoff()

        try:
            file.mount_enclosing_volume(Gio.MountMountFlags.NONE, Gtk.MountOperation.new(self), None, mounted)
        except GLib.Error:
            handoff()

    def open_collection(self, name):
        paths = self.state.settings['collections'].get(name)
        if paths is None:
            return
        self.active.collection = set(paths)
        dialogs.collection_view(self, name)

    @staticmethod
    def query_starred_uris():
        gi.require_version('Tsparql', '3.0')
        from gi.repository import Tsparql

        connection = Tsparql.SparqlConnection.bus_new('org.freedesktop.LocalSearch3')
        query = '''SELECT DISTINCT ?url { ?file a nfo:FileDataObject ; nie:url ?url ; nao:hasTag <urn:gnome:nautilus:starred> . } ORDER BY ?url'''
        cursor = connection.query(query, None)
        values = []
        while cursor.next(None):
            value = cursor.get_string(0)
            if value:
                values.append(value)
        return values

    def open_starred(self, pane, remember=True):
        generation = pane.open_starred(remember)
        future = self.starred_executor.submit(self.query_starred_uris)

        def ready(result):
            try:
                uris = result.result()
            except Exception:
                GLib.idle_add(self.starred_unavailable, pane, generation)
                return
            GLib.idle_add(pane.show_starred_paths, generation, uris)

        future.add_done_callback(ready)

    def starred_unavailable(self, pane, generation):
        if pane.generation == generation and pane.is_starred:
            self.notify(tr('Le service de favoris de GNOME n’est pas disponible.'))
        return False

    def context_menu(self, view, x, y, empty=False):
        menu = self.build_context_menu(empty)
        pop = Gtk.PopoverMenu.new_from_model(menu)
        pop.set_parent(view)
        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = rect.height = 1
        pop.set_pointing_to(rect)
        pop.connect('closed', lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        pop.popup()

    def build_context_menu(self, empty=False):
        menu = Gio.Menu()
        items = self.active.selected()
        rows = [i.row for i in items]
        if self.active.remote_file is not None:
            return self.remote_menu(items, empty)

        def section(entries):
            sub = Gio.Menu()
            for title, action in entries:
                sub.append(tr(title), 'win.' + action)
            menu.append_section(None, sub)

        if self.active.is_trash:
            if not empty and items:
                section(
                    [
                        ('Ouvrir', 'open'),
                        ('Restaurer', 'restore-trash'),
                        ('Supprimer définitivement…', 'delete-trash'),
                    ]
                )
            else:
                section([('Vider la corbeille…', 'empty-trash'), ('Sélectionner tout', 'select-all')])
        elif not empty and items:
            section([('Ouvrir', 'open'), ('Ouvrir avec…', 'open-with')])
            if len(items) == 1 and rows[0].is_dir:
                tab_menu = Gio.Menu()
                entry = Gio.MenuItem.new(tr('Ouvrir dans un nouvel onglet'), None)
                entry.set_action_and_target_value(
                    'win.open-folder-tab', GLib.Variant('s', str(items[0].path))
                )
                duplicate_entry = Gio.MenuItem.new(
                    tr('Chercher les doublons dans ce dossier et ses sous-dossiers…'), None
                )
                duplicate_entry.set_action_and_target_value(
                    'win.find-duplicates-folder', GLib.Variant('s', str(items[0].path))
                )
                tab_menu.append_item(entry)
                menu.append_section(None, tab_menu)
                duplicate_menu = Gio.Menu()
                duplicate_menu.append_item(duplicate_entry)
                menu.append_section(None, duplicate_menu)
                organize = Gio.Menu()
                rename_content = Gio.MenuItem.new(tr('Renommer le contenu du dossier…'), None)
                rename_content.set_action_and_target_value(
                    'win.rename-folder-contents', GLib.Variant('s', str(items[0].path))
                )
                organize.append_item(rename_content)
                menu.append_submenu(tr('Organiser'), organize)
            # GNOME Files exposes one Rename action for both one item and a
            # selection. F2 already routes multiple items to the batch editor.
            rename_entries = [('Renommer', 'rename')]
            program = self.state.settings['external_renamer'].strip()
            if program:
                rename_entries.append((f"{tr('Renommer avec…')} ({Path(program).name})", 'external-rename'))
            section(rename_entries)
            if len(items) > 1:
                section([('Nouveau dossier contenant la sélection…', 'group')])
            section(
                [
                    ('Copier', 'copy'),
                    ('Couper', 'cut'),
                    ('Dupliquer', 'duplicate'),
                    ('Copier l’emplacement', 'copy-path'),
                ]
            )
            section([('Créer une archive…', 'archive-create')])
            if associated.find_associated([item.path for item in items]):
                section([('Sélectionner les fichiers associés', 'associated')])
            if len(items) == 2 and all(not item.row.is_dir for item in items):
                section([('Comparer les deux médias', 'compare-media')])
            if len(items) == 1 and archive_backend_supported(items[0].path):
                archive_menu = Gio.Menu()
                for title, action in [
                    ('Ouvrir l’archive', 'archive-open'),
                    ('Extraire ici', 'archive-extract-here'),
                    ('Extraire ici et déplacer l’archive dans la corbeille', 'archive-extract-trash'),
                    ('Extraire vers…', 'archive-extract-to'),
                ]:
                    archive_menu.append(tr(title), 'win.' + action)
                menu.append_submenu(tr('Archive'), archive_menu)
            if len(items) == 1 and rows[0].is_dir and self.can_paste():
                # Fix the destination when the menu opens, even if selection changes.
                paste_section = Gio.Menu()
                target = Gio.MenuItem.new(tr('Coller dans ce dossier'), None)
                target.set_action_and_target_value('win.paste-into', GLib.Variant('s', str(items[0].path)))
                paste_section.append_item(target)
                menu.append_section(None, paste_section)
            if all(r.is_dir for r in rows):
                section([('Ajouter aux signets', 'add-place')])
            if len(items) > 1:
                section([('Organiser en sous-dossiers…', 'organize')])
            if any(r.media_type in ('video', 'audio', 'image') or r.is_video for r in rows):
                sub = Gio.Menu()
                sub.append(tr('Métadonnées…'), 'win.metadata')
                sub.append(tr('Autres outils multimédias…'), 'win.media-tools')
                menu.append_submenu(tr('Outils multimédias'), sub)
            if any(r.error for r in rows):
                section([('Voir l’erreur…', 'error')])
            section([('Mettre à la corbeille…', 'trash'), ('Supprimer définitivement…', 'delete')])
            section([('Propriétés', 'properties')])
        else:
            if not self.active.is_starred and self.active.remote_file is None:
                creation = self.templates.menu
                menu.append_submenu(tr('Créer un nouveau'), creation)
            entries = []
            if self.can_paste() and not self.active.is_starred:
                entries.append(('Coller', 'paste'))
            entries += [('Sélectionner tout', 'select-all'), ('Éléments cachés', 'hidden')]
            section(entries)
            terminal = Gio.Menu()
            entry = Gio.MenuItem.new(tr('Ouvrir un terminal ici'), 'win.terminal')
            entry.set_icon(Gio.ThemedIcon.new('utilities-terminal-symbolic'))
            terminal.append_item(entry)
            menu.append_section(None, terminal)
            section([('Vue en liste', 'details'), ('Vue en grille', 'icons')])
        return menu

    def remote_menu(self, items, empty=False):
        menu = Gio.Menu()
        if items and not empty:
            menu.append(tr('Ouvrir'), 'win.open')
            menu.append(tr('Ouvrir avec…'), 'win.open-with')
            if len(items) == 1 and items[0].row.is_dir:
                entry = Gio.MenuItem.new(tr('Ouvrir dans un nouvel onglet'), None)
                entry.set_action_and_target_value('win.open-folder-tab', GLib.Variant('s', items[0].file.get_uri()))
                menu.append_item(entry)
            menu.append(tr('Copier'), 'win.copy')
            menu.append(tr('Couper'), 'win.cut')
            menu.append(tr('Copier l’emplacement'), 'win.copy-path')
            if len(items) == 1 and getattr(items[0].row, 'file_capabilities', {}).get('rename'):
                menu.append(tr('Renommer'), 'win.rename')
            if all(getattr(item.row, 'file_capabilities', {}).get('trash') for item in items):
                menu.append(tr('Mettre à la corbeille…'), 'win.trash')
            if all(getattr(item.row, 'file_capabilities', {}).get('delete') for item in items):
                menu.append(tr('Supprimer définitivement…'), 'win.delete')
            menu.append(tr('Propriétés'), 'win.properties')
        if empty and self.active.remote_can_write:
            menu.append(tr('Nouveau dossier…'), 'win.new-folder')
        if self.can_paste():
            destination = items[0].file if not empty and len(items) == 1 and items[0].row.is_dir else self.active.remote_file
            entry = Gio.MenuItem.new(tr('Coller dans ce dossier') if items and not empty and destination != self.active.remote_file else tr('Coller'), None)
            entry.set_action_and_target_value('win.paste-into-uri', GLib.Variant('s', destination.get_uri()))
            menu.append_item(entry)
        if empty:
            menu.append(tr('Sélectionner tout'), 'win.select-all')
            menu.append(tr('Éléments cachés'), 'win.hidden')
        return menu

    def open_items(self, items):
        if self.active.remote_file is not None:
            pane = self.active
            for item in items:
                if item.row.is_dir:
                    if len(items) == 1:
                        self.open_gio_location(item.file, pane)
                    else:
                        self.new_tab(item.file)
                else:
                    launcher = Gtk.FileLauncher.new(item.file)
                    launcher.launch(self, None, self.file_launched)
            return
        if self.active.is_trash:
            for item in items:
                self.open_trash_item(item)
            return
        if len(items) == 1 and items[0].row.is_dir:
            self.active.open(items[0].path)
            return
        if len(items) == 1 and archive_backend_supported(items[0].path):
            self.open_archive(items[0].path)
            return
        # GNOME Files asks GIO to open a file URI, letting the desktop's
        # default-application association handle MIME and portal policy.
        # This is also the single-file path used by double-click activation.
        if len(items) == 1:
            file = Gio.File.new_for_path(str(items[0].path))

            def opened(_source, result, path=str(items[0].path)):
                try:
                    Gio.AppInfo.launch_default_for_uri_finish(result)
                except GLib.Error as error:
                    self.notify(error.message)
                    return
                self.remember_recent_path(path)

            Gio.AppInfo.launch_default_for_uri_async(file.get_uri(), None, None, opened)
            return
        groups = {}
        for item in items:
            mime = getattr(item.row, 'content_type', None) or Gio.content_type_guess(str(item.path), None)[0]
            app = Gio.AppInfo.get_default_for_type(mime, False)
            if app:
                groups.setdefault(app.get_id() or app.get_executable(), (app, []))[1].append(
                    Gio.File.new_for_path(str(item.path))
                )
        for app, files in groups.values():
            try:
                app.launch(files, None)
                for file in files:
                    self.remember_recent_path(file.get_path())
            except GLib.Error as error:
                self.notify(error.message)

    def open_archive_selected(self):
        items = self.active.selected()
        if len(items) == 1:
            self.open_archive(items[0].path)

    def create_archive_selected(self):
        paths = file_moves.normalize_sources(self.paths())
        if not paths:
            return
        if self.paths_busy(paths):
            self.notify(tr('Un élément sélectionné est utilisé par une opération en cours.'))
            return
        if len({path.parent for path in paths}) != 1:
            self.notify(tr('Sélectionnez des éléments du même dossier.'))
            return

        def format_chosen(format):
            suffix = '.zip' if format == 'zip' else '.tar.gz'
            name = (
                paths[0].stem
                if len(paths) == 1 and paths[0].is_file()
                else paths[0].name
                if len(paths) == 1
                else tr('Sélection')
            ) + suffix
            chooser = Gtk.FileDialog(title=tr('Créer une archive…'), initial_name=name)

            def chosen(dialog, result):
                try:
                    file = dialog.save_finish(result)
                except GLib.Error:
                    return
                raw = file.get_path() if file else None
                if not raw:
                    self.notify(tr('Choisissez un fichier local.'))
                    return
                target = Path(raw)
                if not target.name.lower().endswith(suffix):
                    self.notify(tr('Le nom de l’archive doit se terminer par ') + suffix)
                    return

                def work(_path, cancelled, report):
                    created = archive_backend.create(
                        paths,
                        target,
                        format,
                        cancelled,
                        lambda done, total: report(done / total if total else None, target.name),
                    )
                    return {'target': str(created)}

                self.jobs.submit(tr('Créer une archive…'), paths, work, False)

            chooser.save(self, None, chosen)

        dialogs.choice(
            self,
            tr('Format de l’archive'),
            tr('Choisissez un format pris en charge localement.'),
            [(tr('ZIP'), 'zip'), (tr('TAR compressé (gzip)'), 'tar.gz')],
            format_chosen,
        )

    def open_archive(self, path):
        path = Path(path)
        self.jobs.submit(
            tr('Lire l’archive'),
            [path],
            lambda source, cancelled, report: {
                'archive_path': str(source),
                'archive_entries': archive_backend.list_entries(source),
            },
            False,
        )

    def extract_selected_archive(self, here=False, trash_after=False):
        items = self.active.selected()
        if len(items) == 1:
            self.extract_archive(items[0].path, here=here, trash_after=trash_after)

    def extract_archive(self, path, selected=None, here=False, trash_after=False):
        path = Path(path)
        selection = tuple(selected) if selected is not None else None
        if not path.is_file():
            self.notify(tr('Archive introuvable.'))
            return

        def begin(destination):
            destination = Path(destination)

            def work(source, cancelled, report):
                created = False
                if trash_after:
                    destination.mkdir(exist_ok=False)
                    created = True
                try:
                    targets = archive_backend.extract(
                        source,
                        destination,
                        selection,
                        cancelled,
                        lambda done, total: report(done / total if total else None, source.name),
                    )
                except Exception:
                    if created:
                        try:
                            destination.rmdir()
                        except OSError:
                            pass
                    raise
                removed = False
                if trash_after:
                    try:
                        Gio.File.new_for_path(str(source)).trash(None)
                        removed = True
                    except GLib.Error as error:
                        report(None, tr('Extraction terminée, archive conservée : ') + error.message)
                return {
                    'extracted': [str(target) for target in targets],
                    'archive_removed': str(source) if removed else '',
                }

            self.jobs.submit(tr('Extraire l’archive'), [path], work, False)

        if here:
            stem = path.name
            for suffix in ('.tar.gz', '.tar.bz2', '.tar.xz', '.tgz', '.zip', '.cbz', '.tar'):
                if stem.lower().endswith(suffix):
                    stem = stem[: -len(suffix)]
                    break
            begin(path.parent / stem if trash_after else path.parent)
            return
        chooser = Gtk.FileDialog(title=tr('Choisir le dossier d’extraction'))

        def chosen(dialog, result):
            try:
                target = dialog.select_folder_finish(result)
                if target and target.get_path():
                    begin(target.get_path())
                else:
                    self.notify(tr('Choisissez un dossier local accessible.'))
            except GLib.Error:
                pass

        chooser.select_folder(self, None, chosen)

    def remember_recent_path(self, path):
        if not self.state.settings['recent'] or not path:
            return
        if Path(path).suffix.lower() in media.AUDIO_EXT | media.IMAGE_EXT | metadata.EXTENSIONS:
            self.state.settings['recent_paths'] = list(
                dict.fromkeys([path] + self.state.settings['recent_paths'])
            )[:15]
            self.state.save()
            self.menu_button.set_menu_model(self.main_menu())

    def open_recent(self, path):
        try:
            Gio.AppInfo.launch_default_for_uri(Path(path).as_uri(), None)
        except (GLib.Error, OSError) as error:
            self.notify(str(error))

    def trash_menu(self, row, x, y):
        menu = Gio.Menu()
        menu.append(tr('Vider la corbeille…'), 'win.empty-trash')
        pop = Gtk.PopoverMenu.new_from_model(menu)
        pop.set_parent(row)
        pop.connect('closed', lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        pop.popup()

    def empty_trash(self):
        from .core.persistence import stream_command

        def confirmed():
            def work(path, cancelled, report):
                stream_command(['gio', 'trash', '--empty'], lambda _: None, cancelled)
                return {'trash_refresh': True}

            self.jobs.submit(tr('Vider la corbeille'), [Path.home()], work, False)

        dialogs.confirm(
            self,
            tr('Vider la corbeille ?'),
            tr('Tous les éléments de la corbeille seront supprimés définitivement.'),
            confirmed,
        )

    def open_trash_item(self, item):
        try:
            trash_service.open_item(item.row)
        except GLib.Error as error:
            self.notify(error.message)

    def restore_trash(self):
        items = self.active.selected()
        if not items:
            return
        mapping = {item.path: item.row for item in items}

        def confirmed():
            def work(path, cancelled, report):
                if cancelled():
                    raise InterruptedError()
                target = trash_service.restore(mapping[path])
                return {'target': str(target), 'trash_refresh': True}

            self.jobs.submit(tr('Restaurer'), list(mapping), work, False)

        dialogs.confirm(
            self,
            tr('Restaurer les éléments ?'),
            f'{len(items)} {tr("élément(s)")}\n' + tr('Chaque élément retrouvera son emplacement d’origine.'),
            confirmed,
        )

    def delete_trash(self):
        items = self.active.selected()
        if not items:
            return
        mapping = {item.path: item.row for item in items}

        def confirmed():
            def work(path, cancelled, report):
                if cancelled():
                    raise InterruptedError()
                trash_service.delete(mapping[path])
                return {'trash_refresh': True}

            self.jobs.submit(tr('Suppression définitive'), list(mapping), work, False)

        dialogs.confirm(
            self,
            tr('Supprimer définitivement ?'),
            f'{len(items)} {tr("élément(s)")}\n' + tr('Cette action est irréversible.'),
            confirmed,
        )

    def open_folder_with(self):
        folder = self.active.folder
        content_type = Gio.content_type_from_mime_type('inode/directory')
        self.choose_application([Gio.File.new_for_path(str(folder))], content_type)

    def copy_current_location(self):
        if self.active and not self.active.is_trash:
            self.get_clipboard().set(
                self.active.remote_file.get_uri()
                if self.active.remote_file is not None
                else str(self.active.folder)
            )

    def folder_properties(self):
        try:
            dialogs.properties(self, [self.active.folder])
        except (GLib.Error, OSError) as error:
            self.notify(str(error))

    def open_with(self):
        items = list(self.active.selected())
        if not items:
            return
        content_types = {getattr(item.row, 'content_type', None) for item in items}
        content_type = next(iter(content_types)) if len(content_types) == 1 else None
        self.choose_application([item.file for item in items], content_type)

    def file_launched(self, launcher, result):
        try:
            launcher.launch_finish(result)
        except GLib.Error as error:
            if not error.matches(Gtk.dialog_error_quark(), Gtk.DialogError.DISMISSED):
                self.notify(error.message)

    def choose_application(self, files, content_type):
        # GTK owns the single-file application chooser and portal handoff.
        # Keep the multi-file dialog: Gtk.FileLauncher launches one file only.
        if len(files) == 1 and hasattr(Gtk, 'FileLauncher'):
            launcher = Gtk.FileLauncher.new(files[0])
            if hasattr(launcher, 'set_always_ask'):
                launcher.set_always_ask(True)

                def finished(source, result):
                    try:
                        source.launch_finish(result)
                    except GLib.Error as error:
                        self.notify(error.message)

                launcher.launch(self, None, finished)
                return
        applications = Gio.AppInfo.get_all_for_type(content_type) if content_type else [app for app in Gio.AppInfo.get_all() if app.should_show() and (app.supports_files() or app.supports_uris())]
        if not applications:
            self.notify(tr('Aucune application disponible pour ce type de fichier.'))
            return
        default = Gio.AppInfo.get_default_for_type(content_type, False) if content_type else None
        applications.sort(
            key=lambda app: (
                app.get_id() != default.get_id() if default else True,
                app.get_display_name().casefold(),
            )
        )
        dialog = Adw.Window(
            transient_for=self, modal=True, title=tr('Ouvrir avec…'), default_width=450, default_height=480
        )
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(Adw.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for method in ('set_margin_top', 'set_margin_bottom', 'set_margin_start', 'set_margin_end'):
            getattr(box, method)(12)
        toolbar.set_content(box)
        dialog.set_content(toolbar)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        box.append(scroll)
        listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE, css_classes=['boxed-list'])
        scroll.set_child(listing)
        for app in applications:
            row = Gtk.ListBoxRow()
            row.app_info = app
            line = Gtk.Box(spacing=12)
            for method in ('set_margin_top', 'set_margin_bottom', 'set_margin_start', 'set_margin_end'):
                getattr(line, method)(8)
            icon = app.get_icon()
            line.append(
                Gtk.Image.new_from_gicon(icon)
                if icon
                else Gtk.Image.new_from_icon_name('application-x-executable-symbolic')
            )
            line.append(Gtk.Label(label=app.get_display_name(), xalign=0, hexpand=True))
            row.set_child(line)
            listing.append(row)
        listing.select_row(listing.get_row_at_index(0))

        search = Gtk.SearchEntry(placeholder_text=tr('Rechercher une application'))
        box.prepend(search)
        listing.set_filter_func(lambda row: search.get_text().casefold() in row.app_info.get_display_name().casefold())
        search.connect('search-changed', lambda *_: listing.invalidate_filter())

        def launch(*_):
            selected = listing.get_selected_row()
            if not selected:
                return
            try:
                selected.app_info.launch(files, None)
            except GLib.Error as error:
                self.notify(error.message)
                return
            dialog.close()

        listing.connect('row-activated', launch)
        button = Gtk.Button(label=tr('Ouvrir'), css_classes=['suggested-action'], halign=Gtk.Align.END)
        button.connect('clicked', launch)
        box.append(button)
        dialog.present()

    def invert_selection(self):
        selection = self.active.selection
        for index in range(selection.get_n_items()):
            if selection.is_selected(index):
                selection.unselect_item(index)
            else:
                selection.select_item(index, False)

    def open_selected_folders(self, windows=False):
        for item in self.active.selected():
            if item.row.is_dir:
                if windows:
                    self.new_window(item.file)
                else:
                    self.new_tab(item.file)

    def create_file_links(self, files, destination):
        if not destination.get_path() or any(not file.get_path() for file in files):
            self.notify(tr('Les liens symboliques nécessitent des fichiers locaux.'))
            return
        def work(_path, cancelled, report):
            from .core.undo import LinkRecord
            from .core.extensions import fingerprint
            changed, records = [], []
            warning = ''
            for file in files:
                if cancelled():
                    break
                name, count = file.get_basename(), 0
                try:
                    while True:
                        label = name if count == 0 else trf('Lien vers \x1f0\x1f', name)
                        if count > 1:
                            label += ' (' + str(count) + ')'
                        target = destination.get_child(label)
                        try:
                            target.make_symbolic_link(file.get_path(), None)
                            break
                        except GLib.Error as error:
                            if not error.matches(Gio.io_error_quark(), Gio.IOErrorEnum.EXISTS):
                                raise
                            count += 1
                        if cancelled():
                            raise InterruptedError()
                    path = Path(target.get_path())
                    changed.append(str(path))
                    records.append(LinkRecord(path, file.get_path(), fingerprint(path)))
                except (GLib.Error, OSError, InterruptedError) as error:
                    warning = str(error) or tr('Opération interrompue.')
                    break
            return {'gio_changed': changed, 'undo_entries': records, 'warning': warning}
        self.jobs.submit(tr('Créer des liens'), [destination.get_path()], work, False)

    def paths(self):
        return [] if self.active.is_trash else [i.path for i in self.active.selected()]

    def copy_path(self):
        if self.active.remote_file is not None:
            self.get_clipboard().set('\n'.join(file.get_uri() for file in self.active.remote_selected()))
            return
        self.get_clipboard().set('\n'.join(map(str, self.paths())))

    def select_associated(self):
        matches = associated.find_associated(self.paths())
        if not matches:
            self.notify(tr('Aucun fichier associé trouvé.'))
            return
        self.active.select_paths(matches)
        self.notify(f'{len(matches)} {tr("fichier(s) associé(s) ajouté(s) à la sélection.")}')

    def compare_media(self):
        dialogs.compare_media(self, [item.row for item in self.active.selected()])

    def diagnostics(self):
        from .core.diagnostics import diagnostic_report

        dialogs.message(self, tr('Diagnostic de Mirivue'), diagnostic_report())

    def can_paste(self):
        formats = self.get_clipboard().get_formats()
        return any(
            formats.contain_mime_type(mime) for mime in (GNOME_MIME, LEGACY_MIME, 'text/uri-list')
        ) or formats.contain_gtype(Gdk.FileList.__gtype__)

    def copy(self, cut):
        if self.active.remote_file is not None:
            files = self.active.remote_selected()
            if not files:
                return
            provider = Gdk.ContentProvider.new_union([
                Gdk.ContentProvider.new_for_bytes(GNOME_MIME, GLib.Bytes.new(encode_uris([f.get_uri() for f in files], cut))),
                Gdk.ContentProvider.new_for_value(Gdk.FileList.new_from_list(files)),
            ])
            self.remote_clipboard = (files, cut, provider)
            self.get_clipboard().set_content(provider)
            return
        paths = self.paths()
        if not paths:
            return
        self.set_file_clipboard(paths, cut)

    def resolve_transfer_conflict(self, source, target, replace, merge, cancelled):
        done = threading.Event()
        answer = ['cancel']
        opened = []
        def present():
            if self.closed or cancelled():
                done.set()
                return False
            dialog = Adw.AlertDialog(heading=tr('Conflit de noms'),
                                    body=source.get_parse_name() + '\n→ ' + target.get_parse_name())
            dialog.add_response('cancel', tr('Annuler'))
            dialog.add_response('skip', tr('Ignorer'))
            dialog.add_response('rename', tr('Renommer'))
            if merge:
                dialog.add_response('merge', tr('Fusionner les dossiers'))
            elif replace:
                dialog.add_response('replace', tr('Remplacer'))
                dialog.set_response_appearance('replace', Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_close_response('cancel')
            def response(_dialog, value):
                answer[0] = value
                done.set()
            dialog.connect('response', response)
            opened.append(dialog)
            dialog.present(self)
            return False
        GLib.idle_add(present)
        while not done.wait(.1):
            if cancelled() or self.closed:
                for dialog in opened:
                    GLib.idle_add(lambda d=dialog: (d.close(), False)[1])
                return 'cancel'
        return answer[0]

    def gio_transfer(self, files, destination, move=False, confirmed_merge=False, clipboard_cut=False):
        if not files:
            return
        def work(_path, cancelled, report):
            records, changed, warnings = [], [], []
            complete_history = True
            for file in files:
                if cancelled():
                    break
                target = destination.get_child(file.get_basename())
                report(None, file.get_parse_name())
                entries, updates, errors, available = directory_merge.merge(
                    file, target, not move, cancelled,
                    lambda source, target, replace, merge: self.resolve_transfer_conflict(
                        source, target, replace, merge, cancelled),
                    self.undo_manager, confirmed=confirmed_merge)
                records.extend(entries)
                changed.extend(updates)
                warnings.extend(errors)
                complete_history = complete_history and available
                if cancelled():
                    break
            return {'gio_changed': [Gio.File.new_for_uri(uri).get_path() for uri in changed
                                    if Gio.File.new_for_uri(uri).get_path()],
                    'gio_remote_refresh': [destination.get_uri()] + [file.get_parent().get_uri() for file in files
                                                                    if file.get_parent()],
                    'gio_move': move and not warnings and all(not file.query_exists(None) for file in files),
                    'undo_entries': records if complete_history else [],
                    'warning': '\n'.join(warnings)}
        local = [Path(file.get_path()) for file in files if file.get_path()]
        job = self.jobs.submit(tr('Déplacement' if move else 'Copie'), local[:1] or [self.active.folder], work, False)
        job.locked_paths = local + ([Path(destination.get_path())] if destination.get_path() else [])
        if clipboard_cut and local:
            self.pending_cut_jobs.append((job, local, self.clipboard_provider))
        return job

    def paste_remote(self, pane):
        if pane.remote_file is not None:
            self.paste_gio(pane.remote_file)

    def paste_gio(self, destination):
        if destination.get_uri().rstrip('/') == 'network:':
            self.notify(tr('Connectez-vous d’abord à un emplacement réseau.'))
            return
        clipboard = self.get_clipboard()

        def values(source, result):
            try:
                files = list(source.read_value_finish(result).get_files())
                cut = bool(getattr(self, 'remote_clipboard', None) and source.get_content() is self.remote_clipboard[2] and self.remote_clipboard[1])
                if files:
                    self.gio_transfer(files, destination, cut)
            except GLib.Error as error:
                self.notify(error.message)

        def native(source, result):
            try:
                stream, _mime = source.read_finish(result)
                data = stream.read_bytes(1024 * 1024 + 1, None).get_data()
                stream.close(None)
                uris, cut = decode_uris(data)
                if uris:
                    self.gio_transfer([Gio.File.new_for_uri(uri) for uri in uris], destination, cut)
            except (GLib.Error, ValueError, UnicodeError):
                source.read_value_async(Gdk.FileList, GLib.PRIORITY_DEFAULT, None, values)

        formats = clipboard.get_formats()
        if any(formats.contain_mime_type(mime) for mime in (GNOME_MIME, LEGACY_MIME)):
            clipboard.read_async([GNOME_MIME, LEGACY_MIME], GLib.PRIORITY_DEFAULT, None, native)
        else:
            clipboard.read_value_async(Gdk.FileList, GLib.PRIORITY_DEFAULT, None, values)

    def set_file_clipboard(self, paths, cut):
        self.remote_clipboard = None
        paths = list(paths)
        if not paths:
            self.get_clipboard().set_content(None)
            self.clipboard_paths = []
            self.clipboard_cut = False
            self.clipboard_provider = None
            return
        files = Gdk.FileList.new_from_list([Gio.File.new_for_path(str(path)) for path in paths])
        provider = Gdk.ContentProvider.new_union(
            [
                Gdk.ContentProvider.new_for_bytes(GNOME_MIME, GLib.Bytes.new(encode_files(paths, cut))),
                Gdk.ContentProvider.new_for_value(files),
            ]
        )
        self.clipboard_paths = paths
        self.clipboard_cut = cut
        self.clipboard_provider = provider
        self.get_clipboard().set_content(provider)

    def paste(self, folder=None):
        if folder is None and self.active.remote_file is not None:
            self.paste_remote(self.active)
            return
        folder = Path(folder) if folder is not None else self.active.folder
        if (
            folder is not None
            and getattr(self, 'remote_clipboard', None)
            and self.get_clipboard().get_content() is self.remote_clipboard[2]
        ):
            files, move, _provider = self.remote_clipboard
            self.gio_transfer(files, Gio.File.new_for_path(str(folder)), move)
            return
        if not folder.is_dir():
            self.notify(tr('Dossier de destination inaccessible.'))
            return
        clipboard = self.get_clipboard()
        formats = clipboard.get_formats()

        def got_files(source, result):
            try:
                files = source.read_value_finish(result)
                paths = [Path(f.get_path()) for f in files.get_files() if f.get_path()]
                cut = (
                    self.clipboard_cut
                    and source.get_content() == self.clipboard_provider
                    and paths == self.clipboard_paths
                )
                if paths:
                    self.prepare_paste(paths, folder, cut)
                else:
                    self.notify(tr('Aucun fichier local à coller.'))
            except GLib.Error as error:
                self.notify(error.message)

        if any(formats.contain_mime_type(mime) for mime in (GNOME_MIME, LEGACY_MIME)):

            def got_native(source, result):
                try:
                    stream, _mime = source.read_finish(result)
                    data = stream.read_bytes(1024 * 1024 + 1, None).get_data()
                    stream.close(None)
                    uris, cut = decode_uris(data)
                    files = [Gio.File.new_for_uri(uri) for uri in uris]
                    if any(not file.is_native() for file in files):
                        self.gio_transfer(files, Gio.File.new_for_path(str(folder)), cut)
                        return
                    paths, cut = decode_files(data)
                    if paths:
                        self.prepare_paste(paths, folder, cut)
                    else:
                        self.notify(tr('Aucun fichier local à coller.'))
                except (GLib.Error, ValueError):
                    source.read_value_async(Gdk.FileList, GLib.PRIORITY_DEFAULT, None, got_files)

            clipboard.read_async([GNOME_MIME, LEGACY_MIME], GLib.PRIORITY_DEFAULT, None, got_native)
            return
        clipboard.read_value_async(Gdk.FileList, GLib.PRIORITY_DEFAULT, None, got_files)

    def prepare_paste(self, paths, folder, cut):
        paths = file_moves.normalize_sources(paths)
        conflicts = [path for path in paths if file_moves.exists(folder / path.name)]
        if not conflicts:
            self.transfer(paths, folder, copy=not cut, clipboard_cut=cut)
            return

        def chosen(policy):
            if policy == 'merge':
                self.gio_transfer([Gio.File.new_for_path(str(path)) for path in paths],
                                  Gio.File.new_for_path(str(folder)), cut, True, cut)
            elif policy != 'cancel':
                self.transfer(paths, folder, copy=not cut, conflict=policy, clipboard_cut=cut)

        choices = [(tr('Renommer les nouveaux éléments'), 'rename'), (tr('Ignorer les conflits'), 'skip')]
        if any(path.is_dir() and (folder / path.name).is_dir() for path in conflicts):
            choices.append((tr('Fusionner les dossiers…'), 'merge'))
        if all(not path.is_dir() and not (folder / path.name).is_dir() for path in conflicts):
            choices.append((tr('Remplacer les fichiers existants'), 'replace'))
        dialogs.choice(
            self,
            tr('Conflits de noms'),
            tr('Des éléments portent déjà ce nom dans le dossier de destination.'),
            choices,
            chosen,
        )

    def choose_transfer(self, paths, folder):
        dialogs.choice(
            self,
            tr('Copier ou déplacer ?'),
            str(folder),
            [(tr('Copier'), 'copy'), (tr('Déplacer'), 'move')],
            lambda value: self.transfer(paths, folder, value == 'copy'),
        )

    def transfer(self, paths, folder, copy=False, conflict='skip', clipboard_cut=False):
        paths = file_moves.normalize_sources(paths)
        folder = Path(folder)

        def work(path, cancelled, report):
            target = folder / path.name
            if file_moves.exists(target):
                if conflict == 'skip':
                    raise FileExistsError(tr('Un élément porte déjà ce nom dans la destination.'))
                if conflict == 'rename':
                    target = unique_destination(target)
                elif conflict == 'replace':
                    if path.is_dir() or target.is_dir():
                        raise IsADirectoryError(tr('Les dossiers existants ne sont pas remplacés.'))
                    return self.replace_file(path, target, copy, cancelled, report)
            warning = file_moves.move_one(
                path,
                target,
                cancelled,
                lambda text: report(None, text),
                copy_only=copy,
                bytes_progress=lambda done, total: report(done / total if total else None, path.name),
            )
            self.state.relocate(path, target, copy or bool(warning))
            record = None
            if not warning:
                try:
                    record = self.undo_manager.prepare_record(path, target, copy)
                except (OSError, ValueError):
                    pass
            return {'source': str(path), 'target': str(target), 'copy': copy,
                    'warning': warning, 'undo_entry': record}

        job = self.jobs.submit(tr('Copie' if copy else 'Déplacement'), paths, work, False)
        if clipboard_cut:
            self.pending_cut_jobs.append((job, list(paths), self.clipboard_provider))
        return job

    def replace_file(self, path, target, copy, cancelled, report):
        warning = replace_existing_file(
            target,
            lambda: file_moves.move_one(
                path,
                target,
                cancelled,
                lambda text: report(None, text),
                copy_only=copy,
                bytes_progress=lambda done, total: report(done / total if total else None, path.name),
            ),
        )
        self.state.relocate(path, target, copy or bool(warning))
        return {'source': str(path), 'target': str(target), 'copy': copy, 'warning': warning}

    def reverse_file_operation(self, redo):
        stack = self.undo_manager.redo_stack if redo else self.undo_manager.undo_stack
        if not stack:
            self.notify(
                tr(
                    'Aucune opération de fichier à rétablir.'
                    if redo
                    else 'Aucune opération de fichier à annuler.'
                )
            )
            return
        item = stack[-1]
        affected = record_paths(item)
        if self.paths_busy(affected):
            self.notify(tr('Une opération utilise encore ce fichier.'))
            return

        def work(_path, cancelled, report):
            if cancelled():
                raise InterruptedError()
            operation = self.undo_manager.redo() if redo else self.undo_manager.undo()
            for child in individual_records(operation):
                if isinstance(child, RenameRecord):
                    for source, target in child.pairs:
                        self.state.relocate(source if redo else target, target if redo else source)
                elif not hasattr(child, 'target'):
                    pass
                elif not child.copy:
                    self.state.relocate(child.source if redo else child.target,
                                        child.target if redo else child.source)
                elif redo:
                    self.state.relocate(child.source, child.target, True)
            return {'reversed_paths': [str(path) for path in record_paths(operation)], 'trash_refresh': True}

        self.jobs.submit(tr('Rétablir' if redo else 'Annuler'), affected[:1], work, False)

    def duplicate(self):
        paths = self.paths()

        def work(path, cancelled, report):
            n = 1
            target = path.with_name(path.stem + ' — ' + tr('Copie') + path.suffix)
            while target.exists():
                n += 1
                target = path.with_name(path.stem + f' — {tr("Copie")} {n}' + path.suffix)
            file_moves.move_one(
                path,
                target,
                cancelled,
                copy_only=True,
                bytes_progress=lambda d, t: report(d / t if t else None, path.name),
            )
            self.state.relocate(path, target, True)
            return {'target': str(target)}

        self.jobs.submit(tr('Dupliquer'), paths, work, False)

    def paths_busy(self, paths):
        requested = [Path(path).absolute() for path in paths]
        for job in self.jobs.jobs:
            if job.state not in ('queued', 'running'):
                continue
            for current in map(lambda p: Path(p).absolute(), getattr(job, 'locked_paths', job.paths)):
                for requested_path in requested:
                    if (
                        current == requested_path
                        or current in requested_path.parents
                        or requested_path in current.parents
                    ):
                        return True
        return False

    def rename(self):
        if getattr(self.active, 'remote_file', None) is not None:
            selected = self.active.selected()
            if len(selected) == 1 and getattr(selected[0].row, 'file_capabilities', {}).get('rename'):
                self.active.start_inline_rename(selected[0])
            return
        items = self.active.selected()
        if len(items) != 1:
            return self.bulk_rename()
        if self.paths_busy([items[0].path]):
            self.notify(tr('Cet élément est utilisé par une opération en cours.'))
            return
        self.active.start_inline_rename(items[0])

    def finish_inline_rename(self, item, name):
        if getattr(item.row, 'gio_file', None) is not None:
            self.rename_gio_item(item, name)
            return
        source = item.path
        name = name.strip()
        if not name or name == source.name:
            return
        if self.paths_busy([source]):
            self.notify(tr('Cet élément est utilisé par une opération en cours.'))
            item.revision += 1
            return
        plans = renaming.prepare_names([item.row], [name])
        if not plans or plans[0].issue:
            self.notify(plans[0].issue if plans else tr('Nom inchangé.'))
            item.revision += 1
            return
        plan = plans[0]

        def work(path, cancelled, report):
            if cancelled():
                raise InterruptedError()
            renamed, errors = extensions.apply_renames([plan])
            if errors:
                raise ValueError(str(errors))
            self.state.relocate(path, plan.destination)
            return {
                'source': str(path),
                'target': str(plan.destination),
                'renamed': [(str(source), str(target)) for source, target in renamed.items()],
            }

        self.jobs.submit(tr('Renommer'), [source], work, False)

    def rename_gio_item(self, item, name):
        file = item.file
        if name == file.get_basename():
            return
        if not file_moves.valid_name(name):
            self.notify(file_moves.invalid_name_reason(name))
            return
        pane = next((pane for pane in self.panes if pane.items.get(file.get_uri()) is item), None)
        generation = pane.generation if pane else None

        def finished(source, result):
            try:
                source.set_display_name_finish(result)
            except GLib.Error as error:
                self.notify(error.message)
            if pane is not None and not pane.closed and pane.generation == generation:
                pane.open_remote(file.get_parent(), False, keep_search=True)

        file.set_display_name_async(name, GLib.PRIORITY_DEFAULT, None, finished)

    def new_gio_folder(self):
        pane = self.active
        folder = pane.remote_file
        generation = pane.generation
        if folder is None or not pane.remote_can_write:
            return

        def done(name):
            if not file_moves.valid_name(name):
                self.notify(file_moves.invalid_name_reason(name))
                return
            target = folder.get_child(name)

            def finished(source, result):
                try:
                    source.make_directory_finish(result)
                except GLib.Error as error:
                    self.notify(error.message)
                    return
                if not pane.closed and pane.generation == generation:
                    pane.open_remote(folder, False, keep_search=True)

            target.make_directory_async(GLib.PRIORITY_DEFAULT, None, finished)

        dialogs.text_input(self, tr('Nouveau dossier'), tr('Dossier sans titre'), done)

    def remove_gio_items(self, permanent):
        pane = self.active
        selected = pane.selected()
        capability = 'delete' if permanent else 'trash'
        if not selected or not all(getattr(item.row, 'file_capabilities', {}).get(capability)
                                   for item in selected):
            return
        files = [item.file for item in selected]
        folder_uri = pane.remote_file.get_uri()

        def accepted():
            def work(_path, cancelled, report):
                for index, file in enumerate(files):
                    if cancelled():
                        raise InterruptedError()
                    # A backend refusing trash never triggers a permanent delete.
                    gio_backend.remove(file, permanent, cancelled)
                    report((index + 1) / len(files), file.get_basename())
                return {'gio_remote_refresh': [folder_uri]}

            self.jobs.submit(tr('Supprimer définitivement' if permanent else 'Mettre à la corbeille'),
                             [pane.folder], work, False)

        dialogs.confirm(self, tr('Supprimer définitivement ces éléments ?' if permanent else
                                 'Mettre ces éléments à la corbeille ?'),
                        str(len(files)) + ' ' + tr('élément(s)'), accepted)

    def bulk_rename(self):
        paths = self.paths()
        if self.paths_busy(paths):
            self.notify(tr('Un élément sélectionné est utilisé par une opération en cours.'))
            return
        return dialogs.bulk_rename(self)

    def rename_folder_contents(self, folder):
        folder = Path(folder)
        if not folder.is_dir() or folder.is_symlink():
            return
        if self.paths_busy([folder]):
            self.notify(tr('Ce dossier est utilisé par une opération en cours.'))
            return
        try:
            rows = renaming.folder_rename_rows(folder)
        except (OSError, ValueError) as error:
            self.notify(str(error))
            return
        if not rows:
            self.notify(tr('Ce dossier ne contient aucun élément à renommer.'))
            return
        if self.state.settings['external_renamer'].strip():
            return self.external_rename(rows)
        return dialogs.bulk_rename(self, rows, folder)

    def external_rename(self, rows_override=None):
        items = self.active.selected() if rows_override is None else []
        rows = list(rows_override) if rows_override is not None else [item.row for item in items]
        paths = [row.path for row in rows]
        if not paths:
            return
        if self.paths_busy(paths):
            self.notify(tr('Un élément sélectionné est utilisé par une opération en cours.'))
            return
        try:
            executable, args = renaming.external_command(
                self.state.settings['external_renamer'], self.state.settings['external_renamer_args'], paths
            )
            subprocess.Popen([executable, *args])
        except (ValueError, OSError) as error:
            self.notify(str(error))
            return
        pending = list(rows)
        attempts = [0]

        def follow():
            attempts[0] += 1
            mapping = renaming.find_external_renames(pending)
            if mapping:
                for old, new in mapping.items():
                    self.state.relocate(old, new)
                    self.touch(old)
                    self.touch(new)
                    for row in list(pending):
                        if row.path == old:
                            pending.remove(row)
                self.notify(tr('Les renommages externes ont été détectés.'))
            return bool(pending) and attempts[0] < 240 and not self.closed

        GLib.timeout_add(500, follow)

    def new_folder(self):
        if getattr(self.active, 'remote_file', None) is not None:
            self.new_gio_folder()
            return
        if self.active.is_trash or self.active.is_starred or self.active.remote_file is not None:
            return
        folder = self.active.folder

        def done(name):
            if not file_moves.valid_name(name):
                self.notify(file_moves.invalid_name_reason(name))
                return
            try:
                target = folder / name
                target.mkdir()
                self.undo_manager.record_new_folder(target)
            except OSError as e:
                self.notify(str(e))

        dialogs.text_input(self, tr('Nouveau dossier'), file_moves.untitled_folder_name(folder), done)

    def new_from_template(self, file):
        if self.active.remote_file is not None or self.active.is_trash or self.active.is_starred:
            return
        destination = self.active.folder
        target = destination / file_moves.available_name(destination, file.get_basename())
        def work(_path, cancelled, report):
            if cancelled():
                raise InterruptedError()
            # Native GIO copy refuses an occupied name; template stays intact.
            gio_backend.transfer([file], Gio.File.new_for_path(str(destination)), cancelled=cancelled,
                                 names={file.get_uri(): target.name})
            record = self.undo_manager.prepare_record(file.get_path(), target, True, companions=False)
            return {'target': str(target), 'undo_entry': record}
        self.jobs.submit(tr('Créer un document'), [destination], work, False)

    def new_text_file(self):
        if self.active.is_trash or self.active.is_starred or self.active.remote_file is not None:
            return
        from .core.new_document import create_text_file

        def done(name):
            try:
                target = create_text_file(self.active.folder, name)
            except (OSError, ValueError) as error:
                self.notify(str(error))
                return
            self.touch(target)

        dialogs.text_input(self, tr('Nouveau fichier texte'), tr('Nouveau fichier texte.txt'), done)

    def group_folder(self):
        paths = self.paths()
        folder = self.active.folder
        if len(paths) < 2:
            return
        if self.paths_busy(paths):
            self.notify(tr('Un élément sélectionné est utilisé par une opération en cours.'))
            return

        def done(name):
            if not file_moves.valid_name(name):
                self.notify(file_moves.invalid_name_reason(name))
                return
            try:
                target = folder / name
                target.mkdir()
            except OSError as e:
                self.notify(str(e))
                return
            self.transfer(paths, target)

        dialogs.text_input(
            self,
            tr('Nouveau dossier contenant la sélection…'),
            file_moves.available_name(folder, file_moves.suggest_folder(paths)),
            done,
        )

    def trash(self, permanent=False):
        if getattr(self.active, 'remote_file', None) is not None:
            self.remove_gio_items(permanent)
            return
        if self.active.is_trash:
            self.delete_trash()
            return
        paths = self.paths()
        if not paths:
            return
        try:
            signatures = {path: check_removal(path) for path in paths}
        except (OSError, ValueError) as error:
            self.notify(str(error))
            return
        if self.paths_busy(paths):
            self.notify(tr('Un élément sélectionné est utilisé par une opération en cours.'))
            return

        def confirmed():
            def work(path, cancelled, report):
                if cancelled():
                    raise InterruptedError()
                check_removal(path, signatures[path], recursive=True)
                record = None
                if permanent:
                    gio_backend.remove(Gio.File.new_for_path(str(path)), True, cancelled)
                else:
                    uri = trash_service.trash_tracked(path)
                    if uri is not None:
                        record = TrashRecord(path, uri, trash_service.entry_signature(uri))
                return {'source': str(path), 'trash_refresh': not permanent, 'undo_entry': record,
                        'undo_unavailable': not permanent and record is None,
                        'warning': tr('Le fichier est dans la corbeille, mais son suivi n’est pas disponible.')
                                   if not permanent and record is None else ''}

            self.jobs.submit(tr('Suppression'), paths, work, False)

        dialogs.confirm(
            self,
            tr('Supprimer définitivement ?' if permanent else 'Mettre à la corbeille ?'),
            f'{len(paths)} {tr("élément(s)")}\n'
            + tr('Cette action est irréversible.' if permanent else
                 'Ils pourront être restaurés depuis la corbeille du système.'),
            confirmed,
        )

    def terminal(self):
        for app, args in [
            ('xdg-terminal-exec', []),
            ('kgx', ['--working-directory', str(self.active.folder)]),
            ('gnome-terminal', ['--working-directory', str(self.active.folder)]),
        ]:
            if shutil.which(app):
                subprocess.Popen([app, *args], cwd=self.active.folder)
                return
        self.notify(tr('Aucun terminal disponible.'))

    def analyze(self, kind):
        items = self.active.selected()
        if kind not in ('total', 'test'):
            return
        allowed = [
            i
            for i in items
            if (i.row.is_dir if kind == 'total' else i.row.is_video or i.row.media_type == 'audio')
        ]
        if not allowed:
            self.notify(tr('Sélectionnez des médias compatibles.'))
            return
        if kind == 'total':
            # Durations of media and folders share the same sortable column.
            if 2 not in self.state.settings['columns']:
                self.state.settings['columns'].append(2)
                for pane in self.panes:
                    pane.columns[2].set_visible(True)
                self.state.save()
            self.active.stack.set_visible_child_name('details')
        title = {'test': 'Tester la lecture', 'total': 'Durée totale'}[kind]
        for item in allowed:
            item.pending = tr('En attente')
            item.pending_column = 2 if kind == 'total' else 10
            item.revision += 1
        self.jobs.submit(
            tr(title),
            [i.path for i in allowed],
            lambda path, cancelled, report: self.service.analyze(path, kind, cancelled, report),
        )

    def find_duplicates(self, folder=None):
        root = Path(folder if folder is not None else self.active.folder).absolute()
        if not root.is_dir():
            self.notify(tr('Le dossier à examiner est inaccessible.'))
            return
        include_hidden = self.hidden

        def work(_path, cancelled, report):
            groups = duplicates.find_duplicates_in_folder(
                root,
                cancelled,
                lambda text: report(None, text),
                lambda text: report(None, text),
                include_hidden,
            )
            return {'duplicates': groups, 'duplicates_root': str(root)}

        self.jobs.submit(tr('Recherche des doublons exacts'), [root], work)

    def correct_extension(self):
        plans = extensions.prepare_renames([i.row for i in self.active.selected()])
        valid = [p for p in plans if not p.issue]
        if not valid:
            self.notify(tr('Aucune extension à corriger.'))
            return

        def apply():
            def work(path, cancelled, report):
                p = next(p for p in valid if p.source == path)
                if cancelled():
                    raise InterruptedError()
                if extensions.fingerprint(path) != p.signature:
                    raise ValueError(tr('Le fichier a changé.'))
                renamed, errors = extensions.apply_renames([p])
                if errors:
                    raise ValueError(str(errors))
                self.state.relocate(path, p.destination)
                return {
                    'source': str(path),
                    'target': str(p.destination),
                    'renamed': [(str(source), str(target)) for source, target in renamed.items()],
                }

            self.jobs.submit(tr('Extensions'), [p.source for p in valid], work, False)

        dialogs.confirm(
            self,
            tr('Corriger les extensions ?'),
            '\n'.join(f'{p.source.name} → {p.destination.name}' for p in valid),
            apply,
        )

    def mkv_copy(self):
        paths = [i.path for i in self.active.selected() if i.row.is_video]

        def work(path, cancelled, report):
            target = path.with_name(path.stem + ' — copie.mkv')
            remux.mkv_copy(path, target, cancelled, lambda text: report(None, text))
            return {'target': str(target)}

        self.jobs.submit(tr('Copie MKV'), paths, work, False)

    def set_label(self):
        paths = self.paths()

        def done(value):
            for path in paths:
                self.state.annotate(path, label=value)
                self.touch(path)

        dialogs.text_input(self, tr('Étiquette'), '', done)

    def add_place(self):
        bookmarks = read_bookmarks()
        known = {uri for uri, _ in bookmarks}
        for path in self.paths():
            if not path.is_dir():
                continue
            uri = path.resolve().as_uri()
            if uri not in known:
                bookmarks.append((uri, path.name or str(path)))
                known.add(uri)
        write_bookmarks(bookmarks)
        self.fill_places()

    def bookmark_current(self):
        if self.active.is_trash or self.active.is_starred:
            return
        path = self.active.folder
        bookmarks = read_bookmarks()
        uri = path.resolve().as_uri()
        if uri not in {existing for existing, _label in bookmarks}:
            bookmarks.append((uri, path.name or str(path)))
            write_bookmarks(bookmarks)
            self.fill_places()

    def add_collection(self):
        paths = list(map(str, self.paths()))

        def done(name):
            if not name.strip():
                return
            previous = self.state.settings['collections'].get(name, [])
            self.state.settings['collections'][name] = list(dict.fromkeys(previous + paths))
            self.state.save()
            self.fill_places()

        dialogs.text_input(self, tr('Ajouter à une collection…'), '', done)

    def properties(self):
        if getattr(self.active, 'remote_file', None) is not None:
            dialogs.gio_properties(self, self.active.remote_selected())
            return
        items = self.active.selected()
        try:
            dialogs.properties(
                self,
                [item.path for item in items],
                items[0].row
                if len(items) == 1 and items[0].row.media_type in ('video', 'audio', 'image')
                else None,
            )
        except (OSError, ValueError) as error:
            self.notify(str(error))

    def show_error(self):
        dialogs.message(
            self,
            tr('Erreur'),
            '\n\n'.join(
                i.path.name + '\n' + health.explain_error(i.row.error) + '\n' + i.row.error
                for i in self.active.selected()
                if i.row.error
            ),
        )

    def export(self):
        dialogs.export_csv(self)

    def operations(self):
        dialogs.operations(self)

    def pause_jobs(self):
        self.jobs.paused.clear() if self.jobs.paused.is_set() else self.jobs.paused.set()
        self.menu_button.set_menu_model(self.main_menu())

    def cancel_analyses(self):
        dialogs.confirm(
            self,
            tr('Annuler les analyses ?'),
            tr('Les copies et déplacements continueront.'),
            self.jobs.cancel_analyses,
        )

    def touch(self, path):
        for pane in self.panes:
            pane.touch(path)

    def tick(self):
        if self.closed:
            return False
        for job, paths, provider in list(self.pending_cut_jobs):
            if job.state not in ('done', 'failed', 'cancelled'):
                continue
            self.pending_cut_jobs.remove((job, paths, provider))
            clipboard = self.get_clipboard()
            if provider is not None and clipboard.get_content() == provider:
                remaining = [path for path in self.clipboard_paths if path.exists()]
                self.set_file_clipboard(remaining, True)
        width = self.get_width()
        compact = width < 1700
        if compact != self.toolbar_compact:
            self.toolbar_compact = compact
            self.rebuild_toolbar()
        collapsed = width < 850
        if self.navigation.get_collapsed() != collapsed:
            self.navigation.set_collapsed(collapsed)
        self.compact_operations.set_visible(collapsed)
        # The first width notification may be emitted before GtkHeaderBar and
        # its title widget receive their final allocation. Re-evaluate after
        # allocation so split paths cannot remain hidden after startup.
        self.sync_path_visibility()
        self.sync_toolbar_geometry()
        if collapsed and not self.navigation.get_show_content():
            self.navigation.set_show_content(True)
        preview_collapsed = width < 1100
        if self.preview_split.get_collapsed() != preview_collapsed:
            self.preview_split.set_collapsed(preview_collapsed)
        for _ in range(80):
            try:
                job, path, result, error = self.jobs.events.get_nowait()
            except queue.Empty:
                break
            if error:
                for pane in self.panes:
                    item = pane.items.get(str(path))
                    if item:
                        item.row.error = error
                        item.row.values[10] = 'Erreur'
                        item.pending = ''
                        item.revision += 1
            elif isinstance(result, metadata.Video):
                for pane in self.panes:
                    item = pane.items.get(str(path))
                    if item:
                        item.pending = ''
                        item.update(result)
                        pane.update_models()
            elif isinstance(result, dict):
                if result.get('warning'):
                    self.notify(result['warning'])
                if result.get('undo_unavailable'):
                    job.undo_unavailable = True
                    self.undo_manager.discard_group(id(job))
                for entry in ([] if getattr(job, 'undo_unavailable', False) else result.get('undo_entries', [])):
                    self.undo_manager.record_prepared(entry, group=id(job))
                    if hasattr(entry, 'target'):
                        self.state.relocate(entry.source, entry.target, entry.copy)
                if result.get('undo_entry') and not getattr(job, 'undo_unavailable', False):
                    self.undo_manager.record_prepared(result['undo_entry'], group=id(job))
                elif result.get('undo_record'):
                    try:
                        self.undo_manager.record(result['source'], result['target'], result['copy'], group=id(job))
                    except (OSError, ValueError):
                        pass
                if result.get('renamed'):
                    self.undo_manager.record_rename(result['renamed'])
                for changed in result.get('reversed_paths', []):
                    self.touch(changed)
                for source, target in result.get('renamed', []):
                    self.touch(source)
                    self.touch(target)
                if result.get('archive_entries') is not None:
                    dialogs.archive_contents(self, Path(result['archive_path']), result['archive_entries'])
                for target in result.get('extracted', []):
                    self.touch(target)
                for target in result.get('gio_changed', []):
                    self.touch(target)
                if result.get('gio_move'):
                    remote = getattr(self, 'remote_clipboard', None)
                    if remote and self.get_clipboard().get_content() is remote[2]:
                        self.get_clipboard().set_content(None)
                        self.remote_clipboard = None
                    elif self.clipboard_cut and self.get_clipboard().get_content() is self.clipboard_provider:
                        self.set_file_clipboard([], False)
                remote_refresh = set(result.get('gio_remote_refresh', []))
                if remote_refresh:
                    for pane in self.panes:
                        if pane.remote_file is not None and pane.remote_file.get_uri() in remote_refresh:
                            pane.open_remote(pane.remote_file, False, keep_search=True)
                if result.get('archive_removed'):
                    self.touch(result['archive_removed'])
                if 'duplicates' in result:
                    dialogs.duplicate_results(self, result['duplicates'], result.get('duplicates_root'))
                if result.get('trash_refresh'):
                    self.refresh_trash_icon()
                    self.reload_trash_panes()
                for key in ('source', 'target'):
                    if result.get(key):
                        self.touch(result[key])
                if result.get('target'):
                    for pane in self.panes:
                        if pane.folder == Path(result['target']).parent:
                            pane.restore_selection.add(result['target'])
            else:
                self.touch(path)
        self.sync_toggle_actions()
        try:
            self.record_history()
        except OSError as error:
            self.state.settings['history'] = False
            self.notify(str(error))
        busy = [j for j in self.jobs.jobs if j.state in ('queued', 'running')]
        running = next((j for j in busy if j.state == 'running'), None)
        self.progress.set_visible(bool(busy))
        self.compact_progress.set_visible(bool(busy) and collapsed)
        self.stop_button.set_visible(any(j.analysis for j in busy))
        if running:
            for bar in (self.progress, self.compact_progress):
                if running.fraction is None:
                    bar.pulse()
                else:
                    bar.set_fraction(running.fraction)
                bar.set_tooltip_text(running.title + ' : ' + running.message)
        pending_paths = {str(path) for j in busy for path in j.paths}
        for pane in self.panes:
            for path, item in pane.items.items():
                if item.pending and path not in pending_paths:
                    item.pending = ''
                    item.revision += 1
        return True

    def record_history(self):
        if not self.state.settings['history']:
            if self.past_jobs or self.history_path.exists():
                self.past_jobs = []
                self.history_path.unlink(missing_ok=True)
            return
        changed = False
        for job in self.jobs.jobs:
            if job.state not in ('queued', 'running') and id(job) not in self.recorded_jobs:
                self.recorded_jobs.add(id(job))
                self.past_jobs.append(
                    dict(title=job.title, state=job.state, paths=list(map(str, job.paths)), errors=job.errors)
                )
                changed = True
        if changed:
            self.past_jobs = self.past_jobs[-100:]
            temp = self.history_path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.past_jobs, ensure_ascii=False))
            temp.replace(self.history_path)

    def clear_history(self):
        self.past_jobs = []
        self.history_path.unlink(missing_ok=True)
        self.jobs.jobs[:] = [job for job in self.jobs.jobs if job.state in ('queued', 'running')]

    def record_playback(self, path):
        if not self.state.settings['playback_history']:
            return
        try:
            values = (
                json.loads(self.playback_history_path.read_text())
                if self.playback_history_path.exists()
                else []
            )
            values = list(dict.fromkeys([str(path)] + [p for p in values if isinstance(p, str)]))[:100]
            temp = self.playback_history_path.with_suffix('.tmp')
            temp.write_text(json.dumps(values, ensure_ascii=False, indent=2))
            temp.replace(self.playback_history_path)
        except (OSError, ValueError, TypeError) as error:
            self.notify(str(error))

    def clear_playback_history(self):
        self.playback_history_path.unlink(missing_ok=True)
        self.notify(tr('Historique de lecture effacé.'))

    def apply_theme(self):
        value = self.state.settings['theme']
        Adw.StyleManager.get_default().set_color_scheme(
            {
                'auto': Adw.ColorScheme.DEFAULT,
                'dark': Adw.ColorScheme.FORCE_DARK,
                'light': Adw.ColorScheme.FORCE_LIGHT,
            }.get(value, Adw.ColorScheme.DEFAULT)
        )

    def sync_indicator(self):
        enabled = self.state.settings['minimize_to_tray'] and appindicator_available()
        if enabled and self.indicator is None:
            try:
                self.indicator = StatusNotifier(self.restore_from_indicator)
            except GLib.Error as error:
                self.state.settings['minimize_to_tray'] = False
                self.notify(error.message)
                return
        if self.indicator:
            self.indicator.set_active(enabled)

    def restore_from_indicator(self):
        if self.indicator:
            self.indicator.set_active(True)
        self.present()
        return False

    def request_quit(self):
        busy = any(j.state in ('queued', 'running') for j in self.jobs.jobs)
        if busy:
            dialogs.confirm(
                self,
                tr('Quitter Mirivue ?'),
                tr('Les opérations en cours seront interrompues. Les fichiers déjà copiés seront conservés.'),
                self.shutdown,
            )
        else:
            self.shutdown()

    def close_requested(self, *_):
        if self.closed:
            return False
        if self.state.settings['minimize_to_tray'] and appindicator_available():
            self.sync_indicator()
            GLib.idle_add(lambda: (self.set_visible(False), False)[1])
            return True
        self.request_quit()
        return True

    def shutdown(self):
        if self.closed:
            return
        if self.state.settings['startup'] == 'session':
            from .session import snapshot
            self.state.settings['tab_session'] = snapshot(self)
        self.closed = True
        self.templates.close()
        self.jobs.close()
        self.preview.close()
        GLib.source_remove(self.tick_id)
        if self.indicator:
            self.indicator.close()
            self.indicator = None
        self.starred_executor.shutdown(wait=False, cancel_futures=True)
        if self.bookmark_monitor:
            self.bookmark_monitor.cancel()
            self.bookmark_monitor = None
        if self.bookmark_refresh_timer:
            GLib.source_remove(self.bookmark_refresh_timer)
            self.bookmark_refresh_timer = 0
        if self.trash_monitor:
            self.trash_monitor.cancel()
            self.trash_monitor = None
        if self.trash_reload_timer:
            GLib.source_remove(self.trash_reload_timer)
            self.trash_reload_timer = 0
        for pane in self.panes:
            pane.close()
        model = self.active.view.get_columns()
        self.state.settings['column_order'] = [
            self.active.columns.index(model.get_item(i)) for i in range(model.get_n_items())
        ]
        self.state.save()
        self.set_sensitive(False)

        def finish():
            if self.jobs.worker.is_alive() or any(not f.done() for p in self.panes for f in p.futures):
                return True
            if self.job_window:
                self.job_window.close()
            application = self.get_application()
            self.destroy()
            if application and not application.get_windows():
                application.quit()
            return False

        GLib.timeout_add(50, finish)

    def about(self):
        Adw.AboutDialog(
            application_name='Mirivue',
            version=__version__,
            developer_name='pdenams',
            copyright='© 2026 Mirivue contributors',
            license_type=Gtk.License.GPL_3_0,
            comments=tr('Gestionnaire local de fichiers multimédias pour GNOME.'),
        ).present(self)


class MirivueGtkApplication(Adw.Application):
    def __init__(self):
        flags = Gio.ApplicationFlags.HANDLES_OPEN
        if not reuse_existing_window():
            flags |= Gio.ApplicationFlags.NON_UNIQUE
        super().__init__(application_id='org.pdenams.Mirivue.Gtk4', flags=flags)
        self.connect('activate', self.activate)
        self.connect('open', self.open_files)

    def activate(self, *_):
        window = self.props.active_window or MirivueWindow(self)
        window.present()

    def open_files(self, _app, files, _hint):
        self.activate()
        window = self.props.active_window
        seen = set()
        for index, file in enumerate(files):
            if file.get_uri() in seen:
                continue
            seen.add(file.get_uri())
            path = file.get_path()
            is_dir = file.query_file_type(Gio.FileQueryInfoFlags.NONE, None) == Gio.FileType.DIRECTORY if path else True
            location = file if is_dir else file.get_parent()
            if location is None:
                continue
            pane = window.active if index == 0 else window.new_tab(location)
            if pane is not None:
                if index == 0:
                    window.navigate_file(pane, location)
                if not is_dir and path:
                    pane.restore_selection.add(path)


def reuse_existing_window():
    path = (
        Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
        / 'mirivue-gtk4'
        / 'settings.json'
    )
    try:
        value = json.loads(path.read_text()).get('reuse_window', True)
        return value if type(value) is bool else True
    except (OSError, ValueError, TypeError):
        return True


def main():
    return MirivueGtkApplication().run(None)
