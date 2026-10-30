"""Individual F2 uses a GtkPopover, following NautilusRenameFilePopover.

Reference: GNOME/nautilus src/resources/ui/nautilus-rename-file-popover.blp.
Batch rename is deliberately handled by the existing separate editor.
"""
import os
from gi.repository import Gtk, Gdk, GLib
from .i18n import tr
from .core import file_moves, renaming


def show_rename(pane, item):
    old = getattr(pane, 'rename_popover', None)
    if old is not None:
        old.popdown()
    view = pane.grid if pane.local_view == 'icons' else pane.view
    popover = Gtk.Popover(autohide=True)
    popover.set_parent(view)
    pane.rename_popover = popover
    generation = pane.generation
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
    # These margins follow the official Nautilus popover template.
    for side in ('top', 'bottom', 'start', 'end'):
        getattr(box, 'set_margin_' + side)(18)
    box.append(Gtk.Label(label=tr('Renommer'), css_classes=['title-2']))
    entry = Gtk.Entry(text=item.name, activates_default=False)
    entry.update_property([Gtk.AccessibleProperty.LABEL], [tr('Nouveau nom')])
    box.append(entry)
    feedback = Gtk.Label(wrap=True, xalign=0)
    box.append(feedback)
    button = Gtk.Button(label=tr('Renommer'), halign=Gtk.Align.END, css_classes=['suggested-action'])
    box.append(button)
    popover.set_child(box)
    popover.entry = entry

    def validate(*_):
        name = entry.get_text()
        issue = file_moves.invalid_name_reason(name) if not file_moves.valid_name(name) else ''
        if not issue and name != item.name and getattr(item.row, 'gio_file', None) is None:
            if os.path.lexists(item.path.with_name(name)):
                issue = tr('Un élément porte déjà ce nom.')
        feedback.set_label(issue)
        feedback.set_visible(bool(issue))
        entry.remove_css_class('error')
        if issue:
            entry.add_css_class('error')
        button.set_sensitive(not issue and name != item.name)

    def accept(*_):
        if not button.get_sensitive() or pane.closed or generation != pane.generation:
            return
        pane.window.finish_inline_rename(item, entry.get_text())
        popover.popdown()

    def closed(*_):
        if pane.rename_popover is popover:
            pane.rename_popover = None
        GLib.idle_add(lambda: (popover.unparent(), False)[1])

    def anchor(widget):
        child = widget.get_first_child()
        while child:
            if getattr(child, 'record', None) is item:
                ok, bounds = child.compute_bounds(view)
                if ok:
                    rect = Gdk.Rectangle()
                    rect.x, rect.y = int(bounds.get_x()), int(bounds.get_y())
                    rect.width, rect.height = max(1, int(bounds.get_width())), max(1, int(bounds.get_height()))
                    popover.set_pointing_to(rect)
                    return True
            if anchor(child):
                return True
            child = child.get_next_sibling()
        return False

    entry.connect('changed', validate)
    entry.connect('activate', accept)
    button.connect('clicked', accept)
    popover.connect('closed', closed)
    anchor(view)
    validate()
    popover.popup()
    entry.grab_focus()
    entry.select_region(0, renaming.single_name_selection_end(item.name, item.row.is_dir))
    return popover
