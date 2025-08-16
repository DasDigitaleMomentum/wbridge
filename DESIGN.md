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


## 4. Clipboard/Primary Monitoring and History

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
- Promote any history item to clipboard.
- Promote any history item to primary selection.
- Swap the latest two entries (e.g., a quick “toggle” workflow).
- No key injection. The user performs “paste” in their target app manually (Ctrl+V or middle-click, depending on selection type).


## 5. Actions and Placeholders

Action Types
- HTTP:
  - Method: GET or POST.
  - URL: configurable (e.g., http://127.0.0.1:18081/trigger).
  - Headers: optional.
  - Body: optional (JSON or form fields).
- Shell:
  - Execute a program with arguments (no shell by default).
  - If a shell is required, it must be explicit and carefully quoted in the config.

Placeholders (examples)
- {text}              → raw text from selection or history item
- {text_url}          → URL-encoded text
- {selection.type}    → "clipboard" or "primary"
- {app.name}          → name/class of the currently active app if available
- {app.title}         → window title of the currently active app if available
- {app.pid}           → process ID if available
- {now.iso}           → current timestamp in ISO format
- {history[0]}        → most recent history entry of the corresponding selection type
- {history[1]}        → second most recent, etc.

Example HTTP action (conceptual)
- POST http://127.0.0.1:18081/trigger with JSON body:
  {
    "cmd": "prompt",
    "text": "{text}"
  }

Example Shell action (conceptual)
- Command: /usr/bin/notify-send
- Args: ["Action", "Sent: {text}"]


## 6. IPC Protocol

Transport
- Unix Domain Socket: $XDG_RUNTIME_DIR/wbridge.sock
- Permissions: 0600 (owner-only).

Message Framing
- Each request/response is a single JSON object terminated by a newline.
- Alternatively, use simple length-prefix framing. For V1, newline-delimited JSON is sufficient.

Requests (representative)
- Show UI:
  {
    "op": "ui.show"
  }

- Get selection:
  {
    "op": "selection.get",
    "which": "clipboard"   // "clipboard" | "primary"
  }

- Set selection:
  {
    "op": "selection.set",
    "which": "primary",     // "clipboard" | "primary"
    "text": "some text"
  }

- List history:
  {
    "op": "history.list",
    "which": "clipboard",   // "clipboard" | "primary"
    "limit": 10
  }

- Apply history item:
  {
    "op": "history.apply",
    "which": "primary",     // "clipboard" | "primary"
    "index": 1              // 0 = latest
  }

- Swap last two:
  {
    "op": "history.swap",
    "which": "clipboard"    // "clipboard" | "primary"
  }

- Run action by name:
  {
    "op": "action.run",
    "name": "Send to Local Trigger",
    "source": {
      "from": "primary"     // "clipboard" | "primary" | "text"
    },
    "text": "override text (optional if from=text)"
  }

- Trigger shortcut alias (mapped to an action):
  {
    "op": "trigger",
    "cmd": "prompt",
    "source": {
      "from": "primary"
    }
  }

Responses
- Success:
  {
    "ok": true,
    "data": { ... }         // optional
  }

- Error:
  {
    "ok": false,
    "error": "Human-readable message",
    "code": "INVALID_ARG"   // optional code
  }

Error Codes (examples)
- "NOT_RUNNING": IPC server not available (handled by CLI).
- "INVALID_ARG": malformed request.
- "NOT_FOUND": action or history index not found.
- "ACTION_FAILED": executing HTTP/shell failed.


## 7. CLI Specification (wbridge)

Binary
- Installed as `wbridge` (Python entry point).

Global Behavior
- Connects to `$XDG_RUNTIME_DIR/wbridge.sock`.
- On connection failure: print error to stderr and exit with non-zero code.
- Prints minimal output; use `--verbose` for extended diagnostics (optional).

Subcommands (examples)
- Show UI:
  wbridge ui show

- Trigger (maps to action.run):
  wbridge trigger prompt --from-primary
  wbridge trigger command --from-clipboard
  wbridge trigger custom --name "Send to Local Trigger" --from-clipboard
  Options:
    --from-clipboard | --from-primary | --text "literal"

- History:
  wbridge history list --which clipboard --limit 10
  wbridge history apply --which primary --index 1
  wbridge history swap --which clipboard

- Selection:
  wbridge selection get --which primary
  wbridge selection set --which clipboard --text "Hello"

Exit Codes
- 0: success
- 1: general error (including “server not running”)
- 2: invalid arguments
- 3: action failed

### Profile Commands (CLI)

Subcommands
- List built-in profiles:
  - wbridge profile list
- Show profile details (metadata + core contents):
  - wbridge profile show --name witsy
- Install profile into user config:
  - wbridge profile install --name witsy [--overwrite-actions] [--patch-settings] [--install-shortcuts] [--dry-run]

Notes
- Exit Codes: 0 OK, 2 invalid args, 3 failure.
- Behavior:
  - actions.json merge by action "name"; default is user-first (skip), overwrite with --overwrite-actions.
  - triggers merge by key; default user-first, overwrite with --overwrite-actions.
  - settings.patch.ini patches only whitelisted keys in [integration] when --patch-settings is provided.
  - shortcuts.json installs recommended GNOME shortcuts when --install-shortcuts is provided (no forced overwrite; conflicts are surfaced).
- Examples:
  - wbridge profile show --name witsy
  - wbridge profile install --name witsy --patch-settings --overwrite-actions --dry-run


### Config and Maintenance Commands (CLI)

Subcommands
- Show important paths:
  - wbridge config show-paths [--json]
- Backup config files (timestamped):
  - wbridge config backup [--what actions|settings|all]
- Reset config files (delete with optional backup):
  - wbridge config reset [--keep-actions] [--keep-settings] [--backup]
- Restore from backup file:
  - wbridge config restore --file PATH
- Remove profile-installed shortcuts only:
  - wbridge profile uninstall --name NAME --shortcuts-only
- Remove recommended shortcuts:
  - wbridge shortcuts remove --recommended
- Disable autostart:
  - wbridge autostart disable

Notes
- Exit Codes: 0 OK, 2 invalid args, 3 failure.
- No destructive default without explicit flags; backups are timestamped.
- GNOME bindings may require an absolute path to "wbridge" if it is not found in PATH.

## 8. GNOME Custom Shortcuts (Automation)

Concept
- GNOME manages global shortcuts (keybindings) and executes shell commands on activation.
- The app does not “capture” keys; it provides a CLI, which GNOME executes.

Programmatic Setup (via Gio.Settings)
- Schema: org.gnome.settings-daemon.plugins.media-keys
- Key: custom-keybindings (array of object paths)
- Each binding is an object path like:
/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/wbridge-prompt/

Under that path:
- Schema: org.gnome.settings-daemon.plugins.media-keys.custom-keybinding
- Keys: name (string), command (string), binding (string like <Ctrl><Alt>p)

Example Entries (conceptual)
- Add the path to custom-keybindings, then set fields:
  - name: "Bridge: Prompt"
  - command: wbridge trigger prompt --from-primary
  - binding: <Ctrl><Alt>p

The application should provide UI buttons:
- “Install GNOME Shortcuts”: creates/updates a recommended set.
- “Remove GNOME Shortcuts”: removes them.

Conflict Handling
- If a binding is already in use, GNOME’s UI indicates conflicts. The app should handle errors gracefully and allow the user to adjust bindings.


## 9. Autostart

Desktop Entry
- Create/remove `~/.config/autostart/wbridge.desktop`.

Example desktop file content:
[Desktop Entry]
Type=Application
Name=Selection/Shortcut Bridge
Exec=wbridge-app
X-GNOME-Autostart-enabled=true
OnlyShowIn=GNOME;X-GNOME;X-Cinnamon;XFCE;

Notes
- `wbridge-app` is the GUI entry point (see Module Layout below).
- On login, the normal GUI window starts (no hidden headless mode).
- Users can bring it to foreground with `wbridge ui show` or via overview/task switcher.


## 10. Configuration Files

Location
- Settings: `~/.config/wbridge/settings.ini`
- Actions: `~/.config/wbridge/actions.json`
- Logs: `~/.local/state/wbridge/bridge.log` (file and console)

settings.ini (example)
[general]
history_max = 50
poll_interval_ms = 300

[ui]
; future: theme, window size, etc.

[integration]
; Optional local HTTP trigger endpoint (if you have one)
; Keep empty if not used.
http_trigger_enabled = false
http_trigger_base_url = http://127.0.0.1:18081
; Optional endpoints (if not default)
http_trigger_health_path = /health
http_trigger_trigger_path = /trigger

[gnome]
; Manage GNOME Custom Shortcuts from the app
manage_shortcuts = true
; Suggested bindings (examples)
binding_prompt = <Ctrl><Alt>p
binding_command = <Ctrl><Alt>m
binding_ui_show = <Ctrl><Alt>u

actions.json (example)
{
  "actions": [
    {
      "name": "Send to Local Trigger: prompt",
      "type": "http",
      "method": "POST",
      "url": "{config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}",
      "headers": {
        "Content-Type": "application/json"
      },
      "json": {
        "cmd": "prompt",
        "text": "{text}"
      }
    },
    {
      "name": "Send to Local Trigger: command",
      "type": "http",
      "method": "POST",
      "url": "{config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}",
      "headers": {
        "Content-Type": "application/json"
      },
      "json": {
        "cmd": "command",
        "text": "{text}"
      }
    },
    {
      "name": "Notify",
      "type": "shell",
      "command": "/usr/bin/notify-send",
      "args": ["Selection Bridge", "Text: {text}"]
    }
  ],
  "triggers": {
    "prompt": "Send to Local Trigger: prompt",
    "command": "Send to Local Trigger: command"
  }
}

Notes
- Placeholders may reference config values via `{config.section.key}` if desired.
- If `http_trigger_enabled = false`, HTTP actions referencing that config should be disabled in UI or return an error early.


## 11. Module Layout (Python)

Package name suggestion: `wbridge` (generic)

- wbridge/app.py
  - Gtk.Application initialization
  - Builds main window (tabs: History, Actions, Settings, Status)
  - Starts IPC server (Unix socket)
  - Logging setup

- wbridge/gui_window.py
  - History view: two lists (clipboard, primary), actions (apply, promote, send to action)
  - Actions view: manage actions.json, test action
  - Settings: toggle autostart, GNOME shortcut install/remove, configure integration
  - Status: environment info, clipboard monitoring status

- wbridge/history.py
  - Ring buffer for clipboard/primary
  - Deduplication and limits
  - API to get/apply/swap items

- wbridge/client_ipc.py
  - IPC server (GLib IO) and request dispatcher
  - Request/Response schemas and validation

- wbridge/cli.py
  - `wbridge` entry point (argparse)
  - Subcommands → build JSON requests → send to IPC

- wbridge/actions.py
  - Load/save actions.json
  - Placeholder substitution
  - HTTP runner (requests or urllib), shell runner (subprocess)
  - Optional per-action timeout
  - No retry/backoff/throttle in V1

- wbridge/config.py
  - Load settings.ini (configparser)
  - Expand `{config.*}` placeholder resolution

- wbridge/platform.py
  - Wayland/env detection
  - Active window info (best-effort; optional via compositor tools if present)
  - Paths (config, state, autostart)

- wbridge/gnome_shortcuts.py
  - Gio.Settings automation for custom keybindings
  - Create/update/remove functions

- wbridge/autostart.py
  - Create/remove `~/.config/autostart/wbridge.desktop`

- wbridge/logging_setup.py
  - File + console logger

- wbridge/profiles_manager.py
  - Profiles/Preset Manager API (list/show/install) inkl. Merge-/Backup-Strategie, Settings‑Patch (Whitelist), optionaler Shortcuts‑Installation
- Package Resources: wbridge/profiles/witsy/
  - profile.toml, actions.json, shortcuts.json, settings.patch.ini (werden via importlib.resources geladen)

Packaging
- pyproject.toml enthält Paket‑Daten für Profile:
  - [tool.setuptools.package-data]
    "wbridge.profiles" = ["**/*"]


## 12. Logging and Diagnostics

- Logging to console and to `~/.local/state/wbridge/bridge.log`.
- Levels: INFO by default, DEBUG optional (via env var or setting).
- IPC requests should emit brief logs (op, status, duration).
- Action execution logs: type, name, success/failure, elapsed time.


## 13. Security and Privacy

- IPC socket permissions: 0600 (owner-only). No TCP server in V1.
- No implicit data exfiltration; actions are explicit and configured by the user.
- HTTP actions: be cautious with external endpoints and sensitive text.
- Shell actions: default to subprocess without shell; if a shell is used, quoting must be explicit in the config.
- No global key capture; GNOME manages keybindings and executes our CLI.


## 14. Error Handling

- CLI exits non-zero if:
  - IPC server is not reachable.
  - Request rejected as invalid.
  - Action execution failed.
- Application shows a brief UI/notification log entry for failed actions.
- GNOME shortcut setup reports success/failure in the UI.
- No retries/backoff in V1; errors are reported immediately.


## 15. Implementation Plan

Phase 0 – Scaffold
- Create package structure, entry points:
  - `wbridge-app` → wbridge.app:main()
  - `wbridge` → wbridge.cli:main()
- Initialize logging, config dirs and files on first run.

Phase 1 – IPC + CLI
- Implement Unix socket server and basic request routing.
- Implement CLI subcommands: ui show, selection get/set, history list/apply/swap.

Phase 2 – History + GUI
- Implement GTK window with tabs:
  - History (clipboard/primary lists, context menu)
  - Actions (basic CRUD for actions.json, test button)
  - Settings (integration URL, GNOME shortcuts, autostart)
  - Status (env info)
- Hook up selection monitoring and history updates.

Phase 3 – Actions Engine
- Implement HTTP and shell action runners with placeholder substitution.
- Implement `triggers` mapping (trigger name to action name).
- Integrate `selection source` logic (--from-clipboard/--from-primary/--text).

Phase 4 – GNOME Integration + Autostart
- Implement Gio.Settings automation for custom keybindings.
- Implement autostart desktop file creation/removal.

Phase 5 – Polish
- Error messages, logging polish, documentation updates.
- Simple tests for IPC and placeholder substitutions.


## 16. Testing Checklist

Selections and History
- Clipboard and primary updates appear in the UI.
- Deduplication works (no repeated consecutive entries).
- Applying history items to clipboard/primary works.

CLI and IPC
- `wbridge ui show` brings the window to front.
- `wbridge history list/apply/swap` works with proper exit codes.
- `wbridge selection get/set` works.

Actions
- HTTP POST action sends selection text as configured.
- Shell action runs with substituted placeholders.

GNOME Shortcuts
- Install/remove works via app UI.
- Pressing the configured keys executes the intended CLI command.

Autostart
- Desktop entry created; app starts on login (normal visible window).

No Hidden Headless
- Ensure there is no unintended “hidden window” mode.


## 17. Appendix: Example GNOME Keybinding Setup (Gio)

Schema Keys
- org.gnome.settings-daemon.plugins.media-keys
  - custom-keybindings: array of object paths
- org.gnome.settings-daemon.plugins.media-keys.custom-keybinding
  - name (string)
  - command (string)
  - binding (string, e.g. <Ctrl><Alt>p)

Object Path Template
- /org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/wbridge-XXX/

Example Values
- name: "Bridge: Prompt"
- command: wbridge trigger prompt --from-primary
- binding: <Ctrl><Alt>p

The application should:
1) Read current array from `custom-keybindings`.
2) Add any missing paths.
3) Set name/command/binding for each path.
4) Write back the updated array.


