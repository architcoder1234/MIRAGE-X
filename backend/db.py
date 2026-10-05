"""
MIRAGE-X — SQLite data layer.
Keeps the schema deliberately small and frozen for the hackathon so
every other module can rely on it without churn.
"""
import sqlite3
import json
import os
import threading
from datetime import datetime, timezone

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "mirage_x.db")
DB_PATH = os.environ.get("MIRAGE_DB_PATH", DEFAULT_DB_PATH)
CURRENT_SCHEMA_VERSION = 1
WRITE_LOCK = threading.RLock()


def _ensure_column(conn, table, column, definition):
    columns = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def get_conn():
    parent = os.path.dirname(os.path.abspath(DB_PATH))
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    journal_mode = os.environ.get("MIRAGE_JOURNAL_MODE", "WAL").upper()
    if journal_mode not in {"WAL", "DELETE"}:
        journal_mode = "WAL"
    conn.execute(f"PRAGMA journal_mode={journal_mode}")
    return conn


def init_db(reset: bool = False):
    with WRITE_LOCK:
        conn = get_conn()
        conn.executescript(
            """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT,
            ts TEXT,
            event_type TEXT,       -- e.g. AUTH-SSH, PRIV-ESC, DOWNLOAD, DB-SEARCH
            src_ip TEXT,
            host TEXT,
            user TEXT,
            detail TEXT
        );

        CREATE TABLE IF NOT EXISTS incidents (
            incident_id TEXT PRIMARY KEY,
            created_at TEXT,
            behavior_sequence TEXT,   -- JSON list
            risk_score REAL,
            confidence TEXT,          -- HIGH / MEDIUM / LOW
            decoy_deployed TEXT,      -- decoy name or NULL
            similarity_top_match TEXT,-- JSON {incident_id, score, matched_features}
            summary TEXT,             -- AI/explainable-defender text
            status TEXT DEFAULT 'OPEN'
        );

        CREATE TABLE IF NOT EXISTS decoy_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT,
            decoy TEXT,
            ts TEXT,
            command TEXT,
            src_ip TEXT,
            folded INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS alert_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id TEXT,
            ts TEXT,
            severity TEXT,
            channel TEXT,
            message TEXT
        );
        """
        )
        if reset:
            conn.executescript(
                """
                DELETE FROM events;
                DELETE FROM incidents;
                DELETE FROM decoy_interactions;
                DELETE FROM alert_log;
                """
            )
        _ensure_column(conn, "incidents", "status", "TEXT DEFAULT 'OPEN'")
        _ensure_column(conn, "decoy_interactions", "folded", "INTEGER DEFAULT 0")
        row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (CURRENT_SCHEMA_VERSION,),
            )
        else:
            conn.execute(
                "UPDATE schema_version SET version=?",
                (CURRENT_SCHEMA_VERSION,),
            )
        conn.commit()
        conn.close()


def health_check():
    conn = get_conn()
    try:
        conn.execute("SELECT 1").fetchone()
        return True
    finally:
        conn.close()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def insert_event(incident_id, event_type, src_ip, host, user, detail=""):
    with WRITE_LOCK:
        conn = get_conn()
        conn.execute(
            "INSERT INTO events (incident_id, ts, event_type, src_ip, host, user, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (incident_id, now_iso(), event_type, src_ip, host, user, detail),
        )
        conn.commit()
        conn.close()


def get_events(incident_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM events WHERE incident_id=? ORDER BY id", (incident_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_incident(incident_id, behavior_sequence, risk_score, confidence,
                     decoy_deployed=None, similarity_top_match=None, summary=""):
    with WRITE_LOCK:
        conn = get_conn()
        conn.execute(
            """
        INSERT INTO incidents (incident_id, created_at, behavior_sequence, risk_score,
            confidence, decoy_deployed, similarity_top_match, summary)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(incident_id) DO UPDATE SET
            behavior_sequence=excluded.behavior_sequence,
            risk_score=excluded.risk_score,
            confidence=excluded.confidence,
            decoy_deployed=excluded.decoy_deployed,
            similarity_top_match=excluded.similarity_top_match,
            summary=excluded.summary
            """,
            (
                incident_id, now_iso(), json.dumps(behavior_sequence), risk_score,
                confidence, decoy_deployed,
                json.dumps(similarity_top_match) if similarity_top_match else None,
                summary,
            ),
        )
        conn.commit()
        conn.close()


def get_incident(incident_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM incidents WHERE incident_id=?", (incident_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["behavior_sequence"] = json.loads(d["behavior_sequence"] or "[]")
    d["similarity_top_match"] = json.loads(d["similarity_top_match"]) if d["similarity_top_match"] else None
    return d


def list_incidents():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM incidents ORDER BY created_at DESC").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["behavior_sequence"] = json.loads(d["behavior_sequence"] or "[]")
        d["similarity_top_match"] = json.loads(d["similarity_top_match"]) if d["similarity_top_match"] else None
        out.append(d)
    return out


def log_decoy_interaction(incident_id, decoy, command, src_ip):
    with WRITE_LOCK:
        conn = get_conn()
        conn.execute(
            "INSERT INTO decoy_interactions (incident_id, decoy, ts, command, src_ip) "
            "VALUES (?, ?, ?, ?, ?)",
            (incident_id, decoy, now_iso(), command, src_ip),
        )
        conn.commit()
        conn.close()


def get_decoy_interactions(incident_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM decoy_interactions WHERE incident_id=? ORDER BY id",
        (incident_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unfolded_decoy_interactions(incident_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM decoy_interactions WHERE incident_id=? AND folded=0 ORDER BY id",
        (incident_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_decoy_interactions_folded(ids):
    if not ids:
        return
    with WRITE_LOCK:
        conn = get_conn()
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE decoy_interactions SET folded=1 WHERE id IN ({placeholders})",
            ids,
        )
        conn.commit()
        conn.close()


def log_alert(incident_id, severity, channel, message):
    with WRITE_LOCK:
        conn = get_conn()
        conn.execute(
            "INSERT INTO alert_log (incident_id, ts, severity, channel, message) "
            "VALUES (?, ?, ?, ?, ?)",
            (incident_id, now_iso(), severity, channel, message),
        )
        conn.commit()
        conn.close()


def get_alerts(limit=50):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM alert_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_last_alert_for_incident(incident_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM alert_log WHERE incident_id=? ORDER BY id DESC LIMIT 1",
        (incident_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
