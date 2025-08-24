# Weiterführungs‑Prompt – Settings Reload, Inline‑Edit, Health‑Check, Config‑CLI, Profile‑Shortcuts Uninstall

Ziel
- Laufenden Zustand nach Profil‑Install/CLI‑Änderungen zuverlässig übernehmen (ohne App‑Neustart).
- Integration‑Werte direkt in der UI bearbeiten (whitelisted Keys).
- Optionalen Health‑Check für lokale HTTP‑Trigger anzeigen.
- CLI‑Kommandos für Config‑Reset/Backup/Restore bereitstellen.
- Profil‑Shortcuts wieder entfernen können (nur die durch ein Profil installierten).
- Optional: Auto‑Reload via Gio.FileMonitor.

Kontext und Referenzen
- DESIGN.md – siehe Abschnitt 29 „Geplante Erweiterungen – Settings Reload, Inline‑Edit, Health‑Check, Config‑CLI, Profile‑Shortcuts Uninstall“ (soeben ergänzt).
- Bestehende Module:
  - src/wbridge/gui_window.py (Settings/Actions UI)
  - src/wbridge/config.py (Settings/Actions Laden, Defaults, Platzhalter)
  - src/wbridge/cli.py (CLI)
  - src/wbridge/profiles_manager.py (Profile install; Shortcuts‑Install)
  - src/wbridge/gnome_shortcuts.py (Gio.Settings‑Helper)
  - src/wbridge/platform.py (Pfade)
- Aktuelles Verhalten:
  - Actions‑Run wird ausschließlich durch integration.http_trigger_enabled (Settings) enabled/disabled.
  - Nach profilbasiertem Settings‑Patch wird app._settings nicht neu geladen → UI bleibt evtl. auf altem Stand.
  - Kein Inline‑Edit der Integration‑Werte in der UI.
  - Kein Health‑Check‑Knopf/Anzeige.
  - Kein Config‑Reset/Backup/Restore in der CLI.
  - Kein gezielter „Profil‑Shortcuts entfernen“‑Befehl.

Umzusetzende Aufgaben (Implementierung)

1) Settings Reload (GUI)
- Nach erfolgreichem Profil‑Install (Settings‑Tab → „Installieren“):
  - app._settings = load_settings()
  - self._refresh_integration_status()
  - self.refresh_actions_list()
- Settings‑Tab: Button „Reload Settings“
  - Lädt settings.ini neu und aktualisiert Status + Actions‑Liste.
- Optional: Gio.FileMonitor
  - Beobachtet ~/.config/wbridge/settings.ini und ~/.config/wbridge/actions.json
  - On change: (debounced) reload/apply → _refresh_integration_status() + refresh_actions_list()

2) Inline‑Edit der Integration (GUI)
- Settings‑Tab: Editierbare Felder für Whitelist‑Keys in [integration]:
  - http_trigger_enabled (Gtk.Switch)
  - http_trigger_base_url (Gtk.Entry)
  - http_trigger_trigger_path (Gtk.Entry)
- „Speichern“: Atomarer Write (tempfile + os.replace), Validierung:
  - base_url: http/https, localhost erlaubt
  - trigger_path: beginnt mit „/“
- „Verwerfen“: Reload Settings
- Nach Speichern: Integration Status + Actions‑Liste aktualisieren

3) Health‑Check (optional)
- Settings‑Tab: Button „Health check“
- HTTP GET: {integration.http_trigger_base_url}{integration.http_trigger_health_path} (Default /health)
- Anzeige: OK/Fehler + HTTP‑Code; optionale Farbindikation
- requests optional; falls nicht vorhanden, urllib‑Fallback oder klare Fehlermeldung

4) Config‑CLI (optional)
- Neue Subcommands:
  - wbridge config show-paths
    - Gibt Pfade aus (settings.ini, actions.json, state/log)
  - wbridge config reset [--keep-actions] [--keep-settings] [--backup]
    - Löscht standardmäßig beide Dateien im ~/.config/wbridge/, optional Backups mit Timestamp
    - Exit-Codes: 0 ok, 3 failure
  - wbridge config backup [--what actions|settings|all]
    - Speichert Kopie(n) unter .bak-YYYYmmdd-HHMMSS
  - wbridge config restore --file /path/to/backup
    - Atomar zurückschreiben
- Ausgabe: kompakt und robust, JSON‑ähnliche Zusammenfassung erlaubt

