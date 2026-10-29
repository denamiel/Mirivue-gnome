import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mirivue_gtk4.pane import Pane


class DragSelectionTests(unittest.TestCase):
    def test_drag_preview_uses_selected_content_and_total_count(self):
        class Widget:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
                self.children = []

            def set_size_request(self, *args):
                self.size = args

            def set_pixel_size(self, size):
                self.size = size

            def set_content_fit(self, value):
                self.fit = value

            def append(self, child):
                self.children.append(child)

            def set_child(self, child):
                self.child = child

            def add_overlay(self, child):
                self.children.append(child)

            def set_halign(self, value):
                self.halign = value

            def set_valign(self, value):
                self.valign = value

            def set_margin_start(self, value):
                self.margin_start = value

            def set_margin_top(self, value):
                self.margin_top = value

            def set_can_target(self, value):
                self.can_target = value

            def set_focusable(self, value):
                self.focusable = value

        drag_icon = Widget()
        gtk = SimpleNamespace(
            Box=Widget,
            Overlay=Widget,
            Button=Widget,
            Image=SimpleNamespace(new_from_gicon=lambda name: Widget(icon=name)),
            Picture=SimpleNamespace(new_for_filename=lambda path: Widget(thumbnail=path)),
            ContentFit=SimpleNamespace(CONTAIN='contain'),
            Align=SimpleNamespace(START='start', END='end'),
            DragIcon=SimpleNamespace(get_for_drag=lambda drag: drag_icon),
        )
        items = [
            SimpleNamespace(
                path=SimpleNamespace(name=f'{i}.txt'),
                thumbnail=f'{i}.png' if i == 1 else '',
                thumbnail_visible=i == 1,
            )
            for i in range(6)
        ]
        pane = SimpleNamespace(selected=lambda: items, icon=lambda item: item.path.name)
        with patch('mirivue_gtk4.pane.Gtk', gtk):
            Pane.drag_begin(pane, None, object())
        badge = drag_icon.child.children[0]
        self.assertEqual(badge.label, '6')
        self.assertEqual(badge.css_classes, ['suggested-action', 'circular'])
        self.assertFalse(badge.can_target)
        stack = drag_icon.child.child
        icons = stack.child.children + stack.children
        self.assertEqual(len(icons), 4)
        self.assertEqual(
            [child.thumbnail if hasattr(child, 'thumbnail') else child.icon for child in icons],
            ['3.txt', '2.txt', '1.png', '0.txt'],
        )
        self.assertEqual(stack.child.margin_start, 12)

    def test_file_drag_pauses_rectangle_only_until_gesture_finishes(self):
        class View:
            def __init__(self):
                self.states = []

            def set_enable_rubberband(self, value):
                self.states.append(value)

        view = View()
        pane = SimpleNamespace(rubberband_paused=None, window=SimpleNamespace(drag_source_pane='source'))
        pane.picked = lambda _container, x, _y: object() if x > 0 else None
        pane.resume_rubberband = lambda: Pane.resume_rubberband(pane)

        Pane.file_drag_pressed(pane, None, 1, 0, 0, object(), view)
        self.assertEqual(view.states, [])
        Pane.file_drag_pressed(pane, None, 1, 1, 0, object(), view)
        self.assertEqual(view.states, [False])
        Pane.drag_end(pane)
        self.assertEqual(view.states, [False, True])
        self.assertIsNone(pane.window.drag_source_pane)

        Pane.file_drag_pressed(pane, None, 1, 1, 0, object(), view)
        Pane.file_drag_released(pane)
        self.assertEqual(view.states, [False, True, False, True])


if __name__ == '__main__':
    unittest.main()
