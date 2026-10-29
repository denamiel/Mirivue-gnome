"""Create a local empty text document without replacing an existing entry."""

import os
from pathlib import Path
from .file_moves import valid_name, invalid_name_reason


def create_text_file(folder, name):
    name = name.strip()
    if not valid_name(name):
        raise ValueError(invalid_name_reason(name))
    target = Path(folder) / name
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666)
    os.close(descriptor)
    return target