## 18. Completeness Review (against requirements)

Covered in V1
- Wayland-friendly selection monitoring (GTK4/GDK only).
- History of clipboard and primary; promote any entry to clipboard/primary; swap latest two.
- IPC + CLI to run actions and manipulate history/selection.
- GNOME integration via Custom Shortcuts (no global key grabbing).
- Autostart via desktop entry.
- Optional, generic local HTTP trigger support via config (no product names).
- No retry/backoff/throttle; no wl-clipboard; no hidden headless; no tray.

Intentionally deferred/out of scope (V1)
- Automatic compositor-specific hotkey binding (Hyprland/Sway): can be added later.
- Persistence of history across restarts (optional future feature).
- Shell extension for GNOME (not needed for our keybinding model).
- Cross-platform implementations (see Section 20).

Risks/Notes
- Primary selection semantics vary by DE/app; GTK4 provides primary clipboard API; behavior depends on app support.
- No paste injection by design (Wayland security model).


## 19. Example Config Profile: Local Action Server (PR2-compatible)

This example shows how to configure a local HTTP trigger endpoint with command values like `prompt`, `command`, `chat`, etc. The endpoint is assumed to provide:
- GET /health → { ok: true }
- GET /trigger?cmd=...&text=...
- POST /trigger with JSON { "cmd": "...", "text": "..." }

