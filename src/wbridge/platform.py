"""
Platform utilities for wbridge.

- Paths for config, state/logs, and IPC socket
- Basic environment detection helpers
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


APP_NAME = "wbridge"
SOCKET_FILENAME = "wbridge.sock"
DESKTOP_FILENAME = "wbridge.desktop"


def xdg_config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def xdg_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".local" / "state" / APP_NAME


def runtime_dir() -> Path:
    # Prefer XDG_RUNTIME_DIR (per-user tmp with correct perms),
    # fall back to /tmp if not set.
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        return Path(base)
    return Path("/tmp")


def socket_path() -> Path:
    return runtime_dir() / SOCKET_FILENAME


def autostart_dir() -> Path:
    return Path.home() / ".config" / "autostart"


def autostart_desktop_path() -> Path:
    return autostart_dir() / DESKTOP_FILENAME


def ensure_dirs() -> None:
    xdg_config_dir().mkdir(parents=True, exist_ok=True)
    xdg_state_dir().mkdir(parents=True, exist_ok=True)
    autostart_dir().mkdir(parents=True, exist_ok=True)


def is_wayland_session() -> bool:
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        return True
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return False


def active_env_summary() -> str:
    session = os.environ.get("XDG_SESSION_TYPE", "unknown")
    de = os.environ.get("XDG_CURRENT_DESKTOP", "")
    return f"session={session}, desktop={de}"
