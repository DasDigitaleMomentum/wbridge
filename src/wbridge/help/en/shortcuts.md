# Shortcuts (GNOME Custom Keybindings)

Manage GNOME custom keybindings with a clear policy:
- Only wbridge‑managed entries (path suffix starting with `wbridge-`) are editable.
- Foreign (non‑wbridge) entries can be optionally shown read‑only for auditing.
- Conflicts are detected and summarized (e.g., `&#39;<Ctrl><Alt>p&#39; ×2`).

Backed by GNOME Settings schemas:
- Base: `org.gnome.settings-daemon.plugins.media-keys`
- Custom: `org.gnome.settings-daemon.plugins.media-keys.custom-keybinding`
- Paths live under: `/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/`

Each custom entry has:
- `name` (string)
- `command` (string)
- `binding` (accelerator string, e.g., `<Ctrl><Alt>p`)

---

## Page overview

- Show all custom (read‑only): Toggle to include non‑wbridge entries. Those rows are not editable and cannot be deleted here.
- Add: Creates a new editable row (not yet installed until you Save).
- Save: Validates rows and writes changes via Gio.Settings.
- Reload: Re‑reads all custom keybindings from GNOME Settings and rebuilds the list.

Result and conflict information is displayed below the list.

---

## wbridge management rules

wbridge only manages entries whose keybinding path suffix starts with `wbridge-`, for example:
```
/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/wbridge-prompt/
```
- Editable in the UI: yes
- Deletable from the UI: yes

Foreign entries (anything not starting with `wbridge-`) are:
- Editable in the UI: no (read‑only)
- Deletable from the UI: no

This ensures we do not unintentionally modify user‑created or third‑party keybindings.

---

## Suffix generation and renaming

When you Save:
- The UI computes a deterministic suffix from the `name`:
  - Normalize to lowercase, replace non `a-z0-9-` with `-`, trim `-`, and prefix with `wbridge-`.
  - Example: Name `My Prompt` → suffix `wbridge-my-prompt/`.
- If a row previously had a different suffix (rename), the old binding is removed before installing the new one.
- Suffix collisions are avoided by appending `-2`, `-3`, … as needed.

This scheme keeps keybinding paths stable and avoids conflicts.

---

## Validation and conflicts

On Save, each editable row must provide:
- Name: non‑empty
- Command: non‑empty
- Binding: non‑empty (e.g., `<Ctrl><Alt>p`)

The page also scans for binding conflicts (same accelerator used by multiple entries). Conflicts are summarized as:
```
'<Ctrl><Alt>p' ×2
```
Resolve by changing one of the bindings.

---

## PATH hint

If the `wbridge` executable is not found in your `PATH`, you&#39;ll see a hint. Options:
- Install user‑wide via `pipx install wbridge` or `pip install --user wbridge`
- Or reference an absolute path in the `command` field of the shortcuts

---

## Recommended defaults

From Settings you can install a recommended set of wbridge shortcuts, for example:
- Prompt: `<Ctrl><Alt>p`
- Command: `<Ctrl><Alt>m`
- Show UI: `<Ctrl><Alt>u`

These are installed under wbridge scope and can be edited later on this page.

---

## Troubleshooting

- Save failed: “name/command/binding must not be empty”
  - Ensure all three fields are provided.
- Shortcut didn&#39;t appear in GNOME Settings
  - Press Reload in this page.
  - Check `dconf` write permissions or try restarting GNOME Shell or your session if needed.
- Binding not working
  - Verify no global conflict: look for conflicts summary or check GNOME Keyboard shortcuts UI.
- `wbridge` command not found
  - Install via pipx/pip or provide an absolute path in the shortcut command field.
