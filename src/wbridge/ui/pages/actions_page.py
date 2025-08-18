"""Actions page for wbridge (extracted from gui_window.py).

Provides:
- Actions master/detail UI (list on left, editor on right with Form/JSON)
- Run action with source selection (clipboard/primary/text)
- Save (Form / JSON), Duplicate, Delete, Reload, Add
- Hint if HTTP trigger is disabled
- Help panel

Selection text resolution uses HistoryPage (clipboard/primary) or local text entry.
Settings map is read from the Gtk.Application (app._settings.as_mapping()).
"""

from __future__ import annotations

from typing import Optional

import logging
import gettext

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, GLib  # type: ignore
from gi.repository import Pango  # type: ignore

from ...actions import run_action, ActionContext  # type: ignore
from ...config import (  # type: ignore
    load_actions,
    load_actions_raw,
    write_actions_config,
    validate_action_dict,
)
from ..components.help_panel import build_help_panel
from .history_page import HistoryPage


# i18n init (fallback to identity if no translations installed)
try:
    _t = gettext.translation("wbridge", localedir=None, fallback=True)
    _ = _t.gettext
except Exception:
    _ = lambda s: s


class ActionsPage(Gtk.Box):
    """Actions page container (master/detail)."""

    def __init__(self, main_window: Gtk.ApplicationWindow, history_page: HistoryPage):
        """Initialize the page with a reference to MainWindow and HistoryPage."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._main = main_window  # reference to MainWindow for app access
        self._history_page = history_page  # used to get current selection text
        self._logger = logging.getLogger("wbridge")

        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        # Internal state
        self._actions_selected_name: Optional[str] = None
        self._http_trigger_enabled: bool = True

        # Header/Description
        actions_desc = Gtk.Label(label=_("Actions\n"
                                         "• Defined actions (HTTP/Shell) loaded from ~/.config/wbridge/actions.json.\n"
                                         "• Choose source: Clipboard / Primary / Text."))
        actions_desc.set_wrap(True)
        actions_desc.set_xalign(0.0)
        self.append(actions_desc)

        # Controls row: source selection + optional text + reload/add
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

        self.append(controls)

        # Hint if HTTP trigger disabled
        self.actions_hint = Gtk.Label(label="")
        self.actions_hint.set_wrap(True)
        self.actions_hint.set_xalign(0.0)
        self.append(self.actions_hint)

        # Master/Detail split
        md = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        md.set_hexpand(True)
        md.set_vexpand(True)

        # Left: list of actions
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

        # Right: editor area with stack (Form/JSON)
        right_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right_box.set_hexpand(True)
        right_box.set_vexpand(True)

        self._actions_detail_stack = Gtk.Stack()
        self._actions_detail_stack.set_hexpand(True)
        self._actions_detail_stack.set_vexpand(True)

        switcher = Gtk.StackSwitcher()
        switcher.set_stack(self._actions_detail_stack)
        right_box.append(switcher)

        # Form view
        form_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        # Common fields
        row_name = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_name = Gtk.Label(label=_("Name:"))
        lbl_name.set_xalign(0.0)
        self.ed_name_entry = Gtk.Entry()
        self.ed_name_entry.set_hexpand(True)
        row_name.append(lbl_name)
        row_name.append(self.ed_name_entry)
        form_box.append(row_name)

        row_type = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_type = Gtk.Label(label=_("Type:"))
        lbl_type.set_xalign(0.0)
        self.ed_type_combo = Gtk.ComboBoxText()
        self.ed_type_combo.append("http", "http")
        self.ed_type_combo.append("shell", "shell")
        self.ed_type_combo.set_active_id("http")
        self.ed_type_combo.connect("changed", self._actions_on_type_changed)
        row_type.append(lbl_type)
        row_type.append(self.ed_type_combo)
        form_box.append(row_type)

        # HTTP fields
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
        http_row1.append(http_method_lbl)
        http_row1.append(self.ed_http_method)
        http_row1.append(http_url_lbl)
        http_row1.append(self.ed_http_url)
        self.http_box.append(http_row1)
        form_box.append(self.http_box)

        # SHELL fields
        self.shell_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        sh_row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sh_cmd_lbl = Gtk.Label(label=_("Command:"))
        sh_cmd_lbl.set_xalign(0.0)
        self.ed_shell_cmd = Gtk.Entry()
        self.ed_shell_cmd.set_hexpand(True)
        sh_row1.append(sh_cmd_lbl)
        sh_row1.append(self.ed_shell_cmd)
        self.shell_box.append(sh_row1)

        sh_row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sh_args_lbl = Gtk.Label(label=_("Args (JSON array):"))
        sh_args_lbl.set_xalign(0.0)
        self.ed_shell_args_tv = Gtk.TextView()
        self.ed_shell_args_tv.set_monospace(True)
        sh_args_sw = Gtk.ScrolledWindow()
        sh_args_sw.set_min_content_height(40)
        sh_args_sw.set_child(self.ed_shell_args_tv)
        sh_row2.append(sh_args_lbl)
        sh_row2.append(sh_args_sw)
        self.shell_box.append(sh_row2)

        sh_row3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        sh_use_lbl = Gtk.Label(label=_("Use shell:"))
        sh_use_lbl.set_xalign(0.0)
        self.ed_shell_use_switch = Gtk.Switch()
        sh_row3.append(sh_use_lbl)
        sh_row3.append(self.ed_shell_use_switch)
        self.shell_box.append(sh_row3)

        form_box.append(self.shell_box)

        # Form buttons
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
        md.append(right_box)
        self.append(md)

        # Result output
        self.actions_result = Gtk.Label(label="")
        self.actions_result.set_wrap(True)
        self.actions_result.set_xalign(0.0)
        self.append(self.actions_result)

        # Initial visibility of http/shell fields
        self._actions_update_type_visibility()

        # Help panel
        try:
            self.append(build_help_panel("actions"))
        except Exception:
            pass

    # --- Public helpers -----------------------------------------------------

    def notify_config_reloaded(self) -> None:
        """Set a user-visible message when actions.json was reloaded."""
        try:
            self.actions_result.set_text(_("Config reloaded from disk (actions.json)."))
        except Exception:
            pass

    # --- Core actions logic (ported) ----------------------------------------

    def _build_action_list_row(self, action: dict) -> Gtk.ListBoxRow:
        name = str(action.get("name") or "(unnamed)")
        typ = str(action.get("type") or "").lower()
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
        app = self._main.get_application()
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

        def _select_initial():
            try:
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
                self.btn_run.set_sensitive(bool(self._http_trigger_enabled and self._actions_selected_name))
            except Exception:
                pass
            return False

        GLib.idle_add(_select_initial)  # type: ignore

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
        import json as _json
        try:
            pretty = _json.dumps(act, ensure_ascii=False, indent=2)
        except Exception:
            pretty = str(act)
        buf = self._actions_json_tv.get_buffer()
        buf.set_text(pretty, -1)
        try:
            self.btn_run.set_sensitive(bool(self._http_trigger_enabled))
        except Exception:
            pass
        try:
            self._actions_detail_stack.set_visible_child_name("form")
        except Exception:
            pass

    def _actions_bind_form(self, action: dict) -> None:
        self.ed_name_entry.set_text(str(action.get("name") or ""))
        typ = str(action.get("type") or "http").lower()
        if typ not in ("http", "shell"):
            typ = "http"
        self.ed_type_combo.set_active_id(typ)

        self.ed_http_method.set_active_id(str(action.get("method", "GET")).upper() or "GET")
        self.ed_http_url.set_text(str(action.get("url", "") or ""))

        self.ed_shell_cmd.set_text(str(action.get("command", "") or ""))
        try:
            import json as _json
            args_pretty = _json.dumps(action.get("args", []), ensure_ascii=False)
        except Exception:
            args_pretty = "[]"
        args_buf = self.ed_shell_args_tv.get_buffer()
        args_buf.set_text(args_pretty, -1)
        self.ed_shell_use_switch.set_active(bool(action.get("use_shell", False)))

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

    def _get_settings_map(self) -> dict:
        app = self._main.get_application()
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
        self._on_action_run_clicked(_btn, act, None, None)

    def _on_action_run_clicked(
        self,
        _btn: Gtk.Button,
        action: dict,
        override_combo: Optional[Gtk.ComboBoxText] = None,
        override_entry: Optional[Gtk.Entry] = None
    ) -> None:
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
            # use HistoryPage cache
            try:
                sel_text = self._history_page.get_current("primary")
            except Exception:
                sel_text = ""
            sel_type = "primary"
        else:
            try:
                sel_text = self._history_page.get_current("clipboard")
            except Exception:
                sel_text = ""
            sel_type = "clipboard"

        ctx = ActionContext(text=sel_text, selection_type=sel_type, settings_map=self._get_settings_map(), extra={"selection.type": sel_type})
        ok, message = run_action(action, ctx)
        if ok:
            self.actions_result.set_text(f"Success: {message}")
        else:
            self.actions_result.set_text(f"Failed: {message}")

    def _on_reload_actions_clicked(self, _btn: Gtk.Button) -> None:
        app = self._main.get_application()
        try:
            new_cfg = load_actions()
            setattr(app, "_actions", new_cfg)
        except Exception:
            pass
        self.refresh_actions_list()

    # --- Save/Duplicate/Delete helpers --------------------------------------

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
            src = None
            for a in actions:
                if str(a.get("name") or "") == original_name:
                    src = a
                    break
            if src is None:
                self.actions_result.set_text(_("Save (Form) failed: original action not found"))
                return

            new_name = self.ed_name_entry.get_text().strip()
            typ = (self.ed_type_combo.get_active_id() or "http").lower()
            if not new_name:
                self.actions_result.set_text(_("Validation failed: action.name must not be empty"))
                return
            obj = dict(src)
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

            app = self._main.get_application()
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

            app = self._main.get_application()
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
        try:
            app = self._main.get_application()
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

            app = self._main.get_application()
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
            # Also remove triggers referencing this action
            triggers = payload.get("triggers", {})
            if isinstance(triggers, dict):
                for k in list(triggers.keys()):
                    if triggers.get(k) == name:
                        del triggers[k]
                payload["triggers"] = triggers
            payload["actions"] = actions
            backup = write_actions_config(payload)

            app = self._main.get_application()
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
            new = {
                "name": "New Action",
                "type": "http",
                "method": "GET",
                "url": "",
                "headers": {},
                "params": {}
            }
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

            app = self._main.get_application()
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

    # --- Util ----------------------------------------------------------------

    def _clear_listbox(self, lb: Gtk.ListBox) -> None:
        child = lb.get_first_child()
        while child is not None:
            lb.remove(child)
            child = lb.get_first_child()
