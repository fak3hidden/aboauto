"""Instance Manager: spawn, track, and stop running Roblox instances."""

from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .accounts import AccountStore
from .config import ensure_data_dir
from .launcher import LaunchSpec, build_command, build_env, prefix_dir_for, prepare_for_launch


@dataclass
class Instance:
    """A running (or formerly running) Roblox instance."""

    id: str
    account_id: Optional[int] = None
    account_username: str = ""
    pid: Optional[int] = None
    status: str = "starting"  # starting | running | stopped | error
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    log: list[str] = field(default_factory=list)
    process: Optional[subprocess.Popen] = None  # not serialized

    def to_dict(self, include_process: bool = False) -> dict:
        d = {
            "id": self.id,
            "account_id": self.account_id,
            "account_username": self.account_username,
            "pid": self.pid,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "log": list(self.log),
        }
        if include_process:
            d["alive"] = self.process is not None and self.process.poll() is None
        return d


class InstanceManager:
    """Tracks Roblox instances in memory (thread-safe).

    Spawning uses subprocess.Popen so the manager works headless. Each
    instance runs in its own WINEPREFIX for isolation.
    """

    def __init__(self, store: AccountStore | None = None) -> None:
        ensure_data_dir()
        self.store = store or AccountStore()
        self._lock = threading.Lock()
        self._instances: dict[str, Instance] = {}
        self._next_counter = 0

    # ------------------------------------------------------------------ spawn

    def spawn(
        self,
        account_id: int | None = None,
        username: str = "",
        roblox_exe: str = "",
        wine_bin: str = "",
        wine_prefix_base: str = "",
        extra_args: str = "",
        launch_delay_seconds: float = 0.0,
        launcher_mode: str = "wine",
        sober_bin: str = "flatpak",
        sober_flatpak_id: str = "org.vinegarhq.Sober",
    ) -> Instance:
        from .config import (
            DEFAULT_LAUNCHER_MODE,
            DEFAULT_ROBLOX_EXE,
            DEFAULT_SOBER_BIN,
            DEFAULT_SOBER_FLATPAK_ID,
            DEFAULT_WINE_BIN,
            DEFAULT_WINE_PREFIX_BASE,
        )

        account = None
        if account_id is not None:
            account = self.store.get(account_id)
            if account:
                username = account.username
                if account_id:
                    self.store.mark_launched(account_id)

        spec = LaunchSpec(
            instance_id=self._next_id(),
            account_username=username,
            roblox_exe=roblox_exe or DEFAULT_ROBLOX_EXE,
            wine_bin=wine_bin or DEFAULT_WINE_BIN,
            extra_args=extra_args,
            launch_delay_seconds=launch_delay_seconds,
            launcher_mode=launcher_mode or DEFAULT_LAUNCHER_MODE,
            sober_bin=sober_bin or DEFAULT_SOBER_BIN,
            sober_flatpak_id=sober_flatpak_id or DEFAULT_SOBER_FLATPAK_ID,
        )
        # Isolate prefix per instance so multiple Roblox clients can run.
        prefix_dir_for(spec)

        inst = Instance(
            id=spec.instance_id,
            account_id=account_id,
            account_username=username,
            status="starting",
            started_at=datetime.now(timezone.utc),
        )

        def _run() -> None:
            # Prepare Wine prefix (run wineboot --init if needed) so the
            # "configuration is being updated" dialog completes before Roblox
            # launches instead of racing with it and crashing.
            ok, msg = prepare_for_launch(spec)
            with self._lock:
                inst.log.append(f"[system] {msg}")
            if not ok:
                with self._lock:
                    inst.status = "error"
                    inst.log.append(f"[error] failed to prepare prefix: {msg}")
                    inst.stopped_at = datetime.now(timezone.utc)
                return

            cmd = build_command(spec)
            env = build_env(spec)
            try:
                proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
            except FileNotFoundError as exc:
                with self._lock:
                    inst.status = "error"
                    inst.log.append(f"[error] failed to launch: {exc}")
                    inst.stopped_at = datetime.now(timezone.utc)
                return
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    inst.status = "error"
                    inst.log.append(f"[error] {exc}")
                    inst.stopped_at = datetime.now(timezone.utc)
                return

            with self._lock:
                inst.process = proc
                inst.pid = proc.pid
                inst.status = "running"

            # Stream output (bounded) so the instance manager can show logs.
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.rstrip("\n")
                    with self._lock:
                        inst.log.append(line)
                        if len(inst.log) > 500:
                            inst.log = inst.log[-500:]
            except Exception:  # noqa: BLE001
                pass
            finally:
                proc.wait()
                with self._lock:
                    if inst.status != "error":
                        inst.status = "stopped"
                    inst.stopped_at = datetime.now(timezone.utc)

        thread = threading.Thread(target=_run, daemon=True, name=f"aboauto-{inst.id}")
        with self._lock:
            self._instances[inst.id] = inst
        thread.start()
        return inst

    # ------------------------------------------------------------------ query

    def list(self) -> list[Instance]:
        with self._lock:
            instances = list(self._instances.values())
        # refresh status for any process that exited
        for inst in instances:
            self._refresh_status(inst)
        return sorted(instances, key=lambda i: i.started_at or datetime.min, reverse=True)

    def get(self, instance_id: str) -> Optional[Instance]:
        with self._lock:
            inst = self._instances.get(instance_id)
        if inst:
            self._refresh_status(inst)
        return inst

    def stop(self, instance_id: str, force: bool = False) -> bool:
        with self._lock:
            inst = self._instances.get(instance_id)
        if not inst or not inst.process:
            return False
        try:
            if force:
                inst.process.kill()
            else:
                inst.process.terminate()
            try:
                inst.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                inst.process.kill()
                inst.process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            return False
        with self._lock:
            inst.log.append(f"[system] {'killed' if force else 'terminated'} (pid={inst.pid})")
            inst.status = "stopped"
            inst.stopped_at = datetime.now(timezone.utc)
        return True

    def remove(self, instance_id: str) -> bool:
        """Drop a stopped instance from the tracker."""
        with self._lock:
            inst = self._instances.get(instance_id)
            if not inst:
                return False
            if inst.process and inst.process.poll() is None:
                return False  # refuse to remove a running instance
            del self._instances[instance_id]
            return True

    def stop_all(self, force: bool = False) -> int:
        stopped = 0
        with self._lock:
            ids = list(self._instances.keys())
        for iid in ids:
            if self.stop(iid, force=force):
                stopped += 1
        return stopped

    def clear_stopped(self) -> int:
        """Remove all stopped/errored/stuck instances from the tracker.

        An instance in "starting" with no process is stuck (daemon thread
        never spawned a process) and is cleaned up too.
        """
        removed = 0
        with self._lock:
            ids = [
                iid
                for iid, inst in self._instances.items()
                if inst.status in ("stopped", "error")
                or (inst.status == "starting" and inst.process is None)
            ]
        for iid in ids:
            if self.remove(iid):
                removed += 1
        return removed

    # ------------------------------------------------------------------ internals

    def _next_id(self) -> str:
        self._next_counter += 1
        return f"inst-{self._next_counter:04d}-{__import__('uuid').uuid4().hex[:6]}"

    def _refresh_status(self, inst: Instance) -> None:
        """Update status if the underlying process exited."""
        proc = inst.process
        if proc is None:
            return
        rc = proc.poll()
        if rc is None:
            if inst.status in ("starting", "running"):
                inst.status = "running"
            return
        if inst.status not in ("stopped", "error"):
            inst.status = "stopped"
        if inst.stopped_at is None:
            inst.stopped_at = datetime.now(timezone.utc)
        if rc != 0:
            inst.log.append(f"[system] process exited with code {rc}")
