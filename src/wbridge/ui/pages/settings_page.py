"""Settings page for wbridge (extracted from gui_window.py).

Provides:
- Integration status (read-only labels)
- Inline edit for HTTP trigger settings (enable/base/path)
- Reload/Discard/Save and Health check
- Profile management: show/install with options
- Convenience buttons: Install/Remove GNOME shortcuts, Enable/Disable autostart
- Help panel

On changes it reloads settings into the Gtk.Application and asks other pages
(Actions/Triggers) to refresh to keep the UI consistent.
"""

from __future__ import annotations

from typing import Optional, Dict, Any

import shutil
import gettext

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # type: ignore

from ...platform import socket_path, xdg_state_dir  # type: ignore
from ...config import load_settings, set_integration_settings  # type: ignore
from ...profiles_manager import (  # type: ignore
    list_builtin_profiles,
    show_profile as pm_show_profile,
    install_profile as pm_install_profile,
    load_profile_shortcuts,
    remove_profile_shortcuts,
)
from ..components.help_panel import build_help_panel
from ... import gnome_shortcuts  # type: ignore


# i18n init (fallback to identity if no translations installed)
try:
    _t = gettext.translation("wbridge", localedir=None, fallback=True)
    _ = _t.gettext
except Exception:
    _ = lambda s: s


class SettingsPage(Gtk.Box):
    """Settings page container with inline edit and profile helpers."""

    def __init__(self, main_window: Gtk.ApplicationWindow):
        """Initialize the page with a reference to the MainWindow."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._main = main_window  # reference to MainWindow for app access

        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        desc = Gtk.Label(label=_("Settings\n• Basic information and actions."))
        desc.set_wrap(True)
        desc.set_xalign(0.0)
        self.append(desc)

        # PATH hint if 'wbridge' is missing
        self.path_hint = Gtk.Label(label="")
        self.path_hint.set_wrap(True)
        self.path_hint.set_xalign(0.0)
        try:
            if shutil.which("wbridge") is None:
                self.path_hint.set_text(_("Hint: 'wbridge' was not found in PATH. GNOME Shortcuts call 'wbridge'; install user-wide via pipx/pip --user or provide an absolute path in the shortcut command."))
        except Exception:
            pass
        self.append(self.path_hint)

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

        # Integration status (read-only)
        integ_hdr = Gtk.Label(label=_("Integration status"))
        integ_hdr.set_xalign(0.0)
        self.append(integ_hdr)

        integ_grid = Gtk.Grid(column_spacing=12, row_spacing=6)
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

        self.append(integ_grid)
        self.refresh_status()

        # Integration edit
        edit_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        edit_box.set_margin_top(6)

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

        row_base = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_base = Gtk.Label(label="Base URL (http/https):")
        lbl_base.set_xalign(0.0)
        self.integ_base_entry = Gtk.Entry()
        self.integ_base_entry.set_hexpand(True)
        try:
            self.integ_base_entry.set_tooltip_text("Base URL of the HTTP trigger service (e.g., http://localhost:8808)")
        except Exception:
            pass
        row_base.append(lbl_base); row_base.append(self.integ_base_entry)
        edit_box.append(row_base)

        row_path = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_path = Gtk.Label(label="Trigger Path (/trigger):")
        lbl_path.set_xalign(0.0)
        self.integ_path_entry = Gtk.Entry()
        self.integ_path_entry.set_hexpand(True)
        try:
            self.integ_path_entry.set_tooltip_text("Trigger path (e.g., /trigger). Used with the Base URL to form the full endpoint.")
        except Exception:
            pass
        row_path.append(lbl_path); row_path.append(self.integ_path_entry)
        edit_box.append(row_path)

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
        self.append(edit_box)

        self.populate_edit_from_settings()

        # Profile block
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

        self.append(prof_box)

        # Convenience buttons
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

        self.append(btns)

        self.settings_result = Gtk.Label(label="")
        self.settings_result.set_wrap(True)
        self.settings_result.set_xalign(0.0)
        self.append(self.settings_result)

        # Help panel
        try:
            self.append(build_help_panel("settings"))
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

    def refresh_status(self) -> None:
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

    def populate_edit_from_settings(self) -> None:
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
            pass

    def reload_settings(self) -> None:
        """Reload settings from disk and notify dependent pages."""
        app = self._main.get_application()
        try:
            new_settings = load_settings()
            setattr(app, "_settings", new_settings)
        except Exception:
            pass
        self.refresh_status()
        self.populate_edit_from_settings()

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

    # --- Button handlers -----------------------------------------------------

    def _on_reload_settings_clicked(self, _btn: Gtk.Button) -> None:
        self.reload_settings()

    def _on_save_integration_clicked(self, _btn: Gtk.Button) -> None:
        try:
            enabled = self.integ_enabled_switch.get_active()
            base = self.integ_base_entry.get_text().strip()
            path = self.integ_path_entry.get_text().strip()
            if not base.startswith("http://") and not base.startswith("https://"):
                self.settings_result.set_text(_("Invalid base URL (must start with http:// or https://)."))
                return
            if not path.startswith("/"):
                self.settings_result.set_text(_("Invalid trigger path (must start with '/')."))
                return
            set_integration_settings(
                http_trigger_enabled=bool(enabled),
                http_trigger_base_url=base,
                http_trigger_trigger_path=path
            )
            self.settings_result.set_text(_("Integration saved."))
            self.reload_settings()
        except Exception as e:
            self.settings_result.set_text(_("Save failed: {err}").format(err=repr(e)))

    def _on_discard_integration_clicked(self, _btn: Gtk.Button) -> None:
        self.reload_settings()

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
                self.health_result.set_text(f"Health OK ({code}) – {url}")
        except Exception as e:
            self.health_result.set_text(f"Health FAILED – {e!r}")

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
                patch_settings=bool(self.chk_patch_settings.get_active()),
                install_shortcuts=bool(self.chk_install_shortcuts.get_active()),
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
                f"- settings: patched={len(sets.get('patched',[]))} skipped={len(sets.get('skipped',[]))}\n"
                f"- shortcuts: installed={sc.get('installed',0)} skipped={sc.get('skipped',0)}\n"
                f"- errors: {len(errors)}"
            )
            self.profile_result.set_text(txt)
            # Refresh settings and actions after install
            self.reload_settings()
        except Exception as e:
            self.profile_result.set_text(_("Error: {err}").format(err=repr(e)))

    def _on_install_shortcuts_clicked(self, _btn: Gtk.Button) -> None:
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

            # 2) fallback to profile shortcuts
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
                            norm = re.sub(r"[^a-z0-9\\-]+", "-", name.lower()).strip("-")
                            suffix = f"wbridge-{norm}/"
                            gnome_shortcuts.install_binding(suffix, name, cmd, binding)
                            installed += 1
                        except Exception:
                            skipped += 1
                    self.settings_result.set_text(_("Profile shortcuts installed: installed={installed}, skipped={skipped}.").format(installed=installed, skipped=skipped))
                    return

            # 3) defaults
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
