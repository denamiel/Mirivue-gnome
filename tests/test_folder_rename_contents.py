"""Folder-content renaming includes immediate hidden entries and directories."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mirivue_gtk4.core.renaming import folder_rename_rows, external_command, prepare_names


class FolderRenameContentsTests(unittest.TestCase):
    def test_immediate_children_only_and_f2_target_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'parent'
            folder.mkdir()
            (folder / '.hidden').write_text('a')
            (folder / 'film.mkv').write_text('b')
            child = folder / 'subfolder'
            child.mkdir()
            (child / 'nested.txt').write_text('c')
            (folder / 'link').symlink_to(child)
            rows = folder_rename_rows(folder)
            self.assertEqual({row.path.name for row in rows}, {'.hidden', 'film.mkv', 'subfolder'})
            self.assertNotIn(folder, {row.path for row in rows})
            self.assertEqual(len(prepare_names(rows, [row.path.name for row in rows])), 0)

    def test_external_renamer_accepts_directories_but_rejects_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'folder'
            folder.mkdir()
            file = folder / 'file.txt'
            file.touch()
            link = folder / 'link'
            link.symlink_to(file)
            with patch('mirivue_gtk4.core.renaming.shutil.which', return_value='/usr/bin/renamer'):
                executable, args = external_command('renamer', '--batch', [folder, file])
                self.assertEqual(executable, '/usr/bin/renamer')
                self.assertEqual(args, ['--batch', str(folder), str(file)])
                with self.assertRaises(ValueError):
                    external_command('renamer', '', [link])


if __name__ == '__main__':
    unittest.main()
