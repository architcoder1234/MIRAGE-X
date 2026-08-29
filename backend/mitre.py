"""
MIRAGE-X — MITRE ATT&CK Mapping.

Maps every internal event_type to a real MITRE ATT&CK (Enterprise) technique
ID + name. This is deliberately a flat, static dictionary — no external API
calls, no version drift risk right before a demo — but it's what lets the
Explainable AI Defender say "this is T1110.003 (Password Spraying)" instead
of just "AUTH-SSH happened a lot", which is the difference between a toy
label and something a SOC analyst recognizes instantly.

Reference: https://attack.mitre.org/matrices/enterprise/
"""

# event_type -> (technique_id, technique_name, tactic)
TECHNIQUE_MAP = {
    "RECON-SCAN": ("T1595", "Active Scanning", "Reconnaissance"),
    "AUTH-SSH": ("T1110", "Brute Force", "Credential Access"),
    "CRED-SPRAY": ("T1110.003", "Password Spraying", "Credential Access"),
    "PRIV-ESC": ("T1068", "Exploitation for Privilege Escalation", "Privilege Escalation"),
    "DOWNLOAD": ("T1105", "Ingress Tool Transfer", "Command and Control"),
    "DB-SEARCH": ("T1213", "Data from Information Repositories", "Collection"),
    "ADMIN-ACTION": ("T1098", "Account Manipulation", "Persistence"),
    "BRUTEFORCE-CONFIRMED": ("T1110.001", "Password Guessing", "Credential Access"),
    "LATERAL-MOVE": ("T1021", "Remote Services", "Lateral Movement"),
    "EXFIL-STAGING": ("T1560", "Archive Collected Data", "Collection"),
    "EXFIL-TRANSFER": ("T1048", "Exfiltration Over Alternative Protocol", "Exfiltration"),
    "SUPPLY-CHAIN": ("T1195", "Supply Chain Compromise", "Initial Access"),
    "LOTL-ACTIVITY": ("T1059", "Command and Scripting Interpreter", "Execution"),
    "INSIDER-ACCESS": ("T1078", "Valid Accounts", "Defense Evasion"),
    "RECON-SCAN-CONFIRMED": ("T1595", "Active Scanning", "Reconnaissance"),
}


def techniques_for_sequence(behavior_sequence):
    """
    Returns a de-duplicated, order-preserved list of {event_type, technique_id,
    technique_name, tactic} dicts for a behavior sequence. Unknown event types
    are skipped rather than guessed at — an incomplete mapping is honest,
    a fabricated one isn't.
    """
    seen = set()
    out = []
    for event_type in behavior_sequence:
        if event_type in seen:
            continue
        seen.add(event_type)
        mapping = TECHNIQUE_MAP.get(event_type)
        if not mapping:
            continue
        tid, tname, tactic = mapping
        out.append({
            "event_type": event_type,
            "technique_id": tid,
            "technique_name": tname,
            "tactic": tactic,
        })
    return out
