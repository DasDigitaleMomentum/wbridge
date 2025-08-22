# Implementation Plan

[Overview]
Harter Umstieg auf V2: settings.ini als Single Source of Truth (Endpoints, Secrets, GNOME‑Shortcuts); Entfernung aller [integration.*]‑Pfade in Code und UI; Endpoints‑/Shortcuts‑Editor und deterministische GNOME‑Sync aus [gnome.shortcuts].

Die aktuelle Codebasis verwendet noch [integration.*] (config.py DEFAULT_SETTINGS, SettingsPage‑Inline‑Edit, Health‑Check). V2 konsolidiert Konfiguration auf [endpoint.<id>], [secrets], [gnome], [gnome.shortcuts]. Aktionen nutzen Platzhalter {config.endpoint.<id>.*} und {config.secrets.*}. GNOME‑Shortcuts werden ausschließlich aus settings.ini gelesen und in dconf geschrieben (Auto‑Apply bei manage_shortcuts=true, sonst „Apply now“). Profile mergen Endpoints/Secrets/Shortcuts in die INI (kein direkter dconf‑Write). Altes [integration.*] wird konsequent entfernt; keine Migration.

[Types]
Einführung des V2‑INI‑Schemas und Hilfstypen für Endpoints/Shortcuts.

- INI‑Schema
  - [endpoint.<id>]
    - base_url: string; MUSS mit http:// oder https:// beginnen
    - health_path: string; beginnt mit /; Default /health
    - trigger_path: string; beginnt mit /; optional; Default /trigger
    - <id>: slug ([a-z0-9_-]+), eindeutig
  - [secrets]
    - beliebige Key/Value (z. B. obsidian_token)
  - [gnome]
    - manage_shortcuts: bool (Default true)
  - [gnome.shortcuts]
    - alias → binding (z. B. prompt = <Ctrl><Alt>p)
- Platzhalter
  - {config.endpoint.<id>.base_url}, {config.endpoint.<id>.health_path}, {config.endpoint.<id>.trigger_path}
  - {config.secrets.<key>}
- Interne Hilfstypen (optional)
  - dataclass Endpoint(id: str, base_url: str, health_path: str = "/health", trigger_path: str = "/trigger")

[Files]
Entfernung der alten Integrationspfade; neue Editor‑/Sync‑Funktionalität; keine Legacy‑Migration.

- Neue Dateien
  - (Optional) src/wbridge/ui/components/endpoint_dialog.py – Dialog zum Hinzufügen/Bearbeiten eines Endpoints (ID, Base URL, Health/Trigger). Kann alternativ in settings_page.py inline implementiert werden.
