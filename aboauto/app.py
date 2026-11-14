"""Flask web GUI for aboauto.

Endpoints serve a single-page dashboard (templates/index.html) and a small
JSON API used by the frontend. The app binds 0.0.0.0 so it works headless
and can be reached from the local network / live preview.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .accounts import AccountStore
from .config import (
    DEFAULT_LAUNCHER_MODE,
    DEFAULT_ROBLOX_EXE,
    DEFAULT_SOBER_BIN,
    DEFAULT_SOBER_FLATPAK_ID,
    DEFAULT_WINE_BIN,
    DEFAULT_WINE_PREFIX_BASE,
    DEFAULTS,
    SETTINGS_PATH,
    ensure_data_dir,
)
from .instances import InstanceManager
from .launcher import is_sober_available, is_wine_available

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(store: AccountStore | None = None,
               mgr: InstanceManager | None = None) -> Flask:
    ensure_data_dir()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["JSON_SORT_KEYS"] = False

    store = store or AccountStore()
    mgr = mgr or InstanceManager(store=store)

    # ------------------------------------------------------------------ pages

    @app.get("/")
    def index():
        return render_template("index.html")

    # ------------------------------------------------------------------ accounts

    @app.get("/api/accounts")
    def api_list_accounts():
        return jsonify([a.__dict__ for a in store.list()])

    @app.post("/api/accounts")
    def api_create_account():
        data = request.get_json(force=True, silent=True) or {}
        username = (data.get("username") or "").strip()
        if not username:
            return jsonify({"error": "username is required"}), 400
        from .accounts import Account
        acct = Account(
            username=username,
            password=data.get("password") or "",
            cookie=data.get("cookie") or "",
            display_name=data.get("display_name") or "",
            note=data.get("note") or "",
        )
        acct.id = store.add(acct)
        return jsonify(acct.__dict__), 201

    @app.put("/api/accounts/<int:account_id>")
    def api_update_account(account_id):
        data = request.get_json(force=True, silent=True) or {}
        if not store.get(account_id):
            return jsonify({"error": "account not found"}), 404
        ok = store.update(account_id, **data)
        if not ok:
            return jsonify({"error": "nothing to update"}), 400
        acct = store.get(account_id)
        return jsonify(acct.__dict__ if acct else {})

    @app.delete("/api/accounts/<int:account_id>")
    def api_delete_account(account_id):
        ok = store.delete(account_id)
        if not ok:
            return jsonify({"error": "account not found"}), 404
        return jsonify({"ok": True})

    @app.post("/api/accounts/<int:account_id>/launch")
    def api_launch_account(account_id):
        acct = store.get(account_id)
        if not acct:
            return jsonify({"error": "account not found"}), 404
        settings = _load_settings()
        inst = mgr.spawn(
            account_id=account_id,
            username=acct.username,
            roblox_exe=settings.get("roblox_exe", DEFAULT_ROBLOX_EXE),
            wine_bin=settings.get("wine_bin", DEFAULT_WINE_BIN),
            wine_prefix_base=settings.get("wine_prefix_base", DEFAULT_WINE_PREFIX_BASE),
            extra_args=settings.get("extra_args", ""),
            launch_delay_seconds=float(settings.get("launch_delay_seconds", 2.0)),
            launcher_mode=settings.get("launcher_mode", DEFAULT_LAUNCHER_MODE),
            sober_bin=settings.get("sober_bin", DEFAULT_SOBER_BIN),
            sober_flatpak_id=settings.get(
                "sober_flatpak_id", DEFAULT_SOBER_FLATPAK_ID
            ),
        )
        return jsonify(inst.to_dict()), 201

    # ------------------------------------------------------------------ instances (multi + manager)

    @app.post("/api/instances/launch-multi")
    def api_launch_multi():
        data = request.get_json(force=True, silent=True) or {}
        account_ids = data.get("account_ids") or []
        if not isinstance(account_ids, list) or not account_ids:
            return jsonify({"error": "account_ids (list) is required"}), 400
        settings = _load_settings()
        launched = []
        delay = float(settings.get("launch_delay_seconds", 2.0))
        for i, aid in enumerate(account_ids):
            if i > 0 and delay > 0:
                time.sleep(delay)
            acct = store.get(int(aid))
            if not acct:
                continue
            inst = mgr.spawn(
                account_id=acct.id,
                username=acct.username,
                roblox_exe=settings.get("roblox_exe", DEFAULT_ROBLOX_EXE),
                wine_bin=settings.get("wine_bin", DEFAULT_WINE_BIN),
                wine_prefix_base=settings.get("wine_prefix_base", DEFAULT_WINE_PREFIX_BASE),
                extra_args=settings.get("extra_args", ""),
                launch_delay_seconds=float(settings.get("launch_delay_seconds", 2.0)),
                launcher_mode=settings.get("launcher_mode", DEFAULT_LAUNCHER_MODE),
                sober_bin=settings.get("sober_bin", DEFAULT_SOBER_BIN),
                sober_flatpak_id=settings.get(
                    "sober_flatpak_id", DEFAULT_SOBER_FLATPAK_ID
                ),
            )
            launched.append(inst.to_dict())
        return jsonify({"launched": launched, "count": len(launched)}), 201

    @app.get("/api/instances")
    def api_list_instances():
        return jsonify([i.to_dict() for i in mgr.list()])

    @app.get("/api/instances/<instance_id>")
    def api_get_instance(instance_id):
        inst = mgr.get(instance_id)
        if not inst:
            return jsonify({"error": "instance not found"}), 404
        return jsonify(inst.to_dict())

    @app.delete("/api/instances/<instance_id>")
    def api_stop_instance(instance_id):
        data = request.get_json(force=True, silent=True) or {}
        force = bool(data.get("force", False))
        ok = mgr.stop(instance_id, force=force)
        if not ok:
            return jsonify({"error": "instance not found or not running"}), 404
        return jsonify({"ok": True})

    @app.post("/api/instances/stop-all")
    def api_stop_all():
        data = request.get_json(force=True, silent=True) or {}
        force = bool(data.get("force", False))
        n = mgr.stop_all(force=force)
        return jsonify({"stopped": n})

    @app.post("/api/instances/clear-stopped")
    def api_clear_stopped():
        n = mgr.clear_stopped()
        return jsonify({"removed": n})

    # ------------------------------------------------------------------ settings

    @app.get("/api/settings")
    def api_get_settings():
        return jsonify(_load_settings())

    @app.put("/api/settings")
    def api_put_settings():
        data = request.get_json(force=True, silent=True) or {}
        settings = _load_settings()
        settings.update(data)
        _save_settings(settings)
        return jsonify(settings)

    # ------------------------------------------------------------------ status

    @app.get("/api/status")
    def api_status():
        return jsonify({
            "wine_available": is_wine_available(),
            "sober_available": is_sober_available(),
            "accounts": len(store.list()),
            "running_instances": sum(1 for i in mgr.list() if i.status == "running"),
            "total_instances": len(mgr.list()),
        })

    return app


# ------------------------------------------------------------------ settings IO

def _load_settings() -> dict:
    settings = dict(DEFAULTS)
    if SETTINGS_PATH.exists():
        try:
            with SETTINGS_PATH.open("r", encoding="utf-8") as f:
                user_settings = json.load(f)
            if isinstance(user_settings, dict):
                settings.update(user_settings)
        except (json.JSONDecodeError, OSError):
            pass
    return settings


def _save_settings(settings: dict) -> None:
    ensure_data_dir()
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
    tmp.replace(SETTINGS_PATH)


# ------------------------------------------------------------------ dev entrypoint

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=True)
