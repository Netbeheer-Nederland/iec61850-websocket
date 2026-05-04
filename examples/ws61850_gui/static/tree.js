/**
 * Convert a JSON-encoded ASN.1 TimeStamp object to an ISO time string.
 * @param {Object} ts - The TimeStamp object, e.g. { secondSinceEpoch: 1697539200, fractionOfSecond: 123456, timeQuality: {...} }
 * @returns {string} ISO 8601 string or empty string if invalid
 */
function asn1TimeStampToISOString(ts) {
  if (!ts || typeof ts.secondSinceEpoch !== 'number') return '';
  // ASN.1 TimeStamp: seconds since epoch (UTC), fractionOfSecond is optional (microseconds)
  const seconds = ts.secondSinceEpoch;
  let ms = 0;
  if (typeof ts.fractionOfSecond === 'number') {
    // fractionOfSecond is usually in microseconds (0..16777215)
    // Convert to milliseconds (3 digits)
    ms = Math.floor(ts.fractionOfSecond / 1000);
  }
  // Create JS Date from seconds and ms
  const date = new Date((seconds * 1000) + ms);
  return date.toISOString();
}
let modelPollTimer = null;
let statusPollTimer = null;
let reportPollTimer = null;
let connectionPollingEnabled = false;
let connectionPollSession = 0;
let actionsPollInFlight = false;
let statusPollInFlight = false;
let reportPollInFlight = false;
async function fetchModel(initial=true){
  if (initial && modelPollTimer){
    clearTimeout(modelPollTimer); modelPollTimer = null;
  }
  const spinner = document.getElementById('spinner');
  const refreshBtn = document.getElementById('refresh');
  const container = document.getElementById('tree');
  const progressEl = document.getElementById('modelProgress');
  try {
    if (initial){
      spinner.style.display = 'flex';
      refreshBtn.disabled = true;
      container.innerHTML = '';
    }
    indicateFetchingModel();
    const res = await fetch('/api/model');
    const data = await res.json();
    if (data.status === 'building'){
      // show progress
      if (progressEl){
        const p = data.progress || {};
        const ldsTotal = p.lds_total || 0; const ldsDone = p.lds_done || 0;
        const lnsTotal = p.lns_total || 0; const lnsDone = p.lns_done || 0;
        const curLd = p.current_ld || '-'; const curLn = p.current_ln || '-';
        progressEl.textContent = `Building model: LD ${ldsDone}/${ldsTotal}, LN ${lnsDone}/${lnsTotal} (current: ${curLd}/${curLn})`;
      }
      modelPollTimer = setTimeout(() => fetchModel(false), 1200);
      return;
    }
    if (data.status === 'error'){
      container.textContent = 'Model build error: ' + (data.error || 'unknown');
      if (progressEl) progressEl.textContent = '';
      return;
    }
    if (data.status === 'ready' && data.model){
      if (progressEl) progressEl.textContent = '';
      // Store model data globally for RCB edit dialog
      window.modelData = data.model;
      renderModel(data.model, container);
    } else {
      container.textContent = 'Unexpected response';
    }
  } catch(err){
    container.textContent = 'Fetch failed: ' + err;
    if (progressEl) progressEl.textContent = '';
  } finally {
    if (initial){
      spinner.style.display = 'none';
      refreshBtn.disabled = false;
    }
  }
}

// Connection state & auto-reconnect
const connectionDrafts = {
  clientServer: {url:null, port:null, cp:null, direct:true, isServer:false, applicationRole:'iec_server', target:'client-server'},
  serverClient: {url:null, port:null, cp:null, direct:true, isServer:true, applicationRole:'iec_client', target:'server-client'}
};
const panelStates = {
  clientServer: 'not-connected',
  serverClient: 'not-connected'
};
const previousPanelStates = {
  clientServer: 'not-connected',
  serverClient: 'not-connected'
};
let autoReconnectEnabled = false;
let reconnectAttempt = 0;
let reconnectPending = false;
const manualDisconnectByPanel = {
  clientServer: false,
  serverClient: false
};
// Timer id for a scheduled reconnect attempt so we can cancel on manual disconnect
let reconnectTimerId = null;
const MAX_BACKOFF_MS = 15000;
// Cache for data object definitions: key = `${ld}/${ln}.${path}` value = {subDataObjects:[], dataAttributes:[]}
const doDefCache = {};

// --- Action log polling (footer status line) ---
let actionsPollTimer = null;
let lastActionRendered = null; // store message+time to avoid redundant DOM churn
const ACTIONS_POLL_INTERVAL_CONNECTED = 1500; // ms
const ACTIONS_POLL_INTERVAL_IDLE = 5000; // ms
const STATUS_POLL_INTERVAL_CONNECTED = 2000; // ms
const STATUS_POLL_INTERVAL_IDLE = 5000; // ms
const REPORT_POLL_INTERVAL_CONNECTED = 1000; // ms
const REPORT_POLL_INTERVAL_IDLE = 10000; // ms
const MAX_HISTORY = 10;
let actionHistory = []; // store last N actions
let pollingPaused = false; // due to visibility
let frozen = false; // freeze main footer updates
let lastActionTimestamp = null; // epoch ms
let elapsedTimer = null;

function panelHasLiveConnection(panelKey){
  return ['connected', 'connecting', 'starting', 'listening'].includes(panelStates[panelKey]);
}

function anyPanelActive(){
  return Object.keys(panelStates).some(panelHasLiveConnection);
}

function primaryStatusState(){
  return panelStates.serverClient === 'connected' || panelStates.serverClient === 'listening'
    ? panelStates.serverClient
    : panelStates.clientServer;
}

function updateGlobalStatusSummary(){
  const el = document.getElementById('statusText');
  if (!el) return;
  const currentState = primaryStatusState();
  el.textContent = currentState;
  el.style.color = ({
    'connected':'green',
    'connecting':'orange',
    'listening':'blue',
    'starting':'orange',
    'not-connected':'#666',
    'error':'red'
  })[currentState] || '#333';
}

function updateActiveRoleSummary(){
  const labels = [];
  if (panelHasLiveConnection('serverClient')) labels.push(CONNECTION_FORMS.serverClient.roleLabel);
  if (panelHasLiveConnection('clientServer')) labels.push(CONNECTION_FORMS.clientServer.roleLabel);
  setActiveRoleLabel(labels.length ? labels.join(' + ') : 'No active endpoint');
}

function svgIcon(kind){
  const base = {
    info: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1976d2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><circle cx="12" cy="16" r="1"/></svg>',
    warn: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#ff9800" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12" y2="17"/></svg>',
    error: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#c62828" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>'
  };
  return base[kind] || base.info;
}

function setFooterMessage(msg, level='info', opts={}){
  if (frozen && !opts.overrideFreeze) return; // do not update while frozen
  const el = document.getElementById('actionText');
  if (!el) return;
  if (lastActionRendered && lastActionRendered.msg === msg && lastActionRendered.level === level && !opts.force){
    return; // no change
  }
  lastActionRendered = {msg, level};
  el.classList.remove('info','warn','error','fetching');
  el.classList.add(level);
  if (opts.fetching){ el.classList.add('fetching'); }
  el.innerHTML = svgIcon(level) + ' ' + escapeHtml(msg);
}

function escapeHtml(str){
  return str.replace(/[&<>"] /g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',' ' :' ' }[c]));
}

function updateElapsed(){
  const span = document.getElementById('actionElapsed');
  if (!span) return;
  if (!lastActionTimestamp){ span.textContent=''; return; }
  const secs = Math.floor((Date.now() - lastActionTimestamp)/1000);
  span.textContent = secs + 's';
}

function recordActionForHistory(action){
  actionHistory.push(action);
  if (actionHistory.length > MAX_HISTORY) actionHistory.shift();
  lastActionTimestamp = Date.now();
  if (!elapsedTimer){
    elapsedTimer = setInterval(updateElapsed, 1000);
  }
  renderHistory();
  updateElapsed();
}

function renderHistory(){
  const ul = document.getElementById('actionHistoryList');
  if (!ul) return;
  ul.innerHTML = '';
  actionHistory.forEach(a => {
    const li = document.createElement('li');
    const timeSpan = document.createElement('span'); timeSpan.className='time'; timeSpan.textContent = a.time;
    const lvlSpan = document.createElement('span'); lvlSpan.className='lvl-' + (a.level==='warn'?'warn':(a.level==='error'?'error':'info')); lvlSpan.textContent = a.level.toUpperCase();
    const msgSpan = document.createElement('span'); msgSpan.textContent = a.message;
    li.appendChild(timeSpan); li.appendChild(lvlSpan); li.appendChild(msgSpan);
    ul.appendChild(li);
  });
}

async function pollActionsOnce(){
  const session = connectionPollSession;
  if (!connectionPollingEnabled) {
    actionsPollTimer = null;
    return;
  }
  actionsPollInFlight = true;
  try {
    const res = await fetch('/api/actions');
    if (!res.ok) throw new Error('status ' + res.status);
    const data = await res.json();
    const actions = data.actions || [];
    if (actions.length){
      const last = actions[actions.length - 1];
      const lvl = (last.level === 'error') ? 'error' : (last.level === 'warn' ? 'warn' : 'info');
      recordActionForHistory(last);
      setFooterMessage(`[${last.time}] ${last.message}`, lvl);
    } else {
      setFooterMessage('Idle.', 'info');
    }
  } catch(e){
    // Only surface fetch errors if we previously had a message; else remain idle
    setFooterMessage('Action log unavailable', 'warn');
  } finally {
    actionsPollInFlight = false;
    if (!pollingPaused && connectionPollingEnabled && session === connectionPollSession){
      const summaryState = primaryStatusState();
      const actionDelay = (summaryState === 'connected' || summaryState === 'listening')
        ? ACTIONS_POLL_INTERVAL_CONNECTED
        : ACTIONS_POLL_INTERVAL_IDLE;
      actionsPollTimer = setTimeout(pollActionsOnce, actionDelay);
    } else {
      actionsPollTimer = null;
    }
  }
}

function startActionsPolling(){
  if (actionsPollTimer || actionsPollInFlight) return;
  setFooterMessage('Idle.', 'info');
  pollActionsOnce();
}

function stopActionsPolling(){
  if (!actionsPollTimer) return;
  clearTimeout(actionsPollTimer);
  actionsPollTimer = null;
}

function startConnectionPolling(){
  if (!connectionPollingEnabled){
    connectionPollSession += 1;
  }
  connectionPollingEnabled = true;
  if (!statusPollTimer && !statusPollInFlight) pollStatus();
  if (!reportPollTimer && !reportPollInFlight) pollReportUpdates();
  if (!actionsPollTimer) startActionsPolling();
}

function stopConnectionPolling(){
  if (anyPanelActive()) return;
  connectionPollingEnabled = false;
  connectionPollSession += 1;
  if (statusPollTimer){
    clearTimeout(statusPollTimer);
    statusPollTimer = null;
  }
  if (reportPollTimer){
    clearTimeout(reportPollTimer);
    reportPollTimer = null;
  }
  stopActionsPolling();
}

// Provide a hook to temporarily show a message (e.g., before first action appears)
function indicateFetchingModel(){
  setFooterMessage('Fetching model...', 'info', {fetching:true, force:true});
}

// Visibility handling to pause polling
document.addEventListener('visibilitychange', () => {
  if (document.hidden){
    pollingPaused = true;
    if (actionsPollTimer) { clearTimeout(actionsPollTimer); actionsPollTimer = null; }
    if (statusPollTimer) { clearTimeout(statusPollTimer); statusPollTimer = null; }
    if (reportPollTimer) { clearTimeout(reportPollTimer); reportPollTimer = null; }
  } else {
    pollingPaused = false;
    if (connectionPollingEnabled){
      startConnectionPolling();
    }
  }
});

// Footer control buttons
window.addEventListener('DOMContentLoaded', () => {
  const toggleBtn = document.getElementById('toggleHistoryBtn');
  const histDiv = document.getElementById('actionHistory');
  const freezeBtn = document.getElementById('freezeBtn');
  const clearBtn = document.getElementById('clearHistoryBtn');
  if (toggleBtn && histDiv){
    toggleBtn.addEventListener('click', () => {
      const hidden = histDiv.classList.toggle('hidden');
      toggleBtn.dataset.active = hidden ? 'false' : 'true';
      toggleBtn.textContent = hidden ? 'History' : 'Hide';
    });
  }
  if (freezeBtn){
    freezeBtn.addEventListener('click', () => {
      frozen = !frozen;
      freezeBtn.dataset.frozen = frozen ? 'true' : 'false';
      freezeBtn.textContent = frozen ? 'Unfreeze' : 'Freeze';
    });
  }
  if (clearBtn){
    clearBtn.addEventListener('click', () => {
      actionHistory = [];
      renderHistory();
      lastActionRendered = null;
      setFooterMessage('Cleared history', 'info', {overrideFreeze:true});
      lastActionTimestamp = Date.now();
      updateElapsed();
    });
  }
});

function scheduleReconnect(){
  // Suppress auto-reconnect if user explicitly disconnected
  if (manualDisconnectByPanel.clientServer) return;
  if (!autoReconnectEnabled || reconnectPending) return;
  const lastConnection = connectionDrafts.clientServer;
  if (!lastConnection.url || !lastConnection.port || !lastConnection.cp) return;
  reconnectPending = true;
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempt), MAX_BACKOFF_MS);
  reconnectTimerId = setTimeout(async () => {
    try {
      await doReconnect();
      reconnectAttempt = 0; // reset on success
    } catch(e){
      reconnectAttempt++;
    } finally {
      reconnectPending = false;
      reconnectTimerId = null;
    }
  }, delay);
}

async function doReconnect(){
  const lastConnection = connectionDrafts.clientServer;
  // Double-check suppression in case a timer fired after manualDisconnect was set
  if (manualDisconnectByPanel.clientServer) {
    throw new Error('manual reconnect suppressed');
  }
  startConnectionPolling();
  const res = await fetch('/api/connect', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      target: lastConnection.target,
      url: lastConnection.url,
      port: lastConnection.port,
      cp: lastConnection.cp,
      is_direct: lastConnection.direct,
      is_server: false,
      application_role: lastConnection.applicationRole
    })
  });
  const data = await res.json();
  if (data.error) {
    stopConnectionPolling();
    throw new Error(data.error);
  }
}

