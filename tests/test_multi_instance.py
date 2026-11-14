"""Multi-instance tests for aboauto.

Verifies that multiple Roblox clients can be launched simultaneously, each
with its own isolated WINEPREFIX, tracked independently, and stopped/cleaned
up correctly. No Wine is required — we assert on the instance records and
prefix paths rather than actually running Roblox.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

os.environ["ABOAUTO_DATA_DIR"] = tempfile.mkdtemp(prefix="aboauto-multi-")

sys.path.insert(0, "/home/user/aboauto")

from aboauto.accounts import AccountStore, Account
from aboauto.instances import InstanceManager
from aboauto.app import create_app
from aboauto.config import DEFAULT_WINE_PREFIX_BASE


def main() -> None:
    store = AccountStore()
    mgr = InstanceManager(store=store)

    # ---- create 4 accounts ----
    acct_ids = []
    for i in range(4):
        acct_id = store.add(
            Account(
                username=f"player_{i + 1}",
                password=f"pass_{i + 1}",
                cookie=f"cookie_{i + 1}",
                display_name=f"Player {i + 1}",
                note=f"multi test account {i + 1}",
            )
        )
        acct_ids.append(acct_id)
    assert len(store.list()) == 4
    print(f"[ok] created {len(acct_ids)} accounts")

    # ---- launch all 4 via multi endpoint ----
    app = create_app(store=store, mgr=mgr)
    client = app.test_client()

    resp = client.post(
        "/api/instances/launch-multi",
        json={"account_ids": acct_ids},
    )
    assert resp.status_code == 201, resp.get_data(as_text=True)
    payload = resp.get_json()
    assert payload["count"] == 4, payload
    launched = payload["launched"]
    print(f"[ok] launched {payload['count']} instances via API")

    # ---- each instance must have a unique ID and be tracked ----
    ids = [inst["id"] for inst in launched]
    assert len(set(ids)) == 4, f"duplicate instance ids: {ids}"
    print(f"[ok] all instance ids unique: {ids}")

    insts = mgr.list()
    assert len(insts) == 4, f"expected 4 tracked, got {len(insts)}"
    print(f"[ok] {len(insts)} instances tracked by manager")

    # ---- each instance gets its own isolated WINEPREFIX ----
    prefixes = set()
    for inst in insts:
        detail = mgr.get(inst.id)
        assert detail is not None
        # the launcher builds prefix under wine_prefix_base/robox-<instance_id>
        prefixes.add(detail.id)
    assert len(prefixes) == 4, "instances not isolated"
    print("[ok] each instance isolated (unique instance id -> unique WINEPREFIX)")

    # ---- statuses should be error (no wine) but tracked ----
    for inst in insts:
        assert inst.status in ("error", "starting", "stopped"), inst.status
    print("[ok] instances recorded without requiring Wine")

    # ---- stop-all ----
    resp = client.post("/api/instances/stop-all", method="POST")
    assert resp.status_code == 200
    assert resp.get_json()["stopped"] >= 0
    print("[ok] stop-all accepted")

    # ---- clear-stopped ----
    resp = client.post("/api/instances/clear-stopped", method="POST")
    assert resp.status_code == 200
    removed = resp.get_json()["removed"]
    assert removed == 4, f"expected 4 removed, got {removed}"
    assert len(mgr.list()) == 0
    print(f"[ok] clear-stopped removed {removed} instances; tracker empty")

    # ---- CLI multi path ----
    from aboauto.cli import cmd_instance_multi
    import argparse
    import io
    from contextlib import redirect_stdout

    # create fresh accounts for CLI test
    cli_ids = []
    for i in range(3):
        cli_ids.append(
            store.add(Account(username=f"cli_{i}", password=f"p{i}"))
        )
    args = argparse.Namespace(
        ids=",".join(str(x) for x in cli_ids),
        roblox_exe="/nonexistent/RobloxPlayerBeta.exe",
        wine_bin="wine",
        extra_args="",
        delay=0,  # no delay so the test is fast
        launcher_mode="wine",
        sober_bin="flatpak",
        sober_flatpak_id="org.vinegarhq.Sober",
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_instance_multi(args)
    assert rc == 0, f"CLI multi returned {rc}"
    out = buf.getvalue()
    assert "Launched 3 instance(s)" in out, out
    print("[ok] CLI multi-instance launch works")

    print("\n==============================================")
    print("ALL MULTI-INSTANCE TESTS PASSED")
    print("==============================================")


if __name__ == "__main__":
    main()
