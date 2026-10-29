import tempfile
import unittest
from pathlib import Path

from mirivue_gtk4.backend import MediaService
from mirivue_gtk4.core import metadata
from mirivue_gtk4.core.library import decode_row, encode_row


class TotalDurationTests(unittest.TestCase):
    def test_duration_updates_its_column_without_replacing_folder_size(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'one.mp3').write_bytes(b'first')
            (folder / 'two.mp3').write_bytes(b'second')

            class State:
                def __init__(self):
                    self.saved = None

                def put(self, row):
                    self.saved = row

            state = State()
            service = MediaService(state)
            folder_row = metadata.basic_entry(folder, True)
            folder_row.values[1] = '2 éléments'

            def inspect(path, cancelled):
                if path == folder:
                    return folder_row
                row = metadata.basic_entry(path)
                row.sort_values[2] = 65 if path.name == 'one.mp3' else 55
                return row

            service.inspect = inspect
            result = service._analyze(folder, 'total', lambda: False, lambda *_: None)
            self.assertEqual(result.values[2], '00:02:00')
            self.assertEqual(result.sort_values[2], 120)
            self.assertEqual(result.values[15], '')
            self.assertEqual(result.values[1], '2 éléments')
            self.assertIs(state.saved, result)

    def test_previous_folder_total_migrates_to_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            row = metadata.basic_entry(folder, True)
            row.total_duration = 120
            row.values[15] = '00:02:00'
            row.sort_values[15] = 120
            restored = decode_row(encode_row(row))
            self.assertEqual(restored.values[2], '00:02:00')
            self.assertEqual(restored.sort_values[2], 120)
            self.assertEqual(restored.values[15], '')


if __name__ == '__main__':
    unittest.main()
