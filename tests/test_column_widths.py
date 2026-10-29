import unittest
from mirivue_gtk4.backend import column_initial_width


class ColumnWidthTests(unittest.TestCase):
    def test_old_narrow_width_is_readable_at_startup(self):
        self.assertGreaterEqual(column_initial_width(0, 48), 270)
        self.assertGreaterEqual(column_initial_width(12, 75), 210)

    def test_user_wider_width_remains_in_place(self):
        self.assertEqual(column_initial_width(12, 340), 340)
