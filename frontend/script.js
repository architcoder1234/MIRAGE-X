const API = "http://localhost:8000";
let selectedIncident = null;
let askBusy = false;
let allIncidents = [];

// ---------- settings (persisted in this browser only) ----------

const DEFAULT_SETTINGS = {
  beginnerMode: false,
  apiKey: "",
  theme: "dark",
  accentColor: "#4fd1c5",
  panels: { evidence: true, path: true, mitre: true, advisor: true },
};

function loadSettings() {
  try {
    const raw = localStorage.getItem("mirageXSettings");
    if (!raw) return structuredClone(DEFAULT_SETTINGS);
    const parsed = JSON.parse(raw);
    return { ...structuredClone(DEFAULT_SETTINGS), ...parsed, panels: { ...DEFAULT_SETTINGS.panels, ...(parsed.panels || {}) } };
  } catch (e) {
    return structuredClone(DEFAULT_SETTINGS);
  }
}

function persistSettings(settings) {
  localStorage.setItem("mirageXSettings", JSON.stringify(settings));
}

function applySettingsToForm(settings) {
  document.getElementById("beginnerModeToggle").checked = settings.beginnerMode;
  document.getElementById("apiKeyInput").value = settings.apiKey || "";
  document.getElementById("accentInput").value = settings.accentColor || DEFAULT_SETTINGS.accentColor;
  document.querySelectorAll('input[name="theme"]').forEach(r => { r.checked = (r.value === settings.theme); });
  document.getElementById("panel_evidence").checked = settings.panels.evidence;
  document.getElementById("panel_path").checked = settings.panels.path;
  document.getElementById("panel_mitre").checked = settings.panels.mitre;
  document.getElementById("panel_advisor").checked = settings.panels.advisor;
}

function applySettingsToPage(settings) {
  document.body.classList.toggle("beginner-mode", settings.beginnerMode);
  document.body.classList.toggle("light-theme", settings.theme === "light");
  document.documentElement.style.setProperty("--accent", settings.accentColor || DEFAULT_SETTINGS.accentColor);

  document.getElementById("evidenceSection").style.display = settings.panels.evidence ? "" : "none";
  document.getElementById("pathSection").style.display = settings.panels.path ? "" : "none";
  document.getElementById("mitreSection").style.display = settings.panels.mitre ? "" : "none";
  document.getElementById("advisorSection").style.display = settings.panels.advisor ? "" : "none";

  const keyStatus = document.getElementById("keyStatus");
  keyStatus.textContent = settings.apiKey
    ? "Key saved in this browser — the AI Advisor will use live responses."
    : "No key saved — AI Advisor will use the rule-based fallback advisory.";
}

function saveSettings() {
  const themeInput = document.querySelector('input[name="theme"]:checked');
  const settings = {
    beginnerMode: document.getElementById("beginnerModeToggle").checked,
    apiKey: document.getElementById("apiKeyInput").value.trim(),
    theme: themeInput ? themeInput.value : DEFAULT_SETTINGS.theme,
    accentColor: document.getElementById("accentInput").value,
    panels: {
      evidence: document.getElementById("panel_evidence").checked,
      path: document.getElementById("panel_path").checked,
      mitre: document.getElementById("panel_mitre").checked,
      advisor: document.getElementById("panel_advisor").checked,
    },
  };
  persistSettings(settings);
  applySettingsToPage(settings);
  checkLlmStatus();
}

function resetSettings() {
  persistSettings(DEFAULT_SETTINGS);
  applySettingsToForm(DEFAULT_SETTINGS);
  applySettingsToPage(DEFAULT_SETTINGS);
  checkLlmStatus();
}

function authHeaders() {
  const settings = loadSettings();
  return settings.apiKey ? { "X-Anthropic-Key": settings.apiKey } : {};
}

// ---------- modal helpers (shared focus management + Escape-to-close) ----------
// Every modal in the app opens/closes through these two functions so keyboard
// and screen-reader behavior stays consistent: focus moves into the modal on
// open, Escape closes whichever modal is open, and focus returns to whatever
// triggered it on close.

let activeModalId = null;
let lastFocusedElement = null;

function openModal(id) {
  lastFocusedElement = document.activeElement;
  activeModalId = id;
  const overlay = document.getElementById(id);
  overlay.classList.add("open");
  const focusable = overlay.querySelector('input, button, select, [tabindex]');
  if (focusable) focusable.focus();
}

