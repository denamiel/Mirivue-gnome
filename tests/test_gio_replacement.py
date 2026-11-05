"""Cancellation and progress of explicit overwrites, without a desktop session."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from mirivue_gtk4.core import gio_backend

class Cancellable:
    def __init__(self): self.event = threading.Event()
    def cancel(self): self.event.set()
    def is_cancelled(self): return self.event.is_set()

class TestReplacement(unittest.TestCase):
    def gio(self):
        return patch.object(gio_backend, '_gio', return_value=SimpleNamespace(
            Cancellable=Cancellable, FileCopyFlags=SimpleNamespace(OVERWRITE=1, NOFOLLOW_SYMLINKS=2)))

    def test_copy_and_move_report_progress(self):
        for move in (False, True):
            calls, progress = [], []
            def operation(target, flags, cancellable, callback, data):
                calls.append((target, flags, cancellable))
                callback(4, 10, None)
            source = SimpleNamespace(copy=operation, move=operation)
            with self.gio():
                gio_backend.replace(source, 'target', move=move,
                                    progress=lambda done, total: progress.append((done,total)))
            self.assertEqual(progress, [(4,10)])
            self.assertEqual(calls[0][:2], ('target',3))
            self.assertIsInstance(calls[0][2], Cancellable)

    def test_cancel_without_any_progress_reaches_backend(self):
        for move in (False, True):
            requested = threading.Event()
            def operation(target, flags, cancellable, callback, data):
                requested.set()
                self.assertTrue(cancellable.event.wait(2), 'backend never received cancellation')
                raise RuntimeError('native cancellation')
            with self.gio(), self.assertRaises(InterruptedError):
                gio_backend.replace(SimpleNamespace(copy=operation,move=operation), 'target',
                                    move=move, cancelled=requested.is_set)

    def test_already_cancelled_does_not_start(self):
        with self.gio(), self.assertRaises(InterruptedError):
            gio_backend.replace(object(), 'target', cancelled=lambda: True)

    def test_io_failure_is_not_retried_or_reported_as_cancellation(self):
        calls = []
        def operation(*args):
            calls.append(True)
            raise OSError('disk failure')
        with self.gio(), self.assertRaisesRegex(OSError, 'disk failure'):
            gio_backend.replace(SimpleNamespace(copy=operation), 'target')
        self.assertEqual(calls, [True])
