# MIRAGE-X — Fake SSH decoy, isolated container.
# Code is bind-mounted at runtime (see ../../docker-compose.yml) so it shares
# db.py / common.py / the SQLite file with the host-run FastAPI backend —
# the decoy's evidence shows up in the same dashboard, live.
FROM python:3.11-slim
WORKDIR /app
# Stdlib only (socket, sqlite3, threading) — no pip install needed.
CMD ["python", "decoys/fake_ssh.py"]
