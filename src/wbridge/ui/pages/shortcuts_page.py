"""Shortcuts page for wbridge (extracted from gui_window.py).

Provides:
- Show wbridge-managed GNOME custom keybindings (optionally all, read-only)
- Add new managed entries, Save, Reload, Delete
- Conflict hint for duplicate bindings
- PATH hint if 'wbridge' binary is not resolvable
- Help panel

This page reads/writes GNOME keybindings via Gio.Settings and helpers in gnome_shortcuts.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any

import shutil
import gettext

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")
from gi.repository import Gtk, Gio  # type: ignore

from ... import gnome_shortcuts  # type: ignore
from ..components.help_panel import build_help_panel


# i18n init (fallback to identity if no translations installed)
try:
    _t = gettext.translation("wbridge", localedir=None, fallback=True)
    _ = _t.gettext
except Exception:
    _ = lambda s: s


class ShortcutsPage(Gtk.Box):
    """Shortcuts page container."""

    def __init__(self, main_window: Gtk.ApplicationWindow):
        """Initialize the page with a reference to the MainWindow."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._main = main_window  # reference to MainWindow for app access

        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        # Header + hint
        hdr = Gtk.Label(label=_("Shortcuts (GNOME Custom Keybindings)"))
        hdr.set_xalign(0.0)
        self.append(hdr)

        hint = Gtk.Label(label=_("Only wbridge-managed entries are editable. Foreign entries optionally visible (read-only)."))
        hint.set_wrap(True)
        hint.set_xalign(0.0)
        self.append(hint)

        # PATH hint if 'wbridge' is missing
        self.shortcuts_path_hint = Gtk.Label(label="")
        self.shortcuts_path_hint.set_wrap(True)
        self.shortcuts_path_hint.set_xalign(0.0)
        try:
            if shutil.which("wbridge") is None:
                self.shortcuts_path_hint.set_text(_("Hint: 'wbridge' was not found in PATH. GNOME Shortcuts call 'wbridge'; install user-wide via pipx/pip --user or use an absolute path in the shortcuts."))
        except Exception:
            pass
        self.append(self.shortcuts_path_hint)

        # Controls: show-all (read-only), Add, Save, Reload
        ctrl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        lbl_show = Gtk.Label(label=_("Show all custom (read-only):"))
        lbl_show.set_xalign(0.0)
        ctrl.append(lbl_show)

        self.shortcuts_show_all = Gtk.Switch()
        self.shortcuts_show_all.set_active(False)

        def _on_show_all(_sw, _ps=None):
            try:
                self.reload()
            except Exception:
                pass
            return False

        self.shortcuts_show_all.connect("state-set", _on_show_all)
        ctrl.append(self.shortcuts_show_all)

        btn_add = Gtk.Button(label=_("Add"))
        btn_add.connect("clicked", self._on_add_clicked)
        ctrl.append(btn_add)

        btn_save = Gtk.Button(label=_("Save"))
        btn_save.connect("clicked", self._on_save_clicked)
        ctrl.append(btn_save)

        btn_reload = Gtk.Button(label=_("Reload"))
        btn_reload.connect("clicked", self._on_reload_clicked)
        ctrl.append(btn_reload)

        self.append(ctrl)

        # Conflicts label
        self.shortcuts_conflicts_label = Gtk.Label(label="")
        self.shortcuts_conflicts_label.set_xalign(0.0)
        self.append(self.shortcuts_conflicts_label)

        # List
        self.shortcuts_list = Gtk.ListBox()
        self.shortcuts_list.set_selection_mode(Gtk.SelectionMode.NONE)
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sc.set_min_content_height(300)
        sc.set_child(self.shortcuts_list)
        self.append(sc)

        # Result messages
        self.shortcuts_result = Gtk.Label(label="")
        self.shortcuts_result.set_wrap(True)
        self.shortcuts_result.set_xalign(0.0)
        self.append(self.shortcuts_result)

        # Initial load
        try:
            self.reload()
        except Exception:
            pass

        # Help panel
        try:
            self.append(build_help_panel("shortcuts"))
        except Exception:
            pass

    # --- Public API ---------------------------------------------------------

    def reload(self) -> None:
        """Rebuild list and conflict hints."""
        include_foreign = bool(self.shortcuts_show_all.get_active()) if hasattr(self, "shortcuts_show_all") else False
        items = self._read_items(include_foreign=include_foreign)

        # Clear
        child = self.shortcuts_list.get_first_child()
        while child is not None:
            self.shortcuts_list.remove(child)
            child = self.shortcuts_list.get_first_child()

        # Build rows
        for it in items:
            self.shortcuts_list.append(self._build_row(it))

        # Conflicts
        conflicts: Dict[str, int] = {}
        for it in items:
            b = str(it.get("binding") or "")
            if not b:
                continue
            conflicts[b] = conflicts.get(b, 0) + 1
        msgs: List[str] = []
        for k, cnt in conflicts.items():
            if cnt > 1:
                msgs.append(f"'{k}' ×{cnt}")
        self.shortcuts_conflicts_label.set_text((_('Conflicts: ') + ", ".join(msgs)) if msgs else "")

    # --- Button handlers -----------------------------------------------------

    def _on_reload_clicked(self, _btn: Gtk.Button) -> None:
        try:
            self.reload()
            self._notify(_("Reloaded shortcuts."))
        except Exception as e:
            self._notify(f"Reload failed: {e!r}")

    def _on_add_clicked(self, _btn: Gtk.Button) -> None:
        try:
            # Create empty editable row (wbridge-managed, not yet installed)
            item = {
                "full_path": None,
                "suffix": None,
                "is_managed": True,
                "name": "New Shortcut",
                "command": "",
                "binding": ""
            }
            row = self._build_row(item)
            self.shortcuts_list.append(row)
            try:
                getattr(row, "_wbridge_name_entry").grab_focus()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._notify(_("New shortcut row added (not yet saved)."))
        except Exception as e:
            self._notify(f"Add failed: {e!r}")

    def _on_row_delete_clicked(self, _btn: Gtk.Button, row: Gtk.ListBoxRow) -> None:
        try:
            is_managed = bool(getattr(row, "_wbridge_is_managed", False))
            if not is_managed:
                self._notify(_("Delete not allowed for non-wbridge entries."))
                return
            suffix = getattr(row, "_wbridge_suffix", None)
            if suffix:
                try:
                    gnome_shortcuts.remove_binding(suffix)
                except Exception as e:
                    self._notify(f"Remove failed: {e!r}")
            self.shortcuts_list.remove(row)
            self.reload()
            self._notify(_("Shortcut removed."))
        except Exception as e:
            self._notify(f"Delete failed: {e!r}")

    def _on_save_clicked(self, _btn: Gtk.Button) -> None:
        try:
            # Existing suffixes to avoid collisions
            current = self._read_items(include_foreign=True)
            existing_suffixes: set[str] = {str(it.get("suffix")) for it in current if isinstance(it.get("suffix"), str)}
            changed = 0

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
                            self._notify(_("Validation failed: name must not be empty"))
                            return
                        if not cmd:
                            self._notify(_("Validation failed: command must not be empty"))
                            return
                        if not bind:
                            self._notify(_("Validation failed: binding must not be empty"))
                            return

                        desired_suffix = self._compute_suffix(name, existing_suffixes, prefer=old_suffix)
                        if old_suffix and desired_suffix != old_suffix:
                            try:
                                gnome_shortcuts.remove_binding(old_suffix)
                            except Exception:
                                pass
                            existing_suffixes.discard(old_suffix)

                        gnome_shortcuts.install_binding(desired_suffix, name, cmd, bind)
                        setattr(child, "_wbridge_suffix", desired_suffix)
                        existing_suffixes.add(desired_suffix)
                        changed += 1
                child = child.get_next_sibling()

            self.reload()
            self._notify(f"Saved shortcuts: {changed}")
        except Exception as e:
            self._notify(f"Save failed: {e!r}")

    # --- Internals -----------------------------------------------------------

    def _compute_suffix(self, name: str, existing_suffixes: set[str], prefer: Optional[str] = None) -> str:
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

    def _read_items(self, include_foreign: bool) -> list[dict]:
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

    def _build_row(self, item: dict) -> Gtk.ListBoxRow:
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

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        if is_managed:
            del_btn = Gtk.Button(label=_("Delete"))
            btn_box.append(del_btn)
        grid.attach(btn_box, 1, 3, 1, 1)

        row = Gtk.ListBoxRow()
        row.set_child(grid)

        # Row metadata
        row._wbridge_is_managed = is_managed  # type: ignore[attr-defined]
        row._wbridge_suffix = suffix  # type: ignore[attr-defined]
        row._wbridge_name_entry = name_e  # type: ignore[attr-defined]
        row._wbridge_cmd_entry = cmd_e  # type: ignore[attr-defined]
        row._wbridge_bind_entry = bind_e  # type: ignore[attr-defined]

        if is_managed:
            def _on_del(_b):
                self._on_row_delete_clicked(_b, row)
            del_btn.connect("clicked", _on_del)  # type: ignore[name-defined]

        return row

    def _notify(self, text: str) -> None:
        try:
            self.shortcuts_result.set_text(text)
        except Exception:
            pass
