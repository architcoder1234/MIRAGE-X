"""Derived quality metrics for interactions with a selected decoy."""
from datetime import datetime


DECOY_TARGETS = {
    "fake_ssh": "host-03",
    "fake_db": "db-server",
    "fake_admin_panel": "admin-panel",
}


def _parse_timestamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def metrics(interactions, decoy, predicted_path):
    if not interactions:
        return {
            "dwell_time_s": 0.0,
            "interaction_count": 0,
            "distinct_evidence_types": 0,
            "stayed_on_predicted_path": None,
        }

    timestamps = [_parse_timestamp(item["ts"]) for item in interactions]
    evidence_types = {
        str(item.get("command", "")).split(":", 1)[0]
        for item in interactions
    }
    target = (predicted_path or {}).get("predicted_next_target")
    return {
        "dwell_time_s": round((max(timestamps) - min(timestamps)).total_seconds(), 3),
        "interaction_count": len(interactions),
        "distinct_evidence_types": len(evidence_types),
        "stayed_on_predicted_path": (
            DECOY_TARGETS.get(decoy) == target if target else None
        ),
    }
