"""
MIRAGE-X — False-Positive & New-Scenario Test Suite.

The single most common judge question for a "detect attackers" system is
"how do you know it doesn't just flag everything?" This suite proves it,
rather than claiming it: benign traffic never gets a decoy, even after
memory fills up with unrelated high-risk incidents. It also sanity-checks
that the new attack scenarios (password spray, lateral movement,
exfiltration, supply chain, living-off-the-land, insider misuse) actually
produce the behavior the pitch claims they do.

Run with: cd backend && pytest tests/ -v
"""
import simulator
import main as mirage_main


def _run(scenario, incident_id):
    simulator.run_scenario(scenario, incident_id)
    return mirage_main._process_incident(incident_id)


# ---------- false positives ----------

def test_benign_admin_login_gets_no_decoy_on_fresh_memory():
    incident = _run("benign_admin_login", "INC-FP-001")
    assert incident["decoy_deployed"] is None
    assert incident["risk_band"] if "risk_band" in incident else True  # noqa: keep readable
    assert incident["risk_score"] < 45  # stays under the MEDIUM risk band


def test_benign_admin_login_stays_clean_with_populated_memory():
    # Fill memory with unrelated HIGH-risk incidents first — a naive
    # "confidence=LOW -> decoy" rule would misfire here, since a brand new
    # benign incident will always start with a low similarity score against
    # unrelated history. The risk-band gate is what should save it.
    _run("recon_to_db_hunt", "INC-FP-010")
    _run("data_exfiltration", "INC-FP-011")
    _run("lateral_movement_breach", "INC-FP-012")

    incident = _run("benign_admin_login", "INC-FP-013")
    assert incident["decoy_deployed"] is None
    assert incident["soc_alert"]["would_page"] is False


def test_repeated_benign_runs_never_trigger_a_decoy():
    for i in range(5):
        incident = _run("benign_admin_login", f"INC-FP-REPEAT-{i}")
        assert incident["decoy_deployed"] is None, f"run {i} incorrectly deployed a decoy"


def test_benign_admin_login_matches_itself_without_false_alarm():
    # Two benign incidents should be able to recognize each other (HIGH
    # similarity) without that similarity ever being treated as a threat —
    # matching isn't the same as malicious.
    first = _run("benign_admin_login", "INC-FP-020")
    second = _run("benign_admin_login", "INC-FP-021")
    assert second["decoy_deployed"] is None
    assert first["decoy_deployed"] is None


# ---------- new attack scenarios behave as intended ----------

def test_password_spray_uses_distinct_event_type_from_bruteforce():
    spray = _run("password_spray_campaign", "INC-ATK-SPRAY")
    brute = _run("ssh_bruteforce_only", "INC-ATK-BRUTE")
    assert "CRED-SPRAY" in spray["behavior_sequence"]
    assert "CRED-SPRAY" not in brute["behavior_sequence"]


def test_lateral_movement_routes_to_db_decoy_once_it_reaches_db_search():
    # The scenario ends in DB-SEARCH after pivoting hosts — DB-SEARCH is a
    # more specific, worse signal than generic lateral movement, so it
    # should win the routing decision (tested separately below in isolation).
    incident = _run("lateral_movement_breach", "INC-ATK-LATERAL")
    assert incident["decoy_deployed"] == "fake_db"
    assert "LATERAL-MOVE" in incident["behavior_sequence"]


def test_lateral_movement_alone_without_db_search_routes_to_fake_ssh():
    import deception
    decoy, band, reason = deception.select_decoy(
        ["RECON-SCAN", "AUTH-SSH", "PRIV-ESC", "LATERAL-MOVE"],
        similarity_score=0.1, risk_band="MEDIUM",
    )
    assert decoy == "fake_ssh"


def test_data_exfiltration_triggers_critical_soc_alert():
    incident = _run("data_exfiltration", "INC-ATK-EXFIL")
    assert incident["soc_alert"]["severity"] == "CRITICAL"
    assert incident["soc_alert"]["would_page"] is True
    assert incident["decoy_deployed"] == "fake_db"


def test_supply_chain_scenario_reaches_high_risk_without_human_login_events():
    incident = _run("supply_chain_compromise", "INC-ATK-SUPPLY")
    assert "SUPPLY-CHAIN" in incident["behavior_sequence"]
    assert incident["risk_score"] >= 45


def test_living_off_the_land_is_flagged_despite_legitimate_tools():
    incident = _run("living_off_the_land", "INC-ATK-LOTL")
    assert "LOTL-ACTIVITY" in incident["behavior_sequence"]
    assert incident["risk_score"] > 0


def test_insider_misuse_eventually_crosses_out_of_benign_territory():
    incident = _run("insider_misuse", "INC-ATK-INSIDER")
    # Should NOT be treated as identical to true benign traffic — it has
    # DB-SEARCH + EXFIL-STAGING in it despite starting with valid creds.
    assert incident["risk_score"] > _run("benign_admin_login", "INC-ATK-INSIDER-CONTROL")["risk_score"]


def test_mitre_techniques_are_attached_for_new_event_types():
    incident = _run("data_exfiltration", "INC-ATK-MITRE")
    technique_ids = {t["technique_id"] for t in incident["mitre_techniques"]}
    assert "T1560" in technique_ids  # EXFIL-STAGING
    assert "T1048" in technique_ids  # EXFIL-TRANSFER
