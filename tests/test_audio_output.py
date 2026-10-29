import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mirivue_gtk4.core import audio_output


class AudioOutputTests(unittest.TestCase):
    def test_only_this_process_stream_is_moved_and_default_is_unchanged(self):
        calls = []
        responses = {
            'sinks': [
                {'name': 'speakers', 'description': 'Haut-parleurs'},
                {'name': 'headphones', 'description': 'Casque'},
            ],
            'sink-inputs': [
                {'index': 12, 'properties': {'application.process.id': '1234'}},
                {'index': 13, 'properties': {'application.process.id': '9999'}},
            ],
        }

        def run(args, **kwargs):
            calls.append(args)
            payload = responses.get(args[-1], [])
            return SimpleNamespace(stdout=json.dumps(payload))

        with (
            patch.object(audio_output.shutil, 'which', return_value='/usr/bin/pactl'),
            patch.object(audio_output.subprocess, 'run', side_effect=run),
        ):
            self.assertEqual(audio_output.sinks()[1], ('headphones', 'Casque'))
            self.assertEqual(audio_output.route('headphones', pid=1234), 1)
            with self.assertRaises(ValueError):
                audio_output.route('unplugged', pid=1234)
        self.assertIn(['pactl', 'move-sink-input', '12', 'headphones'], calls)
        self.assertFalse(any('13' in call or 'set-default-sink' in call for call in calls))


if __name__ == '__main__':
    unittest.main()
