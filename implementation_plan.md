# Implementation Plan

[Overview]
Professionalisierung der UI von wbridge: Umstellung auf linksseitige Navigation mit Gtk.Stack + Gtk.StackSidebar, klare Trennung der Bereiche (History, Actions, Triggers, Shortcuts, Settings, Status & Log), verbesserte Editierbarkeit, eindeutige Semantik und Stabilität der Layouts.

Ziel ist ein robustes, Wayland‑freundliches UX-Design, das die bestehenden Funktionen strukturiert präsentiert, die häufigsten Workflows (History anwenden, Aktionen starten, Shortcuts verwalten) in möglichst wenig Interaktionen ermöglicht und Stolpersteine beseitigt (Expander/Preview‑Verrutschen, unklare Checkboxes, verborgene Shortcuts). Gleichzeitig werden Leitplanken für zukünftige Erweiterungen gelegt: Multi‑Targets/Endpunkte für HTTP, optionales Zurückschreiben von Action‑Ergebnissen in die Selektion, und langfristig MIME‑Type‑Support.

Hochrangige Änderungen:
- Navigation: Linksseitige StackSidebar, rechts Inhaltsbereich (Stack). Kein Notebook mehr.
- Trennung Actions vs. Triggers, dedizierte Seiten für Shortcuts und Status/Log.
- Master‑Detail‑Editor für Actions (Liste links im Seiteninhalt, rechts editierbarer Bereich), Form‑Editor als Primäransicht mit optionalem Raw‑JSON‑Tab.
- Eindeutige Bezeichnungen/Tooltips für Profile‑Installationsoptionen und Settings.
- Stabilere Listendarstellungen (Wrap, Ellipsize, konsistente Zeilenhöhen), kein „Verrutschen“ der Previews.
- Optionales „on_success.apply_to“ bei Aktionen (Antwort in Clipboard/Primary übernehmen).
- Vorplanung für Multi‑Endpoints (mehrere Ziel‑Apps) und Trigger‑Erweiterungen.
- Pro Seite ein einklappbarer Hilfebereich (Help) mit ausführlichen Texten/Beispielen aus Ressourcen.
- Internationalisierung: UI‑Strings in Englisch (Default) via gettext, Mehrsprachigkeit vorbereitet (de später).

[Types]
Minimale Änderungen am Typsystem: Klare Enums/Strukturfelder für Selektion, Erfolgsverhalten und künftige Endpunkte.

Vollständige Spezifikationen:
- Enum SelectionType: Literal["clipboard", "primary"]
- Enum ApplyTo: Literal["none", "clipboard", "primary"]

- Action (HTTP)
  - name: str (required, unique)
  - type: "http" (required)
  - method: "GET" | "POST" (default "GET")
  - url: str (required; Platzhalter erlaubt)
  - headers: dict[str,str] (optional)
  - params: dict[str,str] (optional)
  - json: object | array | string (optional)
  - data: object | array | string (optional)
  - timeout_s: int (optional; default 5)
  - on_success: object (optional)
    - apply_to: ApplyTo (optional; default "none")
    - response_path: str (optional; Pfad zum zu übernehmenden Text; v1: "" → gesamter Body‑Text; v1.1: JSON‑Pfad, z. B. "text")

- Action (Shell)
  - name: str (required, unique)
  - type: "shell"
  - command: str (required)
  - args: list[str] (optional)
  - use_shell: bool (optional; default false)
  - on_success: object (optional; wie oben, apply_to + response_path unterstützt „stdout“)

- Triggers
  - triggers: dict[str, str] (alias → action.name)

- Settings (settings.ini)
  - [general]
    - history_max: int (default 50)
    - poll_interval_ms: int (default 300)
  - [integration]
    - http_trigger_enabled: bool
    - http_trigger_base_url: str
    - http_trigger_health_path: str
    - http_trigger_trigger_path: str
  - [gnome]
    - manage_shortcuts: bool
    - binding_prompt: str
    - binding_command: str
    - binding_ui_show: str
  - Erweiterung (v1.1, geplant):
    - [endpoint.<name>]
      - base_url, trigger_path, health_path (ermöglicht mehrere Ziel‑Endpunkte)
    - Platzhalter: {config.endpoint.NAME.base_url} in Aktionen.

