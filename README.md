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
  or bring the window to the front (if already running):
  ```bash
  wbridge ui show
  ```
  Note: This does not start the app and, due to Wayland focus rules, may not always take focus.
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
- Via UI: Settings → Profiles → select “obsidian-local-rest” → Install
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
- With the action’s default source (primary) you can run without flags:
  ```bash
  wbridge trigger obsidian.append
  ```
- Use current Primary Selection explicitly:
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

Source priority
- Shortcut/CLI flags (`--from-clipboard`, `--from-primary`, `--text`) override everything.
- If no flags are provided, the action’s `default_source` is used (when set).
- Otherwise, Clipboard is used.

---

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
