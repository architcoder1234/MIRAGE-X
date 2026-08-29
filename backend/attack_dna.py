"""
MIRAGE-X — Attack DNA.

Converts raw events into a behavioral fingerprint (an ordered sequence of
event categories) and a risk score. Kept rule-based and transparent on
purpose — every score is explainable, which matters for the "Explainable
AI Defender" pitch and for judges who ask "how does that number happen?".
"""

# Points contributed per event category towards the 0-100 risk score.
# Tuned so a single scenario walks HIGH by the time DB-SEARCH happens.
RISK_WEIGHTS = {
    "RECON-SCAN": 5,
    "AUTH-SSH": 8,           # each failed/attempt adds a little
    "PRIV-ESC": 20,
    "DOWNLOAD": 20,
    "DB-SEARCH": 30,
    "ADMIN-ACTION": 2,
    "BRUTEFORCE-CONFIRMED": 25,  # real, confirmed brute-force traffic against a decoy
    "CRED-SPRAY": 10,            # per attempt — lower than AUTH-SSH since each guess is quieter,
                                  # but the pattern (many users, one password) is what actually matters
    "LATERAL-MOVE": 22,           # moved beyond the entry host — meaningfully worse than staying put
    "EXFIL-STAGING": 28,          # packaging data for exit — one step from actual loss
    "EXFIL-TRANSFER": 35,         # data is actually leaving — worst single signal in the system
    "SUPPLY-CHAIN": 25,           # compromised dependency/pipeline step, not a human at a terminal
    "LOTL-ACTIVITY": 12,          # legitimate tool misused — individually quiet, dangerous in sequence
    "INSIDER-ACCESS": 6,          # valid creds, working hours — looks benign until the pattern doesn't
}

CONFIDENCE_THRESHOLDS = {
    "HIGH": 0.70,
    "MEDIUM": 0.45,
}


def build_behavior_sequence(events):
    """Ordered list of event_type strings — the 'DNA strand'."""
    return [e["event_type"] for e in events]


def compute_risk_score(events):
    """
    Returns a 0-100 risk score. Simple additive model, capped, with a
    small escalation bonus if privilege escalation is followed by a
    download or DB search (a real chain, not isolated noise).
    """
    score = 0
    seq = build_behavior_sequence(events)
    for etype in seq:
        score += RISK_WEIGHTS.get(etype, 1)

    if "PRIV-ESC" in seq:
        idx = seq.index("PRIV-ESC")
        if any(e in seq[idx:] for e in ("DOWNLOAD", "DB-SEARCH")):
            score += 15  # chained escalation is worse than isolated events

    if "EXFIL-STAGING" in seq and "EXFIL-TRANSFER" in seq:
        score += 15  # staged AND transferred — the full exfil chain completed, not just attempted

    if "LATERAL-MOVE" in seq and any(e in seq for e in ("EXFIL-STAGING", "EXFIL-TRANSFER", "DB-SEARCH")):
        score += 10  # moved to another host and then went after data — deliberate, not exploratory

    return min(score, 100)


def risk_to_confidence_band(risk_score):
    """
    Maps 0-100 risk score onto the frozen confidence thresholds
    (kept in the same 0.70 / 0.45 language as the similarity engine so
    both subsystems speak the same confidence vocabulary).
    """
    normalized = risk_score / 100
    if normalized >= CONFIDENCE_THRESHOLDS["HIGH"]:
        return "HIGH"
    if normalized >= CONFIDENCE_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


def fingerprint(events):
    seq = build_behavior_sequence(events)
    risk = compute_risk_score(events)
    band = risk_to_confidence_band(risk)
    return {
        "behavior_sequence": seq,
        "risk_score": risk,
        "risk_band": band,
    }
