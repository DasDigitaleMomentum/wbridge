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
    "integration": {
        "http_trigger_enabled": "false",
        "http_trigger_base_url": "http://127.0.0.1:18081",
        "http_trigger_health_path": "/health",
        "http_trigger_trigger_path": "/trigger",
    },
    "gnome": {
        "manage_shortcuts": "true",
        "binding_prompt": "<Ctrl><Alt>p",
        "binding_command": "<Ctrl><Alt>m",
        "binding_ui_show": "<Ctrl><Alt>u",
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


def set_integration_settings(*, http_trigger_enabled: Optional[bool] = None,
                             http_trigger_base_url: Optional[str] = None,
                             http_trigger_trigger_path: Optional[str] = None,
                             http_trigger_health_path: Optional[str] = None) -> None:
    """
    Update whitelisted keys in [integration] atomically. Any None value will be left unchanged.
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

    if not parser.has_section("integration"):
        parser.add_section("integration")

    def _set_if_not_none(key: str, value: Optional[str]) -> None:
        if value is not None:
            parser.set("integration", key, value)

    if http_trigger_enabled is not None:
        parser.set("integration", "http_trigger_enabled", "true" if http_trigger_enabled else "false")
    _set_if_not_none("http_trigger_base_url", http_trigger_base_url)
    _set_if_not_none("http_trigger_trigger_path", http_trigger_trigger_path)
    _set_if_not_none("http_trigger_health_path", http_trigger_health_path)

    _write_ini_atomic(parser, ini_path)
