# Implementation Log – wbridge

Purpose
- Track significant implementation steps, decisions, merges, and next actions.
- Keep entries concise and actionable. One log per change-set, newest first.

Conventions
- Timestamp: local time of the developer system
- Scope: brief summary of touched areas
- Commits: local and/or remote SHAs if relevant
- Links: issue/PR if available (future)

---
 
## 2025-08-14 – Actions Editor (Raw‑JSON), Settings Inline‑Edit/Health, Wrapping Fix

- Timestamp: 2025-08-14
- Scope:
  - GUI – Actions Editor (Phase 1, Raw‑JSON):
    - Actions‑Tab zeigt pro Aktion einen Expander mit Kopfzeilen‑Preview (Name, Typ, Kurzinfo).
    - Inline Raw‑JSON‑Editor (monospace) je Aktion mit Buttons: Run, Save, Cancel, Duplicate, Delete.
    - „Add Action“ fügt Standard‑HTTP‑Aktion hinzu.
    - Save/Duplicate/Delete schreiben atomar nach ~/.config/wbridge/actions.json (Timestamp‑Backups), anschließend Reload der Actions und UI‑Refresh.
  - Config‑Helfer:
    - load_actions_raw(): rohes Laden der actions.json
    - write_actions_config(data): atomarer JSON‑Write + Timestamp‑Backup
    - validate_action_dict(action): Minimalvalidierung für http/shell
    - set_integration_settings(...): atomare INI‑Updates für [integration]
  - GUI – Settings Verbesserungen:
    - Nach Profil‑Installation: Settings‑Reload; Integration‑Status + Actions‑Enable aktualisieren sich (Fix: „Run bleibt disabled“).
    - Inline‑Edit: http_trigger_enabled, http_trigger_base_url, http_trigger_trigger_path (Validierung + atomare INI‑Writes); „Reload Settings“; „Health check“ (GET base+health_path).
  - Bugfix:
    - Gtk.Expander.set_expand → GTK4 besitzt diese Methode nicht; Umstellung auf set_hexpand.
  - UI‑Wrapping:
    - PRIMARY/Clipboard „Aktuell:“‑Labels und History‑Zeilen umbrechen hart (Pango WrapMode CHAR), set_max_width_chars(80), set_hexpand(True) → verhindert Fensterverbreiterung bei langen Inhalten.
- Affected files:
  - src/wbridge/gui_window.py (Actions‑Editor, Settings‑Reload/Inline‑Edit/Health, Wrapping, Bugfix)
  - src/wbridge/config.py (load_actions_raw, write_actions_config, validate_action_dict, set_integration_settings)
- Tests (manuell, erfolgreich):
  - Aktionen: Edit/Save/Duplicate/Delete → Backups erstellt, UI reloaded, Run funktioniert.
  - Settings: Inline‑Edit/Reload/Health‑Check → Status/Actions aktualisieren sich ohne App‑Neustart; Health zeigt OK/Fehler abhängig vom Dienst.
  - Lange PRIMARY/Clipboard‑Inhalte → Labels umbrechen, Fenster bleibt stabil.
- Known limitations / Next:
  - Formular‑Modus (feldbasiert) für Actions (statt Raw‑JSON).
  - Triggers‑Editor (alias → action.name) im Actions‑Tab.
  - Config‑CLI (show‑paths/reset/backup/restore).
  - Gio.FileMonitor auf settings.ini/actions.json für Auto‑Reload.
  - Profile‑Shortcuts Uninstall (CLI/UI).

## 2025-08-14 – Profiles/Presets + Witsy + CLI/UI + Docs

- Timestamp: 2025-08-14
- Scope:
  - ProfileManager:
    - Neues Modul src/wbridge/profiles_manager.py mit API list_builtin_profiles/show_profile/install_profile
    - Merge-/Backup-Strategie für actions.json (Name-Kollisionen), triggers, atomare Writes, Timestamp‑Backups
    - settings.patch.ini: Patch nur whitelisted Keys in [integration]
    - Optional: Shortcuts-Installation via Gio.Settings
    - Laden von Paketressourcen via importlib.resources (Traversable‑kompatibel)
  - Built-in Profil „Witsy“:
    - src/wbridge/profiles/witsy/{profile.toml, actions.json, shortcuts.json, settings.patch.ini}
    - Packaging: pyproject.toml → [tool.setuptools.package-data] "wbridge.profiles" = ["**/*"]
  - CLI:
    - Neue Subcommands in src/wbridge/cli.py: profile list/show/install (+ Exit‑Codes 0/2/3)
  - GUI:
    - Settings‑Tab: „Integration Status“ (Enabled/Base‑URL/Trigger‑Pfad)
    - Settings‑Tab: „Profile“-Bereich (Dropdown/Anzeigen/Installieren mit Checkboxen: Actions überschreiben, Settings patchen, Shortcuts installieren, Dry‑run)
    - Actions‑Tab: Hinweis + Deaktivierung der Run‑Buttons, wenn integration.http_trigger_enabled=false
  - Shim:
    - src/wbridge/profiles.py re‑exportiert die API aus profiles_manager.py (verhindert Verwirrung/Legacy‑Imports)
  - Doku:
    - DESIGN.md: „Profile Commands (CLI)“, Module‑Layout (profiles_manager + Ressourcen), Packaging‑Hinweis, Checklist erweitert, „Nächste Schritte“ aktualisiert
    - README.md: „Profiles & Witsy Quickstart“ inkl. Installationsbeispiele und Hinweise
