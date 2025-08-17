# wbridge

General‑purpose selection and shortcut bridge for Wayland desktops (GNOME‑first) built with GTK4/PyGObject. One repository, one Python package, two entry points:
- `wbridge` (CLI): Talks to the running app via IPC (Unix domain socket).
- `wbridge-app` (GUI): GTK4 application providing selection history, actions, triggers, shortcuts, settings, and status/log.

Design guardrails:
- Left‑side navigation: Gtk.StackSidebar + Gtk.Stack (no Notebook tabs)
- Help panel on every page (collapsible), content loaded from resource files (English by default)
- i18n prepared via gettext (domain `wbridge`, fallback to English)
- GNOME shortcuts: only wbridge‑managed entries editable (prefix `wbridge-`); foreign entries read‑only


## Table of Contents

- [Features](#features)
- [UI Overview](#ui-overview)
- [Requirements](#requirements)
- [Install (development)](#install-development)
- [Running](#running)
- [Pages in Detail](#pages-in-detail)
  - [History](#history)
  - [Actions (Master‑Detail)](#actions-master-detail)
  - [Triggers](#triggers)
  - [Shortcuts](#shortcuts)
  - [Settings](#settings)
  - [Status & Log](#status--log)
- [Help & i18n](#help--i18n)
- [GNOME custom shortcuts (concept)](#gnome-custom-shortcuts-concept)
- [Configuration](#configuration)
- [Profiles & Witsy Quickstart](#profiles--witsy-quickstart)
- [CLI overview](#cli-overview)
- [CSS & Theming](#css--theming)
- [File Monitors & Auto‑Reload](#file-monitors--auto-reload)
- [Troubleshooting](#troubleshooting)
- [Project Layout](#project-layout)
- [Changelog / Implementation Log](#changelog--implementation-log)
- [License](#license)


## Features

- Wayland‑friendly selection monitoring (GTK4/GDK only; no wl‑clipboard)
- Dual history rings: Clipboard and Primary Selection
  - Apply a history item back to Clipboard or Primary
  - Swap the latest two items (toggle flow)
- Actions engine (HTTP or Shell) with placeholders like `{text}` / `{text_url}`
- Triggers map aliases (e.g. `prompt`) to actions
- IPC server (Unix domain socket) + CLI client (`wbridge`)
- GNOME integration via Custom Shortcuts (no key grabbing)
- Autostart via desktop entry
- Optional local HTTP trigger integration via config
- Per‑page collapsible Help panels (resource files)
- i18n setup (gettext; English default; fallback safe)
- CSS loaded from resources for subtle UI polish


## UI Overview

Navigation uses a left‑side Gtk.StackSidebar + Gtk.Stack (replaces tabs). Pages:
- History (Clipboard / Primary)
- Actions (Master‑Detail editor: list on the left, shared editor on the right)
- Triggers (Alias → Action mapping)
- Shortcuts (GNOME Custom Keybindings)
- Settings (Integration, Profiles, Autostart, PATH hints)
- Status & Log (Environment info + log tail)

Each page provides a collapsible “Help” panel with detailed guidance (English by default).


## Requirements

- Linux Wayland session (GNOME primary target)
- Python 3.10+
- System packages (names vary by distribution):
  - Debian/Ubuntu: `sudo apt update && sudo apt install -y python3-gi gir1.2-gtk-4.0 gobject-introspection`
  - Fedora: `sudo dnf install -y python3-gobject gtk4`
  - Arch/Manjaro: `sudo pacman -S --needed python-gobject gtk4`
  - openSUSE: `sudo zypper install -y python3-gobject gtk4`
- Optional extra for HTTP actions: `requests` (install via `.[http]`)

Notes
- Install GTK/PyGObject from your distro packages (do not try to build via pip).
- The Python you use must be able to `import gi`; virtualenvs typically need `--system-site-packages`.


## Install (development)

Using pip (system or venv):

```bash
# venv (recommended)
python3 -m venv --system-site-packages .venv
. .venv/bin/activate

# editable install; add [http] if you need HTTP actions
pip install -e ".[http]"
# or:
# pip install -e .
```

Using uv (optional):

```bash
uv venv --system-site-packages
. .venv/bin/activate
uv pip install -e ".[http]"
```


## Running

GUI (if installed as entry point):

```bash
wbridge-app
```

GUI (from source checkout):

```bash
PYTHONPATH=src python3 -m wbridge.app
```

CLI examples:

```bash
# show the GUI window (bring to front)
wbridge ui show

# list last 10 clipboard entries
wbridge history list --which clipboard --limit 10

# apply second latest clipboard entry
wbridge history apply --which clipboard --index 1

# trigger a named action using current primary selection
wbridge trigger prompt --from-primary
```


## Pages in Detail

### History
- Two panes: Clipboard and Primary Selection
- Per pane:
  - Current value (single‑line preview, ellipsized)
  - Set/Get helpers (quick tests)
  - “Swap last two”
  - Scrollable history (newest first); apply buttons per row (Set as Clipboard/Primary)
- Periodic refresh; manual “Refresh” button
- Help panel topic: `history`

### Actions (Master‑Detail)
- Source selection: Clipboard / Primary / Text
- Left: actions list (name + preview)
- Right: shared editor with two tabs:
  - Form (recommended): Name, Type (http/shell); HTTP fields (Method, URL); Shell fields (Command, Args JSON, Use shell)
  - JSON (advanced): raw action JSON
- Buttons: Save (Form), Save (JSON), Duplicate, Delete, Cancel, Run
- Validation & atomic persistence to `~/.config/wbridge/actions.json` with timestamped backups
- If HTTP trigger integration is disabled, Run is disabled and a hint is shown
- Help panel topic: `actions`

### Triggers
- Dedicated page to manage alias → action name
- Add rows, delete rows, Save Triggers
- Validation: alias non‑empty/unique; action must exist
- Help panel topic: `triggers`

### Shortcuts
- GNOME Custom Keybindings overview
- Policy:
  - Only wbridge‑scope entries are editable/deletable (path suffix `wbridge-.../`)
  - Optional “Show all custom (read‑only)” to audit foreign entries
  - Conflicts summarized (e.g., `'<Ctrl><Alt>p' ×2`)
  - Deterministic suffix generation/re‑naming
  - PATH hint if `wbridge` is not found
- Buttons: Add (wbridge scope), Save, Reload
- Help panel topic: `shortcuts`

### Settings
- Environment / backend info (GDK Display; IPC Socket; Log file path)
- Integration (inline edit):
  - Enable HTTP trigger
  - Base URL (http/https), Trigger Path (/trigger)
  - Save / Discard / Reload Settings / Health check
- Profiles:
  - Built‑in profiles (e.g., “witsy”): show/install with options (overwrite actions, patch settings, install shortcuts, dry‑run)
- GNOME Shortcuts: install/remove recommended set (priority: settings.ini bindings → profile → defaults)
- Autostart: enable/disable
- PATH hints if `wbridge` is not found
- Help panel topic: `settings`

### Status & Log
- Environment summary and backend info
- Log tail viewer (`~/.local/state/wbridge/bridge.log`) with “Refresh”
- Help panel topic: `status`


## Help & i18n

- Per‑page Help panels load Markdown from package resources:
  - `src/wbridge/help/en/{history,actions,triggers,shortcuts,settings,status}.md`
- i18n via gettext:
  - Domain: `wbridge`
  - Fallback: English when translations are not shipped
  - UI strings wrapped with `_()` in code
- Translators can ship `.mo` files later (set `localedir` accordingly if bundling translations).


## GNOME custom shortcuts (concept)

Use GNOME Custom Shortcuts to execute CLI commands globally. Example bindings:
- Prompt: `wbridge trigger prompt --from-primary`
- Command: `wbridge trigger command --from-clipboard`
- Show UI: `wbridge ui show`

See also the Shortcuts page policy above. Programmatic setup via Gio.Settings is supported in code (install/remove recommended set).


## Configuration

Config dir: `~/.config/wbridge/`
- `settings.ini` (general)
- `actions.json` (action definitions)

Install optional HTTP extra for requests support:

```bash
pip install -e ".[http]"
```


## Profiles & Witsy Quickstart

Prerequisites:
- Optional HTTP extra (`.[http]`) if you plan to use HTTP actions.

List/show:
```bash
wbridge profile list
wbridge profile show --name witsy
```

Install:
```bash
# dry-run (preview)
wbridge profile install --name witsy --dry-run

# install with overwrite/patch and recommended shortcuts
wbridge profile install --name witsy --overwrite-actions --patch-settings --install-shortcuts
```

Notes
- Settings appear in GUI → Settings → Integration Status; use Health check to verify your local endpoint.
- Actions Run is disabled if HTTP trigger is disabled.


## CLI overview

Representative subcommands:
- `wbridge ui show`
- `wbridge history list|apply|swap`
- `wbridge selection get|set`
- `wbridge trigger <alias> [--from-clipboard|--from-primary|--text "..."]`
- `wbridge profile list|show|install [--dry-run]`
- Config helpers (optional): `config show-paths|backup|reset|restore`
- Shortcuts helpers (optional): `shortcuts remove --recommended`
- Autostart (optional): `autostart disable`

Exit codes: 0 success; 1 general/server not running; 2 invalid args; 3 action failed


## CSS & Theming

- CSS resource: `src/wbridge/assets/style.css`
  - `.dim-label` class for secondary text
  - Modest spacings/paddings; theme‑agnostic styling
- Loaded via `Gtk.CssProvider` at app startup


## File Monitors & Auto‑Reload

The GUI monitors:
- `~/.config/wbridge/settings.ini`
- `~/.config/wbridge/actions.json`

Changes from external editors trigger debounced reloads and UI refreshes (status labels, actions list, triggers, etc.).


## Troubleshooting

“wbridge” not found in PATH (GNOME shortcuts don’t fire)
- Install user‑wide with `pipx install --system-site-packages ".[http]"` (or later `wbridge[http]`)
- Ensure `~/.local/bin` is in your GNOME session PATH
- Or set an absolute command path in the GNOME shortcut

“No module named 'gi'”
- Ensure distro packages (`python3-gi`, GTK4) are installed
- Use venv/pipx with `--system-site-packages`

Starting GUI from checkout
- Use: `PYTHONPATH=src python3 -m wbridge.app`


## Project Layout

```
src/
  wbridge/
    __init__.py
    app.py               # GTK4 app entry point (wbridge-app); starts IPC; loads CSS/resources
    gui_window.py        # Main window; StackSidebar/Stack pages; Help panels; i18n
    cli.py               # CLI entry point (wbridge)
    server_ipc.py        # Unix domain socket server
    client_ipc.py        # Client helpers (if any)
    history.py           # History store and APIs
    actions.py           # Action runner (HTTP/Shell), placeholders
    config.py            # settings.ini + actions.json loading/writing
    platform.py          # env detection, paths, app info
    gnome_shortcuts.py   # Gio.Settings automation for custom keybindings
    autostart.py         # desktop autostart mgmt
    logging_setup.py     # file+console logging
    profiles_manager.py  # built‑in profiles (list/show/install), merge/backup/patch
    profiles/            # built‑in profile bundles (e.g. witsy)
    help/en/*.md         # per‑page Help content (English default)
    assets/style.css     # CSS for subtle UI styling
```

Packaging
- `pyproject.toml` includes package data:
  - `"wbridge" = ["help/**/*", "assets/**/*"]`
  - `"wbridge.profiles" = ["**/*"]`


## Changelog / Implementation Log

See [IMPLEMENTATION_LOG.md](IMPLEMENTATION_LOG.md) for dated entries.  
Latest: Step 8 – Help & i18n; StackSidebar navigation; Shortcuts policy; CSS; packaging; Status log tail; file monitors.


## License

MIT (see LICENSE).
