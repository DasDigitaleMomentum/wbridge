#!/usr/bin/env python3
"""
Gtk4 MainWindow for wbridge with Stack + StackSidebar UI (moved to ui.main_window).

Navigation (left sidebar):
- History
- Actions (Master-Detail: Liste links, Editor rechts; Form primär, Raw-JSON optional)
- Triggers (Stub – implemented in later step)
- Shortcuts (Stub – implemented in later step)
- Settings
- Status

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
import shutil
from pathlib import Path
import gettext

# i18n init (fallback to identity if no translations installed)
try:
    _t = gettext.translation("wbridge", localedir=None, fallback=True)
    _ = _t.gettext
except Exception:
    _ = lambda s: s

from ..platform import active_env_summary, socket_path, xdg_state_dir, xdg_config_dir
from ..config import (
    load_actions,
    load_settings,
    load_actions_raw,
    write_actions_config,
    validate_action_dict,
)
from ..actions import run_action, ActionContext
from .. import gnome_shortcuts
from ..profiles_manager import (
    list_builtin_profiles,
    show_profile as pm_show_profile,
    install_profile as pm_install_profile,
    load_profile_shortcuts,
    remove_profile_shortcuts,
)
from .pages.history_page import HistoryPage
from .pages.actions_page import ActionsPage
from .pages.triggers_page import TriggersPage
from .pages.shortcuts_page import ShortcutsPage
from .pages.settings_page import SettingsPage
from .pages.status_page import StatusPage
from .components.help_panel import build_help_panel


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application)
        self.set_title("wbridge")
        self.set_default_size(1200, 880)
        self._logger = logging.getLogger("wbridge")
        # Cache für aktuelle Selektion (vermeidet Blocking-Reads auf dem GTK-Mainthread)
        self._cur_clip: str = ""
        self._cur_primary: str = ""
        # Dirty-Flag für Listenneuaufbau (verhindert unnötige/zu häufige Refreshes)
        self._hist_dirty: bool = True
        # In-Flight-Guards für async Reads (verhindert Überschwemmung/Hänger)
        self._reading_cb: bool = False
        self._reading_pr: bool = False

        # Load CSS (if available)
        self._load_css()

        # Actions: Master-Detail State
        self._actions_selected_name: Optional[str] = None
        self._http_trigger_enabled: bool = True

        # Navigation: StackSidebar + Stack
        _sidebar, stack = self._build_navigation()
        self.history_page = HistoryPage(self)
        self.actions_page = ActionsPage(self, self.history_page)
        self.triggers_page = TriggersPage(self)
        self.shortcuts_page = ShortcutsPage(self)
        self.settings_page = SettingsPage(self)
        self.status_page = StatusPage(self)

        # Seiten einhängen
        stack.add_titled(self.history_page, "history", _("History"))
        stack.add_titled(self.actions_page, "actions", _("Actions"))
        stack.add_titled(self.triggers_page, "triggers", _("Triggers"))
        stack.add_titled(self.shortcuts_page, "shortcuts", _("Shortcuts"))
        stack.add_titled(self.settings_page, "settings", _("Settings"))
        stack.add_titled(self.status_page, "status", _("Status"))

        # initial population
        self.actions_page.refresh_actions_list()
        self.triggers_page.rebuild_editor()
        # start file monitors (settings.ini, actions.json) for auto-reload
        self._init_file_monitors()

        # Periodisches Refresh der History-Listen
        GLib.timeout_add(400, self._refresh_tick)  # type: ignore

    def _build_navigation(self) -> tuple[Gtk.StackSidebar, Gtk.Stack]:
        """Erstellt die linksseitige Navigation (StackSidebar) und den Inhaltsbereich (Stack)."""
        root = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        root.set_hexpand(True)
        root.set_vexpand(True)

        stack = Gtk.Stack()
        stack.set_hexpand(True)
        stack.set_vexpand(True)
        try:
            stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        except Exception:
            pass

        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(stack)
        sidebar.set_vexpand(True)
        sidebar.set_hexpand(False)
        sidebar.set_size_request(220, -1)

        root.append(sidebar)
        root.append(stack)
        self.set_child(root)
        return sidebar, stack

    # --- Seiten-Fabriken ---

    def _page_history(self) -> Gtk.Widget:
        # History page content
        history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        history_box.set_margin_start(16)
        history_box.set_margin_end(16)
        history_box.set_margin_top(16)
        history_box.set_margin_bottom(16)

        history_desc = Gtk.Label(label=_("History (Clipboard / Primary)\n"
                                       "• List of recent entries with actions: Set as Clipboard, Set as Primary, Swap (swaps the last two).\n"
                                       "• Tip: CLI `wbridge selection set/get` also works."))
        history_desc.set_wrap(True)
        history_desc.set_xalign(0.0)
        history_box.append(history_desc)

        # History Controls: manueller Refresh + Zähler
        hist_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        refresh_btn = Gtk.Button(label=_("Refresh"))
        refresh_btn.connect("clicked", lambda _b: self.refresh_history())
        hist_controls.append(refresh_btn)

        self.hist_count = Gtk.Label(label=_("Entries: 0 / 0"))
        self.hist_count.set_xalign(0.0)
        hist_controls.append(self.hist_count)

        history_box.append(hist_controls)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        grid.set_column_homogeneous(True)

        # Clipboard frame
        cb_frame = Gtk.Frame(label=_("Clipboard"))
        cb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cb_box.set_margin_start(10)
        cb_box.set_margin_end(10)
        cb_box.set_margin_top(10)
        cb_box.set_margin_bottom(10)

        # Simple Set/Get helpers (bleiben als Testwerkzeuge)
        self.cb_entry = Gtk.Entry()
        self.cb_entry.set_placeholder_text(_("Type text here and click Set …"))
        cb_box.append(self.cb_entry)

        cb_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        cb_set_btn = Gtk.Button(label=_("Set clipboard"))
        cb_set_btn.connect("clicked", self.on_set_clipboard_clicked)
        cb_btn_box.append(cb_set_btn)

        cb_get_btn = Gtk.Button(label=_("Get clipboard"))
        cb_get_btn.connect("clicked", self.on_get_clipboard_clicked)
        cb_btn_box.append(cb_get_btn)

        swap_cb_btn = Gtk.Button(label=_("Swap last two (clipboard)"))
        swap_cb_btn.connect("clicked", lambda _b: self.on_swap_clicked("clipboard"))
        cb_btn_box.append(swap_cb_btn)

        cb_box.append(cb_btn_box)

        self.cb_label = Gtk.Label(label=_("Current: (empty)"))
        self.cb_label.set_xalign(0.0)
        self.cb_label.set_wrap(False)
        try:
            self.cb_label.set_ellipsize(Pango.EllipsizeMode.END)
        except Exception:
            pass
        self.cb_label.set_hexpand(True)
        cb_box.append(self.cb_label)

        # Clipboard History List
        cb_hist_hdr = Gtk.Label(label=_("History (newest first):"))
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
        pr_frame = Gtk.Frame(label=_("Primary Selection"))
        pr_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        pr_box.set_margin_start(10)
        pr_box.set_margin_end(10)
        pr_box.set_margin_top(10)
        pr_box.set_margin_bottom(10)

        self.pr_entry = Gtk.Entry()
        self.pr_entry.set_placeholder_text(_("Type text here and click Set …"))
        pr_box.append(self.pr_entry)

        pr_btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        pr_set_btn = Gtk.Button(label=_("Set primary"))
        pr_set_btn.connect("clicked", self.on_set_primary_clicked)
        pr_btn_box.append(pr_set_btn)

        pr_get_btn = Gtk.Button(label=_("Get primary"))
        pr_get_btn.connect("clicked", self.on_get_primary_clicked)
        pr_btn_box.append(pr_get_btn)

        swap_pr_btn = Gtk.Button(label=_("Swap last two (primary)"))
        swap_pr_btn.connect("clicked", lambda _b: self.on_swap_clicked("primary"))
        pr_btn_box.append(swap_pr_btn)

        pr_box.append(pr_btn_box)

        self.pr_label = Gtk.Label(label=_("Current: (empty)"))
        self.pr_label.set_xalign(0.0)
        self.pr_label.set_wrap(False)
        try:
            self.pr_label.set_ellipsize(Pango.EllipsizeMode.END)
        except Exception:
            pass
        self.pr_label.set_hexpand(True)
        pr_box.append(self.pr_label)

        pr_hist_hdr = Gtk.Label(label=_("History (newest first):"))
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
        # Help panel
        try:
            history_box.append(build_help_panel("history"))
        except Exception:
            pass

        return history_box

    def _page_actions(self) -> Gtk.Widget:
        # Actions page content (Master-Detail; Triggers-Editor bleibt vorerst unten, wird in Step 4 separiert)
        actions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        actions_box.set_margin_start(16)
        actions_box.set_margin_end(16)
        actions_box.set_margin_top(16)
        actions_box.set_margin_bottom(16)

        actions_desc = Gtk.Label(label=_("Actions\n"
                                        "• Defined actions (HTTP/Shell) loaded from ~/.config/wbridge/actions.json.\n"
                                        "• Choose source: Clipboard / Primary / Text."))
        actions_desc.set_wrap(True)
        actions_desc.set_xalign(0.0)
        actions_box.append(actions_desc)

        # Controls: source selection + optional text + reload
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        src_label = Gtk.Label(label=_("Source:"))
        src_label.set_xalign(0.0)
        controls.append(src_label)

        self.actions_source = Gtk.ComboBoxText()
        self.actions_source.append("clipboard", _("Clipboard"))
        self.actions_source.append("primary", _("Primary"))
        self.actions_source.append("text", _("Text"))
        self.actions_source.set_active_id("clipboard")
        self.actions_source.connect("changed", self._on_actions_source_changed)
        controls.append(self.actions_source)

        self.actions_text = Gtk.Entry()
        self.actions_text.set_placeholder_text(_("Text for source=Text …"))
        self.actions_text.set_sensitive(False)
        self.actions_text.set_hexpand(True)
        controls.append(self.actions_text)

        reload_btn = Gtk.Button(label=_("Reload actions"))
        reload_btn.connect("clicked", self._on_reload_actions_clicked)
        controls.append(reload_btn)

        add_action_btn = Gtk.Button(label=_("Add Action"))
        add_action_btn.connect("clicked", self._on_add_action_clicked)
        controls.append(add_action_btn)

        actions_box.append(controls)

        # Hint if HTTP trigger disabled
        self.actions_hint = Gtk.Label(label="")
        self.actions_hint.set_wrap(True)
        self.actions_hint.set_xalign(0.0)
        actions_box.append(self.actions_hint)

        # Master-Detail Bereich
        md = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        md.set_hexpand(True)
        md.set_vexpand(True)

        # Left: Actions list
        left_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left_box.set_size_request(280, -1)
        lbl_actions = Gtk.Label(label=_("Actions"))
        lbl_actions.set_xalign(0.0)
        left_box.append(lbl_actions)

        self.actions_list = Gtk.ListBox()
        self.actions_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.actions_list.connect("row-selected", self._on_actions_row_selected)
        left_scroll = Gtk.ScrolledWindow()
        left_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        left_scroll.set_min_content_height(260)
        left_scroll.set_child(self.actions_list)
        left_box.append(left_scroll)

        md.append(left_box)

        # Right: Editor (Stack form/json)
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_box.set_hexpand(True)
        right_box.set_vexpand(True)

        self._actions_detail_stack = Gtk.Stack()
        self._actions_detail_stack.set_hexpand(True)
        self._actions_detail_stack.set_vexpand(True)

        # Stack Switcher
        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self._actions_detail_stack)
        right_box.append(switcher)

        # Form view
        form_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        # Gemeinsame Felder
        row_name = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_name = Gtk.Label(label=_("Name:"))
        lbl_name.set_xalign(0.0)
        self.ed_name_entry = Gtk.Entry()
        self.ed_name_entry.set_hexpand(True)
        row_name.append(lbl_name); row_name.append(self.ed_name_entry)
        form_box.append(row_name)

        row_type = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_type = Gtk.Label(label=_("Type:"))
        lbl_type.set_xalign(0.0)
        self.ed_type_combo = Gtk.ComboBoxText()
        self.ed_type_combo.append("http", "http")
        self.ed_type_combo.append("shell", "shell")
        self.ed_type_combo.set_active_id("http")
        self.ed_type_combo.connect("changed", self._actions_on_type_changed)
        row_type.append(lbl_type); row_type.append(self.ed_type_combo)
        form_box.append(row_type)

        # HTTP Felder
        self.http_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        http_row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        http_method_lbl = Gtk.Label(label=_("Method:"))
        http_method_lbl.set_xalign(0.0)
        self.ed_http_method = Gtk.ComboBoxText()
        self.ed_http_method.append("GET", "GET")
        self.ed_http_method.append("POST", "POST")
        self.ed_http_method.set_active_id("GET")
        http_url_lbl = Gtk.Label(label=_("URL:"))
        http_url_lbl.set_xalign(0.0)
        self.ed_http_url = Gtk.Entry()
        self.ed_http_url.set_hexpand(True)
        http_row1.append(http_method_lbl); http_row1.append(self.ed_http_method)
        http_row1.append(http_url_lbl); http_row1.append(self.ed_http_url)
        self.http_box.append(http_row1)
        form_box.append(self.http_box)

        # SHELL Felder
        self.shell_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sh_row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sh_cmd_lbl = Gtk.Label(label=_("Command:"))
        sh_cmd_lbl.set_xalign(0.0)
        self.ed_shell_cmd = Gtk.Entry()
        self.ed_shell_cmd.set_hexpand(True)
        sh_row1.append(sh_cmd_lbl); sh_row1.append(self.ed_shell_cmd)
        self.shell_box.append(sh_row1)

        sh_row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sh_args_lbl = Gtk.Label(label=_("Args (JSON array):"))
        sh_args_lbl.set_xalign(0.0)
        self.ed_shell_args_tv = Gtk.TextView(); self.ed_shell_args_tv.set_monospace(True)
        sh_args_sw = Gtk.ScrolledWindow(); sh_args_sw.set_min_content_height(40); sh_args_sw.set_child(self.ed_shell_args_tv)
        sh_row2.append(sh_args_lbl); sh_row2.append(sh_args_sw)
        self.shell_box.append(sh_row2)

        sh_row3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sh_use_lbl = Gtk.Label(label=_("Use shell:"))
        sh_use_lbl.set_xalign(0.0)
        self.ed_shell_use_switch = Gtk.Switch()
        sh_row3.append(sh_use_lbl); sh_row3.append(self.ed_shell_use_switch)
        self.shell_box.append(sh_row3)
        form_box.append(self.shell_box)

        # Buttons (Form)
        form_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_save_form = Gtk.Button(label=_("Save (Form)"))
        btn_save_form.connect("clicked", self._on_actions_save_form_clicked)
        form_btns.append(btn_save_form)

        btn_duplicate = Gtk.Button(label=_("Duplicate"))
        btn_duplicate.connect("clicked", self._on_action_duplicate_current_clicked)
        form_btns.append(btn_duplicate)

        btn_delete = Gtk.Button(label=_("Delete"))
        btn_delete.connect("clicked", self._on_action_delete_current_clicked)
        form_btns.append(btn_delete)

        btn_cancel = Gtk.Button(label=_("Cancel"))
        btn_cancel.connect("clicked", self._on_action_cancel_clicked)
        form_btns.append(btn_cancel)

        self.btn_run = Gtk.Button(label=_("Run"))
        self.btn_run.connect("clicked", self._on_action_run_current_clicked)
        form_btns.append(self.btn_run)

        form_box.append(form_btns)

        self._actions_detail_stack.add_titled(form_box, "form", _("Form"))

        # JSON view
        json_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._actions_json_tv = Gtk.TextView()
        self._actions_json_tv.set_monospace(True)
        self._actions_json_tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        json_sw = Gtk.ScrolledWindow()
        json_sw.set_min_content_height(220)
        json_sw.set_child(self._actions_json_tv)
        json_box.append(json_sw)
        btn_save_json = Gtk.Button(label=_("Save (JSON)"))
        btn_save_json.connect("clicked", self._on_actions_save_json_clicked)
        json_box.append(btn_save_json)

        self._actions_detail_stack.add_titled(json_box, "json", "JSON")
        try:
            self._actions_detail_stack.set_visible_child_name("form")
        except Exception:
            pass

        right_box.append(self._actions_detail_stack)

        # Result output (global for Actions)
        self.actions_result = Gtk.Label(label="")
        self.actions_result.set_wrap(True)
        self.actions_result.set_xalign(0.0)
        right_box.append(self.actions_result)

        md.append(right_box)
        actions_box.append(md)

        # Sichtbarkeit HTTP/Shell initial setzen
        self._actions_update_type_visibility()

        # Help panel
        try:
            actions_box.append(build_help_panel("actions"))
        except Exception:
            pass

        return actions_box

    def _page_triggers(self) -> Gtk.Widget:
        # Triggers-Seite: Tabelle + Add/Save Buttons
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)

        hdr = Gtk.Label(label=_("Triggers (Alias → Action)"))
        hdr.set_xalign(0.0)
        box.append(hdr)

        self.triggers_list = Gtk.ListBox()
        self.triggers_list.set_selection_mode(Gtk.SelectionMode.NONE)
        tr_scrolled = Gtk.ScrolledWindow()
        tr_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        tr_scrolled.set_min_content_height(260)
        tr_scrolled.set_child(self.triggers_list)
        box.append(tr_scrolled)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add_btn = Gtk.Button(label=_("Add Trigger"))
        add_btn.connect("clicked", self._on_triggers_add_clicked)
        btns.append(add_btn)

        save_btn = Gtk.Button(label=_("Save Triggers"))
        save_btn.connect("clicked", self._on_triggers_save_clicked)
        btns.append(save_btn)

        box.append(btns)

        # initial populate
        try:
            self._rebuild_triggers_editor()
        except Exception:
            pass

        # Help panel
        try:
            box.append(build_help_panel("triggers"))
        except Exception:
            pass

        return box

    def _page_shortcuts(self) -> Gtk.Widget:
        # Shortcuts-Seite: wbridge-verwaltete Einträge editierbar; optional alle anzeigen (read-only)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(16)
        box.set_margin_bottom(16)

        # Header + Hint
        hdr = Gtk.Label(label=_("Shortcuts (GNOME Custom Keybindings)"))
        hdr.set_xalign(0.0)
        box.append(hdr)

        hint = Gtk.Label(label=_("Only wbridge-managed entries are editable. Foreign entries optionally visible (read-only)."))
        hint.set_wrap(True)
        hint.set_xalign(0.0)
        box.append(hint)

        # PATH-Hinweis (falls wbridge nicht im PATH)
        self.shortcuts_path_hint = Gtk.Label(label="")
        self.shortcuts_path_hint.set_wrap(True)
        self.shortcuts_path_hint.set_xalign(0.0)
        try:
            if shutil.which("wbridge") is None:
                self.shortcuts_path_hint.set_text(_("Hint: 'wbridge' was not found in PATH. GNOME Shortcuts call 'wbridge'; install user-wide via pipx/pip --user or use an absolute path in the shortcuts."))
        except Exception:
            pass
        box.append(self.shortcuts_path_hint)

        # Controls: Show all (read-only), Add, Save, Reload
        ctrl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_show = Gtk.Label(label=_("Show all custom (read-only):"))
        lbl_show.set_xalign(0.0)
        ctrl.append(lbl_show)
        self.shortcuts_show_all = Gtk.Switch()
        self.shortcuts_show_all.set_active(False)
        def _on_show_all(_sw, _ps=None):
            try:
                self._shortcuts_reload()
            except Exception:
                pass
            return False
        self.shortcuts_show_all.connect("state-set", _on_show_all)
        ctrl.append(self.shortcuts_show_all)

        btn_add = Gtk.Button(label=_("Add"))
        btn_add.connect("clicked", self._shortcuts_on_add_clicked)
        ctrl.append(btn_add)

        btn_save = Gtk.Button(label=_("Save"))
        btn_save.connect("clicked", self._shortcuts_on_save_clicked)
        ctrl.append(btn_save)

        btn_reload = Gtk.Button(label=_("Reload"))
        btn_reload.connect("clicked", self._shortcuts_on_reload_clicked)
        ctrl.append(btn_reload)

        box.append(ctrl)

        # Konflikt-Hinweis
        self.shortcuts_conflicts_label = Gtk.Label(label="")
        self.shortcuts_conflicts_label.set_xalign(0.0)
        box.append(self.shortcuts_conflicts_label)

        # List
        self.shortcuts_list = Gtk.ListBox()
        self.shortcuts_list.set_selection_mode(Gtk.SelectionMode.NONE)
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sc.set_min_content_height(300)
        sc.set_child(self.shortcuts_list)
        box.append(sc)

        # Ergebnis-Meldungen
        self.shortcuts_result = Gtk.Label(label="")
        self.shortcuts_result.set_wrap(True)
        self.shortcuts_result.set_xalign(0.0)
        box.append(self.shortcuts_result)

        # Initiales Laden
        try:
            self._shortcuts_reload()
        except Exception:
            pass

        # Help panel
        try:
            box.append(build_help_panel("shortcuts"))
        except Exception:
            pass

        return box

    def _page_settings(self) -> Gtk.Widget:
        # Settings page content (Inline-Edit)
        settings_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        settings_box.set_margin_start(16)
        settings_box.set_margin_end(16)
        settings_box.set_margin_top(16)
        settings_box.set_margin_bottom(16)

        settings_desc = Gtk.Label(label=_("Settings\n• Basic information and actions."))
        settings_desc.set_wrap(True)
        settings_desc.set_xalign(0.0)
        settings_box.append(settings_desc)

        # PATH-Hinweis: Wenn 'wbridge' nicht im PATH gefunden wird, funktionieren GNOME-Shortcuts evtl. nicht.
        self.path_hint = Gtk.Label(label="")
        self.path_hint.set_wrap(True)
        self.path_hint.set_xalign(0.0)
        try:
            if shutil.which("wbridge") is None:
                self.path_hint.set_text(_("Hint: 'wbridge' was not found in PATH. GNOME Shortcuts call 'wbridge'; install user-wide via pipx/pip --user or provide an absolute path in the shortcut command."))
        except Exception:
            pass
        settings_box.append(self.path_hint)

        # Basisinfos
        info_grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        row = 0

        # Backend/Display Info
        try:
            disp = Gdk.Display.get_default()
            disp_type = GObject.type_name(disp.__gtype__)
            lbl_backend_k = Gtk.Label(label=_("GDK Display:"))
            lbl_backend_k.set_xalign(0.0)
            lbl_backend_v = Gtk.Label(label=disp_type)
            lbl_backend_v.set_xalign(0.0)
            info_grid.attach(lbl_backend_k, 0, row, 1, 1)
            info_grid.attach(lbl_backend_v, 1, row, 1, 1)
            row += 1
        except Exception:
            pass

        # Socket Pfad
        lbl_sock_k = Gtk.Label(label=_("IPC Socket:"))
        lbl_sock_k.set_xalign(0.0)
        lbl_sock_v = Gtk.Label(label=str(socket_path()))
        lbl_sock_v.set_xalign(0.0)
        info_grid.attach(lbl_sock_k, 0, row, 1, 1)
        info_grid.attach(lbl_sock_v, 1, row, 1, 1)
        row += 1

        # Log Pfad
        lbl_log_k = Gtk.Label(label=_("Log file:"))
        lbl_log_k.set_xalign(0.0)
        lbl_log_v = Gtk.Label(label=str(xdg_state_dir() / "bridge.log"))
        lbl_log_v.set_xalign(0.0)
        info_grid.attach(lbl_log_k, 0, row, 1, 1)
        info_grid.attach(lbl_log_v, 1, row, 1, 1)
        row += 1

        settings_box.append(info_grid)

        # Integration Status
        integ_grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        lbl_integ_hdr = Gtk.Label(label=_("Integration status"))
        lbl_integ_hdr.set_xalign(0.0)
        settings_box.append(lbl_integ_hdr)

        lbl_enabled_k = Gtk.Label(label=_("http_trigger_enabled:"))
        lbl_enabled_k.set_xalign(0.0)
        self.integ_enabled_v = Gtk.Label(label="")
        self.integ_enabled_v.set_xalign(0.0)
        integ_grid.attach(lbl_enabled_k, 0, 0, 1, 1)
        integ_grid.attach(self.integ_enabled_v, 1, 0, 1, 1)

        lbl_base_k = Gtk.Label(label=_("Base URL:"))
        lbl_base_k.set_xalign(0.0)
        self.integ_base_v = Gtk.Label(label="")
        self.integ_base_v.set_xalign(0.0)
        integ_grid.attach(lbl_base_k, 0, 1, 1, 1)
        integ_grid.attach(self.integ_base_v, 1, 1, 1, 1)

        lbl_path_k = Gtk.Label(label=_("Trigger Path:"))
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
        try:
            self.integ_enabled_switch.set_tooltip_text("Enable or disable the HTTP trigger integration backend.")
        except Exception:
            pass
        row_sw.append(self.integ_enabled_switch)
        edit_box.append(row_sw)

        # Row: Base URL
        row_base = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_base = Gtk.Label(label="Base URL (http/https):")
        lbl_base.set_xalign(0.0)
        self.integ_base_entry = Gtk.Entry()
        self.integ_base_entry.set_hexpand(True)
        row_base.append(lbl_base)
        try:
            self.integ_base_entry.set_tooltip_text("Base URL of the HTTP trigger service (e.g., http://localhost:8808)")
        except Exception:
            pass
        row_base.append(self.integ_base_entry)
        edit_box.append(row_base)

        # Row: Trigger Path
        row_path = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_path = Gtk.Label(label="Trigger Path (/trigger):")
        lbl_path.set_xalign(0.0)
        self.integ_path_entry = Gtk.Entry()
        self.integ_path_entry.set_hexpand(True)
        row_path.append(lbl_path)
        try:
            self.integ_path_entry.set_tooltip_text("Trigger path (e.g., /trigger). Used with the Base URL to form the full endpoint.")
        except Exception:
            pass
        row_path.append(self.integ_path_entry)
        edit_box.append(row_path)

        # Buttons: Save / Discard / Reload Settings / Health check
        row_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_save = Gtk.Button(label=_("Save"))
        btn_save.connect("clicked", self._on_save_integration_clicked)
        row_btns.append(btn_save)

        btn_discard = Gtk.Button(label=_("Discard"))
        btn_discard.connect("clicked", self._on_discard_integration_clicked)
        row_btns.append(btn_discard)

        btn_reload = Gtk.Button(label=_("Reload Settings"))
        btn_reload.connect("clicked", self._on_reload_settings_clicked)
        row_btns.append(btn_reload)

        btn_health = Gtk.Button(label=_("Health check"))
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
        prof_hdr = Gtk.Label(label=_("Profile"))
        prof_hdr.set_xalign(0.0)
        settings_box.append(prof_hdr)

        prof_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_prof = Gtk.Label(label=_("Profile:"))
        lbl_prof.set_xalign(0.0)
        row1.append(lbl_prof)

        self.profile_combo = Gtk.ComboBoxText()
        try:
            names = list_builtin_profiles()
            if not names:
                self.profile_combo.append("none", _("(no profiles found)"))
                self.profile_combo.set_active_id("none")
            else:
                for n in names:
                    self.profile_combo.append(n, n)
                self.profile_combo.set_active(0)
        except Exception:
            self.profile_combo.append("err", _("(error loading)"))
            self.profile_combo.set_active_id("err")
        row1.append(self.profile_combo)

        btn_show = Gtk.Button(label=_("Show"))
        btn_show.connect("clicked", self._on_profile_show_clicked)
        row1.append(btn_show)

        prof_box.append(row1)

        # Installations-Optionen
        opts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_overwrite_actions = Gtk.CheckButton(label=_("Overwrite actions"))
        try:
            self.chk_overwrite_actions.set_tooltip_text("Overwrite existing actions in actions.json with the selected profile's definitions.")
        except Exception:
            pass
        self.chk_patch_settings = Gtk.CheckButton(label=_("Patch settings"))
        try:
            self.chk_patch_settings.set_tooltip_text("Patch settings.ini with profile values (non-destructive where possible).")
        except Exception:
            pass
        self.chk_install_shortcuts = Gtk.CheckButton(label=_("Install shortcuts"))
        try:
            self.chk_install_shortcuts.set_tooltip_text("Install GNOME custom keybindings in the wbridge scope (recommended).")
        except Exception:
            pass
        self.chk_dry_run = Gtk.CheckButton(label=_("Dry-run"))
        try:
            self.chk_dry_run.set_tooltip_text("Preview changes without writing files.")
        except Exception:
            pass
        opts.append(self.chk_overwrite_actions)
        opts.append(self.chk_patch_settings)
        opts.append(self.chk_install_shortcuts)
        opts.append(self.chk_dry_run)

        prof_box.append(opts)

        row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_install = Gtk.Button(label=_("Install"))
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
        btn_shortcuts_install = Gtk.Button(label=_("Install GNOME shortcuts"))
        btn_shortcuts_install.connect("clicked", self._on_install_shortcuts_clicked)
        btns.append(btn_shortcuts_install)

        btn_shortcuts_remove = Gtk.Button(label=_("Remove GNOME shortcuts"))
        btn_shortcuts_remove.connect("clicked", self._on_remove_shortcuts_clicked)
        btns.append(btn_shortcuts_remove)

        btn_autostart_enable = Gtk.Button(label=_("Enable autostart"))
        btn_autostart_enable.connect("clicked", self._on_enable_autostart_clicked)
        btns.append(btn_autostart_enable)

        btn_autostart_disable = Gtk.Button(label=_("Disable autostart"))
        btn_autostart_disable.connect("clicked", self._on_disable_autostart_clicked)
        btns.append(btn_autostart_disable)

        settings_box.append(btns)

        self.settings_result = Gtk.Label(label="")
        self.settings_result.set_wrap(True)
        self.settings_result.set_xalign(0.0)
        settings_box.append(self.settings_result)

        # Help panel
        try:
            settings_box.append(build_help_panel("settings"))
        except Exception:
            pass

        return settings_box

    def _page_status(self) -> Gtk.Widget:
        # Status page content
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

        help_label = Gtk.Label(label=_("Hint: The History page shows the entries. Buttons perform Apply/Swap. The CLI `wbridge history ...` is also available."))
        help_label.set_wrap(True)
        help_label.set_xalign(0.0)
        status_box.append(help_label)

        # Log Tail
        log_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        log_lbl = Gtk.Label(label=_("Log (tail 200):"))
        log_lbl.set_xalign(0.0)
        log_hdr.append(log_lbl)
        btn_log_refresh = Gtk.Button(label=_("Refresh"))
        btn_log_refresh.connect("clicked", self._on_log_refresh_clicked)
        log_hdr.append(btn_log_refresh)
        status_box.append(log_hdr)

        self.log_tv = Gtk.TextView()
        self.log_tv.set_monospace(True)
        self.log_tv.set_wrap_mode(Gtk.WrapMode.CHAR)
        self.log_tv.set_editable(False)
        self.log_tv.set_cursor_visible(False)
        log_sw = Gtk.ScrolledWindow()
        log_sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        log_sw.set_min_content_height(220)
        log_sw.set_child(self.log_tv)
        status_box.append(log_sw)

        # Initial load
        try:
            self._on_log_refresh_clicked(None)
        except Exception:
            pass

        # Help panel
        try:
            status_box.append(build_help_panel("status"))
        except Exception:
            pass

        return status_box

    # --- History UI helpers ---

    def _refresh_tick(self) -> bool:
        try:
            self.history_page.update_current_labels_async()
        except Exception:
            pass
        try:
            if getattr(self.history_page, "_hist_dirty", False):
                self.history_page.refresh()
                self.history_page._hist_dirty = False
        except Exception:
            pass
        return True  # weiterlaufen

    # --- Live-Update: Help mode (revealer/popover) ---

    def apply_help_mode(self, mode: str | None = None) -> None:
        """
        Rebuild the header+help widgets of all pages to reflect the given help mode.
        If mode is None, it is read from settings.ini [general].help_display_mode.
        """
        try:
            if mode is None:
                smap = self._get_settings_map()
                mode = str((smap.get("general", {}) or {}).get("help_display_mode", "revealer"))
            if mode not in ("revealer", "popover"):
                mode = "revealer"
        except Exception:
            mode = "revealer"

        return

        def _top_container_for(page: Gtk.Widget) -> Gtk.Widget:
            """
            Returns the container where header+help are placed as the first two children.
            For most pages this is the page itself; for Actions we wrapped content in a ScrolledWindow.
            """
            try:
                # Detect ScrolledWindow wrapper (as used in Actions page)
                first = page.get_first_child()
                if isinstance(first, Gtk.ScrolledWindow):
                    inner = first.get_child()
                    if isinstance(inner, Gtk.Widget):
                        return inner
            except Exception:
                pass
            return page

        def _rebuild(container: Gtk.Widget, topic: str, title: str, subtitle: str | None = None) -> None:
            try:
                # Build new help/header
                from .components.help_panel import build_help_panel  # local import to avoid cycles
                from .components.page_header import build_page_header
                new_help = build_help_panel(topic, mode=mode)  # type: ignore[arg-type]
                new_hdr = build_page_header(title, subtitle, new_help)

                # Remove first two children (old header + old help)
                # Caution: Gtk.Box API iteration
                if hasattr(container, "get_first_child") and hasattr(container, "remove"):
                    try:
                        c0 = container.get_first_child()
                        if c0 is not None:
                            container.remove(c0)
                        c1 = container.get_first_child()
                        if c1 is not None:
                            container.remove(c1)
                    except Exception:
                        pass
                    # Prepend in reverse order to keep header before help
                    try:
                        container.prepend(new_help)  # type: ignore[attr-defined]
                        container.prepend(new_hdr)   # type: ignore[attr-defined]
                    except Exception:
                        # Fallback: append (order header then help, may end up at bottom if prepend unsupported)
                        container.add_css_class  # type: ignore[attr-defined]  # no-op to keep linters calm
                        try:
                            container.insert_child_after(new_hdr, None)  # type: ignore[attr-defined]
                            container.insert_child_after(new_help, new_hdr)  # type: ignore[attr-defined]
                        except Exception:
                            pass
            except Exception:
                pass

        # Apply to all pages
        try:
            _rebuild(_top_container_for(self.history_page), "history", _("History"))
        except Exception:
            pass
        try:
            _rebuild(_top_container_for(self.actions_page), "actions", _("Actions"))
        except Exception:
            pass
        try:
            _rebuild(_top_container_for(self.triggers_page), "triggers", _("Triggers"))
        except Exception:
            pass
        try:
            _rebuild(_top_container_for(self.shortcuts_page), "shortcuts", _("Shortcuts"))
        except Exception:
            pass
        try:
            _rebuild(_top_container_for(self.settings_page), "settings", _("Settings"))
        except Exception:
            pass
        try:
            _rebuild(_top_container_for(self.status_page), "status", _("Status"))
        except Exception:
            pass

        # Nachlauf: kleines Re-Layout, damit der neue Help-Modus überall sicher greift.
        try:
            def _after_apply():
                try:
                    # Fenster und Root neu zeichnen
                    if hasattr(self, "queue_draw"):
                        self.queue_draw()
                    root = self.get_child()
                    if root and hasattr(root, "queue_draw"):
                        root.queue_draw()
                except Exception:
                    pass
                return False
            GLib.idle_add(_after_apply)  # type: ignore
        except Exception:
            pass

    def refresh_history(self, limit: int = 20) -> None:
        cb_items = self._history_list("clipboard", limit)
        pr_items = self._history_list("primary", limit)
        # Zähler aktualisieren (Clipboard / Primary)
        try:
            self.hist_count.set_text(_("Entries: {cb} / {pr}").format(cb=len(cb_items), pr=len(pr_items)))
        except Exception:
            pass

        # Aktualen Inhalt aus Cache (per Async-Read gepflegt)
        cb_sel = self._cur_clip or ""
        pr_sel = self._cur_primary or ""
        try:
            self.cb_label.set_text(_("Current: {val}").format(val=repr(cb_sel)) if cb_sel else _("Current: (empty)"))
            self.pr_label.set_text(_("Current: {val}").format(val=repr(pr_sel)) if pr_sel else _("Current: (empty)"))
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
        top_label.set_wrap(False)
        top_label.set_use_markup(True)
        try:
            top_label.set_ellipsize(Pango.EllipsizeMode.END)
        except Exception:
            pass
        top_label.set_hexpand(True)
        preview = text.strip().splitlines()[0] if text else ""
        # Markup sicher escapen
        try:
            esc = GLib.markup_escape_text(preview)
        except Exception:
            esc = preview
        mark_current = f"<b>{_('[current]')}</b> " if (current_text and text == current_text) else ""
        top_label.set_markup(f"{mark_current}[{idx}] {esc}")
        vbox.append(top_label)

        # Zeile 2: Buttons
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_clip = Gtk.Button(label=_("Set as Clipboard"))
        btn_clip.connect("clicked", lambda _b: self._apply_text("clipboard", text))
        btns.append(btn_clip)

        btn_prim = Gtk.Button(label=_("Set as Primary"))
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
                    self.pr_label.set_text(_("Current: {val}").format(val=repr(t)))
                else:
                    self.cb_label.set_text(_("Current: {val}").format(val=repr(t)))
            except Exception as e:
                if which == "primary":
                    self.pr_label.set_text(_("Read error: {err}").format(err=repr(e)))
                else:
                    self.cb_label.set_text(_("Read error: {err}").format(err=repr(e)))
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
                    self.cb_label.set_text(_("Current: {val}").format(val=repr(t)) if t else _("Current: (empty)"))
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
                    self.pr_label.set_text(_("Current: {val}").format(val=repr(t)) if t else _("Current: (empty)"))
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

    # --- Actions UI helpers (Master-Detail) ---

    def _build_action_list_row(self, action: dict) -> Gtk.ListBoxRow:
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
        row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label=name)
        title.set_xalign(0.0)
        title.set_wrap(False)
        try:
            title.set_ellipsize(Pango.EllipsizeMode.END)
        except Exception:
            pass
        subtitle = Gtk.Label(label=f"[{typ}] {preview}")
        subtitle.set_xalign(0.0)
        subtitle.set_wrap(False)
        try:
            subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        except Exception:
            pass
        try:
            subtitle.get_style_context().add_class("dim-label")
        except Exception:
            pass
        row_box.append(title)
        row_box.append(subtitle)
        row = Gtk.ListBoxRow()
        row.set_child(row_box)
        row._wbridge_action_name = name  # type: ignore[attr-defined]
        return row

    def _actions_load_list(self) -> list[dict]:
        app = self.get_application()
        cfg = getattr(app, "_actions", None)
        actions = getattr(cfg, "actions", []) if cfg else []
        if not isinstance(actions, list):
            return []
        return actions

    def _actions_find_by_name(self, name: Optional[str]) -> Optional[dict]:
        if not name:
            return None
        for a in self._actions_load_list():
            if str(a.get("name") or "") == name:
                return a
        return None

    def refresh_actions_list(self) -> None:
        # Determine if HTTP trigger is enabled
        enabled = True
        try:
            smap = self._get_settings_map()
            enabled = str(smap.get("integration", {}).get("http_trigger_enabled", "false")).lower() == "true"
        except Exception:
            enabled = True
        self._http_trigger_enabled = enabled

        # Update hint
        try:
            self.actions_hint.set_text("" if enabled else _("HTTP trigger disabled – enable it in Settings"))
        except Exception:
            pass

        prev = self._actions_selected_name
        self._clear_listbox(self.actions_list)
        actions = self._actions_load_list()
        for action in actions:
            row = self._build_action_list_row(action)
            self.actions_list.append(row)

        # Nach Laden: Auswahl wiederherstellen oder erste auswählen
        # Hinweis: row-selected callback bindet Editor
        def _select_initial():
            try:
                # Suche Row mit prev
                target_row = None
                child = self.actions_list.get_first_child()
                while child is not None:
                    if isinstance(child, Gtk.ListBoxRow):
                        name = getattr(child, "_wbridge_action_name", None)
                        if prev and name == prev:
                            target_row = child
                            break
                        if target_row is None:
                            target_row = child
                    child = child.get_next_sibling()
                if target_row is not None:
                    self.actions_list.select_row(target_row)  # type: ignore[arg-type]
                # Run-Button-Sensitivität
                self.btn_run.set_sensitive(bool(self._http_trigger_enabled and self._actions_selected_name))
            except Exception:
                pass
            return False
        GLib.idle_add(_select_initial)  # type: ignore

        # auch Triggers aktualisieren (Namen)
        try:
            self.triggers_page.rebuild_editor()
        except Exception:
            pass

    def _on_actions_row_selected(self, _lb: Gtk.ListBox, row: Optional[Gtk.ListBoxRow]) -> None:
        if row is None:
            return
        try:
            name = getattr(row, "_wbridge_action_name", None)
        except Exception:
            name = None
        if name:
            self._actions_select(name)

    def _actions_select(self, name: str) -> None:
        act = self._actions_find_by_name(name)
        if not act:
            return
        self._actions_selected_name = name
        self._actions_bind_form(act)
        # JSON Editor füllen
        import json as _json
        try:
            pretty = _json.dumps(act, ensure_ascii=False, indent=2)
        except Exception:
            pretty = str(act)
        buf = self._actions_json_tv.get_buffer()
        buf.set_text(pretty, -1)
        # Run-Button je nach Setting
        try:
            self.btn_run.set_sensitive(bool(self._http_trigger_enabled))
        except Exception:
            pass
        # Form anzeigen
        try:
            self._actions_detail_stack.set_visible_child_name("form")
        except Exception:
            pass

    def _actions_bind_form(self, action: dict) -> None:
        # Gemeinsame Felder
        self.ed_name_entry.set_text(str(action.get("name") or ""))
        typ = str(action.get("type") or "http").lower()
        if typ not in ("http", "shell"):
            typ = "http"
        self.ed_type_combo.set_active_id(typ)

        # HTTP
        self.ed_http_method.set_active_id(str(action.get("method", "GET")).upper() or "GET")
        self.ed_http_url.set_text(str(action.get("url", "") or ""))

        # SHELL
        self.ed_shell_cmd.set_text(str(action.get("command", "") or ""))
        try:
            import json as _json
            args_pretty = _json.dumps(action.get("args", []), ensure_ascii=False)
        except Exception:
            args_pretty = "[]"
        args_buf = self.ed_shell_args_tv.get_buffer()
        args_buf.set_text(args_pretty, -1)
        self.ed_shell_use_switch.set_active(bool(action.get("use_shell", False)))

        # Sichtbarkeit
        self._actions_update_type_visibility()

    def _actions_update_type_visibility(self) -> None:
        t = self.ed_type_combo.get_active_id() or "http"
        self.http_box.set_visible(t == "http")
        self.shell_box.set_visible(t == "shell")

    def _actions_on_type_changed(self, _combo: Gtk.ComboBoxText) -> None:
        self._actions_update_type_visibility()

    def _on_actions_source_changed(self, _combo: Gtk.ComboBoxText) -> None:
        active_id = self.actions_source.get_active_id() or "clipboard"
        self.actions_text.set_sensitive(active_id == "text")
        # kein vollständiger Reload nötig

    def _get_settings_map(self) -> dict:
        app = self.get_application()
        settings = getattr(app, "_settings", None)
        try:
            return settings.as_mapping() if settings else {}
        except Exception:
            return {}

    def _on_action_run_current_clicked(self, _btn: Gtk.Button) -> None:
        act = self._actions_find_by_name(self._actions_selected_name)
        if not act:
            self.actions_result.set_text(_("No action selected."))
            return
        # Verwende existierende Runner-Logik
        self._on_action_run_clicked(_btn, act, None, None)

    def _on_action_run_clicked(self, _btn: Gtk.Button, action: dict, override_combo: Optional[Gtk.ComboBoxText] = None, override_entry: Optional[Gtk.Entry] = None) -> None:
        # Determine source and text (global oder override – hier i.d.R. global)
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

    # --- Actions: Speichern/Duplicate/Delete (Master-Detail) ---

    def _get_textview_text(self, tv: Gtk.TextView) -> str:
        buf = tv.get_buffer()
        start = buf.get_start_iter()
        end = buf.get_end_iter()
        return buf.get_text(start, end, True)

    def _on_actions_save_form_clicked(self, _btn: Gtk.Button) -> None:
        try:
            original_name = self._actions_selected_name or ""
            if not original_name:
                self.actions_result.set_text(_("Save (Form) failed: no action selected"))
                return
            payload = load_actions_raw()
            actions = payload.get("actions", [])
            # finde Original
            src = None
            for a in actions:
                if str(a.get("name") or "") == original_name:
                    src = a
                    break
            if src is None:
                self.actions_result.set_text(_("Save (Form) failed: original action not found"))
                return

            # baue neues Objekt
            new_name = self.ed_name_entry.get_text().strip()
            typ = (self.ed_type_combo.get_active_id() or "http").lower()
            if not new_name:
                self.actions_result.set_text(_("Validation failed: action.name must not be empty"))
                return
            obj = dict(src)  # optional Felder erhalten
            obj["name"] = new_name
            obj["type"] = typ
            if typ == "http":
                obj["method"] = (self.ed_http_method.get_active_id() or "GET").upper()
                obj["url"] = (self.ed_http_url.get_text() or "").strip()
            else:
                obj["command"] = (self.ed_shell_cmd.get_text() or "").strip()
                import json as _json
                args_text = self._get_textview_text(self.ed_shell_args_tv).strip()
                try:
                    parsed_args = _json.loads(args_text) if args_text else []
                    if not isinstance(parsed_args, list):
                        raise ValueError("args must be a JSON array")
                except Exception as e:
                    self.actions_result.set_text(f"Validation failed (args): {e}")
                    return
                obj["args"] = parsed_args
                obj["use_shell"] = bool(self.ed_shell_use_switch.get_active())

            ok, err = validate_action_dict(obj)
            if not ok:
                self.actions_result.set_text(f"Validation failed: {err}")
                return

            # ersetze oder hänge an
            replaced = False
            for i, a in enumerate(actions):
                if str(a.get("name") or "") == original_name:
                    actions[i] = obj
                    replaced = True
                    break
            if not replaced:
                actions.append(obj)
            payload["actions"] = actions
            backup = write_actions_config(payload)

            # reload und UI aktualisieren
            app = self.get_application()
            try:
                new_cfg = load_actions()
                setattr(app, "_actions", new_cfg)
            except Exception:
                pass
            self._actions_selected_name = new_name
            self.refresh_actions_list()
            self.actions_result.set_text(f"Action saved (form) (backup: {backup})")
        except Exception as e:
            self.actions_result.set_text(f"Save (Form) failed: {e!r}")

    def _on_actions_save_json_clicked(self, _btn: Gtk.Button) -> None:
        try:
            import json as _json
            original_name = self._actions_selected_name or ""
            raw_text = self._get_textview_text(self._actions_json_tv)
            obj = _json.loads(raw_text)
            if not isinstance(obj, dict):
                raise ValueError("editor content must be a JSON object")
            ok, err = validate_action_dict(obj)
            if not ok:
                self.actions_result.set_text(f"Validation failed: {err}")
                return

            payload = load_actions_raw()
            actions = payload.get("actions", [])

            new_name = str(obj.get("name") or "").strip()
            if not new_name:
                self.actions_result.set_text(_("Validation failed: action.name must not be empty"))
                return

            replaced = False
            for i, a in enumerate(actions):
                if str(a.get("name") or "") == original_name:
                    actions[i] = obj
                    replaced = True
                    break
            if not replaced:
                actions.append(obj)

            payload["actions"] = actions
            backup = write_actions_config(payload)

            # reload und UI aktualisieren
            app = self.get_application()
            try:
                new_cfg = load_actions()
                setattr(app, "_actions", new_cfg)
            except Exception:
                pass
            self._actions_selected_name = new_name
            self.refresh_actions_list()
            self.actions_result.set_text(f"Action saved (JSON) (backup: {backup})")
        except Exception as e:
            self.actions_result.set_text(f"Save failed: {e!r}")

    def _on_action_cancel_clicked(self, _btn: Gtk.Button) -> None:
        # Reload actions from disk and re-bind selection
        try:
            app = self.get_application()
            new_cfg = load_actions()
            setattr(app, "_actions", new_cfg)
        except Exception:
            pass
        self.refresh_actions_list()

    def _on_action_duplicate_current_clicked(self, _btn: Gtk.Button) -> None:
        try:
            original_name = self._actions_selected_name or ""
            payload = load_actions_raw()
            actions = payload.get("actions", [])
            src = next((a for a in actions if str(a.get("name") or "") == original_name), None)
            if not src:
                self.actions_result.set_text(_("Duplicate failed: source action not found"))
                return
            import copy as _copy
            dup = _copy.deepcopy(src)
            base = str(src.get("name") or "Action")
            new_name = base + " (copy)"
            names = {str(a.get("name") or "") for a in actions}
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
            self._actions_selected_name = new_name
            self.refresh_actions_list()
            try:
                self._logger.info("actions.duplicate ok source=%s new=%s", original_name, new_name)
            except Exception:
                pass
            self.actions_result.set_text(f"Action duplicated as '{new_name}' (backup: {backup})")
        except Exception as e:
            self.actions_result.set_text(f"Duplicate failed: {e!r}")

    def _on_action_delete_current_clicked(self, _btn: Gtk.Button) -> None:
        try:
            name = self._actions_selected_name or ""
            if not name:
                self.actions_result.set_text(_("Delete: no action selected"))
                return
            payload = load_actions_raw()
            actions = payload.get("actions", [])
            before = len(actions)
            actions = [a for a in actions if str(a.get("name") or "") != name]
            if len(actions) == before:
                self.actions_result.set_text(_("Delete: action not found"))
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
            self._actions_selected_name = None
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
            self._actions_selected_name = name
            self.refresh_actions_list()
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
        box.append(Gtk.Label(label=_("Alias:")))
        box.append(alias_entry)

        box.append(Gtk.Label(label=_("Action:")))
        action_combo = Gtk.ComboBoxText()
        for n in action_names:
            action_combo.append(n, n)
        # select current
        if target in action_names:
            action_combo.set_active_id(target)
        elif action_names:
            action_combo.set_active(0)
        box.append(action_combo)

        del_btn = Gtk.Button(label=_("Delete"))
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
                            self.actions_result.set_text(_("Save Triggers failed: alias must not be empty"))
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
            self.actions_page.refresh_actions_list()
            self._rebuild_triggers_editor()
            try:
                self._logger.info("triggers.save ok count=%d", len(new_triggers))
            except Exception:
                pass
            self.actions_result.set_text(f"Triggers saved (backup: {backup})")
        except Exception as e:
            self.actions_result.set_text(f"Save Triggers failed: {e!r}")

    # --- Shortcuts Editor helpers ---

    def _shortcuts_on_reload_clicked(self, _btn: Gtk.Button) -> None:
        try:
            self._shortcuts_reload()
            self.shortcuts_result.set_text(_("Reloaded shortcuts."))
        except Exception as e:
            self.shortcuts_result.set_text(f"Reload failed: {e!r}")

    def _shortcuts_on_add_clicked(self, _btn: Gtk.Button) -> None:
        try:
            # Erzeuge leere editierbare Row (wbridge-managed, noch nicht installiert)
            item = {
                "full_path": None,
                "suffix": None,
                "is_managed": True,
                "name": "New Shortcut",
                "command": "",
                "binding": ""
            }
            row = self._shortcuts_build_row(item)
            self.shortcuts_list.append(row)
            # Fokus auf Name
            try:
                getattr(row, "_wbridge_name_entry").grab_focus()  # type: ignore[attr-defined]
            except Exception:
                pass
            self.shortcuts_result.set_text(_("New shortcut row added (not yet saved)."))
        except Exception as e:
            self.shortcuts_result.set_text(f"Add failed: {e!r}")

    def _shortcuts_on_row_delete_clicked(self, _btn: Gtk.Button, row: Gtk.ListBoxRow) -> None:
        try:
            is_managed = bool(getattr(row, "_wbridge_is_managed", False))
            if not is_managed:
                self.shortcuts_result.set_text(_("Delete not allowed for non-wbridge entries."))
                return
            suffix = getattr(row, "_wbridge_suffix", None)
            if suffix:
                try:
                    gnome_shortcuts.remove_binding(suffix)
                except Exception as e:
                    self.shortcuts_result.set_text(f"Remove failed: {e!r}")
                    # continue to remove row visually
            # Entferne Row aus der Liste
            self.shortcuts_list.remove(row)
            # Option: direkt reloaden, um Basis-Array neu einzulesen
            self._shortcuts_reload()
            self.shortcuts_result.set_text(_("Shortcut removed."))
        except Exception as e:
            self.shortcuts_result.set_text(f"Delete failed: {e!r}")

    def _shortcuts_on_save_clicked(self, _btn: Gtk.Button) -> None:
        try:
            # Sammle existierende Suffixe aus dem System, um Kollisionen zu vermeiden
            current = self._shortcuts_read_items(include_foreign=True)
            existing_suffixes: set[str] = {str(it.get("suffix")) for it in current if isinstance(it.get("suffix"), str)}
            changed = 0

            # Validierung und Anwendung
            child = self.shortcuts_list.get_first_child()
            while child is not None:
                if isinstance(child, Gtk.ListBoxRow):
                    is_managed = bool(getattr(child, "_wbridge_is_managed", False))
                    if is_managed:
                        name_e = getattr(child, "_wbridge_name_entry", None)
                        cmd_e = getattr(child, "_wbridge_cmd_entry", None)
                        bind_e = getattr(child, "_wbridge_bind_entry", None)
                        old_suffix = getattr(child, "_wbridge_suffix", None)

                        name = (name_e.get_text() if name_e else "").strip()
                        cmd = (cmd_e.get_text() if cmd_e else "").strip()
                        bind = (bind_e.get_text() if bind_e else "").strip()

                        if not name:
                            self.shortcuts_result.set_text(_("Validation failed: name must not be empty"))
                            return
                        if not cmd:
                            self.shortcuts_result.set_text(_("Validation failed: command must not be empty"))
                            return
                        if not bind:
                            self.shortcuts_result.set_text(_("Validation failed: binding must not be empty"))
                            return

                        desired_suffix = self._shortcuts_compute_suffix(name, existing_suffixes, prefer=old_suffix)
                        # Wenn sich der Suffix ändert, altes Binding entfernen
                        if old_suffix and desired_suffix != old_suffix:
                            try:
                                gnome_shortcuts.remove_binding(old_suffix)
                            except Exception:
                                pass
                            existing_suffixes.discard(old_suffix)

                        # Install/Update
                        gnome_shortcuts.install_binding(desired_suffix, name, cmd, bind)
                        setattr(child, "_wbridge_suffix", desired_suffix)
                        existing_suffixes.add(desired_suffix)
                        changed += 1
                child = child.get_next_sibling()

            # Nach dem Speichern neu laden + Konflikte prüfen
            self._shortcuts_reload()
            self.shortcuts_result.set_text(f"Saved shortcuts: {changed}")
        except Exception as e:
            self.shortcuts_result.set_text(f"Save failed: {e!r}")

    def _shortcuts_compute_suffix(self, name: str, existing_suffixes: set[str], prefer: Optional[str] = None) -> str:
        # Bestimme deterministischen Suffix aus Name; halte prefer, falls noch passend
        import re
        norm = re.sub(r"[^a-z0-9\\-]+", "-", name.lower()).strip("-")
        base = f"wbridge-{norm or 'unnamed'}"
        suffix = base + "/"
        if prefer and prefer.startswith("wbridge-") and prefer.endswith("/") and prefer not in existing_suffixes:
            return prefer
        if suffix not in existing_suffixes:
            return suffix
        i = 2
        while True:
            cand = f"{base}-{i}/"
            if cand not in existing_suffixes:
                return cand
            i += 1

    def _shortcuts_read_items(self, include_foreign: bool) -> list[dict]:
        # Lesen aller Custom-Keybindings
        items: list[dict] = []
        try:
            base = Gio.Settings.new(gnome_shortcuts.BASE_SCHEMA)  # type: ignore
            paths = list(base.get_strv(gnome_shortcuts.BASE_KEY))  # type: ignore
        except Exception:
            return items

        for p in paths:
            try:
                full_path = str(p)
                if not full_path.startswith(gnome_shortcuts.PATH_PREFIX):
                    continue
                suffix = full_path[len(gnome_shortcuts.PATH_PREFIX):]
                is_managed = suffix.startswith("wbridge-")
                if not include_foreign and not is_managed:
                    continue
                custom = Gio.Settings.new_with_path(gnome_shortcuts.CUSTOM_SCHEMA, full_path)  # type: ignore
                name = str(custom.get_string("name") or "")
                cmd = str(custom.get_string("command") or "")
                bind = str(custom.get_string("binding") or "")
                items.append({
                    "full_path": full_path,
                    "suffix": suffix,
                    "is_managed": is_managed,
                    "name": name,
                    "command": cmd,
                    "binding": bind
                })
            except Exception:
                continue
        return items

    def _shortcuts_build_row(self, item: dict) -> Gtk.ListBoxRow:
        is_managed = bool(item.get("is_managed"))
        name = str(item.get("name") or "")
        cmd = str(item.get("command") or "")
        bind = str(item.get("binding") or "")
        suffix = item.get("suffix") or None

        grid = Gtk.Grid(column_spacing=8, row_spacing=4)
        c = 0

        lbl_name = Gtk.Label(label=_("Name:"))
        lbl_name.set_xalign(1.0)
        grid.attach(lbl_name, c, 0, 1, 1); c += 1
        name_e = Gtk.Entry()
        name_e.set_text(name)
        name_e.set_hexpand(True)
        name_e.set_sensitive(is_managed)
        grid.attach(name_e, c, 0, 1, 1); c += 1

        lbl_cmd = Gtk.Label(label=_("Command:"))
        lbl_cmd.set_xalign(1.0)
        grid.attach(lbl_cmd, 0, 1, 1, 1)
        cmd_e = Gtk.Entry()
        cmd_e.set_text(cmd)
        cmd_e.set_hexpand(True)
        cmd_e.set_sensitive(is_managed)
        grid.attach(cmd_e, 1, 1, 1, 1)

        lbl_bind = Gtk.Label(label=_("Binding:"))
        lbl_bind.set_xalign(1.0)
        grid.attach(lbl_bind, 0, 2, 1, 1)
        bind_e = Gtk.Entry()
        bind_e.set_text(bind)
        bind_e.set_hexpand(True)
        bind_e.set_sensitive(is_managed)
        grid.attach(bind_e, 1, 2, 1, 1)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        if is_managed:
            del_btn = Gtk.Button(label=_("Delete"))
            row_ref = None
            # row wird erst nachher erzeugt; Callback nutzt closure, daher setzen wir später
            btn_box.append(del_btn)
        grid.attach(btn_box, 1, 3, 1, 1)

        row = Gtk.ListBoxRow()
        row.set_child(grid)

        # Row-Metadaten
        row._wbridge_is_managed = is_managed  # type: ignore[attr-defined]
        row._wbridge_suffix = suffix  # type: ignore[attr-defined]
        row._wbridge_name_entry = name_e  # type: ignore[attr-defined]
        row._wbridge_cmd_entry = cmd_e  # type: ignore[attr-defined]
        row._wbridge_bind_entry = bind_e  # type: ignore[attr-defined]

        # Delete-Handler jetzt mit Row-Ref
        if is_managed:
            def _on_del(_b):
                self._shortcuts_on_row_delete_clicked(_b, row)
            del_btn.connect("clicked", _on_del)  # type: ignore[name-defined]

        return row

    def _shortcuts_reload(self) -> None:
        # Liste neu aufbauen und Konflikte anzeigen
        include_foreign = bool(self.shortcuts_show_all.get_active()) if hasattr(self, "shortcuts_show_all") else False
        items = self._shortcuts_read_items(include_foreign=include_foreign)

        # Clear
        child = self.shortcuts_list.get_first_child()
        while child is not None:
            self.shortcuts_list.remove(child)
            child = self.shortcuts_list.get_first_child()

        # Build rows
        for it in items:
            self.shortcuts_list.append(self._shortcuts_build_row(it))

        # Konflikte prüfen
        conflicts: dict[str, int] = {}
        for it in items:
            b = str(it.get("binding") or "")
            if not b:
                continue
            conflicts[b] = conflicts.get(b, 0) + 1
        msgs = []
        for k, cnt in conflicts.items():
            if cnt > 1:
                msgs.append(f"'{k}' ×{cnt}")
        self.shortcuts_conflicts_label.set_text((_('Conflicts: ') + ", ".join(msgs)) if msgs else "")

    # --- Status helpers: Log tail ---

    def _log_tail(self, max_lines: int = 200) -> list[str]:
        try:
            path = xdg_state_dir() / "bridge.log"
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            return lines[-max_lines:]
        except Exception:
            return []

    def _on_log_refresh_clicked(self, _btn: Optional[Gtk.Button]) -> None:
        try:
            buf = self.log_tv.get_buffer()  # type: ignore[attr-defined]
            text = "".join(self._log_tail(200))
            buf.set_text(text, -1)
        except Exception:
            pass

    # --- File monitors (Auto-Reload for settings.ini and actions.json) ---

    def _init_file_monitors(self) -> None:
        try:
            cfg = xdg_config_dir()
            self._settings_monitor = None
            self._actions_monitor = None
            self._settings_debounce_id = 0
            self._actions_debounce_id = 0

            # settings.ini monitor
            try:
                sfile = Gio.File.new_for_path(str(cfg / "settings.ini"))
                self._settings_monitor = sfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
                def _on_s_changed(_mon, *_args):
                    if getattr(self, "_settings_debounce_id", 0):
                        return
                    def _reload():
                        try:
                            self.settings_page.reload_settings()
                        except Exception:
                            pass
                        self._settings_debounce_id = 0
                        return False
                    self._settings_debounce_id = GLib.timeout_add(200, _reload)  # type: ignore[arg-type]
                self._settings_monitor.connect("changed", _on_s_changed)
            except Exception:
                pass

            # actions.json monitor
            try:
                afile = Gio.File.new_for_path(str(cfg / "actions.json"))
                self._actions_monitor = afile.monitor_file(Gio.FileMonitorFlags.NONE, None)
                def _on_a_changed(_mon, *_args):
                    if getattr(self, "_actions_debounce_id", 0):
                        return
                    def _reload():
                        try:
                            app = self.get_application()
                            new_cfg = load_actions()
                            setattr(app, "_actions", new_cfg)
                            try:
                                self.actions_page.refresh_actions_list()
                                self.actions_page.notify_config_reloaded()
                            except Exception:
                                pass
                            self.triggers_page.rebuild_editor()
                        except Exception:
                            pass
                        self._actions_debounce_id = 0
                        return False
                    self._actions_debounce_id = GLib.timeout_add(200, _reload)  # type: ignore[arg-type]
                self._actions_monitor.connect("changed", _on_a_changed)
            except Exception:
                pass
        except Exception:
            pass

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
        self.actions_page.refresh_actions_list()
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
        # Legacy integration removed in V2. Settings live in Endpoints editor.
        try:
            self.settings_result.set_text(_("Legacy HTTP integration is no longer supported. Use Settings → Endpoints."))
        except Exception:
            pass

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
            self.profile_result.set_text(_("No profile selected."))
        if not pid or pid in ("none", "err"):
            self.profile_result.set_text(_("No profile selected."))
            return
        try:
            info = pm_show_profile(pid)
            # kompakte Darstellung
            meta = info.get("meta", {})
            acts = info.get("actions", {})
            sc = info.get("shortcuts", {})
            summary = (
                _("Profile: {name} v{version}").format(name=meta.get("name", pid), version=meta.get("version","")) + "\n"
                + _("Actions: {count} (Triggers: {trigs})").format(count=acts.get("count",0), trigs=", ".join(acts.get("triggers", [])[:8])) + "\n"
                + _("Shortcuts: {count}").format(count=sc.get("count",0))
            )
            self.profile_result.set_text(summary)
        except Exception as e:
            self.profile_result.set_text(_("Error: {err}").format(err=repr(e)))

    def _on_profile_install_clicked(self, _btn: Gtk.Button) -> None:
        pid = self.profile_combo.get_active_id()
        if not pid or pid in ("none", "err"):
            self.profile_result.set_text(_("No profile selected."))
            return
        try:
            report = pm_install_profile(
                pid,
                overwrite_actions=bool(self.chk_overwrite_actions.get_active()),
                merge_endpoints=bool(self.chk_patch_settings.get_active()),
                merge_secrets=bool(self.chk_patch_settings.get_active()),
                merge_shortcuts=bool(self.chk_install_shortcuts.get_active()),
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
                f"- settings: merged={len(sets.get('merged',[]))} skipped={len(sets.get('skipped',[]))}\n"
                f"- shortcuts: merged={sc.get('merged',0)} skipped={sc.get('skipped',0)}\n"
                f"- errors: {len(errors)}"
            )
            self.profile_result.set_text(txt)
            # Refresh settings and actions after install (in case settings changed)
            self._reload_settings()
        except Exception as e:
            self.profile_result.set_text(_("Error: {err}").format(err=repr(e)))

    def _on_install_shortcuts_clicked(self, _btn: Gtk.Button) -> None:
        # Install GNOME shortcuts with priority:
        # 1) settings.ini [gnome] bindings -> recommended set
        # 2) if profile selected and has shortcuts.json -> install profile shortcuts
        # 3) fallback: default recommended bindings
        try:
            # 1) try settings.ini [gnome]
            smap = self._get_settings_map()
            gsec = smap.get("gnome", {}) if isinstance(smap, dict) else {}
            b_prompt = gsec.get("binding_prompt")
            b_command = gsec.get("binding_command")
            b_ui = gsec.get("binding_ui_show")
            if b_prompt or b_command or b_ui:
                bindings = {}
                if b_prompt: bindings["prompt"] = b_prompt
                if b_command: bindings["command"] = b_command
                if b_ui: bindings["ui_show"] = b_ui
                gnome_shortcuts.install_recommended_shortcuts(bindings)
                self.settings_result.set_text(_("GNOME shortcuts installed (settings.ini takes priority)."))
                return

            # 2) fallback to profile shortcuts if a profile is selected
            pid = self.profile_combo.get_active_id() if hasattr(self, "profile_combo") else None
            if pid and pid not in ("none", "err", None):
                items = load_profile_shortcuts(pid)
                if items:
                    installed = skipped = 0
                    import re
                    for sc in items:
                        try:
                            name = str(sc.get("name") or "")
                            cmd = str(sc.get("command") or "")
                            binding = str(sc.get("binding") or "")
                            if not name or not cmd or not binding:
                                skipped += 1
                                continue
                            norm = re.sub(r"[^a-z0-9\-]+", "-", name.lower()).strip("-")
                            suffix = f"wbridge-{norm}/"
                            gnome_shortcuts.install_binding(suffix, name, cmd, binding)
                            installed += 1
                        except Exception:
                            skipped += 1
                    self.settings_result.set_text(_("Profile shortcuts installed: installed={installed}, skipped={skipped}.").format(installed=installed, skipped=skipped))
                    return

            # 3) default recommended bindings
            defaults = {
                "prompt": "<Ctrl><Alt>p",
                "command": "<Ctrl><Alt>m",
                "ui_show": "<Ctrl><Alt>u",
            }
            gnome_shortcuts.install_recommended_shortcuts(defaults)
            self.settings_result.set_text(_("GNOME shortcuts installed (default recommendations)."))
        except Exception as e:
            self.settings_result.set_text(_("Installing GNOME shortcuts failed: {err}").format(err=repr(e)))

    def _on_remove_shortcuts_clicked(self, _btn: Gtk.Button) -> None:
        # Remove recommended shortcuts and, if a profile is selected, try to remove its shortcuts as well.
        try:
            gnome_shortcuts.remove_recommended_shortcuts()
            msg = _("Recommended GNOME shortcuts removed.")
            pid = self.profile_combo.get_active_id() if hasattr(self, "profile_combo") else None
            if pid and pid not in ("none", "err", None):
                rep = remove_profile_shortcuts(pid)
                msg += _(" Profile shortcuts removed: removed={removed}, skipped={skipped}.").format(removed=rep.get('removed',0), skipped=rep.get('skipped',0))
            self.settings_result.set_text(msg)
        except Exception as e:
            self.settings_result.set_text(_("Removing GNOME shortcuts failed: {err}").format(err=repr(e)))

    def _on_enable_autostart_clicked(self, _btn: Gtk.Button) -> None:
        try:
            from .. import autostart
            ok = autostart.enable()
            self.settings_result.set_text(_("Autostart enabled.") if ok else _("Autostart could not be enabled."))
        except Exception as e:
            self.settings_result.set_text(_("Enabling autostart failed: {err}").format(err=repr(e)))

    def _on_disable_autostart_clicked(self, _btn: Gtk.Button) -> None:
        try:
            from .. import autostart
            ok = autostart.disable()
            self.settings_result.set_text(_("Autostart disabled.") if ok else _("Autostart could not be disabled."))
        except Exception as e:
            self.settings_result.set_text(_("Disabling autostart failed: {err}").format(err=repr(e)))

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
                self.cb_label.set_text(_("Read error: {err}").format(err=repr(e)))
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
                self.pr_label.set_text(_("Read error: {err}").format(err=repr(e)))
            return False

        prim.read_text_async(None, on_finish)

    # --- CSS helper ---

    def _load_css(self) -> None:
        try:
            provider = Gtk.CssProvider()
            # ui/main_window.py -> parents[2] == src/wbridge
            css_path = Path(__file__).resolve().parents[2] / "assets" / "style.css"
            if css_path.exists():
                provider.load_from_path(str(css_path))
                display = Gdk.Display.get_default()
                Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception:
            pass
