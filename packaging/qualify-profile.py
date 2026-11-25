"""Check that an installed GNOME package restores a profile saved by the previous version."""

import json
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk

from mirivue_gtk4 import __version__, places, session
from mirivue_gtk4.app import MirivueWindow
from mirivue_gtk4.backend import State

action, expected_version = sys.argv[1:]
assert __version__ == expected_version, (__version__, expected_version)
Gtk.init()
app = Adw.Application(application_id="org.pdenams.Mirivue.Upgrade", flags=Gio.ApplicationFlags.NON_UNIQUE)
app.register(None)
state = State()
profile = Path.home() / "profile-fixture.json"

if action == "prepare":
    one, two = [Path.home() / name for name in ("Médias un", "Médias deux")]
    one.mkdir()
    two.mkdir()
    state.settings.update(startup="session", hide_on_start=False, thumbnails=False)
    bookmarks = [(one.as_uri(), "Montage"), (two.as_uri(), "Archives")]
    places.write_bookmarks(bookmarks)
    window = MirivueWindow(app, state=state, restore_session=False)
    window.present()
    window.new_tab(one)
    window.toggle_split()
    window.new_tab(two)
    state.settings["tab_session"] = session.snapshot(window)
    state.save()
    profile.write_text(json.dumps({"settings": state.settings, "bookmarks": bookmarks}))
    window.shutdown()
elif action == "verify":
    expected = json.loads(profile.read_text())
    assert state.settings == expected["settings"], "Des réglages ont changé."
    assert [list(item) for item in places.read_bookmarks()] == expected["bookmarks"], "Les favoris ont changé."
    window = MirivueWindow(app, state=state)
    window.present()
    context = GLib.MainContext.default()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        while context.pending():
            context.iteration(False)
        if session.snapshot(window) == expected["settings"]["tab_session"] and not window.active.pending_location:
            break
        time.sleep(0.025)
    else:
        raise AssertionError("Les onglets ou le volet actif n’ont pas été retrouvés.")
    window.shutdown()
else:
    raise ValueError(action)
print(f"{expected_version} — {action} : réglages, favoris et onglets vérifiés", flush=True)
