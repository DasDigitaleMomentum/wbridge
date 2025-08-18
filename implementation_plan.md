# Implementation Plan

[Overview]
Refaktorierung des wbridge-Codes in kleinere, klar abgegrenzte Module mit Schwerpunkt auf dem großen GUI-File, einheitliche In-Code-Dokumentation und Entfernung der historischen PoC-Datei, ohne Funktionalität oder Features zu verändern.

Ziel ist es, die Wartbarkeit deutlich zu erhöhen, die Kopplung zwischen UI-Teilen zu senken und klar nachvollziehbare Verantwortlichkeiten pro Datei/Komponente zu schaffen. Der bestehende Funktionsumfang (CLI, IPC, GUI-Seiten, Aktionen/Trigger, GNOME-Shortcuts, Autostart, Profile) bleibt unverändert. Dokumentation (README/DESIGN/IMPLEMENTATION_LOG) wird synchron gehalten und auf die neue Struktur angepasst.

[Types]
Einführung leichter, optionaler Typdefinitionen (TypedDict/Protocol) zur Lesbarkeit und IDE-Unterstützung, ohne Laufzeitverhalten zu beeinflussen.

Vorgeschlagene Typen (src/wbridge/types.py):
```python
from __future__ import annotations
from typing import TypedDict, Literal, Dict, List, Optional, Union

SelectionType = Literal["clipboard", "primary"]

class HTTPAction(TypedDict, total=False):
    name: str
    type: Literal["http"]
    method: Literal["GET", "POST"]
    url: str
    headers: Dict[str, str]
    params: Dict[str, str]
    json: object
    data: object

class ShellAction(TypedDict, total=False):
    name: str
    type: Literal["shell"]
    command: str
    args: List[str]
    use_shell: bool

ActionDef = Union[HTTPAction, ShellAction]

class ActionsPayload(TypedDict, total=False):
    actions: List[ActionDef]
    triggers: Dict[str, str]

class ProfileShortcutsItem(TypedDict, total=False):
    name: str
    command: str
    binding: str

class InstallReport(TypedDict, total=False):
    ok: bool
    profile: str
    actions: Dict[str, int | str | None]
    triggers: Dict[str, int]
    settings: Dict[str, object]
    shortcuts: Dict[str, int]
    dry_run: bool
    errors: List[str]
```

Hinweise:
- Nur als Lesehilfe; keine erzwungene Validierung über das bestehende `validate_action_dict`.
- Einsatz schrittweise, primär für IDE-Autovervollständigung und Code-Navigation.

[Files]
Aufteilung der GUI in kleinere Dateien, Entfernung veralteter Datei, minimale Importanpassungen, Docstrings konsistent ergänzen.

- Neu anzulegen:
  - src/wbridge/ui/__init__.py
    - Re-Exports für UI-Hauptkomponenten (z. B. MainWindow).
  - src/wbridge/ui/main_window.py
    - Enthält die bisherige `MainWindow`-Funktionalität (Navigation, Stack, Verkabelung der Seiten).
  - src/wbridge/ui/pages/history_page.py
    - Inhalt von `_page_history`, History-Refresh, Row-Building, Label-Updates, Swap-Handler.
  - src/wbridge/ui/pages/actions_page.py
    - Inhalt von `_page_actions`, Actions-Liste/Editor (Form/JSON), Run/Save/Duplicate/Delete, Triggers-Teil wird aus dieser Seite entfernt und separat behandelt (siehe unten).
  - src/wbridge/ui/pages/triggers_page.py
    - Inhalt von `_page_triggers`, inkl. Editor und Persistenz der Trigger.
  - src/wbridge/ui/pages/shortcuts_page.py
    - Inhalt von `_page_shortcuts`, inkl. Read/Save/Reload/Delete und Konfliktanzeige.
  - src/wbridge/ui/pages/settings_page.py
    - Inhalt von `_page_settings`, inkl. Integration-Status, Inline-Edit, Health-Check, Profile-Installationsbereich und Schaltflächen (Shortcuts/Auotstart).
  - src/wbridge/ui/pages/status_page.py
    - Inhalt von `_page_status`, inkl. Env-Infos und Log-Tail.
  - src/wbridge/ui/components/help_panel.py
    - Auslagerung von `_help_panel`, `_load_help_text`, `_render_help`.
  - src/wbridge/types.py
    - Optionales Typlayer (siehe [Types]).

