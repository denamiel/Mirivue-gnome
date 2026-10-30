"""Cached thumbnails and a docked preview with a separate fullscreen surface."""

import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib, os, tempfile, shutil, time
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
gi.require_version('Graphene', '1.0')
from gi.repository import Gtk, Gdk, Gio, GLib, Graphene

try:
    gi.require_version('GnomeDesktop', '4.0')
    from gi.repository import GnomeDesktop
except (ValueError, ImportError):
    GnomeDesktop = None
try:
    gi.require_version('Poppler', '0.18')
    from gi.repository import Poppler
except (ValueError, ImportError):
    Poppler = None
from .core import persistence, audio_output
from .core.extensions import fingerprint
from .i18n import tr


def render_pdf_page(path, page_number, target):
    """Render one local PDF page through Poppler GLib and Cairo."""
    if Poppler is None:
        raise RuntimeError(tr('Le composant Poppler-Glib est requis pour la navigation PDF intégrée.'))
    import cairo

    document = Poppler.Document.new_from_file(Path(path).absolute().as_uri(), None)
    count = document.get_n_pages()
    if not 0 <= page_number < count:
        raise IndexError(page_number)
    page = document.get_page(page_number)
    width, height = page.get_size()
    scale = min(1.8, 8192 / max(width, height), (6000000 / max(1, width * height)) ** 0.5)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, max(1, int(width * scale)), max(1, int(height * scale)))
    context = cairo.Context(surface)
    context.scale(scale, scale)
    page.render(context)
    surface.flush()
    surface.write_to_png(str(target))
    return count


