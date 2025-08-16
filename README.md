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


## Profiles & Witsy Quickstart

Voraussetzungen
- Optionales HTTP-Extra für HTTP-Aktionen: `pip install -e ".[http]"` (oder ohne `-e`).
- Ein lokaler HTTP-Trigger muss erreichbar sein, wenn du die Witsy‑Aktionen nutzen willst (Default: http://127.0.0.1:18081/trigger).

Profile auflisten/anzeigen
```bash
wbridge profile list
wbridge profile show --name witsy
```

Profil installieren (in die User‑Konfiguration)
```bash
# Dry-run (zeigt geplante Änderungen ohne zu schreiben)
wbridge profile install --name witsy --dry-run

# Installation mit Überschreiben gleichnamiger Actions/Trigger und Settings‑Patch:
wbridge profile install --name witsy --patch-settings --overwrite-actions

# Optional: empfohlene GNOME‑Shortcuts des Profils mitinstallieren
wbridge profile install --name witsy --install-shortcuts
```

Hinweise
- Einstellungen: Im GUI → Settings‑Tab → „Integration Status“ prüfen:
  - integration.http_trigger_enabled, Base‑URL, Trigger‑Pfad
- Actions‑Tab: Wenn `http_trigger_enabled=false`, werden Run‑Buttons deaktiviert und ein Hinweis angezeigt („HTTP Trigger disabled – in Settings aktivieren“).
- Shortcuts: Profil‑Shortcuts können optional über `--install-shortcuts` installiert werden. Die allgemeinen UI‑Buttons für Shortcuts sind derzeit Platzhalter.

## Actions & Triggers Editor

Der Actions‑Tab zeigt alle Aktionen aus `~/.config/wbridge/actions.json` und ermöglicht Bearbeitung sowie Tests:

- Darstellung
  - Jede Aktion als Expander mit Kopfzeilen‑Preview (HTTP: `METHOD URL`, Shell: `command`).
  - Im Expander: Raw‑JSON‑Editor (monospaced).
- Buttons je Aktion
  - Run: führt die Aktion mit der gewählten Quelle (Clipboard/Primary/Text) aus.
  - Save: parst/validiert die JSON‑Definition und speichert atomar in `actions.json`. Vorher wird eine Timestamp‑Sicherung (`actions.json.bak-YYYYmmdd-HHMMSS`) angelegt. Die Liste wird neu geladen.
  - Cancel: verwirft lokale Änderungen und lädt die Datei neu.
  - Duplicate: legt eine Kopie mit eindeutigem Namen an (z. B. „(copy)”).
  - Delete: löscht die Aktion; zugehörige Trigger‑Einträge werden entfernt.
- Add Action
  - Fügt eine Standard‑HTTP‑Aktion (GET, leere URL) hinzu. Speicherung erfolgt atomar, die Liste wird neu geladen.
- Triggers‑Editor (unterhalb der Liste)
  - Alias → Action‑Zuordnung (Alias als Entry, Action als ComboBox).
  - „Add Trigger“, „Save Triggers“, „Delete“ pro Zeile.
  - Validierung: keine doppelten Aliase; Action‑Name muss existieren.
- Hinweise
  - `http_trigger_enabled=false` deaktiviert die Run‑Buttons. Editieren/Speichern bleibt möglich.
  - Beim Umbenennen einer Aktion aktualisiert der Editor Trigger nicht automatisch. Passen Sie Aliase bei Bedarf im Triggers‑Editor an.

## Settings Inline‑Edit & Health‑Check

Im Settings‑Tab können zentrale Integrationswerte direkt bearbeitet werden:

- Inline‑Edit (Whitelist)
  - `integration.http_trigger_enabled` (Switch)
  - `integration.http_trigger_base_url` (Entry, muss mit http/https beginnen)
  - `integration.http_trigger_trigger_path` (Entry, muss mit `/` beginnen)
- Speichern/Verwerfen/Reload Settings
  - Änderungen werden atomar in `~/.config/wbridge/settings.ini` geschrieben (Tempfile + Replace) und anschließend sofort im UI reflektiert.
  - „Reload Settings“ lädt die Datei manuell neu (nützlich nach CLI‑Änderungen).
- Health‑Check
  - Button „Health check“ sendet `GET {base_url}{health_path}` (Default: `/health`) mit kurzem Timeout.
  - Ergebnis (OK/Fehler + HTTP‑Code) wird angezeigt.

## Hinweise zu Backups und Validierung

- Actions‑Editor:
  - Vor dem Schreiben von `actions.json` wird eine Timestamp‑Sicherung angelegt.
  - JSON‑Validierung prüft Pflichtfelder und Typen für HTTP/Shell.
- Settings Inline‑Edit:
  - Atomare INI‑Writes (Tempfile + Replace).
  - Einfache Validierung für Base‑URL/Trigger‑Pfad.

## Config‑CLI

Werkzeuge zur Verwaltung der lokalen Konfiguration:

```bash
# wichtige Pfade anzeigen (optional maschinenlesbar)
wbridge config show-paths
wbridge config show-paths --json

# Backups erstellen (Timestamp)
wbridge config backup --what all      # oder actions|settings

# Reset (löscht Dateien, optional mit Backups)
wbridge config reset --backup               # beide
wbridge config reset --keep-actions --backup
wbridge config reset --keep-settings --backup

# Wiederherstellen aus Backup-Datei
wbridge config restore --file ~/.config/wbridge/actions.json.bak-YYYYmmdd-HHMMSS
wbridge config restore --file ~/.config/wbridge/settings.ini.bak-YYYYmmdd-HHMMSS
```

Exit-Codes: 0 ok, 2 invalid args, 3 failure.

## Auto‑Reload (File Monitor)

Die GUI überwacht `~/.config/wbridge/settings.ini` und `~/.config/wbridge/actions.json`:
- Änderungen von außen werden automatisch erkannt (Debounce ~200 ms).
- Die Oberfläche lädt den Status neu (Label-Hinweis „Config reloaded from disk…“).
- Bei `settings.ini`: Integration‑Status/Enable wird aktualisiert.
- Bei `actions.json`: Actions‑Liste und Triggers‑Editor werden neu geladen.

## GNOME Shortcuts & Autostart

- Shortcuts installieren/entfernen:
  - Settings‑Tab → Buttons „GNOME Shortcuts installieren/entfernen“.
  - Priorität Installation:
    1) settings.ini [gnome] (`binding_prompt`, `binding_command`, `binding_ui_show`)
    2) ausgewähltes Profil (shortcuts.json)
    3) Default‑Empfehlungen (`<Ctrl><Alt>p|m|u`)
  - Entfernen:
    - „Empfohlene“ werden zurückgesetzt.
    - Wenn ein Profil ausgewählt ist, werden dessen Profil‑Shortcuts (deterministischer Suffix `wbridge-<slug>/`) ebenfalls entfernt.

