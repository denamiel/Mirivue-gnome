"""Verify network transfer integrity in a disposable GH Actions container."""
import hashlib
import os
import runpy
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from mirivue_gtk4.core import gio_backend

Gnome = runpy.run_path(str(Path(__file__).with_name("check-linux-integrations.py")))["Gnome"]

protocol = sys.argv[1]
if protocol == "smb":
    url = "smb://127.0.0.1/mirivue/"
    directory = Path("/tmp/validation-smb")
else:
    directory = Path.home() / "validation-ssh"
    url = f"sftp://validation@127.0.0.1{directory}/"

backend = Gnome()
ports = "139,445" if protocol == "smb" else "22"
rule = ["OUTPUT", "-o", "lo", "-p", "tcp", "-m", "multiport", "--dports", ports,
        "-j", "REJECT", "--reject-with", "tcp-reset"]

def digest(path):
    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()

def remote_file(name):
    for attempt in range(80):
        try:
            mount = backend.mount_share(url)
            mount.query_info("standard::type", backend.gio.FileQueryInfoFlags.NONE, None)
            return mount.get_child(name)
        except backend.glib.Error as error:
            if attempt == 79 or not error.matches(
                backend.gio.io_error_quark(), backend.gio.IOErrorEnum.NOT_MOUNTED
            ):
                raise
            time.sleep(0.1)

def verify(upload, mode, fraction):
    with tempfile.TemporaryDirectory() as folder:
        local_dir = Path(folder)
        filename = "qualification.bin"
        source_path = (local_dir if upload else directory) / filename
        target_path = (directory if upload else local_dir) / filename
        target_path.unlink(missing_ok=True)
        source_path.write_bytes(os.urandom(48 * 1024 * 1024))
        original = digest(source_path)
        if mode != "copy":
            target_path.write_bytes(b"ancienne destination")
            previous = digest(target_path)
        local = backend.gio.File.new_for_path(str(local_dir / filename))
        remote = remote_file(filename)
        source, target = (local, remote) if upload else (remote, local)
        initial_stages = set(target_path.parent.glob(".mirivue-transfer-*"))
        interrupted = []
        fault_errors = []
        complete = threading.Event()
        threshold = round(source_path.stat().st_size * fraction)

        def disconnect():
            try:
                while not complete.wait(0.01):
                    for stage in set(target_path.parent.glob(".mirivue-transfer-*")) - initial_stages:
                        try:
                            written = stage.stat().st_size
                        except FileNotFoundError:
                            continue
                        if threshold <= written < source_path.stat().st_size:
                            subprocess.run(["sudo", "-n", "iptables", "-I", *rule], check=True, timeout=10)
                            interrupted.append(written)
                            return
            except Exception as error:
                fault_errors.append(error)

        watcher = threading.Thread(target=disconnect)
        watcher.start()
        transfer_error = None
        try:
            if mode == "copy":
                gio_backend.transfer([source], target.get_parent())
            else:
                gio_backend.replace(source, target, move=mode == "move")
        except (backend.glib.Error, OSError) as error:
            transfer_error = error
        finally:
            complete.set()
            watcher.join()
            if interrupted:
                subprocess.run(["sudo", "-n", "iptables", "-D", *rule], check=True, timeout=10)

        if fault_errors:
            raise fault_errors[0]
        assert interrupted, f"Coupure jamais déclenchée pour {protocol}, envoi={upload}, {mode}, {fraction:.0%}"
        if transfer_error is None:
            raise AssertionError(f"Transfert terminé malgré la coupure à {interrupted[0]} octets")
        assert digest(source_path) == original, "La source a changé"
        if mode == "copy":
            assert not target_path.exists(), "La copie partielle a été publiée"
        else:
            assert digest(target_path) == previous, "La destination a changé"
        if not upload:
            assert not set(local_dir.glob(".mirivue-transfer-*")), "Copie temporaire locale restante"
        print(f"{protocol} : envoi={upload}, {mode}, seuil={fraction:.0%}, coupure à {interrupted[0]} octets — intégrité vérifiée")

print(f"Début de la qualification {protocol}", flush=True)
for upload in (False, True):
    for mode in ("copy", "replace", "move"):
        for fraction in (0.01, 0.50):
            verify(upload, mode, fraction)

with tempfile.TemporaryDirectory() as folder:
    local = Path(folder) / "qualification.bin"
    local.write_bytes(b"nouvelle destination")
    remote = remote_file(local.name)
    gio_backend.replace(backend.gio.File.new_for_path(str(local)), remote)
    assert (directory / local.name).read_bytes() == local.read_bytes()
    print(f"{protocol} : remplacement sortant abouti — intégrité vérifiée")
