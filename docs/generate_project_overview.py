"""Generate the shareable MIRAGE-X project overview PDF."""

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)


OUTPUT = "docs/MIRAGE-X_Project_Overview.pdf"
NAVY = colors.HexColor("#10233f")
BLUE = colors.HexColor("#1769aa")
TEAL = colors.HexColor("#0f766e")
LIGHT_BLUE = colors.HexColor("#eaf3fb")
LIGHT_GRAY = colors.HexColor("#f3f5f7")
MID_GRAY = colors.HexColor("#64748b")
GREEN = colors.HexColor("#166534")
ORANGE = colors.HexColor("#9a3412")


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleX", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=28, leading=34, textColor=NAVY, alignment=TA_CENTER,
            spaceAfter=8 * mm,
        ),
        "subtitle": ParagraphStyle(
            "SubtitleX", parent=base["Normal"], fontName="Helvetica",
            fontSize=12, leading=17, textColor=MID_GRAY, alignment=TA_CENTER,
            spaceAfter=12 * mm,
        ),
        "h1": ParagraphStyle(
            "H1X", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=18, leading=22, textColor=NAVY, spaceBefore=7 * mm,
            spaceAfter=4 * mm, keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "H2X", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12.5, leading=16, textColor=BLUE, spaceBefore=4 * mm,
            spaceAfter=2 * mm, keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "BodyX", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.5, leading=14, textColor=colors.HexColor("#1f2937"),
            spaceAfter=2.5 * mm,
        ),
        "small": ParagraphStyle(
            "SmallX", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8, leading=11, textColor=MID_GRAY,
        ),
        "bullet": ParagraphStyle(
            "BulletX", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.2, leading=13, leftIndent=10, firstLineIndent=-7,
            bulletIndent=0, textColor=colors.HexColor("#1f2937"),
            spaceAfter=1.5 * mm,
        ),
        "callout": ParagraphStyle(
            "CalloutX", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=11, leading=16, textColor=TEAL, alignment=TA_CENTER,
            borderColor=colors.HexColor("#99f6e4"), borderWidth=1,
            borderPadding=8, backColor=colors.HexColor("#f0fdfa"),
            spaceBefore=3 * mm, spaceAfter=6 * mm,
        ),
        "table": ParagraphStyle(
            "TableX", parent=base["BodyText"], fontName="Helvetica",
            fontSize=7.5, leading=10, textColor=colors.HexColor("#1f2937"),
        ),
        "table_head": ParagraphStyle(
            "TableHeadX", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=7.5, leading=10, textColor=colors.white,
        ),
    }


S = styles()


def P(text, style="body"):
    return Paragraph(text, S[style])


def bullets(items):
    return [P("• " + item, "bullet") for item in items]


def table(headers, rows, widths):
    data = [[P(h, "table_head") for h in headers]]
    data.extend([[P(str(cell), "table") for cell in row] for row in rows])
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
    ]))
    return t


