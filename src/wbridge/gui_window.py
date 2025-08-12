#!/usr/bin/env python3
"""
Gtk4 MainWindow for wbridge with basic Notebook UI.

Tabs:
- History: zeigt Clipboard- und Primary-History, inkl. Apply/Swap Aktionen
- Actions: placeholder mit kurzer Erklärung (wird später verdrahtet)
- Settings: placeholder (Autostart/Shortcuts/Integration folgen später)
- Status: Backend/Runtime Informationen

Die History-Ansicht ist mit dem HistoryStore des Application-Objekts verbunden.
"""

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Gdk, Gio, GLib, GObject  # type: ignore
from typing import Optional, Callable, cast

from .platform import active_env_summary, socket_path, xdg_state_dir
from .config import load_actions
from .actions import run_action, ActionContext


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application)
        self.set_title("wbridge")
        self.set_default_size(900, 600)
        # Cache für aktuelle Selektion (vermeidet Blocking-Reads auf dem GTK-Mainthread)
        self._cur_clip: str = ""
        self._cur_primary: str = ""
        # Dirty-Flag für Listenneuaufbau (verhindert unnötige/zu häufige Refreshes)
        self._hist_dirty: bool = True
        # In-Flight-Guards für async Reads (verhindert Überschwemmung/Hänger)
        self._reading_cb: bool = False
        self._reading_pr: bool = False

        notebook = Gtk.Notebook()
        notebook.set_tab_pos(Gtk.PositionType.TOP)
        self.set_child(notebook)

        # History tab
        history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        history_box.set_margin_start(16)
        history_box.set_margin_end(16)
        history_box.set_margin_top(16)
        history_box.set_margin_bottom(16)

        history_desc = Gtk.Label(label="History (Clipboard / Primary)\n"
                                       "• Liste der letzten Einträge mit Aktionen: Als Clipboard setzen, Als Primary setzen, Swap (tauscht die letzten zwei).\n"
                                       "• Tipp: CLI `wbridge selection set/get` funktioniert ebenfalls.")
        history_desc.set_wrap(True)
        history_desc.set_xalign(0.0)
        history_box.append(history_desc)

        # History Controls: manueller Refresh + Zähler
        hist_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", lambda _b: self.refresh_history())
        hist_controls.append(refresh_btn)

        self.hist_count = Gtk.Label(label="Einträge: 0 / 0")
        self.hist_count.set_xalign(0.0)
        hist_controls.append(self.hist_count)

        history_box.append(hist_controls)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)

        # Clipboard frame
        cb_frame = Gtk.Frame(label="Clipboard")
        cb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cb_box.set_margin_start(10)
        cb_box.set_margin_end(10)
        cb_box.set_margin_top(10)
        cb_box.set_margin_bottom(10)

        # Simple Set/Get helpers (bleiben als Testwerkzeuge)
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

        swap_cb_btn = Gtk.Button(label="Swap last two (clipboard)")
        swap_cb_btn.connect("clicked", lambda _b: self.on_swap_clicked("clipboard"))
        cb_btn_box.append(swap_cb_btn)

        cb_box.append(cb_btn_box)

        self.cb_label = Gtk.Label(label="Aktuell: (leer)")
        self.cb_label.set_xalign(0.0)
        cb_box.append(self.cb_label)

        # Clipboard History List
        cb_hist_hdr = Gtk.Label(label="History (neueste zuerst):")
        cb_hist_hdr.set_xalign(0.0)
        cb_box.append(cb_hist_hdr)

        self.cb_list = Gtk.ListBox()
        self.cb_list.set_selection_mode(Gtk.SelectionMode.NONE)
        cb_scrolled = Gtk.ScrolledWindow()
        cb_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        cb_scrolled.set_min_content_height(180)
        cb_scrolled.set_child(self.cb_list)
        cb_box.append(cb_scrolled)

        cb_frame.set_child(cb_box)

        # Primary frame
        pr_frame = Gtk.Frame(label="Primary Selection")
        pr_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
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

        swap_pr_btn = Gtk.Button(label="Swap last two (primary)")
        swap_pr_btn.connect("clicked", lambda _b: self.on_swap_clicked("primary"))
        pr_btn_box.append(swap_pr_btn)

        pr_box.append(pr_btn_box)

        self.pr_label = Gtk.Label(label="Aktuell: (leer)")
        self.pr_label.set_xalign(0.0)
        pr_box.append(self.pr_label)

        pr_hist_hdr = Gtk.Label(label="History (neueste zuerst):")
        pr_hist_hdr.set_xalign(0.0)
        pr_box.append(pr_hist_hdr)

        self.pr_list = Gtk.ListBox()
        self.pr_list.set_selection_mode(Gtk.SelectionMode.NONE)
        pr_scrolled = Gtk.ScrolledWindow()
        pr_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        pr_scrolled.set_min_content_height(180)
        pr_scrolled.set_child(self.pr_list)
        pr_box.append(pr_scrolled)

        pr_frame.set_child(pr_box)

        grid.attach(cb_frame, 0, 0, 1, 1)
        grid.attach(pr_frame, 1, 0, 1, 1)
        history_box.append(grid)

        notebook.append_page(history_box, Gtk.Label(label="History"))

        # Actions tab
        actions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        actions_box.set_margin_start(16)
        actions_box.set_margin_end(16)
        actions_box.set_margin_top(16)
        actions_box.set_margin_bottom(16)

        actions_desc = Gtk.Label(label="Actions\n"
                                        "• Definierte Aktionen (HTTP/Shell) aus ~/.config/wbridge/actions.json.\n"
                                        "• Quelle wählen: Clipboard / Primary / Text.")
        actions_desc.set_wrap(True)
        actions_desc.set_xalign(0.0)
        actions_box.append(actions_desc)

        # Controls: source selection + optional text + reload
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        src_label = Gtk.Label(label="Quelle:")
        src_label.set_xalign(0.0)
        controls.append(src_label)

        self.actions_source = Gtk.ComboBoxText()
        self.actions_source.append("clipboard", "Clipboard")
        self.actions_source.append("primary", "Primary")
        self.actions_source.append("text", "Text")
        self.actions_source.set_active_id("clipboard")
        self.actions_source.connect("changed", self._on_actions_source_changed)
        controls.append(self.actions_source)

        self.actions_text = Gtk.Entry()
        self.actions_text.set_placeholder_text("Text für Quelle=Text …")
        self.actions_text.set_sensitive(False)
        self.actions_text.set_hexpand(True)
        controls.append(self.actions_text)

        reload_btn = Gtk.Button(label="Reload actions")
        reload_btn.connect("clicked", self._on_reload_actions_clicked)
        controls.append(reload_btn)

        actions_box.append(controls)

        # Actions list
        self.actions_list = Gtk.ListBox()
        self.actions_list.set_selection_mode(Gtk.SelectionMode.NONE)
        act_scrolled = Gtk.ScrolledWindow()
        act_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        act_scrolled.set_min_content_height(240)
        act_scrolled.set_child(self.actions_list)
        actions_box.append(act_scrolled)

        # Result output
        self.actions_result = Gtk.Label(label="")
        self.actions_result.set_wrap(True)
        self.actions_result.set_xalign(0.0)
        actions_box.append(self.actions_result)

        notebook.append_page(actions_box, Gtk.Label(label="Actions"))

        # initial population
        self.refresh_actions_list()

        # Settings tab (v1)
        settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        settings_box.set_margin_start(16)
        settings_box.set_margin_end(16)
        settings_box.set_margin_top(16)
        settings_box.set_margin_bottom(16)

        settings_desc = Gtk.Label(label="Settings\n"
                                         "• Basisinformationen und Platzhalter-Buttons (noch ohne Funktion).")
        settings_desc.set_wrap(True)
        settings_desc.set_xalign(0.0)
        settings_box.append(settings_desc)

        # Basisinfos
        info_grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        row = 0

        # Backend/Display Info
        try:
            disp = Gdk.Display.get_default()
            disp_type = GObject.type_name(disp.__gtype__)
            lbl_backend_k = Gtk.Label(label="GDK Display:")
            lbl_backend_k.set_xalign(0.0)
            lbl_backend_v = Gtk.Label(label=disp_type)
            lbl_backend_v.set_xalign(0.0)
            info_grid.attach(lbl_backend_k, 0, row, 1, 1)
            info_grid.attach(lbl_backend_v, 1, row, 1, 1)
            row += 1
        except Exception:
            pass

        # Socket Pfad
        lbl_sock_k = Gtk.Label(label="IPC Socket:")
        lbl_sock_k.set_xalign(0.0)
        lbl_sock_v = Gtk.Label(label=str(socket_path()))
        lbl_sock_v.set_xalign(0.0)
        info_grid.attach(lbl_sock_k, 0, row, 1, 1)
        info_grid.attach(lbl_sock_v, 1, row, 1, 1)
        row += 1

        # Log Pfad
        lbl_log_k = Gtk.Label(label="Log-Datei:")
        lbl_log_k.set_xalign(0.0)
        lbl_log_v = Gtk.Label(label=str(xdg_state_dir() / "bridge.log"))
        lbl_log_v.set_xalign(0.0)
        info_grid.attach(lbl_log_k, 0, row, 1, 1)
        info_grid.attach(lbl_log_v, 1, row, 1, 1)
        row += 1

        settings_box.append(info_grid)

        # Platzhalter-Buttons
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_shortcuts_install = Gtk.Button(label="GNOME Shortcuts installieren")
        btn_shortcuts_install.connect("clicked", self._on_install_shortcuts_clicked)
        btns.append(btn_shortcuts_install)

        btn_shortcuts_remove = Gtk.Button(label="GNOME Shortcuts entfernen")
        btn_shortcuts_remove.connect("clicked", self._on_remove_shortcuts_clicked)
        btns.append(btn_shortcuts_remove)

        btn_autostart_enable = Gtk.Button(label="Autostart aktivieren")
        btn_autostart_enable.connect("clicked", self._on_enable_autostart_clicked)
        btns.append(btn_autostart_enable)

        btn_autostart_disable = Gtk.Button(label="Autostart deaktivieren")
        btn_autostart_disable.connect("clicked", self._on_disable_autostart_clicked)
        btns.append(btn_autostart_disable)

        settings_box.append(btns)

        self.settings_result = Gtk.Label(label="")
        self.settings_result.set_wrap(True)
        self.settings_result.set_xalign(0.0)
        settings_box.append(self.settings_result)

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

        help_label = Gtk.Label(label="Hinweis: History-Tab zeigt die Einträge. "
                                      "Buttons führen Apply/Swap aus. "
                                      "CLI `wbridge history ...` ist ebenfalls verfügbar.")
        help_label.set_wrap(True)
        help_label.set_xalign(0.0)
        status_box.append(help_label)

        notebook.append_page(status_box, Gtk.Label(label="Status"))

        # Periodisches Refresh der History-Listen
        GLib.timeout_add(400, self._refresh_tick)  # type: ignore

    # --- History UI helpers ---

    def _refresh_tick(self) -> bool:
        try:
            self._update_current_labels_async()
        except Exception:
            pass
        # Nur neu aufbauen, wenn Daten sich geändert haben
        try:
            if getattr(self, "_hist_dirty", False):
                self.refresh_history()
                self._hist_dirty = False
        except Exception:
            pass
        return True  # weiterlaufen

    def refresh_history(self, limit: int = 20) -> None:
        cb_items = self._history_list("clipboard", limit)
        pr_items = self._history_list("primary", limit)
        # Zähler aktualisieren (Clipboard / Primary)
        try:
            self.hist_count.set_text(f"Einträge: {len(cb_items)} / {len(pr_items)}")
        except Exception:
            pass

        # Aktualen Inhalt aus Cache (per Async-Read gepflegt)
        cb_sel = self._cur_clip or ""
        pr_sel = self._cur_primary or ""
        try:
            self.cb_label.set_text(f"Aktuell: {cb_sel!r}" if cb_sel else "Aktuell: (leer)")
            self.pr_label.set_text(f"Aktuell: {pr_sel!r}" if pr_sel else "Aktuell: (leer)")
        except Exception:
            pass

        # Clear and rebuild Clipboard list
        self._clear_listbox(self.cb_list)
        for idx, text in enumerate(cb_items):
            row = self._build_history_row(idx, text, src_which="clipboard", current_text=cb_sel)
            self.cb_list.append(row)

        # Clear and rebuild Primary list
        self._clear_listbox(self.pr_list)
        for idx, text in enumerate(pr_items):
            row = self._build_history_row(idx, text, src_which="primary", current_text=pr_sel)
            self.pr_list.append(row)

    def _clear_listbox(self, lb: Gtk.ListBox) -> None:
        child = lb.get_first_child()
        while child is not None:
            lb.remove(child)
            child = lb.get_first_child()

    def _history_list(self, which: str, limit: int) -> list[str]:
        app = self.get_application()
        # Greife auf den HistoryStore der App zu (internal attribute in V1)
        hist = getattr(app, "_history", None)
        if hist is None:
            return []
        try:
            return hist.list(which, limit=limit)
        except Exception:
            return []

    def _build_history_row(self, idx: int, text: str, src_which: str, current_text: str) -> Gtk.Widget:
        # Zweizeilige Darstellung: 1) Text (mit Markierung), 2) Buttons
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        # Zeile 1: Text mit optionaler "aktuell"-Markierung und Index
        top_label = Gtk.Label()
        top_label.set_xalign(0.0)
        top_label.set_wrap(True)
        top_label.set_use_markup(True)
        preview = text.strip().splitlines()[0] if text else ""
        if len(preview) > 200:
            preview = preview[:200] + "…"
        # Markup sicher escapen
        try:
            esc = GLib.markup_escape_text(preview)
        except Exception:
            esc = preview
        mark_current = "<b>[aktuell]</b> " if (current_text and text == current_text) else ""
        top_label.set_markup(f"{mark_current}[{idx}] {esc}")
        vbox.append(top_label)

        # Zeile 2: Buttons
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_clip = Gtk.Button(label="Als Clipboard setzen")
        btn_clip.connect("clicked", lambda _b: self._apply_text("clipboard", text))
        btns.append(btn_clip)

        btn_prim = Gtk.Button(label="Als Primary setzen")
        btn_prim.connect("clicked", lambda _b: self._apply_text("primary", text))
        btns.append(btn_prim)

        vbox.append(btns)

        row = Gtk.ListBoxRow()
        row.set_child(vbox)
        return row

    def on_swap_clicked(self, which: str) -> None:
        # Swap via HistoryStore, danach top anwenden
        app = self.get_application()
        hist = getattr(app, "_history", None)
        if hist is None:
            return
        try:
            if hist.swap_last_two(which):
                top = hist.get(which, 0) or ""
                if top:
                    self._apply_text(which, top)
        except Exception:
            pass
        # UI aktualisieren
        self.refresh_history()

    def _apply_text(self, which: str, text: str) -> None:
        # Setze Auswahl via GDK
        disp = Gdk.Display.get_default()
        clip = disp.get_primary_clipboard() if which == "primary" else disp.get_clipboard()
        if hasattr(clip, "set"):
            try:
                clip.set(text)  # type: ignore[attr-defined]
            except Exception:
                pass

        # Cache und History sofort aktualisieren (keine Blockierung des Mainthreads)
        try:
            if which == "primary":
                if text != self._cur_primary:
                    self._cur_primary = text
                    self._hist_dirty = True
            else:
                if text != self._cur_clip:
                    self._cur_clip = text
                    self._hist_dirty = True
            app = self.get_application()
            hist = getattr(app, "_history", None)
            if hist:
                if which == "primary":
                    hist.add_primary(text)
                else:
                    hist.add_clipboard(text)
                self._hist_dirty = True
        except Exception:
            pass

        # UI zeitnah aktualisieren
        self._update_after_set(which)
        try:
            self.refresh_history()
        except Exception:
            pass

        # leicht verzögert nochmals refreshe, nach dem Monitor-Intervall
        def _later_refresh():
            try:
                self.refresh_history()
            except Exception:
                pass
            return False
        GLib.timeout_add(600, _later_refresh)  # type: ignore

    def _update_after_set(self, which: str) -> None:
        # Lies den aktuellen Text asynchron und aktualisiere das passende Label.
        disp = Gdk.Display.get_default()
        clip = disp.get_primary_clipboard() if which == "primary" else disp.get_clipboard()

        # Verifikation der gesetzten Selektion per Async-Read (ohne Mainthread zu blockieren)
        def on_finish(source, res):
            try:
                t = source.read_text_finish(res)
                if which == "primary":
                    self.pr_label.set_text(f"Aktuell: {t!r}")
                else:
                    self.cb_label.set_text(f"Aktuell: {t!r}")
            except Exception as e:
                if which == "primary":
                    self.pr_label.set_text(f"Lesefehler: {e!r}")
                else:
                    self.cb_label.set_text(f"Lesefehler: {e!r}")
            return False

        try:
            clip.read_text_async(None, on_finish)
        except Exception:
            # Ignoriere read-fehler still
            pass

    def _update_current_labels_async(self) -> None:
        # Asynchron beide Selektionen lesen und Cache/Labels aktualisieren
        disp = Gdk.Display.get_default()
        try:
            cb = disp.get_clipboard()
            def _on_cb(source, res):
                try:
                    t = source.read_text_finish(res) or ""
                    if t != self._cur_clip:
                        self._cur_clip = t
                        self._hist_dirty = True
                    self.cb_label.set_text(f"Aktuell: {t!r}" if t else "Aktuell: (leer)")
                except Exception:
                    pass
                finally:
                    self._reading_cb = False
                return False
            if not getattr(self, "_reading_cb", False):
                self._reading_cb = True
                cb.read_text_async(None, _on_cb)
        except Exception:
            pass

        try:
            prim = disp.get_primary_clipboard()
            def _on_pr(source, res):
                try:
                    t = source.read_text_finish(res) or ""
                    if t != self._cur_primary:
                        self._cur_primary = t
                        self._hist_dirty = True
                    self.pr_label.set_text(f"Aktuell: {t!r}" if t else "Aktuell: (leer)")
                except Exception:
                    pass
                finally:
                    self._reading_pr = False
                return False
            if not getattr(self, "_reading_pr", False):
                self._reading_pr = True
                prim.read_text_async(None, _on_pr)
        except Exception:
            pass

    # --- Actions UI helpers ---

    def refresh_actions_list(self) -> None:
        # Populate actions from application cache
        app = self.get_application()
        cfg = getattr(app, "_actions", None)
        actions = getattr(cfg, "actions", []) if cfg else []
        self._clear_listbox(self.actions_list)
        for action in actions:
            name = str(action.get("name") or "(unnamed)")
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

            lbl = Gtk.Label(label=name)
            lbl.set_xalign(0.0)
            lbl.set_wrap(True)
            lbl.set_hexpand(True)
            row_box.append(lbl)

            run_btn = Gtk.Button(label="Run")
            run_btn.connect("clicked", self._on_action_run_clicked, action)
            row_box.append(run_btn)

            row = Gtk.ListBoxRow()
            row.set_child(row_box)
            self.actions_list.append(row)

    def _on_actions_source_changed(self, _combo: Gtk.ComboBoxText) -> None:
        active_id = self.actions_source.get_active_id() or "clipboard"
        self.actions_text.set_sensitive(active_id == "text")

    def _get_settings_map(self) -> dict:
        app = self.get_application()
        settings = getattr(app, "_settings", None)
        try:
            return settings.as_mapping() if settings else {}
        except Exception:
            return {}


    def _on_action_run_clicked(self, _btn: Gtk.Button, action: dict) -> None:
        # Determine source and text
        src_id = self.actions_source.get_active_id() or "clipboard"
        if src_id == "text":
            sel_text = self.actions_text.get_text() or ""
            sel_type = "clipboard"
        elif src_id == "primary":
            sel_text = self._cur_primary or ""
            sel_type = "primary"
        else:
            sel_text = self._cur_clip or ""
            sel_type = "clipboard"

        ctx = ActionContext(text=sel_text, selection_type=sel_type, settings_map=self._get_settings_map(), extra={"selection.type": sel_type})
        ok, message = run_action(action, ctx)
        if ok:
            self.actions_result.set_text(f"Success: {message}")
        else:
            self.actions_result.set_text(f"Failed: {message}")

    def _on_reload_actions_clicked(self, _btn: Gtk.Button) -> None:
        # Reload actions.json and refresh list
        app = self.get_application()
        try:
            new_cfg = load_actions()
            setattr(app, "_actions", new_cfg)
        except Exception:
            pass
        self.refresh_actions_list()

    # --- Settings placeholder callbacks ---

    def _on_install_shortcuts_clicked(self, _btn: Gtk.Button) -> None:
        # Platzhalter – Logik folgt später
        self.settings_result.set_text("GNOME Shortcuts installieren: noch nicht implementiert.")

    def _on_remove_shortcuts_clicked(self, _btn: Gtk.Button) -> None:
        self.settings_result.set_text("GNOME Shortcuts entfernen: noch nicht implementiert.")

    def _on_enable_autostart_clicked(self, _btn: Gtk.Button) -> None:
        self.settings_result.set_text("Autostart aktivieren: noch nicht implementiert.")

    def _on_disable_autostart_clicked(self, _btn: Gtk.Button) -> None:
        self.settings_result.set_text("Autostart deaktivieren: noch nicht implementiert.")

    # --- Button handlers (bestehende Set/Get-Tests) ---

    def on_set_clipboard_clicked(self, _btn: Gtk.Button) -> None:
        text = self.cb_entry.get_text()
        # Zentralisierte Logik: sorgt für sofortiges UI-Update + History
        self._apply_text("clipboard", text)

    def on_get_clipboard_clicked(self, _btn: Gtk.Button) -> None:
        disp = Gdk.Display.get_default()
        cb = disp.get_clipboard()

        def on_finish(source, res):
            try:
                t = source.read_text_finish(res)
                self.cb_label.set_text(f"Aktuell: {t!r}")
            except Exception as e:
                self.cb_label.set_text(f"Lesefehler: {e!r}")
            return False

        cb.read_text_async(None, on_finish)

    def on_set_primary_clicked(self, _btn: Gtk.Button) -> None:
        text = self.pr_entry.get_text()
        # Zentralisierte Logik: sorgt für sofortiges UI-Update + History
        self._apply_text("primary", text)

    def on_get_primary_clicked(self, _btn: Gtk.Button) -> None:
        disp = Gdk.Display.get_default()
        prim = disp.get_primary_clipboard()

        def on_finish(source, res):
            try:
                t = source.read_text_finish(res)
                self.pr_label.set_text(f"Aktuell: {t!r}")
            except Exception as e:
                self.pr_label.set_text(f"Lesefehler: {e!r}")
            return False

        prim.read_text_async(None, on_finish)
