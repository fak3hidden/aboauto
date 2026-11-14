"""Command-line interface for aboauto.

Useful headless/terminal usage (e.g. over SSH, in a TTY, or in scripts):

    aboauto account add --username player1 --password hunter2
    aboauto account list
    aboauto instance launch --account 1
    aboauto instance list
    aboauto instance stop <id>
    aboauto server            # start the Flask web GUI
"""

from __future__ import annotations

import argparse
import os
import time
import sys
from datetime import datetime

from .accounts import AccountStore
from .app import create_app
from .config import (
    DEFAULT_LAUNCHER_MODE,
    DEFAULT_ROBLOX_EXE,
    DEFAULT_SOBER_BIN,
    DEFAULT_SOBER_FLATPAK_ID,
    DEFAULT_WINE_BIN,
    DEFAULT_WINE_PREFIX_BASE,
    DEFAULTS,
    ensure_data_dir,
)
from .instances import InstanceManager


def _fmt(dt) -> str:
    if not dt:
        return "-"
    return dt.strftime("%Y-%m-%d %H:%M")


def cmd_account_add(args) -> int:
    store = AccountStore()
    from .accounts import Account
    acct = Account(
        username=args.username,
        password=args.password or "",
        cookie=args.cookie or "",
        display_name=args.display_name or "",
        note=args.note or "",
    )
    acct.id = store.add(acct)
    print(f"Added account #{acct.id}: {acct.username}")
    return 0


def cmd_account_list(args) -> int:
    store = AccountStore()
    accts = store.list()
    if not accts:
        print("No accounts found.")
        return 0
    print(f"{'ID':<5} {'Username':<20} {'Display':<20} {'Last launched':<20}")
    print("-" * 70)
    for a in accts:
        print(f"{a.id:<5} {a.username:<20} {a.display_name:<20} {_fmt(a.last_launched):<20}")
    return 0


def cmd_account_show(args) -> int:
    store = AccountStore()
    acct = store.get(args.id)
    if not acct:
        print(f"Account #{args.id} not found.")
        return 1
    print(f"ID        : {acct.id}")
    print(f"Username  : {acct.username}")
    print(f"Password  : {'set' if acct.password else '(empty)'}")
    print(f"Cookie    : {'set' if acct.cookie else '(empty)'}")
    print(f"Display   : {acct.display_name}")
    print(f"Note      : {acct.note}")
    print(f"Created   : {_fmt(acct.created_at)}")
    print(f"Updated   : {_fmt(acct.updated_at)}")
    print(f"Last launched: {_fmt(acct.last_launched)}")
    return 0


def cmd_account_delete(args) -> int:
    store = AccountStore()
    if store.delete(args.id):
        print(f"Deleted account #{args.id}.")
        return 0
    print(f"Account #{args.id} not found.")
    return 1


def cmd_instance_launch(args) -> int:
    store = AccountStore()
    mgr = InstanceManager(store=store)
    acct = None
    if args.account:
        acct = store.get(args.account)
        if not acct:
            print(f"Account #{args.account} not found.")
            return 1
    inst = mgr.spawn(
        account_id=acct.id if acct else None,
        username=acct.username if acct else args.username or "",
        roblox_exe=args.roblox_exe,
        wine_bin=args.wine_bin,
        extra_args=args.extra_args,
        launch_delay_seconds=args.delay,
        launcher_mode=args.launcher_mode,
        sober_bin=args.sober_bin,
        sober_flatpak_id=args.sober_flatpak_id,
    )
    print(f"Launched instance {inst.id} (pid={inst.pid}) status={inst.status}")
    return 0


def cmd_instance_multi(args) -> int:
    store = AccountStore()
    mgr = InstanceManager(store=store)
    ids = [int(x) for x in args.ids.split(",")]
    launched = 0
    delay = args.delay
    for i, aid in enumerate(ids):
        if i > 0 and delay > 0:
            time.sleep(delay)
        acct = store.get(aid)
        if not acct:
            print(f"Account #{aid} not found, skipping.")
            continue
        mgr.spawn(account_id=acct.id, username=acct.username,
                  roblox_exe=args.roblox_exe, wine_bin=args.wine_bin,
                  extra_args=args.extra_args, launch_delay_seconds=args.delay,
                  launcher_mode=args.launcher_mode, sober_bin=args.sober_bin,
                  sober_flatpak_id=args.sober_flatpak_id)
        launched += 1
    print(f"Launched {launched} instance(s).")
    return 0


def cmd_instance_list(args) -> int:
    mgr = InstanceManager()
    insts = mgr.list()
    if not insts:
        print("No instances tracked.")
        return 0
    print(f"{'ID':<18} {'Account':<18} {'PID':<7} {'Status':<10} {'Started':<17}")
    print("-" * 75)
    for i in insts:
        print(f"{i.id:<18} {i.account_username:<18} {str(i.pid or '-'):<7} "
              f"{i.status:<10} {_fmt(i.started_at):<17}")
    return 0