def footer(canvas, doc):
    canvas.saveState()
    width, height = A4
    canvas.setStrokeColor(colors.HexColor("#dbe3ec"))
    canvas.line(18 * mm, 14 * mm, width - 18 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MID_GRAY)
    canvas.drawString(18 * mm, 9 * mm, "MIRAGE-X | Project Overview")
    canvas.drawRightString(width - 18 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_story():
    story = []
    story += [
        Spacer(1, 18 * mm),
        P("MIRAGE-X", "title"),
        P("Integrated Adaptive Cyber Defense & Attacker Intelligence Platform", "subtitle"),
        P(
            "A complete project overview for sharing with collaborators, judges, "
            "mentors, and future contributors.",
            "callout",
        ),
        P(
            "<b>Project purpose.</b> MIRAGE-X is a local, simulation-first cyber "
            "defense MVP that detects suspicious behavior, scores and explains it, "
            "predicts an attacker's next target, deploys a behavior-matched decoy, "
            "learns from the interaction, and presents the full story in a dashboard.",
        ),
        P(
            "<b>Core differentiator.</b> The system is a closed loop rather than a "
            "static alert screen: <b>sensor/simulator -> Attack DNA -> memory and "
            "confidence -> adaptive deception -> evidence feedback -> recomputation "
            "-> explainable dashboard and SOC alerting</b>.",
        ),
        P("At a glance", "h1"),
        table(
            ["Area", "Current implementation"],
            [
                ["Backend", "FastAPI service with SQLite persistence and 20+ REST operations."],
                ["Detection", "Rule-based behavior sequences, risk scoring, confidence bands, and false-positive gates."],
                ["Memory", "Explainable similarity using sequence, MITRE technique overlap, and risk-band matching."],
                ["Deception", "Fake SSH, fake database, and fake admin panel decoys with interaction logging."],
                ["Intelligence", "Attack-path prediction, MITRE ATT&CK mapping, SOC severity, and grounded advisor."],
                ["Frontend", "Responsive static dashboard with replay, trend, comparison, alerts, settings, onboarding, and accessibility."],
                ["Validation", "12 automated tests pass; Python syntax compilation passes."],
                ["Safety", "Simulation-first design, no real credentials, isolated Docker decoys, no live response automation."],
            ],
            [38 * mm, 132 * mm],
        ),
        PageBreak(),
        P("1. Product vision and architecture", "h1"),
        P(
            "MIRAGE-X turns individual security events into an adaptive investigation "
            "workflow. Instead of treating every event as an isolated alert, it builds "
            "a behavioral fingerprint, compares that fingerprint with prior incidents, "
            "selects an appropriate decoy only when justified, and feeds decoy evidence "
            "back into the incident model."
        ),
        P("Closed-loop data flow", "h2"),
        table(
            ["Stage", "What happens", "Primary modules"],
            [
                ["1. Observe", "A repeatable scenario or API event enters the system.", "simulator.py, POST /ingest"],
                ["2. Fingerprint", "Events become a behavior sequence and risk score.", "attack_dna.py"],
                ["3. Remember", "Current behavior is compared with stored incidents.", "memory.py, db.py"],
                ["4. Decide", "Risk band and similarity drive decoy selection.", "deception.py"],
                ["5. Predict", "Behavior is mapped to a likely next network target.", "attack_path.py"],
                ["6. Enrich", "MITRE techniques and SOC severity are attached.", "mitre.py, soc_alert.py"],
                ["7. Deceive", "The selected isolated decoy records raw interaction evidence.", "decoys/*, common.py"],
                ["8. Learn", "Evidence is folded into events and the pipeline recomputes.", "decoy_feedback.py, POST /recompute"],
                ["9. Explain", "Dashboard, PDF, alerts, and advisor present grounded facts.", "frontend, reports.py, advisor.py"],
            ],
            [25 * mm, 91 * mm, 54 * mm],
        ),
        P("Repository structure", "h2"),
        *bullets([
            "<b>backend/</b>: FastAPI application, deterministic engines, SQLite helpers, decoys, and tests.",
            "<b>frontend/</b>: Static HTML/CSS/JavaScript dashboard; no frontend build step is required.",
            "<b>docker/</b>: Dockerfiles for the three isolated decoy services.",
            "<b>docs/</b>: Original concept PDF, build guide, and this shareable overview.",
            "<b>docker-compose.yml</b>: Runs fake SSH, fake DB, and fake admin panel on an internal Docker network.",
            "<b>reset_demo.sh</b>: Resets demo state for repeatable presentations.",
        ]),
        P("2. Implemented backend capabilities", "h1"),
        table(
            ["Capability", "Implemented behavior"],
            [
                ["FastAPI service", "Typed request models, CORS support, startup database initialization, HTTP errors, interactive OpenAPI docs."],
                ["SQLite persistence", "Stores incidents, ordered events, decoy interactions, folded state, and simulated SOC alerts."],
                ["Scenario simulator", "Ten deterministic scenarios cover normal administration and multiple realistic attack patterns."],
                ["Event ingestion", "Accepts external event records with incident ID, event type, source IP, host, user, and detail."],
                ["Risk engine", "Calculates behavior sequence, numeric risk score, and risk band from event evidence."],
                ["False-positive controls", "Benign admin activity remains below the medium-risk threshold and does not trigger a decoy."],
                ["Incident memory", "Finds the closest prior incident and exposes matched features and similarity score."],
                ["Adaptive deception", "Routes database hunting, lateral movement, SSH abuse, privilege escalation, and admin activity to matching decoys."],
                ["Explainability", "Produces a human-readable summary from observed evidence, not an opaque model decision."],
            ],
            [42 * mm, 128 * mm],
        ),
        PageBreak(),
        P("3. Implemented intelligence and defense layers", "h1"),
        P("Attack DNA and risk scoring", "h2"),
        P(
            "The deterministic Attack DNA layer converts raw events into an ordered "
            "behavior sequence. It assigns risk from event types and sequence-level "
            "bonuses, then maps the score to a confidence/risk band. The implementation "
            "covers 14 event types, including reconnaissance, SSH authentication, "
            "privilege escalation, database search, credential spraying, lateral movement, "
            "exfiltration staging and transfer, supply-chain compromise, living-off-the-land "
            "activity, insider access, administrative action, and decoy-derived evidence."
        ),
        P("Cyber Memory", "h2"),
        *bullets([
            "Sequence similarity recognizes behavior even when source indicators differ.",
            "Technique overlap compares the MITRE techniques implied by two sequences.",
            "Risk-band agreement adds context without making similarity alone a threat verdict.",
            "The result is surfaced as a top match with an explainable score and matched features.",
        ]),
        P("Attack-Path and Intent Engine", "h2"),
        *bullets([
            "Maintains a simulated seven-node network graph.",
            "Predicts a likely next target from the observed behavior sequence.",
            "Includes a second host for lateral movement and an external egress point for exfiltration.",
            "Exposes both a JSON prediction and a graph snapshot used by the SVG dashboard diagram.",
        ]),
        P("MITRE ATT&CK mapping", "h2"),
        P(
            "Every supported event type maps to a real technique ID, name, and tactic. "
            "Examples include T1110.003 Password Spraying, T1560 Archive Collected Data, "
            "T1048 Exfiltration Over Alternative Protocol, and T1595 Active Scanning. "
            "Technique tags are returned by the API, shown in the dashboard, and included "
            "in generated incident reports."
        ),
        P("SOC severity simulation", "h2"),
        P(
            "The SOC layer assigns CRITICAL, HIGH, MEDIUM, LOW, or INFO severity and a "
            "would_page flag. High-impact patterns such as exfiltration and supply-chain "
            "signals can page even when a raw numeric score alone would not be sufficient. "
            "The alert channel stores a Slack-styled simulated message, deduplicates repeats, "
            "and only re-fires on a genuine escalation."
        ),
        P("Adaptive deception and feedback", "h2"),
        P(
            "Three decoys are implemented as real socket/HTTP services: fake SSH on port "
            "2222, fake DB on port 3307, and fake admin panel on port 8080. They do not "
            "provide real credentials or real data. Raw traffic is classified into clean "
            "evidence such as CLIENT_BANNER, PROBE_ONLY, and BRUTEFORCE_PATTERN_DETECTED. "
            "The feedback loop folds new evidence into proper incident events idempotently, "
            "then recomputes risk, path prediction, memory, and deception."
        ),
        PageBreak(),
        P("4. Implemented frontend and user experience", "h1"),
        P(
            "The frontend is a static dashboard in frontend/index.html, frontend/style.css, "
            "and frontend/script.js. It can be opened directly in a browser and currently "
            "targets the deployed backend URL configured at the top of script.js."
        ),
        table(
            ["Dashboard feature", "What the user can do"],
            [
                ["Scenario runner", "Choose and execute any simulator scenario, reset the demo, and watch the result."],
                ["Incident list", "Search by incident ID or behavior, filter by risk level and decoy, and select an incident."],
                ["Risk and timeline", "See risk score, band, ordered events, evidence, summary, and a step-by-step risk trend."],
                ["Replay scrubber", "Play, pause, and scrub through event arrival to narrate how risk escalated."],
                ["Attack-path diagram", "See the simulated graph with current and predicted next nodes highlighted."],
                ["Memory view", "Inspect the closest historical match, similarity, and matched features."],
                ["MITRE and SOC panels", "Read technique tags, severity, page decision, and simulated alert reasoning."],
                ["Decoy evidence", "Review interactions captured by fake SSH, fake DB, and fake admin panel."],
                ["Feedback action", "Fold decoy evidence into the incident and recompute the analysis."],
                ["PDF report", "Download a per-incident PDF containing facts, techniques, alert data, and advisor content."],
                ["AI Advisor", "Read a grounded summary, recommended actions, and ask a question about the incident."],
                ["Correlation", "Ask the advisor to compare all incidents currently held in memory."],
                ["Compare", "Select two incidents for a side-by-side risk, decoy, technique, and path comparison."],
                ["Alerts", "Open the simulated SOC channel, see unread counts, and receive toast notifications."],
                ["Settings", "Toggle beginner explanations, panel visibility, theme, accent color, and per-request API key."],
                ["Onboarding", "Use a five-slide guided tour covering the main demo flow and dashboard controls."],
                ["Accessibility", "Use skip navigation, keyboard focus, modal semantics, Escape handling, live regions, and visible focus outlines."],
                ["Responsive layout", "Use the dashboard on a projector, desktop, tablet, or narrow phone-sized viewport."],
            ],
            [43 * mm, 127 * mm],
        ),
        P("AI Advisor design", "h2"),
        P(
            "The advisor is deliberately placed above the deterministic engine. It never "
            "re-decides risk, the selected decoy, MITRE mapping, or SOC severity. With an "
            "Anthropic key it can produce live explanations; without a key, or when a call "
            "fails, it uses a rule-based fallback built from the same facts. Transient "
            "timeouts, connection issues, and rate limits receive bounded retries. The "
            "dashboard distinguishes live AI, missing key, invalid key, and temporary "
            "unavailability rather than hiding the cause."
        ),
        PageBreak(),
        P("5. Scenarios and API surface", "h1"),
        P("Built-in scenarios", "h2"),
        table(
            ["Scenario", "Purpose and notable behavior"],
            [
                ["recon_to_db_hunt", "Classic kill chain: RECON-SCAN -> AUTH-SSH -> PRIV-ESC -> DOWNLOAD -> DB-SEARCH."],
                ["recon_to_db_hunt_variant_ip", "Same behavior from a different source, demonstrating behavior-first memory matching."],
                ["ssh_bruteforce_only", "Repeated SSH authentication attempts against one username."],
                ["benign_admin_login", "Expected administrative activity used as the false-positive control."],
                ["password_spray_campaign", "Many usernames with one password each; emits CRED-SPRAY."],
                ["lateral_movement_breach", "Pivots to a second host and reaches database search."],
                ["data_exfiltration", "Stages data and transfers it out; produces a CRITICAL page."],
                ["supply_chain_compromise", "Poisoned dependency or CI step without human login events."],
                ["living_off_the_land", "Legitimate tools used in a suspicious sequence."],
                ["insider_misuse", "Valid credentials combined with scope drift and sensitive data access."],
            ],
            [52 * mm, 118 * mm],
        ),
        P("REST endpoints", "h2"),
        table(
            ["Method", "Endpoint", "Purpose"],
            [
                ["GET", "/scenarios", "List simulator scenarios."],
                ["POST", "/simulate", "Run a scenario and process its incident."],
                ["POST", "/ingest", "Insert one event and recompute the incident."],
                ["GET", "/incidents", "List stored incidents."],
                ["GET", "/incidents/{id}", "Return a fully enriched incident."],
                ["GET", "/network", "Return the simulated network graph."],
                ["GET", "/incidents/{id}/predicted_path", "Return next-target prediction."],
                ["GET", "/incidents/{id}/risk_trend", "Return step-by-step risk points."],
                ["GET", "/incidents/{id}/similar", "Return closest memory match."],
                ["POST", "/incidents/{id}/recompute", "Fold decoy evidence and recompute."],
                ["GET", "/alerts", "List simulated SOC alerts."],
                ["POST", "/reset", "Reset the demo database."],
                ["GET", "/incidents/{id}/report", "Download a generated PDF report."],
                ["GET", "/settings/llm_status", "Check whether an advisor key is available."],
                ["GET", "/incidents/{id}/advisory", "Generate grounded advisory."],
                ["POST", "/incidents/{id}/ask", "Ask a question about one incident."],
                ["POST", "/advisor/correlate", "Correlate all stored incidents."],
            ],
            [17 * mm, 55 * mm, 98 * mm],
        ),
        PageBreak(),
        P("6. Deployment, safety, and validation", "h1"),
        P("Local run", "h2"),
        P(
            "Install backend/requirements.txt, initialize the SQLite database, start "
            "uvicorn on port 8000, and open frontend/index.html. The backend exposes "
            "interactive API documentation at /docs. The frontend requires no package "
            "manager or build step."
        ),
        P("Dockerized decoys", "h2"),
        *bullets([
            "docker-compose.yml builds all three decoy services.",
            "The services share the backend code and SQLite file through a bind mount, so live evidence appears in the same dashboard.",
            "Ports 2222, 3307, and 8080 are published for controlled local demonstration.",
            "The mirage-isolated Docker network is internal, preventing outbound internet access from the decoy containers.",
            "The design supports nmap, hydra, netcat, curl, and browser demonstrations in a lab environment.",
        ]),
        P("Safety boundary", "h2"),
        *bullets([
            "This is a simulation and deception lab, not a tool for attacking real systems.",
            "Decoys contain no real credentials, production secrets, or real business data.",
            "The SOC channel is explicitly simulated; it does not post to a real Slack or messaging workspace.",
            "The advisor explains and recommends; it does not execute remediation or alter real infrastructure.",
            "Any live-tool testing should stay on localhost or an explicitly isolated lab network.",
        ]),
        P("Validation completed", "h2"),
        table(
            ["Check", "Result"],
            [
                ["Python syntax compilation", "Passed with python -m compileall -q backend."],
                ["Automated backend tests", "12 passed, covering false positives, new scenarios, routing, SOC paging, and MITRE tags."],
                ["Repository state", "The reviewed branch was clean and had no uncommitted changes."],
                ["Known warning", "FastAPI reports a non-blocking deprecation warning for on_event startup handlers."],
                ["Deployment check", "The configured Render URL timed out during the review; deployment availability should be rechecked before sharing a live demo link."],
            ],
            [50 * mm, 120 * mm],
        ),
        P("7. Recommended implementation roadmap", "h1"),
        P(
            "The following additions are ordered by practical value. They preserve the "
            "current deterministic and safety-first design rather than replacing it with "
            "an ungrounded AI system."
        ),
        table(
            ["Priority", "Further implementation", "Expected value"],
            [
                ["P0", "Make deployment reliable: health checks, startup migration, persistent database, logs, and a monitored public URL.", "Ensures the shared dashboard works for every reviewer."],
                ["P0", "Add end-to-end tests for all ten scenarios and API contract tests for every endpoint.", "Catches integration regressions beyond unit-level behavior."],
                ["P0", "Replace permissive CORS in production with an explicit frontend origin allowlist.", "Reduces unnecessary cross-origin exposure."],
                ["P1", "WebSocket or Server-Sent Events updates instead of four-second polling.", "Makes live decoy evidence and alerts feel immediate."],
                ["P1", "Historical analytics view across incidents: trends, top techniques, decoy yield, and false-positive rate.", "Turns the demo into an operational intelligence product."],
                ["P1", "Authentication and role-based access for analysts, viewers, and demo administrators.", "Supports safe multi-user deployment."],
                ["P1", "Background job queue for report generation and advisor requests.", "Prevents slow PDF or AI work from blocking API requests."],
                ["P1", "Configurable rules and scoring profiles stored outside source code.", "Allows different organizations to tune risk without code changes."],
                ["P2", "OpenTelemetry metrics, structured logs, and audit trail for every decision.", "Improves observability and makes decisions defensible."],
                ["P2", "Replayable event stream and export/import of sanitized incidents.", "Enables reproducible research, training, and offline demos."],
                ["P2", "Pluggable sensors for Zeek, Suricata, Windows events, cloud audit logs, or SIEM webhooks.", "Moves from simulation toward controlled real telemetry ingestion."],
                ["P2", "Decoy quality measurement: dwell time, interaction depth, and attacker-path divergence.", "Quantifies whether deception is useful, not merely present."],
                ["P2", "Human feedback workflow for analyst verdicts and rule tuning.", "Creates a safe path toward supervised learning."],
                ["P3", "Advanced sequence models or graph analytics behind the deterministic safety gate.", "Adds research value while preserving explainable fallback behavior."],
                ["P3", "Multi-tenant storage, retention policies, encryption, and secret management.", "Prepares the platform for production-grade deployment."],
            ],
            [17 * mm, 83 * mm, 70 * mm],
        ),
        PageBreak(),
        P("8. Suggested demonstration script", "h1"),
        P(
            "A reliable 90-second presentation can show the complete loop without needing "
            "real external infrastructure."
        ),
        table(
            ["Step", "Demonstration"],
            [
                ["1", "Reset the demo and show an empty incident list."],
                ["2", "Run recon_to_db_hunt. Explain the sequence, score, memory result, predicted path, and fake DB decision."],
                ["3", "Open the timeline replay and scrub through events to show risk climbing."],
                ["4", "Send controlled nmap, hydra, netcat, or curl traffic to a local decoy and show classified evidence."],
                ["5", "Fold the evidence into the incident and point out the recomputed risk and predicted target."],
                ["6", "Run recon_to_db_hunt_variant_ip and show that behavior similarity works despite a different source."],
                ["7", "Run data_exfiltration and show CRITICAL severity, paging, MITRE techniques, and the downloadable PDF."],
                ["8", "Use Compare or Cross-Incident Correlation to demonstrate reasoning across incidents."],
                ["9", "Open Settings to show Beginner Mode, theme, responsive controls, and optional grounded AI Advisor configuration."],
            ],
            [17 * mm, 153 * mm],
        ),
        P("9. Final status", "h1"),
        P(
            "MIRAGE-X is a strong working MVP and demonstration platform. Its most complete "
            "story is the deterministic closed loop: observe behavior, understand it, "
            "predict the next step, deploy a safe decoy, learn from interaction, and "
            "explain the result. The immediate work is reliability and integration testing "
            "rather than adding unbounded features. The strongest future direction is to "
            "connect sanitized real telemetry and analyst feedback while retaining the "
            "current explainability, safety boundary, and rule-based fallback."
        ),
        P(
            "Source of truth: the MIRAGE-X repository README, backend modules, frontend "
            "dashboard, Docker configuration, build guide, and automated tests.",
            "small",
        ),
    ]
    return story


def main():
    doc = BaseDocTemplate(
        OUTPUT,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title="MIRAGE-X Project Overview",
        author="MIRAGE-X Team",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="all", frames=frame, onPage=footer)])
    doc.build(build_story())
    print(OUTPUT)


if __name__ == "__main__":
    main()
