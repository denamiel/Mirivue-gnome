import tempfile
import unittest
from pathlib import Path

from mirivue_gtk4.clipboard_transfer import (
    encode_files,
    decode_files,
    unique_destination,
    replace_existing_file,
)


class ClipboardTransferTests(unittest.TestCase):
    def test_cut_round_trip_with_spaces_and_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / 'été 1.txt', Path(directory) / 'un dossier']
            self.assertEqual(decode_files(encode_files(paths, True)), (paths, True))

    def test_reject_text_and_ignore_remote_files(self):
        with self.assertRaises(ValueError):
            decode_files(b'/home/test.txt')
        self.assertEqual(
            decode_files(b'copy\nhttps://example.org/file\nfile:///tmp/a\n'), ([Path('/tmp/a')], False)
        )

    def test_rename_conflicting_file_and_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'a.txt').write_text('old')
            (root / 'a — copie.txt').write_text('other')
            (root / 'folder').mkdir()
            self.assertEqual(unique_destination(root / 'a.txt').name, 'a — copie 2.txt')
            self.assertEqual(unique_destination(root / 'folder').name, 'folder — copie')

    def test_failed_replacement_restores_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'video.mkv'
            target.write_bytes(b'previous')

            def failing_publish():
                raise OSError('no space')

            with self.assertRaises(OSError):
                replace_existing_file(target, failing_publish)
            self.assertEqual(target.read_bytes(), b'previous')
            self.assertEqual(list(Path(directory).iterdir()), [target])

    def test_successful_replacement_discards_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'video.mkv'
            target.write_bytes(b'previous')
            replace_existing_file(target, lambda: target.write_bytes(b'new'))
            self.assertEqual(target.read_bytes(), b'new')
            self.assertEqual(list(Path(directory).iterdir()), [target])


if __name__ == '__main__':
    unittest.main()
