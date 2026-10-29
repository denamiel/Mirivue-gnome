'MediaInfo JSON uses seconds, bytes and bits/second (not display strings).'

import logging
from ..i18n import tr, trf

from dataclasses import dataclass, field
from pathlib import Path
import json
import math
from datetime import datetime, timedelta
import subprocess
from .extensions import suggest_extension, fingerprint

EXTENSIONS = set(
    '.mkv .mp4 .m4v .avi .mov .webm .wmv .flv .mpg .mpeg .m2v .ts .mts .m2ts .vob .ogv .3gp .3g2 .divx .asf .mxf .rm .rmvb .f4v .qt'.split()
)
HEADERS = [
    'Nom',
    'Taille',
    'Durée',
    'Résolution',
    'Codec vidéo',
    'FPS',
    'Débit vidéo',
    'HDR/SDR',
    'Codec audio',
    'Canaux',
    'État',
    'Extension suggérée',
    'Qualité estimée',
    '',
    'Date de modification',
    'Durée totale',
    'Débit calculé (comparaison)',
    'Type de média',
    'Titre',
    'Artiste',
    'Album',
    'Piste',
    'Année / date',
    'Genre',
    'Fréquence audio',
    'Débit audio',
    'Date de prise de vue',
    'Mots-clés',
    'Auteur',
    'Format',
    'Profondeur audio (bits)',
    'Artiste de l’album',
    'Disque',
    'Compositeur',
    'Droits d’auteur',
    'Description',
    'Contenu multimédia',
]


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (ValueError, TypeError):
        return None


def quantity(value, units, base):
    if value is None:
        return '—'
    for unit in units[:-1]:
        if value < base:
            return trf('\x1f0\x1f \x1f1\x1f', format(value, '.1f'), unit)
        value /= base
    return trf('\x1f0\x1f \x1f1\x1f', format(value, '.1f'), units[-1])


