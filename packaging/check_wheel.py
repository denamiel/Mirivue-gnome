"""Check runtime data and console entry point in the built wheel."""

from pathlib import Path
import sys
from zipfile import ZipFile


def check(path):
    with ZipFile(path) as wheel:
        names = wheel.namelist()
        required = ['mirivue_gtk4/en.json', 'mirivue_gtk4/help.fr.txt', 'mirivue_gtk4/help.en.txt',
                    'mirivue_gtk4/launcher.py']
        for name in required:
            if name not in names:
                raise ValueError(f'Donnée absente de la wheel : {name}')
        entries = next(n for n in names if n.endswith('.dist-info/entry_points.txt'))
        if 'mirivue-gnome = mirivue_gtk4.launcher:main' not in wheel.read(entries).decode():
            raise ValueError('Point d’entrée du paquet absent')
        desktop = next(n for n in names if n.endswith('/share/applications/org.pdenams.Mirivue.Gtk4.desktop'))
        if b'Exec=mirivue-gnome %U' not in wheel.read(desktop):
            raise ValueError('Lanceur non portable dans la wheel')
        print(f'{Path(path).name} : ressources et lanceur OK')


if __name__ == '__main__':
    for path in sys.argv[1:]:
        check(path)
