# wbridge

Wayland‑friendly selection and shortcut bridge for GNOME desktops. Mark text, press a shortcut, run an action (HTTP or Shell) — without global key grabs.

- GUI entry: `wbridge-app` (GTK4 application: History, Actions, Triggers, Shortcuts, Settings, Status)
- CLI entry: `wbridge` (talks to the running app via Unix domain socket)
- No wl‑clipboard, no hidden headless mode, no tray. GNOME Custom Shortcuts trigger the CLI.

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

## First steps (2 minutes)

1) Open the GUI (`wbridge-app` or `wbridge ui show`).
2) Go to Actions → Add Action.
   - Type: `http`
   - Method: `POST`
   - URL: `http://localhost:8808/ingest`
   - Use `{text}` in your body or parameters if needed (see placeholders below).
   - Save.
3) Go to Triggers → add alias `ingest` → select your new action → Save.
4) Go to Settings → Install GNOME Shortcuts (recommended).
   - Example defaults:
     - Prompt: `<Ctrl><Alt>p`
     - Command: `<Ctrl><Alt>m`
     - Show UI: `<Ctrl><Alt>u`
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
  - HTTP (GET/POST, headers/body). Example placeholder: `{text}`, `{text_url}`, `{selection.type}`.
  - Shell (exec program with args). Use “Use shell” only if you need pipes/globs.
- Triggers: map a short alias (e.g., `translate`) to an action name. Use aliases in CLI/HTTP.
- GNOME Custom Shortcuts: system keybindings that run commands like `wbridge trigger translate --from-clipboard`.
- Profiles: curated presets (actions, triggers, settings patches, shortcuts) you can install.

---

## Examples and ideas

- HTTP
  - POST selected text:
    ```
    POST http://localhost:8808/ingest
    Body: {"text":"{text}","source":"{selection.type}"}
    ```
  - GET with query:
    ```
    GET http://localhost:8808/search?q={text_url}
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

## Profiles (example: “witsy”)

List/show:
```
wbridge profile list
wbridge profile show --name witsy
```

Install:
```
# Dry‑run (preview)
wbridge profile install --name witsy --dry-run

# Install with overwrite/patch and recommended shortcuts
wbridge profile install --name witsy --overwrite-actions --patch-settings --install-shortcuts
```

What profiles can do
- Provide ready‑made actions/triggers.
- Patch integration settings (HTTP trigger).
- Install GNOME shortcuts.  
Use the Settings page → Health check to verify local HTTP availability.

---

## Security & privacy

- Wayland‑friendly: no global key grabs; no key injection; GNOME owns shortcuts.
- Local IPC over Unix domain socket (`0600`) in `$XDG_RUNTIME_DIR`.
- Actions are explicit. HTTP endpoints and Shell commands are under your control.
- Be mindful when enabling “Use shell” or calling external endpoints.

---

## Troubleshooting

- `wbridge` not found in PATH
  - Use pipx with `--system-site-packages`.
  - Ensure `~/.local/bin` is in PATH or use absolute command path in GNOME shortcuts.
- “No module named 'gi'”
  - Install distro packages for GTK4/PyGObject; reinstall via pipx with system site packages.
- HTTP actions disabled
  - Enable the HTTP trigger in Settings; run Health check; watch the Status log.
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
- Shortcuts: manage GNOME keybindings (wbridge scope)
- Settings: integration status; inline edit; health check; profiles; shortcuts/autostart
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
    config.py            # settings.ini + actions.json I/O; atomic writes; validation
    platform.py          # paths; env; app info
    gnome_shortcuts.py   # GNOME keybindings install/update/remove
    autostart.py         # desktop autostart mgmt
    logging_setup.py     # file + console logger
    profiles_manager.py  # profiles (list/show/install)
    profiles/            # built‑in profiles
    help/en/*.md         # per‑page Help content
    assets/style.css     # CSS
```

Design & docs
- Design specification: [DESIGN.md](DESIGN.md)
- Changelog: [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md)
- License: MIT (see [LICENSE](LICENSE))
