#!/usr/bin/env bash
###############################################################################
# build.sh — Build, install, test, and run aboauto (Roblox semi account manager
# for Linux).
#
# Usage:
#   ./build.sh              # full build: venv, deps, install, tests
#   ./build.sh --no-tests   # skip the test suite
#   ./build.sh --run        # build then start the web GUI (port 8000)
#   ./build.sh --cli        # build then drop into the CLI help
###############################################################################
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_DIR"

RUN_SERVER=0
SKIP_TESTS=0

for arg in "$@"; do
  case "$arg" in
    --run)      RUN_SERVER=1 ;;
    --no-tests) SKIP_TESTS=1 ;;
    --cli)      RUN_SERVER=2 ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

echo "============================================================"
echo " aboauto — build script"
echo " Repo: $REPO_DIR"
echo "============================================================"

# ---------------------------------------------------------------------------
# 1. Python availability
# ---------------------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 is required but not installed." >&2
  exit 1
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[1/6] Python $PY_VER detected"

# ---------------------------------------------------------------------------
# 2. Virtual environment
# ---------------------------------------------------------------------------
VENV_DIR="$REPO_DIR/.venv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "[2/6] Creating virtualenv at .venv"
  python3 -m venv "$VENV_DIR"
else
  echo "[2/6] Virtualenv already present at .venv"
fi

# ---------------------------------------------------------------------------
# 3. Install dependencies + package
# ---------------------------------------------------------------------------
echo "[3/6] Installing dependencies and package"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r requirements.txt
"$VENV_DIR/bin/pip" install --quiet -e .

# ---------------------------------------------------------------------------
# 4. Run the headless test suite
# ---------------------------------------------------------------------------
if [ "$SKIP_TESTS" -eq 0 ]; then
  echo "[4/6] Running test suite"
  ABOAUTO_DATA_DIR="$(mktemp -d)" "$VENV_DIR/bin/python" -m pytest tests/ -v 2>/dev/null \
    || "$VENV_DIR/bin/python" tests/test_headless.py
else
  echo "[4/6] Skipping tests (--no-tests)"
fi

# ---------------------------------------------------------------------------
# 5. Verify CLI entry point
# ---------------------------------------------------------------------------
echo "[5/6] Verifying CLI entry point"
"$VENV_DIR/bin/aboauto" --help >/dev/null
echo "       aboauto CLI OK"

# ---------------------------------------------------------------------------
# 6. Done / optional run
# ---------------------------------------------------------------------------
echo "[6/6] Build complete"
echo ""
echo "Next steps:"
echo "  # Web GUI (binds 0.0.0.0:8000):"
echo "    ABOAUTO_DATA_DIR=\$HOME/.local/share/aboauto $VENV_DIR/bin/aboauto server"
echo "  # Or with this script:"
echo "    ./build.sh --run"
echo ""
echo "  # CLI:"
echo "    $VENV_DIR/bin/aboauto account add --username player1 --password hunter2"
echo "    $VENV_DIR/bin/aboauto instance launch --account 1"
echo ""
echo "  # Point Settings at your RobloxPlayerBeta.exe (Wine) before launching."
echo ""

if [ "$RUN_SERVER" -eq 1 ]; then
  exec "$VENV_DIR/bin/aboauto" server --port 8000
elif [ "$RUN_SERVER" -eq 2 ]; then
  exec "$VENV_DIR/bin/aboauto" --help
fi
