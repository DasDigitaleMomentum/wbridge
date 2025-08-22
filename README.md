# wbridge

Wayland‑friendly selection and shortcut bridge for GNOME desktops. Mark text, press a shortcut, run an action (HTTP or Shell) — without global key grabs.

- GUI entry: `wbridge-app` (GTK4 application: History, Actions, Triggers, Shortcuts, Settings, Status)
- CLI entry: `wbridge` (talks to the running app via Unix domain socket)
- No wl‑clipboard, no hidden headless mode, no tray. GNOME Custom Shortcuts trigger the CLI.

Configuration model (V2)
- settings.ini is the Single Source of Truth for Endpoints, Secrets, and GNOME Shortcuts (hard switch; no legacy `[integration.*]`).
- Actions use placeholders like `{config.endpoint.<id>.*}` and `{config.secrets.<key>}`.
- Shortcuts sync deterministically from `[gnome.shortcuts]` (Auto‑apply or Apply now).

---

## What problem does wbridge solve?

On Wayland, apps cannot reliably grab global shortcuts or inject keystrokes. Yet power users want: “Take my current selection, send it to a tool, and get a result back — quickly.”  
wbridge provides a safe, robust path:

- GNOME manages global keybindings.
- Keybindings execute `wbridge ...` with parameters.
- A running GTK4 app reads your current Clipboard or Primary Selection, then runs a configurable action (HTTP or Shell) with placeholders.
- You keep full control and visibility in a native GTK UI.

Typical uses
- Text utilities: uppercase/lowercase, URL‑encode, JSON/YAML/CSV formatting
- Local microservices: send a prompt to a local LLM endpoint, query a knowledge base
- Developer tooling: open in editor, run grep/ag/rg, call scripts with selected text
- Automation: send to task manager, browser search, custom data ingests

---

## How it works in 30 seconds

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

## Install (for users)

1) Install system packages (PyGObject/GTK4 from your distro)
- Debian/Ubuntu:
  - `sudo apt update && sudo apt install -y python3-gi gir1.2-gtk-4.0 gobject-introspection`
- Fedora:
  - `sudo dnf install -y python3-gobject gtk4`
- Arch/Manjaro:
  - `sudo pacman -S --needed python-gobject gtk4`
- openSUSE:
  - `sudo zypper install -y python3-gobject gtk4`

2) Install wbridge (pipx, recommended)
- From GitHub (works even before a PyPI release):
  ```
  pipx install --system-site-packages "git+https://github.com/DasDigitaleMomentum/wbridge.git#egg=wbridge[http]"
  ```
  Notes:
  - `--system-site-packages` is required so pipx can see the distro’s GTK bindings.
  - The `[http]` extra enables HTTP actions.

3) Launch and verify
- Start the app:
  ```
  wbridge-app
  ```
  or
  ```
  wbridge ui show
  ```
- Quick CLI checks:
  ```
  wbridge history list --which clipboard --limit 3
  wbridge selection get --which primary
  ```

Uninstall / Update
- Update: `pipx upgrade wbridge`
- Uninstall: `pipx uninstall wbridge`

Troubleshooting install
- “No module named 'gi'”: install the distro packages above and ensure `--system-site-packages` is used.
- `wbridge` not found: ensure `~/.local/bin` is in PATH (pipx installs here).

---

## Quick config (V2)

All configuration lives in `~/.config/wbridge/settings.ini`.

Example:
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

- Endpoints: define base URL and paths; use per-row “Health” in Settings → Endpoints to probe `base_url + health_path` (2 s timeout).
- Secrets: user‑managed key/value store. Reference via `{config.secrets.<key>}` in actions.
- GNOME Shortcuts: edit `[gnome.shortcuts]` mapping in Settings; Auto‑apply toggles immediate sync; otherwise click “Apply now”.

Placeholders in actions:
- `{config.endpoint.local.base_url}`, `{config.endpoint.local.trigger_path}`, …
- `{config.secrets.obsidian_token}`
- plus common `{text}`, `{text_url}`, `{selection.type}`.

---

## First steps (2 minutes)

1) Open the GUI (`wbridge-app` or `wbridge ui show`).
2) Go to Actions → Add Action.
   - Type: `http`
   - Method: `POST`
   - URL: `{config.endpoint.local.base_url}{config.endpoint.local.trigger_path}`
   - Use `{text}` in your body or parameters if needed (see placeholders below).
   - Save.
