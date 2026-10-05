import pytest
import asyncio
import threading

import db
import simulator
import event_stream
import main


EXPECTED_SCENARIOS = {
        "recon_to_db_hunt": ("HIGH", "fake_db", "CRITICAL", True),
        "recon_to_db_hunt_variant_ip": ("HIGH", "fake_db", "CRITICAL", True),
        "ssh_bruteforce_only": ("LOW", None, "LOW", False),
        "benign_admin_login": ("LOW", None, "INFO", False),
        "password_spray_campaign": ("HIGH", "fake_admin_panel", "HIGH", True),
        "lateral_movement_breach": ("HIGH", "fake_db", "CRITICAL", True),
        "data_exfiltration": ("HIGH", "fake_db", "CRITICAL", True),
        "supply_chain_compromise": ("HIGH", "fake_db", "CRITICAL", True),
        "living_off_the_land": ("MEDIUM", "fake_admin_panel", "MEDIUM", False),
        "insider_misuse": ("HIGH", "fake_db", "CRITICAL", True),
}


@pytest.mark.parametrize("scenario", simulator.list_scenarios())
def test_all_scenarios_end_to_end(client, scenario):
    response = client.post("/simulate", json={"scenario": scenario, "incident_id": "API-01"})
    assert response.status_code == 200
    incident = response.json()
    band, decoy, severity, would_page = EXPECTED_SCENARIOS[scenario]
    assert incident["risk_score"] >= 0
    assert incident["confidence"] in {"HIGH", "MEDIUM", "LOW"}
    assert incident["decoy_deployed"] == decoy
    assert incident["soc_alert"]["severity"] == severity
    assert incident["soc_alert"]["would_page"] is would_page
    assert incident["mitre_techniques"]
    assert incident["predicted_path"]["predicted_next_target"]
    assert (incident["risk_score"] >= 70) == (band == "HIGH")


def test_api_contract_endpoints_and_validation(client):
    assert client.get("/health").json().keys() >= {"status", "db_ok", "version", "uptime_s"}
    assert client.get("/scenarios").json()["scenarios"]
    assert client.get("/network").status_code == 200
    assert client.get("/incidents").status_code == 200
    assert client.get("/alerts").status_code == 200
    assert client.get("/settings/llm_status").status_code == 200
    assert client.post("/simulate", json={}).status_code == 422
    assert client.post("/ingest", json={}).status_code == 422
    assert client.post("/ingest", json={
        "incident_id": "UNKNOWN",
        "event_type": "AUTH-SSH",
        "src_ip": "127.0.0.1",
        "host": "host-03",
        "user": "demo",
    }).status_code == 404
    assert client.post("/incidents/UNKNOWN/ask", json={"question": ""}).status_code == 422

    incident = client.post("/simulate", json={"scenario": "benign_admin_login"}).json()
    incident_id = incident["incident_id"]
    assert client.get(f"/incidents/{incident_id}").status_code == 200
    assert client.get(f"/incidents/{incident_id}/predicted_path").status_code == 200
    assert client.get(f"/incidents/{incident_id}/risk_trend").status_code == 200
    assert client.get(f"/incidents/{incident_id}/similar").status_code == 200
    assert client.get(f"/incidents/{incident_id}/report").status_code == 200
    assert client.get(f"/incidents/{incident_id}/advisory").status_code == 200
    assert client.post(f"/incidents/{incident_id}/recompute").status_code == 200
    assert client.post(f"/incidents/{incident_id}/ask", json={"question": "Is this risky?"}).status_code == 200
    assert client.post("/advisor/correlate", json={}).status_code == 200
    assert client.post("/reset").status_code == 200

    unknown = "INC-DOES-NOT-EXIST"
    for path in (
        f"/incidents/{unknown}",
        f"/incidents/{unknown}/predicted_path",
        f"/incidents/{unknown}/risk_trend",
        f"/incidents/{unknown}/similar",
        f"/incidents/{unknown}/report",
        f"/incidents/{unknown}/advisory",
        f"/incidents/{unknown}/recompute",
    ):
        response = client.post(path) if path.endswith("recompute") else client.get(path)
        assert response.status_code == 404


