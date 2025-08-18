# Selection/Shortcut Bridge (Wayland) – Design Specification

Status: Draft (V1)  
Scope: Linux (Wayland), GNOME primary; others may work but are not a focus in V1  
Audience: Implementers and maintainers

This document specifies a general-purpose desktop bridge that:
- Monitors text selections (clipboard and primary selection) reliably on Wayland using GTK4/GDK only.
- Maintains a history and lets users promote any history item to clipboard or primary selection.
- Exposes a local CLI to trigger actions (HTTP or shell commands) that can consume the current selection or history entries.
- Integrates with GNOME via Custom Shortcuts (global keybindings) that execute the CLI (no global key grabbing).
- Supports optional, generic HTTP-trigger integration via configuration (no product references).

No hidden headless mode, no tray icon, no wl-clipboard dependency, no key injection.


## 0. Hintergrund & Motivation

Unter Wayland (und teils auch auf macOS) sind globale Hotkeys/Key‑Grabs für Anwendungen wie Electron stark eingeschränkt. In der Praxis führte dies u. a. unter Ubuntu 25.04 dazu, dass globales Copy/Paste beeinträchtigt wurde, wenn Apps globale Shortcuts aggressiv belegen. Das Projekt „Witsy“ (Electron) versuchte globale Shortcuts zu nutzen und stieß genau auf diese Limitierungen.

Als Reaktion wurden PRs in Witsy erstellt:
1) Deaktivierung der globalen Shortcuts.
2) Bereitstellung eines minimalen lokalen HTTP‑Servers (Loopback), der Shortcut‑Trigger entgegennehmen kann.

Die „Selection/Shortcut Bridge“ (wbridge) ist ein eigenständiges, generisches Projekt, das das GNOME‑Shortcut‑System erweitert, ohne globale Key‑Grabs oder Key‑Injection zu verwenden. GNOME Custom Shortcuts lösen CLI‑Befehle aus; eine laufende GTK4‑App verarbeitet die Requests via Unix‑Domain‑Socket‑IPC und führt konfigurierbare Aktionen (HTTP/Shell) auf Basis der aktuellen Selektion/History aus. Dadurch bleibt die Lösung Wayland‑freundlich, robust und universell nutzbar – u. a. für die optionale Anbindung von Witsy über ein lokales HTTP‑Profil. Das Projekt ist öffentlich, neutral benannt und unter MIT‑Lizenz.

## 1. Goals and Non-Goals

Goals
- Provide a Wayland-friendly workflow to:
  - Track clipboard and primary selection updates via GTK4/GDK.
  - Apply history items back to clipboard or primary.
  - Execute configurable actions (HTTP/shell) with placeholders drawn from current selection/history/app info.
  - Allow invocation via system keybindings, by executing a CLI command that talks to the running app via IPC.
- Be generally useful; no naming or binding to specific products or services.
- Keep the runtime simple (GTK4 + standard Python libraries), robust, and easy to maintain.

Non-Goals
- No global key grabbing on GNOME (use GNOME Custom Shortcuts that execute our CLI).
- No key injection into other apps (e.g., simulating “Ctrl+V”).
- No background/headless mode that relies on a hidden window or wl-clipboard.
- No system tray applet.
- No retry/backoff/throttle logic for actions in V1.


## 2. Environment and Assumptions

- Wayland session (XDG_SESSION_TYPE=wayland).
- GNOME desktop environment is primary target in V1.
- Python 3, PyGObject (GTK 4), GLib/Gio available from the distro packages.
- Network access is not required; if actions target local HTTP endpoints, they must be reachable on localhost.

System Packages & Installation Notes (important)
- PyGObject/GTK4 must come from your Linux distribution packages (do not try to build via pip).
- Typical package names by distro:
  - Debian/Ubuntu:
    - sudo apt update && sudo apt install -y python3-gi gir1.2-gtk-4.0 gobject-introspection
  - Fedora:
    - sudo dnf install -y python3-gobject gtk4
  - Arch/Manjaro:
    - sudo pacman -S --needed python-gobject gtk4
  - openSUSE:
    - sudo zypper install -y python3-gobject gtk4
- Global/user installation of the Python package:
  - Prefer pipx and ensure the environment can see system packages (PyGObject):
    - pipx install --system-site-packages "wbridge[http]"      # once published
    - From source checkout: pipx install --system-site-packages ".[http]"
  - If using a virtual environment for development:
    - python3 -m venv --system-site-packages .venv
    - . .venv/bin/activate && pip install -e ".[http]"
- Verify GI availability:
  - python3 -c "import gi; from gi.repository import Gtk, Gdk; print('GI OK', Gtk.get_major_version())"
- Troubleshooting “No module named 'gi'”:
  - Install the system packages listed above, then reinstall with pipx --system-site-packages (or re-create venv with --system-site-packages).


