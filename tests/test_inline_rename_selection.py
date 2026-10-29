"""F2 selects the file stem without changing the batch rename workflow."""

import unittest

from mirivue_gtk4.core.renaming import single_name_selection_end


class InlineRenameSelectionTests(unittest.TestCase):
    def test_files_select_only_the_name_before_the_last_extension(self):
        for name, selected in [
            ('film.mkv', 'film'),
            ('archive.tar.gz', 'archive.tar'),
            ('été.mp4', 'été'),
            ('.cache', '.cache'),
            ('README', 'README'),
        ]:
            with self.subTest(name=name):
                self.assertEqual(name[: single_name_selection_end(name)], selected)

    def test_folder_name_is_selected_in_full(self):
        self.assertEqual(single_name_selection_end('dossier.photos', True), len('dossier.photos'))
