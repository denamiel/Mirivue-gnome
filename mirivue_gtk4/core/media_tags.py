'Metadata-only editing with explicit destinations, backups and atomic publication.'

from ..i18n import tr, trf

import base64, os, shutil, subprocess, tempfile, json
from pathlib import Path
import xml.etree.ElementTree as ET
from .extensions import fingerprint
from .platform_services import services

NS = {
    'x': 'adobe:ns:meta/',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'dc': 'http://purl.org/dc/elements/1.1/',
    'xmp': 'http://ns.adobe.com/xap/1.0/',
    'exif': 'http://ns.adobe.com/exif/1.0/',
    'mfm': 'https://mfm.local/metadata/1.0/',
}
for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)
XMP_KEYS = {
    'title': ('dc', 'title'),
    'description': ('dc', 'description'),
    'author': ('dc', 'creator'),
    'copyright': ('dc', 'rights'),
    'keywords': ('dc', 'subject'),
    'date_taken': ('exif', 'DateTimeOriginal'),
    'rating': ('xmp', 'Rating'),
}


def q(prefix, name):
    return '{' + NS[prefix] + '}' + name


def xml_root(data):
    if len(data) > 8 * 1024 * 1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError(tr('Le fichier XMP contient une structure non prise en charge.'))
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError(tr('Le fichier XMP existant est illisible ; il ne sera pas remplacé.')) from error


def read_xmp(path):
    with Path(path).open('rb') as stream:
        root = xml_root(stream.read(8 * 1024 * 1024 + 1))
    result = {}
    from .media import FIELDS

    for key in [*FIELDS, 'rating']:
        prefix, name = XMP_KEYS.get(key, ('mfm', key))
        tag = q(prefix, name)
        node = root.find('.//' + tag)
        if node is not None:
            items = node.findall('.//' + q('rdf', 'li'))
            result[key] = (
                '; '.join((''.join(item.itertext()) for item in items)) if items else ''.join(node.itertext())
            )
        else:
            for description in root.iter(q('rdf', 'Description')):
                if tag in description.attrib:
                    result[key] = description.attrib[tag]
                    break
    if 'rating' in result:
        try:
            result['rating'] = str(max(0, min(4, round(float(result['rating']) * 4 / 5))))
        except ValueError:
            result.pop('rating', None)
    return result


def write_xmp(path, changes):
    path = Path(path)
    if path.exists():
        root = xml_root(path.read_bytes())
    else:
        root = ET.Element(q('x', 'xmpmeta'))
        rdf = ET.SubElement(root, q('rdf', 'RDF'))
        ET.SubElement(rdf, q('rdf', 'Description'), {q('rdf', 'about'): ''})
    descriptions = list(root.iter(q('rdf', 'Description')))
    if not descriptions:
        raise ValueError(tr('La structure XMP ne contient pas de description modifiable.'))
    target = descriptions[0]
    for key, value in changes.items():
        if key == 'cover':
            raise ValueError(tr('La pochette doit être intégrée à un format audio compatible.'))
        prefix, name = XMP_KEYS.get(key, ('mfm', key))
        tag = q(prefix, name)
        for description in descriptions:
            description.attrib.pop(tag, None)
            for child in list(description):
                if child.tag == tag:
                    description.remove(child)
        element = ET.SubElement(target, tag)
        if key in ('title', 'description', 'copyright'):
            alt = ET.SubElement(element, q('rdf', 'Alt'))
            ET.SubElement(
                alt,
                q('rdf', 'li'),
                {'{http://www.w3.org/XML/1998/namespace}lang': 'x-default'},
            ).text = str(value)
        elif key in ('author', 'keywords'):
            group = ET.SubElement(element, q('rdf', 'Seq' if key == 'author' else 'Bag'))
            for part in str(value).split(';'):
                ET.SubElement(group, q('rdf', 'li')).text = part.strip()
        else:
            element.text = str(round(int(value) * 5 / 4)) if key == 'rating' else str(value)
    ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


EXIF = {
    'title': 'XMP-dc:Title',
    'description': 'XMP-dc:Description',
    'author': 'XMP-dc:Creator',
    'copyright': 'XMP-dc:Rights',
    'keywords': 'XMP-dc:Subject',
    'date_taken': 'EXIF:DateTimeOriginal',
}


def exiftool_path():
    return services.tool_path('exiftool') or (
        '/usr/bin/vendor_perl/exiftool'
        if services.name == 'linux' and Path('/usr/bin/vendor_perl/exiftool').is_file()
        else None
    )


