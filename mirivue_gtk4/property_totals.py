"""Native property rows updated off the GTK thread and cancelled on close."""
from concurrent.futures import ThreadPoolExecutor
from gi.repository import Adw, Gio, GLib
from .i18n import tr, trf
from .core.file_information import summarize_files


def add_totals(dialog, group, files):
    cancelled = Gio.Cancellable()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='properties')
    contents = Adw.ActionRow(title=tr('Contenu'), subtitle=tr('Calcul en cours…'))
    size = Adw.ActionRow(title=tr('Taille totale'), subtitle=tr('Calcul en cours…'))
    locations = Adw.ActionRow(title=tr('Emplacements'))
    types = Adw.ActionRow(title=tr('Types'))
    warning = Adw.ActionRow(title=tr('Résultat partiel'), visible=False)
    for row in (contents, size, locations, types, warning):
        row.set_subtitle_selectable(True)
        group.add(row)

    def closed(*_):
        cancelled.cancel()
        executor.shutdown(wait=False, cancel_futures=True)

    dialog.connect('closed', closed)

    def publish(future):
        if cancelled.is_cancelled():
            return False
        try:
            data = future.result()
        except Exception as error:
            warning.set_subtitle(str(error))
            warning.set_visible(True)
            contents.set_subtitle(tr('Calcul interrompu'))
            size.set_subtitle('—')
        else:
            contents.set_subtitle(trf('\x1f0\x1f fichiers, \x1f1\x1f dossiers', data['files'], data['folders']))
            size.set_subtitle(GLib.format_size(data['bytes']))
            locations.set_subtitle('\n'.join(sorted(data['locations'])))
            types.set_subtitle(', '.join(sorted(data['types'])))
            warning.set_visible(bool(data['errors']))
            warning.set_subtitle('\n'.join(data['errors'][:5]))
        executor.shutdown(wait=False)
        return False

    future = executor.submit(summarize_files, files, cancelled)
    future.add_done_callback(lambda result: GLib.idle_add(publish, result))
