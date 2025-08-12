# wbridge

General-purpose selection and shortcut bridge for Linux Wayland desktops, built with GTK4/GDK. One repository, one Python package, two entry points:
- `wbridge` (CLI): Talks to the running app via IPC (Unix domain socket).
- `wbridge-app` (GUI): GTK4 application providing selection history, actions, and settings.

No global key grabbing (use GNOME Custom Shortcuts to execute the CLI), no headless hidden window, no tray, no wl-clipboard dependency.


## Features (V1 scope)

- GTK4/GDK-based monitoring for Clipboard and Primary Selection
- History (ring buffer), promote any item to Clipboard/Primary, swap last two
- Actions engine (HTTP or shell) with placeholders like `{text}`, `{text_url}`
- IPC server (Unix domain socket), CLI client (`wbridge`) to trigger actions and manage history/selection
- GNOME integration via Custom Shortcuts (programmatically manageable with Gio.Settings)
- Autostart via desktop entry
- Optional: generic local HTTP trigger configuration (no product coupling)

For full system design, see DESIGN.md.


## Requirements

- Linux with Wayland session (GNOME targeted in V1)
- Python 3.10+
- System packages providing GTK 4 and PyGObject (names vary by distro), for example on Debian/Ubuntu:
  - `sudo apt install -y python3-gi gir1.2-gtk-4.0`
- Optional: `requests` (only needed if you enable HTTP actions; can be installed via optional extra)

Note: GTK/PyGObject are typically installed from distro packages rather than pip.


## Installation (development)

Using pip (system or venv):

```bash
# create and activate a virtual environment (recommended)
python3 -m venv .venv
. .venv/bin/activate

# install in editable mode; requests only if you need HTTP actions
pip install -e ".[http]"
# or without http extra:
# pip install -e .
```

Using uv (optional):

```bash
# install uv if you don't have it
# curl -LsSf https://astral.sh/uv/install.sh | sh

uv venv
. .venv/bin/activate
uv pip install -e ".[http]"
```


## Running

GUI:

```bash
wbridge-app
```

CLI examples (will connect to the app via IPC):

```bash
# show the GUI window (bring to front)
wbridge ui show

# list last 10 clipboard entries
wbridge history list --which clipboard --limit 10

# apply the second latest primary selection entry to Clipboard
wbridge history apply --which clipboard --index 1

# trigger a named action using current primary selection
wbridge trigger prompt --from-primary
```

Note: In fresh scaffolding, the IPC and GUI stubs may be minimal. Implement features per DESIGN.md sections and the implementation checklist.


## Repository setup under GitHub Organization

You will create the repository under the organization:

- Organization: `DasDigitaleMomentum`
- Suggested repo name: `wbridge`
- Visibility: public (or private if preferred)
- License: MIT
- Default branch: `main`
- Recommended protections/policies:
  - Branch protection on `main` (PRs required, optional reviews)
  - Dependabot alerts/updates enabled
  - Secret scanning enabled
  - CODEOWNERS (e.g., `@DasDigitaleMomentum/maintainers`)

After you create the empty repo in the Org, run locally in this project root:

```bash
git init -b main
git add .
git commit -m "chore: scaffold wbridge (CLI+GUI in one package)"
git remote add origin git@github.com:DasDigitaleMomentum/wbridge.git
git push -u origin main
```

Adjust remote URL if you choose a different repository name or HTTPS instead of SSH.


## GNOME custom shortcuts (concept)

Use GNOME Custom Shortcuts to execute the CLI commands globally. Example bindings:

- Prompt action: `wbridge trigger prompt --from-primary`
- Command action: `wbridge trigger command --from-clipboard`
- Show UI: `wbridge ui show`

These can be added via the GNOME Settings UI or programmatically via Gio.Settings. See DESIGN.md for detailed keys and code snippet examples.


## Autostart

Create/remove `~/.config/autostart/wbridge.desktop` with:

```
[Desktop Entry]
Type=Application
Name=Selection/Shortcut Bridge
Exec=wbridge-app
X-GNOME-Autostart-enabled=true
OnlyShowIn=GNOME;X-GNOME;X-Cinnamon;XFCE;
```

Automation helpers will be provided in the code (`autostart.py`), per DESIGN.md.


## Configuration

Config dir: `~/.config/wbridge/`

- `settings.ini` (general)
- `actions.json` (action definitions)

Example profile for a local HTTP trigger endpoint is provided in DESIGN.md (Section “Example Config Profile”). Keep it empty/disabled if you don’t use a local trigger service.

Install optional HTTP extra for requests support:

```bash
pip install -e ".[http]"
```


## Project Layout (to be created next)

```
src/
  wbridge/
    __init__.py
    app.py               # GTK4 app entry point (wbridge-app)
    cli.py               # CLI entry point (wbridge)
    history.py           # ring buffer + APIs
    client_ipc.py        # IPC server/dispatcher
    actions.py           # action runner (HTTP/shell) + placeholders
    config.py            # settings.ini + action loading
    platform.py          # env detection, paths, app info
    gnome_shortcuts.py   # Gio.Settings automation for custom keybindings
    autostart.py         # desktop autostart file mgmt
    logging_setup.py     # file+console logging
```

All module responsibilities and interfaces are defined in DESIGN.md.


## License

MIT (see LICENSE).


## Next steps

- Implement the initial module stubs and minimal runnable entry points.
- Wire up IPC and CLI basics.
- Implement GTK history view and selection monitoring.
- Add actions engine and settings handling.
- Provide GNOME shortcut install/remove buttons in UI.
- Track progress using the checklist in DESIGN.md.
