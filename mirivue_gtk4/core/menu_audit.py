"""Check Gio menu references against GNOME window actions during UI smoke tests."""


def missing_actions(model, lookup):
    missing = []
    for index in range(model.get_n_items()):
        action = model.get_item_attribute_value(index, 'action', None)
        if action is not None:
            name = action.get_string()
            if name.startswith('win.') and lookup(name[4:]) is None:
                missing.append(name)
        for link in ('section', 'submenu'):
            child = model.get_item_link(index, link)
            if child is not None:
                missing.extend(missing_actions(child, lookup))
    return missing
