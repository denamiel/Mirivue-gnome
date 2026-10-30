"""Local media services, durable cache, and one bounded operation queue."""

from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path
import json, os, queue, sqlite3, threading, time, copy
from contextlib import contextmanager
from .core import metadata, media, library, health
from .core.extensions import fingerprint
from .i18n import tr, trf

CACHE_REVISION = 3

COLUMN_MIN_WIDTHS = {
    0: 270,
    1: 130,
    2: 135,
    3: 160,
    4: 160,
    5: 100,
    6: 155,
    7: 120,
    8: 165,
    9: 125,
    10: 145,
    11: 205,
    12: 210,
    14: 195,
    15: 170,
    16: 240,
    17: 160,
    18: 190,
    19: 170,
    20: 170,
    21: 100,
    22: 150,
    23: 150,
    24: 160,
    25: 160,
    26: 205,
    27: 165,
    28: 160,
    29: 160,
    30: 190,
    31: 180,
    32: 130,
    33: 180,
    34: 180,
    35: 220,
    36: 180,
    37: 145,
}


def column_initial_width(index, saved=None):
    minimum = COLUMN_MIN_WIDTHS.get(index, 160)
    return max(minimum, saved if isinstance(saved, int) else minimum)


DEFAULTS = dict(
    language='auto',
    theme='auto',
    split=False,
    preview=False,
    preview_first=False,
    thumbnails=True,
    hidden=False,
    hide_on_start=True,
    startup='home',
    startup_path='',
    tab_session={},
    last_folder='',
    volume_step=5,
    seek_step=10,
    audio_output='',
    history=True,
    recent=True,
    recent_paths=[],
    playback_history=False,
    quality_removed=False,
    reuse_window=True,
    minimize_to_tray=False,
    columns=[0, 1, 14],
    folder_sizes=False,
    date_format='simple',
    icon_captions=[-1, -1, -1],
    remember_folder_view=False,
    folder_views={},
    folders_first=False,
    pane_views={'left': 'details', 'right': 'details'},
    toolbar_order=[
        'home',
        'up',
        'back',
        'forward',
        'refresh',
        'paths',
        'split',
        'details',
        'icons',
        'preview',
        'hidden',
        'thumbnails',
    ],
    toolbar_hidden=['home', 'refresh', 'hidden', 'thumbnails'],
    toolbar_style='icons',
    toolbar_icon_size='normal',
    collections={},
    profiles={},
    column_order=[c for c in range(38) if c != 13],
    pane_column_orders={
        'left': [c for c in range(38) if c != 13],
        'right': [c for c in range(38) if c != 13],
    },
    column_widths={},
    pane_column_widths={'left': {}, 'right': {}},
    external_renamer='',
    external_renamer_args='',
    label_filter='',
)


def reorder_toolbar(order, source, target, after=False):
    """Move one toolbar action around another; the path bar remains an anchor."""
    result = list(order)
    if (
        source not in result
        or target not in result
        or source in ('paths', 'space', 'space1', 'space2')
        or source == target
    ):
        return result
    result.remove(source)
    position = result.index(target) + (1 if after else 0)
    result.insert(position, source)
    return result


def reorder_column_order(order, source, target, after=False):
    """Move a column identifier before or after another without changing peers."""
    result = list(order)
    if source not in result or target not in result or source == target:
        return result
    result.remove(source)
    position = result.index(target) + (1 if after else 0)
    result.insert(position, source)
    return result


def column_order_targets(slot):
    """Return the pane layouts affected by an order edit."""
    return ('left', 'right') if slot == 'both' else (slot,) if slot in ('left', 'right') else ()


