# Settings (V2 Configuration Model)

Goal
Manage everything from one place without editing files manually. The Settings page is the single source of truth for:
- Endpoints (HTTP base + paths) under [endpoint.<id>]
- Secrets under [secrets]
- GNOME shortcuts mapping under [gnome.shortcuts] with optional Auto-apply
- Profile installation (merge into settings.ini and actions.json)
- Autostart

All runtime placeholders in actions resolve against settings.ini.

---

What’s on this page (V2)
- Endpoints editor:
  - Table of endpoints (ID | Base URL | Health | Trigger) with Actions: Health, Edit, Delete
  - Add row (ID, Base URL, Health path, Trigger path) with validation
- Shortcuts (Config) editor:
  - Edit [gnome.shortcuts] alias → binding entries
  - Auto-apply toggle ([gnome].manage_shortcuts)
  - Buttons: Save (INI), Revert, Apply now (visible when Auto-apply = OFF), Remove all (GNOME)
- Profiles:
  - Install a curated preset with flags: Overwrite actions, Merge endpoints, Merge secrets, Merge shortcuts, Dry-run
- Autostart:
  - Enable/Disable wbridge autostart
- Basic info:
  - IPC socket path, log file path

---

INI schema (authoritative)
- [endpoint.<id>]
  - base_url (http/https)
  - health_path (default /health)
  - trigger_path (default /trigger)
  - <id> is a slug [a-z0-9_-]+
- [secrets]
  - arbitrary key/value secrets (e.g., obsidian_token)
- [gnome]
  - manage_shortcuts = true|false (default true)
- [gnome.shortcuts]
  - alias = <binding> (e.g., prompt = <Ctrl><Alt>p)

Example settings.ini
```
[endpoint.local]
base_url = http://127.0.0.1:8808
health_path = /health
trigger_path = /trigger

[secrets]
obsidian_token = YOUR_TOKEN_HERE

[gnome]
manage_shortcuts = true

[gnome.shortcuts]
prompt = <Ctrl><Alt>p
command = <Ctrl><Alt>m
ui_show = <Ctrl><Alt>u
```

---

Placeholders in actions
- {config.endpoint.<id>.base_url}, {config.endpoint.<id>.health_path}, {config.endpoint.<id>.trigger_path}
- {config.secrets.<key>}
- Other common placeholders: {text}, {selection.type}

Example usage in an action
```
{config.endpoint.local.base_url}{config.endpoint.local.trigger_path}
```

---

Endpoints editor
- Add/Edit/Delete endpoints deterministically under [endpoint.<id>].
- Validate:
  - base_url must start with http:// or https://
  - health_path and trigger_path must start with /
- Health:
  - Click Health on a row to GET base_url + health_path (2s timeout) and display status.

Shortcuts (Config) editor
- Manage the declarative mapping in settings.ini under [gnome.shortcuts].
- Auto-apply:
  - When ON, saving the INI immediately synchronizes GNOME custom keybindings.
  - When OFF, use Apply now to trigger synchronization.
- Remove all:
  - Removes all GNOME custom keybindings whose suffix starts with wbridge- (INI remains unchanged).

Profiles (install)
- Options:
  - Overwrite actions
  - Merge endpoints (merge [endpoint.*] into settings.ini)
  - Merge secrets (merge [secrets] into settings.ini)
  - Merge shortcuts (merge [gnome.shortcuts] from profile settings and shortcuts.json into settings.ini; no direct dconf writes)
  - Dry-run (preview)
- Result shows added/updated/skipped for actions/triggers and merged/skipped for settings/shortcuts.

Autostart
- Enable or disable a desktop entry so wbridge starts after login.

---

Process (quick start)
1) Add an endpoint in Endpoints:
   - ID local, Base URL http://127.0.0.1:8808, Health /health, Trigger /trigger
   - Validate then Save
2) Configure shortcuts:
   - Add bindings under Shortcuts (Config), toggle Auto-apply as desired
   - Save (INI); if Auto-apply is OFF, click Apply now
3) Install a profile:
   - Choose a profile, Show to inspect
   - Select flags (e.g., Overwrite actions, Merge endpoints/secrets/shortcuts, Dry-run)
   - Install and review the report
4) Enable Autostart if desired

---

Examples

HTTP action using endpoint placeholders
```json
{
  "name": "Trigger via local endpoint",
  "type": "http",
  "method": "POST",
  "url": "{config.endpoint.local.base_url}{config.endpoint.local.trigger_path}",
  "json": { "text": "{text}", "source": "{selection.type}" }
}
```

Obsidian Local REST API token (in [secrets])
- settings.ini:
```
[secrets]
obsidian_token = YOUR_TOKEN_HERE
```
- Action header:
```json
{
  "headers": {
    "Authorization": "Bearer {config.secrets.obsidian_token}",
    "Content-Type": "text/markdown"
  },
  "body_is_text": true
}
```

---

Validation & persistence
- All writes are atomic and create backups where applicable.
- File monitors auto-reload settings/actions in the UI after changes on disk.

Troubleshooting
- Health fails:
  - Verify endpoint Base URL/Health path and that the service is running.
- Shortcuts didn’t change:
  - If Auto-apply is OFF, use Apply now.
  - Confirm wbridge is on PATH or use an absolute command in GNOME keybindings.
- Profile didn’t merge:
  - Use Dry-run to inspect what would change.
  - Ensure profile contains the sections you expect (endpoint.*, secrets, gnome.shortcuts).

Related pages
- Actions: help/en/actions.md
- Shortcuts: help/en/shortcuts.md
- Status (logs): help/en/status.md
- Triggers: help/en/triggers.md
