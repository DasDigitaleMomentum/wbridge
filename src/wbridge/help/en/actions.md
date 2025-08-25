# Actions

Problem & Goal
You want to reuse the current text selection and send it to a tool or service (HTTP or Shell) with one click or shortcut. 
The Actions page lets you create, inspect, and run reusable actions against your current selection — reliably on Wayland, without global key grabs.

What’s on this page
- Vertical split: Editor on top (Form/JSON tabs, result area), Actions list below
- Source selector at the top of the editor: dropdown + adjacent text entry (enabled only when Source = Text)
- Buttons under the editor fields: Save (Form), Duplicate, Delete, Cancel, Run
- Add Action / Reload actions buttons below the list
- Run: Execute the selected action with the chosen source

---

## Key terms

- Action: A reusable operation you run on the current selection. Types:
  - `http`: Send text to an HTTP endpoint (GET/POST; headers/body supported).
  - `shell`: Run a local program with arguments (no shell unless explicitly enabled).
- Source: Where the input text comes from:
  - Clipboard (regular copy/paste buffer)
  - Primary Selection (mouse selection; usually pasted with middle‑click)
  - Text (ad‑hoc text you type for this run)
- Placeholders: Variables you can reference in actions, resolved at runtime:
  - `{text}`, `{text_url}`, `{selection.type}`
  - `{history[0]}`, `{history[1]}`, …
  - `{app.name}`, `{now.iso}`, and config references like `{config.section.key}`
- Result area: Shows success/failure and response snippets after running an action.

---

## Default source and priority

- Optional field default_source in an action (values: clipboard | primary | text).
- Runtime priority:
  1) Shortcut/CLI flags (--from-clipboard/--from-primary/--text) override everything
  2) If no flags are provided, the action's default_source is used (when set)
  3) Otherwise clipboard is used
- UI “Run” uses the Source selector at the top of this page (independent of default_source). Use default_source for consistent shortcut behavior without flags.

## Process (overview)

1) Choose Source (Clipboard, Primary, or Text).
2) Select or create an Action.
3) Edit the Action (Form tab recommended; JSON tab for advanced fields).
4) Save changes (writes to `~/.config/wbridge/actions.json`, with a backup).
5) Run the Action.
6) Inspect results.

---

## Step‑by‑step (quick start)

1) Select Source (top of editor)
   - Clipboard: use current Clipboard content
   - Primary: use current Primary selection
   - Text: type ad‑hoc text into the adjacent entry

2) Add a new Action
   - Click “Add Action”. A new action appears with defaults.
   - Names are auto‑deduplicated.

3) Edit in the Form tab
   - Name: choose a stable, descriptive name (triggers refer to it)
   - Type: `http` or `shell`
   - HTTP fields: Method (GET/POST), URL (http/https)
   - Shell fields: Command (executable), Args (JSON array), Use shell (only if you need shell features)
   - Save (Form): validates and writes to `actions.json` (creates a timestamped backup)

4) (Optional) Adjust advanced fields in the JSON tab
   - Edit raw JSON if you need headers, body, params, or custom fields not shown in the Form
   - Save (JSON): validates and persists with backup

5) Run
   - Click “Run” to execute the selected action with the chosen source
   - See the result area for status and output

---

## Examples

HTTP – POST selected text (with placeholders from settings.ini)
- Goal: Send the current selection as JSON to a local API
- Form (minimum):
  - Type: `http`
  - Method: `POST`
  - URL: `{config.endpoint.local.base_url}{config.endpoint.local.trigger_path}`
- JSON (body via advanced field in JSON tab):
  ```json
  {
    "name": "Post to local API",
    "type": "http",
    "method": "POST",
    "url": "{config.endpoint.local.base_url}{config.endpoint.local.trigger_path}",
    "headers": { "Content-Type": "application/json" },
    "json": { "text": "{text}", "source": "{selection.type}" }
  }
  ```

HTTP – GET with query
- Use URL placeholders directly:
  ```
  {config.endpoint.local.base_url}/search?q={text_url}
  ```

Shell – Uppercase
```json
{
  "name": "Uppercase",
  "type": "shell",
  "command": "tr",
  "args": ["a-z", "A-Z"],
  "use_shell": false
}
```

Shell – URL‑encode via Python
```json
{
  "name": "URL encode (python)",
  "type": "shell",
  "command": "python3",
  "args": ["-c", "import urllib.parse,sys;print(urllib.parse.quote(sys.stdin.read()))"],
  "use_shell": false
}
```

Obsidian – Local REST API token (from [secrets])
- Goal: Append the current selection as plain text to a file in your Obsidian vault via the Local REST API plugin.
- Action JSON (add via the JSON tab):
```json
{
  "name": "Obsidian: Append to Inbox.md",
  "type": "http",
  "method": "POST",
  "url": "http://127.0.0.1:27124/vault/Inbox.md",
  "headers": {
    "Authorization": "Bearer {config.secrets.obsidian_token}",
    "Content-Type": "text/markdown"
  },
  "body_is_text": true
}
```
- Notes on body_is_text:
  - Optional boolean. When true and method is POST and neither `json` nor `data` is set, the raw `{text}` is sent as the request body.
  - Ignored for GET.
  - Mutually exclusive with `json` for POST.
  - If `data` is present, it takes precedence over `body_is_text`.

Tips for placeholders
- `{text}`: raw input text
- `{text_url}`: URL‑encoded input text
- `{selection.type}`: `"clipboard"` or `"primary"`
- `{config.endpoint.<id>.*}`: values from settings.ini
- `{config.secrets.<key>}`: secret values from settings.ini

---

## Validation & persistence

- Validation: The UI validates required structure/type (e.g., Name non‑empty, Args is a JSON array).
- Writeback: Saved to `~/.config/wbridge/actions.json` with a timestamped backup.
- Auto‑reload: If the file changes on disk (edited in a text editor), UI refreshes via file monitors.

---

## Good practices

- Stable names: Triggers reference actions by name; avoid frequent renames.
- Start simple: Begin with GET/POST and `{text}`; add headers/body later as needed.
- Shell safety:
  - Prefer explicit Args over a single shell string.
  - Only enable “Use shell” when you need pipes/globs/expansions and accept the risks.
- Iteration loop:
  - Keep the Status page open to watch logs while testing runs.
  - Use History to quickly re‑apply or swap test values.

---

## Troubleshooting

Run failing
- Check the Status page for logs (requests, errors).
- Confirm the endpoint is reachable (use Endpoints Health in Settings).

Validation failures
- Name must be non‑empty and unique.
- Shell Args must be a JSON array of strings.
- URL must start with `http://` or `https://`.

Unexpected action behavior
- Inspect raw JSON (JSON tab).
- Review command paths and PATH environment; consider using absolute paths.

---

## Glossary & links

- Clipboard: regular copy/paste buffer (Ctrl+C / Ctrl+V)
- Primary Selection: mouse selection buffer (often middle‑click paste)
- Triggers: alias → action mapping for easier invocation
- Shortcuts: GNOME keybindings that run `wbridge` commands

Related pages:
- Triggers: `help/en/triggers.md`
- Settings (Endpoints, Shortcuts, Profiles): `help/en/settings.md`
- History (apply/swap): `help/en/history.md`
- Shortcuts (GNOME custom keybindings): `help/en/shortcuts.md`
- Status (logs): `help/en/status.md`
