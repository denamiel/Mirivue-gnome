"""Optional routing of this process's playback streams through pactl."""

from ..i18n import tr
import json
import os
import shutil
import subprocess


def _list(kind):
    if not shutil.which('pactl'):
        raise RuntimeError(tr('La sélection de sortie requiert pactl.'))
    result = subprocess.run(
        ['pactl', '--format=json', 'list', kind], capture_output=True, text=True, timeout=3, check=True
    )
    values = json.loads(result.stdout)
    if not isinstance(values, list):
        raise ValueError(tr('Réponse audio invalide.'))
    return values


def sinks():
    """Return stable sink names and human-readable device names."""
    return [
        (item['name'], item.get('description') or item['name'])
        for item in _list('sinks')
        if isinstance(item, dict) and isinstance(item.get('name'), str)
    ]


def route(sink, pid=None):
    """Move only playback streams bearing our PID. Never change the default sink."""
    pid = os.getpid() if pid is None else pid
    available = {name for name, _ in sinks()}
    if sink != '@DEFAULT_SINK@' and sink not in available:
        raise ValueError(tr('Cette sortie audio n’est plus disponible.'))
    matched = []
    for item in _list('sink-inputs'):
        if not isinstance(item, dict):
            continue
        props = item.get('properties') or item.get('proplist') or {}
        if not isinstance(props, dict) or str(props.get('application.process.id', '')) != str(pid):
            continue
        index = item.get('index')
        if isinstance(index, int) and index >= 0:
            matched.append(index)
    for index in matched:
        subprocess.run(
            ['pactl', 'move-sink-input', str(index), sink],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
    return len(matched)
