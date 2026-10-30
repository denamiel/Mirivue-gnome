"""Check package identity and refuse publication without an explicit licence."""

import argparse
import ast
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def version():
    tree = ast.parse((ROOT / 'mirivue_gtk4/__init__.py').read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', '') == '__version__' for t in node.targets):
            value = ast.literal_eval(node.value)
            if re.fullmatch(r'\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.[1-9]\d*)?', value):
                return value
    raise ValueError('Version absente ou invalide')


def package_version(value, ecosystem):
    """Map the displayed version to each package manager's prerelease syntax."""
    match = re.fullmatch(r'(\d+\.\d+\.\d+)(?:-(alpha|beta|rc)\.([1-9]\d*))?', value)
    if not match:
        raise ValueError('Version absente ou invalide')
    base, stage, number = match.groups()
    if not stage or ecosystem == 'display':
        return value
    if ecosystem == 'rpm':
        return base + '~' + stage + '.' + number
    if ecosystem == 'arch':
        return base + stage + number
    if ecosystem == 'python':
        return base + {'alpha': 'a', 'beta': 'b', 'rc': 'rc'}[stage] + number
    raise ValueError('Format de version inconnu')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--require-license', action='store_true')
    parser.add_argument('--tag')
    parser.add_argument('--format', choices=('display', 'rpm', 'arch', 'python'))
    args = parser.parse_args()
    current = version()
    if args.format:
        print(package_version(current, args.format))
        return
    config = json.loads((ROOT / 'packaging/release.json').read_text())
    spec = (ROOT / 'packaging/fedora/mirivue-gnome.spec').read_text()
    if not re.search(r'^Version:\s+' + re.escape(package_version(current, 'rpm')) + r'\s*$', spec, re.M):
        parser.error('La version RPM ne correspond pas aux sources')
    if f"VERSION = '{current}'" not in (ROOT / 'packaging/install_gnome.py').read_text():
        parser.error('La version du programme .run ne correspond pas aux sources')
    if args.tag and args.tag != f'v{current}':
        parser.error(f'Le tag attendu est v{current}')
    if '-' in current and f'%global upstream_version {current}' not in spec:
        parser.error('La version des sources RPM ne correspond pas aux sources')
    desktop = (ROOT / 'org.pdenams.Mirivue.Gtk4.desktop').read_text()
    if 'Exec=mirivue-gnome %U' not in desktop or '/home/' in desktop:
        parser.error('Le lanceur de paquet doit être indépendant du compte utilisateur')
    if args.require_license:
        spdx = config.get('license_spdx')
        if not config.get('publication_ready') or not spdx or not (ROOT / 'LICENSE').is_file():
            parser.error('Publication suspendue : choisir la licence GNOME, ajouter LICENSE et confirmer release.json')
        if 'Pending' in spec or f'License:        {spdx}' not in spec:
            parser.error('Mettre à jour la licence du RPM après confirmation')
        if 'Mirivue-Pending' in (ROOT / 'packaging/arch/PKGBUILD.in').read_text():
            parser.error('Mettre à jour aussi la licence Arch')
    print(f'Mirivue GNOME {current} : cohérence des paquets OK')


if __name__ == '__main__':
    main()
