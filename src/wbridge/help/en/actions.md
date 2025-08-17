# Actions

Create, inspect, and run reusable actions against your current selection. The page uses a master–detail layout:
- Left: list of actions loaded from `~/.config/wbridge/actions.json`
- Right: shared editor for the selected action (Form and JSON tabs), plus a result area

You can run actions against one of three sources:
- Clipboard (default)
- Primary Selection
- Text (ad‑hoc text you provide)

---

## Anatomy of an action

Two action types are supported:

1) HTTP action (`type: "http"`)
- Method: `GET` or `POST`
- URL: Full http/https URL
- Optional extra fields (headers, params) may be present in the JSON, even if not exposed in the Form tab.

2) Shell action (`type: "shell"`)
- Command: Executable or script to run
- Args: A JSON array of string arguments
- Use shell: If enabled, executes via a system shell (e.g., `/bin/sh -c`) — use with care

The selected source provides the input text (Clipboard or Primary) or the text you supply when Source = Text. The action runner passes this text to your action; for HTTP/Shell, the integration logic decides how to incorporate it (e.g., as a body, argument, or query param depending on your configuration and action semantics).

---

## Workflow

1) Select source
- Combo next to the text field:
  - Clipboard: Use current Clipboard content
  - Primary: Use current Primary Selection content
  - Text: Enable the adjacent entry and type your ad‑hoc input

2) Manage actions
- Reload actions: Re-read `actions.json` from disk and refresh the list.
- Add Action: Create a new HTTP action with defaults. Names are de‑duplicated automatically.

3) Edit the selected action (right side)
- Form tab (recommended):
  - Name: Unique identifier
  - Type: `http` or `shell`
  - HTTP fields: Method, URL
  - Shell fields: Command, Args (JSON array), Use shell
  - Save (Form): Validates and writes back to `actions.json`. A timestamped backup is created.

- JSON tab (advanced):
  - Raw JSON view of the action object
  - Save (JSON): Validates and writes back to `actions.json`. A backup is created.

- Other actions:
  - Duplicate: Creates a copy with a unique name, then selects it
  - Delete: Removes the selected action (and cleans up triggers that referenced it)
  - Cancel: Discards local edits by reloading from disk

4) Run
- Run: Executes the action against the chosen source.
- Results appear in the result area below the editor.
- Note: If the HTTP integration is disabled, running HTTP actions may be unavailable. Enable it in Settings (HTTP trigger).

---

## Validation and persistence

- Validation: The UI uses the project&#39;s `validate_action_dict` to ensure the minimal required structure and types.
- Persistence: On save, changes are written to `~/.config/wbridge/actions.json`. A backup is created before overwriting.
- Auto‑reload: File monitors refresh the in‑memory configuration and UI when changes are detected externally (edits from a text editor, etc.).

---

## Tips

- Naming: Use stable names; triggers refer to actions by name. Renaming an action will require reassigning triggers.
- HTTP: Start with `GET` and a simple URL, then add headers/params as needed (via JSON when advanced fields apply).
- Shell:
  - Keep commands idempotent; the selected text is often user‑provided.
  - Prefer explicit arguments via `Args (JSON array)`.
  - Use “Use shell” only when you need a shell feature (pipes, globs, expansions) and accept the risks.

---

## Known limitations and roadmap notes

- Timeout and on‑success behaviors are planned for a later step (optional v1). For example:
  - `timeout_s`: Allow canceling long‑running requests.
  - `on_success.apply_to`: Apply the result back to Clipboard/Primary automatically.
- The Form tab surfaces the most common fields. Advanced/custom fields may require editing via JSON.

---

## Troubleshooting

- Run is disabled or failing:
  - Check “Settings > Integration” and ensure HTTP trigger is enabled if you rely on HTTP actions.
  - Review logs on the “Status” page (Log tail).
- Validation failures:
  - Check that Names are non‑empty and unique.
  - For shell: `Args` must be a JSON array (e.g., `["-n", "value"]`).
- Unexpected action behavior:
  - Inspect the raw JSON in the JSON tab.
  - Review your command paths and environment (PATH, permissions).
