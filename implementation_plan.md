# Implementation Plan

[Overview]
UI-Optimierung für wbridge: vereinheitlichte, professionellere Layouts, bessere Hilfe-Darstellung, konsistente CTA-Position (unten) und Auto-Refresh im Status-Log.

Die aktuelle UI zeigt auf mehreren Seiten lange Headertexte, gemischte Button-Positionen und inkonsistente Layouts (z. B. History in zwei Spalten). Dieser Plan räumt das auf: Wir reduzieren Kopfinformationen, bringen Hauptaktionen konsistent nach unten, stellen History vertikal dar (Clipboard und Primary untereinander), ordnen die Actions-Seite vertikal (Editor oben, Liste unten), und verbessern die Hilfe-Darstellung, sodass im eingeklappten Zustand kein Platz verbraucht wird. Zudem erhält die Status-Seite ein Follow/Auto-Refresh des Logs (standardmäßig an, 1 s Intervall). Die Änderungen bleiben innerhalb des bestehenden GTK4/PyGObject-Stacks ohne neue harte Abhängigkeiten und folgen DESIGN.md (Wayland-freundlich, wartbar, ohne Zusatz-Frameworks).

[Types]
Leichte UI-Typen und Konfigurationskonstanten für konsistente Darstellung.

- HelpDisplayMode: Literal["revealer", "popover"] – steuert, wie Hilfe ein-/ausgeblendet wird (Standard "revealer").
- RefreshConfig (Status): enabled: bool (default True), interval_ms: int (default 1000).
- CTAPlacement: Literal["bottom"] – deklarativer Hinweis, Haupt-CTAs unten zu platzieren.
- MarkdownRenderOptions: einfache Flags (headings_bold=True, bullets="• ").

[Files]
Gezielte Änderungen an Seiten + kleine, wiederverwendbare Komponenten.

