'Bounded media probing, MKV XML handling, and stream verification.'

from ..i18n import tr, trf

import re
import uuid
import hashlib
import json
import queue
import threading
import subprocess
import time
import xml.etree.ElementTree as ET

TAG = 'VIDEOINFOTABLE_BITRATE_V1'
MARKER = 'Mirivue-bitrate-v1:'


def stream_command(command, callback, cancelled=lambda: False, timeout=None):
    """Run a tool with bounded pipe buffering and cooperative cancellation."""
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL
    )
    events = queue.Queue(maxsize=32)
    stopping = threading.Event()

    def offer(event):
        while not stopping.is_set():
            try:
                events.put(event, timeout=0.1)
                return
            except queue.Full:
                continue

    def read_stream(stream, channel):
        try:
            while not stopping.is_set():
                data = stream.read(65536)
                if not data:
                    break
                offer((channel, data))
        finally:
            offer((channel, None))

    readers = [
        threading.Thread(target=read_stream, args=(process.stdout, 'out'), daemon=True),
        threading.Thread(target=read_stream, args=(process.stderr, 'err'), daemon=True),
    ]
    for reader in readers:
        reader.start()
    started = time.monotonic()
    error = b''
    closed = set()
    try:
        while len(closed) < 2 or process.poll() is None:
            if cancelled():
                raise InterruptedError()
            if timeout and time.monotonic() - started > timeout:
                raise TimeoutError(tr('Lecture des métadonnées trop longue'))
            try:
                channel, data = events.get(timeout=0.1)
            except queue.Empty:
                continue
            if data is None:
                closed.add(channel)
            elif channel == 'out':
                callback(data)
            else:
                error = (error + data)[:16384]
        if cancelled():
            raise InterruptedError()
        if process.returncode or error.strip():
            raise ValueError(error.decode('utf-8', 'replace').strip() or tr('Échec de l’outil vidéo'))
    finally:
        stopping.set()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()


def capture(command, cancelled=lambda: False):
    parts = []
    size = 0

    def add(data):
        nonlocal size
        size += len(data)
        if size > 32 * 1024 * 1024:
            raise ValueError(tr('Métadonnées trop volumineuses'))
        parts.append(data)

    stream_command(command, add, cancelled, timeout=30)
    return json.loads(b''.join(parts))


def probe(path, cancelled=lambda: False):
    return capture(
        [
            'ffprobe',
            '-v',
            'error',
            '-protocol_whitelist',
            'file',
            '-show_format',
            '-show_streams',
            '-show_chapters',
            '-show_data_hash',
            'sha256',
            '-of',
            'json',
            str(path),
        ],
        cancelled,
    )


def packet_digest(path, cancelled=lambda: False, include_timing=True):
    pending = b''
    streams = {}

    def add(data):
        nonlocal pending
        pending += data
        lines = pending.split(b'\n')
        pending = lines.pop()
        if len(pending) > 131072:
            raise ValueError(tr('Paquet de contrôle inattendu'))
        for line in lines:
            if cancelled():
                raise InterruptedError()
            if not line.startswith(b'packet|'):
                continue
            fields = dict((part.split(b'=', 1) for part in line.split(b'|')[1:] if b'=' in part))
            index = fields[b'stream_index']
            digest, count = streams.setdefault(index, (hashlib.sha256(), 0))
            if b'data_hash' not in fields:
                raise ValueError(tr('Empreinte de paquet absente'))
            values = [fields[b'size'], fields[b'data_hash']]
            if include_timing:
                for key in (b'pts_time', b'dts_time', b'duration_time'):
                    value = fields.get(key, b'N/A')
                    try:
                        value = str(round(float(value), 3)).encode()
                    except ValueError:
                        pass
                    values.append(value)
            digest.update(b'|'.join(values) + b'\n')
            streams[index] = (digest, count + 1)

    stream_command(
        [
            'ffprobe',
            '-v',
            'error',
            '-protocol_whitelist',
            'file',
            '-show_packets',
            '-show_data_hash',
            'sha256',
            '-show_entries',
            'packet=stream_index,size,data_hash,pts_time,dts_time,duration_time',
            '-of',
            'compact=p=1:nk=0',
            str(path),
        ],
        add,
        cancelled,
    )
    if pending.strip():
        add(b'\n')
    if not streams:
        raise ValueError(tr('Aucune piste contrôlable'))
    return {key: (digest.hexdigest(), count) for key, (digest, count) in streams.items()}


