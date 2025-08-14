"""
Autostart management for wbridge.

Creates/removes ~/.config/autostart/wbridge.desktop with Exec=wbridge-app.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .platform import autostart_desktop_path, autostart_dir, ensure_dirs


DESKTOP_CONTENT = """[Desktop Entry]
Type=Application
Name=Selection/Shortcut Bridge
Exec=wbridge-app
X-GNOME-Autostart-enabled=true
OnlyShowIn=GNOME;X-GNOME;X-Cinnamon;XFCE;
"""


def is_enabled() -> bool:
    """
    Returns True if the autostart desktop file exists.
    """
    p = autostart_desktop_path()
    try:
        return p.exists()
    except Exception:
        return False


def enable() -> bool:
    """
    Create/overwrite the autostart desktop file atomically.
    Returns True on success, False otherwise.
    """
    tmp: Optional[Path] = None
    try:
        ensure_dirs()
        p = autostart_desktop_path()
        tmp = p.parent / (p.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            f.write(DESKTOP_CONTENT)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
        return True
    except Exception:
        try:
            if tmp is not None and tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return False


def disable() -> bool:
    """
    Remove the autostart desktop file. Returns True if removed or didn't exist.
    """
    try:
        p = autostart_desktop_path()
        if p.exists():
            p.unlink()
        return True
    except Exception:
        return False
