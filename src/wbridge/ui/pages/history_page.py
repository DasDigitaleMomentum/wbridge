"""History page for wbridge (extracted from gui_window.py).

Provides:
- Clipboard/Primary current values and lists (newest first)
- Apply/Swap actions
- Manual refresh and periodic async update of current selection labels
- Help panel rendering

This page maintains its own selection caches and also keeps the
MainWindow caches in sync to preserve compatibility with existing
logic that still reads from MainWindow during the refactor.
"""

from __future__ import annotations

from typing import Optional

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib  # type: ignore
from gi.repository import Pango  # type: ignore

import gettext

# i18n init (fallback to identity if no translations installed)
try:
    _t = gettext.translation("wbridge", localedir=None, fallback=True)
    _ = _t.gettext
except Exception:
    _ = lambda s: s

from ..components.help_panel import build_help_panel


class HistoryPage(Gtk.Box):
    """History page container."""

    def __init__(self, main_window: Gtk.ApplicationWindow):
        """Initialize the page with a reference to the MainWindow."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._main = main_window  # reference to MainWindow for app access

        # Selection caches (kept to mirror current design)
        self._cur_clip: str = ""
        self._cur_primary: str = ""
        self._hist_dirty: bool = True
        self._reading_cb: bool = False
        self._reading_pr: bool = False

        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        # Top description
        history_desc = Gtk.Label(label=_("History (Clipboard / Primary)\n"
                                         "• List of recent entries with actions: Set as Clipboard, Set as Primary, Swap (swaps the last two).\n"
                                         "• Tip: CLI `wbridge selection set/get` also works."))
        history_desc.set_wrap(True)
        history_desc.set_xalign(0.0)
        self.append(history_desc)

        # Controls: manual refresh + counter
        hist_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        refresh_btn = Gtk.Button(label=_("Refresh"))
        refresh_btn.connect("clicked", lambda _b: self.refresh())
        hist_controls.append(refresh_btn)

        self.hist_count = Gtk.Label(label=_("Entries: 0 / 0"))
        self.hist_count.set_xalign(0.0)
        hist_controls.append(self.hist_count)

        self.append(hist_controls)

        # Two-column grid
        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        grid.set_column_homogeneous(True)

        # Clipboard column
        cb_frame = Gtk.Frame(label=_("Clipboard"))
        cb_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cb_box.set_margin_start(10)
        cb_box.set_margin_end(10)
        cb_box.set_margin_top(10)
        cb_box.set_margin_bottom(10)

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

        # Primary column
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
        self.append(grid)

        # Help panel
        try:
            self.append(build_help_panel("history"))
        except Exception:
            pass

    # ---- Public API for MainWindow orchestration ----

    def refresh(self, limit: int = 20) -> None:
        """Rebuild list views and update counters and current labels."""
        cb_items = self._history_list("clipboard", limit)
        pr_items = self._history_list("primary", limit)

        try:
            self.hist_count.set_text(_("Entries: {cb} / {pr}").format(cb=len(cb_items), pr=len(pr_items)))
        except Exception:
            pass

        cb_sel = self._cur_clip or ""
        pr_sel = self._cur_primary or ""
        try:
            self.cb_label.set_text(_("Current: {val}").format(val=repr(cb_sel)) if cb_sel else _("Current: (empty)"))
            self.pr_label.set_text(_("Current: {val}").format(val=repr(pr_sel)) if pr_sel else _("Current: (empty)"))
        except Exception:
            pass

        self._clear_listbox(self.cb_list)
        for idx, text in enumerate(cb_items):
            row = self._build_history_row(idx, text, src_which="clipboard", current_text=cb_sel)
            self.cb_list.append(row)

        self._clear_listbox(self.pr_list)
        for idx, text in enumerate(pr_items):
            row = self._build_history_row(idx, text, src_which="primary", current_text=pr_sel)
            self.pr_list.append(row)

    def update_current_labels_async(self) -> None:
        """Asynchronously read current selections and update caches/labels."""
        disp = Gdk.Display.get_default()
        try:
            cb = disp.get_clipboard()

            def _on_cb(source, res):
                try:
                    t = source.read_text_finish(res) or ""
                    if t != self._cur_clip:
                        self._cur_clip = t
                        self._hist_dirty = True
                    # keep MainWindow caches in sync (compat with Actions before split)
                    try:
                        setattr(self._main, "_cur_clip", t)
                    except Exception:
                        pass
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
                    # keep MainWindow caches in sync
                    try:
                        setattr(self._main, "_cur_primary", t)
                    except Exception:
                        pass
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

    def on_swap_clicked(self, which: str) -> None:
        """Swap via HistoryStore and apply new top item."""
        app = self._main.get_application()
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
        self.refresh()

    def get_current(self, which: str) -> str:
        """Return cached current selection for 'clipboard' or 'primary'."""
        if which == "primary":
            return self._cur_primary or ""
        return self._cur_clip or ""

    # ---- Button handlers (local to page) ----

    def on_set_clipboard_clicked(self, _btn: Gtk.Button) -> None:
        text = self.cb_entry.get_text()
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

    # ---- Internals ----

    def _history_list(self, which: str, limit: int) -> list[str]:
        app = self._main.get_application()
        hist = getattr(app, "_history", None)
        if hist is None:
            return []
        try:
            return hist.list(which, limit=limit)
        except Exception:
            return []

    def _clear_listbox(self, lb: Gtk.ListBox) -> None:
        child = lb.get_first_child()
        while child is not None:
            lb.remove(child)
            child = lb.get_first_child()

    def _build_history_row(self, idx: int, text: str, src_which: str, current_text: str) -> Gtk.Widget:
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

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
        try:
            esc = GLib.markup_escape_text(preview)
        except Exception:
            esc = preview
        mark_current = f"<b>{_('[current]')}</b> " if (current_text and text == current_text) else ""
        top_label.set_markup(f"{mark_current}[{idx}] {esc}")
        vbox.append(top_label)

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

    def _apply_text(self, which: str, text: str) -> None:
        # Set via GDK
        disp = Gdk.Display.get_default()
        clip = disp.get_primary_clipboard() if which == "primary" else disp.get_clipboard()
        if hasattr(clip, "set"):
            try:
                clip.set(text)  # type: ignore[attr-defined]
            except Exception:
                pass

        # Update caches and history without blocking main thread
        try:
            if which == "primary":
                if text != self._cur_primary:
                    self._cur_primary = text
                    # keep MainWindow cache in sync
                    try:
                        setattr(self._main, "_cur_primary", text)
                    except Exception:
                        pass
                    self._hist_dirty = True
            else:
                if text != self._cur_clip:
                    self._cur_clip = text
                    try:
                        setattr(self._main, "_cur_clip", text)
                    except Exception:
                        pass
                    self._hist_dirty = True
            app = self._main.get_application()
            hist = getattr(app, "_history", None)
            if hist:
                if which == "primary":
                    hist.add_primary(text)
                else:
                    hist.add_clipboard(text)
                self._hist_dirty = True
        except Exception:
            pass

        self._update_after_set(which)
        try:
            self.refresh()
        except Exception:
            pass

        def _later_refresh():
            try:
                self.refresh()
            except Exception:
                pass
            return False

        GLib.timeout_add(600, _later_refresh)  # type: ignore

    def _update_after_set(self, which: str) -> None:
        disp = Gdk.Display.get_default()
        clip = disp.get_primary_clipboard() if which == "primary" else disp.get_clipboard()

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
            pass
