"""First-original provenance and metadata publication with disposable files."""
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mirivue_gtk4.core import backup_policy as policy, media_tags
from mirivue_gtk4.core.extensions import fingerprint


class BackupPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'été audio.wav'
        self.path.write_bytes(b'initial audio')

    def edit(self, title='edited', cancelled=lambda: False):
        row = SimpleNamespace(path=self.path, file_signature=fingerprint(self.path))
        def write(path, changes):
            path.write_bytes(changes['title'].encode())
        with patch.object(media_tags, 'write_audio', side_effect=write), \
             patch('mirivue_gtk4.core.media.audio_tags', return_value=({'title': title}, None)):
            return media_tags.safe_edit(row, {'title': title}, 'audio', cancelled=cancelled)

    def test_successive_edits_keep_first_original_and_update_provenance(self):
        first = self.edit('first')
        second = self.edit('second')
        self.assertEqual(first, second)
        self.assertEqual(Path(first).read_bytes(), b'initial audio')
        self.assertEqual(self.path.read_bytes(), b'second')
        backup, marker = policy._names(self.path)
        data = json.loads(marker.read_text())
        self.assertEqual(data['current'], policy._signature(self.path))
        self.assertEqual(data['original'], policy._signature(backup))
        self.assertEqual(list(self.path.parent.glob('*.mirivue-original')), [backup])

    def test_same_content_after_copy_or_remount_does_not_depend_on_inode(self):
        backup = Path(self.edit('first'))
        replacement = self.path.with_name('replacement')
        shutil.copy2(self.path, replacement)
        os.replace(replacement, self.path)
        self.edit('second')
        self.assertEqual(backup.read_bytes(), b'initial audio')

    def test_replaced_current_file_is_refused_without_overwriting_anything(self):
        backup = Path(self.edit())
        self.path.write_bytes(b'other content')
        with self.assertRaises(ValueError):
            self.edit('new')
        self.assertEqual(self.path.read_bytes(), b'other content')
        self.assertEqual(backup.read_bytes(), b'initial audio')

    def test_modified_original_and_unknown_records_are_refused(self):
        backup, _marker = policy._names(self.path)
        backup.write_bytes(b'unrecognized')
        with self.assertRaises(ValueError):
            self.edit()
        self.assertEqual(backup.read_bytes(), b'unrecognized')
        backup.unlink()
        self.edit()
        backup.write_bytes(b'user modification')
        with self.assertRaises(ValueError):
            self.edit('again')
        self.assertEqual(backup.read_bytes(), b'user modification')

    def test_existing_legacy_backups_are_preserved_and_not_adopted(self):
        legacy = Path(str(self.path) + '.mirivue-original-abcdef')
        legacy.write_bytes(b'older backup')
        backup = Path(self.edit())
        self.assertEqual(legacy.read_bytes(), b'older backup')
        self.assertEqual(policy.legacy_backups(self.path), [legacy])
        self.assertEqual(backup.read_bytes(), b'initial audio')

    def test_failure_to_publish_discards_only_new_unchanged_reservation(self):
        replace = os.replace
        def fail(source, target):
            if Path(target) == self.path:
                raise OSError('simulated publication failure')
            return replace(source, target)
        with patch.object(media_tags.os, 'replace', side_effect=fail):
            with self.assertRaises(OSError):
                self.edit()
        self.assertEqual(self.path.read_bytes(), b'initial audio')
        self.assertFalse(any(path.exists() for path in policy._names(self.path)))
        backup = Path(self.edit('first'))
        with patch.object(media_tags.os, 'replace', side_effect=fail):
            with self.assertRaises(OSError):
                self.edit('second')
        self.assertEqual(self.path.read_bytes(), b'first')
        self.assertEqual(backup.read_bytes(), b'initial audio')
        policy.reserve_backup(self.path)  # Existing provenance still valid.

    def test_cancellation_during_reservation_preserves_source_and_old_backups(self):
        with self.assertRaises(InterruptedError):
            policy.reserve_backup(self.path, lambda: True)
        self.assertEqual(self.path.read_bytes(), b'initial audio')
        self.assertFalse(any(path.exists() for path in policy._names(self.path)))
        backup, _new = policy.reserve_backup(self.path)
        self.assertEqual(backup.read_bytes(), b'initial audio')

    def test_disabled_backup_still_does_not_create_files(self):
        row = SimpleNamespace(path=self.path, file_signature=fingerprint(self.path))
        with patch.object(media_tags, 'write_audio', side_effect=lambda p, _c: p.write_bytes(b'edit')), \
             patch('mirivue_gtk4.core.media.audio_tags', return_value=({'title': 'edit'}, None)):
            self.assertEqual(media_tags.safe_edit(row, {'title': 'edit'}, 'audio', backup=False), '')
        self.assertFalse(any(path.exists() for path in policy._names(self.path)))

    def test_post_publication_tracking_failure_keeps_media_original_and_blocks_next_edit(self):
        write_record = policy._write_record
        calls = []
        def write(marker, data):
            calls.append(None)
            if len(calls) == 2:
                raise OSError('simulated record failure')
            return write_record(marker, data)
        with patch.object(policy, '_write_record', side_effect=write), self.assertLogs('mirivue-gtk4', level='WARNING'):
            backup = Path(self.edit())
        self.assertEqual(self.path.read_bytes(), b'edited')
        self.assertEqual(backup.read_bytes(), b'initial audio')
        with self.assertRaises(ValueError):
            self.edit('again')

    def test_real_xmp_edits_preserve_first_existing_sidecar_only(self):
        companion = self.path.with_suffix(self.path.suffix + '.xmp')
        media_tags.write_xmp(companion, {'title': 'original title'})
        def row():
            return SimpleNamespace(path=self.path, file_signature=fingerprint(self.path),
                                   companion_signature=fingerprint(companion))
        first = media_tags.safe_edit(row(), {'title': 'first'}, 'xmp')
        second = media_tags.safe_edit(row(), {'title': 'second'}, 'xmp')
        self.assertEqual(first, second)
        self.assertEqual(media_tags.read_xmp(Path(first))['title'], 'original title')
        self.assertEqual(media_tags.read_xmp(companion)['title'], 'second')
        self.assertEqual(self.path.read_bytes(), b'initial audio')
