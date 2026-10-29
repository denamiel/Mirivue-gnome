import os
import tempfile
import unittest
from pathlib import Path

from mirivue_gtk4.places import (
    migrate_legacy_favorites,
    read_bookmarks,
    write_bookmarks,
    rename_bookmark,
    add_bookmark_folders,
)
from mirivue_gtk4.preview import render_pdf_page
from mirivue_gtk4.pane import apply_folder_count
from mirivue_gtk4.i18n import tr


class GnomePlacesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = os.environ.get('XDG_CONFIG_HOME')
        os.environ['XDG_CONFIG_HOME'] = self.temp.name

    def tearDown(self):
        if self.previous is None:
            os.environ.pop('XDG_CONFIG_HOME', None)
        else:
            os.environ['XDG_CONFIG_HOME'] = self.previous
        self.temp.cleanup()

    def test_bookmarks_share_local_and_remote_uris(self):
        entries = [('file:///home/test/My%20Folder', 'My Folder'), ('sftp://server/home/test', 'Server')]
        write_bookmarks(entries)
        self.assertEqual(read_bookmarks(), entries)

    def test_gtk4_bookmarks_are_authoritative_over_legacy_gtk3_list(self):
        config = Path(self.temp.name)
        (config / 'gtk-3.0').mkdir()
        (config / 'gtk-3.0' / 'bookmarks').write_text('file:///old-gtk3 Old entry\n')
        (config / 'gtk-4.0').mkdir()
        (config / 'gtk-4.0' / 'bookmarks').write_text('file:///nautilus GTK 4 entry\n')
        self.assertEqual(read_bookmarks(), [('file:///nautilus', 'GTK 4 entry')])

    def test_bookmark_rename_changes_label_only_and_drop_adds_folders(self):
        root = Path(self.temp.name)
        first = root / 'First'
        second = root / 'Second'
        first.mkdir()
        second.mkdir()
        original = [('sftp://server/share', 'Remote'), (first.as_uri(), 'First')]
        write_bookmarks(original)
        self.assertTrue(rename_bookmark(first.as_uri(), 'New name'))
        self.assertFalse(rename_bookmark(first.as_uri(), '\ninvalid'))
        self.assertEqual(add_bookmark_folders([first, second, root / 'missing']), 1)
        self.assertEqual(
            read_bookmarks(), [original[0], (first.as_uri(), 'New name'), (second.as_uri(), 'Second')]
        )

    def test_legacy_migration_preserves_remote_and_avoids_duplicates(self):
        folder = Path(self.temp.name) / 'Folder'
        folder.mkdir()
        remote = ('sftp://server/home/test', 'Server')
        write_bookmarks([remote])
        self.assertEqual(migrate_legacy_favorites([str(folder), str(folder)]), 1)
        self.assertEqual(read_bookmarks(), [remote, (folder.as_uri(), 'Folder')])

    def test_poppler_renders_document_pages_for_fullscreen_view(self):
        import cairo

        folder = Path(self.temp.name)
        source = folder / 'two-pages.pdf'
        pdf = cairo.PDFSurface(str(source), 320, 180)
        context = cairo.Context(pdf)
        for label in ('Page one', 'Page two'):
            context.move_to(24, 90)
            context.show_text(label)
            pdf.show_page()
        pdf.finish()
        output = folder / 'page-2.png'
        self.assertEqual(render_pdf_page(source, 1, output), 2)
        self.assertGreater(output.stat().st_size, 100)


if __name__ == '__main__':
    unittest.main()


