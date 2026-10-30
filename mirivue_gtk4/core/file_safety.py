"""Preflight destructive operations without traversing symbolic links."""

import os
import stat
from pathlib import Path
from ..i18n import tr
from .extensions import fingerprint


def check_removal(path, expected=None, recursive=False):
    path = Path(path).absolute()
    info = path.lstat()
    if expected is not None and fingerprint(path) != expected:
        raise ValueError(tr('La sélection a changé ; opération interrompue.'))
    if not stat.S_ISLNK(info.st_mode):
        if path.parent == path or os.path.ismount(path):
            raise ValueError(tr('Impossible de supprimer la racine d’un volume.'))
        if recursive and stat.S_ISDIR(info.st_mode):
            def failed(error):
                raise error
            for root, dirs, _files in os.walk(path, followlinks=False, onerror=failed):
                for name in dirs:
                    child = Path(root) / name
                    if child.is_symlink():
                        continue
                    if os.path.ismount(child):
                        raise ValueError(tr('Le dossier contient un volume monté ; opération interrompue.'))
    return fingerprint(path)
