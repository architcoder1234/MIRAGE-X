"""
MIRAGE-X — Controlled Attacker Simulator.

Generates repeatable, safe, synthetic event sequences that stand in for a
real attacker. Every scenario is a list of (event_type, detail) tuples fed
into the event collector via db.insert_event(). No real network activity,
no real credentials — pure simulation for demo purposes.
"""
import random

SCENARIOS = {
    # Full kill-chain style scenario -> should trigger DB decoy escalation
    "recon_to_db_hunt": [
        ("RECON-SCAN", "port scan on host-03 from attacker"),
        ("AUTH-SSH", "failed login attempt (user: admin)"),
        ("AUTH-SSH", "failed login attempt (user: root)"),
        ("AUTH-SSH", "successful test login (user: svc-test)"),
        ("PRIV-ESC", "sudo attempt on low-priv account"),
        ("DOWNLOAD", "suspicious binary fetched via curl"),
        ("DB-SEARCH", "querying for database credentials / config files"),
    ],
    # Brute force only -> should stay at SSH decoy, lower risk
    "ssh_bruteforce_only": [
        ("RECON-SCAN", "port scan on host-01"),
        ("AUTH-SSH", "failed login attempt (user: admin)"),
        ("AUTH-SSH", "failed login attempt (user: admin)"),
        ("AUTH-SSH", "failed login attempt (user: admin)"),
        ("AUTH-SSH", "failed login attempt (user: admin)"),
    ],
    # Benign traffic -> should stay LOW risk, no decoy
    "benign_admin_login": [
        ("AUTH-SSH", "successful login (user: known-admin, expected schedule)"),
        ("ADMIN-ACTION", "routine config check"),
    ],
    # Same behavior sequence as recon_to_db_hunt but different IOCs
    # -> your best "explainable memory" demo pair
    "recon_to_db_hunt_variant_ip": [
        ("RECON-SCAN", "port scan on host-07 from different attacker"),
        ("AUTH-SSH", "failed login attempt (user: operator)"),
        ("AUTH-SSH", "failed login attempt (user: backup)"),
        ("AUTH-SSH", "successful test login (user: svc-legacy)"),
        ("PRIV-ESC", "sudo attempt on low-priv account"),
        ("DOWNLOAD", "suspicious script fetched via wget"),
        ("DB-SEARCH", "querying for database credentials / config files"),
    ],

    # Password spray: many usernames, one password each, spread out to
    # dodge per-IP lockouts — distinct signature from ssh_bruteforce_only,
    # which is one username hammered repeatedly.
    "password_spray_campaign": [
        ("RECON-SCAN", "enumerating valid usernames via SMTP/VPN portal"),
        ("CRED-SPRAY", "login attempt (user: jsmith, password: Summer2026!)"),
        ("CRED-SPRAY", "login attempt (user: mchen, password: Summer2026!)"),
        ("CRED-SPRAY", "login attempt (user: rpatel, password: Summer2026!)"),
        ("CRED-SPRAY", "login attempt (user: agupta, password: Summer2026!)"),
        ("AUTH-SSH", "successful login (user: rpatel) — spray landed"),
        ("PRIV-ESC", "sudo attempt using compromised rpatel account"),
    ],

    # Lateral movement: attacker doesn't stop at the entry host, pivots to
    # a second host and keeps going — most real breaches involve this and
    # it's the piece the original 4 scenarios didn't cover at all.
    "lateral_movement_breach": [
        ("RECON-SCAN", "port scan on host-03"),
        ("AUTH-SSH", "successful login (user: svc-test)"),
        ("PRIV-ESC", "sudo attempt on low-priv account"),
        ("LATERAL-MOVE", "SMB session opened host-03 -> host-07 using stolen ticket"),
        ("LATERAL-MOVE", "RDP session opened on host-07"),
        ("DB-SEARCH", "querying host-07's local DB config for credentials"),
    ],

    # Data exfiltration: staging (archiving) followed by an actual outbound
    # transfer — the #1 thing a real SOC cares about, and previously
    # nothing in the system modeled the "data actually left" step.
    "data_exfiltration": [
        ("RECON-SCAN", "port scan on host-03"),
        ("AUTH-SSH", "successful login (user: svc-test)"),
        ("PRIV-ESC", "sudo attempt on low-priv account"),
        ("DB-SEARCH", "querying customer records table"),
        ("EXFIL-STAGING", "customer_records.tar.gz created in /tmp (340MB)"),
        ("EXFIL-TRANSFER", "outbound transfer to unrecognized external IP over HTTPS"),
    ],

    # Supply-chain compromise: the "attacker" is a poisoned dependency or
    # CI step, not a human at a terminal — same event pipeline, different
    # origin story, which is exactly the point (the system doesn't care
    # who/what triggered PRIV-ESC, only what happens after).
    "supply_chain_compromise": [
        ("SUPPLY-CHAIN", "malicious postinstall script executed via compromised npm dependency"),
        ("LOTL-ACTIVITY", "PowerShell used to download second-stage payload"),
        ("PRIV-ESC", "scheduled task created for persistence"),
        ("DOWNLOAD", "second-stage payload fetched from attacker-controlled CDN"),
        ("DB-SEARCH", "querying local secrets/config files for CI credentials"),
    ],

    # Living-off-the-land: legitimate admin tools used in a suspicious
    # sequence instead of malware — individually each step looks like
    # normal sysadmin activity, which is exactly why it's hard to catch
    # and a strong "explainability" demo beat.
    "living_off_the_land": [
        ("AUTH-SSH", "successful login (user: svc-ops, expected schedule)"),
        ("LOTL-ACTIVITY", "PowerShell Invoke-WebRequest used to fetch a script"),
        ("LOTL-ACTIVITY", "WMI used to query remote host process list"),
        ("ADMIN-ACTION", "scheduled task modified via schtasks.exe"),
        ("PRIV-ESC", "token impersonation via legitimate admin utility"),
    ],

    # Insider misuse: valid credentials, working hours, nothing that looks
    # like a classic attack — but the access pattern drifts outside normal
    # scope. Meant to look almost benign, unlike ssh_bruteforce_only which
    # is obviously loud; this is the "subtle" test case.
    "insider_misuse": [
        ("INSIDER-ACCESS", "valid login (user: contractor-42, during business hours)"),
        ("INSIDER-ACCESS", "accessed file share outside assigned project folder"),
        ("DB-SEARCH", "queried HR salary table — outside contractor's normal scope"),
        ("EXFIL-STAGING", "salary_export.xlsx created in personal downloads folder"),
    ],
}

