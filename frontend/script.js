const API = (() => {
  const query = new URLSearchParams(window.location.search).get("api");
  const valid = value => {
    try {
      const url = new URL(value);
      return url.protocol === "https:" ||
        (url.protocol === "http:" && ["localhost", "127.0.0.1"].includes(url.hostname));
    } catch (e) {
      return false;
    }
  };
  if (query && valid(query)) {
    localStorage.setItem("mirageXApiBase", query.replace(/\/+$/, ""));
  }
  const stored = localStorage.getItem("mirageXApiBase");
  return ((query && valid(query) ? query : (stored && valid(stored) ? stored : "https://mirage-x.onrender.com")).replace(/\/+$/, ""));
})();
let selectedIncident = null;
let askBusy = false;
let allIncidents = [];
let eventsSource = null;
let sseFailed = false;
let demoRunning = false;

// ---------- settings (persisted in this browser only) ----------

const DEFAULT_SETTINGS = {
  beginnerMode: false,
  apiKey: "",
  resetToken: "",
  theme: "dark",
  accentColor: "#4fd1c5",
  panels: { evidence: true, path: true, mitre: true, advisor: true },
};

function loadSettings() {
  try {
    const raw = localStorage.getItem("mirageXSettings");
    if (!raw) return structuredClone(DEFAULT_SETTINGS);
    const parsed = JSON.parse(raw);
    parsed.apiKey = sessionStorage.getItem("mirageXApiKey") || "";
    parsed.resetToken = sessionStorage.getItem("mirageXResetToken") || "";
    return { ...structuredClone(DEFAULT_SETTINGS), ...parsed, panels: { ...DEFAULT_SETTINGS.panels, ...(parsed.panels || {}) } };
  } catch (e) {
    return structuredClone(DEFAULT_SETTINGS);
  }
}

function persistSettings(settings) {
  const stored = { ...settings };
  delete stored.apiKey;
  delete stored.resetToken;
  localStorage.setItem("mirageXSettings", JSON.stringify(stored));
  sessionStorage.setItem("mirageXApiKey", settings.apiKey || "");
  sessionStorage.setItem("mirageXResetToken", settings.resetToken || "");
}

function applySettingsToForm(settings) {
  document.getElementById("beginnerModeToggle").checked = settings.beginnerMode;
  document.getElementById("apiKeyInput").value = settings.apiKey || "";
  document.getElementById("resetTokenInput").value = settings.resetToken || "";
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
    resetToken: document.getElementById("resetTokenInput").value.trim(),
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
  sessionStorage.removeItem("mirageXApiKey");
  sessionStorage.removeItem("mirageXResetToken");
  persistSettings(DEFAULT_SETTINGS);
  applySettingsToForm(DEFAULT_SETTINGS);
  applySettingsToPage(DEFAULT_SETTINGS);
  checkLlmStatus();
}

function authHeaders() {
  const settings = loadSettings();
  const allowed = API === "https://mirage-x.onrender.com" ||
    ["localhost", "127.0.0.1"].includes(new URL(API).hostname);
  return settings.apiKey && allowed ? { "X-Anthropic-Key": settings.apiKey } : {};
}