function renderModel(data, container){
  const server = data.server;
  const root = makeNode('Server');

  // Add server-level status badge
  const serverHeader = root.querySelector('.node-title');
  if (serverHeader && data.source === 'live') {
    const badge = document.createElement('span');
    // Determine overall status: if any LD has error => error, else if all ok => ok, else mixed
    const statuses = Object.values(data.logicalDeviceStatus || {});
    let overallStatus = 'ok';
    if (statuses.some(s => s === 'error')) {
      overallStatus = 'error';
    } else if (statuses.some(s => s === 'old')) {
      overallStatus = 'old';
    }
    badge.className = 'badge ' + overallStatus;
    badge.textContent = overallStatus.toUpperCase();
    serverHeader.appendChild(badge);
  }

  container.appendChild(root);
  if(server && server.logicalDevices){
    const ul = document.createElement('ul');
    server.logicalDevices.forEach(ld => {
      const li = document.createElement('li');
      const ldHeader = document.createElement('div');
      ldHeader.textContent = ld;
      ldHeader.style.fontWeight = '600';
      // Remove LD-level badge rendering
      li.appendChild(ldHeader);
      // If logicalDeviceMap already provided, render children immediately
      if (data.logicalDeviceMap && data.logicalDeviceMap[ld]){
        const childUl = document.createElement('ul');
        data.logicalDeviceMap[ld].forEach(n => {
          const childLi = document.createElement('li');
          // Determine key & details
          let lnInst = n;
            if (n.includes('/')){ lnInst = n.split('/')[1]; }
            else if (n.includes(':')){ lnInst = n.split(':')[1]; }
          const key = ld + '/' + lnInst;
          const lnHeader = document.createElement('div');
          lnHeader.className = 'ln-header';
          lnHeader.style.fontWeight = '500';
          const det = (data.logicalNodeDetails && data.logicalNodeDetails[key]) || null;
          const objs = det ? (det.dataObjects || []) : [];
          const das = det ? (det.dataAttributes || []) : [];
          const rcbs = det ? (det.reportControlBlocks || []) : [];
          const datasets = det ? (det.dataSets || []) : [];
          const countsSpan = document.createElement('span');
          countsSpan.className = 'ln-counts';
          countsSpan.textContent = `(${objs.length} DO, ${das.length} DA, ${rcbs.length} RCB, ${datasets.length} DS)`;
          lnHeader.textContent = n;
          lnHeader.appendChild(countsSpan);
          childLi.appendChild(lnHeader);
          const detailsWrap = document.createElement('div');
          detailsWrap.className = 'ln-details';
          if (det){
            const detUl = document.createElement('ul');
            if (objs.length){
              const objLi = document.createElement('li');
              objLi.textContent = 'DataObjects';
              const oUl = document.createElement('ul');
              objs.forEach(o => {
                const li2 = document.createElement('li');
                const btn = document.createElement('button');
                btn.textContent = '+';
                btn.className = 'inline-expand';
                btn.dataset.state = 'collapsed';
                const labelSpan = document.createElement('span');

                // Handle both old format (string) and new format (object with name and cdc)
                const oName = typeof o === 'string' ? o : o.name;
                const oCdc = (typeof o === 'object' && o.cdc) ? o.cdc : null;

                // Add the data object name as text node
                const nameText = document.createTextNode(oName);
                labelSpan.appendChild(nameText);

                // Add CDC badge after the name if available
                if (oCdc) {
                  const cdcBadge = document.createElement('span');
                  cdcBadge.className = 'cdc-badge';
                  cdcBadge.textContent = oCdc.toUpperCase();
                  labelSpan.appendChild(cdcBadge);
                }

                labelSpan.className = 'data-item';
                // Add context menu for data objects (will show FC selector)
                const fullRef = `${ld}/${lnInst}.${oName}`;
                labelSpan.dataset.objRef = fullRef;

                // Check if this is a controllable CDC
                const isControllable = oCdc && CONTROLLABLE_CDCS.includes(oCdc.toUpperCase());

                if (isControllable) {
                  // For controllable CDCs: left-click opens control dialog, right-click shows context menu
                  labelSpan.style.cursor = 'pointer';
                  labelSpan.title = `Click to control ${oName} (${oCdc.toUpperCase()})`;
                  labelSpan.addEventListener('click', (e) => {
                    e.stopPropagation();
                    showControlDialog(fullRef, oName, oCdc);
                  });
                  labelSpan.addEventListener('contextmenu', (e) => showContextMenuForDataObject(e, fullRef));
                } else {
                  // For non-controllable: only right-click context menu
                  labelSpan.style.cursor = 'context-menu';
                  labelSpan.addEventListener('contextmenu', (e) => showContextMenuForDataObject(e, fullRef));
                }

                // Add tree value display span (stores last read value for DO)
                const treeValSpan = document.createElement('span');
                treeValSpan.className = 'tree-value-display';
                treeValSpan.dataset.objRef = fullRef;
                treeValSpan.textContent = '';
                labelSpan.appendChild(treeValSpan);
                li2.appendChild(btn);
                li2.appendChild(labelSpan);
                const subWrap = document.createElement('div');
                subWrap.style.display = 'none';
                li2.appendChild(subWrap);
                btn.addEventListener('click', () => toggleDoExpansion({btn, subWrap, ldlnKey:key, doPath:oName}));
                oUl.appendChild(li2);
              });
              objLi.appendChild(oUl); detUl.appendChild(objLi);
            }
            if (das.length){
              das.forEach(d => {
                const li3 = document.createElement('li');
                li3.textContent = d;
                li3.className = 'data-item';
                li3.style.cursor = 'context-menu';
                // Add context menu for data attributes (use default 'mx' since we don't have FC info here)
                const fullRef = `${ld}/${lnInst}.${d}`;
                li3.addEventListener('contextmenu', (e) => showContextMenuForDataAttribute(e, fullRef, 'mx'));
                detUl.appendChild(li3);
              });
            }
            if (rcbs.length){
              const rcbLi = document.createElement('li');
              rcbLi.textContent = 'ReportControlBlocks';
              const rUl = document.createElement('ul');
              rcbs.forEach(r => {
                const ri = document.createElement('li');
                ri.style.display = 'flex';
                ri.style.alignItems = 'center';
                ri.style.gap = '8px';

                // Create a span for the name and badge
                const nameSpan = document.createElement('span');
                nameSpan.style.cursor = 'pointer';
                nameSpan.style.flex = '1';
                nameSpan.textContent = r.name + (r.type ? ` (${r.type})` : '');

                // Add enabled/disabled badge
                if (r.enabled !== undefined) {
                  const badge = document.createElement('span');
                  badge.className = r.enabled ? 'rcb-badge rcb-enabled' : 'rcb-badge rcb-disabled';
                  badge.textContent = r.enabled ? 'Enabled' : 'Disabled';
                  nameSpan.appendChild(document.createTextNode(' '));
                  nameSpan.appendChild(badge);
                }

                // Add click handler to show RCB details
                nameSpan.addEventListener('click', (e) => {
                  e.stopPropagation();
                  const rcbRef = `${ld}/${lnInst}.${r.name}`;
                  showRcbDetails(rcbRef, r);
                });

                // Create refresh button
                const refreshBtn = document.createElement('button');
                refreshBtn.className = 'rcb-tree-refresh-btn';
                refreshBtn.title = 'read RCB values';
                refreshBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M13.65 2.35C12.2 0.9 10.21 0 8 0 3.58 0 0.01 3.58 0.01 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L9 7h7V0l-2.35 2.35z" fill="currentColor"/>
                </svg>`;

                refreshBtn.addEventListener('click', async (e) => {
                  e.stopPropagation();
                  await refreshRcbValues(ld, lnInst, r, refreshBtn, nameSpan);
                });

                // Create edit button
                const editBtn = document.createElement('button');
                editBtn.className = 'rcb-tree-edit-btn';
                editBtn.title = 'modify RCB values';
                editBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M11.013 1.427a1.75 1.75 0 0 1 2.474 0l1.086 1.086a1.75 1.75 0 0 1 0 2.474l-8.61 8.61c-.21.21-.47.364-.756.445l-3.251.93a.75.75 0 0 1-.927-.928l.929-3.25c.081-.286.235-.547.445-.758l8.61-8.61Zm.176 4.823L9.75 4.81l-6.286 6.287a.253.253 0 0 0-.064.108l-.558 1.953 1.953-.558a.253.253 0 0 0 .108-.064Zm1.238-3.763a.25.25 0 0 0-.354 0L10.811 3.75l1.439 1.44 1.263-1.263a.25.25 0 0 0 0-.354Z" fill="currentColor"/>
                </svg>`;

                editBtn.addEventListener('click', async (e) => {
                  e.stopPropagation();
                  const rcbRef = `${ld}/${lnInst}.${r.name}`;
                  showRcbEditDialog(rcbRef, r, ld, lnInst, nameSpan);
                });

                ri.appendChild(nameSpan);
                ri.appendChild(refreshBtn);
                ri.appendChild(editBtn);
                rUl.appendChild(ri);
              });
              rcbLi.appendChild(rUl); detUl.appendChild(rcbLi);
            }
            if (datasets.length){
              const dsLi = document.createElement('li');
              dsLi.textContent = 'DataSets';
              const dsUl = document.createElement('ul');
              datasets.forEach(ds => { const dsi = document.createElement('li'); dsi.textContent = ds; dsUl.appendChild(dsi); });
              dsLi.appendChild(dsUl); detUl.appendChild(dsLi);
            }
            if (!objs.length && !das.length){
              const emptyLi = document.createElement('li'); emptyLi.textContent = '(empty)'; detUl.appendChild(emptyLi);
            }
            detailsWrap.appendChild(detUl);
          }
          childLi.appendChild(detailsWrap);
          lnHeader.addEventListener('click', () => {
            const visible = detailsWrap.classList.toggle('visible');
            lnHeader.classList.toggle('expanded', visible);
          });
          childUl.appendChild(childLi);
        });
        li.appendChild(childUl);
      } else {
        // Fallback to on-demand fetch if map missing
        const btn = document.createElement('button');
        btn.textContent = '+ expand';
        btn.addEventListener('click', async () => {
          const existing = li.querySelector('ul');
          if (existing){
            li.removeChild(existing);
            btn.textContent = '+ expand';
            return;
          }
          btn.textContent = '...';
          const res = await fetch('/api/ld/' + encodeURIComponent(ld));
          const ldData = await res.json();
          if (ldData.error){
            alert('Error: ' + ldData.error);
            btn.textContent = '+ expand';
            return;
          }
          const nodes = (ldData.ld && ldData.ld.logicalNodes) ? ldData.ld.logicalNodes : [];
          const childUl = document.createElement('ul');
          nodes.forEach(n => {
            const childLi = document.createElement('li');
            childLi.textContent = n;
            childUl.appendChild(childLi);
          });
          li.appendChild(childUl);
          btn.textContent = '- collapse';
        });
        li.appendChild(btn);
      }
      ul.appendChild(li);
    });
    root.appendChild(ul);
  }
}

function makeNode(title){
  const div = document.createElement('div');
  div.className = 'node';
  const h = document.createElement('div');
  h.className = 'node-title';
  h.textContent = title;
  div.appendChild(h);
  return div;
}

function ldInstFromKey(key){
  return key.split('/')[0];
}
function lnInstFromKey(key){
  return key.split('/')[1];
}

async function fetchDoDefinition(ldlnKey, doPath){
  const ld = ldInstFromKey(ldlnKey);
  const ln = lnInstFromKey(ldlnKey);
  const cacheKey = `${ld}/${ln}.${doPath}`;
  if (doDefCache[cacheKey]) return doDefCache[cacheKey];
  const path = encodeURIComponent(doPath);
  const res = await fetch(`/api/dodef/${encodeURIComponent(ld)}/${encodeURIComponent(ln)}/${path}`);
  const jd = await res.json();
  if (!jd.error) doDefCache[cacheKey] = jd;
  return jd;
}

function buildDoDetailsDom(def, fullObjRef){
  const subUl = document.createElement('ul');
  if (def.subDataObjects && def.subDataObjects.length){
    def.subDataObjects.forEach(sd => {
      const sdi = document.createElement('li');
      const btn = document.createElement('button');
      btn.textContent = '+';
      btn.className = 'inline-expand';
      btn.dataset.state = 'collapsed';
      const labelSpan = document.createElement('span');

      // Handle both old format (string) and new format (object with name and cdc)
      const sdName = typeof sd === 'string' ? sd : sd.name;
      const sdCdc = (typeof sd === 'object' && sd.cdc) ? sd.cdc : null;

      // Add the data object name as text node
      const nameText = document.createTextNode(sdName);
      labelSpan.appendChild(nameText);

      // Add CDC badge after the name if available
      if (sdCdc) {
        const cdcBadge = document.createElement('span');
        cdcBadge.className = 'cdc-badge';
        cdcBadge.textContent = sdCdc.toUpperCase();
        labelSpan.appendChild(cdcBadge);
      }

          // Add context menu for SubDataObject similar to top-level DO
          labelSpan.className = 'data-item';
          labelSpan.style.cursor = 'context-menu';
          const fullSubRef = `${fullObjRef}.${sdName}`; // LD/LN.DO.SubDO path
          labelSpan.dataset.objRef = fullSubRef;
          labelSpan.addEventListener('contextmenu', (e) => showContextMenuForDataObject(e, fullSubRef));

          // Add tree value display span for SubDO
          const treeValSpan = document.createElement('span');
          treeValSpan.className = 'tree-value-display';
          treeValSpan.dataset.objRef = fullSubRef;
          treeValSpan.textContent = '';
          labelSpan.appendChild(treeValSpan);

      const subWrap = document.createElement('div');
      subWrap.style.display = 'none';
      btn.addEventListener('click', () => toggleDoExpansion({btn, subWrap, ldlnKey: def._ldlnKey, doPath: def._basePath + '.' + sdName}));
      const liContainer = document.createElement('div');
      liContainer.appendChild(btn);
      liContainer.appendChild(labelSpan);
      liContainer.appendChild(subWrap);
      sdi.appendChild(liContainer);
      subUl.appendChild(sdi);
    });
  }
  if (def.dataAttributes && def.dataAttributes.length){
    def.dataAttributes.forEach(da => {
      const dai = document.createElement('li');
      // Handle both old format (string) and new format (object with structure info)
      if (typeof da === 'string') {
        dai.textContent = da;
      } else if (da.daRef) {
        if (da.hasStructure && da.subAttributes && da.subAttributes.length > 0) {
          // Data attribute with nested structure - make it expandable
          const btn = document.createElement('button');
          btn.textContent = '';
          btn.className = 'inline-expand';
          btn.dataset.state = 'collapsed';
          btn.setAttribute('aria-label', 'Expand attribute');
          const labelSpan = document.createElement('span');
          labelSpan.className = 'data-item';
          labelSpan.style.cursor = 'context-menu';

          // Add FC badge before the name
          if (da.fc) {
            const fcBadge = document.createElement('span');
            fcBadge.className = 'tree-fc-badge';
            fcBadge.textContent = da.fc.toUpperCase();
            labelSpan.appendChild(fcBadge);
          }

          // Add expand/collapse button after FC badge
          labelSpan.appendChild(btn);

          // Add the attribute name
          const nameText = document.createTextNode(da.daRef);
          labelSpan.appendChild(nameText);

          // Add context menu for structured attributes too
          if (fullObjRef) {
            const attrRef = `${fullObjRef}.${da.daRef}`;
            const fc = da.fc || 'mx';
            labelSpan.addEventListener('contextmenu', (e) => showContextMenuForDataAttribute(e, attrRef, fc));
          }
          // Add type badge if available
          if (da.type) {
            const typeBadge = document.createElement('span');
            typeBadge.className = 'da-type';
            typeBadge.textContent = da.type;
            labelSpan.appendChild(typeBadge);
          }

          // Add value display span at the end (will be updated when value is read)
          if (fullObjRef) {
            const attrRef = `${fullObjRef}.${da.daRef}`;
            const valueSpan = document.createElement('span');
            valueSpan.className = 'tree-value-display';
            valueSpan.dataset.objRef = attrRef;
            valueSpan.textContent = ''; // Empty initially
            labelSpan.appendChild(valueSpan);
          }

          const subWrap = document.createElement('div');
          subWrap.style.display = 'none';
          const attrRef = fullObjRef ? `${fullObjRef}.${da.daRef}` : da.daRef;
          const fc = da.fc || 'mx';
          btn.addEventListener('click', () => toggleDaExpansion(btn, subWrap, da.subAttributes, attrRef, fc));
          const liContainer = document.createElement('div');
          liContainer.appendChild(labelSpan);
          liContainer.appendChild(subWrap);
          dai.appendChild(liContainer);
        } else {
          // Simple data attribute without structure
          const nameSpan = document.createElement('span');
          nameSpan.className = 'data-item';
          nameSpan.style.cursor = 'context-menu';

          // Add FC badge before the name
          if (da.fc) {
            const fcBadge = document.createElement('span');
            fcBadge.className = 'tree-fc-badge';
            fcBadge.textContent = da.fc.toUpperCase();
            nameSpan.appendChild(fcBadge);
          }

          // Add the attribute name
          const nameText = document.createTextNode(da.daRef);
          nameSpan.appendChild(nameText);

          // Add context menu if we have full object reference
          if (fullObjRef) {
            const attrRef = `${fullObjRef}.${da.daRef}`;
            const fc = da.fc || 'mx';  // Use FC from attribute definition or default to 'mx'
            nameSpan.addEventListener('contextmenu', (e) => showContextMenuForDataAttribute(e, attrRef, fc));
          }
          dai.appendChild(nameSpan);
          // Add type badge if available
          if (da.type) {
            const typeBadge = document.createElement('span');
            typeBadge.className = 'da-type';
            typeBadge.textContent = da.type;
            dai.appendChild(typeBadge);
          }

          // Add value display span at the end (will be updated when value is read)
          if (fullObjRef) {
            const attrRef = `${fullObjRef}.${da.daRef}`;
            const valueSpan = document.createElement('span');
            valueSpan.className = 'tree-value-display';
            valueSpan.dataset.objRef = attrRef;
            valueSpan.textContent = ''; // Empty initially
            dai.appendChild(valueSpan);
          }
        }
      }
      subUl.appendChild(dai);
    });
  }
  if (!subUl.children.length){
    const empty = document.createElement('li'); empty.textContent = '(empty)'; subUl.appendChild(empty);
  }
  return subUl;
}

function buildDaStructureDom(subAttributes, parentRef = null, parentFc = 'mx'){
  const ul = document.createElement('ul');
  subAttributes.forEach(attr => {
    const li = document.createElement('li');
    const attrRef = parentRef ? `${parentRef}.${attr.name}` : attr.name;
    const fc = attr.fc || parentFc; // Use attribute's FC or inherit from parent

    if (attr.hasStructure && attr.subAttributes && attr.subAttributes.length > 0) {
      // Nested structure - make it expandable
      const btn = document.createElement('button');
      btn.textContent = '';
      btn.className = 'inline-expand';
      btn.dataset.state = 'collapsed';
      btn.setAttribute('aria-label', 'Expand attribute');
      const labelSpan = document.createElement('span');

      // Add FC badge before the name
      const fcBadge = document.createElement('span');
      fcBadge.className = 'tree-fc-badge';
      fcBadge.textContent = fc.toUpperCase();
      labelSpan.appendChild(fcBadge);

      // Add expand/collapse button after FC badge
      labelSpan.appendChild(btn);

      // Add the attribute name
      const nameText = document.createTextNode(attr.name);
      labelSpan.appendChild(nameText);

      // Add type badge if available
      if (attr.type) {
        const typeBadge = document.createElement('span');
        typeBadge.className = 'da-type';
        typeBadge.textContent = attr.type;
        labelSpan.appendChild(typeBadge);
      }

      // Add value display span (will be updated when value is read)
      if (parentRef) {
        const valueSpan = document.createElement('span');
        valueSpan.className = 'tree-value-display';
        valueSpan.dataset.objRef = attrRef;
        valueSpan.textContent = ''; // Empty initially
        labelSpan.appendChild(valueSpan);
      }

      // Add context menu for structured sub-attributes
      if (parentRef) {
        labelSpan.className = 'data-item';
        labelSpan.style.cursor = 'context-menu';
        labelSpan.addEventListener('contextmenu', (e) => showContextMenuForDataAttribute(e, attrRef, fc));
      }

      const subWrap = document.createElement('div');
      subWrap.style.display = 'none';
      btn.addEventListener('click', () => toggleDaExpansion(btn, subWrap, attr.subAttributes, attrRef, fc));
      const liContainer = document.createElement('div');
      liContainer.appendChild(labelSpan);
      liContainer.appendChild(subWrap);
      li.appendChild(liContainer);
    } else {
      // Simple leaf attribute
      const nameSpan = document.createElement('span');

      // Add FC badge before the name
      const fcBadge = document.createElement('span');
      fcBadge.className = 'tree-fc-badge';
      fcBadge.textContent = fc.toUpperCase();
      nameSpan.appendChild(fcBadge);

      // Add the attribute name
      const nameText = document.createTextNode(attr.name);
      nameSpan.appendChild(nameText);

      // Add context menu for simple leaf sub-attributes
      if (parentRef) {
        nameSpan.className = 'data-item';
        nameSpan.style.cursor = 'context-menu';
        nameSpan.addEventListener('contextmenu', (e) => showContextMenuForDataAttribute(e, attrRef, fc));
      }

      li.appendChild(nameSpan);
      // Add type badge if available
      if (attr.type) {
        const typeBadge = document.createElement('span');
        typeBadge.className = 'da-type';
        typeBadge.textContent = attr.type;
        li.appendChild(typeBadge);
      }

      // Add value display span (will be updated when value is read)
      if (parentRef) {
        const valueSpan = document.createElement('span');
        valueSpan.className = 'tree-value-display';
        valueSpan.dataset.objRef = attrRef;
        valueSpan.textContent = ''; // Empty initially
        li.appendChild(valueSpan);
      }
    }
    ul.appendChild(li);
  });
  return ul;
}

function toggleDaExpansion(btn, subWrap, subAttributes, parentRef = null, parentFc = 'mx'){
  if (btn.dataset.state === 'collapsed'){
    subWrap.innerHTML = '';
    subWrap.appendChild(buildDaStructureDom(subAttributes, parentRef, parentFc));
    btn.setAttribute('aria-label', 'Collapse attribute');
    btn.dataset.state = 'expanded';
    subWrap.style.display = 'block';
  } else if (btn.dataset.state === 'expanded'){
    subWrap.style.display = 'none';
    btn.setAttribute('aria-label', 'Expand attribute');
    btn.dataset.state = 'collapsed';
  }
}

async function toggleDoExpansion({btn, subWrap, ldlnKey, doPath}){
  if (btn.dataset.state === 'collapsed'){
    btn.textContent = '…';
    btn.disabled = true;
    try {
      const def = await fetchDoDefinition(ldlnKey, doPath);
      def._ldlnKey = ldlnKey; // annotate for nested fetch
      def._basePath = doPath; // base path for nesting
      const fullObjRef = ldlnKey.replace('/', '/') + '.' + doPath; // e.g., LD0/LN0.DO1
      subWrap.innerHTML = '';
      subWrap.appendChild(buildDoDetailsDom(def, fullObjRef));
      btn.textContent = '-';
      btn.dataset.state = 'expanded';
      subWrap.style.display = 'block';
    } catch(e){
      subWrap.textContent = 'Error loading';
      btn.textContent = '!';
    } finally {
      btn.disabled = false;
    }
  } else if (btn.dataset.state === 'expanded'){
    subWrap.style.display = 'none';
    btn.textContent = '+';
    btn.dataset.state = 'collapsed';
  }
}

// expandLogicalNode retained only if needed for on-demand later; currently details preloaded
async function expandLogicalNode(){ /* no-op with prefetch */ }

document.getElementById('refresh').addEventListener('click', async () => {
  // First trigger a model rebuild
  try {
    await fetch('/api/model/rebuild', { method: 'POST' });
  } catch (e) {
    console.error('Failed to trigger model rebuild:', e);
  }
  // Then fetch the model (which will poll until ready)
  fetchModel();
});
// Legacy connect button listener removed (replaced by unified handler)

// Input validation helpers and wiring
function displayHostError(id, msg){
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg || '';
  el.style.display = msg ? 'inline-block' : 'none';
  const input = id === 'wsClientHostError' ? document.getElementById('wsClientHost') : null;
  if (input) {
    if (msg) input.classList.add('input-invalid'); else input.classList.remove('input-invalid');
  }
}

function displayPortError(id, msg){
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg || '';
  el.style.display = msg ? 'inline-block' : 'none';
  const input = id === 'wsClientPortError'
    ? document.getElementById('wsClientPort')
    : id === 'wsServerPortError'
      ? document.getElementById('wsServerPort')
      : null;
  if (input) {
    if (msg) input.classList.add('input-invalid'); else input.classList.remove('input-invalid');
  }
}