class BreadcrumbTests(unittest.TestCase):
    def test_tab_title_updates_plain_and_close_button_headers(self):
        from types import SimpleNamespace
        from gi.repository import Gtk
        from mirivue_gtk4.pane import Pane

        plain = Gtk.Label(label='Dossier personnel')
        composite = Gtk.Box()
        composite.append(Gtk.Label(label='Ancien'))
        composite.append(Gtk.Button())
        for tab in (plain, composite):
            pane = SimpleNamespace(tabs=SimpleNamespace(get_tab_label=lambda _pane: tab))
            Pane.set_tab_title(pane, 'Audios')
            label = tab if isinstance(tab, Gtk.Label) else tab.get_first_child()
            self.assertEqual(label.get_label(), 'Audios')
            self.assertEqual(label.get_tooltip_text(), 'Audios')

    def test_focus_from_other_pane_does_not_override_navigation(self):
        from types import SimpleNamespace
        from mirivue_gtk4.app import MirivueWindow

        left = SimpleNamespace()
        right = SimpleNamespace()
        window = SimpleNamespace(navigation_pane=left, active=left)
        MirivueWindow.activate_pane(window, right, from_focus=True)
        self.assertIs(window.active, left)

    def test_navigation_keeps_the_opened_pane_active_after_focus_changes(self):
        from types import SimpleNamespace
        from mirivue_gtk4.pane import Pane

        left = SimpleNamespace(closed=False, generation=4, search_recursive_active=False)
        right = SimpleNamespace()
        activated = []
        window = SimpleNamespace(
            navigation_pane=left, active=right, activate_pane=lambda pane: activated.append(pane)
        )
        left.window = window
        self.assertFalse(Pane.finish_navigation_activation(left, 4))
        self.assertEqual(activated, [left])
        self.assertIs(window.navigation_pane, left)
        left.set_loading = lambda loading: None
        left.update_search_empty = lambda: None
        Pane.finish_loading(left, 4)
        self.assertEqual(activated, [left, left])
        self.assertIsNone(window.navigation_pane)
        window.navigation_pane = right
        Pane.finish_navigation_activation(left, 4)
        self.assertEqual(activated, [left, left])

    def test_relative_path_shows_home_and_each_folder_segment(self):
        from pathlib import Path
        from mirivue_gtk4.navigation import breadcrumb_segments, _all_breadcrumb_segments

        home = Path.home()
        self.assertEqual(breadcrumb_segments(home), [home])
        self.assertEqual(breadcrumb_segments(home / 'Documents'), [home, home / 'Documents'])
        self.assertEqual(
            breadcrumb_segments(home / 'Documents' / 'Images'),
            [home, home / 'Documents', home / 'Documents' / 'Images'],
        )
        deep = home / 'A' / 'B' / 'C' / 'D' / 'E' / 'F'
        self.assertEqual(
            _all_breadcrumb_segments(deep),
            [home, deep.parents[4], deep.parents[3], deep.parents[2], deep.parents[1], deep.parents[0], deep],
        )
        self.assertEqual(breadcrumb_segments(deep), [home, None, deep.parents[1], deep.parents[0], deep])

    def test_pathbar_keeps_nearest_segments_when_window_shrinks(self):
        from mirivue_gtk4.navigation import breadcrumb_visible_start

        widths = [55, 65, 75, 85]
        self.assertEqual(breadcrumb_visible_start(widths, 400, 42), 0)
        self.assertEqual(breadcrumb_visible_start(widths, 220, 42), 2)
        self.assertEqual(breadcrumb_visible_start(widths, 130, 42), 3)


class PathBarMenuTests(unittest.TestCase):
    def test_current_folder_menu_matches_native_file_manager_actions(self):
        from mirivue_gtk4.navigation import PATHBAR_MENU_SECTIONS

        actions = [[action for _label, action in section] for section in PATHBAR_MENU_SECTIONS]
        self.assertEqual(
            actions,
            [
                ['folder-open-with', 'terminal'],
                ['refresh', 'copy-location'],
                ['paste', 'select-all'],
                ['folder-properties'],
            ],
        )


class FolderCountTests(unittest.TestCase):
    def test_direct_child_count_updates_display_and_sort_value(self):
        class Row:
            values = ['folder', '—']
            sort_values = ['folder', None]

        row = Row()
        apply_folder_count(row, 4)
        self.assertEqual(row.values[1], f'4 {tr("éléments")}')
        self.assertEqual(row.sort_values[1], 4)

    def test_singular_child_count_uses_singular_label(self):
        class Row:
            values = ['folder', '—']
            sort_values = ['folder', None]

        row = Row()
        apply_folder_count(row, 1)
        self.assertEqual(row.values[1], f'1 {tr("élément")}')
        self.assertEqual(row.sort_values[1], 1)

    def test_thumbnail_toggle_changes_only_file_icon_state(self):
        from mirivue_gtk4.pane import Item, Pane

        class Row:
            def __init__(self, is_dir):
                self.is_dir = is_dir
                self.values = ['folder', '4 éléments']
                self.sort_values = ['folder', 4]

        class TestPane:
            def __init__(self, items):
                self.items = items
                self.refreshed = False

            def refresh_thumbnails(self):
                self.refreshed = True

        folder = Item(Row(True))
        file = Item(Row(False))
        file.thumbnail = '/tmp/thumbnail.png'
        pane = TestPane({'folder': folder, 'file': file})
        Pane.set_thumbnail_visibility(pane, True)
        self.assertFalse(folder.thumbnail_visible)
        self.assertTrue(file.thumbnail_visible)
        self.assertEqual(folder.row.values[1], '4 éléments')
        self.assertEqual(folder.row.sort_values[1], 4)
        Pane.set_thumbnail_visibility(pane, False)
        self.assertFalse(file.thumbnail_visible)
        self.assertEqual(folder.row.values[1], '4 éléments')
