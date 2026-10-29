import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from mirivue_gtk4.pane import Pane
from mirivue_gtk4.i18n import tr


class FolderCountTests(unittest.TestCase):
    def make_pane(self, folder_sizes):
        row = SimpleNamespace(
            is_dir=True,
            values=['Folder', '—'],
            sort_values=['folder', 0],
        )
        item = SimpleNamespace(row=row, folder_count=None, folder_size_known=False, revision=0)
        state = SimpleNamespace(settings={'folder_sizes': folder_sizes})
        window = SimpleNamespace(state=state)
        sorter = Mock()
        pane = SimpleNamespace(
            generation=2,
            closed=False,
            items={'/tmp/Folder': item},
            window=window,
            view=SimpleNamespace(get_sorter=lambda: sorter),
        )
        return pane, item, sorter

    def test_count_is_shown_while_recursive_size_is_enabled(self):
        pane, item, sorter = self.make_pane(folder_sizes=True)
        Pane.folder_count_ready(pane, 2, Path('/tmp/Folder'), 7)
        self.assertEqual(item.row.values[1], f"7 {tr('éléments')}")
        self.assertEqual(item.row.sort_values[1], 7)
        sorter.changed.assert_called_once()

    def test_late_count_does_not_replace_completed_recursive_size(self):
        pane, item, _sorter = self.make_pane(folder_sizes=True)
        item.folder_size_known = True
        item.row.values[1] = '2.0 Mio'
        item.row.sort_values[1] = 2 * 1024 * 1024
        Pane.folder_count_ready(pane, 2, Path('/tmp/Folder'), 7)
        self.assertEqual(item.row.values[1], '2.0 Mio')
        self.assertEqual(item.folder_count, 7)

    def test_disabling_full_sizes_restores_the_immediate_count(self):
        pane, item, sorter = self.make_pane(folder_sizes=False)
        item.folder_count = 7
        item.row.values[1] = '2.0 Mio'
        pane.folder_size_cancel = Mock()
        Pane.set_folder_sizes(pane, False)
        self.assertEqual(item.row.values[1], f"7 {tr('éléments')}")
        self.assertEqual(item.row.sort_values[1], 7)
        pane.folder_size_cancel.set.assert_called_once()
        sorter.changed.assert_called_once()

    def test_enrichment_publishes_row_after_restoring_early_count(self):
        path = Path('/tmp/Folder')
        notifications = []

        class ItemWithRevision:
            folder_count = 7
            thumbnail = ''
            thumbnail_visible = False
            row = None

            def update(self, row):
                self.row = row
                notifications.append(row.values[1])

        item = ItemWithRevision()
        row = SimpleNamespace(is_dir=True, values=['Folder', '—'], sort_values=['folder', 0])
        pane = SimpleNamespace(
            generation=2,
            closed=False,
            search_recursive_active=False,
            items={str(path): item},
            window=SimpleNamespace(
                state=SimpleNamespace(settings={'thumbnails': False, 'folder_sizes': False}),
                active=None,
            ),
            model_timer=1,
        )

        Pane.enriched(pane, 2, path, row, '')

        self.assertEqual(notifications, [f"7 {tr('éléments')}"])
        self.assertEqual(item.row.values[1], f"7 {tr('éléments')}")


if __name__ == '__main__':
    unittest.main()
