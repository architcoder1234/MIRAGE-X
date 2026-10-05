import json

import advisor


class TextBlock:
    type = "text"
    text = '{"plain_summary":"ok","recommended_actions":[],"analyst_note":"ok"}'


class Response:
    content = [TextBlock()]


class RetryMessages:
    def __init__(self):
        self.calls = 0

    def create(self, **_kwargs):
        self.calls += 1
        if self.calls < 2:
            raise RuntimeError("temporary")
        return Response()


def _incident():
    return {
        "incident_id": "INC-ADVISOR",
        "behavior_sequence": ["RECON-SCAN"],
        "risk_score": 5,
        "confidence": "LOW",
        "decoy_deployed": None,
        "mitre_techniques": [],
        "soc_alert": {"severity": "INFO", "would_page": False},
        "predicted_path": {},
    }


def test_retry_then_success(monkeypatch):
    messages = RetryMessages()
    monkeypatch.setattr(advisor, "_classify_error", lambda _error: ("temporary", True))
    monkeypatch.setattr(advisor.time, "sleep", lambda _seconds: None)
    response, error = advisor._call_with_retry(type("Client", (), {"messages": messages})(), prompt="x")
    assert response is not None
    assert error is None
    assert messages.calls == 2


def test_auth_error_does_not_retry(monkeypatch):
    messages = RetryMessages()
    monkeypatch.setattr(advisor, "_classify_error", lambda _error: ("invalid API key", False))
    response, error = advisor._call_with_retry(type("Client", (), {"messages": messages})(), prompt="x")
    assert response is None
    assert error == "invalid API key"
    assert messages.calls == 1


def test_correlation_falls_back_after_api_failure(monkeypatch):
    class Failing:
        def create(self, **_kwargs):
            raise RuntimeError("outage")

    monkeypatch.setattr(advisor, "_client", lambda *_args, **_kwargs: type("Client", (), {"messages": Failing()})())
    monkeypatch.setattr(advisor, "_classify_error", lambda _error: ("network error", False))
    result = advisor.correlate_incidents([_incident()], api_key_override="test")
    assert result["mode"] == "fallback"
    assert result["available"] is False
    assert "unavailable" in result["error"]


def test_fallback_advisory_covers_medium_and_technique_paths():
    incident = _incident()
    incident.update({
        "risk_score": 50,
        "decoy_deployed": "fake_ssh",
        "soc_alert": {"severity": "MEDIUM", "would_page": False},
        "mitre_techniques": [{"technique_id": "T1595", "technique_name": "Scan", "tactic": "Recon"}],
    })
    result = advisor._fallback_advisory(incident)
    assert "closer look" in result["plain_summary"]
    assert "fake_ssh" in result["plain_summary"]
    assert result["recommended_actions"]


def test_generate_and_question_success(monkeypatch):
    client = type("Client", (), {"messages": type("Messages", (), {
        "create": lambda self, **_kwargs: Response()
    })()})()
    monkeypatch.setattr(advisor, "_client", lambda *_args, **_kwargs: client)
    generated = advisor.generate_advisory(_incident(), api_key_override="test")
    answered = advisor.answer_question(_incident(), "What happened?", api_key_override="test")
    assert generated["mode"] == "llm"
    assert answered["mode"] == "llm"


def test_generate_parse_failure_and_question_failure(monkeypatch):
    class BadMessages:
        def create(self, **_kwargs):
            return type("BadResponse", (), {"content": [type("Block", (), {"type": "text", "text": "not-json"})()]})()

    class FailingMessages:
        def create(self, **_kwargs):
            raise RuntimeError("offline")

    monkeypatch.setattr(advisor, "_client", lambda *_args, **_kwargs: type("Client", (), {"messages": BadMessages()})())
    parsed = advisor.generate_advisory(_incident(), api_key_override="test")
    assert parsed["mode"] == "fallback"
    assert "unparseable" in parsed["error"]

    monkeypatch.setattr(advisor, "_client", lambda *_args, **_kwargs: type("Client", (), {"messages": FailingMessages()})())
    monkeypatch.setattr(advisor, "_classify_error", lambda _error: ("network error", False))
    answer = advisor.answer_question(_incident(), "What happened?", api_key_override="test")
    assert answer["mode"] == "fallback"
    assert "unavailable" in answer["error"]


def test_correlation_success_and_shared_fallback():
    incidents = [_incident(), {**_incident(), "incident_id": "INC-OTHER", "decoy_deployed": "fake_ssh",
                               "soc_alert": {"severity": "HIGH", "would_page": True}}]
    fallback = advisor._fallback_correlation(incidents)
    assert "same decoy" in fallback["answer"]
    assert "CRITICAL/HIGH" in fallback["answer"]
