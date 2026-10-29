"""Single translation module: French source strings, English catalog (en.json).

Only user-facing text goes through tr()/trf(). Internal identifiers, file
modes, tag names and column keys are plain strings and must never be wrapped.
"""

import json, os
from pathlib import Path

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


def date_text(timestamp_ns):
    from datetime import datetime, timedelta

    if timestamp_ns is None:
        return '—'
    try:
        value = datetime.fromtimestamp(timestamp_ns / 1e9)
    except (OSError, ValueError, OverflowError):
        return '—'
    english = tr('Nom') == 'Name'
    today = datetime.now().date()
    if value.date() == today:
        prefix = 'Today' if english else 'Aujourd’hui'
    elif value.date() == today - timedelta(days=1):
        prefix = 'Yesterday' if english else 'Hier'
    else:
        prefix = value.strftime('%m/%d/%Y' if english else 'le %d/%m/%Y')
    return prefix + (' at ' if english else ' à ') + value.strftime('%H:%M:%S')


def size_text(value):
    if tr('Nom') != 'Name':
        return str(value)
    text = str(value)
    for old, new in [('Kio', 'KiB'), ('Mio', 'MiB'), ('Gio', 'GiB'), ('Tio', 'TiB'), (' o', ' B')]:
        text = text.replace(old, new)
    return text
