"""Single translation module: French source strings, English catalog (en.json).

Only user-facing text goes through tr()/trf(). Internal identifiers, file
modes, tag names and column keys are plain strings and must never be wrapped.
"""

import json, os
from pathlib import Path
from functools import lru_cache

CATALOG = json.loads(Path(__file__).with_name('en.json').read_text())
language = 'auto'


def tr(text):
    locale = (
        language
        if language != 'auto'
        else (
            os.environ.get('LANGUAGE')
            or os.environ.get('LC_ALL')
            or os.environ.get('LC_MESSAGES')
            or os.environ.get('LANG')
            or 'en'
        )
    )
    return text if locale.lower().startswith('fr') else CATALOG.get(text, text)


def trf(text, *values):
    """Translate, then replace the \\x1fN\\x1f placeholders with values."""
    text = tr(text)
    for i, value in enumerate(values):
        text = text.replace('\x1f' + str(i) + '\x1f', str(value))
    return text


@lru_cache(maxsize=1)
def clock_settings():
    from gi.repository import Gio
    source = Gio.SettingsSchemaSource.get_default()
    schema = source.lookup('org.gnome.desktop.interface', True) if source else None
    return Gio.Settings.new_full(schema, None, None) if schema else None


def date_text(timestamp_ns, style='simple'):
    """GLib regional dates; Mirivue preference is separate from Nautilus.

    Follows Nautilus's documented simple/detailed distinction. Nautilus's
    internal ICU formatter is not a public GTK/GIO API; this uses GLib.
    """
    if timestamp_ns is None:
        return '—'
    from gi.repository import GLib
    try:
        value = GLib.DateTime.new_from_unix_local(int(timestamp_ns // 1_000_000_000))
        if value is None:
            return '—'
    except (ValueError, OverflowError):
        return '—'
    settings = clock_settings()
    clock = '%I:%M %p' if settings and settings.get_string('clock-format') == '12h' else '%H:%M'
    if style == 'detailed':
        return value.format('%x ' + ('%I:%M:%S %p' if '%p' in clock else '%H:%M:%S'))
    today = GLib.DateTime.new_now_local()
    stamp = (value.get_year(), value.get_month(), value.get_day_of_month())
    yesterday = today.add_days(-1)
    if stamp == (today.get_year(), today.get_month(), today.get_day_of_month()):
        return tr('Aujourd’hui') + ' ' + value.format(clock)
    if stamp == (yesterday.get_year(), yesterday.get_month(), yesterday.get_day_of_month()):
        return tr('Hier') + ' ' + value.format(clock)
    return value.format('%x')


def size_text(value):
    if tr('Nom') != 'Name':
        return str(value)
    text = str(value)
    for old, new in [('Kio', 'KiB'), ('Mio', 'MiB'), ('Gio', 'GiB'), ('Tio', 'TiB'), (' o', ' B')]:
        text = text.replace(old, new)
    return text