class Thumbnails:
    def __init__(self, root):
        self.root = Path(root) / 'thumbnails'
        self.root.mkdir(parents=True, exist_ok=True)
        self.gnome_factory = (
            GnomeDesktop.DesktopThumbnailFactory.new(GnomeDesktop.DesktopThumbnailSize.LARGE)
            if GnomeDesktop
            else None
        )

    def get(self, path, row, cancelled=lambda: False):
        if row.is_dir:
            return ''
        signature = fingerprint(path)
        key = hashlib.sha256(repr((str(path), signature)).encode()).hexdigest()
        target = self.root / (key + '.png')
        if target.is_file():
            return str(target)
        # GNOME owns the thumbnailer registry and its MIME-specific helpers.
        # This also enables Papers/Evince and office thumbnailers without
        # coupling Mirivue to a document editor or a desktop-specific shell.
        try:
            stat = path.stat()
            uri = path.absolute().as_uri()
            mtime = int(stat.st_mtime)
            content_type = Gio.content_type_guess(path.name, None)[0]
            if not content_type:
                info = Gio.File.new_for_uri(uri).query_info(
                    'standard::content-type', Gio.FileQueryInfoFlags.NONE, None
                )
                content_type = info.get_content_type()
            if (
                content_type
                and self.gnome_factory
                and self.gnome_factory.can_thumbnail(uri, content_type, mtime)
            ):
                cached = self.gnome_factory.lookup(uri, mtime)
                if cached and Path(cached).is_file():
                    return cached
                if cancelled():
                    raise InterruptedError()
                pixbuf = self.gnome_factory.generate_thumbnail(uri, content_type, None)
                if pixbuf is not None and fingerprint(path) == signature:
                    self.gnome_factory.save_thumbnail(pixbuf, uri, mtime, None)
                    cached = self.gnome_factory.lookup(uri, mtime)
                    if cached and Path(cached).is_file():
                        return cached
        except InterruptedError:
            raise
        except Exception as error:
            logging.getLogger('mirivue-gtk4').warning('Miniature GNOME impossible pour %s : %s', path, error)
        # Prefer GNOME's shared thumbnails, validating the original modification time.
        digest = hashlib.md5(path.absolute().as_uri().encode()).hexdigest() + '.png'
        cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'thumbnails'
        for size in ('large', 'x-large', 'normal'):
            candidate = cache / size / digest
            if candidate.is_file() and candidate.stat().st_mtime >= path.stat().st_mtime:
                return str(candidate)
        if row.media_type == 'image':
            try:
                from PIL import Image, ImageOps

                with Image.open(path) as opened:
                    if opened.width * opened.height > 40000000:
                        raise ValueError(tr('Image trop grande'))
                    picture = ImageOps.exif_transpose(opened)
                    picture.thumbnail((1200, 1200))
                    picture = picture.convert('RGBA')
                    fd, name = tempfile.mkstemp(prefix='.picture-', suffix='.png', dir=self.root)
                    os.close(fd)
                    try:
                        picture.save(name, 'PNG')
                        if fingerprint(path) == signature:
                            os.replace(name, target)
                            return str(target)
                    finally:
                        Path(name).unlink(missing_ok=True)
            except Exception as error:
                logging.getLogger('mirivue-gtk4').warning(
                    'Aperçu d’image impossible pour %s : %s', path, error
                )
        if row.media_type == 'audio':
            try:
                from .core.media_tags import read_cover

                cover = read_cover(path)
                if cover:
                    data = cover if isinstance(cover, bytes) and len(cover) <= 20 * 1024 * 1024 else b''
                    if data:
                        fd, name = tempfile.mkstemp(prefix='.cover-', suffix='.png', dir=self.root)
                        try:
                            with os.fdopen(fd, 'wb') as file:
                                file.write(data)
                            os.replace(name, target)
                            return str(target)
                        finally:
                            Path(name).unlink(missing_ok=True)
            except Exception as error:
                logging.getLogger('mirivue-gtk4').warning(
                    'Pochette audio illisible pour %s : %s', path, error
                )
            return ''
        if row.media_type not in ('video', 'audio') and not row.is_video:
            return ''
        fd, name = tempfile.mkstemp(prefix='.thumbnail-', suffix='.png', dir=self.root)
        os.close(fd)
        temp = Path(name)
        try:
            command = ['ffmpeg', '-v', 'error', '-nostdin', '-y']
            if row.is_video:
                command += ['-ss', str(max(0, row.sort_values[2]) * 0.2)]
            command += [
                '-protocol_whitelist',
                'file',
                '-i',
                str(path),
                '-frames:v',
                '1',
                '-vf',
                'thumbnail=20,scale=640:640:force_original_aspect_ratio=decrease'
                if row.is_video
                else 'scale=1200:1200:force_original_aspect_ratio=decrease',
                '-threads',
                '1',
                str(temp),
            ]
            persistence.stream_command(command, lambda _: None, cancelled, timeout=15)
            if temp.stat().st_size and fingerprint(path) == signature:
                os.replace(temp, target)
                return str(target)
        except InterruptedError:
            raise
        except Exception:
            if (
                row.media_type == 'image'
                and path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.gif')
                and path.stat().st_size < 20 * 1024 * 1024
            ):
                return str(path)
        finally:
            temp.unlink(missing_ok=True)
        return ''


class ZoomPicture(Gtk.Widget):
    """A GTK snapshot widget for a fitted image with a centered zoom level."""

    def __init__(self, background='checker'):
        super().__init__(hexpand=True, vexpand=True)
        self.texture = None
        self.zoom = 1.0
        self.background = background

    def clear(self):
        self.texture = None
        self.zoom = 1.0
        self.queue_draw()

    def set_file(self, path, reset_zoom=True):
        self.texture = Gdk.Texture.new_from_file(Gio.File.new_for_path(str(path)))
        if reset_zoom:
            self.zoom = 1.0
        self.queue_draw()

    def adjust_zoom(self, delta):
        if self.texture is None or not delta:
            return False
        factor = 1.18 if delta < 0 else 1 / 1.18
        value = max(0.25, min(8.0, self.zoom * factor))
        if value == self.zoom:
            return False
        self.zoom = value
        self.queue_draw()
        return True

    def theme_color(self, name):
        found, color = self.get_style_context().lookup_color(name)
        return color if found else self.get_color()

    def do_snapshot(self, snapshot):
        if self.texture is None:
            return
        width, height = self.get_width(), self.get_height()
        if width <= 0 or height <= 0:
            return
        scale = min(width / self.texture.get_width(), height / self.texture.get_height()) * self.zoom
        rendered_width = self.texture.get_width() * scale
        rendered_height = self.texture.get_height() * scale
        x, y = (width - rendered_width) / 2, (height - rendered_height) / 2
        rect = Graphene.Rect()
        rect.init(x, y, rendered_width, rendered_height)
        if self.background == 'paper':
            border = Graphene.Rect()
            border.init(x - 1, y - 1, rendered_width + 2, rendered_height + 2)
            snapshot.append_color(self.theme_color('border_color'), border)
            color = Gdk.RGBA()
            color.parse('#ffffff')
            snapshot.append_color(color, rect)
        else:
            # A single 2×2 tile is repeated by the renderer and clipped to
            # the image itself. Opaque pixels cover it; alpha reveals it.
            tile = Graphene.Rect()
            tile.init(x, y, 24, 24)
            snapshot.push_repeat(rect, tile)
            for dy in (0, 12):
                for dx in (0, 12):
                    cell = Graphene.Rect()
                    cell.init(x + dx, y + dy, 12, 12)
                    snapshot.append_color(
                        self.theme_color('view_bg_color' if dx == dy else 'window_bg_color'), cell
                    )
            snapshot.pop()
        snapshot.append_texture(self.texture, rect)


