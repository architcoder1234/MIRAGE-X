"""
MIRAGE-X — Cyber Incident Memory + Explainable Retrieval.

Rule-based similarity (no embeddings needed for the hackathon — keep it
explainable). Start with sequence_match + technique_match working
end-to-end (P0), then layer in the rest (P1) if time allows.
"""
from difflib import SequenceMatcher
import db


WEIGHTS = {
    "sequence_match": 0.40,      # bumped up since we only ship 2 features at P0
    "technique_match": 0.30,
    "risk_band_match": 0.15,
}


def sequence_similarity(seq_a, seq_b):
    """Ratio-based similarity between two ordered event-type sequences."""
    if not seq_a or not seq_b:
        return 0.0
    return SequenceMatcher(None, seq_a, seq_b).ratio()


def technique_overlap(seq_a, seq_b):
    """Jaccard overlap of the *set* of event types touched (technique family)."""
    set_a, set_b = set(seq_a), set(seq_b)
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def compare_incidents(incident_a, incident_b):
    """
    Returns (score, matched_features) — matched_features is what powers the
    "explanation" panel in the dashboard (Section: Explainable AI Defender).
    """
    seq_a = incident_a["behavior_sequence"]
    seq_b = incident_b["behavior_sequence"]

    seq_sim = sequence_similarity(seq_a, seq_b)
    tech_sim = technique_overlap(seq_a, seq_b)

    matched = []
    score = 0.0
    if seq_sim > 0.3:
        score += WEIGHTS["sequence_match"] * seq_sim
        matched.append("sequence")
    if tech_sim > 0.3:
        score += WEIGHTS["technique_match"] * tech_sim
        matched.append("technique_family")

    # The incidents table stores the risk band in its `confidence` column.
    if incident_a.get("risk_band") and incident_a.get("risk_band") == incident_b.get("confidence"):
        score += WEIGHTS["risk_band_match"]
        matched.append("risk_band")

    return round(score, 3), matched


def find_most_similar(current_events, current_risk_band, exclude_incident_id=None):
    """
    Compares the current (in-progress) incident's fingerprint against every
    stored past incident and returns the best match, or None if memory is
    empty. This is what drives the confidence engine's decoy trigger.
    """
    import attack_dna
    current_seq = attack_dna.build_behavior_sequence(current_events)
    current = {"behavior_sequence": current_seq, "risk_band": current_risk_band}

    best = None
    for past in db.list_incidents():
        if exclude_incident_id and past["incident_id"] == exclude_incident_id:
            continue
        score, matched = compare_incidents(current, past)
        if best is None or score > best["score"]:
            best = {
                "incident_id": past["incident_id"],
                "score": score,
                "matched_features": matched,
            }
    return best
