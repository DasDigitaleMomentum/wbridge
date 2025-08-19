# Settings

Problem & Goal
You want to configure integration once and manage profiles, GNOME shortcuts, and autostart from a single place — without editing files manually. 
The Settings page gives you status, inline edit, quick installers, and a health check.

What’s on this page
- Integration Status: live view of HTTP trigger settings, IPC socket, and log path
- Inline Edit: enable/disable HTTP trigger, Base URL, Trigger Path
- Profiles: install curated presets (actions, triggers, settings patches, shortcuts)
- GNOME Shortcuts: install or remove recommended keybindings
- Autostart: start wbridge automatically in your session
- Result messages: success/errors for each operation

---

## Key terms

- HTTP trigger: Optional backend that lets other apps invoke `wbridge` via HTTP (e.g., `POST /trigger`). You control Base URL and paths.
- Base URL: The host:port of your HTTP server (e.g., `http://localhost:8808`).
- Trigger Path: The request path used for invocations (default `/trigger`).
- Health check: A GET to `/health` (or configured path) to verify the backend is reachable.
- IPC socket: Local Unix domain socket where the GUI app accepts CLI requests.
- Profile: A curated package that can write actions/triggers, patch settings, and install GNOME shortcuts.
- GNOME shortcuts: Custom keybindings that execute `wbridge ...` commands (no global key grabs).

---

## Process (overview)

1) Review Integration Status (HTTP trigger on/off, Base URL/Path, IPC socket, log file).
2) Edit settings inline if needed and Save (validation applies).
3) Use Profiles to install a preset (dry‑run recommended first).
4) Install recommended GNOME shortcuts.
5) Enable Autostart to keep wbridge ready after login.
6) Use the Health check to verify your HTTP integration.

---

## Step‑by‑step (quick start)

Integration (HTTP trigger)
1) Open Settings → Integration.
2) Toggle “Enable HTTP trigger” on if you plan to call wbridge from other apps/services.
3) Set “Base URL”, e.g., `http://localhost:8808`.
4) Set “Trigger Path”, e.g., `/trigger`.
5) Click Save. Validation ensures:
   - Base URL starts with `http://` or `https://`
   - Trigger Path starts with `/`
6) Click Health check to verify `Base URL + /health` (or your configured path).

Profiles
1) Choose a profile (e.g., `witsy`) from the dropdown.
2) Click Show to see a compact summary.
3) Select options:
   - Overwrite actions (write profile actions to `~/.config/wbridge/actions.json`)
   - Patch settings (non‑destructive changes to `~/.config/wbridge/settings.ini`)
   - Install shortcuts (install profile keybindings)
   - Dry‑run (preview changes; recommended first)
4) Click Install. The page refreshes status after completion.

GNOME Shortcuts
1) Click “Install GNOME Shortcuts”.
   - Priority order:
     1) If `[gnome]` bindings exist in your `settings.ini`, install those.
     2) Else, if a profile is selected and provides `shortcuts.json`, install those.
     3) Else, install the default recommended set:
        - Prompt: `<Ctrl><Alt>p`
        - Command: `<Ctrl><Alt>m`
        - Show UI: `<Ctrl><Alt>u`
2) Later, use the Shortcuts page to edit bindings, audit conflicts, or remove entries.

Autostart
1) Click “Enable autostart” to create a desktop entry in your session (visible app on login).
2) Use “Disable autostart” to remove it.

---

## Examples

Health check
- After saving HTTP settings, run Health check. Expected: a success message if your backend replies at `GET /health`.
- If it fails, verify the Base URL and server availability, then check the Status page (Log tail).

Profile install (typical)
- Select “witsy”, enable:
  - Overwrite actions
  - Patch settings
  - Install shortcuts
  - Dry‑run first
- Click Install; review dry‑run; then Install again without Dry‑run to apply.

PATH hint (shortcuts)
- If `wbridge` is not in PATH, GNOME shortcuts won’t run as expected.
- Solutions:
  - Install via pipx (`pipx install --system-site-packages ...`)
  - Ensure `~/.local/bin` is in PATH
  - Or set an absolute path in the shortcut command

---

## Validation & persistence

- Inline Edit Save:
  - Validates Base URL scheme (`http://` or `https://`) and Trigger Path (`/` prefix)
  - Writes atomically to `~/.config/wbridge/settings.ini`
- Profiles:
  - `Overwrite actions` writes to `~/.config/wbridge/actions.json` (backup created)
  - `Patch settings` updates `~/.config/wbridge/settings.ini` non‑destructively
  - `Install shortcuts` writes GNOME bindings via `Gio.Settings`
- Auto‑reload:
  - File monitors refresh the UI when `settings.ini` or `actions.json` change on disk (debounced)

---

## Good practices

- Use Dry‑run for profiles before applying changes.
- Keep action names stable; triggers and shortcuts often rely on names.
- Store HTTP endpoints on localhost for local workflows; secure external endpoints appropriately.
- Keep the Status page open while testing to correlate actions with logs.

---

## Troubleshooting

Health check fails
- Verify Base URL/Trigger Path, ensure backend is running.
- Check the Status page (log tail) for connection/timeouts and details.

Shortcuts don’t work
- Confirm `wbridge` is on PATH or use an absolute command path.
- Check for binding conflicts on the Shortcuts page.
- If GNOME dconf writes are delayed, try reloading the page or restarting GNOME Shell/session.

Actions/triggers don’t update
- Wait briefly for file monitor debounce or click “Reload Settings” / “Reload actions”.
- Ensure `actions.json` is valid JSON.

Autostart didn’t enable
- Check the result message.
- Inspect your session’s autostart directory for the created entry.

---

## Glossary & links

- HTTP trigger: optional integration to call `wbridge` via HTTP
- Profiles: curated presets that set up actions/triggers/settings/shortcuts
- Shortcuts: GNOME keybindings that run `wbridge` commands
- Autostart: start wbridge on login

Related pages
- Actions: `help/en/actions.md`
- Triggers: `help/en/triggers.md`
- Shortcuts: `help/en/shortcuts.md`
- Status (logs): `help/en/status.md`
