"""Produce the same release tarball for COPR, GitHub and Arch."""

import argparse
import gzip
import hashlib
import io
from pathlib import Path
import tarfile

from check_release import ROOT, version

EXCLUDED = {'.git', '__pycache__', '.venv', '.pytest_cache', '.ruff_cache', 'dist', 'build'}


def build(destination, make_aur=True):
    current = version()
    prefix = f'mirivue-gnome-{current}'
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / f'{prefix}.tar.gz'
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w', format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(ROOT.rglob('*')):
            rel = path.relative_to(ROOT)
            if (not path.is_file() or path.is_symlink() or any(p in EXCLUDED or p.endswith('.egg-info') for p in rel.parts)
                    or path.is_relative_to(destination / 'aur') or path.is_relative_to(ROOT / 'packaging/fedora/aur')
                    or path.suffix in ('.pyc', '.run', '.zip', '.sha256') or path.name.endswith(('.tar.gz', '.rpm', '.pkg.tar.zst'))):
                continue
            info = archive.gettarinfo(str(path), arcname=f'{prefix}/{rel.as_posix()}')
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            info.mtime = 0
            info.mode = 0o755 if path.suffix == '.sh' else 0o644
            with path.open('rb') as stream:
                archive.addfile(info, stream)
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, filename='', mode='wb', mtime=0) as stream:
        stream.write(payload.getvalue())
    target.write_bytes(compressed.getvalue())
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (destination / f'{target.name}.sha256').write_text(f'{digest}  {target.name}\n')
    if make_aur:
        aur = destination / 'aur'
        aur.mkdir(exist_ok=True)
        recipe = (ROOT / 'packaging/arch/PKGBUILD.in').read_text()
        (aur / 'PKGBUILD').write_text(recipe.replace('@VERSION@', current).replace('@SHA256@', digest))
    print(target)
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--no-aur', action='store_true')
    args = parser.parse_args()
    build(args.output.resolve(), not args.no_aur)
