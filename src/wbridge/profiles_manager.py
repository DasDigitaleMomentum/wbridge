"""Profiles/Preset-Management for wbridge.

Implements:
- list_builtin_profiles() -> list[str]
- show_profile(name: str) -> dict
- install_profile(name: str, *, overwrite_actions: bool, merge_endpoints: bool,
                  merge_secrets: bool, merge_shortcuts: bool, dry_run: bool) -> dict (Report)

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
  - Allowed sections: endpoint.*, secrets, gnome.shortcuts, optional gnome.manage_shortcuts
  - Default: do nothing; if merge_* flags are set, merge the corresponding sections/keys into settings.ini.
  - Backup before write.
- shortcuts.json:
  - Only merge into settings.ini if merge_shortcuts=True. Report merged/skipped. No direct dconf write; GNOME will be synced by UI based on settings.

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
    merge_endpoints: bool = False
    merge_secrets: bool = False
    merge_shortcuts: bool = False
    dry_run: bool = False




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


def remove_profile_shortcuts(name: str) -> Dict[str, int]:
    """
    Remove shortcuts installed by a profile's shortcuts.json using the deterministic
    suffix scheme: 'wbridge-' + slugify(shortcut.name) + '/'.
    Returns {"removed": N, "skipped": M}.
    """
    removed = skipped = 0
    pdir = _profile_dir(name)
    try:
        is_dir = bool(getattr(pdir, "is_dir", lambda: False)()) if pdir else False
    except Exception:
        is_dir = False
    if not pdir or not is_dir:
        return {"removed": 0, "skipped": 0}

    shortcuts = _load_json_pkg(pdir.joinpath("shortcuts.json")) or {}  # type: ignore[attr-defined]
    items = shortcuts.get("shortcuts") or []
    for sc in items:
        try:
            sc_name = str(sc.get("name") or "")
            if not sc_name:
                skipped += 1
                continue
            norm = re.sub(r"[^a-z0-9\-]+", "-", sc_name.lower()).strip("-")
            suffix = f"wbridge-{norm}/"
            gnome_shortcuts.remove_binding(suffix)
            removed += 1
        except Exception:
            skipped += 1
    return {"removed": removed, "skipped": skipped}


def load_profile_shortcuts(name: str) -> List[dict]:
    """
    Return raw list of shortcuts from a built-in profile's shortcuts.json.
    If not found, returns [].
    """
    pdir = _profile_dir(name)
    try:
        is_dir = bool(getattr(pdir, "is_dir", lambda: False)()) if pdir else False
    except Exception:
        is_dir = False
    if not pdir or not is_dir:
        return []
    shortcuts = _load_json_pkg(pdir.joinpath("shortcuts.json")) or {}  # type: ignore[attr-defined]
    items = shortcuts.get("shortcuts") or []
    return list(items)


# ---------- V2 shortcut merging helpers (INI as SoT) ----------

def _shortcut_alias_from_command(cmd: str) -> Optional[str]:
    """
    Try to derive a trigger alias from a shortcut command.
    Supported patterns:
      - "wbridge ui show"                  -> "ui_show"
      - "wbridge trigger <alias> ..."      -> "<alias>"
    Returns None if alias cannot be determined.
    """
    try:
        import re
        s = str(cmd or "").strip()
        if not s:
            return None
        if s.startswith("wbridge ui show"):
            return "ui_show"
        m = re.search(r"\\bwbridge\\s+trigger\\s+([^\\s]+)", s)
        if m:
            return m.group(1)
        return None
    except Exception:
        return None


def _merge_shortcuts_section(sp: configparser.ConfigParser, mapping: Dict[str, str]) -> Dict[str, int]:
    """
    Merge alias->binding entries into settings.ini under [gnome.shortcuts].
    Returns counts: {"installed": merged, "skipped": skipped}
    """
    merged = skipped = 0
    try:
        if not sp.has_section("gnome.shortcuts"):
            sp.add_section("gnome.shortcuts")
        for alias, binding in mapping.items():
            try:
                if binding:
                    sp.set("gnome.shortcuts", alias, binding)
                    merged += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1
    except Exception:
        pass
    return {"installed": merged, "skipped": skipped}


def _merge_shortcuts_from_items(sp: configparser.ConfigParser, items: List[dict]) -> Dict[str, int]:
    """
    Merge GNOME shortcuts defined as a list of dicts (profile shortcuts.json)
    into settings.ini's [gnome.shortcuts] using derived trigger aliases.
    """
    mapping: Dict[str, str] = {}
    for sc in items or []:
        try:
            cmd = str(sc.get("command") or "")
            binding = str(sc.get("binding") or "")
            alias = _shortcut_alias_from_command(cmd)
            if alias and binding:
                mapping[alias] = binding
        except Exception:
            continue
    return _merge_shortcuts_section(sp, mapping)


def install_profile(name: str, *, overwrite_actions: bool = False,
                    merge_endpoints: bool = False, merge_secrets: bool = False,
                    merge_shortcuts: bool = False, dry_run: bool = False) -> Dict[str, Any]:
    """
    Install a profile into the user's configuration per options.
    Returns a report dict as specified in DESIGN.md.
    """
    report: Dict[str, Any] = {
        "ok": False,
        "profile": name,
        "actions": {"added": 0, "updated": 0, "skipped": 0, "backup": None},
        "triggers": {"added": 0, "updated": 0, "skipped": 0},
        "settings": {"merged": [], "skipped": [], "backup": None},
        "shortcuts": {"merged": 0, "skipped": 0},
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

    # 2) settings.patch.ini (V2 merge: endpoint.*, secrets, gnome.shortcuts (if requested), optional gnome.manage_shortcuts)
    if prof_settings_cp and (merge_endpoints or merge_secrets or (merge_shortcuts and prof_settings_cp.has_section("gnome.shortcuts"))):
        try:
            # Read or create settings.ini
            if settings_path.exists():
                sp = configparser.ConfigParser()
                sp.read(settings_path)
            else:
                sp = configparser.ConfigParser()

            merged_keys: List[str] = []
            skipped_keys: List[str] = []

            if prof_settings_cp and (merge_endpoints or merge_secrets or merge_shortcuts):
                # Merge endpoint.*, secrets and optional gnome.manage_shortcuts
                for sec in prof_settings_cp.sections():
                    try:
                        if sec.startswith("endpoint.") and merge_endpoints:
                            if not sp.has_section(sec):
                                sp.add_section(sec)
                            for key, val in prof_settings_cp.items(sec):
                                try:
                                    sp.set(sec, key, val)
                                    merged_keys.append(f"{sec}.{key}")
                                except Exception:
                                    skipped_keys.append(f"{sec}.{key}")
                        elif sec == "secrets" and merge_secrets:
                            if not sp.has_section("secrets"):
                                sp.add_section("secrets")
                            for key, val in prof_settings_cp.items("secrets"):
                                try:
                                    sp.set("secrets", key, val)
                                    merged_keys.append(f"secrets.{key}")
                                except Exception:
                                    skipped_keys.append(f"secrets.{key}")
                        elif sec == "gnome" and merge_shortcuts:
                            # accept manage_shortcuts boolean from profile
                            for key, val in prof_settings_cp.items("gnome"):
                                if key == "manage_shortcuts":
                                    try:
                                        if not sp.has_section("gnome"):
                                            sp.add_section("gnome")
                                        sp.set("gnome", key, val)
                                        merged_keys.append(f"gnome.{key}")
                                    except Exception:
                                        skipped_keys.append(f"gnome.{key}")
                        else:
                            # ignore others; [gnome.shortcuts] handled below if requested
                            pass
                    except Exception:
                        continue

            # Optionally merge [gnome.shortcuts] from profile settings.ini if install_shortcuts requested
            if prof_settings_cp and merge_shortcuts and prof_settings_cp.has_section("gnome.shortcuts"):
                src_map = dict(prof_settings_cp.items("gnome.shortcuts"))
                res = _merge_shortcuts_section(sp, src_map)
                # map to report counters
                report["shortcuts"]["merged"] = report["shortcuts"].get("merged", 0) + int(res.get("installed", 0))
                report["shortcuts"]["skipped"] = report["shortcuts"].get("skipped", 0) + int(res.get("skipped", 0))

            if not dry_run:
                bak = _backup_file(settings_path)
                if bak:
                    report["settings"]["backup"] = str(bak)
                # atomic write
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=settings_path.parent, prefix=settings_path.name + ".") as tf:
                    sp.write(tf)
                    tf.flush()
                    os.fsync(tf.fileno())
                    tmpname = tf.name
                os.replace(tmpname, settings_path)

            report["settings"]["merged"] = merged_keys
            report["settings"]["skipped"] = skipped_keys
        except Exception as e:
            report["errors"].append(f"settings patch error: {e}")
    else:
        # list sections that could be merged (dry-run/info)
        if prof_settings_cp:
            sec_list: List[str] = []
            for sec in prof_settings_cp.sections():
                if sec.startswith("endpoint.") or sec in ("secrets", "gnome.shortcuts", "gnome"):
                    sec_list.append(sec)
            report["settings"]["skipped"] = sec_list

    # 3) shortcuts merge into settings.ini (SoT)
    if merge_shortcuts and prof_shortcuts:
        try:
            # Load or create settings.ini to merge shortcut bindings under [gnome.shortcuts]
            if settings_path.exists():
                sp = configparser.ConfigParser()
                sp.read(settings_path)
            else:
                sp = configparser.ConfigParser()

            res = _merge_shortcuts_from_items(sp, prof_shortcuts)

            if not dry_run:
                # Backup once if not already done
                if not report["settings"].get("backup"):
                    bak = _backup_file(settings_path)
                    if bak:
                        report["settings"]["backup"] = str(bak)
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=settings_path.parent, prefix=settings_path.name + ".") as tf:
                    sp.write(tf)
                    tf.flush()
                    os.fsync(tf.fileno())
                    tmpname = tf.name
                os.replace(tmpname, settings_path)

            # Report merged counts
            report["shortcuts"]["merged"] = report["shortcuts"].get("merged", 0) + int(res.get("installed", 0))
            report["shortcuts"]["skipped"] = report["shortcuts"].get("skipped", 0) + int(res.get("skipped", 0))
        except Exception as e:
            report["errors"].append(f"shortcuts merge error: {e}")

    report["ok"] = len(report["errors"]) == 0
    return report