Example settings.ini
[integration]
http_trigger_enabled = true
http_trigger_base_url = http://127.0.0.1:18081
http_trigger_health_path = /health
http_trigger_trigger_path = /trigger

Example actions.json (extended)
{
  "actions": [
    {
      "name": "Local Trigger: prompt",
      "type": "http",
      "method": "POST",
      "url": "{config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}",
      "headers": { "Content-Type": "application/json" },
      "json": { "cmd": "prompt", "text": "{text}" }
    },
    {
      "name": "Local Trigger: command",
      "type": "http",
      "method": "POST",
      "url": "{config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}",
      "headers": { "Content-Type": "application/json" },
      "json": { "cmd": "command", "text": "{text}" }
    },
    {
      "name": "Local Trigger: chat",
      "type": "http",
      "method": "GET",
      "url": "{config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}?cmd=chat"
    },
    {
      "name": "Local Trigger: scratchpad",
      "type": "http",
      "method": "GET",
      "url": "{config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}?cmd=scratchpad"
    },
    {
      "name": "Local Trigger: readaloud",
      "type": "http",
      "method": "GET",
      "url": "{config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}?cmd=readaloud"
    },
    {
      "name": "Local Trigger: transcribe",
      "type": "http",
      "method": "GET",
      "url": "{config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}?cmd=transcribe"
    },
    {
      "name": "Local Trigger: realtime",
      "type": "http",
      "method": "GET",
      "url": "{config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}?cmd=realtime"
    },
    {
      "name": "Local Trigger: studio",
      "type": "http",
      "method": "GET",
      "url": "{config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}?cmd=studio"
    },
    {
      "name": "Local Trigger: forge",
      "type": "http",
      "method": "GET",
      "url": "{config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}?cmd=forge"
    }
  ],
  "triggers": {
    "prompt":   "Local Trigger: prompt",
    "command":  "Local Trigger: command",
    "chat":     "Local Trigger: chat",
    "scratchpad":"Local Trigger: scratchpad",
    "readaloud":"Local Trigger: readaloud",
    "transcribe":"Local Trigger: transcribe",
    "realtime": "Local Trigger: realtime",
    "studio":   "Local Trigger: studio",
    "forge":    "Local Trigger: forge"
  }
}

Notes
- For long multi-line text, prefer the POST actions with JSON body.
- If the endpoint is disabled, the app should indicate that these actions are unavailable.


## 20. Cross-Platform Considerations (macOS, Windows 11)

General strategy
- Keep core modular and abstract platform differences behind interfaces.
- V1 targets Wayland/Linux; this section outlines what would be needed for other OSes.

macOS (suggested approach)
- Selections:
  - Clipboard only (primary selection concept does not exist).
  - Use AppKit NSPasteboard via PyObjC or a separate helper.
- Global shortcuts:
  - Use macOS system shortcuts to execute the CLI (analogous to GNOME Custom Shortcuts).
  - Alternatively, implement a small helper using Carbon/IOHID for RegisterEventHotKey (requires app entitlements, more complex).
