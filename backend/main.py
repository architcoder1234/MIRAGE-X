"""
MIRAGE-X — FastAPI backend.

Closed loop implemented here:
  simulate/ingest -> attack_dna -> memory.find_most_similar -> deception.select_decoy
  -> store incident -> (decoy runs separately, logs interactions) -> re-fingerprint

Run:
    cd backend
    pip install -r requirements.txt
    uvicorn main:app --reload --port 8000

Then hit http://localhost:8000/docs for the interactive API, or point the
frontend/index.html dashboard at it.
"""
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import os
import uuid

import db
import simulator
import attack_dna
import memory
import deception
import attack_path
import decoy_feedback
import mitre
import soc_alert
import reports
import advisor
import alert_channel

app = FastAPI(title="MIRAGE-X API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    db.init_db()


# ---------- request models ----------

class SimulateRequest(BaseModel):
    scenario: str
    incident_id: Optional[str] = None
    host: Optional[str] = "host-03"
    user: Optional[str] = "svc-test"


class AskRequest(BaseModel):
    question: str


class CorrelateRequest(BaseModel):
    question: Optional[str] = None


class IngestEvent(BaseModel):
    incident_id: str
    event_type: str
    src_ip: str
    host: str
    user: str
    detail: Optional[str] = ""


# ---------- helpers ----------

def _full_incident(incident_id):
    """Incident dict enriched with events, decoy evidence, path, MITRE, and SOC alert —
    the same shape every read-heavy endpoint (get_incident, report, advisory, ask) needs."""
    incident = db.get_incident(incident_id)
    if not incident:
        return None
    incident["events"] = db.get_events(incident_id)
    incident["decoy_evidence"] = db.get_decoy_interactions(incident_id)
    incident["predicted_path"] = attack_path.predict_next_target(incident["behavior_sequence"])
    incident["mitre_techniques"] = mitre.techniques_for_sequence(incident["behavior_sequence"])
    incident["soc_alert"] = soc_alert.severity_for(incident["risk_score"], incident["behavior_sequence"])
    return incident


def _next_incident_id():
    existing = db.list_incidents()
    return f"INC-{len(existing) + 1:04d}"


def _process_incident(incident_id):
    """Runs the full closed loop for an incident that already has events."""
    events = db.get_events(incident_id)
    fp = attack_dna.fingerprint(events)

    match = memory.find_most_similar(events, fp["risk_band"], exclude_incident_id=incident_id)
    sim_score = match["score"] if match else 0.0

    decoy, band, reason = deception.select_decoy(fp["behavior_sequence"], sim_score, fp["risk_band"])
    path_prediction = attack_path.predict_next_target(fp["behavior_sequence"])
    mitre_techniques = mitre.techniques_for_sequence(fp["behavior_sequence"])
    alert = soc_alert.severity_for(fp["risk_score"], fp["behavior_sequence"])
    alert_channel.maybe_send_alert(incident_id, fp, alert)

    summary = _explain(fp, match, decoy, reason, path_prediction, alert)

    db.upsert_incident(
        incident_id=incident_id,
        behavior_sequence=fp["behavior_sequence"],
        risk_score=fp["risk_score"],
        confidence=band,
        decoy_deployed=decoy,
        similarity_top_match=match,
        summary=summary,
    )
    incident = db.get_incident(incident_id)
    incident["predicted_path"] = path_prediction
    incident["mitre_techniques"] = mitre_techniques
    incident["soc_alert"] = alert
    return incident


def _explain(fp, match, decoy, reason, path_prediction=None, alert=None):
    """Human-readable, evidence-grounded summary — the 'Explainable AI Defender'."""
    lines = []
    lines.append(
        f"Behavior sequence observed: {' -> '.join(fp['behavior_sequence'])}."
    )
    lines.append(f"Risk score: {fp['risk_score']}/100 ({fp['risk_band']}).")
    if match:
        lines.append(
            f"Closest historical match: {match['incident_id']} "
            f"(similarity {match['score']}, matched on {', '.join(match['matched_features']) or 'no strong features'})."
        )
    else:
        lines.append("No prior incidents in memory to compare against.")
    if decoy:
        lines.append(f"Decision: deploy {decoy}. Reason: {reason}")
    else:
        lines.append(f"Decision: no decoy needed. Reason: {reason}")
    if path_prediction and path_prediction.get("predicted_next_target"):
        lines.append(
            f"Predicted next target: {path_prediction['predicted_next_label']}. "
            f"{path_prediction['reason']}."
        )
    if alert:
        page_note = "would page a SOC analyst" if alert["would_page"] else "would not page, queued for review"
        lines.append(f"SOC severity: {alert['severity']} ({page_note}). {alert['reason']}.")
    return " ".join(lines)


# ---------- endpoints ----------

@app.get("/scenarios")
def get_scenarios():
    return {"scenarios": simulator.list_scenarios()}


@app.post("/simulate")
def simulate(req: SimulateRequest):
    incident_id = req.incident_id or _next_incident_id()
    try:
        simulator.run_scenario(req.scenario, incident_id, req.host, req.user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    incident = _process_incident(incident_id)
    return incident


@app.post("/ingest")
def ingest(event: IngestEvent):
    db.insert_event(event.incident_id, event.event_type, event.src_ip,
                     event.host, event.user, event.detail or "")
    incident = _process_incident(event.incident_id)
    return incident


@app.get("/incidents")
def get_incidents():
    return db.list_incidents()


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str):
    incident = _full_incident(incident_id)
    if not incident:
        raise HTTPException(404, "incident not found")
    return incident


@app.get("/network")
def get_network():
    """Static simulated network graph for the dashboard's attack-path view."""
    return attack_path.graph_snapshot()


@app.get("/incidents/{incident_id}/predicted_path")
def get_predicted_path(incident_id: str):
    events = db.get_events(incident_id)
    if not events:
        raise HTTPException(404, "incident not found or has no events")
    fp = attack_dna.fingerprint(events)
    return attack_path.predict_next_target(fp["behavior_sequence"])


@app.get("/incidents/{incident_id}/risk_trend")
def get_risk_trend(incident_id: str):
    """
    Step-by-step risk score as events arrived, not just the final number —
    powers the sparkline in the dashboard so the story is "risk climbed as
    behavior escalated," not just a single static figure.
    """
    events = db.get_events(incident_id)
    if not events:
        raise HTTPException(404, "incident not found or has no events")
    points = []
    for i in range(1, len(events) + 1):
        prefix = events[:i]
        fp = attack_dna.fingerprint(prefix)
        points.append({
            "step": i,
            "event_type": prefix[-1]["event_type"],
            "risk_score": fp["risk_score"],
        })
    return {"incident_id": incident_id, "trend": points}


@app.get("/incidents/{incident_id}/similar")
def get_similar(incident_id: str):
    events = db.get_events(incident_id)
    if not events:
        raise HTTPException(404, "incident not found or has no events")
    fp = attack_dna.fingerprint(events)
    match = memory.find_most_similar(events, fp["risk_band"], exclude_incident_id=incident_id)
    return {"incident_id": incident_id, "top_match": match}


@app.post("/incidents/{incident_id}/recompute")
def recompute(incident_id: str):
    """
    Folds any new decoy evidence (real nmap/hydra/netcat traffic logged
    since last time) into proper events, then re-runs the full pipeline —
    attack DNA, memory, deception, attack-path — so real attacks against
    a decoy actually move the risk score, not just the evidence panel.
    """
    incident = db.get_incident(incident_id)
    if not incident:
        raise HTTPException(404, "incident not found")
    folded_event_types = decoy_feedback.fold_decoy_evidence(incident_id)
    result = _process_incident(incident_id)
    result["decoy_events_folded"] = folded_event_types
    return result


@app.get("/alerts")
def get_alerts():
    """Simulated SOC alert channel — every incident that would have paged an
    analyst, most recent first. See alert_channel.py for what "simulated" means here."""
    return db.get_alerts()


@app.post("/reset")
def reset():
    db.init_db(reset=True)
    return {"status": "reset"}


@app.get("/incidents/{incident_id}/report")
def get_report(incident_id: str, x_anthropic_key: Optional[str] = Header(None)):
    """
    Generates a one-page PDF incident report (evidence-grounded, same
    numbers as the dashboard) and returns it as a download. Includes the
    AI Advisor's plain-English summary as a section if available — falls
    back to the rule-based advisory automatically, same as the dashboard,
    so report generation never blocks or fails on a missing/bad key.
    """
    incident = _full_incident(incident_id)
    if not incident:
        raise HTTPException(404, "incident not found")

    advisory = advisor.generate_advisory(incident, api_key_override=x_anthropic_key)
    path = reports.generate_incident_report(incident, advisory=advisory)
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"MIRAGE-X_{incident_id}_report.pdf",
    )


