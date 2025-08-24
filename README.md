# wbridge

Wayland‑friendly selection and shortcut bridge for GNOME. Mark text. Press a shortcut. Run an action (HTTP or Shell) — without global key grabs.

- Benefits
  - Wayland-safe: no global key grabs, no key injection, no wl‑clipboard dependency
  - Native GNOME: Custom Shortcuts invoke the CLI; the GTK4 app does selection + actions
  - Fast workflows: one shortcut from selection to result, visible in a native UI
  - Open and configurable: simple INI/JSON with powerful placeholders and profiles

- Entries
  - GUI: `wbridge-app` (GTK4 application: History, Actions, Triggers, Shortcuts, Settings, Status)
  - CLI: `wbridge` (talks to the running app via Unix domain socket)

---

## Why wbridge? What problems does it solve?

Wayland limits global hotkeys and key injection. Power users still want: “Take my current selection, send it to a tool, and get the result back — quickly.”

wbridge provides a robust, Wayland‑friendly path:
- GNOME manages global keybindings (Custom Shortcuts).
- Keybindings execute `wbridge ...` with parameters.
- A running GTK4 app reads your Clipboard or Primary Selection and runs a configured action (HTTP or Shell) with placeholders.
- You keep full control and visibility in a native GTK UI.

Typical uses
- Text utilities: uppercase/lowercase, URL‑encode, JSON/YAML/CSV formatting
- Local microservices: send a prompt to a local LLM endpoint, query a knowledge base
- Developer tooling: open in editor, run grep/ag/rg, call scripts with selected text
- Automation: send to task manager, browser search, custom data ingests

---

## Quick start (60–120 seconds)

1) Install system packages (PyGObject/GTK4 from your distro)
- Debian/Ubuntu:
  ```bash
  sudo apt update && sudo apt install -y python3-gi gir1.2-gtk-4.0 gobject-introspection
  ```
- Fedora:
  ```bash
  sudo dnf install -y python3-gobject gtk4
  ```
- Arch/Manjaro:
  ```bash
  sudo pacman -S --needed python-gobject gtk4
  ```
- openSUSE:
  ```bash
  sudo zypper install -y python3-gobject gtk4
  ```

2) Install wbridge (pipx, recommended)
- From GitHub (works even before a PyPI release):
  ```bash
  pipx install --system-site-packages "git+https://github.com/DasDigitaleMomentum/wbridge.git#egg=wbridge[http]"
  ```
  Notes:
  - `--system-site-packages` is required so pipx can see the distro’s GTK bindings.
  - The `[http]` extra enables HTTP actions.

3) Launch and verify
- Start the app:
  ```bash
  wbridge-app
  ```
  or:
  ```bash
  wbridge ui show
  ```
- Quick CLI checks:
  ```bash
  wbridge history list --which clipboard --limit 3
  wbridge selection get --which primary
  ```

Update / Uninstall
- Update: `pipx upgrade wbridge`
- Uninstall: `pipx uninstall wbridge`

Troubleshooting install
- “No module named 'gi'”: install the distro packages above and ensure `--system-site-packages` is used.
- `wbridge` not found: ensure `~/.local/bin` is in PATH (pipx installs here).

---

## Spotlight: Obsidian in 2 minutes

Goal: Append your current selection (Primary Selection or literal text) into `Inbox.md` via the Obsidian Local REST API.

Prerequisites
- Obsidian Local REST API is running
- An API token (we’ll store it in `settings.ini`)

Step 1 — Inspect and install the profile
```bash
# See what will be installed:
wbridge profile install --name obsidian-local-rest --merge-shortcuts --dry-run

# Install profile artifacts (actions + GNOME shortcuts mapping into settings.ini)
wbridge profile install --name obsidian-local-rest --merge-shortcuts
```
What this does:
- Adds an action “Obsidian: Append to Inbox.md”
- Adds a trigger alias `obsidian.append`
- Suggests a shortcut (e.g. `<Ctrl><Alt>o`) mapped to:
  ```
  wbridge trigger obsidian.append --from-primary
  ```

Step 2 — Add endpoint + token to your settings.ini
```bash
# Get the path of your settings.ini:
wbridge config show-paths --json
# Open the "settings" path shown above and add/edit:
```

Add the following to `~/.config/wbridge/settings.ini`:
```
[endpoint.obsidian]
base_url = http://127.0.0.1:27123
health_path = /health
trigger_path = /trigger

[secrets]
obsidian_token = YOUR_TOKEN
```

Step 3 — Run it
- Use current Primary Selection (recommended first test):
  ```bash
  wbridge trigger obsidian.append --from-primary
  ```
