"""
MIRAGE-X — Decoy Evidence Feedback.

Converts logged decoy interactions (real nmap/hydra/netcat traffic against
fake_ssh/fake_db) into proper `events` rows, so a real attack against a
decoy actually moves the risk score and confidence — not just shows up as
text in the evidence panel. Each decoy_interactions row is folded in
exactly once (tracked via the `folded` column), so calling /recompute
repeatedly doesn't double-count the same traffic.
"""
import db

# decoy name -> event type for "a real protocol-level interaction happened here"
DECOY_DEFAULT_EVENT = {
    "fake_db": "DB-SEARCH",
    "fake_ssh": "AUTH-SSH",
    "fake_admin_panel": "ADMIN-ACTION",
}


def _event_type_for(decoy, command):
    if command.startswith("CONNECTION_OPENED"):
        return None  # informational only — the follow-up label carries the real signal
    if command.startswith("BRUTEFORCE_PATTERN_DETECTED"):
        return "BRUTEFORCE-CONFIRMED"
    if command.startswith("PROBE_ONLY"):
        return "RECON-SCAN"
    # CLIENT_BANNER, raw binary handshake data, or manually typed text all
    # count as a genuine protocol-level interaction with the decoy
    return DECOY_DEFAULT_EVENT.get(decoy, "AUTH-SSH")


def fold_decoy_evidence(incident_id):
    """
    Reads any not-yet-folded decoy_interactions for this incident, inserts
    a matching event for each, and marks them folded. Returns the list of
    event types that were folded in (for the API response / summary text).
    """
    rows = db.get_unfolded_decoy_interactions(incident_id)
    folded_ids = []
    folded_event_types = []

    for row in rows:
        event_type = _event_type_for(row["decoy"], row["command"])
        folded_ids.append(row["id"])
        if event_type is None:
            continue
        db.insert_event(
            incident_id, event_type, row["src_ip"],
            host=f"decoy:{row['decoy']}", user="attacker",
            detail=f"folded from decoy evidence: {row['command']}",
        )
        folded_event_types.append(event_type)

    db.mark_decoy_interactions_folded(folded_ids)
    return folded_event_types
