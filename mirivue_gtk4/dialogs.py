"""Non-blocking GTK dialogs: explicit previews before batch mutations."""

from pathlib import Path
import csv, shutil, threading, stat, pwd, grp
import gi

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Adw, Gtk, Gio, Gdk, GLib, GObject, Pango
from .i18n import tr
from .backend import reorder_toolbar, reorder_column_order, column_order_targets
from .core import media, metadata, media_tags, renaming, file_moves, extensions, duplicates, gio_backend


def choice(parent, title, body, options, callback):
    dialog = Adw.AlertDialog(heading=title, body=body)
    dialog.add_response('cancel', tr('Annuler'))
    dialog.set_close_response('cancel')
    for label, key in options:
        dialog.add_response(key, label)
    dialog.connect('response', lambda _d, value: callback(value) if value != 'cancel' else None)
    dialog.present(parent)
    return dialog


def confirm(parent, title, body, callback):
    return choice(parent, title, body, [(tr('Confirmer'), 'yes')], lambda _: callback())


def message(parent, title, body):
    return choice(parent, title, body, [], lambda _: None)


def reorder_handle():
    # Some icon themes omit the Adwaita drag grip. Let GIO choose the native
    # grip when present and a standard themed vertical-dots icon otherwise.
    icon = Gio.ThemedIcon.new('list-drag-handle-symbolic')
    icon.append_name('view-more-symbolic')
    handle = Gtk.Image.new_from_gicon(icon)
    handle.set_tooltip_text(tr('Faire glisser pour déplacer'))
    return handle


def text_input(parent, title, initial, callback):
    dialog = Adw.AlertDialog(heading=title)
    entry = Gtk.Entry(text=initial, activates_default=True)
    dialog.set_extra_child(entry)
    dialog.add_response('cancel', tr('Annuler'))
    dialog.add_response('ok', tr('Valider'))
    dialog.set_default_response('ok')
    dialog.set_close_response('cancel')
    dialog.connect('response', lambda _d, value: callback(entry.get_text()) if value == 'ok' else None)
    dialog.present(parent)
    entry.grab_focus()
    return dialog


def window(parent, title, width=750, height=540):
    win = Adw.Window(
        transient_for=parent, modal=False, title=title, default_width=width, default_height=height
    )
    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    header.set_title_widget(Gtk.Label(label=title, css_classes=['title']))
    toolbar.add_top_bar(header)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_start(12)
    box.set_margin_end(12)
    box.set_margin_top(8)
    box.set_margin_bottom(12)
    toolbar.set_content(box)
    win.set_content(toolbar)
    return win, box, header


def properties(parent, paths, media_row=None):
    """GNOME-style details and optional local Unix permissions for one item."""
    if not paths:
        return
    if len(paths) != 1:
        dialog = Adw.PreferencesDialog(title=tr('Propriétés'))
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup()
        page.add(group)
        dialog.add(page)
        from .property_totals import add_totals
        add_totals(dialog, group, [Gio.File.new_for_path(str(path)) for path in paths])
        dialog.present(parent)
        return dialog
    from .core import permissions

    path = Path(paths[0])
    info = path.lstat()
    directory = stat.S_ISDIR(info.st_mode)
    link = stat.S_ISLNK(info.st_mode)
    mode = [stat.S_IMODE(info.st_mode)]
    identity = (info.st_dev, info.st_ino)
    dialog = Adw.PreferencesDialog(title=tr('Propriétés'))
    dialog.set_content_width(660)
    dialog.set_content_height(560)
    general = Adw.PreferencesPage(title=tr('Général'), icon_name='document-properties-symbolic')
    group = Adw.PreferencesGroup()
    general.add(group)
    dialog.add(general)
    for title, value in (
        (tr('Nom'), path.name),
        (tr('Emplacement'), str(path.parent)),
        (tr('Type'), tr('Lien symbolique') if link else tr('Dossier') if directory else tr('Fichier')),
        (tr('Taille'), '—' if directory else GLib.format_size(info.st_size)),
        (tr('Modifié'), __import__('datetime').datetime.fromtimestamp(info.st_mtime).strftime('%x %X')),
    ):
        row = Adw.ActionRow(title=title, subtitle=value)
        row.set_subtitle_selectable(True)
        group.add(row)
    if directory:
        from .property_totals import add_totals
        add_totals(dialog, group, [Gio.File.new_for_path(str(path))])
    if media_row is not None:
        row = Adw.ActionRow(title=tr('Métadonnées'))
        button = Gtk.Button(label=tr('Modifier…'), valign=Gtk.Align.CENTER)
        button.connect('clicked', lambda *_: metadata_editor(parent, [media_row]))
        row.add_suffix(button)
        group.add(row)
    if not link:
        rights = Adw.PreferencesPage(title=tr('Droits d’accès'), icon_name='changes-allow-symbolic')
        permission_group = Adw.PreferencesGroup()
        rights.add(permission_group)
        dialog.add(rights)
        levels = (
            (
                (tr('Aucun accès'), False, False, False),
                (tr('Traverser seulement'), False, False, True),
                (tr('Lecture seule'), True, False, True),
                (tr('Lecture et écriture'), True, True, True),
            )
            if directory
            else (
                (tr('Aucun accès'), False, False, None),
                (tr('Lecture seule'), True, False, None),
                (tr('Lecture et écriture'), True, True, None),
            )
        )
        controls = []
        updating = [False]

        def current_index(category):
            for index, (_label, read, write, execute) in enumerate(levels):
                value = permissions.replace_access(mode[0], category, read, write, execute)
                if value == mode[0]:
                    return index
            return len(levels)

        for category, title in enumerate(('Propriétaire', 'Groupe', 'Autres')):
            row = Adw.ComboRow(
                title=tr(title),
                model=Gtk.StringList.new([tr(level[0]) for level in levels] + [tr('Personnalisé')]),
                selected=current_index(category),
            )

            def changed(control, _property, category=category):
                if updating[0]:
                    return
                if control.get_selected() >= len(levels):
                    return
                _label, read, write, execute = levels[control.get_selected()]
                mode[0] = permissions.replace_access(mode[0], category, read, write, execute)

            row.connect('notify::selected', changed)
            permission_group.add(row)
            controls.append(row)
        if stat.S_ISREG(info.st_mode):
            executable = Adw.SwitchRow(
                title=tr('Autoriser l’exécution comme programme'),
                active=bool(mode[0] & sum(permissions.EXEC)),
            )
            executable.connect(
                'notify::active',
                lambda row, _: (
                    mode.__setitem__(0, permissions.set_executable(mode[0], row.get_active()))
                    if not updating[0]
                    else None
                ),
            )
            permission_group.add(executable)
        else:
            executable = None

        def advanced(*_):
            win, box, _ = window(parent, tr('Droits d’accès avancés'), 500, 390)
            grid = Gtk.Grid(column_spacing=12, row_spacing=8)
            box.append(grid)
            for col, title in enumerate(('Lecture', 'Écriture', 'Exécution'), 1):
                grid.attach(Gtk.Label(label=tr(title)), col, 0, 1, 1)
            checks = {}
            for row_index, title in enumerate(('Propriétaire', 'Groupe', 'Autres'), 1):
                grid.attach(Gtk.Label(label=tr(title)), 0, row_index, 1, 1)
                for col, bits in enumerate((permissions.READ, permissions.WRITE, permissions.EXEC), 1):
                    check = Gtk.CheckButton(active=bool(mode[0] & bits[row_index - 1]))
                    grid.attach(check, col, row_index, 1, 1)
                    checks[row_index - 1, col - 1] = check

            def accept(*_):
                value = mode[0]
                for (category, column), check in checks.items():
                    bit = (permissions.READ, permissions.WRITE, permissions.EXEC)[column][category]
                    value = value | bit if check.get_active() else value & ~bit
                mode[0] = value
                updating[0] = True
                for category, control in enumerate(controls):
                    control.set_selected(current_index(category))
                if executable:
                    executable.set_active(bool(value & sum(permissions.EXEC)))
                updating[0] = False
                win.close()

            button = Gtk.Button(label=tr('Reporter ces droits'), css_classes=['suggested-action'])
            button.connect('clicked', accept)
            box.append(button)
            win.present()

        advanced_row = Adw.ActionRow(title=tr('Droits d’accès avancés'))
        advanced_button = Gtk.Button(label=tr('Modifier…'), valign=Gtk.Align.CENTER)
        advanced_button.connect('clicked', advanced)
        advanced_row.add_suffix(advanced_button)
        permission_group.add(advanced_row)
        try:
            owner = pwd.getpwuid(info.st_uid).pw_name
        except KeyError:
            owner = str(info.st_uid)
        try:
            group_name = grp.getgrgid(info.st_gid).gr_name
        except KeyError:
            group_name = str(info.st_gid)
        for title, value in ((tr('Utilisateur'), owner), (tr('Groupe'), group_name)):
            permission_group.add(Adw.ActionRow(title=title, subtitle=value))
        save_row = Adw.ActionRow(title=tr('Appliquer les droits'))
        save = Gtk.Button(label=tr('Appliquer'), valign=Gtk.Align.CENTER, css_classes=['suggested-action'])

        def apply(*_):
            if mode[0] == stat.S_IMODE(info.st_mode):
                return
            try:
                permissions.apply_permissions(path, mode[0], identity)
            except (OSError, ValueError, GLib.Error) as error:
                message(dialog, tr('Droits inchangés'), str(error))
                return
            parent.touch(path)
            dialog.close()

        save.connect('clicked', apply)
        save_row.add_suffix(save)
        permission_group.add(save_row)
    dialog.present(parent)
    return dialog


