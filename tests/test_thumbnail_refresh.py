"""A thumbnail from an older file revision must not replace the visible one."""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    from mirivue_gtk4.pane import Pane
except ImportError:
    Pane = None


@unittest.skipIf(Pane is None, 'PyGObject is required for GTK view tests')
class ThumbnailRefreshTests(unittest.TestCase):
    def test_late_enrichment_keeps_newer_thumbnail(self):
        path = Path('/tmp/mirivue-thumbnail-test.png')
        item = SimpleNamespace(thumbnail='current.png', thumbnail_visible=True)
        pane = SimpleNamespace(
            search_recursive_active=False,
            generation=2,
            closed=False,
            items={str(path): item},
            window=SimpleNamespace(state=SimpleNamespace(settings={'thumbnails': True})),
        )
        old = SimpleNamespace(file_signature=(1, 2, 3, 4), is_dir=False)
        with patch('mirivue_gtk4.pane.metadata.fingerprint', return_value=(1, 2, 3, 5)):
            self.assertFalse(Pane.enriched(pane, 2, path, old, 'obsolete.png'))
        self.assertEqual(item.thumbnail, 'current.png')


if __name__ == '__main__':
    unittest.main()