3) Go to Triggers → add alias `ingest` → select your new action → Save.
4) Go to Settings:
   - Endpoints: add `local` if needed, probe Health.
   - Shortcuts (Config): set bindings; Auto‑apply ON to sync or OFF + “Apply now”.
5) Select some text in any app, then run:
   ```
   wbridge trigger ingest --from-primary
   ```
   or press your shortcut that invokes a trigger.

Tip: Use the Status page to watch logs while testing.

---

## Core concepts (glossary)

- Clipboard vs Primary Selection
  - Clipboard: regular copy/paste buffer (Ctrl+C / Ctrl+V).
  - Primary Selection: mouse‑selection buffer, often pasted via middle‑click. You can keep two parallel buffers.
- Actions: reusable units you run on the current selection. Types:
  - HTTP (GET/POST, headers/body). Example placeholders: `{text}`, `{text_url}`, `{selection.type}`, `{config.endpoint.<id>.*}`, `{config.secrets.*}`.
  - Shell (exec program with args). Use “Use shell” only if you need pipes/globs.
- Triggers: map a short alias (e.g., `translate`) to an action name. Use aliases in CLI/HTTP.
- GNOME Custom Shortcuts: system keybindings that run commands like `wbridge trigger translate --from-clipboard`.
- Profiles: curated presets (actions, triggers, optional settings patches, shortcuts) you can merge into your config.

---

## Examples and ideas

- HTTP
  - POST selected text:
    ```
    POST {config.endpoint.local.base_url}{config.endpoint.local.trigger_path}
    Body: {"text":"{text}","source":"{selection.type}"}
    ```
  - GET with query:
    ```
    GET {config.endpoint.local.base_url}/search?q={text_url}
    ```
- Shell
  - Uppercase:
    ```
    command: tr
    args: ["a-z","A-Z"]
    ```
  - URL‑encode via Python:
    ```
    command: python3
    args: ["-c","import urllib.parse,sys;print(urllib.parse.quote(sys.stdin.read()))"]
    use_shell: false
    ```
- Workflows
  - “Send to local LLM prompt server; return summary to Clipboard”
  - “Look up selected code in docs; open browser”
  - “Normalize JSON; copy result back to Clipboard”

---

## Profiles (example: “witsy” / “obsidian-local-rest”)

List/show:
```
wbridge profile list
wbridge profile show --name witsy
```

Install (V2 merge flags):
```
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
- Profiles do not ship your personal tokens. Put tokens in `[secrets]` and reference them via `{config.secrets.<key>}`.
- There is no direct dconf write in profile install; GNOME shortcuts are synced from INI via the app.

---

## Security & privacy

- Wayland‑friendly: no global key grabs; no key injection; GNOME owns shortcuts.
- Local IPC over Unix domain socket (`0600`) in `$XDG_RUNTIME_DIR`.
- Actions are explicit. HTTP endpoints and Shell commands are under your control.
- Be mindful when enabling “Use shell” or calling external endpoints.
- Secrets live in `~/.config/wbridge/settings.ini` under `[secrets]` (user‑managed).

---

## Troubleshooting

- Endpoint not reachable
  - Settings → Endpoints: use “Health” on the row to test `base_url + health_path`.
  - Check the Status page for logs (timeouts, connection errors).

- Shortcuts didn’t sync
  - If Auto‑apply is OFF, use “Apply now” in Settings → Shortcuts (Config).
  - Ensure `wbridge` is on PATH or use an absolute command path in GNOME shortcuts.

- `wbridge` not found in PATH
  - Use pipx with `--system-site-packages`.
  - Ensure `~/.local/bin` is in PATH or use an absolute command in GNOME Shortcuts.

- Start GUI from a source checkout
  ```
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

- System packages as above.
- Dev install:
  ```
  python3 -m venv --system-site-packages .venv
  . .venv/bin/activate
  pip install -e ".[http]"
  ```
- Run:
  ```
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

Design & docs
- Design specification (V2): [DESIGN.md](DESIGN.md)
- Changelog: [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md)
- License: MIT (see [LICENSE](LICENSE))