- Autostart:
  - LaunchAgent (~/Library/LaunchAgents) with a plist that runs the app at login.
- IPC:
  - Unix domain sockets supported; keep the same IPC client/server.
- UI:
  - PyGObject GTK4 works on macOS but requires setup; alternatively use a native UI in a separate path (out of scope for V1).

Windows 11 (suggested approach)
- Selections:
  - Clipboard via Windows API (pywin32). No primary selection concept.
- Global shortcuts:
  - Windows allows RegisterHotKey; however, the V1 model prefers system shortcuts that execute CLI (Task Scheduler shortcuts or third-party tooling).
- Autostart:
  - Startup folder shortcut or registry Run key (HKCU\Software\Microsoft\Windows\CurrentVersion\Run).
- IPC:
  - Replace Unix socket with Named Pipes; provide an IPC transport abstraction to keep CLI semantics identical.
- UI:
  - GTK on Windows is possible; ensure the runtime is packaged accordingly (later effort).

Conclusion
- Introduce `SelectionProvider`, `ShortcutProvider`, `AutostartProvider`, and `IPCTransport` abstractions to facilitate future ports.


## 21. Modularity Review and Extensibility

The proposed module layout is sufficiently modular for V1. To strengthen extensibility:
- Define interfaces (protocols) and inject implementations:
  - SelectionProvider: get/set clipboard/primary (Linux implementation uses GTK4/GDK).
  - HistoryStore: in-memory ring; later add persistence via JSON/SQLite.
  - IPCTransport: Unix domain sockets now; Named Pipes for Windows later.
  - ActionRunner: HTTPActionRunner and ShellActionRunner; can add others (e.g., DBusActionRunner).
  - ShortcutManager: GNOME Custom Shortcuts now; Hyprland/Sway or Windows/macOS providers later.
  - AutostartManager: desktop file now; LaunchAgent/Registry later.
- Keep placeholder expansion in a separate module to reuse across action types.
- Decouple UI from execution: UI calls into services that do not depend on Gtk widgets (testable).


## 22. Reference Code Snippets (PoC-inspired)

Clipboard monitoring (GTK4/GDK, Python)
```python
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
from gi.repository import Gtk, Gdk, GLib

POLL_INTERVAL_MS = 300
history_clip = []
history_prim = []
max_history = 50
cache_clip = None
cache_prim = None

class Window(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("Selection Bridge")
        self.set_default_size(600, 400)
        self.display = self.get_display()
        self.clipboard = self.display.get_clipboard()
        self.primary = self.display.get_primary_clipboard()
        GLib.timeout_add(POLL_INTERVAL_MS, self.poll)

    def poll(self):
        self.clipboard.read_text_async(None, self._on_read, "clipboard")
        self.primary.read_text_async(None, self._on_read, "primary")
        return True

    def _on_read(self, source, res, which):
        global cache_clip, cache_prim
        try:
            text = source.read_text_finish(res)
            if not text or not text.strip():
                return
            if which == "clipboard":
                if text != cache_clip:
                    cache_clip = text
                    history_clip.insert(0, text)
                    if len(history_clip) > max_history:
                        history_clip.pop()
            else:
                if text != cache_prim:
                    cache_prim = text
                    history_prim.insert(0, text)
                    if len(history_prim) > max_history:
                        history_prim.pop()
        except GLib.Error:
            pass

class App(Gtk.Application):
    def do_activate(self):
        win = self.props.active_window or Window(self)
        win.present()

def main(argv=None):
    app = App()
    return app.run(argv or [])

if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv))
```

Set selection from history (GTK4/GDK)
```python
def set_clipboard_text(display: Gdk.Display, text: str):
    cb = display.get_clipboard()
    cb.set_text(text)

def set_primary_text(display: Gdk.Display, text: str):
    prim = display.get_primary_clipboard()
    prim.set_text(text)
```

Unix socket IPC server (newline-delimited JSON)
```python
import socket, json, os, selectors

SOCK_PATH = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "wbridge.sock")

def serve(handler):
    sel = selectors.DefaultSelector()
    if os.path.exists(SOCK_PATH):
        os.remove(SOCK_PATH)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(SOCK_PATH)
    os.chmod(SOCK_PATH, 0o600)
    srv.listen(5)
    sel.register(srv, selectors.EVENT_READ)

    def accept(sock):
        conn, _ = sock.accept()
        conn.setblocking(False)
        sel.register(conn, selectors.EVENT_READ)

    def read(conn):
        data = conn.recv(65536)
        if not data:
            sel.unregister(conn); conn.close(); return
        for line in data.splitlines():
            try:
                req = json.loads(line.decode("utf-8"))
                resp = handler(req)
            except Exception as e:
                resp = {"ok": False, "error": str(e)}
            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))

    try:
        while True:
            for key, _ in sel.select():
                if key.fileobj is srv:
                    accept(srv)
                else:
                    read(key.fileobj)
    finally:
        srv.close()
        if os.path.exists(SOCK_PATH):
            os.remove(SOCK_PATH)
```

CLI client request
```python
def cli_request(obj: dict) -> int:
    import sys
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "wbridge.sock")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(path)
            s.sendall((json.dumps(obj) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk: break
                data += chunk
        resp = json.loads(data.decode("utf-8"))
        if resp.get("ok"):
            return 0
        else:
            print(resp.get("error", "error"), file=sys.stderr)
            return 3
    except FileNotFoundError:
        print("server not running", file=sys.stderr)
        return 1
```

HTTP action execution (requests)
```python
import requests

def run_http_action(url: str, method: str = "POST", headers=None, json_body=None, timeout=5):
    headers = headers or {"Content-Type": "application/json"}
    if method.upper() == "GET":
        r = requests.get(url, headers=headers, timeout=timeout)
    else:
        r = requests.post(url, headers=headers, json=json_body, timeout=timeout)
    r.raise_for_status()
    return r.status_code
```

GNOME Custom Shortcuts via Gio.Settings
```python
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio

def install_gnome_shortcut(path_suffix: str, name: str, command: str, binding: str):
    base_schema = "org.gnome.settings-daemon.plugins.media-keys"
    custom_schema = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
    base = Gio.Settings.new(base_schema)
    paths = list(base.get_strv("custom-keybindings"))

    path = f"/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/{path_suffix}/"
    if path not in paths:
        paths.append(path)
        base.set_strv("custom-keybindings", paths)

    custom = Gio.Settings.new_with_path(custom_schema, path)
    custom.set_string("name", name)
    custom.set_string("command", command)
    custom.set_string("binding", binding)

# Example:
# install_gnome_shortcut("wbridge-prompt", "Bridge: Prompt", "wbridge trigger prompt --from-primary", "<Ctrl><Alt>p")
```

