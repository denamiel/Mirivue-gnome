'Local media discovery, descriptive tags, and signature-validated technical cache.'

from ..i18n import tr, trf

import hashlib, json, tempfile
from pathlib import Path
from .platform_services import services
from .metadata import basic_entry, quantity, duration, number
from .extensions import fingerprint

AUDIO_EXT = set(
    '.mp3 .flac .ogg .oga .opus .wav .wave .aiff .aif .m4a .m4b .aac .wma .ape .wv .ac3 .a52 .mka'.split()
)
IMAGE_EXT = set(
    '.jpg .jpeg .png .webp .gif .bmp .tif .tiff .avif .heic .heif .jxl .svg .psd .psb .dng .cr2 .cr3 .nef .arw .orf .rw2 .pef .raf'.split()
)
LABELS = {
    'video': 'Vidéo',
    'audio': 'Audio',
    'image': 'Image',
    'folder': 'Dossier',
    'other': 'Autre fichier',
}
FIELDS = {
    'title': 'Titre',
    'artist': 'Artiste',
    'album': 'Album',
    'albumartist': 'Artiste de l’album',
    'tracknumber': 'Piste',
    'discnumber': 'Disque',
    'date': 'Année / date',
    'genre': 'Genre',
    'composer': 'Compositeur',
    'author': 'Auteur',
    'copyright': 'Droits d’auteur',
    'description': 'Description',
    'keywords': 'Mots-clés',
    'date_taken': 'Date de prise de vue',
}
COLUMNS = {
    18: 'title',
    19: 'artist',
    20: 'album',
    21: 'tracknumber',
    22: 'date',
    23: 'genre',
    26: 'date_taken',
    27: 'keywords',
    28: 'author',
    31: 'albumartist',
    32: 'discnumber',
    33: 'composer',
    34: 'copyright',
    35: 'description',
}


def kind(row):
    return row.media_type or ('folder' if row.is_dir else 'video' if row.is_video else 'other')


def expected_kind(path):
    suffix = Path(path).suffix.lower()
    return 'image' if suffix in IMAGE_EXT else 'audio' if suffix in AUDIO_EXT else 'video'


def companion(path):
    return Path(str(path) + '.xmp')


def companion_signature(path):
    try:
        return fingerprint(companion(path))
    except OSError:
        return None


def read_companion(path):
    from .media_tags import read_xmp

    return read_xmp(companion(path)) if companion(path).exists() else {}


def sync_columns(row):
    row.__post_init__()
    media = kind(row)
    row.values[17] = row.sort_values[17] = LABELS[media]
    for column, key in COLUMNS.items():
        value = str(row.media_tags.get(key, ''))
        row.values[column] = value
        row.sort_values[column] = value.casefold()
    for column, key, units in [
        (24, 'sample_rate', ['Hz', 'kHz']),
        (25, 'bitrate', ['bit/s', 'kbit/s', 'Mbit/s']),
    ]:
        value = row.media_technical.get(key)
        row.values[column] = quantity(value, units, 1000) if value else ''
        row.sort_values[column] = value or -1
    row.values[29] = str(row.media_technical.get('format', row.container_info.get('Format', '')))
    row.sort_values[29] = row.values[29].casefold()
    bits = row.media_technical.get('bits')
    row.values[30] = str(bits) if bits else ''
    row.sort_values[30] = bits or -1
    row.values[36] = ' • '.join(
        (
            trf('\x1f0\x1f \x1f1\x1f', v, LABELS[k].lower()) + ('s' if v != 1 else '')
            for k, v in row.media_counts.items()
        )
    )
    row.sort_values[36] = sum(row.media_counts.values()) if row.media_counts else -1


def text_value(value):
    if isinstance(value, (list, tuple)):
        return '; '.join((str(v) for v in value))
    return str(value) if value is not None else ''


