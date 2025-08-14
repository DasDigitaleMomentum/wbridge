# Weiterführungs‑Prompt – Finalisierung wbridge (Checkliste V1 vollständig)

Ziel
- Die Anwendung funktional und dokumentarisch auf V1‑Stand bringen (Checkliste in DESIGN.md Abschnitt 23 vollständig abhaken).
- Ausstehende Implementierungen ergänzen: Actions‑Formular‑Editor, Config‑CLI, Auto‑Reload (FileMonitor), Profile‑Shortcuts Uninstall, GNOME‑Shortcuts‑Buttons, Autostart.
- Doku (README/DESIGN/IMPLEMENTATION_LOG) finalisieren; manuelle Tests durchführen.

Kontext (aktueller Stand)
- Implementiert:
  - ProfileManager (list/show/install), Built‑in „Witsy“-Profil (Paketressourcen), CLI „profile …“
  - Actions‑Editor (Phase 1: Raw‑JSON) mit Run/Save/Cancel/Duplicate/Delete + „Add Action“, atomare Writes + Timestamp‑Backups, Validierung
  - Triggers‑Editor (Alias → Action), Validierung, atomare Writes + Reload
  - Settings Inline‑Edit (Enable/Base‑URL/Trigger‑Path) + atomare INI‑Writes, Settings‑Reload‑Button, Health‑Check
  - Wrapping‑Fix (lange PRIMARY/Clipboard/History Inhalte umbrechen; kein Fenster‑Overflow)
  - Doku: DESIGN.md Abschnitte 29/30; README um Actions/Triggers‑Editor und Settings‑Inline‑Edit; IMPLEMENTATION_LOG Einträge vorhanden
- Offen (dieser Prompt):
  1) Actions‑Formular‑Modus (feldbasierte UI) statt Raw‑JSON (Raw‑Modus bleibt optional)
  2) Config‑CLI (show‑paths/reset/backup/restore)
  3) Gio.FileMonitor für settings.ini/actions.json (Auto‑Reload)
  4) Profile‑Shortcuts Uninstall (CLI/UI)
  5) GNOME‑Shortcuts‑Buttons (Install/Remove) und Autostart (autostart.py + UI)
  6) Doku‑Finalisierung (README/DESIGN Checkliste), IMPLEMENTATION_LOG aktueller Eintrag
  7) Manuelle End‑to‑End Tests

---

## Aufgaben (Implementierung)

1) Actions – Formular‑Editor (zusätzlich zum Raw‑JSON)
- Ziel: Typ‑bezogene, feldbasierte Bearbeitung (http/shell); bessere Usability als reines JSON.
- UI‑Erweiterung im Actions‑Tab:
  - Pro Aktion Umschalter: „Formular | Raw JSON“ (Default: Formular)
  - Allgemeine Felder:
    - name (Entry, einzigartig), type (Combo: http|shell)
  - HTTP‑Sicht:
    - method (Combo: GET|POST)
    - url (Entry, nicht leer)
    - headers (TextView JSON ➜ dict), params (TextView JSON ➜ dict)
    - json (TextView JSON ➜ dict/array/string), data (TextView JSON ➜ dict/array/string)
  - Shell‑Sicht:
    - command (Entry, nicht leer)
    - args (TextView JSON ➜ array)
    - use_shell (Switch + Warnhinweis)
  - Save/Cancel/Duplicate/Delete Buttons 1:1 wie beim Raw‑Modus; Validierung identisch (config.validate_action_dict)
- Persistenz:
  - Lesen payload via load_actions_raw(), Änderungen in der einen Aktion anwenden, write_actions_config(payload) atomar, Backups
  - Nach Save: load_actions() ins App‑Objekt, UI refresh
- Validierung:
  - Anzeigen von Fehlern inline; Name‑Kollision vermeiden; ungültiges JSON in Unterfeldern (headers/params/json/data/args) melden
- Hinweis:
  - Beim Umbenennen keine automatische Trigger‑Anpassung (bewusst); dem Nutzer im UI/README klar kommunizieren

2) Config‑CLI (neue Subcommands in wbridge/cli.py)
- wbridge config show-paths
  - Ausgabe JSON: { "settings": "~/.config/wbridge/settings.ini", "actions": "~/.config/wbridge/actions.json", "state_log": "~/.local/state/wbridge/bridge.log", "autostart_desktop": "~/.config/autostart/wbridge.desktop" }
- wbridge config reset [--keep-actions] [--keep-settings] [--backup]
  - Default: beide Dateien löschen
  - Bei --backup: Timestamp‑Backups anlegen
  - Exit‑Code 0 OK, 3 Failure
- wbridge config backup [--what actions|settings|all]
  - Legt Kopien .bak‑YYYYmmdd‑HHMMSS an
- wbridge config restore --file /path/to/backup
  - Prüft Datei, atomarer Replace
- Konsistente, kurze Text/JSON‑Ausgaben; Fehler/Exit‑Codes wie CLI‑Specs (0/2/3)