- Tests (Smoke):
  - wbridge profile list → ["witsy"]
  - wbridge profile show --name witsy → ok=true, enthält Metadaten/Actions/Triggers/Shortcuts/Settings‑Patch
  - wbridge profile install --name witsy --dry-run → ok=true, zeigt geplante Adds/Patches/Backups, keine Writes
- Known limitations:
  - UI‑Buttons für GNOME Shortcuts und Autostart sind weiterhin Platzhalter (separater Task)
  - HTTP‑Actions benötigen optional „requests“; ohne Extra liefern HTTP‑Aktionen einen klaren Fehlermeldungstext

## 2025-08-12 – History/GUI/IPC enhancements

- Timestamp: 2025-08-12
- Scope:
  - IPC: implementiert `history.list/apply/swap`; `action.run` + `trigger`; Settings/Actions werden beim Start geladen.
  - GUI/History: zweizeilige Einträge mit Apply-Buttons, „Aktuell: …“-Label je Bereich, manueller Refresh + Zähler; Swap‑Button; stabile Refresh‑Mechanik (Dirty‑Flag), keine UI‑Blockierung.
  - GUI/Actions: Liste aus actions.json; Quellwahl (Clipboard/Primary/Text); Run‑Button mit Ergebnisanzeige; Reload actions.
  - GUI/Settings: Basisinfos (GDK‑Backend, Socket, Log) + Platzhalter‑Buttons (Shortcuts/Autostart).
  - Stabilität: zentrale Apply‑Logik, asynchrone Lese‑Guards (`_reading_cb`, `_reading_pr`), kein reentrantes Listen‑Refresh, Shutdown‑Fix (`Gtk.Application.do_shutdown(self)`).
  - CLI: History‑Subcommands arbeiten gegen neue IPC‑Handler; manuelle Tests durchgeführt.
  - DESIGN.md: Checkliste angepasst (umgesetzte Punkte abgehakt).
- Local commit:
  - tbd (nach Push): feat(gui,ipc): History‑IPC, History‑UI mit „Aktuell“, Actions‑Tab, Settings‑Basis; Async‑Guards/Dirty‑Refresh; CLI‑Integration
- Notes:
  - Bugfixes: „Doppel‑Klick nötig“ und „Hängen nach erster Selektion“ behoben durch sofortige History‑Aktualisierung, asynchrones Label‑Update, Dirty‑Flag‑Refresh und In‑Flight‑Guards.

## 2025-08-12 – Initial scaffold, push to org

- Timestamp: 2025-08-12
- Scope:
  - Repo scaffolded locally (single package with CLI+GUI).
  - Created: pyproject.toml, README.md, DESIGN.md, LICENSE (MIT), .gitignore.
  - Source modules added under src/wbridge/: app.py, cli.py, server_ipc.py, client_ipc.py, history.py, config.py, actions.py, gnome_shortcuts.py, platform.py, logging_setup.py, __init__.py.
  - IPC server started from GUI; ui.show handler implemented; CLI wired to IPC.
- Local commit:
  - d694c5f chore: scaffold wbridge (CLI+GUI, IPC server/client, docs, config)
- Remote integration:
  - Remote default branch contained initial skeleton (e.g., LICENSE). Performed merge favoring local scaffold for conflicts.
  - Merge and push completed.
  - Remote tip: bbd642f main
- Notes:
  - SSH key added and authorized for org; push now functional.
  - LICENSE conflict auto-merged using recursive strategy (ours preference). Final license retained as MIT from local scaffold.

Next Steps (per DESIGN.md Checklist)
- Extend IPC handler to support: selection.get/set, history.list/apply/swap, action.run/trigger.
- Add GUI tabs (History/Actions/Settings/Status) and wire to services.
- Implement actions management UI and settings loading.
- Provide GNOME shortcuts install/remove UI and Autostart toggle.
