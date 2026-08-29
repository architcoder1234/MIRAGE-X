# MIRAGE-X — Build Guide (dated)

Today is **Sun 16 Aug 2026**. Hackathon is **28th–29th Aug** at UGI Prayagraj.
That gives you 12 prep days + the 2-day event itself.

**Status right now:** the P0 backend skeleton, the Attack-Path & Intent Engine,
real-attack-aware decoy logging (classifies nmap/hydra traffic instead of
showing binary noise), Docker isolation for all three decoys, and the
fake_admin_panel stretch decoy are **all built and tested**. You're
effectively past Day 11 territory already. Use the runway below for
integration testing and pitch polish, not more building.

## Day-by-day

| Date | Day | Focus | Deliverable |
|---|---|---|---|
| Sun 16 Aug | 1 | Read through the scaffold, run it locally, tweak risk weights / scenarios to match how you want to pitch it. Freeze the incident schema (already frozen in `db.py` — just review it). | Backend running locally, scenario outputs make sense to you |
| Done | 2–4 | ~~Attack-Path & Intent Engine~~ — built. Predicts likely next target from behavior sequence; wired into `/incidents/{id}/predicted_path`, the dashboard, and the explainable summary. | — |
| Done | 5–6 | ~~Docker isolation~~ — built. `docker-compose.yml` isolates both decoys on an `internal: true` network (no outbound internet access) while staying reachable from the host for the live demo. | — |
| Done | 7–8 | ~~Real-attack-aware decoy logging~~ — built. `decoys/common.py` classifies real nmap/hydra/netcat traffic into `CLIENT_BANNER` / `PROBE_ONLY` / `BRUTEFORCE_PATTERN_DETECTED`, color-coded in the dashboard. | — |
| Done | — | ~~fake_admin_panel.py decoy~~ — built. Real HTTP login-console decoy; `deception.py` now routes `PRIV-ESC`/`ADMIN-ACTION` behavior here to match the Attack-Path engine's predicted next target. Wired into `docker-compose.yml`. | — |
| **Next: Sun 16 – Mon 17 Aug** | **9–10** | **Full integration pass.** Run each of the 4 scenarios end-to-end through the dashboard. Fire real `nmap`/`hydra`/`curl` traffic at the Dockerized decoys (including the admin panel) from WSL/Parrot and confirm the labels render correctly. Fix the "same behavior, different IOC" pair so it visibly returns a HIGH-confidence match on the second run. | All 4 scenarios demo cleanly, real-attack evidence renders correctly, memory match works as the centerpiece |
| Tue 18 – Wed 19 Aug | 11 | Write the Explainable AI Defender summaries to read well out loud. Optional: swap in a real LLM call for the summary text, grounded strictly in retrieved evidence fields — skip if it adds risk this close to the deadline. | Summaries sound good live |
| Thu 20 – Sun 23 Aug | 12 | Full run-through ×5 with `reset_demo.sh` between each. Time the 90-second demo script (below). Take dashboard screenshots for the deck/README. Fix anything that broke under repetition. | Demo is boring-reliable — no surprises |
| Mon 24 – Thu 27 Aug | 13 | Pitch deck, README polish, architecture diagram export, rehearsal, record a backup demo video in case live networking fails at the venue. Extra banked days for final fixes. | Everything submission-ready, several days early |
| 28th–29th Aug | Event | Present, demo, pitch. | 🏆 |

**Checkpoint:** everything on the P0/P1 build list — including the
admin-panel decoy — is done. From here it's testing and polish; don't add
new scope this close to the deadline.

## 90-second demo script

1. Reset memory (`reset_demo.sh`), show empty incident list
2. Run `recon_to_db_hunt` scenario — walk through the timeline as it builds
3. Point out: no prior match -> LOW confidence -> `fake_db` decoy selected (behavior included DB-SEARCH)
4. Switch to your WSL/Parrot terminal and hit the live decoy with real tools instead of typed text — this is the moment that makes it a real demo, not a script:
   - `nmap -sV -p 2222 127.0.0.1` — shows up in Evidence as `PROBE_ONLY` (nmap grabs the banner and disconnects without sending data)
   - `hydra -l admin -P /usr/share/wordlists/rockyou.txt -s 2222 127.0.0.1 ssh` for a few seconds, then Ctrl+C — shows up as a `CLIENT_BANNER` line per attempt, then a `BRUTEFORCE_PATTERN_DETECTED` line once 5 connections land within 30s (color-coded red in the dashboard)
   - Point at the dashboard updating live as these run — real traffic, not canned events
   - Click **"Fold Decoy Evidence Into Risk Score"** — this is the payoff moment: watch the risk score jump and the predicted next target update, driven by what the real tools actually did, not the scripted scenario
5. Run `recon_to_db_hunt_variant_ip` (same behavior, different source IP)
6. Point out: this time the memory match against incident #1 is HIGH confidence — same sequence, different IOC — explain why that's the interesting part, not the raw IP
7. Read the Explainable AI Defender summary out loud (now also states the predicted next target from the Attack-Path engine)
8. Close on the one-liner: *"MIRAGE-X doesn't just detect attackers — it understands their behavior, predicts their path, dynamically changes the environment they see, and turns their actions into defensive intelligence."*

**Bonus (if judges want more / Q&A time allows):** run `curl -d "username=admin&password=test" http://127.0.0.1:8080/login` against the admin panel decoy to show the third decoy type live, and point out that `deception.py` chose it specifically because the behavior sequence matched the Attack-Path engine's predicted next target — the system showed the attacker the fake resource that fit where it predicted they were headed. If time allows, run `data_exfiltration` to show the CRITICAL SOC-paging alert and download its PDF incident report — MITRE ATT&CK technique tags included. Then open Settings (⚙), paste an Anthropic API key, and point at the AI Advisor panel flipping from `RULE-BASED` to `LIVE AI` — ask it a question live ("should this page someone?") to show it answers from the same grounded facts, not a fresh guess. Point at the attack-path diagram lighting up the predicted next node, and the risk sparkline showing the score climb step-by-step as each event landed. Run a second scenario that routes to the same decoy, then use "Cross-Incident Correlation" to ask "are any of these related?" — showing the AI reasoning across incidents, not just within one. Open the 🔔 Alerts button to show the simulated `#soc-alerts` channel picking up the CRITICAL page. Tick two incidents in the list and hit Compare for the side-by-side diff, and use the replay slider above the timeline to step through an incident's events one at a time while narrating.

## Pitch deck outline

Hook → Problem (alert fatigue, no memory across incidents) → Solution (one-liner
+ closed-loop diagram from `docs/MIRAGE-X_Original_Concept.pdf` §2) → Live demo
→ What's different (confidence-driven integration, not "5 projects glued together")
→ Architecture → Roadmap / final-year research question (§10 of the concept doc)
→ Close on tagline.

## Safety reminders (keep saying this to judges)

Isolated lab only, no real credentials anywhere, decoys have no uncontrolled
external access, the LLM advisor is grounded in retrieved evidence only (it
explains and recommends, it never re-decides risk score, decoy, or
severity, and falls back to a rule-based advisory with no network call if
no API key is set), the simulated SOC alert channel never makes a real
network call or posts to an actual Slack workspace — it's a labeled
simulation, not a fake integration — response actions stay recommendations
— never live automation against real infrastructure.
