"""
MIRAGE-X — shared decoy helpers.

Real attack tools (nmap, hydra, etc.) don't send tidy newline-delimited
text — SSH clients speak mostly binary after the initial banner exchange.
Without this, the evidence panel fills up with garbled bytes. These
helpers turn raw socket traffic into clean, demo-readable labels and
detect brute-force bursts by connection rate, so the dashboard tells a
clear story instead of showing noise.
"""
import time

_connection_log = {}  # ip -> list of recent connection timestamps
BURST_WINDOW_SECONDS = 30
BURST_THRESHOLD = 5


def classify_data(data: bytes) -> str:
    """Turns a raw chunk of socket bytes into a clean, human-readable label."""
    if not data:
        return "[empty read]"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return f"[binary data, {len(data)} bytes]"

    printable = sum(1 for c in text if c.isprintable() or c in "\r\n\t")
    ratio = printable / max(len(text), 1)
    if ratio > 0.85:
        cleaned = text.strip()
        if cleaned.startswith("SSH-"):
            return f"CLIENT_BANNER: {cleaned}"
        return cleaned if cleaned else f"[whitespace only, {len(data)} bytes]"
    return f"[binary data, {len(data)} bytes]"


def note_connection(ip: str):
    """
    Tracks connection attempts per source IP in a sliding time window.
    Returns a burst-detection label the moment the count crosses a
    multiple of BURST_THRESHOLD (so it fires periodically, not once and
    never again, but doesn't spam every single connection either).
    """
    now = time.time()
    times = _connection_log.setdefault(ip, [])
    times.append(now)
    _connection_log[ip] = [t for t in times if now - t <= BURST_WINDOW_SECONDS]
    count = len(_connection_log[ip])
    if count and count % BURST_THRESHOLD == 0:
        return (f"BRUTEFORCE_PATTERN_DETECTED: {count} connection attempts "
                f"from this IP in the last {BURST_WINDOW_SECONDS}s")
    return None
