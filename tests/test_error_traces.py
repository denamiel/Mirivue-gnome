"""Errors that are deliberately tolerated still leave a trace in mirivue.log."""

import ast
import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1] / 'mirivue_gtk4'


class ErrorTraceTests(unittest.TestCase):
    def test_no_silent_catch_all(self):
        """No `except Exception: pass` (or bare except) left in the application."""
        silent = []
        for path in sorted(ROOT.rglob('*.py')):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ExceptHandler):
                    broad = node.type is None or (
                        isinstance(node.type, ast.Name) and node.type.id == 'Exception'
                    )
                    if broad and len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        silent.append(f'{path.relative_to(ROOT)}:{node.lineno}')
        self.assertEqual(silent, [])

    def test_remote_cleanup_failure_is_logged(self):
        from mirivue_gtk4.core import gio_backend

        class BrokenTarget:
            def query_info(self, *args):
                raise OSError('volume déconnecté')

            def get_uri(self):
                return 'sftp://serveur/.mirivue-stage'

        with self.assertLogs('mirivue-gtk4', 'WARNING') as logs:
            gio_backend._remove_own_tree(BrokenTarget())
        self.assertIn('sftp://serveur/.mirivue-stage', logs.output[0])

    def test_log_lines_are_dated(self):
        from mirivue_gtk4.core import diagnostics

        logger = logging.getLogger('mirivue-gtk4')
        saved = logger.handlers[:]
        logger.handlers.clear()
        try:
            with (
                tempfile.TemporaryDirectory() as temp,
                mock.patch.object(diagnostics, 'state_dir', return_value=Path(temp)),
                mock.patch('sys.excepthook'),
            ):
                diagnostics.start_session()
                logger.warning('essai de trace')
                for handler in logger.handlers:
                    handler.flush()
                line = (Path(temp) / 'mirivue.log').read_text().strip().splitlines()[-1]
                for handler in logger.handlers:
                    handler.close()
            self.assertRegex(line, r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} WARNING essai de trace$')
        finally:
            logger.handlers[:] = saved


if __name__ == '__main__':
    unittest.main()