Validierungsregeln:
- action.name darf nicht leer sein; type ∈ {"http","shell"}.
- http: url required, method ∈ {"GET","POST"}; headers/params dict; json/data dict/array/string.
- shell: command required; args list; use_shell bool.
- on_success.apply_to ∈ {"none","clipboard","primary"}; response_path string.
- triggers‑Werte müssen existierende action.name referenzieren.

[Files]
Umstellung der UI-Struktur und gezielte Erweiterungen ohne externe Abhängigkeiten.

Neu:
- Ressourcen für Hilfe (englisch, lokalisierbar):
  - src/wbridge/help/en/history.md
  - src/wbridge/help/en/actions.md
  - src/wbridge/help/en/triggers.md
  - src/wbridge/help/en/shortcuts.md
  - src/wbridge/help/en/settings.md
  - src/wbridge/help/en/status.md
  - Placeholder‑Struktur für weitere Sprachen: src/wbridge/help/<lang>/<topic>.md
- Internationalisierung (gettext):
  - gettext‑Domain: "wbridge"; Strings via _("...").
  - Locale‑Verzeichnisstruktur vorbereitet (po/mo) – Erstellung der .po/.mo außerhalb des Codes (Tooling).
- Optional: src/wbridge/assets/style.css (kleines CSS für Abstände, dim-label).
- Optional (später): modulare UI‑Dateien (ui_actions.py, ui_triggers.py, ui_shortcuts.py, ui_history.py, ui_status.py) zur Entkopplung – zunächst bleibt alles in gui_window.py.

Bestehend – zu ändern:
- src/wbridge/gui_window.py
  - Entfernen Gtk.Notebook, einführen Gtk.Stack + Gtk.StackSidebar, Seiten: "History", "Actions", "Triggers", "Shortcuts", "Settings", "Status".
  - Actions: Master‑Detail statt Expander‑Liste; Formular‑Editor (Primär), optionaler Raw‑JSON‑Tab.
  - Triggers: separate Seite mit Tabelle und eindeutigen Fehlermeldungen.
  - Shortcuts: eigene Seite (sichtbar/editierbar) mit Einschränkung:
    - Bearbeitbar nur wbridge‑verwaltete Einträge (deterministische Suffixe "wbridge-.../") und empfohlene Bindings.
    - Optionaler Modus "alle Custom Shortcuts anzeigen (read‑only)"; fremde Einträge nicht veränderbar.
  - Status: erweiterte Systeminfos + Log‑Tail (Datei ~/.local/state/wbridge/bridge.log).
  - History: stabilere Zeilen (Wrap, Ellipsize), gleiche Bedienlogik, optional Filter‑Entry (v1.1).
  - Help‑Bereich pro Seite: einklappbar (Expander/Revealer), lädt Text aus src/wbridge/help/en/<topic>.md.
  - Tooltips/Labels anpassen (Eindeutigkeit „Actions überschreiben“, „Settings patchen“, „Shortcuts installieren“).
- src/wbridge/actions.py
  - run_http_action/run_shell_action: optionale Auswertung von on_success (apply_to, response_path); Timeout respektieren; Fehlertexte belassen.
- src/wbridge/config.py
  - validate_action_dict: Felder timeout_s (int ≥1) und on_success (Schema) erlauben.
  - expand_placeholders: unverändert nutzbar; optional zukünftige Endpoints.
- src/wbridge/app.py
  - Keine großen Änderungen, aber: UI‑Bring‑to‑front unverändert; evtl. Window‑Defaultsize an Stack‑Layout anpassen (z. B. 1000x650).
- src/wbridge/gnome_shortcuts.py
  - Unverändert; UI nutzt es umfassender (Listen, Install/Remove/Edit im wbridge‑Scope).
- README.md / DESIGN.md
  - Screenshots/Abschnitte zu neuer Navigation, Seiten, Help‑Konzept, i18n, und Shortcuts‑Scope aktualisieren.

