# Selection/Shortcut Bridge (Wayland) – Design Specification (V2)

Status: Stable (V2)  
Scope: Linux (Wayland), GNOME primary; others may work but are not a focus in V2  
Audience: Implementers and maintainers

This document specifies a general-purpose desktop bridge that:
- Monitors text selections (clipboard and primary selection) reliably on Wayland using GTK4/GDK only.
- Maintains a history and lets users promote any history item to clipboard or primary selection.
- Exposes a local CLI to trigger actions (HTTP or shell commands) that can consume the current selection or history entries.
- Integrates with GNOME via Custom Shortcuts (global keybindings) that execute the CLI (no global key grabbing).
- Uses settings.ini as the single source of truth for Endpoints, Secrets, and GNOME Shortcuts (hard switch to V2 model).
- Supports curated Profiles that merge actions/triggers/config into the user’s configuration (no dconf writes).

No hidden headless mode, no tray icon, no wl-clipboard dependency, no key injection.


## 0. Background & Motivation

Wayland restricts global hotkeys and key injection. The project provides a robust, Wayland‑friendly workflow using:
- GNOME Custom Shortcuts that invoke our CLI (no key grabs).
- A GTK4 app that performs selection reads and runs configured actions over IPC.

V2 change: Configuration is fully consolidated in settings.ini under:
- [endpoint.<id>]
- [secrets]
- [gnome] and [gnome.shortcuts]

Legacy [integration.*] is removed without migration paths. Actions use placeholders such as:
- `{config.endpoint.<id>.*}` and `{config.secrets.*}`


## 1. Goals and Non-Goals

Goals
- Wayland-friendly selection workflow without key grabs or injection.
- Configurable actions (HTTP/Shell) with placeholder expansion drawing from current selection and config.
- Deterministic GNOME Shortcuts synchronization from settings.ini.
- Profiles that merge content into settings.ini/actions.json (no direct dconf writes).
- Simplicity and maintainability (GTK4, standard Python libs).

Non-Goals
- No global key grabbing or key injection.
- No hidden background/headless app.
- No wl-clipboard dependency.
- No retry/backoff logic for actions in V2.


## 2. Environment and Assumptions

- Wayland session (XDG_SESSION_TYPE=wayland).
- GNOME is the primary target.
- Python 3 + PyGObject (GTK 4) from distro packages.
- Optional HTTP actions depend on standard libs (+ requests only if enabled).


## 3. High-Level Architecture

Components
- GUI Application (GTK4)
  - Pages: History, Actions, Triggers, Shortcuts, Settings, Status.
  - Runs GLib main loop and hosts IPC server.
  - Auto-reloads settings/actions on file changes.

- IPC Server (Unix Domain Socket – NDJSON)
  - Handles selection/history/actions requests.

- CLI Client (wbridge)
  - Sends JSON requests to the running app (used by GNOME Shortcuts).

- Configuration
  - settings.ini (V2: Endpoints/Secrets/GNOME Shortcuts/general).
  - actions.json (actions + triggers).

- GNOME Shortcuts Sync
  - Deterministic scope via `wbridge-<slug>/` suffix.
  - Based on [gnome.shortcuts] mapping when Auto‑apply is enabled.

Data Flow (example)
1) GNOME executes a CLI command (`wbridge trigger prompt --from-primary`).  
2) CLI sends IPC request to app.  
3) App reads current selection, expands placeholders, runs action.  
4) App logs results; CLI returns exit code accordingly.


## 4. UI Composition and Responsibilities (V2)

MainWindow (Gtk.ApplicationWindow)
- Navigation via Gtk.StackSidebar + Gtk.Stack.
- Loads CSS (`assets/style.css`).
- Auto‑reloads on settings.ini / actions.json changes.

Pages
- HistoryPage: clipboard/primary buffers, apply/swap, lists.
- ActionsPage: master/detail editor (Form + JSON), run/save/duplicate/delete. Actions are always executable (no legacy “http_trigger_enabled” gate).
- TriggersPage: alias → action mapping editor for actions.json.
- ShortcutsPage (V2): Audit and sync GNOME shortcuts vs settings.ini
  - Table: Alias | INI Binding (editable) | Installed Binding (read-only)
  - Controls: Save (INI), Apply now (sync), Remove all (GNOME), Reload
