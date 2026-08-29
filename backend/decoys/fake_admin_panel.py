"""
MIRAGE-X — Fake Admin Panel Decoy.

An isolated HTTP decoy that looks like a corporate admin login console.
Unlike fake_ssh/fake_db (raw sockets), this speaks real HTTP so it can be
hit with curl, a browser, nmap -sV/-sC, or hydra's http-post-form module —
same "real tools against a real-looking service" story as the demo script,
just for the web surface instead of SSH/DB.

Every request becomes a clean decoy_interactions row, exactly like the
other two decoys, so the dashboard and decoy_feedback.py treat all three
uniformly. Deployed by deception.py when behavior shows ADMIN-ACTION or
PRIV-ESC — which lines up with attack_path.py's prediction that a
privilege-escalation attempt is heading for the admin panel next, so the
attacker gets shown exactly the fake resource their behavior points at.

This is NOT a real login system. No credentials are ever validated, no
session is ever created, and it never talks to anything else. It always
answers 401 after logging the attempt. Passwords are masked before being
logged — there's no reason to keep even fake credential material sitting
around in plaintext.

Safety: run this only inside an isolated lab/Docker network. No real
credentials, no real filesystem access, no outbound connections.

Usage:
    python fake_admin_panel.py --incident INC-0007 --port 8080
"""
import argparse
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db  # noqa: E402
import common  # noqa: E402

DECOY_NAME = "fake_admin_panel"
INCIDENT_ID = "INC-DEMO"  # set once at startup by serve(), same pattern as fake_ssh/fake_db

LOGIN_PAGE = b"""<!DOCTYPE html>
<html><head><title>CorpNet Admin Console</title>
<style>
body{font-family:sans-serif;background:#0d1117;color:#e6edf3;display:flex;
height:100vh;align-items:center;justify-content:center;margin:0}
.box{background:#161b22;padding:32px 40px;border-radius:8px;width:280px;
box-shadow:0 4px 18px rgba(0,0,0,.4)}
h1{font-size:18px;margin:0 0 20px}
input{width:100%;padding:8px;margin:6px 0;border-radius:4px;border:1px solid #30363d;
background:#0d1117;color:#e6edf3;box-sizing:border-box}
button{width:100%;padding:9px;margin-top:10px;border:none;border-radius:4px;
background:#238636;color:white;cursor:pointer}
</style></head>
<body><div class="box"><h1>CorpNet Admin Console</h1>
<form method="POST" action="/login">
<input name="username" placeholder="Username" autocomplete="off">
<input name="password" type="password" placeholder="Password" autocomplete="off">
<button type="submit">Sign in</button>
</form></div></body></html>"""

DENY_PAGE = b"<html><body style='font-family:sans-serif;color:#c00'>Invalid credentials.</body></html>"


def _mask(password):
    """Never log a fake password in plaintext, on principle."""
    if not password:
        return "(empty)"
    return password[0] + "*" * max(len(password) - 1, 0)


class Handler(BaseHTTPRequestHandler):
    server_version = "Apache/2.4.41"  # plausible banner for nmap -sV / curl -I, not the real thing
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # suppress default stderr logging — we print our own [fake_admin_panel] lines

    def _note_connection(self, src_ip):
        burst_label = common.note_connection(src_ip)
        if burst_label:
            db.log_decoy_interaction(INCIDENT_ID, DECOY_NAME, burst_label, src_ip)
            print(f"[fake_admin_panel] {src_ip} -> {burst_label}")

    def _log(self, src_ip, label):
        db.log_decoy_interaction(INCIDENT_ID, DECOY_NAME, label, src_ip)
        print(f"[fake_admin_panel] {src_ip} -> {label}")

    def do_GET(self):
        src_ip = self.client_address[0]
        self._note_connection(src_ip)

        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(LOGIN_PAGE)))
            self.end_headers()
            self.wfile.write(LOGIN_PAGE)
            self._log(src_ip, "PAGE_LOAD: GET / (admin login page served)")
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            self._log(src_ip, f"PROBE_ONLY: GET {self.path} (enumeration attempt, no such page)")

    def do_POST(self):
        src_ip = self.client_address[0]
        self._note_connection(src_ip)

        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""

        if self.path == "/login":
            fields = parse_qs(body.decode("utf-8", errors="replace"))
            username = fields.get("username", [""])[0] or "(blank)"
            password = fields.get("password", [""])[0]
            self.send_response(401)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(DENY_PAGE)))
            self.end_headers()
            self.wfile.write(DENY_PAGE)
            self._log(src_ip, f"LOGIN_ATTEMPT: user={username} pass={_mask(password)}")
        else:
            inner = common.classify_data(body) if body else "[empty POST]"
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            self._log(src_ip, f"PROBE_ONLY: POST {self.path} -> {inner}")


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def serve(port, incident_id):
    global INCIDENT_ID
    INCIDENT_ID = incident_id
    db.init_db()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"[fake_admin_panel] listening on 0.0.0.0:{port} for incident={incident_id}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[fake_admin_panel] shutting down")
    finally:
        srv.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--incident", default=os.environ.get("INCIDENT_ID", "INC-DEMO"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("DECOY_PORT", "8080")))
    args = parser.parse_args()
    serve(args.port, args.incident)