[Functions]
Fokussierte Funktionsänderungen in gui_window.py und moderate Erweiterungen in actions.py/config.py.

Neu (gui_window.py):
- def _build_navigation(self) -> tuple[Gtk.StackSidebar, Gtk.Stack]
- def _page_history(self) -> Gtk.Widget
- def _page_actions(self) -> Gtk.Widget
- def _page_triggers(self) -> Gtk.Widget
- def _page_shortcuts(self) -> Gtk.Widget
- def _page_settings(self) -> Gtk.Widget
- def _page_status(self) -> Gtk.Widget
- def _log_tail(self, max_lines: int = 200) -> list[str]
- def _help_panel(self, topic: str) -> Gtk.Widget
- def _load_help_text(self, topic: str) -> str
- def _render_help(self, text: str) -> Gtk.Widget
- def _actions_load_list(self) -> list[dict]
- def _actions_select(self, name: str) -> None
- def _actions_bind_form(self, action: dict) -> None
- def _actions_save_form(self) -> None
- def _actions_toggle_editor(self, mode: Literal["form","json"]) -> None

Geändert (gui_window.py):
- refresh_actions_list() → ersetzt durch Master‑Detail Logik (Liste neu laden + Auswahl binden).
- _rebuild_triggers_editor() → ersetzt durch Tabellen‑Seite (_page_triggers + _triggers_save()).
- _on_action_run_clicked(): Quelle konsistent bestimmen, Ergebnis im Statusbereich der Seite, ggf. apply_to umsetzen (falls im Runner nicht automatisch).
- Shortcuts‑Editor:
  - Auflisten/Erstellen/Bearbeiten/Löschen ausschließlich für wbridge‑verwaltete Einträge; Validierung von Namen/Bindings; Konflikte detektieren und anzeigen.
  - Optional: Schalter "Show all custom (read‑only)".

Neu (actions.py):
- parse_response_text(resp, response_path: str | None) -> str
- apply_to_selection(apply_to: ApplyTo, text: str, app_ctx) → erfolgt primär im App/UI‑Kontext; für CLI‑Pfad in app.py.

Geändert (actions.py):
- run_http_action(...): timeout_s berücksichtigen; Rückgabe (ok,msg) bleibt; response_text ggf. extrahieren (wenn on_success genutzt).
- run_action(...): on_success nicht direkt anwenden (UI/Server entscheidet anhand Kontext), aber response_text zurückliefern (message enthält Detail).

Geändert (config.py):
- validate_action_dict: on_success prüfen (apply_to ∈ {"none","clipboard","primary"}, response_path: str), timeout_s: int ≥1 (optional).
- load_actions_raw/write_actions_config unverändert (Felder werden durchgelassen).

[Classes]
Keine neuen Kernklassen erforderlich; optional View‑Klassen später.

Neu (optional Phase 2):
- class ActionsView(Gtk.Box)
- class TriggersView(Gtk.Box)
- class ShortcutsView(Gtk.Box)
- class HistoryView(Gtk.Box)
- class StatusView(Gtk.Box)

Geändert:
- class MainWindow (in gui_window.py)
  - Aufbau Stack/Sidebar statt Notebook.
  - Initialisierung der Seitenfabrik (_page_…).
  - Entfernt: Expander‑basierter Actions‑Editor; ersetzt durch Master‑Detail.
  - Ergänzt: Help‑Bereiche, gettext‑basierte Strings.

[Dependencies]
- Keine neuen Hard‑Dependencies für HTTP/Shell.
- Neu: gettext‑Einbindung (Python stdlib). Lokale .mo/.po Dateien optional; Fallback auf Englisch.

Integration:
- Gtk.Stack / Gtk.StackSidebar aus GTK4.
- Optional CSS via Gtk.CssProvider (keine externe Lib).

[Testing]
Manuelle Tests plus gezielte Checks im UI.

