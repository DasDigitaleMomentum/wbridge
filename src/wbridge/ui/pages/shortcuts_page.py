"""Shortcuts page (V2): Audit and sync GNOME shortcuts vs settings.ini.

Provides:
- Audit table: Alias | INI binding (editable) | Installed binding (read-only)
- Controls: Add row, Save (INI), Apply now (sync GNOME), Remove all (GNOME), Reload
- Conflicts summary
- Help panel

This page compares [gnome.shortcuts] from settings.ini with currently installed
GNOME custom keybindings (wbridge-* scope) and lets you edit/save the INI mapping
and synchronize it deterministically to GNOME.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any

import re
import gettext

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # type: ignore

from ...config import load_settings, get_shortcuts_map, set_shortcuts_map  # type: ignore
from ... import gnome_shortcuts  # type: ignore
from ..components.help_panel import build_help_panel
from ..components.page_header import build_page_header
from ..components.cta_bar import build_cta_bar


# i18n init (fallback to identity if no translations installed)
try:
    _t = gettext.translation("wbridge", localedir=None, fallback=True)
    _ = _t.gettext
except Exception:
    _ = lambda s: s


def _alias_from_command(cmd: str) -> Optional[str]:
    """
    Derive a trigger alias from a GNOME shortcut command.
      - 'wbridge ui show'                 -> 'ui_show'
      - 'wbridge trigger <alias> [..]'    -> '<alias>'
    Returns None if it cannot be determined.
    """
    try:
        s = str(cmd or "").strip()
        if not s:
            return None
        if s.startswith("wbridge ui show"):
            return "ui_show"
        m = re.search(r"\bwbridge\s+trigger\s+([^\s]+)", s)
        if m:
            return m.group(1)
        return None
    except Exception:
        return None


class ShortcutsPage(Gtk.Box):
    """Shortcuts audit/sync page for V2."""

    def __init__(self, main_window: Gtk.ApplicationWindow):
        """Initialize the page with a reference to the MainWindow."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._main = main_window  # reference to MainWindow for app access
        try:
            self.set_hexpand(True)
            self.set_vexpand(True)
        except Exception:
            pass

        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        # Scrollable content container (CTA bar stays fixed at bottom)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        try:
            content_box.set_hexpand(True)
            content_box.set_vexpand(True)
        except Exception:
            pass
        self.append(content_box)

        _help = build_help_panel("shortcuts")
        header = build_page_header(_("Shortcuts"), _("Audit and sync GNOME shortcuts vs settings.ini"), _help)
        content_box.append(header)
        content_box.append(_help)

        # Controls: Add, Save (INI), Apply now, Remove all, Reload
        ctrl = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        btn_add = Gtk.Button(label=_("Add row"))
        btn_add.connect("clicked", self._on_add_clicked)
        ctrl.append(btn_add)

        btn_save = Gtk.Button(label=_("Save (INI)"))
        btn_save.connect("clicked", self._on_save_clicked)
        ctrl.append(btn_save)

        btn_apply = Gtk.Button(label=_("Apply now (GNOME)"))
        btn_apply.connect("clicked", self._on_apply_now_clicked)
        ctrl.append(btn_apply)

        btn_remove_all = Gtk.Button(label=_("Remove all (GNOME)"))
        btn_remove_all.connect("clicked", self._on_remove_all_clicked)
        ctrl.append(btn_remove_all)

        btn_reload = Gtk.Button(label=_("Reload"))
        btn_reload.connect("clicked", self._on_reload_clicked)
        ctrl.append(btn_reload)

        content_box.append(ctrl)

        # Conflicts label
        self.shortcuts_conflicts_label = Gtk.Label(label="")
        self.shortcuts_conflicts_label.set_xalign(0.0)
        content_box.append(self.shortcuts_conflicts_label)

        # List (Audit table)
        self.shortcuts_list = Gtk.ListBox()
        self.shortcuts_list.set_selection_mode(Gtk.SelectionMode.NONE)
        sc = Gtk.ScrolledWindow()
        sc.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sc.set_min_content_height(320)
        try:
            sc.set_hexpand(True)
            sc.set_vexpand(True)
        except Exception:
            pass
        sc.set_child(self.shortcuts_list)
        content_box.append(sc)

        # Result messages
        self.shortcuts_result = Gtk.Label(label="")
        self.shortcuts_result.set_wrap(True)
        self.shortcuts_result.set_xalign(0.0)
        content_box.append(self.shortcuts_result)

        # Bottom CTA bar (Save/Apply/Reload duplicates kept for quick access)
        btn_save2 = Gtk.Button(label=_("Save (INI)"))
        btn_save2.connect("clicked", self._on_save_clicked)
        btn_apply2 = Gtk.Button(label=_("Apply now (GNOME)"))
        btn_apply2.connect("clicked", self._on_apply_now_clicked)
        btn_reload2 = Gtk.Button(label=_("Reload"))
        btn_reload2.connect("clicked", self._on_reload_clicked)
        self.append(build_cta_bar(btn_save2, btn_apply2, btn_reload2))

        # Initial load
        try:
            self.reload()
        except Exception:
            pass

    # --- Public API ---------------------------------------------------------

    def reload(self) -> None:
        """Rebuild audit table from INI mapping and installed GNOME shortcuts."""
        ini_map = self._load_ini_mapping()
        installed_map = self._load_installed_mapping()

        # Union of aliases: from INI and installed
        aliases: List[str] = sorted(set(ini_map.keys()) | set(installed_map.keys()))

        # Clear listbox
        self._clear_listbox(self.shortcuts_list)

        # Header row
        hdr = Gtk.Grid(column_spacing=8, row_spacing=4)
        def _hdr_label(text: str) -> Gtk.Label:
            l = Gtk.Label(label=text)
            l.set_xalign(0.0)
            try:
                l.get_style_context().add_class("dim-label")
            except Exception:
                pass
            return l
        hdr.attach(_hdr_label(_("Alias")), 0, 0, 1, 1)
        hdr.attach(_hdr_label(_("INI Binding (editable)")), 1, 0, 1, 1)
        hdr.attach(_hdr_label(_("Installed Binding (read-only)")), 2, 0, 1, 1)
        row_hdr = Gtk.ListBoxRow()
        row_hdr.set_sensitive(False)
        row_hdr.set_child(hdr)
        self.shortcuts_list.append(row_hdr)

        # Rows
        for a in aliases:
            ini_bind = ini_map.get(a, "")
            inst_bind = installed_map.get(a, "")
            self.shortcuts_list.append(self._build_row(a, ini_bind, inst_bind))

        # Conflicts summary (installed)
        self._update_conflicts(installed_map)

    # --- Button handlers -----------------------------------------------------

    def _on_reload_clicked(self, _btn: Gtk.Button) -> None:
        try:
            self.reload()
            self._notify(_("Reloaded shortcuts audit."))
        except Exception as e:
            self._notify(f"Reload failed: {e!r}")

    def _on_add_clicked(self, _btn: Gtk.Button) -> None:
        try:
            # Add an empty editable row (alias + ini binding), installed binding stays empty
            row = self._build_row("", "", "")
            self.shortcuts_list.append(row)
            # Focus alias field
            try:
                getattr(row, "_wbridge_alias_entry").grab_focus()  # type: ignore[attr-defined]
            except Exception:
                pass
            self._notify(_("New row added (INI only)."))
        except Exception as e:
            self._notify(f"Add failed: {e!r}")

    def _on_row_delete_clicked(self, _btn: Gtk.Button, row: Gtk.ListBoxRow) -> None:
        try:
            self.shortcuts_list.remove(row)
            self._notify(_("Row removed (remember to Save)."))
        except Exception as e:
            self._notify(f"Delete failed: {e!r}")

    def _on_save_clicked(self, _btn: Gtk.Button) -> None:
        try:
            mapping = self._collect_ini_mapping()
            set_shortcuts_map(mapping)
            self._notify(_("INI saved (aliases={n}).").format(n=len(mapping)))
            # After saving, refresh audit to reflect current INI
            self.reload()
        except Exception as e:
            self._notify(_("Save failed: {err}").format(err=repr(e)))

    def _on_apply_now_clicked(self, _btn: Gtk.Button) -> None:
        try:
            smap = load_settings().as_mapping()
            res = gnome_shortcuts.sync_from_ini(smap, auto_remove=True)
            self._notify(_("Applied: installed={i} updated={u} removed={r} skipped={s}").format(
                i=res.get("installed", 0),
                u=res.get("updated", 0),
                r=res.get("removed", 0),
                s=res.get("skipped", 0),
            ))
            # After applying, refresh audit to show current 'Installed Binding'
            self.reload()
        except Exception as e:
            self._notify(_("Apply failed: {err}").format(err=repr(e)))

    def _on_remove_all_clicked(self, _btn: Gtk.Button) -> None:
        try:
            rep = gnome_shortcuts.remove_all_wbridge_shortcuts()
            self._notify(_("All wbridge shortcuts removed: removed={removed}, kept={kept}.").format(
                removed=rep.get("removed", 0), kept=rep.get("kept", 0)
            ))
            self.reload()
        except Exception as e:
            self._notify(_("Remove failed: {err}").format(err=repr(e)))

    # --- Internals -----------------------------------------------------------

    def _load_ini_mapping(self) -> Dict[str, str]:
        try:
            return get_shortcuts_map(load_settings())
        except Exception:
            return {}

    def _load_installed_mapping(self) -> Dict[str, str]:
        """
        Build alias -> installed binding map by inspecting current GNOME shortcuts
        within wbridge scope via gnome_shortcuts.list_installed().
        """
        out: Dict[str, str] = {}
        try:
            items = gnome_shortcuts.list_installed() or []
            for it in items:
                alias = _alias_from_command(str(it.get("command") or ""))
                if alias:
                    bind = str(it.get("binding") or "")
                    out[alias] = bind
        except Exception:
            pass
        return out

    def _build_row(self, alias: str, ini_binding: str, installed_binding: str) -> Gtk.ListBoxRow:
        grid = Gtk.Grid(column_spacing=8, row_spacing=4)

        # Alias (editable)
        lbl_alias = Gtk.Label(label=_("Alias:")); lbl_alias.set_xalign(1.0)
        e_alias = Gtk.Entry(); e_alias.set_text(str(alias or "")); e_alias.set_width_chars(16)

        # INI binding (editable)
        lbl_ini = Gtk.Label(label=_("INI:")); lbl_ini.set_xalign(1.0)
        e_ini = Gtk.Entry(); e_ini.set_text(str(ini_binding or "")); e_ini.set_hexpand(True)

        # Installed binding (read-only)
        lbl_inst = Gtk.Label(label=_("Installed:")); lbl_inst.set_xalign(1.0)
        v_inst = Gtk.Label(label=str(installed_binding or "")); v_inst.set_xalign(0.0)

        # Buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        del_btn = Gtk.Button(label=_("Delete"))
        btn_box.append(del_btn)

        # Layout
        grid.attach(lbl_alias, 0, 0, 1, 1)
        grid.attach(e_alias, 1, 0, 1, 1)
        grid.attach(lbl_ini, 0, 1, 1, 1)
        grid.attach(e_ini, 1, 1, 1, 1)
        grid.attach(lbl_inst, 0, 2, 1, 1)
        grid.attach(v_inst, 1, 2, 1, 1)
        grid.attach(btn_box, 1, 3, 1, 1)

        row = Gtk.ListBoxRow()
        row.set_child(grid)

        # Attach metadata for later collection
        row._wbridge_alias_entry = e_alias  # type: ignore[attr-defined]
        row._wbridge_ini_entry = e_ini      # type: ignore[attr-defined]
        row._wbridge_inst_label = v_inst    # type: ignore[attr-defined]

        def _on_del(_b):
            self._on_row_delete_clicked(_b, row)
        del_btn.connect("clicked", _on_del)  # type: ignore[name-defined]

        return row

    def _collect_ini_mapping(self) -> Dict[str, str]:
        """
        Read table rows and build an alias -> binding mapping for INI.
        Rows missing alias or binding are ignored.
        """
        mapping: Dict[str, str] = {}
        child = self.shortcuts_list.get_first_child()
        # Skip header row (first)
        if child is not None:
            child = child.get_next_sibling()
        while child is not None:
            if isinstance(child, Gtk.ListBoxRow):
                e_alias = getattr(child, "_wbridge_alias_entry", None)
                e_ini = getattr(child, "_wbridge_ini_entry", None)
                alias = (e_alias.get_text() if e_alias else "").strip()
                bind = (e_ini.get_text() if e_ini else "").strip()
                if alias and bind:
                    mapping[alias] = bind
            child = child.get_next_sibling()
        return mapping

    def _update_conflicts(self, installed_map: Dict[str, str]) -> None:
        # Summarize duplicates within installed bindings (read-only audit)
        counts: Dict[str, int] = {}
        for b in (installed_map or {}).values():
            b = str(b or "")
            if not b:
                continue
            counts[b] = counts.get(b, 0) + 1
        msgs: List[str] = []
        for k, cnt in counts.items():
            if cnt > 1:
                msgs.append(f"'{k}' ×{cnt}")
        self.shortcuts_conflicts_label.set_text((_('Conflicts: ') + ", ".join(msgs)) if msgs else "")

    def _clear_listbox(self, lb: Gtk.ListBox) -> None:
        child = lb.get_first_child()
        while child is not None:
            lb.remove(child)
            child = lb.get_first_child()

    def _notify(self, text: str) -> None:
        try:
            self.shortcuts_result.set_text(text)
        except Exception:
            pass
