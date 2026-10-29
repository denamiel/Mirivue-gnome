import unittest
from pathlib import Path
from types import SimpleNamespace

from mirivue_gtk4.pane import Pane


class SearchUiTests(unittest.TestCase):
    def test_media_type_excludes_directories_and_nonmatching_files(self):
        pane = SimpleNamespace(
            window=SimpleNamespace(hidden=False),
            type_filter='video',
            collection=None,
            criteria={},
            search=SimpleNamespace(get_text=lambda: 'clip'),
        )
        values = [0] * 38
        row = SimpleNamespace(
            is_dir=False,
            media_type='video',
            sort_values=values,
            media_technical={},
            personal_label='',
            media_tags={},
        )
        item = SimpleNamespace(path=Path('/tmp/clip.mp4'), row=row)
        self.assertTrue(Pane.matches(pane, item))
        row.is_dir = True
        self.assertFalse(Pane.matches(pane, item))
        row.is_dir = False
        row.media_type = 'audio'
        self.assertFalse(Pane.matches(pane, item))

    def test_retired_quality_filter_is_not_applied_to_search_results(self):
        pane = SimpleNamespace(
            window=SimpleNamespace(hidden=False),
            type_filter='video',
            collection=None,
            criteria={'quality': 70},
            search=SimpleNamespace(get_text=lambda: ''),
        )
        values = [0] * 38
        row = SimpleNamespace(
            is_dir=False,
            media_type='video',
            sort_values=values,
            media_technical={},
            personal_label='',
            media_tags={},
        )
        item = SimpleNamespace(path=Path('/tmp/clip.mp4'), row=row)
        self.assertTrue(Pane.matches(pane, item))
        values[12] = 78
        self.assertTrue(Pane.matches(pane, item))

    def test_size_and_known_error_filters(self):
        pane = SimpleNamespace(
            window=SimpleNamespace(hidden=False),
            type_filter='all',
            collection=None,
            criteria={'size_mib': 10, 'errors': True},
            search=SimpleNamespace(get_text=lambda: ''),
        )
        values = [0] * 38
        values[1] = 12 * 1024 * 1024
        row = SimpleNamespace(
            is_dir=False,
            media_type='other',
            sort_values=values,
            media_technical={},
            personal_label='',
            media_tags={},
            error='Invalid file',
        )
        item = SimpleNamespace(path=Path('/tmp/broken.bin'), row=row)
        self.assertTrue(Pane.matches(pane, item))
        row.error = ''
        self.assertFalse(Pane.matches(pane, item))
        row.error = 'Invalid file'
        values[1] = 9 * 1024 * 1024
        self.assertFalse(Pane.matches(pane, item))


if __name__ == '__main__':
    unittest.main()