- Or send literal text:
  ```bash
  wbridge trigger obsidian.append --text "Quick note via wbridge"
  ```

Useful shell snippet (timestamped note):
```bash
wbridge trigger obsidian.append --text "$(printf 'Note %s: %s' "$(date -Iseconds)" "Captured via wbridge")"
```

Shortcuts sync
- Shortcuts are sourced from `[gnome.shortcuts]` in `settings.ini`.
- In the app under Settings → Shortcuts (Config), enable “Auto-apply” for immediate sync or press “Apply now”.

---

## Creative Shortcuts: Recipes

Real-world shortcut ideas that combine your current selection with a shell command. Add the actions via the GUI (Actions → Add) or merge the JSON snippet into ~/.config/wbridge/actions.json. Then bind a GNOME shortcut to the shown trigger.

Recipe: Journal entry (Markdown) — append selection
- Idea: Take the current selection, prefix it with an ISO timestamp, and append it as a list item to ~/Documents/Journal.md.
- Action (Shell) reading selection from stdin and appending to a file:

```json
{
  "actions": [
    {
      "name": "Journal: Append",
      "type": "shell",
      "command": "sh",
      "args": [
        "-lc",
        "printf '* %s — %s\\n' \"$(date -Iseconds)\" \"$(cat)\" >> \"$HOME/Documents/Journal.md\""
      ],
      "use_shell": true
    }
  ],
  "triggers": {
    "journal.append": "Journal: Append"
  }
}
```

Notes
- The file is created automatically if it does not exist. Adjust the path if needed.
- Selection (including newlines) is safely read from stdin via `$(cat)`.

Trigger and shortcut
- Suggested GNOME binding: `<Ctrl><Alt>j`
- Command the binding should run:
  ```bash
  wbridge trigger journal.append --from-primary
  ```
  Use `--from-clipboard` if you prefer the clipboard buffer.

Usage
1) Select text in any app (Primary Selection).
2) Press your shortcut.
3) A new line is appended to `~/Documents/Journal.md`, for example:
   `* 2025-08-25T00:41:27+02:00 — Your selected text`

Mini recipe: Scratchpad window for selection
- Action (Shell):
  ```json
  {
    "name": "Scratchpad: Open",
    "type": "shell",
    "command": "sh",
    "args": ["-lc", "f=\"$(mktemp /tmp/wbridge-XXXX.md)\"; cat > \"$f\"; xdg-open \"$f\" >/dev/null 2>&1 &"],
    "use_shell": true
  }
  ```
- Trigger and run:
  ```bash
  wbridge trigger scratchpad.open --from-primary
  ```

Mini recipe: Web search for selection (no extra packages)
- Action (Shell):
  ```json
  {
    "name": "Search: Web",
    "type": "shell",
    "command": "sh",
    "args": ["-lc", "python3 -c 'import sys, urllib.parse, webbrowser; webbrowser.open(\"https://duckduckgo.com/?q=\"+urllib.parse.quote(sys.stdin.read()))'"],
    "use_shell": true
  }
  ```
- Trigger and run:
  ```bash
  wbridge trigger search.web --from-primary
  ```

## More runnable examples (CLI)

Show UI:
```bash
wbridge ui show
```

Get/set selections:
```bash
wbridge selection get --which clipboard
wbridge selection set --which clipboard --text "Hello from wbridge"
wbridge history list --which primary --limit 5
```

Triggers and actions:
- Run a trigger alias using the current clipboard (default):
  ```bash
  wbridge trigger prompt
  ```
- Run a named action with literal text:
  ```bash
  wbridge trigger --name "Obsidian: Append to Inbox.md" --text "Hello Obsidian"
  ```

---

## Configuration (V2) — compact

All configuration lives in `~/.config/wbridge/settings.ini`. Actions and triggers live in `~/.config/wbridge/actions.json`.

Example `settings.ini`:
```
[general]
history_max = 50
poll_interval_ms = 300

[endpoint.local]
base_url = http://127.0.0.1:8808
health_path = /health
trigger_path = /trigger

[secrets]
obsidian_token = YOUR_TOKEN

[gnome]
manage_shortcuts = true

[gnome.shortcuts]
prompt  = <Ctrl><Alt>p
command = <Ctrl><Alt>m
ui_show = <Ctrl><Alt>u
```

Placeholders you can use in actions:
- `{text}`, `{text_url}`, `{selection.type}`
- `{config.endpoint.<id>.*}` e.g. `{config.endpoint.local.base_url}`
- `{config.secrets.<key>}` e.g. `{config.secrets.obsidian_token}`