def audio_tags(path):
    import mutagen
    from mutagen.id3 import ID3
    from mutagen.mp4 import MP4

    file = mutagen.File(path)
    if file is None:
        return ({}, None)
    tags = {}
    raw = file.tags
    if isinstance(raw, ID3):
        ids = {
            'title': 'TIT2',
            'artist': 'TPE1',
            'album': 'TALB',
            'albumartist': 'TPE2',
            'tracknumber': 'TRCK',
            'discnumber': 'TPOS',
            'date': 'TDRC',
            'genre': 'TCON',
            'composer': 'TCOM',
            'copyright': 'TCOP',
        }
        tags = {k: text_value(raw.get(v)) for k, v in ids.items() if raw.get(v)}
        comments = raw.getall('COMM')
        if comments:
            tags['description'] = text_value(comments[0].text)
        for frame in raw.getall('TXXX'):
            if frame.desc in ('Mirivue Keywords', 'MFM Keywords'):
                tags['keywords'] = text_value(frame.text)
    elif isinstance(file, MP4):
        ids = {
            'title': '©nam',
            'artist': '©ART',
            'album': '©alb',
            'albumartist': 'aART',
            'date': '©day',
            'genre': '©gen',
            'composer': '©wrt',
            'copyright': 'cprt',
            'description': '©cmt',
        }
        tags = {k: text_value(file.get(v)) for k, v in ids.items() if file.get(v)}
        for key, atom in [('tracknumber', 'trkn'), ('discnumber', 'disk')]:
            if file.get(atom):
                a, b = file[atom][0]
                tags[key] = str(a) + (trf('/\x1f0\x1f', b) if b else '')
        if file.get('----:com.apple.iTunes:KEYWORDS'):
            tags['keywords'] = bytes(file['----:com.apple.iTunes:KEYWORDS'][0]).decode('utf-8', 'replace')
    elif raw:
        keys = {
            'title': 'title',
            'artist': 'artist',
            'album': 'album',
            'albumartist': 'albumartist',
            'tracknumber': 'tracknumber',
            'discnumber': 'discnumber',
            'date': 'date',
            'genre': 'genre',
            'composer': 'composer',
            'copyright': 'copyright',
            'description': 'description',
            'keywords': 'keywords',
        }
        for key, tag in keys.items():
            if raw.get(tag):
                tags[key] = text_value(raw[tag])
    return (tags, file)


def cache_path(path):
    root = services.cache_directory() / 'metadata'
    return root / (hashlib.sha256(str(path.absolute()).encode()).hexdigest() + '.json')


