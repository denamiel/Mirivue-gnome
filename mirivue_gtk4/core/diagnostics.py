"""Local diagnostics and bounded failure logs, without telemetry."""

from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler
import os
import platform
import shutil
import sys
from .. import __version__


def state_dir():
    path = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'mirivue-gtk4'
    path.mkdir(parents=True, exist_ok=True)
    return path


def diagnostic_report():
    root = state_dir()
    lines = [
        f'Mirivue GNOME GTK4 {__version__}',
        f'Python : {platform.python_version()}',
        f'Système : {platform.system()} {platform.release()}',
        'Dernier arrêt incomplet : ' + ('oui' if (root / 'session-active').exists() else 'non'),
    ]
    for name in ('ffmpeg', 'ffprobe', 'mediainfo', 'exiftool', 'mkvpropedit', 'mkvextract', 'pactl'):
        lines.append(f'{name} : {shutil.which(name) or "indisponible"}')
    logfile = root / 'mirivue.log'
    if logfile.exists():
        lines.extend(
            ('', 'Dernières erreurs locales :', *logfile.read_text(errors='replace').splitlines()[-20:])
        )
    return '\n'.join(lines)


def start_session():
    root = state_dir()
    previous = (root / 'session-active').exists()
    logger = logging.getLogger('mirivue-gtk4')
    logger.setLevel(logging.WARNING)
    if not logger.handlers:
        handler = RotatingFileHandler(root / 'mirivue.log', maxBytes=512 * 1024, backupCount=2)
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
    if previous:
        logger.warning('Démarrage après un arrêt incomplet.')
    (root / 'session-active').write_text(str(os.getpid()))
    old_hook = sys.excepthook

    def record(type_, value, traceback):
        logger.error('Erreur inattendue', exc_info=(type_, value, traceback))
        old_hook(type_, value, traceback)

    sys.excepthook = record
    return root / 'session-active'


def finish_session(marker):
    marker.unlink(missing_ok=True)
