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

## 2025-08-22 – V2 Hard Switch: settings.ini as SoT; Endpoints/Secrets/Shortcuts; merge_*; Secrets editor; cleanup integration.*

- Timestamp: 2025-08-22
- Scope:
  - Config (V2 schema):
    - Entfernt: DEFAULT_SETTINGS["integration"], sämtliche http_trigger_* Verwendungen und set_integration_settings().
    - Neu in src/wbridge/config.py:
      - Endpoints: list_endpoints(), upsert_endpoint(), delete_endpoint()
      - Shortcuts (INI): get_shortcuts_map(), set_shortcuts_map(), set_manage_shortcuts()
      - Secrets: get_secrets_map(), set_secrets_map()
  - GNOME Shortcuts:
    - src/wbridge/gnome_shortcuts.py: list_installed() (Audit), sync_from_ini(settings_map, auto_remove=True) für deterministische Synchronisation aus [gnome.shortcuts]; einheitlicher Suffix wbridge-<slug>/
  - Profiles/CLI:
    - src/wbridge/profiles_manager.py: install_profile() Flags auf merge_endpoints/merge_secrets/merge_shortcuts umgestellt; Reports vereinheitlicht (merged/skipped)
    - src/wbridge/cli.py: profile install → --merge-endpoints/--merge-secrets/--merge-shortcuts/--dry-run; Help-Texte aktualisiert; Restore-Heuristik für V2-Sektionen
  - UI:
    - SettingsPage (src/wbridge/ui/pages/settings_page.py):
      - Endpoints-Editor (ID, Base URL, Health, Trigger, Health-Check je Zeile)
      - Secrets-Editor (Key/Value, Save/Revert)
      - Shortcuts (INI)-Editor mit Auto-apply, Apply now, Remove all
      - Profile-Installer mit merge_* Flags
    - ShortcutsPage (src/wbridge/ui/pages/shortcuts_page.py): Audit-Ansicht (Alias | INI | Installed), Save/Apply/Remove all/Reload
    - ActionsPage: Legacy „HTTP trigger enabled“-Gate entfernt; Run-Button immer nutzbar
    - MainWindow: Legacy „Integration Inline Edit“ neutralisiert; Hinweise angepasst
  - App:
    - src/wbridge/app.py: entfernte Legacy-Alias-Fallbacks von [integration].obsidian_token nach [secrets]
  - Doku:
    - DESIGN.md komplett auf V2 umgestellt (Endpoints/Secrets/Shortcuts, merge_* Flags, ohne [integration.*])
    - Help: settings.md/actions.md an V2-Placeholders {config.endpoint.*}/{config.secrets.*} angepasst
    - README.md aktualisiert (V2 Schema, Endpoints/Shortcuts/Secrets, CLI merge_*)
- Affected files:
  - src/wbridge/config.py, src/wbridge/gnome_shortcuts.py, src/wbridge/profiles_manager.py, src/wbridge/cli.py,
    src/wbridge/ui/pages/{settings_page.py,shortcuts_page.py,actions_page.py}, src/wbridge/ui/main_window.py,
    src/wbridge/app.py, src/wbridge/help/en/{settings.md,actions.md}, DESIGN.md, README.md
- Tests (manuell/Smoke):
  - Settings → Endpoints: Add/Edit/Delete, Health GET base+health_path (2s Timeout) OK/NOK
  - Settings → Secrets: Key/Value Save/Revert; Platzhalter {config.secrets.KEY} in Aktionen wird ersetzt
  - Settings → Shortcuts (INI): Auto-apply ON synchronisiert GNOME sofort; OFF erfordert Apply now; Remove all entfernt wbridge-*
  - ShortcutsPage: Audit zeigt INI vs Installed; Apply/Reload/Remove all funktionieren
  - Actions: HTTP/Shell mit {config.endpoint.<id>.*} und {config.secrets.*} funktionieren; Run immer verfügbar
  - CLI: profile install --merge-*; Reports merged/skipped; Backup erstellt
- Notes:
  - Harte Umstellung ohne Migration; keine Legacy [integration.*] in Code/UI/Docs
  - Deprecated: install_recommended_shortcuts/remove_recommended_shortcuts behalten, aber nicht Teil des V2-Sync-Workflows

---
 
## 2025-08-19 – UI-Polish: Popover-only Help, Responsivität, Actions-Split-Logik stabilisiert

