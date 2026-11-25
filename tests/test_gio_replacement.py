"""Cancellation, progress and publication of explicit GIO overwrites."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mirivue_gtk4.core import gio_backend


class Cancellable:
    def __init__(self):
        self.event = threading.Event()

    def cancel(self):
        self.event.set()

    def is_cancelled(self):
        return self.event.is_set()


class TestReplacement(unittest.TestCase):
    def gio(self):
        return patch.object(gio_backend, '_gio', return_value=SimpleNamespace(
            Cancellable=Cancellable, FileCopyFlags=SimpleNamespace(
                OVERWRITE=1, NOFOLLOW_SYMLINKS=2, NO_FALLBACK_FOR_MOVE=4)))

    def test_copy_and_move_report_progress(self):
        for move in (False, True):
            with self.subTest(move=move):
                calls, progress = [], []

                def native_move(target, flags, cancellable, callback, data):
                    calls.append((target, flags, cancellable))
                    if callback is not None:
                        callback(4, 10, None)

                def copy(source, stage, cancellable, callback):
                    callback(4, 10)

                stage = SimpleNamespace(move=native_move)
                parent = SimpleNamespace(get_child=lambda name: stage)
                target = SimpleNamespace(get_parent=lambda: parent)
                source = SimpleNamespace(move=native_move)
                with self.gio(), patch.object(gio_backend, '_copy_tree', side_effect=copy):
                    gio_backend.replace(source, target, move=move,
                                        progress=lambda done, total: progress.append((done, total)))
                self.assertEqual(progress, [(4, 10)])
                self.assertEqual(len(calls), 1)
                self.assertEqual(calls[0][:2], (target, 7))
                self.assertIsInstance(calls[0][2], Cancellable)

    def test_cancel_without_any_progress_reaches_backend(self):
        requested = threading.Event()

        def copy(source, target, cancellable, progress):
            requested.set()
            self.assertTrue(cancellable.event.wait(2), 'backend never received cancellation')
            raise RuntimeError('native cancellation')

        parent = SimpleNamespace(get_child=lambda name: object())
        target = SimpleNamespace(get_parent=lambda: parent)
        with self.gio(), patch.object(gio_backend, '_copy_tree', side_effect=copy), \
                patch.object(gio_backend, '_remove_own_tree') as cleanup, self.assertRaises(InterruptedError):
            gio_backend.replace(object(), target, cancelled=requested.is_set)
        cleanup.assert_called_once()

    def test_already_cancelled_does_not_start(self):
        with self.gio(), self.assertRaises(InterruptedError):
            gio_backend.replace(object(), object(), cancelled=lambda: True)

    def test_interrupted_copy_preserves_target_and_removes_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'destination'
            destination.write_bytes(b'original')

            def copy(source, stage, cancellable, progress):
                stage.write_bytes(b'partial')
                raise OSError('disk failure')

            parent = SimpleNamespace(get_child=lambda name: Path(directory) / name)
            target = SimpleNamespace(get_parent=lambda: parent)
            with self.gio(), patch.object(gio_backend, '_copy_tree', side_effect=copy) as copy_tree, \
                    patch.object(gio_backend, '_remove_own_tree', side_effect=Path.unlink), \
                    self.assertRaisesRegex(OSError, 'disk failure'):
                gio_backend.replace(object(), target)
            copy_tree.assert_called_once()
            self.assertEqual(destination.read_bytes(), b'original')
            self.assertEqual(list(Path(directory).iterdir()), [destination])
