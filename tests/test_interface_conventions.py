import json
import tempfile
import threading
import unittest
from pathlib import Path

from mirivue_gtk4.backend import DEFAULTS, State
from mirivue_gtk4 import i18n
from mirivue_gtk4.app import MirivueWindow
from mirivue_gtk4.pane import Pane


class InterfaceConventionTests(unittest.TestCase):
    """These checks use the French source labels, whatever the system language."""

    def setUp(self):
        self._previous_language = i18n.language
        i18n.language = 'fr'

    def tearDown(self):
        i18n.language = self._previous_language

    def test_f2_uses_native_editable_selection_for_a_single_file(self):
        from types import SimpleNamespace

        class Editable:
            def __init__(self, item):
                self.record = item
                self.calls = []

            def start_editing(self):
                self.calls.append('start')

            def get_editing(self):
                return False

            def get_text(self):
                return 'été.mkv'

            def select_region(self, start, end):
                self.calls.append((start, end))

        item = SimpleNamespace(editing=True, row=SimpleNamespace(is_dir=False))
        label = Editable(item)
        pane = SimpleNamespace(inline_editor=None)
        self.assertFalse(Pane.begin_inline_edit(pane, label, item))
        self.assertEqual(label.calls, ['start', (0, 3)])
        self.assertIs(pane.inline_editor, label)

    def test_old_idle_rename_cannot_edit_recycled_row(self):
        from types import SimpleNamespace

        old = SimpleNamespace(editing=True, row=SimpleNamespace(is_dir=False))
        current = SimpleNamespace(editing=True, row=SimpleNamespace(is_dir=False))
        label = SimpleNamespace(record=current, rename_pending_item=current)
        self.assertFalse(Pane.begin_inline_edit(None, label, old))
        self.assertIs(label.rename_pending_item, current)

    def test_repeated_row_paint_schedules_only_one_rename_start(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        callbacks = []
        item = object()
        label = SimpleNamespace()
        fake = SimpleNamespace(begin_inline_edit=lambda *args: None)
        with patch('mirivue_gtk4.pane.GLib.idle_add', side_effect=lambda *args: callbacks.append(args)):
            Pane.queue_inline_edit(fake, label, item)
            Pane.queue_inline_edit(fake, label, item)
        self.assertEqual(len(callbacks), 1)

    def test_typing_in_native_gtk_text_does_not_open_search(self):
        from types import SimpleNamespace
        from gi.repository import Gtk, Gdk

        focused = Gtk.Text()
        fake = SimpleNamespace(
            remote_file=None,
            is_trash=False,
            is_starred=False,
            window=SimpleNamespace(get_focus=lambda: focused),
        )
        self.assertFalse(Pane.type_to_search(fake, None, Gdk.KEY_a, 0, Gdk.ModifierType(0)))

    def test_empty_area_click_cancels_f2_then_clears_selection_after_gtk(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        class Editor:
            def __init__(self):
                self.cancelled = []
                self.suppress_focus_restore = False

            def get_editing(self):
                return True

            def stop_editing(self, commit):
                self.cancelled.append(commit)

        editor = Editor()
        cleared = []
        scheduled = []
        pane = SimpleNamespace(
            inline_editor=editor,
            generation=4,
            closed=False,
            picked=lambda *_: None,
            selection=SimpleNamespace(unselect_all=lambda: cleared.append(True)),
        )
        pane.clear_background_selection = lambda generation: Pane.clear_background_selection(pane, generation)
        gesture = SimpleNamespace(get_current_event_state=lambda: 0)
        with patch(
            'mirivue_gtk4.pane.GLib.idle_add', side_effect=lambda fn, *args: scheduled.append((fn, args))
        ):
            Pane.background_pressed(pane, gesture, 1, 20, 30, object())
        self.assertEqual(editor.cancelled, [False])
        self.assertTrue(editor.suppress_focus_restore)
        self.assertEqual(cleared, [])
        self.assertEqual(len(scheduled), 1)
        callback, args = scheduled[0]
        self.assertFalse(callback(*args))
        self.assertEqual(cleared, [True])

    def test_click_on_file_does_not_cancel_rename_or_clear_selection(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        editor = SimpleNamespace(get_editing=lambda: True)
        pane = SimpleNamespace(inline_editor=editor, picked=lambda *_: object())
        gesture = SimpleNamespace(get_current_event_state=lambda: 0)
        with patch('mirivue_gtk4.pane.GLib.idle_add') as idle:
            Pane.background_pressed(pane, gesture, 1, 20, 30, object())
        idle.assert_not_called()

    def test_background_cancellation_does_not_refocus_old_file(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        item = SimpleNamespace(editing=True)
        label = SimpleNamespace(
            record=item,
            was_editing=True,
            suppress_focus_restore=True,
            get_editing=lambda: False,
            get_text=lambda: 'film.mkv',
            set_editable=lambda value: None,
            display_label=SimpleNamespace(set_label=lambda text: None),
            set_visible=lambda value: None,
            name_stack=SimpleNamespace(set_visible_child_name=lambda name: None),
        )
        pane = SimpleNamespace(
            inline_editor=label, window=SimpleNamespace(finish_inline_rename=lambda *args: None)
        )
        with patch('mirivue_gtk4.pane.GLib.idle_add') as idle:
            Pane.inline_edit_finished(pane, label, None)
        idle.assert_not_called()
        self.assertFalse(item.editing)
        self.assertIsNone(pane.inline_editor)

    def test_inline_rename_keeps_original_name_until_job_succeeds(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        for proposed in ('essai-b.txt', 'essai-c.txt'):
            with self.subTest(proposed=proposed):
                shown = []
                calls = []
                display = SimpleNamespace(set_label=lambda value: shown.append(value))
                label = SimpleNamespace(
                    record=SimpleNamespace(editing=True),
                    was_editing=True,
                    suppress_focus_restore=False,
                    display_label=display,
                    get_editing=lambda: False,
                    get_text=lambda: proposed,
                    set_editable=lambda value: None,
                    set_visible=lambda value: None,
                    name_stack=SimpleNamespace(set_visible_child_name=lambda name: None),
                )
                pane = SimpleNamespace(
                    inline_editor=label,
                    restore_focus_after_inline_edit=lambda label: False,
                    window=SimpleNamespace(finish_inline_rename=lambda item, name: calls.append(name)),
                )
                with patch('mirivue_gtk4.pane.GLib.idle_add'):
                    Pane.inline_edit_finished(pane, label, None)
                self.assertEqual(calls, [proposed])
                self.assertEqual(
                    shown, [], 'The pending or rejected name must not replace the original label'
                )

    def test_f2_on_multiple_files_still_opens_batch_rename(self):
        from types import SimpleNamespace

        calls = []
        fake = SimpleNamespace(
            active=SimpleNamespace(selected=lambda: [object(), object()]),
            bulk_rename=lambda: calls.append('batch'),
        )
        MirivueWindow.rename(fake)
        self.assertEqual(calls, ['batch'])

    def test_active_pane_marker_only_in_two_pane_mode(self):
        from types import SimpleNamespace

        class Label:
            def __init__(self):
                self.classes = set()

            def add_css_class(self, value):
                self.classes.add(value)

            def remove_css_class(self, value):
                self.classes.discard(value)

        left = SimpleNamespace(panel_count=Label())
        right = SimpleNamespace(panel_count=Label())
        split = [False]
        fake = SimpleNamespace(
            panes=[left, right], active=left, tab_groups=[None, SimpleNamespace(get_visible=lambda: split[0])]
        )
        MirivueWindow.sync_active_pane_indicator(fake)
        self.assertEqual((left.panel_count.classes, right.panel_count.classes), (set(), set()))
        split[0] = True
        MirivueWindow.sync_active_pane_indicator(fake)
        self.assertEqual((left.panel_count.classes, right.panel_count.classes), ({'accent'}, set()))
        fake.active = right
        MirivueWindow.sync_active_pane_indicator(fake)
        self.assertEqual((left.panel_count.classes, right.panel_count.classes), (set(), {'accent'}))
        split[0] = False
        MirivueWindow.sync_active_pane_indicator(fake)
        self.assertEqual((left.panel_count.classes, right.panel_count.classes), (set(), set()))

    def test_view_and_folder_sort_are_mirivue_preferences(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as temp:
            state = State(Path(temp))
            self.assertEqual(state.settings['pane_views'], {'left': 'details', 'right': 'details'})
            saved = []
            state.save = lambda: saved.append(dict(state.settings['pane_views']))
            pane = SimpleNamespace(
                width_slot='left',
                local_view='details',
                window=SimpleNamespace(state=state),
                update_grid_columns=lambda: False,
                stack=SimpleNamespace(get_visible_child_name=lambda: 'icons'),
            )
            Pane.grid_view_changed(pane)
            self.assertEqual(pane.local_view, 'icons')
            self.assertEqual(saved, [{'left': 'icons', 'right': 'details'}])
            self.assertFalse(state.settings['folders_first'])
            self.assertNotIn('nautilus_preferences', vars(pane.window))

    def test_duplicate_search_uses_selected_folder_not_file_selection(self):
        from types import SimpleNamespace

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            folder = root / 'chosen'
            folder.mkdir()
            submitted = []
            fake = SimpleNamespace(
                active=SimpleNamespace(folder=root),
                hidden=False,
                jobs=SimpleNamespace(submit=lambda *args: submitted.append(args)),
            )
            MirivueWindow.find_duplicates(fake, folder=folder)
            self.assertEqual(len(submitted), 1)
            self.assertEqual(submitted[0][1], [folder])

    def test_default_columns_prioritize_common_file_information(self):
        self.assertEqual(DEFAULTS['columns'], [0, 1, 14])
        self.assertEqual(DEFAULTS['toolbar_hidden'], ['home', 'refresh', 'hidden', 'thumbnails'])

    def test_folders_first_is_opt_in_and_existing_choice_is_preserved(self):
        self.assertFalse(DEFAULTS['folders_first'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'settings.json').write_text(json.dumps({'folders_first': True}))
            self.assertTrue(State(root).settings['folders_first'])

    def test_factory_column_set_migrates_but_custom_columns_are_preserved(self):
        for columns, expected in [
            ([0, 1, 2, 3, 6, 10, 14], [0, 1, 14]),
            ([0, 1, 2, 3, 4, 6, 12, 14], [0, 1, 2, 3, 4, 6, 14]),
        ]:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / 'settings.json').write_text(json.dumps({'columns': columns}))
                self.assertEqual(State(root).settings['columns'], expected)

    def test_toolbar_factory_migrates_without_overriding_a_custom_layout(self):
        factory = [
            'home',
            'up',
            'back',
            'forward',
            'refresh',
            'paths',
            'search',
            'split',
            'details',
            'icons',
            'preview',
            'hidden',
            'thumbnails',
            'menu',
        ]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'settings.json').write_text(json.dumps({'toolbar_order': factory, 'toolbar_hidden': []}))
            self.assertEqual(State(root).settings['toolbar_hidden'], DEFAULTS['toolbar_hidden'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'settings.json').write_text(
                json.dumps({'toolbar_order': ['menu', 'paths', 'home', 'split'], 'toolbar_hidden': []})
            )
            state = State(root)
            self.assertEqual(state.settings['toolbar_hidden'], [])
            self.assertEqual(state.settings['toolbar_order'][:3], ['paths', 'home', 'split'])

    def test_search_and_primary_menu_are_fixed_outside_toolbar_preferences(self):
        self.assertNotIn('search', DEFAULTS['toolbar_order'])
        self.assertNotIn('menu', DEFAULTS['toolbar_order'])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'settings.json').write_text(
                json.dumps(
                    {
                        'toolbar_order': ['back', 'paths', 'search', 'preview', 'menu', 'split'],
                        'toolbar_hidden': ['search', 'menu', 'preview'],
                    }
                )
            )
            state = State(root)
            self.assertEqual(state.settings['toolbar_order'][:4], ['back', 'paths', 'preview', 'split'])
            self.assertEqual(state.settings['toolbar_hidden'], ['preview'])

    def test_new_navigation_labels_have_french_and_english_strings(self):
        previous = i18n.language
        try:
            for french, english in [
                ('Favoris', 'Starred'),
                ('Signets', 'Bookmarks'),
                ('Vue en liste', 'List View'),
                ('Vue en grille', 'Grid View'),
                ('Deux panneaux', 'Two Panes'),
                ('Ajouter aux signets', 'Add to Bookmarks'),
            ]:
                i18n.language = 'fr'
                self.assertEqual(i18n.tr(french), french)
                i18n.language = 'en'
                self.assertEqual(i18n.tr(french), english)
        finally:
            i18n.language = previous

    def test_primary_menu_has_shortcuts_and_media_tools_but_no_quit_item(self):
        from types import SimpleNamespace
        from gi.repository import Gio

        fake = SimpleNamespace(
            state=SimpleNamespace(settings={'recent': False, 'recent_paths': [], 'collections': {}}),
            jobs=SimpleNamespace(paused=threading.Event()),
        )
        previous = i18n.language
        i18n.language = 'fr'
        try:
            menu = MirivueWindow.main_menu(fake)
            labels = []

            def collect(model):
                for index in range(model.get_n_items()):
                    value = model.get_item_attribute_value(index, Gio.MENU_ATTRIBUTE_LABEL, None)
                    if value:
                        labels.append(value.get_string())
                    for link in (Gio.MENU_LINK_SECTION, Gio.MENU_LINK_SUBMENU):
                        child = model.get_item_link(index, link)
                        if child:
                            collect(child)

            collect(menu)
            self.assertIn('Raccourcis clavier', labels)
            self.assertIn('Outils multimédias…', labels)
            self.assertNotIn('Recherche avancée…', labels)
            self.assertNotIn('Nettoyage guidé…', labels)
            self.assertIn('Nouveau dossier…', labels)
            for removed in (
                'Rechercher…',
                'Vue en liste',
                'Afficher les miniatures',
                'Colonnes…',
                'Opérations…',
                'Personnaliser la barre d’outils…',
            ):
                self.assertNotIn(removed, labels)
            self.assertNotIn('Quitter Mirivue', labels)
        finally:
            i18n.language = previous

    def test_gnome_context_menu_matches_selection_and_registered_actions(self):
        from types import SimpleNamespace
        from mirivue_gtk4.core.menu_audit import missing_actions
        from mirivue_gtk4.core import associated
        from unittest.mock import patch

        row = SimpleNamespace(
            is_dir=True, media_type='', is_video=False, quality_score=None, suggested_extension='', error=''
        )
        item = SimpleNamespace(path=Path.home() / 'example-folder', row=row)
        pane = SimpleNamespace(is_trash=False, is_starred=False, selected=lambda: [item])
        fake = SimpleNamespace(
            active=pane, can_paste=lambda: False, state=SimpleNamespace(settings={'external_renamer': ''})
        )
        with patch.object(associated, 'find_associated', return_value=[]):
            folder = MirivueWindow.build_context_menu(fake)
            row.is_dir = False
            row.is_video = True
            row.media_type = 'video'
            row.quality_score = None
            video = MirivueWindow.build_context_menu(fake)
            row.quality_score = 74
            analyzed = MirivueWindow.build_context_menu(fake)

        def labels(menu):
            result = []
            for i in range(menu.get_n_items()):
                name = menu.get_item_attribute_value(i, 'label', None)
                if name:
                    result.append(name.get_string())
                for link in ('section', 'submenu'):
                    child = menu.get_item_link(i, link)
                    if child:
                        result.extend(labels(child))
            return result

        self.assertIn('Ouvrir dans un nouvel onglet', labels(folder))
        self.assertIn('Renommer le contenu du dossier…', labels(folder))
        multiple = SimpleNamespace(
            active=SimpleNamespace(is_trash=False, is_starred=False, selected=lambda: [item, item]),
            can_paste=lambda: False,
            state=fake.state,
        )
        with patch.object(associated, 'find_associated', return_value=[]):
            selected = MirivueWindow.build_context_menu(multiple)
        self.assertIn('Renommer', labels(selected))
        self.assertNotIn('Renommer en masse…', labels(selected))
        self.assertIn('Chercher les doublons dans ce dossier et ses sous-dossiers…', labels(folder))
        self.assertNotIn('Détails de qualité…', labels(video))
        self.assertNotIn('Détails de qualité…', labels(analyzed))
        # These cases verify that context menus have valid action names.
        actions = {
            'open',
            'open-with',
            'open-folder-tab',
            'find-duplicates-folder',
            'rename-folder-contents',
            'rename',
            'copy',
            'cut',
            'duplicate',
            'copy-path',
            'archive-create',
            'total',
            'add-place',
            'trash',
            'delete',
            'properties',
            'metadata',
            'label',
            'collection',
            'test',
            'mkv',
            'media-tools',
        }
        for menu in (folder, video, analyzed):
            self.assertEqual(missing_actions(menu, lambda name: name if name in actions else None), [])


if __name__ == '__main__':
    unittest.main()
