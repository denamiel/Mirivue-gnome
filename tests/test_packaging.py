"""Verify the package identity and preservation of user launchers."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('gnome_transition', ROOT / 'packaging/transition_user_install.py')
transition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transition)


class PackagingTests(unittest.TestCase):
    def test_package_versions_and_portable_desktop_entry(self):
        subprocess.run([sys.executable, str(ROOT / 'packaging/check_release.py')], check=True, capture_output=True)

    def test_confirmed_licence_allows_release_validation(self):
        subprocess.run([sys.executable, str(ROOT / 'packaging/check_release.py'), '--require-license'],
                       check=True, capture_output=True)

    def test_old_launcher_is_backed_up_without_touching_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, state = root / 'data with spaces', root / 'state'
            desktop = data / 'applications' / f'{transition.APP_ID}.desktop'
            desktop.parent.mkdir(parents=True)
            executable = str(data / 'mirivue-gtk4/Lancer.sh').replace(' ', '\\ ')
            content = f'[Desktop Entry]\nExec={executable} %U\nIcon={transition.APP_ID}\n'
            desktop.write_text(content)
            settings = state / 'mirivue-gtk4/settings.json'
            settings.parent.mkdir(parents=True)
            settings.write_text('{"pane_views":{"left":"icons"}}')
            self.assertEqual(transition.transition(data, state), desktop)
            self.assertTrue(desktop.exists())
            saved = transition.transition(data, state, True)
            self.assertFalse(desktop.exists())
            self.assertEqual(saved.read_text(), content)
            self.assertEqual(settings.read_text(), '{"pane_views":{"left":"icons"}}')

    def test_custom_user_launcher_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            desktop = root / 'applications' / f'{transition.APP_ID}.desktop'
            desktop.parent.mkdir()
            desktop.write_text('[Desktop Entry]\nExec=/my/custom/program\n')
            with self.assertRaises(ValueError):
                transition.transition(root, root / 'state', True)
            self.assertTrue(desktop.exists())
