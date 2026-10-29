"""Back up an old user launcher which would mask the distribution launcher."""

import argparse
import os
from pathlib import Path
import time

APP_ID = 'org.pdenams.Mirivue.Gtk4'


def transition(data, state, apply=False):
    desktop = data / 'applications' / f'{APP_ID}.desktop'
    if not desktop.is_file() or desktop.is_symlink():
        return None
    text = desktop.read_text()
    old_launcher = str(data / 'mirivue-gtk4/Lancer.sh').replace('\\', '\\\\').replace(' ', '\\ ')
    if f'Exec={old_launcher} %U' not in text or f'Icon={APP_ID}' not in text:
        raise ValueError('Le lanceur personnel ne correspond pas à celui de l’ancien installateur ; il est conservé.')
    if not apply:
        return desktop
    backup = state / 'mirivue-gtk4' / 'anciens-lanceurs' / str(time.time_ns())
    backup.mkdir(parents=True, exist_ok=False)
    destination = backup / desktop.name
    desktop.rename(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='déplacer le seul ancien lanceur dans une sauvegarde')
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error('Lancer cette commande avec votre compte utilisateur, sans sudo.')
    data = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    state = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state')
    try:
        result = transition(data, state, args.apply)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(('Ancien lanceur sauvegardé : ' if args.apply else 'Ancien lanceur détecté : ') + str(result)
          if result else 'Aucun ancien lanceur personnel à déplacer.')


if __name__ == '__main__':
    main()