// Validate host: allow IP v4, IPv6 (simple), or DNS name
function validateHost(host){
  if (!host) return false;
  // IPv4 simple regex
  const ipv4 = /^(25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)){3}$/;
  // IPv6 basic check (contains colons)
  const ipv6 = /:/;
  // Hostname per RFC-like: labels separated by dots, 1-63 chars per label, allowed chars
  const hostname = /^(?=.{1,253}$)([a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)(\.[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$/;

  if (ipv4.test(host)) return true;
  if (ipv6.test(host)) return true; // not strict, but accept common IPv6 literal
  if (hostname.test(host)) return true;
  return false;
}

// Validate port number
function validatePort(port){
  if (!port) return false;
  const num = Number(port);
  if (!Number.isInteger(num)) return false;
  if (num < 1 || num > 65535) return false;
  return true;
}

const CONNECTION_FORMS = {
  clientServer: {
    target: 'client-server',
    hostId: 'wsClientHost',
    hostErrorId: 'wsClientHostError',
    portId: 'wsClientPort',
    portErrorId: 'wsClientPortError',
    cpId: 'wsClientCp',
    buttonId: 'wsClientConnectBtn',
    roleLabel: 'WS Client / IEC Server',
    connectLabel: 'Connect',
    busyLabel: 'Connecting…',
    disconnectLabel: 'Disconnect',
    isServer: false,
    applicationRole: 'iec_server'
  },
  serverClient: {
    target: 'server-client',
    hostId: 'wsServerHost',
    hostErrorId: null,
    portId: 'wsServerPort',
    portErrorId: 'wsServerPortError',
    cpId: 'wsServerCp',
    buttonId: 'wsServerConnectBtn',
    roleLabel: 'WS Server / IEC Client',
    connectLabel: 'Start Server',
    busyLabel: 'Starting…',
    disconnectLabel: 'Stop Server',
    isServer: true,
    applicationRole: 'iec_client'
  }
};

function setButtonState(button, enabled) {
  if (!button) return;
  button.disabled = !enabled;
  button.classList.toggle('btn-disabled', !enabled);
}

function updateConnectButtonState(formKey){
  const form = CONNECTION_FORMS[formKey];
  if (!form) return;
  const hostValue = ((document.getElementById(form.hostId) || {}).value || '').trim();
  const portValue = ((document.getElementById(form.portId) || {}).value || '').trim();
  const hostOk = form.isServer || validateHost(hostValue);
  const portOk = validatePort(portValue);
  setButtonState(document.getElementById(form.buttonId), hostOk && portOk);
}

function bindConnectionValidation(formKey){
  const form = CONNECTION_FORMS[formKey];
  const hostInput = document.getElementById(form.hostId);
  const portInput = document.getElementById(form.portId);
  if (hostInput && !form.isServer){
    hostInput.addEventListener('input', () => {
      const ok = validateHost(hostInput.value.trim());
      displayHostError(form.hostErrorId, ok ? '' : 'Invalid host');
      updateConnectButtonState(formKey);
    });
  }
  if (portInput){
    portInput.addEventListener('input', () => {
      const ok = validatePort(portInput.value.trim());
      displayPortError(form.portErrorId, ok ? '' : 'Invalid port');
      updateConnectButtonState(formKey);
    });
  }
  updateConnectButtonState(formKey);
}

function setActiveRoleLabel(text){
  const el = document.getElementById('activeRoleText');
  if (el) el.textContent = text;
}

function syncConnectionButtons(){
  Object.entries(CONNECTION_FORMS).forEach(([key, form]) => {
    const btn = document.getElementById(form.buttonId);
    if (!btn) return;
    const state = panelStates[key];
    switch(state){
      case 'connected':
      case 'listening':
        btn.textContent = form.disconnectLabel;
        break;
      case 'connecting':
      case 'starting':
        btn.textContent = form.busyLabel;
        break;
      default:
        btn.textContent = form.connectLabel;
    }
  });
}

async function handleConnectionButton(formKey){
  const form = CONNECTION_FORMS[formKey];
  const btn = document.getElementById(form.buttonId);
  if (!btn) return;
  const label = btn.textContent.trim();
  if ([form.disconnectLabel].includes(label)){
    try {
      btn.disabled = true;
      btn.textContent = form.isServer ? 'Stopping…' : 'Disconnecting…';
      // Set manualDisconnect BEFORE issuing the request to avoid race with pollStatus scheduling
      manualDisconnectByPanel[formKey] = true;
      // Cancel any pending reconnect timers
      if (reconnectTimerId){
        clearTimeout(reconnectTimerId);
        reconnectTimerId = null;
      }
      reconnectPending = false;
      const res = await fetch('/api/disconnect', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({target: form.target})
      });
      const data = await res.json();
      if (data.error){
        alert('Disconnect error: ' + data.error);
      }
      markLogicalDevicesOld();
      panelStates[formKey] = 'not-connected';
      updateGlobalStatusSummary();
      updateActiveRoleSummary();
      syncConnectionButtons();
      stopConnectionPolling();
    } catch(e){
      console.error('disconnect failed', e);
      syncConnectionButtons();
    } finally {
      btn.disabled = false;
    }
    return;
  }
  // Initiate connection
  const url = document.getElementById(form.hostId).value.trim();
  const port = document.getElementById(form.portId).value.trim();
  const cp = document.getElementById(form.cpId).value;
  const hostValid = form.isServer || validateHost(url);
  const portValid = validatePort(port);
  if (form.hostErrorId) {
    displayHostError(form.hostErrorId, hostValid ? '' : 'Invalid host (hostname or IP address expected)');
  }
  displayPortError(form.portErrorId, portValid ? '' : 'Invalid port (1-65535 expected)');
  if (!hostValid || !portValid) return;
  connectionDrafts[formKey] = {
    url,
    port,
    cp,
    direct: !form.isServer,
    isServer: form.isServer,
    applicationRole: form.applicationRole,
    panel: formKey,
    target: form.target
  };
  const payload = form.isServer
    ? {target: form.target, url, port, cp, is_direct: true, is_server: true, application_role: form.applicationRole}
    : {target: form.target, url, port, cp, is_direct: true, is_server: false, application_role: form.applicationRole};
  window.currentConnectionDraft = payload;
  try {
    btn.disabled = true;
    btn.textContent = form.busyLabel;
    panelStates[formKey] = form.isServer ? 'listening' : 'connecting';
    startConnectionPolling();
    const res = await fetch('/api/connect', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
    const data = await res.json();
    if (data.error){
      panelStates[formKey] = 'not-connected';
      updateGlobalStatusSummary();
      updateActiveRoleSummary();
      stopConnectionPolling();
      alert('Connect error: ' + data.error);
      syncConnectionButtons();
      return;
    }
    // User is actively connecting again; clear manual disconnect suppression
    manualDisconnectByPanel[formKey] = false;
    // Safe to clear any stale reconnect timer state
    if (reconnectTimerId){
      clearTimeout(reconnectTimerId);
      reconnectTimerId = null;
    }
    panelStates[formKey] = form.isServer ? 'listening' : 'connecting';
    updateGlobalStatusSummary();
    updateActiveRoleSummary();
    syncConnectionButtons();
    if (!form.isServer){
      setTimeout(fetchModel, 1500);
    } else {
      const treeContainer = document.getElementById('tree');
      treeContainer.innerHTML = '';
      const msg = document.createElement('div');
      msg.style.padding = '20px';
      msg.style.color = '#666';
      msg.textContent = 'Waiting for WebSocket client to connect...';
      treeContainer.appendChild(msg);
    }
  } catch(e){
    panelStates[formKey] = 'not-connected';
    updateGlobalStatusSummary();
    updateActiveRoleSummary();
    stopConnectionPolling();
    console.error('connect failed', e);
    syncConnectionButtons();
  } finally {
    btn.disabled = false;
  }
}

bindConnectionValidation('clientServer');
bindConnectionValidation('serverClient');
document.getElementById('wsClientConnectBtn').addEventListener('click', () => handleConnectionButton('clientServer'));
document.getElementById('wsServerConnectBtn').addEventListener('click', () => handleConnectionButton('serverClient'));

document.getElementById('autoReconnectBtn').addEventListener('click', () => {
  autoReconnectEnabled = !autoReconnectEnabled;
  const btn = document.getElementById('autoReconnectBtn');
  btn.dataset.enabled = autoReconnectEnabled ? 'true' : 'false';
  btn.textContent = autoReconnectEnabled ? 'Disable Auto Reconnect' : 'Enable Auto Reconnect';
  if (autoReconnectEnabled){
    reconnectAttempt = 0;
    // Only schedule if previous state was connected and we are now disconnected due to remote closure
    if (!manualDisconnectByPanel.clientServer && panelStates.clientServer === 'connected'){
      scheduleReconnect();
    }
  }
});

function markLogicalDevicesOld(){
  // Update server-level badge to OLD
  const tree = document.getElementById('tree');
  const serverBadge = tree.querySelector('.node-title .badge');
  if (serverBadge) {
    serverBadge.classList.remove('ok','error','unexpected-response');
    serverBadge.classList.add('old');
    serverBadge.textContent = 'OLD';
  } else {
    // Create server badge if missing
    const serverTitle = tree.querySelector('.node-title');
    if (serverTitle) {
      const badge = document.createElement('span');
      badge.className = 'badge old';
      badge.textContent = 'OLD';
      serverTitle.appendChild(badge);
    }
  }
}


// Context menu for reading data values
let contextMenu = null;
let contextMenuTarget = null;

function createContextMenu(items) {
  // Remove existing menu if any
  if (contextMenu) {
    contextMenu.remove();
    contextMenu = null;
  }

  const menu = document.createElement('div');
  menu.id = 'contextMenu';
  menu.className = 'context-menu';
  menu.style.display = 'none';

  items.forEach(item => {
    const menuItem = document.createElement('div');
    menuItem.className = 'context-menu-item';
    menuItem.textContent = item.label;
    menuItem.addEventListener('click', () => {
      item.action();
      hideContextMenu();
    });
    menu.appendChild(menuItem);
  });

  document.body.appendChild(menu);
  contextMenu = menu;
  return menu;
}

async function showContextMenuForDataAttribute(e, objRef, fc) {
  e.preventDefault();
  e.stopPropagation();

  // For data attributes, show "Read Value" and "Write" options
  const menuItems = [
    {
      label: `Read Value [${fc.toUpperCase()}]`,
      action: () => readDataValue(objRef, fc)
    },
    {
      label: `Write Value [${fc.toUpperCase()}]`,
      action: () => showWriteValueDialog(objRef, fc)
    }
  ];

  const menu = createContextMenu(menuItems);

  menu.style.display = 'block';
  menu.style.left = e.pageX + 'px';
  menu.style.top = e.pageY + 'px';
}

async function showContextMenuForDataObject(e, objRef) {
  e.preventDefault();
  e.stopPropagation();

  // Immediately show a provisional menu with a loading indicator
  const provisionalMenu = createContextMenu([
    { label: 'Loading FCs…', action: () => {} }
  ]);
  provisionalMenu.style.display = 'block';
  provisionalMenu.style.left = e.pageX + 'px';
  provisionalMenu.style.top = e.pageY + 'px';

  const statusEl = document.getElementById('actionText');
  if (statusEl) {
    statusEl.textContent = `Fetching FCs for ${objRef}…`;
    statusEl.className = 'info fetching';
  }

  // Helper to replace menu contents
  const replaceMenu = (fcs) => {
    const items = (fcs && fcs.length ? fcs : ['mx','st','cf','dc','sp','sv','co']).map(fc => ({
      label: `Read DO [${fc.toUpperCase()}]`,
      action: () => readDataObject(objRef, fc)
    }));
    provisionalMenu.innerHTML = '';
    items.forEach(item => {
      const mi = document.createElement('div');
      mi.className = 'context-menu-item';
      mi.textContent = item.label;
      mi.addEventListener('click', () => { item.action(); hideContextMenu(); });
      provisionalMenu.appendChild(mi);
    });
  };

  try {
    // Primary approach: call /api/getfcs
    const res = await fetch('/api/getfcs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objRef })
    });
    const data = await res.json();
    let fcs = [];
    if (!data.error && Array.isArray(data.fcs) && data.fcs.length) {
      fcs = data.fcs;
    } else {
      // Fallback: derive FCs from data definition
      const parts = objRef.split('/');
      if (parts.length === 2) {
        const ld = parts[0];
        const lnAndPath = parts[1].split('.');
        if (lnAndPath.length >= 2) {
          const ln = lnAndPath[0];
          const doPath = lnAndPath.slice(1).join('.');
          const ddRes = await fetch(`/api/dodef/${encodeURIComponent(ld)}/${encodeURIComponent(ln)}/${encodeURIComponent(doPath)}`);
            try {
              const dd = await ddRes.json();
              if (dd && dd.dataAttributes && Array.isArray(dd.dataAttributes)) {
                const setFcs = new Set();
                dd.dataAttributes.forEach(da => { if (da && da.fc) setFcs.add(da.fc.toLowerCase()); });
                fcs = Array.from(setFcs);
              }
            } catch(e2){ /* ignore parse errors */ }
        }
      }
    }
    replaceMenu(fcs);
    if (statusEl) {
      statusEl.textContent = `Select FC for ${objRef}`;
      statusEl.className = 'info';
    }
  } catch(err) {
    // Replace with fallback list
    replaceMenu(['mx','st','cf','dc','sp','sv','co']);
    if (statusEl) {
      statusEl.textContent = `Fallback FC list for ${objRef}`;
      statusEl.className = 'warn';
    }
  }
}

function hideContextMenu() {
  if (contextMenu) {
    contextMenu.style.display = 'none';
  }
  contextMenuTarget = null;
}

// Context menu for reading data values
function updateTreeValueDisplay(objRef, valueData, isError = false) {
  console.log('[updateTreeValueDisplay] Called for:', objRef, 'isError:', isError, 'valueData:', valueData);

  // Find the tree value display span by objRef
  const treeValueSpan = document.querySelector(`.tree-value-display[data-obj-ref="${objRef}"]`);

  if (!treeValueSpan) {
    console.log('[updateTreeValueDisplay] Span not found for:', objRef);
    return;
  }

  console.log('[updateTreeValueDisplay] Found span for:', objRef);

  if (isError) {
    treeValueSpan.textContent = ` ✗ Error`;
    treeValueSpan.style.color = '#c62828';
    console.log('[updateTreeValueDisplay] Set error display');
    return;
  }

  // Helper to extract actual value from wrapped structure
  function extractActualValue(val) {
    // Handle wrapped format: [{data: {...}}]
    if (Array.isArray(val) && val.length > 0 && val[0] && val[0].data) {
      const dataObj = val[0].data;
      // If data is an object with a single key (the type), extract that value
      if (typeof dataObj === 'object' && !Array.isArray(dataObj)) {
        const keys = Object.keys(dataObj);
        if (keys.length === 1) {
          return dataObj[keys[0]];
        }
      }
      return dataObj;
    }
    return val;
  }

  // Check if this is a structured value
  if (Array.isArray(valueData) && valueData.length > 0) {
    const firstItem = valueData[0];

    if (firstItem && firstItem.data && Array.isArray(firstItem.data)) {
      if (firstItem.data.length === 2 &&
          typeof firstItem.data[0] === 'string' &&
          firstItem.data[0] === 'structure') {
        // This is a structured attribute - show dash
        treeValueSpan.textContent = '—';
        treeValueSpan.style.color = '#4caf50'; // Green
        return;
      }

      // Simple value - extract and display
      if (firstItem.data.length === 2 && typeof firstItem.data[0] === 'string') {
        const value = firstItem.data[1];
        // If ASN.1 TimeStamp object, convert to ISO
        let displayValue = value;
        if (value && typeof value === 'object' && typeof value.secondSinceEpoch === 'number') {
          displayValue = asn1TimeStampToISOString(value) || JSON.stringify(value);
        } else if (typeof value === 'number') {
          displayValue = value.toFixed(2);
        } else if (typeof value === 'boolean') {
          displayValue = value ? 'true' : 'false';
        } else if (typeof value === 'object') {
          // For complex objects (like quality), show clean JSON
          displayValue = JSON.stringify(value);
        }
        treeValueSpan.textContent = displayValue;
        treeValueSpan.style.color = '#4caf50'; // Green for successful read
        return;
      }
    }
  }

  // Default display - extract actual value if wrapped
  const actualValue = extractActualValue(valueData);
  treeValueSpan.textContent = JSON.stringify(actualValue);
  treeValueSpan.style.color = '#4caf50'; // Green
}

// Update value display for structured/simple values
function updateValueEntry(objRef, valueData, isError = false) {
  console.log('[updateValueEntry]', objRef);

  if (isError) {
    updateTreeValueDisplay(objRef, valueData, true);
  } else {
    // Check if this is a structured value (array with nested objects/values)
    if (Array.isArray(valueData) && valueData.length > 0) {
      const firstItem = valueData[0];

      // Check if this is API response format with data wrapper
      if (firstItem && firstItem.data && Array.isArray(firstItem.data)) {

        // Check if this is ASN.1 format: [typeString, dataObject]
        if (firstItem.data.length === 2 &&
            typeof firstItem.data[0] === 'string' &&
            firstItem.data[0] === 'structure' &&
            firstItem.data[1] && typeof firstItem.data[1] === 'object') {

          const structureData = firstItem.data[1];

          // Always update tree display for structured values
          updateTreeValueDisplay(objRef, valueData, isError);

          // Check if the structure has nested data array with components
          if (structureData.data && Array.isArray(structureData.data)) {
            // This is a structured value - use existing parseStructuredValue or model matching
            console.log('[updateValueEntry] Structured value detected for', objRef);
          }
          return;
        }

        // Simple value wrapped in data array - extract and display
        // Check if it's a type-value pair like ['float32', 123.45]
        if (firstItem.data.length === 2 && typeof firstItem.data[0] === 'string') {
          // Update tree display for simple values
          updateTreeValueDisplay(objRef, valueData, isError);
          return;
        }

        // Update tree display for other data
        updateTreeValueDisplay(objRef, valueData, isError);
        return;
      }
    }
    // For non-structured values
    updateTreeValueDisplay(objRef, valueData, isError);
  }
}

/**
 * Ensure the tree node for an object reference exists in the DOM.
 * This programmatically expands parent nodes by fetching definitions.
 *
 * @param {string} objRef - Object reference (e.g., "LD0/MMXU1.PhV.phsA.cVal.mag")
 * @returns {Promise<boolean>} - True if successfully ensured
 */
async function ensureTreeNodeExists(objRef) {
  console.log('[ensureTreeNodeExists] Ensuring node exists for:', objRef);

  // Parse the objRef: "LD0/MMXU1.PhV.phsA.cVal.mag"
  const parts = objRef.split('/');
  if (parts.length !== 2) return false;

  const ldInst = parts[0];
  const rest = parts[1].split('.');
  if (rest.length < 2) return false;

  const lnInst = rest[0];
  const ldlnKey = `${ldInst}/${lnInst}`;

  // We need to ensure that all parent data objects are expanded
    // Build path from root: PhV -> PhV.phsA -> PhV.phsA.cVal -> PhV.phsA.cVal.mag

    for (let i = 1; i < rest.length; i++) {
      const doPath = rest.slice(1, i + 1).join('.');
      const fullRef = `${ldlnKey}.${doPath}`;

      // Check if this node already has tree value display span (meaning it's been expanded)
      const treeSpan = document.querySelector(`.tree-value-display[data-obj-ref="${fullRef}"]`);
      if (treeSpan) {
        console.log('[ensureTreeNodeExists] Node already exists:', fullRef);
        continue;
      }    console.log('[ensureTreeNodeExists] Need to ensure node:', fullRef);

    // Try to fetch the definition and build the DOM
    // This will create the necessary value entries
    // Note: This may fail for DA sub-attributes (e.g., mxVal.f), which is expected
    // because sub-attributes don't have separate definitions - they're part of the parent DA
    try {
      const def = await fetchDoDefinition(ldlnKey, doPath);
      if (def) {
        // Build the DOM elements (this creates value entries)
        buildDoDetailsDom(def, fullRef);
        console.log('[ensureTreeNodeExists] Built DOM for:', fullRef);
      }
    } catch (e) {
      // This is expected for DA sub-attributes - they don't have separate DO definitions
      // They are created when the parent DA is processed by matchStructuredValueToModel
      console.log('[ensureTreeNodeExists] Path is likely a DA sub-attribute (no separate definition):', fullRef);
      // Don't treat this as an error - it's normal behavior
    }
  }

  return true;
}

/**
 * Match nested structured values using model subAttributes (no API call needed).
 *
 * @param {string} baseRef - Base reference for the parent attribute
 * @param {Array} valueComponents - Array of value tuples from ASN.1 structure
 * @param {Array} modelSubAttributes - Sub-attributes from the model
 * @param {string} fc - Functional constraint
 */
async function matchNestedStructure(baseRef, valueComponents, modelSubAttributes, fc) {
  console.log('[matchNestedStructure] Matching', baseRef, 'with', modelSubAttributes.length, 'sub-attributes');

  // NOTE: We don't call ensureTreeNodeExists here because:
  // - This function is called for DA sub-attributes, not DO nodes
  // - The parent DA value entry should already exist (created by the caller)
  // - Sub-attribute entries are created directly in this function

  for (let i = 0; i < Math.min(modelSubAttributes.length, valueComponents.length); i++) {
    const modelAttr = modelSubAttributes[i];
    const valueComponent = valueComponents[i];

    const elementName = modelAttr.name;
    if (!elementName) {
      console.warn('[matchNestedStructure] No name for sub-attribute at index', i);
      continue;
    }

    const subRef = `${baseRef}.${elementName}`;
    console.log(`[matchNestedStructure] Matching ${subRef} at position ${i}`);

    // Extract value from component (ASN.1 format: [type, data])
    let componentValue = valueComponent;
    if (Array.isArray(valueComponent) && valueComponent.length === 2) {
      const [type, data] = valueComponent;
      console.log(`[matchNestedStructure] Component type: ${type}, data:`, data);

      // Check if this is a nested structure
      if (type === 'structure' && data && typeof data === 'object' && data.data && Array.isArray(data.data)) {
        console.log(`[matchNestedStructure] ${subRef} is nested structure`);

        // Check if modelAttr has subAttributes
        if (modelAttr.hasStructure && modelAttr.subAttributes && modelAttr.subAttributes.length > 0) {
          console.log(`[matchNestedStructure] Recursing for ${subRef}`);
          await matchNestedStructure(subRef, data.data, modelAttr.subAttributes, fc);

          // Update tree display for structured attribute
          const treeValueSpan = document.querySelector(`.tree-value-display[data-obj-ref="${subRef}"]`);
          if (treeValueSpan) {
            treeValueSpan.textContent = '—';
            treeValueSpan.style.color = '#4caf50'; // Green
          }
        }
        continue;
      }

      componentValue = data;
    }

    // Update the tree display
    const treeValueSpan = document.querySelector(`.tree-value-display[data-obj-ref="${subRef}"]`);
    if (treeValueSpan) {
      let displayValue = componentValue;
      if (typeof componentValue === 'number') {
        displayValue = componentValue.toFixed(2);
      } else if (typeof componentValue === 'boolean') {
        displayValue = componentValue ? 'true' : 'false';
      } else if (typeof componentValue === 'object') {
        displayValue = JSON.stringify(componentValue);
      }
      treeValueSpan.textContent = displayValue;
      treeValueSpan.style.color = '#4caf50'; // Green for successful read
    }
    console.log(`[matchNestedStructure] Updated tree display for ${subRef} with value:`, componentValue);
  }
}

/**
 * Match structured value data to model structure and update sub-attribute values.
 * Fetches the model definition for the attribute and correlates value arrays by position.
 *
 * @param {string} objRef - Object reference (e.g., "LD0/MMXU1.PhV.phsA.cVal")
 * @param {Array} valueComponents - Array of value tuples from ASN.1 structure
 * @param {string} fc - Functional constraint
 * @returns {Promise<boolean>} - True if successful
 */
async function matchStructuredValueToModel(objRef, valueComponents, fc) {
  try {
    console.log('[matchStructuredValueToModel] Fetching model for', objRef);

    // Parse objRef to construct the API URL
    // Format: "LD0/MMXU1.PhV.phsA.cVal"
    // We need to get the parent DO definition (PhV.phsA) and look for cVal in its dataAttributes
    const parts = objRef.split('/');
    if (parts.length !== 2) {
      console.error('[matchStructuredValueToModel] Invalid objRef format:', objRef);
      return false;
    }

    const ldInst = parts[0];
    const rest = parts[1].split('.');
    if (rest.length < 2) {
      console.error('[matchStructuredValueToModel] Invalid objRef format:', objRef);
      return false;
    }

    const lnInst = rest[0];

    console.log('[matchStructuredValueToModel] Parsing:', objRef);
    console.log('[matchStructuredValueToModel] - ldInst:', ldInst);
    console.log('[matchStructuredValueToModel] - lnInst:', lnInst);
    console.log('[matchStructuredValueToModel] - rest:', rest);

    // Determine if this is a nested DA sub-attribute (e.g., "cVal.mag")
    // by checking if there are more than 2 parts after LN
    // Format: LN.DO[.SDO]*.DA[.SubDA]*
    // Example: "MMXU1.PhV.phsA.cVal.mag" -> LN=MMXU1, DO path=PhV.phsA, DA=cVal, SubDA=mag

    // Strategy: Try from shortest to longest DO path
    // Start with just one level (e.g., "PhV"), then try two levels ("PhV.phsB"), etc.
    // DOs typically have 1-3 levels, DAs come after
    let modelData = null;
    let doPath = null;
    let daPath = [];

    // Try different combinations: start with shortest DO path and work forwards
    for (let i = 2; i <= rest.length; i++) {
      doPath = rest.slice(1, i).join('.');
      daPath = rest.slice(i);

      // We need at least one DA component
      if (daPath.length === 0) continue;

      const url = `/api/dodef/${ldInst}/${lnInst}/${doPath}`;
      console.log('[matchStructuredValueToModel] Trying URL:', url, '(DA path:', daPath, ')');

      try {
        const response = await fetch(url);
        if (response.ok) {
          const data = await response.json();
          // Make sure we got actual data attributes
          if (data.dataAttributes && data.dataAttributes.length > 0) {
            modelData = data;
            console.log('[matchStructuredValueToModel] Success! Found model at DO path:', doPath);
            console.log('[matchStructuredValueToModel] DA path:', daPath);
            break;
          } else {
            console.log('[matchStructuredValueToModel] No data attributes at:', doPath);
          }
        }
      } catch (e) {
        console.log('[matchStructuredValueToModel] Error fetching:', url, e.message);
      }
    }

    if (!modelData) {
      console.error('[matchStructuredValueToModel] Could not fetch model for any DO path');
      return false;
    }

    console.log('[matchStructuredValueToModel] Model data:', modelData);

    // Now navigate through the DA path to find the structured attribute
    let structuredAttr = null;
    let currentAttrs = modelData.dataAttributes || [];

    for (let i = 0; i < daPath.length; i++) {
      const daName = daPath[i];
      console.log('[matchStructuredValueToModel] Looking for DA:', daName, 'in', currentAttrs.length, 'attributes');

      let foundAttr = null;
      for (const da of currentAttrs) {
        if (da.daRef === daName || da.name === daName) {
          foundAttr = da;
          break;
        }
      }

      if (!foundAttr) {
        console.warn('[matchStructuredValueToModel] Could not find attribute:', daName);
        return false;
      }

      // If this is the last DA in the path, this is our target
      if (i === daPath.length - 1) {
        structuredAttr = foundAttr;
      } else {
        // Navigate deeper into sub-attributes
        if (foundAttr.subAttributes && foundAttr.subAttributes.length > 0) {
          currentAttrs = foundAttr.subAttributes;
        } else {
          console.warn('[matchStructuredValueToModel] Attribute has no sub-attributes:', daName);
          return false;
        }
      }
    }

    if (!structuredAttr) {
      console.warn('[matchStructuredValueToModel] Could not find structured attribute');
      return false;
    }

    const subAttributes = structuredAttr.subAttributes;
    console.log('[matchStructuredValueToModel] Sub-attributes from model:', subAttributes);

    if (subAttributes.length === 0) {
      console.warn('[matchStructuredValueToModel] No sub-attributes in model');
      return false;
    }

    // Ensure the tree node exists for the base attribute
    await ensureTreeNodeExists(objRef);

    // Match values to model by position
    const valueColumn = document.getElementById('valueColumn');

    for (let i = 0; i < Math.min(subAttributes.length, valueComponents.length); i++) {
      const modelAttr = subAttributes[i];
      const valueComponent = valueComponents[i];

      const elementName = modelAttr.name;
      if (!elementName) {
        console.warn('[matchStructuredValueToModel] No name for sub-attribute at index', i);
        continue;
      }

      const subRef = `${objRef}.${elementName}`;
      console.log(`[matchStructuredValueToModel] Matching ${subRef} at position ${i}`);

      // NOTE: We don't call ensureTreeNodeExists for DA sub-attributes
      // because they are not separate Data Objects - they are part of the parent DA
      // The value entry should be created directly here

      // Get or create value entry
      let entry = valueRegistry.get(subRef);
      if (!entry) {
        console.log(`[matchStructuredValueToModel] Creating entry for ${subRef}`);
        const valueDiv = createValueEntry(subRef, fc);
        valueColumn.appendChild(valueDiv);
        // Register the entry in the valueRegistry
        valueRegistry.set(subRef, {element: valueDiv, fc: fc});
        entry = valueRegistry.get(subRef);
      }

      if (!entry) {
        console.error('[matchStructuredValueToModel] Failed to create entry for', subRef);
        continue;
      }

      // Extract value from component (ASN.1 format: [type, data])
      let componentValue = valueComponent;
      if (Array.isArray(valueComponent) && valueComponent.length === 2) {
        const [type, data] = valueComponent;
        console.log(`[matchStructuredValueToModel] Component type: ${type}, data:`, data);

        // Check if this is a nested structure
        if (type === 'structure' && data && typeof data === 'object' && data.data && Array.isArray(data.data)) {
          console.log(`[matchStructuredValueToModel] ${subRef} is nested structure`);

          // Check if modelAttr has subAttributes (nested structure in model)
          if (modelAttr.hasStructure && modelAttr.subAttributes && modelAttr.subAttributes.length > 0) {
            console.log(`[matchStructuredValueToModel] Matching nested structure for ${subRef}`);
            // Recursively match nested structure using the model's subAttributes
            await matchNestedStructure(subRef, data.data, modelAttr.subAttributes, fc);
            const dataSpan = entry.element.querySelector('.value-data');
            dataSpan.textContent = '—';
            dataSpan.style.color = 'var(--text-muted, #999)';

            // Update tree display for structured attribute
            const treeValueSpan = document.querySelector(`.tree-value-display[data-obj-ref="${subRef}"]`);
            if (treeValueSpan) {
              treeValueSpan.textContent = '—';
              treeValueSpan.style.color = '#4caf50'; // Green
            }
          } else {
            console.warn(`[matchStructuredValueToModel] No nested structure info in model for ${subRef}`);
            const dataSpan = entry.element.querySelector('.value-data');
            dataSpan.textContent = '(structure)';
            dataSpan.style.color = 'var(--text-muted, #888)';
          }
          continue;
        }

        componentValue = data;
      }

      // Update the value display in value column
      const dataSpan = entry.element.querySelector('.value-data');
      if (typeof componentValue === 'object' && componentValue !== null) {
        dataSpan.textContent = JSON.stringify(componentValue);
      } else {
        dataSpan.textContent = String(componentValue);
      }
      dataSpan.style.color = 'var(--text-dark)';
      console.log(`[matchStructuredValueToModel] Updated ${subRef} with value:`, componentValue);

      // Also update the tree display
      const treeValueSpan = document.querySelector(`.tree-value-display[data-obj-ref="${subRef}"]`);
      if (treeValueSpan) {
        let displayValue = componentValue;
        if (typeof componentValue === 'number') {
          displayValue = componentValue.toFixed(2);
        } else if (typeof componentValue === 'boolean') {
          displayValue = componentValue ? 'true' : 'false';
        } else if (typeof componentValue === 'object') {
          displayValue = JSON.stringify(componentValue);
        }
        treeValueSpan.textContent = displayValue;
        treeValueSpan.style.color = '#4caf50'; // Green for successful read
      }
    }

    return true;

  } catch (error) {
    console.error('[matchStructuredValueToModel] Error:', error);
    return false;
  }
}

function parseStructuredValue(baseRef, valueData) {
  /**
   * Parse structured data value and update tree inline displays for sub-attributes.
   * Returns {isStructured: boolean} to indicate if this was a structure.
   *
   * Value format from API: [{name: 'attrName', data: [...]}]
   * For structured attributes, data contains sub-components with elementName
   */
  if (!Array.isArray(valueData) || valueData.length === 0) {
    return {isStructured: false};
  }

  console.log('[parseStructuredValue]', baseRef, valueData);
  let isStructured = false;

  // Iterate through value array
  for (const item of valueData) {
    if (typeof item === 'object' && item !== null) {
      // Check if this has 'data' object (Report format: {data: {structure: {data: [...]}}})
      if (item.data && typeof item.data === 'object' && !Array.isArray(item.data)) {
        console.log('[parseStructuredValue] Detected data object:', Object.keys(item.data));

        if (item.data.structure && item.data.structure.data && Array.isArray(item.data.structure.data)) {
          console.log('[parseStructuredValue] Detected Report structure format for', baseRef);
          const components = item.data.structure.data;
          console.log('[parseStructuredValue] Structure components:', JSON.stringify(components));

          // Mark parent as structured (show "—")
          const parentSpan = document.querySelector(`.tree-value-display[data-obj-ref="${baseRef}"]`);
          if (parentSpan) {
            parentSpan.textContent = '—';
            parentSpan.style.color = 'var(--text-muted, #999)';
          }

          // Process each component - these are primitives without elementName
          // We need to map them by position to known sub-attributes
          // For CDC types like mag, the order is typically: f, then potentially others
          const knownSubAttrs = ['f', 'i']; // Common for AnalogueValue (mag)

          for (let i = 0; i < components.length; i++) {
            const component = components[i];
            console.log('[parseStructuredValue] Processing component:', component);

            if (typeof component === 'object' && !Array.isArray(component)) {
              // This is a primitive type object like {float32: 0}, {quality: {...}}, {timeStamp: {...}}
              const typeKeys = Object.keys(component);
              if (typeKeys.length === 1) {
                const typeName = typeKeys[0];
                const value = component[typeName];
                const subAttrName = knownSubAttrs[i] || `attr${i}`;
                const subRef = `${baseRef}.${subAttrName}`;

                console.log('[parseStructuredValue] Mapped', typeName, 'to', subRef, 'value:', value);

                // Update tree span for sub-attribute
                let treeSpan = document.querySelector(`.tree-value-display[data-obj-ref="${subRef}"]`);
                if (treeSpan) {
                  let displayValue = value;
                  if (typeof value === 'number') {
                    displayValue = value.toFixed(2);
                  } else if (typeof value === 'boolean') {
                    displayValue = value ? 'true' : 'false';
                  } else if (value && typeof value === 'object') {
                    // Check for timestamp
                    if (typeof value.secondSinceEpoch === 'number') {
                      displayValue = asn1TimeStampToISOString(value) || JSON.stringify(value);
                    } else {
                      displayValue = JSON.stringify(value);
                    }
                  }
                  treeSpan.textContent = displayValue;
                  treeSpan.style.color = '#4caf50';
                  console.log('[parseStructuredValue] Updated', subRef, 'with', displayValue);
                }
              }
            }
          }

          isStructured = true;
          continue; // Skip to next item
        }

        // Check for direct types like quality, timeStamp (Report format: {data: {quality: {...}}})
        const dataKeys = Object.keys(item.data);
        if (dataKeys.length === 1) {
          const typeName = dataKeys[0];
          const value = item.data[typeName];

          // Update the tree span for this baseRef directly
          const treeSpan = document.querySelector(`.tree-value-display[data-obj-ref="${baseRef}"]`);
          if (treeSpan) {
            let displayValue = value;
            if (typeName === 'timeStamp' && value && typeof value.secondSinceEpoch === 'number') {
              displayValue = asn1TimeStampToISOString(value) || JSON.stringify(value);
            } else if (typeof value === 'object') {
              displayValue = JSON.stringify(value);
            } else if (typeof value === 'number') {
              displayValue = value.toFixed(2);
            } else if (typeof value === 'boolean') {
              displayValue = value ? 'true' : 'false';
            }
            treeSpan.textContent = displayValue;
            treeSpan.style.color = '#4caf50';
            console.log('[parseStructuredValue] Updated', baseRef, 'with direct type', typeName, ':', displayValue);
          }
          continue; // Skip to next item
        }
      }

      // Check if this has 'data' array (API response wrapper)
      if (item.data && Array.isArray(item.data)) {

        // Check if this is ASN.1 format: ['structure', {data: [...]}]
        if (item.data.length === 2 &&
            typeof item.data[0] === 'string' &&
            item.data[0] === 'structure' &&
            item.data[1] && typeof item.data[1] === 'object' &&
            item.data[1].data && Array.isArray(item.data[1].data)) {

          console.log('[parseStructuredValue] Detected ASN.1 structure, parsing components');
          const components = item.data[1].data;
          console.log('[parseStructuredValue] Components:', components);

          // Parse each component (each is a tuple: ['structure', {elementName, value}])
          let foundElementName = false;
          for (const component of components) {
            console.log('[parseStructuredValue] Processing component:', component, 'isArray:', Array.isArray(component));
            if (Array.isArray(component) && component.length === 2 &&
                typeof component[0] === 'string' && component[1] &&
                typeof component[1] === 'object') {

              const componentData = component[1];
              console.log('[parseStructuredValue] Component data:', componentData, 'keys:', Object.keys(componentData));
              const elementName = componentData.elementName;

              if (elementName) {
                isStructured = true;
                const subRef = `${baseRef}.${elementName}`;
                const subValue = componentData.value !== undefined ? componentData.value : componentData.data;

                console.log('[parseStructuredValue] Found component:', elementName, 'subRef:', subRef, 'value:', subValue);

                // Update tree inline span - create if missing
                let treeSpan = document.querySelector(`.tree-value-display[data-obj-ref="${subRef}"]`);
                if (!treeSpan) {
                  const label = document.querySelector(`span.data-item[data-obj-ref="${subRef}"]`);
                  if (label) {
                    treeSpan = document.createElement('span');
                    treeSpan.className = 'tree-value-display';
                    treeSpan.dataset.objRef = subRef;
                    label.appendChild(treeSpan);
                  }
                }

                if (treeSpan) {
                  // Check if this is also a structure that needs recursive parsing
                  if (Array.isArray(subValue) && subValue.length === 2 &&
                      subValue[0] === 'structure' && subValue[1] && subValue[1].data) {
                    // Recursively parse nested structure
                    parseStructuredValue(subRef, [{data: subValue}]);
                    treeSpan.textContent = '—';
                    treeSpan.style.color = 'var(--text-muted, #999)';
                  } else {
                    // Extract actual value from wrapper if needed
                    let actualValue = subValue;

                    // Handle format: [{data: {typeName: actualValue}}]
                    if (Array.isArray(subValue) && subValue.length > 0 && subValue[0] && subValue[0].data) {
                      const dataObj = subValue[0].data;
                      if (typeof dataObj === 'object' && !Array.isArray(dataObj)) {
                        const keys = Object.keys(dataObj);
                        // Extract the value if there's a single type key (float32, quality, timeStamp, etc.)
                        if (keys.length === 1) {
                          actualValue = dataObj[keys[0]];
                        }
                      }
                    }

                    // Format and display the value
                    let displayValue = actualValue;
                    if (actualValue && typeof actualValue === 'object') {
                      if (typeof actualValue.secondSinceEpoch === 'number') {
                        displayValue = asn1TimeStampToISOString(actualValue) || JSON.stringify(actualValue);
                      } else {
                        displayValue = JSON.stringify(actualValue);
                      }
                    } else if (typeof actualValue === 'number') {
                      displayValue = actualValue.toFixed(2);
                    } else if (typeof actualValue === 'boolean') {
                      displayValue = actualValue ? 'true' : 'false';
                    }
                    treeSpan.textContent = displayValue;
                    treeSpan.style.color = '#4caf50';
                    console.log('[parseStructuredValue] Updated tree span for', subRef, 'with', displayValue);
                  }
                }
                foundElementName = true;
              }
            }
          }

          // If no elementName objects found and first primitive tuple exists, map it to baseRef
          if (!foundElementName) {
            const prim = components.find(c => Array.isArray(c) && c.length === 2 && typeof c[0] === 'string' && (typeof c[1] !== 'object'));
            if (prim) {
              const primVal = prim[1];
              let display = primVal;
              if (typeof primVal === 'number') display = primVal.toFixed(2);
              const baseTreeSpan = document.querySelector(`.tree-value-display[data-obj-ref="${baseRef}"]`);
              if (baseTreeSpan) {
                baseTreeSpan.textContent = display;
                baseTreeSpan.style.color = '#4caf50';
                console.log('[parseStructuredValue] Updated base tree span for', baseRef, 'with', display);
              }
            }
          }
          continue;
        }

        // Look inside the data array for structured components (old format)
        for (const dataItem of item.data) {
          if (typeof dataItem === 'object' && dataItem !== null) {
            const elementName = dataItem.elementName;
            if (elementName) {
              isStructured = true;
              const subRef = `${baseRef}.${elementName}`;
              const subValue = dataItem.value !== undefined ? dataItem.value : dataItem.data;

              console.log('[parseStructuredValue] Found sub-component:', elementName, 'subRef:', subRef, 'value:', subValue);

              // Update tree inline span - create if missing
              let treeSpan = document.querySelector(`.tree-value-display[data-obj-ref="${subRef}"]`);
              if (!treeSpan) {
                const label = document.querySelector(`span.data-item[data-obj-ref="${subRef}"]`);
                if (label) {
                  treeSpan = document.createElement('span');
                  treeSpan.className = 'tree-value-display';
                  treeSpan.dataset.objRef = subRef;
                  label.appendChild(treeSpan);
                }
              }

              if (treeSpan) {
                // Check if the sub-value is also structured (array with elementName items)
                if (Array.isArray(subValue)) {
                  const subParsed = parseStructuredValue(subRef, [{data: subValue}]);
                  if (!subParsed.isStructured) {
                    // Leaf array value - display the values
                    treeSpan.textContent = JSON.stringify(subValue);
                    treeSpan.style.color = '#4caf50';
                    console.log('[parseStructuredValue] Set leaf array value for tree span', subRef);
                  } else {
                    // Nested structure - show placeholder
                    treeSpan.textContent = '—';
                    treeSpan.style.color = 'var(--text-muted, #999)';
                    console.log('[parseStructuredValue] Set placeholder for nested structure', subRef);
                  }
                } else {
                  // Format and display the value
                  let displayValue = subValue;
                  if (subValue && typeof subValue === 'object') {
                    if (typeof subValue.secondSinceEpoch === 'number') {
                      displayValue = asn1TimeStampToISOString(subValue) || JSON.stringify(subValue);
                    } else {
                      displayValue = JSON.stringify(subValue);
                    }
                  } else if (typeof subValue === 'number') {
                    displayValue = subValue.toFixed(2);
                  } else if (typeof subValue === 'boolean') {
                    displayValue = subValue ? 'true' : 'false';
                  }
                  treeSpan.textContent = displayValue;
                  treeSpan.style.color = '#4caf50';
                  console.log('[parseStructuredValue] Updated tree span for', subRef, 'with', displayValue);
                }
              }
            }
          }
        }
      }
    }
  }

  return {isStructured};
}

/**
 * Ensure that a DA tree node is expanded so its sub-attribute spans exist in the DOM.
 * For example, if objRef is "LD0/MMXU1.PhV.phsA.cVal.mag.f", we need to ensure
 * that "LD0/MMXU1.PhV.phsA.cVal.mag" is expanded in the tree.
 */
async function ensureDaTreeNodeExpanded(objRef) {
  console.log('[ensureDaTreeNodeExpanded] Checking:', objRef);

  // Check if the tree value display span already exists
  const existingSpan = document.querySelector(`.tree-value-display[data-obj-ref="${objRef}"]`);
  if (existingSpan) {
    console.log('[ensureDaTreeNodeExpanded] Span already exists for:', objRef);
    return;
  }

  // Parse: "LD0/MMXU1.PhV.phsA.cVal.mag.f" -> parent is "LD0/MMXU1.PhV.phsA.cVal.mag"
  const parts = objRef.split('/');
  if (parts.length !== 2) return;

  const ldInst = parts[0];
  const rest = parts[1].split('.');

  // If there are at least 3 parts after LN (e.g., "PhV.phsA.cVal.mag.f" -> 5 parts),
  // we likely have a nested sub-attribute
  if (rest.length < 3) return; // Not a nested sub-attribute

  // Find the parent DA value span in the tree
  const parentRef = `${ldInst}/${rest.slice(0, rest.length - 1).join('.')}`;
  console.log('[ensureDaTreeNodeExpanded] Looking for parent:', parentRef);

  // Find the parent's tree value display span
  const parentSpan = document.querySelector(`.tree-value-display[data-obj-ref="${parentRef}"]`);
  if (!parentSpan) {
    console.log('[ensureDaTreeNodeExpanded] Parent span not found, recursively ensuring parent:', parentRef);
    // Recursively ensure parent is expanded
    await ensureDaTreeNodeExpanded(parentRef);
    // Try again to find the parent span
    const parentSpanRetry = document.querySelector(`.tree-value-display[data-obj-ref="${parentRef}"]`);
    if (!parentSpanRetry) {
      console.log('[ensureDaTreeNodeExpanded] Still cannot find parent span after recursion');
      return;
    }
  }

  // Find the expand button near the parent span
  // The structure is: <li><div><button class="inline-expand">+</button><span>...</span><div class="subWrap"></div></div></li>
  const parentLi = parentSpan.closest('li');
  if (!parentLi) {
    console.log('[ensureDaTreeNodeExpanded] Cannot find parent <li>');
    return;
  }

  const expandBtn = parentLi.querySelector('button.inline-expand');
  if (!expandBtn) {
    console.log('[ensureDaTreeNodeExpanded] No expand button found for parent');
    return;
  }

  // Check if already expanded (button shows '-' when expanded)
  if (expandBtn.textContent === '-') {
    console.log('[ensureDaTreeNodeExpanded] Parent already expanded');
    return;
  }

  // Click to expand
  console.log('[ensureDaTreeNodeExpanded] Clicking expand button for:', parentRef);
  expandBtn.click();

  // Wait for DOM update
  await new Promise(resolve => setTimeout(resolve, 100));

  // Verify the span now exists
  const verifySpan = document.querySelector(`.tree-value-display[data-obj-ref="${objRef}"]`);
  if (verifySpan) {
    console.log('[ensureDaTreeNodeExpanded] Successfully created span for:', objRef);
  } else {
    console.log('[ensureDaTreeNodeExpanded] Failed to create span for:', objRef);
  }
}

async function readDataValue(objRef, fc) {
  console.log('[readDataValue] Reading:', objRef, 'FC:', fc);
  const statusEl = document.getElementById('actionText');
  statusEl.textContent = `Reading ${objRef} [${fc}]...`;
  statusEl.className = 'info fetching';

  // Ensure the tree node exists in the DOM before reading
  // This is needed for nested attributes that might not be expanded yet
  await ensureTreeNodeExists(objRef);

  // For nested DA sub-attributes (e.g., "mag.f" in "LD0/MMXU1.PhV.phsA.cVal.mag.f"),
  // we need to ensure the parent DA tree node is expanded so the span exists
  await ensureDaTreeNodeExpanded(objRef);

  try {
    const res = await fetch('/api/readvalue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objRef, fc })
    });

    const data = await res.json();
    console.log('[readDataValue] Response:', data);

    if (data.error) {
      statusEl.textContent = `Error reading ${objRef}: ${data.error}`;
      statusEl.className = 'error';
      updateTreeValueDisplay(objRef, data.error, true);
    } else {
      // Format the values for display
      const valueStr = JSON.stringify(data.values, null, 2);
      statusEl.textContent = `${objRef} [${fc}]: ${valueStr}`;
      statusEl.className = 'info';
      console.log('[readDataValue] Updating tree display for:', objRef, data.values);
      updateTreeValueDisplay(objRef, data.values, false);
    }
  } catch (e) {
    console.error('[readDataValue] Exception:', e);
    statusEl.textContent = `Exception reading ${objRef}: ${e.message}`;
    statusEl.className = 'error';
    updateTreeValueDisplay(objRef, e.message, true);
  }
}