- Timestamp: 2025-08-19
- Scope:
  - Help: Revealer entfernt; „?“ öffnet Popover (≈65% Fensterbreite, min 520 px), Autohide, natürliche Breite; CSS `.help-popover` ergänzt; Breite folgt Window-Resize via Hook.
  - Responsivität: History/Triggers/Shortcuts – äußere Page-Scroller entfernt; Inhalt wächst mit Fensterhöhe; Scroll nur in Listen/Editoren; CTA-Bar bleibt fix unten. History-Minheight von 120→140 px.
  - Actions: Vertikaler Split Editor/Liste (start_child no-shrink, end_child shrink); Default-Ratio oben ≈0.62; Editor-Scroller min 320 px; robuste Initial-Position (map/visible/idle + kurze Retries + size-allocate); Ratio-Persistenz bei Resize; Guard gegen frühe Events.
  - Status: newest-first Log, Follow alle 1 s, Scroll/Cursor an den Anfang, vexpand sichergestellt.
  - Doku: DESIGN.md erweitert (Popover-only, Responsivität, Actions-Split, CSS, Markdown→Pango, Startgröße).
- Affected files:
  - src/wbridge/ui/components/page_header.py
  - src/wbridge/ui/components/help_panel.py
  - src/wbridge/assets/style.css
  - src/wbridge/ui/pages/actions_page.py
  - src/wbridge/ui/pages/history_page.py
  - src/wbridge/ui/pages/triggers_page.py
  - src/wbridge/ui/pages/shortcuts_page.py
  - src/wbridge/ui/pages/status_page.py
  - src/wbridge/ui/main_window.py (Startgröße)
  - DESIGN.md
- Tests (manuell):
  - Nach Appstart und erstem Wechsel auf „Actions“: Editor oben ~62% Höhe, Liste unten ~38%; Nutzer-Drag bleibt über Resizes hinweg erhalten; keine 0px-Fallbacks.
  - Popover-Breite passt sich Fenstergröße an; keine horizontale Scrollbar.
  - Andere Seiten wachsen mit Fensterhöhe; Scroll nur in Inhalts-Scroller; CTA-Bar fix.
- Notes:
  - apply_help_mode() neutralisiert; frühere Help-Mode-Konfiguration entfernt/ignoriert.
  - Weitere Feinschliffe möglich (Ratio-Default ±, History-MinHeight ±10 px).

## 2025-08-18 – UI split refactor to ui/*, wire pages, remove legacy PoC, docs sync

- Timestamp: 2025-08-18
- Scope:
  - UI refactor: split monolithic gui_window.py into ui/main_window.py + ui/pages/* (History, Actions, Triggers, Shortcuts, Settings, Status) and ui/components/help_panel.py. Wired pages in MainWindow; switched import in app.py.
  - Wiring: integrated HistoryPage, ActionsPage, TriggersPage; added ShortcutsPage, SettingsPage, StatusPage; adjusted file monitors so settings.ini changes call SettingsPage.reload_settings(); actions.json changes refresh ActionsPage and TriggersPage and notify ActionsPage.
  - Docs: README Project Layout updated to ui/*; DESIGN Module Layout updated; implementation plan validated.
  - Cleanup: prepared to remove legacy gui_window.py and wayland-bridge.py; follow-up deletion executed next.
- Affected files:
  - src/wbridge/ui/main_window.py (imports pages; stack wiring; settings/actions monitors adjusted)
  - src/wbridge/ui/pages/{history_page.py, actions_page.py, triggers_page.py, shortcuts_page.py, settings_page.py, status_page.py} (added/implemented)
  - src/wbridge/ui/components/help_panel.py
  - src/wbridge/app.py (import MainWindow from ui.main_window)
  - README.md, DESIGN.md (synced to new structure)
- Notes:
  - Old _page_* factory methods and helper code remain temporarily in MainWindow but are no longer used; slated for deletion in a follow-up cleanup.
  - Feature parity maintained; no changes to data formats or IPC.

## 2025-08-17 – Step 8: Help & i18n, Hilfe‑Panels, CSS/Packaging, Doku

- Timestamp: 2025-08-17
- Scope:
  - GUI – Help & i18n:
    - Pro Seite einklappbarer Hilfebereich (Gtk.Expander(_("Help"))) mit Markdown‑Inhalt aus Ressourcen (src/wbridge/help/en/*.md).
    - gettext initialisiert (Domain "wbridge", Fallback True); UI‑Texte sukzessive in _() gewrappt; Englisch als Default.
    - CSS‑Loader: assets/style.css wird geladen und als Gtk.CssProvider registriert (prio: APPLICATION); Klassennamen u.a. .dim-label für Sekundärtexte.
  - Navigation/Guardrails (Bestätigung): Linksseitige Gtk.StackSidebar + Gtk.Stack bleibt Grundlage; Shortcuts‑Policy „nur wbridge‑verwaltete“ in UI beachtet (Bearbeitbarkeit auf wbridge‑Suffixe beschränkt; Fremde read‑only).
  - Doku/Packaging:
    - pyproject.toml: Paketdaten für "wbridge" um help/**/* und assets/**/* ergänzt.
    - README.md/DESIGN.md aktualisiert: neue Navigation, Hilfe‑Konzept, i18n‑Vorbereitung, Shortcuts‑Scope‑Policy, CSS‑Hinweise, Run‑Anleitung.
