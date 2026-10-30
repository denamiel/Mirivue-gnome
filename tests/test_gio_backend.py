"""Exercise the transfer policy without requiring a running GNOME session."""

import shutil
import tempfile
import unittest
import sys
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from mirivue_gtk4 import i18n
from mirivue_gtk4.core import gio_backend
from mirivue_gtk4.backend import DEFAULTS, State


class FakeGio:
    class FileType:
        DIRECTORY = 1
        REGULAR = 2
        SYMBOLIC_LINK = 3

    class FileQueryInfoFlags:
        NONE = 0
        NOFOLLOW_SYMLINKS = 1

    class FileCopyFlags:
        NONE = 0
        NO_FALLBACK_FOR_MOVE = 1
        NOFOLLOW_SYMLINKS = 2

    class Cancellable:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

        def is_cancelled(self):
            return self.cancelled


class FakeInfo:
    def __init__(self, path):
        self.path = path

    def get_file_type(self):
        return FakeGio.FileType.DIRECTORY if self.path.is_dir() else FakeGio.FileType.REGULAR

    def get_size(self):
        return self.path.stat().st_size

    def get_attribute_uint64(self, key):
        return self.path.stat().st_mtime_ns // 1_000_000_000

    def get_attribute_uint32(self, key):
        return self.path.stat().st_mtime_ns // 1000 % 1_000_000

    def get_attribute_string(self, key):
        return None


class FakeGLib:
    class Error(Exception):
        def matches(self, domain, code):
            return domain == 'gio' and code == 'would-recurse'

    class UserDirectory:
        DIRECTORY_DOCUMENTS = 0

    @staticmethod
    def get_home_dir():
        return '/home/tester'

    @staticmethod
    def get_user_special_dir(kind):
        return '/home/tester/Documents' if kind == 0 else None


class FakeFile:
    def __init__(self, path):
        self.path = Path(path)

    def get_path(self):
        return str(self.path)

    def get_uri(self):
        return self.path.as_uri()

    def get_basename(self):
        return self.path.name

    def get_child(self, name):
        return FakeFile(self.path / name)

    def query_exists(self, _):
        return self.path.exists()

    def equal(self, other):
        return self.path == other.path

    def has_prefix(self, other):
        return other.path in self.path.parents

    def query_info(self, *_):
        return FakeInfo(self.path)

    def enumerate_children(self, *_):
        children = iter(sorted(self.path.iterdir()))

        class Enumerator:
            def next_file(self, _):
                child = next(children, None)
                if child is None:
                    return None
                info = FakeInfo(child)
                info.get_name = lambda: child.name
                info.get_display_name = lambda: child.name
                return info

            def close(self, _):
                pass

        return Enumerator()

    def make_directory(self, _):
        self.path.mkdir()

    def delete(self, _):
        self.path.rmdir() if self.path.is_dir() else self.path.unlink()

    def copy(self, dest, flags, cancellable, progress, data):
        shutil.copyfile(self.path, dest.path)
        progress(self.path.stat().st_size, self.path.stat().st_size, None)

    def move(self, dest, flags, cancellable, progress, data):
        if dest.path.exists():
            raise FileExistsError()
        self.path.rename(dest.path)

    def trash(self, _):
        self.path.unlink()


