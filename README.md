# MIRAGE-X

**Integrated Adaptive Cyber Defense & Attacker Intelligence Platform**
Ignition × United Hackathon 2026 · UGI Prayagraj · 28th–29th August 2026

> "MIRAGE-X doesn't just detect attackers — it understands their behavior, predicts their path, dynamically changes the environment they see, and turns their actions into defensive intelligence."

## What this repo is

A working MVP skeleton of the closed loop described in `docs/MIRAGE-X_Original_Concept.pdf`:

```
Attack Sensor → Attack DNA → Attack-Path/Confidence Engine → Adaptive Deception
      → Cyber Memory → Explainable AI Defender → Dashboard
```

Everything runs **locally, in simulation** — no real attacks, no real credentials,
no uncontrolled external access. See "Safety Boundary" below.

## Quick start

```bash
cd backend
pip install -r requirements.txt
python -c "import db; db.init_db(reset=True)"
uvicorn main:app --reload --port 8000
```

Then open `frontend/index.html` directly in a browser (no build step needed —
it's a single static file that calls `http://localhost:8000`).

### Running isolated decoys via Docker (recommended for the actual demo)

```bash
INCIDENT_ID=INC-0001 docker compose up --build
```

This starts both decoys on an isolated Docker network (no outbound internet
access from inside the containers) while still publishing their ports to the
host, so `nmap`/`hydra`/`nc` from your WSL Kali or Parrot terminal can reach
them. They share the same SQLite file as the backend running on the host, so
everything shows up live in the dashboard.

If you'd rather run a decoy directly without Docker (fine for local dev,
just not isolated):

```bash
cd backend
python decoys/fake_ssh.py --incident INC-0001 --port 2222
```

## What's implemented (P0, working now)

- [x] Controlled attacker simulator — **10 repeatable scenarios**, covering
      recon→DB, brute force, benign traffic, a same-behavior/different-IOC
      pair for the memory demo, **plus six industry-realistic attack
      patterns**: password spraying, lateral movement, data exfiltration,
      supply-chain compromise, living-off-the-land, and insider misuse
- [x] MITRE ATT&CK mapping (`mitre.py`) — every event type maps to a real
      technique ID/name/tactic (T1110.003, T1560, T1048, etc.), surfaced in
      the API, dashboard, and PDF report — so the pitch says "this is
      T1595 (Active Scanning)" instead of an internal-only label
- [x] SOC severity simulation (`soc_alert.py`) — CRITICAL/HIGH/MEDIUM/LOW/INFO
      severity + a `would_page` flag; exfiltration and supply-chain signals
      always page regardless of raw score, modeling how a real SOC actually
      triages, not just a number on a gauge
- [x] Attack DNA — behavior sequence + rule-based risk score, now covering
      14 event types including exfiltration-chain and lateral-movement bonuses
- [x] Cyber Memory — rule-based, explainable similarity (sequence + technique
      overlap + risk-band match)
- [x] Adaptive Deception — confidence-driven decoy selection across all
      three decoys, with exfiltration signals taking top routing priority
- [x] Fake SSH + Fake DB + Fake Admin Panel decoys — real isolated socket/HTTP
      servers, log every interaction
- [x] Dashboard — timeline, risk gauge, decoy status, evidence panel, memory
      list, MITRE technique tags, SOC alert banner, PDF report download
- [x] Explainable summary — human-readable, grounded only in retrieved evidence

- [x] Attack-Path & Intent Engine — expanded simulated network graph
      (7 nodes including a second host for lateral movement and an external
      egress point for exfiltration) + rule-based next-target prediction
      (`attack_path.py`, `GET /network`, `GET /incidents/{id}/predicted_path`)
- [x] Real-attack-aware decoy logging — `decoys/common.py` classifies raw
      traffic from actual tools (nmap, hydra, netcat, curl) into clean labels
      (`CLIENT_BANNER`, `PROBE_ONLY`, `BRUTEFORCE_PATTERN_DETECTED`) instead of
      binary noise, color-coded in the dashboard evidence panel
- [x] Decoy-evidence feedback loop — `decoy_feedback.py` converts logged decoy
      interactions into real `events` (idempotently, via a `folded` flag), so
      running `nmap`/`hydra`/`curl` against a decoy actually moves the risk
      score and predicted next target on `POST /incidents/{id}/recompute`
- [x] Docker isolation for all three decoys — `docker-compose.yml` +
      `docker/fake-ssh/`, `docker/fake-db/`, `docker/fake-admin-panel/`. All
      run on an `internal: true` network (no outbound internet) while still
      reachable from the host for the live demo; code is bind-mounted so
      decoys share the same SQLite file as the host-run backend
- [x] PDF incident reports (`reports.py`, `GET /incidents/{id}/report`) —
      one-page report with risk score, SOC severity, MITRE techniques, and
      decoy evidence, generated with ReportLab and downloadable straight
      from the dashboard
