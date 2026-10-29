from .i18n import tr
import sys
from . import __version__

if '--version' in sys.argv:
    print(__version__)
    raise SystemExit(0)
if '--check-dependencies' in sys.argv:
    import gi

    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Gtk, Adw, Gio

    if (Gtk.get_major_version(), Gtk.get_minor_version()) < (4, 12):
        raise SystemExit(tr('GTK 4.12 ou plus récent est requis.'))
    if (Adw.get_major_version(), Adw.get_minor_version()) < (1, 4):
        raise SystemExit(tr('libadwaita 1.4 ou plus récent est requis.'))
    print('PyGObject, GTK4, libadwaita et GIO : OK')
    raise SystemExit(0)
if '--smoke-test' in sys.argv:
    import gi

    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Gtk, Adw
    from .app import MirivueGtkApplication, MirivueWindow
    from .pane import Pane

    Gtk.init()
    assert issubclass(MirivueWindow, Adw.ApplicationWindow)
    assert issubclass(Pane, Gtk.Box)
    assert isinstance(MirivueGtkApplication(), Adw.Application)
    print('Composants GTK4 : OK')
    raise SystemExit(0)
if '--window-smoke-test' in sys.argv:
    # Explicit post-install check: keep settings and media cache in a temporary
    # directory, and close the real window once GTK has mapped it.
    import os
    import tempfile
    from pathlib import Path
    import gi

    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    from gi.repository import Gtk, GLib, Gio
    from .backend import State
    from .app import MirivueGtkApplication

    with tempfile.TemporaryDirectory(prefix='mirivue-window-check-') as temporary:
        for name in ('XDG_STATE_HOME', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME'):
            location = Path(temporary) / name
            location.mkdir()
            os.environ[name] = str(location)
        state = State()
        state.settings.update(
            startup='custom', startup_path=temporary, reuse_window=False, minimize_to_tray=False
        )
        state.save()
        app = MirivueGtkApplication()
        app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
        succeeded = [False]

        def mapped(window):
            succeeded[0] = bool(window.panes and window.active and window.active.location)
            if succeeded[0]:
                print('Fenêtre GTK4 affichée : OK', flush=True)
            GLib.idle_add(lambda: (window.shutdown(), False)[1])

        app.connect('window-added', lambda _app, window: window.connect('map', lambda *_: mapped(window)))
        result = app.run([])
        raise SystemExit(0 if result == 0 and succeeded[0] else 1)
if '--diagnostic' in sys.argv:
    from .core.diagnostics import diagnostic_report

    print(diagnostic_report())
    raise SystemExit(0)
from .app import main
from .core.diagnostics import start_session, finish_session

marker = start_session()
result = main()
finish_session(marker)
raise SystemExit(result)
