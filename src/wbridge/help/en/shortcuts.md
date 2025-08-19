# Shortcuts (GNOME Custom Keybindings)

Problem & Goal
You want to trigger wbridge quickly with global shortcuts — without breaking Wayland rules or other apps. 
The Shortcuts page lets you install, review, and edit GNOME custom keybindings that run `wbridge` commands.

What’s on this page
- List of GNOME custom keybindings
- Edit rows that are managed by wbridge (scope: `wbridge-...`)
- Optional read‑only view of foreign entries (for auditing)
- Add / Save / Reload controls
- Conflicts summary (e.g., `&#39;<Ctrl><Alt>p&#39; ×2`)

---

## Key terms

- GNOME Custom Keybindings: User‑defined shortcuts managed via `Gio.Settings`.
- Managed scope: Only entries whose dconf path suffix starts with `wbridge-` are editable/deletable from this page.
- Foreign entries: Any non‑wbridge entry (viewable optionally, read‑only).
- Binding: Accelerator string (e.g., `<Ctrl><Alt>p`).
- Command: The shell command run by GNOME (e.g., `wbridge trigger prompt --from-primary`).

Backed by schemas
- Base: `org.gnome.settings-daemon.plugins.media-keys`
- Custom: `org.gnome.settings-daemon.plugins.media-keys.custom-keybinding`
- Paths live under: `/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/`

---

## Process (overview)

1) Show all custom keybindings (optionally include foreign entries read‑only).
2) Add or edit wbridge‑managed rows (name, command, binding).
3) Save (validates; writes via `Gio.Settings`).
4) Resolve any binding conflicts.
5) Test your shortcut.

---

## Step‑by‑step (quick start)

1) Install recommended defaults (from Settings)
   - Settings → “Install GNOME Shortcuts”.
   - Default set (if no profile/settings override):
     - Prompt: `<Ctrl><Alt>p`
     - Command: `<Ctrl><Alt>m`
     - Show UI: `<Ctrl><Alt>u`

2) Review on the Shortcuts page
   - Toggle “Show all custom (read‑only)” to audit foreign entries.
   - wbridge entries are editable; foreign entries remain read‑only.

3) Add / Edit
   - Click “Add” to create a new editable row.
   - Provide:
     - Name (non‑empty)
     - Command (e.g., `wbridge trigger prompt --from-primary`)
     - Binding (e.g., `<Ctrl><Alt>p`)

4) Save
   - Click “Save” to write bindings.
   - Validation checks name/command/binding are present and summarizes conflicts.

5) Test
   - Use the new shortcut.
   - Open the Status page to see logs when the shortcut runs.

---

## Examples

Common wbridge commands for shortcuts
- Show UI
  ```
  wbridge ui show
  ```
- Run by trigger (from Primary Selection)
  ```
  wbridge trigger prompt --from-primary
  ```
- Run by trigger (from Clipboard)
  ```
  wbridge trigger command --from-clipboard
  ```

Suffix generation (what the app does)
- When saving, a stable dconf path suffix is derived from the Name:
  - Lowercase, replace non `a-z0-9-` with `-`, trim `-`, prefix `wbridge-`
  - Example: `My Prompt` → `/.../wbridge-my-prompt/`
- Renames remove the old binding before installing the new one.
- Collisions are resolved by appending `-2`, `-3`, …

---

## Validation & conflicts

On Save, each editable row must have:
- Name: non‑empty
- Command: non‑empty
- Binding: non‑empty accelerator string

Conflict detection
- The page summarizes duplicates like:
  ```
  '<Ctrl><Alt>p' ×2
  ```
- Resolve by changing one of the bindings.

---

## Good practices

- Keep Names descriptive; they become part of the stable keybinding path.
- Prefer triggers in Command (aliases are human‑friendly and decouple from action names).
- Start with defaults, then tailor bindings to your workflow.
- If `wbridge` is not on PATH, use an absolute path in Command.

PATH hint
- If GNOME can’t find `wbridge`:
  - Install via pipx with `--system-site-packages`
  - Ensure `~/.local/bin` is in PATH
  - Or use an absolute path in Command

---

## Troubleshooting

Save failed: “name/command/binding must not be empty”
- Provide all fields for each editable row.

Shortcut didn’t appear or update
- Click “Reload”.
- If necessary, restart GNOME Shell/session.

Binding not working
- Check the conflicts summary or GNOME Keyboard shortcuts UI for collisions.
- Try a different accelerator.

`wbridge` command not found
- Ensure PATH is correct (pipx installs into `~/.local/bin`).
- Use an absolute path if needed.

---

## Glossary & links

- Triggers: alias → action mapping (useful in Command)
- Actions: reusable operations (HTTP/Shell)
- Settings: install/remove recommended shortcuts; configure PATH hints
- Status: watch logs while pressing a shortcut

Related pages
- Actions: `help/en/actions.md`
- Triggers: `help/en/triggers.md`
- Settings (install defaults): `help/en/settings.md`
- Status (logs): `help/en/status.md`