function resetHeaders() {
  const token = loadSettings().resetToken;
  return token ? { "X-Mirage-Reset-Token": token } : {};
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

function openAnalytics() {
  openModal("analyticsOverlay");
  loadAnalytics();
}

function closeAnalytics() { closeModal("analyticsOverlay"); }

function analyticsBars(title, values, labelKey, valueKey) {
  const entries = Object.entries(values || {});
  if (!entries.length) return `<div class="empty">No ${title.toLowerCase()} yet.</div>`;
  const max = Math.max(...entries.map(([, value]) => Number(value) || 0), 1);
  return `<h3>${title}</h3><div class="analytics-bars">${entries.map(([label, value]) => `
    <div class="analytics-row">
      <span>${label}</span><div class="analytics-track"><div class="analytics-fill" style="width:${((value / max) * 100).toFixed(1)}%"></div></div><strong>${value}</strong>
    </div>`).join('')}</div>`;
}

async function loadAnalytics() {
  const body = document.getElementById("analyticsBody");
  body.innerHTML = '<div class="empty">Loading analytics…</div>';
  try {
    const data = await (await fetch(`${API}/analytics`)).json();
    const techniques = Object.fromEntries((data.top_mitre_techniques || []).map(t => [t.technique_id, t.count]));
    const decoys = Object.fromEntries((data.decoy_usage_yield || []).map(d => [d.decoy, d.interactions]));
    const fp = data.false_positive_control_rate || {};
    body.innerHTML = `
      <div class="analytics-summary"><strong>${data.incident_count}</strong><span>incidents in memory</span></div>
      ${analyticsBars("Risk bands", data.risk_band_distribution)}
      ${analyticsBars("SOC severity", data.soc_severity_distribution)}
      ${analyticsBars("Top MITRE techniques", techniques)}
      ${analyticsBars("Decoy interactions", decoys)}
      <div class="analytics-fp"><strong>False-positive control:</strong>
        ${fp.rate === null ? "No benign control incidents yet." : `${(fp.rate * 100).toFixed(0)}% clean (${fp.clean_benign_incidents}/${fp.eligible_benign_incidents})`}
      </div>`;
  } catch (error) {
    body.innerHTML = '<div class="empty">Could not load analytics right now.</div>';
  }
}

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

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function setDemoCaption(text) {
  const box = document.getElementById("demoCaption");
  document.getElementById("demoCaptionText").textContent = text;
  box.hidden = false;
}

function skipFullDemo() {
  demoRunning = false;
  document.getElementById("demoCaption").hidden = true;
  showToast("Full demo skipped.", "info");
}

async function runDemoScenario(scenario, narration) {
  if (!demoRunning) return;
  setDemoCaption(narration);
  const response = await fetch(`${API}/simulate`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ scenario }),
  });
  if (!response.ok) throw new Error(`Scenario failed: ${response.status}`);
  const incident = await response.json();
  await loadIncidents();
  await selectIncident(incident.incident_id);
  await sleep(1200);
}

