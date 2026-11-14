# aboauto

**Roblox semi account manager for Linux.**

Account Manager • Multi Instance • Instance Manager • Settings • CLI

aboauto lets you keep multiple Roblox accounts in an encrypted local store,
launch any number of Roblox clients at once (each in its own isolated Wine
prefix so they don't collide), and track/stop every running instance from one
place. It runs headless-friendly: a Flask web GUI (binds `0.0.0.0`) plus a
terminal CLI.

## Features

| Feature | What it does |
|---|---|
| **Account Manager** | Add/edit/delete Roblox accounts. Username, password, and `.ROBLOSECURITY` cookie are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256) in a local SQLite database. |
| **Multi Instance** | Launch several Roblox clients at once, each assigned to an account. Each instance gets its own `WINEPREFIX` and a staggerable launch delay. |
| **Instance Manager** | View every tracked client (PID, status, start time, log tail), stop or kill instances, stop all, clear stopped entries. |
| **Launcher backends** | **Wine** (`RobloxPlayerBeta.exe` via Wine) or **Sober** (`flatpak run org.vinegarhq.Sober`). Switch in Settings. |
| **Settings** | Point the app at your `RobloxPlayerBeta.exe` (Windows path under Wine), the `wine` binary, prefix base directory, and launch delay. |
| **CLI** | Full terminal interface: `aboauto account ...`, `aboauto instance ...`, `aboauto server`. |

## Quick start

```bash
# 1. Clone
git clone https://github.com/fak3hidden/aboauto.git
cd aboauto

# 2. Create a virtualenv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Run the web GUI
aboauto server          # or: python -m aboauto.app
# open http://localhost:8000

# 4. (CLI) Add an account and launch an instance (Wine backend)
aboauto account add --username player1 --password hunter2
aboauto instance launch --account 1

# Or use the Sober backend (VinegarHQ Flatpak client):
# flatpak install flathub org.vinegarhq.Sober
# aboauto instance launch --account 1 --launcher-mode sober
```

### Launcher backends

Roblox has no official Linux client, so aboauto launches Roblox through one of
two backends, chosen in Settings → Launcher mode:

**Wine** — launches `RobloxPlayerBeta.exe` (a Windows Roblox install) through
Wine. Install Wine (e.g. `sudo apt install wine`) and point the app at your
`RobloxPlayerBeta.exe`, e.g.:

```
~/.wine/drive_c/Program Files (x86)/Roblox/Versions/<version>/RobloxPlayerBeta.exe
```

Each Wine launch gets its own `WINEPREFIX` under
`~/.local/share/aboauto/wineprefixes/`, so multiple clients can run side by side.

**Sober** — launches `flatpak run --instance=<id> org.vinegarhq.Sober`
(VinegarHQ's unofficial Linux Roblox client running Roblox's Android build
natively). Install Sober:

```
flatpak install flathub org.vinegarhq.Sober
```

Sober handles its own login UI, so aboauto launches Sober and you pick the
account inside it. Set Launcher mode to `sober` in Settings (or pass
`--launcher-mode sober` on the CLI).

Sober uses Flatpak's ``--instance`` flag so each launch is a separate,
isolated client — multi-instance works the same as Wine mode.

### Data & security

## Data & security

- Database: `~/.local/share/aboauto/aboauto.db` (override with `ABOAUTO_DATA_DIR`)
- Encryption key: `~/.local/share/aboauto/key.bin` (mode `0600`) — **back this up**; losing it means losing saved passwords/cookies.
- Logs: `~/.local/share/aboauto/aboauto.log`

## Project structure

```
aboauto/
├── aboauto/            # Python package
│   ├── accounts.py     # Account Manager (encrypted SQLite store)
│   ├── instances.py    # Instance Manager (spawn/track/stop)
│   ├── launcher.py     # Roblox Wine launch command builder
│   ├── crypto.py       # Fernet encryption at rest
│   ├── config.py       # Paths & defaults
│   ├── app.py          # Flask web GUI + JSON API
│   └── cli.py          # Terminal CLI
├── aboauto/templates/index.html   # Single-page dashboard
├── aboauto/static/               # (CSS/JS are embedded in the template)
├── tests/
├── pyproject.toml
├── requirements.txt
└── README.md
```

## API

`GET /api/status`, `GET/POST/PUT/DELETE /api/accounts`,
`POST /api/accounts/<id>/launch`, `POST /api/instances/launch-multi`,
`GET/DELETE /api/instances/<id>`, `GET /api/instances`,
`POST /api/instances/stop-all`, `POST /api/instances/clear-stopped`,
`GET/PUT /api/settings`.

## License

MIT. See `LICENSE`.