Notes
- These snippets are illustrative; production code should add validation, logging, and error handling as outlined elsewhere in this document.


## 23. Implementation Checklist (Progress Tracking)

Scaffold
- [x] Package structure created
- [x] Entry points (`wbridge-app`, `wbridge`) defined
- [x] Logging and config directories initialized

IPC + CLI
- [x] Unix socket server with request routing
- [x] CLI: `ui show`
- [x] CLI: `selection get/set`
- [x] CLI: `history list/apply/swap`

History + GUI
- [x] GTK window with tabs (History, Actions, Settings, Status)
- [x] Clipboard/Primary monitoring wired
- [x] History context actions (promote to clipboard/primary, swap)

Actions Engine
- [x] Placeholder substitution
- [x] HTTP action runner
- [x] Shell action runner
- [x] `triggers` mapping (name → action)

Profiles & Presets
- [x] ProfileManager + CLI (profile list/show/install)
- [x] Built-in Profil „Witsy“ als Paketressource
- [x] Settings‑UI: Profile‑Bereich (Dropdown/Anzeigen/Installieren), Integration‑Status
- [x] Actions‑Tab: Hinweis/Disable bei http_trigger_enabled = false

GNOME Integration + Autostart
- [ ] GNOME Custom Shortcuts create/update/remove (Gio.Settings)
- [ ] Autostart desktop file create/remove
- [ ] Suggested shortcuts installable from UI

Configuration
- [x] settings.ini handling
- [x] actions.json handling
- [x] Optional local HTTP trigger profile supported

Testing and Docs
- [ ] Manual tests per checklist
- [ ] Update DESIGN.md if decisions change
- [ ] Prepare quickstart guide (future)

## 24. Clipboard Implementation Notes (GTK4/PyGObject, Wayland)

Summary
- For plain text, prefer Clipboard.set("...") in GTK4; PyGObject handles the GValue internally.
- For advanced cases, use Gdk.ContentProvider with a retained reference to avoid early GC.
- Ensure all clipboard operations run on the GTK main thread (use GLib.idle_add from worker threads).
- Primary selection is supported but compositor/app-dependent under Wayland.

Verified approach (strings)
- Write:
  - display = Gdk.Display.get_default()
  - clipboard = display.get_clipboard()  # or get_primary_clipboard()
  - clipboard.set("Hello World")  # PyGObject converts to GValue(gchararray)
- Read (async):
  - clipboard.read_text_async(None, callback)
  - text = clipboard.read_text_finish(result)

Fallback (provider, with retention)
- If Clipboard.set is not available on the binding, use:
  - val = GObject.Value(); val.init(str); val.set_string(text)
  - provider = Gdk.ContentProvider.new_for_value(val)
  - clipboard.set_content(provider)
- Important: retain provider (e.g., keep in a list attribute) until another owner takes the clipboard.

Threading/Timing
- Schedule set/get via GLib.idle_add in main thread.
- Allow small delays between set and subsequent get in automated tests.

Backend checks
- Prefer native Wayland backend when running on Wayland:
  - Environment variable: GDK_BACKEND=wayland (for testing)
  - Detect backend via type names if needed (e.g., GdkWaylandDisplay).

Documentation/Research

## 25. Profiles & Presets (Konfigurations-Bundles)

Ziele
- Out-of-the-box Konfigurationen („Profile“) installierbar machen, um wbridge schnell nutzbar zu machen.
- Ein Profil enthält mindestens: actions.json (inkl. triggers), optional shortcuts.json (empfohlene GNOME‑Shortcuts) und settings.patch.ini (gezieltes Patchen whitelisted Settings).
- Installation via CLI und UI (Settings‑Tab) mit Backup- und Merge-Strategie; alles lokal im Benutzerkontext.

Begriffe und Dateien
- Built-in Profile (im Paket ausgeliefert): src/wbridge/profiles/<name>/
  - profile.toml (Metadaten: name, version, description, includes)
  - actions.json (Pflicht; HTTP/Shell Actions inkl. triggers)
  - shortcuts.json (empfohlene GNOME Shortcuts, optional)
  - settings.patch.ini (optionale Patches, whitelisted Keys)
- User-Konfiguration:
  - ~/.config/wbridge/actions.json (User Actions/Triggers)
  - ~/.config/wbridge/settings.ini (User Settings)
  - GNOME Custom Shortcuts via Gio.Settings (Install/Remove durch UI/CLI)

Datenformate
- profile.toml:
  name = "witsy"
  version = "1.0.0"
  description = "Witsy local HTTP trigger integration (PR2)"
  includes = ["actions.json", "shortcuts.json", "settings.patch.ini"]

- shortcuts.json:
  {
    "shortcuts": [
      { "name": "Bridge: Prompt", "command": "wbridge trigger prompt --from-primary", "binding": "<Ctrl><Alt>p" },
      { "name": "Bridge: Command", "command": "wbridge trigger command --from-clipboard", "binding": "<Ctrl><Alt>m" },
      { "name": "Bridge: Show UI", "command": "wbridge ui show", "binding": "<Ctrl><Alt>u" }
    ]
  }

- settings.patch.ini (nur whitelisted Keys):
  [integration]
  http_trigger_enabled = true
  http_trigger_base_url = http://127.0.0.1:18081
  http_trigger_trigger_path = /trigger
  ; http_trigger_health_path = /health (optional)

ProfileManager (Spezifikation)
- list_builtin_profiles() -> List[str]
- show_profile(name: str) -> Dict (Metadaten + Kerninhalte)
- install_profile(name: str, options) -> Report
  options:
    - overwrite_actions: bool (default false)
    - patch_settings: bool (default false)
    - install_shortcuts: bool (default false)
    - dry_run: bool (default false)
  Verhalten:
    - actions.json: Merge mit ~/.config/wbridge/actions.json (siehe Merge-Strategie)
    - settings.patch.ini: gezieltes Patchen erlaubter Keys in settings.ini
    - shortcuts.json: Installation via Gio.Settings (Konflikte melden; kein hard overwrite)
    - pro Schritt Backups erstellen; Report mit Änderungen/Backups/Fehlern zurückgeben

CLI-Erweiterungen
- wbridge profile list
  - Ausgabe: Liste verfügbarer Profile (z. B. ["witsy"])
- wbridge profile show --name witsy
  - Ausgabe: Metadaten und Kerninhalte (Actions/Triggers, Shortcuts, Settings-Patch)
- wbridge profile install --name witsy [--overwrite-actions] [--patch-settings] [--install-shortcuts] [--dry-run]
  - Exit-Codes: 0 OK, 2 invalid args, 3 failure
  - Ausgabe: Zusammenfassung inkl. Pfaden zu Backups

