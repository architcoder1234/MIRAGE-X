"""
MIRAGE-X — Windows-friendly stand-in for `hydra`.

Hydra doesn't have a native Windows build, so this sends the same kind of
repeated login-attempt traffic straight over TCP to the fake SSH decoy,
so the decoy's classify_data() picks it up as a brute-force pattern.

Usage:
    python brute_force_sim.py --host localhost --port 2222 --attempts 8
"""
import argparse
import socket
import time

CREDS = [
    ("admin", "admin"), ("admin", "password"), ("root", "toor"),
    ("admin", "123456"), ("user", "letmein"), ("root", "admin123"),
    ("admin", "qwerty"), ("test", "test123"),
]


def attempt(host, port, user, pwd):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect((host, port))
        s.recv(1024)  # banner
        s.sendall(f"USER {user}\r\nPASS {pwd}\r\n".encode())
        time.sleep(0.2)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=2222)
    p.add_argument("--attempts", type=int, default=len(CREDS))
    args = p.parse_args()

    for i, (user, pwd) in enumerate(CREDS[: args.attempts]):
        try:
            attempt(args.host, args.port, user, pwd)
            print(f"[{i+1}] tried {user}:{pwd}")
        except Exception as e:
            print(f"[{i+1}] failed to connect: {e}")
        time.sleep(0.3)