- Affected files:
  - src/wbridge/gui_window.py (Help‑Panels, gettext‑Init, CSS‑Loader, Tooltips verfeinert)
  - src/wbridge/help/en/{history.md,actions.md,triggers.md,shortcuts.md,settings.md,status.md} (neu)
  - src/wbridge/assets/style.css (neu)
  - pyproject.toml ([tool.setuptools.package-data] ergänzt)
  - README.md, DESIGN.md (Doku‑Aktualisierungen)
- Tests (manuell, erfolgreich):
  - Hilfe‑Panels auf allen Seiten rendern Markdown korrekt; Expander‑Zustand stabil.
  - i18n‑Fallback aktiv (englische Texte sichtbar, keine Missing‑Locale‑Fehler).
  - Shortcuts‑Seite: Fremde Custom‑Keybindings sind read‑only; wbridge‑Einträge editierbar; Konfliktmeldungen erscheinen.
  - CSS‑Klassen anwenden sich (z.B. .dim-label).
- Notes:
  - Lokalisierung: localedir bleibt zunächst None (Fallback); Vorbereitung für spätere .mo‑Auslieferung.
  - Screenshots für README/DESIGN folgen in einem separaten Patch.
  - Optional v1 (Folgeschritt): on_success.apply_to und timeout_s in Actions‑Validierung/Runner.

## 2025-08-16 – Optional Cleanup CLIs, PATH‑Hinweis in GUI, Doku‑Sync

- Timestamp: 2025-08-16
- Scope:
  - CLI – neue Wartungs-/Cleanup‑Kommandos:
    - profile uninstall --shortcuts-only (entfernt nur Profil‑Shortcuts über deterministische Suffixe)
    - shortcuts remove --recommended (empfohlene wbridge‑Shortcuts entfernen)
    - autostart disable (löscht ~/.config/autostart/wbridge.desktop)
  - CLI – Config‑Utilities:
    - config show-paths [--json] (wichtige Pfade)
    - config backup [--what actions|settings|all] (timestamp‑Backups)
    - config reset [--keep-actions] [--keep-settings] [--backup] (löschen mit optionalem Backup)
    - config restore --file PATH (Wiederherstellung in Ziel anhand Dateiname/Heuristik)
  - GUI – Settings PATH‑Hinweis:
    - Wenn shutil.which("wbridge") None zurückgibt, sichtbarer Hinweis, dass GNOME Shortcuts den Befehl ggf. nicht finden; Empfehlung: absolute Pfade oder korrekter PATH.
  - Doku‑Sync:
    - DESIGN.md: neue Sektion „Config and Maintenance Commands (CLI)“ + Änderungsprotokoll 2025‑08‑16
    - README: Ergänzende Hinweise zu globaler Installation/PATH (separat bereits aktualisiert)
- Affected files:
  - src/wbridge/cli.py (neue Subcommands: profile uninstall, shortcuts remove, autostart disable; config show-paths/backup/reset/restore)
  - src/wbridge/gui_window.py (PATH‑Hinweis in Settings)
  - src/wbridge/gnome_shortcuts.py (Helper remove_recommended_shortcuts/Binding‑Removal genutzt)
  - src/wbridge/autostart.py (disable/enable/is_enabled)
  - DESIGN.md (CLI‑Wartungssektion + Eintrag 2025‑08‑16)
- Tests (manuell, Smoke):
  - wbridge profile uninstall --name witsy --shortcuts-only → Profil‑Shortcuts entfernt (wbridge‑… Suffixe)
  - wbridge shortcuts remove --recommended → OK
  - wbridge autostart disable → OK/FAILED je nach vorhandener Desktop‑Datei
  - wbridge config show-paths|backup|reset|restore → Pfade korrekt, Backups erstellt, Restore ersetzt atomar
  - GUI zeigt PATH‑Hinweis, wenn „wbridge“ nicht im PATH gefunden wird
- Notes:
  - Nicht destruktiv per Default; Backups sind timestamped (…bak‑YYYYmmdd‑HHMMSS)
  - Shortcuts‑Removal ist gezielt; keine Fremd‑Keybindings werden überschrieben
  - GNOME Custom Shortcuts benötigen ggf. absolute Pfade, wenn „wbridge“ nicht im PATH ist

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
  - Bugfixes: „Doppel‑Klick nötig“ und „Hängen nach erster Selektion“ behoben durch sofortige History‑Aktualisierung, asynchrone Label‑Update, Dirty‑Flag‑Refresh und In‑Flight‑Guards.

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
