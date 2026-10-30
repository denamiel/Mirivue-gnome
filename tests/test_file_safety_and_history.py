import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mirivue_gtk4.core.file_safety import check_removal
from mirivue_gtk4.core.undo import UndoManager, BatchRecord


class SafetyAndHistoryTests(unittest.TestCase):
    def test_mount_root_and_nested_mount_are_refused_before_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / 'mounted'
            nested.mkdir()
            (nested / 'keep.txt').write_text('keep')
            with patch('mirivue_gtk4.core.file_safety.os.path.ismount', side_effect=lambda p: Path(p) == nested):
                with self.assertRaises(ValueError):
                    check_removal(nested)
                with self.assertRaises(ValueError):
                    check_removal(root, recursive=True)
            self.assertEqual((nested / 'keep.txt').read_text(), 'keep')
            link = root / 'link'
            link.symlink_to(nested, target_is_directory=True)
            with patch('mirivue_gtk4.core.file_safety.os.path.ismount', return_value=True):
                check_removal(link, recursive=True)

    def test_one_action_undoes_and_redoes_complete_copy_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = UndoManager()
            pairs = []
            for name in ('one', 'two'):
                source, target = root / name, root / (name + '-copy')
                source.write_text(name)
                shutil.copy2(source, target)
                manager.record(source, target, True, group='one-copy')
                pairs.append((source, target))
            self.assertEqual(len(manager.undo_stack), 1)
            self.assertIsInstance(manager.undo_stack[-1], BatchRecord)
            manager.undo()
            self.assertTrue(all(source.exists() and not target.exists() for source, target in pairs))
            manager.redo()
            self.assertEqual([target.read_text() for _, target in pairs], ['one', 'two'])

    def test_changed_second_copy_preserves_entire_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = UndoManager()
            for name in ('one', 'two'):
                source, target = root / name, root / (name + '-copy')
                source.write_text(name)
                shutil.copy2(source, target)
                manager.record(source, target, True, group='copy')
            (root / 'two-copy').write_text('new user data')
            with self.assertRaises(ValueError):
                manager.undo()
            self.assertTrue((root / 'one-copy').exists())
            self.assertEqual((root / 'two-copy').read_text(), 'new user data')
