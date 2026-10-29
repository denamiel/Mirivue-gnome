'Read-only decoding checks and plain French explanations.'

from ..i18n import tr

import shutil
from .extensions import fingerprint
from .persistence import stream_command


def explain_error(message):
    text = str(message).lower()
    if 'could not find tag for codec' in text or 'codec not currently supported in container' in text:
        return tr(
            'Une piste ne peut pas être réécrite dans ce conteneur. Ce n’est pas nécessairement un codec manquant ni une erreur des images ou du son. L’original est conservé. Une copie MKV peut être essayée uniquement si toutes les pistes sont identifiées et compatibles.'
        )
    if any((word in text for word in ('permission denied', 'permission refusée'))):
        return tr('Le fichier ne peut pas être lu car l’accès est refusé. Vérifiez ses droits d’accès.')
    if any((word in text for word in ('no such file', 'introuvable'))):
        return tr(
            'Le fichier ou un outil nécessaire est introuvable. Actualisez le dossier et vérifiez l’installation.'
        )
    if any(
        (
            word in text
            for word in (
                'decoder not found',
                'unknown decoder',
                'unsupported codec',
                'decoding requested, but no decoder',
            )
        )
    ):
        return tr(
            'Le format de cette piste ne peut pas être lu avec les composants installés. Cela ne prouve pas que le média est abîmé.'
        )
    if any((word in text for word in ('horodat', 'timestamp', 'non monoton', 'non-monoton'))):
        return tr(
            'Les repères de temps de certaines images ou du son sont incohérents. La lecture peut présenter des sauts ou un décalage du son.'
        )
    if any(
        (
            word in text
            for word in (
                'invalid data',
                'corrupt',
                'error while decoding',
                'invalid nal',
                'missing picture',
                'end of file',
                'moov atom',
                'truncat',
            )
        )
    ):
        return tr(
            'Certaines données du média sont illisibles ou incomplètes. Des images ou du son peuvent manquer. Essayez une autre copie du fichier si vous en avez une.'
        )
    if 'reference to invalid character' in text or 'xml' in text:
        return tr(
            'Une information descriptive du fichier contient un caractère non reconnu. Cela ne signifie pas forcément que les images ou le son sont abîmés.'
        )
    if 'espace' in text or 'no space' in text:
        return tr('Il manque de l’espace sur le disque pour terminer cette opération.')
    return tr(
        'L’opération n’a pas pu se terminer correctement. Le rapport technique ci-dessous donne la cause signalée par l’outil ; cette erreur ne prouve pas à elle seule que le média est abîmé.'
    )


def check_video(path, cancelled=lambda: False):
    if not shutil.which('ffmpeg'):
        raise ValueError(tr('Outil FFmpeg introuvable : relancez Installer.sh.'))
    signature = fingerprint(path)
    stream_command(
        [
            'ffmpeg',
            '-v',
            'error',
            '-nostdin',
            '-protocol_whitelist',
            'file',
            '-i',
            str(path),
            '-map',
            '0:v?',
            '-map',
            '0:a?',
            '-f',
            'null',
            '-',
        ],
        lambda data: None,
        cancelled,
    )
    if fingerprint(path) != signature:
        raise ValueError(tr('Le fichier a changé pendant le test : actualisez et recommencez.'))
