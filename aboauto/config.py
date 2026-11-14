"""Runtime configuration and filesystem paths for aboauto.

All user data lives under the data directory (default: ``~/.local/share/aboauto``)
so the application is portable and does not touch your Roblox installation.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Default locations
# ---------------------------------------------------------------------------
DATA_DIR = Path(os.environ.get("ABOAUTO_DATA_DIR", Path.home() / ".local/share/aboauto"))
DB_PATH = DATA_DIR / "aboauto.db"
KEY_PATH = DATA_DIR / "key.bin"
SETTINGS_PATH = DATA_DIR / "settings.json"
LOG_PATH = DATA_DIR / "aboauto.log"

# Roblox on Linux is normally launched through Wine. These defaults are
# placeholders - the user points the app at their own Roblox install via the
# Settings page (or CLI). Nothing here is required to run the manager itself.
DEFAULT_ROBLOX_EXE = os.environ.get(
    "ABOAUTO_ROBLOX_EXE",
    str(Path.home() / ".wine/drive_c/Program Files (x86)/Roblox/Versions/version/RobloxPlayerBeta.exe"),
)
DEFAULT_WINE_PREFIX_BASE = os.environ.get(
    "ABOAUTO_WINE_PREFIX_BASE", str(DATA_DIR / "wineprefixes")
)
DEFAULT_WINE_BIN = os.environ.get("ABOAUTO_WINE_BIN", "wine")

# Sober (VinegarHQ) Flatpak client for Roblox on Linux.
DEFAULT_SOBER_BIN = os.environ.get("ABOAUTO_SOBER_BIN", "flatpak")
DEFAULT_SOBER_FLATPAK_ID = os.environ.get(
    "ABOAUTO_SOBER_FLATPAK_ID", "org.vinegarhq.Sober"
)
DEFAULT_LAUNCHER_MODE = os.environ.get("ABOAUTO_LAUNCHER_MODE", "wine")

# ---------------------------------------------------------------------------
# Settings schema (stored as JSON in SETTINGS_PATH)
# ---------------------------------------------------------------------------
DEFAULTS: dict = {
    "roblox_exe": DEFAULT_ROBLOX_EXE,
    "wine_bin": DEFAULT_WINE_BIN,
    "wine_prefix_base": DEFAULT_WINE_PREFIX_BASE,
    "launch_delay_seconds": 2.0,  # stagger between multi-instance launches
    "use_separate_prefix_per_instance": True,
    "auto_bring_to_front": False,
    "theme": "dark",
    "launcher_mode": DEFAULT_LAUNCHER_MODE,
    "sober_bin": DEFAULT_SOBER_BIN,
    "sober_flatpak_id": DEFAULT_SOBER_FLATPAK_ID,
}


def ensure_data_dir() -> Path:
    """Create the data directory (and subdirs) if missing. Returns the dir."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "wineprefixes").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
    return DATA_DIR