def gio_properties(parent, files):
    if not files:
        return
    dialog = Adw.PreferencesDialog(title=tr('Propriétés'))
    page = Adw.PreferencesPage()
    group = Adw.PreferencesGroup()
    page.add(group)
    dialog.add(page)
    dialog.present(parent)
    if len(files) != 1:
        from .property_totals import add_totals
        add_totals(dialog, group, files)
        return dialog

    def received(file, result):
        try:
            info = file.query_info_finish(result)
        except GLib.Error as error:
            parent.notify(error.message)
            dialog.close()
            return
        if info.get_file_type() == Gio.FileType.DIRECTORY:
            from .property_totals import add_totals
            add_totals(dialog, group, files)
        for title, value in ((tr('Nom'), info.get_display_name()),
                             (tr('Emplacement'), file.get_parse_name()),
                             (tr('Type'), Gio.content_type_get_description(info.get_content_type() or 'application/octet-stream')),
                             (tr('Taille'), GLib.format_size(info.get_size()))):
            row = Adw.ActionRow(title=title, subtitle=value)
            row.set_subtitle_selectable(True)
            group.add(row)

    files[0].query_info_async('standard::display-name,standard::content-type,standard::size,standard::type',
                              Gio.FileQueryInfoFlags.NONE, GLib.PRIORITY_DEFAULT, None, received)


def metadata_editor(parent, rows_override=None):
    items = list(parent.active.selected())
    rows = (
        rows_override
        if rows_override is not None
        else [i.row for i in items if i.row.media_type in ('video', 'audio', 'image') or i.row.is_video]
    )
    if not rows:
        parent.notify(tr('Sélectionnez des médias compatibles.'))
        return
    win, box, header = window(parent, tr('Métadonnées…'), 950, 560)
    fields = ['title', 'artist', 'album', 'author', 'description', 'keywords', 'copyright', 'date_taken']
    table, records = editable_table(
        rows,
        [(key, tr(media.FIELDS[key])) for key in fields],
        lambda row, key: str(row.media_tags.get(key, '')),
    )
    box.append(table)

    def uniform(_button):
        if not records:
            return
        first = records[0]
        changed = {key: value for key, value in first.values.items() if value != first.original[key]}
        for record in records[1:]:
            record.values.update(changed)
            record.revision += 1

    options = Gtk.Box(spacing=10)
    suggest = Gtk.Button(label=tr('Proposer à partir des noms'))
    options.append(suggest)
    options.append(Gtk.Box(hexpand=True))
    write_in_file = Gtk.CheckButton(
        label=tr('Enregistrer dans le fichier lorsque le format le permet'), active=True
    )
    write_in_file.set_tooltip_text(
        tr('Décochez pour utiliser un fichier compagnon XMP sans modifier le média.')
    )
    options.append(write_in_file)
    explanation = tr(
        'Modifiez les cellules nécessaires. Les suggestions complètent seulement les cellules vides à partir des noms, sans recherche en ligne. Les fichiers sont vérifiés avant remplacement ; si l’écriture interne est impossible, un compagnon XMP est utilisé.'
    )
    help_button = Gtk.Button(icon_name='dialog-information-symbolic', tooltip_text=explanation)
    help_button.add_css_class('flat')
    help_button.connect('clicked', lambda *_: message(win, tr('Métadonnées'), explanation))
    options.append(help_button)
    box.append(options)

    def suggest_names(*_):
        for record in records:
            for key, value in media.suggestions(record.source).items():
                if key in record.values and not record.values[key]:
                    record.values[key] = str(value)
            record.revision += 1

    suggest.connect('clicked', suggest_names)
    common = Gtk.Button(label=tr('Reporter les modifications de la première ligne'))
    common.connect('clicked', uniform)
    common.set_visible(len(rows) > 1)
    box.append(common)
    routes = Gtk.Label(wrap=True, xalign=0)
    box.append(routes)

    def update_routes(*_):
        values = [
            row.path.name
            + ' → '
            + tr(
                'Compagnon XMP'
                if not write_in_file.get_active() or media_tags.native_route(row) == 'xmp'
                else 'Dans le fichier'
            )
            for row in rows[:5]
        ]
        routes.set_label('\n'.join(values) + ('\n…' if len(rows) > 5 else ''))

    write_in_file.connect('toggled', update_routes)
    update_routes()
    save = Gtk.Button(label=tr('Enregistrer…'), css_classes=['suggested-action'])
    box.append(save)

    def apply(_):
        plans = []
        for record in records:
            row = record.source
            changes = {key: value for key, value in record.values.items() if value != record.original[key]}
            if changes:
                route = media_tags.native_route(row) if write_in_file.get_active() else 'xmp'
                if route == 'image' and any(key not in media_tags.EXIF for key in changes):
                    route = 'xmp'
                if route == 'audio' and any(key in changes for key in ('author', 'date_taken')):
                    route = 'xmp'
                plans.append((row, changes, route))
        if not plans:
            parent.notify(tr('Aucune modification.'))
            return

        def commit():
            by_path = {row.path: (row, changes, route) for row, changes, route in plans}

            def work(path, cancelled, report):
                row, changes, route = by_path[path]
                report(None, tr('Écriture et vérification des métadonnées…'))
                media_tags.safe_edit(row, changes, route, backup=True, cancelled=cancelled)
                return parent.service.inspect(path, cancelled, force=True)

            parent.jobs.submit(tr('Métadonnées'), list(by_path), work, False)
            win.close()

        confirm(
            win,
            tr('Enregistrer les modifications ?'),
            f'{len(plans)} {tr("fichier(s)")}\n' + tr('Les originaux seront sauvegardés.'),
            commit,
        )

    save.connect('clicked', apply)
    win.present()
    return win


def bulk_rename(parent, rows_override=None, folder=None):
    rows = (
        list(rows_override) if rows_override is not None else [item.row for item in parent.active.selected()]
    )
    if not rows:
        return
    win, box, header = window(
        parent, tr('Renommer le contenu du dossier…') if folder else tr('Renommer en masse…')
    )
    modes = ['manual', 'prefix', 'suffix', 'replace', 'number', 'metadata']
    labels = [
        'Modifier les noms manuellement',
        'Ajouter un préfixe',
        'Ajouter un suffixe',
        'Remplacer du texte',
        'Numéroter',
        'À partir des métadonnées',
    ]
    mode = Gtk.DropDown.new_from_strings([tr(s) for s in labels])
    mode.set_selected(1)
    first = Gtk.Entry(placeholder_text=tr('Texte'))
    second = Gtk.Entry(placeholder_text=tr('Remplacer par'))
    box.append(mode)
    box.append(first)
    box.append(second)
    number_box = Gtk.Box(spacing=8)
    number_box.append(Gtk.Label(label=tr('Premier numéro')))
    start = Gtk.SpinButton.new_with_range(0, 1000000, 1)
    start.set_value(1)
    number_box.append(start)
    number_box.append(Gtk.Label(label=tr('Nombre de chiffres')))
    digits = Gtk.SpinButton.new_with_range(1, 9, 1)
    digits.set_value(3)
    number_box.append(digits)
    box.append(number_box)
    table, records = editable_table(rows, [('name', tr('Nouveau nom'))], lambda row, key: row.path.name, rename_status=True)
    box.append(table)
    warning = Gtk.Label(wrap=True, xalign=0)
    box.append(warning)
    apply = Gtk.Button(label=tr('Renommer…'), css_classes=['suggested-action'])
    box.append(apply)
    updating = [False]

    def validate(*_):
        if updating[0]:
            return
        plans = renaming.prepare_names(rows, [r.values['name'] for r in records])
        by_source = {plan.source: plan for plan in plans}
        ready = sum(not plan.issue for plan in plans)
        conflicts = sum(bool(plan.issue) for plan in plans)
        for record in records:
            plan = by_source.get(record.source.path)
            record.status = (tr('Inchangé') if plan is None else
                             tr('Conflit') + ' : ' + plan.issue if plan.issue else
                             tr('Sera renommé'))
        from .i18n import trf
        warning.set_label(trf('\x1f0\x1f à renommer · \x1f1\x1f inchangé(s) · \x1f2\x1f conflit(s)',
                              ready, len(rows) - len(plans), conflicts))
        apply.set_sensitive(ready > 0)

    def update(*_):
        selected = mode.get_selected()
        if selected == 0:
            first.set_visible(False)
            second.set_visible(False)
            number_box.set_visible(False)
            validate()
            return
        if selected == 5:
            import re

            template = first.get_text() or '{title}'
            names = [
                (
                    re.sub(r'\{([a-z_]+)\}', lambda m: str(row.media_tags.get(m[1], '')), template).strip()
                    + row.path.suffix
                )
                if row.media_tags.get('title')
                else row.path.name
                for row in rows
            ]
            first.set_placeholder_text('{artist} — {title}')
        else:
            names = renaming.batch_names(
                rows,
                modes[selected],
                first.get_text(),
                second.get_text(),
                int(start.get_value()),
                int(digits.get_value()),
            )
            first.set_placeholder_text(tr('Texte'))
        updating[0] = True
        for record, name in zip(records, names):
            record.values['name'] = name
            record.revision += 1
        updating[0] = False
        first.set_visible(True)
        second.set_visible(selected == 3)
        number_box.set_visible(selected == 4)
        validate()

    for record in records:
        record.connect('notify::revision', validate)
    mode.connect('notify::selected', update)
    first.connect('changed', update)
    second.connect('changed', update)
    start.connect('value-changed', update)
    digits.connect('value-changed', update)
    update()

    def commit(_):
        plans = renaming.prepare_names(rows, [r.values['name'] for r in records])
        valid = [p for p in plans if not p.issue]
        if not valid:
            validate()
            return

        def accepted():
            def work(_path, cancelled, report):
                if cancelled():
                    raise InterruptedError()
                renamed, errors = extensions.apply_renames(plans)
                for source, target in renamed.items():
                    parent.state.relocate(source, target)
                if errors:
                    report(None, '\n'.join(errors[:5]))
                return {
                    'renamed': [(str(source), str(target)) for source, target in renamed.items()],
                    'warning': '\n'.join(errors[:5]) if errors else '',
                }

            parent.jobs.submit(tr('Renommer'), [rows[0].path.parent], work, False)
            win.close()

        confirm(win, tr('Renommer ces éléments ?'), f'{len(valid)} {tr("élément(s)")}', accepted)

    apply.connect('clicked', commit)
    win.present()
    return win


PROFILES = {
    'Général': [0, 1, 14],
    'Vidéo': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 14],
    'Audio': [0, 1, 2, 8, 9, 14, 18, 19, 20, 21, 24, 25, 30],
    'Images': [0, 1, 3, 14, 26, 27, 28, 29],
    'Personnel': [0, 1, 14],
    'Toutes les colonnes': [c for c in range(38) if c not in (12, 13, 15, 16, 36)],
}


