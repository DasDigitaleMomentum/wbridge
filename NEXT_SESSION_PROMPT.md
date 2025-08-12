# Weiterführungs-Prompt für die nächste Session (wbridge)

Ziel
- Diese Datei enthält einen ausführlichen Prompt für die Fortsetzung der Entwicklung in einer neuen Session, inklusive aller relevanten Kontexte und Referenzen.
- Einfach in der neuen Session als Eingabe verwenden.

---

## Kurzfassung (Was als Nächstes zu tun ist)

Implementiere die nächste Ausbaustufe gemäß DESIGN.md:
1) History + IPC/CLI
   - Server: history.list, history.apply, history.swap in app.py implementieren.
   - CLI: Subcommands in cli.py fertig verdrahten (list/apply/swap).
   - App: HistoryStore (src/wbridge/history.py) nutzen, der bereits existiert (Ringpuffer, dedupe, swap).
2) GUI – History-Tab
   - In src/wbridge/gui_window.py die beiden Sektionen (Clipboard/Primary) mit HistoryStore verbinden.
   - Anzeige der letzten N Einträge, Aktionen: „Als Clipboard setzen“, „Als Primary setzen“, „Swap“.
3) Actions-Tab
   - actions.json laden (src/wbridge/config.py) und Liste darstellen.
   - „Run“-Button (Quelle wählbar: Clipboard/Primary/Text) → src/wbridge/actions.py (http/shell) ausführen.
   - Ergebnis im UI anzeigen (Success/Failed + Message).
4) Settings-Tab (erste Iteration)
   - Basisinfos (Backend, Socket-Pfad, Log-Pfad) anzeigen.
   - Platzhalter-Buttons (noch ohne Funktion): „GNOME Shortcuts installieren/entfernen“, „Autostart aktivieren/deaktivieren“.
5) README + DESIGN aktualisieren, wenn Teile fertig sind (Checkliste).

Akzeptanzkriterien (für diese Stufe)
- CLI:
  - wbridge history list --which clipboard --limit 5 → Liste der letzten Einträge.
  - wbridge history apply --which primary --index 1 → setzt den Eintrag auf Primary.
  - wbridge history swap --which clipboard → tauscht die letzten zwei Einträge.
- GUI (History-Tab):
  - Zeigt Einträge pro Bereich (Clipboard/Primary).
  - Kontextaktionen/Buttons funktionieren (Apply/Swap).
- Actions-Tab:
  - Zeigt definierte Actions aus actions.json.
  - „Run“ führt Aktion aus und zeigt Resultat.

---

## Aktueller Funktionsstand (heute)

- IPC/CLI:
  - ui.show funktioniert (Fenster nach vorne bringen).
  - selection set/get funktioniert (Clipboard und Primary).
- GUI:
  - Gtk4 Notebook mit Tabs: History/Actions/Settings/Status (Scaffold, History-Interaktion lokal).
- Clipboard/Primary (Wayland):
  - Schreiben via Clipboard.set("...") (PyGObject wandelt in GValue).
  - Fallback via ContentProvider (String/Bytes) mit Referenzhaltung.
  - Lesen via read_text_async → read_text_finish.
- Monitoring:
  - SelectionMonitor (GLib.timeout_add) pollt Clipboard und Primary, dedupliziert und aktualisiert HistoryStore.

---

## Projektstruktur und Bedeutung der Dateien

- README.md
  - Quickstart (Installation, Start, CLI-Beispiele), Org-Repo Hinweise.
- DESIGN.md
  - Produktspezifikation, Architektur, IPC/CLI, Checklisten (Abschnitt 23), Clipboard Notes (Abschnitt 24).
- IMPLEMENTATION_LOG.md
  - Chronologie, Merges, nächste Schritte.
- RESEARCH_QUESTION.md
  - Zusammenfassung/Quellen zur GTK4/PyGObject Clipboard-Thematik unter Wayland, offene Fragen.
- src/wbridge/app.py
  - Gtk.Application (IPC-Server, Clipboard/Primary set/get, ui.show, SelectionMonitor/HistoryStore wiring).
- src/wbridge/gui_window.py
  - Notebook UI (History/Actions/Settings/Status) – funktionsfähiges Scaffold mit Set/Get-Buttons.
- src/wbridge/selection_monitor.py
  - Permanentes Monitoring per GLib.timeout_add + async reads; ruft Callback bei Änderungen.
- src/wbridge/history.py
  - Ringpuffer (Clipboard/Primary), dedupe, get/list/swap/apply-Logik.
- src/wbridge/cli.py
  - CLI Subcommands (ui/selection/…); History-Subcommands vorbereiten/vervollständigen.
- src/wbridge/server_ipc.py / src/wbridge/client_ipc.py
  - Unix Domain Socket (newline JSON) + Client-Hilfen.
- src/wbridge/actions.py
  - Aktionen (http/shell) mit Platzhaltern (Text, {config.*}).
- src/wbridge/config.py
  - settings.ini & actions.json laden, Placeholder-Expansion.
- src/wbridge/gnome_shortcuts.py
  - Gio.Settings-Helfer für GNOME Custom Shortcuts.
- src/wbridge/platform.py
  - XDG-Pfade, Socket/Autostart-Pfade, Env-Infos.
- src/wbridge/logging_setup.py
  - Logging (Konsole + ~/.local/state/wbridge/bridge.log).

---

