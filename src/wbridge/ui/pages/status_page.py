"""Status page for wbridge (extracted from gui_window.py).

Provides:
- Environment summary and backend info (GDK display/clipboard types)
- Log tail viewer with Refresh
- Help panel

This page is read-only and intended for diagnostics.
"""

from __future__ import annotations

import gettext

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GObject, GLib  # type: ignore

from ...platform import active_env_summary, xdg_state_dir  # type: ignore
from ..components.help_panel import build_help_panel
from ..components.page_header import build_page_header


# i18n init (fallback to identity if no translations installed)
try:
    _t = gettext.translation("wbridge", localedir=None, fallback=True)
    _ = _t.gettext
except Exception:
    _ = lambda s: s


class StatusPage(Gtk.Box):
    """Status/Diagnostics page."""

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

        _help = build_help_panel("status")
        header = build_page_header(_("Status"), None, _help)
        self.append(header)
        self.append(_help)

        # Environment summary
        env_label = Gtk.Label(label=f"Environment: {active_env_summary()}")
        env_label.set_xalign(0.0)
        self.append(env_label)

        # Backend info (display/clipboard types)
        try:
            disp = Gdk.Display.get_default()
            disp_type = GObject.type_name(disp.__gtype__)
            cb = disp.get_clipboard()
            cb_type = GObject.type_name(cb.__gtype__)
            backend_label = Gtk.Label(label=f"GDK Display: {disp_type}, Clipboard: {cb_type}")
            backend_label.set_xalign(0.0)
            self.append(backend_label)
        except Exception as e:
            backend_label = Gtk.Label(label=f"GDK info unavailable: {e}")
            backend_label.set_xalign(0.0)
            self.append(backend_label)


        # Log Tail header with Refresh
        log_hdr = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        log_lbl = Gtk.Label(label=_("Log (tail 200):"))
        log_lbl.set_xalign(0.0)
        log_hdr.append(log_lbl)

        # Follow switch (auto-refresh)
        self.follow_switch = Gtk.Switch()
        self.follow_switch.set_active(True)
        self.follow_switch.connect("state-set", self._on_follow_toggled)
        follow_lbl = Gtk.Label(label=_("Follow"))
        follow_lbl.set_xalign(0.0)
        log_hdr.append(follow_lbl)
        log_hdr.append(self.follow_switch)

        btn_log_refresh = Gtk.Button(label=_("Refresh"))
        btn_log_refresh.connect("clicked", self._on_refresh_clicked)
        log_hdr.append(btn_log_refresh)
        self.append(log_hdr)

        # Log view
        self.log_tv = Gtk.TextView()
        self.log_tv.set_monospace(True)
        self.log_tv.set_wrap_mode(Gtk.WrapMode.CHAR)
        self.log_tv.set_editable(False)
        self.log_tv.set_cursor_visible(False)
        log_sw = Gtk.ScrolledWindow()
        log_sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        log_sw.set_min_content_height(220)
        try:
            log_sw.set_hexpand(True)
            log_sw.set_vexpand(True)
        except Exception:
            pass
        log_sw.set_child(self.log_tv)
        self.append(log_sw)

        # Initial load (best-effort)
        try:
            self.refresh_log_tail()
        except Exception:
            pass

        # Start follow timer (1s) if enabled
        try:
            self._ensure_follow_timer()
        except Exception:
            pass


    # --- Public API ---------------------------------------------------------

    def refresh_log_tail(self, max_lines: int = 200) -> None:
        """Load the latest lines from the log file into the text view."""
        try:
            buf = self.log_tv.get_buffer()
            text = "".join(self._log_tail(max_lines))
            buf.set_text(text, -1)
            # Neu: neueste Zeilen oben – Cursor an den Start und dorthin scrollen
            try:
                it = buf.get_start_iter()
                buf.place_cursor(it)
                insert = buf.get_insert()
                self.log_tv.scroll_to_mark(insert, 0.0, True, 0.0, 0.0)
            except Exception:
                pass
        except Exception:
            # ignore errors silently
            pass

    # --- Follow/Auto-Refresh ------------------------------------------------

    def _on_follow_toggled(self, _sw, _ps=None):
        self._ensure_follow_timer()
        return False

    def _ensure_follow_timer(self):
        try:
            active = bool(self.follow_switch.get_active()) if hasattr(self, "follow_switch") else False
            cur_id = getattr(self, "_follow_timeout_id", 0)
            if active and not cur_id:
                self._follow_timeout_id = GLib.timeout_add_seconds(1, self._follow_tick)
            elif (not active) and cur_id:
                GLib.source_remove(cur_id)
                self._follow_timeout_id = 0
        except Exception:
            pass

    def _follow_tick(self):
        try:
            self.refresh_log_tail()
        except Exception:
            pass
        # keep running only if still active
        try:
            return bool(self.follow_switch.get_active())
        except Exception:
            return False

    # --- Internals ----------------------------------------------------------

    def _log_tail(self, max_lines: int = 200) -> list[str]:
        try:
            path = xdg_state_dir() / "bridge.log"
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            tail = lines[-max_lines:]
            tail.reverse()  # neueste zuerst
            return tail
        except Exception:
            return []

    def _on_refresh_clicked(self, _btn: Gtk.Button) -> None:
        self.refresh_log_tail()