class State:
    def __init__(self, root=None):
        self.root = (
            Path(root)
            if root
            else Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'mirivue-gtk4'
        )
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.path = self.root / 'settings.json'
        self.settings = copy.deepcopy(DEFAULTS)
        self.legacy_favorites = []
        try:
            loaded = json.loads(self.path.read_text())
            if isinstance(loaded, dict):
                self.legacy_favorites = (
                    [p for p in loaded.get('favorites', []) if isinstance(p, str)]
                    if isinstance(loaded.get('favorites', []), list)
                    else []
                )
                self.settings.update({k: v for k, v in loaded.items() if k in DEFAULTS})
                # Migrate only the untouched factory column set. Keep every
                # user-customized arrangement intact.
                if loaded.get('columns') == [0, 1, 2, 3, 6, 10, 14]:
                    self.settings['columns'] = [0, 1, 14]
                old_toolbar = [
                    'home',
                    'up',
                    'back',
                    'forward',
                    'refresh',
                    'paths',
                    'search',
                    'split',
                    'details',
                    'icons',
                    'preview',
                    'hidden',
                    'thumbnails',
                    'menu',
                ]
                if loaded.get('toolbar_order') == old_toolbar and loaded.get('toolbar_hidden') == []:
                    self.settings['toolbar_hidden'] = list(DEFAULTS['toolbar_hidden'])
        except (OSError, ValueError, TypeError):
            pass
        self.sanitize_settings()
        self.recovery_notice = ''
        try:
            self.create_tables()
        except sqlite3.DatabaseError:
            database = self.root / 'media.sqlite'
            backup = self.root / ('media.corrupt-' + str(time.time_ns()) + '.sqlite')
            database.replace(backup)
            self.create_tables()
            self.recovery_notice = 'Le cache local était illisible. Il a été conservé dans ' + str(backup)
        if not self.settings['quality_removed']:
            self.clear_quality_scores()
            self.settings['quality_removed'] = True
            self.save()

    def create_tables(self):
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS cache (path TEXT PRIMARY KEY, signature TEXT, row TEXT)')
            db.execute(
                'CREATE TABLE IF NOT EXISTS personal (path TEXT PRIMARY KEY, rating INTEGER, label TEXT)'
            )
            db.execute('UPDATE personal SET rating=0 WHERE rating!=0')

    def sanitize_settings(self):
        for key, default in DEFAULTS.items():
            if type(self.settings.get(key)) is not type(default):
                self.settings[key] = copy.deepcopy(default)
        self.settings['icon_captions'] = [(value if type(value) is int and value in (-1, 1, 2, 3, 14, 17, 19, 20) else -1)
                                            for value in (self.settings['icon_captions'] + [-1, -1, -1])[:3]]
        views = self.settings['pane_views']
        self.settings['pane_views'] = {
            slot: views.get(slot) if views.get(slot) in ('details', 'icons') else 'details'
            for slot in ('left', 'right')
        }
        for key, values in {
            'language': ('auto', 'fr', 'en'),
            'theme': ('auto', 'light', 'dark'),
            'date_format': ('simple', 'detailed'),
            'startup': ('home', 'last', 'custom', 'session'),
        }.items():
            if self.settings[key] not in values:
                self.settings[key] = DEFAULTS[key]
        for key, limit in [('volume_step', 25), ('seek_step', 120)]:
            self.settings[key] = max(1, min(limit, self.settings[key]))
        self.settings['columns'] = list(
            dict.fromkeys(
                [0]
                + [
                    2 if c == 15 else c
                    for c in self.settings['columns']
                    if type(c) is int and 0 <= c < 38 and c not in (12, 13, 16, 36)
                ]
            )
        )
        self.settings['column_order'] = list(
            dict.fromkeys(
                [
                    c
                    for c in self.settings['column_order']
                    if type(c) is int and 0 <= c < 38 and c not in (12, 13, 16)
                ]
                + [c for c in range(38) if c not in (12, 13, 16)]
            )
        )
        # The former single column order becomes the initial order for both
        # sides of a split view; later moves remain local to their side.
        raw_orders = self.settings['pane_column_orders']
        self.settings['pane_column_orders'] = {
            slot: list(
                dict.fromkeys(
                    [
                        c
                        for c in raw_orders.get(slot, self.settings['column_order'])
                        if type(c) is int and 0 <= c < 38 and c not in (12, 13, 16)
                    ]
                    + [c for c in range(38) if c not in (12, 13, 16)]
                )
            )
            for slot in ('left', 'right')
        }
        self.settings['column_widths'] = {
            str(k): max(48, min(900, v))
            for k, v in self.settings['column_widths'].items()
            if str(k).isdigit() and 0 <= int(k) < 38 and int(k) not in (12, 13, 16) and type(v) is int
        }

        # Older settings had one shared width map.  Preserve it as the initial
        # width in both panes, then keep later changes separate.
        def clean_widths(values):
            return {
                str(k): max(48, min(900, v))
                for k, v in values.items()
                if str(k).isdigit() and 0 <= int(k) < 38 and int(k) not in (12, 13, 16) and type(v) is int
            }

        raw_panes = self.settings['pane_column_widths']
        self.settings['pane_column_widths'] = {
            slot: clean_widths(raw_panes.get(slot, {}) or self.settings['column_widths'])
            for slot in ('left', 'right')
        }
        self.settings['recent_paths'] = [p for p in self.settings['recent_paths'] if isinstance(p, str)][:15]
        self.settings['collections'] = {
            k: [p for p in v if isinstance(p, str)]
            for k, v in self.settings['collections'].items()
            if isinstance(k, str) and isinstance(v, list)
        }
        # Old releases exposed stretchable spacer widgets.  Discard them when
        # loading settings; the path bar is now the fixed boundary between
        # leading and trailing controls, as in a GNOME header bar.
        valid_toolbar = set(DEFAULTS['toolbar_order'])
        self.settings['toolbar_order'] = [
            k for k in self.settings['toolbar_order'] if isinstance(k, str) and k in valid_toolbar
        ]
        self.settings['toolbar_order'] = list(
            dict.fromkeys(self.settings['toolbar_order'] + DEFAULTS['toolbar_order'])
        )
        self.settings['toolbar_hidden'] = [
            key
            for key in self.settings['toolbar_hidden']
            if isinstance(key, str) and key in valid_toolbar and key != 'paths'
        ]
        if self.settings['toolbar_style'] not in ('icons', 'both', 'text'):
            self.settings['toolbar_style'] = 'icons'
        if self.settings.get('toolbar_icon_size') not in ('normal', 'large', 'huge'):
            self.settings['toolbar_icon_size'] = 'normal'
        self.settings['profiles'] = {
            k: list(
                dict.fromkeys(
                    2 if c == 15 else c
                    for c in v
                    if type(c) is int and 0 <= c < 38 and c not in (12, 13, 16, 36)
                )
            )
            for k, v in self.settings['profiles'].items()
            if isinstance(k, str) and isinstance(v, list)
        }

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.root / 'media.sqlite', timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self):
        with self.lock:
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2))
            os.replace(temp, self.path)

    def clear_cache(self):
        with self.db() as db:
            db.execute('DELETE FROM cache')

    def clear_quality_scores(self):
        """Remove only calculated quality fields; retain metadata and labels."""
        with self.lock, self.db() as db:
            for path, serialized in list(db.execute('SELECT path,row FROM cache')):
                try:
                    data = json.loads(serialized)
                    if data.get('quality_score') is None:
                        continue
                    data.update(
                        quality_score=None,
                        quality_samples=0,
                        quality_details={},
                        quality_version='',
                        quality_profile_signature='',
                        quality_note='',
                        quality_error='',
                        quality_state='',
                    )
                    data['values'][12] = ''
                    data['sort_values'][12] = -1
                    db.execute('UPDATE cache SET row=? WHERE path=?', (json.dumps(data), path))
                except (ValueError, TypeError, IndexError, KeyError):
                    continue

    def signature(self, path):
        return json.dumps([CACHE_REVISION, fingerprint(path), media.companion_signature(path)])

    def read(self, path):
        try:
            signature = self.signature(path)
            with self.db() as db:
                record = db.execute(
                    'SELECT row FROM cache WHERE path=? AND signature=?', (str(path), signature)
                ).fetchone()
            return library.decode_row(json.loads(record[0])) if record else None
        except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.DatabaseError):
            return None

    def put(self, row):
        # Do not certify stale metadata with a newer filesystem signature.
        if row.file_signature and tuple(row.file_signature) != fingerprint(row.path):
            return
        try:
            with self.db() as db:
                db.execute(
                    'INSERT OR REPLACE INTO cache VALUES (?,?,?)',
                    (str(row.path), self.signature(row.path), json.dumps(library.encode_row(row))),
                )
        except (sqlite3.Error, OSError):
            return False
        return True

    def personal(self, row):
        with self.db() as db:
            record = db.execute('SELECT rating,label FROM personal WHERE path=?', (str(row.path),)).fetchone()
        if record:
            row.personal_label = record[1]
        return row

    def annotate(self, path, label=None):
        with self.db() as db:
            old = db.execute('SELECT rating,label FROM personal WHERE path=?', (str(path),)).fetchone() or (
                0,
                '',
            )
            db.execute(
                'INSERT OR REPLACE INTO personal VALUES (?,?,?)',
                (str(path), 0, old[1] if label is None else label),
            )

    def relocate(self, source, target, copy=False):
        """Retain expensive analysis after a verified copy/move (including trees)."""
        source, target = Path(source), Path(target)
        with self.db() as db:
            records = db.execute('SELECT path,row FROM cache').fetchall()
            personal = db.execute('SELECT path,rating,label FROM personal').fetchall()
        for path, raw in records:
            try:
                relative = Path(path).relative_to(source)
            except ValueError:
                continue
            destination = target / relative
            if not destination.exists():
                continue
            row = library.decode_row(json.loads(raw))
            row.path = destination
            row.file_signature = fingerprint(destination)
            row.values[0] = destination.name
            row.sort_values[0] = destination.name.casefold()
            self.put(row)
            if not copy:
                with self.db() as db:
                    db.execute('DELETE FROM cache WHERE path=?', (path,))
        for path, rating, label in personal:
            try:
                destination = target / Path(path).relative_to(source)
            except ValueError:
                continue
            self.annotate(destination, label=label)
            if not copy:
                with self.db() as db:
                    db.execute('DELETE FROM personal WHERE path=?', (path,))