- SettingsPage (V2): Endpoints, Secrets, Shortcuts (INI), Profiles, Autostart
  - Endpoints editor (ID, Base URL, Health, Trigger) + per‑row Health check
  - Secrets editor (Key/Value) → [secrets]
  - Shortcuts (INI) editor with Auto‑apply toggle:
    - Auto‑apply ON → save triggers immediate sync
    - Auto‑apply OFF → “Apply now”
  - Profiles installer using merge_* flags
  - Autostart toggles
  - Basic info (socket, log path)

Help panel component
- Renders contextual help from `help/en/*.md` via markdown renderer.

Layout
- No outer page scroller; lists/editors have their own ScrolledWindow wrappers.
- CTA Bar remains fixed at bottom.
- Actions editor uses Gtk.Paned (vertical split) with robust sizing logic.


## 5. Clipboard/Primary Monitoring and History

- Pure GTK4/GDK APIs (no wl-clipboard).
- Two ring buffers; dedupe consecutive duplicates; default max = 50.
- Operations: apply/set/swap.


## 6. Actions and Placeholders

Action Types
- HTTP: GET/POST, headers/json/form, optional body_is_text (mutually exclusive to json for POST).
- Shell: exec program with args; no shell unless `use_shell=true`.

Placeholder Expansion (V2)
- `{text}`, `{text_url}`, `{selection.type}`
- `{config.section.key}`:
  - `{config.endpoint.<id>.base_url}`
  - `{config.endpoint.<id>.health_path}`
  - `{config.endpoint.<id>.trigger_path}`
  - `{config.secrets.<key>}`

Engine provides a naive but efficient replacement strategy using the settings mapping.


## 7. IPC Protocol

- Unix Domain Socket: `$XDG_RUNTIME_DIR/wbridge.sock` (0600), NDJSON framing.
- Representative requests: ui.show, selection.get/set, history.list/apply/swap, action.run, trigger.
- Responses: `{ok: true, data: {...}}` or `{ok: false, error, code}`.


## 8. GNOME Custom Shortcuts (Automation, V2)

- Only entries under `wbridge-*` are managed by the app.
- Deterministic suffix: `wbridge-<slug>/` (slug from alias).
- Sync source of truth: `[gnome.shortcuts]` in settings.ini (Auto‑apply or Apply now).
- Deprecated helpers for “recommended shortcuts” kept for compatibility but not used by V2 sync.


## 9. Autostart

- Create/remove `~/.config/autostart/wbridge.desktop` (visible window on login).
- Users can bring it to front: `wbridge ui show`.


## 10. Configuration Files (V2)

Location
- Settings: `~/.config/wbridge/settings.ini`
- Actions: `~/.config/wbridge/actions.json`
- Logs: `~/.local/state/wbridge/bridge.log`

