"""
MIRAGE-X — SOC Alert Simulation.

Real SOC tooling doesn't just show a number — it decides whether a human
gets paged. This maps risk score + specific high-severity techniques onto a
CRITICAL/HIGH/MEDIUM/LOW/INFO severity and a would_page flag, so the pitch
can show operational thinking, not just a dashboard number. No actual
paging happens anywhere — this is a label for the dashboard/report only.
"""

# Event types that page a human regardless of overall risk score, because
# in a real SOC these are "stop everything" signals even in isolation —
# exfiltration and supply-chain compromise are the two that matter most.
ALWAYS_PAGE_EVENTS = {"EXFIL-STAGING", "EXFIL-TRANSFER", "SUPPLY-CHAIN"}


def severity_for(risk_score, behavior_sequence):
    """
    Returns {severity, would_page, reason}. Severity thresholds intentionally
    mirror the risk bands used elsewhere (LOW/MEDIUM/HIGH) plus a CRITICAL
    tier above HIGH, so the vocabulary stays consistent across the system.
    """
    triggered = ALWAYS_PAGE_EVENTS.intersection(behavior_sequence)
    if triggered:
        return {
            "severity": "CRITICAL",
            "would_page": True,
            "reason": f"{', '.join(sorted(triggered))} detected — exfiltration/supply-chain "
                      f"signals page regardless of overall score",
        }

    if risk_score >= 85:
        return {
            "severity": "CRITICAL",
            "would_page": True,
            "reason": f"risk score {risk_score}/100 exceeds the CRITICAL threshold (85)",
        }
    if risk_score >= 70:
        return {
            "severity": "HIGH",
            "would_page": True,
            "reason": f"risk score {risk_score}/100 in the HIGH band — pages during business hours",
        }
    if risk_score >= 45:
        return {
            "severity": "MEDIUM",
            "would_page": False,
            "reason": f"risk score {risk_score}/100 in the MEDIUM band — queued for analyst review, no page",
        }
    if risk_score >= 15:
        return {
            "severity": "LOW",
            "would_page": False,
            "reason": f"risk score {risk_score}/100 in the LOW band — logged only",
        }
    return {
        "severity": "INFO",
        "would_page": False,
        "reason": "minimal or benign activity — informational only",
    }
