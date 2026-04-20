#!/bin/bash

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
BACKEND_VENV_DIR="$BACKEND_DIR/.venv"
BACKEND_PYTHON="$BACKEND_VENV_DIR/bin/python"
WITH_BACKEND=0
BACKEND_PID=""

for arg in "$@"; do
    case "$arg" in
        --with-backend)
            WITH_BACKEND=1
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: ./start.sh [--with-backend]"
            exit 1
            ;;
    esac
done

cleanup() {
    if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo
        echo "[*] Stopping Python backend..."
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

ensure_backend_env() {
    if [ -x "$BACKEND_PYTHON" ]; then
        return
    fi

    echo "[*] Backend virtual environment missing or incomplete. Rebuilding..."
    cd "$BACKEND_DIR"
    rm -rf "$BACKEND_VENV_DIR"
    python3 -m venv .venv
    "$BACKEND_PYTHON" -m pip install -r requirements.txt
}

ensure_ml_compat_env() {
    echo "[*] Verifying RTLS analytics compatibility runtime..."
    cd "$BACKEND_DIR"
    "$BACKEND_PYTHON" setup_backend.py --ensure-ml-compat
}

echo "====================================="
echo "   BRIGID RTLS Desktop Platform"
echo "====================================="
echo

ensure_backend_env
ensure_ml_compat_env

if [ "$WITH_BACKEND" -eq 1 ]; then
    echo "[*] Starting Python backend..."
    cd "$BACKEND_DIR"

    "$BACKEND_PYTHON" -m uvicorn main:app --reload --port 8000 &
    BACKEND_PID=$!
    sleep 2
    echo "[+] Backend started on http://localhost:8000"
    echo
fi

echo "[*] Starting Electron frontend..."
cd "$FRONTEND_DIR"
npm run dev