Erforderliche Tests:
- Navigation: Seitenwechsel per Sidebar, Zustände bleiben konsistent, Fokus/Tab‑Reihenfolgen sinnvoll.
- History: Listenaufbau stabil, Wrap/Ellipsize korrekt, Apply/Swap funktionieren.
- Actions:
  - Liste → Auswahl → Formular → Save (validiert), JSON‑Tab → Save; Reload spiegelt Datei.
  - Run: Quelle Clipboard/Primary/Text; http_trigger_enabled=false → Run disabled + Hinweis.
  - on_success.apply_to=clipboard/primary → Ergebnistext landet korrekt in Auswahl (HTTP: Body oder response_path; Shell: stdout).
- Triggers: Tabelle laden, Alias/Action validiert, Save persistiert; Aktionen mit Trigger‑Alias per CLI funktionieren.
- Shortcuts:
  - Nur wbridge‑verwaltete Einträge editierbar (Empfehlungen + profilinstallierte wbridge‑Suffixe); fremde Custom‑Shortcuts sind read‑only oder ausgeblendet.
  - Install/Remove funktioniert; PATH‑Hinweis sichtbar; Konflikte werden angezeigt.
- Status & Log: Environment, GDK Infos, Log‑Tail zeigt letzte Zeilen; Refresh aktualisiert.
- Help: Pro Seite Expander vorhanden, Inhalte aus Ressourcen geladen; Beispiele korrekt gerendert.
- i18n: Fallback auf Englisch bei fehlender Übersetzung; ausgewählte Keys via gettext aufrufbar.
- Regression: CLI‑Befehle intakt (ui show, history, selection, trigger).

Validierungsstrategie:
- UI‑Smoke für jede Seite.
- Einfache Fehleingaben (leere Namen, doppelte Aliase) → klare Fehlerlabels.
- HTTP ohne requests → klarer Fehlertext.

[Implementation Order]
Schrittweise Umstellung zur Reduktion von Risiko.

1) Navigation umstellen
   - gui_window.py: Notebook entfernen, Gtk.Stack + Gtk.StackSidebar integrieren; Stub‑Seiten einhängen.
2) History Seite stabilisieren
   - Bestehende Widgets übernehmen, Wrap/Ellipsize, konsistente Zeilenhöhen; optional Filter vorbereiten (ausgeblendet).
3) Actions Master‑Detail
   - Linke Liste der Actions; rechts Form‑Editor (Name/Typ + HTTP/Shell Felder), Tab/Toggle zum Raw‑JSON.
   - Save/Cancel/Duplicate/Delete anpassen; Reload integriert.
4) Triggers Seite
   - Tabelle (Alias ↔ Action), Add/Save/Delete, Validierung; Persistenz via write_actions_config.
5) Shortcuts Seite (empfohlene + wbridge‑verwaltete)
   - Anzeigen/Erstellen/Bearbeiten/Löschen nur wbridge‑Scope; optional „alle anzeigen (read‑only)“; Konflikthinweise; PATH‑Hinweis.
6) Settings Seite bereinigen
   - Inline‑Edit Integration (bereits vorhanden) klar beschriften; Tooltips erläutern Bedeutung („Actions überschreiben“, „Settings patchen“, Priorität Shortcuts).
7) Status & Log
   - Log‑Tail implementieren; zusätzliche Env/Backend‑Infos.
8) Help & i18n
   - Help‑Resourcen anlegen, Loader + Expander je Seite; gettext initialisieren, Strings auf _("…") umbauen.
9) Actions on_success (optional in v1)
   - config.validate_action_dict erweitern, actions.run_* response_text extrahieren.
   - app/gui: falls on_success gesetzt, Text in Clipboard/Primary anwenden.
10) Feinschliff & Doku
   - README/DESIGN Screens/Abschnitte aktualisieren; Labels/Tooltips prüfen.

Phasen für Multi‑Endpoints/MIME (Planung, später):
- v1.1: Sections [endpoint.<name>], UI‑Dropdown „Ziel‑Endpunkt“ pro Action; Health‑Check je Endpunkt.
- v1.2: MIME‑Vorbereitung (ContentProvider Pfade); Cross‑Platform Schnittstellen definieren.