function closeModal(id) {
  document.getElementById(id).classList.remove("open");
  if (activeModalId === id) activeModalId = null;
  if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
    lastFocusedElement.focus();
  }
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && activeModalId) {
    closeModal(activeModalId);
  }
});

function openSettings() {
  applySettingsToForm(loadSettings());
  openModal("settingsOverlay");
}
function closeSettings() { closeModal("settingsOverlay"); }

// ---------- toast notifications ----------

function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => { toast.classList.add("toast-out"); }, 4200);
  setTimeout(() => { toast.remove(); }, 4700);
}

// ---------- risk banding ----------

// Risk score (0-100) -> band. Separate from "confidence", which measures
// how well this incident matches something already in memory — the two
// are NOT the same thing, so they get their own badges below.
function riskBand(score) {
  if (score >= 70) return 'HIGH';
  if (score >= 45) return 'MEDIUM';
  return 'LOW';
}

// ---------- status checks ----------

async function checkApi() {
  try {
    await fetch(`${API}/scenarios`);
    document.getElementById('apiStatus').textContent = "connected";
    document.getElementById('apiStatus').style.color = "#4fd17e";
  } catch (e) {
    document.getElementById('apiStatus').textContent = "offline (start uvicorn)";
    document.getElementById('apiStatus').style.color = "#ff5c5c";
  }
}

async function checkLlmStatus() {
  const el = document.getElementById('llmStatus');
  try {
    const res = await fetch(`${API}/settings/llm_status`, { headers: authHeaders() });
    const data = await res.json();
    if (data.llm_available) {
      el.textContent = "connected";
      el.style.color = "#4fd17e";
    } else {
      el.textContent = "rule-based (no key)";
      el.style.color = "#ffb454";
    }
  } catch (e) {
    el.textContent = "unknown";
    el.style.color = "var(--muted)";
  }
}

// ---------- scenario / incident actions ----------

async function loadScenarios() {
  const res = await fetch(`${API}/scenarios`);
  const data = await res.json();
  const sel = document.getElementById('scenarioSelect');
  sel.innerHTML = data.scenarios.map(s => `<option value="${s}">${s}</option>`).join('');
}

async function runScenario() {
  const scenario = document.getElementById('scenarioSelect').value;
  const res = await fetch(`${API}/simulate`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({scenario})
  });
  const incident = await res.json();
  await loadIncidents();
  selectIncident(incident.incident_id);
  showToast(`New incident ${incident.incident_id} created (risk ${incident.risk_score}/100).`, "info");
}

async function resetDemo() {
  await fetch(`${API}/reset`, {method: 'POST'});
  selectedIncident = null;
  compareSelection.clear();
  updateCompareUI();
  await loadIncidents();
  renderEmpty();
}

async function foldEvidence() {
  if (!selectedIncident) return;
  const res = await fetch(`${API}/incidents/${selectedIncident}/recompute`, {method: 'POST'});
  const data = await res.json();
  if (data.decoy_events_folded && data.decoy_events_folded.length) {
    showToast(`Folded ${data.decoy_events_folded.length} decoy event(s) into the risk score.`, "success");
  } else {
    showToast("No new decoy evidence to fold in yet.", "info");
  }
  await selectIncident(selectedIncident);
}

// ---------- incident list: search, filter, compare selection ----------

let compareSelection = new Set();

function populateDecoyFilterOptions(incidents) {
  const select = document.getElementById('decoyFilter');
  const current = select.value;
  const decoys = [...new Set(incidents.map(i => i.decoy_deployed).filter(Boolean))].sort();
  select.innerHTML = '<option value="">Any decoy</option><option value="__none__">No decoy</option>' +
    decoys.map(d => `<option value="${d}">${d}</option>`).join('');
  if ([...select.options].some(o => o.value === current)) select.value = current;
}

async function loadIncidents() {
  const res = await fetch(`${API}/incidents`);
  allIncidents = await res.json();
  populateDecoyFilterOptions(allIncidents);
  renderIncidentList();
}