def inspect_media(path, cancelled=lambda: False):
    from . import library

    if cancelled():
        raise InterruptedError()
    signature = fingerprint(path)
    sidecar = companion_signature(path)
    cache = cache_path(path)
    try:
        data = json.loads(cache.read_text())
        if (
            data.get('schema') == 1
            and data['signature'] == list(signature)
            and (data.get('sidecar') == (list(sidecar) if sidecar else None))
        ):
            row = library.decode_row(data['row'])
            sync_columns(row)
            return row
    except (OSError, ValueError, KeyError, TypeError):
        pass
    row = basic_entry(path)
    row.media_type = 'image' if path.suffix.lower() in IMAGE_EXT else 'audio'
    if row.media_type == 'image':
        try:
            from PIL import Image

            with Image.open(path) as image:
                width, height = image.size
                exif = image.getexif()
                orientation = exif.get(274, 1)
                if orientation in (5, 6, 7, 8):
                    width, height = (height, width)
                row.media_technical = {
                    'width': width,
                    'height': height,
                    'format': image.format,
                    'mode': image.mode,
                    'frames': getattr(image, 'n_frames', 1),
                }
                row.media_tags = {
                    key: str(exif[tag])
                    for key, tag in [('description', 270), ('author', 315), ('copyright', 33432)]
                    if exif.get(tag)
                }
                for key, tag in [('camera_make', 271), ('camera_model', 272)]:
                    if exif.get(tag):
                        row.media_technical[key] = str(exif[tag])
                try:
                    exif_ifd = exif.get_ifd(34665)
                    date = exif_ifd.get(36867)
                    for key, tag in [
                        ('exposure', 33434),
                        ('aperture', 33437),
                        ('iso', 34855),
                        ('focal_length', 37386),
                    ]:
                        if exif_ifd.get(tag) is not None:
                            row.media_technical[key] = str(exif_ifd[tag])
                except (KeyError, TypeError, ValueError):
                    date = None
                if date:
                    row.media_tags['date_taken'] = str(date)
                for key, field in [
                    ('Title', 'title'),
                    ('Description', 'description'),
                    ('Author', 'author'),
                ]:
                    if image.info.get(key):
                        row.media_tags.setdefault(field, str(image.info[key]))
        except Exception:
            row.media_technical = {'format': path.suffix.lstrip('.').upper()}
        if not row.media_technical.get('width'):
            from .media_tags import exiftool_path

            if exiftool_path():
                from .media_tags import run_exif

                data = json.loads(
                    run_exif(
                        [
                            '-j',
                            '-n',
                            '-ImageWidth',
                            '-ImageHeight',
                            '-Orientation',
                            str(path.absolute()),
                        ],
                        cancelled,
                    )
                )[0]
                width = number(data.get('ImageWidth'))
                height = number(data.get('ImageHeight'))
                if width and height:
                    if data.get('Orientation') in (5, 6, 7, 8):
                        width, height = (height, width)
                    row.media_technical.update(width=int(width), height=int(height))
                    row.values[10] = row.sort_values[10] = 'OK'
        width = row.media_technical.get('width')
        height = row.media_technical.get('height')
        if width and height:
            row.values[3] = trf('\x1f0\x1f × \x1f1\x1f', width, height)
            row.sort_values[3] = width * height
        try:
            from .media_tags import embedded_image_tags

            row.media_tags.update(embedded_image_tags(path, cancelled))
        except (OSError, ValueError):
            pass
    else:
        tags, file = audio_tags(path)
        if file is None:
            from .persistence import capture

            info = capture(
                [
                    'ffprobe',
                    '-v',
                    'error',
                    '-protocol_whitelist',
                    'file',
                    '-show_format',
                    '-show_streams',
                    '-of',
                    'json',
                    str(path),
                ],
                cancelled,
            )
            stream = next((s for s in info.get('streams', []) if s.get('codec_type') == 'audio'), {})
            general = info.get('format', {})
            seconds = number(general.get('duration'))
            row.media_technical = {
                'format': stream.get('codec_name', ''),
                'sample_rate': number(stream.get('sample_rate')),
                'bitrate': number(stream.get('bit_rate', general.get('bit_rate'))),
                'channels': number(stream.get('channels')),
            }
            tags = {k: text_value(v) for k, v in general.get('tags', {}).items() if k in FIELDS}
        else:
            info = file.info
            seconds = getattr(info, 'length', None)
            row.media_technical = {
                'format': file.__class__.__name__,
                'sample_rate': getattr(info, 'sample_rate', None),
                'bitrate': getattr(info, 'bitrate', None),
                'channels': getattr(info, 'channels', None),
                'bits': getattr(info, 'bits_per_sample', None),
            }
        if not row.media_technical.get('sample_rate') or not row.media_technical.get('bitrate'):
            from .persistence import capture

            info = capture(
                [
                    'ffprobe',
                    '-v',
                    'error',
                    '-protocol_whitelist',
                    'file',
                    '-select_streams',
                    'a:0',
                    '-show_entries',
                    'stream=sample_rate,bit_rate,codec_name',
                    '-of',
                    'json',
                    str(path),
                ],
                cancelled,
            )
            stream = next(iter(info.get('streams', [])), {})
            if not row.media_technical.get('sample_rate'):
                row.media_technical['sample_rate'] = number(stream.get('sample_rate'))
            if not row.media_technical.get('bitrate') and stream.get('bit_rate'):
                row.media_technical['bitrate'] = number(stream['bit_rate'])
        row.media_tags = tags
        row.values[2] = duration(seconds)
        row.sort_values[2] = seconds if seconds is not None else -1
        row.values[8] = row.media_technical.get('format', '')
        row.sort_values[8] = row.values[8].casefold()
        channels = row.media_technical.get('channels')
        row.values[9] = str(int(channels)) if channels else ''
        row.sort_values[9] = channels or -1
    row.media_tags.update(read_companion(path))
    row.companion_signature = sidecar
    if row.values[10] == tr('Autre fichier'):
        row.values[10] = row.sort_values[10] = 'OK'
    sync_columns(row)
    if cancelled():
        raise InterruptedError()
    if fingerprint(path) == signature and companion_signature(path) == sidecar:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile('w', dir=cache.parent, delete=False) as out:
                temporary = Path(out.name)
                json.dump(
                    {
                        'schema': 1,
                        'signature': signature,
                        'sidecar': sidecar,
                        'row': library.encode_row(row),
                    },
                    out,
                    ensure_ascii=False,
                )
            temporary.replace(cache)
        except OSError:
            pass
    return row


def suggestions(row):
    'Conservative, local suggestions. Never invent an artist or capture date.'

    result = {}
    stem = row.path.stem
    if kind(row) == 'audio':
        pieces = [p.strip() for p in stem.split(' - ')]
        if len(pieces) == 3 and pieces[0].isdigit():
            result.update(tracknumber=pieces[0], artist=pieces[1], title=pieces[2])
        elif len(pieces) == 2 and pieces[0].isdigit():
            result.update(tracknumber=pieces[0], title=pieces[1])
        elif len(pieces) == 2:
            result.update(artist=pieces[0], title=pieces[1])
        if row.path.parent.name:
            result['album'] = row.path.parent.name
    result.setdefault('title', stem)
    return {k: v for k, v in result.items() if v and (not row.media_tags.get(k))}
