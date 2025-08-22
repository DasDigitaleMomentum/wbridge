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


# ---------------- V2 generic helpers (INI as SoT) ----------------

def _slug(s: str) -> str:
    try:
        import re
        return re.sub(r"[^a-z0-9\\-]+", "-", s.lower()).strip("-")
    except Exception:
        return s


def install_from_mapping(bindings: Dict[str, str]) -> Dict[str, int]:
    """
    Install/update shortcuts for arbitrary trigger aliases from a mapping:
      { "alias": "<Ctrl><Alt>X", ... }
    Command resolution:
      - alias == "ui_show" -> "wbridge ui show"
      - otherwise          -> "wbridge trigger <alias>"
    Returns counts: {"installed": N, "skipped": M}
    """
    _ensure_gio()
    installed = skipped = 0
    for alias, binding in (bindings or {}).items():
        try:
            alias = str(alias or "").strip()
            binding = str(binding or "").strip()
            if not alias or not binding:
                skipped += 1
                continue
            if alias == "ui_show":
                name = "Bridge: Show UI"
                cmd = "wbridge ui show"
            else:
                name = f"Bridge: {alias}"
                cmd = f"wbridge trigger {alias}"
            suffix = f"wbridge-{_slug(alias)}/"
            install_binding(suffix, name, cmd, binding)
            installed += 1
        except Exception:
            skipped += 1
    return {"installed": installed, "skipped": skipped}


def remove_all_wbridge_shortcuts() -> Dict[str, int]:
    """
    Remove all shortcuts whose custom-keybinding path suffix starts with 'wbridge-'.
    Returns {"removed": N, "kept": M}.
    """
    _ensure_gio()
    base = _get_base_settings()
    paths = _get_paths(base)
    kept: List[str] = []
    removed = 0
    for p in paths:
        try:
            if not isinstance(p, str):
                kept.append(p)
                continue
            # Example path: /org/.../custom-keybindings/wbridge-foo/
            if p.startswith(PATH_PREFIX + "wbridge-"):
                removed += 1
                continue
            kept.append(p)
        except Exception:
            kept.append(p)
    _set_paths(base, kept)
    return {"removed": removed, "kept": len(kept)}


# ---------------- V2 sync helpers ----------------

def _suffix_for_alias(alias: str) -> str:
    """
    Deterministic custom-keybinding path suffix for an alias.
    """
    return f"wbridge-{_slug(alias)}/"


def list_installed() -> List[Dict[str, str]]:
    """
    List all currently installed wbridge-specific custom keybindings.
    Returns a list of dicts: { "name": str, "command": str, "binding": str, "suffix": str }.
    """
    _ensure_gio()
    base = _get_base_settings()
    paths = _get_paths(base)
    out: List[Dict[str, str]] = []
    for p in paths:
        try:
            if not isinstance(p, str):
                continue
            if not p.startswith(PATH_PREFIX):
                continue
            suffix = p[len(PATH_PREFIX):]
            if not suffix.startswith("wbridge-"):
                continue
            custom = _custom_settings_for(p)
            name = custom.get_string("name")
            command = custom.get_string("command")
            binding = custom.get_string("binding")
            out.append({"name": name, "command": command, "binding": binding, "suffix": suffix})
        except Exception:
            # skip broken entry
            continue
    return out


def sync_from_ini(settings_map: Dict[str, Dict[str, str]], auto_remove: bool = True) -> Dict[str, int]:
    """
    Synchronize GNOME custom shortcuts with the [gnome.shortcuts] section from settings.ini.
    - Installs or updates entries for aliases in INI
    - Optionally removes wbridge-* entries not present in INI (auto_remove=True)
    Returns counts: {"installed": n, "updated": m, "removed": r, "skipped": s}
    """
    _ensure_gio()

    # Extract desired mapping alias -> binding from settings_map["gnome.shortcuts"]
    desired_section = {}
    try:
        if isinstance(settings_map, dict):
            desired_section = dict(settings_map.get("gnome.shortcuts", {}) or {})
    except Exception:
        desired_section = {}

    desired: Dict[str, str] = {}
    for k, v in desired_section.items():
        alias = str(k or "").strip()
        binding = str(v or "").strip()
        if alias and binding:
            desired[alias] = binding

    installed = updated = removed = skipped = 0

    # Install or update desired entries
    for alias, binding in desired.items():
        try:
            suffix = _suffix_for_alias(alias)
            full_path = PATH_PREFIX + suffix
            # Canonical name/command mapping
            if alias == "ui_show":
                name = "Bridge: Show UI"
                cmd = "wbridge ui show"
            else:
                name = f"Bridge: {alias}"
                cmd = f"wbridge trigger {alias}"

            base = _get_base_settings()
            paths = _get_paths(base)
            if full_path in paths:
                # Update binding/name/command if needed
                try:
                    custom = _custom_settings_for(full_path)
                    changed = False
                    if custom.get_string("binding") != binding:
                        custom.set_string("binding", binding)
                        changed = True
                    try:
                        if custom.get_string("name") != name:
                            custom.set_string("name", name)
                            changed = True
                        if custom.get_string("command") != cmd:
                            custom.set_string("command", cmd)
                            changed = True
                    except Exception:
                        pass
                    if changed:
                        updated += 1
                    else:
                        skipped += 1
                except Exception:
                    # Fallback: install
                    install_binding(suffix, name, cmd, binding)
                    installed += 1
            else:
                # Fresh install
                install_binding(suffix, name, cmd, binding)
                installed += 1
        except Exception:
            skipped += 1

    # Optionally remove entries that are no longer desired
    if auto_remove:
        desired_suffixes = {_suffix_for_alias(a) for a in desired.keys()}
        base2 = _get_base_settings()
        paths2 = _get_paths(base2)
        for p in paths2:
            try:
                if not isinstance(p, str):
                    continue
                if not p.startswith(PATH_PREFIX + "wbridge-"):
                    continue
                suf = p[len(PATH_PREFIX):]
                if suf not in desired_suffixes:
                    remove_binding(suf)
                    removed += 1
            except Exception:
                # ignore removal errors
                pass

    return {"installed": installed, "updated": updated, "removed": removed, "skipped": skipped}