- Bestehende Dateien zu ändern:
  - src/wbridge/app.py
    - Import von `MainWindow` auf `.ui.main_window` umstellen.
    - Entfernen der ungenutzten lokalen `class MainWindow` (Platzhalter); nur `UIMainWindow` verwenden.
  - src/wbridge/gui_window.py
    - Datei entfällt komplett (Inhalt wird in die neuen `ui/*`-Module verteilt).
  - README.md
    - Projektstruktur anpassen („ui/… pages/components“), Entfernen/Ersetzen von Verweisen auf `gui_window.py` und `wayland-bridge.py`.
  - DESIGN.md
    - Modul-Layout-Abschnitt aktualisieren (UI-Aufteilung, Bezüge zu neuen Dateien).
  - IMPLEMENTATION_LOG.md
    - Neuer Eintrag „Refactor UI split; remove legacy PoC; docs sync“.
  - pyproject.toml
    - Keine inhaltlichen Änderungen notwendig; Code liegt weiter unter `src/` und Package-Data bleibt gültig.

- Dateien zu löschen:
  - gui_window.py (nach vollständigem Split)
  - wayland-bridge.py (Nutzerwunsch; historischer PoC fällt weg; ggf. kurzer Hinweis in README „Removed legacy PoC“)

- Konfigurationsdateien:
  - Keine Änderungen an Einstellungen oder Datenformaten (settings.ini, actions.json); keine Migration erforderlich.

[Functions]
Verschiebung/Entkopplung von Page-spezifischen Funktionen in dedizierte Module. Keine Signatur-/Semantikänderungen über die UI-Grenze hinaus.

- Neue Funktionen (Auszug; Signatur, Ziel-Datei, Zweck):
  - pages/history_page.py
    - class HistoryPage(Gtk.Box):
      - methods:
        - refresh(limit: int = 20) -> None
        - on_swap_clicked(which: str) -> None
        - _apply_text(which: str, text: str) -> None
  - pages/actions_page.py
    - class ActionsPage(Gtk.Box):
      - methods:
        - refresh_actions_list() -> None
        - _on_action_run_clicked(...)
        - _on_actions_save_form_clicked(...)
        - _on_actions_save_json_clicked(...)
        - _on_action_duplicate_current_clicked(...)
        - _on_action_delete_current_clicked(...)
        - _on_reload_actions_clicked(...)
  - pages/triggers_page.py
    - class TriggersPage(Gtk.Box):
      - methods:
        - rebuild_editor() -> None
        - _on_triggers_add_clicked(...)
        - _on_triggers_save_clicked(...)
  - pages/shortcuts_page.py
    - class ShortcutsPage(Gtk.Box):
      - methods:
        - reload() -> None
        - _shortcuts_on_save_clicked(...)
        - _shortcuts_on_row_delete_clicked(...)
  - pages/settings_page.py
    - class SettingsPage(Gtk.Box):
      - methods:
        - refresh_status() -> None
        - _on_save_integration_clicked(...)
        - _on_discard_integration_clicked(...)
        - _on_reload_settings_clicked(...)
        - _on_health_check_clicked(...)
        - _on_profile_show_clicked(...)
        - _on_profile_install_clicked(...)
        - _on_install_shortcuts_clicked(...)
        - _on_remove_shortcuts_clicked(...)
        - _on_enable_autostart_clicked(...)
        - _on_disable_autostart_clicked(...)
  - pages/status_page.py
    - class StatusPage(Gtk.Box):
      - methods:
        - refresh_log_tail() -> None

- Modifizierte Funktionen:
  - app.BridgeApplication.do_activate(): Erzeugt `UIMainWindow(self)` aus ui/main_window.py.
  - app.BridgeApplication._ipc_handler(): unverändert in Semantik; keine Anpassung nötig.
  - Keine Änderungen in CLI/IPC/Aktionen/History/etc.

- Entfernte Funktionen:
  - Platzhalter-`MainWindow` in app.py (nicht genutzt).
  - Alle `_page_*`-Factories und UI-Helfer aus gui_window.py (ersetzt durch Page-Klassen in `ui/pages/*.py`).