class MediaService:
    def __init__(self, state):
        self.state = state

    def inspect(self, path, cancelled=lambda: False, force=False):
        path = Path(path)
        row = None if force else self.state.read(path)
        if row is None:
            if path.is_dir():
                row = metadata.basic_entry(path, True)
            elif not path.is_file():
                row = metadata.basic_entry(path)
                row.media_type = 'other'
            elif path.suffix.lower() in metadata.EXTENSIONS | media.IMAGE_EXT | media.AUDIO_EXT:
                row = metadata.inspect(path, cancelled)
            else:
                row = metadata.basic_entry(path)
                row.media_type = 'other'
            if cancelled():
                raise InterruptedError()
            metadata.update_modification(row)
            self.state.put(row)
        return self.state.personal(row)

    def analyze(self, path, kind, cancelled, report):
        try:
            return self._analyze(path, kind, cancelled, report)
        except InterruptedError:
            raise
        except Exception as error:
            try:
                row = self.inspect(path, cancelled)
                row.error = str(error)
                row.values[10] = 'Erreur'
                self.state.put(row)
            except Exception:
                logging.getLogger('mirivue-gtk4').warning(
                    'Enregistrement de l’erreur impossible pour %s', path, exc_info=True
                )
            raise

    def _analyze(self, path, kind, cancelled, report):
        row = self.inspect(path, cancelled)
        row.error = ''
        if kind == 'total':
            seconds = 0
            count = 0
            for folder, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [d for d in dirs if not (Path(folder) / d).is_symlink()]
                for name in files:
                    if cancelled():
                        raise InterruptedError()
                    item = Path(folder) / name
                    if item.is_symlink():
                        continue
                    if item.suffix.lower() not in metadata.EXTENSIONS | media.AUDIO_EXT:
                        continue
                    child = self.inspect(item, cancelled)
                    seconds += max(0, child.sort_values[2])
                    count += 1
                    report(None, trf('\x1f0\x1f médias — \x1f1\x1f', count, metadata.duration(seconds)))
            row.total_duration = seconds
            row.values[2] = metadata.duration(seconds)
            row.sort_values[2] = seconds
            row.values[15] = ''
            row.sort_values[15] = -1
        elif kind == 'test':
            report(None, tr('Vérification de la lecture…'))
            health.check_video(path, cancelled)
            row.validation_status = 'Lecture vérifiée'
            row.values[10] = 'Lecture vérifiée'
        else:
            raise ValueError(tr('Opération inconnue'))
        self.state.put(row)
        return row