function renderIncidentList() {
  const list = document.getElementById('incidentList');
  if (!allIncidents.length) {
    list.innerHTML = '<div class="empty">No incidents yet — run a scenario.</div>';
    return;
  }

  const query = (document.getElementById('incidentSearch').value || '').trim().toLowerCase();
  const severityFilter = document.getElementById('severityFilter').value;
  const decoyFilter = document.getElementById('decoyFilter').value;

  const filtered = allIncidents.filter(i => {
    if (query) {
      const haystack = (i.incident_id + ' ' + i.behavior_sequence.join(' ')).toLowerCase();
      if (!haystack.includes(query)) return false;
    }
    if (severityFilter && riskBand(i.risk_score) !== severityFilter) return false;
    if (decoyFilter === '__none__' && i.decoy_deployed) return false;
    if (decoyFilter && decoyFilter !== '__none__' && i.decoy_deployed !== decoyFilter) return false;
    return true;
  });

  if (!filtered.length) {
    list.innerHTML = '<div class="empty">No incidents match your search/filters.</div>';
    return;
  }

  list.innerHTML = filtered.map(i => `
    <div class="incident-item ${selectedIncident === i.incident_id ? 'selected' : ''}">
      <input type="checkbox" class="compare-check" aria-label="Select ${i.incident_id} for comparison"
        onclick="event.stopPropagation(); toggleCompareSelect('${i.incident_id}', this.checked)"
        ${compareSelection.has(i.incident_id) ? 'checked' : ''} />
      <div class="incident-click-area" onclick="selectIncident('${i.incident_id}')" tabindex="0"
        role="button" aria-label="View incident ${i.incident_id}"
        onkeydown="if(event.key==='Enter') selectIncident('${i.incident_id}')">
        <strong>${i.incident_id}</strong> <span class="badge badge-${riskBand(i.risk_score)}">${riskBand(i.risk_score)}</span>
        <div style="color:var(--muted); font-size:11px; margin-top:2px;">${i.behavior_sequence.join(' → ')}</div>
      </div>
    </div>
  `).join('');
}

function toggleCompareSelect(id, checked) {
  if (checked) {
    if (compareSelection.size >= 2) {
      showToast("You can only compare 2 incidents at a time — uncheck one first.", "warn");
      renderIncidentList();
      return;
    }
    compareSelection.add(id);
  } else {
    compareSelection.delete(id);
  }
  updateCompareUI();
}

function updateCompareUI() {
  document.getElementById('compareCount').textContent = `${compareSelection.size} selected for comparison`;
  document.getElementById('compareBtn').disabled = compareSelection.size !== 2;
}

// ---------- side-by-side incident comparison ----------

async function openCompare() {
  if (compareSelection.size !== 2) return;
  const [idA, idB] = [...compareSelection];
  const body = document.getElementById('compareBody');
  body.innerHTML = '<div class="empty">Loading…</div>';
  openModal('compareOverlay');

  try {
    const [resA, resB] = await Promise.all([
      fetch(`${API}/incidents/${idA}`), fetch(`${API}/incidents/${idB}`),
    ]);
    const [a, b] = await Promise.all([resA.json(), resB.json()]);
    renderCompare(a, b);
  } catch (e) {
    body.innerHTML = '<div class="empty">Could not load both incidents.</div>';
  }
}

function closeCompare() { closeModal('compareOverlay'); }

function renderCompare(a, b) {
  const rows = [
    ['Risk score', `${a.risk_score}/100 (${riskBand(a.risk_score)})`, `${b.risk_score}/100 (${riskBand(b.risk_score)})`],
    ['Memory confidence', a.confidence, b.confidence],
    ['Behavior sequence', a.behavior_sequence.join(' → ') || '—', b.behavior_sequence.join(' → ') || '—'],
    ['Decoy deployed', a.decoy_deployed || 'None', b.decoy_deployed || 'None'],
    ['SOC severity', a.soc_alert ? a.soc_alert.severity : '—', b.soc_alert ? b.soc_alert.severity : '—'],
    ['Predicted next target', a.predicted_path?.predicted_next_label || '—', b.predicted_path?.predicted_next_label || '—'],
    ['MITRE techniques', (a.mitre_techniques || []).map(t => t.technique_id).join(', ') || '—',
                          (b.mitre_techniques || []).map(t => t.technique_id).join(', ') || '—'],
  ];

  const sharedDecoy = a.decoy_deployed && a.decoy_deployed === b.decoy_deployed;
  const sharedTechniques = (a.mitre_techniques || []).filter(t =>
    (b.mitre_techniques || []).some(bt => bt.technique_id === t.technique_id));

  document.getElementById('compareBody').innerHTML = `
    <table class="compare-table">
      <thead><tr><th>Field</th><th>${a.incident_id}</th><th>${b.incident_id}</th></tr></thead>
      <tbody>
        ${rows.map(([label, av, bv]) => `<tr><th scope="row">${label}</th><td>${av}</td><td>${bv}</td></tr>`).join('')}
      </tbody>
    </table>
    ${sharedDecoy || sharedTechniques.length ? `
      <div class="compare-note">
        ${sharedDecoy ? `⚠️ Both incidents were routed to the same decoy (${a.decoy_deployed}) — worth checking if this is one attacker returning.<br>` : ''}
        ${sharedTechniques.length ? `Shared MITRE techniques: ${sharedTechniques.map(t => t.technique_id).join(', ')}` : ''}
      </div>` : '<div class="compare-note">No obvious overlap between these two incidents.</div>'}
  `;
}

