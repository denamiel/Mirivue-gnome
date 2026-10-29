Version 0.5.57

- Stream initial folder rows in small batches (at most 16 entries or about 50 ms apart) so both panels begin showing their contents during enumeration instead of waiting for the whole folder.
- Preserve the configured startup folder independently in each visible panel.
- Keep the native selection, keyboard context menu, file clipboard, and empty-space parent navigation behavior from 0.5.56.
