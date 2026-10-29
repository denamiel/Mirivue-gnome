import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

from mirivue_gtk4 import i18n
from mirivue_gtk4.backend import State
from mirivue_gtk4.core.extensions import apply_renames
from mirivue_gtk4.core.metadata import basic_entry
from mirivue_gtk4.core.panel_status import summarize
from mirivue_gtk4.core import archive_backend
from mirivue_gtk4.core.associated import find_associated
from mirivue_gtk4.core.undo import UndoManager
from mirivue_gtk4.core.diagnostics import diagnostic_report
from mirivue_gtk4.core.renaming import prepare_names


class ParityTests(unittest.TestCase):
    """These checks use the French source labels, whatever the system language."""

    def setUp(self):
        self._previous_language = i18n.language
        i18n.language = 'fr'

    def tearDown(self):
        i18n.language = self._previous_language

    def test_panel_status_matches_folder_and_file_counts_without_zero_errors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'folder').mkdir()
            (root / 'one.txt').write_bytes(b'a' * 2048)
            rows = [basic_entry(root / 'folder', True), basic_entry(root / 'one.txt')]
            text = summarize(rows)
            self.assertIn('1 dossier', text)
            self.assertIn('1 fichier', text)
            self.assertIn('2.0 Kio', text)
            self.assertNotIn('erreur', text)
            rows[1].error = 'Failure'
            self.assertIn('1 erreur', summarize(rows))
            self.assertIn('Sélection', summarize(rows, rows[:1]))

    def test_rename_chain_skips_correct_name_and_moves_others(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('001.txt', '002.txt', '003.txt'):
                (root / name).write_text(name)
            rows = [basic_entry(root / name) for name in ('001.txt', '002.txt', '003.txt')]
            plans = prepare_names(rows, ['001.txt', '003.txt', '004.txt'])
            self.assertEqual(len(plans), 2)
            self.assertFalse(any(plan.issue for plan in plans))
            renamed, errors = apply_renames(plans)
            self.assertFalse(errors)
            self.assertEqual(len(renamed), 2)
            self.assertEqual((root / '003.txt').read_text(), '002.txt')
            self.assertEqual((root / '004.txt').read_text(), '003.txt')

    def test_external_conflict_does_not_block_other_renames(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('one.txt', 'two.txt', 'taken.txt'):
                (root / name).write_text(name)
            rows = [basic_entry(root / name) for name in ('one.txt', 'two.txt')]
            plans = prepare_names(rows, ['taken.txt', 'renamed.txt'])
            renamed, errors = apply_renames(plans)
            self.assertEqual(len(errors), 1)
            self.assertIn(root / 'two.txt', renamed)
            self.assertEqual((root / 'taken.txt').read_text(), 'taken.txt')
            self.assertEqual((root / 'renamed.txt').read_text(), 'two.txt')

    def test_old_column_profile_keeps_duration_and_hides_media_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'settings.json').write_text('{"columns":[0,1,15,36],"profiles":{"Tout":[0,1,15,36]}}')
            settings = State(root).settings
            self.assertEqual(settings['columns'], [0, 1, 2])
            self.assertEqual(settings['profiles']['Tout'], [0, 1, 2])

    def test_archive_browsing_and_selected_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / 'example.zip'
            target = root / 'out'
            target.mkdir()
            with ZipFile(archive, 'w') as writer:
                writer.writestr('first/one.txt', 'one')
                writer.writestr('second/two.txt', 'two')
            self.assertEqual(len(archive_backend.list_entries(archive)), 2)
            output = archive_backend.extract(archive, target, selected=['first/one.txt'])
            self.assertEqual(output, [target / 'first'])
            self.assertEqual((target / 'first/one.txt').read_text(), 'one')
            self.assertFalse((target / 'second').exists())

    def test_archive_rejects_escape_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / 'out'
            target.mkdir()
            archive = root / 'unsafe.zip'
            with ZipFile(archive, 'w') as writer:
                writer.writestr('../escape.txt', 'bad')
            with self.assertRaises(ValueError):
                archive_backend.extract(archive, target)
            self.assertFalse((root / 'escape.txt').exists())
            with ZipFile(archive, 'w') as writer:
                writer.writestr('safe.txt', 'new')
            (target / 'safe.txt').write_text('old')
            with self.assertRaises(FileExistsError):
                archive_backend.extract(archive, target)
            self.assertEqual((target / 'safe.txt').read_text(), 'old')

    def test_create_zip_and_tar_gzip_round_trip(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'folder'
            source.mkdir()
            (source / 'file.txt').write_text('contenu')
            for format, suffix in [('zip', '.zip'), ('tar.gz', '.tar.gz')]:
                archive = root / ('test' + suffix)
                archive_backend.create([source], archive, format)
                output = root / ('out-' + format)
                output.mkdir()
                archive_backend.extract(archive, output)
                self.assertEqual((output / 'folder/file.txt').read_text(), 'contenu')
                with self.assertRaises(FileExistsError):
                    archive_backend.create([source], archive, format)

    def test_create_archive_rejects_links_and_cleans_cancelled_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            file = root / 'one.txt'
            file.write_text('one')
            link = root / 'link.txt'
            link.symlink_to(file)
            with self.assertRaises(ValueError):
                archive_backend.create([link], root / 'link.zip')
            with self.assertRaises(InterruptedError):
                archive_backend.create([file], root / 'cancel.zip', cancelled=lambda: True)
            self.assertFalse((root / 'cancel.zip').exists())
            self.assertFalse(any(root.glob('.mirivue-archive-*')))

    def test_associated_subtitles_are_found_without_unrelated_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ('film.mkv', 'film.fr.srt', 'film.nfo', 'other.srt'):
                (root / name).touch()
            names = {path.name for path in find_associated([root / 'film.mkv'])}
            self.assertEqual(names, {'film.fr.srt', 'film.nfo'})

    def test_undo_copy_and_redo_while_preserving_newer_edits(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source.txt'
            target = root / 'target.txt'
            source.write_text('original')
            target.write_text('original')
            manager = UndoManager()
            self.assertTrue(manager.record(source, target, True))
            manager.undo()
            self.assertFalse(target.exists())
            manager.redo()
            self.assertEqual(target.read_text(), 'original')
            target.write_text('changed')
            with self.assertRaises(ValueError):
                manager.undo()
            self.assertEqual(target.read_text(), 'changed')

    def test_undo_move_refuses_occupied_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source.txt'
            target = root / 'target.txt'
            target.write_text('moved')
            manager = UndoManager()
            self.assertTrue(manager.record(source, target, False))
            source.write_text('new')
            with self.assertRaises(FileExistsError):
                manager.undo()
            self.assertEqual(source.read_text(), 'new')
            self.assertEqual(target.read_text(), 'moved')

    def test_undo_directory_move_and_empty_folder_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'old'
            target = root / 'new'
            target.mkdir()
            (target / 'inside.txt').write_text('keep')
            manager = UndoManager()
            self.assertTrue(manager.record(source, target, False))
            manager.undo()
            self.assertEqual((source / 'inside.txt').read_text(), 'keep')
            manager.redo()
            self.assertEqual((target / 'inside.txt').read_text(), 'keep')
            (target / 'inside.txt').write_text('modified')
            with self.assertRaises(ValueError):
                manager.undo()
            folder = root / 'empty'
            folder.mkdir()
            self.assertTrue(manager.record_new_folder(folder))
            manager.undo()
            self.assertFalse(folder.exists())
            manager.redo()
            self.assertTrue(folder.is_dir())
            (folder / 'added').touch()
            with self.assertRaises(OSError):
                manager.undo()

    def test_undo_copy_with_xmp_companion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source.mp4'
            target = root / 'target.mp4'
            source.write_text('video')
            (root / 'source.mp4.xmp').write_text('metadata')
            from mirivue_gtk4.core.file_moves import move_one

            move_one(source, target, copy_only=True)
            manager = UndoManager()
            self.assertTrue(manager.record(source, target, True))
            manager.undo()
            self.assertFalse(target.exists())
            self.assertFalse((root / 'target.mp4.xmp').exists())
            manager.redo()
            self.assertEqual((root / 'target.mp4.xmp').read_text(), 'metadata')

    def test_batch_rename_undo_redo_with_chain_and_xmp(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / 'one.mp4'
            second = root / 'two.mp4'
            third = root / 'three.mp4'
            for path in (first, second, third):
                path.write_text(path.name)
            side = root / 'one.mp4.xmp'
            side.write_text('sidecar')
            renamed, errors = apply_renames(
                prepare_names([basic_entry(first), basic_entry(second)], ['two.mp4', 'four.mp4'])
            )
            self.assertFalse(errors)
            manager = UndoManager()
            self.assertTrue(manager.record_rename(renamed.items()))
            manager.undo()
            self.assertEqual(first.read_text(), 'one.mp4')
            self.assertEqual(second.read_text(), 'two.mp4')
            self.assertEqual(side.read_text(), 'sidecar')
            manager.redo()
            self.assertEqual((root / 'four.mp4').read_text(), 'two.mp4')
            self.assertEqual((root / 'two.mp4.xmp').read_text(), 'sidecar')
            manager.undo()
            third.rename(root / 'four.mp4')
            with self.assertRaises(FileExistsError):
                manager.redo()
            self.assertEqual(first.read_text(), 'one.mp4')
            self.assertEqual((root / 'four.mp4').read_text(), 'three.mp4')

    def test_diagnostic_report_is_local_and_reports_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            from unittest.mock import patch

            with patch.dict('os.environ', {'XDG_STATE_HOME': temporary}):
                report = diagnostic_report()
            self.assertIn('Mirivue GNOME GTK4', report)
            self.assertIn('ffmpeg :', report)


if __name__ == '__main__':
    unittest.main()
