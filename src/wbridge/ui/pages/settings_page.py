"""Settings page for wbridge (V2 configuration model).

Provides:
- Endpoints editor: list/add/edit/delete HTTP endpoints stored in settings.ini ([endpoint.<id>])
- Shortcuts editor (Config): edit [gnome.shortcuts] mapping with Auto-apply toggle, Apply now, Remove all
- Profile management: show/install with options (merge_* flags)
- Convenience buttons: Enable/Disable autostart
- Help panel

On changes it reloads settings into the Gtk.Application and asks other pages
(Actions/Triggers) to refresh to keep the UI consistent.
"""

from __future__ import annotations

from typing import Optional, Dict, Any, List

import gettext

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # type: ignore

from ...platform import socket_path, xdg_state_dir  # type: ignore
from ...config import (  # type: ignore
    load_settings,
    list_endpoints,
    upsert_endpoint,
    delete_endpoint,
    get_shortcuts_map,
    set_shortcuts_map,
    set_manage_shortcuts,
    get_secrets_map,
    set_secrets_map,
)
from ...profiles_manager import (  # type: ignore
    list_builtin_profiles,
    show_profile as pm_show_profile,
    install_profile as pm_install_profile,
)
from ..components.help_panel import build_help_panel
from ..components.page_header import build_page_header
from ... import gnome_shortcuts  # type: ignore


# i18n init (fallback to identity if no translations installed)
try:
    _t = gettext.translation("wbridge", localedir=None, fallback=True)
    _ = _t.gettext
except Exception:
    _ = lambda s: s


