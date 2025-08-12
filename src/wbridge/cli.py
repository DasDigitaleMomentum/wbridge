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
from typing import Any, Dict, Tuple

from .client_ipc import send_request, cli_exit_code_from_response


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