def columns(parent):
    win, box, header = window(parent, tr('Colonnes…'), 560, 700)
    css = Gtk.CssProvider()
    css.load_from_data(
        b'.column-drop-before { border-top: 3px solid @accent_color; } .column-drop-after { border-bottom: 3px solid @accent_color; } .column-dragging { opacity: 0.5; }'
    )
    Gtk.StyleContext.add_provider_for_display(win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    controls = Gtk.Grid(column_spacing=12, row_spacing=8)
    controls.attach(Gtk.Label(label=tr('Profil'), xalign=0), 0, 0, 1, 1)
    profile_values = {name: list(values) for name, values in PROFILES.items()}
    profile_names = list(profile_values)
    visible_now = list(parent.state.settings['columns'])
    profiles = parent.state.settings['profiles']
    for name, values in profiles.items():
        if name not in profile_values:
            profile_values[name] = list(values)
            profile_names.append(name)
    matched = next(
        (name for name in profile_names if list(profiles.get(name, profile_values[name])) == visible_now),
        None,
    )
    if matched is None:
        profile_names.insert(0, 'Personnalisé')
        profile_values['Personnalisé'] = list(visible_now)
        matched = 'Personnalisé'
    select = Gtk.DropDown.new_from_strings([tr(name) for name in profile_names])
    select.set_selected(profile_names.index(matched))
    controls.attach(select, 1, 0, 1, 1)
    controls.attach(Gtk.Label(label=tr('Panneau'), xalign=0), 0, 1, 1, 1)
    slot_values = ['left', 'right', 'both']
    pane_select = Gtk.DropDown.new_from_strings(
        [tr('Panneau gauche'), tr('Panneau droit'), tr('Les deux panneaux')]
    )
    base_slot = getattr(parent.active, 'width_slot', 'left')
    pane_select.set_selected(slot_values.index(base_slot))
    controls.attach(pane_select, 1, 1, 1, 1)
    controls.set_hexpand(True)
    controls.get_child_at(1, 0).set_hexpand(True)
    box.append(controls)
    note = Gtk.Label(
        label=tr('Cochez les colonnes à afficher. Faites glisser la poignée pour changer leur ordre.'),
        wrap=True,
        xalign=0,
    )
    box.append(note)
    scope_note = Gtk.Label(
        label=tr(
            'Les colonnes affichées sont communes aux deux panneaux. L’ordre peut être réglé pour un panneau ou pour les deux.'
        ),
        wrap=True,
        xalign=0,
        css_classes=['dim-label'],
    )
    box.append(scope_note)
    listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=['boxed-list'])
    scroll = Gtk.ScrolledWindow(vexpand=True)
    scroll.set_child(listing)
    box.append(scroll)
    checkboxes = []
    rows = []
    highlighted = [None]
    updating_visibility = [False]
    order_source_slot = [base_slot]
    headers = metadata.HEADERS + ['Étiquette']

    def current_order(slot):
        source_slot = order_source_slot[0] if slot == 'both' else slot
        stored = parent.state.settings['pane_column_orders'].get(
            source_slot, parent.state.settings['column_order']
        )
        count = len(headers)
        return list(
            dict.fromkeys(
                [i for i in stored if type(i) is int and 0 <= i < count and i not in (12, 13, 15, 16, 36)]
                + [i for i in range(count) if i not in (12, 13, 15, 16, 36)]
            )
        )

    def clear_marker():
        row = highlighted[0]
        if row:
            row.remove_css_class('column-drop-before')
            row.remove_css_class('column-drop-after')
        highlighted[0] = None

    def apply_order(slot, order):
        targets = column_order_targets(slot)
        for target_slot in targets:
            parent.state.settings['pane_column_orders'][target_slot] = list(order)
        if slot == 'both' or getattr(parent.active, 'width_slot', None) in targets:
            parent.state.settings['column_order'] = list(order)
        parent.state.save()
        for pane in getattr(parent, 'panes', []):
            if pane.width_slot in targets:
                pane.apply_column_order(order)

    for index, title in enumerate(headers):
        row = Gtk.ListBoxRow()
        line = Gtk.Box(spacing=10)
        line.set_margin_start(10)
        line.set_margin_end(10)
        line.set_margin_top(5)
        line.set_margin_bottom(5)
        row.set_child(line)
        handle = reorder_handle()
        line.append(handle)
        check = Gtk.CheckButton(
            active=index in parent.state.settings['columns'] and index not in (12, 13, 16)
        )
        check.set_sensitive(index not in (0, 12, 13, 16))
        line.append(check)
        label = Gtk.Label(label=tr(title), xalign=0, hexpand=True)
        line.append(label)
        if not check.get_active():
            label.add_css_class('dim-label')
        checkboxes.append(check)
        rows.append(row)

        def visibility_changed(button, column=index, column_label=label):
            if button.get_active():
                column_label.remove_css_class('dim-label')
            else:
                column_label.add_css_class('dim-label')
            if updating_visibility[0]:
                return
            visible = [
                i
                for i, control in enumerate(checkboxes)
                if i not in (12, 13, 15, 16, 36) and control.get_active()
            ]
            parent.state.settings['columns'] = visible
            for pane in parent.panes:
                for i, column_widget in enumerate(pane.columns):
                    column_widget.set_visible(i in visible)
            parent.state.save()

        check.connect('toggled', visibility_changed)
        source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect(
            'prepare', lambda _source, _x, _y, value=str(index): Gdk.ContentProvider.new_for_value(value)
        )
        source.connect(
            'drag-begin', lambda _source, _drag, r=row: (r.add_css_class('column-dragging'), None)[1]
        )
        source.connect(
            'drag-end', lambda _source, _drag, _delete, r=row: r.remove_css_class('column-dragging')
        )
        handle.add_controller(source)
        target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)

        def motion(_target, _x, y, row_widget=row):
            clear_marker()
            row_widget.add_css_class(
                'column-drop-after' if y >= row_widget.get_height() / 2 else 'column-drop-before'
            )
            highlighted[0] = row_widget
            return Gdk.DragAction.MOVE

        def leave(_target):
            clear_marker()

        def drop(_target, value, _x, y, target_index=index, target_row=row):
            if not value.isdigit():
                return False
            slot = slot_values[pane_select.get_selected()]
            order = current_order(slot)
            updated = reorder_column_order(order, int(value), target_index, y >= target_row.get_height() / 2)
            clear_marker()
            if updated == order:
                return False
            apply_order(slot, updated)
            GLib.idle_add(show_order)
            return True

        target.connect('motion', motion)
        target.connect('leave', leave)
        target.connect('drop', drop)
        row.add_controller(target)
        if index not in (12, 13, 15, 16, 36):
            listing.append(row)

    # ListBox doesn't expose a public move-row API; reconstruct from stable
    # row widgets on an order update and whenever the target panel changes.
    def show_order(*_):
        clear_marker()
        while listing.get_first_child():
            listing.remove(listing.get_first_child())
        for index in current_order(slot_values[pane_select.get_selected()]):
            if index not in (12, 13, 15, 16, 36):
                listing.append(rows[index])

    def apply_visibility(values):
        updating_visibility[0] = True
        try:
            for index, check in enumerate(checkboxes):
                check.set_active((index in values or index == 0) and index not in (12, 13, 15, 16, 36))
        finally:
            updating_visibility[0] = False
        visible = [
            i for i, check in enumerate(checkboxes) if i not in (12, 13, 15, 16, 36) and check.get_active()
        ]
        parent.state.settings['columns'] = visible
        for pane in parent.panes:
            for i, column_widget in enumerate(pane.columns):
                column_widget.set_visible(i in visible)
        parent.state.save()

    def apply_profile(*_):
        name = profile_names[select.get_selected()]
        apply_visibility(
            parent.state.settings['profiles'].get(name, profile_values.get(name, PROFILES['Général']))
        )

    select.connect('notify::selected', apply_profile)
    actions = Gtk.Box(spacing=8)
    save = Gtk.Button(label=tr('Enregistrer dans ce profil'), hexpand=True)
    reset_profile = Gtk.Button(label=tr('Rétablir ce profil'), hexpand=True)
    actions.append(save)
    actions.append(reset_profile)
    box.append(actions)

    def save_profile(*_):
        name = profile_names[select.get_selected()]
        parent.state.settings['profiles'][name] = [
            i for i, check in enumerate(checkboxes) if i not in (12, 13, 15, 16, 36) and check.get_active()
        ]
        parent.state.save()

    def restore_profile(*_):
        name = profile_names[select.get_selected()]
        parent.state.settings['profiles'].pop(name, None)
        apply_visibility(PROFILES.get(name, PROFILES['Général']))

    save.connect('clicked', save_profile)
    reset_profile.connect('clicked', restore_profile)
    reset_order = Gtk.Button(label=tr('Rétablir l’ordre initial de ce panneau'))

    def update_reset_label(*_):
        reset_order.set_label(
            tr('Rétablir l’ordre initial des deux panneaux')
            if slot_values[pane_select.get_selected()] == 'both'
            else tr('Rétablir l’ordre initial de ce panneau')
        )

    def pane_selection_changed(*_):
        selected = slot_values[pane_select.get_selected()]
        if selected in ('left', 'right'):
            order_source_slot[0] = selected
        show_order()
        update_reset_label()

    pane_select.connect('notify::selected', pane_selection_changed)

    def restore_order(*_):
        slot = slot_values[pane_select.get_selected()]
        order = list(range(len(headers)))
        apply_order(slot, order)
        show_order()

    reset_order.connect('clicked', restore_order)
    box.append(reset_order)
    win.connect(
        'close-request',
        lambda *_: (
            parent.state.save(),
            Gtk.StyleContext.remove_provider_for_display(win.get_display(), css),
            False,
        )[2],
    )
    show_order()
    win.present()
    return win


