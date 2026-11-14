#!/usr/bin/env bash
###############################################################################
# update.sh — Pull the latest aboauto from GitHub and rebuild.
#
# Usage:
#   ./update.sh            # git pull, reinstall deps, run tests
#   ./update.sh --no-tests # skip the test suite
#   ./update.sh --run      # build then start the web GUI (port 8000)
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
    -h|--help)
      sed -n '2,13p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

VENV_DIR="$REPO_DIR/.venv"

echo "============================================================"
echo " aboauto — update script"
echo " Repo: $REPO_DIR"
echo "============================================================"

# ---------------------------------------------------------------------------
# 1. Git pull latest from the tracked branch
# ---------------------------------------------------------------------------
echo "[1/4] Pulling latest from GitHub"
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[ERROR] Not a git repository. Clone aboauto first." >&2
  exit 1
fi

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "       On branch: $CURRENT_BRANCH"

git fetch origin
git merge "origin/$CURRENT_BRANCH" --ff-only || {
  echo "[WARN] Fast-forward failed; attempting rebase"
  git rebase "origin/$CURRENT_BRANCH"
}

# ---------------------------------------------------------------------------
# 2. Python availability
# ---------------------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 is required but not installed." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 3. Refresh the virtualenv (reuse if present, create otherwise)
# ---------------------------------------------------------------------------
echo "[2/4] Preparing virtualenv"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  echo "       Creating virtualenv at .venv"
  python3 -m venv "$VENV_DIR"
fi

echo "[3/4] Installing dependencies and package"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -r requirements.txt
"$VENV_DIR/bin/pip" install --quiet -e .

# ---------------------------------------------------------------------------
# 4. Run the headless test suite
# ---------------------------------------------------------------------------
if [ "$SKIP_TESTS" -eq 0 ]; then
  echo "[4/4] Running test suite"
  ABOAUTO_DATA_DIR="$(mktemp -d)" "$VENV_DIR/bin/python" -m pytest tests/ -v 2>/dev/null \
    || "$VENV_DIR/bin/python" tests/test_headless.py
else
  echo "[4/4] Skipping tests (--no-tests)"
fi

echo ""
echo "============================================================"
echo " aboauto updated successfully"
echo "============================================================"
echo ""
echo "Web GUI (binds 0.0.0.0:8000):"
echo "  ABOAUTO_DATA_DIR=\$HOME/.local/share/aboauto $VENV_DIR/bin/aboauto server"
echo "  # Or with this script:"
echo "  ./update.sh --run"
echo ""
echo "CLI:"
echo "  $VENV_DIR/bin/aboauto account add --username player1 --password hunter2"
echo "  $VENV_DIR/bin/aboauto instance launch --account 1"
echo ""

if [ "$RUN_SERVER" -eq 1 ]; then
  exec "$VENV_DIR/bin/aboauto" server --port 8000
fi
