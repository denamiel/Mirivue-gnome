import json
import tempfile
import unittest
from pathlib import Path

from mirivue_gtk4.backend import State


class ViewPreferencesTests(unittest.TestCase):
    def test_restores_each_pane_view_without_changing_other_preferences(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'settings.json').write_text(
                json.dumps(
                    {'pane_views': {'left': 'icons', 'right': 'bad'}, 'folders_first': True, 'hidden': True}
                )
            )
            state = State(root)
            self.assertEqual(state.settings['pane_views'], {'left': 'icons', 'right': 'details'})
            self.assertTrue(state.settings['folders_first'])
            self.assertTrue(state.settings['hidden'])
            state.save()
            self.assertEqual(State(root).settings['pane_views'], {'left': 'icons', 'right': 'details'})

    def test_retired_monitor_switch_is_ignored_without_changing_other_choices(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            selected = {'monitor_external': False, 'folders_first': True, 'hidden': True,
                        'pane_views': {'left': 'icons', 'right': 'details'}}
            (root / 'settings.json').write_text(json.dumps(selected))
            state = State(root)
            self.assertNotIn('monitor_external', state.settings)
            for key in ('folders_first', 'hidden', 'pane_views'):
                self.assertEqual(state.settings[key], selected[key])
            state.save()
            saved = json.loads((root / 'settings.json').read_text())
            self.assertNotIn('monitor_external', saved)
            for key in ('folders_first', 'hidden', 'pane_views'):
                self.assertEqual(saved[key], selected[key])

    def test_does_not_reference_nautilus_view_or_sort_preferences(self):
        source = (Path(__file__).resolve().parents[1] / 'mirivue_gtk4' / 'app.py').read_text()
        self.assertNotIn('org.gnome.nautilus.preferences', source)
        self.assertNotIn('default-folder-viewer', source)
        self.assertNotIn('sort-directories-first', source)
