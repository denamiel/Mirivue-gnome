"""Native GTK/GIO integration for the behavior corrections of 0.6.24."""
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import test_native_parity as support
from gi.repository import Gtk, Gdk, Gio, GLib
from mirivue_gtk4.core.undo import UndoManager
from mirivue_gtk4.core.file_information import summarize_files
from mirivue_gtk4.pane import Pane
from mirivue_gtk4.preview import Preview


class NativeFileBehaviorsTests(unittest.TestCase):
    setUpClass = classmethod(support.NativeParityTests.setUpClass.__func__)
    setUp = support.NativeParityTests.setUp
    tearDown = support.NativeParityTests.tearDown

    def test_native_links_use_available_names_and_grouped_undo(self):
        source = self.folder / 'original.txt'
        source.write_text('keep original')
        file = Gio.File.new_for_path(str(source))
        self.window.create_file_links([file], Gio.File.new_for_path(str(self.folder)))
        from mirivue_gtk4.i18n import trf
        link = self.folder / trf('Lien vers \x1f0\x1f', source.name)
        support.until(lambda: link.is_symlink() and bool(self.window.undo_manager.undo_stack))
        self.window.reverse_file_operation(False)
        support.until(lambda: not link.is_symlink() and bool(self.window.undo_manager.redo_stack))
        self.assertEqual(source.read_text(), 'keep original')
        self.window.reverse_file_operation(True)
        support.until(lambda: link.is_symlink())
        self.assertEqual(link.read_text(), 'keep original')

    def test_regional_dates_honor_clock_preference_in_both_styles(self):
        from mirivue_gtk4.i18n import date_text
        noon = GLib.DateTime.new_now_local().to_unix() * 1_000_000_000
        clock = SimpleNamespace(get_string=lambda _key: '12h')
        with patch('mirivue_gtk4.i18n.clock_settings', return_value=clock):
            self.assertRegex(date_text(noon), r'[AP]M$')
            self.assertRegex(date_text(noon, 'detailed'), r'[AP]M$')

    def test_text_clipboard_does_not_enable_file_paste_or_raise(self):
        self.window.get_clipboard().set('plain text')
        self.assertFalse(self.window.can_paste())
        self.window.build_context_menu()

    def test_f2_popover_selects_stem_validates_and_renames(self):
        source = self.folder / 'été.mkv'
        source.write_text('original')
        occupied = self.folder / 'occupied.mkv'
        occupied.write_text('keep')
        pane = self.window.active
        pane.open(self.folder)
        support.until(lambda: str(source) in pane.items)
        popover = pane.start_inline_rename(pane.items[str(source)])
        self.assertIsInstance(popover, Gtk.Popover)
        self.assertEqual(popover.entry.get_selection_bounds(), (0, 3))
        popover.entry.set_text('occupied.mkv')
        popover.entry.emit('activate')
        self.assertEqual(occupied.read_text(), 'keep')
        self.assertTrue(source.exists())
        popover.entry.set_text('renamed.mkv')
        popover.entry.emit('activate')
        support.until(lambda: (self.folder / 'renamed.mkv').exists())
        self.assertFalse(source.exists())

    def test_one_copy_action_is_undone_and_redone_once(self):
        paths = [self.folder / 'one.txt', self.folder / 'two.txt']
        destination = self.folder / 'destination'
        destination.mkdir()
        for path in paths:
            path.write_text(path.name)
        self.window.transfer(paths, destination, copy=True)
        support.until(lambda: len(self.window.undo_manager.undo_stack) == 1 and not self.window.paths_busy(paths))
        self.window.reverse_file_operation(False)
        support.until(lambda: not any((destination / path.name).exists() for path in paths))
        support.until(lambda: bool(self.window.undo_manager.redo_stack))
        self.window.reverse_file_operation(True)
        support.until(lambda: all((destination / path.name).exists() for path in paths))
        self.assertEqual([path.read_text() for path in paths], ['one.txt', 'two.txt'])

    def test_copied_tree_undo_rejects_new_user_content(self):
        source = self.folder / 'original'
        source.mkdir()
        (source / 'one.txt').write_text('keep')
        target = self.folder / 'copy'
        shutil.copytree(source, target)
        manager = UndoManager()
        self.assertTrue(manager.record(source, target, True))
        extra = target / 'user.txt'
        extra.write_text('new content')
        with self.assertRaises(ValueError):
            manager.undo()
        self.assertEqual(extra.read_text(), 'new content')
        extra.unlink()
        # Re-record the current verified tree, then exercise native GIO deletion.
        manager = UndoManager()
        manager.record(source, target, True)
        manager.undo()
        self.assertFalse(target.exists())
        manager.redo()
        self.assertEqual((target / 'one.txt').read_text(), 'keep')

    def test_gio_properties_total_deduplicates_selected_children(self):
        sub = self.folder / 'sub'
        sub.mkdir()
        first = sub / 'one.txt'
        first.write_bytes(b'123')
        (sub / 'two.txt').write_bytes(b'45678')
        data = summarize_files([Gio.File.new_for_path(str(sub)), Gio.File.new_for_path(str(first))], Gio.Cancellable())
        self.assertEqual((data['files'], data['folders'], data['bytes']), (2, 1, 8))
        self.assertEqual(data['errors'], [])
        cancel = Gio.Cancellable()
        cancel.cancel()
        with self.assertRaises(GLib.Error):
            summarize_files([Gio.File.new_for_path(str(sub))], cancel)

    def test_drop_targets_same_pane_subfolder_and_respects_control(self):
        pane = self.window.active
        sub = self.folder / 'destination'
        sub.mkdir()
        source = self.folder / 'source.txt'
        source.write_text('keep')
        file = Gio.File.new_for_path(str(source))
        destination = Gio.File.new_for_path(str(sub))
        item = SimpleNamespace(row=SimpleNamespace(is_dir=True), file=destination)
        pane.picked = lambda *_: item
        self.window.drag_source_pane = pane
        calls = []
        target = SimpleNamespace(get_current_event_state=lambda: Gdk.ModifierType.CONTROL_MASK,
                                 get_current_drop=lambda: None)
        with patch.object(self.window, 'prepare_paste', side_effect=lambda *args: calls.append(args)):
            self.assertTrue(pane.drop(target, Gdk.FileList.new_from_list([file]), 0, 0, pane.view))
        self.assertEqual(calls, [([source], sub, False)])
        self.assertEqual(source.read_text(), 'keep')

    def test_video_scroll_leaves_volume_and_position_untouched(self):
        stream = SimpleNamespace(set_volume=lambda *_: self.fail('Unexpected volume change'),
                                 seek=lambda *_: self.fail('Unexpected seek'))
        preview = SimpleNamespace(current=SimpleNamespace(row=SimpleNamespace(media_type='video')), stream=stream)
        self.assertFalse(Preview.wheel(preview, None, 1, 1))

    def test_filter_only_search_visits_subfolders_and_remote_search_keeps_uris(self):
        sub = self.folder / 'nested'
        sub.mkdir()
        deep = sub / 'deep.txt'
        deep.write_text('example')
        pane = self.window.active
        pane.open(self.folder)
        pane.search_box.set_visible(True)
        pane.criteria = {'size_mib': 1}
        pane.search_changed()
        support.until(lambda: pane.search_finished and str(deep) in pane.items)
        self.assertTrue(pane.search_recursive_active)
        pane.open_remote(Gio.File.new_for_path(str(self.folder)))
        support.until(lambda: pane.remote_model is not None and not pane.remote_model.is_loading())
        pane.search_box.set_visible(True)
        pane.search.set_text('deep')
        pane.search_changed()
        support.until(lambda: pane.search_finished and deep.as_uri() in pane.items)
        self.assertEqual(pane.filtered.get_n_items(), 1)
        self.assertEqual(pane.filtered.get_item(0).file.get_uri(), deep.as_uri())

    def test_required_native_shortcuts_are_registered(self):
        app = self.window.get_application()
        for action, key in [('new-window', '<Control>n'), ('delete', '<Shift>Delete'),
                            ('details', '<Control>1'), ('icons', '<Control>2'),
                            ('open-folder-tabs', '<Control>Return'), ('terminal', '<Control>period')]:
            actual = [Gtk.accelerator_parse(value)[1:] for value in app.get_accels_for_action('win.' + action)]
            self.assertIn(Gtk.accelerator_parse(key)[1:], actual)

    def test_session_restores_two_groups_and_does_not_store_passwords(self):
        from mirivue_gtk4.app import MirivueWindow
        from mirivue_gtk4.session import snapshot, location
        first, second = self.folder / 'one', self.folder / 'two'
        first.mkdir(); second.mkdir()
        self.window.new_tab(first)
        self.window.toggle_split()
        self.window.new_tab(second)
        self.state.settings['startup'] = 'session'
        self.state.settings['tab_session'] = snapshot(self.window)
        other = MirivueWindow(self.app, state=self.state)
        other.present()
        support.until(lambda: other.active.folder == second)
        self.assertEqual([group.get_n_pages() for group in other.tab_groups], [2, 2])
        self.assertTrue(other.tab_groups[1].get_visible())
        self.assertIs(other.active.tabs, other.tab_groups[1])
        lazy = other.tab_groups[0].get_nth_page(0)
        self.assertIsNotNone(lazy.pending_location)
        other.tab_groups[0].set_current_page(0)
        support.until(lambda: lazy.pending_location is None and other.active is lazy)
        saved = location(SimpleNamespace(pending_location=Gio.File.new_for_uri('sftp://user:secret@example.invalid/folder')))
        self.assertEqual(saved, 'sftp://user@example.invalid/folder')

    def test_folder_views_remain_mirivue_preferences_and_restore_independently(self):
        pane = self.window.active
        first, second = self.folder / 'first', self.folder / 'second'
        first.mkdir(); second.mkdir()
        self.state.settings['remember_folder_view'] = True
        pane.open(first)
        pane.stack.set_visible_child_name('icons')
        pane.view.sort_by_column(pane.columns[1], Gtk.SortType.DESCENDING)
        pane.open(second)
        pane.stack.set_visible_child_name('details')
        pane.view.sort_by_column(pane.columns[0], Gtk.SortType.ASCENDING)
        pane.open(first)
        self.assertEqual(pane.local_view, 'icons')
        self.assertIs(pane.view.get_sorter().get_primary_sort_column(), pane.columns[1])
        self.assertEqual(pane.view.get_sorter().get_primary_sort_order(), Gtk.SortType.DESCENDING)
        pane.open(second)
        self.assertEqual(pane.local_view, 'details')
        self.assertIs(pane.view.get_sorter().get_primary_sort_column(), pane.columns[0])

    def test_templates_populate_native_menu_and_copy_original_without_changing_it(self):
        from mirivue_gtk4.templates import Templates
        templates = self.root / 'templates'
        (templates / 'nested').mkdir(parents=True)
        source = templates / 'Note.txt'
        source.write_text('template content')
        (templates / 'nested' / 'Other.txt').write_text('other')
        with patch('mirivue_gtk4.templates.GLib.get_user_special_dir', return_value=str(templates)):
            provider = Templates(self.window)
            try:
                def ready():
                    section = provider.menu.get_item_link(1, 'section') if provider.menu.get_n_items() > 1 else None
                    return section is not None and section.get_n_items() == 2
                support.until(ready)
                self.window.new_from_template(Gio.File.new_for_path(str(source)))
                support.until(lambda: (self.folder / 'Note.txt').exists())
                self.assertIsNone(getattr(self.window.active, 'rename_popover', None))
                self.assertEqual(source.read_text(), 'template content')
                self.assertEqual((self.folder / 'Note.txt').read_text(), 'template content')
            finally:
                provider.close()

    def test_status_selection_uses_incremental_model_totals(self):
        path = self.folder / 'item.txt'
        path.write_bytes(b'123')
        pane = self.window.active
        pane.open(self.folder)
        support.until(lambda: str(path) in pane.items)
        item = pane.items[str(path)]
        item.row.sort_values[1] = 50
        item.revision += 1
        with patch.object(pane.filtered, 'get_item', side_effect=AssertionError('No complete recount on selection')):
            text = pane.status_index.text([item])
        self.assertIn('50', text)
        self.assertNotIn('0 erreurs', text)

    def test_bookmark_reordering_preserves_remote_uris_and_labels(self):
        from mirivue_gtk4 import places
        file = self.root / 'bookmarks'
        with patch.object(places, 'bookmark_file', return_value=file):
            places.write_bookmarks([('file:///one', 'One'), ('smb://server/share', 'Shared'), ('file:///two', 'Two')])
            self.assertTrue(places.reorder_bookmark('smb://server/share', 'file:///two', True))
            self.assertEqual(places.read_bookmarks(), [('file:///one', 'One'), ('file:///two', 'Two'), ('smb://server/share', 'Shared')])

    def test_trash_undo_redo_uses_exact_gvfs_entry_when_available(self):
        from mirivue_gtk4.core import trash
        from mirivue_gtk4.core.undo import TrashRecord
        try:
            trash.rows()
        except GLib.Error:
            self.skipTest('GVfs Trash is not available in this isolated environment')
        path = self.folder / 'trash-roundtrip.txt'
        path.write_text('keep')
        uri = trash.trash_tracked(path)
        self.assertIsNotNone(uri)
        manager = UndoManager()
        manager.record_prepared(TrashRecord(path, uri, trash.entry_signature(uri)))
        manager.undo()
        self.assertEqual(path.read_text(), 'keep')
        manager.redo()
        self.assertFalse(path.exists())
        manager.undo()
        self.assertEqual(path.read_text(), 'keep')