UI (Settings-Tab)
- Bereich „Profile“:
  - Auswahl (Dropdown) verfügbarer Profile; Buttons „Anzeigen“, „Installieren…“
  - Installationsdialog mit Checkboxen:
    - Actions installieren/überschreiben
    - Settings patchen
    - Shortcuts installieren
  - Ergebnis-/Fehlerlabel (kurze Zusammenfassung)
- Bereich „Integration Status“:
  - Anzeige integration.http_trigger_enabled, Base-URL, Trigger-Pfad
  - Deutlicher Hinweis, wenn disabled → Actions-Tab entsprechend markieren/disable Run

Merge-/Backup-Strategie
- Backups:
  - actions.json.bak-YYYYmmdd-HHMMSS (vor Änderungen)
  - settings.ini.bak-YYYYmmdd-HHMMSS (vor Änderungen)
- actions.json:
  - actions: Kollision anhand name
    - default: User first (keine Überschreibung)
    - --overwrite-actions: Profil-Action ersetzt vorhandene gleichnamige
  - triggers: neue hinzufügen; Kollision:
    - default: User first
    - --overwrite-actions: überschreiben
- settings.ini Patch:
  - Nur Keys in [integration]: http_trigger_enabled, http_trigger_base_url, http_trigger_trigger_path, http_trigger_health_path
  - default: behalten (User first), nur überschreiben wenn --patch-settings
- shortcuts:
  - Installation optional; Konflikte (belegte Bindings) melden; kein erzwungenes Überschreiben

Sicherheit & Fehler
- Profile liefern nur lokale HTTP-Ziele (127.0.0.1); keine externen Endpunkte per Default-Profil.
- Kein Retry/Backoff in V1 (konform); klare Fehleranzeigen im CLI/UI.
- requests ist optional; wenn fehlt, werden http-actions mit klarer Fehlermeldung quittiert.

Implementierungs-Hinweise (Profiles)
- Built-in Profile Pfade: src/wbridge/profiles/<name>/
  - Laden via importlib.resources (Python 3.11+):
    - from importlib.resources import files
    - base = files("wbridge.profiles").joinpath("witsy")
- Kollisions-Identität:
  - Actions: exakter name (case-sensitive 1:1 Vergleich)
  - Triggers: exakter Alias-Key im triggers-Objekt (case-sensitive)
- Report-Schema install_profile (Empfehlung für CLI/UI):
  {
    "ok": true,
    "actions": {"added": N1, "updated": N2, "skipped": N3, "backup": "/path/to/actions.json.bak-..."},
    "settings": {"patched": ["key1","key2"], "skipped": ["key3"], "backup": "/path/to/settings.ini.bak-..."},
    "shortcuts": {"installed": M1, "skipped": M2},
    "dry_run": true,
    "errors": []
  }
- UI-Konkretisierung:
  - Settings‑Tab: Inline‑Bedienelemente (Dropdown „Profil“, Checkboxen „Actions/Settings/Shortcuts“, Button „Installieren“, Ergebnislabel). Kein modaler Dialog nötig.
  - Actions‑Tab: Wenn integration.http_trigger_enabled=false → Run‑Buttons disabled und kurzer Hinweis „HTTP Trigger disabled – in Settings aktivieren“.
- Optional-Dependency:
  - Fehlt requests, liefern http‑Actions einen klaren Fehlertext (z. B. „python-requests is not installed; install the 'http' extra“), der im UI/CLI angezeigt wird.

## 26. Witsy‑Profil (Profile/Preset für Witsy PR2)

Quelle
- Aus /home/tim/IMPLEMENTATION_WAYLAND_MINIMAL_HTTP.md:
  - Lokaler HTTP-Server (opt-in), 127.0.0.1, Default-Port 18081
  - API:
    - GET /health → { ok: true }
    - GET /trigger?cmd=...&text=...
    - POST /trigger { "cmd": "...", "text": "..." }
  - cmd-Werte: prompt | chat | scratchpad | command | readaloud | transcribe | realtime | studio | forge
  - Text: für prompt/command optional; für andere üblicherweise ohne text

Actions (Profil actions.json)
- Mit Text (POST/JSON):
  - "Witsy: prompt" → POST {cmd:"prompt", text:"{text}"}
  - "Witsy: command" → POST {cmd:"command", text:"{text}"}
- Ohne Text (GET):
  - "Witsy: chat" → GET ?cmd=chat
  - "Witsy: scratchpad" → GET ?cmd=scratchpad
  - "Witsy: readaloud" → GET ?cmd=readaloud
  - "Witsy: transcribe" → GET ?cmd=transcribe
  - "Witsy: realtime" → GET ?cmd=realtime
  - "Witsy: studio" → GET ?cmd=studio
  - "Witsy: forge" → GET ?cmd=forge
- Gemeinsame URL:
  - {config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}
  - Default via settings.patch.ini: http://127.0.0.1:18081 und /trigger

Triggers (Profil)
{
  "prompt":   "Witsy: prompt",
  "command":  "Witsy: command",
  "chat":     "Witsy: chat",
  "scratchpad":"Witsy: scratchpad",
  "readaloud":"Witsy: readaloud",
  "transcribe":"Witsy: transcribe",
  "realtime": "Witsy: realtime",
  "studio":   "Witsy: studio",
  "forge":    "Witsy: forge"
}

Shortcuts (Empfehlung shortcuts.json)
- Prompt (Primary als Quelle): wbridge trigger prompt --from-primary → <Ctrl><Alt>p
- Command (Clipboard als Quelle): wbridge trigger command --from-clipboard → <Ctrl><Alt>m
- Show UI: wbridge ui show → <Ctrl><Alt>u
- Weitere cmd ohne Default-Bindings; können im UI benannt/vorgeschlagen werden.

Settings-Patch (settings.patch.ini)
[integration]
http_trigger_enabled = true
http_trigger_base_url = http://127.0.0.1:18081
http_trigger_trigger_path = /trigger
; http_trigger_health_path = /health

Actions‑Tab Verhalten
- Wenn http_trigger_enabled=false → Run disabled oder deutlicher Hinweis („HTTP Trigger disabled“).
- Quelle: Clipboard/Primary/Text; bei „Text“ ein Eingabefeld aktiv.
- Ergebnis: Success/Failed + Message (HTTP‑Status/Fehlertext); bei fehlendem requests klarer Hinweis.

## 27. Testplan (manuell)

Profil-Erkennung/Anzeige
- CLI: wbridge profile list → enthält „witsy“
- CLI: wbridge profile show --name witsy → Metadaten + Kerninhalte
- UI (Settings): Dropdown zeigt „Witsy“; „Anzeigen“ zeigt Kurzinfo

