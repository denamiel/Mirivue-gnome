"""Migration and file operations imported from the newer, simpler release."""

import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mirivue_gtk4.backend import State
from mirivue_gtk4.core import permissions
from mirivue_gtk4.core.library import decode_row, encode_row
from mirivue_gtk4.core.metadata import basic_entry
from mirivue_gtk4.core.new_document import create_text_file


class SimplificationTests(unittest.TestCase):
    def test_retired_status_setting_does_not_change_other_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'state'
            root.mkdir()
            (root / 'settings.json').write_text(
                json.dumps({'show_status': False, 'split': True, 'preview': True, 'columns': [0, 1, 2, 14]})
            )
            settings = State(root).settings
            self.assertNotIn('show_status', settings)
            self.assertTrue(settings['split'])
            self.assertTrue(settings['preview'])
            self.assertEqual(settings['columns'], [0, 1, 2, 14])

    def test_legacy_quality_removed_but_labels_and_metadata_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'video.mkv'
            path.touch()
            row = basic_entry(path)
            row.is_video = True
            row.quality_score = 87
            row.quality_version = 'estimated-quality-v3'
            row.values[12] = '87/100'
            row.personal_label = 'À conserver'
            row.media_tags = {'title': 'Titre personnel'}
            serialized = encode_row(row)
            self.assertIsNone(serialized['quality_score'])
            restored = decode_row(serialized)
            self.assertIsNone(restored.quality_score)
            self.assertEqual(restored.values[12], '')
            self.assertEqual(restored.personal_label, row.personal_label)
            self.assertEqual(restored.media_tags, row.media_tags)
            state = State(Path(tmp) / 'settings')
            self.assertTrue(state.settings['quality_removed'])
            self.assertTrue(state.put(row))
            self.assertIsNone(state.read(path).quality_score)
            self.assertEqual(state.read(path).personal_label, row.personal_label)

    def test_existing_text_file_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            existing = folder / 'notes.txt'
            existing.write_text('important')
            with self.assertRaises(FileExistsError):
                create_text_file(folder, 'notes.txt')
            self.assertEqual(existing.read_text(), 'important')
            self.assertEqual(create_text_file(folder, 'nouveau.txt').read_bytes(), b'')
            with self.assertRaises(ValueError):
                create_text_file(folder, '../hors.txt')

    def test_upgrade_scrubs_existing_cache_without_touching_other_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'state'
            state = State(root)
            path = Path(tmp) / 'video.mkv'
            path.touch()
            row = basic_entry(path)
            row.personal_label = 'Favori'
            row.media_tags = {'title': 'Test'}
            state.put(row)
            with state.db() as db:
                raw = json.loads(db.execute('SELECT row FROM cache WHERE path=?', (str(path),)).fetchone()[0])
                raw.update(quality_score=99, quality_version='estimated-quality-v3')
                raw['values'][12] = '99/100'
                raw['sort_values'][12] = 99
                db.execute('UPDATE cache SET row=? WHERE path=?', (json.dumps(raw), str(path)))
            settings = json.loads(state.path.read_text())
            settings.pop('quality_removed')
            settings.update(quality_profile='custom', save_bitrate=True)
            state.path.write_text(json.dumps(settings))
            upgraded = State(root)
            self.assertNotIn('quality_profile', upgraded.settings)
            self.assertNotIn('save_bitrate', upgraded.settings)
            restored = upgraded.read(path)
            self.assertEqual(restored.personal_label, 'Favori')
            self.assertEqual(restored.media_tags, {'title': 'Test'})
            with upgraded.db() as db:
                stored = json.loads(
                    db.execute('SELECT row FROM cache WHERE path=?', (str(path),)).fetchone()[0]
                )
            self.assertIsNone(stored['quality_score'])
            self.assertEqual(stored['values'][12], '')

    def test_permission_change_uses_gio_and_checks_actual_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'notes.txt'
            path.touch()
            before = path.stat()
            identity = (before.st_dev, before.st_ino)

            class File:
                def set_attribute_uint32(self, key, mode, flags, cancellable):
                    self.assert_called_with(key, flags, cancellable)
                    path.chmod(mode)

                def assert_called_with(self, key, flags, cancellable):
                    if (key, flags, cancellable) != ('unix::mode', 1, None):
                        raise AssertionError('GIO mode flags')

            class Gio:
                FileQueryInfoFlags = type('Flags', (), {'NOFOLLOW_SYMLINKS': 1})
                File = type('Factory', (), {'new_for_path': staticmethod(lambda _: File())})

            with patch.object(permissions, '_gio', return_value=Gio):
                self.assertEqual(permissions.apply_permissions(path, 0o640, identity), 0o640)
                with self.assertRaises(ValueError):
                    permissions.apply_permissions(path, 0o600, (identity[0], identity[1] + 1))
                link = Path(tmp) / 'link'
                link.symlink_to(path)
                with self.assertRaises(ValueError):
                    permissions.apply_permissions(link, 0o600)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
