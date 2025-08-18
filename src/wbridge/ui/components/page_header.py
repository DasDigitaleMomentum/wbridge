# SPDX-License-Identifier: MIT
# Compact page header with optional subtitle and help toggle button.
# The help_widget is a Gtk.Popover: clicking the help button toggles popup/popdown
# and sets relative_to to anchor it properly.

from __future__ import annotations

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # type: ignore


def build_page_header(title: str, subtitle: str | None, help_widget: Gtk.Widget | None) -> Gtk.Widget:
    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

    top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

    title_lbl = Gtk.Label(label=title or "")
    title_lbl.set_xalign(0.0)
    try:
        title_lbl.add_css_class("page-header")
    except Exception:
        pass
    title_lbl.set_hexpand(True)
    top.append(title_lbl)

    if help_widget is not None:
        help_btn = Gtk.Button(label="?")
        try:
            help_btn.add_css_class("flat")
        except Exception:
            pass
        help_btn.set_tooltip_text("Help")
        top.append(help_btn)

        # Revealer toggle
        if hasattr(help_widget, "get_reveal_child") and hasattr(help_widget, "set_reveal_child"):
            def _on_help_clicked(_btn):
                try:
                    cur = help_widget.get_reveal_child()  # type: ignore[attr-defined]
                    help_widget.set_reveal_child(not bool(cur))  # type: ignore[attr-defined]
                except Exception:
                    pass
            help_btn.connect("clicked", _on_help_clicked)

        # Popover toggle
        elif hasattr(help_widget, "popup") and hasattr(help_widget, "popdown"):
            try:
                if hasattr(help_widget, "set_relative_to"):
                    help_widget.set_relative_to(help_btn)  # type: ignore[attr-defined]
            except Exception:
                pass
            _state = {"open": False}
            # keep state in sync when popover auto-hides or is closed programmatically
            try:
                help_widget.connect("closed", lambda *_args: _state.update(open=False))  # type: ignore[attr-defined]
            except Exception:
                pass

            # compute a reasonable width (≈65% of window, min 520, max window-48)
            def _resize_popover():
                try:
                    root = help_btn.get_root()
                    win_w = root.get_width() if root and hasattr(root, "get_width") else 0
                    target = 600
                    if win_w and win_w > 0:
                        # aim for ~65% of window width, min 520px, max (window - 48px)
                        target = max(520, int(win_w * 0.65))
                        target = min(target, max(520, win_w - 48))
                    # child structure: Popover -> Box(.help-popover) -> ScrolledWindow
                    box = help_widget.get_child()  # type: ignore[attr-defined]
                    sw = None
                    if box and hasattr(box, "get_first_child"):
                        try:
                            if hasattr(box, "set_hexpand"):
                                box.set_hexpand(True)
                        except Exception:
                            pass
                        sw = box.get_first_child()
                    if sw and hasattr(sw, "set_min_content_width"):
                        sw.set_min_content_width(target)
                    # also request a minimum popover width so GTK honors it
                    try:
                        if hasattr(help_widget, "set_size_request"):
                            help_widget.set_size_request(target, -1)
                    except Exception:
                        pass
                except Exception:
                    pass

            def _on_help_clicked_pop(_btn):
                try:
                    if _state["open"]:
                        help_widget.popdown()  # type: ignore[attr-defined]
                        _state["open"] = False
                    else:
                        # ensure relation and set a sensible width
                        try:
                            if hasattr(help_widget, "set_relative_to"):
                                help_widget.set_relative_to(help_btn)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                        try:
                            _resize_popover()
                            GLib.idle_add(lambda: (_resize_popover(), False))
                        except Exception:
                            pass
                        help_widget.popup()  # type: ignore[attr-defined]
                        _state["open"] = True
                except Exception:
                    pass

            help_btn.connect("clicked", _on_help_clicked_pop)

            # Adjust width while the toplevel window is resized (when popover is open)
            try:
                root_ref = help_btn.get_root()
                def _on_root_size_alloc(_w, _alloc):
                    try:
                        if _state.get("open"):
                            _resize_popover()
                    except Exception:
                        pass
                    return False
                if root_ref and hasattr(root_ref, "connect"):
                    _state["root_size_handler"] = root_ref.connect("size-allocate", _on_root_size_alloc)
                    # best-effort cleanup on button destroy
                    def _cleanup(*_a):
                        try:
                            rid = _state.get("root_size_handler")
                            if rid and hasattr(root_ref, "disconnect"):
                                root_ref.disconnect(rid)
                        except Exception:
                            pass
                    help_btn.connect("destroy", _cleanup)
            except Exception:
                pass

    root.append(top)

    if subtitle:
        sub = Gtk.Label(label=subtitle)
        sub.set_xalign(0.0)
        try:
            sub.add_css_class("page-subtitle")
        except Exception:
            pass
        try:
            sub.add_css_class("dim")
        except Exception:
            pass
        root.append(sub)

    return root
