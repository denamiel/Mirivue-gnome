"""Single translation module: core messages are translated, identifiers are not."""

import ast
import json
import re
import tempfile
import unittest
from pathlib import Path

from mirivue_gtk4 import i18n
from mirivue_gtk4.core import file_moves

ROOT = Path(__file__).resolve().parents[1] / 'mirivue_gtk4'
CATALOG = json.loads((ROOT / 'en.json').read_text())
PLACEHOLDER = re.compile('\x1f\\d\x1f')


def core_translation_calls():
    for path in sorted((ROOT / 'core').glob('*.py')):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ('tr', 'trf')
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                yield path.name, node.lineno, node.args[0].value


def untranslated_messages(source):
    """(line, text) of multi-word messages given to raise/notify/report/progress without tr()."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            arguments = node.exc.args
        elif isinstance(node, ast.Call) and (
            getattr(node.func, 'attr', None) or getattr(node.func, 'id', None)
        ) in (
            'notify',
            'report',
            'progress',
        ):
            arguments = node.args
        else:
            continue
        for argument in arguments:
            if any(
                isinstance(n, ast.Call) and getattr(n.func, 'id', None) in ('tr', 'trf')
                for n in ast.walk(argument)
            ):
                continue  # translated message, possibly followed by technical detail
            words = [
                n.value
                for n in ast.walk(argument)
                if isinstance(n, ast.Constant) and isinstance(n.value, str) and ' ' in n.value.strip()
            ]
            if words:
                found.append((node.lineno, words[0]))
    return found


class I18nTests(unittest.TestCase):
    def setUp(self):
        self._previous = i18n.language

    def tearDown(self):
        i18n.language = self._previous

    def test_there_is_only_one_translation_module(self):
        self.assertFalse((ROOT / 'core' / 'i18n.py').exists())

    def test_core_error_follows_interface_language(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / 'absent'
            for language, expected in (
                ('fr', 'La source n’existe plus.'),
                ('en', 'The source no longer exists.'),
            ):
                i18n.language = language
                with self.assertRaises(OSError) as context:
                    file_moves.validate_target(missing, Path(temp) / 'cible')
                self.assertEqual(str(context.exception), expected)

    def test_trf_translates_then_substitutes(self):
        i18n.language = 'en'
        text = i18n.trf('Restauration de \x1f0\x1f impossible : \x1f1\x1f', 'a.mkv', 'refus')
        self.assertEqual(text, 'Could not restore a.mkv: refus')

    def test_every_core_message_has_an_english_translation(self):
        # Pure layout templates such as '\x1f0\x1f × \x1f1\x1f' contain no words to translate.
        missing = [
            f'{name}:{line}: {text!r}'
            for name, line, text in core_translation_calls()
            if text not in CATALOG and sum(c.isalpha() for c in PLACEHOLDER.sub('', text)) >= 3
        ]
        self.assertEqual(missing, [])

    def test_core_never_translates_technical_strings(self):
        technical = re.compile(r'^[\w./:+-]*$')  # single tokens: modes, keys, tags, paths
        offenders = [
            f'{name}:{line}: {text!r}'
            for name, line, text in core_translation_calls()
            if technical.match(text) and text not in CATALOG
        ]
        self.assertEqual(offenders, [])

    def test_status_bar_size_unit_follows_language(self):
        from types import SimpleNamespace

        from mirivue_gtk4.core.panel_status import summarize

        row = SimpleNamespace(is_dir=False, sort_values=[None, 2048], error=None)
        i18n.language = 'en'
        self.assertIn('KiB', summarize([row]))
        self.assertNotIn('Kio', summarize([row]))
        i18n.language = 'fr'
        self.assertIn('Kio', summarize([row]))

    def test_no_untranslated_user_message(self):
        """Strict rule: any text of several words given to an exception, notify(),
        report() or progress() goes through tr() or trf(), whatever its wording."""
        offenders = []
        for path in sorted(ROOT.rglob('*.py')):
            for line, text in untranslated_messages(path.read_text()):
                offenders.append(f'{path.relative_to(ROOT)}:{line}: {text!r}')
        self.assertEqual(offenders, [])

    def test_strict_rule_detects_and_accepts_the_right_cases(self):
        missed_in_0_6_20 = "raise ValueError('Type de fichier distant non pris en charge.')"
        self.assertEqual(len(untranslated_messages(missed_in_0_6_20)), 1)
        self.assertEqual(len(untranslated_messages("self.notify(f'{n} fichiers copiés')")), 1)
        self.assertEqual(untranslated_messages("raise ValueError(tr('Nom invalide.'))"), [])
        self.assertEqual(untranslated_messages("raise ValueError(tr('Échec : ') + detail)"), [])
        self.assertEqual(untranslated_messages("raise KeyError('width')"), [])

    def test_placeholders_are_preserved_in_catalog(self):
        broken = [
            k for k, v in CATALOG.items() if sorted(PLACEHOLDER.findall(k)) != sorted(PLACEHOLDER.findall(v))
        ]
        self.assertEqual(broken, [])


if __name__ == '__main__':
    unittest.main()
