#!/usr/bin/env bash
# MIRAGE-X — one-command reset before each demo run.
set -e
cd "$(dirname "$0")/backend"

echo "Resetting MIRAGE-X memory, schema metadata, alerts, and decoy evidence (DB wipe)..."
python3 -c "import db; db.init_db(reset=True)"

echo "Done. Fresh incident memory. Restart uvicorn if it's already running:"
echo "  uvicorn main:app --reload --port 8000"
