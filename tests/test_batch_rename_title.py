"""Word capitalization follows KDE and preserves file extensions."""

from pathlib import Path
from types import SimpleNamespace
import unittest

from mirivue_gtk4.core.renaming import batch_names


class BatchRenameTitleTests(unittest.TestCase):
    def test_capitalization_normalizes_words_and_preserves_extensions(self):
        names = [
            'ma VIDEO de paris.mp4',
            'ÉTÉ  À-PARIS_AVEC  ÉLODIE.MP4',
            'Déjà Correct.txt',
            'SANS EXTENSION',
            '.CACHE',
        ]
        rows = [SimpleNamespace(path=Path(name), is_dir=False) for name in names]
        expected = [
            'Ma Video De Paris.mp4',
            'Été  À-Paris_Avec  Élodie.MP4',
            'Déjà Correct.txt',
            'Sans Extension',
            '.cache',
        ]
        self.assertEqual(batch_names(rows, 'title'), expected)
        normalized = [SimpleNamespace(path=Path(name), is_dir=False) for name in expected]
        self.assertEqual(batch_names(normalized, 'title'), expected)

    def test_folder_has_no_extension_to_preserve(self):
        row = SimpleNamespace(path=Path('MES VIDÉOS.ÉTÉ'), is_dir=True)
        self.assertEqual(batch_names([row], 'title'), ['Mes Vidéos.été'])