def preferences(parent):
    from .indicator import appindicator_available

    # PreferencesDialog is a widget inside the parent window and cannot follow
    # the window manager's dialog attachment preference. PreferencesWindow is
    # a native separate top-level window on the supported libadwaita versions.
    dialog = Adw.PreferencesWindow(title=tr('Préférences'), transient_for=parent, modal=False)
    dialog.set_search_enabled(True)
    dialog.set_default_size(760, 620)
    settings = parent.state.settings

    def page(title, icon):
        p = Adw.PreferencesPage(title=tr(title), icon_name=icon)
        g = Adw.PreferencesGroup()
        p.add(g)
        dialog.add(p)
        return g

    general = page('Général', 'preferences-system-symbolic')
    appearance = page('Apparence', 'preferences-desktop-display-symbolic')
    playback = page('Aperçus et lecture', 'media-playback-start-symbolic')
    privacy = page('Confidentialité', 'changes-prevent-symbolic')
    advanced = page('Avancé', 'preferences-other-symbolic')
    tools = page('Composants', 'applications-engineering-symbolic')

    def toggle(group, title, key, subtitle='', callback=None):
        row = Adw.SwitchRow(title=tr(title), subtitle=tr(subtitle) if subtitle else '', active=settings[key])

        def changed(r, _):
            settings[key] = r.get_active()
            parent.state.save()
            if callback:
                callback(r.get_active())

        row.connect('notify::active', changed)
        group.add(row)
        return row

    def combo(group, title, key, values, labels, callback=None):
        row = Adw.ComboRow(
            title=tr(title),
            model=Gtk.StringList.new([tr(s) for s in labels]),
            selected=values.index(settings[key]) if settings[key] in values else 0,
        )
        row.connect(
            'notify::selected',
            lambda r, _: (
                settings.__setitem__(key, values[r.get_selected()]),
                parent.state.save(),
                callback() if callback else None,
            ),
        )
        group.add(row)
        return row

    combo(
        general,
        'Langue (au prochain lancement)',
        'language',
        ['auto', 'fr', 'en'],
        ['Langue du système', 'Français', 'English'],
    )
    startup = combo(
        general,
        'Dossier au démarrage',
        'startup',
        ['home', 'last', 'custom', 'session'],
        ['Dossier personnel', 'Dernier dossier ouvert', 'Autre dossier', 'Onglets de la dernière fenêtre fermée'],
    )
    folder = Adw.EntryRow(title=tr('Dossier choisi'), text=settings['startup_path'] or str(Path.home()))

    def startup_path_changed(row):
        settings['startup_path'] = row.get_text()
        parent.state.save()

    folder.connect('changed', startup_path_changed)
    general.add(folder)
    choose = Gtk.Button(icon_name='folder-open-symbolic', valign=Gtk.Align.CENTER)
    folder.add_suffix(choose)

    def pick(*_):
        chooser = Gtk.FileDialog(title=tr('Choisir un dossier'))

        def done(c, result):
            try:
                path = c.select_folder_finish(result).get_path()
                folder.set_text(path)
                settings['startup'] = 'custom'
                parent.state.save()
            except GLib.Error:
                pass

        chooser.select_folder(parent, None, done)

    choose.connect('clicked', pick)
    folder.set_visible(settings['startup'] == 'custom')
    startup.connect('notify::selected', lambda *_: folder.set_visible(settings['startup'] == 'custom'))
    toggle(general, 'Toujours démarrer en mode scindé', 'split')
    toggle(general, 'Toujours masquer les éléments cachés au démarrage', 'hide_on_start')
    if appindicator_available():
        toggle(
            general,
            'Réduire dans la zone de notification à la fermeture',
            'minimize_to_tray',
            callback=lambda _active: parent.sync_indicator(),
        )
    instances = Adw.SwitchRow(
        title=tr('Autoriser plusieurs instances de Mirivue'),
        subtitle=tr('Ce choix sera appliqué au prochain lancement.'),
        active=not settings['reuse_window'],
    )

    def instances_changed(row, _):
        settings['reuse_window'] = not row.get_active()
        parent.state.save()

    instances.connect('notify::active', instances_changed)
    general.add(instances)

    def thumbnails_changed(enabled):
        for pane in parent.panes:
            pane.set_thumbnail_visibility(enabled)
        parent.sync_toggle_actions()

    combo(
        appearance,
        'Thème',
        'theme',
        ['auto', 'light', 'dark'],
        ['Automatique (système)', 'Clair', 'Sombre'],
        parent.apply_theme,
    )
    toggle(appearance, 'Afficher les miniatures', 'thumbnails', callback=thumbnails_changed)
    toggle(appearance, 'Mémoriser la vue et le tri de chaque dossier', 'remember_folder_view',
           callback=lambda enabled: parent.active.remember_folder_style() if enabled else None)
    combo(appearance, 'Format des dates', 'date_format', ['simple', 'detailed'], ['Simple', 'Détaillé'],
          lambda: [setattr(item, 'revision', item.revision + 1) for pane in parent.panes for item in pane.items.values()])

    combo(
        appearance,
        'Colonne Taille pour les dossiers',
        'folder_sizes',
        [False, True],
        ['Nombre d’éléments', 'Taille totale'],
        lambda: [pane.set_folder_sizes(settings['folder_sizes']) for pane in parent.panes],
    )
    toggle(
        appearance,
        'Dossiers avant les fichiers',
        'folders_first',
        callback=lambda enabled: parent.set_folders_first(enabled),
    )
    caption_values = [-1, 1, 14, 17, 2, 3, 19, 20]
    caption_labels = ['Aucune', 'Taille', 'Date de modification', 'Type de média', 'Durée', 'Résolution', 'Artiste', 'Album']
    for index, title in enumerate(('Première information sous les icônes', 'Deuxième information sous les icônes', 'Troisième information sous les icônes')):
        caption = Adw.ComboRow(title=tr(title), model=Gtk.StringList.new([tr(label) for label in caption_labels]),
                               selected=caption_values.index(settings['icon_captions'][index]))
        def changed(row, _prop, index=index):
            settings['icon_captions'][index] = caption_values[row.get_selected()]
            parent.state.save()
            for pane in parent.panes:
                for item in pane.items.values():
                    item.revision += 1
        caption.connect('notify::selected', changed)
        appearance.add(caption)
    row = Adw.ActionRow(title=tr('Colonnes et disposition'))
    button = Gtk.Button(label=tr('Configurer'), valign=Gtk.Align.CENTER)
    button.connect('clicked', lambda *_: columns(parent))
    row.add_suffix(button)
    appearance.add(row)
    row = Adw.ActionRow(title=tr('Personnaliser la barre d’outils'))
    button = Gtk.Button(label=tr('Configurer'), valign=Gtk.Align.CENTER)
    button.connect('clicked', lambda *_: toolbar(parent))
    row.add_suffix(button)
    appearance.add(row)
    preview_first_row = None

    def preview_changed(active):
        parent.set_preview_enabled(active)
        if preview_first_row:
            preview_first_row.set_sensitive(active)
        if not active and settings['preview_first']:
            settings['preview_first'] = False
            parent.state.save()

    toggle(playback, 'Toujours démarrer avec le panneau d’aperçu', 'preview', callback=preview_changed)
    preview_first_row = toggle(
        playback, 'Afficher le premier fichier si aucun n’est sélectionné', 'preview_first'
    )
    preview_first_row.set_sensitive(bool(settings['preview']))
    if not settings['preview'] and settings['preview_first']:
        settings['preview_first'] = False
        parent.state.save()
    toggle(playback, 'Conserver l’historique de lecture local', 'playback_history')
    row = Adw.ActionRow(title=tr('Effacer l’historique de lecture'))
    button = Gtk.Button(label=tr('Effacer'), valign=Gtk.Align.CENTER)
    button.connect('clicked', lambda *_: parent.clear_playback_history())
    row.add_suffix(button)
    playback.add(row)
    for title, key, minimum, maximum in [
        ('Pas du volume (%)', 'volume_step', 1, 25),
        ('Pas de déplacement (secondes)', 'seek_step', 1, 120),
    ]:
        row = Adw.SpinRow.new_with_range(minimum, maximum, 1)
        row.set_title(tr(title))
        row.set_value(settings[key])
        row.connect('notify::value', lambda r, _, k=key: settings.__setitem__(k, int(r.get_value())))
        playback.add(row)
    toggle(privacy, 'Conserver l’historique des opérations', 'history')
    recent = Adw.SwitchRow(title=tr('Conserver les médias récents dans le menu'), active=settings['recent'])
    privacy.add(recent)

    def recent_changed(row, _):
        settings['recent'] = row.get_active()
        if not row.get_active():
            settings['recent_paths'] = []
        parent.menu_button.set_menu_model(parent.main_menu())
        parent.state.save()

    recent.connect('notify::active', recent_changed)
    row = Adw.ActionRow(title=tr('Effacer l’historique des opérations'))
    button = Gtk.Button(label=tr('Effacer'), valign=Gtk.Align.CENTER)
    button.connect('clicked', lambda *_: parent.clear_history())
    row.add_suffix(button)
    privacy.add(row)
    # The integrated batch renamer is the normal/default choice.  External
    # tools remain optional and a manually entered command is explicit.
    preset_names = [tr('Renommage intégré'), tr('Commande personnalisée'), *renaming.PRESETS.keys()]
    preset = Adw.ComboRow(title=tr('Préréglage de renommage'), model=Gtk.StringList.new(preset_names))
    advanced.add(preset)
    external = Adw.EntryRow(title=tr('Programme de renommage'), text=settings['external_renamer'])
    advanced.add(external)
    external_args = Adw.EntryRow(title=tr('Options du programme'), text=settings['external_renamer_args'])
    advanced.add(external_args)
    current = (settings['external_renamer'].strip(), settings['external_renamer_args'].strip())
    if not any(current):
        preset.set_selected(0)
    else:
        preset.set_selected(1)
        for index, values in enumerate(renaming.PRESETS.values(), 2):
            if current == (values[0], values[1]):
                preset.set_selected(index)
                break
    changing = [False]

    def update_external_rows():
        custom = preset.get_selected() == 1
        external.set_visible(custom)
        external_args.set_visible(custom)

    def preset_changed(row, _):
        selected = row.get_selected()
        changing[0] = True
        if selected == 0:
            external.set_text('')
            external_args.set_text('')
            settings['external_renamer'] = ''
            settings['external_renamer_args'] = ''
        elif selected > 1:
            program, arguments = list(renaming.PRESETS.values())[selected - 2]
            external.set_text(program)
            external_args.set_text(arguments)
            settings['external_renamer'] = program
            settings['external_renamer_args'] = arguments
        changing[0] = False
        update_external_rows()

    def external_changed(*_):
        settings['external_renamer'] = external.get_text()
        settings['external_renamer_args'] = external_args.get_text()
        if not changing[0]:
            preset.set_selected(1)

    preset.connect('notify::selected', preset_changed)
    external.connect('changed', external_changed)
    external_args.connect('changed', external_changed)
    update_external_rows()
    optional_tools = {
        'mediainfo': 'Métadonnées techniques des vidéos',
        'ffmpeg': 'Miniatures vidéo, contrôle de lecture et copie MKV',
        'ffprobe': 'Analyse complémentaire des médias',
        'mkvpropedit': 'Écriture des métadonnées MKV',
        'mkvextract': 'Lecture des métadonnées MKV',
        'exiftool': 'Lecture et écriture des métadonnées des images',
        'pactl': 'Choix de la sortie audio',
    }
    for name, feature in optional_tools.items():
        found = shutil.which(name) or (
            '/usr/bin/vendor_perl/exiftool'
            if name == 'exiftool' and Path('/usr/bin/vendor_perl/exiftool').exists()
            else ''
        )
        subtitle = found if found else tr('Non installé') + ' — ' + tr(feature)
        tools.add(Adw.ActionRow(title=name, subtitle=subtitle))
    dialog.connect('close-request', lambda *_: (parent.state.save(), False)[1])
    dialog.present()
    return dialog