- [x] False-positive test suite (`backend/tests/`) — 12 automated pytest
      tests proving benign traffic never triggers a decoy, even with memory
      full of unrelated HIGH-risk incidents, plus sanity checks that every
      new attack scenario produces the behavior the pitch claims. Run with
      `cd backend && pytest tests/ -v`
- [x] LLM advisor layer (`backend/advisor.py`, `GET /incidents/{id}/advisory`,
      `POST /incidents/{id}/ask`) — grounded strictly in the already-computed
      risk score, decoy decision, MITRE techniques, and SOC severity; it
      explains and recommends, it never re-decides anything. Falls back to a
      rule-based advisory (same facts, template text) if no API key is set
      or the call fails, so the dashboard never depends on network access
- [x] Dashboard redesign for non-technical audiences — a Settings panel
      (⚙ top right) with Beginner Mode (adds plain-English explanations
      under every panel), per-panel show/hide toggles, and a place to paste
      an Anthropic API key for the live AI Advisor; "?" tooltips on every
      section header explain the jargon (risk vs. confidence, MITRE ATT&CK,
      SOC severity) inline
- [x] Attack-path node diagram — the predicted-path panel now renders the
      actual simulated network graph (`GET /network`) as an SVG, with the
      attacker's current position and predicted next hop highlighted, not
      just text
- [x] Risk trend sparkline (`GET /incidents/{id}/risk_trend`) — shows how
      the risk score climbed step-by-step as each event arrived, not just
      the final number, reinforcing the closed-loop story
- [x] Cross-incident correlation (`advisor.correlate_incidents`,
      `POST /advisor/correlate`) — the AI Advisor can now answer questions
      across every incident in memory at once ("are any of these related?"),
      the one thing the rule-based engine can't do on its own. Same
      grounded-facts/rule-based-fallback pattern as the per-incident advisor
- [x] Retry + error classification in the advisor layer — transient errors
      (rate limits, timeouts, connection issues) get a couple of quick
      retries before falling back; the UI now distinguishes "no key
      configured" from "bad key" from "AI temporarily unavailable" instead
      of treating every failure identically
- [x] AI Advisor summary folded into the PDF report — `reports.py` now
      renders the advisor's plain-English summary, recommended actions, and
      analyst note as a labeled section (clearly marked AI-Generated vs.
      Rule-Based), in addition to the existing rule-based explainable
      summary
- [x] Responsive dashboard — the 3-column layout collapses to a single
      column under ~1100px and the settings modal goes full-screen under
      ~640px, so it degrades gracefully on a projector or a judge's phone
- [x] Attack replay / timeline scrubber — a play/pause + slider control
      above the timeline steps through an incident's events one at a time
      instead of dumping the whole sequence at once, for narrating the
      story live during a demo
- [x] Incident search & filtering — free-text search (ID or behavior) plus
      risk-level and decoy dropdown filters above the incident list, so
      judges can find something themselves during Q&A without you
      scrolling for them
- [x] Simulated SOC alert channel (`backend/alert_channel.py`, `GET
      /alerts`) — any incident that crosses the paging threshold gets a
      Slack-styled message logged to a simulated `#soc-alerts` channel
      (🔔 Alerts button, header badge for unread, toast on arrival).
      Dedupes against repeat calls for the same incident and only re-fires
      on a genuine severity escalation — no real network call is ever
      made; it's honestly labeled as a simulation, not a fake integration
- [x] Side-by-side incident comparison — tick two incidents in the list
      and hit Compare for a field-by-field diff (risk, decoy, MITRE
      techniques, predicted path), with a callout when they share a decoy
      or techniques — surfaces the "same attacker returning?" question
      visually instead of just via the AI Advisor's correlation answer
- [x] Theme customization — light/dark toggle and an accent-color picker
      in Settings, applied via CSS custom properties and persisted
      per-browser alongside the other settings
- [x] Toast notifications — new incidents, folded decoy evidence, live
      decoy interactions picked up on the periodic poll, and new simulated
      alerts all surface as a brief toast instead of a silent panel update
- [x] Onboarding walkthrough — a 5-slide guided tour (❓ Help button,
      auto-shown once per browser) covering running a scenario, search/
      filter/compare, replay, the AI Advisor, and alerts/settings
- [x] Accessibility pass — skip-to-content link, `sr-only` labels on
      inputs that only had a placeholder before, all modals use
      `role="dialog"`/`aria-modal`, focus moves into a modal on open and
      returns to the trigger on close, Escape closes whichever modal is
      open, visible `:focus-visible` outlines, `aria-live` regions on
      status lines and toasts

## What's left (P1 / stretch — see `docs/BUILD_GUIDE.md`)

- [ ] Live updates via WebSocket/SSE instead of the current 4s poll
- [ ] Historical analytics view (trends across all incidents, not just one)
- [ ] Full end-to-end run-through of all 10 scenarios to confirm nothing's broken
- [ ] Pitch deck, architecture diagram export, rehearsal, backup demo video

## AI Advisor layer