/**
 * Extract all primitive values from ASN.1 response data in depth-first order.
 * Recursively traverses structures and collects leaf primitive values.
 *
 * @param {Array} values - Response values array from getDataValues
 * @returns {Array} - Ordered array of primitive values
 */
function extractPrimitivesInOrder(values) {
  const primitives = [];

  function extractFromData(data) {
    if (!Array.isArray(data)) return;

    // Check if this is a type-value pair: ['typeName', value]
    if (data.length === 2 && typeof data[0] === 'string') {
      const typeName = data[0];
      const value = data[1];

      // If it's a structure, recurse into its data array
      if (typeName === 'structure' && value && typeof value === 'object' && Array.isArray(value.data)) {
        // Recurse into each element of the nested structure
        value.data.forEach(nestedData => {
          extractFromData(nestedData);
        });
      } else if (typeof value !== 'object' || value === null || typeof value.secondSinceEpoch === 'number') {
        // Primitive value or timestamp - add to collection
        primitives.push(value);
      } else {
        // Complex object (like Quality) - treat as primitive
        primitives.push(value);
      }
    }
  }

  function extractFromItem(item) {
    if (!item || !item.data) return;
    extractFromData(item.data);
  }

  if (Array.isArray(values)) {
    values.forEach(extractFromItem);
  }

  return primitives;
}