[Classes]
Einführung von Page-Klassen; `MainWindow` orchestriert, composition over monolith.

- Neue Klassen:
  - ui/main_window.py: class MainWindow(Gtk.ApplicationWindow)
    - Methoden:
      - _build_navigation() -> tuple[Gtk.StackSidebar, Gtk.Stack]
      - set_page(page_name: str) -> None
      - delegates: Aufruf von Page-Methoden (z. B. refresh)
  - ui/pages/history_page.py: class HistoryPage(Gtk.Box)
  - ui/pages/actions_page.py: class ActionsPage(Gtk.Box)
  - ui/pages/triggers_page.py: class TriggersPage(Gtk.Box)
  - ui/pages/shortcuts_page.py: class ShortcutsPage(Gtk.Box)
  - ui/pages/settings_page.py: class SettingsPage(Gtk.Box)
  - ui/pages/status_page.py: class StatusPage(Gtk.Box)
  - ui/components/help_panel.py: ggf. `build_help_panel(topic: str) -> Gtk.Widget`

- Modifizierte Klassen:
  - app.BridgeApplication: nur Importziel und Erzeugung der `MainWindow`-Instanz ändern.
  - Keine Änderung an HistoryStore, SelectionMonitor, ActionContext etc.

- Entfernte Klassen:
  - app.MainWindow (Platzhalter, unbenutzt).

[Dependencies]
Keine neuen externen Abhängigkeiten. Optionales `requests` bleibt via Extra `[http]`. GTK/PyGObject weiterhin Systempakete.

[Testing]
Manuelle Smoke- und Funktionsparitätstests, um garantierte Feature-Gleichheit sicherzustellen.

- CLI/IPC:
  - `wbridge ui show` → Fenster erscheint
  - `wbridge selection get|set` → Werte korrekt
  - `wbridge history list|apply|swap` → Semantik unverändert
  - `wbridge trigger prompt --from-primary` → Aktion läuft (bei aktivierter Integration)
- GUI:
  - Navigation (StackSidebar/Stack) wie zuvor
  - History: Anzeige/Apply/Swap funktioniert
  - Actions: Liste, Form/JSON-Editor, Run/Save/Reload, Duplicate/Delete
  - Triggers: Editor/Save Validation
  - Shortcuts: Laden/Anlegen/Speichern/Löschen, Konflikt-Hinweis
  - Settings: Integration-Status, Inline-Edit, Health-Check, Profile install, Shortcuts/Autostart
  - Status: Env-Infos und Log-Tail
- Docs:
  - README/DESIGN auf neue Struktur konsistent
  - IMPLEMENTATION_LOG-Eintrag vorhanden

[Implementation Order]
Minimalinvasive Sequenz zur Risikoreduktion.

1) Vorbereitung
   - `src/wbridge/types.py` hinzufügen (nur Typen).
   - `ui/`-Ordnerstruktur anlegen: ui/, ui/pages/, ui/components/.
2) MainWindow extrahieren
   - `ui/main_window.py` erstellen; Navigation, CSS-Load/Zusammenbau verlagern.
   - Import in `app.py` auf `.ui.main_window` umstellen; Platzhalter `MainWindow` aus `app.py` entfernen.
3) Pages splitten
   - `history_page.py` aus `_page_history`+Helfer extrahieren.
   - `actions_page.py` aus `_page_actions` extrahieren (inkl. Form/JSON, Save/Run/Duplicate/Delete, Reload).
   - `triggers_page.py` aus `_page_triggers` extrahieren.
   - `shortcuts_page.py` aus `_page_shortcuts` extrahieren.
   - `settings_page.py` aus `_page_settings` extrahieren.
   - `status_page.py` aus `_page_status` extrahieren.
   - `components/help_panel.py` (Help-Baustein) erstellen.
4) Umschalten auf neue UI
   - `gui_window.py` referenzfrei machen → entfernen.
   - `MainWindow` aus `ui/main_window.py` nutzen; Page-Klassen im Stack registrieren.
5) PoC entfernen
   - `wayland-bridge.py` löschen (User-Wunsch); README-Hinweis („Legacy PoC removed“).
6) Docs & Log
   - README/DESIGN mit neuer Struktur (Projektlayout) aktualisieren.
   - IMPLEMENTATION_LOG.md Eintrag anlegen.
