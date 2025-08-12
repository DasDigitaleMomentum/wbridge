"""
IPC client utilities for wbridge.

Transport:
- Unix Domain Socket at $XDG_RUNTIME_DIR/wbridge.sock (see platform.socket_path)
- Newline-delimited JSON per request/response

This module is used by the CLI to communicate with the running GUI app.
"""

from __future__ import annotations

import json
import os
import socket
from typing import Any, Dict, Tuple

from .platform import socket_path


def send_request(obj: Dict[str, Any], timeout: float = 3.0) -> Tuple[bool, Dict[str, Any]]:
    """
    Send a single JSON request and wait for a single JSON response.

    Returns:
      (ok, response_dict)
      ok = True if transport succeeded AND response contains {"ok": true}
      ok = False otherwise (response will include error information if available)
    """
    path = str(socket_path())
    data = (json.dumps(obj) + "\n").encode("utf-8")

    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(path)
            s.sendall(data)

            # Read until newline
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk

        if not buf:
            return False, {"ok": False, "error": "empty response from server"}

        try:
            resp = json.loads(buf.decode("utf-8").rstrip("\n"))
        except Exception as e:
            return False, {"ok": False, "error": f"invalid json response: {e}"}

        if isinstance(resp, dict) and resp.get("ok") is True:
            return True, resp
        return False, resp if isinstance(resp, dict) else {"ok": False, "error": "malformed response"}

    except FileNotFoundError:
        return False, {"ok": False, "error": "server not running", "code": "NOT_RUNNING", "socket": path}
    except socket.timeout:
        return False, {"ok": False, "error": "timeout", "code": "TIMEOUT"}
    except Exception as e:
        return False, {"ok": False, "error": str(e)}


def cli_exit_code_from_response(ok: bool, resp: Dict[str, Any]) -> int:
    """
    Map (ok, resp) to CLI exit code.
    0: success
    1: general error (including transport/server not running)
    2: invalid arguments (server reports INVALID_ARG)
    3: action failed or other server-side failure
    """
    if ok:
        return 0

    code = str(resp.get("code", "")).upper()
    if code == "INVALID_ARG":
        return 2
    # Distinguish explicit server-not-running if present
    if code in ("NOT_RUNNING", "TIMEOUT"):
        return 1
    # Fallback for other failures
    return 3