function renderEmpty() {
  document.getElementById('timeline').innerHTML = '<div class="empty">Select an incident to see its behavior sequence.</div>';
  document.getElementById('evidence').innerHTML = '<div class="empty">No decoy interactions logged.</div>';
  document.getElementById('riskBox').innerHTML = '<div class="empty">—</div>';
  document.getElementById('decoyBox').innerHTML = '<div class="empty">—</div>';
  document.getElementById('summaryBox').innerHTML = '<div class="empty">Run or select an incident to generate an explanation.</div>';
  document.getElementById('pathBox').innerHTML = '<div class="empty">Select an incident to see predicted next target.</div>';
  document.getElementById('mitreBox').innerHTML = '<div class="empty">—</div>';
  document.getElementById('socBanner').innerHTML = '';
  document.getElementById('advisorBox').innerHTML = '<div class="empty">Select an incident to get an AI-generated summary.</div>';
  document.getElementById('advisorModeBadge').innerHTML = '';
  document.getElementById('askHistory').innerHTML = '';
  document.getElementById('pathDiagram').innerHTML = '';
  document.getElementById('riskTrend').innerHTML = '';
  document.getElementById('replayControls').hidden = true;
  stopReplay();
}

async function downloadReport() {
  if (!selectedIncident) return;
  window.open(`${API}/incidents/${selectedIncident}/report`, '_blank');
}

// ---------- network graph / attack-path diagram ----------

let networkGraph = null;

// Fixed hand-placed layout for the small demo graph (matches node ids in
// backend/attack_path.py's NODES dict). A real deployment would compute
// this, but the graph is small and static enough that a fixed layout
// reads more clearly than an auto-layout would for a live demo.
const GRAPH_LAYOUT = {
  "internet":      { x: 60,  y: 190 },
  "host-03":       { x: 230, y: 190 },
  "host-07":       { x: 420, y: 70  },
  "db-server":     { x: 420, y: 160 },
  "admin-panel":   { x: 420, y: 250 },
  "file-share":    { x: 420, y: 330 },
  "exfil-gateway": { x: 610, y: 330 },
};

async function loadNetworkGraph() {
  try {
    const res = await fetch(`${API}/network`);
    networkGraph = await res.json();
  } catch (e) {
    networkGraph = null;
  }
}