7) Tests
   - Smoke-Tests wie in [Testing], Funktionsparität verifizieren.
   - Keine Änderungen an Datenformaten/Kommandos/Features.

[Refactor Details]
Konkretisierung des Splits inklusive Mapping, Orchestrierung, Skelette und Abnahmekriterien.

Alt → Neu Mapping (Kurzüberblick)
- gui_window.MainWindow → ui.main_window.MainWindow
  - Behält: Navigation (StackSidebar + Stack), CSS-Load, File-Monitors (settings.ini/actions.json), periodischer GLib-Timeout.
  - Delegiert an Pages: History, Actions, Triggers, Shortcuts, Settings, Status.
- Hilfe-Baustein: ui/components/help_panel.py
  - Funktionen: build_help_panel(topic), internes _load_help_text(topic), _render_help(text).
- Pages (jeweils Gtk.Box):
  - ui/pages/history_page.py:
    - refresh(limit=20), update_current_labels_async(), on_swap_clicked(which)
    - intern: _apply_text(which,text), _update_after_set(which), _history_list(which,limit), _clear_listbox(lb), _build_history_row(...)
    - interner Cache: _cur_clip, _cur_primary, _hist_dirty, _reading_cb/_reading_pr
  - ui/pages/actions_page.py:
    - refresh_actions_list(), notify_config_reloaded()
    - _on_action_run_current_clicked(), _on_action_run_clicked(...)
    - _on_actions_save_form_clicked(), _on_actions_save_json_clicked()
    - _on_action_duplicate_current_clicked(), _on_action_delete_current_clicked()
    - _on_reload_actions_clicked(), _on_add_action_clicked()
    - Helpers: _build_action_list_row(), _actions_load_list(), _actions_find_by_name(), _actions_select(), _actions_bind_form(), _actions_update_type_visibility(), _get_textview_text(), _on_actions_source_changed(), _actions_on_type_changed(), _get_settings_map()
    - Quelle clipboard/primary via HistoryPage.get_current(...)
  - ui/pages/triggers_page.py:
    - rebuild_editor(), _on_triggers_add_clicked(), _on_triggers_save_clicked()
    - intern: _build_trigger_row(), _on_trigger_row_delete_clicked()
  - ui/pages/shortcuts_page.py:
    - reload(), _shortcuts_on_reload_clicked(), _shortcuts_on_add_clicked(), _shortcuts_on_save_clicked()
    - intern: _shortcuts_on_row_delete_clicked(), _shortcuts_compute_suffix(), _shortcuts_read_items(include_foreign), _shortcuts_build_row(item)
  - ui/pages/settings_page.py:
    - refresh_status(), populate_edit_from_settings(), reload_settings()
    - _on_save_integration_clicked(), _on_discard_integration_clicked(), _on_reload_settings_clicked()
    - _on_health_check_clicked()
    - _on_profile_show_clicked(), _on_profile_install_clicked()
    - _on_install_shortcuts_clicked(), _on_remove_shortcuts_clicked()
    - _on_enable_autostart_clicked(), _on_disable_autostart_clicked()
  - ui/pages/status_page.py:
    - refresh_log_tail() (unter Nutzung von _log_tail(max_lines))

Orchestrierung & Datenflüsse
- Jede Page bekommt `MainWindow`-Referenz (`self._main`) im Konstruktor für:
  - Zugriff auf `Gtk.Application` (z. B. app._settings, app._actions).
  - Optionale Kommunikation zwischen Pages (z. B. ActionsPage → HistoryPage.get_current()).
- MainWindow:
  - Takt (`GLib.timeout_add(400)`): `history_page.update_current_labels_async()`; bei `_hist_dirty` → `history_page.refresh()`.
  - File-Monitors:
    - settings.ini geändert → `settings_page.reload_settings()`, `actions_page.refresh_actions_list()`, `triggers_page.rebuild_editor()`.
    - actions.json geändert → `app._actions = load_actions()`, `actions_page.refresh_actions_list()`, `triggers_page.rebuild_editor()`, `actions_page.notify_config_reloaded()`.
- Selektionsquelle in Actions:
  - clipboard → HistoryPage.get_current("clipboard")
  - primary → HistoryPage.get_current("primary")
  - text → lokales Entry der ActionsPage

