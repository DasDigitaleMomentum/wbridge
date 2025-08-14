"""Profiles/Preset-Management for wbridge.

Implements:
- list_builtin_profiles() -> list[str]
- show_profile(name: str) -> dict
- install_profile(name: str, *, overwrite_actions: bool, patch_settings: bool,
                  install_shortcuts: bool, dry_run: bool) -> dict (Report)

Profile structure (as package resources):
  wbridge/profiles/<name>/
    - profile.toml
    - actions.json
    - shortcuts.json (optional)
    - settings.patch.ini (optional)

Merge/Backup rules per DESIGN.md (Abschnitt 25/27):
- actions.json:
  - Identify collisions by exact "name".
  - Default: User first (skip existing entries); overwrite if overwrite_actions=True.
  - triggers: add new keys; collisions: default keep user; overwrite if overwrite_actions=True.
  - Backup: actions.json.bak-YYYYmmdd-HHMMSS (before write)
- settings.patch.ini:
  - Only allowed keys (whitelist) in [integration]: http_trigger_enabled, http_trigger_base_url,
    http_trigger_trigger_path, http_trigger_health_path
  - Default: do nothing; if patch_settings=True, patch these keys from profile file.
  - Backup before write.
- shortcuts.json:
  - Only install if install_shortcuts=True. Report installed/skipped. No forced overwrite; GNOME handles conflicts.

All file writes are atomic (write temp + replace).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import configparser

try:
    import importlib.resources as ilr
except Exception:  # pragma: no cover
    ilr = None  # type: ignore

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    tomllib = None  # type: ignore

from .platform import xdg_config_dir, ensure_dirs
from . import gnome_shortcuts


# ---------- Helpers ----------

def _ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _backup_file(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    bak = path.with_suffix(path.suffix + f".bak-{_ts()}")
    try:
        shutil.copy2(path, bak)
        return bak
    except Exception:
        return None


def _write_atomic(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception:
            pass


def _pkg_root() -> Optional[Any]:
    if ilr is None:
        return None
    try:
        return ilr.files("wbridge.profiles")
    except Exception:
        return None


def _profile_dir(name: str) -> Optional[Any]:
    base = _pkg_root()
    if not base:
        return None
    p = base.joinpath(name)  # type: ignore[attr-defined]
    return p


def _read_pkg_text(path: Any) -> Optional[str]:
    # Traversable in stdlib has read_text() in Python 3.11+
    try:
        return path.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        try:
            with ilr.as_file(path) as real_path:  # type: ignore
                return Path(real_path).read_text(encoding="utf-8")
        except Exception:
            return None


def _load_json_pkg(path: Any) -> Optional[dict]:
    try:
        txt = _read_pkg_text(path)
        if txt is None:
            return None
        return json.loads(txt)
    except Exception:
        return None


def _load_ini_pkg(path: Any) -> Optional[configparser.ConfigParser]:
    txt = _read_pkg_text(path)
    if txt is None:
        return None
    cp = configparser.ConfigParser()
    try:
        cp.read_string(txt)
        return cp
    except Exception:
        return None


def _load_toml_pkg(path: Any) -> Optional[dict]:
    txt = _read_pkg_text(path)
    if txt is None:
        return None
    if tomllib:
        try:
            return tomllib.loads(txt)  # type: ignore
        except Exception:
            pass
    # Fallback: naive parse for key = "value" lines (sufficient for simple profile.toml)
    meta: Dict[str, Any] = {}
    try:
        for line in txt.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            key = k.strip()
            val = v.strip().strip('"').strip("'")
            if key == "includes":
                # naive parse of array ["a","b"]
                arr = re.findall(r'"([^"]+)"', v)
                meta[key] = arr
            else:
                meta[key] = val
        return meta
    except Exception:
        return None


# ---------- Public API ----------

def list_builtin_profiles() -> List[str]:
    """
    Enumerate available built-in profiles under package resources.
    Only include directories that contain a profile.toml (filters out __pycache__, etc.).
    """
    base = _pkg_root()
    if not base:
        return []
    names: List[str] = []
    try:
        for child in base.iterdir():  # type: ignore[attr-defined]
            try:
                if not child.is_dir():  # type: ignore[attr-defined]
                    continue
                pt = child.joinpath("profile.toml")  # type: ignore[attr-defined]
                has_meta = False
                # Prefer as_file to check real existence when zipped
                try:
                    with ilr.as_file(pt) as real_path:  # type: ignore
                        has_meta = Path(real_path).exists()
                except Exception:
                    # Fallback: try reading text to verify presence
                    try:
                        _ = pt.read_text(encoding="utf-8")  # type: ignore[attr-defined]
                        has_meta = True
                    except Exception:
                        has_meta = False
                if has_meta:
                    names.append(child.name)  # type: ignore[attr-defined]
            except Exception:
                continue
    except Exception:
        return []
    names.sort()
    return names


def show_profile(name: str) -> Dict[str, Any]:
    """
    Return a summary of profile metadata and core contents.
    """
    result: Dict[str, Any] = {"ok": False, "name": name, "error": None}
    pdir = _profile_dir(name)
    try:
        is_dir = bool(getattr(pdir, "is_dir", lambda: False)()) if pdir else False
    except Exception:
        is_dir = False
    if not pdir or not is_dir:
        result["error"] = f"profile not found: {name}"
        return result

    meta = _load_toml_pkg(pdir.joinpath("profile.toml")) or {}  # type: ignore[attr-defined]
    actions = _load_json_pkg(pdir.joinpath("actions.json")) or {}  # type: ignore[attr-defined]
    shortcuts = _load_json_pkg(pdir.joinpath("shortcuts.json")) or {}  # type: ignore[attr-defined]
    settings_patch_cp = _load_ini_pkg(pdir.joinpath("settings.patch.ini"))  # type: ignore[attr-defined]
    settings_patch: Dict[str, Dict[str, str]] = {}
    if settings_patch_cp:
        for section in settings_patch_cp.sections():
            settings_patch[section] = dict(settings_patch_cp.items(section))

    # Summaries
    actions_list = actions.get("actions") or []
    triggers_map = actions.get("triggers") or {}
    shortcuts_list = shortcuts.get("shortcuts") or []

    result.update({
        "ok": True,
        "meta": meta,
        "actions": {
            "count": len(actions_list),
            "triggers": list(triggers_map.keys()),
            "sample": [a.get("name") for a in actions_list[:5]],
        },
        "shortcuts": {
            "count": len(shortcuts_list),
            "sample": shortcuts_list[:3],
        },
        "settings_patch": settings_patch,
    })
    return result


@dataclass
class InstallOptions:
    overwrite_actions: bool = False
    patch_settings: bool = False
    install_shortcuts: bool = False
    dry_run: bool = False


_ALLOWED_INTEGRATION_KEYS = {
    "http_trigger_enabled",
    "http_trigger_base_url",
    "http_trigger_trigger_path",
    "http_trigger_health_path",
}


def _merge_actions(user: dict, prof: dict, overwrite: bool) -> Dict[str, Any]:
    """
    Merge profile actions/triggers into user config per policy.
    Returns merged dict and counters in '_stats'.
    """
    user_actions = user.get("actions") or []
    user_triggers = user.get("triggers") or {}

    prof_actions = prof.get("actions") or []
    prof_triggers = prof.get("triggers") or {}

    # Build index by name for user actions
    idx: Dict[str, int] = {}
    for i, a in enumerate(user_actions):
        name = str(a.get("name") or "")
        if name:
            idx[name] = i

    added = updated = skipped = 0
    merged_actions = list(user_actions)

    for a in prof_actions:
        name = str(a.get("name") or "")
        if not name:
            continue
        if name in idx:
            if overwrite:
                merged_actions[idx[name]] = a
                updated += 1
            else:
                skipped += 1
        else:
            merged_actions.append(a)
            added += 1

    # Merge triggers
    merged_triggers = dict(user_triggers)
    trig_added = trig_updated = trig_skipped = 0
    for key, val in prof_triggers.items():
        if key in merged_triggers:
            if overwrite:
                merged_triggers[key] = val
                trig_updated += 1
            else:
                trig_skipped += 1
        else:
            merged_triggers[key] = val
            trig_added += 1

    out = {
        "actions": merged_actions,
        "triggers": merged_triggers,
        "_stats": {
            "actions": {"added": added, "updated": updated, "skipped": skipped},
            "triggers": {"added": trig_added, "updated": trig_updated, "skipped": trig_skipped},
        }
    }
    return out


def _install_shortcuts(shortcuts: List[dict]) -> Dict[str, int]:
    """
    Install shortcut entries using gnome_shortcuts.install_binding.
    We synthesize a unique, stable path suffix from the 'name'.
    """
    installed = skipped = 0
    for sc in shortcuts:
        try:
            name = str(sc.get("name") or "")
            cmd = str(sc.get("command") or "")
            binding = str(sc.get("binding") or "")
            if not name or not cmd or not binding:
                skipped += 1
                continue
            # synthesize suffix: "wbridge-" + normalized name
            norm = re.sub(r"[^a-z0-9\-]+", "-", name.lower()).strip("-")
            suffix = f"wbridge-{norm}/"
            gnome_shortcuts.install_binding(suffix, name, cmd, binding)
            installed += 1
        except Exception:
            skipped += 1
    return {"installed": installed, "skipped": skipped}


def install_profile(name: str, *, overwrite_actions: bool = False, patch_settings: bool = False,
                    install_shortcuts: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    """
    Install a profile into the user's configuration per options.
    Returns a report dict as specified in DESIGN.md.
    """
    report: Dict[str, Any] = {
        "ok": False,
        "profile": name,
        "actions": {"added": 0, "updated": 0, "skipped": 0, "backup": None},
        "triggers": {"added": 0, "updated": 0, "skipped": 0},
        "settings": {"patched": [], "skipped": [], "backup": None},
        "shortcuts": {"installed": 0, "skipped": 0},
        "dry_run": bool(dry_run),
        "errors": [],
    }

    pdir = _profile_dir(name)
    try:
        is_dir = bool(getattr(pdir, "is_dir", lambda: False)()) if pdir else False
    except Exception:
        is_dir = False
    if not pdir or not is_dir:
        report["errors"].append(f"profile not found: {name}")
        return report

    ensure_dirs()
    cfg_dir = xdg_config_dir()
    actions_path = cfg_dir / "actions.json"
    settings_path = cfg_dir / "settings.ini"

    # Load profile resources
    prof_actions = _load_json_pkg(pdir.joinpath("actions.json")) or {"actions": [], "triggers": {}}  # type: ignore[attr-defined]
    prof_shortcuts_json = _load_json_pkg(pdir.joinpath("shortcuts.json")) or {}  # type: ignore[attr-defined]
    prof_shortcuts = prof_shortcuts_json.get("shortcuts") or []
    prof_settings_cp = _load_ini_pkg(pdir.joinpath("settings.patch.ini"))  # type: ignore[attr-defined]

    # 1) actions.json merge
    try:
        if actions_path.exists():
            try:
                user_actions = json.loads(actions_path.read_text(encoding="utf-8"))
            except Exception:
                user_actions = {"actions": [], "triggers": {}}
        else:
            user_actions = {"actions": [], "triggers": {}}

        merged = _merge_actions(user_actions, prof_actions, overwrite_actions)
        merged_out = {"actions": merged["actions"], "triggers": merged["triggers"]}

        stats = merged["_stats"]
        report["actions"].update(stats["actions"])
        report["triggers"].update(stats["triggers"])

        if not dry_run:
            bak = _backup_file(actions_path)
            if bak:
                report["actions"]["backup"] = str(bak)
            _write_atomic(actions_path, json.dumps(merged_out, ensure_ascii=False, indent=2))
    except Exception as e:
        report["errors"].append(f"actions merge error: {e}")

    # 2) settings.patch.ini (whitelist keys)
    if patch_settings and prof_settings_cp:
        try:
            if settings_path.exists():
                sp = configparser.ConfigParser()
                sp.read(settings_path)
            else:
                sp = configparser.ConfigParser()
            # Ensure [integration] exists
            if not sp.has_section("integration"):
                sp.add_section("integration")

            patched_keys: List[str] = []
            skipped_keys: List[str] = []
            if prof_settings_cp.has_section("integration"):
                for key, val in prof_settings_cp.items("integration"):
                    if key in _ALLOWED_INTEGRATION_KEYS:
                        try:
                            # preserve exact textual value
                            sp.set("integration", key, val)
                            patched_keys.append(key)
                        except Exception:
                            skipped_keys.append(key)
                    else:
                        skipped_keys.append(key)

            if not dry_run:
                bak = _backup_file(settings_path)
                if bak:
                    report["settings"]["backup"] = str(bak)
                # Write INI
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=settings_path.parent, prefix=settings_path.name + ".") as tf:
                    sp.write(tf)
                    tf.flush()
                    os.fsync(tf.fileno())
                    tmpname = tf.name
                os.replace(tmpname, settings_path)
            report["settings"]["patched"] = patched_keys
            report["settings"]["skipped"] = skipped_keys
        except Exception as e:
            report["errors"].append(f"settings patch error: {e}")
    else:
        # list which keys would be patched in dry-run or if patch_settings not set
        if prof_settings_cp and prof_settings_cp.has_section("integration"):
            can_patch = [k for k, _ in prof_settings_cp.items("integration") if k in _ALLOWED_INTEGRATION_KEYS]
            report["settings"]["skipped"] = can_patch

    # 3) shortcuts install
    if install_shortcuts and prof_shortcuts:
        try:
            res = _install_shortcuts(prof_shortcuts)
            report["shortcuts"].update(res)
        except Exception as e:
            # Gio not available or runtime error
            report["errors"].append(f"shortcuts install error: {e}")

    report["ok"] = len(report["errors"]) == 0
    return report