# Fixed source IPs per scenario so re-runs are reproducible for the demo
SCENARIO_IPS = {
    "recon_to_db_hunt": "10.0.0.42",
    "ssh_bruteforce_only": "10.0.0.51",
    "benign_admin_login": "10.0.0.9",
    "recon_to_db_hunt_variant_ip": "10.0.0.88",
    "password_spray_campaign": "10.0.0.61",
    "lateral_movement_breach": "10.0.0.73",
    "data_exfiltration": "10.0.0.94",
    "supply_chain_compromise": "10.0.0.15",   # CI/build-agent IP, not a human's
    "living_off_the_land": "10.0.0.27",
    "insider_misuse": "10.0.0.3",              # internal IP — insider, not external attacker
}


def run_scenario(scenario_name, incident_id, host="host-03", user="svc-test", insert_fn=None):
    """
    Feeds a scripted event sequence into the event store (or into any
    insert_fn(incident_id, event_type, src_ip, host, user, detail) you pass in,
    e.g. for testing without touching the DB).
    """
    if scenario_name not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario_name}. Options: {list(SCENARIOS)}")

    src_ip = SCENARIO_IPS[scenario_name]
    events = SCENARIOS[scenario_name]

    if insert_fn is None:
        from db import insert_event as insert_fn

    for event_type, detail in events:
        insert_fn(incident_id, event_type, src_ip, host, user, detail)

    return {"incident_id": incident_id, "scenario": scenario_name,
            "src_ip": src_ip, "event_count": len(events)}


def list_scenarios():
    return list(SCENARIOS.keys())
