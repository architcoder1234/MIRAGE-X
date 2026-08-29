"""
MIRAGE-X — LLM Advisor Layer.

Deliberately sits ON TOP of the deterministic engine, never inside it.
attack_dna.py / deception.py / mitre.py / soc_alert.py still make every
actual decision (risk score, decoy, technique mapping, page/no-page) —
that's what stays 100% explainable and rule-based. This module's only job
is to turn those already-computed, evidence-grounded facts into:

  1. a plain-English narrative a non-technical stakeholder can read, and
  2. a short list of recommended next actions for a human responder,
  3. free-form Q&A about one specific incident.

It never invents a risk score, a decoy choice, or a MITRE technique — the
prompt hands the model the finished facts and tells it to explain them,
not re-decide them. If no API key is configured (or the call fails for any
reason — offline demo, rate limit, bad key), everything falls back to a
template built from the same facts, so the dashboard never breaks and
never blocks on the network.

Auth: reads ANTHROPIC_API_KEY from the environment by default. A caller
may also pass an explicit api_key_override (the frontend's Settings panel
lets a user paste their own key, sent per-request via the
X-Anthropic-Key header, so a judge's laptop with no env var set can still
demo the live LLM path without editing any files).

Transient failures (rate limits, timeouts, connection errors) get a couple
of quick retries before falling back, so a momentary blip is labeled
differently in the UI than "no key configured" or "bad key" — see
_classify_error(). correlate_incidents() extends the same pattern across
*all* incidents currently in memory, for cross-incident questions the
rule engine can't answer on its own (e.g. "are any of these related?").
"""
import os
import json
import time

MODEL = os.environ.get("MIRAGE_X_ANTHROPIC_MODEL", "claude-sonnet-5")

# Transient errors (rate limit, timeout, 5xx) get a couple of quick retries
# with backoff before falling back — a blip shouldn't look identical to "no
# key configured" in the UI. Auth errors and bad requests never retry, since
# retrying a wrong key just burns time for the same guaranteed failure.
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = (0.6, 1.5)

SYSTEM_PROMPT = """You are the advisory layer of MIRAGE-X, a cyber-deception \
demo system. You are given the ALREADY-COMPUTED, evidence-grounded output of \
a rule-based detection engine for one incident: its behavior sequence, risk \
score, confidence, the decoy decision, MITRE ATT&CK techniques, the SOC \
severity, and the predicted next target.

Your only job is to explain these facts in plain English for two audiences \
at once — a non-technical stakeholder and a SOC analyst — and to suggest \
concrete next actions. You must NOT invent a different risk score, decoy, \
technique, or severity than the ones given to you; treat them as ground \
truth and explain/advise around them. If the incident looks benign, say so \
plainly instead of manufacturing urgency.

Respond with ONLY a JSON object, no markdown fences, no preamble, matching \
exactly this shape:
{
  "plain_summary": "2-3 sentences, no jargon, understandable by someone with zero security background",
  "recommended_actions": ["short imperative action", "short imperative action", "short imperative action"],
  "analyst_note": "1-2 sentences of the technical detail a SOC analyst would want, referencing the specific techniques/events given"
}"""


def _client(api_key_override=None):
    key = api_key_override or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    return anthropic.Anthropic(api_key=key)


def _classify_error(e):
    """
    Turns an SDK exception into a short, honest label for the UI, and says
    whether it's worth retrying. Falls back to a generic label if the
    anthropic package isn't importable (e.g. it was available at call time
    but something odd happened) or the exception type is unrecognized.
    """
    try:
        import anthropic
    except ImportError:
        return "connection error", False

    if isinstance(e, anthropic.AuthenticationError):
        return "invalid API key", False
    if isinstance(e, anthropic.PermissionDeniedError):
        return "API key lacks permission", False
    if isinstance(e, anthropic.RateLimitError):
        return "rate limited", True
    if isinstance(e, anthropic.APITimeoutError):
        return "request timed out", True
    if isinstance(e, anthropic.APIConnectionError):
        return "network error reaching Anthropic", True
    if isinstance(e, anthropic.InternalServerError):
        return "Anthropic API error", True
    if isinstance(e, anthropic.APIStatusError):
        return f"API error ({e.status_code})", False
    return f"{type(e).__name__}", False


