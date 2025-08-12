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
    from gi.repository import Gtk, Gio, GLib  # type: ignore
except Exception as e:
    print("Error: GTK4/PyGObject not available. Please install system packages (e.g., python3-gi, gir1.2-gtk-4.0).")
    print(f"Details: {e}")
    sys.exit(1)

from .logging_setup import setup_logging
from .server_ipc import IPCServer
from .platform import active_env_summary


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

    def do_startup(self) -> None:
        super().do_startup()
        self._logger.info("Starting wbridge application")
        # Start IPC server early; handler will marshal UI ops to main thread
        self._ipc = IPCServer(self._ipc_handler)
        self._ipc.start()
        self._logger.info("IPC server started")

    def do_shutdown(self) -> None:
        self._logger.info("Shutting down")
        try:
            if self._ipc:
                self._ipc.stop()
        except Exception as e:
            self._logger.exception("IPC server stop error: %s", e)
        super().do_shutdown()

    def do_activate(self) -> None:
        win = self.props.active_window
        if not win:
            win = MainWindow(self)
        win.present()

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
                        win = MainWindow(self)
                    win.present()
                except Exception as e:
                    self._logger.exception("ui.show error: %s", e)
                return False  # run once

            GLib.idle_add(_present, priority=GLib.PRIORITY_DEFAULT)  # type: ignore
            return {"ok": True, "data": {"op": "ui.show"}}

        return {"ok": False, "error": f"unsupported op: {op}", "code": "INVALID_OP"}
        

def main(argv=None) -> int:
    app = BridgeApplication()
    return app.run(argv or sys.argv)


if __name__ == "__main__":
    sys.exit(main())