/**
 * Flatten model dataAttributes structure to ordered leaf paths.
 * Returns array of {ref: string, fc: string} objects for each leaf attribute
 * in depth-first traversal order.
 *
 * @param {Array} dataAttributes - Array of attribute definitions from model
 * @param {string} baseRef - Base object reference (e.g., "LD0/MMXU1.PhV")
 * @returns {Array} - Ordered array of {ref, fc} leaf paths
 */
function flattenModelToLeafPaths(dataAttributes, baseRef) {
  const leafPaths = [];

  function traverse(attrs, parentRef, parentFc) {
    if (!Array.isArray(attrs)) return;

    attrs.forEach(attr => {
      const attrName = attr.daRef || attr.name;
      if (!attrName) return;

      const attrRef = `${parentRef}.${attrName}`;
      const attrFc = attr.fc || parentFc || 'mx';

      // Check if this attribute has nested structure
      if (attr.hasStructure && attr.subAttributes && Array.isArray(attr.subAttributes) && attr.subAttributes.length > 0) {
        // Recurse into sub-attributes
        traverse(attr.subAttributes, attrRef, attrFc);
      } else {
        // Leaf attribute - add to paths
        leafPaths.push({ref: attrRef, fc: attrFc});
      }
    });
  }

  traverse(dataAttributes, baseRef, 'mx');
  return leafPaths;
}

/**
 * Ensure the path to a nested attribute is expanded in the tree.
 * Expands parent structures so the target element exists in the DOM.
 *
 * @param {string} targetRef - Full reference to target attribute (e.g., "LD0/MMXU1.PhV.phsA.cVal.mag.f")
 * @param {string} baseRef - Base DO reference (e.g., "LD0/MMXU1.PhV")
 * @param {string} fc - Functional constraint
 */
async function ensurePathExpanded(targetRef, baseRef, fc) {
  // Parse target to get intermediate paths
  // Example: targetRef = "LD0/MMXU1.PhV.phsA.cVal.mag.f"
  //          baseRef = "LD0/MMXU1.PhV"
  // We need to expand: PhV.phsA, PhV.phsA.cVal, PhV.phsA.cVal.mag

  const [ldPart, targetRest] = targetRef.split('/');
  const [, baseRest] = baseRef.split('/');

  if (!ldPart || !targetRest || !baseRest) return;

  const targetParts = targetRest.split('.');
  const baseParts = baseRest.split('.');

  // Find how many parts are shared (should be at least LN + DO)
  let sharedCount = 0;
  for (let i = 0; i < Math.min(targetParts.length, baseParts.length); i++) {
    if (targetParts[i] === baseParts[i]) {
      sharedCount++;
    } else {
      break;
    }
  }

  // Expand each intermediate level
  for (let i = sharedCount; i < targetParts.length - 1; i++) {
    const intermediatePath = `${ldPart}/${targetParts.slice(0, i + 1).join('.')}`;

    // Find expand button for this path
    const btn = document.querySelector(`span.data-item[data-obj-ref="${intermediatePath}"] button.inline-expand`);
    if (btn && btn.dataset.state === 'collapsed') {
      console.log('[ensurePathExpanded] Expanding:', intermediatePath);
      btn.click();
      // Allow DOM to update
      await new Promise(resolve => setTimeout(resolve, 50));
    }
  }
}

/**
 * Update tree inline display for an attribute.
 * Creates tree value span if it doesn't exist.
 *
 * @param {string} ref - Attribute reference
 * @param {*} rawVal - Raw value to display
 * @param {string} fcLocal - Functional constraint (not used for tree display, kept for compatibility)
 */
function updateTreeAndValue(ref, rawVal, fcLocal) {
  // Tree span
  let treeSpan = document.querySelector(`.tree-value-display[data-obj-ref="${ref}"]`);
  if (!treeSpan) {
    const label = document.querySelector(`span.data-item[data-obj-ref="${ref}"]`);
    if (label) {
      treeSpan = document.createElement('span');
      treeSpan.className = 'tree-value-display';
      treeSpan.dataset.objRef = ref;
      label.appendChild(treeSpan);
    }
  }
  if (treeSpan) {
    treeSpan.textContent = formatDisplayValue(rawVal);
    treeSpan.style.color = '#4caf50';
  }
}

/**
 * Format a value for display (handles timestamps, numbers, booleans, objects)
 *
 * @param {*} v - Value to format
 * @returns {string} - Formatted display string
 */
function formatDisplayValue(v) {
  if (v && typeof v === 'object') {
    if (typeof v.secondSinceEpoch === 'number') {
      return asn1TimeStampToISOString(v) || JSON.stringify(v);
    }
    return JSON.stringify(v);
  }
  if (typeof v === 'number') return v.toFixed(2);
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  return String(v);
}

// Read a Data Object (or SubDataObject path) with a selected FC and update sub-elements
async function readDataObject(objRef, fc) {
  console.log('[readDataObject] Reading DO:', objRef, 'FC:', fc);
  const statusEl = document.getElementById('actionText');
  statusEl.textContent = `Reading DO ${objRef} [${fc}]...`;
  statusEl.className = 'info fetching';

  await ensureTreeNodeExists(objRef);
  // Ensure all parent DO/SubDO nodes are expanded so tree-value-display spans exist
  await expandDoChain(objRef);
  try {
    const res = await fetch('/api/readvalue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objRef, fc })
    });
    const data = await res.json();
    console.log('[readDataObject] Response:', data);
    if (data.error) {
      statusEl.textContent = `Error reading DO ${objRef}: ${data.error}`;
      statusEl.className = 'error';
      return;
    }
    statusEl.textContent = `DO ${objRef} [${fc}] read.`;
    statusEl.className = 'info';

    // Update tree display for the DO itself
    updateTreeValueDisplay(objRef, data.values, false);

    // Parse structured components
    const firstItem = Array.isArray(data.values) ? data.values[0] : null;
    if (firstItem && firstItem.data && Array.isArray(firstItem.data)) {
      if (firstItem.data.length === 2 && typeof firstItem.data[0] === 'string' && firstItem.data[0] === 'structure') {
        const structureObj = firstItem.data[1];
        if (structureObj && structureObj.data && Array.isArray(structureObj.data)) {
          parseStructuredValue(objRef, [{data: firstItem.data}]);
        }
      } else {
        parseStructuredValue(objRef, data.values);
      }
    }

    // Additional direct mapping: fetch definition and correlate elementName values to DA/SubDA spans
    try {
      // Properly split objRef: LD0/MMXU1.TotW => ldlnKey=LD0/MMXU1, doPath=TotW (and nested path if deeper)
      const [ldPart, restPart] = objRef.split('/');
      if (ldPart && restPart) {
        const lnAndDo = restPart.split('.');
        if (lnAndDo.length >= 2) {
          const lnInst = lnAndDo[0];
          const doPath = lnAndDo.slice(1).join('.');
          const ldlnKey = `${ldPart}/${lnInst}`;
          await fetchDoDefinition(ldlnKey, doPath); // caches definition if available
        }
      }
    } catch(e){ /* silent */ }

    // Generic model-driven mapping using DO definition structure
    // Check if response contains elementName metadata
    let hasElementNames = false;
    if (Array.isArray(data.values)) {
      hasElementNames = data.values.some(v => v && v.data && Array.isArray(v.data) && v.data.some(c => c && typeof c === 'object' && c.elementName));
    }

    if (!hasElementNames) {
      // Fetch DO definition to get model structure
      const [ldPart, restPart] = objRef.split('/');
      if (ldPart && restPart) {
        const lnAndDo = restPart.split('.');
        if (lnAndDo.length >= 2) {
          const lnInst = lnAndDo[0];
          const doPath = lnAndDo.slice(1).join('.');
          const ldlnKey = `${ldPart}/${lnInst}`;
          let def = null;
          try { def = await fetchDoDefinition(ldlnKey, doPath); } catch(e) {}

          if (def && Array.isArray(def.dataAttributes)) {
            console.log('[readDataObject] DO definition:', def);
            console.log('[readDataObject] Response values:', data.values);

            // Extract all primitives from response in order
            const primitiveValues = extractPrimitivesInOrder(data.values);
            console.log('[readDataObject] Extracted primitives:', primitiveValues);

            // Flatten model structure to ordered leaf paths
            const allLeafPaths = flattenModelToLeafPaths(def.dataAttributes, objRef);
            console.log('[readDataObject] All leaf paths from model:', allLeafPaths);

            // Filter leaf paths to only those matching the requested FC
            const leafPaths = allLeafPaths.filter(lp => lp.fc && lp.fc.toLowerCase() === fc.toLowerCase());
            console.log('[readDataObject] Filtered leaf paths for FC=' + fc + ':', leafPaths);

            // Map primitives to leaf paths by position
            for (let i = 0; i < Math.min(primitiveValues.length, leafPaths.length); i++) {
              const primitive = primitiveValues[i];
              const leafPath = leafPaths[i];

              console.log(`[readDataObject] Mapping primitive[${i}] = ${primitive} to ${leafPath.ref}`);

              // Ensure parent structures are expanded
              await ensurePathExpanded(leafPath.ref, objRef, fc);

              // Update value
              updateTreeAndValue(leafPath.ref, primitive, fc);
            }
          }
        }
      }
    }

  } catch (e) {
    console.error('[readDataObject] Exception:', e);
    statusEl.textContent = `Exception reading DO ${objRef}: ${e.message}`;
    statusEl.className = 'error';
  }
}

