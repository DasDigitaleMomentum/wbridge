# Triggers

Map simple aliases to actions so you can invoke actions indirectly (from CLI, HTTP trigger, or UI features) without remembering long names. Triggers are stored in the same config as actions: `~/.config/wbridge/actions.json`.

On this page you can:
- View and edit the trigger table (Alias → Action)
- Add new rows
- Delete rows
- Save the table with validation

---

## Concept

- Alias: A short, human‑friendly identifier (e.g., `translate`, `send-to-server`, `open-ui`).
- Action: The name of an existing action defined under `actions` in `actions.json`.

When a trigger is invoked (e.g., via HTTP endpoint or CLI), wbridge resolves the alias to the referenced action and runs it with the current selection.

---

## UI operations

- Add Trigger: Appends a new row with empty Alias and a preselected Action (if any exist). Fill the alias and pick the target action.
- Delete (row): Removes the row from the table. If you need to restore it, discard changes and reload from disk before saving.
- Save Triggers:
  - Validates aliases (non‑empty, unique)
  - Validates that each selected Action exists
  - Writes the updated `triggers` object back to `~/.config/wbridge/actions.json` (with a backup prior to write)
- Reload (implicit):
  - When actions/triggers change on disk (e.g., edited in a text editor), the UI auto‑reloads due to file monitors.

---

## Validation rules

- Alias must not be empty.
- Aliases must be unique (no duplicates).
- Each row must reference a valid Action by name (the Action must exist).
- On save, the UI surfaces validation errors at the top (result label).

---

## Example: actions.json (excerpt)

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

- The table in the Triggers page corresponds to the `triggers` object.
- If you rename an Action, you must update any triggers that reference it.

---

## Workflows and tips

- Start simple: Create a few actions first, then define triggers that point to them.
- Stable names: Keep Action names stable; triggers reference action names.
- Housekeeping: Deleting an Action will also remove triggers that reference it when performed via the Actions page.

---

## Trigger invocation (CLI and HTTP)

- CLI (example):
  - `wbridge actions run --trigger upper --which clipboard`
- HTTP (example):
  - If the HTTP trigger is enabled in Settings, remote clients can call an endpoint that uses trigger aliases server‑side. See your integration settings for exact base URL and paths.

---

## Troubleshooting

- Save fails: “duplicate alias” or “alias must not be empty”
  - Ensure all rows have a unique, non‑empty alias string.
- Save fails: “action ‘X’ … not found”
  - Verify the action exists and the name matches exactly (case‑sensitive).
- Table doesn’t reflect external edits
  - Wait a moment for file monitor debounce or press the Actions page “Reload actions” button and revisit the Triggers page.
