"""
GNOME Custom Shortcuts automation using Gio.Settings.

This module provides helper functions to create/update/remove custom keybindings
that execute CLI commands (e.g., "wbridge trigger ...", "wbridge ui show").

Schema keys:
- org.gnome.settings-daemon.plugins.media-keys
  - custom-keybindings: array of object paths
- org.gnome.settings-daemon.plugins.media-keys.custom-keybinding
  - name (string), command (string), binding (string like "<Ctrl><Alt>p")
"""

from __future__ import annotations

from typing import Dict, List

try:
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio  # type: ignore
except Exception:
    Gio = None  # type: ignore


BASE_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
CUSTOM_SCHEMA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
BASE_KEY = "custom-keybindings"

# Path template: must end with a slash
PATH_PREFIX = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"
PATH_SUFFIXES = {
    "prompt": "wbridge-prompt/",
    "command": "wbridge-command/",
    "ui_show": "wbridge-ui-show/",
}


def _ensure_gio() -> None:
    if Gio is None:
        raise RuntimeError("Gio not available (PyGObject missing)")


def _get_base_settings():
    return Gio.Settings.new(BASE_SCHEMA)  # type: ignore


def _get_paths(base) -> List[str]:
    try:
        return list(base.get_strv(BASE_KEY))
    except Exception:
        return []


def _set_paths(base, paths: List[str]) -> None:
    base.set_strv(BASE_KEY, paths)


def _custom_settings_for(path: str):
    return Gio.Settings.new_with_path(CUSTOM_SCHEMA, path)  # type: ignore


def install_binding(path_suffix: str, name: str, command: str, binding: str) -> None:
    """
    Create or update a single custom keybinding entry.
    """
    _ensure_gio()
    base = _get_base_settings()
    paths = _get_paths(base)

    full_path = f"{PATH_PREFIX}{path_suffix}"
    if full_path not in paths:
        paths.append(full_path)
        _set_paths(base, paths)

    custom = _custom_settings_for(full_path)
    custom.set_string("name", name)
    custom.set_string("command", command)
    custom.set_string("binding", binding)


def remove_binding(path_suffix: str) -> None:
    """
    Remove a single custom keybinding entry.
    """
    _ensure_gio()
    base = _get_base_settings()
    paths = _get_paths(base)

    full_path = f"{PATH_PREFIX}{path_suffix}"
    if full_path in paths:
        paths.remove(full_path)
        _set_paths(base, paths)
    # Best-effort: GNOME cleans up orphan entries; explicit deletion isn't required by Gio.Settings API.


def install_recommended_shortcuts(bindings: Dict[str, str]) -> None:
    """
    Install/update a recommended set of bindings.

    bindings keys:
      - "prompt": "<Ctrl><Alt>p"
      - "command": "<Ctrl><Alt>m"
      - "ui_show": "<Ctrl><Alt>u"
    """
    _ensure_gio()
    mapping = {
        "prompt": ("Bridge: Prompt", "wbridge trigger prompt --from-primary"),
        "command": ("Bridge: Command", "wbridge trigger command --from-clipboard"),
        "ui_show": ("Bridge: Show UI", "wbridge ui show"),
    }
    for key, binding in bindings.items():
        if key not in PATH_SUFFIXES or key not in mapping:
            continue
        name, cmd = mapping[key]
        install_binding(PATH_SUFFIXES[key], name, cmd, binding)


def remove_recommended_shortcuts() -> None:
    _ensure_gio()
    for key, suffix in PATH_SUFFIXES.items():
        remove_binding(suffix)
