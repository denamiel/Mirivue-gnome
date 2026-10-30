"""Exercise native Adwaita tabs and the shared GIO directory model under Xvfb."""
import tempfile
import time
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
        (self.folder / 'new.txt').touch()
        until(lambda: pane.store.get_n_items() == 4)
        pane.open(self.folder)
        until(lambda: pane.remote_model is None and pane.remote_file is None)

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
