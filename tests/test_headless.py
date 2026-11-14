"""Headless tests for aboauto core logic + Flask API (no Wine, no display)."""
import os, sys, tempfile, json

os.environ["ABOAUTO_DATA_DIR"] = tempfile.mkdtemp(prefix="aboauto-test-")

sys.path.insert(0, "/home/user/aboauto")

from aboauto.accounts import AccountStore
from aboauto.crypto import encrypt, decrypt, is_encrypted
from aboauto.instances import InstanceManager
from aboauto.app import create_app
from aboauto.config import KEY_PATH

store = AccountStore()
mgr = InstanceManager(store=store)

# ---- accounts ----
a_id = store.add(__import__("aboauto.accounts", fromlist=["Account"]).Account(
    username="player_one", password="secret123", cookie="cookieABC",
    display_name="Player One", note="main account"))
assert a_id == 1
a = store.get(a_id)
assert a.username == "player_one"
assert a.password == "secret123", "password should decrypt back"
assert a.cookie == "cookieABC"
assert a.display_name == "Player One"
assert a.label == "Player One"

raw = store.list()
assert len(raw) == 1
# stored encrypted at rest
import sqlite3
conn = sqlite3.connect(store.db_path)
row = conn.execute("SELECT password, cookie FROM accounts WHERE id=1").fetchone()
assert is_encrypted(row[0]) and is_encrypted(row[1]), "credentials must be encrypted at rest"
conn.close()

# update
store.update(a_id, password="newpass", note="updated")
a2 = store.get(a_id)
assert a2.password == "newpass" and a2.note == "updated"

# mark launched
store.mark_launched(a_id)
a3 = store.get(a_id)
assert a3.last_launched is not None

# delete
assert store.delete(a_id) is True
assert store.get(a_id) is None
assert len(store.list()) == 0
print("AccountStore CRUD + encryption: OK")

# ---- instances (no wine installed -> launch should fail gracefully / record error) ----
inst = mgr.spawn(account_id=None, username="nouser", roblox_exe="/nonexistent/RobloxPlayerBeta.exe")
assert inst.id
assert inst.status in ("starting", "running", "error")
# wait for the background thread to settle (wineboot/init may take a few seconds)
import time
for _ in range(100):  # up to ~10s
    inst = mgr.get(inst.id)
    if inst.status in ("error", "stopped", "running"):
        break
    time.sleep(0.1)
# The instance must be created and tracked without crashing the manager.
# Status depends on the machine: no Wine -> error; Wine present -> running/stopped/error
# as wine tries the nonexistent exe. All are valid outcomes.
assert inst.status in ("error", "stopped", "running"), f"unexpected status: {inst.status}"
assert inst.log, "instance should have at least one log line"
print("InstanceManager spawn: OK ->", inst.status, "| log:", inst.log[-1] if inst.log else "")

# Clean up the spawned instance so we don't leave Wine windows open.
try:
    mgr.stop(inst.id, force=True)
except Exception:
    pass
mgr.clear_stopped()

# ---- Flask API ----
app = create_app(store=store, mgr=mgr)
client = app.test_client()

# accounts api
r = client.post("/api/accounts", json={"username": "alice", "password": "pw", "cookie": "ck"})
assert r.status_code == 201, r.get_data(as_text=True)
body = r.get_json(); assert body["username"] == "alice"

r = client.get("/api/accounts"); assert r.status_code == 200
accts = r.get_json(); assert len(accts) == 1
aid = accts[0]["id"]

r = client.put(f"/api/accounts/{aid}", json={"display_name": "Alice D"})
assert r.status_code == 200
assert r.get_json()["display_name"] == "Alice D"

# launch without wine -> should still create an instance record (error)
r = client.post(f"/api/accounts/{aid}/launch", method="POST")
assert r.status_code == 201, r.get_data(as_text=True)
iid = r.get_json()["id"]

# multi launch
r = client.post("/api/instances/launch-multi", json={"account_ids": [aid]})
assert r.status_code == 201
assert r.get_json()["count"] == 1

r = client.get("/api/instances"); assert r.status_code == 200
insts = r.get_json(); assert len(insts) >= 1

r = client.get(f"/api/instances/{iid}"); assert r.status_code == 200

r = client.delete(f"/api/instances/{iid}"); assert r.status_code in (200, 404)  # may already be stopped/error

r = client.post("/api/instances/stop-all", method="POST"); assert r.status_code == 200
r = client.post("/api/instances/clear-stopped", method="POST"); assert r.status_code == 200

# settings
r = client.get("/api/settings"); assert r.status_code == 200
s = r.get_json(); assert "roblox_exe" in s
r = client.put("/api/settings", json={"launch_delay_seconds": 5})
assert r.status_code == 200 and r.get_json()["launch_delay_seconds"] == 5

# status
r = client.get("/api/status"); assert r.status_code == 200
st = r.get_json(); assert "wine_available" in st and "accounts" in st
print("Flask API: OK  (wine_available=", st["wine_available"], ")")

# key file created with 0600
import stat
mode = stat.S_IMODE(os.stat(KEY_PATH).st_mode)
assert mode == 0o600, oct(mode)
print("Key file permissions: OK (0o600)")

print("\nALL HEADLESS TESTS PASSED")