def cmd_instance_stop(args) -> int:
    mgr = InstanceManager()
    ok = mgr.stop(args.id, force=args.force)
    if ok:
        print(f"Stopped instance {args.id}.")
        return 0
    print(f"Instance {args.id} not found or not running.")
    return 1


def cmd_instance_stop_all(args) -> int:
    mgr = InstanceManager()
    n = mgr.stop_all(force=args.force)
    print(f"Stopped {n} instance(s).")
    return 0


def cmd_instance_clear(args) -> int:
    mgr = InstanceManager()
    n = mgr.clear_stopped()
    print(f"Removed {n} stopped instance(s).")
    return 0


def cmd_server(args) -> int:
    import os
    app = create_app()
    app.run(host="0.0.0.0", port=args.port, debug=args.debug)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aboauto", description="Roblox semi account manager for Linux")
    sub = parser.add_subparsers(dest="command", required=True)

    # ---- account
    p_acc = sub.add_parser("account", help="account manager")
    acc_sub = p_acc.add_subparsers(dest="action", required=True)

    p_add = acc_sub.add_parser("add", help="add an account")
    p_add.add_argument("--username", required=True)
    p_add.add_argument("--password", default="")
    p_add.add_argument("--cookie", default="", help=".ROBLOSECURITY cookie")
    p_add.add_argument("--display-name", default="")
    p_add.add_argument("--note", default="")
    p_add.set_defaults(func=cmd_account_add)

    p_list = acc_sub.add_parser("list", help="list accounts")
    p_list.set_defaults(func=cmd_account_list)

    p_show = acc_sub.add_parser("show", help="show an account")
    p_show.add_argument("id", type=int)
    p_show.set_defaults(func=cmd_account_show)

    p_del = acc_sub.add_parser("delete", help="delete an account")
    p_del.add_argument("id", type=int)
    p_del.set_defaults(func=cmd_account_delete)

    # ---- instance
    p_inst = sub.add_parser("instance", help="instance manager")
    inst_sub = p_inst.add_subparsers(dest="action", required=True)

    def _instance_flags(p):
        p.add_argument("--roblox-exe", default=DEFAULT_ROBLOX_EXE)
        p.add_argument("--wine-bin", default=DEFAULT_WINE_BIN)
        p.add_argument("--extra-args", default="")
        p.add_argument("--delay", type=float, default=DEFAULTS["launch_delay_seconds"])
        p.add_argument(
            "--launcher-mode",
            default=DEFAULTS.get("launcher_mode", DEFAULT_LAUNCHER_MODE),
            choices=["wine", "sober"],
            help="launch backend: wine (RobloxPlayerBeta.exe) or sober (Flatpak)",
        )
        p.add_argument(
            "--sober-bin",
            default=DEFAULTS.get("sober_bin", DEFAULT_SOBER_BIN),
            help="flatpak binary (sober mode)",
        )
        p.add_argument(
            "--sober-flatpak-id",
            default=DEFAULTS.get("sober_flatpak_id", DEFAULT_SOBER_FLATPAK_ID),
            help="Sober Flatpak application id (sober mode)",
        )

    p_launch = inst_sub.add_parser("launch", help="launch one instance")
    p_launch.add_argument("--account", type=int, default=None, help="account id to launch with")
    p_launch.add_argument("--username", default="", help="username if not using an account")
    _instance_flags(p_launch)
    p_launch.set_defaults(func=cmd_instance_launch)

    p_multi = inst_sub.add_parser("multi", help="launch multiple instances")
    p_multi.add_argument("--ids", required=True, help="comma-separated account ids")
    _instance_flags(p_multi)
    p_multi.set_defaults(func=cmd_instance_multi)

    p_ilist = inst_sub.add_parser("list", help="list running instances")
    p_ilist.set_defaults(func=cmd_instance_list)

    p_stop = inst_sub.add_parser("stop", help="stop an instance")
    p_stop.add_argument("id")
    p_stop.add_argument("--force", action="store_true")
    p_stop.set_defaults(func=cmd_instance_stop)

    p_stopall = inst_sub.add_parser("stop-all", help="stop all instances")
    p_stopall.add_argument("--force", action="store_true")
    p_stopall.set_defaults(func=cmd_instance_stop_all)
    inst_sub.add_parser("clear-stopped", help="remove stopped instances").set_defaults(func=cmd_instance_clear)

    # ---- server
    p_srv = sub.add_parser("server", help="start the web GUI")
    p_srv.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p_srv.add_argument("--debug", action="store_true")
    p_srv.set_defaults(func=cmd_server)

    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_data_dir()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