async function runFullDemo() {
  if (demoRunning) return;
  demoRunning = true;
  try {
    setDemoCaption("1/9 Resetting the isolated demo memory.");
    const reset = await fetch(`${API}/reset`, {method: "POST", headers: resetHeaders()});
    if (!reset.ok) throw new Error(reset.status === 403
      ? "Reset denied: add the hosted reset token in Settings."
      : `Reset failed (${reset.status})`);
    await loadIncidents();
    renderEmpty();
    await sleep(700);
    await runDemoScenario("recon_to_db_hunt", "2/9 Running the recon-to-database attack chain.");
    setDemoCaption("3/9 The dashboard now shows risk, memory, MITRE, SOC severity, and the selected fake DB decoy.");
    await sleep(1800);
    setDemoCaption("4/9 Replaying the event timeline and risk escalation.");
    setupReplay(replayEvents);
    await sleep(1800);
    await runDemoScenario("recon_to_db_hunt_variant_ip", "5/9 Running the same behavior from a different source IP.");
    setDemoCaption("6/9 Behavior-first memory recognizes the returning pattern.");
    await sleep(1600);
    await runDemoScenario("data_exfiltration", "7/9 Running the critical exfiltration scenario.");
    setDemoCaption("8/9 Showing the simulated SOC page and downloadable evidence report.");
    await loadAlerts();
    await sleep(1800);
    openAnalytics();
    setDemoCaption("9/9 Analytics summarizes risk bands, techniques, decoy use, and false-positive control.");
    await sleep(2500);
    document.getElementById("demoCaption").hidden = true;
    showToast("Full demo complete.", "success");
  } catch (error) {
    showToast(`Full demo stopped: ${error.message}`, "warn");
  } finally {
    demoRunning = false;
  }
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
  const banner = document.getElementById("backendBanner");
  const delays = [0, 1000, 2500, 5000, 8000];
  for (let i = 0; i < delays.length; i += 1) {
    if (delays[i]) await new Promise(resolve => setTimeout(resolve, delays[i]));
    try {
      const response = await fetch(`${API}/health`, { signal: AbortSignal.timeout(12000) });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      document.getElementById('apiStatus').textContent = "connected";
      document.getElementById('apiStatus').style.color = "#4fd17e";
      banner.hidden = true;
      return true;
    } catch (e) {
      document.getElementById('apiStatus').textContent = i < 2 ? "waking up…" : "unreachable";
      document.getElementById('apiStatus').style.color = "#ff5c5c";
      banner.textContent = i < 2
        ? "Backend waking up… retrying automatically."
        : `Backend unreachable at ${API}. Check the service or open the dashboard with ?api=http://localhost:8000`;
      banner.hidden = false;
    }
  }
  return false;
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
  sel.innerHTML = data.scenarios.map(s => `<option value="${escapeHtml(s)}">${escapeHtml(s)}</option>`).join('');
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
  const response = await fetch(`${API}/reset`, {method: 'POST', headers: resetHeaders()});
  if (!response.ok) {
    showToast(response.status === 403
      ? "Reset denied. Add the hosted reset token in Settings."
      : `Reset failed (${response.status}).`, "warn");
    return;
  }
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

function startLiveUpdates() {
  if (!window.EventSource || eventsSource) return;
  eventsSource = new EventSource(`${API}/events/stream`);
  eventsSource.addEventListener("ready", () => { sseFailed = false; });
  ["new_incident", "incident_updated", "decoy_evidence"].forEach(type => {
    eventsSource.addEventListener(type, async (event) => {
      const data = JSON.parse(event.data || "{}");
      await loadIncidents();
      if (selectedIncident && data.incident_id === selectedIncident) {
        await renderIncident(selectedIncident);
      }
      if (type === "new_incident") showToast(`Incident ${data.incident_id} updated live.`, "info");
      if (type === "decoy_evidence") showToast("New decoy evidence received.", "success");
    });
  });
  eventsSource.addEventListener("new_soc_alert", () => {
    loadAlerts();
    showToast("New simulated SOC alert received.", "warn");
  });
  eventsSource.onerror = () => {
    if (!sseFailed) {
      sseFailed = true;
      showToast("Live updates unavailable; using periodic polling.", "warn");
    }
  };
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
      <input type="checkbox" class="compare-check" aria-label="Select ${escapeHtml(i.incident_id)} for comparison"
        data-incident-id="${escapeHtml(i.incident_id)}"
        ${compareSelection.has(i.incident_id) ? 'checked' : ''} />
      <div class="incident-click-area" data-incident-id="${escapeHtml(i.incident_id)}" tabindex="0"
        role="button" aria-label="View incident ${escapeHtml(i.incident_id)}">
        <strong>${escapeHtml(i.incident_id)}</strong> <span class="badge badge-${riskBand(i.risk_score)}">${riskBand(i.risk_score)}</span>
        <div style="color:var(--muted); font-size:11px; margin-top:2px;">${escapeHtml(i.behavior_sequence.join(' → '))}</div>
      </div>
    </div>
  `).join('');
  list.querySelectorAll('.compare-check').forEach(input => {
    input.addEventListener('click', event => {
      event.stopPropagation();
      toggleCompareSelect(input.dataset.incidentId, input.checked);
    });
  });
  list.querySelectorAll('.incident-click-area').forEach(item => {
    item.addEventListener('click', () => selectIncident(item.dataset.incidentId));
    item.addEventListener('keydown', event => {
      if (event.key === 'Enter') selectIncident(item.dataset.incidentId);
    });
  });
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
        ${rows.map(([label, av, bv]) => `<tr><th scope="row">${escapeHtml(label)}</th><td>${escapeHtml(av)}</td><td>${escapeHtml(bv)}</td></tr>`).join('')}
      </tbody>
    </table>
    ${sharedDecoy || sharedTechniques.length ? `
      <div class="compare-note">
        ${sharedDecoy ? `⚠️ Both incidents were routed to the same decoy (${escapeHtml(a.decoy_deployed)}) — worth checking if this is one attacker returning.<br>` : ''}
        ${sharedTechniques.length ? `Shared MITRE techniques: ${escapeHtml(sharedTechniques.map(t => t.technique_id).join(', '))}` : ''}
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
      <div><strong>${escapeHtml(e.event_type)}</strong><br><span style="color:var(--muted)">${escapeHtml(e.detail || '')}</span></div>
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
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
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
        <div class="alert-bubble-head"><strong>${escapeHtml(a.channel)}</strong> <span class="setting-desc">${escapeHtml(new Date(a.ts).toLocaleTimeString())}</span></div>
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

  const actions = (data.recommended_actions || []).map(a => `<li>${escapeHtml(a)}</li>`).join('');
  document.getElementById('advisorBox').innerHTML = `
    <div class="advisor-summary">${escapeHtml(data.plain_summary || '')}</div>
    ${actions ? `<ul class="advisor-actions">${actions}</ul>` : ''}
    ${data.analyst_note ? `<div class="advisor-note"><strong>Analyst note:</strong> ${escapeHtml(data.analyst_note)}</div>` : ''}
    ${data.error ? `<div class="advisor-note muted">${escapeHtml(data.error)}</div>` : ''}
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
      <div class="ask-q">${escapeHtml(question)}</div>
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
    box.innerHTML = `<div class="advisor-summary">${badge} ${escapeHtml(data.answer || 'No answer returned.')}</div>`;
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

  document.getElementById('centerTitle').innerHTML = `Timeline — ${escapeHtml(id)} <span class="hint" tabindex="0" title="The exact sequence of actions the system observed, in order.">?</span>`;
  setupReplay(inc.events);

  const quality = inc.decoy_quality_metrics || {};
  const qualitySummary = quality.interaction_count
    ? `<div class="quality-metrics" aria-label="Decoy quality metrics">
        <strong>Quality:</strong> dwell ${quality.dwell_time_s}s,
        ${quality.interaction_count} interaction(s),
        ${quality.distinct_evidence_types} evidence type(s),
        path ${quality.stayed_on_predicted_path === true ? 'stayed' : 'diverged/unknown'}.
      </div>`
    : '';
  document.getElementById('evidence').innerHTML = qualitySummary + (inc.decoy_evidence.length
    ? inc.decoy_evidence.map(ev => {
        let cls = '';
        if (ev.command.startsWith('BRUTEFORCE_PATTERN_DETECTED')) cls = 'danger';
        else if (ev.command.startsWith('PROBE_ONLY')) cls = 'warn';
        else if (ev.command.startsWith('CLIENT_BANNER')) cls = 'info';
        return `<div class="evidence-line ${cls}">[${escapeHtml(ev.decoy)}] ${escapeHtml(ev.src_ip)} → ${escapeHtml(ev.command)}</div>`;
      }).join('')
    : '<div class="empty">No decoy interactions logged.</div>');

  const path = inc.predicted_path;
  document.getElementById('pathBox').innerHTML = path && path.predicted_next_target
    ? `<div class="path-chain">
         <div class="path-node">${escapeHtml(path.current_position)}</div>
         <div class="path-arrow">→</div>
         <div class="path-node target">${escapeHtml(path.predicted_next_label)}</div>
       </div>
       <div class="path-reason">${escapeHtml(path.reason)} (triggered by ${escapeHtml(path.triggering_event)})</div>`
    : `<div class="empty">${path ? escapeHtml(path.reason) : 'No prediction yet.'}</div>`;
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
      Closest match: ${escapeHtml(inc.similarity_top_match.incident_id)} (score ${Number(inc.similarity_top_match.score) || 0})<br>
      Matched on: ${escapeHtml(inc.similarity_top_match.matched_features.join(', ') || 'none')}
    </div>` : ''}
  `;
  loadRiskTrend(id);

  document.getElementById('decoyBox').innerHTML = inc.decoy_deployed
    ? `<div class="decoy-tag">🎭 ${escapeHtml(inc.decoy_deployed)} deployed</div>`
    : `<div class="decoy-tag" style="background:#132018; color:var(--low);">No decoy needed</div>`;

  const mitre = inc.mitre_techniques || [];
  document.getElementById('mitreBox').innerHTML = mitre.length
    ? mitre.map(t => `<span class="mitre-tag" title="${escapeHtml(t.tactic)}">${escapeHtml(t.technique_id)} — ${escapeHtml(t.technique_name)}</span>`).join('')
    : '<div class="empty">No mapped techniques yet.</div>';

  const alert = inc.soc_alert;
  if (alert) {
    document.getElementById('socBanner').innerHTML = `
      <div class="soc-banner ${alert.would_page ? 'page' : 'noage'}">
        ${alert.would_page ? '🚨' : 'ℹ️'} SOC Severity: <strong>${escapeHtml(alert.severity)}</strong>
        ${alert.would_page ? '— would page an analyst' : '— no page, queued for review'}
      </div>`;
  } else {
    document.getElementById('socBanner').innerHTML = '';
  }

  document.getElementById('summaryBox').textContent = inc.summary || 'No summary yet.';
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
startLiveUpdates();

if (!localStorage.getItem('mirageXOnboarded')) {
  setTimeout(startOnboarding, 400);
}

setInterval(refreshSelected, 4000);
setInterval(checkApi, 5000);
setInterval(pollAlerts, 6000);