5) Profile‑Shortcuts Uninstall (optional)
- profiles_manager.remove_profile_shortcuts(name):
  - Liest shortcuts.json des Profils
  - Synthetisiert Suffixe „wbridge-<normalized-name>/“
  - Entfernt passende Einträge via gnome_shortcuts.remove_binding(...)
- CLI:
  - wbridge profile uninstall --name NAME --shortcuts-only
- GUI (Settings‑Tab → Profile‑Bereich):
  - Button „Profil‑Shortcuts entfernen“
- Keine anderen Custom‑Keybindings antasten

Module/Dateien (Erweiterungen/Änderungen)
- src/wbridge/gui_window.py
  - Nach Profil‑Install Settings reload + UI refresh
  - Buttons: „Reload Settings“, „Health check“, Inline‑Edit‑Widgets, „Speichern/Verwerfen“
  - Optional Gio.FileMonitor Implementierung
- src/wbridge/config.py
  - Hilfsfunktionen für atomare Writes (INI) ggf. ergänzen
  - Validierungs‑Helpers (Base‑URL, Trigger‑Pfad) (alternativ lokal in gui_window.py)
- src/wbridge/cli.py
  - Neue „config“ Subcommands (show-paths/reset/backup/restore)
  - „profile uninstall --shortcuts-only“
- src/wbridge/profiles_manager.py
  - remove_profile_shortcuts(name) implementieren
- src/wbridge/gnome_shortcuts.py
  - remove_binding(path_suffix) existiert; wiederverwenden

Testplan (manuell)

1) Disabled → Enabled nach Profil‑Install
- Ausgangszustand: http_trigger_enabled=false
- Aktion: wbridge profile install --name witsy --patch-settings
- Erwartung:
  - GUI (ohne Neustart): Integration Status zeigt enabled=true
  - Actions‑Run aktiv
  - Health‑Check OK, wenn lokaler Dienst läuft (127.0.0.1:18081/health)

2) Inline‑Edit
- base_url/trigger_path via UI ändern → Speichern
- Erwartung:
  - settings.ini enthält neue Werte
  - Integration Status aktualisiert
  - Actions‑Run nutzt neue URL/Path
- „Verwerfen“ setzt UI wieder auf Settings‑Stand

3) Health‑Check
- Dienst aus → Fehleranzeige
- Dienst an → OK + HTTP 200

4) Config‑CLI
- wbridge config show-paths → zeigt Pfade
- wbridge config reset --backup → Backups erstellt; Dateien entfernt; GUI zeigt Defaults
- wbridge config backup/restore → Dateien konsistent gesichert/wiederhergestellt

5) Profile‑Shortcuts Uninstall
- wbridge profile install --name witsy --install-shortcuts
- wbridge profile uninstall --name witsy --shortcuts-only
- Erwartung: GNOME‑Einstellungen zeigen die Profil‑Shortcuts nicht mehr

6) FileMonitor (optional)
- settings.ini extern editieren (Editor)
- Erwartung: UI aktualisiert Status/Actions automatisch

Akzeptanzkriterien
- Settings‑Reload funktioniert (nach Profil‑Install/CLI‑Änderungen ohne App‑Neustart).
- Inline‑Edit speichert und reflektiert Integration‑Werte korrekt (inkl. Enable/Disable der Actions).
- Health‑Check liefert nachvollziehbare Anzeige (OK/Fehler).
- Config‑CLI führt Reset/Backup/Restore zuverlässig aus, mit Backups.
- Profil‑Shortcuts lassen sich gezielt entfernen (nur die aus shortcuts.json des Profils).
- Doku/Log aktualisiert (README/DESIGN/IMPLEMENTATION_LOG).

Leitplanken
- Wayland‑freundlich, keine globalen Key‑Grabs; GNOME Shortcuts rufen CLI auf.
- Kein TCP‑Server in V1; IPC via Unix‑Socket (0600).
- Keine Retries/Backoffs/Throttles in V1.
- requests optional; bei Fehlen klare Fehlermeldung.

Nach Umsetzung
- README: Abschnitte „Reload Settings“, „Health check“, „Config‑CLI“, „Profile‑Shortcuts entfernen“ ergänzen.
- DESIGN: Abschnitt 29 ggfs. um finale Details/Entscheidungen aktualisieren.
- IMPLEMENTATION_LOG: Neuer Eintrag (Datum/Uhrzeit, Änderungen, Testresultate, offene Punkte).