- Zu modifizierende Dateien
  - src/wbridge/config.py
    - Entferne DEFAULT_SETTINGS["integration"] vollständig.
    - Entferne statische Binding‑Defaults in DEFAULT_SETTINGS["gnome"] (binding_prompt/command/ui_show).
    - Neue Helpers:
      - list_endpoints(settings: Settings) → Dict[str, Dict[str, str>]
      - upsert_endpoint(id: str, base_url: str, health_path: str = "/health", trigger_path: str = "/trigger") → None
      - delete_endpoint(id: str) → bool
      - get_shortcuts_map(settings: Settings) → Dict[str, str]
      - set_shortcuts_map(mapping: Dict[str, str]) → None
      - set_manage_shortcuts(on: bool) → None
    - expand_placeholders: beibehaltend; Dokumentation der {config.endpoint.*}/{config.secrets.*}‑Varianten.
    - Entferne set_integration_settings(...) und sämtliche http_trigger_* Verwendungen.
  - src/wbridge/ui/pages/settings_page.py
    - Entferne kompletten „Integration status/Edit/Health“‑Block (Labels, Switch/Entries, Buttons, Handler).
    - Implementiere:
      - Endpoints‑Editor: Liste (ID | Base URL | Health | Trigger | [Health] [Edit] [Delete]) und [Add Endpoint].
      - Shortcuts‑Editor (Config vs Installed): Tabelle alias | binding (editierbar); Status „Auto‑apply ON/OFF“; Buttons: Save (INI), Revert, Apply now (sichtbar wenn manage_shortcuts=false), Remove all.
      - Health‑Button: urllib.request GET base_url + health_path mit 2s Timeout.
      - Auf Save: Schreibvorgänge in settings.ini; wenn manage_shortcuts=true, sofort gnome_shortcuts.sync_from_ini(...)
    - Entferne Verweise auf http_trigger_* und set_integration_settings.
  - src/wbridge/gnome_shortcuts.py
    - Ergänze:
      - list_installed() → List[dict] mit {name, command, binding, suffix}
      - sync_from_ini(settings_map: Dict[str, Dict[str, str]], auto_remove: bool = True) → Dict[str, int]  // {"installed": n, "updated": m, "removed": r, "skipped": s}
    - Vereinheitliche Slug/Suffix (wbridge-<slug>/) mit bestehender _slug()/install_binding().
    - Behalte install_recommended_shortcuts/remove_recommended_shortcuts als deprecated.
  - src/wbridge/cli.py
    - Subcommand „profile install“: Flags anpassen
      - --overwrite-actions (bestehend)
      - --merge-endpoints, --merge-secrets, --merge-shortcuts, --dry-run (ersetzen/ergänzen gegenüber --patch-settings/--install-shortcuts)
    - Help/Output‑Texte auf „Merge in settings.ini“ umstellen, kein dconf‑Write.
  - src/wbridge/profiles_manager.py
    - Signatur install_profile(...) an neue Flags anpassen: merge_endpoints: bool, merge_secrets: bool, merge_shortcuts: bool (ersetzen patch_settings/install_shortcuts).
    - Merge‑Whitelist (endpoint.*, secrets, gnome.shortcuts, optional gnome.manage_shortcuts) sicherstellen (bereits vorhanden).
    - Report‑Keys/‑Texte: „merged/skipped“ konsistent; backups wie gehabt.
  - src/wbridge/ui/pages/shortcuts_page.py
    - Audit‑Ansicht: Tabelle Alias | ini.Binding | installed.Binding; Diff farblich; Buttons: Save (INI), Apply now, Remove all.
  - src/wbridge/ui/main_window.py
    - Entferne Gate/Disable‑Logik basierend auf integration.http_trigger_enabled (Actions immer benutzbar).
- Zu löschen/verschieben
  - In src/wbridge/config.py: Funktion set_integration_settings(...) entfernen.
  - In src/wbridge/ui/pages/settings_page.py: Methoden _on_save_integration_clicked, _on_discard_integration_clicked, _on_health_check_clicked, _on_reload_settings_clicked und zugehörige UI‑Elemente entfernen/ersetzen.

[Functions]
Ziel: neue V2‑Helpers hinzufügen und alte Integrationsfunktionen entfernen.

- Neu
  - config.py
    - def list_endpoints(settings: Settings) → Dict[str, Dict[str, str]]
    - def upsert_endpoint(id: str, base_url: str, health_path: str = "/health", trigger_path: str = "/trigger") → None
    - def delete_endpoint(id: str) → bool
    - def get_shortcuts_map(settings: Settings) → Dict[str, str]
    - def set_shortcuts_map(mapping: Dict[str, str]) → None
    - def set_manage_shortcuts(on: bool) → None
  - gnome_shortcuts.py
    - def list_installed() → List[dict]
    - def sync_from_ini(settings_map: Dict[str, Dict[str, str]], auto_remove: bool = True) → Dict[str, int]
  - settings_page.py
    - def on_endpoint_add/edit/delete(self, …) → None
    - def on_endpoint_health_check(self, endpoint_id: str) → None
    - def on_shortcuts_save(self, mapping: Dict[str, str]) → None
    - def on_shortcuts_apply_now(self) → None
- Modifiziert
  - config.py: DEFAULT_SETTINGS ohne „integration.*“ und ohne statische „binding_*“; expand_placeholders unverändert nutzbar.
  - profiles_manager.py: install_profile Parameter/Reportnamen an neue Flags; intern _merge_shortcuts_section/_merge_shortcuts_from_items bleiben.
  - cli.py: build_parser(), cmd_profile_install() Flag‑Mapping und Messages.
- Entfernt
  - config.py: set_integration_settings(...)
  - settings_page.py: alle Handler/UI‑Elemente zu http_trigger_*

[Classes]
Keine neuen Kernklassen; optionale interne Dataclasses.

- Neu
  - (Optional) dataclass Endpoint in config.py für Validierung/Hilfen.
- Modifiziert
  - Settings unverändert (get/getint/getboolean/as_mapping).
- Entfernt
  - Keine Klassenentfernung erforderlich.

[Dependencies]
Keine neuen Pflicht‑Abhängigkeiten; optional bleibt requests für HTTP‑Aktionen erhalten.

[Testing]
Testansatz: Unit für Merge/Helpers; Smoke/E2E für UI und GNOME‑Sync.

- Unit
  - profiles_manager: Merge endpoint.*, secrets, gnome.shortcuts; Flags merge_*; overwrite_actions True/False
  - gnome_shortcuts: _slug, list_installed, sync_from_ini(auto_remove), remove_all_wbridge_shortcuts
  - config.py: upsert/delete_endpoint, set_shortcuts_map, set_manage_shortcuts
- E2E (manuell)
  - Profile obsidian/witsy installieren (dry‑run, dann merge); INI prüfen
  - manage_shortcuts=true: Save → Shortcuts erscheinen in GNOME
  - manage_shortcuts=false: Save ändert nur INI; Apply now synchronisiert
  - Endpoints‑Health‑Check Button → OK/Fehler wie erwartet
- UX
  - Settings‑Endpoints: Add/Edit/Delete, Health
  - Shortcuts‑Editor: Config vs Installed Diff

[Implementation Order]
Schrittweise, konfliktarm: Core → Shortcuts‑Sync → Profile/CLI → UI → Doku → Cleanup.

1) config.py: DEFAULTS bereinigen; neue INI‑Helpers (endpoints/shortcuts/manage_shortcuts); set_integration_settings entfernen
2) gnome_shortcuts.py: list_installed, sync_from_ini; Suffix‑Logik vereinheitlichen
3) profiles_manager.py: Flags/Reports auf merge_endpoints/merge_secrets/merge_shortcuts umstellen
4) cli.py: Parser/Help/Report‑Texte aktualisieren
5) UI SettingsPage: Endpoints‑Editor + Shortcuts‑Editor, Auto‑apply, Remove all, Health; Status „Auto‑apply ON/OFF“
6) UI ShortcutsPage: Audit‑Ansicht (Diff) + Buttons
7) Doku: help/en/settings.md, help/en/shortcuts.md, help/en/actions.md aktualisieren
8) Cleanup/Smoke/E2E: Entferne restliche [integration.*]‑Referenzen; manuelle Prüfung aller Flows