Trockenlauf
- wbridge profile install --name witsy --dry-run → listet geplante Änderungen (Backups, Merges), keine Schreibzugriffe

Installation Actions/Settings
- Actions:
  - wbridge profile install --name witsy --overwrite-actions
  - Prüfen: ~/.config/wbridge/actions.json enthält „Witsy: …“; triggers vollständig
  - Backup: actions.json.bak-YYYYmmdd-HHMMSS existiert
- Settings:
  - wbridge profile install --name witsy --patch-settings
  - Prüfen: settings.ini [integration] Werte gesetzt, Backup existiert

Shortcuts
- wbridge profile install --name witsy --install-shortcuts
- GNOME Einstellungen: Pfade/Bindings sichtbar; Konflikte werden gemeldet

Actions‑Tab
- http_trigger_enabled=true; Witsy läuft (Health check):
  - Quelle=Text → „Hallo Welt“ → Run „Witsy: prompt“ → Success; Witsy‑Log zeigt Request
  - Quelle=Clipboard → zuvor per CLI/WYSIWYG setzen; Run „Witsy: command“ → Success
  - Aktion ohne Text (z. B. „Witsy: chat“) → Run → Success
- Disabled‑Zustand:
  - http_trigger_enabled=false → Run disabled oder klarer Hinweis

CLI Trigger Smoke‑Tests
- wbridge trigger prompt --from-primary
- wbridge trigger chat --from-clipboard (ohne text)

Fehlerfälle
- Kein requests installiert → http action Failed: „python-requests not installed“ (o. ä.)
- Witsy nicht aktiv → HTTP Fehler; UI zeigt Failed + Message (HTTPCode/ConnectionError)

Akzeptanzkriterien
- Witsy‑Profil vollständig installierbar (Actions/Triggers, optional Settings/Shortcuts) mit Backups und Merge nach Regeln.
- CLI/GUI verhalten sich wie spezifiziert; Actions‑Tab liefert Ergebnisse/Fehler klar aus.
- Doku-Abschnitte (dieser) enthalten alle notwendigen Informationen zur Umsetzung/Tests.

## 28. Nächste Schritte (Implementierung; Folge-Session)
- Autostart: Implementierung von `autostart.py` und UI‑Buttons (aktivieren/deaktivieren).
- GNOME Shortcuts: UI‑Buttons in Settings funktionsfähig machen (Install/Remove der empfohlenen Shortcuts), Fehler-/Konfliktanzeige.
- Tests/Docs: Manuelle Tests gemäß Checkliste (Abschnitt 27) dokumentieren; README Quickstart ggf. erweitern (Screenshots/Fehlermeldungen).
- Stabilität: kleinere UX‑Polish im Actions‑Tab (z. B. Statusfarben), Logging‑Details (Aktionen mit Dauer/Fehlercodes).
- Packaging: optionaler Smoke‑Test Wheel/SDist, Verifikation der Profil‑Ressourcen im Paket.

## 29. Geplante Erweiterungen – Settings Reload, Inline‑Edit, Health‑Check, Config‑CLI, Profile‑Shortcuts Uninstall

Ziel
- Laufenden Zustand nach Profil‑Install/CLI‑Änderungen zuverlässig übernehmen (ohne App‑Neustart).
- Integration‑Werte direkt in der UI bearbeiten (whitelisted Keys).
- Optionalen Health‑Check für lokale HTTP‑Trigger anzeigen.
- CLI‑Kommandos für Config‑Reset/Backup/Restore bereitstellen.
- Profil‑Shortcuts wieder entfernen können (nur die durch ein Profil installierten).

Änderungen (funktional)
1) Settings Reload
   - GUI: Nach erfolgreicher Profil‑Installation (Settings‑Tab) → Settings neu laden, Integrations‑Status + Actions‑Liste refreshen.
   - GUI: „Reload Settings“‑Button.
   - Optional: Gio.FileMonitor auf ~/.config/wbridge/settings.ini und ~/.config/wbridge/actions.json (Auto‑Reload + UI Refresh).

2) Inline‑Edit der Integration
   - Settings‑Tab: Switch (integration.http_trigger_enabled), Entry (integration.http_trigger_base_url), Entry (integration.http_trigger_trigger_path).
   - Atomare Saves (temp + replace), Validierung (Base‑URL http/https; Trigger‑Pfad beginnt mit „/“).
   - Nach Speichern: Status + Actions refresh; „Verwerfen“ lädt Settings erneut.

3) Health‑Check (optional)
   - Button „Health check“ → GET {base_url}{health_path} (Default /health).
   - Anzeige OK/Fehler (HTTP‑Code), optionale Farbindikation.

4) Config‑CLI (optional)
   - wbridge config show-paths
   - wbridge config reset [--keep-actions] [--keep-settings] [--backup]
   - wbridge config backup [--what actions|settings|all]
   - wbridge config restore --file /path/to/backup

5) Profile‑Shortcuts Uninstall (optional)
   - profiles_manager.remove_profile_shortcuts(name): liest shortcuts.json des Profils, berechnet Suffixe „wbridge-<normalized-name>/“, entfernt entsprechende Einträge via Gio.Settings.
   - CLI: wbridge profile uninstall --name NAME --shortcuts-only
   - GUI: Button „Profil‑Shortcuts entfernen“ im Profil‑Bereich.

Technische Hinweise
- Settings‑Reload: app._settings = load_settings(); anschließend self._refresh_integration_status(); self.refresh_actions_list().
- FileMonitor: Gio.File.new_for_path(...).monitor_file(...); on change → (debounced) reload + refresh.
- Atomare Writes: wie in profiles_manager (tempfile + os.replace).
- HTTP Health‑Check: requests falls verfügbar, sonst urllib Request; Timeouts kurz halten (z. B. 1–2 s).
- Shortcuts‑Remove: Nur Suffixe aus dem Profil entfernen; keine anderen Custom‑Keybindings ändern.

Akzeptanzkriterien
- Nach Profil‑Install oder CLI‑Änderungen werden Integration‑Status und Actions‑Enable ohne App‑Neustart korrekt aktualisiert.
- Inline‑Edit speichert/validiert Werte; UI zeigt sie unmittelbar; Actions‑Run reagiert.
- Health‑Check zeigt korrekten Status (OK bei laufendem Dienst, Fehler sonst).
- Config‑Reset/Backup/Restore funktioniert nachvollziehbar; Pfade werden ausgewiesen.
- Profil‑Shortcuts lassen sich gezielt entfernen, ohne fremde Shortcuts zu beeinflussen.

