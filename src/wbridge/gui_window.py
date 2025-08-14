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
from gi.repository import Pango  # type: ignore
from typing import Optional, Callable, cast
import logging

from .platform import active_env_summary, socket_path, xdg_state_dir
from .config import (
    load_actions,
    load_settings,
    set_integration_settings,
    load_actions_raw,
    write_actions_config,
    validate_action_dict,
)
from .actions import run_action, ActionContext
from .profiles_manager import (
    list_builtin_profiles,
    show_profile as pm_show_profile,
    install_profile as pm_install_profile,
)


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application)
        self.set_title("wbridge")
        self.set_default_size(900, 600)
        self._logger = logging.getLogger("wbridge")
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
        self.cb_label.set_wrap(True)
        try:
            self.cb_label.set_wrap_mode(Pango.WrapMode.CHAR)
        except Exception:
            pass
        try:
            self.cb_label.set_max_width_chars(80)
        except Exception:
            pass
        self.cb_label.set_hexpand(True)
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
        self.pr_label.set_wrap(True)
        try:
            self.pr_label.set_wrap_mode(Pango.WrapMode.CHAR)
        except Exception:
            pass
        try:
            self.pr_label.set_max_width_chars(80)
        except Exception:
            pass
        self.pr_label.set_hexpand(True)
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

        # Add Action button
        add_action_btn = Gtk.Button(label="Add Action")
        add_action_btn.connect("clicked", self._on_add_action_clicked)
        actions_box.append(add_action_btn)

        # Hint if HTTP trigger disabled
        self.actions_hint = Gtk.Label(label="")
        self.actions_hint.set_wrap(True)
        self.actions_hint.set_xalign(0.0)
        actions_box.append(self.actions_hint)

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

        # Triggers editor
        triggers_hdr = Gtk.Label(label="Triggers (Alias → Action)")
        triggers_hdr.set_xalign(0.0)
        actions_box.append(triggers_hdr)

        self.triggers_list = Gtk.ListBox()
        self.triggers_list.set_selection_mode(Gtk.SelectionMode.NONE)
        tr_scrolled = Gtk.ScrolledWindow()
        tr_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        tr_scrolled.set_min_content_height(160)
        tr_scrolled.set_child(self.triggers_list)
        actions_box.append(tr_scrolled)

        tr_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        tr_add_btn = Gtk.Button(label="Add Trigger")
        tr_add_btn.connect("clicked", self._on_triggers_add_clicked)
        tr_btns.append(tr_add_btn)

        tr_save_btn = Gtk.Button(label="Save Triggers")
        tr_save_btn.connect("clicked", self._on_triggers_save_clicked)
        tr_btns.append(tr_save_btn)

        actions_box.append(tr_btns)

        notebook.append_page(actions_box, Gtk.Label(label="Actions"))

        # initial population
        self.refresh_actions_list()
        self._rebuild_triggers_editor()

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

        # Integration Status
        integ_grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        lbl_integ_hdr = Gtk.Label(label="Integration Status")
        lbl_integ_hdr.set_xalign(0.0)
        settings_box.append(lbl_integ_hdr)

        lbl_enabled_k = Gtk.Label(label="http_trigger_enabled:")
        lbl_enabled_k.set_xalign(0.0)
        self.integ_enabled_v = Gtk.Label(label="")
        self.integ_enabled_v.set_xalign(0.0)
        integ_grid.attach(lbl_enabled_k, 0, 0, 1, 1)
        integ_grid.attach(self.integ_enabled_v, 1, 0, 1, 1)

        lbl_base_k = Gtk.Label(label="Base URL:")
        lbl_base_k.set_xalign(0.0)
        self.integ_base_v = Gtk.Label(label="")
        self.integ_base_v.set_xalign(0.0)
        integ_grid.attach(lbl_base_k, 0, 1, 1, 1)
        integ_grid.attach(self.integ_base_v, 1, 1, 1, 1)

        lbl_path_k = Gtk.Label(label="Trigger Path:")
        lbl_path_k.set_xalign(0.0)
        self.integ_path_v = Gtk.Label(label="")
        self.integ_path_v.set_xalign(0.0)
        integ_grid.attach(lbl_path_k, 0, 2, 1, 1)
        integ_grid.attach(self.integ_path_v, 1, 2, 1, 1)

        settings_box.append(integ_grid)
        self._refresh_integration_status()

        # Integration edit controls (inline edit)
        edit_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        edit_box.set_margin_top(6)

        # Row: Enable switch
        row_sw = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_sw = Gtk.Label(label="Enable HTTP trigger:")
        lbl_sw.set_xalign(0.0)
        row_sw.append(lbl_sw)
        self.integ_enabled_switch = Gtk.Switch()
        row_sw.append(self.integ_enabled_switch)
        edit_box.append(row_sw)

        # Row: Base URL
        row_base = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_base = Gtk.Label(label="Base URL (http/https):")
        lbl_base.set_xalign(0.0)
        self.integ_base_entry = Gtk.Entry()
        self.integ_base_entry.set_hexpand(True)
        row_base.append(lbl_base)
        row_base.append(self.integ_base_entry)
        edit_box.append(row_base)

        # Row: Trigger Path
        row_path = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_path = Gtk.Label(label="Trigger Path (/trigger):")
        lbl_path.set_xalign(0.0)
        self.integ_path_entry = Gtk.Entry()
        self.integ_path_entry.set_hexpand(True)
        row_path.append(lbl_path)
        row_path.append(self.integ_path_entry)
        edit_box.append(row_path)

        # Buttons: Save / Discard / Reload Settings / Health check
        row_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_save = Gtk.Button(label="Speichern")
        btn_save.connect("clicked", self._on_save_integration_clicked)
        row_btns.append(btn_save)

        btn_discard = Gtk.Button(label="Verwerfen")
        btn_discard.connect("clicked", self._on_discard_integration_clicked)
        row_btns.append(btn_discard)

        btn_reload = Gtk.Button(label="Reload Settings")
        btn_reload.connect("clicked", self._on_reload_settings_clicked)
        row_btns.append(btn_reload)

        btn_health = Gtk.Button(label="Health check")
        btn_health.connect("clicked", self._on_health_check_clicked)
        row_btns.append(btn_health)

        self.health_result = Gtk.Label(label="")
        self.health_result.set_xalign(0.0)

        edit_box.append(row_btns)
        edit_box.append(self.health_result)

        settings_box.append(edit_box)

        # Populate edit controls from current settings
        self._populate_integration_edit()

        # Profile Bereich
        prof_hdr = Gtk.Label(label="Profile")
        prof_hdr.set_xalign(0.0)
        settings_box.append(prof_hdr)

        prof_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_prof = Gtk.Label(label="Profil:")
        lbl_prof.set_xalign(0.0)
        row1.append(lbl_prof)

        self.profile_combo = Gtk.ComboBoxText()
        try:
            names = list_builtin_profiles()
            if not names:
                self.profile_combo.append("none", "(keine Profile gefunden)")
                self.profile_combo.set_active_id("none")
            else:
                for n in names:
                    self.profile_combo.append(n, n)
                self.profile_combo.set_active(0)
        except Exception:
            self.profile_combo.append("err", "(Fehler beim Laden)")
            self.profile_combo.set_active_id("err")
        row1.append(self.profile_combo)

        btn_show = Gtk.Button(label="Anzeigen")
        btn_show.connect("clicked", self._on_profile_show_clicked)
        row1.append(btn_show)

        prof_box.append(row1)

        # Installations-Optionen
        opts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_overwrite_actions = Gtk.CheckButton(label="Actions überschreiben")
        self.chk_patch_settings = Gtk.CheckButton(label="Settings patchen")
        self.chk_install_shortcuts = Gtk.CheckButton(label="Shortcuts installieren")
        self.chk_dry_run = Gtk.CheckButton(label="Dry-run")
        opts.append(self.chk_overwrite_actions)
        opts.append(self.chk_patch_settings)
        opts.append(self.chk_install_shortcuts)
        opts.append(self.chk_dry_run)

        prof_box.append(opts)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_install = Gtk.Button(label="Installieren")
        btn_install.connect("clicked", self._on_profile_install_clicked)
        row2.append(btn_install)
        prof_box.append(row2)

        self.profile_result = Gtk.Label(label="")
        self.profile_result.set_wrap(True)
        self.profile_result.set_xalign(0.0)
        prof_box.append(self.profile_result)

        settings_box.append(prof_box)

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
        try:
            top_label.set_wrap_mode(Pango.WrapMode.CHAR)
        except Exception:
            pass
        try:
            top_label.set_max_width_chars(80)
        except Exception:
            pass
        top_label.set_hexpand(True)
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

        # Determine if HTTP trigger is enabled
        enabled = True
        try:
            smap = self._get_settings_map()
            enabled = str(smap.get("integration", {}).get("http_trigger_enabled", "false")).lower() == "true"
        except Exception:
            enabled = True

        # Update hint
        try:
            self.actions_hint.set_text("" if enabled else "HTTP Trigger disabled – in Settings aktivieren")
        except Exception:
            pass

        self._clear_listbox(self.actions_list)
        for action in actions:
            row = self._build_action_row(action, enabled)
            self.actions_list.append(row)
        # also refresh triggers editor when actions change (names/options)
        self._rebuild_triggers_editor()

    def _on_actions_source_changed(self, _combo: Gtk.ComboBoxText) -> None:
        active_id = self.actions_source.get_active_id() or "clipboard"
        self.actions_text.set_sensitive(active_id == "text")
        # Liste neu aufbauen, damit die [src=...] Badges in jeder Aktionszeile
        # die aktuell gewählte Quelle anzeigen.
        try:
            self.refresh_actions_list()
        except Exception:
            pass

    def _get_settings_map(self) -> dict:
        app = self.get_application()
        settings = getattr(app, "_settings", None)
        try:
            return settings.as_mapping() if settings else {}
        except Exception:
            return {}


    def _on_action_run_clicked(self, _btn: Gtk.Button, action: dict, override_combo: Optional[Gtk.ComboBoxText] = None, override_entry: Optional[Gtk.Entry] = None) -> None:
        # Determine source and text (per-row override hat Vorrang, sonst globale Quelle)
        src_id = None
        try:
            if override_combo is not None:
                ov = override_combo.get_active_id() or "global"
                if ov != "global":
                    src_id = ov
        except Exception:
            src_id = None

        if not src_id:
            src_id = self.actions_source.get_active_id() or "clipboard"

        if src_id == "text":
            if override_entry is not None:
                sel_text = override_entry.get_text() or ""
            else:
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
        self._rebuild_triggers_editor()

    # --- Actions Editor helpers (inline, raw JSON first phase) ---

    def _build_action_row(self, action: dict, run_enabled: bool) -> Gtk.ListBoxRow:
        """
        Build a row showing an action expander with preview and an inline raw JSON editor.
        """
        name = str(action.get("name") or "(unnamed)")
        typ = str(action.get("type") or "").lower()
        # header preview
        if typ == "http":
            method = str(action.get("method") or "GET").upper()
            url = str(action.get("url") or "")
            preview = f"{method} {url}" if url else method
        else:
            cmd = str(action.get("command") or "")
            preview = cmd or "(no command)"

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title = Gtk.Label(label=name)
        title.set_xalign(0.0)
        title.set_wrap(True)
        title.set_hexpand(True)
        # kompaktes Preview (Quelle-Override wird in der Zeile separat editiert)
        subt = Gtk.Label(label=f"[{typ}] {preview}")
        subt.set_xalign(0.0)
        subt.set_wrap(True)
        subt.get_style_context().add_class("dim-label")
        header.append(title)
        header.append(subt)

        # Editor area (raw JSON)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        tv = Gtk.TextView()
        tv.set_monospace(True)
        tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        buf = tv.get_buffer()
        import json as _json
        try:
            pretty = _json.dumps(action, ensure_ascii=False, indent=2)
        except Exception:
            pretty = str(action)
        buf.set_text(pretty, -1)
        sc = Gtk.ScrolledWindow()
        sc.set_min_content_height(140)
        sc.set_child(tv)
        vbox.append(sc)

        # Quelle (Override) – optional pro Aktion editierbar
        ovbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        ovlabel = Gtk.Label(label="Quelle (Override):")
        ovlabel.set_xalign(0.0)
        ovbox.append(ovlabel)

        ovcombo = Gtk.ComboBoxText()
        ovcombo.append("global", "Global (oben)")
        ovcombo.append("clipboard", "Clipboard")
        ovcombo.append("primary", "Primary")
        ovcombo.append("text", "Text")
        ovcombo.set_active_id("global")
        ovbox.append(ovcombo)

        oventry = Gtk.Entry()
        oventry.set_placeholder_text("Text für Override=Text …")
        oventry.set_sensitive(False)
        oventry.set_hexpand(True)
        ovbox.append(oventry)

        def _ov_changed(_c):
            try:
                oventry.set_sensitive((ovcombo.get_active_id() or "global") == "text")
            except Exception:
                pass
            return False
        ovcombo.connect("changed", _ov_changed)

        vbox.append(ovbox)

        # Buttons: Run / Save / Cancel / Duplicate / Delete
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        run_btn = Gtk.Button(label="Run")
        run_btn.set_sensitive(run_enabled)
        run_btn.connect("clicked", self._on_action_run_clicked, action, ovcombo, oventry)
        btns.append(run_btn)

        save_btn = Gtk.Button(label="Save")
        save_btn.connect("clicked", self._on_action_save_clicked, tv, name)
        btns.append(save_btn)

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self._on_action_cancel_clicked)
        btns.append(cancel_btn)

        dup_btn = Gtk.Button(label="Duplicate")
        dup_btn.connect("clicked", self._on_action_duplicate_clicked, name)
        btns.append(dup_btn)

        del_btn = Gtk.Button(label="Delete")
        del_btn.connect("clicked", self._on_action_delete_clicked, name)
        btns.append(del_btn)

        # per-row status
        status = Gtk.Label(label="")
        status.set_xalign(0.0)

        vbox.append(btns)
        vbox.append(status)

        # Wrap into expander
        exp = Gtk.Expander()
        exp.set_child(vbox)
        exp.set_hexpand(True)
        exp.set_margin_top(4)
        # expander header must be a widget; using a box with two labels
        header_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header_row.append(header)
        exp.set_label_widget(header_row)

        row = Gtk.ListBoxRow()
        row.set_child(exp)
        # attach some refs for status updates
        row._wbridge_status_label = status  # type: ignore[attr-defined]
        return row

    def _get_textview_text(self, tv: Gtk.TextView) -> str:
        buf = tv.get_buffer()
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        return buf.get_text(start, end, True)

    def _on_action_save_clicked(self, _btn: Gtk.Button, tv: Gtk.TextView, original_name: str) -> None:
        # Parse JSON, validate, write back into actions.json (replace by original_name or rename)
        try:
            import json as _json
            raw_text = self._get_textview_text(tv)
            obj = _json.loads(raw_text)
            if not isinstance(obj, dict):
                raise ValueError("editor content must be a JSON object")
            ok, err = validate_action_dict(obj)
            if not ok:
                self.actions_result.set_text(f"Validation failed: {err}")
                return

            payload = load_actions_raw()
            actions = payload.get("actions", [])
            # Check name collisions if renamed
            new_name = str(obj.get("name") or "").strip()
            if not new_name:
                self.actions_result.set_text("Validation failed: action.name must not be empty")
                return

            # replace or rename
            replaced = False
            for i, a in enumerate(actions):
                if str(a.get("name") or "") == original_name:
                    actions[i] = obj
                    replaced = True
                    break
            if not replaced:
                # if original missing (race), append
                actions.append(obj)

            # if name changed and triggers reference original_name, keep as-is (user can adjust in Triggers editor later)
            payload["actions"] = actions

            backup = write_actions_config(payload)
            # reload actions into app
            app = self.get_application()
            try:
                new_cfg = load_actions()
                setattr(app, "_actions", new_cfg)
            except Exception:
                pass
            self.refresh_actions_list()
            try:
                self._logger.info("actions.save ok name=%s", new_name)
            except Exception:
                pass
            self.actions_result.set_text(f"Action saved (backup: {backup})")
        except Exception as e:
            self.actions_result.set_text(f"Save failed: {e!r}")

    def _on_action_cancel_clicked(self, _btn: Gtk.Button) -> None:
        # Simply reload actions from disk and rebuild list
        try:
            app = self.get_application()
            new_cfg = load_actions()
            setattr(app, "_actions", new_cfg)
        except Exception:
            pass
        self.refresh_actions_list()

    def _on_action_duplicate_clicked(self, _btn: Gtk.Button, original_name: str) -> None:
        try:
            payload = load_actions_raw()
            actions = payload.get("actions", [])
            src = next((a for a in actions if str(a.get("name") or "") == original_name), None)
            if not src:
                self.actions_result.set_text("Duplicate failed: source action not found")
                return
            import copy as _copy
            dup = _copy.deepcopy(src)
            base = str(src.get("name") or "Action")
            new_name = base + " (copy)"
            names = {str(a.get("name") or "") for a in actions}
            # ensure uniqueness
            idx = 2
            while new_name in names:
                new_name = f"{base} (copy {idx})"
                idx += 1
            dup["name"] = new_name
            actions.append(dup)
            payload["actions"] = actions
            backup = write_actions_config(payload)
            # reload
            app = self.get_application()
            try:
                new_cfg = load_actions()
                setattr(app, "_actions", new_cfg)
            except Exception:
                pass
            self.refresh_actions_list()
            try:
                self._logger.info("actions.duplicate ok source=%s new=%s", original_name, new_name)
            except Exception:
                pass
            self.actions_result.set_text(f"Action duplicated as '{new_name}' (backup: {backup})")
        except Exception as e:
            self.actions_result.set_text(f"Duplicate failed: {e!r}")

    def _on_action_delete_clicked(self, _btn: Gtk.Button, name: str) -> None:
        try:
            payload = load_actions_raw()
            actions = payload.get("actions", [])
            before = len(actions)
            actions = [a for a in actions if str(a.get("name") or "") != name]
            if len(actions) == before:
                self.actions_result.set_text("Delete: action not found")
                return
            # Remove triggers that reference the deleted action
            triggers = payload.get("triggers", {})
            if isinstance(triggers, dict):
                for k in list(triggers.keys()):
                    if triggers.get(k) == name:
                        del triggers[k]
                payload["triggers"] = triggers
            payload["actions"] = actions
            backup = write_actions_config(payload)
            # reload
            app = self.get_application()
            try:
                new_cfg = load_actions()
                setattr(app, "_actions", new_cfg)
            except Exception:
                pass
            self.refresh_actions_list()
            try:
                self._logger.info("actions.delete ok name=%s", name)
            except Exception:
                pass
            self.actions_result.set_text(f"Action '{name}' deleted (backup: {backup})")
        except Exception as e:
            self.actions_result.set_text(f"Delete failed: {e!r}")

    def _on_add_action_clicked(self, _btn: Gtk.Button) -> None:
        try:
            payload = load_actions_raw()
            actions = payload.get("actions", [])
            # default http action
            new = {
                "name": "New Action",
                "type": "http",
                "method": "GET",
                "url": "",
                "headers": {},
                "params": {}
            }
            # ensure unique name
            names = {str(a.get("name") or "") for a in actions}
            base = new["name"]
            name = base
            idx = 2
            while name in names:
                name = f"{base} {idx}"
                idx += 1
            new["name"] = name
            actions.append(new)
            payload["actions"] = actions
            backup = write_actions_config(payload)
            # reload and rebuild
            app = self.get_application()
            try:
                new_cfg = load_actions()
                setattr(app, "_actions", new_cfg)
            except Exception:
                pass
            self.refresh_actions_list()
            self._rebuild_triggers_editor()
            try:
                self._logger.info("actions.add ok name=%s", name)
            except Exception:
                pass
            self.actions_result.set_text(f"Action '{name}' added (backup: {backup})")
        except Exception as e:
            self.actions_result.set_text(f"Add failed: {e!r}")

    # --- Triggers Editor helpers ---

    def _rebuild_triggers_editor(self) -> None:
        # Build rows from current payload (aliases and selectable action names)
        payload = load_actions_raw()
        triggers = payload.get("triggers", {}) or {}
        actions = payload.get("actions", []) or []
        action_names = sorted({str(a.get("name") or "") for a in actions if a.get("name")})
        # clear list
        self._clear_listbox(self.triggers_list)
        # create row per alias
        for alias, target in triggers.items():
            row = self._build_trigger_row(str(alias), str(target or ""), action_names)
            self.triggers_list.append(row)

    def _build_trigger_row(self, alias: str, target: str, action_names: list[str]) -> Gtk.ListBoxRow:
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        alias_entry = Gtk.Entry()
        alias_entry.set_text(alias)
        alias_entry.set_width_chars(18)
        box.append(Gtk.Label(label="Alias:"))
        box.append(alias_entry)

        box.append(Gtk.Label(label="Action:"))
        action_combo = Gtk.ComboBoxText()
        for n in action_names:
            action_combo.append(n, n)
        # select current
        if target in action_names:
            action_combo.set_active_id(target)
        elif action_names:
            action_combo.set_active(0)
        box.append(action_combo)

        del_btn = Gtk.Button(label="Delete")
        del_btn.connect("clicked", self._on_trigger_row_delete_clicked, alias_entry)
        box.append(del_btn)

        row = Gtk.ListBoxRow()
        row.set_child(box)
        # annotate for save
        row._wbridge_alias_entry = alias_entry  # type: ignore[attr-defined]
        row._wbridge_action_combo = action_combo  # type: ignore[attr-defined]
        return row

    def _on_triggers_add_clicked(self, _btn: Gtk.Button) -> None:
        # Add an empty/new row
        payload = load_actions_raw()
        actions = payload.get("actions", []) or []
        action_names = sorted({str(a.get("name") or "") for a in actions if a.get("name")})
        row = self._build_trigger_row("", action_names[0] if action_names else "", action_names)
        self.triggers_list.append(row)

    def _on_trigger_row_delete_clicked(self, _btn: Gtk.Button, alias_entry: Gtk.Entry) -> None:
        # remove the row from listbox
        row = alias_entry.get_parent().get_parent()  # type: ignore[attr-defined]
        # find the actual ListBoxRow ancestor
        parent = row
        while parent and not isinstance(parent, Gtk.ListBoxRow):
            parent = parent.get_parent()  # type: ignore[attr-defined]
        if isinstance(parent, Gtk.ListBoxRow):
            self.triggers_list.remove(parent)

    def _on_triggers_save_clicked(self, _btn: Gtk.Button) -> None:
        try:
            # gather rows
            new_triggers: dict[str, str] = {}
            child = self.triggers_list.get_first_child()
            seen_aliases = set()
            while child is not None:
                if isinstance(child, Gtk.ListBoxRow):
                    alias_entry = getattr(child, "_wbridge_alias_entry", None)
                    action_combo = getattr(child, "_wbridge_action_combo", None)
                    if alias_entry and action_combo:
                        alias = alias_entry.get_text().strip()
                        action_name = action_combo.get_active_id() or ""
                        if not alias:
                            self.actions_result.set_text("Save Triggers failed: alias must not be empty")
                            return
                        if alias in seen_aliases:
                            self.actions_result.set_text(f"Save Triggers failed: duplicate alias '{alias}'")
                            return
                        seen_aliases.add(alias)
                        new_triggers[alias] = action_name
                child = child.get_next_sibling()

            # validate action names exist
            payload = load_actions_raw()
            actions = payload.get("actions", []) or []
            valid_names = {str(a.get("name") or "") for a in actions}
            for k, v in new_triggers.items():
                if v and v not in valid_names:
                    self.actions_result.set_text(f"Save Triggers failed: action '{v}' for alias '{k}' not found")
                    return

            payload["triggers"] = new_triggers
            backup = write_actions_config(payload)

            # reload actions into app (triggers part)
            app = self.get_application()
            try:
                new_cfg = load_actions()
                setattr(app, "_actions", new_cfg)
            except Exception:
                pass
            self.refresh_actions_list()
            self._rebuild_triggers_editor()
            try:
                self._logger.info("triggers.save ok count=%d", len(new_triggers))
            except Exception:
                pass
            self.actions_result.set_text(f"Triggers saved (backup: {backup})")
        except Exception as e:
            self.actions_result.set_text(f"Save Triggers failed: {e!r}")

    # --- Settings helpers: reload, edit, health check ---

    def _reload_settings(self) -> None:
        # Reload settings from disk into the application, refresh UI and actions
        app = self.get_application()
        try:
            new_settings = load_settings()
            setattr(app, "_settings", new_settings)
        except Exception:
            pass
        self._refresh_integration_status()
        self._populate_integration_edit()
        self.refresh_actions_list()
        try:
            self._logger.info("settings.reload ok")
        except Exception:
            pass

    def _on_reload_settings_clicked(self, _btn: Gtk.Button) -> None:
        self._reload_settings()

    def _populate_integration_edit(self) -> None:
        try:
            smap = self._get_settings_map()
            integ = smap.get("integration", {})
            enabled = str(integ.get("http_trigger_enabled", "false")).lower() == "true"
            base = str(integ.get("http_trigger_base_url", ""))
            path = str(integ.get("http_trigger_trigger_path", ""))
            self.integ_enabled_switch.set_active(enabled)
            self.integ_base_entry.set_text(base)
            self.integ_path_entry.set_text(path)
        except Exception:
            # leave defaults if parsing fails
            pass

    def _on_save_integration_clicked(self, _btn: Gtk.Button) -> None:
        # Validate and persist integration fields atomically
        try:
            enabled = self.integ_enabled_switch.get_active()
            base = self.integ_base_entry.get_text().strip()
            path = self.integ_path_entry.get_text().strip()
            # simple validations
            if not base.startswith("http://") and not base.startswith("https://"):
                self.settings_result.set_text("Ungültige Base-URL (muss mit http:// oder https:// beginnen).")
                return
            if not path.startswith("/"):
                self.settings_result.set_text("Ungültiger Trigger-Pfad (muss mit '/' beginnen).")
                return
            # write
            set_integration_settings(
                http_trigger_enabled=bool(enabled),
                http_trigger_base_url=base,
                http_trigger_trigger_path=path
            )
            try:
                self._logger.info("settings.integration.save enabled=%s base=%s path=%s", bool(enabled), base, path)
            except Exception:
                pass
            self.settings_result.set_text("Integration gespeichert.")
            # reload to reflect new state
            self._reload_settings()
        except Exception as e:
            self.settings_result.set_text(f"Fehler beim Speichern: {e!r}")

    def _on_discard_integration_clicked(self, _btn: Gtk.Button) -> None:
        # Discard local edits and re-populate from disk
        self._reload_settings()

    def _on_health_check_clicked(self, _btn: Gtk.Button) -> None:
        # Perform a simple HTTP GET to base_url + health_path
        try:
            smap = self._get_settings_map()
            integ = smap.get("integration", {})
            base = str(integ.get("http_trigger_base_url", "") or "")
            hpath = str(integ.get("http_trigger_health_path", "/health") or "/health")
            import urllib.request
            import urllib.error
            url = f"{base}{hpath}"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:  # type: ignore[arg-type]
                code = getattr(resp, "status", 200)
                try:
                    self._logger.info("health.check ok code=%s url=%s", code, url)
                except Exception:
                    pass
                self.health_result.set_text(f"Health OK ({code}) – {url}")
        except Exception as e:
            try:
                self._logger.warning("health.check failed error=%r", e)
            except Exception:
                pass
            self.health_result.set_text(f"Health FAILED – {e!r}")

    # --- Settings placeholder callbacks ---

    def _refresh_integration_status(self) -> None:
        try:
            smap = self._get_settings_map()
            integ = smap.get("integration", {})
            enabled = str(integ.get("http_trigger_enabled", "false"))
            base = str(integ.get("http_trigger_base_url", ""))
            path = str(integ.get("http_trigger_trigger_path", ""))
            self.integ_enabled_v.set_text(enabled)
            self.integ_base_v.set_text(base)
            self.integ_path_v.set_text(path)
        except Exception:
            self.integ_enabled_v.set_text("?")
            self.integ_base_v.set_text("?")
            self.integ_path_v.set_text("?")

    def _on_profile_show_clicked(self, _btn: Gtk.Button) -> None:
        pid = self.profile_combo.get_active_id()
        if not pid or pid in ("none", "err"):
            self.profile_result.set_text("Kein Profil ausgewählt.")
            return
        try:
            info = pm_show_profile(pid)
            # kompakte Darstellung
            meta = info.get("meta", {})
            acts = info.get("actions", {})
            sc = info.get("shortcuts", {})
            summary = (
                f"Profil: {meta.get('name', pid)} v{meta.get('version','')}\n"
                f"Actions: {acts.get('count',0)} (Triggers: {', '.join(acts.get('triggers', [])[:8])})\n"
                f"Shortcuts: {sc.get('count',0)}"
            )
            self.profile_result.set_text(summary)
        except Exception as e:
            self.profile_result.set_text(f"Fehler: {e!r}")

    def _on_profile_install_clicked(self, _btn: Gtk.Button) -> None:
        pid = self.profile_combo.get_active_id()
        if not pid or pid in ("none", "err"):
            self.profile_result.set_text("Kein Profil ausgewählt.")
            return
        try:
            report = pm_install_profile(
                pid,
                overwrite_actions=bool(self.chk_overwrite_actions.get_active()),
                patch_settings=bool(self.chk_patch_settings.get_active()),
                install_shortcuts=bool(self.chk_install_shortcuts.get_active()),
                dry_run=bool(self.chk_dry_run.get_active()),
            )
            # kompakte Zusammenfassung
            acts = report.get("actions", {})
            trigs = report.get("triggers", {})
            sets = report.get("settings", {})
            sc = report.get("shortcuts", {})
            errors = report.get("errors", [])
            txt = (
                f"Install-Report (ok={report.get('ok')} dry_run={report.get('dry_run')}):\n"
                f"- actions: added={acts.get('added',0)} updated={acts.get('updated',0)} skipped={acts.get('skipped',0)}\n"
                f"- triggers: added={trigs.get('added',0)} updated={trigs.get('updated',0)} skipped={trigs.get('skipped',0)}\n"
                f"- settings: patched={len(sets.get('patched',[]))} skipped={len(sets.get('skipped',[]))}\n"
                f"- shortcuts: installed={sc.get('installed',0)} skipped={sc.get('skipped',0)}\n"
                f"- errors: {len(errors)}"
            )
            self.profile_result.set_text(txt)
            # Refresh settings and actions after install (in case settings changed)
            self._reload_settings()
        except Exception as e:
            self.profile_result.set_text(f"Fehler: {e!r}")

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