class SettingsPage(Gtk.Box):
    """Settings page container with Endpoints/Shortcuts editors and profile helpers."""

    def __init__(self, main_window: Gtk.ApplicationWindow):
        """Initialize the page with a reference to the MainWindow."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._main = main_window  # reference to MainWindow for app access

        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        _help = build_help_panel("settings")
        header = build_page_header(_("Settings"), None, _help)
        self.append(header)
        self.append(_help)

        # Basic info grid
        info_grid = Gtk.Grid(column_spacing=12, row_spacing=6)
        row = 0

        lbl_sock_k = Gtk.Label(label=_("IPC Socket:"))
        lbl_sock_k.set_xalign(0.0)
        lbl_sock_v = Gtk.Label(label=str(socket_path()))
        lbl_sock_v.set_xalign(0.0)
        info_grid.attach(lbl_sock_k, 0, row, 1, 1)
        info_grid.attach(lbl_sock_v, 1, row, 1, 1)
        row += 1

        lbl_log_k = Gtk.Label(label=_("Log file:"))
        lbl_log_k.set_xalign(0.0)
        lbl_log_v = Gtk.Label(label=str(xdg_state_dir() / "bridge.log"))
        lbl_log_v.set_xalign(0.0)
        info_grid.attach(lbl_log_k, 0, row, 1, 1)
        info_grid.attach(lbl_log_v, 1, row, 1, 1)
        row += 1

        self.append(info_grid)

        # ------- Endpoints editor -------
        ep_hdr = Gtk.Label(label=_("Endpoints"))
        ep_hdr.set_xalign(0.0)
        self.append(ep_hdr)

        ep_sc = Gtk.ScrolledWindow()
        ep_sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        ep_sc.set_min_content_height(220)
        self.endpoints_list = Gtk.ListBox()
        self.endpoints_list.set_selection_mode(Gtk.SelectionMode.NONE)
        ep_sc.set_child(self.endpoints_list)
        self.append(ep_sc)

        # Add/Edit row
        ep_add_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.ep_add_id_entry = Gtk.Entry()
        self.ep_add_id_entry.set_placeholder_text(_("id (slug)"))
        self.ep_add_id_entry.set_width_chars(12)

        self.ep_add_base_entry = Gtk.Entry()
        self.ep_add_base_entry.set_hexpand(True)
        self.ep_add_base_entry.set_placeholder_text(_("base_url (http/https)"))

        self.ep_add_health_entry = Gtk.Entry()
        self.ep_add_health_entry.set_placeholder_text(_("/health"))

        self.ep_add_trigger_entry = Gtk.Entry()
        self.ep_add_trigger_entry.set_placeholder_text(_("/trigger"))

        self.ep_add_btn = Gtk.Button(label=_("Add Endpoint"))
        self.ep_add_btn.connect("clicked", self._on_endpoint_add_or_save_clicked)

        for w in [
            Gtk.Label(label=_("ID:")), self.ep_add_id_entry,
            Gtk.Label(label=_("Base URL:")), self.ep_add_base_entry,
            Gtk.Label(label=_("Health:")), self.ep_add_health_entry,
            Gtk.Label(label=_("Trigger:")), self.ep_add_trigger_entry,
            self.ep_add_btn
        ]:
            ep_add_box.append(w)
        self.append(ep_add_box)

        self._editing_endpoint_id: Optional[str] = None
        self.endpoints_result = Gtk.Label(label="")
        self.endpoints_result.set_xalign(0.0)
        self.append(self.endpoints_result)

        # ------- Secrets editor -------
        sec_hdr = Gtk.Label(label=_("Secrets"))
        sec_hdr.set_xalign(0.0)
        self.append(sec_hdr)

        sec_scrolled = Gtk.ScrolledWindow()
        sec_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sec_scrolled.set_min_content_height(180)
        self.secrets_list = Gtk.ListBox()
        self.secrets_list.set_selection_mode(Gtk.SelectionMode.NONE)
        sec_scrolled.set_child(self.secrets_list)
        self.append(sec_scrolled)

        sec_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_sec_add = Gtk.Button(label=_("Add row"))
        btn_sec_add.connect("clicked", self._on_secrets_add_row_clicked)
        btn_sec_save = Gtk.Button(label=_("Save (INI)"))
        btn_sec_save.connect("clicked", self._on_secrets_save_clicked)
        btn_sec_revert = Gtk.Button(label=_("Revert"))
        btn_sec_revert.connect("clicked", self._on_secrets_revert_clicked)
        for b in [btn_sec_add, btn_sec_save, btn_sec_revert]:
            sec_btns.append(b)
        self.append(sec_btns)

        self.secrets_result = Gtk.Label(label="")
        self.secrets_result.set_wrap(True)
        self.secrets_result.set_xalign(0.0)
        self.append(self.secrets_result)

        # ------- Shortcuts (Config) editor -------
        sc_hdr = Gtk.Label(label=_("Shortcuts (Config)"))
        sc_hdr.set_xalign(0.0)
        self.append(sc_hdr)

        sc_ctrl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.manage_shortcuts_chk = Gtk.CheckButton(label=_("Auto-apply GNOME shortcuts"))
        self.manage_shortcuts_chk.connect("toggled", self._on_manage_shortcuts_toggled)
        self.shortcuts_auto_label = Gtk.Label(label="")
        self.shortcuts_auto_label.set_xalign(0.0)
        sc_ctrl.append(self.manage_shortcuts_chk)
        sc_ctrl.append(self.shortcuts_auto_label)
        self.append(sc_ctrl)

        sc_scrolled = Gtk.ScrolledWindow()
        sc_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc_scrolled.set_min_content_height(220)
        self.shortcuts_list = Gtk.ListBox()
        self.shortcuts_list.set_selection_mode(Gtk.SelectionMode.NONE)
        sc_scrolled.set_child(self.shortcuts_list)
        self.append(sc_scrolled)

        sc_btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_sc_add = Gtk.Button(label=_("Add row"))
        btn_sc_add.connect("clicked", self._on_shortcuts_add_row_clicked)
        btn_sc_save = Gtk.Button(label=_("Save (INI)"))
        btn_sc_save.connect("clicked", self._on_shortcuts_save_clicked)
        btn_sc_revert = Gtk.Button(label=_("Revert"))
        btn_sc_revert.connect("clicked", self._on_shortcuts_revert_clicked)
        btn_sc_apply = Gtk.Button(label=_("Apply now"))
        btn_sc_apply.connect("clicked", self._on_shortcuts_apply_now_clicked)
        btn_sc_remove_all = Gtk.Button(label=_("Remove all (GNOME)"))
        btn_sc_remove_all.connect("clicked", self._on_shortcuts_remove_all_clicked)
        self._btn_sc_apply = btn_sc_apply  # keep ref for sensitivity updates

        for b in [btn_sc_add, btn_sc_save, btn_sc_revert, btn_sc_apply, btn_sc_remove_all]:
            sc_btns.append(b)
        self.append(sc_btns)

        self.shortcuts_result = Gtk.Label(label="")
        self.shortcuts_result.set_wrap(True)
        self.shortcuts_result.set_xalign(0.0)
        self.append(self.shortcuts_result)

        # ------- Profile block -------
        prof_hdr = Gtk.Label(label=_("Profile"))
        prof_hdr.set_xalign(0.0)
        self.append(prof_hdr)

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

        opts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.chk_overwrite_actions = Gtk.CheckButton(label=_("Overwrite actions"))
        try:
            self.chk_overwrite_actions.set_tooltip_text(_("Overwrite existing actions in actions.json with the selected profile's definitions."))
        except Exception:
            pass
        self.chk_merge_endpoints = Gtk.CheckButton(label=_("Merge endpoints"))
        try:
            self.chk_merge_endpoints.set_tooltip_text(_("Merge [endpoint.*] sections from profile into settings.ini"))
        except Exception:
            pass
        self.chk_merge_secrets = Gtk.CheckButton(label=_("Merge secrets"))
        try:
            self.chk_merge_secrets.set_tooltip_text(_("Merge [secrets] from profile into settings.ini"))
        except Exception:
            pass
        self.chk_merge_shortcuts = Gtk.CheckButton(label=_("Merge shortcuts"))
        try:
            self.chk_merge_shortcuts.set_tooltip_text(_("Merge [gnome.shortcuts] and shortcuts.json into settings.ini (no dconf write)"))
        except Exception:
            pass
        self.chk_dry_run = Gtk.CheckButton(label=_("Dry-run"))
        try:
            self.chk_dry_run.set_tooltip_text(_("Preview changes without writing files."))
        except Exception:
            pass

        for w in [self.chk_overwrite_actions, self.chk_merge_endpoints, self.chk_merge_secrets, self.chk_merge_shortcuts, self.chk_dry_run]:
            opts.append(w)
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
        self.append(prof_box)

        # ------- Autostart convenience -------
        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_autostart_enable = Gtk.Button(label=_("Enable autostart"))
        btn_autostart_enable.connect("clicked", self._on_enable_autostart_clicked)
        btns.append(btn_autostart_enable)

        btn_autostart_disable = Gtk.Button(label=_("Disable autostart"))
        btn_autostart_disable.connect("clicked", self._on_disable_autostart_clicked)
        btns.append(btn_autostart_disable)

        self.append(btns)

        self.settings_result = Gtk.Label(label="")
        self.settings_result.set_wrap(True)
        self.settings_result.set_xalign(0.0)
        self.append(self.settings_result)

        # Initial population
        try:
            self._rebuild_endpoints_list()
        except Exception:
            pass
        try:
            self._rebuild_secrets_editor()
        except Exception:
            pass
        try:
            self._rebuild_shortcuts_editor()
        except Exception:
            pass

    # --- Settings helpers ----------------------------------------------------

    def _get_settings_map(self) -> Dict[str, Any]:
        app = self._main.get_application()
        settings = getattr(app, "_settings", None)
        try:
            return settings.as_mapping() if settings else {}
        except Exception:
            return {}

    def reload_settings(self) -> None:
        """Reload settings from disk and notify dependent pages."""
        app = self._main.get_application()
        try:
            new_settings = load_settings()
            setattr(app, "_settings", new_settings)
        except Exception:
            pass

        # Rebuild editors
        try:
            self._rebuild_endpoints_list()
        except Exception:
            pass
        try:
            self._rebuild_secrets_editor()
        except Exception:
            pass
        try:
            self._rebuild_shortcuts_editor()
        except Exception:
            pass

        # Dependent pages: actions list / triggers editor reflect settings changes
        try:
            if hasattr(self._main, "actions_page"):
                self._main.actions_page.refresh_actions_list()  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            if hasattr(self._main, "triggers_page"):
                self._main.triggers_page.rebuild_editor()  # type: ignore[attr-defined]
        except Exception:
            pass

    # --- Endpoints editor ----------------------------------------------------

    def _clear_listbox(self, lb: Gtk.ListBox) -> None:
        child = lb.get_first_child()
        while child is not None:
            lb.remove(child)
            child = lb.get_first_child()

    def _rebuild_endpoints_list(self) -> None:
        self._clear_listbox(self.endpoints_list)
        settings = load_settings()
        eps = list_endpoints(settings)
        for eid, data in sorted(eps.items(), key=lambda kv: kv[0]):
            self.endpoints_list.append(self._build_endpoint_row(eid, data))
        self._set_endpoint_editing(None, None)

    def _build_endpoint_row(self, eid: str, data: Dict[str, str]) -> Gtk.ListBoxRow:
        base = str(data.get("base_url", ""))
        health = str(data.get("health_path", "/health"))
        trigger = str(data.get("trigger_path", "/trigger"))

        grid = Gtk.Grid(column_spacing=8, row_spacing=4)
        c = 0

        # Labels
        lbl_id_k = Gtk.Label(label=_("ID:")); lbl_id_k.set_xalign(1.0)
        lbl_id_v = Gtk.Label(label=eid); lbl_id_v.set_xalign(0.0)
        grid.attach(lbl_id_k, c, 0, 1, 1); c += 1
        grid.attach(lbl_id_v, c, 0, 1, 1); c += 1

        lbl_base_k = Gtk.Label(label=_("Base URL:")); lbl_base_k.set_xalign(1.0)
        lbl_base_v = Gtk.Label(label=base); lbl_base_v.set_xalign(0.0)
        grid.attach(lbl_base_k, 0, 1, 1, 1)
        grid.attach(lbl_base_v, 1, 1, 1, 1)

        lbl_health_k = Gtk.Label(label=_("Health:")); lbl_health_k.set_xalign(1.0)
        lbl_health_v = Gtk.Label(label=health); lbl_health_v.set_xalign(0.0)
        grid.attach(lbl_health_k, 0, 2, 1, 1)
        grid.attach(lbl_health_v, 1, 2, 1, 1)

        lbl_trigger_k = Gtk.Label(label=_("Trigger:")); lbl_trigger_k.set_xalign(1.0)
        lbl_trigger_v = Gtk.Label(label=trigger); lbl_trigger_v.set_xalign(0.0)
        grid.attach(lbl_trigger_k, 0, 3, 1, 1)
        grid.attach(lbl_trigger_v, 1, 3, 1, 1)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_health = Gtk.Button(label=_("Health"))
        btn_edit = Gtk.Button(label=_("Edit"))
        btn_del = Gtk.Button(label=_("Delete"))
        btn_box.append(btn_health); btn_box.append(btn_edit); btn_box.append(btn_del)
        grid.attach(btn_box, 1, 4, 1, 1)

        status = Gtk.Label(label="")
        status.set_xalign(0.0)
        grid.attach(status, 1, 5, 1, 1)

        row = Gtk.ListBoxRow()
        row.set_child(grid)

        # wire actions
        def _on_health(_b):
            try:
                import urllib.request, urllib.error
                url = f"{base}{health}"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=2.0) as resp:  # type: ignore[arg-type]
                    code = getattr(resp, "status", 200)
                    status.set_text(_("Health OK ({code}) – {url}").format(code=code, url=url))
            except Exception as e:
                status.set_text(_("Health FAILED – {err}").format(err=repr(e)))
        btn_health.connect("clicked", _on_health)

        def _on_edit(_b):
            self._set_endpoint_editing(eid, {"base_url": base, "health_path": health, "trigger_path": trigger})
        btn_edit.connect("clicked", _on_edit)

        def _on_del(_b):
            try:
                ok = delete_endpoint(eid)
                self.endpoints_result.set_text(_("Endpoint removed.") if ok else _("Endpoint not found."))
                self.reload_settings()
            except Exception as e:
                self.endpoints_result.set_text(_("Delete failed: {err}").format(err=repr(e)))
        btn_del.connect("clicked", _on_del)

        return row

    def _set_endpoint_editing(self, eid: Optional[str], data: Optional[Dict[str, str]]) -> None:
        self._editing_endpoint_id = eid
        if eid and data:
            self.ep_add_id_entry.set_text(str(eid))
            self.ep_add_base_entry.set_text(str(data.get("base_url", "")))
            self.ep_add_health_entry.set_text(str(data.get("health_path", "/health")))
            self.ep_add_trigger_entry.set_text(str(data.get("trigger_path", "/trigger")))
            self.ep_add_btn.set_label(_("Save changes"))
        else:
            self.ep_add_id_entry.set_text("")
            self.ep_add_base_entry.set_text("")
            self.ep_add_health_entry.set_text("/health")
            self.ep_add_trigger_entry.set_text("/trigger")
            self.ep_add_btn.set_label(_("Add Endpoint"))

    def _on_endpoint_add_or_save_clicked(self, _btn: Gtk.Button) -> None:
        try:
            eid_new = self.ep_add_id_entry.get_text().strip()
            base = self.ep_add_base_entry.get_text().strip()
            health = self.ep_add_health_entry.get_text().strip() or "/health"
            trigger = self.ep_add_trigger_entry.get_text().strip() or "/trigger"
            if not eid_new:
                self.endpoints_result.set_text(_("Validation failed: id must not be empty"))
                return
            if not (base.startswith("http://") or base.startswith("https://")):
                self.endpoints_result.set_text(_("Invalid base URL (must start with http:// or https://)."))
                return
            if not health.startswith("/") or not trigger.startswith("/"):
                self.endpoints_result.set_text(_("Invalid paths (must start with '/')."))
                return

            eid_old = self._editing_endpoint_id
            # If ID changed, remove old section first
            if eid_old and eid_old != eid_new:
                try:
                    delete_endpoint(eid_old)
                except Exception:
                    pass
            upsert_endpoint(eid_new, base, health_path=health, trigger_path=trigger)
            self.endpoints_result.set_text(_("Endpoint saved."))
            self.reload_settings()
        except Exception as e:
            self.endpoints_result.set_text(_("Save failed: {err}").format(err=repr(e)))

    # --- Secrets editor ----------------------------------------------------

    def _rebuild_secrets_editor(self) -> None:
        self._clear_listbox(self.secrets_list)
        mapping = get_secrets_map(load_settings())
        if not mapping:
            self._add_secret_row("", "")
        else:
            for k, v in sorted(mapping.items(), key=lambda kv: kv[0]):
                self._add_secret_row(str(k), str(v))

    def _add_secret_row(self, key: str, value: str) -> None:
        grid = Gtk.Grid(column_spacing=8, row_spacing=4)

        lbl_key = Gtk.Label(label=_("Key:")); lbl_key.set_xalign(1.0)
        e_key = Gtk.Entry(); e_key.set_text(key); e_key.set_width_chars(20)

        lbl_val = Gtk.Label(label=_("Value:")); lbl_val.set_xalign(1.0)
        e_val = Gtk.Entry(); e_val.set_text(value); e_val.set_hexpand(True)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_del = Gtk.Button(label=_("Delete"))
        btn_row.append(btn_del)

        grid.attach(lbl_key, 0, 0, 1, 1)
        grid.attach(e_key, 1, 0, 1, 1)
        grid.attach(lbl_val, 0, 1, 1, 1)
        grid.attach(e_val, 1, 1, 1, 1)
        grid.attach(btn_row, 1, 2, 1, 1)

        row = Gtk.ListBoxRow()
        row.set_child(grid)
        row._wbridge_secret_key_entry = e_key  # type: ignore[attr-defined]
        row._wbridge_secret_val_entry = e_val  # type: ignore[attr-defined]

        def _on_del(_b):
            try:
                self.secrets_list.remove(row)
                self.secrets_result.set_text(_("Row removed."))
            except Exception as e:
                self.secrets_result.set_text(_("Delete failed: {err}").format(err=repr(e)))
        btn_del.connect("clicked", _on_del)  # type: ignore[name-defined]

        self.secrets_list.append(row)

    def _on_secrets_add_row_clicked(self, _btn: Gtk.Button) -> None:
        self._add_secret_row("", "")
        try:
            last = self.secrets_list.get_last_child()
            if isinstance(last, Gtk.ListBoxRow):
                getattr(last, "_wbridge_secret_key_entry").grab_focus()  # type: ignore[attr-defined]
        except Exception:
            pass

    def _collect_secrets_mapping(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        child = self.secrets_list.get_first_child()
        while child is not None:
            if isinstance(child, Gtk.ListBoxRow):
                e_key = getattr(child, "_wbridge_secret_key_entry", None)
                e_val = getattr(child, "_wbridge_secret_val_entry", None)
                key = (e_key.get_text() if e_key else "").strip()
                val = (e_val.get_text() if e_val else "").strip()
                if key and val:
                    mapping[key] = val
            child = child.get_next_sibling()
        return mapping

    def _on_secrets_save_clicked(self, _btn: Gtk.Button) -> None:
        try:
            mapping = self._collect_secrets_mapping()
            set_secrets_map(mapping)
            self.secrets_result.set_text(_("Secrets saved ({n} entries).").format(n=len(mapping)))
            self.reload_settings()
        except Exception as e:
            self.secrets_result.set_text(_("Save failed: {err}").format(err=repr(e)))

    def _on_secrets_revert_clicked(self, _btn: Gtk.Button) -> None:
        try:
            self._rebuild_secrets_editor()
            self.secrets_result.set_text(_("Reverted to INI."))
        except Exception as e:
            self.secrets_result.set_text(_("Revert failed: {err}").format(err=repr(e)))

    # --- Shortcuts editor ----------------------------------------------------

    def _rebuild_shortcuts_editor(self) -> None:
        # manage_shortcuts
        smap = self._get_settings_map()
        manage = False
        try:
            manage = str(smap.get("gnome", {}).get("manage_shortcuts", "true")).lower() == "true"
        except Exception:
            manage = False
        try:
            self.manage_shortcuts_chk.set_active(bool(manage))
        except Exception:
            pass
        self._update_auto_apply_status()

        # mapping rows
        self._clear_listbox(self.shortcuts_list)
        mapping = get_shortcuts_map(load_settings())
        if not mapping:
            # start with a helpful empty row
            self._add_shortcut_row("", "")
        else:
            for alias, binding in sorted(mapping.items(), key=lambda kv: kv[0]):
                self._add_shortcut_row(str(alias), str(binding))

    def _add_shortcut_row(self, alias: str, binding: str) -> None:
        grid = Gtk.Grid(column_spacing=8, row_spacing=4)

        lbl_alias = Gtk.Label(label=_("Alias:")); lbl_alias.set_xalign(1.0)
        e_alias = Gtk.Entry(); e_alias.set_text(alias); e_alias.set_width_chars(16)
        lbl_bind = Gtk.Label(label=_("Binding:")); lbl_bind.set_xalign(1.0)
        e_bind = Gtk.Entry(); e_bind.set_text(binding); e_bind.set_hexpand(True)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_del = Gtk.Button(label=_("Delete"))
        btn_row.append(btn_del)

        grid.attach(lbl_alias, 0, 0, 1, 1)
        grid.attach(e_alias, 1, 0, 1, 1)
        grid.attach(lbl_bind, 0, 1, 1, 1)
        grid.attach(e_bind, 1, 1, 1, 1)
        grid.attach(btn_row, 1, 2, 1, 1)

        row = Gtk.ListBoxRow()
        row.set_child(grid)
        row._wbridge_alias_entry = e_alias  # type: ignore[attr-defined]
        row._wbridge_bind_entry = e_bind  # type: ignore[attr-defined]

        def _on_del(_b):
            try:
                self.shortcuts_list.remove(row)
                self._notify_sc(_("Row removed."))
            except Exception as e:
                self._notify_sc(_("Delete failed: {err}").format(err=repr(e)))
        btn_del.connect("clicked", _on_del)  # type: ignore[name-defined]

        self.shortcuts_list.append(row)

    def _on_shortcuts_add_row_clicked(self, _btn: Gtk.Button) -> None:
        self._add_shortcut_row("", "")
        try:
            # focus new alias field
            last = self.shortcuts_list.get_last_child()
            if isinstance(last, Gtk.ListBoxRow):
                getattr(last, "_wbridge_alias_entry").grab_focus()  # type: ignore[attr-defined]
        except Exception:
            pass

    def _collect_shortcuts_mapping(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        child = self.shortcuts_list.get_first_child()
        while child is not None:
            if isinstance(child, Gtk.ListBoxRow):
                e_alias = getattr(child, "_wbridge_alias_entry", None)
                e_bind = getattr(child, "_wbridge_bind_entry", None)
                alias = (e_alias.get_text() if e_alias else "").strip()
                bind = (e_bind.get_text() if e_bind else "").strip()
                if alias and bind:
                    mapping[alias] = bind
            child = child.get_next_sibling()
        return mapping

    def _on_shortcuts_save_clicked(self, _btn: Gtk.Button) -> None:
        try:
            mapping = self._collect_shortcuts_mapping()
            set_shortcuts_map(mapping)
            set_manage_shortcuts(bool(self.manage_shortcuts_chk.get_active()))
            # After saving INI, auto-apply if enabled
            if bool(self.manage_shortcuts_chk.get_active()):
                smap = load_settings().as_mapping()
                res = gnome_shortcuts.sync_from_ini(smap, auto_remove=True)
                self._notify_sc(_("Saved and applied: installed={i} updated={u} removed={r} skipped={s}").format(
                    i=res.get("installed", 0),
                    u=res.get("updated", 0),
                    r=res.get("removed", 0),
                    s=res.get("skipped", 0),
                ))
            else:
                self._notify_sc(_("Saved. Auto-apply is OFF."))
            self.reload_settings()
        except Exception as e:
            self._notify_sc(_("Save failed: {err}").format(err=repr(e)))

    def _on_shortcuts_revert_clicked(self, _btn: Gtk.Button) -> None:
        try:
            self._rebuild_shortcuts_editor()
            self._notify_sc(_("Reverted to INI."))
        except Exception as e:
            self._notify_sc(_("Revert failed: {err}").format(err=repr(e)))

    def _on_shortcuts_apply_now_clicked(self, _btn: Gtk.Button) -> None:
        try:
            smap = load_settings().as_mapping()
            res = gnome_shortcuts.sync_from_ini(smap, auto_remove=True)
            self._notify_sc(_("Applied: installed={i} updated={u} removed={r} skipped={s}").format(
                i=res.get("installed", 0),
                u=res.get("updated", 0),
                r=res.get("removed", 0),
                s=res.get("skipped", 0),
            ))
        except Exception as e:
            self._notify_sc(_("Apply failed: {err}").format(err=repr(e)))

    def _on_shortcuts_remove_all_clicked(self, _btn: Gtk.Button) -> None:
        try:
            rep = gnome_shortcuts.remove_all_wbridge_shortcuts()
            self._notify_sc(_("All wbridge shortcuts removed: removed={removed}, kept={kept}.").format(
                removed=rep.get("removed", 0), kept=rep.get("kept", 0)
            ))
        except Exception as e:
            self._notify_sc(_("Remove failed: {err}").format(err=repr(e)))

    def _on_manage_shortcuts_toggled(self, _chk: Gtk.CheckButton) -> None:
        self._update_auto_apply_status()

    def _update_auto_apply_status(self) -> None:
        on = False
        try:
            on = bool(self.manage_shortcuts_chk.get_active())
        except Exception:
            on = False
        self.shortcuts_auto_label.set_text(_("Auto-apply: {state}").format(state=_("ON") if on else _("OFF")))
        try:
            # Apply-now button only useful when auto-apply is OFF
            self._btn_sc_apply.set_sensitive(not on)
        except Exception:
            pass

    def _notify_sc(self, text: str) -> None:
        try:
            self.shortcuts_result.set_text(text)
        except Exception:
            pass

    # --- Profile handlers ----------------------------------------------------

    def _on_profile_show_clicked(self, _btn: Gtk.Button) -> None:
        pid = self.profile_combo.get_active_id()
        if not pid or pid in ("none", "err"):
            self.profile_result.set_text(_("No profile selected."))
            return
        try:
            info = pm_show_profile(pid)
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
                merge_endpoints=bool(self.chk_merge_endpoints.get_active()),
                merge_secrets=bool(self.chk_merge_secrets.get_active()),
                merge_shortcuts=bool(self.chk_merge_shortcuts.get_active()),
                dry_run=bool(self.chk_dry_run.get_active()),
            )
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
            # Refresh settings and actions after install
            self.reload_settings()
        except Exception as e:
            self.profile_result.set_text(_("Error: {err}").format(err=repr(e)))

    # --- Autostart convenience ----------------------------------------------

    def _on_enable_autostart_clicked(self, _btn: Gtk.Button) -> None:
        try:
            from ... import autostart  # type: ignore
            ok = autostart.enable()
            self.settings_result.set_text(_("Autostart enabled.") if ok else _("Autostart could not be enabled."))
        except Exception as e:
            self.settings_result.set_text(_("Enabling autostart failed: {err}").format(err=repr(e)))

    def _on_disable_autostart_clicked(self, _btn: Gtk.Button) -> None:
        try:
            from ... import autostart  # type: ignore
            ok = autostart.disable()
            self.settings_result.set_text(_("Autostart disabled.") if ok else _("Autostart could not be disabled."))
        except Exception as e:
            self.settings_result.set_text(_("Disabling autostart failed: {err}").format(err=repr(e)))