`backend/advisor.py` sits **on top of** the deterministic engine, not inside
it — `attack_dna.py` / `deception.py` / `mitre.py` / `soc_alert.py` still make
every actual decision (risk score, decoy, technique mapping, page/no-page).
The advisor only turns those already-computed facts into a plain-English
summary, 2-3 recommended next actions, and free-form Q&A about one incident.

- **With an API key** (`ANTHROPIC_API_KEY` env var on the server, or pasted
  into the dashboard's Settings panel — sent per-request via the
  `X-Anthropic-Key` header so a judge's laptop can demo it without editing
  any files): live calls to the Anthropic API, model set via
  `MIRAGE_X_ANTHROPIC_MODEL` (defaults to `claude-sonnet-5`). Transient
  errors (rate limits, timeouts, connection issues) get up to two quick
  retries before falling back.
- **Without a key**, or if a call fails for any reason: a rule-based
  fallback built from the same facts — the dashboard never breaks and never
  blocks on the network. The AI Advisor panel labels which mode produced
  what you're looking at (`LIVE AI` vs `RULE-BASED`), and the error message
  distinguishes "no key configured" from "bad key" from "temporarily
  unavailable (rate limited/timeout)" instead of treating every failure the
  same way.
- **`POST /advisor/correlate`** — the same pattern extended across every
  incident currently in memory, for questions a single-incident view can't
  answer ("are any of these related, or the same attacker returning?").
  Surfaced in the dashboard as the "Cross-Incident Correlation" block below
  the AI Advisor panel.
- The advisor's summary is also folded into the PDF report
  (`GET /incidents/{id}/report`) as a labeled section, alongside the
  existing rule-based Explainable AI Defender summary.

## Attack scenarios

| Scenario | What it models | Notable event types |
|---|---|---|
| `recon_to_db_hunt` | Classic kill chain to DB compromise | RECON-SCAN → AUTH-SSH → PRIV-ESC → DOWNLOAD → DB-SEARCH |
| `recon_to_db_hunt_variant_ip` | Same behavior, different source — the memory-match demo pair | same as above |
| `ssh_bruteforce_only` | One username hammered repeatedly | AUTH-SSH ×4 |
| `benign_admin_login` | Expected admin activity — the false-positive control case | AUTH-SSH, ADMIN-ACTION |
| `password_spray_campaign` | Many usernames, one password each — dodges lockouts | CRED-SPRAY ×4 |
| `lateral_movement_breach` | Pivots from the entry host to a second host | LATERAL-MOVE ×2, DB-SEARCH |
| `data_exfiltration` | Data staged then actually transferred out | EXFIL-STAGING, EXFIL-TRANSFER |
| `supply_chain_compromise` | Poisoned dependency/CI step, not a human attacker | SUPPLY-CHAIN, LOTL-ACTIVITY |
| `living_off_the_land` | Legitimate admin tools used suspiciously | LOTL-ACTIVITY ×2 |
| `insider_misuse` | Valid creds, working hours, scope drift | INSIDER-ACCESS, DB-SEARCH |

## Repo structure

```
mirage-x/
  backend/
    main.py           FastAPI app — all endpoints
    db.py              SQLite schema + helpers (frozen schema)
    simulator.py        Controlled attacker simulator (10 scenarios)
    attack_dna.py        Behavior sequence + risk scoring
    memory.py             Explainable similarity retrieval
    deception.py            Confidence-driven decoy selection
    attack_path.py            Attack-path & intent prediction
    mitre.py                    MITRE ATT&CK technique mapping
    soc_alert.py                  SOC severity / paging simulation
    reports.py                      PDF incident report generator
    decoy_feedback.py                 Decoy evidence -> risk score feedback
    decoys/
      fake_ssh.py            Isolated SSH honeypot socket server
      fake_db.py               Isolated fake-DB socket server
      fake_admin_panel.py       Isolated HTTP admin-login decoy
    tests/
      conftest.py             Isolated per-test SQLite fixture
      test_false_positives.py False-positive + new-scenario regression suite
    requirements.txt
  frontend/
    index.html         Single-file dashboard (no build step)
    script.js
    style.css
  docker/
    fake-ssh/Dockerfile
    fake-db/Dockerfile
    fake-admin-panel/Dockerfile
  docker-compose.yml   Isolated decoy stack (internal network, no outbound access)
  data/                (put exported demo incident JSON here if you want fixtures)
  docs/
    BUILD_GUIDE.md      Day-by-day plan mapped to real dates
    MIRAGE-X_Original_Concept.pdf   (your original proposal — kept for reference)
  reset_demo.sh
  README.md
```

## Safety Boundary

All demos run in an isolated local/lab environment. The attacker is a
controlled simulator, not real traffic. Decoys hold no real credentials, no
sensitive data, and make no outbound connections. Response actions in this
MVP are **recommendations only** — nothing here takes live automated action
against real infrastructure.

## Novelty note (for the pitch)

Honeypots, attack graphs, behavioral analysis, incident correlation, and
AI-assisted security are all established areas. The contribution here is the
**specific integrated architecture and confidence-driven adaptive loop** —
behavior decides what deceptive environment the attacker sees next, and every
past decision becomes reusable memory for the next incident.