function renderPathDiagram(path) {
  const el = document.getElementById('pathDiagram');
  if (!networkGraph || !path) { el.innerHTML = ''; return; }

  const current = path.current_position;
  const target = path.predicted_next_target;

  const edgesSvg = networkGraph.edges.map(([from, to]) => {
    const a = GRAPH_LAYOUT[from], b = GRAPH_LAYOUT[to];
    if (!a || !b) return '';
    const isActivePath = (from === current && to === target);
    return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"
      class="graph-edge ${isActivePath ? 'active' : ''}" />`;
  }).join('');

  const nodesSvg = Object.entries(networkGraph.nodes).map(([id, node]) => {
    const pos = GRAPH_LAYOUT[id];
    if (!pos) return '';
    let cls = 'graph-node';
    if (id === current) cls += ' current';
    else if (id === target) cls += ' target';
    return `
      <g class="${cls}">
        <circle cx="${pos.x}" cy="${pos.y}" r="16" />
        <text x="${pos.x}" y="${pos.y + 32}" text-anchor="middle" class="graph-label">${node.label}</text>
      </g>`;
  }).join('');

  el.innerHTML = `
    <svg viewBox="0 0 680 380" class="graph-svg" role="img" aria-label="Simulated network graph showing predicted attack path">
      <g class="graph-edges">${edgesSvg}</g>
      <g class="graph-nodes">${nodesSvg}</g>
    </svg>`;
}

// ---------- risk trend sparkline ----------

async function loadRiskTrend(id) {
  const el = document.getElementById('riskTrend');
  try {
    const res = await fetch(`${API}/incidents/${id}/risk_trend`);
    const data = await res.json();
    renderRiskTrend(data.trend || []);
  } catch (e) {
    el.innerHTML = '';
  }
}

function renderRiskTrend(trend) {
  const el = document.getElementById('riskTrend');
  if (!trend.length) { el.innerHTML = ''; return; }

  const w = 280, h = 56, pad = 6;
  const stepX = trend.length > 1 ? (w - pad * 2) / (trend.length - 1) : 0;
  const points = trend.map((t, i) => {
    const x = pad + i * stepX;
    const y = h - pad - (t.risk_score / 100) * (h - pad * 2);
    return `${x},${y}`;
  }).join(' ');

  const dots = trend.map((t, i) => {
    const x = pad + i * stepX;
    const y = h - pad - (t.risk_score / 100) * (h - pad * 2);
    return `<circle cx="${x}" cy="${y}" r="2.5" class="trend-dot"><title>${t.event_type}: ${t.risk_score}/100</title></circle>`;
  }).join('');

  el.innerHTML = `
    <div class="setting-desc" style="margin-bottom:4px;">Risk score as events arrived, step by step:</div>
    <svg viewBox="0 0 ${w} ${h}" class="trend-svg" role="img" aria-label="Risk score trend over time">
      <polyline points="${points}" class="trend-line" />
      ${dots}
    </svg>`;
}

// ---------- attack replay / timeline scrubber ----------

let replayEvents = [];
let replayIndex = 0;
let replayTimer = null;

function renderTimelineUpTo(events, uptoIndex) {
  document.getElementById('timeline').innerHTML = events.map((e, i) => `
    <div class="timeline-step ${i > uptoIndex ? 'future' : ''} ${i === uptoIndex ? 'current' : ''}"><div class="dot"></div>
      <div><strong>${e.event_type}</strong><br><span style="color:var(--muted)">${e.detail || ''}</span></div>
    </div>
  `).join('') || '<div class="empty">No events.</div>';
}

function setupReplay(events) {
  replayEvents = events;
  stopReplay();
  const controls = document.getElementById('replayControls');
  if (!events.length) { controls.hidden = true; return; }
  controls.hidden = false;
  const slider = document.getElementById('replaySlider');
  slider.max = events.length - 1;
  slider.value = events.length - 1;
  replayIndex = events.length - 1;
  updateReplayLabel();
  renderTimelineUpTo(events, replayIndex);
}

function updateReplayLabel() {
  document.getElementById('replayStepLabel').textContent = `${replayIndex + 1} / ${replayEvents.length}`;
}

function scrubReplay(value) {
  replayIndex = parseInt(value, 10);
  updateReplayLabel();
  renderTimelineUpTo(replayEvents, replayIndex);
}

function toggleReplay() {
  const btn = document.getElementById('replayPlayBtn');
  if (replayTimer) {
    stopReplay();
    btn.textContent = '▶ Replay';
    return;
  }
  if (replayIndex >= replayEvents.length - 1) {
    replayIndex = -1; // restart from the beginning
  }
  btn.textContent = '⏸ Pause';
  replayTimer = setInterval(() => {
    replayIndex++;
    if (replayIndex >= replayEvents.length) {
      stopReplay();
      btn.textContent = '▶ Replay';
      return;
    }
    document.getElementById('replaySlider').value = replayIndex;
    updateReplayLabel();
    renderTimelineUpTo(replayEvents, replayIndex);
  }, 900);
}

function stopReplay() {
  if (replayTimer) { clearInterval(replayTimer); replayTimer = null; }
}

// ---------- simulated SOC alert channel ----------

let lastSeenAlertId = parseInt(localStorage.getItem('mirageXLastSeenAlertId') || '0', 10);

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function formatAlertHtml(message) {
  // Alert messages use a tiny markdown-lite (*bold*) from alert_channel.py —
  // escape first, then apply formatting, so nothing in the message can
  // inject HTML.
  return escapeHtml(message)
    .replace(/\*(.+?)\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');
}

async function loadAlerts() {
  const list = document.getElementById('alertsList');
  try {
    const res = await fetch(`${API}/alerts`);
    const alerts = await res.json();
    if (!alerts.length) {
      list.innerHTML = '<div class="empty">No alerts yet — an incident needs to cross the paging threshold first.</div>';
      return;
    }
    list.innerHTML = alerts.map(a => `
      <div class="alert-bubble severity-${a.severity}">
        <div class="alert-bubble-head"><strong>${a.channel}</strong> <span class="setting-desc">${new Date(a.ts).toLocaleTimeString()}</span></div>
        <div class="alert-bubble-body">${formatAlertHtml(a.message)}</div>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = '<div class="empty">Could not load the alert channel right now.</div>';
  }
}

function openAlerts() {
  loadAlerts();
  openModal('alertsOverlay');
  markAlertsSeen();
}
function closeAlerts() { closeModal('alertsOverlay'); }

function markAlertsSeen() {
  document.getElementById('alertsBadge').hidden = true;
}

async function pollAlerts() {
  try {
    const res = await fetch(`${API}/alerts`);
    const alerts = await res.json();
    if (!alerts.length) return;
    const newest = alerts[0];
    if (newest.id > lastSeenAlertId) {
      const unseenCount = alerts.filter(a => a.id > lastSeenAlertId).length;
      const badge = document.getElementById('alertsBadge');
      badge.textContent = unseenCount;
      badge.hidden = false;
      if (lastSeenAlertId > 0) {
        // Don't toast on the very first poll after page load (that would
        // re-announce every alert already logged from a prior session).
        showToast(`🔔 New ${newest.severity} alert on ${newest.incident_id}`, "warn");
      }
      lastSeenAlertId = newest.id;
      localStorage.setItem('mirageXLastSeenAlertId', String(lastSeenAlertId));
    }
  } catch (e) {
    // silent — alert polling is best-effort
  }
}

function renderAdvisor(data) {
  const badge = document.getElementById('advisorModeBadge');
  if (data.mode === 'llm') {
    badge.textContent = 'LIVE AI';
    badge.className = 'mode-badge live';
  } else {
    badge.textContent = 'RULE-BASED';
    badge.className = 'mode-badge fallback';
  }

  const actions = (data.recommended_actions || []).map(a => `<li>${a}</li>`).join('');
  document.getElementById('advisorBox').innerHTML = `
    <div class="advisor-summary">${data.plain_summary || ''}</div>
    ${actions ? `<ul class="advisor-actions">${actions}</ul>` : ''}
    ${data.analyst_note ? `<div class="advisor-note"><strong>Analyst note:</strong> ${data.analyst_note}</div>` : ''}
    ${data.error ? `<div class="advisor-note muted">${data.error}</div>` : ''}
  `;
}

async function loadAdvisor(id) {
  document.getElementById('advisorBox').innerHTML = '<div class="empty">Thinking…</div>';
  try {
    const res = await fetch(`${API}/incidents/${id}/advisory`, { headers: authHeaders() });
    const data = await res.json();
    renderAdvisor(data);
  } catch (e) {
    document.getElementById('advisorBox').innerHTML = '<div class="empty">Could not load the AI advisor right now.</div>';
  }
}

async function askAdvisor() {
  if (!selectedIncident || askBusy) return;
  const input = document.getElementById('askInput');
  const question = input.value.trim();
  if (!question) return;
  input.value = '';
  askBusy = true;

  const history = document.getElementById('askHistory');
  const qId = `q-${Date.now()}`;
  history.insertAdjacentHTML('afterbegin', `
    <div class="ask-item">
      <div class="ask-q">${question}</div>
      <div class="ask-a" id="${qId}">Thinking…</div>
    </div>
  `);

  try {
    const res = await fetch(`${API}/incidents/${selectedIncident}/ask`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    document.getElementById(qId).textContent = data.answer || 'No answer returned.';
  } catch (e) {
    document.getElementById(qId).textContent = 'Could not reach the AI advisor right now.';
  } finally {
    askBusy = false;
  }
}

let correlateBusy = false;

async function runCorrelation() {
  if (correlateBusy) return;
  correlateBusy = true;
  const question = document.getElementById('correlateInput').value.trim();
  const box = document.getElementById('correlationBox');
  box.innerHTML = '<div class="empty">Analyzing all incidents in memory…</div>';

  try {
    const res = await fetch(`${API}/advisor/correlate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ question: question || null }),
    });
    const data = await res.json();
    const badge = data.mode === 'llm'
      ? '<span class="mode-badge live">LIVE AI</span>'
      : '<span class="mode-badge fallback">RULE-BASED</span>';
    box.innerHTML = `<div class="advisor-summary">${badge} ${data.answer || 'No answer returned.'}</div>`;
  } catch (e) {
    box.innerHTML = '<div class="empty">Could not reach the AI advisor right now.</div>';
  } finally {
    correlateBusy = false;
  }
}

// ---------- incident selection ----------
// selectIncident() is the full load (fires on click, resets the AI Advisor
// panel and Q&A history, and asks the advisor for a fresh take).
// refreshSelected() is the lightweight periodic poll (every 4s) that keeps
// the timeline/evidence/risk panels live for real decoy traffic — it does
// NOT touch the AI Advisor panel or Q&A history, so it doesn't fire an LLM
// call every few seconds or wipe out an in-progress conversation.

async function selectIncident(id) {
  const previous = selectedIncident;
  selectedIncident = id;
  await renderIncident(id);
  document.getElementById('askHistory').innerHTML = '';

  const settings = loadSettings();
  if (settings.panels.advisor) {
    loadAdvisor(id);
  }
  await loadIncidents();
  if (previous !== id) renderIncidentList();
}

async function refreshSelected() {
  if (!selectedIncident) return;
  const before = document.getElementById('evidence').querySelectorAll('.evidence-line').length;
  await renderIncident(selectedIncident);
  const after = document.getElementById('evidence').querySelectorAll('.evidence-line').length;
  if (after > before) {
    showToast(`New decoy interaction logged on ${selectedIncident}.`, "info");
  }
  await loadIncidents();
}

async function renderIncident(id) {
  const res = await fetch(`${API}/incidents/${id}`);
  const inc = await res.json();

  document.getElementById('centerTitle').innerHTML = `Timeline — ${id} <span class="hint" tabindex="0" title="The exact sequence of actions the system observed, in order.">?</span>`;
  setupReplay(inc.events);

  document.getElementById('evidence').innerHTML = inc.decoy_evidence.length
    ? inc.decoy_evidence.map(ev => {
        let cls = '';
        if (ev.command.startsWith('BRUTEFORCE_PATTERN_DETECTED')) cls = 'danger';
        else if (ev.command.startsWith('PROBE_ONLY')) cls = 'warn';
        else if (ev.command.startsWith('CLIENT_BANNER')) cls = 'info';
        return `<div class="evidence-line ${cls}">[${ev.decoy}] ${ev.src_ip} → ${ev.command}</div>`;
      }).join('')
    : '<div class="empty">No decoy interactions logged.</div>';

  const path = inc.predicted_path;
  document.getElementById('pathBox').innerHTML = path && path.predicted_next_target
    ? `<div class="path-chain">
         <div class="path-node">${path.current_position}</div>
         <div class="path-arrow">→</div>
         <div class="path-node target">${path.predicted_next_label}</div>
       </div>
       <div class="path-reason">${path.reason} (triggered by ${path.triggering_event})</div>`
    : `<div class="empty">${path ? path.reason : 'No prediction yet.'}</div>`;
  renderPathDiagram(path);

  // Risk (how dangerous the behavior looks) and Confidence (how well it
  // matches something already in memory) are two different signals —
  // shown as two separate badges so they can't be mistaken for each other.
  const rBand = riskBand(inc.risk_score);
  document.getElementById('riskBox').innerHTML = `
    <div class="badge-row">
      <span class="badge badge-${rBand}">Risk: ${rBand}</span>
      <span class="badge badge-${inc.confidence}">Memory Confidence: ${inc.confidence}</span>
    </div>
    <div style="margin-top:8px;">Risk score: <strong>${inc.risk_score}</strong>/100</div>
    <div class="risk-bar-bg"><div class="risk-bar-fill" style="width:${inc.risk_score}%"></div></div>
    ${inc.similarity_top_match ? `<div style="margin-top:10px; font-size:12px; color:var(--muted);">
      Closest match: ${inc.similarity_top_match.incident_id} (score ${inc.similarity_top_match.score})<br>
      Matched on: ${inc.similarity_top_match.matched_features.join(', ') || 'none'}
    </div>` : ''}
  `;
  loadRiskTrend(id);

  document.getElementById('decoyBox').innerHTML = inc.decoy_deployed
    ? `<div class="decoy-tag">🎭 ${inc.decoy_deployed} deployed</div>`
    : `<div class="decoy-tag" style="background:#132018; color:var(--low);">No decoy needed</div>`;

  const mitre = inc.mitre_techniques || [];
  document.getElementById('mitreBox').innerHTML = mitre.length
    ? mitre.map(t => `<span class="mitre-tag" title="${t.tactic}">${t.technique_id} — ${t.technique_name}</span>`).join('')
    : '<div class="empty">No mapped techniques yet.</div>';

  const alert = inc.soc_alert;
  if (alert) {
    document.getElementById('socBanner').innerHTML = `
      <div class="soc-banner ${alert.would_page ? 'page' : 'noage'}">
        ${alert.would_page ? '🚨' : 'ℹ️'} SOC Severity: <strong>${alert.severity}</strong>
        ${alert.would_page ? '— would page an analyst' : '— no page, queued for review'}
      </div>`;
  } else {
    document.getElementById('socBanner').innerHTML = '';
  }

  document.getElementById('summaryBox').innerHTML = inc.summary || '<div class="empty">No summary yet.</div>';
}

// ---------- onboarding walkthrough ----------

const ONBOARD_SLIDES = [
  {
    title: "Run a simulated attack",
    body: "Pick a scenario from the dropdown on the left and click <strong>Launch Simulated Attack</strong>. MIRAGE-X will fingerprint the behavior, score its risk, and decide whether to deploy a decoy — all in real time.",
  },
  {
    title: "Search, filter, and compare",
    body: "As incidents pile up, use the search box and risk/decoy filters to find what you're after. Tick two incidents and hit <strong>Compare</strong> to see them side by side.",
  },
  {
    title: "Replay the timeline",
    body: "Once an incident is selected, use the replay controls above the timeline to step through — or auto-play — exactly what the attacker did, in order.",
  },
  {
    title: "The AI Advisor",
    body: "On the right, the AI Advisor turns the risk score, decoy decision, and MITRE mapping into a plain-English summary and next steps — and you can ask it questions, either about one incident or across all of them.",
  },
  {
    title: "Simulated alerts & settings",
    body: "The 🔔 Alerts button shows a simulated SOC channel for anything that would page an analyst. The ⚙ Settings panel lets you enable Beginner Mode, change the theme, and customize which panels are visible.",
  },
];
let onboardIndex = 0;

function renderOnboardSlide() {
  const slide = ONBOARD_SLIDES[onboardIndex];
  document.getElementById('onboardBody').innerHTML = `<h3>${slide.title}</h3><p>${slide.body}</p>`;
  document.getElementById('onboardDots').innerHTML = ONBOARD_SLIDES.map((_, i) =>
    `<span class="onboard-dot ${i === onboardIndex ? 'active' : ''}"></span>`).join('');
  document.getElementById('onboardPrevBtn').disabled = onboardIndex === 0;
  document.getElementById('onboardNextBtn').textContent = onboardIndex === ONBOARD_SLIDES.length - 1 ? 'Done' : 'Next';
}

function startOnboarding() {
  onboardIndex = 0;
  renderOnboardSlide();
  openModal('onboardOverlay');
}

function onboardNext() {
  if (onboardIndex < ONBOARD_SLIDES.length - 1) {
    onboardIndex++;
    renderOnboardSlide();
  } else {
    closeOnboarding();
  }
}

function onboardPrev() {
  if (onboardIndex > 0) {
    onboardIndex--;
    renderOnboardSlide();
  }
}

function closeOnboarding() {
  closeModal('onboardOverlay');
  localStorage.setItem('mirageXOnboarded', '1');
}

// ---------- init ----------

const initialSettings = loadSettings();
applySettingsToForm(initialSettings);
applySettingsToPage(initialSettings);
updateCompareUI();

checkApi();
checkLlmStatus();
loadScenarios();
loadNetworkGraph();
loadIncidents();
pollAlerts();

if (!localStorage.getItem('mirageXOnboarded')) {
  setTimeout(startOnboarding, 400);
}

setInterval(refreshSelected, 4000);
setInterval(checkApi, 5000);
setInterval(pollAlerts, 6000);
