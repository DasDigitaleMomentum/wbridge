# Weiterführungs-Prompt (wbridge) – Profile/Presets + Witsy-Integration

Ziel
- Dieses Dokument ist ein selbständiger Prompt für die nächste Session. Es führt die Umsetzung des Profile/Preset-Systems und die Integration eines „Witsy“-Profils aus.
- Enthält Akzeptanzkriterien und Testplan.
- Grundlage ist die aktualisierte Spezifikation in DESIGN.md (Abschnitte 25–28).

---

## Kontext und Referenzen (vorab lesen)

- README.md (Kurzüberblick, CLI/GUI)
- DESIGN.md
  - Profil-Spezifikation: Abschnitte 25 („Profiles & Presets“), 26 („Witsy‑Profil“)
  - Testplan: Abschnitt 27
  - Nächste Schritte: Abschnitt 28
- IMPLEMENTATION_LOG.md (letzter Eintrag „History/GUI/IPC enhancements“)
- RESEARCH_QUESTION.md (Clipboard/Wayland Hinweise)

Relevante Module für diese Session:
- src/wbridge/config.py (Settings/Actions Laden, Platzhalter)
- src/wbridge/actions.py (HTTP/Shell Actions Engine)
- src/wbridge/cli.py (CLI Subcommands)
- src/wbridge/gui_window.py (Settings/Actions Tabs, UI-Interaktion)
- src/wbridge/gnome_shortcuts.py (Gio.Settings-Helper für Shortcuts)
- src/wbridge/platform.py (Pfade, XDG-Verzeichnisse, Env)
- src/wbridge/logging_setup.py (Logging)

---

## Umzusetzende Aufgaben (Implementierung)

1) ProfileManager (neues Modul, z. B. src/wbridge/profiles.py)
   - Built-in Profile-Struktur im Paket: src/wbridge/profiles/<name>/ mit:
     - profile.toml (Metadaten)
     - actions.json (Pflicht; inkl. triggers)
     - shortcuts.json (empfohlen)
     - settings.patch.ini (optional)
   - API:
     - list_builtin_profiles() - List[str]
     - show_profile(name) - Dict (Metadaten + Kerninhalte für Anzeige)
     - install_profile(name, options) - Report:
       - options: overwrite_actions (bool), patch_settings (bool), install_shortcuts (bool), dry_run (bool)
       - Verhalten: Mergen/Ersetzen von actions.json, Patchen whitelisted Settings, optional Shortcuts installieren.
       - Backups: actions.json.bak-YYYYmmdd-HHMMSS und settings.ini.bak-YYYYmmdd-HHMMSS
     - Utilities: Laden von Paketressourcen (json/toml/ini), atomare Writes.

2) CLI – Profile Subcommands (src/wbridge/cli.py)
   - wbridge profile list
   - wbridge profile show --name witsy
   - wbridge profile install --name witsy [--overwrite-actions] [--patch-settings] [--install-shortcuts] [--dry-run]
   - Exit-Codes: 0 ok, 2 invalid args, 3 failure
   - Ausgabe: prägnante Zusammenfassung (Änderungen/Backups/Fehler)

3) UI – Settings-Tab: Bereich „Profile“
   - Dropdown „Profil“ (mindestens „Witsy“)
   - Buttons: „Anzeigen“ (Kurzinfo), „Installieren…“
     - Dialog/Controls mit Checkboxen:
       - Actions installieren/überschreiben
       - Settings patchen
       - Shortcuts installieren
     - Ergebnis-/Fehlerlabel
   - Bereich „Integration Status“ (falls nicht vorhanden):
     - Anzeigen: integration.http_trigger_enabled, Base-URL, Trigger-Pfad
     - Bei disabled: deutlicher Hinweis für Actions-Tab

4) Actions-Tab – Verhalten
   - Wenn integration.http_trigger_enabled=false: Run-Buttons disabled oder klarer Hinweis („HTTP Trigger disabled – aktivieren in Settings“).
   - Sonst wie gehabt: Quelle (Clipboard/Primary/Text), Run, Resultat (Success/Failed + Message). Fehlende requests-Lib klar anzeigen.

5) Built-in „Witsy“-Profil beilegen (als Paketressourcen)
   - actions.json (Profil):
     - Mit Text (POST/JSON):
       - „Witsy: prompt“ – POST { cmd: "prompt", text: "{text}" }
       - „Witsy: command“ – POST { cmd: "command", text: "{text}" }
     - Ohne Text (GET):
       - „Witsy: chat“/„scratchpad“/„readaloud“/„transcribe“/„realtime“/„studio“/„forge“ – GET ?cmd=NAME
     - Gemeinsame URL: {config.integration.http_trigger_base_url}{config.integration.http_trigger_trigger_path}
   - triggers (Profil):
     {
       "prompt": "Witsy: prompt",
       "command": "Witsy: command",
       "chat": "Witsy: chat",
       "scratchpad": "Witsy: scratchpad",
       "readaloud": "Witsy: readaloud",
       "transcribe": "Witsy: transcribe",
       "realtime": "Witsy: realtime",
       "studio": "Witsy: studio",
       "forge": "Witsy: forge"
     }
   - shortcuts.json (Empfehlung):
     - Prompt: wbridge trigger prompt --from-primary → <Ctrl><Alt>p
     - Command: wbridge trigger command --from-clipboard → <Ctrl><Alt>m
     - Show UI: wbridge ui show → <Ctrl><Alt>u
   - settings.patch.ini:
     [integration]
     http_trigger_enabled = true
     http_trigger_base_url = http://127.0.0.1:18081
     http_trigger_trigger_path = /trigger
     ; http_trigger_health_path = /health

