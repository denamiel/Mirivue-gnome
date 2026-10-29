import json
import tempfile
import unittest
from pathlib import Path

from mirivue_gtk4.backend import DEFAULTS, State, reorder_toolbar


class ToolbarLayoutTests(unittest.TestCase):
    def test_reorder_keeps_path_anchor_and_moves_across_it(self):
        order = ['home', 'paths', 'split', 'menu']
        self.assertEqual(reorder_toolbar(order, 'menu', 'home'), ['menu', 'home', 'paths', 'split'])
        self.assertEqual(
            reorder_toolbar(order, 'home', 'menu', after=True), ['paths', 'split', 'menu', 'home']
        )
        self.assertEqual(reorder_toolbar(order, 'paths', 'menu'), order)

    def test_drop_can_target_both_sides_of_path_anchor(self):
        order = ['home', 'up', 'paths', 'search', 'menu']
        self.assertEqual(reorder_toolbar(order, 'menu', 'paths'), ['home', 'up', 'menu', 'paths', 'search'])
        self.assertEqual(
            reorder_toolbar(order, 'home', 'paths', after=True), ['up', 'paths', 'home', 'search', 'menu']
        )

    def test_defaults_have_split_and_no_spacers(self):
        self.assertIn('split', DEFAULTS['toolbar_order'])
        self.assertEqual(DEFAULTS['toolbar_order'].count('paths'), 1)
        self.assertFalse(any(key.startswith('space') for key in DEFAULTS['toolbar_order']))

    def test_old_spacers_are_discarded_and_new_command_is_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'settings.json').write_text(
                json.dumps(
                    {
                        'toolbar_order': ['home', 'space1', 'paths', 'menu'],
                        'toolbar_hidden': ['space1', 'paths'],
                    }
                )
            )
            state = State(tmp)
            self.assertNotIn('space1', state.settings['toolbar_order'])
            self.assertIn('split', state.settings['toolbar_order'])
            self.assertNotIn('paths', state.settings['toolbar_hidden'])
            self.assertEqual(state.settings['toolbar_order'].count('paths'), 1)

    def test_fixed_sidebar_actions_are_removed_from_saved_toolbar_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'settings.json').write_text(
                json.dumps(
                    {
                        'toolbar_order': ['back', 'paths', 'search', 'preview', 'menu', 'split'],
                        'toolbar_hidden': ['search', 'menu', 'preview'],
                    }
                )
            )
            state = State(tmp)
            self.assertEqual(state.settings['toolbar_order'][:4], ['back', 'paths', 'preview', 'split'])
            self.assertEqual(state.settings['toolbar_hidden'], ['preview'])
            self.assertNotIn('search', DEFAULTS['toolbar_order'])
            self.assertNotIn('menu', DEFAULTS['toolbar_order'])


if __name__ == '__main__':
    unittest.main()
