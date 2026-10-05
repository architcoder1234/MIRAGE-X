"""
MIRAGE-X — Fake SSH Decoy.

A minimal, isolated TCP socket service that *looks* like an SSH banner and
logs whatever the connecting client sends. This is NOT a real SSH
implementation and accepts no real authentication — it exists purely to
collect interaction telemetry for the demo.

Safety: run this only inside an isolated lab/Docker network. No real
credentials, no real filesystem access, no outbound connections.

Usage:
    python fake_ssh.py --incident INC-0007 --port 2222
"""
import argparse
import socket
import sys
import os
import threading

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db  # noqa: E402
import common  # noqa: E402

BANNER = b"SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.4\r\n"
MAX_CLIENT_BYTES = 64 * 1024


def handle_client(conn, addr, incident_id, decoy_name):
    src_ip = addr[0]
    received_any = False
    try:
        conn.sendall(BANNER)
        conn.settimeout(15)
        total_bytes = 0
        while True:
            data = conn.recv(1024)
            if not data:
                break
            received_any = True
            total_bytes += len(data)
            if total_bytes > MAX_CLIENT_BYTES:
                db.log_decoy_interaction(incident_id, decoy_name, "INPUT_LIMIT_REACHED", src_ip)
                break
            label = common.classify_data(data)
            db.log_decoy_interaction(incident_id, decoy_name, label, src_ip)
            print(f"[fake_ssh] {src_ip} -> {label}")
    except (socket.timeout, ConnectionResetError):
        pass
    finally:
        if not received_any:
            label = "PROBE_ONLY: connected and disconnected without sending data (looks like a scan)"
            db.log_decoy_interaction(incident_id, decoy_name, label, src_ip)
            print(f"[fake_ssh] {src_ip} -> {label}")
        conn.close()


def serve(port, incident_id, decoy_name="fake_ssh"):
    db.init_db()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", port))
    srv.listen(5)
    print(f"[fake_ssh] listening on 0.0.0.0:{port} for incident={incident_id}")
    try:
        while True:
            conn, addr = srv.accept()
            db.log_decoy_interaction(incident_id, decoy_name, "CONNECTION_OPENED", addr[0])
            burst_label = common.note_connection(addr[0])
            if burst_label:
                db.log_decoy_interaction(incident_id, decoy_name, burst_label, addr[0])
                print(f"[fake_ssh] {addr[0]} -> {burst_label}")
            t = threading.Thread(target=handle_client, args=(conn, addr, incident_id, decoy_name), daemon=True)
            t.start()
    except KeyboardInterrupt:
        print("\n[fake_ssh] shutting down")
    finally:
        srv.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident", default=os.environ.get("INCIDENT_ID", "INC-DEMO"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DECOY_PORT", "2222")))
    args = parser.parse_args()
    serve(args.port, args.incident)