def duration(value):
    if value is None:
        return '—'
    seconds = round(value)
    return trf(
        '\x1f0\x1f:\x1f1\x1f:\x1f2\x1f',
        format(seconds // 3600, '02'),
        format(seconds // 60 % 60, '02'),
        format(seconds % 60, '02'),
    )


def hdr_label(video):
    hdr = str(video.get('HDR_Format', ''))
    transfer = str(video.get('transfer_characteristics', '')).lower()
    if hdr:
        return hdr
    if '2084' in transfer or 'pq' in transfer:
        return 'HDR (PQ)'
    if 'hlg' in transfer or 'arib' in transfer:
        return 'HDR (HLG)'
    if any(
        (
            token in transfer
            for token in (
                '709',
                '601',
                '470',
                '170m',
                '240m',
                'gamma',
                'srgb',
                '61966',
                '2020',
            )
        )
    ):
        return 'SDR'
    return 'Indéterminé'


@dataclass
class Video:
    path: Path
    values: list = field(default_factory=list)
    sort_values: list = field(default_factory=list)
    error: str = ''
    bitrate_note: str = ''
    bitrate_error: str = ''
    validation_error: str = ''
    validation_status: str = ''
    duplicate_group: int = 0
    preview_dir: str = ''
    analysis_dates: dict = field(default_factory=dict)
    modified_ns: int | None = None
    quality_score: int | None = None
    quality_version: str = ''
    quality_profile_signature: str = ''
    quality_samples: int = 0
    quality_details: dict = field(default_factory=dict)
    quality_note: str = ''
    quality_error: str = ''
    quality_state: str = ''
    hdr_note: str = 'Détection fondée sur les métadonnées de la première piste vidéo. Sans indication fiable, HDR ou SDR ne peut pas être confirmé.'
    suggested_extension: str = ''
    extension_note: str = ''
    file_signature: tuple | None = None
    bitrate_result: tuple | None = None
    bitrate_saved: bool = False
    original_bitrate: float | None = None
    total_duration: float | None = None
    duration_note: str = ''
    is_dir: bool = False
    is_video: bool = True
    container_info: dict = field(default_factory=dict)
    media_type: str = ''
    media_tags: dict = field(default_factory=dict)
    media_technical: dict = field(default_factory=dict)
    media_counts: dict = field(default_factory=dict)
    companion_signature: tuple | None = None
    personal_label: str = ''
    personal_label_color: str = ''
    trash_uri: str = ''
    original_path: str = ''

    def __post_init__(self):
        while len(self.values) < len(HEADERS):
            self.values.append('')
        while len(self.sort_values) < len(HEADERS):
            self.sort_values.append(-1)


def parse(path, document):
    tracks = document.get('media', {}).get('track', [])
    general = next((t for t in tracks if t.get('@type') == 'General'), {})
    video = next((t for t in tracks if t.get('@type') == 'Video'), None)
    audio = [t for t in tracks if t.get('@type') == 'Audio']
    if video is None:
        if any((t.get('@type') in ('Audio', 'Image') for t in tracks)):
            from .media import inspect_media

            return inspect_media(path)
        raise ValueError(tr('Aucune piste vidéo reconnue'))
    size = number(general.get('FileSize'))
    if size is None:
        size = path.stat().st_size
    size = int(size)
    seconds = number(video.get('Duration', general.get('Duration')))
    width, height = (number(video.get('Width')), number(video.get('Height')))
    fps, bitrate = (number(video.get('FrameRate')), number(video.get('BitRate')))
    channels = [number(a.get('Channels')) for a in audio]
    values = [
        path.name,
        quantity(size, ['o', 'Kio', 'Mio', 'Gio', 'Tio'], 1024),
        duration(seconds),
        trf('\x1f0\x1f × \x1f1\x1f', int(width), int(height)) if width and height else '—',
        video.get('Format', '—'),
        trf('\x1f0\x1f', format(fps, '.3f')).rstrip('0').rstrip('.') if fps is not None else '—',
        quantity(bitrate, ['bit/s', 'kbit/s', 'Mbit/s', 'Gbit/s'], 1000),
        hdr_label(video),
        ' / '.join((a.get('Format', 'Inconnu') for a in audio)) or 'Aucun',
        ' / '.join((str(int(c)) if c is not None else '—' for c in channels)) or '—',
        'OK',
    ]
    sort = [
        path.name.casefold(),
        size,
        seconds,
        width * height if width and height else None,
        str(values[4]).casefold(),
        fps,
        bitrate,
        str(values[7]).casefold(),
        str(values[8]).casefold(),
        channels[0] if channels else None,
        'OK',
    ]
    suggested, note = suggest_extension(general, path.suffix)
    label = (
        suggested + (' (correcte)' if path.suffix.lower() == suggested else ' (à corriger)')
        if suggested
        else 'Indéterminée'
    )
    values.extend([label, '', '', ''])
    sort.extend([label.casefold(), -1, -1, -1])
    try:
        signature = fingerprint(path)
    except OSError:
        signature = None
    tags = {}
    for key, names in {
        'title': ('Title',),
        'description': ('Description',),
        'author': ('Performer', 'Artist', 'WrittenBy'),
        'copyright': ('Copyright',),
        'keywords': ('Keywords',),
        'date_taken': ('Recorded_Date', 'Date_Recorded', 'Date'),
    }.items():
        value = next((general.get(name) for name in names if general.get(name)), None)
        if value is not None:
            tags[key] = str(value)
    primary_audio = audio[0] if audio else {}
    technical = {
        'width': width,
        'height': height,
        'sample_rate': number(primary_audio.get('SamplingRate')),
        'bitrate': number(primary_audio.get('BitRate')),
        'bits': number(primary_audio.get('BitDepth')),
        'channels': channels[0] if channels else None,
    }
    return Video(
        path,
        values,
        [v if v is not None else -1 for v in sort],
        suggested_extension=suggested,
        extension_note=note,
        file_signature=signature,
        original_bitrate=bitrate,
        container_info={k: general.get(k, '') for k in ('Format', 'Format_Profile', 'CodecID')},
        media_type='video',
        media_tags=tags,
        media_technical=technical,
    )


def inspect(path, cancelled=lambda: False):
    'Poll the child so cancel/close never waits for a complete MediaInfo scan.'
    from .media import AUDIO_EXT, IMAGE_EXT, inspect_media, read_companion, companion_signature, sync_columns

    if path.suffix.lower() in AUDIO_EXT | IMAGE_EXT:
        return inspect_media(path, cancelled)
    import time

    process = subprocess.Popen(
        ['mediainfo', '--Output=JSON', str(path.absolute())],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 30
    try:
        while True:
            if cancelled():
                raise InterruptedError()
            if time.monotonic() >= deadline:
                raise TimeoutError(tr('Analyse trop longue (30 secondes)'))
            try:
                output, error = process.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise ValueError(error.decode('utf-8', 'replace').strip() or tr('MediaInfo a échoué'))
        row = parse(path, json.loads(output))
        if not row.is_video:
            return row
        row.media_type = 'video'
        try:
            from .media import audio_tags

            row.media_tags.update(audio_tags(path)[0])
        except Exception as error:
            logging.getLogger('mirivue-gtk4').warning('Balises audio illisibles pour %s : %s', path, error)
        sidecar = read_companion(path)
        if path.suffix.lower() == '.mkv':
            embedded = True
            if embedded:
                for key, value in sidecar.items():
                    row.media_tags.setdefault(key, value)
            else:
                row.media_tags.update(sidecar)
        else:
            row.media_tags.update(sidecar)
        row.companion_signature = companion_signature(path)
        sync_columns(row)
        from .persistence import capture
        import shutil

        if row.values[7] == 'Indéterminé' and shutil.which('ffprobe'):
            try:
                document = capture(
                    [
                        'ffprobe',
                        '-v',
                        'error',
                        '-protocol_whitelist',
                        'file',
                        '-select_streams',
                        'v:0',
                        '-show_streams',
                        '-of',
                        'json',
                        str(path),
                    ],
                    cancelled,
                )
                streams = document.get('streams', [])
                if streams:
                    row.values[7] = hdr_from_probe(streams[0])
                    row.sort_values[7] = row.values[7].casefold()
                    if row.values[7] != 'Indéterminé':
                        row.hdr_note = tr(
                            'Identifié à partir des métadonnées de la première piste vidéo lues par FFprobe.'
                        )
            except InterruptedError:
                raise
            except Exception as error:
                row.hdr_note += trf(' Lecture complémentaire indisponible : \x1f0\x1f', error)
        return row
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate()


def failed(path, error):
    return Video(
        path,
        [path.name] + ['—'] * 9 + ['Erreur', 'Indéterminée', '', '', ''],
        [
            path.name.casefold(),
            -1,
            -1,
            -1,
            '',
            -1,
            -1,
            '',
            '',
            -1,
            'Erreur',
            'indéterminée',
            -1,
            -1,
            -1,
        ],
        str(error),
    )


def basic_entry(path, is_dir=False):
    row = Video(path, is_dir=is_dir, is_video=False, media_type='folder' if is_dir else 'other')
    size = None if is_dir else path.stat().st_size
    row.values = (
        [path.name, quantity(size, ['o', 'Kio', 'Mio', 'Gio', 'Tio'], 1024)]
        + [''] * 8
        + ['Dossier' if is_dir else tr('Autre fichier'), '', '', '', '']
    )
    row.sort_values = [
        path.name.casefold(),
        size or 0,
        -1,
        -1,
        '',
        -1,
        -1,
        '',
        '',
        -1,
        row.values[10],
        '',
        -1,
        -1,
        -1,
    ]
    row.file_signature = fingerprint(path)
    row.__post_init__()
    update_modification(row)
    return row


def hdr_from_probe(stream):
    side = stream.get('side_data_list', [])
    if any(
        (
            'dovi' in str(item.get('side_data_type', '')).lower()
            or 'dolby vision' in str(item.get('side_data_type', '')).lower()
            for item in side
        )
    ):
        return 'Dolby Vision'
    transfer = str(stream.get('color_transfer', '')).lower()
    if transfer == 'smpte2084':
        return 'HDR (PQ)'
    if transfer == 'arib-std-b67':
        return 'HDR (HLG)'
    if transfer in (
        'bt709',
        'gamma22',
        'gamma28',
        'smpte170m',
        'smpte240m',
        'iec61966-2-1',
        'bt2020-10',
        'bt2020-12',
    ):
        return 'SDR'
    return 'Indéterminé'


def modification_text(timestamp_ns, now=None):
    if timestamp_ns is None:
        return '—'
    try:
        date = datetime.fromtimestamp(timestamp_ns / 1000000000)
    except (ValueError, OverflowError, OSError):
        return '—'
    today = (now or datetime.now()).date()
    if date.date() == today:
        prefix = 'Aujourd’hui'
    elif date.date() == today - timedelta(days=1):
        prefix = 'Hier'
    else:
        prefix = 'le ' + date.strftime('%d/%m/%Y')
    return prefix + ' à ' + date.strftime('%H:%M:%S')


def update_modification(row):
    while len(row.values) < len(HEADERS):
        row.values.append('')
    while len(row.sort_values) < len(HEADERS):
        row.sort_values.append(-1)
    try:
        row.modified_ns = row.path.stat().st_mtime_ns
    except OSError:
        row.modified_ns = None
    row.values[14] = modification_text(row.modified_ns)
    row.sort_values[14] = row.modified_ns if row.modified_ns is not None else -1
