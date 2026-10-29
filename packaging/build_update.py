"""Build a self-contained GNOME updater and its exact source archive."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import base64
import hashlib
import io
import tarfile

source = Path(__file__).resolve().parents[1]
version = source.joinpath('mirivue_gtk4/__init__.py').read_text().split('"')[1]
destination = source.parent
files = sorted(
    path
    for path in source.rglob('*')
    if path.is_file()
    and not any(part in ('__pycache__', '.pytest_cache', '.ruff_cache', '.git') for part in path.parts)
    and path.suffix != '.pyc'
)
with ZipFile(destination / f'Mirivue-GNOME-GTK4-{version}-sources.zip', 'w', ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, path.relative_to(source.parent))
# The sources archive keeps docs/ (release-note history); the installed
# application does not need it.
installed = [path for path in files if path.relative_to(source).parts[0] != 'docs']
payload = io.BytesIO()
with tarfile.open(fileobj=payload, mode='w:gz') as archive:
    for path in installed:
        archive.add(path, arcname=str(path.relative_to(source)), recursive=False)
body = payload.getvalue()
digest = hashlib.sha256(body).hexdigest()
installer = source.joinpath('packaging/install_gnome.py').read_text()
assert f"VERSION = '{version}'" in installer
header = '''#!/usr/bin/env bash
set -euo pipefail
tmp_dir="$(mktemp -d)"
trap 'rm -rf -- "$tmp_dir"' EXIT
sed -n '/^__MIRIVUE_PAYLOAD__$/,$p' "$0" | sed '1d' | base64 -d > "$tmp_dir/app.tar.gz"
/usr/bin/python3 - "$tmp_dir/app.tar.gz" 'HASH' "$@" <<'PYINSTALL'
'''.replace('HASH', digest)
script = destination / f'Mettre-a-jour-Mirivue-GNOME-vers-{version}.run'
script.write_bytes(
    (header + installer + '\nPYINSTALL\nexit 0\n__MIRIVUE_PAYLOAD__\n').encode() + base64.encodebytes(body)
)
script.chmod(0o755)
print(script)
