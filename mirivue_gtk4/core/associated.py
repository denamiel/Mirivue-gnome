"""Find nearby files that belong to the same media without changing them."""

from pathlib import Path

SUBTITLES = {'.srt', '.ass', '.ssa', '.vtt', '.sub', '.idx'}
SIDECARS = {'.nfo', '.chapters', '.txt', '.cue', '.lrc'}
RAW = {'.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.rw2'}
PHOTOS = {'.jpg', '.jpeg', '.png', '.heic', '.webp'}
COVERS = {'.jpg', '.jpeg', '.png', '.webp'}
VIDEO = {'.mkv', '.mp4', '.mov', '.avi', '.webm', '.m4v', '.ts', '.m2ts'}
AUDIO = {'.mp3', '.flac', '.m4a', '.ogg', '.opus', '.wav', '.aac'}


def find_associated(paths):
    sources = [Path(path) for path in paths]
    selected = set(sources)
    found = set()
    for source in sources:
        if not source.is_file() or source.is_symlink():
            continue
        suffix = source.suffix.lower()
        if suffix not in VIDEO | AUDIO | RAW | PHOTOS:
            continue
        try:
            candidates = source.parent.iterdir()
        except OSError:
            continue
        for candidate in candidates:
            if (
                candidate in selected
                or candidate in found
                or not candidate.is_file()
                or candidate.is_symlink()
            ):
                continue
            other = candidate.suffix.lower()
            if suffix in VIDEO:
                match = (
                    candidate.stem.casefold() == source.stem.casefold() and other in SIDECARS | SUBTITLES
                ) or (
                    other in SUBTITLES and candidate.stem.casefold().startswith(source.stem.casefold() + '.')
                )
            elif suffix in AUDIO:
                match = candidate.stem.casefold() == source.stem.casefold() and other in SIDECARS | COVERS
            else:
                match = candidate.stem.casefold() == source.stem.casefold() and (
                    other in PHOTOS if suffix in RAW else other in RAW
                )
            # XMP sidecars are already handled by the existing transfer engine.
            if match:
                found.add(candidate)
    return sorted(found, key=lambda path: str(path).casefold())