def run_exif(args, cancelled=lambda: False):
    tool = exiftool_path()
    if not tool:
        raise ValueError(tr('ExifTool est absent. Relancez l’installateur pour l’ajouter.'))
    process = subprocess.Popen([tool, *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        import time

        deadline = time.monotonic() + 60
        while True:
            if cancelled():
                raise InterruptedError()
            if time.monotonic() > deadline:
                raise ValueError(tr('L’outil de métadonnées n’a pas répondu dans le délai prévu.'))
            try:
                out, err = process.communicate(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
        if process.returncode:
            raise ValueError(
                tr('ExifTool n’a pas pu enregistrer les informations : ')
                + err.decode('utf-8', 'replace')[:1500]
            )
        return out
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def embedded_image_tags(path, cancelled=lambda: False):
    if not exiftool_path():
        return {}
    data = json.loads(
        run_exif(['-j', '-s', *['-' + v for v in EXIF.values()], str(Path(path).absolute())], cancelled)
    )[0]
    result = {}
    for key, name in EXIF.items():
        value = data.get(name.split(':')[-1])
        if value is not None:
            result[key] = '; '.join(map(str, value)) if isinstance(value, list) else str(value)
    return result


def native_route(row, force_xmp=False, embed_mkv=True):
    from .media import kind

    media = kind(row)
    suffix = row.path.suffix.lower()
    from .media import companion

    if media == 'video' and suffix == '.mkv' and embed_mkv:
        return 'mkv'
    if companion(row.path).exists():
        return 'xmp'
    if force_xmp and media == 'image':
        return 'xmp'
    if media == 'image' and suffix in ('.jpg', '.jpeg', '.png', '.tif', '.tiff', '.webp') and exiftool_path():
        return 'image'
    if media in ('audio', 'video') and suffix in (
        '.mp3',
        '.flac',
        '.ogg',
        '.oga',
        '.opus',
        '.m4a',
        '.m4b',
        '.mp4',
        '.m4v',
        '.wav',
        '.wave',
        '.aif',
        '.aiff',
    ):
        return 'audio'
    return 'xmp'


MkvKeyNames = {
    'title': 'TITLE',
    'description': 'DESCRIPTION',
    'author': 'ARTIST',
    'copyright': 'COPYRIGHT',
    'keywords': 'KEYWORDS',
    'date_taken': 'DATE_RELEASED',
}


def _mkv_document(path, cancelled=lambda: False):
    'Read Matroska tags safely, preserving unusual but valid XML references.'
    if not shutil.which('mkvextract'):
        raise ValueError(
            tr('MKVToolNix manque : relancez l’installateur pour activer l’écriture interne aux MKV.')
        )
    from .persistence import stream_command, parse_mkv_tags

    parts = []
    stream_command(['mkvextract', str(Path(path)), 'tags'], parts.append, cancelled, timeout=60)
    document, references = parse_mkv_tags(b''.join(parts))
    if document.tag != 'Tags':
        raise ValueError(tr('Les balises MKV ne sont pas reconnues ; l’original est conservé.'))
    return (document, references)


def _mkv_global_tags(document):
    'Return only file-level tags; track and chapter tags stay untouched.'
    for tag in document.findall('Tag'):
        targets = tag.find('Targets')
        if targets is not None and any(
            (
                targets.find(name) is not None
                for name in ('TrackUID', 'ChapterUID', 'AttachmentUID', 'EditionUID')
            )
        ):
            continue
        yield tag


def read_mkv_tags(path, cancelled=lambda: False):
    try:
        document, _ = _mkv_document(path, cancelled)
    except (OSError, ValueError, InterruptedError):
        if cancelled():
            raise
        return {}
    names = {name: key for key, name in MkvKeyNames.items()}
    result = {}
    for tag in _mkv_global_tags(document):
        for simple in tag.findall('Simple'):
            key = names.get(simple.findtext('Name', '').upper())
            if key and key not in result:
                value = simple.findtext('String', '')
                if value:
                    result[key] = value
    return result


def write_mkv(path, changes, cancelled=lambda: False):
    'Write selected file-level Matroska tags into a temporary copy only.'
    if not shutil.which('mkvpropedit'):
        raise ValueError(
            tr('MKVToolNix manque : relancez l’installateur pour activer l’écriture interne aux MKV.')
        )
    unknown = set(changes) - set(MkvKeyNames)
    if unknown:
        raise ValueError(
            tr('Ces champs ne peuvent pas être enregistrés directement dans un MKV : ')
            + ', '.join(sorted(unknown))
        )
    document, references = _mkv_document(path, cancelled)
    wanted = {MkvKeyNames[key]: str(value) for key, value in changes.items()}
    remaining = dict(wanted)
    for tag in _mkv_global_tags(document):
        for simple in list(tag.findall('Simple')):
            name = simple.findtext('Name', '').upper()
            if name not in wanted:
                continue
            value = remaining.pop(name)
            if value:
                string = simple.find('String')
                if string is None:
                    string = ET.SubElement(simple, 'String')
                string.text = value
            else:
                tag.remove(simple)
    if remaining:
        tag = next(_mkv_global_tags(document), None)
        if tag is None:
            tag = ET.SubElement(document, 'Tag')
            ET.SubElement(tag, 'Targets')
        for name, value in remaining.items():
            if not value:
                continue
            simple = ET.SubElement(tag, 'Simple')
            ET.SubElement(simple, 'Name').text = name
            ET.SubElement(simple, 'String').text = value
    from .persistence import stream_command, serialize_mkv_tags

    with tempfile.TemporaryDirectory(prefix='mirivue-mkv-tags-') as directory:
        xml = Path(directory) / 'tags.xml'
        xml.write_bytes(serialize_mkv_tags(document, references))
        stream_command(
            ['mkvpropedit', str(Path(path)), '--tags', 'all:' + str(xml)],
            lambda data: None,
            cancelled,
            timeout=60,
        )
    actual = read_mkv_tags(path, cancelled)
    for key, value in changes.items():
        if str(actual.get(key, '')) != str(value):
            raise ValueError(
                trf('La relecture ne confirme pas le champ « \x1f0\x1f ». L’original est conservé.', key)
            )
    return actual


def read_cover(path):
    from .media import audio_tags
    from mutagen.id3 import ID3
    from mutagen.mp4 import MP4
    from mutagen.flac import Picture

    _, file = audio_tags(path)
    if file is None:
        return b''
    if hasattr(file, 'pictures') and file.pictures:
        return file.pictures[0].data
    if isinstance(file.tags, ID3):
        pictures = file.tags.getall('APIC')
        return pictures[0].data if pictures else b''
    if isinstance(file, MP4):
        return bytes(file['covr'][0]) if file.get('covr') else b''
    if file.get('metadata_block_picture'):
        try:
            return Picture(base64.b64decode(file['metadata_block_picture'][0])).data
        except (ValueError, TypeError):
            return b''
    return b''


def write_audio(path, changes):
    from .media import audio_tags
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TPE2, TRCK, TPOS, TDRC, TCON, TCOM, TCOP, COMM, TXXX, APIC
    from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm
    from mutagen.flac import Picture

    _, file = audio_tags(path)
    if file is None:
        raise ValueError(tr('Ce format ne permet pas une écriture intégrée avec les composants disponibles.'))
    if file.tags is None:
        file.add_tags()
    text = {k: v for k, v in changes.items() if k != 'cover'}
    if isinstance(file.tags, ID3):
        frames = {
            'title': TIT2,
            'artist': TPE1,
            'album': TALB,
            'albumartist': TPE2,
            'tracknumber': TRCK,
            'discnumber': TPOS,
            'date': TDRC,
            'genre': TCON,
            'composer': TCOM,
            'copyright': TCOP,
        }
        for key, value in text.items():
            if key in frames:
                frame = frames[key]
                file.tags.delall(frame.__name__)
                if value:
                    file.tags.add(frame(encoding=3, text=[value]))
            elif key == 'description':
                file.tags.delall('COMM')
                if value:
                    file.tags.add(COMM(encoding=3, lang='fra', desc='', text=[value]))
            elif key == 'keywords':
                file.tags.delall('TXXX:Mirivue Keywords')
                file.tags.delall('TXXX:MFM Keywords')
                if value:
                    file.tags.add(TXXX(encoding=3, desc='Mirivue Keywords', text=[value]))
            else:
                raise ValueError(tr('Ce champ n’est pas compatible avec les métadonnées audio : ') + key)
    elif isinstance(file, MP4):
        atoms = {
            'title': '©nam',
            'artist': '©ART',
            'album': '©alb',
            'albumartist': 'aART',
            'date': '©day',
            'genre': '©gen',
            'composer': '©wrt',
            'copyright': 'cprt',
            'description': '©cmt',
            'keywords': '----:com.apple.iTunes:KEYWORDS',
        }
        for key, value in text.items():
            if key in ('tracknumber', 'discnumber'):
                atom = 'trkn' if key == 'tracknumber' else 'disk'
                file.pop(atom, None)
                if value:
                    parts = value.split('/')
                    file[atom] = [(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)]
            elif key in atoms:
                atom = atoms[key]
                file.pop(atom, None)
                if value:
                    file[atom] = [MP4FreeForm(value.encode())] if key == 'keywords' else [value]
            else:
                raise ValueError(tr('Champ non pris en charge dans ce conteneur : ') + key)
    else:
        for key, value in text.items():
            file.pop(key, None)
            if value:
                file[key] = [value]
    if 'cover' in changes:
        cover = Path(changes['cover']).read_bytes() if changes['cover'] else b''
        if len(cover) > 20 * 1024 * 1024:
            raise ValueError(tr('La pochette dépasse 20 Mio.'))
        if cover:
            from PIL import Image
            import io

            with Image.open(io.BytesIO(cover)) as image:
                if image.format not in ('JPEG', 'PNG'):
                    raise ValueError(tr('Choisissez une pochette JPEG ou PNG.'))
                mime = 'image/jpeg' if image.format == 'JPEG' else 'image/png'
        if isinstance(file.tags, ID3):
            file.tags.delall('APIC')
            if cover:
                file.tags.add(APIC(encoding=3, mime=mime, type=3, desc='Pochette', data=cover))
        elif isinstance(file, MP4):
            file.pop('covr', None)
            if cover:
                file['covr'] = [
                    MP4Cover(
                        cover,
                        imageformat=MP4Cover.FORMAT_JPEG if mime == 'image/jpeg' else MP4Cover.FORMAT_PNG,
                    )
                ]
        else:
            picture = Picture()
            picture.type = 3
            if cover:
                picture.mime = mime
                picture.data = cover
            if hasattr(file, 'clear_pictures'):
                file.clear_pictures()
                if cover:
                    file.add_picture(picture)
            else:
                file.pop('metadata_block_picture', None)
                if cover:
                    file['metadata_block_picture'] = [base64.b64encode(picture.write()).decode()]
    file.save()


def safe_edit(row, changes, route, backup=True, cancelled=lambda: False):
    from .media import companion, audio_tags

    source = row.path
    if source.is_symlink() or not source.is_file():
        raise ValueError(tr('Choisissez un fichier ordinaire, pas un lien symbolique.'))
    if fingerprint(source) != row.file_signature:
        raise ValueError(
            tr('Le fichier a changé depuis l’affichage. Actualisez le dossier avant de réessayer.')
        )
    target = companion(source) if route == 'xmp' else source
    if target.is_symlink():
        raise ValueError(tr('Le fichier compagnon est un lien symbolique ; écriture refusée.'))
    old_signature = fingerprint(target) if target.exists() else None
    if route == 'xmp' and old_signature != getattr(row, 'companion_signature', None):
        raise ValueError(tr('Le fichier compagnon a changé. Actualisez le dossier.'))
    fd, name = tempfile.mkstemp(prefix='.mirivue-', suffix=target.suffix, dir=target.parent)
    os.close(fd)
    temporary = Path(name)
    from . import backup_policy
    backup_path = None
    backup_created = False
    backup_expected = None
    published = False
    try:
        if target.exists():
            shutil.copy2(target, temporary)
        else:
            temporary.unlink()
        if cancelled():
            raise InterruptedError()
        if route == 'xmp':
            write_xmp(temporary, changes)
            actual = read_xmp(temporary)
        elif route == 'audio':
            write_audio(temporary, changes)
            actual, _ = audio_tags(temporary)
        elif route == 'mkv':
            actual = write_mkv(temporary, changes, cancelled)
        else:
            if any((key not in EXIF for key in changes)):
                raise ValueError(tr('Un champ demandé n’est pas compatible avec cette image.'))
            args = ['-overwrite_original']
            for key, value in changes.items():
                args.append('-' + EXIF[key] + '=')
                if key in ('keywords', 'author'):
                    args.extend(
                        (
                            '-' + EXIF[key] + '+=' + part.strip()
                            for part in str(value).split(';')
                            if part.strip()
                        )
                    )
                elif value:
                    args.append('-' + EXIF[key] + '=' + str(value))
            run_exif([*args, str(temporary.absolute())], cancelled)
            actual = embedded_image_tags(temporary, cancelled)
        for key, value in changes.items():
            if key == 'cover':
                continue
            if str(actual.get(key, '')) != str(value):
                raise ValueError(
                    trf('La relecture ne confirme pas le champ « \x1f0\x1f ». L’original est conservé.', key)
                )
        if cancelled():
            raise InterruptedError()
        if (
            fingerprint(source) != row.file_signature
            or (fingerprint(target) if target.exists() else None) != old_signature
        ):
            raise ValueError(
                tr('Le fichier a été modifié par un autre logiciel ; l’enregistrement est annulé.')
            )
        if backup and target.exists():
            backup_path, backup_created = backup_policy.reserve_backup(target, cancelled)
            backup_expected = (backup_policy._signature(backup_path),
                               fingerprint(backup_policy._names(target)[1]))
        if cancelled():
            raise InterruptedError()
        if (
            fingerprint(source) != row.file_signature
            or (fingerprint(target) if target.exists() else None) != old_signature
        ):
            raise ValueError(tr('Le fichier a changé pendant la sauvegarde ; l’original reste en place.'))
        with temporary.open('rb') as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        published = True
        if backup_path is not None:
            backup_policy.record_backup(target, backup_path)
        return str(backup_path) if backup_path else ''
    finally:
        temporary.unlink(missing_ok=True)
        if backup_path is not None and not published:
            backup_policy.discard_new_backup(target, backup_path, backup_created, backup_expected)
