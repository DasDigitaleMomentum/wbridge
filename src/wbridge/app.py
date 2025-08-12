#!/usr/bin/env python3
"""
wbridge-app: GTK4 GUI entry point for the Selection/Shortcut Bridge.

Scope (V1):
- Normal visible window (no hidden headless mode, no tray).
- Placeholder GUI with future tabs (History, Actions, Settings, Status).
- Runs a GLib main loop and hosts the IPC server.

Requirements:
- Python 3.10+
- PyGObject with GTK 4 (provided by system packages, e.g., python3-gi, gir1.2-gtk-4.0)

Run:
    wbridge-app
"""

import sys

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gio", "2.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gtk, Gio, GLib, Gdk, GObject  # type: ignore
except Exception as e:
    print("Error: GTK4/PyGObject not available. Please install system packages (e.g., python3-gi, gir1.2-gtk-4.0).")
    print(f"Details: {e}")
    sys.exit(1)

from .logging_setup import setup_logging
from .server_ipc import IPCServer
from .platform import active_env_summary
from .gui_window import MainWindow as UIMainWindow
from .history import HistoryStore
from .selection_monitor import SelectionMonitor
from .config import load_settings, load_actions
from .actions import run_action, ActionContext


class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application)
        self.set_title("wbridge")
        self.set_default_size(800, 600)

        # Placeholder content (to be replaced with real tabs: History, Actions, Settings, Status)
        label = Gtk.Label(label="wbridge – Selection/Shortcut Bridge\n\n"
                                "Initial scaffold.\n"
                                "- Future tabs: History / Actions / Settings / Status\n"
                                "- IPC server is running in this process.\n"
                                "- Use GNOME custom shortcuts to execute the CLI (wbridge).\n\n"
                                f"Environment: {active_env_summary()}\n")
        label.set_wrap(True)
        label.set_margin_top(24)
        label.set_margin_bottom(24)
        label.set_margin_start(24)
        label.set_margin_end(24)
        label.set_xalign(0.0)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(label)
        scrolled.set_vexpand(True)
        self.set_child(scrolled)


