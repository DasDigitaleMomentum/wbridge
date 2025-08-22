"""
Configuration loading for wbridge.

- settings.ini in XDG config dir (~/.config/wbridge/settings.ini)
- actions.json in XDG config dir (~/.config/wbridge/actions.json)

Provides:
- Settings (INI) as a lightweight dict-like wrapper.
- Actions configuration (list of action dicts and an optional triggers map).
- Placeholder expansion, including {config.section.key}.
"""

from __future__ import annotations

import configparser
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .platform import xdg_config_dir, ensure_dirs


DEFAULT_SETTINGS = {
    "general": {
        "history_max": "50",
        "poll_interval_ms": "300",
    },
    "gnome": {
        "manage_shortcuts": "true",
    },
}


@dataclass
class Settings:
    config: configparser.ConfigParser
    path: Path

    def get(self, section: str, key: str, fallback: Optional[str] = None) -> str:
        return self.config.get(section, key, fallback=fallback)  # type: ignore[no-any-return]

    def getint(self, section: str, key: str, fallback: Optional[int] = None) -> int:
        try:
            return self.config.getint(section, key)  # type: ignore[no-any-return]
        except Exception:
            if fallback is None:
                raise
            return fallback

    def getboolean(self, section: str, key: str, fallback: Optional[bool] = None) -> bool:
        try:
            return self.config.getboolean(section, key)  # type: ignore[no-any-return]
        except Exception:
            if fallback is None:
                raise
            return fallback

    def as_mapping(self) -> Dict[str, Dict[str, str]]:
        # Return nested dict for placeholder expansion
        mapping: Dict[str, Dict[str, str]] = {}
        for section in self.config.sections():
            mapping[section] = {}
            for key, val in self.config.items(section):
                mapping[section][key] = val
        return mapping


@dataclass
class ActionsConfig:
    actions: List[Dict[str, Any]]
    triggers: Dict[str, str]


def load_settings() -> Settings:
    ensure_dirs()
    cfg_dir = xdg_config_dir()
    ini_path = cfg_dir / "settings.ini"

    parser = configparser.ConfigParser()
    # preload defaults
    for section, kv in DEFAULT_SETTINGS.items():
        parser.add_section(section)
        for k, v in kv.items():
            parser.set(section, k, v)

    if ini_path.exists():
        parser.read(ini_path)

    return Settings(parser, ini_path)


def load_actions() -> ActionsConfig:
    cfg_dir = xdg_config_dir()
    actions_path = cfg_dir / "actions.json"

    if not actions_path.exists():
        # Default empty config if not present
        return ActionsConfig(actions=[], triggers={})

    try:
        data = json.loads(actions_path.read_text(encoding="utf-8"))
    except Exception:
        return ActionsConfig(actions=[], triggers={})

    actions = data.get("actions") or []
    triggers = data.get("triggers") or {}
    if not isinstance(actions, list):
        actions = []
    if not isinstance(triggers, dict):
        triggers = {}
    return ActionsConfig(actions=actions, triggers=triggers)


# --------- Actions read/write helpers ---------

