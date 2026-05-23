#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# setup_venv.sh — one-time project setup
#   1. Create a virtual environment and install dependencies
#   2. Create config.ini from config.example.ini (first run only)
#   3. Check/create databases
# ---------------------------------------------------------------------------
set -euo pipefail

VENV_DIR=".venv"
PYTHON="${PYTHON:-python3}"

# ---------------------------------------------------------------------------
# 1. Virtual environment & dependencies
# ---------------------------------------------------------------------------
echo "=== 1/3  Virtual environment ==="
if [[ ! -d "$VENV_DIR" ]]; then
    echo "Creating virtual environment in ${VENV_DIR}/ ..."
    "$PYTHON" -m venv "$VENV_DIR"
else
    echo "${VENV_DIR}/ already exists — skipping creation."
fi

echo "Upgrading pip ..."
"$VENV_DIR/bin/pip" install --upgrade pip

echo "Installing requirements ..."
"$VENV_DIR/bin/pip" install -r requirements.txt
echo "Dependencies installed."

# ---------------------------------------------------------------------------
# 2. Configuration
# ---------------------------------------------------------------------------
echo ""
echo "=== 2/3  Configuration ==="
"$VENV_DIR/bin/python" scripts/setup_config.py

# ---------------------------------------------------------------------------
# 3. Databases
# ---------------------------------------------------------------------------
echo ""
echo "=== 3/3  Databases ==="
"$VENV_DIR/bin/python" scripts/init_db.py

# ---------------------------------------------------------------------------
echo ""
echo "Setup complete."
echo ""
echo "Activate the environment with:"
echo "  source ${VENV_DIR}/bin/activate"
echo ""
echo "Start the development server with:"
echo "  uvicorn app.main:app --reload"
