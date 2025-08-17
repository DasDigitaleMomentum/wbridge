#!/usr/bin/env python3
"""
wbridge CLI

Thin client that sends JSON requests over a Unix domain socket to the running GUI app.

Subcommands:
  - ui show
  - selection get/set
  - history list/apply/swap
  - trigger (alias for action mapped on the server) or run a named action

Exit codes:
  0: success
  1: transport/server not running or general error
  2: invalid arguments
  3: server-side action failed
"""

from __future__ import annotations

import argparse
import json
import sys
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

from .platform import xdg_config_dir, xdg_state_dir, autostart_desktop_path
from . import gnome_shortcuts, autostart

from .client_ipc import send_request, cli_exit_code_from_response
from .profiles_manager import (
    list_builtin_profiles as profiles_list,
    show_profile as profiles_show,
    install_profile as profiles_install,
    remove_profile_shortcuts,
)


def _print_response(ok: bool, resp: Dict[str, Any]) -> int:
    code = cli_exit_code_from_response(ok, resp)
    if ok:
        data = resp.get("data")
        if data is None:
            print("OK")
        else:
            # pretty-print data if present
            try:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            except Exception:
                print(str(data))
    else:
        msg = resp.get("error", "error")
        print(msg, file=sys.stderr)
    return code


def cmd_ui_show(args: argparse.Namespace) -> int:
    ok, resp = send_request({"op": "ui.show"})
    return _print_response(ok, resp)


def cmd_selection_get(args: argparse.Namespace) -> int:
    ok, resp = send_request({
        "op": "selection.get",
        "which": args.which
    })
    return _print_response(ok, resp)


def cmd_selection_set(args: argparse.Namespace) -> int:
    if args.text is None or args.text == "":
        print("--text is required for selection set", file=sys.stderr)
        return 2
    ok, resp = send_request({
        "op": "selection.set",
        "which": args.which,
        "text": args.text
    })
    return _print_response(ok, resp)


def cmd_history_list(args: argparse.Namespace) -> int:
    payload: Dict[str, Any] = {"op": "history.list", "which": args.which}
    if args.limit is not None:
        payload["limit"] = args.limit
    ok, resp = send_request(payload)
    return _print_response(ok, resp)


def cmd_history_apply(args: argparse.Namespace) -> int:
    ok, resp = send_request({
        "op": "history.apply",
        "which": args.which,
        "index": args.index
    })
    return _print_response(ok, resp)


def cmd_history_swap(args: argparse.Namespace) -> int:
    ok, resp = send_request({
        "op": "history.swap",
        "which": args.which
    })
    return _print_response(ok, resp)


def _source_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    if args.from_clipboard:
        return {"from": "clipboard"}
    if args.from_primary:
        return {"from": "primary"}
    if args.text is not None:
        return {"from": "text"}
    # default to clipboard if nothing specified
    return {"from": "clipboard"}


def cmd_trigger(args: argparse.Namespace) -> int:
    source = _source_from_args(args)
    req: Dict[str, Any]
    if args.name:
        # Run a named action directly
        req = {
            "op": "action.run",
            "name": args.name,
            "source": source
        }
        if args.text is not None:
            req["text"] = args.text
    else:
        if not args.cmd:
            print("trigger: either provide a positional CMD or use --name for a named action", file=sys.stderr)
            return 2
        req = {
            "op": "trigger",
            "cmd": args.cmd,
            "source": source
        }
        if args.text is not None:
            req["text"] = args.text

    ok, resp = send_request(req)
    return _print_response(ok, resp)