Ressourcenpfade
- CSS: `Path(__file__).resolve().parents[2] / "assets" / "style.css"`
- Help: `Path(__file__).resolve().parents[2] / "help" / "en" / f"{topic}.md"`

Skelette (Auszüge)
- ui/__init__.py
```python
from .main_window import MainWindow
__all__ = ["MainWindow"]
```

- ui/main_window.py (Kurzfassung)
```python
import gi, gettext, logging
gi.require_version("Gtk","4.0"); gi.require_version("Gdk","4.0"); gi.require_version("Gio","2.0")
from gi.repository import Gtk, Gdk, Gio, GLib  # type: ignore
from pathlib import Path
from ..config import load_actions
from ..platform import xdg_config_dir
from .pages.history_page import HistoryPage
from .pages.actions_page import ActionsPage
from .pages.triggers_page import TriggersPage
from .pages.shortcuts_page import ShortcutsPage
from .pages.settings_page import SettingsPage
from .pages.status_page import StatusPage

_t = gettext.translation("wbridge", localedir=None, fallback=True); _ = _t.gettext

class MainWindow(Gtk.ApplicationWindow):
    """Main application window orchestrating all pages."""
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application)
        self.set_title("wbridge"); self.set_default_size(1000, 650)
        self._logger = logging.getLogger("wbridge"); self._load_css()
        sidebar, stack = self._build_navigation()
        self.history_page = HistoryPage(self)
        self.actions_page = ActionsPage(self, self.history_page)
        self.triggers_page = TriggersPage(self)
        self.shortcuts_page = ShortcutsPage(self)
        self.settings_page = SettingsPage(self)
        self.status_page = StatusPage(self)
        stack.add_titled(self.history_page, "history", _("History"))
        stack.add_titled(self.actions_page, "actions", _("Actions"))
        stack.add_titled(self.triggers_page, "triggers", _("Triggers"))
        stack.add_titled(self.shortcuts_page, "shortcuts", _("Shortcuts"))
        stack.add_titled(self.settings_page, "settings", _("Settings"))
        stack.add_titled(self.status_page, "status", _("Status"))
        self.actions_page.refresh_actions_list(); self.triggers_page.rebuild_editor()
        self._init_file_monitors()
        GLib.timeout_add(400, self._refresh_tick)  # type: ignore

    def _build_navigation(self) -> tuple[Gtk.StackSidebar, Gtk.Stack]:
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        stack = Gtk.Stack(); sidebar = Gtk.StackSidebar(); sidebar.set_stack(stack)
        root.append(sidebar); root.append(stack); self.set_child(root); return sidebar, stack

    def _refresh_tick(self) -> bool:
        try:
            self.history_page.update_current_labels_async()
            if getattr(self.history_page, "_hist_dirty", False):
                self.history_page.refresh(); self.history_page._hist_dirty = False
        except Exception: pass
        return True
```

Abnahmekriterien (Feature-Parität)
- CLI/IPC unverändert; keine Änderungen an Datenformaten (settings.ini, actions.json).
- GUI-Seiten verhalten sich wie zuvor:
  - History: Anzeige, Apply/Swap, periodische Label-Updates.
  - Actions: Liste, Form/JSON, Run/Save/Reload, Duplicate/Delete, Hinweis wenn HTTP-Trigger deaktiviert.
  - Triggers: Editor/Save mit Validierung; Action-Namen sind konsistent.
  - Shortcuts: Lesen/Anlegen/Speichern/Löschen; Konfliktanzeige.
  - Settings: Status/Inline-Edit/Health/Profiles/Shortcuts/Autostart.
  - Status: Env-Infos/Log-Tail.
- CSS und Help-Panels funktionieren; File-Monitors reagieren mit Debounce.
- app.py nutzt nur noch `ui.main_window.MainWindow`; Platzhalterklasse entfällt.
- `wayland-bridge.py` entfernt; `gui_window.py` nach Migration entfernt.
- README/DESIGN/IMPLEMENTATION_LOG aktualisiert.

Dokstring-Konvention
- Knapp/pragmatisch. Einzeiler für triviale Methoden; kurz im Google-Stil bei Bedarf.
- Beispiele:
  - Klassen: „Main application window orchestrating pages.“
  - Methoden: „Refresh history lists from HistoryStore and update labels.“
