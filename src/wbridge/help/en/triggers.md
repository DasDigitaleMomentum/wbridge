# Triggers

Problem & Goal
You want to invoke actions by memorable short names (aliases) from CLI, HTTP, or shortcuts — without remembering long action names. 
The Triggers page lets you map aliases to existing actions and save them to your configuration.

What’s on this page
- Table editor: Alias → Action mapping
- Add/Delete rows
- Save with validation (writes to `~/.config/wbridge/actions.json`)
- Auto‑reload when the file changes on disk

---

## Key terms

- Trigger (alias): A short, human‑friendly name (e.g., `translate`, `prompt`, `open-ui`).
- Action (target): The name of an existing action defined under `actions` in `actions.json`.
- Triggers map: The `triggers` object inside `~/.config/wbridge/actions.json`:
  ```json
  {
    "triggers": {
      "upper": "Uppercase",
      "ingest": "Post to local API"
    }
  }
  ```

Invocation sources
- CLI: `wbridge trigger <alias> --from-primary|--from-clipboard`
- HTTP: Available if HTTP trigger is enabled in Settings
- Shortcuts: GNOME keybindings can execute `wbridge trigger <alias> ...`

---

## Process (overview)

1) Create or edit an alias in the table.
2) Select a target Action (must already exist on the Actions page).
3) Save (validates; writes to `actions.json` with backup).
4) Invoke the alias from CLI, HTTP, or a GNOME Shortcut.

---

## Step‑by‑step (quick start)

1) Prepare actions
   - Go to Actions and create at least one action (e.g., `Uppercase` or `Post to local API`).
   - Use stable names — triggers reference action names.

2) Add a trigger
   - On the Triggers page, click “Add Trigger”.
   - Enter an Alias (e.g., `upper`) and pick the target action (e.g., `Uppercase`).

3) Save
   - Click “Save Triggers”. The UI validates:
     - Alias is non‑empty
     - Aliases are unique
     - Each row references an existing Action name

4) Invoke
   - CLI examples:
     ```
     wbridge trigger upper --from-clipboard
     wbridge trigger ingest --from-primary
     ```
   - For HTTP invocation, enable the HTTP trigger in Settings and consult your base URL/paths there.

---

## Examples

`~/.config/wbridge/actions.json` (excerpt)
```json
{
  "actions": [
    {
      "name": "Uppercase",
      "type": "shell",
      "command": "tr",
      "args": ["a-z", "A-Z"]
    },
    {
      "name": "Post to local API",
      "type": "http",
      "method": "POST",
      "url": "http://localhost:8808/ingest"
    }
  ],
  "triggers": {
    "upper": "Uppercase",
    "ingest": "Post to local API"
  }
}
```

CLI
```
# Use Primary Selection as input
wbridge trigger upper --from-primary
# Use Clipboard as input
wbridge trigger ingest --from-clipboard
```

GNOME Shortcut (concept)
- Command field: `wbridge trigger upper --from-primary`
- Binding: e.g., `<Ctrl><Alt>p`

---

## Validation & persistence

- Validation on Save:
  - Alias must not be empty
  - Aliases must be unique
  - Each alias must reference an existing Action by name (case‑sensitive)
- Persistence:
  - Writes the `triggers` object to `~/.config/wbridge/actions.json`
  - Creates a timestamped backup before write
- Auto‑reload:
  - Edits made externally are picked up by file monitors; revisit the page or wait briefly for debounce.

---

## Good practices

- Keep aliases short and stable (don’t rename frequently).
- Housekeeping: If you remove an Action on the Actions page, related triggers are cleaned up there.
- Start simple: create a working action first, then add a trigger to it.
- Naming conventions: lowercase and hyphens (e.g., `send-to-api`, `open-ui`).

---

## Troubleshooting

Save fails: “duplicate alias” or “alias must not be empty”
- Ensure every row has a unique, non‑empty alias.

Save fails: “action ‘X’ … not found”
- Verify the action exists and the name matches exactly (case‑sensitive).

Table doesn’t reflect external edits
- Wait briefly for file monitor debounce or press the Actions page “Reload actions” and revisit Triggers.

HTTP invocation doesn’t work
- Enable HTTP trigger in Settings and verify Base URL/paths with the Health check.
- Check the Status page log tail for errors.

---

## Glossary & links

- Actions: reusable operations (HTTP/Shell) that consume the current selection
- Triggers: alias → action mapping; short names for invoking actions
- Shortcuts: GNOME keybindings that run `wbridge` CLI commands

Related pages:
- Actions: `help/en/actions.md`
- Settings (HTTP trigger, profiles, shortcuts): `help/en/settings.md`
- Shortcuts (GNOME custom keybindings): `help/en/shortcuts.md`
- Status (logs): `help/en/status.md`