/**
 * Expand the chain of Data Objects / SubDataObjects for a given objRef so that
 * tree-value-display spans are present before we attempt to populate them.
 * Example: LD0/MMXU1.PhV.phsA.cVal.mag -> expand PhV, then PhV.phsA, then PhV.phsA.cVal, then PhV.phsA.cVal.mag
 */
async function expandDoChain(objRef){
  try {
    const [ld, rest] = objRef.split('/');
    if (!ld || !rest) return;
    const parts = rest.split('.');
    if (parts.length < 2) return; // need at least LN.DO
    const ln = parts[0];
    const ldlnKey = `${ld}/${ln}`;
    // Build incremental DO paths (exclude LN inst itself)
    for (let i = 1; i < parts.length; i++) {
      const path = parts.slice(1, i+1).join('.');
      const fullPathRef = `${ldlnKey}.${path}`;
      // Locate the expand button for this path (if any) and expand if collapsed
      // Buttons created have inline-expand and parent li contains label span with text path end segment
      // We'll search for a context menu span matching exact path end to locate the correct li
      const selector = `span.data-item`;
      const spans = Array.from(document.querySelectorAll(selector));
      // Match by constructing ending reference
      const endSegment = parts[i];
      let foundBtn = null;
      for (const sp of spans){
        if (sp.textContent.trim().startsWith(endSegment)){
          const btn = sp.parentElement && sp.parentElement.querySelector('button.inline-expand');
          if (btn && btn.dataset.state === 'collapsed') {
            foundBtn = btn;
            break;
          }
        }
      }
      if (foundBtn){
        // Simulate click to expand
        foundBtn.click();
        // Allow DOM to process
        await new Promise(r => setTimeout(r, 50));
      }
    }
  } catch(e){
    console.warn('[expandDoChain] Exception:', e);
  }
}

// Close context menu when clicking elsewhere
document.addEventListener('click', hideContextMenu);
document.addEventListener('contextmenu', (e) => {
  // Only prevent default if not on our custom context menu items
  if (!e.target.classList.contains('data-item')) {
    // Allow browser context menu on other elements
  }
});

async function pollStatus(){
  const session = connectionPollSession;
  statusPollTimer = null;
  if (!connectionPollingEnabled) return;
  statusPollInFlight = true;
  try {
    const res = await fetch('/api/statuses');
    const statuses = await res.json();
    const serverClientStatus = (statuses && statuses['server-client']) || {state: 'not-connected'};
    const clientServerStatus = (statuses && statuses['client-server']) || {state: 'not-connected'};

      panelStates.serverClient = serverClientStatus.state || 'not-connected';
      panelStates.clientServer = clientServerStatus.state || 'not-connected';

      updateGlobalStatusSummary();
      updateActiveRoleSummary();
      syncConnectionButtons();

      const autoBtn = document.getElementById('autoReconnectBtn');
      if (autoBtn){
        autoBtn.disabled = false;
        autoBtn.classList.remove('btn-disabled');
      }

      if (previousPanelStates.serverClient === 'listening' && panelStates.serverClient === 'connected') {
        console.log('[Status] Client connected in server mode, fetching model');
        fetchModel();
      }

      if (previousPanelStates.serverClient === 'connected' && panelStates.serverClient === 'listening') {
        console.log('[Status] Client disconnected in server mode, clearing model tree');
        const treeContainer = document.getElementById('tree');
        treeContainer.innerHTML = '';
        // Show message that we're ready for new connections
        const msg = document.createElement('div');
        msg.style.padding = '20px';
        msg.style.color = '#666';
        msg.textContent = 'Waiting for IEC61850 client to connect...';
        treeContainer.appendChild(msg);
      }

      if ((panelStates.serverClient === 'not-connected' || panelStates.serverClient === 'error') && document.getElementById('tree').children.length){
        markLogicalDevicesOld();
      }

      if ((panelStates.clientServer === 'not-connected' || panelStates.clientServer === 'error') && previousPanelStates.clientServer === 'connected'){
        if (!manualDisconnectByPanel.clientServer){
          scheduleReconnect();
        }
      }

      previousPanelStates.serverClient = panelStates.serverClient;
      previousPanelStates.clientServer = panelStates.clientServer;

      if (!anyPanelActive()) {
        stopConnectionPolling();
      }
  } catch(e){
    panelStates.serverClient = 'error';
    panelStates.clientServer = 'error';
    updateGlobalStatusSummary();
    syncConnectionButtons();
  } finally {
    statusPollInFlight = false;
    if (!pollingPaused && connectionPollingEnabled && session === connectionPollSession) {
      const summaryState = primaryStatusState();
      const statusDelay = (summaryState === 'connected' || summaryState === 'listening')
        ? STATUS_POLL_INTERVAL_CONNECTED
        : STATUS_POLL_INTERVAL_IDLE;
      statusPollTimer = setTimeout(pollStatus, statusDelay);
    }
  }
}

// Poll for report updates
async function pollReportUpdates() {
  const session = connectionPollSession;
  reportPollTimer = null;
  if (!connectionPollingEnabled) return;
  reportPollInFlight = true;
  try {
    const shouldPollReports = !document.hidden && panelStates.serverClient === 'connected';
    if (!shouldPollReports) {
      return;
    }

    const res = await fetch('/api/report-updates?target=server-client');
    const data = await res.json();
    if (data.updates && data.updates.length > 0) {
      data.updates.forEach(update => {
        updateTreeWithReportData(update.dataRef, update.values);
      });
    }
  } catch(e) {
    console.error('Error polling report updates:', e);
  } finally {
    reportPollInFlight = false;
    if (!pollingPaused && connectionPollingEnabled && session === connectionPollSession) {
      const reportDelay = panelStates.serverClient === 'connected'
        ? REPORT_POLL_INTERVAL_CONNECTED
        : REPORT_POLL_INTERVAL_IDLE;
      reportPollTimer = setTimeout(pollReportUpdates, reportDelay);
    }
  }
}

function updateTreeWithReportData(dataRef, values) {
  /**
   * Update tree with values from a Report message.
   * dataRef: object reference like "LD0/MMXU1.TotW" or "LD0/MMXU1.MinWPhs.mag"
   * values: array of DataAttributeValue from Report entryData
   */
  console.log('[Report v2] Updating tree for:', dataRef, 'values:', JSON.stringify(values));

  if (!dataRef || !values || !Array.isArray(values)) {
    return;
  }

  // Check the format of the value
  const firstItem = values[0];
  if (!firstItem || !firstItem.data) {
    return;
  }

  // Report format: {data: {structure: {...}}} or {data: {quality: {...}}} or {data: {timeStamp: {...}}}
  if (typeof firstItem.data === 'object' && !Array.isArray(firstItem.data)) {
    // This is Report format - pass directly to parseStructuredValue which handles it
    parseStructuredValue(dataRef, values);
  } else if (Array.isArray(firstItem.data)) {
    // Old ASN.1 format: {data: ['structure', {...}]}
    updateTreeValueDisplay(dataRef, values, false);

    if (firstItem.data.length === 2 && typeof firstItem.data[0] === 'string' && firstItem.data[0] === 'structure') {
      const structureObj = firstItem.data[1];
      if (structureObj && structureObj.data && Array.isArray(structureObj.data)) {
        parseStructuredValue(dataRef, [{data: firstItem.data}]);
      }
    } else {
      parseStructuredValue(dataRef, values);
    }
  }

  console.log('[Report] Tree updated for:', dataRef);
}

setFooterMessage('Idle.', 'info', {overrideFreeze:true});

// ==================== Message Monitor ====================
let messagesFrozen = false;
let messagesVisible = false;
let messagesFullscreen = false;

function toggleMessageMonitor() {
  const panel = document.getElementById('messageMonitor');
  messagesVisible = !messagesVisible;
  if (messagesVisible) {
    panel.classList.remove('hidden');
    startMessagesPolling();
  } else {
    panel.classList.add('hidden');
    // Reset fullscreen state when closing
    if (messagesFullscreen) {
      messagesFullscreen = false;
      panel.classList.remove('fullscreen');
      updateMaximizeButton();
    }
  }
}

function toggleMessageFullscreen() {
  const panel = document.getElementById('messageMonitor');
  messagesFullscreen = !messagesFullscreen;

  if (messagesFullscreen) {
    panel.classList.add('fullscreen');
  } else {
    panel.classList.remove('fullscreen');
  }

  updateMaximizeButton();
}

function updateMaximizeButton() {
  const btn = document.getElementById('maximizeMessagesBtn');
  if (messagesFullscreen) {
    btn.textContent = '🗗'; // Restore/minimize icon
    btn.title = 'Restore';
  } else {
    btn.textContent = '🗖'; // Maximize icon
    btn.title = 'Maximize';
  }
}

async function clearMessages() {
  // Clear server-side messages first so polling won't repopulate old entries
  try {
    const res = await fetch('/api/messages/clear', { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.status === 'cleared') {
      document.getElementById('messageList').innerHTML = '';
      showToast('Messages cleared', 'success');
    } else {
      console.warn('Message clear failed:', data.error || res.status);
      // Still clear UI locally even if server failed
      document.getElementById('messageList').innerHTML = '';
      showToast('Failed to clear messages', 'error');
    }
  } catch (e) {
    console.error('Error clearing messages:', e);
    document.getElementById('messageList').innerHTML = '';
    showToast('Error clearing messages', 'error');
  }
}

// Toast notification helper
function showToast(message, type = 'info', timeout = 2500) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = message;
  el.className = 'toast visible ' + (type ? type : '');
  clearTimeout(el._hideTimer);
  el._hideTimer = setTimeout(() => {
    el.className = 'toast';
  }, timeout);
}

// Message retention UI logic
async function fetchMessageRetention() {
  try {
    const res = await fetch('/api/messages/settings');
    const data = await res.json();
    if (data.max) {
      const select = document.getElementById('messageRetentionSelect');
      if (select) {
        // If current max not in list, append it
        if (![...select.options].some(o => o.value == data.max)) {
          const opt = document.createElement('option');
          opt.value = data.max;
          opt.textContent = data.max;
          select.appendChild(opt);
        }
        select.value = data.max;
      }
    }
  } catch (e) {
    console.warn('Failed to fetch retention setting:', e);
  }
}

async function applyMessageRetention() {
  const select = document.getElementById('messageRetentionSelect');
  if (!select) return;
  const val = parseInt(select.value, 10);
  if (!val) return;
  try {
    const res = await fetch('/api/messages/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max: val })
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.status === 'updated') {
      showToast(`Retention updated to ${data.max}`, 'success');
    } else {
      showToast(data.error || 'Retention update failed', 'error');
    }
  } catch (e) {
    showToast('Error updating retention', 'error');
  }
}

function extractImportantParams(msg) {
  // Extract important parameters from the message
  try {
    const parsed = JSON.parse(msg.message);
    const params = [];
    console.log('Extracting params from:', parsed);

    // Helper to recursively extract from nested structure
    const extractFromService = (serviceObj) => {
      if (!serviceObj || typeof serviceObj !== 'object') return;

      // Handle ref object (nested in getDataValues, etc.)
      if (serviceObj.ref && typeof serviceObj.ref === 'object') {
        if (serviceObj.ref.ref) params.push(`ref: ${serviceObj.ref.ref}`);
        if (serviceObj.ref.fc) params.push(`FC: ${serviceObj.ref.fc}`);
      }

      // Direct reference fields (various naming conventions)
      if (serviceObj.dataRef) params.push(`ref: ${serviceObj.dataRef}`);
      if (serviceObj.objectReference) params.push(`ref: ${serviceObj.objectReference}`);
      if (serviceObj.objRef && typeof serviceObj.objRef === 'string') params.push(`ref: ${serviceObj.objRef}`);

      // Logical Device/Node
      if (serviceObj.ldInst) params.push(`LD: ${serviceObj.ldInst}`);
      if (serviceObj.lnInst) params.push(`LN: ${serviceObj.lnInst}`);

      // Functional Constraint
      if (serviceObj.fc && typeof serviceObj.fc === 'string') params.push(`FC: ${serviceObj.fc}`);

      // Mode for directory requests
      if (serviceObj.mode) params.push(`mode: ${serviceObj.mode}`);
      if (serviceObj.objectClass) params.push(`class: ${serviceObj.objectClass}`);

      // Dataset related
      if (serviceObj.dsInst) params.push(`DS: ${serviceObj.dsInst}`);

      // Control related
      if (serviceObj.ctlVal !== undefined) params.push(`ctlVal: ${serviceObj.ctlVal}`);
      if (serviceObj.operTm !== undefined) params.push(`operTm: ${serviceObj.operTm}`);

      // Report control blocks
      if (serviceObj.RptEna !== undefined) params.push(`RptEna: ${serviceObj.RptEna}`);
      if (serviceObj.RptId) params.push(`RptId: ${serviceObj.RptId}`);

      // Flags
      if (serviceObj.includeElementName !== undefined) params.push(`includeNames: ${serviceObj.includeElementName}`);
      if (serviceObj.moreFollows !== undefined) params.push(`moreFollows: ${serviceObj.moreFollows}`);
    };

    // Navigate to service data
    if (parsed.request && parsed.request.service) {
      const serviceName = Object.keys(parsed.request.service)[0];
      console.log('Request service:', serviceName, parsed.request.service[serviceName]);
      extractFromService(parsed.request.service[serviceName]);
    } else if (parsed.response && parsed.response.service) {
      const serviceName = Object.keys(parsed.response.service)[0];
      const responseData = parsed.response.service[serviceName];
      console.log('Response service:', serviceName, responseData);
      extractFromService(responseData);

      // For responses, also show count of items if available
      if (responseData && typeof responseData === 'object') {
        if (Array.isArray(responseData.listOfIdentifier)) {
          params.push(`count: ${responseData.listOfIdentifier.length}`);
        }
        if (Array.isArray(responseData.listOfData)) {
          params.push(`count: ${responseData.listOfData.length}`);
        }
      }
    } else if (parsed.associate && parsed.associate.service) {
      const serviceName = Object.keys(parsed.associate.service)[0];
      const assocData = parsed.associate.service[serviceName];
      if (assocData.apTitle) params.push(`AP: ${assocData.apTitle}`);
      if (assocData.maxOutstandingCalling) params.push(`maxCalls: ${assocData.maxOutstandingCalling}`);
    } else if (parsed.unconfirmed && parsed.unconfirmed.service) {
      const serviceName = Object.keys(parsed.unconfirmed.service)[0];
      extractFromService(parsed.unconfirmed.service[serviceName]);
    }

    const result = params.length > 0 ? ` (${params.join(', ')})` : '';
    console.log('Extracted params:', params, 'Result:', result);
    return result;
  } catch (e) {
    console.error('Error extracting params:', e);
    return '';
  }
}

function renderMessages(messages) {
  if (messagesFrozen) return;

  const container = document.getElementById('messageList');
  const filterSend = document.getElementById('filterSendMsg').checked;
  const filterRecv = document.getElementById('filterRecvMsg').checked;

  // Filter messages
  const filtered = messages.filter(msg => {
    if (msg.direction === 'send' && !filterSend) return false;
    if (msg.direction === 'recv' && !filterRecv) return false;
    return true;
  });

  // Clear and rebuild (could be optimized to only add new ones)
  container.innerHTML = '';

  filtered.forEach(msg => {
    const entry = document.createElement('div');
    entry.className = 'message-entry';
    entry.dataset.msgId = msg.id;

    const header = document.createElement('div');
    header.className = 'message-header';
    const category = msg.category || 'unknown';
    const params = extractImportantParams(msg);
    header.innerHTML = `
      <span class="msg-direction ${msg.direction}">${msg.direction.toUpperCase()}</span>
      <span class="msg-timestamp">${msg.timestamp}</span>
      <span class="msg-category ${category}">${category}</span>
      <span class="msg-service">${msg.service_type}${params}</span>
      <span class="msg-expand">▶</span>
    `;

    const body = document.createElement('div');
    body.className = 'message-body';

    // Pretty print JSON if possible
    try {
      const parsed = JSON.parse(msg.message);
      body.textContent = JSON.stringify(parsed, null, 2);
    } catch {
      body.textContent = msg.message;
    }

    header.addEventListener('click', () => {
      entry.classList.toggle('expanded');
    });

    entry.appendChild(header);
    entry.appendChild(body);
    container.appendChild(entry);
  });

  // Auto-scroll to bottom if not frozen
  if (!messagesFrozen) {
    container.scrollTop = container.scrollHeight;
  }
}

async function pollMessages() {
  if (!messagesVisible) return;

  try {
    const res = await fetch('/api/messages');
    const data = await res.json();
    if (data.messages) {
      renderMessages(data.messages);
    }
  } catch (e) {
    console.error('Failed to fetch messages:', e);
  }
}

let messagesPollingInterval = null;

function startMessagesPolling() {
  if (messagesPollingInterval) return;
  pollMessages();
  messagesPollingInterval = setInterval(pollMessages, 1000);
}

function stopMessagesPolling() {
  if (messagesPollingInterval) {
    clearInterval(messagesPollingInterval);
    messagesPollingInterval = null;
  }
}

// Event listeners for message monitor
document.getElementById('toggleMessagesBtn').addEventListener('click', toggleMessageMonitor);
document.getElementById('closeMessagesBtn').addEventListener('click', toggleMessageMonitor);
document.getElementById('maximizeMessagesBtn').addEventListener('click', toggleMessageFullscreen);
document.getElementById('clearMessagesBtn').addEventListener('click', clearMessages);

document.getElementById('freezeMessagesBtn').addEventListener('click', (e) => {
  messagesFrozen = !messagesFrozen;
  e.target.dataset.frozen = messagesFrozen;
  e.target.textContent = messagesFrozen ? 'Unfreeze' : 'Freeze';
});

document.getElementById('filterSendMsg').addEventListener('change', () => {
  pollMessages();
});

document.getElementById('filterRecvMsg').addEventListener('change', () => {
  pollMessages();
});
const applyRetentionBtn = document.getElementById('applyMessageRetentionBtn');
if (applyRetentionBtn) {
  applyRetentionBtn.addEventListener('click', applyMessageRetention);
  // Fetch current setting once when UI loads
  fetchMessageRetention();
}

// ========== RCB Details Panel ==========