# ---------- AI advisor layer ----------
# Sits on top of the deterministic engine (attack_dna/deception/mitre/soc_alert) —
# it explains and recommends, it never re-decides risk score, decoy, or severity.
# X-Anthropic-Key lets the dashboard's Settings panel supply a key per-request
# without needing an env var on the server (handy for a demo laptop with no key
# set); server env var ANTHROPIC_API_KEY is used if the header is absent.

@app.get("/settings/llm_status")
def llm_status(x_anthropic_key: Optional[str] = Header(None)):
    return {"llm_available": bool(x_anthropic_key or os.environ.get("ANTHROPIC_API_KEY"))}


@app.get("/incidents/{incident_id}/advisory")
def get_advisory(incident_id: str, x_anthropic_key: Optional[str] = Header(None)):
    incident = _full_incident(incident_id)
    if not incident:
        raise HTTPException(404, "incident not found")
    return advisor.generate_advisory(incident, api_key_override=x_anthropic_key)


@app.post("/incidents/{incident_id}/ask")
def ask_advisor(incident_id: str, req: AskRequest, x_anthropic_key: Optional[str] = Header(None)):
    incident = _full_incident(incident_id)
    if not incident:
        raise HTTPException(404, "incident not found")
    if not req.question.strip():
        raise HTTPException(400, "question must not be empty")
    return advisor.answer_question(incident, req.question, api_key_override=x_anthropic_key)


@app.post("/advisor/correlate")
def correlate_incidents(req: CorrelateRequest, x_anthropic_key: Optional[str] = Header(None)):
    """
    Cross-incident correlation — looks across every incident currently in
    memory, not just one, for patterns a single-incident view can't show
    (e.g. "are any of these the same attacker returning?").
    """
    ids = [i["incident_id"] for i in db.list_incidents()]
    incidents = [inc for inc in (_full_incident(i) for i in ids) if inc]
    return advisor.correlate_incidents(incidents, req.question, api_key_override=x_anthropic_key)
