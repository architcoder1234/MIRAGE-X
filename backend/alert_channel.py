"""
MIRAGE-X — Simulated SOC Alert Channel.

Demonstrates the "this would actually page someone" story without ever
making a real network call — there is no live Slack workspace here, and
there shouldn't be one in a hackathon demo. Instead, whenever soc_alert.py
decides an incident would page an analyst, this module formats a
Slack-style message and logs it to the alert_log table. The dashboard
polls it and renders it as a mock alert channel.

Kept intentionally simple and honest: nothing here claims to have sent a
real message anywhere. It's a simulation of the *decision*, not a fake
integration pretending to be real.
"""
import db

CHANNEL = "#soc-alerts"


def format_message(incident_id, fp, alert):
    severity_emoji = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "LOW": "🟢",
        "INFO": "⚪",
    }.get(alert.get("severity"), "⚪")

    sequence = " → ".join(fp.get("behavior_sequence", []))
    return (
        f"{severity_emoji} *{alert.get('severity')}* incident `{incident_id}` "
        f"— risk {fp.get('risk_score')}/100\n"
        f"Behavior: {sequence or 'n/a'}\n"
        f"{alert.get('reason', '')}"
    )


SEVERITY_RANK = {"INFO": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def maybe_send_alert(incident_id, fp, alert):
    """
    Only logs (simulates sending) when the incident would actually page —
    mirrors real alerting, where routine/low-severity events shouldn't
    spam the channel. Also dedupes against repeat calls for the SAME
    incident (e.g. recompute() after folding decoy evidence): only fires
    again if this is the first page for this incident, or severity has
    escalated since the last one logged — so re-running recompute with no
    real change doesn't spam the channel, but a genuine escalation still
    shows up. Returns the logged message dict, or None if nothing was sent.
    """
    if not alert or not alert.get("would_page"):
        return None

    last = db.get_last_alert_for_incident(incident_id)
    if last:
        prev_rank = SEVERITY_RANK.get(last["severity"], -1)
        new_rank = SEVERITY_RANK.get(alert.get("severity"), -1)
        if new_rank <= prev_rank:
            return None

    message = format_message(incident_id, fp, alert)
    db.log_alert(incident_id, alert.get("severity", "INFO"), CHANNEL, message)
    return {"incident_id": incident_id, "severity": alert.get("severity"), "channel": CHANNEL, "message": message}
