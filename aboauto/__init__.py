"""aboauto - Roblox semi account manager for Linux.

Features:
  * Account Manager - store and launch Roblox accounts (credentials encrypted at rest)
  * Multi Instance - launch several Roblox clients at once, each with its own account
  * Instance Manager - view, restart, and stop running Roblox instances

Designed for Linux (Roblox is typically run through Wine). Runs headless-friendly:
a Flask web GUI (binds 0.0.0.0) plus a terminal CLI.
"""

__version__ = "0.1.0"