@dataclass
class Job:
    title: str
    paths: tuple
    work: object
    analysis: bool = True
    state: str = 'queued'
    fraction: float | None = None
    message: str = ''
    errors: list = field(default_factory=list)
    cancel: threading.Event = field(default_factory=threading.Event)


class JobQueue:
    """One worker across panes; no GTK access, polling supplies coalesced UI updates."""

    def __init__(self):
        self.jobs = []
        self.pending = queue.Queue()
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.paused = threading.Event()
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def submit(self, title, paths, work, analysis=True):
        job = Job(title, tuple(map(Path, paths)), work, analysis)
        self.jobs.append(job)
        self.pending.put(job)
        return job

    def _run(self):
        while not self.stop.is_set():
            try:
                job = self.pending.get(timeout=0.1)
            except queue.Empty:
                continue
            while self.paused.is_set() and not job.cancel.is_set() and not self.stop.wait(0.1):
                pass
            if job.cancel.is_set() or self.stop.is_set():
                job.state = 'cancelled'
                continue
            job.state = 'running'
            for index, path in enumerate(job.paths):
                if job.cancel.is_set() or self.stop.is_set():
                    break
                while self.paused.is_set() and not job.cancel.is_set() and not self.stop.wait(0.1):
                    pass
                if job.cancel.is_set() or self.stop.is_set():
                    break

                def report(fraction, message):
                    job.fraction = None if fraction is None else (index + fraction) / max(1, len(job.paths))
                    job.message = message

                try:
                    report(None, path.name)
                    result = job.work(path, lambda: job.cancel.is_set() or self.stop.is_set(), report)
                    if isinstance(result, dict) and result.get('warning'):
                        job.errors.append((str(path), result['warning']))
                    self.events.put((job, path, result, None))
                except InterruptedError:
                    job.cancel.set()
                    break
                except Exception as error:
                    job.errors.append((str(path), str(error)))
                    self.events.put((job, path, None, str(error)))
                job.fraction = (index + 1) / max(1, len(job.paths))
            job.state = (
                'cancelled'
                if job.cancel.is_set() or self.stop.is_set()
                else 'failed'
                if job.errors
                else 'done'
            )
            self.pending.task_done()

    def cancel_analyses(self):
        for job in self.jobs:
            if job.analysis and job.state in ('queued', 'running'):
                job.cancel.set()

    def close(self):
        self.stop.set()
        for job in self.jobs:
            job.cancel.set()
