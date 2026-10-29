import tempfile
import unittest
from pathlib import Path

from mirivue_gtk4.core.duplicates import find_duplicates_in_folder, keep_one


class RecursiveDuplicateTests(unittest.TestCase):
    def test_matches_identical_bytes_across_subfolders_and_ignores_links(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('A', 'B', '.hidden'):
                (root / name).mkdir()
            first = root / 'A' / 'first.mp4'
            second = root / 'B' / 'second.mp4'
            first.write_bytes(b'same content')
            second.write_bytes(b'same content')
            (root / 'B' / 'different.mp4').write_bytes(b'same contEnt')
            (root / '.hidden' / 'third.mp4').write_bytes(b'same content')
            (root / 'linked').symlink_to(root / 'A', target_is_directory=True)
            (root / 'alias.mp4').symlink_to(first)
            groups = find_duplicates_in_folder(root)
            self.assertEqual(len(groups), 1)
            self.assertEqual({path for path, _ in groups[0]['files']}, {first, second})
            hidden_groups = find_duplicates_in_folder(root, include_hidden=True)
            self.assertEqual(len(hidden_groups[0]['files']), 3)

    def test_keeper_in_another_subfolder_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'A').mkdir()
            (root / 'B').mkdir()
            first = root / 'A' / 'first'
            keeper = root / 'B' / 'keeper'
            first.write_bytes(b'1234')
            keeper.write_bytes(b'1234')
            group = find_duplicates_in_folder(root)[0]
            removed, errors = keep_one(group, keeper, lambda path: path.unlink())
            self.assertEqual(errors, [])
            self.assertEqual(removed, [first])
            self.assertTrue(keeper.exists())

    def test_cancelled_tree_search_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(InterruptedError):
                find_duplicates_in_folder(temp, cancelled=lambda: True)


if __name__ == '__main__':
    unittest.main()
