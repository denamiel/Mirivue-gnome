# Mirivue GTK 0.5.76

- Fixes an asynchronous GTK row-update race that could leave folder item counts stored in the model but missing from the Details list. Existing direct counts are restored before the enriched row is published, so the visible cell refreshes reliably.
- Adds a regression test for the exact race.

Validation: all 26 GTK-independent and model/UI-menu tests pass.
