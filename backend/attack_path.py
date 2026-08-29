"""
MIRAGE-X — Attack-Path & Intent Engine (P1).

Small, fixed simulated network graph. Given the current behavior sequence,
predicts the attacker's likely next target using simple, explainable rules —
no ML needed for the hackathon. This is what lets MIRAGE-X ask "where will
they go next?" instead of only "is this malicious?"

Kept intentionally simple: a handful of nodes, a handful of edges, and a
rule table mapping observed event types to a predicted next node + reason.
"""

# Fixed demo network. Edges are directed: attacker moves along them.
NODES = {
    "internet": {"label": "Internet / Attacker", "type": "external"},
    "host-03": {"label": "Host-03 (jump box)", "type": "host"},
    "host-07": {"label": "Host-07 (finance workstation)", "type": "host"},
    "db-server": {"label": "DB Server", "type": "asset"},
    "admin-panel": {"label": "Admin Panel", "type": "asset"},
    "file-share": {"label": "Internal File Share", "type": "asset"},
    "exfil-gateway": {"label": "External Egress Point", "type": "external"},
}

EDGES = [
    ("internet", "host-03"),
    ("host-03", "db-server"),
    ("host-03", "admin-panel"),
    ("host-03", "file-share"),
    ("host-03", "host-07"),        # lateral movement hop
    ("host-07", "db-server"),      # finance workstation also has DB access
    ("file-share", "exfil-gateway"),  # staged data leaving the network
]

# event_type -> (predicted_next_node, reason)
# Order matters: first matching rule (scanning the behavior sequence from the
# end) wins, since the most recent event is the strongest signal of intent.
PREDICTION_RULES = [
    ("EXFIL-TRANSFER", "exfil-gateway", "data transfer already in progress -> attacker is actively exfiltrating through the egress point"),
    ("EXFIL-STAGING", "exfil-gateway", "attacker is archiving/staging data -> next step is almost always pushing it out through the egress point"),
    ("LATERAL-MOVE", "host-07", "attacker pivoted off the entry host -> likely continuing to move toward higher-value hosts"),
    ("DB-SEARCH", "db-server", "attacker is actively querying for database credentials/config -> likely pivot target is db-server"),
    ("BRUTEFORCE-CONFIRMED", "host-03", "confirmed real brute-force traffic against the decoy -> attacker still focused on obtaining SSH access"),
    ("CRED-SPRAY", "host-03", "password-spray pattern against multiple accounts -> attacker still hunting for a valid foothold on host-03"),
    ("DOWNLOAD", "file-share", "attacker fetched a tool/payload -> often followed by staging on a file share"),
    ("SUPPLY-CHAIN", "host-03", "compromised dependency/pipeline executed -> behaves like an attacker already has a foothold on host-03"),
    ("LOTL-ACTIVITY", "admin-panel", "living-off-the-land tool use -> often precedes quiet privilege/admin actions"),
    ("PRIV-ESC", "admin-panel", "privilege escalation attempt -> likely aiming for admin-level access next"),
    ("INSIDER-ACCESS", "file-share", "valid-credential access outside normal pattern -> worth watching what gets touched on the file share"),
    ("AUTH-SSH", "host-03", "still working the entry point -> attacker likely stays on host-03 for now"),
    ("RECON-SCAN", "host-03", "early reconnaissance -> attacker probing host-03 before moving further"),
]


def predict_next_target(behavior_sequence):
    """
    Walk the behavior sequence from most recent to oldest, return the first
    rule that matches. Falls back to 'unknown' if nothing recognized yet.
    """
    for event_type in reversed(behavior_sequence):
        for rule_event, target_node, reason in PREDICTION_RULES:
            if event_type == rule_event:
                return {
                    "current_position": "host-03",
                    "predicted_next_target": target_node,
                    "predicted_next_label": NODES[target_node]["label"],
                    "reason": reason,
                    "triggering_event": event_type,
                }
    return {
        "current_position": "internet",
        "predicted_next_target": None,
        "predicted_next_label": None,
        "reason": "no recognizable attack behavior yet",
        "triggering_event": None,
    }


def graph_snapshot():
    """Static graph description for the dashboard to render."""
    return {"nodes": NODES, "edges": EDGES}