def test_recompute_is_idempotent_for_decoy_derived_events(client):
    incident = client.post("/simulate", json={"scenario": "recon_to_db_hunt"}).json()
    incident_id = incident["incident_id"]
    before_count = len(db.get_events(incident_id))
    db.log_decoy_interaction(incident_id, "fake_db", "SELECT users", "127.0.0.1")
    first = client.post(f"/incidents/{incident_id}/recompute").json()
    second = client.post(f"/incidents/{incident_id}/recompute").json()
    assert first["decoy_events_folded"]
    assert second["decoy_events_folded"] == []
    assert len(db.get_events(incident_id)) == before_count + 1


def test_alert_dedup_and_escalation(client):
    incident = client.post("/simulate", json={"scenario": "benign_admin_login"}).json()
    incident_id = incident["incident_id"]
    assert client.post(f"/incidents/{incident_id}/recompute").status_code == 200
    assert db.get_alerts() == []

    db.insert_event(incident_id, "EXFIL-TRANSFER", "10.0.0.8", "host-03", "svc-test", "test")
    client.post(f"/incidents/{incident_id}/recompute")
    assert len(db.get_alerts()) == 1
    client.post(f"/incidents/{incident_id}/recompute")
    assert len(db.get_alerts()) == 1


def test_behavior_first_memory_ignores_source_ip(client):
    first = client.post("/simulate", json={
        "scenario": "recon_to_db_hunt",
        "incident_id": "INC-MEM-A",
    }).json()
    second = client.post("/simulate", json={
        "scenario": "recon_to_db_hunt_variant_ip",
        "incident_id": "INC-MEM-B",
    }).json()
    assert second["similarity_top_match"]["incident_id"] == "INC-MEM-A"
    assert second["similarity_top_match"]["score"] >= 0.7


def test_advisor_fallback_without_key_and_on_failure(client, monkeypatch):
    incident = client.post("/simulate", json={"scenario": "data_exfiltration"}).json()
    response = client.get(f"/incidents/{incident['incident_id']}/advisory")
    data = response.json()
    assert data["mode"] == "fallback"
    assert data["available"] is False
    assert str(incident["risk_score"]) in data["plain_summary"]

    class FailingMessages:
        def create(self, **_kwargs):
            raise RuntimeError("mock API outage")

    class FailingClient:
        messages = FailingMessages()

    import advisor
    monkeypatch.setattr(advisor, "_client", lambda *_args, **_kwargs: FailingClient())
    failed = client.get(f"/incidents/{incident['incident_id']}/advisory")
    assert failed.json()["mode"] == "fallback"
    assert failed.json()["available"] is False
    assert "unavailable" in failed.json()["error"]


def test_analytics_returns_aggregates(client):
    client.post("/simulate", json={"scenario": "benign_admin_login"})
    client.post("/simulate", json={"scenario": "data_exfiltration"})
    response = client.get("/analytics")
    assert response.status_code == 200
    data = response.json()
    assert data["incident_count"] == 2
    assert sum(data["risk_band_distribution"].values()) == 2
    assert data["top_mitre_techniques"]
    assert data["soc_severity_distribution"]["CRITICAL"] == 1
    assert data["false_positive_control_rate"]["rate"] == 1.0


def test_decoy_quality_metrics_are_exposed(client):
    incident = client.post("/simulate", json={"scenario": "recon_to_db_hunt"}).json()
    incident_id = incident["incident_id"]
    db.log_decoy_interaction(incident_id, "fake_db", "PROBE_ONLY", "127.0.0.1")
    db.log_decoy_interaction(incident_id, "fake_db", "CLIENT_BANNER: db", "127.0.0.1")
    result = client.get(f"/incidents/{incident_id}").json()
    metrics = result["decoy_quality_metrics"]
    assert metrics["interaction_count"] == 2
    assert metrics["distinct_evidence_types"] == 2
    assert metrics["dwell_time_s"] >= 0
    assert metrics["stayed_on_predicted_path"] is True


