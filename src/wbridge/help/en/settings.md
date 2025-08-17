# Settings

Configure integration, profiles, GNOME shortcuts, and autostart from a single page. All controls apply at user scope.

The page is divided into sections:
- Integration Status and Inline Edit
- Profiles (install curated presets)
- GNOME Shortcuts (install/remove recommended bindings)
- Autostart controls
- Result messages

---

## Integration

The HTTP trigger integration enables remote invocation of actions (e.g., from scripts or other apps).

### Status
- http_trigger_enabled: whether the HTTP trigger backend is enabled
- Base URL: e.g., `http://localhost:8808`
- Trigger Path: e.g., `/trigger`
- IPC Socket: path to the local IPC socket used by the app
- Log file: `~/.local/state/wbridge/bridge.log`

These values reflect the current on-disk configuration and environment.

### Edit (inline)

- Enable HTTP trigger: turn the integration on or off
- Base URL (http/https): host and port of the HTTP server
- Trigger Path (/trigger): relative path appended to the Base URL

Buttons:
- Save: Validate and persist your changes. Validation ensures:
  - Base URL starts with `http://` or `https://`
  - Trigger Path starts with `/`
- Discard: Revert the edit fields to the current on-disk settings
- Reload Settings: Reload from disk and refresh all dependent UI
- Health check: Perform a quick GET to `Base URL + /health` (or a configured health path) to verify availability

Notes:
- Changes are written atomically to your settings.
- The UI reloads the status after saving to keep the page consistent.

---

## Profiles

Profiles provide ready-to-use sets of actions, triggers, settings patches, and shortcuts for specific workflows.

Controls:
- Profile: choose an available built-in profile from the dropdown
- Show: display a compact summary (counts for actions/triggers/shortcuts and metadata)
- Options:
  - Overwrite actions: write profile actions into `~/.config/wbridge/actions.json` (existing entries may be replaced)
  - Patch settings: apply non-destructive changes to `~/.config/wbridge/settings.ini`
  - Install shortcuts: install profile-provided GNOME custom keybindings (wbridge scope)
  - Dry-run: preview changes without writing to disk
- Install: apply the selected profile with your chosen options

After installation, the page reloads settings and refreshes dependent UI.

---

## GNOME Shortcuts

Install or remove recommended wbridge custom keybindings (managed under the `wbridge-` scope). These are convenient defaults that you can later audit and edit on the Shortcuts page.

Buttons:
- Install GNOME Shortcuts: priority order
  1) If `[gnome]` bindings are present in `settings.ini`, install those
  2) Else, if a profile is selected and provides `shortcuts.json`, install those
  3) Else, install the default recommended set:
     - Prompt: `<Ctrl><Alt>p`
     - Command: `<Ctrl><Alt>m`
     - Show UI: `<Ctrl><Alt>u`
- Remove GNOME Shortcuts:
  - Remove the default recommended set
  - If a profile is selected, also try removing its installed shortcuts

PATH hint:
- If the `wbridge` executable is not found in your PATH, GNOME shortcuts may fail to run
- Solutions: install via `pipx install wbridge` or `pip install --user wbridge`, or specify an absolute path in the shortcut command

---

## Autostart

Enable wbridge autostart in your session so the background services are always available.

Buttons:
- Enable autostart
- Disable autostart

The result area shows success/failure messages.

---

## File monitors and live reload

- The UI monitors `~/.config/wbridge/actions.json` and `settings.ini`
- When these files change on disk (e.g., edited externally), the app reloads data and refreshes dependent views (Actions, Triggers, Integration Status)
- Debounce is applied to avoid excessive reloads

---

## Troubleshooting

- Health check fails:
  - Verify Base URL and Trigger Path
  - Ensure the backend process is running and reachable
  - Check the Status page log tail for details

- Shortcuts not working:
  - Confirm `wbridge` is on PATH or use an absolute command path
  - Check for binding conflicts on the Shortcuts page
  - Restart GNOME Shell/session if dconf writes were delayed

- Actions/triggers don’t reflect edits:
  - Wait briefly for file monitor debounce or press Reload Settings / Reload actions
  - Ensure the JSON structure in `actions.json` is valid

- Autostart didn’t enable:
  - Check the message for errors
  - Inspect your session autostart directory for the created entry