Testplan (manuell)
1) Disabled → Enabled nach Profil‑Install:
   - Ausgang: http_trigger_enabled=false
   - wbridge profile install --name witsy --patch-settings
   - Erwartet: Status=enabled, Actions‑Run aktiv; Health‑Check OK (bei laufendem Dienst).

2) Inline‑Edit:
   - base_url/trigger_path im UI ändern → Speichern
   - settings.ini enthält neue Werte; UI/Actions aktualisiert.

3) Health‑Check:
   - Dienst aus → Fehler; Dienst an → OK.

4) Config‑CLI:
   - show-paths: Pfade werden angezeigt
   - reset --backup: Backups vorhanden; Dateien entfernt; UI zeigt Defaults
   - backup/restore: Dateien werden wiederhergestellt.

5) Profile‑Shortcuts Uninstall:
   - Installiere Profil‑Shortcuts; anschließend uninstall --shortcuts-only → Einträge entfernt.

6) FileMonitor (falls aktiviert):
   - settings.ini extern editieren → UI aktualisiert automatisch.

Hinweise für Doku
- README: Hinweise zu „Reload Settings“, Health‑Check, Config‑CLI ergänzen; expliziter Hinweis: Nach CLI‑Profil‑Install ggf. „Reload Settings“ ausführen (oder FileMonitor aktivieren).
- IMPLEMENTATION_LOG: neuen Eintrag nach Umsetzung mit Datum, Änderungen, Tests, offenen Punkten.

## 30. Änderungen 2025‑08‑14 (Implementiert)

Kurzüberblick
- Actions‑Editor (Phase 1, Raw‑JSON) im Actions‑Tab:
  - Je Aktion ein Expander mit Kopfzeilen‑Preview (Name, Typ, Kurzinfo).
  - Inline Raw‑JSON‑Editor (monospaced) mit Buttons: Run, Save, Cancel, Duplicate, Delete.
  - „Add Action“ fügt Standard‑HTTP‑Aktion hinzu.
  - Save/Duplicate/Delete schreiben atomar nach ~/.config/wbridge/actions.json (Timestamp‑Backups).
  - Validierung per `validate_action_dict()` (http/shell Felder).
  - Nach Änderungen: `load_actions()` + UI‑Refresh.
- Triggers‑Editor (Alias → Action) im Actions‑Tab:
  - Liste der Trigger mit Editier‑Zeilen (Alias als Entry, Action als ComboBox), „Add Trigger“, „Save Triggers“, „Delete“ pro Zeile.
  - Validierung (keine doppelten Aliase; Action‑Name muss existieren); atomarer Write via `write_actions_config`, anschließend Reload + UI‑Refresh.
- Settings: Reload/Inline‑Edit/Health‑Check
  - Nach Profil‑Installation werden Settings re‑geladen; Integration‑Status + Actions‑Enable aktualisieren sich (Fix für „Run bleibt disabled“).
  - Inline‑Edit für `integration.http_trigger_enabled`, `integration.http_trigger_base_url`, `integration.http_trigger_trigger_path` (Validierung + atomare INI‑Writes).
  - „Reload Settings“‑Button; „Health check“ (GET base+health_path).
- UI‑Fix (Wrapping)
  - PRIMARY/Clipboard „Aktuell:“‑Labels und History‑Zeilen umbrechen hart (Pango WrapMode CHAR), begrenzen Breite (`max_width_chars`), verhindern Fenster‑Verbreiterung.

Technische Details
- Neue/erweiterte Helfer (config.py):
  - `load_actions_raw()` – rohes Laden von actions.json
  - `write_actions_config(data)` – atomarer JSON‑Write + Timestamp‑Backup
  - `validate_action_dict(action)` – Minimalvalidierung (http/shell)
  - `set_integration_settings(...)` – atomare INI‑Updates für [integration]
- GUI (gui_window.py):
  - Actions‑Editor (Raw‑JSON) mit Save/Cancel/Duplicate/Delete + Add Action
  - Settings‑Reload nach Profil‑Install, Inline‑Edit, Health‑Check
  - Label‑Wrapping für „Aktuell:“ + History‑Zeilen

Bekannte offene Punkte (geplant, siehe Abschnitt 29)
- Formular‑Modus für Actions (Feld‑basierte UI statt Raw‑JSON).
- Triggers‑Editor im Actions‑Tab (alias → action.name).
- Config‑CLI: show‑paths, reset, backup/restore.
- Gio.FileMonitor auf settings.ini/actions.json für Auto‑Reload.
- Profile‑Shortcuts Uninstall (CLI/UI).

Tests (Kurz)
- Aktionen editieren/speichern/duplizieren/löschen → Backups angelegt, Liste reloaded, Run funktioniert.
- Settings Inline‑Edit/Reload/Health‑Check → Status/Actions aktualisieren sich ohne App‑Neustart.
- Lange PRIMARY/Clipboard‑Inhalte → Labels umbrechen, Fenster bleibt stabil.

## 31. Änderungen 2025‑08‑16 (Optionales Cleanup + PATH‑Hinweis)

Kurzüberblick
- CLI – Wartungs-/Cleanup-Befehle ergänzt:
  - profile uninstall --shortcuts-only
  - shortcuts remove --recommended
  - autostart disable
- Config-CLI erweitert:
  - config show-paths [--json]
  - config backup [--what actions|settings|all]
  - config reset [--keep-actions] [--keep-settings] [--backup]
  - config restore --file PATH
- GUI – Settings PATH-Hinweis:
  - Wenn shutil.which("wbridge") None ergibt, wird ein Hinweis angezeigt, dass GNOME Custom Shortcuts den Befehl ggf. nicht finden (absolute Pfade empfohlen).

Details
- Die zusätzlichen CLI-Kommandos sind nicht destruktiv per Default; Backups sind timestamped (…bak-YYYYmmdd-HHMMSS).
- Shortcuts-Entfernung wirkt nur auf die vordefinierten bzw. profilinstallierten Suffixe, andere benutzerdefinierte Bindings bleiben unberührt.
- Autostart disable entfernt ~/.config/autostart/wbridge.desktop atomar.

Smoke-Tests (manuell)
- wbridge profile uninstall --name witsy --shortcuts-only → entfernt Profil-Shortcuts (Suffixe wbridge-…/)
- wbridge shortcuts remove --recommended → OK
- wbridge autostart disable → OK/FAILED abhängig von existierender Desktop-Datei
- wbridge config show-paths|backup|reset|restore → Pfade/Backups/Restore geprüft

Doku-Hinweis
- README sollte einen kurzen „PATH/absolute Pfade“-Hinweis enthalten, damit GNOME Shortcuts „wbridge“ sicher finden.
