"""Find broken runtime names and retired actions without importing GTK."""

import builtins
import symtable
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'mirivue_gtk4'


class CodeHygieneTests(unittest.TestCase):
    def test_no_unresolved_python_globals(self):
        errors = []
        for path in ROOT.rglob('*.py'):
            symbols = symtable.symtable(path.read_text(), str(path), 'exec')
            defined = {
                s.get_name()
                for s in symbols.get_symbols()
                if s.is_assigned() or s.is_imported() or s.is_namespace()
            }

            def check(table):
                for symbol in table.get_symbols():
                    name = symbol.get_name()
                    if (
                        symbol.is_global()
                        and symbol.is_referenced()
                        and name not in defined
                        and name not in dir(builtins)
                        and name not in {'__file__', '__name__', '__package__'}
                    ):
                        errors.append(f'{path.relative_to(ROOT)}: {name}')
                for child in table.get_children():
                    check(child)

            check(symbols)
        self.assertEqual(errors, [])

    def test_retired_quality_and_bitrate_actions_are_absent(self):
        app = (ROOT / 'app.py').read_text()
        self.assertNotIn("'quality':", app)
        self.assertNotIn("'bitrate':", app)
        self.assertNotIn("'persist':", app)
        self.assertNotIn('Détails de qualité…', app)
        self.assertFalse((ROOT / 'core/deep_scan.py').exists())
        self.assertFalse((ROOT / 'core/estimated_quality.py').exists())

    def test_help_does_not_advertise_retired_tools_or_wheel_controls(self):
        french = (ROOT / 'help.fr.txt').read_text()
        english = (ROOT / 'help.en.txt').read_text()
        for obsolete in (
            'Qualité estimée évalue',
            'Débit calculé',
            'la molette verticale règle le volume',
            'Estimated Quality gives',
            'vertical wheel adjusts volume',
        ):
            self.assertNotIn(obsolete, french + english)
        self.assertNotIn('.responsive import', (ROOT / 'core/library.py').read_text())


if __name__ == '__main__':
    unittest.main()