def test_reset_requires_token_for_non_local_administration(client, monkeypatch):
    monkeypatch.setenv("MIRAGE_RESET_TOKEN", "test-reset-token")
    assert client.post("/reset").status_code == 403
    assert client.post(
        "/reset", headers={"X-Mirage-Reset-Token": "test-reset-token"}
    ).status_code == 200


def test_frontend_escapes_ingest_and_advisor_values():
    from pathlib import Path
    script = Path(__file__).parents[2].joinpath("frontend", "script.js").read_text(encoding="utf-8")
    assert "escapeHtml(ev.command)" in script
    assert "escapeHtml(e.detail || '')" in script
    assert "escapeHtml(data.plain_summary || '')" in script
    assert "history.insertAdjacentHTML" in script
    assert "escapeHtml(question)" in script


def test_frontend_reconnect_and_secret_storage_contract():
    from pathlib import Path
    script = Path(__file__).parents[2].joinpath("frontend", "script.js").read_text(encoding="utf-8")
    assert "sessionStorage.setItem(\"mirageXApiKey\"" in script
    assert "sessionStorage.setItem(\"mirageXResetToken\"" in script
    assert "eventsSource.close()" not in script
    assert "X-Mirage-Reset-Token" in script


def test_sse_queue_is_bounded_and_drops_overflow():
    subscriber = event_stream.subscribe()
    try:
        for index in range(100):
            event_stream.publish("test", {"index": index})
        event_stream.publish("overflow", {"index": 101})
        assert subscriber.qsize() == 100
        assert subscriber.get_nowait()["data"]["index"] == 0
    finally:
        event_stream.unsubscribe(subscriber)


def test_reset_clears_rows_without_replacing_database(client):
    client.post("/simulate", json={"scenario": "benign_admin_login"})
    db_path = db.DB_PATH
    assert client.post("/reset").status_code == 200
    assert db.DB_PATH == db_path
    assert db.list_incidents() == []
    assert db.get_alerts() == []


def test_journal_mode_environment_allowlist(monkeypatch):
    monkeypatch.setenv("MIRAGE_JOURNAL_MODE", "DELETE")
    conn = db.get_conn()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].upper() == "DELETE"
    finally:
        conn.close()
    monkeypatch.setenv("MIRAGE_JOURNAL_MODE", "invalid")
    conn = db.get_conn()
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].upper() == "WAL"
    finally:
        conn.close()


def test_sse_endpoint_emits_ready_event(client):
    response = asyncio.run(main.events_stream())
    assert response.media_type == "text/event-stream"

    async def read_ready():
        generator = event_stream.stream()
        message = await generator.__anext__()
        await generator.aclose()
        return message

    assert asyncio.run(read_ready()) == {"event": "ready", "data": {"status": "connected"}}


def test_input_validation_rejects_invalid_identifiers_and_ip(client):
    payload = {
        "incident_id": "bad id",
        "event_type": "auth ssh",
        "src_ip": "not-an-ip",
        "host": "host-03",
        "user": "demo",
    }
    assert client.post("/ingest", json=payload).status_code == 422


def test_all_simulator_and_decoy_writes_are_thread_safe():
    errors = []

    def write(index):
        try:
            db.log_decoy_interaction("INC-CONCURRENT", "fake_ssh", f"PROBE-{index}", "127.0.0.1")
            db.log_alert("INC-CONCURRENT", "LOW", "test", f"alert-{index}")
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(index,)) for index in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(db.get_decoy_interactions("INC-CONCURRENT")) == 20
    assert len(db.get_alerts(limit=100)) == 20


def test_second_run_decoy_gating_is_observable(client, capsys):
    for index, scenario in enumerate(simulator.list_scenarios(), start=1):
        first = client.post("/simulate", json={"scenario": scenario, "incident_id": f"FIRST-{index}"}).json()
        second = client.post("/simulate", json={"scenario": scenario, "incident_id": f"SECOND-{index}"}).json()
        print(f"{scenario}: second run decoy={second['decoy_deployed']}")
        assert first["incident_id"] != second["incident_id"]
    assert "second run decoy=" in capsys.readouterr().out
