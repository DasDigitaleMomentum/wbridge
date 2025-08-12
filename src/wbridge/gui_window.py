#!/usr/bin/env python3
"""
Gtk4 MainWindow for wbridge with basic Notebook UI.

Tabs:
- History: placeholder sections for Clipboard and Primary (will be wired to history store later)
- Actions: placeholder with brief explanation
- Settings: environment info and planned toggles
- Status: backend/runtime diagnostics

This is a usable scaffold (not just a single label), designed to evolve per DESIGN.md.
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Gdk, Gio, GLib, GObject  # type: ignore

from .platform import active_env_summary


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application)
        self.set_title("wbridge")
        self.set_default_size(900, 600)

        notebook = Gtk.Notebook()
        notebook.set_tab_pos(Gtk.PositionType.TOP)
        self.set_child(notebook)

        # History tab
        history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        history_box.set_margin_start(16)
        history_box.set_margin_end(16)
        history_box.set_margin_top(16)
        history_box.set_margin_bottom(16)

        history_desc = Gtk.Label(label="History (Clipboard / Primary) – scaffold\n"
                                       "• Diese Ansicht wird demnächst die jüngsten Einträge anzeigen und Kontextaktionen anbieten.\n"
                                       "• Aktuell: Verwende CLI `wbridge selection set/get` zur Verifikation.\n")
        history_desc.set_wrap(True)
        history_desc.set_xalign(0.0)
        history_box.append(history_desc)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)

        # Clipboard frame
        cb_frame = Gtk.Frame(label="Clipboard")
        cb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        cb_box.set_margin_start(10)
        cb_box.set_margin_end(10)
        cb_box.set_margin_top(10)
        cb_box.set_margin_bottom(10)

        self.cb_entry = Gtk.Entry()
        self.cb_entry.set_placeholder_text("Text hier eintippen und auf Set klicken …")
        cb_box.append(self.cb_entry)

        cb_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        cb_set_btn = Gtk.Button(label="Set clipboard")
        cb_set_btn.connect("clicked", self.on_set_clipboard_clicked)
        cb_btn_box.append(cb_set_btn)

        cb_get_btn = Gtk.Button(label="Get clipboard")
        cb_get_btn.connect("clicked", self.on_get_clipboard_clicked)
        cb_btn_box.append(cb_get_btn)

        self.cb_label = Gtk.Label(label="Zuletzt gelesen: (leer)")
        self.cb_label.set_xalign(0.0)
        cb_box.append(cb_btn_box)
        cb_box.append(self.cb_label)

        cb_frame.set_child(cb_box)

        # Primary frame
        pr_frame = Gtk.Frame(label="Primary Selection")
        pr_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        pr_box.set_margin_start(10)
        pr_box.set_margin_end(10)
        pr_box.set_margin_top(10)
        pr_box.set_margin_bottom(10)

        self.pr_entry = Gtk.Entry()
        self.pr_entry.set_placeholder_text("Text hier eintippen und auf Set klicken …")
        pr_box.append(self.pr_entry)

        pr_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        pr_set_btn = Gtk.Button(label="Set primary")
        pr_set_btn.connect("clicked", self.on_set_primary_clicked)
        pr_btn_box.append(pr_set_btn)

        pr_get_btn = Gtk.Button(label="Get primary")
        pr_get_btn.connect("clicked", self.on_get_primary_clicked)
        pr_btn_box.append(pr_get_btn)

        self.pr_label = Gtk.Label(label="Zuletzt gelesen: (leer)")
        self.pr_label.set_xalign(0.0)
        pr_box.append(pr_btn_box)
        pr_box.append(self.pr_label)

        pr_frame.set_child(pr_box)

        grid.attach(cb_frame, 0, 0, 1, 1)
        grid.attach(pr_frame, 1, 0, 1, 1)
        history_box.append(grid)

        notebook.append_page(history_box, Gtk.Label(label="History"))

        # Actions tab (placeholder)
        actions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        actions_box.set_margin_start(16)
        actions_box.set_margin_end(16)
        actions_box.set_margin_top(16)
        actions_box.set_margin_bottom(16)

        actions_desc = Gtk.Label(label="Actions – scaffold\n"
                                        "• Hier werden definierte Aktionen (HTTP/Shell) gelistet und testbar gemacht.\n"
                                        "• Konfiguration über ~/.config/wbridge/actions.json (siehe DESIGN.md).")
        actions_desc.set_wrap(True)
        actions_desc.set_xalign(0.0)
        actions_box.append(actions_desc)
        notebook.append_page(actions_box, Gtk.Label(label="Actions"))

        # Settings tab (placeholder)
        settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        settings_box.set_margin_start(16)
        settings_box.set_margin_end(16)
        settings_box.set_margin_top(16)
        settings_box.set_margin_bottom(16)

        settings_desc = Gtk.Label(label="Settings – scaffold\n"
                                         "• Geplante Inhalte: Autostart‑Toggle, GNOME‑Shortcuts anlegen/entfernen, "
                                         "Integration (optional HTTP‑Trigger).\n")
        settings_desc.set_wrap(True)
        settings_desc.set_xalign(0.0)
        settings_box.append(settings_desc)
        notebook.append_page(settings_box, Gtk.Label(label="Settings"))

        # Status tab
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        status_box.set_margin_start(16)
        status_box.set_margin_end(16)
        status_box.set_margin_top(16)
        status_box.set_margin_bottom(16)

        env_label = Gtk.Label(label=f"Environment: {active_env_summary()}")
        env_label.set_xalign(0.0)
        status_box.append(env_label)

        # Backend info
        try:
            disp = Gdk.Display.get_default()
            disp_type = GObject.type_name(disp.__gtype__)
            cb = disp.get_clipboard()
            cb_type = GObject.type_name(cb.__gtype__)
            backend_label = Gtk.Label(label=f"GDK Display: {disp_type}, Clipboard: {cb_type}")
            backend_label.set_xalign(0.0)
            status_box.append(backend_label)
        except Exception as e:
            backend_label = Gtk.Label(label=f"GDK info unavailable: {e}")
            backend_label.set_xalign(0.0)
            status_box.append(backend_label)

        help_label = Gtk.Label(label="Hinweis: CLI `wbridge selection set/get` funktioniert bereits. "
                                      "Die UI wird Schritt für Schritt mit den History‑ und Actions‑Funktionen verdrahtet.")
        help_label.set_wrap(True)
        help_label.set_xalign(0.0)
        status_box.append(help_label)

        notebook.append_page(status_box, Gtk.Label(label="Status"))

    # --- Button handlers (use GDK directly; later we will route via services/history) ---

    def on_set_clipboard_clicked(self, _btn: Gtk.Button) -> None:
        text = self.cb_entry.get_text()
        disp = Gdk.Display.get_default()
        cb = disp.get_clipboard()
        # In GTK4, set() accepts strings; GValue handled in binding
        if hasattr(cb, "set"):
            try:
                cb.set(text)  # type: ignore[attr-defined]
            except Exception:
                pass

    def on_get_clipboard_clicked(self, _btn: Gtk.Button) -> None:
        disp = Gdk.Display.get_default()
        cb = disp.get_clipboard()

        def on_finish(source, res):
            try:
                t = source.read_text_finish(res)
                self.cb_label.set_text(f"Zuletzt gelesen: {t!r}")
            except Exception as e:
                self.cb_label.set_text(f"Lesefehler: {e!r}")
            return False

        cb.read_text_async(None, on_finish)

    def on_set_primary_clicked(self, _btn: Gtk.Button) -> None:
        text = self.pr_entry.get_text()
        disp = Gdk.Display.get_default()
        prim = disp.get_primary_clipboard()
        if hasattr(prim, "set"):
            try:
                prim.set(text)  # type: ignore[attr-defined]
            except Exception:
                pass

    def on_get_primary_clicked(self, _btn: Gtk.Button) -> None:
        disp = Gdk.Display.get_default()
        prim = disp.get_primary_clipboard()

        def on_finish(source, res):
            try:
                t = source.read_text_finish(res)
                self.pr_label.set_text(f"Zuletzt gelesen: {t!r}")
            except Exception as e:
                self.pr_label.set_text(f"Lesefehler: {e!r}")
            return False

        prim.read_text_async(None, on_finish)