function showRcbDetails(rcbRef, rcbData) {
  const panel = document.getElementById('rcbDetails');
  const content = document.getElementById('rcbDetailsContent');
  const statusBadge = document.getElementById('rcbStatusBadge');
  const typeBadge = document.getElementById('rcbTypeBadge');

  // Store the current RCB reference and type for refresh
  window.currentRcbRef = rcbRef;
  window.currentRcbType = rcbData.type;

  // Update type badge in header
  typeBadge.textContent = rcbData.type || 'RCB';

  // Update status badge in header
  if (rcbData.enabled) {
    statusBadge.className = 'rcb-badge rcb-enabled';
    statusBadge.textContent = 'Enabled';
  } else {
    statusBadge.className = 'rcb-badge rcb-disabled';
    statusBadge.textContent = 'Disabled';
  }

  // Helper function to create nested table for bitstring fields
  function createNestedTable(bitObject) {
    // If it's a string, try to parse it as JSON
    if (typeof bitObject === 'string') {
      try {
        bitObject = JSON.parse(bitObject);
      } catch (e) {
        return bitObject; // Return as-is if not valid JSON
      }
    }

    if (!bitObject || typeof bitObject !== 'object') {
      return JSON.stringify(bitObject);
    }

    let tableHtml = '<table class="rcb-nested-table"><tbody>';
    for (const [bitKey, bitValue] of Object.entries(bitObject)) {
      let displayValue;

      // Show checkboxes for boolean values
      if (typeof bitValue === 'boolean') {
        const checkedAttr = bitValue ? 'checked' : '';
        displayValue = `<input type="checkbox" ${checkedAttr} disabled class="rcb-checkbox">`;
      } else {
        displayValue = bitValue;
      }

      tableHtml += `
        <tr>
          <td>${bitKey}</td>
          <td>${displayValue}</td>
        </tr>
      `;
    }
    tableHtml += '</tbody></table>';
    return tableHtml;
  }

  // Build the details HTML
  let html = `
    <div class="rcb-info-section">
      <span class="rcb-info-label">Object Reference:</span>
      <div class="rcb-info-value">${rcbRef}</div>
    </div>
  `;

  // Add RCB values if available
  if (rcbData.values && typeof rcbData.values === 'object') {
    html += `
      <div class="rcb-info-section">
        <span class="rcb-info-label">RCB Values:</span>
        <table class="rcb-values-table">
          <thead>
            <tr>
              <th>Attribute</th>
              <th>Value</th>
            </tr>
          </thead>
          <tbody>
    `;

    // Display each value
    for (const [key, value] of Object.entries(rcbData.values)) {
      let displayValue = value;

      // Special handling for optFlds and trgOps - show as nested tables
      // Check various case variations
      const keyLower = key.toLowerCase();
      if (keyLower === 'optflds' || keyLower === 'trgops' || keyLower === 'trgop') {
        // Try to parse if it's a string, or use directly if already an object
        displayValue = createNestedTable(value);
      }
      // Special handling for timeOfEntry - format as ISO timestamp
      else if (keyLower === 'timeofentry' && typeof value === 'object' && value !== null) {
        const isoTime = asn1TimeStampToISOString(value);
        displayValue = isoTime || JSON.stringify(value);
      }
      // Format other complex values
      else if (typeof value === 'object' && value !== null) {
        displayValue = JSON.stringify(value, null, 2);
      } else if (typeof value === 'boolean') {
        displayValue = value ? 'true' : 'false';
      } else if (value === null || value === undefined) {
        displayValue = 'null';
      }

      html += `
        <tr>
          <td><strong>${key}</strong></td>
          <td>${displayValue}</td>
        </tr>
      `;
    }

    html += `
          </tbody>
        </table>
      </div>
    `;
  } else {
    html += `
      <div class="rcb-info-section">
        <div class="rcb-no-values">No RCB values available</div>
      </div>
    `;
  }

  content.innerHTML = html;
  panel.classList.remove('hidden');
}

function hideRcbDetails() {
  const panel = document.getElementById('rcbDetails');
  panel.classList.add('hidden');
  // Clear the current RCB reference
  window.currentRcbRef = null;
  window.currentRcbType = null;
}

// Store the current RCB reference and type for refresh
window.currentRcbRef = null;
window.currentRcbType = null;

// Event listener for closing RCB details
document.getElementById('closeRcbDetailsBtn').addEventListener('click', hideRcbDetails);

// Function to refresh RCB values
async function refreshRcbValues(ld, lnInst, rcbData, button, nameSpan) {
  const originalContent = button.innerHTML;
  const rcbRef = `${ld}/${lnInst}.${rcbData.name}`;
  const rcbType = rcbData.type;

  try {
    // Disable button and show spinning state
    button.disabled = true;
    button.classList.add('spinning');
    button.innerHTML = `<svg class="spin" width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M13.65 2.35C12.2 0.9 10.21 0 8 0 3.58 0 0.01 3.58 0.01 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L9 7h7V0l-2.35 2.35z" fill="currentColor"/>
    </svg>`;

    // Call the API endpoint
    const response = await fetch('/api/rcb/values', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rcbRef, rcbType })
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to refresh RCB values');
    }

    const result = await response.json();

    // Update the RCB data
    rcbData.values = result.values;
    rcbData.enabled = result.enabled;

    // Update the badge in the tree
    const existingBadge = nameSpan.querySelector('.rcb-badge');
    if (existingBadge) {
      existingBadge.className = result.enabled ? 'rcb-badge rcb-enabled' : 'rcb-badge rcb-disabled';
      existingBadge.textContent = result.enabled ? 'Enabled' : 'Disabled';
    }

    // If the panel is currently showing this RCB, update it
    if (window.currentRcbRef === rcbRef) {
      showRcbDetails(rcbRef, rcbData);
    }

  } catch (error) {
    console.error('Error refreshing RCB values:', error);
    alert(`Failed to refresh RCB values: ${error.message}`);
  } finally {
    // Re-enable button and restore original content
    button.disabled = false;
    button.classList.remove('spinning');
    button.innerHTML = originalContent;
  }
}

// Function to show RCB edit dialog
function showRcbEditDialog(rcbRef, rcbData, ld, lnInst, nameSpan) {
  const modal = document.getElementById('rcbEditModal');
  const title = document.getElementById('rcbEditTitle');
  const formContainer = document.getElementById('rcbEditForm');

  title.textContent = `Modify ${rcbData.type} Values - ${rcbRef}`;

  // Collect all dataset references from the model
  const allDatasets = [];
  if (window.modelData && window.modelData.logicalNodeDetails) {
    // Iterate through logicalNodeDetails which has structure: { "LD0/LLN0": { dataSets: [...] } }
    for (const [ldLnKey, details] of Object.entries(window.modelData.logicalNodeDetails)) {
      if (details.dataSets && Array.isArray(details.dataSets)) {
        details.dataSets.forEach(dsName => {
          // ldLnKey is already "LD/LN" format, so just append .DataSetName
          const fullRef = `${ldLnKey}.${dsName}`;
          allDatasets.push(fullRef);
        });
      }
    }
  }

  console.log('Available datasets:', allDatasets);
  console.log('Model data structure:', window.modelData);

  // Define writable RCB parameters
  // Map field names to their possible variations in the response
  const writableFields = {
    'RptEna': { type: 'boolean', label: 'Report Enable', aliases: ['rptEna', 'RptEna'] },
    'DatSet': { type: 'dataset', label: 'Data Set Reference', aliases: ['dataSet', 'DatSet', 'DataSet'], datasets: allDatasets },
    'IntgPd': { type: 'number', label: 'Integrity Period (ms)', aliases: ['intgPd', 'IntgPd'] },
    'GI': { type: 'boolean', label: 'General Interrogation', aliases: ['gi', 'GI'] },
    'PurgeBuf': { type: 'boolean', label: 'Purge Buffer', aliases: ['purgeBuf', 'PurgeBuf'] },
    'OptFlds': { type: 'bitfield', label: 'Optional Fields', aliases: ['optFlds', 'OptFlds'] },
    'TrgOps': { type: 'bitfield', label: 'Trigger Options', aliases: ['trgOp', 'trgOps', 'TrgOps', 'TrgOp'] }
  };

  // Helper to find value with case-insensitive key matching
  function findValue(values, aliases) {
    if (!values) return undefined;
    for (const alias of aliases) {
      if (values.hasOwnProperty(alias)) {
        return values[alias];
      }
    }
    return undefined;
  }

  // Build form
  let formHtml = '';

  for (const [fieldName, fieldConfig] of Object.entries(writableFields)) {
    // Try to find the value using aliases
    let value = findValue(rcbData.values, fieldConfig.aliases);

    formHtml += `<div class="rcb-edit-field">`;
    formHtml += `<div class="rcb-edit-field-header">`;
    formHtml += `<input type="checkbox" class="rcb-edit-include" id="include_${fieldName}" data-field="${fieldName}" checked>`;
    formHtml += `<label class="rcb-edit-label" for="include_${fieldName}">${fieldConfig.label} (${fieldName})</label>`;
    formHtml += `</div>`;
    formHtml += `<div class="rcb-edit-field-value">`;

    if (fieldConfig.type === 'boolean') {
      const checked = value === true ? 'checked' : '';
      formHtml += `<input type="checkbox" class="rcb-edit-checkbox" data-field="${fieldName}" ${checked}>`;
    } else if (fieldConfig.type === 'dataset') {
      const val = value || '';
      const datasetId = `datasets_${fieldName}`;
      console.log(`Building dataset field, ${fieldConfig.datasets ? fieldConfig.datasets.length : 0} datasets available`);
      formHtml += `<div class="rcb-edit-dataset-wrapper">`;
      formHtml += `<input type="text" class="rcb-edit-input rcb-edit-dataset" data-field="${fieldName}" value="${val}" list="${datasetId}" placeholder="LD0/LLN0.dataset1">`;
      formHtml += `<datalist id="${datasetId}">`;
      formHtml += `</datalist>`;
      formHtml += `<span class="rcb-edit-dataset-validation" data-field="${fieldName}"></span>`;
      formHtml += `</div>`;
    } else if (fieldConfig.type === 'string') {
      const val = value || '';
      formHtml += `<input type="text" class="rcb-edit-input" data-field="${fieldName}" value="${val}">`;
    } else if (fieldConfig.type === 'number') {
      const val = value || 0;
      formHtml += `<input type="number" class="rcb-edit-input" data-field="${fieldName}" value="${val}">`;
    } else if (fieldConfig.type === 'bitfield') {
      // Parse bitfield if it's a string
      let bitObject = value;
      if (typeof value === 'string') {
        try {
          bitObject = JSON.parse(value);
        } catch (e) {
          bitObject = {};
        }
      }

      if (bitObject && typeof bitObject === 'object') {
        formHtml += `<div class="rcb-edit-bitfield" data-field="${fieldName}">`;
        for (const [bitKey, bitValue] of Object.entries(bitObject)) {
          const checked = bitValue === true ? 'checked' : '';
          formHtml += `
            <div class="rcb-edit-bit">
              <input type="checkbox" id="bit_${fieldName}_${bitKey}" data-bit="${bitKey}" ${checked}>
              <label for="bit_${fieldName}_${bitKey}">${bitKey}</label>
            </div>
          `;
        }
        formHtml += `</div>`;
      } else {
        formHtml += `<input type="text" class="rcb-edit-input" data-field="${fieldName}" value="${value || ''}" placeholder="{}">`;
      }
    }

    formHtml += `</div>`;
    formHtml += `</div>`;
  }

  formContainer.innerHTML = formHtml;

  // Populate datalists dynamically (more reliable than innerHTML for datalist options)
  if (writableFields['DatSet'] && writableFields['DatSet'].datasets) {
    const datalistEl = document.getElementById('datasets_DatSet');
    if (datalistEl) {
      // Clear any existing options
      datalistEl.innerHTML = '';
      // Add each dataset as an option
      writableFields['DatSet'].datasets.forEach(ds => {
        const option = document.createElement('option');
        option.value = ds;
        option.textContent = ds;
        datalistEl.appendChild(option);
      });
      console.log('Datalist populated with', datalistEl.options.length, 'options');
    }
  }

  modal.classList.remove('hidden');

  // Add event listeners to include checkboxes to enable/disable fields
  formContainer.querySelectorAll('.rcb-edit-include').forEach(checkbox => {
    const fieldName = checkbox.dataset.field;
    const fieldValue = formContainer.querySelector(`.rcb-edit-field-value input[data-field="${fieldName}"], .rcb-edit-field-value .rcb-edit-bitfield[data-field="${fieldName}"]`);

    checkbox.addEventListener('change', () => {
      if (fieldValue) {
        if (fieldValue.classList && fieldValue.classList.contains('rcb-edit-bitfield')) {
          // For bitfields, enable/disable all checkboxes inside
          fieldValue.querySelectorAll('input').forEach(input => {
            input.disabled = !checkbox.checked;
          });
          fieldValue.style.opacity = checkbox.checked ? '1' : '0.5';
        } else {
          // For simple inputs
          fieldValue.disabled = !checkbox.checked;
        }
      }
    });
  });

  // Add validation for dataset field
  formContainer.querySelectorAll('.rcb-edit-dataset').forEach(input => {
    const fieldName = input.dataset.field;
    const validationSpan = formContainer.querySelector(`.rcb-edit-dataset-validation[data-field="${fieldName}"]`);
    const fieldConfig = writableFields[fieldName];

    function validateDataset() {
      const value = input.value.trim();
      if (!value) {
        validationSpan.textContent = '';
        validationSpan.className = 'rcb-edit-dataset-validation';
        input.classList.remove('valid', 'invalid');
        return true;
      }

      const isValid = fieldConfig.datasets && fieldConfig.datasets.includes(value);
      console.log('Validating dataset:', value, 'Available:', fieldConfig.datasets, 'Valid:', isValid);

      if (isValid) {
        validationSpan.textContent = '✓';
        validationSpan.className = 'rcb-edit-dataset-validation valid';
        input.classList.remove('invalid');
        input.classList.add('valid');
      } else {
        validationSpan.textContent = '⚠ Dataset not found in model';
        validationSpan.className = 'rcb-edit-dataset-validation invalid';
        input.classList.remove('valid');
        input.classList.add('invalid');
      }
      return isValid;
    }

    // Validate on input
    input.addEventListener('input', validateDataset);
    input.addEventListener('change', validateDataset);

    // Initial validation
    validateDataset();
  });

  // Store context for save handler
  window.rcbEditContext = { rcbRef, rcbData, rcbType: rcbData.type, ld, lnInst, nameSpan };
}

// Modal event handlers
document.getElementById('closeRcbEditModal').addEventListener('click', () => {
  document.getElementById('rcbEditModal').classList.add('hidden');
});

document.getElementById('cancelRcbEdit').addEventListener('click', () => {
  document.getElementById('rcbEditModal').classList.add('hidden');
});

document.getElementById('saveRcbEdit').addEventListener('click', async () => {
  const modal = document.getElementById('rcbEditModal');
  const saveBtn = document.getElementById('saveRcbEdit');
  const context = window.rcbEditContext;

  if (!context) return;

  try {
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';

    // Collect form values - only include fields that are checked
    const updates = {};
    const formContainer = document.getElementById('rcbEditForm');

    // Get all include checkboxes
    const includeCheckboxes = formContainer.querySelectorAll('.rcb-edit-include');
    const includedFields = new Set();

    includeCheckboxes.forEach(checkbox => {
      if (checkbox.checked) {
        includedFields.add(checkbox.dataset.field);
      }
    });

    // Get simple inputs - only if included
    const allInputs = formContainer.querySelectorAll('input[data-field]:not([type="checkbox"][data-bit]):not(.rcb-edit-include)');
    console.log('[RCB Edit] Found', allInputs.length, 'input fields');

    allInputs.forEach(input => {
      const fieldName = input.dataset.field;
      console.log('[RCB Edit] Processing input:', fieldName, 'type:', input.type, 'value:', input.value, 'included:', includedFields.has(fieldName));

      if (!includedFields.has(fieldName)) {
        return; // Skip if not included
      }

      if (input.type === 'checkbox' && !input.dataset.bit) {
        updates[fieldName] = input.checked;
      } else if (input.type === 'number') {
        updates[fieldName] = parseInt(input.value, 10);
      } else if (input.type === 'text') {
        updates[fieldName] = input.value;
      }
    });

    // Get bitfields - only if included
    formContainer.querySelectorAll('.rcb-edit-bitfield').forEach(bitfieldDiv => {
      const fieldName = bitfieldDiv.dataset.field;

      if (!includedFields.has(fieldName)) {
        return; // Skip if not included
      }

      const bitObject = {};

      bitfieldDiv.querySelectorAll('input[data-bit]').forEach(checkbox => {
        bitObject[checkbox.dataset.bit] = checkbox.checked;
      });

      updates[fieldName] = bitObject;
    });

    console.log('[RCB Edit] Included fields:', Array.from(includedFields));
    console.log('[RCB Edit] Collected updates:', updates);

    // Call the API to set RCB values
    const response = await fetch('/api/rcb/set', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        rcbRef: context.rcbRef,
        rcbType: context.rcbType,
        values: updates
      })
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || 'Failed to set RCB values');
    }

    const result = await response.json();

    // Update local data
    context.rcbData.values = result.values;
    context.rcbData.enabled = result.enabled;

    // Update badge in tree
    const existingBadge = context.nameSpan.querySelector('.rcb-badge');
    if (existingBadge) {
      existingBadge.className = result.enabled ? 'rcb-badge rcb-enabled' : 'rcb-badge rcb-disabled';
      existingBadge.textContent = result.enabled ? 'Enabled' : 'Disabled';
    }

    // Update panel if open
    if (window.currentRcbRef === context.rcbRef) {
      showRcbDetails(context.rcbRef, context.rcbData);
    }

    // Close modal
    modal.classList.add('hidden');

  } catch (error) {
    console.error('Error setting RCB values:', error);
    alert(`Failed to set RCB values: ${error.message}`);
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = 'Save';
  }
});

// ===== Control Dialog Functions =====

// List of controllable CDC types
const CONTROLLABLE_CDCS = ['SPC', 'DPC', 'APC', 'INC', 'ENC', 'BSC', 'ING', 'ASG', 'CTE', 'ENG'];

