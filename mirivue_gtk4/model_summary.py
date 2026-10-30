"""Maintain visible-row totals from native model notifications, not selections."""
from .core.panel_status import format_counts


def snapshot(item):
    row = item.row
    folder = int(row.is_dir)
    size = row.sort_values[1] if not folder else 0
    return (folder, 1 - folder, size if isinstance(size, (int, float)) and size > 0 else 0,
            int(bool(row.error)))


class ModelSummary:
    def __init__(self, model):
        self.model = model
        self.entries = []
        self.totals = [0, 0, 0, 0]
        self.signal = model.connect('items-changed', self.changed)
        self.changed(model, 0, 0, model.get_n_items())

    def add(self, values, factor):
        for index, value in enumerate(values):
            self.totals[index] += value * factor

    def changed(self, model, position, removed, added):
        for item, values, handler in self.entries[position:position + removed]:
            item.disconnect(handler)
            self.add(values, -1)
        entries = []
        for index in range(position, position + added):
            item = model.get_item(index)
            entry = [item, snapshot(item), None]
            def revised(_item, _prop, entry=entry):
                self.add(entry[1], -1)
                entry[1] = snapshot(entry[0])
                self.add(entry[1], 1)
            entry[2] = item.connect('notify::revision', revised)
            self.add(entry[1], 1)
            entries.append(entry)
        self.entries[position:position + removed] = entries

    def text(self, selected=()):
        selected = list(selected)
        if selected:
            values = [snapshot(item) for item in selected]
            folders, files, size = (sum(value[i] for value in values) for i in range(3))
        else:
            folders, files, size = self.totals[:3]
        return format_counts(folders, files, size, self.totals[3], bool(selected))

    def close(self):
        self.model.disconnect(self.signal)
        for item, _values, handler in self.entries:
            item.disconnect(handler)
        self.entries.clear()
