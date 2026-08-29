"""
MIRAGE-X — Adaptive Deception Engine.

Confidence-driven decoy selection. LOW confidence is what triggers a decoy
deployment at all (per the frozen thresholds); WHICH decoy gets shown then
depends on what the attacker's behavior sequence suggests they're after.
This is the "closed loop" — behavior decides the environment they see next.
"""

DECOYS = {
    "fake_ssh": "Generic SSH honeypot — shown by default once a decoy triggers.",
    "fake_db": "Fake database service — shown if behavior includes DB-SEARCH.",
    "fake_admin_panel": "Fake admin login console — shown if behavior includes ADMIN-ACTION or PRIV-ESC probing.",
}

CONFIDENCE_THRESHOLDS = {"HIGH": 0.70, "MEDIUM": 0.45}


def confidence_band(similarity_score):
    if similarity_score is None:
        return "LOW"
    if similarity_score >= CONFIDENCE_THRESHOLDS["HIGH"]:
        return "HIGH"
    if similarity_score >= CONFIDENCE_THRESHOLDS["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


def select_decoy(behavior_sequence, similarity_score, risk_band="MEDIUM"):
    """
    Returns (decoy_name_or_None, confidence_band, reason).
    Decoy only deploys when confidence is LOW *and* the behavior's own risk
    band isn't LOW — this stops clearly-benign traffic (which will always
    start with no memory match, hence "LOW confidence") from triggering a
    decoy just because memory is empty. Confidence measures "do we
    recognize this," risk measures "does this look dangerous" — both
    matter for the decision, not confidence alone.

        score >= 0.70 -> HIGH   -> retrieve + recommend directly (no decoy)
        score >= 0.45 -> MEDIUM -> retrieve, flag for review (no decoy)
        score <  0.45 -> LOW    -> decoy only if risk_band != LOW
    """
    band = confidence_band(similarity_score)

    if band != "LOW":
        return None, band, f"confidence={band} ({similarity_score}) — enough historical match, no decoy needed"

    if risk_band == "LOW":
        return None, band, f"confidence=LOW but underlying behavior risk is LOW -> treated as benign, no decoy needed"

    if "EXFIL-STAGING" in behavior_sequence or "EXFIL-TRANSFER" in behavior_sequence:
        return "fake_db", band, (
            "exfiltration staging/transfer signal detected -> highest-priority case, route to "
            "fake_db to keep the attacker contained on a monitored decoy while data-loss alerts fire"
        )
    if "DB-SEARCH" in behavior_sequence:
        return "fake_db", band, "attacker behavior indicates DB targeting -> escalate to fake_db"
    if "LATERAL-MOVE" in behavior_sequence:
        return "fake_ssh", band, (
            "lateral movement detected -> attacker is pivoting between hosts via SSH-like access, "
            "hold them on fake_ssh to keep observing without granting a real second hop"
        )
    if "ADMIN-ACTION" in behavior_sequence or "PRIV-ESC" in behavior_sequence:
        return "fake_admin_panel", band, (
            "privilege-escalation/admin-probing behavior detected -> matches the Attack-Path "
            "engine's predicted next target (admin-panel), so escalate to fake_admin_panel"
        )

    return "fake_ssh", band, "low confidence, early-stage behavior -> default fake_ssh decoy"
