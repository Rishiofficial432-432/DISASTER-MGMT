#!/bin/bash
# SIH26191 — Red Zone & Relocation Assessment
# Starts the Flask backend, which also serves the frontend.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -d ".venv" ]]; then
  echo "❌  .venv not found. Run:"
  echo "    python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi

source .venv/bin/activate
echo "✔  Virtual environment: $(which python)"
PORT="${PORT:-8080}"
echo "▶  Starting server on http://localhost:${PORT} ..."
PORT="$PORT" python backend/server.py
