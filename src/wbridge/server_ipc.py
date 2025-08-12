"""
IPC server (Unix Domain Socket) for wbridge.

- Newline-delimited JSON protocol.
- Runs in a background thread so the GTK main loop remains responsive.
- Accepts a handler callable that processes each JSON request and returns a dict response.

Security:
- Socket path: $XDG_RUNTIME_DIR/wbridge.sock (0600)
"""

from __future__ import annotations

import json
import os
import selectors
import socket
import threading
from typing import Any, Callable, Dict, Optional

from .platform import socket_path


Request = Dict[str, Any]
Response = Dict[str, Any]
Handler = Callable[[Request], Response]


class IPCServer:
    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._selector: Optional[selectors.BaseSelector] = None
        self._server_sock: Optional[socket.socket] = None
        self._path = str(socket_path())

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="wbridge-ipc", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._selector:
            try:
                self._selector.close()
            except Exception:
                pass
        if self._server_sock:
            try:
                self._server_sock.close()
            except Exception:
                pass
        # Remove socket file
        try:
            if os.path.exists(self._path):
                os.remove(self._path)
        except Exception:
            pass
        if self._thread:
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        # Clean previous socket file if any
        try:
            if os.path.exists(self._path):
                os.remove(self._path)
        except Exception:
            pass

        sel = selectors.DefaultSelector()
        self._selector = sel

        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock = srv
        try:
            srv.bind(self._path)
        except OSError as e:
            # Could not bind; nothing else to do
            return

        try:
            os.chmod(self._path, 0o600)
        except Exception:
            pass

        srv.listen(16)
        srv.setblocking(False)
        sel.register(srv, selectors.EVENT_READ)

        try:
            while not self._stop_event.is_set():
                events = sel.select(timeout=0.2)
                for key, _ in events:
                    if key.fileobj is srv:
                        self._accept(sel, srv)
                    else:
                        conn_obj = key.fileobj
                        if isinstance(conn_obj, socket.socket):
                            try:
                                self._read(sel, conn_obj)
                            except Exception:
                                try:
                                    sel.unregister(conn_obj)
                                except Exception:
                                    pass
                                try:
                                    conn_obj.close()
                                except Exception:
                                    pass
        finally:
            try:
                sel.close()
            except Exception:
                pass
            try:
                srv.close()
            except Exception:
                pass
            try:
                if os.path.exists(self._path):
                    os.remove(self._path)
            except Exception:
                pass

    def _accept(self, sel: selectors.BaseSelector, srv: socket.socket) -> None:
        try:
            conn, _ = srv.accept()
            conn.setblocking(False)
            sel.register(conn, selectors.EVENT_READ, data=b"")
        except BlockingIOError:
            pass

    def _read(self, sel: selectors.BaseSelector, conn: socket.socket) -> None:
        try:
            data = conn.recv(65536)
        except BlockingIOError:
            return
        if not data:
            try:
                sel.unregister(conn)
            except Exception:
                pass
            conn.close()
            return

        # We accept possibly multiple newline-delimited JSON messages in one recv.
        for line in data.splitlines():
            if not line:
                continue
            response = self._handle_line(line)
            try:
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
            except Exception:
                # Close on send failure
                try:
                    sel.unregister(conn)
                except Exception:
                    pass
                conn.close()
                return

    def _handle_line(self, line: bytes) -> Response:
        try:
            req: Request = json.loads(line.decode("utf-8"))
        except Exception as e:
            return {"ok": False, "error": f"invalid json: {e}", "code": "INVALID_ARG"}
        try:
            resp = self._handler(req)
            if not isinstance(resp, dict):
                return {"ok": False, "error": "handler returned non-dict"}
            # Ensure ok present
            if "ok" not in resp:
                resp["ok"] = True
            return resp
        except Exception as e:
            return {"ok": False, "error": str(e), "code": "ACTION_FAILED"}