## Technische Leitplanken (weiterhin gültig)

- Wayland-freundlich: Keine globalen Key-Grabs, keine Eingabe-Injektionen.
- Nur GTK4/GDK für Clipboard/Primary (kein wl-clipboard).
- IPC: $XDG_RUNTIME_DIR/wbridge.sock (0600), JSON pro Zeile.
- Keine Retries/Backoffs/Throttles (V1).
- Generische Nutzbarkeit (keine Produktnennung); optionales HTTP-Trigger-Ziel via Config.

---

## Nützliche Befehle (zum Testen)

- App starten:
  - python3 -m wbridge.app
- Fenster in den Vordergrund:
  - python3 -m wbridge.cli ui show
- Clipboard/Primary:
  - python3 -m wbridge.cli selection set --which clipboard --text "HELLO"
  - python3 -m wbridge.cli selection get --which clipboard
  - python3 -m wbridge.cli selection set --which primary --text "HELLO-P"
  - python3 -m wbridge.cli selection get --which primary
- Log ansehen:
  - tail -n 100 ~/.local/state/wbridge/bridge.log

---

## Vollständiger Prompt (zum Einfügen in die neue Session)

Bitte in einer neuen Session verwenden:

„
Ich übernehme die Weiterentwicklung des Projekts ‚wbridge‘ (Wayland‑freundliche Selection/Shortcut‑Bridge, GTK4/PyGObject). Lese folgende Dateien für Kontext und Vorgaben:
- README.md (Quickstart, CLI-Übersicht)
- DESIGN.md (Architektur, IPC/CLI, Checkliste, Abschnitt 24 Clipboard Notes)
- IMPLEMENTATION_LOG.md (bisherige Schritte, nächste Todos)
- RESEARCH_QUESTION.md (Clipboard/Wayland, Dokumentations- und API‑Hinweise)

Relevante Module:
- src/wbridge/app.py (Gtk.Application, IPC-Server, Clipboard/Primary, SelectionMonitor/HistoryStore wiring)
- src/wbridge/gui_window.py (Notebook UI: History/Actions/Settings/Status – Scaffold)
- src/wbridge/selection_monitor.py (Polling/Async read)
- src/wbridge/history.py (Ringpuffer)
- src/wbridge/cli.py (CLI Subcommands)
- src/wbridge/server_ipc.py / client_ipc.py (Unix Socket + JSON)
- src/wbridge/actions.py (Actions Engine)
- src/wbridge/config.py (settings.ini, actions.json)
- src/wbridge/gnome_shortcuts.py (Gio.Settings Helper)
- src/wbridge/platform.py (Pfade, Env)
- src/wbridge/logging_setup.py (Logging)

Umzusetzende Aufgaben dieser Session:
1) History + IPC/CLI
   - app.py: history.list/apply/swap im IPC-Handler implementieren.
   - cli.py: die History‑Subcommands (list/apply/swap) fertig verdrahten.
2) GUI – History-Tab
   - gui_window.py: HistoryStore anbinden, Einträge anzeigen (Clipboard/Primary separat), Aktionen (Apply/Swap).
3) Actions-Tab
   - actions.json laden und anzeigen, „Run“-Button mit Quellwahl (Clipboard/Primary/Text), Ausführung via actions.run_action, Ergebnis anzeigen.
4) Settings-Tab (v1)
   - Anzeige von Backend/Socket/Log; Platzhalter-Buttons (Shortcuts/Autostart) anlegen (Logik folgt später).
5) Doku
   - README/DESIGN.md aktualisieren (GUI Überblick, Checkliste fortschreiben), wenn obige Punkte erfüllt sind.

Akzeptanzkriterien:
- CLI:
  - wbridge history list --which clipboard --limit 5 liefert Liste.
  - wbridge history apply --which primary --index 1 setzt Eintrag.
  - wbridge history swap --which clipboard tauscht die letzten 2 Einträge.
- GUI:
  - History‑Tab zeigt Einträge und kann Apply/Swap ausführen.
- Actions-Tab:
  - Listet actions.json und kann testweise ausführen (Resultat sichtbar).

Leitplanken:
- Nur GTK4/GDK‑APIs (kein wl-clipboard).
- Keine Key‑Injection.
- IPC: $XDG_RUNTIME_DIR/wbridge.sock (0600), JSON pro Zeile.
- Keine Retries/Backoffs (V1).
- Generische Nutzbarkeit (keine Produktnennung).
„

---

## Hinweise zu Querverweisen

- DESIGN.md Abschnitt 23 (Checkliste): Hake Punkte nach erfolgreicher Umsetzung ab.
- DESIGN.md Abschnitt 24 (Clipboard Notes): Grundlage für die bestehende Clipboard‑Implementierung und Wayland‑Details.
- IMPLEMENTATION_LOG.md: Nach jedem Commit kurz zusammenfassen.
- README.md: Sobald History/Actions UI bedienbar sind, um eine kurze GUI‑Einführung erweitern (z. B. „History zeigt N Einträge, Aktionen rechtsklick/Buttons“).

---

## Was die neue Session „nicht“ tun soll

- Keine Tool‑Abhängigkeiten wie wl-clipboard.
- Keine globalen Hotkey‑Grabs auf GNOME (Shortcuts sollen weiterhin CLI starten).
- Keine Express‑Server/Netzwerkdienste einführen (HTTP‑Trigger bleibt extern/optional via Config).