---

## Merge-/Backup-Strategie (verbindlich)

- Aktionen (actions.json):
  - Kollision anhand „name“.
  - Default: User first (keine Überschreibung vorhandener gleichnamiger Actions/Trigger).
  - --overwrite-actions: Profil-Action/Trigger überschreibt vorhandene gleichnamige Einträge.
- Settings (settings.ini):
  - Nur whitelisted Keys: [integration] http_trigger_enabled, http_trigger_base_url, http_trigger_trigger_path, http_trigger_health_path
  - Default: User first; nur überschreiben, wenn --patch-settings gesetzt.
- Shortcuts:
  - Installation optional; Konflikte (Binding belegt) melden, kein erzwungenes Überschreiben.
- Backups:
  - Vor jeder Änderung Timestamp-Backups anlegen:
    - actions.json.bak-YYYYmmdd-HHMMSS
    - settings.ini.bak-YYYYmmdd-HHMMSS

---

## Testplan (manuell)

1) Profil-Erkennung
   - wbridge profile list → enthält „witsy“
   - wbridge profile show --name witsy → zeigt Metadaten + Kerninhalte

2) Dry-Run
   - wbridge profile install --name witsy --dry-run → listet Änderungen (Backups, Merges), ohne Dateischreibzugriffe

3) Installation – Actions
   - Backup/Reset ~/.config/wbridge/actions.json
   - wbridge profile install --name witsy --overwrite-actions
   - Prüfen: actions.json enthält „Witsy: …“-Einträge, triggers vollständig; Backup existiert

4) Installation – Settings
   - wbridge profile install --name witsy --patch-settings
   - Prüfen: settings.ini [integration] http_trigger_enabled=true; Base-URL/Trigger-Pfad gesetzt; Backup existiert

5) Installation – Shortcuts
   - wbridge profile install --name witsy --install-shortcuts
   - GNOME Einstellungen → Einträge vorhanden; Konflikte werden gemeldet

6) Actions-Tab
   - http_trigger_enabled=true; Witsy läuft lokal (Health check).
   - Quelle=Text → „Hallo Welt“ → Run „Witsy: prompt“ → Success (Witsy‑Log zeigt Request)
   - Quelle=Clipboard → zuvor per CLI: wbridge selection set --which clipboard --text "X" → Run „Witsy: command“ → Success
   - Aktion ohne Text (z. B. „Witsy: chat“) → Run → Success
   - Disabled-Fall: http_trigger_enabled=false → Run disabled oder klarer Hinweis sichtbar

7) CLI Triggers
   - wbridge trigger prompt --from-primary
   - wbridge trigger chat --from-clipboard

8) Fehlerpfade
   - requests fehlt: http action Failed – klarer Hinweis
   - Witsy nicht aktiv: HTTP Fehler → UI zeigt Failed + Message (HTTPCode/ConnectionError)

---

## Akzeptanzkriterien

- Witsy‑Profil vollständig installierbar (Actions/Triggers, optional Settings/Shortcuts) mit Backups und Merge nach den Regeln.
- CLI: profile list/show/install funktionieren inkl. Exit-Codes und aussagekräftiger Ausgaben.
- UI (Settings‑Tab): Profil‑Anzeige, Installationsoptionen, Ergebnis/Fehler sichtbar; Integration‑Status klar dargestellt.
- Actions‑Tab: Witsy‑Aktionen ausführbar; Quelle (Clipboard/Primary/Text) wirksam; Resultate (Success/Failed + Message) sichtbar; disabled‑Hinweise wenn http‑Trigger off.
- Doku in DESIGN.md konsistent (Profile‑Abschnitte vorhanden; Quickstart in README kann im Anschluss ergänzt werden).

---

## Leitplanken (weiterhin gültig)

- Wayland-freundlich, keine globalen Key-Grabs aus der App (GNOME Shortcuts steuern CLI).
- Nur GTK4/GDK für Clipboard/Primary (kein wl-clipboard).
- IPC: $XDG_RUNTIME_DIR/wbridge.sock (0600), JSON pro Zeile.
- Keine Retries/Backoffs/Throttles (V1).
- Lokale HTTP‑Ziele (127.0.0.1); keine externen Endpunkte in Standard-Profilen.
- requests ist optional; UI/CLI melden fehlende Abhängigkeit klar.

---

## Hinweise (nach Umsetzung)

- README: Kurzabschnitt „Profile & Witsy Quickstart“ (z. B. wbridge profile install --name witsy --patch-settings --overwrite-actions).
- DESIGN: Profile‑Abschnitt (25–28) aktuell halten, falls Details während Implementierung angepasst werden.