def _call_with_retry(client, **kwargs):
    """
    Calls client.messages.create with a couple of quick retries on
    transient errors only. Returns (response_or_None, error_label_or_None).
    """
    last_label = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return client.messages.create(**kwargs), None
        except Exception as e:
            label, retryable = _classify_error(e)
            last_label = label
            if not retryable or attempt == MAX_RETRIES:
                return None, label
            time.sleep(RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)])
    return None, last_label


def _incident_facts_block(incident):
    """Compact, deterministic text block handed to the model as ground truth."""
    mitre_lines = "\n".join(
        f"  - {t['technique_id']} {t['technique_name']} ({t['tactic']})"
        for t in incident.get("mitre_techniques", [])
    ) or "  - none mapped"

    alert = incident.get("soc_alert") or {}
    path = incident.get("predicted_path") or {}
    match = incident.get("similarity_top_match")

    return f"""Incident: {incident.get('incident_id')}
Behavior sequence: {' -> '.join(incident.get('behavior_sequence', []))}
Risk score: {incident.get('risk_score')}/100
Memory confidence: {incident.get('confidence')}
Closest historical match: {f"{match['incident_id']} (score {match['score']})" if match else "none"}
Decoy decision: {incident.get('decoy_deployed') or 'no decoy deployed'}
SOC severity: {alert.get('severity', 'n/a')} (would_page={alert.get('would_page', False)}) — {alert.get('reason', '')}
Predicted next target: {path.get('predicted_next_label', 'n/a')} — {path.get('reason', '')}
MITRE ATT&CK techniques:
{mitre_lines}"""


def _fallback_advisory(incident):
    """Template built from the same facts, used whenever the LLM path is unavailable."""
    alert = incident.get("soc_alert") or {}
    decoy = incident.get("decoy_deployed")
    risk = incident.get("risk_score", 0)
    techniques = incident.get("mitre_techniques", [])

    if risk >= 70:
        tone = "This looks like a real, active attack, not routine noise."
    elif risk >= 45:
        tone = "This is worth a closer look, though it hasn't escalated to the top severity band."
    else:
        tone = "This activity currently looks low-risk or routine."

    plain_summary = (
        f"{tone} The system observed {len(incident.get('behavior_sequence', []))} step(s) "
        f"of activity and scored it {risk}/100. "
        + (f"A decoy ({decoy}) was deployed to keep watching without exposing anything real."
           if decoy else "No decoy was needed for this one.")
    )

    actions = []
    if alert.get("would_page"):
        actions.append("Treat as active — notify the on-call responder now.")
    else:
        actions.append("Log and queue for analyst review during normal hours.")
    if decoy:
        actions.append(f"Monitor {decoy} for further attacker interaction before responding.")
    if techniques:
        actions.append(f"Cross-check {techniques[0]['technique_id']} ({techniques[0]['technique_name']}) against existing playbooks.")
    else:
        actions.append("No mapped techniques yet — re-check once more events arrive.")

    analyst_note = (
        f"Sequence: {' -> '.join(incident.get('behavior_sequence', [])) or 'no events'}. "
        + (f"Techniques observed: {', '.join(t['technique_id'] for t in techniques)}." if techniques
           else "No MITRE techniques mapped for this sequence.")
    )

    return {
        "mode": "fallback",
        "available": False,
        "plain_summary": plain_summary,
        "recommended_actions": actions,
        "analyst_note": analyst_note,
    }


def generate_advisory(incident, api_key_override=None):
    """
    Returns {mode, available, plain_summary, recommended_actions, analyst_note,
    error?}. mode is "llm" on a successful model call, "fallback" otherwise —
    the frontend uses this to label which one it's showing.
    """
    client = _client(api_key_override)
    if client is None:
        result = _fallback_advisory(incident)
        result["error"] = "No ANTHROPIC_API_KEY configured — showing rule-based advisory instead."
        return result

    resp, error_label = _call_with_retry(
        client,
        model=MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _incident_facts_block(incident)}],
    )
    if resp is None:
        result = _fallback_advisory(incident)
        result["error"] = f"AI advisor unavailable ({error_label}) — showing rule-based advisory instead."
        return result

    try:
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(text)
        return {
            "mode": "llm",
            "available": True,
            "plain_summary": parsed.get("plain_summary", ""),
            "recommended_actions": parsed.get("recommended_actions", []),
            "analyst_note": parsed.get("analyst_note", ""),
        }
    except Exception as e:
        result = _fallback_advisory(incident)
        result["error"] = f"AI advisor returned an unparseable response ({type(e).__name__}) — showing rule-based advisory instead."
        return result


