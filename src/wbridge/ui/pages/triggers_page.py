"""Triggers page for wbridge (extracted from gui_window.py).

Provides:
- Triggers editor mapping aliases to action names
- Add/Delete rows and Save to persist to actions.json
- Validation against existing action names
- Help panel

On save it reloads the application's actions and asks ActionsPage to refresh.
"""

from __future__ import annotations

from typing import Optional

import gettext
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # type: ignore

from ...config import load_actions_raw, write_actions_config, load_actions  # type: ignore
from ..components.help_panel import build_help_panel


# i18n init (fallback to identity if no translations installed)
try:
    _t = gettext.translation("wbridge", localedir=None, fallback=True)
    _ = _t.gettext
except Exception:
    _ = lambda s: s


class TriggersPage(Gtk.Box):
    """Triggers page container."""

    def __init__(self, main_window: Gtk.ApplicationWindow):
        """Initialize the page with a reference to the MainWindow."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._main = main_window  # reference to MainWindow for app access

        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        hdr = Gtk.Label(label=_("Triggers (Alias → Action)"))
        hdr.set_xalign(0.0)
        self.append(hdr)

        self.triggers_list = Gtk.ListBox()
        self.triggers_list.set_selection_mode(Gtk.SelectionMode.NONE)
        tr_scrolled = Gtk.ScrolledWindow()
        tr_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        tr_scrolled.set_min_content_height(260)
        tr_scrolled.set_child(self.triggers_list)
        self.append(tr_scrolled)

        btns = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        add_btn = Gtk.Button(label=_("Add Trigger"))
        add_btn.connect("clicked", self._on_triggers_add_clicked)
        btns.append(add_btn)

        save_btn = Gtk.Button(label=_("Save Triggers"))
        save_btn.connect("clicked", self._on_triggers_save_clicked)
        btns.append(save_btn)

        self.append(btns)

        # Help panel
        try:
            self.append(build_help_panel("triggers"))
        except Exception:
            pass

        # Initial populate
        try:
            self.rebuild_editor()
        except Exception:
            pass

    # --- Public API ---------------------------------------------------------

    def rebuild_editor(self) -> None:
        """Rebuild the rows based on current actions.json payload."""
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

    # --- Internals ----------------------------------------------------------

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
        # select current or first available
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
        # annotate for save usage
        row._wbridge_alias_entry = alias_entry  # type: ignore[attr-defined]
        row._wbridge_action_combo = action_combo  # type: ignore[attr-defined]
        return row

    def _on_triggers_add_clicked(self, _btn: Gtk.Button) -> None:
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
                            self._notify(_("Save Triggers failed: alias must not be empty"))
                            return
                        if alias in seen_aliases:
                            self._notify(f"Save Triggers failed: duplicate alias '{alias}'")
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
                    self._notify(f"Save Triggers failed: action '{v}' for alias '{k}' not found")
                    return

            payload["triggers"] = new_triggers
            backup = write_actions_config(payload)

            # reload actions into app (triggers part)
            app = self._main.get_application()
            try:
                new_cfg = load_actions()
                setattr(app, "_actions", new_cfg)
            except Exception:
                pass

            # ask actions page to refresh (if present)
            try:
                if hasattr(self._main, "actions_page"):
                    self._main.actions_page.refresh_actions_list()  # type: ignore[attr-defined]
            except Exception:
                pass

            # rebuild our UI
            self.rebuild_editor()
            self._notify(f"Triggers saved (backup: {backup})")
        except Exception as e:
            self._notify(f"Save Triggers failed: {e!r}")

    def _clear_listbox(self, lb: Gtk.ListBox) -> None:
        child = lb.get_first_child()
        while child is not None:
            lb.remove(child)
            child = lb.get_first_child()

    def _notify(self, text: str) -> None:
        # Reuse actions_result label on main window if present; otherwise ignore silently
        try:
            if hasattr(self._main, "actions_result"):
                self._main.actions_result.set_text(text)  # type: ignore[attr-defined]
        except Exception:
            pass