INI schema (authoritative)
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
prompt = <Ctrl><Alt>p
command = <Ctrl><Alt>m
ui_show = <Ctrl><Alt>u
```

Legacy section [integration.*] was removed in V2 (no migration).


## 11. Module Layout (Python)

Package: `wbridge`

Core
- `wbridge/app.py` – Gtk.Application, IPC, load settings/actions, logging.
- `wbridge/ui/main_window.py` – navigation, pages orchestration, file monitors.
- `wbridge/ui/pages/*` – per-page UIs (History, Actions, Triggers, Shortcuts, Settings, Status).
- `wbridge/ui/components/*` – shared UI components (help panel, CTA bar, markdown).
- `wbridge/config.py` – settings.ini read/write (atomic), actions.json helpers, V2 helpers:
  - Endpoints: list_endpoints, upsert_endpoint, delete_endpoint
  - Shortcuts: get_shortcuts_map, set_shortcuts_map, set_manage_shortcuts
  - Secrets: get_secrets_map, set_secrets_map
- `wbridge/gnome_shortcuts.py` – Gio.Settings automation:
  - install_binding/remove_binding
  - install_from_mapping/remove_all_wbridge_shortcuts
  - list_installed(), sync_from_ini(settings_map, auto_remove=True)
- `wbridge/actions.py` – placeholder expansion, HTTP/Shell runner, validation
- `wbridge/history.py`, `wbridge/server_ipc.py`, `wbridge/cli.py`, `wbridge/autostart.py`, `wbridge/platform.py`, `wbridge/logging_setup.py`

Profiles
- `wbridge/profiles_manager.py`
  - list/show/install
  - merge into settings.ini with flags:
    - `--merge-endpoints`, `--merge-secrets`, `--merge-shortcuts`
  - actions.json merge policy (by name), triggers merge
  - backups, atomic writes
- `wbridge/profiles/**` – built-in profiles (e.g., witsy, obsidian-local-rest)

Packaging
- `pyproject.toml`: includes package data for `assets/**/*`, `help/**/*`, `profiles/**/*`.


## 12. Logging and Diagnostics

- Log to console and `~/.local/state/wbridge/bridge.log`.
- INFO default; DEBUG optional.
- Log IPC op/status/duration and action outcomes.


## 13. Security and Privacy

- IPC socket 0600; no TCP.
- No key capture or injection.
- Treat external HTTP endpoints and Shell commands with care.
- Secrets live in `settings.ini` under `[secrets]` (user-managed; profiles do not set user tokens).


## 14. Error Handling

- CLI exits non-zero on server not reachable, invalid args, or action failures.
- UI displays statuses; no retries/backoff.


## 15. Implementation Plan (V2)

Phase 0 – Scaffold  
Phase 1 – IPC + CLI  
Phase 2 – History + GUI (StackSidebar + Stack)  
Phase 3 – Actions Engine  
Phase 4 – GNOME Integration + Autostart  
Phase 5 – V2 hard switch (settings.ini: endpoints, secrets, gnome.shortcuts); UI rewiring; CLI/Profiles merge_*  
Phase 6 – Polish (docs, logging)


## 16. Testing Checklist (V2)

Selections and History
- Clipboard/primary updates, apply/swap, dedupe.

CLI and IPC
- `wbridge ui show`, `history list/apply/swap`, `selection get/set`.

Actions
- HTTP/POST sends text; shell runs with placeholders; `{config.endpoint.*}` and `{config.secrets.*}` expand.

GNOME Shortcuts
- Settings: Auto‑apply ON triggers immediate sync; OFF requires “Apply now”.
- Shortcuts page: audit table shows INI vs Installed; Remove all clears wbridge scope.

Endpoints
- Add/Edit/Delete; Health GET base_url + health_path (2 s timeout).

Secrets
- Add/Edit/Delete keys; saved in [secrets].

Profiles/CLI
- `profile install --merge-endpoints --merge-secrets --merge-shortcuts [--overwrite-actions] [--dry-run]` merges into settings.ini/actions.json.
- Reports show merged/skipped and backups.

File Monitors & Auto-Reload
- settings.ini/actions.json changes are picked up and reflected in the UI.


## 17. Appendix: Example GNOME Keybinding Setup (Gio)

Conceptual snippets using:
- Base schema: `org.gnome.settings-daemon.plugins.media-keys`
- Custom schema: `org.gnome.settings-daemon.plugins.media-keys.custom-keybinding`
- Path prefix: `/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/`
- Suffix: `wbridge-<slug>/`


## 18. Completeness Review (V2)

Covered
- Wayland-friendly selection workflow.
- Actions with placeholders, now including settings-backed endpoints and secrets.
- Deterministic GNOME Shortcuts sync from settings.ini.
- Profiles merge into settings.ini/actions.json; CLI merge_* flags.
- No legacy [integration.*] references.

Deferred
- Cross‑DE/Compositor support and cross‑platform ports.
- Persistent history.

Risks/Notes
- No paste injection by design (Wayland).
- Users must manage secrets themselves (profiles won’t set personal tokens).
