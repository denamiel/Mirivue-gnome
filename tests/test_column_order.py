import unittest
from mirivue_gtk4.backend import reorder_column_order, column_order_targets


class ColumnOrderTests(unittest.TestCase):
    def test_move_before_and_after(self):
        self.assertEqual(reorder_column_order([0, 1, 2, 3], 3, 1), [0, 3, 1, 2])
        self.assertEqual(reorder_column_order([0, 1, 2, 3], 0, 2, True), [1, 2, 0, 3])

    def test_same_or_unknown_column_preserves_order(self):
        order = [0, 1, 2]
        self.assertEqual(reorder_column_order(order, 1, 1), order)
        self.assertEqual(reorder_column_order(order, 5, 1), order)

    def test_panel_selection_controls_layout_scope(self):
        self.assertEqual(column_order_targets('left'), ('left',))
        self.assertEqual(column_order_targets('right'), ('right',))
        self.assertEqual(column_order_targets('both'), ('left', 'right'))
        self.assertEqual(column_order_targets('invalid'), ())


if __name__ == '__main__':
    unittest.main()