def operations(parent):
    if parent.job_window:
        parent.job_window.present()
        return parent.job_window
    if not parent.jobs.jobs and not parent.past_jobs:
        current = getattr(parent, 'empty_operations_popover', None)
        if current is not None:
            current.popup()
            return current
        anchor = (
            parent.compact_operations if parent.compact_operations.get_mapped() else parent.places_operations
        )
        pop = Gtk.Popover()
        pop.set_parent(anchor)
        empty = Gtk.Label(label=tr('Aucune opération en cours'))
        empty.set_wrap(False)
        empty.add_css_class('dim-label')
        pop.set_child(empty)
        parent.empty_operations_popover = pop

        def closed(_popover):
            parent.empty_operations_popover = None
            GLib.idle_add(lambda: (pop.unparent(), False)[1])

        pop.connect('closed', closed)
        pop.popup()
        return pop
    win, box, header = window(parent, tr('Opérations'), 760, 460)
    parent.job_window = win
    listing = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    scroll = Gtk.ScrolledWindow(vexpand=True)
    scroll.set_child(listing)
    box.append(scroll)
    buttons = Gtk.Box(spacing=8)
    box.append(buttons)
    pause = Gtk.Button(label=tr('Suspendre ou reprendre les opérations'))
    pause.connect('clicked', lambda *_: parent.pause_jobs())
    buttons.append(pause)
    cancel = Gtk.Button(label=tr('Annuler les analyses…'))
    cancel.connect('clicked', lambda *_: parent.cancel_analyses())
    buttons.append(cancel)
    labels = {}
    for job in parent.past_jobs:
        listing.append(
            Gtk.Label(
                label=job['title']
                + ' — '
                + tr(
                    {'done': 'Terminé', 'failed': 'Erreur', 'cancelled': 'Annulé'}.get(
                        job['state'], job['state']
                    )
                ),
                xalign=0,
                wrap=True,
            )
        )

    def update():
        for job in parent.jobs.jobs:
            if id(job) not in labels:
                row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                top = Gtk.Box(spacing=8)
                label = Gtk.Label(xalign=0, wrap=True, hexpand=True)
                top.append(label)
                stop = Gtk.Button(icon_name='process-stop-symbolic', tooltip_text=tr('Annuler'))
                stop.connect('clicked', lambda _b, j=job: j.cancel.set())
                top.append(stop)
                progress = Gtk.ProgressBar()
                progress.set_visible(False)
                row.append(top)
                row.append(progress)
                listing.append(row)
                labels[id(job)] = (label, stop, progress)
            label, stop, progress = labels[id(job)]
            label.set_label(
                job.title
                + ' — '
                + tr(
                    {
                        'queued': 'En attente',
                        'running': 'En cours',
                        'done': 'Terminé',
                        'failed': 'Erreur',
                        'cancelled': 'Annulé',
                    }[job.state]
                )
                + '\n'
                + tr(job.message)
                + (
                    '\n' + '\n'.join(path + ' : ' + health_text(error) for path, error in job.errors)
                    if job.errors
                    else ''
                )
            )
            stop.set_sensitive(job.state in ('queued', 'running'))
            progress.set_visible(job.state in ('queued', 'running'))
            if job.state == 'running':
                if job.fraction is None:
                    progress.pulse()
                else:
                    progress.set_fraction(job.fraction)
        return True

    update()
    timer = GLib.timeout_add(400, update)

    def closed(*_):
        GLib.source_remove(timer)
        parent.job_window = None
        return False

    win.connect('close-request', closed)
    win.present()
    return win


def archive_contents(parent, path, entries):
    """Read-only archive listing; extraction is queued in the normal job UI."""
    win, box, _header = window(parent, tr('Contenu de l’archive') + ' — ' + path.name, 760, 550)
    note = Gtk.Label(
        label=tr('Sélectionnez les entrées à extraire, ou extrayez toute l’archive.'), xalign=0, wrap=True
    )
    box.append(note)
    listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE)
    scroll = Gtk.ScrolledWindow(vexpand=True)
    scroll.set_child(listing)
    box.append(scroll)
    for entry in entries:
        row = Gtk.ListBoxRow()
        row.archive_name = entry.name
        line = Gtk.Box(spacing=8)
        icon = Gtk.Image.new_from_icon_name('folder-symbolic' if entry.is_dir else 'text-x-generic-symbolic')
        label = Gtk.Label(label=entry.name, xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.MIDDLE)
        line.append(icon)
        line.append(label)
        row.set_child(line)
        listing.append(row)
    buttons = Gtk.Box(spacing=8)
    box.append(buttons)
    all_button = Gtk.Button(label=tr('Extraire tout vers…'))
    chosen_button = Gtk.Button(label=tr('Extraire la sélection vers…'))
    buttons.append(all_button)
    buttons.append(chosen_button)

    def chosen(*_):
        names = []
        listing.selected_foreach(lambda _list, row: names.append(row.archive_name))
        if not names:
            parent.notify(tr('Sélectionnez au moins une entrée.'))
            return
        parent.extract_archive(path, selected=names)

    all_button.connect('clicked', lambda *_: parent.extract_archive(path))
    chosen_button.connect('clicked', chosen)
    win.present()
    return win


def remote_browser(parent, initial):
    """Browse GIO URIs even when GVfs does not expose a local FUSE path."""
    win, box, _header = window(parent, tr('Emplacement réseau'), 850, 600)
    current = [initial]
    listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE)
    location = Gtk.Label(
        label=initial.get_uri(), xalign=0, selectable=True, ellipsize=Pango.EllipsizeMode.MIDDLE
    )
    box.append(location)
    toolbar = Gtk.Box(spacing=8)
    box.append(toolbar)
    back = Gtk.Button(label=tr('Dossier parent'))
    toolbar.append(back)
    refresh = Gtk.Button(label=tr('Actualiser'))
    toolbar.append(refresh)
    status = Gtk.Label(xalign=0)
    box.append(status)
    scroll = Gtk.ScrolledWindow(vexpand=True)
    scroll.set_child(listing)
    box.append(scroll)
    buttons = Gtk.Box(spacing=8)
    box.append(buttons)
    copy_local = Gtk.Button(label=tr('Copier vers le panneau actif'))
    move_local = Gtk.Button(label=tr('Déplacer vers le panneau actif'))
    paste_local = Gtk.Button(label=tr('Coller depuis Mirivue'))
    for button in (copy_local, move_local, paste_local):
        buttons.append(button)
    generation = [0]

    def load(folder):
        current[0] = folder
        generation[0] += 1
        token = generation[0]
        location.set_label(folder.get_uri())
        status.set_label(tr('Chargement…'))
        while (row := listing.get_row_at_index(0)) is not None:
            listing.remove(row)

        def read():
            try:
                entries = gio_backend.browse(folder, include_icons=True)
                error = None
            except Exception as exc:
                entries = []
                error = str(exc)

            def render():
                if token != generation[0] or not win.get_visible():
                    return False
                status.set_label(error or f'{len(entries)} {tr("élément(s)")}')
                for title, file, is_dir, size, gicon in entries:
                    row = Gtk.ListBoxRow()
                    row.gio_file = file
                    row.is_directory = is_dir
                    text = (
                        f'{title}  —  {metadata.quantity(size, ["o", "Kio", "Mio", "Gio", "Tio"], 1024)}'
                        if not is_dir
                        else title
                    )
                    line = Gtk.Box(spacing=8)
                    line.append(
                        Gtk.Image.new_from_gicon(
                            gicon or Gio.ThemedIcon.new('folder' if is_dir else 'text-x-generic')
                        )
                    )
                    line.append(Gtk.Label(label=text, xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE))
                    row.set_child(line)
                    listing.append(row)
                return False

            GLib.idle_add(render)

        threading.Thread(target=read, daemon=True).start()

    def selected_files():
        values = []
        listing.selected_foreach(lambda _list, row: values.append(row.gio_file))
        return values

    def opened(_list, row):
        if row.is_directory:
            load(row.gio_file)
        else:

            def finished(_source, result):
                try:
                    Gio.AppInfo.launch_default_for_uri_finish(result)
                except GLib.Error as error:
                    parent.notify(error.message)

            Gio.AppInfo.launch_default_for_uri_async(row.gio_file.get_uri(), None, None, finished)

    listing.connect('row-activated', opened)
    back.connect('clicked', lambda *_: load(current[0].get_parent() or current[0]))
    refresh.connect('clicked', lambda *_: load(current[0]))

    def submit(files, destination, move):
        if not files:
            parent.notify(tr('Sélectionnez au moins un fichier.'))
            return

        def work(_path, cancelled, report):
            results = gio_backend.transfer(
                files,
                destination,
                move,
                cancelled,
                lambda done, total: report(done / total if total else None, tr('Transfert réseau')),
            )
            warnings = [warning for _, _, warning in results if warning]
            return {
                'gio_changed': [target.get_path() for _, target, _ in results if target.get_path()],
                'warning': '\n'.join(warnings),
            }

        parent.jobs.submit(tr('Transfert réseau'), [parent.active.folder], work, False)

    copy_local.connect(
        'clicked',
        lambda *_: submit(selected_files(), Gio.File.new_for_path(str(parent.active.folder)), False),
    )
    move_local.connect(
        'clicked', lambda *_: submit(selected_files(), Gio.File.new_for_path(str(parent.active.folder)), True)
    )
    paste_local.connect(
        'clicked',
        lambda *_: submit(
            [Gio.File.new_for_path(str(path)) for path in parent.clipboard_paths],
            current[0],
            parent.clipboard_cut,
        ),
    )
    win.present()
    load(initial)
    return win


