"""Roblox launch command builder for Linux.

Roblox on Linux is normally run through Wine. Because the official Roblox
client does not support multiple concurrent instances (and has no clean
CLI login), each launched instance gets:

  * its own WINEPREFIX (isolated user data / settings), and
  * a staggered launch delay so the singleton check does not collide.

The builder returns a list suitable for ``subprocess.Popen(..., env=env)``.
It does **not** require Wine to be installed to *build* commands - only to
actually launch - which keeps the manager testable headless.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import (
    DEFAULT_LAUNCHER_MODE,
    DEFAULT_ROBLOX_EXE,
    DEFAULT_SOBER_BIN,
    DEFAULT_SOBER_FLATPAK_ID,
    DEFAULT_WINE_BIN,
    DEFAULT_WINE_PREFIX_BASE,
)


@dataclass
class LaunchSpec:
    """Everything needed to start one Roblox instance."""

    instance_id: str
    account_username: str
    roblox_exe: str = DEFAULT_ROBLOX_EXE
    wine_bin: str = DEFAULT_WINE_BIN
    wine_prefix: str = ""  # empty => auto-generated under prefix base
    extra_args: str = ""  # additional arguments appended to RobloxPlayerBeta.exe
    launch_delay_seconds: float = 0.0
    env: dict | None = None  # extra environment variables
    launcher_mode: str = DEFAULT_LAUNCHER_MODE  # "wine" | "sober"
    sober_bin: str = DEFAULT_SOBER_BIN
    sober_flatpak_id: str = DEFAULT_SOBER_FLATPAK_ID

    def __post_init__(self) -> None:
        if not self.instance_id:
            self.instance_id = uuid.uuid4().hex[:12]
        if not self.wine_prefix:
            self.wine_prefix = str(
                Path(DEFAULT_WINE_PREFIX_BASE) / f"robox-{self.instance_id}"
            )


def build_command(spec: LaunchSpec) -> list[str]:
    """Build the argv list for launching one Roblox instance.

    Launcher mode ``wine`` launches RobloxPlayerBeta.exe through Wine.
    Launcher mode ``sober`` launches the VinegarHQ Sober Flatpak
    (org.vinegarhq.Sober), which runs Roblox's Android build natively on
    Linux and handles its own login UI.  Each instance uses Flatpak's
    ``--instance`` flag so multiple Sober clients can run concurrently.
    """
    if spec.launcher_mode == "sober":
        # Flatpak --instance lets us run multiple isolated Sober clients at
        # once. Without it, `flatpak run` reuses the existing instance and
        # just focuses the window ("another instance is already running").
        cmd = [spec.sober_bin, "run", "--instance=" + spec.instance_id,
               spec.sober_flatpak_id]
        if spec.extra_args:
            cmd.extend(shlex.split(spec.extra_args))
        return cmd
    cmd: list[str] = [spec.wine_bin]
    # Windows apps under Wine sometimes need the working dir set to the exe's dir.
    cmd.append(spec.roblox_exe)
    if spec.extra_args:
        cmd.extend(shlex.split(spec.extra_args))
    return cmd


def build_env(spec: LaunchSpec) -> dict[str, str]:
    """Build the environment for one isolated Roblox instance."""
    env = dict(os.environ)
    if spec.launcher_mode == "sober":
        # Sober is a Flatpak GUI app; no WINEPREFIX or Wine env needed.
        if spec.env:
            env.update(spec.env)
        return env
    env["WINEPREFIX"] = spec.wine_prefix
    env["WINEDEBUG"] = "-all"  # keep logs quieter unless the user wants them
    env["WINEDLLOVERRIDES"] = "mscoree,mshtml="
    if spec.env:
        env.update(spec.env)
    return env


def prefix_dir_for(spec: LaunchSpec) -> Path:
    """Return the WINEPREFIX path for a spec (creating parents)."""
    p = Path(spec.wine_prefix)
    p.mkdir(parents=True, exist_ok=True)
    return p


def init_wine_prefix(wine_bin: str, wine_prefix: str, timeout: int = 8) -> tuple[bool, str]:
    """Initialize a Wine prefix if it is not already initialized.

    Creates the WINEPREFIX directory and runs ``wineboot --init`` so the
    "Wine configuration is being updated, please wait..." dialog completes
    *before* Roblox launches, instead of racing with it and crashing.

    wineboot is best-effort: if it times out (e.g. no display to show the
    dialog) we still proceed -- the prefix directory exists and Wine will
    initialize on first Roblox launch.  Returns (success, message).
    """
    from pathlib import Path

    prefix = Path(wine_prefix)

    # Already initialized?  Skip wineboot.
    if (prefix / "system.reg").exists():
        return True, "prefix already initialized"

    prefix.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["WINEPREFIX"] = wine_prefix
    env["WINEDEBUG"] = "-all"
    env["WINEDLLOVERRIDES"] = "mscoree,mshtml="

    try:
        result = subprocess.run(
            [wine_bin, "wineboot", "--init"],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, "prefix initialized"
        return True, f"wineboot exited {result.returncode} (continuing anyway)"
    except subprocess.TimeoutExpired:
        return True, "wineboot timed out (continuing anyway)"
    except FileNotFoundError:
        return False, f"{wine_bin} not found"


def prepare_for_launch(spec: LaunchSpec) -> tuple[bool, str]:
    """Prepare everything needed before launching one Roblox instance.

    For Wine mode this creates the isolated WINEPREFIX and runs
    ``wineboot --init`` if needed.  For Sober mode nothing to prepare.
    Returns (success, message).
    """
    if spec.launcher_mode == "sober":
        return True, "sober mode (no prefix needed)"
    prefix_dir_for(spec)
    ok, msg = init_wine_prefix(spec.wine_bin, spec.wine_prefix)
    # If wine isn't installed at all we can't launch; otherwise proceed
    # even if wineboot timed out -- the prefix dir exists.
    if not ok and "not found" in msg:
        return False, msg
    return True, msg


def is_wine_available() -> bool:
    """True if a wine binary can be found on PATH."""
    from shutil import which

    return which(os.environ.get("ABOAUTO_WINE_BIN", "wine")) is not None


def is_sober_available(flatpak_id: str | None = None) -> bool:
    """True if the Sober Flatpak is installed and runnable."""
    from shutil import which

    if not which("flatpak"):
        return False
    flatpak_id = flatpak_id or DEFAULT_SOBER_FLATPAK_ID
    import subprocess

    try:
        out = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return flatpak_id in out.stdout.split()
    except Exception:  # noqa: BLE001
        return False
