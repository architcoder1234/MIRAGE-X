"""
MIRAGE-X — Fake Database Decoy (P1 stretch).

Same isolated-socket pattern as fake_ssh.py, but responds with a fake
MySQL-style greeting so a simulator/tool probing for "database resources"
gets a plausible-looking target instead of anything real. Reuses the same
decoy_interactions log table so the dashboard/evidence panel treats both
decoys uniformly.

Usage:
    python fake_db.py --incident INC-0007 --port 3307
"""
import argparse
import socket
import sys
import os
import threading

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db  # noqa: E402
import common  # noqa: E402

# Fake MySQL-ish handshake packet (not protocol-accurate — just plausible bytes)
FAKE_GREETING = b"\x4a\x00\x00\x00\x0a5.7.44-log\x00"


def handle_client(conn, addr, incident_id, decoy_name):
    src_ip = addr[0]
    received_any = False
    try:
        conn.sendall(FAKE_GREETING)
        conn.settimeout(15)
        while True:
            data = conn.recv(1024)
            if not data:
                break
            received_any = True
            label = common.classify_data(data)
            db.log_decoy_interaction(incident_id, decoy_name, label, src_ip)
            print(f"[fake_db] {src_ip} -> {label}")
    except (socket.timeout, ConnectionResetError):
        pass
    finally:
        if not received_any:
            label = "PROBE_ONLY: connected and disconnected without sending data (looks like a scan)"
            db.log_decoy_interaction(incident_id, decoy_name, label, src_ip)
            print(f"[fake_db] {src_ip} -> {label}")
        conn.close()


def serve(port, incident_id, decoy_name="fake_db"):
    db.init_db()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    print(f"[fake_db] listening on 0.0.0.0:{port} for incident={incident_id}")
    try:
        while True:
            conn, addr = srv.accept()
            db.log_decoy_interaction(incident_id, decoy_name, "CONNECTION_OPENED", addr[0])
            burst_label = common.note_connection(addr[0])
            if burst_label:
                db.log_decoy_interaction(incident_id, decoy_name, burst_label, addr[0])
                print(f"[fake_db] {addr[0]} -> {burst_label}")
            t = threading.Thread(target=handle_client, args=(conn, addr, incident_id, decoy_name), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\n[fake_db] shutting down")
    finally:
        srv.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident", default=os.environ.get("INCIDENT_ID", "INC-DEMO"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DECOY_PORT", "3307")))
    args = parser.parse_args()
    serve(args.port, args.incident)