class GioBackendTests(unittest.TestCase):
    """Error messages are checked in French, whatever the system language."""

    def setUp(self):
        self._previous_language = i18n.language
        i18n.language = 'fr'

    def tearDown(self):
        i18n.language = self._previous_language

    def test_folders_first_default_preserves_saved_preference(self):
        import json

        self.assertFalse(DEFAULTS['folders_first'])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'settings.json').write_text(json.dumps({'folders_first': True}))
            self.assertTrue(State(root).settings['folders_first'])

    def test_local_icon_uses_file_backend_result(self):
        marker = object()

        class Info:
            def get_icon(self):
                return marker

            def get_attribute_string(self, _):
                return None

            def get_file_type(self):
                return FakeGio.FileType.REGULAR

        class File:
            def query_info(self, attributes, *_):
                self.attributes = attributes
                return Info()

        file = File()

        class Gio(FakeGio):
            class File:
                @staticmethod
                def new_for_path(_path):
                    return file

        with (
            patch.object(gio_backend, '_gio', return_value=Gio),
            patch.object(gio_backend, '_glib', return_value=FakeGLib),
        ):
            self.assertIs(gio_backend.local_icon(Path('/tmp/video.bin')), marker)
        self.assertIn('standard::content-type', file.attributes)
        self.assertIn('standard::icon', file.attributes)

    def test_special_folder_and_custom_icon_follow_gnome_metadata(self):
        _marker = object()

        class Info:
            def __init__(self, custom):
                self.custom = custom

            def get_icon(self):
                return 'generic-folder'

            def get_attribute_string(self, _):
                return self.custom

            def get_file_type(self):
                return FakeGio.FileType.DIRECTORY

        class File:
            def __init__(self, path):
                self.path = path

            def query_info(self, *_):
                return Info('file:///tmp/custom.svg' if self.path.endswith('/custom') else None)

        class Gio(FakeGio):
            File = SimpleNamespace(new_for_path=lambda path: File(path), new_for_uri=lambda uri: uri)
            FileIcon = SimpleNamespace(new=lambda uri: ('custom', uri))
            ThemedIcon = SimpleNamespace(new=lambda name: ('themed', name))

        with (
            patch.object(gio_backend, '_gio', return_value=Gio),
            patch.object(gio_backend, '_glib', return_value=FakeGLib),
        ):
            self.assertEqual(gio_backend.local_icon('/home/tester/Documents'), ('themed', 'folder-documents'))
            self.assertEqual(gio_backend.local_icon('/tmp/custom'), ('custom', 'file:///tmp/custom.svg'))

    def test_enumeration_keeps_transfer_shape_and_can_include_icons(self):
        marker = object()

        class Info:
            def get_name(self):
                return 'file.pdf'

            def get_display_name(self):
                return 'file.pdf'

            def get_file_type(self):
                return FakeGio.FileType.REGULAR

            def get_size(self):
                return 12

            def get_icon(self):
                return marker

        class Enumerator:
            def __init__(self):
                self.once = False

            def next_file(self, _):
                if self.once:
                    return None
                self.once = True
                return Info()

            def close(self, _):
                pass

        class Folder:
            def enumerate_children(self, attributes, *_):
                self.attributes = attributes
                return Enumerator()

            def get_child(self, name):
                return name

        folder = Folder()
        with patch.object(gio_backend, '_gio', return_value=FakeGio):
            self.assertEqual(len(gio_backend.browse(folder)[0]), 4)
            self.assertIs(gio_backend.browse(folder, include_icons=True)[0][4], marker)
        self.assertIn('standard::icon', folder.attributes)

    def test_copy_preserves_source_and_refuses_existing_target(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(gio_backend, '_gio', return_value=FakeGio),
        ):
            root = Path(temporary)
            source = root / 'source'
            dest = root / 'dest'
            dest.mkdir()
            source.write_text('content')
            results = gio_backend.transfer([FakeFile(source)], FakeFile(dest))
            self.assertEqual(len(results), 1)
            self.assertEqual((dest / 'source').read_text(), 'content')
            self.assertEqual(source.read_text(), 'content')
            with self.assertRaises(FileExistsError):
                gio_backend.transfer([FakeFile(source)], FakeFile(dest))
            self.assertEqual((dest / 'source').read_text(), 'content')

    def test_move_uses_gio_fallback_and_does_not_trash_a_regular_file(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(gio_backend, '_gio', return_value=FakeGio),
        ):
            root = Path(temporary)
            source = root / 'source'
            dest = root / 'dest'
            dest.mkdir()
            source.write_text('content')
            with patch.object(FakeFile, 'trash', side_effect=AssertionError('unexpected trash')):
                results = gio_backend.transfer([FakeFile(source)], FakeFile(dest), move=True)
            self.assertEqual(results[0][2], '')
            self.assertFalse(source.exists())
            self.assertEqual((dest / 'source').read_text(), 'content')

    def test_recursive_move_removes_verified_source_without_trashing(self):
        class RecursiveFile(FakeFile):
            def get_child(self, name):
                return RecursiveFile(self.path / name)

            def move(self, dest, flags, cancellable, progress, data):
                if self.path.is_dir() and self.path.name == 'source':
                    raise FakeGLib.Error('would recurse')
                super().move(dest, flags, cancellable, progress, data)

        class RecursiveGio(FakeGio):
            IOErrorEnum = SimpleNamespace(WOULD_RECURSE='would-recurse')
            io_error_quark = staticmethod(lambda: 'gio')

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(gio_backend, '_gio', return_value=RecursiveGio),
            patch.object(gio_backend, '_glib', return_value=FakeGLib),
        ):
            root = Path(temporary)
            source = root / 'source'
            (source / 'nested').mkdir(parents=True)
            (source / 'nested' / 'film.txt').write_text('content')
            dest = root / 'dest'
            dest.mkdir()
            with patch.object(RecursiveFile, 'trash', side_effect=AssertionError('unexpected trash')):
                results = gio_backend.transfer([RecursiveFile(source)], RecursiveFile(dest), move=True)
            self.assertEqual(results[0][2], '')
            self.assertFalse(source.exists())
            self.assertEqual((dest / 'source' / 'nested' / 'film.txt').read_text(), 'content')

    def test_recursive_move_keeps_source_if_it_changes_during_copy(self):
        class RecursiveFile(FakeFile):
            def get_child(self, name):
                return RecursiveFile(self.path / name)

            def move(self, dest, *args):
                if self.path.is_dir() and self.path.name == 'source':
                    raise FakeGLib.Error('would recurse')
                super().move(dest, *args)

        class RecursiveGio(FakeGio):
            IOErrorEnum = SimpleNamespace(WOULD_RECURSE='would-recurse')
            io_error_quark = staticmethod(lambda: 'gio')

        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.object(gio_backend, '_gio', return_value=RecursiveGio),
            patch.object(gio_backend, '_glib', return_value=FakeGLib),
        ):
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            (source / 'film.txt').write_text('old')
            dest = root / 'dest'
            dest.mkdir()
            original = gio_backend._copy_tree

            def changed(*args):
                original(*args)
                (source / 'film.txt').write_text('changed')

            with patch.object(gio_backend, '_copy_tree', side_effect=changed):
                with self.assertRaisesRegex(IOError, 'source a changé'):
                    gio_backend.transfer([RecursiveFile(source)], RecursiveFile(dest), move=True)
            self.assertEqual((source / 'film.txt').read_text(), 'changed')
            self.assertFalse((dest / 'source').exists())


if __name__ == '__main__':
    unittest.main()