New files:
- src/wbridge/ui/components/markdown.py
  - Zweck: Minimaler Markdown→Pango-Markup-Konverter (subset: #/##, Listen, Codeblöcke/inline, Fett/Kursiv), ohne externe Pakete. Fallback: Plaintext.
  - API:
    - def md_to_pango(md: str) -> str
- src/wbridge/ui/components/page_header.py
  - Zweck: Schlanker Page-Header-Builder mit Titel, optionaler Unterzeile (dim) und Help-Toggle (verknüpft mit Help-Revealer/Popover).
  - API:
    - def build_page_header(title: str, subtitle: str | None, help_widget: Gtk.Widget | None) -> Gtk.Widget
- src/wbridge/ui/components/cta_bar.py
  - Zweck: Einheitliche Bottom-Action-Bar (Container), in die pro Seite vorhandene Haupt-Buttons eingefügt werden.
  - API:
    - def build_cta_bar(*buttons: Gtk.Widget) -> Gtk.Widget

Modified files:
- src/wbridge/ui/components/help_panel.py
  - Ersetzt Expander durch:
    - Default: Gtk.Revealer (geschlossen: Höhe 0, kein Platzverbrauch), Button/Link in Header.
    - Optional: Gtk.Popover (Anker am Help-Button), falls HelpDisplayMode="popover".
  - Rendered Markdown: Nutzung markdown.md_to_pango, Anzeige als Gtk.Label(use_markup=True) in ScrolledWindow.
  - Signatur: def build_help_panel(topic: str, mode: str = "revealer") -> Gtk.Widget
- src/wbridge/ui/pages/history_page.py
  - Layoutwechsel: Zwei-Spalten-Grid → eine Spalte (Clipboard-Sektion über Primary-Sektion).
  - Headertext entfernen/verkürzen; Page-Header-Komponente verwenden.
  - CTA unten: Refresh-Button in Bottom-Bar verschieben.
  - Feinschliff: List-Höhen, Abstände, Zähler neben CTA oder als dim-Label.
- src/wbridge/ui/pages/actions_page.py
  - Layoutwechsel: Vertikal, Editor oben (Stack Form/JSON), Liste unten (scrollbar).
  - Controls: Source-Auswahl bleibt oben; „Add Action“/„Reload actions“ in Bottom-CTA-Bar.
  - Headertext reduzieren; Help über Revealer.
- src/wbridge/ui/pages/triggers_page.py
  - CTA unten: „Add Trigger“/„Save Triggers“ in Bottom-Bar.
  - Kleinere Breite/Texteinzug optimieren, damit unnötiges Scrollen reduziert wird.
- src/wbridge/ui/pages/shortcuts_page.py
  - CTA unten: „Add“, „Save“, „Reload“ als Bottom-Bar.
  - Header-Hinweise kompakt (dim).
- src/wbridge/ui/pages/status_page.py
  - Auto-Refresh („Follow log“) einbauen: Switch (default an), Intervall 1000 ms, Autoscroll ans Ende beim Refresh.
  - Headertext kompakter; Help via Revealer.
- src/wbridge/ui/main_window.py
  - Falls erforderlich: Anpassung der Page-Konstruktion (z. B. kein eigener History/Actions-Headertext mehr).
  - Keine Funktionsänderung am App-Flow.
- src/wbridge/assets/style.css
  - Neue Klassen:
    - .page-header { margin-bottom: 8px; }
    - .page-subtitle.dim { opacity: 0.6; }
    - .cta-bar { margin-top: 8px; padding-top: 6px; border-top: 1px solid alpha(currentColor, 0.1); }
    - .help-revealer scrolledwindow { min-height: 160px; }
    - .mono { font-family: monospace; }
  - Kleinere Button-/Label-Abstände konsistent halten.

No-op/As-is:
- src/wbridge/ui/pages/settings_page.py (CTAs sind hier eher Konfig-Kontrollen; nur Header/Help modernisieren).

[Functions]
Neue Builder-Funktionen und gezielte UI-Umbauten.

New functions:
- src/wbridge/ui/components/markdown.py
  - md_to_pango(text: str) -> str
- src/wbridge/ui/components/page_header.py
  - build_page_header(title: str, subtitle: str | None, help_widget: Gtk.Widget | None) -> Gtk.Widget
- src/wbridge/ui/components/cta_bar.py
  - build_cta_bar(*buttons: Gtk.Widget) -> Gtk.Widget
- src/wbridge/ui/components/help_panel.py
  - build_help_panel(topic: str, mode: str = "revealer") -> Gtk.Widget
  - _render_help_pango(text: str) -> Gtk.Widget  (intern)

Modified functions (Auswahl, exakte Signatur erhalten):
- HistoryPage.__init__:
  - Entfernt grid (zwei Spalten), erstellt vertical layout mit zwei Frames in Reihenfolge: Clipboard → Primary.
  - Ersetzt top „history_desc“-Label durch page_header.build_page_header(...).
  - Verschiebt Refresh-Button in cta_bar.build_cta_bar(refresh_btn).
- HistoryPage.refresh / update_current_labels_async / _build_history_row:
  - Logik unverändert; nur Widgets gehören nun zum neuen Layout.
- ActionsPage.__init__:
  - Container md (horizontal) → vertical; Editorbereich (Stack/Form/JSON) vor die Liste.
  - „Add Action“/„Reload actions“ in CTA-Bar unten, Run/Save/Cancel/Delete bleiben innerhalb des Editors, aber Page-CTA (Add/Reload) stets unten.
  - Headertext gestrafft, help_panel mode="revealer".
- TriggersPage.__init__:
  - Buttons in Bottom-CTA.
- ShortcutsPage.__init__:
  - Buttons in Bottom-CTA.
- StatusPage.__init__:
  - „Follow log“ Switch (aktiviert GLib.timeout_add_seconds(1, ...)).
  - Autoscroll: Buffer an das Ende setzen bei Refresh.
  - Manuelle „Refresh“-Aktion bleibt zusätzlich verfügbar.
- StatusPage.refresh_log_tail(max_lines=200) → ergänzt Autoscroll bei Follow.
- help_panel._load_help_text / _render_help → ersetzt TextView durch Label(use_markup=True) + Scroll, und Revealer/Popover-Logik.

Removed/relocated:
- Lange Seitenkopf-Labels mit Bullet-„Tipps“ entfallen (duplizierte Hilfe).

[Classes]
Keine neuen komplexen Klassen erforderlich; Builder-Funktionen genügen.

- New classes: keine (nur Funktions-Builder in components/*).
- Modified classes:
  - HistoryPage, ActionsPage, TriggersPage, ShortcutsPage, StatusPage: Layoutstruktur und CTA-Positionierung.
- Removed classes: keine.

[Dependencies]
Keine neuen harten Abhängigkeiten.

- Optional (zukünftig): markdown / markdown2 als extra; wird hier nicht vorausgesetzt.
- pyproject.toml bleibt unverändert.

[Testing]
Visuelle und funktionale UI-Checks.

- Start: wbridge-app
- History:
  - Clipboard/Primary erscheinen untereinander; Einträge/Buttons funktionieren.
  - Refresh-CTA unten sichtbar, Zähler korrekt.
- Actions:
  - Editor oben, Liste unten; „Add Action“/„Reload actions“ unten (CTA-Bar).
  - Run/Save/Cancel/Delete funktionieren wie gehabt.
- Triggers:
  - Add/Save unten; Mapping validiert; keine unnötigen Scrolls.
- Shortcuts:
  - Add/Save/Reload unten; Konflikt-Hinweis weiterhin sichtbar.
- Help:
  - Offen: gerendertes Markdown (Überschriften fett, Listen mit •).
  - Geschlossen: kein zusätzlicher Leerraum; Umschalten ohne Sprünge.
- Status:
  - Follow aktiviert (default an), aktualisiert ca. 1/s, autoscroll ans Ende.

[Implementation Order]
Schrittweise, risikoarm.

1) Komponenten vorbereiten: markdown.py, help_panel.py umbauen (Revealer + Markdown-Render).
2) HistoryPage vertikal umbauen; CTA-Bar unten; Header entschlacken.
3) ActionsPage vertikal (Editor oben, Liste unten); Page-CTA unten.
4) TriggersPage und ShortcutsPage: CTA nach unten, Kopf vereinfacht.
5) StatusPage: Follow/Auto-Refresh + Autoscroll; Kopf/Help modernisieren.
6) CSS finalisieren (Header/CTA/Help-Klassen).
7) Manuelle Tests (alle Seiten); Feinjustage von Abständen.
8) Cleanup: Entfernte Kopf-Labels prüfen, tote IDs entfernen, Logging-Meldungen bestätigen.