def answer_question(incident, question, api_key_override=None):
    """Free-form Q&A about one incident, grounded in the same facts block."""
    client = _client(api_key_override)
    if client is None:
        return {
            "mode": "fallback",
            "available": False,
            "answer": "The AI advisor isn't connected right now (no API key configured). "
                      "You can still read the risk score, decoy decision, MITRE techniques, "
                      "and predicted path panels directly — those are the same facts it would "
                      "have answered from.",
            "error": "No ANTHROPIC_API_KEY configured.",
        }

    resp, error_label = _call_with_retry(
        client,
        model=MODEL,
        max_tokens=400,
        system="You are the advisory layer of MIRAGE-X. Answer the user's question about "
               "the ONE incident described below, using only the facts given — don't invent "
               "numbers, techniques, or decisions not present in the facts. Keep it to 2-4 "
               "sentences, plain English, no markdown.",
        messages=[{
            "role": "user",
            "content": f"{_incident_facts_block(incident)}\n\nQuestion: {question}",
        }],
    )
    if resp is None:
        return {
            "mode": "fallback",
            "available": False,
            "answer": "Couldn't reach the AI advisor just now (" + error_label + "), so here are "
                      "the grounded facts instead: " + _incident_facts_block(incident).replace("\n", " "),
            "error": f"AI advisor unavailable ({error_label}).",
        }

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    return {"mode": "llm", "available": True, "answer": text}


def _fallback_correlation(incidents):
    """Rule-based cross-incident summary — groups by decoy and flags shared high-severity signals."""
    by_decoy = {}
    critical_or_high = []
    for inc in incidents:
        decoy = inc.get("decoy_deployed")
        if decoy:
            by_decoy.setdefault(decoy, []).append(inc["incident_id"])
        alert = inc.get("soc_alert") or {}
        if alert.get("severity") in ("CRITICAL", "HIGH"):
            critical_or_high.append((inc["incident_id"], alert.get("severity")))

    lines = [f"{len(incidents)} incident(s) in memory."]
    shared = {d: ids for d, ids in by_decoy.items() if len(ids) > 1}
    if shared:
        for decoy, ids in shared.items():
            lines.append(f"{len(ids)} incidents were routed to the same decoy ({decoy}): {', '.join(ids)} — worth checking if this is one attacker returning.")
    else:
        lines.append("No two incidents share the same decoy yet.")
    if critical_or_high:
        lines.append(f"{len(critical_or_high)} incident(s) at CRITICAL/HIGH severity: " +
                      ", ".join(f"{iid} ({sev})" for iid, sev in critical_or_high) + ".")

    return {
        "mode": "fallback",
        "available": False,
        "answer": " ".join(lines),
        "error": "No ANTHROPIC_API_KEY configured — showing rule-based correlation instead.",
    }


def correlate_incidents(incidents, question=None, api_key_override=None):
    """
    Cross-incident Q&A/correlation — answers a question (or a default
    "are any of these related?" prompt) using ALL incidents currently in
    memory, not just one. This is the one thing the rule engine genuinely
    can't do on its own: spot a pattern across separate incidents.
    """
    if not incidents:
        return {"mode": "fallback", "available": False, "answer": "No incidents in memory yet — run a scenario first."}

    client = _client(api_key_override)
    if client is None:
        return _fallback_correlation(incidents)

    facts = "\n\n---\n\n".join(_incident_facts_block(inc) for inc in incidents)
    q = question.strip() if question and question.strip() else (
        "Are any of these incidents related, part of the same campaign, or worth "
        "escalating together? Summarize any patterns across them in plain English."
    )

    resp, error_label = _call_with_retry(
        client,
        model=MODEL,
        max_tokens=500,
        system="You are the advisory layer of MIRAGE-X, looking across ALL incidents "
               "currently in memory (given below, separated by ---). Use only the facts "
               "given — don't invent techniques, scores, or decisions not present. Answer "
               "the question in plain English, 3-6 sentences, no markdown.",
        messages=[{"role": "user", "content": f"{facts}\n\nQuestion: {q}"}],
    )
    if resp is None:
        result = _fallback_correlation(incidents)
        result["error"] = f"AI advisor unavailable ({error_label}) — showing rule-based correlation instead."
        return result

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()
    return {"mode": "llm", "available": True, "answer": text}