## 3. High-Level Architecture

Components
- GUI Application (GTK4)
  - Shows history (clipboard + primary).
  - Allows applying history items to clipboard/primary.
  - Provides UI to manage “Actions” (HTTP/shell), with placeholders, and a settings area.
  - Runs a GLib main loop and hosts the IPC server.

- IPC Server (Unix Domain Socket)
  - Listens for JSON requests from the CLI.
  - Path: $XDG_RUNTIME_DIR/wbridge.sock (0600).
  - Processes requests: show UI, get/set selection, manipulate history, run actions.

- CLI Client (wbridge)
  - Thin client that connects to the IPC server and sends JSON requests.
  - Used by GNOME Custom Shortcuts: GNOME binds a key → executes the CLI command.

- Configuration
  - settings.ini (general settings).
  - actions.json (action definitions).

- Actions Engine
  - Runs either HTTP requests (GET/POST with optional JSON body) or shell commands (subprocess).
  - Substitutes placeholders like {text}, {text_url}, {history[0]}, {app.name}, etc.

Data Flow (example)
1) User presses GNOME global keybinding.  
2) GNOME executes CLI, e.g., `wbridge trigger prompt --from-primary`.  
3) CLI connects to IPC socket and sends a request.  
4) Application reads current primary selection, substitutes placeholders, and executes the configured action (e.g., HTTP POST).  
5) The application logs the result; the CLI exits with code 0 or a non-zero error code.


## 4. UI Composition and Responsibilities

MainWindow (Gtk.ApplicationWindow)
- Navigation: left-side Gtk.StackSidebar + Gtk.Stack.
- Loads CSS (`assets/style.css`).
- Orchestrates pages:
  - HistoryPage: current values and lists for clipboard/primary; apply/swap.
  - ActionsPage: master/detail editor (Form + JSON); run/save/duplicate/delete; hint if HTTP trigger disabled.
  - TriggersPage: alias → action mapping editor.
  - ShortcutsPage: GNOME custom keybindings management (wbridge scope editable).
  - SettingsPage: Integration status; inline edit (enable/base/path); health check; profiles; shortcuts/autostart helpers.
  - StatusPage: environment info + log tail.
- File monitors (debounced):
  - `~/.config/wbridge/settings.ini` → `SettingsPage.reload_settings()` and dependent refresh chains.
  - `~/.config/wbridge/actions.json` → reload app._actions; `ActionsPage.refresh_actions_list()`, `ActionsPage.notify_config_reloaded()`, `TriggersPage.rebuild_editor()`.
- Periodic tick (GLib.timeout_add) for HistoryPage label updates and list refresh when dirty.

Help panel component
- `ui/components/help_panel.py` renders per-page “Help” from package resources (`help/en/*.md`).

Notes
- All page classes are Gtk.Box descendants and attach only newly created child widgets (no reparenting).
- No Notebook tabs; navigation is StackSidebar + Stack for a modern GNOME UX.

### Page Header, Help (Popover-only) und CTA-Bar
- Der Help-Button („?“) öffnet ein Gtk.Popover; es gibt keinen Revealer-Modus mehr.
- Popover-Breite dynamisch ≈65% der Fensterbreite (min 520 px), keine horizontale Scrollbar (Policy NEVER/AUTOMATIC), natürliche Breite wird propagiert. CSS-Klasse: `.help-popover` (mit Fallback `min-width` in CSS).
- Popover ist relativ zum Help-Button verankert (`set_relative_to`), `autohide=True`, Breite wird bei Fenster-Resize per `size-allocate`-Hook nachgeführt.
- CTA-Bar pro Seite fest am unteren Rand, gebaut mit `ui/components/cta_bar.py::build_cta_bar(...)`; sie liegt außerhalb der Inhalts-Scroller und bleibt damit fix.

### Responsives Layout – Muster pro Seite
- Kein äußerer Scroller für die gesamte Seite. Stattdessen wächst der Seitencontainer (`hexpand/vexpand=True`), und nur lange Inhaltsbereiche erhalten eigene `Gtk.ScrolledWindow`-Wrapper (`vexpand=True`). Die CTA-Bar bleibt außerhalb der Scroller.
- History/Triggers/Shortcuts:
  - Äußere Page-Scroller entfernt; die jeweiligen Listen befinden sich in eigenen ScrolledWindows (vexpand=True).
  - Mindesthöhen leicht angehoben (History-Listen je 140 px) für ein stabileres Layout bei kleinen Fenstern.
- Status:
  - Log newest-first (neueste Zeilen oben), Follow-Switch (1 s), Cursor/Scroll an den Anfang; Log-Scroller `vexpand=True`.

### Actions – Vertikaler Split (Editor oben, Liste unten)
- `Gtk.Paned(orientation=VERTICAL)` mit:
  - `set_shrink_start_child(False)` (Editor darf nicht schrumpfen),
  - `set_shrink_end_child(True)` (Liste darf schrumpfen).
