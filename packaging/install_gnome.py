"""User-scope, reversible GNOME installer run from a self-contained .run file."""

from pathlib import Path
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile

VERSION = '0.6.24'
APP_ID = 'org.pdenams.Mirivue.Gtk4'


def paths():
    data = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    return (
        data,
        data / 'mirivue-gtk4',
        data / 'mirivue-gtk4-previous',
        data / 'applications' / f'{APP_ID}.desktop',
        data / 'icons/hicolor/scalable/apps' / f'{APP_ID}.svg',
        data / 'icons/hicolor/256x256/apps' / f'{APP_ID}.png',
    )


def running():
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            argv = (process / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace')
            if 'mirivue_gtk4' in argv and ('-m mirivue_gtk4' in argv or '/mirivue-gtk4/' in argv):
                return True
        except (OSError, ValueError):
            continue
    return False


def check_dependencies():
    subprocess.run(
        [
            '/usr/bin/python3',
            '-c',
            'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1"); '
            'from gi.repository import Gtk,Adw,Gio; '
            'assert (Gtk.get_major_version(),Gtk.get_minor_version()) >= (4,12), "GTK >= 4.12 requis"; '
            'assert (Adw.get_major_version(),Adw.get_minor_version()) >= (1,4), "libadwaita >= 1.4 requis"',
        ],
        check=True,
    )


def dialog(kind, message):
    if os.environ.get('MIRIVUE_INSTALL_NONINTERACTIVE') == '1':
        print(message)
        return True
    if shutil.which('zenity'):
        option = '--question' if kind == 'confirm' else '--error' if kind == 'error' else '--info'
        return (
            subprocess.run(
                [
                    'zenity',
                    option,
                    '--no-markup',
                    '--title=Mirivue (GNOME)',
                    f'--text={message}',
                    '--width=450',
                ],
                check=False,
            ).returncode
            == 0
        )
    try:
        import gi

        gi.require_version('Gtk', '4.0')
        from gi.repository import Gtk, GLib

        result = [False]
        loop = GLib.MainLoop()
        window = Gtk.Window(title='Mirivue (GNOME)')
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(box, 'set_margin_' + edge)(20)
        box.append(Gtk.Label(label=message, wrap=True))
        buttons = Gtk.Box(spacing=10)
        if kind == 'confirm':
            cancel = Gtk.Button(label='Annuler')
            cancel.connect('clicked', lambda *_: loop.quit())
            buttons.append(cancel)
        accept = Gtk.Button(label='Continuer' if kind == 'confirm' else 'Fermer')
        accept.connect('clicked', lambda *_: (result.__setitem__(0, True), loop.quit()))
        buttons.append(accept)
        box.append(buttons)
        window.set_child(box)
        window.connect('close-request', lambda *_: (loop.quit(), False)[1])
        window.present()
        loop.run()
        window.destroy()
        return result[0]
    except Exception:
        print(message, file=sys.stderr)
        return False


def unpack(archive, stage):
    with tarfile.open(archive, 'r:gz') as source:
        seen = set()
        for member in source:
            name = Path(member.name)
            if (
                not member.isfile()
                or name.is_absolute()
                or '..' in name.parts
                or name in seen
                or not name.parts
            ):
                raise ValueError('Archive invalide.')
            seen.add(name)
            dest = stage / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            with source.extractfile(member) as stream, dest.open('xb') as output:
                shutil.copyfileobj(stream, output)
    if not (stage / 'Lancer.sh').is_file() or not (stage / 'mirivue_gtk4/__main__.py').is_file():
        raise ValueError('Sources GTK4 incomplètes.')
    if f'"{VERSION}"' not in (stage / 'mirivue_gtk4/__init__.py').read_text():
        raise ValueError('Version du contenu inattendue.')
    (stage / 'Lancer.sh').chmod(0o755)
    verifier = stage / 'Verifier-installation-GNOME.sh'
    if verifier.is_file():
        verifier.chmod(0o755)


def smoke(stage):
    result = subprocess.run(
        ['/usr/bin/python3', '-m', 'mirivue_gtk4', '--smoke-test'],
        cwd=stage,
        capture_output=True,
        text=True,
        timeout=40,
        check=False,
    )
    if result.returncode or 'Composants GTK4 : OK' not in result.stdout:
        raise RuntimeError('Le contrôle des composants GTK4 a échoué : ' + result.stderr[-1000:])


def metadata(app, desktop, svg, png):
    desktop.parent.mkdir(parents=True, exist_ok=True)
    svg.parent.mkdir(parents=True, exist_ok=True)
    png.parent.mkdir(parents=True, exist_ok=True)
    executable = str(app / 'Lancer.sh').replace('\\', '\\\\').replace(' ', '\\ ')
    content = (
        '[Desktop Entry]\nType=Application\nName=Mirivue (GNOME)\n'
        'Comment=Gestionnaire de fichiers et de médias GTK4\n'
        f'Exec={executable} %U\nIcon={APP_ID}\nStartupNotify=true\n'
        'Terminal=false\nStartupWMClass=' + APP_ID + '\n'
        'Categories=System;FileTools;GTK;\nMimeType=inode/directory;\n'
    )
    icon_svg = app / 'icons/hicolor/scalable/apps' / f'{APP_ID}.svg'
    icon_png = app / 'icons/hicolor/256x256/apps' / f'{APP_ID}.png'
    for target, value in (
        (desktop, content.encode()),
        (svg, icon_svg.read_bytes() if icon_svg.is_file() else svg.read_bytes()),
        (png, icon_png.read_bytes() if icon_png.is_file() else png.read_bytes()),
    ):
        with tempfile.NamedTemporaryFile(prefix='.mirivue-', dir=target.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(value)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(target)


def install(archive, expected_sha, rollback=False):
    data, app, previous, desktop, svg, png = paths()
    if running():
        raise RuntimeError('Fermez Mirivue (GNOME) avant la mise à jour.')
    for target in (app, previous, desktop, svg, png):
        if target.is_symlink():
            raise RuntimeError('Un chemin d’installation est un lien symbolique : ' + str(target))
    if rollback and not previous.is_dir():
        raise RuntimeError('Aucune version précédente à restaurer.')
    if not rollback:
        check_dependencies()
        digest = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
        if digest != expected_sha:
            raise ValueError('La somme SHA-256 de l’archive ne correspond pas.')
    data.mkdir(parents=True, exist_ok=True)
    stage = None
    old_previous = None
    old_app = None
    published = False
    metadata_before = {
        target: target.read_bytes() if target.is_file() else None for target in (desktop, svg, png)
    }
    try:
        if rollback:
            if app.exists():
                old_app = Path(tempfile.mkdtemp(prefix='.mirivue-gtk4-newer-', dir=data))
                old_app.rmdir()
                app.rename(old_app)
            previous.rename(app)
            published = True
        else:
            stage = Path(tempfile.mkdtemp(prefix='.mirivue-gtk4-stage-', dir=data))
            unpack(archive, stage)
            smoke(stage)
            if previous.exists():
                old_previous = Path(tempfile.mkdtemp(prefix='.mirivue-gtk4-older-', dir=data))
                old_previous.rmdir()
                previous.rename(old_previous)
            if app.exists():
                app.rename(previous)
            stage.rename(app)
            stage = None
            published = True
        metadata(app, desktop, svg, png)
    except BaseException:
        if rollback:
            if published and app.exists():
                app.rename(previous)
            if old_app and old_app.exists():
                old_app.rename(app)
        else:
            if published and app.exists():
                shutil.rmtree(app)
            if previous.exists() and not app.exists():
                previous.rename(app)
            if old_previous and old_previous.exists():
                old_previous.rename(previous)
        for target, value in metadata_before.items():
            if value is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(value)
        raise
    finally:
        if stage and stage.exists():
            shutil.rmtree(stage)
    if old_previous and old_previous.exists():
        shutil.rmtree(old_previous)
    if old_app and old_app.exists():
        old_app.rename(previous)
    print(
        'Version précédente restaurée.'
        if rollback
        else f'Mirivue GNOME {VERSION} installé ; version précédente conservée.'
    )


if __name__ == '__main__':
    try:
        archive, expected, *arguments = sys.argv[1:]
        if arguments == ['--check-dependencies']:
            check_dependencies()
            print('GTK4 et libadwaita : OK')
        else:
            if arguments not in ([], ['--rollback']):
                raise ValueError('Option inconnue.')
            operation = (
                'restaurer la version précédente' if arguments else f'installer Mirivue GNOME {VERSION}'
            )
            if not dialog('confirm', 'Voulez-vous ' + operation + ' ?'):
                raise SystemExit(0)
            install(archive, expected, rollback=bool(arguments))
            dialog(
                'info',
                'Version précédente restaurée.' if arguments else f'Mirivue GNOME {VERSION} est installé.',
            )
    except Exception as exc:
        message = 'Échec de la mise à jour : ' + str(exc)
        print(message, file=sys.stderr)
        dialog('error', message)
        raise SystemExit(1)