def load_actions_raw() -> Dict[str, Any]:
    """
    Load raw actions.json content as a dict with shape:
      { "actions": [ ... ], "triggers": { ... } }
    Returns defaults if file missing/invalid.
    """
    cfg_dir = xdg_config_dir()
    actions_path = cfg_dir / "actions.json"
    try:
        if actions_path.exists():
            data = json.loads(actions_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("actions", [])
                data.setdefault("triggers", {})
                if not isinstance(data["actions"], list):
                    data["actions"] = []
                if not isinstance(data["triggers"], dict):
                    data["triggers"] = {}
                return data
    except Exception:
        pass
    return {"actions": [], "triggers": {}}


def _write_json_atomic(data: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, prefix=path.name + ".") as tf:
        tf.write(payload)
        tf.flush()
        os.fsync(tf.fileno())
        tmpname = tf.name
    os.replace(tmpname, path)


def write_actions_config(data: Dict[str, Any]) -> Optional[Path]:
    """
    Atomically write actions.json. Creates a timestamped backup if the file exists.
    Returns backup path or None if no previous file existed.
    """
    ensure_dirs()
    cfg_dir = xdg_config_dir()
    actions_path = cfg_dir / "actions.json"
    backup: Optional[Path] = None
    if actions_path.exists():
        backup = actions_path.with_suffix(actions_path.suffix + ".bak-" + Path(tempfile.mkstemp()[1]).name.split(".")[-1])
        try:
            # Better timestamped backup name
            from datetime import datetime
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = actions_path.with_suffix(actions_path.suffix + f".bak-{ts}")
            actions_path.replace(backup)
        except Exception:
            backup = None
    # If we moved file to backup, we need to write fresh new file; otherwise overwrite atomically
    try:
        _write_json_atomic(data, actions_path)
    except Exception:
        # best-effort: if write failed and we created a backup, try to restore
        try:
            if backup and backup.exists():
                actions_path.replace(actions_path.with_suffix(actions_path.suffix + ".failed"))
                backup.replace(actions_path)
        except Exception:
            pass
        raise
    return backup


def validate_action_dict(action: Dict[str, Any]) -> tuple[bool, str]:
    """
    Minimal validation for an action definition.
    """
    name = str(action.get("name") or "").strip()
    typ = str(action.get("type") or "").strip().lower()
    if not name:
        return False, "action.name must not be empty"
    if typ not in ("http", "shell"):
        return False, "action.type must be 'http' or 'shell'"
    if typ == "http":
        url = str(action.get("url") or "").strip()
        if not url:
            return False, "http action requires url"
        method = str(action.get("method") or "GET").upper()
        if method not in ("GET", "POST"):
            return False, "http action.method must be GET or POST"
        # headers/params/json/data may be present; if present, must be proper types
        for k in ("headers", "params"):
            v = action.get(k)
            if v is not None and not isinstance(v, dict):
                return False, f"http action.{k} must be an object"
        for k in ("json", "data"):
            v = action.get(k)
            if v is not None and not isinstance(v, (dict, list, str)):
                return False, f"http action.{k} must be object/array/string"
        # optional minimal engine feature: plain text body
        if "body_is_text" in action and not isinstance(action.get("body_is_text"), bool):
            return False, "http action.body_is_text must be boolean"
        # mutual exclusivity: POST with body_is_text cannot also specify json
        if method == "POST" and bool(action.get("body_is_text")) and action.get("json") is not None:
            return False, "http action.body_is_text is mutually exclusive with json for POST"
    else:
        cmd = str(action.get("command") or "").strip()
        if not cmd:
            return False, "shell action requires command"
        args = action.get("args")
        if args is not None and not isinstance(args, list):
            return False, "shell action.args must be an array"
        if "use_shell" in action and not isinstance(action.get("use_shell"), bool):
            return False, "shell action.use_shell must be boolean"
    return True, ""


def expand_placeholders(text: str, selection_text: str, extra: Optional[Dict[str, Any]] = None,
                        settings_map: Optional[Dict[str, Dict[str, str]]] = None) -> str:
    """
    Very simple placeholder expansion for:
      - {text}
      - {config.section.key}
    Additional placeholders can be added later (app info, history, timestamps, etc.).
    """
    if text is None:
        return text
    out = text.replace("{text}", selection_text or "")
    if settings_map:
        # allow {config.section.key}
        # naive approach to avoid heavy templating
        for section, kv in settings_map.items():
            for k, v in kv.items():
                out = out.replace(f"{{config.{section}.{k}}}", v)
    if extra:
        for k, v in extra.items():
            out = out.replace(f"{{{k}}}", str(v))
    return out


# --------- Settings write helpers (atomic) ---------

def _write_ini_atomic(parser: configparser.ConfigParser, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, prefix=path.name + ".") as tf:
        parser.write(tf)
        tf.flush()
        os.fsync(tf.fileno())
        tmpname = tf.name
    os.replace(tmpname, path)


def _load_settings_parser_with_defaults() -> tuple[configparser.ConfigParser, Path]:
    """
    Internal helper: load settings.ini with DEFAULT_SETTINGS preloaded.
    """
    ensure_dirs()
    cfg_dir = xdg_config_dir()
    ini_path = cfg_dir / "settings.ini"

    parser = configparser.ConfigParser()
    # preload defaults to ensure required sections exist
    for section, kv in DEFAULT_SETTINGS.items():
        parser.add_section(section)
        for k, v in kv.items():
            parser.set(section, k, v)

    if ini_path.exists():
        try:
            parser.read(ini_path)
        except Exception:
            # continue with defaults
            pass

    return parser, ini_path


# --------- V2 INI helpers: endpoints and shortcuts ---------

def list_endpoints(settings: Settings) -> Dict[str, Dict[str, str]]:
    """
    Collect endpoints from settings into a mapping:
      {
        "<id>": {
          "base_url": "...",
          "health_path": "...",
          "trigger_path": "..."
        }
      }
    """
    result: Dict[str, Dict[str, str]] = {}
    for section in settings.config.sections():
        if section.startswith("endpoint."):
            id_ = section.split(".", 1)[1]
            kv: Dict[str, str] = {
                "base_url": settings.get(section, "base_url", fallback=""),
                "health_path": settings.get(section, "health_path", fallback="/health"),
                "trigger_path": settings.get(section, "trigger_path", fallback="/trigger"),
            }
            result[id_] = kv
    return result


def upsert_endpoint(id: str, base_url: str, health_path: str = "/health", trigger_path: str = "/trigger") -> None:
    """
    Create or update [endpoint.<id>] with provided values. Minimal validation applied.
    """
    if not id or any(c for c in id if c not in "abcdefghijklmnopqrstuvwxyz0123456789_-"):
        raise ValueError("endpoint id must be a slug [a-z0-9_-]+")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("base_url must start with http:// or https://")
    if not health_path.startswith("/"):
        raise ValueError("health_path must start with '/'")
    if not trigger_path.startswith("/"):
        raise ValueError("trigger_path must start with '/'")

    parser, ini_path = _load_settings_parser_with_defaults()
    section = f"endpoint.{id}"
    if not parser.has_section(section):
        parser.add_section(section)
    parser.set(section, "base_url", base_url)
    parser.set(section, "health_path", health_path or "/health")
    parser.set(section, "trigger_path", trigger_path or "/trigger")
    _write_ini_atomic(parser, ini_path)


def delete_endpoint(id: str) -> bool:
    """
    Delete [endpoint.<id>] section if present. Returns True if removed.
    """
    parser, ini_path = _load_settings_parser_with_defaults()
    section = f"endpoint.{id}"
    if parser.has_section(section):
        parser.remove_section(section)
        _write_ini_atomic(parser, ini_path)
        return True
    return False


def get_shortcuts_map(settings: Settings) -> Dict[str, str]:
    """
    Read [gnome.shortcuts] as alias -> binding mapping.
    """
    mapping: Dict[str, str] = {}
    section = "gnome.shortcuts"
    if settings.config.has_section(section):
        for k, v in settings.config.items(section):
            mapping[k] = v
    return mapping


def set_shortcuts_map(mapping: Dict[str, str]) -> None:
    """
    Overwrite [gnome.shortcuts] with the provided alias -> binding pairs.
    """
    parser, ini_path = _load_settings_parser_with_defaults()
    section = "gnome.shortcuts"
    if parser.has_section(section):
        parser.remove_section(section)
    parser.add_section(section)
    for alias, binding in mapping.items():
        parser.set(section, str(alias), str(binding))
    _write_ini_atomic(parser, ini_path)


def set_manage_shortcuts(on: bool) -> None:
    """
    Set [gnome].manage_shortcuts = true/false.
    """
    parser, ini_path = _load_settings_parser_with_defaults()
    if not parser.has_section("gnome"):
        parser.add_section("gnome")
    parser.set("gnome", "manage_shortcuts", "true" if on else "false")
    _write_ini_atomic(parser, ini_path)


# --------- V2 INI helpers: secrets ---------

def get_secrets_map(settings: Settings) -> Dict[str, str]:
    """
    Read [secrets] as key -> value mapping.
    """
    mapping: Dict[str, str] = {}
    section = "secrets"
    try:
        if settings.config.has_section(section):
            for k, v in settings.config.items(section):
                mapping[k] = v
    except Exception:
        pass
    return mapping


def set_secrets_map(mapping: Dict[str, str]) -> None:
    """
    Overwrite [secrets] with the provided key -> value pairs.
    """
    parser, ini_path = _load_settings_parser_with_defaults()
    section = "secrets"
    if parser.has_section(section):
        parser.remove_section(section)
    parser.add_section(section)
    for k, v in (mapping or {}).items():
        parser.set(section, str(k), str(v))
    _write_ini_atomic(parser, ini_path)
