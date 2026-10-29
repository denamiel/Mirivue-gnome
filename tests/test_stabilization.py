import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from mirivue_gtk4.core.menu_audit import missing_actions


MODULE = Path(__file__).resolve().parents[1] / 'packaging/install_gnome.py'
spec = importlib.util.spec_from_file_location('gnome_install', MODULE)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class Menu:
    def __init__(self, action=None, children=()):
        self.action = action
        self.children = children

    def get_n_items(self):
        return 1

    def get_item_attribute_value(self, index, key, _type):
        if key != 'action' or not self.action:
            return None
        return type('Variant', (), {'get_string': lambda _: self.action})()

    def get_item_link(self, index, kind):
        return self.children[0] if kind == 'section' and self.children else None


class StabilizationTests(unittest.TestCase):
    def test_menu_audit_follows_sections(self):
        model = Menu(children=[Menu(action='win.unregistered')])
        self.assertEqual(missing_actions(model, lambda name: None), ['win.unregistered'])

    def test_install_keeps_previous_version_and_rollback_swaps_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / 'data'
            data.mkdir()
            original = data / 'mirivue-gtk4'
            original.mkdir()
            (original / 'old-marker').write_text('previous')
            for suffix, name in [
                ('scalable/apps', 'org.pdenams.Mirivue.Gtk4.svg'),
                ('256x256/apps', 'org.pdenams.Mirivue.Gtk4.png'),
            ]:
                target = data / 'icons/hicolor' / suffix / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('old icon')
            archive = root / 'update.tar.gz'
            with tarfile.open(archive, 'w:gz') as output:
                for name, content in {
                    'Lancer.sh': '#!/bin/sh\n',
                    'Verifier-installation-GNOME.sh': '#!/bin/bash\n',
                    'mirivue_gtk4/__main__.py': '',
                    'mirivue_gtk4/__init__.py': f'__version__ = "{installer.VERSION}"\n',
                    'icons/hicolor/scalable/apps/org.pdenams.Mirivue.Gtk4.svg': '<svg/>',
                    'icons/hicolor/256x256/apps/org.pdenams.Mirivue.Gtk4.png': 'png',
                }.items():
                    encoded = content.encode()
                    info = tarfile.TarInfo(name)
                    info.size = len(encoded)
                    output.addfile(info, io.BytesIO(encoded))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with (
                patch.dict(os.environ, {'XDG_DATA_HOME': str(data)}),
                patch.object(installer, 'running', return_value=False),
                patch.object(installer, 'check_dependencies'),
                patch.object(installer, 'smoke'),
            ):
                installer.install(archive, digest)
                self.assertEqual((data / 'mirivue-gtk4-previous/old-marker').read_text(), 'previous')
                self.assertTrue((original / 'Lancer.sh').is_file())
                self.assertTrue(os.access(original / 'Verifier-installation-GNOME.sh', os.X_OK))
                installer.install(archive, digest, rollback=True)
                self.assertEqual((original / 'old-marker').read_text(), 'previous')
                self.assertTrue((data / 'mirivue-gtk4-previous/Lancer.sh').is_file())

    def test_failed_metadata_restores_application_and_previous_backup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / 'data'
            data.mkdir()
            app = data / 'mirivue-gtk4'
            app.mkdir()
            (app / 'current').touch()
            previous = data / 'mirivue-gtk4-previous'
            previous.mkdir()
            (previous / 'earlier').touch()
            archive = root / 'update.tar.gz'
            with tarfile.open(archive, 'w:gz') as output:
                for name, content in {
                    'Lancer.sh': '',
                    'mirivue_gtk4/__main__.py': '',
                    'mirivue_gtk4/__init__.py': f'__version__ = "{installer.VERSION}"',
                }.items():
                    encoded = content.encode()
                    info = tarfile.TarInfo(name)
                    info.size = len(encoded)
                    output.addfile(info, io.BytesIO(encoded))
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with (
                patch.dict(os.environ, {'XDG_DATA_HOME': str(data)}),
                patch.object(installer, 'running', return_value=False),
                patch.object(installer, 'check_dependencies'),
                patch.object(installer, 'smoke'),
                patch.object(installer, 'metadata', side_effect=OSError('failure')),
            ):
                with self.assertRaises(OSError):
                    installer.install(archive, digest)
            self.assertTrue((app / 'current').exists())
            self.assertTrue((previous / 'earlier').exists())


if __name__ == '__main__':
    unittest.main()