async function showControlDialog(objRef, objName, cdc) {
  const modal = document.getElementById('controlModal');
  const titleEl = document.getElementById('controlTitle');
  const objRefEl = document.getElementById('controlObjRef');
  const cdcTypeEl = document.getElementById('controlCdcType');
  const ctlModelEl = document.getElementById('controlCtlModel');
  const ctlValInput = document.getElementById('ctlVal');
  const ctlNumInput = document.getElementById('ctlNum');
  const resultDiv = document.getElementById('controlResult');

  // Set dialog title and info
  titleEl.textContent = `Control: ${objName}`;
  objRefEl.textContent = objRef;
  cdcTypeEl.textContent = cdc.toUpperCase();
  ctlModelEl.textContent = 'Reading...';

  // Reset form
  ctlValInput.value = '';
  ctlNumInput.value = '0';
  document.getElementById('originCat').value = '1';
  document.getElementById('originOrIdent').value = '0';
  document.getElementById('testMode').checked = false;
  resultDiv.classList.add('hidden');
  resultDiv.className = 'control-result hidden';

  // Set placeholder and type based on CDC
  switch(cdc.toUpperCase()) {
    case 'SPC':
      ctlValInput.placeholder = 'true or false';
      ctlValInput.type = 'text';
      break;
    case 'DPC':
      ctlValInput.placeholder = 'on, off, or intermediate-state';
      ctlValInput.type = 'text';
      break;
    case 'APC':
      ctlValInput.placeholder = 'Float value (e.g., 123.45)';
      ctlValInput.type = 'number';
      ctlValInput.step = 'any';
      break;
    case 'INC':
    case 'ENC':
      ctlValInput.placeholder = 'Integer value';
      ctlValInput.type = 'number';
      ctlValInput.step = '1';
      break;
    case 'BSC':
      ctlValInput.placeholder = 'step-up or step-down';
      ctlValInput.type = 'text';
      break;
    default:
      ctlValInput.placeholder = 'Control value';
      ctlValInput.type = 'text';
  }

  // Store current control context
  modal.dataset.objRef = objRef;
  modal.dataset.cdc = cdc;

  // Show modal
  modal.classList.remove('hidden');

  // Read ctlModel attribute value
  try {
    const ctlModelRef = `${objRef}.ctlModel`;
    const res = await fetch('/api/readvalue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objRef: ctlModelRef, fc: 'cf' })
    });

    const data = await res.json();

    if (data.error) {
      ctlModelEl.textContent = 'N/A';
      console.log(`[Control Dialog] Could not read ctlModel: ${data.error}`);
    } else if (data.values) {
      // Extract the ctlModel value
      let ctlModelValue = 'N/A';

      if (Array.isArray(data.values)) {
        // Handle array format: [{data: [typeName, value]}]
        if (data.values[0] && data.values[0].data) {
          const dataObj = data.values[0].data;
          
          // Check if it's [typeName, value] format
          if (Array.isArray(dataObj) && dataObj.length === 2 && typeof dataObj[0] === 'string') {
            ctlModelValue = dataObj[1]; // The actual value is at index 1
          } else if (dataObj.enumerated) {
            ctlModelValue = dataObj.enumerated;
          } else if (typeof dataObj === 'object') {
            // Get first value from object
            ctlModelValue = Object.values(dataObj)[0];
          }
        }
      } else if (typeof data.values === 'object') {
        // Handle direct object format
        if (data.values.enumerated) {
          ctlModelValue = data.values.enumerated;
        } else if (data.values.data && data.values.data.enumerated) {
          ctlModelValue = data.values.data.enumerated;
        }
      } else if (typeof data.values === 'string') {
        ctlModelValue = data.values;
      }

      // Map numeric values to string representations
      const ctlModelMap = {
        0: 'status-only',
        1: 'direct-with-normal-security',
        2: 'sbo-with-normal-security',
        3: 'direct-with-enhanced-security',
        4: 'sbo-with-enhanced-security'
      };

      // If it's a number, show both number and string representation
      if (typeof ctlModelValue === 'number' && ctlModelValue in ctlModelMap) {
        ctlModelEl.textContent = `${ctlModelValue} (${ctlModelMap[ctlModelValue]})`;
      } else if (typeof ctlModelValue === 'string' && !isNaN(ctlModelValue)) {
        // Handle string numbers
        const numValue = parseInt(ctlModelValue);
        if (numValue in ctlModelMap) {
          ctlModelEl.textContent = `${numValue} (${ctlModelMap[numValue]})`;
        } else {
          ctlModelEl.textContent = ctlModelValue;
        }
      } else {
        ctlModelEl.textContent = ctlModelValue;
      }

      console.log(`[Control Dialog] ctlModel: ${ctlModelValue}`);
    } else {
      ctlModelEl.textContent = 'N/A';
    }
  } catch (e) {
    console.error('[Control Dialog] Error reading ctlModel:', e);
    ctlModelEl.textContent = 'N/A';
  }
}

function getControlParameters() {
  const ctlValInput = document.getElementById('ctlVal');
  const ctlNumInput = document.getElementById('ctlNum');
  const originCatSelect = document.getElementById('originCat');
  const originIdentInput = document.getElementById('originOrIdent');
  const testModeCheck = document.getElementById('testMode');
  const modal = document.getElementById('controlModal');

  const cdc = modal.dataset.cdc.toUpperCase();
  let ctlVal = ctlValInput.value.trim();

  // Parse control value based on CDC type
  switch(cdc) {
    case 'SPC':
      if (ctlVal === 'true' || ctlVal === '1' || ctlVal === 'on') {
        ctlVal = true;
      } else if (ctlVal === 'false' || ctlVal === '0' || ctlVal === 'off') {
        ctlVal = false;
      } else {
        throw new Error('Invalid SPC value. Use true/false or on/off');
      }
      break;
    case 'DPC':
      const dpcMap = {
        'on': 'on',
        'off': 'off',
        'intermediate-state': 'intermediateState',
        'intermediate': 'intermediateState',
        'intermediatestate': 'intermediateState'
      };
      ctlVal = dpcMap[ctlVal.toLowerCase()];
      if (!ctlVal) {
        throw new Error('Invalid DPC value. Use on, off, or intermediate-state');
      }
      break;
    case 'APC':
      ctlVal = parseFloat(ctlVal);
      if (isNaN(ctlVal)) {
        throw new Error('Invalid APC value. Must be a number');
      }
      break;
    case 'INC':
    case 'ENC':
      ctlVal = parseInt(ctlVal);
      if (isNaN(ctlVal)) {
        throw new Error('Invalid value. Must be an integer');
      }
      break;
    case 'BSC':
      const bscMap = {
        'step-up': 'stepUp',
        'step-down': 'stepDown',
        'up': 'stepUp',
        'down': 'stepDown',
        'stepup': 'stepUp',
        'stepdown': 'stepDown'
      };
      ctlVal = bscMap[ctlVal.toLowerCase()];
      if (!ctlVal) {
        throw new Error('Invalid BSC value. Use step-up or step-down');
      }
      break;
  }

  return {
    objRef: modal.dataset.objRef,
    ctlVal: ctlVal,
    ctlNum: parseInt(ctlNumInput.value),
    origin: {
      orCat: parseInt(originCatSelect.value),
      orIdent: originIdentInput.value
    },
    test: testModeCheck.checked
  };
}

function showControlResult(success, message) {
  const resultDiv = document.getElementById('controlResult');
  resultDiv.classList.remove('hidden', 'success', 'error');
  resultDiv.classList.add(success ? 'success' : 'error');
  resultDiv.textContent = message;
}

// Control operation handlers
document.getElementById('selectControlBtn').addEventListener('click', async () => {
  const btn = document.getElementById('selectControlBtn');
  const originalText = btn.textContent;

  try {
    btn.disabled = true;
    btn.textContent = 'Selecting...';

    const params = getControlParameters();

    const response = await fetch('/api/control/select', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    });

    const result = await response.json();

    if (response.ok) {
      if (result.ctlNum !== undefined) {
        document.getElementById('ctlNum').value = result.ctlNum;
      }
      showControlResult(true, `Select successful. Control number: ${result.ctlNum || 'N/A'}`);
    } else {
      showControlResult(false, `Select failed: ${result.error || 'Unknown error'}`);
    }

  } catch (error) {
    console.error('Select error:', error);
    showControlResult(false, `Select error: ${error.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
});

document.getElementById('operateControlBtn').addEventListener('click', async () => {
  const btn = document.getElementById('operateControlBtn');
  const originalText = btn.textContent;

  try {
    btn.disabled = true;
    btn.textContent = 'Operating...';

    const params = getControlParameters();

    const response = await fetch('/api/control/operate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    });

    const result = await response.json();

    if (response.ok) {
      showControlResult(true, 'Operate successful');
    } else {
      showControlResult(false, `Operate failed: ${result.error || 'Unknown error'}`);
    }

  } catch (error) {
    console.error('Operate error:', error);
    showControlResult(false, `Operate error: ${error.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
});

document.getElementById('cancelControlBtn').addEventListener('click', async () => {
  const btn = document.getElementById('cancelControlBtn');
  const originalText = btn.textContent;

  try {
    btn.disabled = true;
    btn.textContent = 'Canceling...';

    const params = getControlParameters();

    const response = await fetch('/api/control/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params)
    });

    const result = await response.json();

    if (response.ok) {
      showControlResult(true, 'Cancel successful');
    } else {
      showControlResult(false, `Cancel failed: ${result.error || 'Unknown error'}`);
    }

  } catch (error) {
    console.error('Cancel error:', error);
    showControlResult(false, `Cancel error: ${error.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
});

document.getElementById('closeControlModal').addEventListener('click', () => {
  document.getElementById('controlModal').classList.add('hidden');
});

document.getElementById('closeControlBtn').addEventListener('click', () => {
  document.getElementById('controlModal').classList.add('hidden');
});

// Close modal when clicking outside
document.getElementById('controlModal').addEventListener('click', (e) => {
  if (e.target.id === 'controlModal') {
    document.getElementById('controlModal').classList.add('hidden');
  }
});

// ===== Write Data Value Dialog Functions =====

async function showWriteValueDialog(objRef, fc) {
  const modal = document.getElementById('writeValueModal');
  const titleEl = document.getElementById('writeValueTitle');
  const objRefEl = document.getElementById('writeValueObjRef');
  const typeEl = document.getElementById('writeValueType');
  const currentValueEl = document.getElementById('writeValueCurrent');
  const inputEl = document.getElementById('writeValueInput');
  const validationEl = document.getElementById('writeValueValidation');
  const resultDiv = document.getElementById('writeValueResult');

  // Set dialog info
  titleEl.textContent = `Write Data Value`;
  objRefEl.textContent = objRef;
  typeEl.textContent = 'Reading...';
  currentValueEl.textContent = 'Reading...';

  // Reset form
  inputEl.value = '';
  inputEl.disabled = true;
  validationEl.textContent = '';
  validationEl.className = 'write-value-validation';
  resultDiv.classList.add('hidden');
  resultDiv.className = 'control-result hidden';

  // Store context
  modal.dataset.objRef = objRef;
  modal.dataset.fc = fc;

  // Show modal
  modal.classList.remove('hidden');

  // Read current value to get type information
  try {
    const res = await fetch('/api/readvalue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objRef, fc })
    });

    const data = await res.json();

    if (data.error) {
      typeEl.textContent = 'Unknown';
      currentValueEl.textContent = `Error: ${data.error}`;
      inputEl.disabled = false;
      inputEl.placeholder = 'Enter value';
      modal.dataset.dataType = 'unknown';
    } else if (data.values) {
      // Extract type and current value
      let dataType = 'unknown';
      let currentValue = '';

      if (Array.isArray(data.values) && data.values.length > 0) {
        const firstValue = data.values[0];

        // Handle format: {name: 'f', data: ['float32', 1.5]} (tuple converted to array)
        if (firstValue.data && Array.isArray(firstValue.data) && firstValue.data.length >= 2) {
          dataType = firstValue.data[0];
          currentValue = JSON.stringify(firstValue.data[1]);
        }
        // Handle format: {name: 'f', data: {float32: 1.5}} (dict format)
        else if (firstValue.data && typeof firstValue.data === 'object' && !Array.isArray(firstValue.data)) {
          const typeKeys = Object.keys(firstValue.data).filter(k => k !== 'name' && k !== 'elementName');
          if (typeKeys.length > 0) {
            dataType = typeKeys[0];
            currentValue = JSON.stringify(firstValue.data[dataType]);
          }
        }
        // Handle format: ['float32', 1.5] (direct tuple as array)
        else if (Array.isArray(firstValue) && firstValue.length >= 2 && typeof firstValue[0] === 'string') {
          dataType = firstValue[0];
          currentValue = JSON.stringify(firstValue[1]);
        }
        // Handle format: {name: 'f', float32: 1.5} (flattened)
        else if (typeof firstValue === 'object' && !firstValue.data && !Array.isArray(firstValue)) {
          const typeKeys = Object.keys(firstValue).filter(k => k !== 'name' && k !== 'elementName');
          if (typeKeys.length > 0) {
            dataType = typeKeys[0];
            currentValue = JSON.stringify(firstValue[dataType]);
          }
        }
      }
      // Handle direct object format: {data: {float32: 1.5}} or {float32: 1.5}
      else if (typeof data.values === 'object' && !Array.isArray(data.values)) {
        // Check if it has a 'data' wrapper
        const valueObj = data.values.data || data.values;

        // Handle array format (tuple)
        if (Array.isArray(valueObj) && valueObj.length >= 2) {
          dataType = valueObj[0];
          currentValue = JSON.stringify(valueObj[1]);
        }
        // Handle dict format
        else if (typeof valueObj === 'object' && !Array.isArray(valueObj)) {
          const typeKeys = Object.keys(valueObj).filter(k => k !== 'name' && k !== 'elementName');
          if (typeKeys.length > 0) {
            dataType = typeKeys[0];
            currentValue = JSON.stringify(valueObj[dataType]);
          }
        }
      }

      // Display type and current value
      typeEl.textContent = dataType;
      currentValueEl.textContent = currentValue || 'N/A';

      // Set input type based on data type
      configureInputForType(inputEl, dataType);

      inputEl.disabled = false;
      modal.dataset.dataType = dataType;

      console.log(`[Write Value] Type: ${dataType}, Current: ${currentValue}, Raw response:`, data.values);
    }
  } catch (e) {
    console.error('[Write Value] Error reading current value:', e);
    typeEl.textContent = 'Unknown';
    currentValueEl.textContent = `Error: ${e.message}`;
    inputEl.disabled = false;
    modal.dataset.dataType = 'unknown';
  }
}

function configureInputForType(inputEl, dataType) {
  // Configure input field based on data type
  switch(dataType) {
    case 'boolean':
      inputEl.placeholder = 'true or false';
      inputEl.type = 'text';
      break;
    case 'int8':
    case 'int8u':
    case 'int16':
    case 'int16u':
    case 'int32':
    case 'int32u':
    case 'int64':
      inputEl.placeholder = 'Integer value';
      inputEl.type = 'number';
      inputEl.step = '1';
      break;
    case 'float32':
    case 'float64':
      inputEl.placeholder = 'Decimal value (e.g., 123.45)';
      inputEl.type = 'number';
      inputEl.step = 'any';
      break;
    case 'visString32':
    case 'visString64':
    case 'visString65':
    case 'visString129':
    case 'visString255':
    case 'string':
      inputEl.placeholder = 'Text value';
      inputEl.type = 'text';
      break;
    case 'enumerated':
      inputEl.placeholder = 'Enumerated value';
      inputEl.type = 'text';
      break;
    case 'timeStamp':
      inputEl.placeholder = 'Unix timestamp or ISO date';
      inputEl.type = 'text';
      break;
    case 'octetString':
      inputEl.placeholder = 'Hex string (e.g., 0x1234)';
      inputEl.type = 'text';
      break;
    default:
      inputEl.placeholder = 'Enter value';
      inputEl.type = 'text';
  }
}

function validateWriteValue(value, dataType) {
  // Validate value based on data type
  const trimmedValue = value.trim();

  if (!trimmedValue) {
    return { valid: false, message: 'Value cannot be empty' };
  }

  switch(dataType) {
    case 'boolean':
      const boolValue = trimmedValue.toLowerCase();
      if (boolValue !== 'true' && boolValue !== 'false' &&
          boolValue !== '1' && boolValue !== '0') {
        return { valid: false, message: 'Must be true, false, 1, or 0' };
      }
      return { valid: true, message: 'Valid boolean value' };

    case 'int8':
    case 'int16':
    case 'int32':
    case 'int64':
      const intVal = parseInt(trimmedValue);
      if (isNaN(intVal)) {
        return { valid: false, message: 'Must be a valid integer' };
      }
      return { valid: true, message: 'Valid integer' };

    case 'int8u':
    case 'int16u':
    case 'int32u':
      const uintVal = parseInt(trimmedValue);
      if (isNaN(uintVal) || uintVal < 0) {
        return { valid: false, message: 'Must be a non-negative integer' };
      }
      return { valid: true, message: 'Valid unsigned integer' };

    case 'float32':
    case 'float64':
      const floatVal = parseFloat(trimmedValue);
      if (isNaN(floatVal)) {
        return { valid: false, message: 'Must be a valid number' };
      }
      return { valid: true, message: 'Valid decimal number' };

    case 'visString32':
    case 'visString64':
    case 'visString65':
    case 'visString129':
    case 'visString255':
    case 'string':
      const maxLen = parseInt(dataType.replace(/[^0-9]/g, '')) || 255;
      if (trimmedValue.length > maxLen) {
        return { valid: false, message: `String too long (max ${maxLen} chars)` };
      }
      return { valid: true, message: 'Valid string' };

    default:
      return { valid: true, message: 'Ready to write' };
  }
}

// Add input validation on keyup
document.getElementById('writeValueInput').addEventListener('input', () => {
  const inputEl = document.getElementById('writeValueInput');
  const validationEl = document.getElementById('writeValueValidation');
  const modal = document.getElementById('writeValueModal');
  const dataType = modal.dataset.dataType;

  const validation = validateWriteValue(inputEl.value, dataType);

  validationEl.className = 'write-value-validation';
  if (validation.valid) {
    validationEl.classList.add('valid');
  } else {
    validationEl.classList.add('invalid');
  }
  validationEl.textContent = validation.message;
});

// Write button handler
document.getElementById('writeValueBtn').addEventListener('click', async () => {
  const btn = document.getElementById('writeValueBtn');
  const originalText = btn.textContent;
  const modal = document.getElementById('writeValueModal');
  const inputEl = document.getElementById('writeValueInput');
  const validationEl = document.getElementById('writeValueValidation');
  const resultDiv = document.getElementById('writeValueResult');

  const objRef = modal.dataset.objRef;
  const fc = modal.dataset.fc;
  const dataType = modal.dataset.dataType;
  const value = inputEl.value.trim();

  // Validate before sending
  const validation = validateWriteValue(value, dataType);
  if (!validation.valid) {
    validationEl.className = 'write-value-validation invalid';
    validationEl.textContent = validation.message;
    return;
  }

  try {
    btn.disabled = true;
    btn.textContent = 'Writing...';

    // Convert value to appropriate type
    let convertedValue;
    switch(dataType) {
      case 'boolean':
        convertedValue = (value.toLowerCase() === 'true' || value === '1');
        break;
      case 'int8':
      case 'int8u':
      case 'int16':
      case 'int16u':
      case 'int32':
      case 'int32u':
      case 'int64':
        convertedValue = parseInt(value);
        break;
      case 'float32':
      case 'float64':
        convertedValue = parseFloat(value);
        break;
      default:
        convertedValue = value;
    }

    const response = await fetch('/api/writevalue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        objRef,
        fc,
        value: convertedValue,
        dataType
      })
    });

    console.log('[Write Value] Request:', { objRef, fc, value: convertedValue, dataType, originalValue: value });

    const result = await response.json();

    resultDiv.classList.remove('hidden');
    if (response.ok && result.success) {
      resultDiv.className = 'control-result success';
      resultDiv.textContent = 'Value written successfully';

      // Update current value display
      document.getElementById('writeValueCurrent').textContent = JSON.stringify(convertedValue);

      // Clear input after successful write
      setTimeout(() => {
        inputEl.value = '';
        validationEl.textContent = '';
        validationEl.className = 'write-value-validation';
      }, 1000);
    } else {
      resultDiv.className = 'control-result error';
      resultDiv.textContent = `Write failed: ${result.error || 'Unknown error'}`;
    }

  } catch (error) {
    console.error('Write error:', error);
    resultDiv.classList.remove('hidden');
    resultDiv.className = 'control-result error';
    resultDiv.textContent = `Write error: ${error.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
});

// Close write value modal handlers
document.getElementById('closeWriteValueModal').addEventListener('click', () => {
  document.getElementById('writeValueModal').classList.add('hidden');
});

document.getElementById('cancelWriteValueBtn').addEventListener('click', () => {
  document.getElementById('writeValueModal').classList.add('hidden');
});

document.getElementById('writeValueModal').addEventListener('click', (e) => {
  if (e.target.id === 'writeValueModal') {
    document.getElementById('writeValueModal').classList.add('hidden');
  }
});
