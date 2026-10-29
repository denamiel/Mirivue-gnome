'Local, versioned JSON state. No executable data is deserialized.'

from ..i18n import tr

from dataclasses import asdict, fields
from pathlib import Path
from .metadata import Video


def encode_row(row):
    data = asdict(row)
    data['path'] = str(row.path)
    data.update(
        quality_score=None,
        quality_samples=0,
        quality_details={},
        quality_version='',
        quality_profile_signature='',
        quality_note='',
        quality_error='',
        quality_state='',
    )
    if len(data.get('values', [])) > 12:
        data['values'][12] = ''
    if len(data.get('sort_values', [])) > 12:
        data['sort_values'][12] = -1
    return data


def decode_row(data):
    if not isinstance(data, dict):
        raise ValueError(tr('Entrée invalide'))
    data = {k: v for k, v in data.items() if k in {f.name for f in fields(Video)}}
    data['path'] = Path(data['path'])
    for key in ('file_signature', 'bitrate_result', 'companion_signature'):
        if data.get(key) is not None:
            data[key] = tuple(data[key])
    if 'original_bitrate' not in data:
        rates = data.get('sort_values', [])
        data['original_bitrate'] = (
            rates[6]
            if len(rates) > 6
            and rates[6] > 0
            and (data.get('bitrate_saved') or not data.get('bitrate_result'))
            else None
        )
    data.pop('sharpness', None)
    data.pop('sharpness_samples', None)
    row = Video(**data)
    row.quality_score = None
    row.quality_samples = 0
    row.quality_details = {}
    row.quality_version = ''
    row.quality_profile_signature = ''
    row.quality_note = ''
    row.quality_error = ''
    row.quality_state = ''
    if row.is_dir and row.total_duration is not None:
        from .metadata import duration

        row.values[2] = duration(row.total_duration)
        row.sort_values[2] = row.total_duration
        row.values[15] = ''
        row.sort_values[15] = -1
    row.values[12] = ''
    row.sort_values[12] = -1
    row.values[13] = ''
    row.sort_values[13] = -1
    row.values[16] = ''
    row.sort_values[16] = -1
    if row.bitrate_result and not row.bitrate_saved:
        from .metadata import quantity

        rate = row.original_bitrate
        row.values[6] = quantity(rate, ['bit/s', 'kbit/s', 'Mbit/s', 'Gbit/s'], 1000)
        row.sort_values[6] = rate if rate is not None else -1
    row.bitrate_result = None
    row.bitrate_note = ''
    row.bitrate_error = ''
    return row
