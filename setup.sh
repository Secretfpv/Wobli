#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
VENV_DIR="$PROJECT_DIR/local-files/.venv"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install Python 3, then run this file again." >&2
  exit 1
fi

echo "Creating the Wobli virtual environment..."
python3 -m venv "$VENV_DIR"

echo "Installing dependencies from requirements.txt..."
"$VENV_DIR/bin/python" -m pip install --disable-pip-version-check -r "$PROJECT_DIR/requirements.txt"

echo ""
echo "Setup complete. Start Wobli with:"
echo "  python3 local-files/start.py"