class Preview(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True, vexpand=True)
        self.window = window
        self.items = []
        self.index = 0
        self.current = None
        self.selection_key = None
        self.stream = None
        self.fullscreen = None
        self.dragging = False
        self.control_sets = []
        self.pdf_page = 0
        self.pdf_pages = 0
        self.pdf_generation = 0
        self.pdf_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='pdf-preview')
        self.audio_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='audio-output')
        self.audio_generation = 0
        self.picture = Gtk.Picture(
            can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN, hexpand=True, vexpand=True
        )
        self.image_picture = ZoomPicture()
        self.pdf_picture = ZoomPicture('paper')
        self.unavailable = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            hexpand=True,
            vexpand=True,
        )
        self.unavailable.set_margin_start(16)
        self.unavailable.set_margin_end(16)
        self.unavailable_icon = Gtk.Image(pixel_size=96)
        self.unavailable.append(self.unavailable_icon)
        self.unavailable_label = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.unavailable_label.add_css_class('dim-label')
        self.unavailable.append(self.unavailable_label)
        self.no_preview = False
        self.display = Gtk.Stack(hexpand=True, vexpand=True)
        self.display.add_named(self.picture, 'media')
        self.display.add_named(self.image_picture, 'image')
        self.display.add_named(self.pdf_picture, 'pdf')
        self.display.add_named(self.unavailable, 'unavailable')
        self.append(self.display)
        self.controls = self.make_controls()
        self.append(self.controls)
        self.info = Gtk.Label(wrap=True, xalign=0, selectable=True)
        self.info.set_margin_start(10)
        self.info.set_margin_end(10)
        self.info.set_visible(False)
        scroll = Gtk.ScrolledWindow(max_content_height=180, propagate_natural_height=True)
        scroll.set_child(self.info)
        self.append(scroll)
        self.attach_events(self.picture)
        self.attach_events(self.image_picture)
        self.attach_events(self.pdf_picture)
        self.attach_events(self.unavailable)
        self.timer = GLib.timeout_add(200, self.tick)

    def show_unavailable(self, item):
        content_type = Gio.content_type_guess(item.path.name, None)[0] or 'application/octet-stream'
        app = Gio.AppInfo.get_default_for_type(content_type, False)
        icon = app.get_icon() if app else None
        if icon is None:
            icon = Gio.content_type_get_icon(content_type)
        if icon is None:
            icon = Gio.ThemedIcon.new('application-x-generic-symbolic')
        self.unavailable_icon.set_from_gicon(icon)
        self.unavailable_label.set_label(
            tr('Aperçu indisponible. Double-cliquez pour ouvrir avec {application}.').format(
                application=app.get_name()
            )
            if app
            else tr('Aperçu indisponible. Aucune application par défaut pour ce type de fichier.')
        )
        self.no_preview = True
        self.display.set_visible_child_name('unavailable')

    def make_controls(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_bottom(8)
        progress = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
        progress.set_draw_value(False)
        progress.connect('change-value', lambda scale, scroll, value: self.seek_absolute(value))
        box.append(progress)
        # Capture clicks anywhere on the track instead of GTK's page-sized jump.
        click = Gtk.GestureClick(button=1)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect('pressed', lambda gesture, _n, x, y: self.track_click(gesture, progress, x))
        progress.add_controller(click)
        row = Gtk.Box(spacing=4)
        box.append(row)

        def button(icon, label, callback):
            b = Gtk.Button(icon_name=icon, tooltip_text=tr(label))
            b.add_css_class('flat')
            b.connect('clicked', lambda *_: callback())
            row.append(b)
            return b

        prev = button('media-skip-backward-symbolic', 'Précédent', lambda: self.advance(-1))
        play = button('media-playback-start-symbolic', 'Lire', self.toggle)
        nxt = button('media-skip-forward-symbolic', 'Suivant', lambda: self.advance(1))
        counter = Gtk.Label(hexpand=True)
        row.append(counter)
        volume = Gtk.VolumeButton()
        volume.set_value(0)
        volume.connect('value-changed', self.volume_changed)
        row.append(volume)
        level = Gtk.Label(label='0 %')
        row.append(level)
        output = Gtk.Button(icon_name='audio-speakers-symbolic', tooltip_text=tr('Sortie audio'))
        output.add_css_class('flat')
        output.connect('clicked', self.open_audio_menu)
        row.append(output)
        button(
            'dialog-information-symbolic',
            'Informations',
            lambda: self.info.set_visible(not self.info.get_visible()),
        )
        self.control_sets.append((progress, prev, play, nxt, counter, volume, level, output))
        return box

    def open_audio_menu(self, button):
        pop = Gtk.Popover()
        pop.set_parent(button)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.append(Gtk.Label(label=tr('Recherche des sorties audio…')))
        pop.set_child(box)
        pop.connect('closed', lambda p: GLib.idle_add(lambda: (p.unparent(), False)[1]))
        pop.popup()

        def read():
            try:
                outputs = audio_output.sinks()
                error = None
            except Exception as exc:
                outputs = []
                error = str(exc)

            def present():
                if not pop.get_visible():
                    return False
                while box.get_first_child():
                    box.remove(box.get_first_child())
                if error:
                    box.append(Gtk.Label(label=error, wrap=True))
                    return False
                for sink, label in [('', tr('Sortie système')), *outputs]:
                    choice = Gtk.Button(label=label, halign=Gtk.Align.FILL)
                    choice.add_css_class('flat')
                    if sink == self.window.state.settings['audio_output']:
                        choice.add_css_class('accent')
                    choice.connect(
                        'clicked', lambda _button, s=sink: (self.select_audio_output(s), pop.popdown())
                    )
                    box.append(choice)
                return False

            GLib.idle_add(present)

        self.audio_executor.submit(read)

    def select_audio_output(self, sink):
        self.window.state.settings['audio_output'] = sink
        self.window.state.save()
        if self.stream and self.stream.get_playing():
            self.schedule_audio_route(sink or '@DEFAULT_SINK@')

    def schedule_audio_route(self, sink):
        self.audio_generation += 1
        generation = self.audio_generation
        stream = self.stream

        def run():
            try:
                for _ in range(10):
                    if generation != self.audio_generation or stream is not self.stream:
                        return
                    if audio_output.route(sink):
                        return
                    time.sleep(0.25)
                GLib.idle_add(self.window.notify, tr('Flux audio de Mirivue introuvable.'))
            except Exception as error:
                GLib.idle_add(self.window.notify, str(error))

        self.audio_executor.submit(run)

    def attach_events(self, widget):
        gesture = Gtk.GestureClick(button=0)
        gesture.connect('pressed', self.clicked)
        widget.add_controller(gesture)
        wheel = Gtk.EventControllerScroll.new(
            Gtk.EventControllerScrollFlags.BOTH_AXES | Gtk.EventControllerScrollFlags.DISCRETE
        )
        wheel.connect('scroll', self.wheel)
        widget.add_controller(wheel)

    def clicked(self, gesture, count, x, y):
        if gesture.get_current_button() == 3:
            self.toggle()
        elif count == 2:
            if self.current and self.current.row.is_dir:
                return
            if self.no_preview or (
                self.current
                and self.current.row.media_type not in ('audio', 'video', 'image')
                and not self.is_pdf()
            ):
                self.open_with_system()
            else:
                self.toggle_fullscreen()

    def open_with_system(self):
        if not self.current:
            return
        try:
            Gio.AppInfo.launch_default_for_uri(self.current.path.as_uri(), None)
        except GLib.Error as error:
            self.window.notify(error.message)

    def wheel(self, controller, dx, dy):
        if self.current and self.current.row.media_type == 'image':
            if dx and abs(dx) > abs(dy):
                self.advance_image(1 if dx > 0 else -1)
            elif dy:
                picture = self.fullscreen.image_picture if self.fullscreen else self.image_picture
                picture.adjust_zoom(dy)
            return True
        # Leave the native volume and seek controls in charge of audio/video.
        # Image zoom/navigation above remains available.
        return False

    def track_click(self, gesture, scale, x):
        self.seek_absolute(max(0, min(1, x / max(1, scale.get_width()))))
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def seek_absolute(self, value):
        if self.stream and self.stream.is_seekable():
            self.stream.seek(int(max(0, min(1, value)) * self.stream.get_duration()))
        return True

    def volume_changed(self, button, value):
        if self.stream and abs(self.stream.get_volume() - value) > 0.001:
            self.stream.set_muted(False)
            self.stream.set_volume(value)

    def show_items(self, items):
        paths = [str(i.path) for i in items]
        key = [(str(i.path), i.row.media_type, i.thumbnail) for i in items]
        if key == self.selection_key:
            return
        same_paths = paths == [str(i.path) for i in self.items]
        self.selection_key = key
        self.items = list(items)
        if not same_paths:
            self.index = 0
        if same_paths and self.stream:
            return
        self.load()

    def load(self):
        self.audio_generation += 1
        previous = self.stream
        self.picture.set_paintable(None)
        self.image_picture.clear()
        self.pdf_picture.clear()
        if previous:
            previous.pause()
        self.stream = None
        self.no_preview = False
        self.pdf_generation += 1
        self.pdf_page = 0
        self.pdf_pages = 0
        self.current = self.items[self.index] if self.items else None
        if self.current:
            item = self.current
            row = item.row
            if row.media_type in ('audio', 'video') or row.is_video:
                self.stream = Gtk.MediaFile.new_for_filename(str(item.path))
                self.stream.set_volume(0)
                self.stream.set_muted(False)
                self.picture.set_paintable(self.stream)
                self.display.set_visible_child_name('media')
                self.stream.connect('notify::ended', self.ended)
                self.stream.connect('notify::error', self.media_error)
            elif row.media_type == 'image':
                # Render the original through GDK instead of enlarging a
                # thumbnail. GTK chooses the native texture representation.
                try:
                    self.image_picture.set_file(item.path)
                    self.display.set_visible_child_name('image')
                except (GLib.Error, OSError):
                    self.show_unavailable(item)
            elif item.thumbnail and item.path.suffix.casefold() == '.pdf':
                try:
                    self.pdf_picture.set_file(item.thumbnail)
                    self.display.set_visible_child_name('pdf')
                except (GLib.Error, OSError):
                    self.show_unavailable(item)
            elif item.thumbnail:
                try:
                    self.picture.set_filename(item.thumbnail)
                    self.display.set_visible_child_name('media')
                except (GLib.Error, OSError):
                    self.show_unavailable(item)
            else:
                self.show_unavailable(item)
            lines = [item.path.name] + [
                f'{tr(title)} : {tr(str(value)) if title in ("État", "Type de média", "HDR/SDR") else str(value)}'
                for title, value in zip(
                    __import__('mirivue_gtk4.core.metadata', fromlist=['HEADERS']).HEADERS, row.values
                )
                if value not in ('', '—')
            ]
            lines += [f'{key} : {value}' for key, value in row.media_technical.items()]
            self.info.set_label('\n'.join(lines))
        else:
            self.display.set_visible_child_name('media')
            self.info.set_label(tr('Choisissez un fichier pour afficher ses informations.'))
        self.sync_fullscreen_picture()
        self.tick()

    def sync_fullscreen_picture(self):
        if not self.fullscreen:
            return
        if self.current and self.current.row.media_type == 'image':
            try:
                self.fullscreen.image_picture.set_file(self.current.path)
                self.fullscreen.display.set_visible_child_name('image')
            except GLib.Error as error:
                self.window.notify(error.message)
        elif self.is_pdf():
            self.fullscreen.pdf_picture.clear()
            if self.current.thumbnail:
                try:
                    self.fullscreen.pdf_picture.set_file(self.current.thumbnail)
                except GLib.Error as error:
                    self.window.notify(error.message)
            self.fullscreen.display.set_visible_child_name('pdf')
        else:
            self.fullscreen.picture.set_paintable(self.picture.get_paintable())
            self.fullscreen.display.set_visible_child_name('media')

    def ended(self, stream, *_):
        if stream.get_ended() and self.index + 1 < len(self.items):
            self.advance(1)
            self.toggle()

    def media_error(self, stream, *_):
        error = stream.get_error()
        if error and self.stream is stream and self.current:
            self.stream = None
            self.show_unavailable(self.current)
            self.tick()

    def advance(self, delta):
        if self.is_pdf() and self.fullscreen and self.pdf_pages:
            page = max(0, min(self.pdf_pages - 1, self.pdf_page + delta))
            if page != self.pdf_page:
                self.pdf_page = page
                self.render_pdf_page()
            return
        new = self.index + delta
        if 0 <= new < len(self.items):
            self.index = new
            self.load()

    def advance_image(self, delta):
        """Browse image files in the active folder, independently of selection."""
        if not self.current or self.current.row.media_type != 'image':
            return False
        pane = self.window.active
        images = [pane.sorted.get_item(index) for index in range(pane.sorted.get_n_items())]
        images = [item for item in images if not item.row.is_dir and item.row.media_type == 'image']
        try:
            current = next(index for index, item in enumerate(images) if item.path == self.current.path)
        except StopIteration:
            return False
        target = current + delta
        if not 0 <= target < len(images):
            return False
        self.items = images
        self.index = target
        self.load()
        return True

    def is_pdf(self):
        return bool(self.current and self.current.path.suffix.casefold() == '.pdf')

    def render_pdf_page(self):
        if not self.is_pdf() or not self.fullscreen:
            return
        self.pdf_generation += 1
        generation = self.pdf_generation
        path = self.current.path
        page_number = self.pdf_page
        self.pdf_executor.submit(self._render_pdf_page, path, page_number, generation)

    def _render_pdf_page(self, path, page_number, generation):
        try:
            source_signature = fingerprint(path)
            cache = Path(self.window.state.root) / 'document-pages'
            cache.mkdir(parents=True, exist_ok=True)
            signature = hashlib.sha256(f'{path}:{source_signature}:{page_number}'.encode()).hexdigest()
            target = cache / (signature + '.png')
            if target.is_file():
                count = Poppler.Document.new_from_file(path.as_uri(), None).get_n_pages()
                GLib.idle_add(self.finish_pdf_render, path, page_number, count, str(target), generation)
                return
            temp = target.with_suffix('.tmp.png')
            count = render_pdf_page(path, page_number, temp)
            os.replace(temp, target)
            if fingerprint(path) != source_signature:
                target.unlink(missing_ok=True)
                return
            GLib.idle_add(self.finish_pdf_render, path, page_number, count, str(target), generation)
        except Exception as error:
            GLib.idle_add(self.window.notify, tr('Impossible de lire cette page PDF.') + ' ' + str(error))

    def finish_pdf_render(self, path, page_number, count, filename, generation):
        if (
            generation != self.pdf_generation
            or not self.fullscreen
            or not self.current
            or path != self.current.path
        ):
            return False
        self.pdf_page = page_number
        self.pdf_pages = count
        self.pdf_picture.set_file(filename)
        self.display.set_visible_child_name('pdf')
        if self.fullscreen:
            self.fullscreen.pdf_picture.set_file(filename)
            self.fullscreen.display.set_visible_child_name('pdf')
        self.tick()
        return False

    def toggle(self):
        if self.stream:
            if self.stream.get_playing():
                self.stream.pause()
            else:
                self.window.record_playback(self.current.path)
                self.stream.play()
                sink = self.window.state.settings.get('audio_output', '')
                if sink:
                    self.schedule_audio_route(sink)

    def tick(self):
        for progress, prev, play, nxt, counter, volume, level, output in self.control_sets:
            is_media = self.stream is not None
            is_pdf = self.is_pdf() and self.fullscreen is not None
            for widget in (progress, play, volume, level):
                widget.set_visible(is_media)
            output.set_visible(is_media and shutil.which('pactl') is not None)
            has_pages = is_pdf and self.pdf_pages > 1
            prev.set_visible(len(self.items) > 1 or has_pages)
            nxt.set_visible(len(self.items) > 1 or has_pages)
            prev.set_sensitive(self.pdf_page > 0 if is_pdf else self.index > 0)
            nxt.set_sensitive(
                self.pdf_page + 1 < self.pdf_pages if is_pdf else self.index + 1 < len(self.items)
            )
            counter.set_label(
                f'{self.pdf_page + 1} / {self.pdf_pages}'
                if has_pages
                else f'{self.index + 1} / {len(self.items)}'
                if len(self.items) > 1
                else ''
            )
            if is_media:
                duration = self.stream.get_duration()
                progress.set_value(self.stream.get_timestamp() / duration if duration else 0)
                progress.set_sensitive(self.stream.is_seekable())
                play.set_icon_name(
                    'media-playback-pause-symbolic'
                    if self.stream.get_playing()
                    else 'media-playback-start-symbolic'
                )
                volume.set_value(self.stream.get_volume())
                level.set_label(f'{round(self.stream.get_volume() * 100)} %')
        return True

    def toggle_fullscreen(self):
        if self.fullscreen:
            self.exit_fullscreen()
            return
        if not self.current:
            return
        win = Gtk.Window(transient_for=self.window, title=self.current.path.name)
        win.set_default_size(900, 600)
        overlay = Gtk.Overlay()
        display = Gtk.Stack(hexpand=True, vexpand=True)
        picture = Gtk.Picture(
            can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN, paintable=self.picture.get_paintable()
        )
        image_picture = ZoomPicture()
        pdf_picture = ZoomPicture('paper')
        display.add_named(picture, 'media')
        display.add_named(image_picture, 'image')
        display.add_named(pdf_picture, 'pdf')
        overlay.set_child(display)
        win.picture = picture
        win.image_picture = image_picture
        win.pdf_picture = pdf_picture
        win.display = display
        controls = self.make_controls()
        controls.set_valign(Gtk.Align.END)
        controls.add_css_class('osd')
        overlay.add_overlay(controls)
        win.set_child(overlay)
        self.attach_events(picture)
        self.attach_events(image_picture)
        self.attach_events(pdf_picture)
        keys = Gtk.EventControllerKey()
        keys.connect('key-pressed', self.fullscreen_keys)
        win.add_controller(keys)
        win.connect('close-request', lambda *_: (self.exit_fullscreen(), True)[1])
        self.fullscreen = win
        self.sync_fullscreen_picture()
        win.fullscreen()
        win.present()
        if self.is_pdf():
            self.render_pdf_page()

    def fullscreen_keys(self, controller, key, keycode, state):
        if key == Gdk.KEY_Escape:
            self.exit_fullscreen()
        elif key in (Gdk.KEY_Left, Gdk.KEY_Up, Gdk.KEY_Page_Up):
            self.advance(-1)
        elif key in (Gdk.KEY_Right, Gdk.KEY_Down, Gdk.KEY_Page_Down):
            self.advance(1)
        elif key == Gdk.KEY_space:
            self.toggle()
        else:
            return False
        return True

    def exit_fullscreen(self):
        if self.fullscreen:
            win = self.fullscreen
            self.fullscreen = None
            self.control_sets.pop()
            win.destroy()

    def close(self):
        self.audio_generation += 1
        self.exit_fullscreen()
        if self.stream:
            self.stream.pause()
        self.pdf_generation += 1
        self.pdf_executor.shutdown(wait=False, cancel_futures=True)
        self.audio_executor.shutdown(wait=False, cancel_futures=True)
        GLib.source_remove(self.timer)
