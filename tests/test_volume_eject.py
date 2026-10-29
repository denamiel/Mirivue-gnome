"""Each sidebar eject button acts on its own volume with its own action."""

import unittest
from types import SimpleNamespace

import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk  # noqa: E402

from mirivue_gtk4 import i18n  # noqa: E402
from mirivue_gtk4.app import MirivueWindow  # noqa: E402


class FakeMount:
    def __init__(self, name, ejectable):
        self.name = name
        self.ejectable = ejectable

    def can_eject(self):
        return self.ejectable

    def can_unmount(self):
        return True


class VolumeEjectButtonTests(unittest.TestCase):
    def setUp(self):
        Gtk.init()
        self.previous = i18n.language
        i18n.language = 'fr'

    def tearDown(self):
        i18n.language = self.previous

    def test_each_button_keeps_its_own_volume_and_action(self):
        calls = []
        window = SimpleNamespace(unmount_volume=lambda mount, eject: calls.append((mount.name, eject)))
        usb = FakeMount('clé USB', ejectable=True)
        share = FakeMount('partage réseau', ejectable=False)
        # Same order as the sidebar loop: the last volume used to win.
        usb_button = MirivueWindow.volume_eject_button(window, usb)
        share_button = MirivueWindow.volume_eject_button(window, share)
        usb_button.emit('clicked')
        share_button.emit('clicked')
        self.assertEqual(calls, [('clé USB', True), ('partage réseau', False)])
        self.assertEqual(usb_button.get_tooltip_text(), 'Éjecter')
        self.assertEqual(share_button.get_tooltip_text(), 'Démonter')


if __name__ == '__main__':
    unittest.main()
