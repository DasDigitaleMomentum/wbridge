# History

Problem & Goal
You want to see, reuse, and quickly switch between recent selections. 
The History page shows Clipboard and Primary Selection histories side by side and lets you apply items back with one click.

What’s on this page
- Two panes: Clipboard and Primary Selection
- Current value preview (single line, ellipsized)
- Quick helpers: Set/Get and Swap last two
- Scrollable lists (newest first) with actions to re‑apply an item
- Manual Refresh (auto refresh happens periodically)

---

## Key terms

- Clipboard: Regular copy/paste buffer used by Ctrl+C/Ctrl+V.
- Primary Selection: Mouse selection buffer; often pasted via middle‑click. Exists in many Linux/Unix environments, including Wayland.
- Index convention: `[0]` is the most recent entry (newest first).
- Apply: Set a history item as the current Clipboard or Primary value.
- Swap: Swap the two most recent entries in a buffer and apply the top entry.

---

## Process (overview)

1) Observe current values and lists for Clipboard and Primary.
2) Use Set/Get helpers for quick ad‑hoc tests.
3) Apply an item from history back to Clipboard or Primary.
4) Swap the last two values if you need to toggle quickly.
5) Refresh if you need an immediate update (otherwise it refreshes periodically).

---

## Step‑by‑step (quick start)

1) Inspect current values
   - Each pane shows the current content (compact preview with ellipsis).

2) Test Set/Get
   - Type into the entry at the top of a pane.
   - Click “Set clipboard” / “Set primary” to apply the text.
   - Click “Get clipboard” / “Get primary” to read the current value.

3) Apply from history
   - In a list row, click “Set as Clipboard” or “Set as Primary”.
   - The value becomes current and is added to the respective history.

4) Swap last two
   - Click “Swap last two (clipboard)” or “Swap last two (primary)”.
   - Useful to toggle between two recent values.

5) Refresh
   - Click “Refresh” to reload both lists immediately.
   - Otherwise, the page updates periodically to reflect external changes.

---

## Examples

- Toggle between two snippets (Clipboard)
  1) Ensure both snippets have been used recently (they appear as `[0]` and `[1]`).
  2) Click “Swap last two (clipboard)” to alternate which one is active.

- Move a Primary value to Clipboard
  1) Find the item in the Primary list.
  2) Click “Set as Clipboard” on that row.
  3) Paste with Ctrl+V in your target app.

- Quick test of system integration
  1) Use the entry field to “Set primary” with a known string.
  2) Middle‑click in another app to verify Primary paste behavior.

---

## CLI equivalents

Read current value
```
wbridge selection get --which clipboard
wbridge selection get --which primary
```

Set a value
```
wbridge selection set --which clipboard "your text"
wbridge selection set --which primary "your text"
```

History operations
```
wbridge history list --which clipboard --limit 10
wbridge history apply --which primary --index 1
wbridge history swap --which clipboard
```

These commands integrate with scripts or external tools.

---

## Good practices

- Keep lists compact: newest first with stable line heights for fast scanning.
- Remember Primary vs Clipboard: middle‑click usually pastes from Primary.
- Index awareness: `[0]` is latest; higher indexes are older.
- Use the Status page to watch logs while reproducing selection behaviors.

---

## Troubleshooting

Nothing updates when setting values
- Confirm your session exposes Clipboard/Primary correctly.
- Use the Get buttons to verify set/get operations.
- Try Refresh; watch the Status page log for errors.

Unexpected characters or encoding issues
- Non‑UTF‑8 or binary content may be sanitized for display.
- Paste into a UTF‑8 aware editor to check encoding.

Values change outside of wbridge
- The page refreshes periodically; click Refresh to update immediately.
- Other apps may be writing to Clipboard/Primary; watch the Status log to correlate changes.

---

## Glossary & links

- Clipboard: Ctrl+C/Ctrl+V buffer
- Primary Selection: mouse selection buffer (often middle‑click paste)
- Apply: set a history item as the current value
- Swap: exchange the last two entries in a buffer

Related pages:
- Actions (use selection as input): `help/en/actions.md`
- Triggers (invoke actions by alias): `help/en/triggers.md`
- Shortcuts (GNOME keybindings): `help/en/shortcuts.md`
- Status (logs & environment): `help/en/status.md`
