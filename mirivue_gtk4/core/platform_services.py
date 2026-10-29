import os, errno, shutil
from pathlib import Path
from ..i18n import tr


class PlatformServices:
    name = "linux"

    def cache_directory(self):
        return Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))) / "mirivue-gtk4"

    def tool_path(self, name):
        return shutil.which(name)

    def rename_no_replace(self, source: Path, target: Path) -> None:
        """Atomically publish a same-volume rename without replacing a target (Linux)."""
        source, target = (Path(source), Path(target))
        try:
            self._renameat2_noreplace(source, target)
        except OSError as error:
            # Some filesystems (certain FUSE or network mounts) reject the
            # RENAME_NOREPLACE flag. Fall back without ever overwriting.
            if error.errno not in self.NOREPLACE_UNSUPPORTED:
                raise
            self._rename_fallback(source, target)

    NOREPLACE_UNSUPPORTED = {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS}

    def _renameat2_noreplace(self, source: Path, target: Path) -> None:
        import ctypes

        library = ctypes.CDLL(None, use_errno=True)
        rename = getattr(library, 'renameat2', None)
        if rename is None:
            raise OSError(errno.ENOSYS, tr('Renommage sécurisé indisponible sur ce système.'), str(target))
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(target), 1):
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code), str(target))

    def _rename_fallback(self, source: Path, target: Path) -> None:
        """Rename without RENAME_NOREPLACE, never replacing an existing target.

        Files and symlinks: a hard link is created first (atomic, fails if the
        target exists), then the source name is removed. Directories, or
        filesystems without hard links: existence check then os.rename(); the
        remaining race window is tiny and only concerns concurrent writers.
        """
        if not (source.is_dir() and not source.is_symlink()):
            try:
                os.link(source, target, follow_symlinks=False)
            except FileExistsError:
                raise
            except OSError as error:
                if error.errno == errno.EXDEV:
                    raise
            else:
                try:
                    os.unlink(source)
                except OSError:
                    os.unlink(target)
                    raise
                return
        if os.path.lexists(target):
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(target))
        os.rename(source, target)

    def validate_portable_name(self, name: str) -> str | None:
        'Return a clear reason when a name cannot safely travel between OSes.'
        if not name or name.strip() != name or name in ('.', '..'):
            return tr('Choisissez un nom non vide.')
        if any((character in name for character in '<>:"/\\|?*\x00')):
            return tr('Ce nom contient un caractère incompatible avec Windows.')
        if name.endswith((' ', '.')):
            return tr('Un nom ne peut pas se terminer par un espace ou un point.')
        stem = name.split('.', 1)[0].upper()
        if stem in {'CON', 'PRN', 'AUX', 'NUL'} or stem in {
            f'{port}{i}' for port in ('COM', 'LPT') for i in range(1, 10)
        }:
            return tr('Ce nom est réservé par Windows.')
        return None


services = PlatformServices()
