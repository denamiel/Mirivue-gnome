import tempfile
import unittest
from pathlib import Path

from mirivue_gtk4.core.folder_search import matching_paths


class FolderSearchTests(unittest.TestCase):
    def test_searches_nested_names_without_following_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'sub').mkdir()
            (root / 'sub' / 'movie.mp4').touch()
            (root / '.hidden').mkdir()
            (root / '.hidden' / 'movie.txt').touch()
            (root / 'linked').symlink_to(root / 'sub', target_is_directory=True)
            found = list(matching_paths(root, 'MOVIE', lambda: False))
            self.assertEqual(found, [root / 'sub' / 'movie.mp4'])
            self.assertIn(
                root / '.hidden' / 'movie.txt', list(matching_paths(root, 'movie', lambda: False, True))
            )

    def test_cancel_and_empty_query(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'match').touch()
            self.assertEqual(list(matching_paths(root, 'match', lambda: True)), [])
            self.assertEqual(list(matching_paths(root, ' ', lambda: False)), [])


if __name__ == '__main__':
    unittest.main()