3) Auto‑Reload per Gio.FileMonitor (GUI)
- Beobachte:
  - ~/.config/wbridge/settings.ini → bei Änderung: Settings reload + Integration‑Status/Actions‑Enable refresh
  - ~/.config/wbridge/actions.json → bei Änderung: Actions + Triggers neu laden (UI refresh)
- Debounce (z. B. 200 ms) um Burst‑Writes zu glätten
- Log‑Events (INFO): file.monitor event + angewandte Reloads

4) Profile‑Shortcuts Uninstall (profiles_manager + CLI/UI)
- profiles_manager.remove_profile_shortcuts(name):
  - shortcuts.json des Profils lesen
  - Pfad‑Suffixe „wbridge-<normalized-name>/“ bilden (wie Install)
  - gnome_shortcuts.remove_binding(suffix) für jede Zeile
  - Report zurückgeben: {"removed": N, "skipped": M}
- CLI:
  - wbridge profile uninstall --name NAME --shortcuts-only
  - Ausgabe Report; Exit‑Code 0/3
- GUI (Settings → Profile):
  - Button „Profil‑Shortcuts entfernen“ (wenn Profil gewählt)

5) GNOME‑Shortcuts‑Buttons & Autostart
- Settings‑Tab:
  - „GNOME Shortcuts installieren“: install_recommended_shortcuts mit Werten aus settings.ini (oder Profil‑Empfehlungen)
  - „GNOME Shortcuts entfernen“: remove_recommended_shortcuts
  - Erfolg/Fehler in settings_result + Log
- Autostart:
  - Modul autostart.py: create/remove ~/.config/autostart/wbridge.desktop (Exec=wbridge-app)
  - Zwei Buttons: „Autostart aktivieren/deaktivieren“; Ergebnis anzeigen + Log

6) Doku‑Finalisierung
- DESIGN.md Abschnitt 23 (Checkliste) vervollständigen (alle relevanten Items auf [x])
- README.md:
  - Kurzabschnitte:
    - Actions Formular‑Editor (mit Feldern + Validierung)
    - Config‑CLI (mit Beispielen)
    - Auto‑Reload Hinweis (FileMonitor)
    - Profile‑Shortcuts Uninstall (CLI/UI)
    - GNOME‑Shortcuts Buttons, Autostart Buttons
- IMPLEMENTATION_LOG.md:
  - Neuer Eintrag „Finalize V1“: Inhalte, betroffene Dateien, Tests, bekannte Einschränkungen

7) Manuelle End‑to‑End Tests
- Profile:
  - wbridge profile install --name witsy --patch-settings
  - Settings Reload/Status prüfen, Health‑Check OK, Run‑Buttons enabled
- Actions Formular‑Editor:
  - HTTP‑Aktion via Formular anpassen (URL/Header), Save → Backup/Reload; Testen via Run
  - Shell‑Aktion neu anlegen (echo), Run (Quelle=Text)
  - Rename: Trigger bewusst nicht automatisch anpassen; im Triggers‑Editor korrigieren
- Triggers‑Editor:
  - Alias anlegen/ändern/löschen; Save → CLI `wbridge trigger <alias>` testen
- Config‑CLI:
  - show-paths / backup / reset --backup / restore
- Auto‑Reload:
  - actions.json und settings.ini extern editieren → UI aktualisiert sich automatisch
- Shortcuts:
  - install_recommended_shortcuts / remove_recommended_shortcuts Buttons testen
  - profile uninstall --shortcuts-only → GNOME‑Einstellungen prüfen
- Autostart:
  - Buttons erstellen/entfernen .desktop Datei; Login‑Test (manuell, später)
- Wrapping‑Fix:
  - Sehr lange PRIMARY/Clipboard‑Inhalte → keine Fenster‑Verbreiterung

Akzeptanzkriterien
- Formular‑Editor arbeitet stabil (Validierung, atomare Writes, Reload, Backups).
- Config‑CLI Subcommands funktionieren inkl. Exit‑Codes und klarer Ausgaben.
- Auto‑Reload reagiert zuverlässig auf Dateiänderungen; UI zeigt neuen Status/Listen.
- Profil‑Shortcuts können gezielt entfernt werden (nur die durch das Profil installierten).
- GNOME‑Shortcuts Install/Remove und Autostart Buttons funktionieren; Statusmeldungen und Logging sind nachvollziehbar.
- README/DESIGN/IMPLEMENTATION_LOG sind komplett und konsistent.
- Checkliste (Abschnitt 23) markiert V1‑Features als abgeschlossen.

Leitplanken
- Wayland‑freundlich, keine globalen Key‑Grabs aus der App (GNOME Shortcuts steuern CLI).
- Kein TCP‑Server; IPC via Unix‑Socket (0600).
- Keine Retries/Backoffs/Throttles in V1.
- requests optional; bei Fehlen klare Meldungen.

Hinweise
- Bei Rename von Actions die Triggers bewusst nicht automatisch anpassen (Explizitheit).
- Backups können wachsen; Retention ist optional (künftige Verbesserung).
