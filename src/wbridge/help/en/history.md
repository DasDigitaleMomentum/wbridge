# History

Inspect and reuse your selection history for both Clipboard and Primary selections. The view is split into two panes:
- Clipboard
- Primary Selection

Each pane shows:
- Current value (single-line preview, ellipsized)
- Quick test helpers (Set/Get and Swap last two)
- A scrollable list of the latest entries (newest first) with actions to re-apply an item

The list is optimized for stable line heights and fast navigation.

---

## Clipboard vs Primary (What&#39;s the difference?)

- Clipboard: The "regular" selection buffer used by most copy/paste shortcuts (e.g., Ctrl+C/Ctrl+V).
- Primary Selection: The "selection" buffer usually tied to mouse selections and middle-click paste in many Linux/Unix environments (especially under X11/Wayland setups).

Primary paste (middle-click) typically uses the Primary Selection, not the Clipboard. This lets you keep two parallel buffers.

---

## What you see on this page

- Entries counter: Displays the number of entries in each list (Clipboard / Primary).
- Current value: Shows the currently active text for each buffer. The preview is ellipsized to keep row heights stable.
- History list: Newest entries appear at the top. Each row shows:
  - An index (e.g., [0], [1], …)
  - A single-line preview of the entry&#39;s first line
  - A mark ["[current]"] for the row that matches the current selection
  - Action buttons per row:
    - Set as Clipboard
    - Set as Primary

---

## Operations

### Set/Get helpers (top of each pane)
Use the text entry and buttons for quick testing:
- Set clipboard / Set primary: Apply the entry field’s text to the chosen buffer.
- Get clipboard / Get primary: Read and display the current value.

These helpers are intended for quick ad‑hoc checks while developing or verifying system integration.

### Apply from history
In the list:
- Click "Set as Clipboard" to set that item as the current Clipboard content.
- Click "Set as Primary" to set that item as the current Primary content.

The UI updates immediately and the History is refreshed. The newly applied value becomes the current selection and is added to history.

### Swap last two
- Swap last two (clipboard) or Swap last two (primary) swaps the two most recent entries of the respective list and applies the top entry.
- Useful for quick toggling between two values.

### Refresh
- Press "Refresh" to manually reload both lists.
- The view also refreshes periodically to reflect external changes.

---

## CLI equivalents

You can also read and set selections via the CLI:

- Read current value:
  - Clipboard: `wbridge selection get --which clipboard`
  - Primary: `wbridge selection get --which primary`

- Set value:
  - Clipboard: `wbridge selection set --which clipboard "your text"`
  - Primary: `wbridge selection set --which primary "your text"`

These commands integrate well with scripts and other tools.

---

## Tips and notes

- Ellipsizing: Long values are shown as single-line previews to keep the UI compact and easy to scan.
- Newest first: Index [0] is always the latest value.
- Primary paste: Middle-click paste typically pulls from Primary Selection, not the Clipboard.
- Limits: The UI shows the latest N entries (default around 20) for each buffer to keep the interface fast and compact.

---

## Troubleshooting

- Nothing updates when setting values:
  - Use the Get buttons to confirm the environment exposes the selection buffers properly.
  - Verify Wayland/X11 clipboard integration in your desktop session.

- Unexpected characters or encoding issues:
  - Non‑UTF‑8 or binary content may be sanitized before display.
  - Try pasting the text into a UTF‑8 aware editor to confirm its encoding.

- Values change outside of wbridge:
  - The page periodically refreshes to reflect external changes (other apps and tools).