def cmd_profile_list(_args: argparse.Namespace) -> int:
    try:
        names = profiles_list()
        print(json.dumps(names, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1


def cmd_profile_show(args: argparse.Namespace) -> int:
    name = args.name
    if not name:
        print("--name is required", file=sys.stderr)
        return 2
    try:
        res = profiles_show(name)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else 3
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1


def cmd_profile_install(args: argparse.Namespace) -> int:
    name = args.name
    if not name:
        print("--name is required", file=sys.stderr)
        return 2
    try:
        report = profiles_install(
            name,
            overwrite_actions=bool(args.overwrite_actions),
            patch_settings=bool(args.patch_settings),
            install_shortcuts=bool(args.install_shortcuts),
            dry_run=bool(args.dry_run),
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 3
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1


# ------------- Config CLI helpers -------------

def _config_paths() -> Dict[str, str]:
    cfg = xdg_config_dir()
    return {
        "settings": str(cfg / "settings.ini"),
        "actions": str(cfg / "actions.json"),
        "state_log": str(xdg_state_dir() / "bridge.log"),
        "autostart_desktop": str(autostart_desktop_path()),
    }


def cmd_config_show_paths(args: argparse.Namespace) -> int:
    paths = _config_paths()
    if getattr(args, "json", False):
        print(json.dumps(paths, ensure_ascii=False, indent=2))
    else:
        for k, v in paths.items():
            print(f"{k}: {v}")
    return 0


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _backup_file(path: Path) -> Path:
    ts = _timestamp()
    bak = path.with_suffix(path.suffix + f".bak-{ts}")
    shutil.copy2(path, bak)
    return bak


def cmd_config_backup(args: argparse.Namespace) -> int:
    paths = _config_paths()
    what = (args.what or "all").lower()
    codes = 0
    try:
        if what in ("actions", "all"):
            p = Path(paths["actions"])
            if p.exists():
                b = _backup_file(p)
                print(f"actions backup: {b}")
        if what in ("settings", "all"):
            p = Path(paths["settings"])
            if p.exists():
                b = _backup_file(p)
                print(f"settings backup: {b}")
        return 0
    except Exception as e:
        print(f"backup failed: {e}", file=sys.stderr)
        return 3


def cmd_config_reset(args: argparse.Namespace) -> int:
    paths = _config_paths()
    keep_actions = bool(args.keep_actions)
    keep_settings = bool(args.keep_settings)
    do_backup = bool(args.backup)
    try:
        if not keep_actions:
            ap = Path(paths["actions"])
            if ap.exists():
                if do_backup:
                    b = _backup_file(ap)
                    print(f"actions backed up: {b}")
                ap.unlink()
                print("actions.json removed")
        if not keep_settings:
            sp = Path(paths["settings"])
            if sp.exists():
                if do_backup:
                    b = _backup_file(sp)
                    print(f"settings backed up: {b}")
                sp.unlink()
                print("settings.ini removed")
        return 0
    except Exception as e:
        print(f"reset failed: {e}", file=sys.stderr)
        return 3


def cmd_config_restore(args: argparse.Namespace) -> int:
    src = Path(args.file)
    if not src.exists():
        print("restore: --file does not exist", file=sys.stderr)
        return 2
    paths = _config_paths()
    try:
        # Decide target based on filename suffix
        name = src.name
        if name.startswith("actions.json"):
            tgt = Path(paths["actions"])
        elif name.startswith("settings.ini"):
            tgt = Path(paths["settings"])
        else:
            # heuristic: look into file header to guess
            try:
                text = src.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                text = ""
            if "[general]" in text or "[integration]" in text:
                tgt = Path(paths["settings"])
            else:
                tgt = Path(paths["actions"])
        tgt.parent.mkdir(parents=True, exist_ok=True)
        tmp = tgt.parent / (tgt.name + ".tmp")
        shutil.copy2(src, tmp)
        os.replace(tmp, tgt)
        print(f"restored into: {tgt}")
        return 0
    except Exception as e:
        print(f"restore failed: {e}", file=sys.stderr)
        return 3


def cmd_profile_uninstall(args: argparse.Namespace) -> int:
    name = args.name
    if not name:
        print("--name is required", file=sys.stderr)
        return 2
    # for now only shortcuts-only is supported
    if not args.shortcuts_only:
        print("profile uninstall currently supports only --shortcuts-only", file=sys.stderr)
        return 2
    try:
        rep = remove_profile_shortcuts(name)
        print(json.dumps({"ok": True, "name": name, "report": rep}, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1


def cmd_shortcuts_remove(args: argparse.Namespace) -> int:
    if not args.recommended:
        print("specify --recommended to remove recommended shortcuts", file=sys.stderr)
        return 2
    try:
        gnome_shortcuts.remove_recommended_shortcuts()
        print("OK: recommended shortcuts removed")
        return 0
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1


def cmd_autostart_disable(_args: argparse.Namespace) -> int:
    try:
        ok = autostart.disable()
        print("OK" if ok else "FAILED")
        return 0 if ok else 3
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wbridge", description="Selection/Shortcut Bridge CLI")
    sub = p.add_subparsers(dest="sub")

    # ui show
    p_ui = sub.add_parser("ui", help="UI commands")
    sub_ui = p_ui.add_subparsers(dest="sub_ui")
    p_ui_show = sub_ui.add_parser("show", help="bring the GUI window to the foreground")
    p_ui_show.set_defaults(func=cmd_ui_show)

    # selection
    p_sel = sub.add_parser("selection", help="selection operations")
    sub_sel = p_sel.add_subparsers(dest="sub_sel")

    p_sel_get = sub_sel.add_parser("get", help="get current selection text")
    p_sel_get.add_argument("--which", choices=["clipboard", "primary"], default="clipboard")
    p_sel_get.set_defaults(func=cmd_selection_get)

    p_sel_set = sub_sel.add_parser("set", help="set selection text")
    p_sel_set.add_argument("--which", choices=["clipboard", "primary"], default="clipboard")
    p_sel_set.add_argument("--text", required=True, help="literal text to set")
    p_sel_set.set_defaults(func=cmd_selection_set)

    # history
    p_hist = sub.add_parser("history", help="history operations")
    sub_hist = p_hist.add_subparsers(dest="sub_hist")

    p_hist_list = sub_hist.add_parser("list", help="list recent history entries")
    p_hist_list.add_argument("--which", choices=["clipboard", "primary"], default="clipboard")
    p_hist_list.add_argument("--limit", type=int, default=10)
    p_hist_list.set_defaults(func=cmd_history_list)

    p_hist_apply = sub_hist.add_parser("apply", help="apply a history entry to a selection")
    p_hist_apply.add_argument("--which", choices=["clipboard", "primary"], default="clipboard")
    p_hist_apply.add_argument("--index", type=int, required=True, help="0 = latest")
    p_hist_apply.set_defaults(func=cmd_history_apply)

    p_hist_swap = sub_hist.add_parser("swap", help="swap the last two history entries")
    p_hist_swap.add_argument("--which", choices=["clipboard", "primary"], default="clipboard")
    p_hist_swap.set_defaults(func=cmd_history_swap)

    # trigger
    p_tr = sub.add_parser("trigger", help="trigger an action (alias) or run a named action")
    p_tr.add_argument("cmd", nargs="?", help="trigger alias (e.g., prompt, command)")
    p_tr.add_argument("--name", help="run specific named action instead of alias")
    src = p_tr.add_mutually_exclusive_group()
    src.add_argument("--from-clipboard", action="store_true", help="use current clipboard (default)")
    src.add_argument("--from-primary", action="store_true", help="use current primary selection")
    src.add_argument("--text", help="use literal text instead of reading a selection")
    p_tr.set_defaults(func=cmd_trigger)

    # profile
    p_prof = sub.add_parser("profile", help="profile operations")
    sub_prof = p_prof.add_subparsers(dest="sub_prof")

    p_prof_list = sub_prof.add_parser("list", help="list built-in profiles")
    p_prof_list.set_defaults(func=cmd_profile_list)

    p_prof_show = sub_prof.add_parser("show", help="show profile details")
    p_prof_show.add_argument("--name", required=True, help="profile name to show (e.g., witsy)")
    p_prof_show.set_defaults(func=cmd_profile_show)

    p_prof_install = sub_prof.add_parser("install", help="install a profile into user config")
    p_prof_install.add_argument("--name", required=True, help="profile name to install (e.g., witsy)")
    p_prof_install.add_argument("--overwrite-actions", action="store_true", help="overwrite existing actions/triggers with the same names")
    p_prof_install.add_argument("--patch-settings", action="store_true", help="patch whitelisted settings in [integration]")
    p_prof_install.add_argument("--install-shortcuts", action="store_true", help="install recommended GNOME shortcuts from the profile")
    p_prof_install.add_argument("--dry-run", action="store_true", help="do not write files; print planned changes")
    p_prof_install.set_defaults(func=cmd_profile_install)

    p_prof_uninstall = sub_prof.add_parser("uninstall", help="uninstall profile artifacts")
    p_prof_uninstall.add_argument("--name", required=True, help="profile name (e.g., witsy)")
    p_prof_uninstall.add_argument("--shortcuts-only", action="store_true", help="remove shortcuts installed by the profile")
    p_prof_uninstall.set_defaults(func=cmd_profile_uninstall)

    # shortcuts
    p_sc = sub.add_parser("shortcuts", help="shortcuts utilities")
    sub_sc = p_sc.add_subparsers(dest="sub_sc")
    p_sc_rm = sub_sc.add_parser("remove", help="remove shortcuts")
    p_sc_rm.add_argument("--recommended", action="store_true", help="remove recommended shortcuts")
    p_sc_rm.set_defaults(func=cmd_shortcuts_remove)

    # autostart
    p_as = sub.add_parser("autostart", help="autostart utilities")
    sub_as = p_as.add_subparsers(dest="sub_as")
    p_as_disable = sub_as.add_parser("disable", help="disable autostart")
    p_as_disable.set_defaults(func=cmd_autostart_disable)

    # config
    p_cfg = sub.add_parser("config", help="configuration utilities")
    sub_cfg = p_cfg.add_subparsers(dest="sub_cfg")

    p_cfg_paths = sub_cfg.add_parser("show-paths", help="print important file paths")
    p_cfg_paths.add_argument("--json", action="store_true", help="print as JSON")
    p_cfg_paths.set_defaults(func=cmd_config_show_paths)

    p_cfg_backup = sub_cfg.add_parser("backup", help="backup config files with timestamp")
    p_cfg_backup.add_argument("--what", choices=["actions", "settings", "all"], default="all")
    p_cfg_backup.set_defaults(func=cmd_config_backup)

    p_cfg_reset = sub_cfg.add_parser("reset", help="reset config files (delete)")
    p_cfg_reset.add_argument("--keep-actions", action="store_true", help="do not delete actions.json")
    p_cfg_reset.add_argument("--keep-settings", action="store_true", help="do not delete settings.ini")
    p_cfg_reset.add_argument("--backup", action="store_true", help="create timestamped backups before deleting")
    p_cfg_reset.set_defaults(func=cmd_config_reset)

    p_cfg_restore = sub_cfg.add_parser("restore", help="restore from a backup file")
    p_cfg_restore.add_argument("--file", required=True, help="path to backup file")
    p_cfg_restore.set_defaults(func=cmd_config_restore)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 2

    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 1


if __name__ == "__main__":
    sys.exit(main())
