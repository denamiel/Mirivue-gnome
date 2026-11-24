"""Integration checks run in a disposable GNOME or Plasma desktop session."""
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from types import SimpleNamespace

from PIL import Image


def wait_for(predicate):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError("Le résultat attendu n’est pas apparu.")


class Gnome:
    def __init__(self):
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gio, GLib, Gtk

        Gtk.init()
        self.application = Adw.Application(application_id="org.pdenams.Mirivue.validation",
                                           flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.application.register(None)
        self.gio = Gio
        self.glib = GLib

    def wait_for_event(self, ready):
        context = self.glib.MainContext.default()

        def probe():
            while context.pending():
                context.iteration(False)
            return ready()

        return wait_for(probe)

    def desktop_window(self, directory):
        from mirivue_gtk4.app import MirivueWindow
        from mirivue_gtk4.backend import State

        window = MirivueWindow(self.application, state=State(directory), restore_session=False)
        window.present()
        return window

    def check_removable_volume(self):
        mountpoint = Path("/media/validation/MIRIVUE_EXT4")
        monitor = self.gio.VolumeMonitor.get()

        def find_volume():
            return next((volume for volume in monitor.get_volumes()
                         if volume.get_name() == "MIRIVUE_EXT4"
                         or (volume.get_mount() is not None
                             and volume.get_mount().get_root().get_path() == str(mountpoint))), None)

        volume = self.wait_for_event(find_volume)
        with tempfile.TemporaryDirectory() as state:
            window = self.desktop_window(Path(state))
            try:
                mount = self.wait_for_event(volume.get_mount)
                window.unmount_volume(mount)
                self.wait_for_event(lambda: volume.get_mount() is None)
                window.mount_volume(volume)
                mount = self.wait_for_event(volume.get_mount)
                self.wait_for_event(lambda: window.active.folder == Path(mount.get_root().get_path()))
                window.unmount_volume(mount, mount.can_eject())
                self.wait_for_event(lambda: volume.get_mount() is None)
            finally:
                window.shutdown()

    def trash_roundtrip(self, file):
        from mirivue_gtk4.core import trash
        from mirivue_gtk4.core.undo import TrashRecord, UndoManager

        uri = trash.trash_tracked(file)
        assert uri and not file.exists(), file
        manager = UndoManager()
        manager.record_prepared(TrashRecord(file, uri, trash.entry_signature(uri)))
        manager.undo()
        assert file.read_bytes() == b"Mirivue\n"
        manager.redo()
        assert not file.exists()
        manager.undo()
        assert file.read_bytes() == b"Mirivue\n"

    def download(self, url, destination):
        from mirivue_gtk4.core import gio_backend

        remote = self.gio.File.new_for_uri(url)
        loop = self.glib.MainLoop()
        operation = self.gio.MountOperation()
        errors = []

        def finish(source, result):
            try:
                source.mount_enclosing_volume_finish(result)
            except self.glib.Error as error:
                if not error.matches(self.gio.io_error_quark(), self.gio.IOErrorEnum.ALREADY_MOUNTED):
                    errors.append(error)
            finally:
                loop.quit()

        operation.connect("ask-password", self._authenticate)
        remote.mount_enclosing_volume(self.gio.MountMountFlags.NONE, operation, None, finish)
        loop.run()
        if errors:
            raise errors[0]
        entries = gio_backend.browse(remote)
        child, = [entry[1] for entry in entries if entry[1].get_basename() == "exemple.txt"]
        gio_backend.transfer([child], self.gio.File.new_for_path(str(destination)))

    def _authenticate(self, operation, _message, _user, _domain, flags):
        if flags & self.gio.AskPasswordFlags.ANONYMOUS_SUPPORTED:
            operation.set_anonymous(True)
            operation.reply(self.gio.MountOperationResult.HANDLED)
        else:
            operation.reply(self.gio.MountOperationResult.ABORTED)

    def check_media(self, directory):
        from mirivue_gtk4.core.media import inspect_media
        from mirivue_gtk4.preview import render_pdf_page

        assert render_pdf_page(directory / "test.pdf", 0, directory / "page.png") == 1
        assert Image.open(directory / "page.png").width > 0
        with tempfile.TemporaryDirectory() as state:
            window = self.desktop_window(Path(state))
            try:
                for name in ("test.wav", "test.webm"):
                    path = directory / name
                    row = inspect_media(path)
                    assert row.media_technical, name
                    window.preview.show_items([SimpleNamespace(path=path, row=row, thumbnail="")])
                    window.preview.toggle()
                    stream = window.preview.stream

                    def started():
                        error = stream.get_error()
                        assert error is None, error
                        return stream.get_timestamp() > 150_000

                    self.wait_for_event(started)
                    window.preview.toggle()
                    self.wait_for_event(lambda: not stream.get_playing())
            finally:
                window.shutdown()


class Kde:
    def __init__(self):
        from PySide6.QtWidgets import QApplication
        from mirivue.platform_services import services

        self.app = QApplication([])
        self.services = services

    def request(self, command, sources, destination=""):
        ok, error = self.services._kio_service_request(
            command, sources=sources, destination=destination, timeout=30
        )
        assert ok, (command, error)

    def trash_roundtrip(self, file):
        self.request("trash", [file.as_uri()])
        assert not file.exists(), file

        def find():
            entries = self.services.list_kio_location("trash:/") or ()
            return [entry["url"] for entry in entries if entry.get("originalPath") == str(file)]

        uri, = wait_for(find)
        self.request("restore", [uri])
        assert file.read_bytes() == b"Mirivue\n"

    def download(self, url, destination):
        entries = self.services.list_kio_location(url)
        assert entries is not None, url
        child, = [entry["url"] for entry in entries if entry["realName"] == "exemple.txt"]
        self.request("copy", [child], destination.as_uri())

    def check_media(self, directory):
        from mirivue.media import inspect_media
        from mirivue.media_preview import render_pdf_page

        image, pages = render_pdf_page(directory / "test.pdf")
        assert pages == 1 and not image.isNull()
        for name in ("test.wav", "test.mp4"):
            assert inspect_media(directory / name).media_technical, name


def run(backend):
    failures = []
    for label in ("EXT4", "NTFS"):
        directory = Path("/media/validation") / f"MIRIVUE_{label}"
        try:
            with tempfile.TemporaryDirectory(dir=directory) as sample:
                file = Path(sample) / "corbeille.txt"
                file.write_bytes(b"Mirivue\n")
                backend.trash_roundtrip(file)
            print(f"Corbeille et restauration sur {label} vérifiées", flush=True)
        except Exception:
            traceback.print_exc()
            failures.append(label)

    if isinstance(backend, Gnome):
        try:
            backend.check_removable_volume()
            print("Montage et démontage du volume USB depuis Mirivue vérifiés", flush=True)
        except Exception:
            traceback.print_exc()
            failures.append("montage USB")

    local_sftp = f"sftp://validation@127.0.0.1{Path.home()}/validation-ssh/"
    for url, expected in (("smb://127.0.0.1/mirivue/", b"smb-fixture\n"), (local_sftp, b"sftp-fixture\n")):
        protocol = url.split(":", 1)[0]
        try:
            with tempfile.TemporaryDirectory() as destination:
                target = Path(destination)
                backend.download(url, target)
                assert (target / "exemple.txt").read_bytes() == expected
            print(f"Copie et contenu vérifiés depuis {protocol}", flush=True)
        except Exception:
            traceback.print_exc()
            failures.append(protocol)

    try:
        with tempfile.TemporaryDirectory() as media:
            directory = Path(media)
            with Image.new("RGB", (80, 100), "white") as image:
                image.save(directory / "test.pdf")
            ffmpeg = shutil.which("ffmpeg")
            assert ffmpeg
            for source, output in (("sine=frequency=440", "test.wav"), ("color=c=blue:s=80x80:r=10", "test.webm")):
                subprocess.run(
                    [ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i", source,
                     "-t", "3", str(directory / output)],
                    check=True, timeout=30,
                )
            backend.check_media(directory)
        print("Rendu PDF, lecture et pause des fichiers audio et vidéo vérifiés", flush=True)
    except Exception:
        traceback.print_exc()
        failures.append("médias")

    if failures:
        raise SystemExit("Vérifications en échec — " + ", ".join(failures))


if __name__ == "__main__":
    backend = Gnome() if sys.argv[1] == "mirivue-gnome" else Kde()
    try:
        run(backend)
    finally:
        if isinstance(backend, Kde):
            backend.services.shutdown_kio_service()