def verify_structure(before, after, allow_timing_changes=False):
    old, new = (before.get('streams', []), after.get('streams', []))
    if len(old) != len(new):
        raise ValueError(tr('Le nombre de pistes a changé ; original conservé'))
    keys = (
        'codec_type',
        'codec_name',
        'width',
        'height',
        'pix_fmt',
        'sample_rate',
        'channels',
        'channel_layout',
        'extradata_hash',
        'side_data_list',
    )
    ignored = {
        'encoder',
        'duration',
        'bps',
        'number_of_bytes',
        'number_of_frames',
        '_statistics_writing_app',
        '_statistics_writing_date_utc',
        '_statistics_tags',
    }
    for a, b in zip(old, new):
        if any((a.get(k) != b.get(k) for k in keys)):
            raise ValueError(tr('Les caractéristiques d’une piste ont changé ; original conservé'))
        if a.get('disposition', {}) != b.get('disposition', {}):
            raise ValueError(tr('Les dispositions des pistes ont changé ; original conservé'))
        after_tags = {k.lower(): v for k, v in b.get('tags', {}).items()}
        for key, value in a.get('tags', {}).items():
            if key.lower() not in ignored and after_tags.get(key.lower()) != value:
                raise ValueError(trf('Métadonnée de piste non conservée : \x1f0\x1f', key))

    def chapters(document):
        if allow_timing_changes:
            return [c.get('tags', {}) for c in document.get('chapters', [])]
        return [
            (round(float(c['start_time']), 3), round(float(c['end_time']), 3), c.get('tags', {}))
            for c in document.get('chapters', [])
        ]

    if chapters(before) != chapters(after):
        raise ValueError(tr('Les chapitres ont changé ; original conservé'))
    after_tags = {k.lower(): v for k, v in after.get('format', {}).get('tags', {}).items()}
    for key, value in before.get('format', {}).get('tags', {}).items():
        if key.lower() in {
            'encoder',
            TAG.lower(),
            'major_brand',
            'minor_version',
            'compatible_brands',
        }:
            continue
        actual = after_tags.get(key.lower(), '')
        if key.lower() == 'comment':
            clean = lambda text: '\n'.join(
                (line for line in str(text).splitlines() if not line.startswith(MARKER))
            )
            if clean(actual) == clean(value):
                continue
        if actual != value:
            raise ValueError(trf('Métadonnée globale non conservée : \x1f0\x1f', key))


def parse_mkv_tags(data):
    prefix = 'Mirivue_XML_' + uuid.uuid4().hex + '_'
    while prefix.encode() in data:
        prefix = 'Mirivue_XML_' + uuid.uuid4().hex + '_'
    references = {}

    def protect(match):
        token = match.group(1)
        value = int(token[1:], 16) if token[:1].lower() == b'x' else int(token)
        valid = (
            value in (9, 10, 13)
            or 32 <= value <= 55295
            or 57344 <= value <= 65533
            or (65536 <= value <= 1114111)
        )
        if valid:
            return match.group(0)
        key = (prefix + str(len(references))).encode()
        references[key] = match.group(0)
        return key

    protected = re.sub(b'&#(x[0-9a-fA-F]+|[0-9]+);', protect, data)
    try:
        root = ET.fromstring(protected)
    except ET.ParseError as error:
        raise ValueError(trf('Métadonnées MKV illisibles (\x1f0\x1f) ; original conservé', error)) from error
    return (root, references)


def serialize_mkv_tags(document, references):
    data = ET.tostring(document, encoding='utf-8', xml_declaration=True)
    for key in sorted(references, key=len, reverse=True):
        data = data.replace(key, references[key])
    return data