Shortcuts sync (deterministic)
- Source of truth: `[gnome.shortcuts]` mapping in `settings.ini`.
- App can Auto-apply on save or “Apply now” on demand.

---

## How it works at a glance

1) Select text (Clipboard via Ctrl+C or Primary Selection via mouse).
2) Press a GNOME shortcut (e.g., Ctrl+Alt+P) that runs a `wbridge` CLI command.
3) The app reads the selection and executes the configured action (HTTP or Shell).  
   You see results in the UI (and optionally re‑apply to the Clipboard/Primary).

Flow
```
[GNOME Shortcut] → runs → [wbridge CLI] → IPC → [wbridge GTK App]
                                       → reads selection → runs action → logs/result
```

---

## Profiles

List/show:
```bash
wbridge profile list
wbridge profile show --name witsy
```

Install (merge flags):
```bash
# Dry‑run (preview)
wbridge profile install --name witsy --dry-run

# Merge into settings.ini/actions.json
wbridge profile install --name witsy \
  --overwrite-actions \
  --merge-endpoints \
  --merge-secrets \
  --merge-shortcuts
```

Notes
- Profiles never ship personal tokens. Put tokens in `[secrets]` and reference them via `{config.secrets.<key>}`.
- No direct dconf write during profile install; GNOME shortcuts are synced from INI via the app.

---

## Security & privacy

- Wayland‑friendly: no global key grabs; no key injection; GNOME owns shortcuts.
- Local IPC over Unix domain socket (`0600`) in `$XDG_RUNTIME_DIR`.
- Actions are explicit. HTTP endpoints and Shell commands are under your control.
- Secrets live in `~/.config/wbridge/settings.ini` under `[secrets]` (user‑managed).

---

## Troubleshooting

- Endpoint not reachable
  - Settings → Endpoints: use “Health” to test `base_url + health_path` (2 s timeout).
  - Check the Status page for logs (timeouts, connection errors).

- Shortcuts didn’t sync
  - If Auto‑apply is OFF, use “Apply now” in Settings → Shortcuts (Config).
  - Ensure `wbridge` is on PATH or use an absolute command path in GNOME shortcuts.

- `wbridge` not found in PATH
  - Use pipx with `--system-site-packages`.
  - Ensure `~/.local/bin` is in PATH or use an absolute command in GNOME Shortcuts.

Start GUI from a source checkout:
```bash
PYTHONPATH=src python3 -m wbridge.app
```

---

## In‑App Help

Each GUI page includes contextual help:
- History: dual buffers, apply/swap, refresh
- Actions: master/detail editor, run/save/duplicate/delete, placeholders
- Triggers: alias → action mapping
- Shortcuts: audit INI vs Installed, Apply now, Remove all
- Settings: Endpoints, Secrets, Shortcuts (INI), Profiles, Autostart
- Status: environment info + log tail

Sources: `src/wbridge/help/en/{history,actions,triggers,shortcuts,settings,status}.md`

---

## For developers

System packages as above.

Dev install:
```bash
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -e ".[http]"
```

Run:
```bash
wbridge-app
# or
PYTHONPATH=src python3 -m wbridge.app
```

Project layout (condensed)
```
src/
  wbridge/
    app.py               # Gtk.Application; IPC; logging; settings/actions load
    ui/
      main_window.py
      components/
        help_panel.py
        cta_bar.py
        markdown.py
      pages/
        history_page.py
        actions_page.py
        triggers_page.py
        shortcuts_page.py
        settings_page.py
        status_page.py
    cli.py               # CLI entry (wbridge)
    server_ipc.py        # Unix domain socket server (NDJSON)
    history.py           # History store and APIs
    actions.py           # Actions (HTTP/Shell), placeholders
    config.py            # settings.ini + actions.json I/O + V2 helpers (endpoints/secrets/shortcuts)
    platform.py          # paths; env; app info
    gnome_shortcuts.py   # GNOME keybindings install/update/remove + V2 sync
    autostart.py         # desktop autostart mgmt
    logging_setup.py     # file + console logger
    profiles_manager.py  # profiles (list/show/install) with merge_* flags
    profiles/            # built‑in profiles
    help/en/*.md         # per‑page Help content
    assets/style.css     # CSS
```

---

## Design & docs

- Design specification (V2): [docs/DESIGN.md](docs/DESIGN.md)
- Changelog: [docs/IMPLEMENTATION_LOG.md](docs/IMPLEMENTATION_LOG.md)
- License: MIT (see [LICENSE](LICENSE))