def compare_media(parent, rows):
    if len(rows) != 2 or any(row.is_dir for row in rows):
        parent.notify(tr('Sélectionnez exactement deux fichiers.'))
        return
    win, box, _header = window(parent, tr('Comparer deux médias'), 900, 560)
    grid = Gtk.Grid(column_spacing=18, row_spacing=7)
    for column, title in enumerate((tr('Information'), rows[0].path.name, rows[1].path.name)):
        grid.attach(Gtk.Label(label=title, xalign=0, wrap=True, css_classes=['heading']), column, 0, 1, 1)
    line = 1
    for index in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 17, 18, 19, 20, 22, 23, 26, 27, 28, 29):
        if not rows[0].values[index] and not rows[1].values[index]:
            continue
        for column, text in enumerate(
            (metadata.HEADERS[index], rows[0].values[index], rows[1].values[index])
        ):
            label = Gtk.Label(label=str(text), xalign=0, wrap=True, selectable=True)
            grid.attach(label, column, line, 1, 1)
        line += 1
    scroll = Gtk.ScrolledWindow(vexpand=True)
    scroll.set_child(grid)
    box.append(scroll)
    win.present()
    return win


def health_text(error):
    from .core.health import explain_error

    return tr(explain_error(error)) + '\n' + error


def duplicate_results(parent, groups, root=None):
    if not groups:
        parent.notify(tr('Aucun doublon exact trouvé dans ce dossier et ses sous-dossiers.'))
        return
    root = Path(root) if root else None
    win, box, header = window(parent, tr('Doublons exacts'), 900, 600)
    box.append(
        Gtk.Label(
            label=tr(
                'Ces fichiers ont un contenu strictement identique. Choisissez celui à conserver dans chaque groupe.'
            ),
            xalign=0,
            wrap=True,
        )
    )
    listing = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    scroll = Gtk.ScrolledWindow(vexpand=True)
    scroll.set_child(listing)
    box.append(scroll)

    def display_path(path):
        if root is not None:
            try:
                return str(path.relative_to(root))
            except ValueError:
                pass
        return str(path)

    for number, group in enumerate(groups, 1):
        paths = [Path(p) for p, signature in group["files"]]
        for pane in parent.panes:
            for path in paths:
                item = pane.items.get(str(path))
                if item:
                    item.row.duplicate_group = number
                    item.revision += 1
        frame = Gtk.Frame(label=f'{tr("Groupe")} {number} — {len(paths)} {tr("fichiers")}')
        choices_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        choices_box.set_margin_start(12)
        choices_box.set_margin_end(12)
        choices_box.set_margin_top(8)
        choices_box.set_margin_bottom(8)
        frame.set_child(choices_box)
        listing.append(frame)
        choices = []
        for path in paths:
            choice = Gtk.CheckButton(label=display_path(path))
            if choices:
                choice.set_group(choices[0])
            choice.set_tooltip_text(str(path))
            choices_box.append(choice)
            choices.append(choice)
        choices[0].set_active(True)
        keep = Gtk.Button(label=tr('Mettre les autres à la corbeille…'), halign=Gtk.Align.START)
        choices_box.append(keep)

        def clicked(_button, paths=paths, choices=choices, button=keep, group=group):
            keeper = next((path for path, choice in zip(paths, choices) if choice.get_active()), paths[0])

            def accepted():
                def work(path, cancelled, report):
                    removed, errors = duplicates.keep_one(
                        group,
                        keeper,
                        lambda p: Gio.File.new_for_path(str(p)).trash(None),
                        cancelled,
                        lambda t: report(None, t),
                    )
                    if errors:
                        raise ValueError('\n'.join(errors))
                    return {'source': str(path)}

                parent.jobs.submit(tr('Doublons'), [keeper], work, False)
                button.set_sensitive(False)

            message = (
                f'{tr("Conserver")} : {display_path(keeper)}\n{len(paths) - 1} {tr("fichier(s) à mettre à la corbeille")}\n'
                + tr('Le contenu sera vérifié une nouvelle fois avant la suppression.')
            )
            confirm(win, tr('Mettre les autres doublons à la corbeille ?'), message, accepted)

        keep.connect('clicked', clicked)
    win.present()
    return win


def collection_view(parent, name):
    paths = list(parent.state.settings['collections'].get(name, []))
    win, box, header = window(parent, name)
    listing = Gtk.ListBox()
    scroll = Gtk.ScrolledWindow(vexpand=True)
    scroll.set_child(listing)
    box.append(scroll)
    for path in paths:
        line = Gtk.Box(spacing=6)
        button = Gtk.Button(label=path, hexpand=True)
        line.append(button)
        button.connect(
            'clicked',
            lambda _b, p=Path(path): (
                parent.active.open(p.parent),
                parent.active.restore_selection.add(str(p)),
                win.close(),
            ),
        )
        remove = Gtk.Button(icon_name='list-remove-symbolic')
        line.append(remove)
        listing.append(line)

        def removed(_b, p=path, line=line):
            values = parent.state.settings['collections'][name]
            if p in values:
                values.remove(p)
            parent.state.save()
            listing.remove(line)

        remove.connect('clicked', removed)
    win.present()


def export_csv(parent):
    rows = [i.row for i in parent.active.selected()] or [
        parent.active.sorted.get_item(i).row for i in range(parent.active.sorted.get_n_items())
    ]
    chooser = Gtk.FileDialog(title=tr('Exporter CSV…'), initial_name='Mirivue.csv')

    def done(c, result):
        try:
            target = Path(c.save_finish(result).get_path())
            with target.open('w', newline='', encoding='utf-8-sig') as stream:
                writer = csv.writer(stream, delimiter=';')
                writer.writerow(
                    [tr(h) for i, h in enumerate(metadata.HEADERS) if i not in (12, 13, 15, 16, 36)]
                )
                writer.writerows(
                    [
                        value
                        for i, value in enumerate(row.values[: len(metadata.HEADERS)])
                        if i not in (12, 13, 15, 16, 36)
                    ]
                    for row in rows
                )
        except GLib.Error:
            pass
        except OSError as error:
            parent.notify(str(error))

    chooser.save(parent, None, done)


def search(parent):
    pane = parent.active
    win, box, header = window(parent, tr('Filtres de recherche'), 520, 520)
    types = ['all', 'video', 'audio', 'image']
    kind = Gtk.DropDown.new_from_strings([tr(s) for s in ['Tous', 'Vidéo', 'Audio', 'Images']])
    kind.set_selected(types.index(pane.type_filter))
    box.append(kind)
    values = {}
    for title, key in [
        ('Taille minimale (Mio)', 'size_mib'),
        ('Durée minimale (secondes)', 'duration'),
        ('Largeur minimale (pixels)', 'width'),
    ]:
        line = Gtk.Box(spacing=8)
        line.append(Gtk.Label(label=tr(title), xalign=0, hexpand=True))
        spin = Gtk.SpinButton.new_with_range(0, 100000, 1)
        spin.set_value(pane.criteria.get(key, 0))
        line.append(spin)
        values[key] = spin
        box.append(line)
    errors = Gtk.CheckButton(
        label=tr('Fichiers avec erreur connue'), active=bool(pane.criteria.get('errors'))
    )
    box.append(errors)
    label = Gtk.Entry(text=pane.criteria.get('label', ''), placeholder_text=tr('Étiquette'))
    box.append(label)
    text_filters = {}
    for key, title in (('artist', 'Artiste'), ('album', 'Album')):
        entry = Gtk.Entry(text=pane.criteria.get(key, ''), placeholder_text=tr(title))
        entry.update_property([Gtk.AccessibleProperty.LABEL], [tr(title)])
        text_filters[key] = entry
        box.append(entry)
    note = Gtk.Label(
        label=tr(
            'Ces filtres complètent la recherche par nom. Les critères multimédias utilisent les métadonnées disponibles.'
        ),
        wrap=True,
        xalign=0,
    )
    box.append(note)

    def apply(_):
        pane.type_filter = types[kind.get_selected()]
        pane.criteria = {k: int(v.get_value()) for k, v in values.items() if v.get_value()}
        pane.criteria.update({key: entry.get_text().strip() for key, entry in text_filters.items() if entry.get_text().strip()})
        pane.criteria['label'] = label.get_text().strip()
        if not pane.criteria['label']:
            pane.criteria.pop('label')
        if errors.get_active():
            pane.criteria['errors'] = True
        pane.update_search_labels()
        pane.search_changed()
        pane.update_search_empty()
        win.close()

    button = Gtk.Button(label=tr('Appliquer les filtres'), css_classes=['suggested-action'])
    button.connect('clicked', apply)
    box.append(button)
    reset = Gtk.Button(label=tr('Effacer les filtres'))
    reset.connect('clicked', lambda *_: (pane.clear_search_filters(), win.close()))
    box.append(reset)
    win.present()
    return win


