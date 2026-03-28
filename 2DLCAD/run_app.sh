#!/bin/bash
# Ensure we are in the script's directory
cd "$(dirname "$0")"

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Creating one..."
    python3 -m venv .venv
    ./.venv/bin/pip install -r requirements.txt
fi

# Run the app using the virtual environment's Python
./.venv/bin/python main_qt.py
