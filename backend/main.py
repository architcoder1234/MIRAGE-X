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
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional
import os
import json
import logging
import time
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
import event_stream
import decoy_quality

VERSION = "0.2.0"
STARTED_AT = time.monotonic()
logger = logging.getLogger("mirage_x")
logging.basicConfig(level=os.environ.get("MIRAGE_LOG_LEVEL", "INFO"))


def _origins():
    configured = os.environ.get("MIRAGE_ALLOWED_ORIGINS")
    if configured:
        return [item.strip() for item in configured.split(",") if item.strip()]
    return ["http://localhost", "http://localhost:8000", "http://127.0.0.1:8000", "null"]


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    yield


app = FastAPI(title="MIRAGE-X API", version=VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _log_event(name, incident_id=None, started=None, **fields):
    payload = {"event": name}
    if incident_id:
        payload["incident_id"] = incident_id
    if started is not None:
        payload["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    payload.update(fields)
    logger.info(json.dumps(payload, sort_keys=True))


# ---------- request models ----------

class SimulateRequest(BaseModel):
    scenario: str = Field(min_length=1, max_length=100)
    incident_id: Optional[str] = Field(default=None, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$")
    host: Optional[str] = Field(default="host-03", max_length=100, pattern=r"^[A-Za-z0-9_.:@-]+$")
    user: Optional[str] = Field(default="svc-test", max_length=100, pattern=r"^[A-Za-z0-9_.:@-]+$")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class CorrelateRequest(BaseModel):
    question: Optional[str] = Field(default=None, max_length=2000)


class IngestEvent(BaseModel):
    incident_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$")
    event_type: str = Field(min_length=1, max_length=100, pattern=r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
    src_ip: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:@-]+$")
    user: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:@-]+$")
    detail: Optional[str] = Field(default="", max_length=4000)

    @field_validator("src_ip")
    @classmethod
    def validate_src_ip(cls, value):
        import ipaddress
        try:
            ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("src_ip must be a valid IPv4 or IPv6 address") from exc
        return value


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
    incident["decoy_quality_metrics"] = decoy_quality.metrics(
        incident["decoy_evidence"],
        incident.get("decoy_deployed"),
        incident["predicted_path"],
    )
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
    incident["decoy_evidence"] = db.get_decoy_interactions(incident_id)
    incident["decoy_quality_metrics"] = decoy_quality.metrics(
        incident["decoy_evidence"], decoy, path_prediction
    )
    incident["mitre_techniques"] = mitre_techniques
    incident["soc_alert"] = alert
    return incident


def _publish_incident(event_type, incident):
    event_stream.publish(event_type, {
        "incident_id": incident.get("incident_id"),
        "risk_score": incident.get("risk_score"),
        "decoy_deployed": incident.get("decoy_deployed"),
    })


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


@app.get("/health")
def health():
    try:
        db_ok = db.health_check()
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "db_ok": db_ok,
        "version": VERSION,
        "uptime_s": round(time.monotonic() - STARTED_AT, 2),
    }


@app.post("/simulate")
def simulate(req: SimulateRequest):
    incident_id = req.incident_id or _next_incident_id()
    try:
        simulator.run_scenario(req.scenario, incident_id, req.host, req.user)
    except ValueError as e:
        raise HTTPException(400, str(e))
    incident = _process_incident(incident_id)
    _publish_incident("new_incident", incident)
    return incident


@app.post("/ingest")
def ingest(event: IngestEvent):
    if not db.get_incident(event.incident_id):
        raise HTTPException(404, "incident not found; create it with /simulate first")
    started = time.perf_counter()
    db.insert_event(event.incident_id, event.event_type, event.src_ip,
                     event.host, event.user, event.detail or "")
    incident = _process_incident(event.incident_id)
    _log_event("ingest", event.incident_id, started, event_type=event.event_type)
    _publish_incident("incident_updated", incident)
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
    started = time.perf_counter()
    folded_event_types = decoy_feedback.fold_decoy_evidence(incident_id)
    result = _process_incident(incident_id)
    result["decoy_events_folded"] = folded_event_types
    _log_event("recompute", incident_id, started, folded_count=len(folded_event_types))
    if folded_event_types:
        _log_event("decoy_feedback", incident_id, started, folded_count=len(folded_event_types))
    _publish_incident("incident_updated", result)
    if folded_event_types:
        event_stream.publish("decoy_evidence", {
            "incident_id": incident_id,
            "folded_count": len(folded_event_types),
        })
    return result


@app.get("/alerts")
def get_alerts():
    """Simulated SOC alert channel — every incident that would have paged an
    analyst, most recent first. See alert_channel.py for what "simulated" means here."""
    return db.get_alerts()


@app.get("/analytics")
def analytics():
    incidents = db.list_incidents()
    risk_bands = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    severity_distribution = {}
    technique_counts = {}
    decoy_stats = {}
    benign_total = 0
    benign_clean = 0

    for incident in incidents:
        band = attack_dna.risk_to_confidence_band(incident["risk_score"])
        risk_bands[band] = risk_bands.get(band, 0) + 1
        alert = soc_alert.severity_for(incident["risk_score"], incident["behavior_sequence"])
        severity = alert["severity"]
        severity_distribution[severity] = severity_distribution.get(severity, 0) + 1
        for technique in mitre.techniques_for_sequence(incident["behavior_sequence"]):
            technique_id = technique["technique_id"]
            technique_counts[technique_id] = technique_counts.get(technique_id, 0) + 1
        is_benign = "ADMIN-ACTION" in incident["behavior_sequence"] and "AUTH-SSH" in incident["behavior_sequence"]
        if is_benign:
            benign_total += 1
            if incident["risk_score"] < 45:
                benign_clean += 1
        decoy = incident.get("decoy_deployed")
        if decoy:
            interactions = db.get_decoy_interactions(incident["incident_id"])
            stats = decoy_stats.setdefault(decoy, {"incidents": 0, "interactions": 0})
            stats["incidents"] += 1
            stats["interactions"] += len(interactions)

    return {
        "incident_count": len(incidents),
        "risk_band_distribution": risk_bands,
        "top_mitre_techniques": [
            {"technique_id": key, "count": value}
            for key, value in sorted(technique_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
        ],
        "decoy_usage_yield": [
            {"decoy": key, **value}
            for key, value in sorted(decoy_stats.items())
        ],
        "false_positive_control_rate": {
            "eligible_benign_incidents": benign_total,
            "clean_benign_incidents": benign_clean,
            "rate": round(benign_clean / benign_total, 4) if benign_total else None,
        },
        "soc_severity_distribution": severity_distribution,
    }


@app.get("/events/stream")
async def events_stream():
    async def encoded():
        async for message in event_stream.stream():
            if isinstance(message, str):
                yield message
                continue
            yield f"event: {message['event']}\ndata: {json.dumps(message['data'])}\n\n"

    return StreamingResponse(
        encoded(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/reset")
def reset(request: Request, x_mirage_reset_token: Optional[str] = Header(None)):
    configured_token = os.environ.get("MIRAGE_RESET_TOKEN")
    client_host = request.client.host if request.client else ""
    local_client = client_host in {"127.0.0.1", "::1", "localhost", "testclient"}
    if configured_token:
        if x_mirage_reset_token != configured_token:
            raise HTTPException(403, "reset authorization required")
    elif not local_client:
        raise HTTPException(403, "reset is local-only; configure MIRAGE_RESET_TOKEN for remote administration")
    db.init_db(reset=True)
    event_stream.publish("reset", {"status": "reset"})
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