def organize(parent):
    rows = [i.row for i in parent.active.selected()]
    if not rows:
        return
    folder = parent.active.folder
    win, box, header = window(parent, tr('Organiser en sous-dossiers…'))
    keys = ['artist', 'album', 'genre', 'date_taken', 'media_type']
    select = Gtk.DropDown.new_from_strings(
        [tr(s) for s in ['Artiste', 'Album', 'Genre', 'Date de prise de vue', 'Type de média']]
    )
    box.append(select)
    preview = Gtk.Label(xalign=0, wrap=True, selectable=True)
    scroll = Gtk.ScrolledWindow(vexpand=True)
    scroll.set_child(preview)
    box.append(scroll)
    plans = {}
    button = Gtk.Button(label=tr('Déplacer…'), css_classes=['suggested-action'])
    box.append(button)

    def update(*_):
        plans.clear()
        key = keys[select.get_selected()]
        lines = []
        for row in rows:
            value = row.media_type if key == 'media_type' else str(row.media_tags.get(key, ''))
            if key == 'date_taken':
                value = value[:10].replace(':', '-')
            if not value or not file_moves.valid_name(value):
                lines.append(row.path.name + ' → ' + tr('Métadonnée absente ou nom invalide'))
                continue
            target = folder / value / row.path.name
            plans[row.path] = target
            lines.append(row.path.name + ' → ' + str(target.relative_to(folder)))
        preview.set_label('\n'.join(lines))
        button.set_sensitive(bool(plans))

    def apply(_):
        snapshot = dict(plans)

        def commit():
            def work(path, cancelled, report):
                target = snapshot[path]
                if cancelled():
                    raise InterruptedError()
                target.parent.mkdir(exist_ok=True)
                file_moves.move_one(
                    path,
                    target,
                    cancelled,
                    bytes_progress=lambda d, t: report(d / t if t else None, path.name),
                )
                parent.state.relocate(path, target)
                return {'source': str(path), 'target': str(target)}

            parent.jobs.submit(tr('Organiser'), list(snapshot), work, False)
            win.close()

        confirm(win, tr('Déplacer les éléments proposés ?'), f'{len(snapshot)} {tr("élément(s)")}', commit)

    select.connect('notify::selected', update)
    button.connect('clicked', apply)
    update()
    win.present()
    return win


class EditRecord(GObject.Object):
    revision = GObject.Property(type=int, default=0)
    status = GObject.Property(type=str, default='')

    def __init__(self, source, values):
        super().__init__()
        self.source = source
        self.values = dict(values)
        self.original = dict(values)


def editable_table(rows, fields, get_value, rename_status=False):
    """Only the visible cells own GTK editors, even for thousands of files."""
    records = [EditRecord(row, {key: get_value(row, key) for key, title in fields}) for row in rows]
    store = Gio.ListStore.new(EditRecord)
    store.splice(0, 0, records)
    view = Gtk.ColumnView(model=Gtk.NoSelection.new(store))
    view.set_show_column_separators(True)
    columns = [('__filename', tr('Nom actuel') if rename_status else tr('Fichier')), *fields]
    if rename_status:
        columns.append(('__status', tr('Résultat')))
    for key, title in columns:
        factory = Gtk.SignalListItemFactory()

        def setup(_f, li, key=key):
            if key in ('__filename', '__status'):
                child = Gtk.Label(xalign=0, ellipsize=3)
            else:
                child = Gtk.Entry(has_frame=False, width_chars=12)

                def changed(entry):
                    record = li.get_item()
                    if record and record.values[key] != entry.get_text():
                        record.values[key] = entry.get_text()
                        record.revision += 1

                child.connect('changed', changed)
            li.set_child(child)

        def bind(_f, li, key=key):
            record = li.get_item()
            child = li.get_child()

            def paint(*_):
                if key == '__filename':
                    child.set_label(record.source.path.name)
                    child.set_tooltip_text(str(record.source.path))
                elif key == '__status':
                    child.set_label(record.status)
                    child.set_tooltip_text(record.status)
                elif child.get_text() != record.values[key]:
                    child.set_text(record.values[key])

            paint()
            li.edit_binding = (record, [record.connect('notify::revision', paint), record.connect('notify::status', paint)])

        def unbind(_f, li):
            if getattr(li, 'edit_binding', None):
                record, handlers = li.edit_binding
                for handler in handlers:
                    record.disconnect(handler)
                li.edit_binding = None

        factory.connect('setup', setup)
        factory.connect('bind', bind)
        factory.connect('unbind', unbind)
        column = Gtk.ColumnViewColumn(
            title=title, factory=factory, resizable=True, expand=key != '__filename'
        )
        column.set_fixed_width(240 if key == '__filename' else 170)
        view.append_column(column)
    scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    scroll.set_child(view)
    return scroll, records


def toolbar(parent):
    win, box, header = window(parent, tr('Personnaliser la barre d’outils'), 570, 640)
    css = Gtk.CssProvider()
    css.load_from_data(
        b'.toolbar-drop-before { border-top: 2px solid @accent_color; } .toolbar-drop-after { border-bottom: 2px solid @accent_color; } .toolbar-dragging { opacity: 0.45; }'
    )
    Gtk.StyleContext.add_provider_for_display(win.get_display(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    note = Gtk.Label(
        label=tr(
            'Faites glisser les commandes pour les réorganiser. La barre de chemin reste au centre et ne peut pas être masquée. Dans une fenêtre étroite, Mirivue utilise automatiquement les icônes seules.'
        ),
        wrap=True,
        xalign=0,
    )
    box.append(note)
    styles = ['icons', 'both', 'text']
    select = Gtk.DropDown.new_from_strings([tr(s) for s in ['Icônes', 'Icônes et texte', 'Texte seul']])
    select.set_selected(styles.index(parent.state.settings['toolbar_style']))
    box.append(select)
    select.connect(
        'notify::selected',
        lambda row, _: (
            parent.state.settings.__setitem__('toolbar_style', styles[row.get_selected()]),
            parent.rebuild_toolbar(),
        ),
    )
    size_values = ['normal', 'large', 'huge']
    size = Gtk.DropDown.new_from_strings([tr(s) for s in ['Normale', 'Grande', 'Très grande']])
    size.set_selected(size_values.index(parent.state.settings.get('toolbar_icon_size', 'normal')))
    box.append(size)
    size.connect(
        'notify::selected',
        lambda row, _: (
            parent.state.settings.__setitem__('toolbar_icon_size', size_values[row.get_selected()]),
            parent.state.save(),
            parent.rebuild_toolbar(),
        ),
    )
    listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=['boxed-list'])
    scroll = Gtk.ScrolledWindow(vexpand=True)
    scroll.set_child(listing)
    box.append(scroll)
    highlighted = [None]

    def clear_drop_indicator():
        row = highlighted[0]
        if row:
            row.remove_css_class('toolbar-drop-before')
            row.remove_css_class('toolbar-drop-after')
        highlighted[0] = None

    def build():
        clear_drop_indicator()
        while listing.get_first_child():
            listing.remove(listing.get_first_child())
        order = parent.state.settings['toolbar_order']
        for index, key in enumerate(order):
            row = Gtk.ListBoxRow()
            line = Gtk.Box(spacing=10)
            line.set_margin_start(10)
            line.set_margin_end(10)
            line.set_margin_top(6)
            line.set_margin_bottom(6)
            row.set_child(line)
            if key == 'paths':
                line.append(Gtk.Image.new_from_icon_name('folder-symbolic'))
                line.append(
                    Gtk.Label(label=tr('Barre de chemin — toujours affichée'), xalign=0, hexpand=True)
                )
                row.add_css_class('toolbar-path-anchor')
            else:
                drag_handle = reorder_handle()
                line.append(drag_handle)
                check = Gtk.CheckButton(active=key not in parent.state.settings['toolbar_hidden'])
                check.set_tooltip_text(tr('Afficher ou masquer cette commande'))
                line.append(check)
                icon, label = parent.TOOLBAR[key]
                line.append(Gtk.Image.new_from_icon_name(icon))
                line.append(Gtk.Label(label=tr(label), xalign=0, hexpand=True))

                def toggled(c, key=key):
                    hidden = parent.state.settings['toolbar_hidden']
                    if c.get_active():
                        if key in hidden:
                            hidden.remove(key)
                    elif key not in hidden:
                        hidden.append(key)
                    parent.state.save()
                    parent.rebuild_toolbar()

                check.connect('toggled', toggled)
                source = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
                source.connect('prepare', lambda _source, _x, _y, k=key: Gdk.ContentProvider.new_for_value(k))
                source.connect(
                    'drag-begin', lambda _source, _drag, r=row: (r.add_css_class('toolbar-dragging'), None)[1]
                )
                source.connect(
                    'drag-end', lambda _source, _drag, _delete, r=row: r.remove_css_class('toolbar-dragging')
                )
                row.add_controller(source)
            target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)

            def motion(_target, x, y, row_widget=row):
                clear_drop_indicator()
                row_widget.add_css_class(
                    'toolbar-drop-after' if y >= row_widget.get_height() / 2 else 'toolbar-drop-before'
                )
                highlighted[0] = row_widget
                return Gdk.DragAction.MOVE

            def leave(_target):
                clear_drop_indicator()

            def drop(_target, value, x, y, target_key=key, row_widget=row):
                if value not in parent.TOOLBAR:
                    return False
                after = bool(y >= row_widget.get_height() / 2)
                changed = reorder_toolbar(parent.state.settings['toolbar_order'], value, target_key, after)
                clear_drop_indicator()
                if changed == parent.state.settings['toolbar_order']:
                    return False
                parent.state.settings['toolbar_order'] = changed
                parent.state.save()
                parent.rebuild_toolbar()
                GLib.idle_add(build)
                return True

            target.connect('motion', motion)
            target.connect('leave', leave)
            target.connect('drop', drop)
            row.add_controller(target)
            listing.append(row)

    reset = Gtk.Button(label=tr('Rétablir la disposition par défaut'))

    def reset_toolbar(*_):
        from .backend import DEFAULTS

        parent.state.settings['toolbar_order'] = list(DEFAULTS['toolbar_order'])
        parent.state.settings['toolbar_hidden'] = []
        parent.state.settings['toolbar_style'] = 'icons'
        parent.state.settings['toolbar_icon_size'] = 'normal'
        select.set_selected(0)
        parent.state.save()
        parent.rebuild_toolbar()
        build()

    reset.connect('clicked', reset_toolbar)
    box.append(reset)
    build()
    win.connect(
        'close-request',
        lambda *_: (
            parent.state.save(),
            Gtk.StyleContext.remove_provider_for_display(win.get_display(), css),
            False,
        )[2],
    )
    win.present()
    return win