- Autostart:
  - Settings‑Tab → „Autostart aktivieren/deaktivieren“.
  - Legt `~/.config/autostart/wbridge.desktop` an/entfernt es (Exec=`wbridge-app`).

## Global Installation (ohne venv)

Für eine nutzerweite („globale“) Bereitstellung der CLIs (wbridge, wbridge-app) ohne venv empfehlen sich diese Wege:

- Variante A: pipx (empfohlen)
  - Installation: sudo apt install pipx && pipx ensurepath
  - Aus diesem Projekt (mit HTTP‑Extra, optional):
    - pipx install ".[http]"
  - Prüfen:
    - which wbridge
    - which wbridge-app
  - Vorteil: saubere Isolierung je Tool, Binaries liegen im Benutzer‑PATH (~/.local/bin), GNOME Shortcuts finden sie.

- Variante B: pip --user
  - Installation:
    - pip install --user ".[http]"
  - Achte darauf, dass ~/.local/bin im PATH deiner GNOME‑Session ist (ab-/anmelden kann nötig sein).

Hinweis:
- Systemweite Installation per sudo pip ist auf Debian/Ubuntu nicht empfohlen (Konflikt mit Paketmanager).
- GTK/PyGObject kommen weiterhin aus den OS‑Paketen (z. B. apt install python3-gi gir1.2-gtk-4.0).

## Hinweise zu uv

- Entwicklung: uv ist ein schneller Ersatz für venv/pip.
  - uv venv
  - . .venv/bin/activate
  - uv pip install -e ".[http]"
- Nutzerweit („global“) ist pipx heute meist die klarste Option. uv kann technisch auch --user‑Ziele bedienen (uv pip install --user …), bietet aber erst mit einem veröffentlichten Paket den bequemen Modus „uv tool install wbridge[http]“ (geplant nach Veröffentlichung).

## Troubleshooting – GNOME Shortcuts finden „wbridge“ nicht

- Symptom: Tastenkombination löst nichts aus, obwohl der Shortcut existiert.
- Ursache: GNOME‑Session‑PATH enthält ggf. nicht ~/.local/bin oder dein venv. 
- Lösungen:
  1) Installiere wbridge nutzerweit via pipx/pip --user (siehe „Global Installation“) und melde dich einmal ab/an.
  2) Alternativ: Öffne GNOME Einstellungen → Tastatur → Benutzerdefinierte Verknüpfungen, wähle den Eintrag („Bridge: Prompt/Command/Show UI“) und ersetze den Command von „wbridge …“ durch den absoluten Pfad, z. B. 
     /home/USER/.local/bin/wbridge trigger prompt --from-primary
     oder dein venv‑Pfad.
- Diagnose:
  - gsettings get org.gnome.settings-daemon.plugins.media-keys custom-keybindings
  - which wbridge
  - wbridge-app starten, dann im Terminal testen:
    wbridge trigger prompt --from-primary

## Uninstall

- Paket deinstallieren
  - pipx: pipx uninstall wbridge
  - pip --user: pip uninstall wbridge
- GNOME Shortcuts entfernen
  - In der App (Settings‑Tab): „GNOME Shortcuts entfernen“ (empfohlene) und ggf. „Profil‑Shortcuts entfernen“.
  - Alternativ per GNOME Einstellungen → Tastatur → Benutzerdefinierte Verknüpfungen → manuell löschen.
- Autostart deaktivieren
  - In der App: „Autostart deaktivieren“
  - Manuell: rm ~/.config/autostart/wbridge.desktop
- Konfiguration/Logs
  - CLI (solange wbridge vorhanden): wbridge config reset --backup
  - Manuell: 
    - rm -f ~/.config/wbridge/settings.ini ~/.config/wbridge/actions.json
    - rm -f ~/.local/state/wbridge/bridge.log

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
