import tempfile
import unittest
from pathlib import Path
from gi.repository import Gio
from mirivue_gtk4.core.directory_merge import merge
from mirivue_gtk4.core.undo import UndoManager


class DirectoryMergeTests(unittest.TestCase):
    def test_move_merges_nested_folders_and_undo_redo_keeps_existing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root / 'source', root / 'target'
            (source / 'nested').mkdir(parents=True)
            (target / 'nested').mkdir(parents=True)
            (source / 'a.mkv').write_text('video')
            (source / 'a.mkv.xmp').write_text('metadata')
            (source / 'nested' / 'b.txt').write_text('b')
            (target / 'nested' / 'keep.txt').write_text('keep')
            manager = UndoManager()
            records, _changed, warnings, available = merge(Gio.File.new_for_path(str(source)),
                Gio.File.new_for_path(str(target)), False, lambda: False,
                lambda _s, _t, _replace, directory: 'merge' if directory else 'skip', manager, True)
            self.assertTrue(available)
            self.assertEqual(warnings, [])
            self.assertFalse(source.exists())
            for record in records:
                manager.record_prepared(record, group='merge')
            manager.undo()
            self.assertEqual((source / 'a.mkv').read_text(), 'video')
            self.assertEqual((source / 'a.mkv.xmp').read_text(), 'metadata')
            self.assertEqual((source / 'nested' / 'b.txt').read_text(), 'b')
            self.assertEqual((target / 'nested' / 'keep.txt').read_text(), 'keep')
            manager.redo()
            self.assertFalse(source.exists())
            self.assertEqual((target / 'a.mkv.xmp').read_text(), 'metadata')

    def test_copy_conflict_is_explicit_and_never_replaces_when_renamed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root / 'source', root / 'target'
            source.mkdir(); target.mkdir()
            (source / 'a.txt').write_text('new')
            (target / 'a.txt').write_text('old')
            manager = UndoManager()
            called = []
            def decide(s, t, replace, directory):
                called.append((s.get_basename(), t.get_basename(), replace, directory))
                return 'rename'
            records, _changed, errors, available = merge(Gio.File.new_for_path(str(source)),
                Gio.File.new_for_path(str(target)), True, lambda: False, decide, manager, True)
            self.assertEqual(called, [('a.txt', 'a.txt', True, False)])
            self.assertEqual(errors, [])
            self.assertTrue(available)
            self.assertEqual((target / 'a.txt').read_text(), 'old')
            self.assertEqual((target / 'a (2).txt').read_text(), 'new')
            for record in records: manager.record_prepared(record, group='merge')
            manager.undo()
            self.assertFalse((target / 'a (2).txt').exists())
            self.assertEqual((source / 'a.txt').read_text(), 'new')
            self.assertEqual((target / 'a.txt').read_text(), 'old')

    def test_cancel_preserves_conflict_and_completed_moves_remain_undoable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target = root / 'source', root / 'target'
            source.mkdir(); target.mkdir()
            (source / 'a.txt').write_text('a')
            (source / 'b.txt').write_text('b new')
            (target / 'b.txt').write_text('b old')
            manager = UndoManager()
            records, _changed, errors, available = merge(Gio.File.new_for_path(str(source)),
                Gio.File.new_for_path(str(target)), False, lambda: False,
                lambda *_: 'cancel', manager, True)
            self.assertTrue(errors)
            self.assertTrue(available)
            self.assertEqual((target / 'b.txt').read_text(), 'b old')
            self.assertEqual((source / 'b.txt').read_text(), 'b new')
            for record in records: manager.record_prepared(record, group='partial-merge')
            manager.undo()
            self.assertEqual((source / 'a.txt').read_text(), 'a')