class BridgeApplication(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(application_id="org.wbridge.app",
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        self._logger = setup_logging()
        self._ipc: IPCServer | None = None
        self._display: object | None = None
        self._providers: list = []
        self._history: HistoryStore = HistoryStore()
        self._monitor: SelectionMonitor | None = None
        self._settings = None
        self._actions = None

    def do_startup(self) -> None:
        # Explicitly chain to Gtk.Application to avoid GI binding quirks
        Gtk.Application.do_startup(self)
        self._logger.info("Starting wbridge application")
        # Start IPC server early; handler will marshal UI ops to main thread
        self._ipc = IPCServer(self._ipc_handler)
        self._ipc.start()
        self._logger.info("IPC server started")
        # Prepare display handles for selections
        try:
            self._display = Gdk.Display.get_default()
        except Exception:
            self._display = None

        # Load settings and actions
        try:
            self._settings = load_settings()
            self._logger.info("Settings loaded from %s", getattr(self._settings, "path", None))
        except Exception as e:
            self._logger.exception("settings load error: %s", e)
            self._settings = None
        try:
            self._actions = load_actions()
            self._logger.info("Actions loaded: %s actions, %s triggers",
                              len(getattr(self._actions, "actions", []) or []),
                              len(getattr(self._actions, "triggers", {}) or {}))
        except Exception as e:
            self._logger.exception("actions load error: %s", e)
            self._actions = None

        # Start selection monitor (periodic async reads on GTK main loop)
        try:
            self._monitor = SelectionMonitor(interval_ms=300, on_change=self._on_selection_change)
            self._monitor.start()
            self._logger.info("Selection monitor started")
        except Exception as e:
            self._logger.exception("Selection monitor start error: %s", e)

    def do_shutdown(self) -> None:
        self._logger.info("Shutting down")
        try:
            if self._ipc:
                self._ipc.stop()
        except Exception as e:
            self._logger.exception("IPC server stop error: %s", e)
        try:
            if self._monitor:
                self._monitor.stop()
        except Exception as e:
            self._logger.exception("Selection monitor stop error: %s", e)
        # Chain correctly to Gtk.Application (avoid GI TypeError)
        Gtk.Application.do_shutdown(self)

    def do_activate(self) -> None:
        win = self.props.active_window
        if not win:
            win = UIMainWindow(self)
        win.present()

    # Helper methods (run on main thread via GLib.idle_add when needed)
    def _ensure_display(self) -> object:
        if self._display is None:
            try:
                self._display = Gdk.Display.get_default()
            except Exception:
                self._display = None
        return self._display

    def _set_selection_mainthread(self, which: str, text: str) -> None:
        disp = self._ensure_display()
        try:
            # Obtain the right clipboard object
            clip = disp.get_primary_clipboard() if which == "primary" else disp.get_clipboard()  # type: ignore[attr-defined]
            # Preferred: simple set(...) for strings in GTK4 (PyGObject handles GValue)
            if hasattr(clip, "set"):
                try:
                    clip.set(text)  # type: ignore[attr-defined]
                    return
                except Exception:
                    pass
            # Fallback: value-based provider, keep a reference to avoid GC
            try:
                val = GObject.Value()
                val.init(str)  # type: ignore[arg-type]
                val.set_string(text)
                provider = Gdk.ContentProvider.new_for_value(val)
            except Exception:
                # As last resort, bytes-based provider
                try:
                    b = GLib.Bytes.new(text.encode("utf-8"))  # type: ignore[attr-defined]
                except Exception:
                    b = GLib.Bytes(text.encode("utf-8"))  # type: ignore
                try:
                    formats = Gdk.ContentFormats.parse("text/plain;charset=utf-8")
                except Exception:
                    formats = None
                provider = Gdk.ContentProvider.new_for_bytes(formats or "text/plain", b)
            # Keep provider alive until next ownership change
            try:
                self._providers.append(provider)  # type: ignore[name-defined]
            except Exception:
                pass
            if hasattr(clip, "set_content"):
                clip.set_content(provider)  # type: ignore[attr-defined]
            else:
                clip.set(provider)  # type: ignore[attr-defined]
        except Exception as e:
            self._logger.exception("set_selection error: %s", e)

    def _get_selection_blocking(self, which: str, timeout_ms: int = 1000) -> str:
        """
        Schedule an async read on the GTK main thread and wait for completion.
        Returns empty string on timeout/error.
        """
        result = {"text": ""}
        done = {"flag": False}

        def _start_read():
            try:
                disp = self._ensure_display()
                if which == "primary":
                    clip = disp.get_primary_clipboard()  # type: ignore[attr-defined]
                else:
                    clip = disp.get_clipboard()  # type: ignore[attr-defined]

                def _on_finish(source, res):
                    try:
                        txt = source.read_text_finish(res)
                        result["text"] = txt or ""
                    except Exception:
                        result["text"] = ""
                    finally:
                        done["flag"] = True
                    return False

                clip.read_text_async(None, _on_finish)  # type: ignore[arg-type]
            except Exception:
                done["flag"] = True
            return False

        GLib.idle_add(_start_read, priority=GLib.PRIORITY_DEFAULT)  # type: ignore
        # Busy-wait with small sleeps; GLib timeout in a separate thread is fine for V1.
        waited = 0
        step = 0.01
        while not done["flag"] and waited < timeout_ms / 1000.0:
            GLib.usleep(int(step * 1_000_000))
            waited += step
        return result["text"]

    def _resolve_source_text(self, source: dict, text: str | None) -> tuple[str, str]:
        """
        Resolve selection text based on source:
          source = {"from": "clipboard"|"primary"|"text"}
        Returns (selection_text, selection_type)
        """
        which = "clipboard"
        try:
            if isinstance(source, dict):
                which = str(source.get("from", "clipboard")).lower()
        except Exception:
            which = "clipboard"

        if which == "text":
            sel_text = text or ""
            sel_type = "clipboard"  # default type for placeholder resolution
        elif which == "primary":
            sel_text = self._get_selection_blocking("primary")
            sel_type = "primary"
        else:
            sel_text = self._get_selection_blocking("clipboard")
            sel_type = "clipboard"
        return sel_text, sel_type

    # Monitor callback: update history when selections change
    def _on_selection_change(self, which: str, text: str) -> None:
        try:
            if which == "clipboard":
                self._history.add_clipboard(text)
            else:
                self._history.add_primary(text)
            # TODO: future - notify UI model to refresh list views
            self._logger.debug("History updated (%s): %s", which, text[:60].replace("\n", " "))
        except Exception as e:
            self._logger.exception("History update error: %s", e)

    # ------------- IPC handler -------------
    def _ipc_handler(self, req: dict) -> dict:
        """
        Minimal handler for early scaffold. Supports:
          - {"op":"ui.show"}  -> present the window and return ok
        Other ops return "INVALID_OP" for now.
        """
        try:
            op = str(req.get("op", ""))
        except Exception:
            return {"ok": False, "error": "op missing", "code": "INVALID_ARG"}

        if op == "ui.show":
            # Present window on the GTK main thread
            def _present():
                try:
                    win = self.props.active_window
                    if not win:
                        win = UIMainWindow(self)
                    win.present()
                except Exception as e:
                    self._logger.exception("ui.show error: %s", e)
                return False  # run once

            GLib.idle_add(_present, priority=GLib.PRIORITY_DEFAULT)  # type: ignore
            return {"ok": True, "data": {"op": "ui.show"}}

        if op == "selection.set":
            which = str(req.get("which", "clipboard")).lower()
            text = str(req.get("text", ""))
            # Run on main thread and wait briefly for it to be scheduled
            GLib.idle_add(self._set_selection_mainthread, which, text, priority=GLib.PRIORITY_DEFAULT)  # type: ignore
            return {"ok": True, "data": {"op": "selection.set", "which": which, "len": len(text)}}

        if op == "selection.get":
            which = str(req.get("which", "clipboard")).lower()
            txt = self._get_selection_blocking(which)
            return {"ok": True, "data": {"op": "selection.get", "which": which, "text": txt}}

        if op == "history.list":
            which = str(req.get("which", "clipboard")).lower()
            limit_val = req.get("limit", None)
            limit = None
            if limit_val is not None:
                try:
                    limit = int(limit_val)
                except Exception:
                    return {"ok": False, "error": "limit must be an integer", "code": "INVALID_ARG"}
            items = self._history.list(which, limit=limit)
            return {"ok": True, "data": {"op": "history.list", "which": which, "items": items}}

        if op == "history.apply":
            which = str(req.get("which", "clipboard")).lower()
            try:
                index = int(req.get("index", 0))
            except Exception:
                return {"ok": False, "error": "index must be an integer", "code": "INVALID_ARG"}
            text = self._history.get(which, index)
            if text is None:
                return {"ok": False, "error": "history index not found", "code": "NOT_FOUND"}
            # Apply on GTK main thread
            GLib.idle_add(self._set_selection_mainthread, which, text, priority=GLib.PRIORITY_DEFAULT)  # type: ignore
            return {"ok": True, "data": {"op": "history.apply", "which": which, "index": index, "len": len(text)}}

        if op == "history.swap":
            which = str(req.get("which", "clipboard")).lower()
            swapped = self._history.swap_last_two(which)
            if not swapped:
                return {"ok": False, "error": "not enough history items to swap", "code": "NOT_FOUND"}
            # After swap, apply the new top item to effect a 'toggle'
            top = self._history.get(which, 0) or ""
            if top:
                GLib.idle_add(self._set_selection_mainthread, which, top, priority=GLib.PRIORITY_DEFAULT)  # type: ignore
            return {"ok": True, "data": {"op": "history.swap", "which": which, "applied": bool(top), "len": len(top)}}

        if op == "action.run":
            name = str(req.get("name", "")).strip()
            if not name:
                return {"ok": False, "error": "name is required", "code": "INVALID_ARG"}
            src = req.get("source") or {}
            text_override = req.get("text")

            actions_cfg = getattr(self, "_actions", None)
            actions_list = getattr(actions_cfg, "actions", []) if actions_cfg else []
            if not actions_list:
                return {"ok": False, "error": "no actions configured", "code": "NOT_FOUND"}
            action = next((a for a in actions_list if a.get("name") == name), None)
            if not action:
                return {"ok": False, "error": f"action not found: {name}", "code": "NOT_FOUND"}

            sel_text, sel_type = self._resolve_source_text(src, text_override)
            try:
                settings_map = self._settings.as_mapping() if self._settings else None  # type: ignore[union-attr]
            except Exception:
                settings_map = None
            ctx = ActionContext(text=sel_text, selection_type=sel_type, settings_map=settings_map, extra={"selection.type": sel_type})

            ok, message = run_action(action, ctx)
            if ok:
                return {"ok": True, "data": {"op": "action.run", "name": name, "result": message}}
            else:
                return {"ok": False, "error": message, "code": "ACTION_FAILED"}

        if op == "trigger":
            cmd = str(req.get("cmd", "")).strip()
            if not cmd:
                return {"ok": False, "error": "cmd is required", "code": "INVALID_ARG"}
            actions_cfg = getattr(self, "_actions", None)
            triggers = getattr(actions_cfg, "triggers", {}) if actions_cfg else {}
            if not triggers:
                return {"ok": False, "error": "no triggers configured", "code": "NOT_FOUND"}
            target_name = triggers.get(cmd)
            if not target_name:
                return {"ok": False, "error": f"trigger not found: {cmd}", "code": "NOT_FOUND"}
            # reuse action.run path
            sub_req = dict(req)
            sub_req["op"] = "action.run"
            sub_req["name"] = target_name
            return self._ipc_handler(sub_req)

        return {"ok": False, "error": f"unsupported op: {op}", "code": "INVALID_OP"}
        

def main(argv=None) -> int:
    app = BridgeApplication()
    return app.run(argv or sys.argv)


if __name__ == "__main__":
    sys.exit(main())
