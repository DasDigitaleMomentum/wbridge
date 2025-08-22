"""
Actions engine for wbridge.

Supports two action types in V1:
- http: HTTP GET/POST to a configured URL (optionally with headers and JSON body)
- shell: execute a program with arguments (no shell by default)

Includes simple placeholder substitution. No retry/backoff in V1.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    import requests  # optional; used if installed and http actions are enabled
except Exception:  # pragma: no cover
    requests = None  # type: ignore


@dataclass
class ActionContext:
    text: str
    selection_type: str  # "clipboard" | "primary"
    settings_map: Optional[Dict[str, Dict[str, str]]] = None
    extra: Optional[Dict[str, Any]] = None


def _expand(s: str, ctx: ActionContext) -> str:
    if s is None:
        return s
    out = s.replace("{text}", ctx.text or "")
    # minimal config expansion
    if ctx.settings_map:
        for sec, kv in ctx.settings_map.items():
            for k, v in kv.items():
                out = out.replace(f"{{config.{sec}.{k}}}", v)
    if ctx.extra:
        for k, v in ctx.extra.items():
            out = out.replace(f"{{{k}}}", str(v))
    return out


def _expand_recursive(obj: Any, ctx: ActionContext) -> Any:
    if isinstance(obj, str):
        return _expand(obj, ctx)
    if isinstance(obj, list):
        return [_expand_recursive(x, ctx) for x in obj]
    if isinstance(obj, dict):
        return {k: _expand_recursive(v, ctx) for k, v in obj.items()}
    return obj


def run_http_action(action: Dict[str, Any], ctx: ActionContext, timeout: float = 5.0) -> Tuple[bool, str]:
    """
    action dict schema (example):
    {
      "type": "http",
      "method": "POST",
      "url": "http://127.0.0.1:18081/trigger",
      "headers": {"Content-Type": "application/json"},
      "json": {"cmd":"prompt","text":"{text}"}
    }
    """
    if requests is None:
        return False, "python-requests is not installed; install the 'http' extra"

    method = (action.get("method") or "POST").upper()
    url = str(action.get("url") or "")
    if not url:
        return False, "http action missing url"

    headers = action.get("headers") or {}
    json_body = action.get("json")
    data_body = action.get("data")
    params = action.get("params")
    body_is_text = bool(action.get("body_is_text", False))

    # expand placeholders across fields
    url = _expand(url, ctx)
    headers = _expand_recursive(headers, ctx)
    json_body = _expand_recursive(json_body, ctx)
    data_body = _expand_recursive(data_body, ctx)
    params = _expand_recursive(params, ctx)
    if method != "GET" and body_is_text and json_body is None and data_body is None:
        data_body = ctx.text

    try:
        if method == "GET":
            r = requests.get(url, headers=headers, params=params, timeout=timeout)  # type: ignore[call-arg]
        else:
            # Prefer JSON if provided; otherwise form data
            if json_body is not None:
                r = requests.post(url, headers=headers, json=json_body, params=params, timeout=timeout)  # type: ignore[call-arg]
            else:
                r = requests.post(url, headers=headers, data=data_body, params=params, timeout=timeout)  # type: ignore[call-arg]
        r.raise_for_status()
        return True, f"http {method} {url} -> {r.status_code}"
    except Exception as e:
        return False, str(e)


def run_shell_action(action: Dict[str, Any], ctx: ActionContext) -> Tuple[bool, str]:
    """
    action dict schema (example):
    {
      "type": "shell",
      "command": "/usr/bin/notify-send",
      "args": ["Selection Bridge", "Text: {text}"],
      "use_shell": false
    }
    """
    cmd = str(action.get("command") or "").strip()
    if not cmd:
        return False, "shell action missing command"

    args = action.get("args") or []
    use_shell = bool(action.get("use_shell", False))

    # expand placeholders
    cmd = _expand(cmd, ctx)
    args = [str(_expand(a, ctx)) for a in args]

    try:
        if use_shell:
            # caller must provide correct quoting in 'command' field
            full_cmd = cmd
            if args:
                # append expanded args for convenience
                full_cmd = " ".join([cmd] + [shlex.quote(a) for a in args])
            proc = subprocess.run(full_cmd, shell=True, capture_output=True, text=True)
        else:
            proc = subprocess.run([cmd, *args], shell=False, capture_output=True, text=True)

        if proc.returncode == 0:
            return True, proc.stdout.strip() or "ok"
        else:
            err = proc.stderr.strip() or f"exit {proc.returncode}"
            return False, err
    except Exception as e:
        return False, str(e)


def run_action(action: Dict[str, Any], ctx: ActionContext) -> Tuple[bool, str]:
    """
    Dispatch to the appropriate action runner.
    """
    typ = (action.get("type") or "").lower()
    if typ == "http":
        return run_http_action(action, ctx)
    if typ == "shell":
        return run_shell_action(action, ctx)
    return False, f"unsupported action type: {typ or 'missing'}"