- Standard-Split oben ≈0.62 (Editor), unten ≈0.38 (Liste).
- Editor besitzt eigenen Scroller mit `min_content_height=320`.
- Robuste Initialpositionierung:
  - Split wird nach dem ersten Anzeigen (map/visible) gesetzt (via `GLib.idle_add`), zusätzlich kurze verzögerte Retries.
  - `size-allocate`-Hook setzt die Position bei Größenänderungen gemäß Ratio neu.
  - `notify::position` aktualisiert die Ratio bei Nutzer-Drag; ein Guard ignoriert frühe Events, bis der erste sinnvolle Split gesetzt ist.

### CSS und Assets
- `assets/style.css`:
  - `.page-header`, `.page-subtitle.dim`, `.cta-bar`
  - `.help-popover` und `.help-popover scrolledwindow { min-width: 520px; }`
  - `.mono` für Monospace-Bereiche
- `MainWindow` Startfenstergröße: `set_default_size(1200, 880)`.

### Markdown → Pango
- `ui/components/markdown.py::md_to_pango` konvertiert Minimal-Markdown (Headings, Bullets, Inline-/Fenced-Code, Bold/Italic) in Pango-Markup, gerendert in `Gtk.Label(use_markup=True)`.

### Help-Mode: Konsolidierung
- Der frühere Hilfe-Modus (Revealer/Popover) wurde konsolidiert: Popover-only ist der kanonische Modus.
- `apply_help_mode()` in `MainWindow` ist neutralisiert; die Konfigurationsoption wurde entfernt.


## 5. Clipboard/Primary Monitoring and History

- Use GTK4/GDK APIs exclusively (no wl-clipboard):
  - Gdk.Display.get_clipboard()
  - Gdk.Display.get_primary_clipboard()
  - Read text periodically or via async reads.
- Maintain two histories:
  - Clipboard history
  - Primary selection history
- History behavior:
  - Ring buffer with a configurable maximum (default: 50).
  - Dedupe consecutive duplicates (do not add if identical to the last cached value).
  - Persisting history to disk is optional in V1 (can be added later).

Operations
- Promote any history item to clipboard/primary.
- Swap the latest two entries (toggle flow).
- No key injection. Paste is performed by the user (Ctrl+V or middle-click).


## 6. Actions and Placeholders

Action Types
- HTTP: GET or POST; optional headers/body (JSON/form).
- Shell: Execute a program with arguments; no shell unless explicitly requested.

Placeholders (examples)
- {text}, {text_url}
- {selection.type} → "clipboard" | "primary"
- {app.name}, {app.title}, {app.pid}
- {now.iso}
- {history[0]}, {history[1]}, …
- Optionally `{config.section.key}` to reference config values.


## 7. IPC Protocol

Transport
- Unix Domain Socket: $XDG_RUNTIME_DIR/wbridge.sock (0600).

Framing
- Newline-delimited JSON (one JSON object per line).

Requests (representative)
- `ui.show`, `selection.get/set`, `history.list/apply/swap`, `action.run`, `trigger`.

Responses
- `{ "ok": true, "data": { … } }` or `{ "ok": false, "error": "...", "code": "..." }`


## 8. GNOME Custom Shortcuts (Automation)

- GNOME manages global keybindings and executes shell commands.
- Programmatic setup: Gio.Settings (`org.gnome.settings-daemon.plugins.media-keys`).
- Recommended bindings provided; only wbridge-managed entries (`wbridge-*`) are editable from the app.


## 9. Autostart

- Create/remove `~/.config/autostart/wbridge.desktop` (visible window on login).
- Users can bring it to front with `wbridge ui show`.


## 10. Configuration Files

Location
- Settings: `~/.config/wbridge/settings.ini`
- Actions: `~/.config/wbridge/actions.json`
- Logs: `~/.local/state/wbridge/bridge.log`

INI example (excerpt)
```
[integration]
http_trigger_enabled = false
http_trigger_base_url = http://127.0.0.1:18081
http_trigger_health_path = /health
http_trigger_trigger_path = /trigger
```

JSON example (excerpt)
```
{
  "actions": [{ "name": "...", "type": "http" | "shell", ... }],
  "triggers": { "prompt": "Action Name", ... }
}
```


## 11. Module Layout (Python)

Package name: `wbridge`

- `wbridge/app.py`
  - Gtk.Application init; starts IPC server; loads settings/actions; creates MainWindow; logging setup.
- `wbridge/ui/main_window.py`
  - Orchestrates navigation and all pages; CSS load; file monitors; periodic tick.
- `wbridge/ui/pages/{history_page.py, actions_page.py, triggers_page.py, shortcuts_page.py, settings_page.py, status_page.py}`
  - Page-specific UI modules (composition over monolith).
