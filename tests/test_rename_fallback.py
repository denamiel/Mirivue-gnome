"""RENAME_NOREPLACE fallback: never overwrite, even when the flag is rejected."""

import errno
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mirivue_gtk4.core.platform_services import PlatformServices


def rejecting(code):
    def fake(self, source, target):
        raise OSError(code, os.strerror(code), str(target))

    return fake


class RenameFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.services = PlatformServices()

    def tearDown(self):
        self.tmp.cleanup()

    def test_native_noreplace_refuses_existing_target(self):
        (self.root / 'a').write_text('A')
        (self.root / 'b').write_text('B')
        with self.assertRaises(FileExistsError):
            self.services.rename_no_replace(self.root / 'a', self.root / 'b')
        self.assertEqual((self.root / 'b').read_text(), 'B')

    def test_einval_falls_back_for_file(self):
        (self.root / 'a').write_text('A')
        with mock.patch.object(PlatformServices, '_renameat2_noreplace', rejecting(errno.EINVAL)):
            self.services.rename_no_replace(self.root / 'a', self.root / 'b')
        self.assertFalse((self.root / 'a').exists())
        self.assertEqual((self.root / 'b').read_text(), 'A')

    def test_fallback_never_overwrites_file(self):
        (self.root / 'a').write_text('A')
        (self.root / 'b').write_text('B')
        with mock.patch.object(PlatformServices, '_renameat2_noreplace', rejecting(errno.EINVAL)):
            with self.assertRaises(FileExistsError):
                self.services.rename_no_replace(self.root / 'a', self.root / 'b')
        self.assertEqual((self.root / 'a').read_text(), 'A')
        self.assertEqual((self.root / 'b').read_text(), 'B')

    def test_fallback_for_directory_and_existing_empty_directory(self):
        (self.root / 'd').mkdir()
        (self.root / 'd' / 'f').write_text('x')
        (self.root / 'empty').mkdir()
        with mock.patch.object(PlatformServices, '_renameat2_noreplace', rejecting(errno.ENOTSUP)):
            with self.assertRaises(FileExistsError):
                self.services.rename_no_replace(self.root / 'd', self.root / 'empty')
            self.services.rename_no_replace(self.root / 'd', self.root / 'e')
        self.assertEqual((self.root / 'e' / 'f').read_text(), 'x')

    def test_fallback_without_hard_links(self):
        (self.root / 'a').write_text('A')
        with (
            mock.patch.object(PlatformServices, '_renameat2_noreplace', rejecting(errno.EINVAL)),
            mock.patch('os.link', side_effect=OSError(errno.EPERM, 'no links')),
        ):
            self.services.rename_no_replace(self.root / 'a', self.root / 'b')
        self.assertEqual((self.root / 'b').read_text(), 'A')

    def test_symlink_is_moved_not_followed(self):
        (self.root / 'real').write_text('R')
        os.symlink('real', self.root / 'link')
        with mock.patch.object(PlatformServices, '_renameat2_noreplace', rejecting(errno.EINVAL)):
            self.services.rename_no_replace(self.root / 'link', self.root / 'moved')
        self.assertTrue((self.root / 'moved').is_symlink())
        self.assertEqual(os.readlink(self.root / 'moved'), 'real')

    def test_other_errors_are_not_masked(self):
        (self.root / 'a').write_text('A')
        with mock.patch.object(PlatformServices, '_renameat2_noreplace', rejecting(errno.EACCES)):
            with self.assertRaises(PermissionError):
                self.services.rename_no_replace(self.root / 'a', self.root / 'b')
        self.assertTrue((self.root / 'a').exists())


if __name__ == '__main__':
    unittest.main()


class NewFolderDefaultTests(unittest.TestCase):
    def setUp(self):
        from mirivue_gtk4 import i18n

        self.i18n = i18n
        self.previous = i18n.language
        i18n.language = 'fr'
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.i18n.language = self.previous
        self.tmp.cleanup()

    def test_default_name_is_untitled_folder_like_gnome_files(self):
        from mirivue_gtk4.core import file_moves

        self.assertEqual(file_moves.untitled_folder_name(self.root), 'Dossier sans titre')
        self.assertTrue(file_moves.valid_name('Dossier sans titre'))

    def test_default_name_never_collides(self):
        from mirivue_gtk4.core import file_moves

        (self.root / 'Dossier sans titre').mkdir()
        (self.root / 'Dossier sans titre 2').write_text('')
        self.assertEqual(file_moves.untitled_folder_name(self.root), 'Dossier sans titre 3')

    def test_english_default_name(self):
        from mirivue_gtk4.core import file_moves

        self.i18n.language = 'en'
        self.assertEqual(file_moves.untitled_folder_name(self.root), 'Untitled Folder')

    def test_group_folder_fallback_name(self):
        from mirivue_gtk4.core import file_moves

        self.assertEqual(file_moves.suggest_folder(['/x/a.txt', '/x/b.txt']), 'Dossier sans titre')

    def test_dialogs_use_the_helpers(self):
        app = (Path(__file__).resolve().parents[1] / 'mirivue_gtk4' / 'app.py').read_text()
        self.assertIn('file_moves.untitled_folder_name(folder)', app)
        self.assertIn('file_moves.available_name(folder, file_moves.suggest_folder(paths))', app)
