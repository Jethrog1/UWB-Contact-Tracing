#!/bin/bash

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
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

echo "====================================="
echo "   BRIGID RTLS Desktop Platform"
echo "====================================="
echo

if [ "$WITH_BACKEND" -eq 1 ]; then
    echo "[*] Starting Python backend..."
    cd "$BACKEND_DIR"

    if [ ! -d ".venv" ]; then
        echo "[*] Backend virtual environment not found. Creating one..."
        python3 -m venv .venv
        ./.venv/bin/pip install -r requirements.txt
    fi

    ./.venv/bin/python -m uvicorn main:app --reload --port 8000 &
    BACKEND_PID=$!
    sleep 2
    echo "[+] Backend started on http://localhost:8000"
    echo
fi

echo "[*] Starting Electron frontend..."
cd "$FRONTEND_DIR"
npm run dev