- `wbridge/ui/components/help_panel.py`
  - Reusable Help panel builder (Markdown → TextView inside scroller).

Core services
- `wbridge/server_ipc.py`
  - Unix domain socket server (newline-delimited JSON), request routing.
- `wbridge/cli.py`
  - CLI entry point (`wbridge`), builds JSON requests → IPC.
- `wbridge/actions.py`
  - Load/save actions; placeholder substitution; HTTP (requests/urllib) & shell runner.
- `wbridge/config.py`
  - Load settings.ini; load/write actions.json; atomic writes; validation helpers.
- `wbridge/history.py`
  - Ring buffers for clipboard/primary with dedupe and limits.
- `wbridge/platform.py`
  - Paths (config/state/autostart), Wayland/env detection, optional app info.
- `wbridge/gnome_shortcuts.py`
  - Gio.Settings automation for custom keybindings (install/update/remove).
- `wbridge/autostart.py`
  - Create/remove desktop entry.
- `wbridge/logging_setup.py`
  - File + console logger.
- `wbridge/profiles_manager.py`
  - Profiles (list/show/install), merge/backup/patch; resources in `wbridge/profiles/**`.

Packaging
- `pyproject.toml` includes package data:
  - `"wbridge" = ["help/**/*", "assets/**/*"]`
  - `"wbridge.profiles" = ["**/*"]`


## 12. Logging and Diagnostics

- Logging to console and to `~/.local/state/wbridge/bridge.log`.
- Levels: INFO by default; DEBUG optional via env/setting.
- IPC: log op/status/duration; actions: log type/name/success/failure/elapsed.


## 13. Security and Privacy

- IPC socket 0600 (owner-only); no TCP in V1.
- No implicit data exfiltration; actions are explicit.
- HTTP actions: caution with external endpoints; Shell: default no shell, explicit if needed.
- No key capture; GNOME manages keybindings and executes our CLI.


## 14. Error Handling

- CLI exits non-zero if server not reachable, invalid args, action failed.
- App shows brief UI/log entries for failed actions.
- No retries/backoff in V1.


## 15. Implementation Plan (V1)

Phase 0 – Scaffold  
Phase 1 – IPC + CLI  
Phase 2 – History + GUI (StackSidebar + Stack)  
Phase 3 – Actions Engine  
Phase 4 – GNOME Integration + Autostart  
Phase 5 – Polish (docs, logging)

(Details unchanged; see earlier revisions in repo history.)


## 16. Testing Checklist

Selections and History
- Clipboard/primary updates appear; dedupe works; apply/swap works.

CLI and IPC
- `wbridge ui show`, `history list/apply/swap`, `selection get/set`.

Actions
- HTTP/POST sends text; shell runs with placeholders; disabled state honored.

GNOME Shortcuts
- Install/remove via UI; pressing keys runs CLI.

Autostart
- Desktop entry created; app starts visible.

File Monitors & Auto-Reload
- Editing `settings.ini` updates integration labels and actions enable state without restart.
- Editing `actions.json` reloads actions and triggers list (debounced).

No Hidden Headless
- Ensure no unintended “hidden window” mode.


## 17. Appendix: Example GNOME Keybinding Setup (Gio)

(unchanged; conceptual snippets illustrating Gio.Settings setup)


## 18. Completeness Review (against requirements)

Covered in V1
- Wayland-friendly selection monitoring (GTK4/GDK only).
- History with apply/swap.
- IPC + CLI to run actions and manipulate history/selection.
- GNOME shortcuts; Autostart; optional local HTTP trigger.
- No wl-clipboard, no headless, no tray.

Deferred/out of scope (V1)
- Compositor-specific bindings (Hyprland/Sway).
- Persistent history; GNOME Shell extension; cross-platform transports.

Risks/Notes
- Primary selection semantics vary by DE/app.
- No paste injection by design (Wayland security model).


## 19. Example Config Profile: Local Action Server (PR2-compatible)

(unchanged; see examples for actions/triggers/paths)


## 20. Cross-Platform Considerations (macOS, Windows 11)

(unchanged; transport/provider abstractions suggested for future ports)


## 21. Modularity Review and Extensibility

- Interfaces/Protocols for SelectionProvider, HistoryStore, IPCTransport, ActionRunner, ShortcutManager, AutostartManager.
- Placeholder expansion as dedicated service.
- UI decoupled from execution; services testable without Gtk widgets.


## 22. Reference Code Snippets (PoC-inspired)

Snippets illustrate concepts. Production code follows the modular UI architecture (pages + services) described above.


## 23. Implementation Checklist (Progress Tracking)

(kept as running checklist at the end of the document)


## 24. Clipboard Implementation Notes (GTK4/PyGObject, Wayland)

(operational notes; unchanged)
