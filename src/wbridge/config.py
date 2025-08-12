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
