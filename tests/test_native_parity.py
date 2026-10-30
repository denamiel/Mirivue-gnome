"""Exercise native Adwaita tabs and the shared GIO directory model under Xvfb."""
import tempfile
import time
import sys
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk, Gio, GLib
from mirivue_gtk4.app import MirivueWindow
from mirivue_gtk4.backend import State
from mirivue_gtk4.pane import Pane
from mirivue_gtk4.clipboard_transfer import encode_uris, decode_uris
from mirivue_gtk4.core import gio_backend


def until(condition, seconds=6):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        if condition():
            return
        time.sleep(.01)
    raise AssertionError('Native GTK operation did not finish')


class NativeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Gtk.init()
        cls.app = Adw.Application(application_id='org.pdenams.Mirivue.NativeTests',
                                  flags=Gio.ApplicationFlags.NON_UNIQUE)
        cls.app.register(None)

    def setUp(self):
        self.callback_errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda *args: self.callback_errors.append(''.join(traceback.format_exception(*args)))
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder = self.root / 'files'
        self.folder.mkdir()
        self.state = State(self.root / 'state')
        self.state.settings.update(startup='custom', startup_path=str(self.folder),
                                   hide_on_start=False, thumbnails=False)
        self.window = MirivueWindow(self.app, state=self.state)
        self.window.present()
        until(lambda: not self.window.active.loading_details.get_visible())

    def tearDown(self):
        for window in list(self.app.get_windows()):
            if isinstance(window, MirivueWindow):
                window.shutdown()
            else:
                window.destroy()
        until(lambda: not self.app.get_windows())
        self.temp.cleanup()
        sys.excepthook = self.old_hook
        self.assertEqual(self.callback_errors, [], 'GTK signal handlers must not raise')

    def test_native_tab_close_restore_reorder_and_detach(self):
        one = self.folder / 'one'
        two = self.folder / 'two'
        one.mkdir()
        two.mkdir()
        pane = self.window.new_tab(one)
        group = pane.tabs
        self.assertIsInstance(group.view, Adw.TabView)
        self.assertIsInstance(group.bar, Adw.TabBar)
        self.assertEqual(group.view.get_page(pane).get_title(), 'one')
        other = self.window.new_tab(two)
        group.view.reorder_backward(group.view.get_page(other))
        self.assertEqual(group.page_num(other), 1)
        self.window.close_specific_tab(other)
        self.assertTrue(other.closed)
        group.restore()
        restored = self.window.active
        self.assertEqual(restored.folder, two)
        self.assertEqual(restored.history[-1], two)
        group.context_page = group.view.get_page(restored)
        group.detach()
        until(lambda: restored.window is not self.window)
        self.assertFalse(restored.closed)
        self.assertIs(restored.tabs.view.get_selected_page().get_child(), restored)
        self.assertIn(restored, restored.window.panes)
        self.assertNotIn(restored, self.window.panes)

    def test_gio_model_uses_common_views_filters_and_monitoring(self):
        (self.folder / 'clip.mp4').write_text('example')
        (self.folder / 'other.txt').write_text('text')
        (self.folder / 'backup~').touch()
        pane = self.window.active
        pane.open_remote(Gio.File.new_for_path(str(self.folder)))
        until(lambda: pane.remote_model is not None and not pane.remote_model.is_loading()
              and pane.store.get_n_items() == 3)
        self.assertIsInstance(pane.remote_model, Gtk.DirectoryList)
        self.assertEqual(pane.stack.get_visible_child_name(), 'details')
        pane.search.set_text('clip')
        pane.search_box.set_visible(True)
        pane.search_changed()
        self.assertEqual(pane.filtered.get_n_items(), 1)
        item = pane.filtered.get_item(0)
        self.assertEqual(item.file.get_uri(), (self.folder / 'clip.mp4').as_uri())
        pane.search.set_text('')
        pane.search_changed()
        self.assertEqual(pane.filtered.get_n_items(), 2)
        pane.search.set_text('clip')
        pane.search_changed()
        (self.folder / 'new.txt').touch()
        until(lambda: pane.store.get_n_items() == 4)
        self.assertEqual(pane.search.get_text(), 'clip')
        self.assertTrue(pane.search_box.get_visible())
        self.assertEqual(pane.filtered.get_n_items(), 1)
        pane.open(self.folder)
        until(lambda: pane.remote_model is None and pane.remote_file is None)

    def test_bulk_rename_reports_only_changes_and_conflicts_without_writing(self):
        from mirivue_gtk4 import dialogs
        from mirivue_gtk4.core import metadata
        paths = [self.folder / 'alpha.txt', self.folder / 'beta.txt']
        for path in paths:
            path.write_text('original')
        rows = [metadata.basic_entry(path) for path in paths]
        dialog = dialogs.bulk_rename(self.window, rows_override=rows)
        dialog.present()

        def widgets(root):
            yield root
            child = root.get_first_child()
            while child:
                yield from widgets(child)
                child = child.get_next_sibling()

        until(lambda: any(isinstance(w, Gtk.Entry) and w.get_placeholder_text() == 'Texte'
                          for w in widgets(dialog)))
        entry = next(w for w in widgets(dialog) if isinstance(w, Gtk.Entry)
                     and w.get_placeholder_text() == 'Texte')
        entry.set_text('new-')
        until(lambda: any(isinstance(w, Gtk.Label) and '2 à renommer' in w.get_label()
                          for w in widgets(dialog)))
        occupied = self.folder / 'taken-alpha.txt'
        occupied.write_text('preserve existing')
        entry.set_text('taken-')
        until(lambda: any(isinstance(w, Gtk.Label) and '1 à renommer' in w.get_label()
                          and '1 conflit(s)' in w.get_label() for w in widgets(dialog)))
        self.assertEqual(occupied.read_text(), 'preserve existing')
        entry.set_text('')
        until(lambda: any(isinstance(w, Gtk.Label) and '0 à renommer' in w.get_label()
                          and '2 inchangé(s)' in w.get_label() for w in widgets(dialog)))
        self.assertEqual([path.read_text() for path in paths], ['original', 'original'])
        dialog.destroy()

    def test_summary_uses_visible_items_or_explicit_selection(self):
        from mirivue_gtk4.dialogs import summary_items
        visible = [object(), object()]
        selected = []
        pane = SimpleNamespace(selected=lambda: selected,
                               filtered=SimpleNamespace(get_n_items=lambda: len(visible),
                                                        get_item=lambda i: visible[i]))
        self.assertEqual(summary_items(pane), visible)
        selected.append(visible[0])
        self.assertEqual(summary_items(pane), [visible[0]])

    def test_gio_create_rename_and_confirmed_recursive_delete(self):
        from mirivue_gtk4 import dialogs
        pane = self.window.active
        pane.open_remote(Gio.File.new_for_path(str(self.folder)))
        until(lambda: pane.remote_can_write)
        with patch.object(dialogs, 'text_input', side_effect=lambda parent, title, initial, callback: callback('new folder')):
            self.window.new_folder()
        until(lambda: (self.folder / 'new folder').is_dir())
        until(lambda: any(item.name == 'new folder' for item in pane.items.values()))
        item = next(item for item in pane.items.values() if item.name == 'new folder')
        self.assertTrue(item.row.file_capabilities['rename'])
        self.window.rename_gio_item(item, 'renamed folder')
        until(lambda: (self.folder / 'renamed folder').is_dir())
        (self.folder / 'renamed folder' / 'child.txt').write_text('disposable')
        untouched = self.folder / 'untouched.txt'
        untouched.write_text('keep')
        gio_backend.remove(Gio.File.new_for_path(str(self.folder / 'renamed folder')), True)
        self.assertFalse((self.folder / 'renamed folder').exists())
        self.assertEqual(untouched.read_text(), 'keep')

    def test_external_launch_processes_all_locations_once(self):
        from mirivue_gtk4.app import MirivueGtkApplication
        folders = [self.folder / 'one', self.folder / 'two']
        for folder in folders:
            folder.mkdir()
        calls = []
        pane = SimpleNamespace(restore_selection=set())
        window = SimpleNamespace(active=pane,
            navigate_file=lambda p, file: calls.append(('open', file.get_uri())),
            new_tab=lambda file: calls.append(('tab', file.get_uri())))
        application = SimpleNamespace(activate=lambda: None, props=SimpleNamespace(active_window=window))
        files = [Gio.File.new_for_path(str(path)) for path in folders]
        MirivueGtkApplication.open_files(application, None, files + files, None)
        self.assertEqual(calls, [('open', files[0].get_uri()), ('tab', files[1].get_uri())])

    def test_closing_last_tab_of_one_pane_keeps_other_pane_and_can_split_again(self):
        window = self.window
        left = window.active
        window.toggle_split()
        right = window.active
        self.assertIsNot(left, right)
        window.close_specific_tab(left)
        until(lambda: window.tab_groups[0] is right.tabs)
        self.assertFalse(window.closed)
        self.assertIs(window.active, right)
        window.toggle_split()
        self.assertEqual([group.get_n_pages() for group in window.tab_groups], [1, 1])
        self.assertTrue(window.tab_groups[1].get_visible())

    def test_gio_uri_clipboard_preserves_remote_cut(self):
        uris = ['smb://server/share/a%20b.mkv', 'sftp://server/home/u/c.txt']
        self.assertEqual(decode_uris(encode_uris(uris, True)), (uris, True))
        info = Gio.FileInfo()
        info.set_name('a b.mkv')
        info.set_display_name('a b.mkv')
        info.set_file_type(Gio.FileType.REGULAR)
        info.set_size(123)
        info.set_content_type('video/x-matroska')
        row = gio_backend.row_from_info(Gio.File.new_for_uri('smb://server/share/'), info)
        self.assertEqual(row.gio_file.get_uri(), uris[0])
        self.assertIsNone(row.gio_file.get_path())

    def test_name_search_never_matches_only_a_metadata_tag(self):
        pane = self.window.active
        row = SimpleNamespace(is_dir=False, media_type='audio', sort_values=[0]*38,
                              media_technical={}, personal_label='', media_tags={'artist': 'hidden artist'})
        item = SimpleNamespace(path=Path('/example/song.mp3'), row=row)
        pane.search.set_text('hidden artist')
        self.assertFalse(Pane.matches(pane, item))
        pane.search.set_text('song')
        self.assertTrue(Pane.matches(pane, item))


if __name__ == '__main__':
    unittest.main()
