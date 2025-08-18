# wbridge

Wayland‑friendly selection and shortcut bridge for GNOME desktops, built with GTK4/PyGObject. It tracks clipboard and primary selections, keeps a history, and lets you run configurable actions (HTTP or Shell) via a GUI or CLI – including triggering from GNOME Custom Shortcuts.

- CLI entry point: `wbridge` (talks to the running app via Unix domain socket)
- GUI entry point: `wbridge-app` (GTK4 application: history, actions, triggers, shortcuts, settings, status/log)


## Highlights

- Pure GTK4/GDK – no wl‑clipboard, no hidden headless mode, no tray
- Clipboard and Primary Selection histories with apply/swap
- Actions engine (HTTP or Shell) with placeholders (e.g. `{text}`, `{text_url}`, `{selection.type}`)
- GNOME integration via Custom Shortcuts (no key grabbing), and Autostart desktop entry
- Lightweight IPC: newline‑delimited JSON over Unix domain socket
- Per‑page Help panels (from package resources), i18n‑ready via gettext
- Auto‑reload (debounced) when `settings.ini` or `actions.json` changes


## Quick Start

1) Install system packages (GTK4/PyGObject)
- Debian/Ubuntu:
  - `sudo apt update && sudo apt install -y python3-gi gir1.2-gtk-4.0 gobject-introspection`
- Fedora:
  - `sudo dnf install -y python3-gobject gtk4`
- Arch/Manjaro:
  - `sudo pacman -S --needed python-gobject gtk4`
- openSUSE:
  - `sudo zypper install -y python3-gobject gtk4`

2) Install wbridge (development)
- venv (recommended):
  ```
  python3 -m venv --system-site-packages .venv
  . .venv/bin/activate
  pip install -e ".[http]"   # include [http] if you need HTTP actions
  ```
- Using pipx (global user, with system site packages):
  ```
  pipx install --system-site-packages ".[http]"
  ```

3) Run
- GUI: `wbridge-app` (or from checkout: `PYTHONPATH=src python3 -m wbridge.app`)
- CLI (talks to the running app): `wbridge ui show`


## Usage

- Show the GUI:
  ```
  wbridge ui show
  ```

- History (CLI):
  ```
  wbridge history list --which clipboard --limit 10
  wbridge history apply --which primary --index 1
  wbridge history swap --which clipboard
  ```

- Actions (CLI):
  ```
  # trigger action by alias via triggers map
  wbridge trigger prompt --from-primary

  # run action by name (example)
  wbridge action run --name "Send to Local Trigger: prompt" --from-clipboard
  ```

GUI pages (brief)
- History: current values + lists for clipboard/primary; apply/swap; refresh
- Actions: list + editor (Form/JSON); run/save/duplicate/delete; disabled hint when HTTP integration is off
- Triggers: alias → action mapping editor
- Shortcuts: manage GNOME custom keybindings (wbridge scope editable); audit all (read‑only)
- Settings: integration status; inline edit (enable/base/path); health check; profiles; shortcuts/autostart helpers
- Status: environment info + log tail


## Configuration

User config directory: `~/.config/wbridge/`
- `settings.ini`
- `actions.json`

Notes
- If HTTP actions are used, install the optional extra: `pip install -e ".[http]"`
- When `http_trigger_enabled = false`, the GUI disables Runs and shows a hint


## Profiles & Quickstart (Example: “witsy”)

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

The profile can set up actions/triggers, patch integration settings, and install GNOME shortcuts. Use the Settings page → Health check to verify your local HTTP endpoint.


## GNOME Custom Shortcuts

wbridge doesn’t grab keys; GNOME runs CLI commands for your bindings.

Examples
- Prompt: `wbridge trigger prompt --from-primary`
- Command: `wbridge trigger command --from-clipboard`
- Show UI: `wbridge ui show`

Recommended shortcuts can be installed from the Settings page or programmatically (see `wbridge/gnome_shortcuts.py`). Only wbridge‑managed entries (`wbridge-*`) are editable from the app; foreign entries remain read‑only.


## Troubleshooting

- “wbridge not found in PATH”
  - Install via pipx with `--system-site-packages`
  - Ensure `~/.local/bin` is in your session PATH, or use an absolute command path in the GNOME shortcut
- “No module named 'gi'”
  - Install distro packages (see Quick Start), and use a venv/pipx with `--system-site-packages`
- Starting GUI from checkout
  - `PYTHONPATH=src python3 -m wbridge.app`


## Documentation

- Design Specification (architecture, IPC, modules, testing): see [DESIGN.md](DESIGN.md)
- In‑App Help (per page): `src/wbridge/help/en/{history,actions,triggers,shortcuts,settings,status}.md`

To explore the code structure, see the condensed layout below. For deeper architectural details, consult the Design Spec.


## Project Layout (condensed)

```
src/
  wbridge/
    app.py               # Gtk.Application; IPC; logging; settings/actions load
    ui/
      main_window.py      # StackSidebar/Stack; pages orchestration; CSS; file monitors
      components/
        help_panel.py
      pages/
        history_page.py
        actions_page.py
        triggers_page.py
        shortcuts_page.py
        settings_page.py
        status_page.py
    cli.py               # CLI entry point (wbridge)
    server_ipc.py        # Unix domain socket server
    history.py           # History store and APIs
    actions.py           # Actions (HTTP/Shell), placeholders
    config.py            # settings.ini + actions.json I/O; atomic writes; validation
    platform.py          # paths; env; app info
    gnome_shortcuts.py   # GNOME keybindings install/update/remove
    autostart.py         # desktop autostart mgmt
    logging_setup.py     # file + console logger
    profiles_manager.py  # profiles (list/show/install), merge/backup/patch
    profiles/            # built‑in profiles
    help/en/*.md         # per‑page Help content
    assets/style.css     # CSS
```

Packaging
- `pyproject.toml` includes package data:
  - `"wbridge" = ["help/**/*", "assets/**/*"]`
  - `"wbridge.profiles" = ["**/*"]`


## Changelog

See [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) for dated entries and history.


## License

MIT (see [LICENSE](LICENSE)).
