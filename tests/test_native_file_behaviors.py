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
