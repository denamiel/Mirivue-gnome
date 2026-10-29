'Conservative all-track MKV copy. Never change or remove the source.'

from ..i18n import tr

import os, shutil, tempfile
from pathlib import Path
from .persistence import probe, stream_command, verify_structure, packet_digest
from .extensions import fingerprint
from .file_moves import rename_noreplace, exists


def mkv_copy(source, target, cancelled=lambda: False, progress=lambda text: None):
    source = Path(source)
    target = Path(target)
    if source.is_symlink() or not source.is_file():
        raise ValueError(tr('Choisissez un fichier ordinaire.'))
    if exists(target):
        raise FileExistsError(tr('Ce nom existe déjà. Aucun remplacement effectué.'))
    initial = fingerprint(source)
    before = probe(source, cancelled)
    streams = before.get('streams', [])
    if not streams or any(
        (
            s.get('codec_name') in (None, 'none', 'unknown')
            or s.get('codec_type') in (None, 'data', 'unknown')
            for s in streams
        )
    ):
        raise ValueError(
            tr(
                'Une piste est inconnue ou contient des données que cette copie MKV ne peut pas garantir de conserver. Aucune piste n’a été supprimée ; original conservé.'
            )
        )
    if shutil.disk_usage(target.parent).free < source.stat().st_size + 16 * 1024 * 1024:
        raise ValueError(tr('Espace insuffisant pour la copie MKV.'))
    with tempfile.TemporaryDirectory(prefix='.mirivue-mkv-', dir=target.parent) as directory:
        temporary = Path(directory) / 'copy.mkv'
        progress(tr('Copie de toutes les pistes, sans réencodage…'))
        stream_command(
            [
                'ffmpeg',
                '-v',
                'error',
                '-nostdin',
                '-copyts',
                '-protocol_whitelist',
                'file',
                '-i',
                str(source),
                '-map',
                '0',
                '-map_metadata',
                '0',
                '-map_chapters',
                '0',
                '-c',
                'copy',
                '-copy_unknown',
                '-avoid_negative_ts',
                'disabled',
                '-f',
                'matroska',
                str(temporary),
            ],
            lambda data: None,
            cancelled,
        )
        progress(tr('Contrôle des pistes et des données…'))
        after = probe(temporary, cancelled)
        import copy

        comparison = copy.deepcopy(before)
        for old, new in zip(comparison.get('streams', []), after.get('streams', [])):
            tags = old.get('tags', {})
            other = {k.lower(): v for k, v in new.get('tags', {}).items()}
            if tags.get('language') == 'und' and 'language' not in other:
                tags.pop('language')
        verify_structure(comparison, after, allow_timing_changes=True)
        if packet_digest(source, cancelled, include_timing=False) != packet_digest(
            temporary, cancelled, include_timing=False
        ):
            raise ValueError(tr('Les données d’une piste ont changé. Copie refusée ; original conservé.'))
        if fingerprint(source) != initial:
            raise ValueError(tr('La source a changé pendant la copie ; recommencez.'))
        if cancelled():
            raise InterruptedError()
        shutil.copystat(source, temporary)
        with temporary.open('rb') as file:
            os.fsync(file.fileno())
        rename_noreplace(temporary, target)
    return target
