"""Fast, local summary of the rows already displayed by a browser pane."""

from ..i18n import size_text, tr
from .metadata import quantity


def summarize(rows, selected=()):
    rows = list(rows)
    selected = list(selected)
    visible = selected if selected else rows
    folders = sum(bool(row.is_dir) for row in visible)
    files = len(visible) - folders
    total = sum(
        row.sort_values[1]
        for row in visible
        if not row.is_dir and isinstance(row.sort_values[1], (int, float)) and row.sort_values[1] > 0
    )
    label = ', '.join(
        (
            f'{folders} {tr("dossier" if folders == 1 else "dossiers")}',
            f'{files} {tr("fichier" if files == 1 else "fichiers")}',
        )
    )
    if total:
        label += f' ({size_text(quantity(total, ["o", "Kio", "Mio", "Gio", "Tio"], 1024))})'
    if selected:
        label = tr('Sélection : ') + label
    errors = sum(bool(row.error) for row in rows)
    if errors:
        label += f' • {errors} {tr("erreur" if errors == 1 else "erreurs")}'
    return label