def summary_items(pane):
    return list(pane.selected()) or [pane.filtered.get_item(i) for i in range(pane.filtered.get_n_items())]


def media_summary(parent):
    """A concise local overview of the current selection or loaded folder."""
    from .i18n import size_text

    items = summary_items(parent.active)
    items = [item for item in items if not item.row.is_dir]
    if not items:
        parent.notify(tr('Aucun média à résumer.'))
        return
    counts = {'video': 0, 'audio': 0, 'image': 0, 'other': 0}
    total_size = 0
    duration = 0.0
    errors = 0
    missing_bitrate = 0
    for item in items:
        kind = item.row.media_type if item.row.media_type in counts else 'other'
        counts[kind] += 1
        try:
            total_size += item.path.stat().st_size
        except OSError:
            pass
        value = item.row.sort_values[2] if len(item.row.sort_values) > 2 else 0
        if isinstance(value, (int, float)):
            duration += value
        if item.row.error:
            errors += 1
        if kind == 'video' and not item.row.media_technical.get('bitrate'):
            missing_bitrate += 1

    def time_text(seconds):
        seconds = int(seconds)
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f'{hours} h {minutes:02d} min {seconds:02d} s' if hours else f'{minutes} min {seconds:02d} s'

    win, box, _header = window(parent, tr('Résumé multimédia'), 500, 430)
    title = Gtk.Label(
        label=tr('Résumé de la sélection') if parent.active.selected() else tr('Résumé du dossier chargé'),
        xalign=0,
        css_classes=['title-2'],
    )
    box.append(title)
    group = Adw.PreferencesGroup()
    box.append(group)
    for title, value in [
        (tr('Éléments analysés'), str(len(items))),
        ('Vidéos', str(counts['video'])),
        ('Fichiers audio', str(counts['audio'])),
        ('Images', str(counts['image'])),
        (tr('Autres fichiers'), str(counts['other'])),
        (tr('Taille totale'), size_text(total_size)),
        (tr('Durée totale'), time_text(duration)),
        (tr('Fichiers en erreur'), str(errors)),
        (tr('Vidéos sans débit'), str(missing_bitrate)),
    ]:
        row = Adw.ActionRow(title=tr(title))
        row.add_suffix(Gtk.Label(label=value, selectable=True))
        group.add(row)
    win.present()
    return win


def media_tools(parent):
    """Keep specialized media operations discoverable without crowding the primary menu."""
    win, box, _header = window(parent, tr('Outils multimédias'), 620, 680)
    rows = [item.row for item in parent.active.selected()]
    note = Gtk.Label(
        label=tr(
            'Les outils du dossier sont disponibles ; sélectionnez des éléments pour afficher les autres outils.'
        )
        if not rows
        else tr('Seuls les outils applicables à la sélection sont affichés.'),
        wrap=True,
        xalign=0,
    )
    box.append(note)
    video = bool(rows) and all(row.is_video for row in rows)
    playable = bool(rows) and all(row.media_type in ('video', 'audio') or row.is_video for row in rows)
    media_rows = bool(rows) and any(
        row.media_type in ('video', 'audio', 'image') or row.is_video for row in rows
    )
    folders = bool(rows) and all(row.is_dir for row in rows)
    eligible = {
        'summary': bool(parent.active.filtered.get_n_items()),
        'metadata': media_rows,
        'label': media_rows,
        'export': True,
        'test': playable,
        'total': folders,
        'bulk-rename': len(rows) > 1,
        'group': len(rows) > 1,
        'organize': len(rows) > 1,
        'collection': media_rows,
        'associated': playable,
        'compare-media': len(rows) == 2 and not any(row.is_dir for row in rows),
        'extension': any(row.suggested_extension for row in rows),
        'mkv': video,
    }
    groups = [
        (
            tr('Informations'),
            [
                ('Résumé multimédia', 'summary'),
                ('Métadonnées…', 'metadata'),
                ('Tester la lecture', 'test'),
                ('Étiquette…', 'label'),
                ('Exporter la liste…', 'export'),
            ],
        ),
        (
            tr('Organisation'),
            [
                ('Calculer la durée totale', 'total'),
                ('Renommer en masse…', 'bulk-rename'),
                ('Nouveau dossier contenant la sélection…', 'group'),
                ('Organiser en sous-dossiers…', 'organize'),
                ('Ajouter à une collection…', 'collection'),
                ('Sélectionner les fichiers associés', 'associated'),
                ('Comparer les deux médias', 'compare-media'),
                ('Corriger les extensions…', 'extension'),
                ('Créer une copie MKV…', 'mkv'),
            ],
        ),
    ]
    for title, actions in groups:
        actions = [(label, action) for label, action in actions if eligible.get(action, False)]
        if not actions:
            continue
        section = Adw.PreferencesGroup(title=title)
        box.append(section)
        for label, action in actions:
            row = Adw.ActionRow(title=tr(label))
            button = Gtk.Button(label=tr('Exécuter'), valign=Gtk.Align.CENTER, action_name='win.' + action)
            if action in ('test', 'mkv') and not shutil.which('ffmpeg'):
                button.set_sensitive(False)
                row.set_subtitle(tr('ffmpeg requis pour cette action'))
            row.add_suffix(button)
            section.add(row)
    win.present()
    return win


def shortcuts(parent):
    groups = [
        (
            'Actions',
            [
                (
                    'Fichiers',
                    [
                        ('Ouvrir', 'Return'),
                        ('Copier', '<Control>c'),
                        ('Couper', '<Control>x'),
                        ('Coller', '<Control>v'),
                        ('Tout sélectionner', '<Control>a'),
                        ('Inverser la sélection', '<Control><Shift>i'),
                        ('Nouveau dossier', '<Control><Shift>n'),
                        ('Renommer', 'F2'),
                        ('Mettre à la corbeille', 'Delete'),
                        ('Annuler', '<Control>z'),
                        ('Rétablir', '<Control><Shift>z'),
                        ('Propriétés', '<Alt>Return'),
                    ],
                ),
                (
                    'Affichage',
                    [
                        ('Actualiser le dossier', 'F5'),
                        ('Afficher les éléments cachés', '<Control>h'),
                        ('Afficher ou masquer le second panneau', 'F3'),
                        ('Afficher ou masquer l’aperçu', 'F9'),
                        ('Zoom avant', '<Control>plus'),
                        ('Zoom arrière', '<Control>minus'),
                        ('Zoom normal', '<Control>0'),
                    ],
                ),
            ],
        ),
        (
            'Navigation',
            [
                (
                    'Emplacements',
                    [
                        ('Emplacement précédent', '<Alt>Left'),
                        ('Emplacement suivant', '<Alt>Right'),
                        ('Dossier parent', '<Alt>Up'),
                        ('Dossier personnel', '<Alt>Home'),
                        ('Saisir un emplacement', '<Control>l'),
                        ('Rechercher', '<Control>f'),
                        ('Ajouter ce dossier aux signets', '<Control>d'),
                    ],
                ),
                (
                    'Onglets',
                    [
                        ('Nouvelle fenêtre', '<Control>n'),
                        ('Nouvel onglet', '<Control>t'),
                        ('Ouvrir dans de nouveaux onglets', '<Control>Return'),
                        ('Ouvrir dans de nouvelles fenêtres', '<Shift>Return'),
                        ('Fermer l’onglet ou la fenêtre', '<Control>w'),
                        ('Rouvrir l’onglet fermé', '<Control><Shift>t'),
                        ('Onglet précédent', '<Control>Page_Up'),
                        ('Onglet suivant', '<Control>Page_Down'),
                    ],
                ),
            ],
        ),
        (
            'Application',
            [
                (
                    'Mirivue',
                    [
                        ('Menu principal', 'F10'),
                        ('Ouvrir un terminal ici', '<Control>period'),
                        ('Aide', 'F1'),
                        ('Préférences', '<Control>comma'),
                        ('Raccourcis clavier', '<Control>question'),
                        ('Quitter', '<Control>q'),
                    ],
                )
            ],
        ),
    ]
    if hasattr(Adw, 'ShortcutsDialog'):
        dialog = Adw.ShortcutsDialog()
        for section_title, section_groups in groups:
            section = Adw.ShortcutsSection.new(tr(section_title))
            for _group_title, entries in section_groups:
                for label, accelerator in entries:
                    item = Adw.ShortcutsItem.new(tr(label), accelerator)
                    section.add(item)
            dialog.add(section)
        dialog.present(parent)
        return dialog
    if not hasattr(Gtk, 'ShortcutsWindow') or not hasattr(Gtk.ShortcutsWindow, 'add_section'):
        win, box, _header = window(parent, tr('Raccourcis clavier'), 620, 560)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        box.append(scroll)
        listing = Gtk.ListBox(css_classes=['boxed-list'])
        scroll.set_child(listing)
        for _section_title, section_groups in groups:
            for _group_title, entries in section_groups:
                for label, accelerator in entries:
                    row = Adw.ActionRow(title=tr(label))
                    row.add_suffix(
                        Gtk.Label(label=Gtk.accelerator_get_label(*Gtk.accelerator_parse(accelerator)))
                    )
                    listing.append(row)
        win.present()
        return win
    win = Gtk.ShortcutsWindow(transient_for=parent, modal=True, title=tr('Raccourcis clavier'))
    for section_title, section_groups in groups:
        section = Gtk.ShortcutsSection(title=tr(section_title), section_name=section_title.lower())
        for group_title, entries in section_groups:
            group = Gtk.ShortcutsGroup(title=tr(group_title))
            for label, accelerator in entries:
                group.add_shortcut(Gtk.ShortcutsShortcut(title=tr(label), accelerator=accelerator))
            section.add_group(group)
        win.add_section(section)
    win.present()
    return win


def help_page(parent):
    language = 'en' if tr('Nom') == 'Name' else 'fr'
    win, box, header = window(parent, tr('Aide'), 660, 580)
    label = Gtk.Label(
        label=Path(__file__).with_name('help.' + language + '.txt').read_text(),
        wrap=True,
        xalign=0,
        selectable=True,
    )
    scroll = Gtk.ScrolledWindow(vexpand=True)
    scroll.set_child(label)
    box.append(scroll)
    win.present()
    return win
