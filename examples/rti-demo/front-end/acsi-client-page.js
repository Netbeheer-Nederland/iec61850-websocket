/* ==============================================
   ACSI Client - IEC 61850 Client Page
   ============================================== */

(function initACSIClientPage() {
    // Guard against double-loading
    if (window.__acsiClientPageLoaded) {
        return;
    }
    window.__acsiClientPageLoaded = true;
    // Protocol Messages state
    let protocolMessages = [];
    let isMonitoring = false;
    let monitorInterval = null;

    // Put this at the top of initACSIClientPage(), outside all other functions
    document.addEventListener('click', () => hideContextMenu());
    document.addEventListener('contextmenu', (e) => {
        // Hide if clicking outside the menu
        if (contextMenu && !contextMenu.contains(e.target)) {
            hideContextMenu();
        }
    });
    // ==================== API Definitions ====================
    const apiDefinitions = [
        { id: 'connect', label: 'POST /api/connect', method: 'POST', path: '/api/connect' },
        { id: 'disconnect', label: 'POST /api/disconnect', method: 'POST', path: '/api/disconnect' },
        { id: 'model-tree', label: 'POST /api/model/tree', method: 'POST', path: '/api/model/tree' },
        { id: 'data-definition', label: 'POST /api/getDataDefinition', method: 'POST', path: '/api/getDataDefinition' },
        { id: 'read', label: 'POST /api/readvalue', method: 'POST', path: '/api/readvalue' },
        { id: 'write', label: 'POST /api/writevalue', method: 'POST', path: '/api/writevalue' },
        { id: 'dataset-directory', label: 'POST /api/getDataSetDirectory', method: 'POST', path: '/api/getDataSetDirectory' },
        { id: 'actions-logs', label: 'GET /api/actions_logs', method: 'GET', path: '/api/actions_logs', sampleBody: '' },
        { id: 'clear-logs', label: 'POST /api/clear_logs', method: 'POST', path: '/api/clear_logs', sampleBody: '' },
        { id: 'status', label: 'GET /api/status', method: 'GET', path: '/api/status'},
        { id: 'operate', label: 'POST /api/operate', method: 'POST', path: '/api/operate'},
        { id: 'urcb-read', label: 'POST /api/urcb-read', method: 'POST', path: '/api/urcb-read'},
        { id: 'brcb-read', label: 'POST /api/brcb-read', method: 'POST', path: '/api/brcb-read'},
        { id: 'brcb-write', label: 'POST /api/brcb-write', method: 'POST', path: '/api/brcb-write'},
        { id: 'urcb-write', label: 'POST /api/urcb-write', method: 'POST', path: '/api/urcb-write'},
    ];

    function getApiById(id) {
        return apiDefinitions.find(api => api.id === id);
    }

    // ==================== Helper Functions ====================
    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function getBffBaseUrl() {
        if (window.app && window.app.bffBaseUrl) {
            return window.app.bffBaseUrl;
        }

        const storedHost = localStorage.getItem('bffHost');
        const storedPort = localStorage.getItem('bffPort');
        if (storedHost && /^\d+$/.test(String(storedPort || ''))) {
            const portNum = Number(storedPort);
            if (portNum > 0 && portNum <= 65535) {
                return `http://${storedHost}:${portNum}`;
            }
        }

        if (window.location && window.location.origin && window.location.origin !== 'null') {
            return window.location.origin;
        }

        // Default to BFF server port
        return 'http://127.0.0.1:5000';
    }

    function buildBffApiUrl(path, targetValue) {
        const baseUrl = getBffBaseUrl();
        if (!baseUrl) {
            throw new Error('BFF base URL is not configured.');
        }
        if (!String(path || '').startsWith('/api/')) {
            throw new Error(`Blocked non-BFF API path: ${path}`);
        }
        const requestUrl = new URL(`${baseUrl}${path}`, window.location.origin);
        if (targetValue) {
            requestUrl.searchParams.set('target', targetValue);
        }
        return requestUrl.toString();
    }

    async function ensureBffHealthy() {
        const healthUrl = buildBffApiUrl('/api/health');
        const response = await fetch(healthUrl, { method: 'GET' });
        if (!response.ok) {
            throw new Error(`BFF health check failed with HTTP ${response.status}`);
        }
        const payload = await response.json();
        const bffStatus = payload && payload.bff && payload.bff.status;
        if (String(bffStatus || '').toLowerCase() !== 'ok') {
            throw new Error('BFF health check returned non-ok status');
        }
    }

    // ==================== Protocol Messages Helper Functions ====================

    function renderProtocolMessages(rootElement) {
        const messagesEl = rootElement.querySelector('#acsi-protocol-messages');
        if (!messagesEl) {
            return;
        }

        if (protocolMessages.length === 0) {
            messagesEl.innerHTML = '<div class="acsi-log-empty">No log messages yet. Click Start to begin monitoring.</div>';
            return;
        }

        messagesEl.innerHTML = protocolMessages.map((entry) => {
            const action = entry.payload;
            const hasDetail = action.detail && Object.keys(action.detail).length > 0;
            const detailJson = hasDetail ? JSON.stringify(action.detail, null, 2).replace(/</g, '&lt;').replace(/>/g, '&gt;') : '';
            const levelClass = action.level === 'error' ? 'message-direction recv' : action.level === 'warning' ? 'message-direction send' : '';
            
            return `
                <div class="acsi-log-item acsi-log-${action.level}">
                    <div class="acsi-log-head">
                        <span class="acsi-log-time">#${action.id} - ${action.time}</span>
                        <span class="acsi-log-message ${levelClass}">${escapeHtml(action.message)}</span>
                    </div>
                    ${hasDetail ? `<pre class="acsi-log-details">${detailJson}</pre>` : ''}
                </div>
            `;
        }).join('');
    }

    function addProtocolMessagesEntry(messagesArray) {
        const existingIds = new Set(protocolMessages.map(entry => entry.payload.id));
        
        if (Array.isArray(messagesArray)) {
            messagesArray.forEach(msg => {
                if (msg && msg.id && !existingIds.has(msg.id)) {
                    protocolMessages.unshift({
                        timestamp: new Date().toLocaleTimeString(),
                        payload: msg,
                    });
                    existingIds.add(msg.id);
                }
            });
        } else if (messagesArray && messagesArray.id && !existingIds.has(messagesArray.id)) {
            protocolMessages.unshift({
                timestamp: new Date().toLocaleTimeString(),
                payload: messagesArray,
            });
        }
        if (protocolMessages.length > 30) {
            protocolMessages = protocolMessages.slice(0, 30);
        }
    }

    function stopMonitoring() {
        isMonitoring = false;
        if (monitorInterval) {
            clearInterval(monitorInterval);
            monitorInterval = null;
        }
    }

    function updateMessagesStatus(rootElement, statusText) {
        const statusEl = rootElement.querySelector('#messages-status');
        if (statusEl) {
            statusEl.textContent = statusText;
        }
    }

    async function fetchActionLogs(rootElement, targetValue) {
        const api = getApiById('actions-logs');
        const result = await executeApiCall(api, targetValue, {});
        
        if (result && result.ok && result.payload) {
            const actions = result.payload.result?.actions || result.payload.actions || [];
            if (Array.isArray(actions) && actions.length > 0) {
                addProtocolMessagesEntry(actions);
                renderProtocolMessages(rootElement);
                const statusText = `Last updated: ${new Date().toLocaleTimeString()} - ${targetValue} (${protocolMessages.length} logs)`;
                updateMessagesStatus(rootElement, statusText);
            }
        }
    }

    function parsePythonDictString(pythonStr) {
            if (!pythonStr || typeof pythonStr !== 'string') {
                return pythonStr;
            }
            try {
                const jsonStr = pythonStr
                    .replace(/'/g, '"')
                    .replace(/True/g, 'true')
                    .replace(/False/g, 'false')
                    .replace(/None/g, 'null');
                return JSON.parse(jsonStr);
            } catch (e) {
                console.log('Warning: Could not parse Python dict string as JSON:', e);
                return pythonStr;
            }
    }

    function formatPayloadForDisplay(payload) {
            if (!payload || typeof payload !== 'object') {
                return payload;
            }
            const formatted = JSON.parse(JSON.stringify(payload));

            // Parse any stringified Python dicts in the result
            if (formatted.result && typeof formatted.result === 'object') {
                if (formatted.result.status && typeof formatted.result.status === 'string') {
                    formatted.result.status = parsePythonDictString(formatted.result.status);
                }
                if (formatted.result.message && typeof formatted.result.message === 'string') {
                    formatted.result.message = parsePythonDictString(formatted.result.message);
                }
            }

            // Also check at top level
            if (formatted.status && typeof formatted.status === 'string') {
                formatted.status = parsePythonDictString(formatted.status);
            }

            return formatted;
    }

    function setUpdatedStatusText(text, isError = false) {
        const updatedStatusEl = document.getElementById('acsi-endpoint-updated-status');
        if (!updatedStatusEl) {
            return;
        }
        updatedStatusEl.textContent = text;
        updatedStatusEl.classList.toggle('acsi-model-error', !!isError);
    }

    async function updateStatus(endpointTarget)
        {
            setUpdatedStatusText('Loading status...');
            await ensureBffHealthy();

            const api = getApiById('status');
            const result = await executeApiCall(api, endpointTarget, null);

            if (result && result.ok && result.payload) {

                const addressEl = document.getElementById('acsi-address-field');
                const statusEl = document.getElementById('acsi-status-field');
                const apEl = document.getElementById('acsi-ap-field');

                const formattedPayload = formatPayloadForDisplay(result.payload);
                const text = `Connected clients: ${formattedPayload.result.status.connectedClients} - IED: ${formattedPayload.result.status.modelName} - Model source: ${formattedPayload.result.status.modelSource}`
                setUpdatedStatusText(text);
                addressEl.textContent = `${formattedPayload.result.host}:${formattedPayload.result.port}`
                statusEl.textContent = `${formattedPayload.result.status}`
                apEl.textContent = `${formattedPayload.result.accessPoints}`
                console.log('success', 'GET /api/status -> HTTP 200', JSON.stringify(formattedPayload, null, 2));
            } else {
                const message = result ? `HTTP ${result.status}` : 'Unknown error';
                setUpdatedStatusText(`Updated status: failed (${message})`, true);
                console.log('error', 'GET /api/status failed', message);
            }
        }

    async function startMonitoring(rootElement, targetValue) {
        if (isMonitoring) {
            return;
        }

        if (!targetValue) {
            updateMessagesStatus(rootElement, 'Please select an endpoint first');
            return;
        }

        stopMonitoring();
        isMonitoring = true;
        
        const startBtn = rootElement.querySelector('#messages-start-btn');
        const stopBtn = rootElement.querySelector('#messages-stop-btn');
        const reloadBtn = rootElement.querySelector('#reloadMessagesBtn');
        const messagesIntervalSelect = rootElement.querySelector('#messages-interval');
        
        if (startBtn) startBtn.disabled = true;
        if (stopBtn) stopBtn.disabled = false;
        if (reloadBtn) reloadBtn.disabled = false;
        
        updateMessagesStatus(rootElement, `Monitoring ${targetValue}...`);
        
        await fetchActionLogs(rootElement, targetValue);
        
        const interval = messagesIntervalSelect ? parseInt(messagesIntervalSelect.value) : 5000;
        monitorInterval = setInterval(() => {
            fetchActionLogs(rootElement, targetValue);
        }, interval);
    }

    async function clearMessages(rootElement, targetValue) {
        if (!targetValue) {
            updateMessagesStatus(rootElement, 'Please select an endpoint first');
            return;
        }

        const clearApi = getApiById('clear-logs');
        const result = await executeApiCall(clearApi, targetValue, {});
        
        if (result && result.ok) {
            protocolMessages = [];
            renderProtocolMessages(rootElement);
            updateMessagesStatus(rootElement, 'Messages cleared');
        } else {
            const message = result ? `HTTP ${result.status}` : 'Unknown error';
            updateMessagesStatus(rootElement, `Error clearing messages: ${message}`);
        }
        
        setTimeout(() => {
            if (isMonitoring) {
                updateMessagesStatus(rootElement, `Monitoring ${targetValue}...`);
            } else {
                updateMessagesStatus(rootElement, `Ready to monitor ${targetValue}`);
            }
        }, 2000);
    }

    // ==================== Core API Call Function ====================
       async function executeApiCall(selected, targetValue, bodyOverride) {
            if (!selected) {
                return null;
            }

            let url;
            try {
                url = url = buildBffApiUrl('/api/execute');
            } catch (error) {
                console.error(`Blocked ${selected.label}:`, error && error.message ? error.message : error);
                return null;
            }

            const options = {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
            };

            const payload = {
                target: targetValue,
                method: selected.method,
                path: selected.path,
            };

            if (bodyOverride) {
                payload.body = bodyOverride;
            }

           options.body = JSON.stringify(payload);

            try {
                const response = await fetch(url, options);
                const rawText = await response.text();
                let parsedPayload = null;

                try {
                    parsedPayload = JSON.parse(rawText);
                } catch (error) {
                    // keep raw text for non-JSON responses
                }

                return {
                    ok: response.ok,
                    status: response.status,
                    payload: parsedPayload,
                    rawText,
                };
            } catch (error) {
                console.error(`Request failed for ${selected.label}:`, error && error.message ? error.message : error);
                return null;
            }
       }

    // ==================== UI Functions ====================
    function showStatus(rootElement, message, type = 'info') {
        const statusDiv = rootElement.querySelector('#acsi-client-status');
        const statusMessage = rootElement.querySelector('#acsi-client-status-message');

        if (!statusDiv || !statusMessage) return;

        statusDiv.style.display = 'block';
        statusMessage.textContent = message;

        const colorMap = {
            'success': 'var(--success-color)',
            'error': 'var(--danger-color)',
            'warning': 'var(--warning-color)',
            'info': 'var(--info-color)'
        };

        statusDiv.style.borderLeft = `4px solid ${colorMap[type] || colorMap['info']}`;
    }

    function buildTargetValue(host, port) {
        if (!host || port === undefined || port === null) {
            return '';
        }
        return `${host}:${port}`;
    }

    function getDefaultTargetFromEndpoint(endpoint) {
        if (!endpoint) {
            return '';
        }
        return buildTargetValue(endpoint.host, endpoint.port);
    }

    function updateEndpointBadge(host, port, name = '') {
        const nameEl = document.getElementById('endpoint-name');
        const hostEl = document.getElementById('endpoint-host');
        const portEl = document.getElementById('endpoint-port');
        
        if (nameEl) nameEl.textContent = name || 'Endpoint';
        if (hostEl) hostEl.textContent = host || 'host';
        if (portEl) portEl.textContent = port || 'port';
    }

    // ==================== Event Handlers ====================
    function setupEventListeners(rootElement, endpoint) {

        const cp = rootElement.querySelector('#acsi-client-cp-page').value.trim() || 'cp1';

        const connectBtn = rootElement.querySelector('#acsi-client-connect-page-btn');
        const disconnectBtn = rootElement.querySelector('#acsi-client-disconnect-page-btn');
        const fetchModelBtn = rootElement.querySelector('#acsi-client-fetch-model-btn');
        const messagesStartBtn = rootElement.querySelector('#messages-start-btn');
        const messagesStopBtn = rootElement.querySelector('#messages-stop-btn');
        const messagesClearBtn = rootElement.querySelector('#messages-clear-btn');
        const reloadMessagesBtn = rootElement.querySelector('#reloadMessagesBtn');
        const reloadStatusBtn = rootElement.querySelector('#acsi-reload-status-btn');

        const endpointTarget = getDefaultTargetFromEndpoint(endpoint);

        // Control event listeners - FIXED
        const controlModal = rootElement.querySelector('#controlModal');
        const closeControlModal = rootElement.querySelector('#closeControlModal');
        const closeControlBtn = rootElement.querySelector('#closeControlBtn');
        const cancelControlBtn = rootElement.querySelector('#cancelControlBtn');
        const selectControlBtn = rootElement.querySelector('#selectControlBtn');
        const operateControlBtn = rootElement.querySelector('#operateControlBtn');

        const hideModal = () => {
            if (controlModal) controlModal.classList.add('hidden');
        };

        // Close modal handlers
        if (closeControlModal) {
            closeControlModal.onclick = hideModal;
        }
        if (closeControlBtn) {
            closeControlBtn.onclick = hideModal;
        }
        if (cancelControlBtn) {
            cancelControlBtn.onclick = hideModal;
        }

        // Click outside to close
        if (controlModal) {
            controlModal.addEventListener('click', (e) => {
                if (e.target === controlModal) {
                    hideModal();
                }
            });
        }

        // Select button handler
        if (selectControlBtn) {
            selectControlBtn.addEventListener('click', async () => {
                const btn = selectControlBtn;
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
                        showControlResult(true, 'Select successful - Now you can Operate');
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
        }

        // Operate button handler - FIXED selector
        if (operateControlBtn) {
            operateControlBtn.addEventListener('click', async () => {
                const btn = operateControlBtn;
                const originalText = btn.textContent;
                try {
                    btn.disabled = true;
                    btn.textContent = 'Operating...';

                    const params = getControlParameters();
                    const response = await executeApiCall(getApiById('operate'), endpointTarget, params);
                    if (response.ok) {
                        showControlResult(true, 'Operate successful');
                    } else {
                        showControlResult(false, `Operate failed: ${response.error || 'Unknown error'}`);
                    }
                } catch (error) {
                    console.error('Operate error:', error);
                    showControlResult(false, `Operate error: ${error.message}`);
                } finally {
                    btn.disabled = false;
                    btn.textContent = originalText;
                }
            });
        }


        if (connectBtn) {
            connectBtn.addEventListener('click', () => handleConnect(rootElement, endpoint));
        }

        if (disconnectBtn) {
            disconnectBtn.addEventListener('click', () => handleDisconnect(rootElement, endpoint));
        }

        if (fetchModelBtn) {
            fetchModelBtn.addEventListener('click', () => handleFetchModel(rootElement, endpoint));
        }

        // Protocol Messages event listeners
        if (messagesStartBtn) {
            messagesStartBtn.addEventListener('click', () => {
                startMonitoring(rootElement, endpointTarget);
            });
        }

        if (messagesStopBtn) {
            messagesStopBtn.addEventListener('click', () => {
                stopMonitoring();
                const startBtn = rootElement.querySelector('#messages-start-btn');
                const stopBtn = rootElement.querySelector('#messages-stop-btn');
                if (startBtn) startBtn.disabled = false;
                if (stopBtn) stopBtn.disabled = true;
                updateMessagesStatus(rootElement, `Ready to monitor ${endpointTarget || 'endpoint'}`);
            });
        }

        if (reloadMessagesBtn) {
            reloadMessagesBtn.addEventListener('click', async () => {
                await fetchActionLogs(rootElement, endpointTarget);
            });
        }

        if (reloadStatusBtn) {
            reloadStatusBtn.addEventListener('click', async () => {
                if (!endpointTarget) {
                    setUpdatedStatusText('Updated status: blocked (missing selected endpoint address).', true);
                    return;
                }

                try {
                    reloadStatusBtn.disabled = true;
                    updateStatus(endpointTarget);
                } catch (error) {
                    const message = String(error && error.message ? error.message : error);
                    setUpdatedStatusText(`Updated status: failed (${message})`, true);
                    console.log('error', 'GET /api/status failed', message);
                } finally {
                    reloadStatusBtn.disabled = false;
                }
            });
        }

        if (messagesClearBtn) {
            messagesClearBtn.addEventListener('click', () => {
                clearMessages(rootElement, endpointTarget);
            });
        }

        // Initialize messages status
        updateMessagesStatus(rootElement, 'Select an endpoint and click Start');

        (async () => {
            let targetToUse = endpointTarget;

            if (!targetToUse) {
                const storedHost = localStorage.getItem('bffHost');
                const storedPort = localStorage.getItem('bffPort');
                if (storedHost && storedPort) {
                    targetToUse = buildTargetValue(storedHost, Number(storedPort));
                }
            }

            if (targetToUse) {
                try {

                if (!document.getElementById('page-acsi-client')?.classList.contains('active')) {
                    return;
                }
                    await updateStatus(targetToUse);
                } catch (error) {
                    console.log('Auto status load failed:', error);
                }
            }
        })();
    }

    async function handleConnect(rootElement, endpoint) {
        const endpointTarget = getDefaultTargetFromEndpoint(endpoint);
        const host = rootElement.querySelector('#acsi-client-host-page').value.trim();
        const port = parseInt(rootElement.querySelector('#acsi-client-port-page').value.trim());
        const cp = rootElement.querySelector('#acsi-client-cp-page').value.trim() || 'cp1';

        if (!host || !port) {
            //showStatus(rootElement, 'Please enter both host and port', 'error');
            return;
        }

        if (isNaN(port) || port < 1 || port > 65535) {
            //showStatus(rootElement, 'Invalid port number', 'error');
            return;
        }

        //showStatus(rootElement, 'Connecting...', 'info');
        const result = await executeApiCall(
            getApiById('connect'),
            endpointTarget,
            { host, port, cp }
        );

        if (result && result.ok) {
            //showStatus(rootElement, `Connected to ${host}:${port}`, 'success');
            rootElement.querySelector('#acsi-client-connect-page-btn').disabled = true;
            rootElement.querySelector('#acsi-client-disconnect-page-btn').disabled = false;
            updateEndpointBadge(host, port, '');
            
            // Enable message monitoring buttons
            const startBtn = rootElement.querySelector('#messages-start-btn');
            if (startBtn) startBtn.disabled = false;
        } else {
            const error = result?.payload?.error || result?.rawText || 'Unknown error';
            //showStatus(rootElement, `Connection failed: ${error}`, 'error');
        }
    }

    async function handleDisconnect(rootElement, endpoint) {
        const endpointTarget = getDefaultTargetFromEndpoint(endpoint);
        const host = rootElement.querySelector('#acsi-client-host-page').value.trim();
        const port = parseInt(rootElement.querySelector('#acsi-client-port-page').value.trim());
        const cp = rootElement.querySelector('#acsi-client-cp-page').value.trim() || 'cp1';

        //showStatus(rootElement, 'Disconnecting...', 'info');
        
        const result = await executeApiCall(
            getApiById('disconnect'),
            endpointTarget,
            { host, port, cp }
        );

        if (result && result.ok) {
            //showStatus(rootElement, 'Disconnected', 'info');
            rootElement.querySelector('#acsi-client-connect-page-btn').disabled = false;
            rootElement.querySelector('#acsi-client-disconnect-page-btn').disabled = true;
            rootElement.querySelector('#acsi-client-tree-container-page').style.display = 'none';
            updateEndpointBadge('', '', '');
            
            // Disable message monitoring buttons
            const startBtn = rootElement.querySelector('#messages-start-btn');
            const stopBtn = rootElement.querySelector('#messages-stop-btn');
            if (startBtn) startBtn.disabled = true;
            if (stopBtn) stopBtn.disabled = true;
            stopMonitoring();
        } else {
            const error = result?.payload?.error || result?.rawText || 'Unknown error';
            //showStatus(rootElement, `Disconnect failed: ${error}`, 'error');
        }

        setUpdatedStatusText('Updated status: not loaded yet.');
        document.getElementById('acsi-address-field').textContent = '';
        document.getElementById('acsi-status-field').textContent = '';
        document.getElementById('acsi-ap-field').textContent = '';
    }

    // Context menu for reading data values
    let contextMenu = null;
    let contextMenuTarget = null;

    function createContextMenu(items) {
        if (contextMenu) {
            contextMenu.remove();
            contextMenu = null;
        }

        const menu = document.createElement('div');
        menu.id = 'contextMenu';
        menu.className = 'context-menu';

        items.forEach(item => {
            if (item.divider) {
                const divider = document.createElement('div');
                divider.className = 'context-menu-divider';
                menu.appendChild(divider);
                return;
            }
            const menuItem = document.createElement('div');
            menuItem.className = `context-menu-item${item.danger ? ' danger' : ''}`;
            if (item.icon) {
                const icon = document.createElement('i');
                icon.className = `fas ${item.icon}`;
                menuItem.appendChild(icon);
            }
            const label = document.createElement('span');
            label.textContent = item.label;
            menuItem.appendChild(label);
            menuItem.addEventListener('click', () => {
                if (typeof item.action === 'function') item.action();
                hideContextMenu();
            });
            menu.appendChild(menuItem);
        });

        document.body.appendChild(menu);
        contextMenu = menu;
        return menu;
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

      function asn1TimeStampToISOString(ts) {
          if (!ts || typeof ts.secondSinceEpoch !== 'number') return '';
          const seconds = ts.secondSinceEpoch;
          let ms = 0;
          if (typeof ts.fractionOfSecond === 'number') {
            ms = Math.floor(ts.fractionOfSecond / 1000);
          }
          const date = new Date((seconds * 1000) + ms);
          return date.toISOString();
      }

      function extractActualValue(val) {
        if (Array.isArray(val) && val.length > 0 && val[0] && val[0].data) {
          const dataObj = val[0].data;
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

      if (Array.isArray(valueData) && valueData.length > 0) {
        const firstItem = valueData[0];

        if (firstItem && firstItem.data && Array.isArray(firstItem.data)) {
          if (firstItem.data.length === 2 &&
              typeof firstItem.data[0] === 'string' &&
              firstItem.data[0] === 'structure') {
            treeValueSpan.textContent = '—';
            treeValueSpan.style.color = '#4caf50';
            return;
          }

          if (firstItem.data.length === 2 && typeof firstItem.data[0] === 'string') {
            const value = firstItem.data[1];
            let displayValue = value;
            if (value && typeof value === 'object' && typeof value.secondSinceEpoch === 'number') {
              displayValue = asn1TimeStampToISOString(value) || JSON.stringify(value);
            } else if (typeof value === 'number') {
              displayValue = value.toFixed(2);
            } else if (typeof value === 'boolean') {
              displayValue = value ? 'true' : 'false';
            } else if (typeof value === 'object') {
              displayValue = JSON.stringify(value);
            }
            treeValueSpan.textContent = displayValue;
            treeValueSpan.style.color = '#4caf50';
            return;
          }
        }
      }

      const actualValue = extractActualValue(valueData);
      treeValueSpan.textContent = JSON.stringify(actualValue);
      treeValueSpan.style.color = '#4caf50';
    }

    async function readDataValue(objRef, fc, endpoint, cp) {
      console.log('[readDataValue] Reading:', objRef, 'FC:', fc);
      const endpointTarget = getDefaultTargetFromEndpoint(endpoint);
      const host = document.getElementById('acsi-client-host-page').value.trim();
      const port = document.getElementById('acsi-client-port-page').value.trim();

      try {
        const res = await executeApiCall(
            getApiById('read'),
            endpointTarget,
            { objRef, fc, cp }
        );

        const data = res?.payload || { error: 'No response payload' };
        console.log('[readDataValue] Response:', data);

        if (data.error) {
          console.log('[readDataValue] Error reading:', objRef, data.error);
          updateTreeValueDisplay(objRef, data.error, true);
        } else {
          console.log('[readDataValue] Updating tree display for:', objRef, data.result?.value);
          updateTreeValueDisplay(objRef, data.result?.value, false);
        }
      } catch (e) {
        console.error('[readDataValue] Exception:', e);
        updateTreeValueDisplay(objRef, e.message, true);
      }
    }

    async function writeDataValue(objRef, fc, endpoint, value, value_type, cp) {
      console.log('[writeDataValue] Writing:', objRef, 'FC:', fc, 'Value:', value);
      const endpointTarget = getDefaultTargetFromEndpoint(endpoint);

      try {
        const res = await executeApiCall(
            getApiById('write'),
            endpointTarget,
            { objRef, fc, value, value_type, cp }
        );

        const data = res?.payload || { error: 'No response payload' };
        console.log('[writeDataValue] Response:', data);

        if (data.error) {
          console.error('[writeDataValue] Error:', data.error);
          throw new Error(data.error);
        }

        updateTreeValueDisplay(objRef, data.result?.value || value, false);
        return data;
      } catch (e) {
        console.error('[writeDataValue] Exception:', e);
        updateTreeValueDisplay(objRef, e.message, true);
        throw e;
      }
    }

    async function showContextMenuForDataObject(e, objRef) {
      e.preventDefault();
      e.stopPropagation();

      // Immediately show a provisional menu with a loading indicator
      const provisionalMenu = createContextMenu([
        { label: 'Read DO', action: () => {} }
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
    }


    // List of controllable CDC types
    const CONTROLLABLE_CDCS = ['SPC', 'DPC', 'APC', 'INC', 'ENC', 'BSC', 'ING', 'ASG', 'CTE', 'ENG'];

//    async function showControlDialog(objRef, objName, cdc, endpoint) {
//         // Use root.querySelector to find modal within the rendered template scope
//        const root = document.querySelector('.acsi-server-page') || document;
//
//        // Find all modal elements with null checks
//        const modal = root.querySelector('#controlModal');
//        const controlTitle = root.querySelector('#controlTitle');
//        const controlObjRef = root.querySelector('#controlObjRef');
//        const controlCdcType = root.querySelector('#controlCdcType');
//        const controlCtlModel = root.querySelector('#controlCtlModel');
//        const ctlValInput = root.querySelector('#ctlVal');
//        const ctlNumInput = root.querySelector('#ctlNum');
//        const originCat = root.querySelector('#originCat');
//        const originOrIdent = root.querySelector('#originOrIdent');
//        const testMode = root.querySelector('#testMode');
//        const controlResult = root.querySelector('#controlResult');
//        const selectControlBtn = root.querySelector('#selectControlBtn');
//        const operateControlBtn = root.querySelector('#operateControlBtn');
//        const cancelControlBtn = root.querySelector('#cancelControlBtn');
//        const closeControlBtn = root.querySelector('#closeControlBtn');
//        const closeControlModal = root.querySelector('#closeControlModal');
//
//        // Early return if modal doesn't exist
//        if (!modal) {
//            console.error('Control modal not found');
//            return;
//        }
//
//
//          // Reset form
//          ctlValInput.value = '';
//          ctlNumInput.value = '0';
//          originCat.value = '1';
//          originOrIdent.value = '0';
//          testMode.checked = false;
//          //resultDiv.classList.add('hidden');
//          //resultDiv.className = 'control-result hidden';
//
//          // Set placeholder and type based on CDC
//          switch(cdc.toUpperCase()) {
//            case 'SPC':
//              ctlValInput.placeholder = 'true or false';
//              ctlValInput.type = 'text';
//              break;
//            case 'DPC':
//              ctlValInput.placeholder = 'on, off, or intermediate-state';
//              ctlValInput.type = 'text';
//              break;
//            case 'APC':
//              ctlValInput.placeholder = 'Float value (e.g., 123.45)';
//              ctlValInput.type = 'number';
//              ctlValInput.step = 'any';
//              break;
//            case 'INC':
//            case 'ENC':
//              ctlValInput.placeholder = 'Integer value';
//              ctlValInput.type = 'number';
//              ctlValInput.step = '1';
//              break;
//            case 'BSC':
//              ctlValInput.placeholder = 'step-up or step-down';
//              ctlValInput.type = 'text';
//              break;
//            default:
//              ctlValInput.placeholder = 'Control value';
//              ctlValInput.type = 'text';
//          }
//
//          // Store current control context
//          modal.dataset.objRef = objRef;
//          modal.dataset.cdc = cdc;
//
//          // Show modal
//          modal.classList.remove('hidden');
//
//          const endpointTarget = getDefaultTargetFromEndpoint(endpoint);
//
//
//          // Read ctlModel attribute value
//          try {
//            const ctlModelRef = `${objRef}.ctlModel`;
//            const res = await executeApiCall(getApiById('read'), endpointTarget, { objRef: ctlModelRef, fc: 'cf' });
//            const data = res;
//
//            if (data.error) {
//              //ctlModelEl.textContent = 'N/A';
//              console.log(`[Control Dialog] Could not read ctlModel: ${data.error}`);
//            } else if (data.values) {
//              // Extract the ctlModel value
//              let ctlModelValue = 'N/A';
//
//              if (Array.isArray(data.values)) {
//                // Handle array format: [{data: [typeName, value]}]
//                if (data.values[0] && data.values[0].data) {
//                  const dataObj = data.values[0].data;
//
//                  // Check if it's [typeName, value] format
//                  if (Array.isArray(dataObj) && dataObj.length === 2 && typeof dataObj[0] === 'string') {
//                    ctlModelValue = dataObj[1]; // The actual value is at index 1
//                  } else if (dataObj.enumerated) {
//                    ctlModelValue = dataObj.enumerated;
//                  } else if (typeof dataObj === 'object') {
//                    // Get first value from object
//                    ctlModelValue = Object.values(dataObj)[0];
//                  }
//                }
//              } else if (typeof data.values === 'object') {
//                // Handle direct object format
//                if (data.values.enumerated) {
//                  ctlModelValue = data.values.enumerated;
//                } else if (data.values.data && data.values.data.enumerated) {
//                  ctlModelValue = data.values.data.enumerated;
//                }
//              } else if (typeof data.values === 'string') {
//                ctlModelValue = data.values;
//              }
//
//              // Map numeric values to string representations
//              const ctlModelMap = {
//                0: 'status-only',
//                1: 'direct-with-normal-security',
//                2: 'sbo-with-normal-security',
//                3: 'direct-with-enhanced-security',
//                4: 'sbo-with-enhanced-security'
//              };
//
//              // If it's a number, show both number and string representation
//              if (typeof ctlModelValue === 'number' && ctlModelValue in ctlModelMap) {
//                //ctlModelEl.textContent = `${ctlModelValue} (${ctlModelMap[ctlModelValue]})`;
//              } else if (typeof ctlModelValue === 'string' && !isNaN(ctlModelValue)) {
//                // Handle string numbers
//                const numValue = parseInt(ctlModelValue);
//                if (numValue in ctlModelMap) {
//                  //ctlModelEl.textContent = `${numValue} (${ctlModelMap[numValue]})`;
//                } else {
//                  //ctlModelEl.textContent = ctlModelValue;
//                }
//              } else {
//                //ctlModelEl.textContent = ctlModelValue;
//              }
//
//              console.log(`[Control Dialog] ctlModel: ${ctlModelValue}`);
//            } else {
//              //ctlModelEl.textContent = 'N/A';
//            }
//          } catch (e) {
//            console.error('[Control Dialog] Error reading ctlModel:', e);
//            //ctlModelEl.textContent = 'N/A';
//          }
//    }

    async function showControlDialog(objRef, objName, cdc, endpoint, cp) {
        const root = document.querySelector('.acsi-server-page') || document;

        // Find all modal elements with null checks
        const modal = root.querySelector('#controlModal');
        const controlTitle = root.querySelector('#controlTitle');
        const controlObjRef = root.querySelector('#controlObjRef');
        const controlCdcType = root.querySelector('#controlCdcType');
        const controlCtlModel = root.querySelector('#controlCtlModel');
        const ctlValInput = root.querySelector('#ctlVal');
        const ctlNumInput = root.querySelector('#ctlNum');
        const originCat = root.querySelector('#originCat');
        const originOrIdent = root.querySelector('#originOrIdent');
        const testMode = root.querySelector('#testMode');
        const controlResult = root.querySelector('#controlResult');
        const selectControlBtn = root.querySelector('#selectControlBtn');
        const operateControlBtn = root.querySelector('#operateControlBtn');
        const cancelControlBtn = root.querySelector('#cancelControlBtn');
        const closeControlBtn = root.querySelector('#closeControlBtn');
        const closeControlModal = root.querySelector('#closeControlModal');

        // Critical: Early return if modal doesn't exist
        if (!modal) {
            console.error('[showControlDialog] Control modal not found');
            return;
        }

        try {
            // Populate modal fields - ALL with null checks
            if (controlTitle) controlTitle.textContent = 'Control Operation';
            if (controlObjRef) controlObjRef.textContent = objRef || 'Unknown';
            if (controlCdcType) controlCdcType.textContent = cdc || 'Unknown';
            if (controlCtlModel) controlCtlModel.textContent = 'Loading...';
            if (controlResult) {
                controlResult.classList.add('hidden');
                controlResult.textContent = '';
            }

            // Reset form with null checks
            if (ctlValInput) ctlValInput.value = '';
            if (ctlNumInput) ctlNumInput.value = '0';
            if (originCat) originCat.value = '1';
            if (originOrIdent) originOrIdent.value = '0';
            if (testMode) testMode.checked = false;

            // Set placeholder and type based on CDC - with null check
            if (ctlValInput) {
                switch(cdc?.toUpperCase()) {
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
            }

            // Store current control context
            modal.dataset.objRef = objRef;
            modal.dataset.cdc = cdc;

            // ==== THIS IS CRITICAL: Show modal BEFORE async operations ====
            modal.classList.remove('hidden');

            const endpointTarget = getDefaultTargetFromEndpoint(endpoint);

            // Read ctlModel attribute value
            try {
                const ctlModelRef = `${objRef}.ctlModel`;
                const res = await executeApiCall(getApiById('read'), endpointTarget, { objRef: ctlModelRef, fc: 'cf', cp:cp });
                const data = res;

                if (data.error) {
                    console.log(`[Control Dialog] Could not read ctlModel: ${data.error}`);
                    if (controlCtlModel) controlCtlModel.textContent = 'N/A';
                } else if (data.values) {
                    let ctlModelValue = 'N/A';

                    if (Array.isArray(data.values)) {
                        if (data.values[0]?.data) {
                            const dataObj = data.values[0].data;
                            if (Array.isArray(dataObj) && dataObj.length === 2 && typeof dataObj[0] === 'string') {
                                ctlModelValue = dataObj[1];
                            } else if (dataObj?.enumerated) {
                                ctlModelValue = dataObj.enumerated;
                            } else if (typeof dataObj === 'object') {
                                ctlModelValue = Object.values(dataObj)[0];
                            }
                        }
                    } else if (typeof data.values === 'object') {
                        if (data.values.enumerated) {
                            ctlModelValue = data.values.enumerated;
                        } else if (data.values.data?.enumerated) {
                            ctlModelValue = data.values.data.enumerated;
                        }
                    } else if (typeof data.values === 'string') {
                        ctlModelValue = data.values;
                    }

                    const ctlModelMap = {
                        0: 'status-only',
                        1: 'direct-with-normal-security',
                        2: 'sbo-with-normal-security',
                        3: 'direct-with-enhanced-security',
                        4: 'sbo-with-enhanced-security'
                    };

                    if (typeof ctlModelValue === 'number' && ctlModelValue in ctlModelMap) {
                        if (controlCtlModel) controlCtlModel.textContent = `${ctlModelValue} (${ctlModelMap[ctlModelValue]})`;
                    } else if (typeof ctlModelValue === 'string' && !isNaN(ctlModelValue)) {
                        const numValue = parseInt(ctlModelValue);
                        if (numValue in ctlModelMap) {
                            if (controlCtlModel) controlCtlModel.textContent = `${numValue} (${ctlModelMap[numValue]})`;
                        } else if (controlCtlModel) {
                            controlCtlModel.textContent = ctlModelValue;
                        }
                    } else if (controlCtlModel) {
                        controlCtlModel.textContent = ctlModelValue;
                    }

                    console.log(`[Control Dialog] ctlModel: ${ctlModelValue}`);
                } else if (controlCtlModel) {
                    controlCtlModel.textContent = 'N/A';
                }
            } catch (e) {
                console.error('[Control Dialog] Error reading ctlModel:', e);
                if (controlCtlModel) controlCtlModel.textContent = 'N/A';
            }

        } catch (error) {
            console.error('[showControlDialog] Error:', error);
            // Ensure modal is hidden if there's an error
            if (modal) modal.classList.add('hidden');
        }
    }

    function getControlParameters() {
        const root = document.querySelector('.acsi-server-page') || document;
        const modal = root.querySelector('#controlModal');

        const ctlValInput = root.querySelector('#ctlVal');
        const ctlNumInput = root.querySelector('#ctlNum');
        const originCatSelect = root.querySelector('#originCat');
        const originIdentInput = root.querySelector('#originOrIdent');
        const testModeCheck = root.querySelector('#testMode');

        if (!modal || !ctlValInput || !ctlNumInput || !originCatSelect || !originIdentInput || !testModeCheck) {
            throw new Error('Required modal elements not found');
        }

        const cdc = modal.dataset.cdc?.toUpperCase() || '';
        let ctlVal = ctlValInput.value.trim();
        value_type = 'unknown';

        // Parse control value based on CDC type
        switch(cdc) {
            case 'SPC':
                value_type = 'boolean';
                if (ctlVal === 'true' || ctlVal === '1' || ctlVal === 'on') {
                    ctlVal = true;
                } else if (ctlVal === 'false' || ctlVal === '0' || ctlVal === 'off') {
                    ctlVal = false;
                } else {
                    throw new Error('Invalid SPC value. Use true/false or on/off');
                }
                break;
            case 'DPC':
                value_type = 'enumerated';
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
                value_type = 'float32';
                ctlVal = parseFloat(ctlVal);
                if (isNaN(ctlVal)) {
                    throw new Error('Invalid APC value. Must be a number');
                }
                break;
            case 'INC':
            case 'ENC':
                value_type = 'int32';
                ctlVal = parseInt(ctlVal);
                if (isNaN(ctlVal)) {
                    throw new Error('Invalid value. Must be an integer');
                }
                break;
            case 'BSC':
                value_type = 'string';
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
            value: ctlVal,
            value_type: value_type
            //ctlNum: parseInt(ctlNumInput.value),
            //origin: {
            //    orCat: parseInt(originCatSelect.value),
            //    orIdent: originIdentInput.value
            //},
            //test: testModeCheck.checked
        };
    }

    async function showContextMenuForControllableDO(e, objRef, objName, cdc, endpoint, cp) {
        e.preventDefault();
        e.stopPropagation();

        const menuItems = [
            {
                label: 'Operate',
                icon: 'fa-play',
                action: () => showControlDialog(objRef, objName, cdc, endpoint, cp)  // Only this opens the modal
            },
            //{
            //    label: 'Read Value',
            //    icon: 'fa-eye',
            //    action: () => readDataValue(objRef, 'cf', endpoint)
           // }
        ];

        const menu = createContextMenu(menuItems);
        menu.style.left = e.clientX + 'px';
        menu.style.top = e.clientY + 'px';
        menu.style.display = 'block';

        requestAnimationFrame(() => {
            const rect = menu.getBoundingClientRect();
            if (rect.right > window.innerWidth) {
                menu.style.left = (e.clientX - rect.width) + 'px';
            }
            if (rect.bottom > window.innerHeight) {
                menu.style.top = (e.clientY - rect.height) + 'px';
            }
        });
    }

//    function getControlParameters() {
//      const ctlValInput = document.getElementById('ctlVal');
//      const ctlNumInput = document.getElementById('ctlNum');
//      const originCatSelect = document.getElementById('originCat');
//      const originIdentInput = document.getElementById('originOrIdent');
//      const testModeCheck = document.getElementById('testMode');
//      const modal = document.getElementById('controlModal');
//
//      const cdc = modal.dataset.cdc.toUpperCase();
//      let ctlVal = ctlValInput.value.trim();
//
//      // Parse control value based on CDC type
//      switch(cdc) {
//        case 'SPC':
//          if (ctlVal === 'true' || ctlVal === '1' || ctlVal === 'on') {
//            ctlVal = true;
//          } else if (ctlVal === 'false' || ctlVal === '0' || ctlVal === 'off') {
//            ctlVal = false;
//          } else {
//            throw new Error('Invalid SPC value. Use true/false or on/off');
//          }
//          break;
//        case 'DPC':
//          const dpcMap = {
//            'on': 'on',
//            'off': 'off',
//            'intermediate-state': 'intermediateState',
//            'intermediate': 'intermediateState',
//            'intermediatestate': 'intermediateState'
//          };
//          ctlVal = dpcMap[ctlVal.toLowerCase()];
//          if (!ctlVal) {
//            throw new Error('Invalid DPC value. Use on, off, or intermediate-state');
//          }
//          break;
//        case 'APC':
//          ctlVal = parseFloat(ctlVal);
//          if (isNaN(ctlVal)) {
//            throw new Error('Invalid APC value. Must be a number');
//          }
//          break;
//        case 'INC':
//        case 'ENC':
//          ctlVal = parseInt(ctlVal);
//          if (isNaN(ctlVal)) {
//            throw new Error('Invalid value. Must be an integer');
//          }
//          break;
//        case 'BSC':
//          const bscMap = {
//            'step-up': 'stepUp',
//            'step-down': 'stepDown',
//            'up': 'stepUp',
//            'down': 'stepDown',
//            'stepup': 'stepUp',
//            'stepdown': 'stepDown'
//          };
//          ctlVal = bscMap[ctlVal.toLowerCase()];
//          if (!ctlVal) {
//            throw new Error('Invalid BSC value. Use step-up or step-down');
//          }
//          break;
//      }
//
//      return {
//        objRef: modal.dataset.objRef,
//        ctlVal: ctlVal,
//        ctlNum: parseInt(ctlNumInput.value),
//        origin: {
//          orCat: parseInt(originCatSelect.value),
//          orIdent: originIdentInput.value
//        },
//        test: testModeCheck.checked
//      };
//    }

    function showControlResult(success, message) {
        const root = document.querySelector('.acsi-client-page') || document;
        const resultDiv = root.querySelector('#controlResult');
        if (!resultDiv) {
            console.error('controlResult element not found');
            return;
        }
        resultDiv.classList.remove('hidden', 'success', 'error');
        resultDiv.classList.add(success ? 'success' : 'error');
        resultDiv.textContent = message;
    }


    async function showWriteValueDialog(objRef, fc, endpoint, cp) {
      const modal = document.getElementById('writeValueModal');
      const titleEl = document.getElementById('writeValueTitle');
      const objRefEl = document.getElementById('writeValueObjRef');
      const typeEl = document.getElementById('writeValueType');
      const currentValueEl = document.getElementById('writeValueCurrent');
      const inputEl = document.getElementById('writeValueInput');
      const validationEl = document.getElementById('writeValueValidation');
      const resultDiv = document.getElementById('writeValueResult');
      const submitBtn = document.getElementById('writeValueSubmit');
      const cancelBtn = document.getElementById('writeValueCancel');

      titleEl.textContent = 'Write Data Value';
      objRefEl.textContent = objRef;
      typeEl.textContent = 'Reading...';
      currentValueEl.textContent = 'Reading...';
      inputEl.value = '';
      inputEl.disabled = false;
      inputEl.readOnly = false;
      inputEl.placeholder = 'Enter new value';
      validationEl.textContent = '';
      resultDiv.classList.add('hidden');

      modal.classList.remove('hidden');
      inputEl.focus();

      const endpointTarget = getDefaultTargetFromEndpoint(endpoint);
      
      try {
        const res = await executeApiCall(
            getApiById('read'),
            endpointTarget,
            { objRef, fc, cp }
        );

        if (res?.ok && res.payload?.result?.value) {
          const values = Array.isArray(res.payload.result.value)
            ? res.payload.result.value
            : [res.payload.result.value];

          if (values.length > 0 && values[0]?.data) {
            const firstValue = values[0];
            if (Array.isArray(firstValue.data) && firstValue.data.length >= 2) {
              typeEl.textContent = firstValue.data[0];
              currentValueEl.textContent = JSON.stringify(firstValue.data[1]);
            } else if (typeof firstValue.data === 'object') {
              const typeKeys = Object.keys(firstValue.data).filter(k => !['name', 'elementName'].includes(k));
              if (typeKeys.length > 0) {
                typeEl.textContent = typeKeys[0];
                currentValueEl.textContent = JSON.stringify(firstValue.data[typeKeys[0]]);
              }
            }
          }
        } else {
          typeEl.textContent = 'Unknown';
          currentValueEl.textContent = res?.payload?.error || 'N/A';
        }
      } catch (e) {
        typeEl.textContent = 'Error';
        currentValueEl.textContent = e.message;
      }

      submitBtn.onclick = async () => {
        const newValue = inputEl.value.trim();
        if (!newValue) {
          validationEl.textContent = 'Please enter a value';
          return;
        }
        validationEl.textContent = '';
        submitBtn.disabled = true;

        try {
          await writeDataValue(objRef, fc, endpoint, newValue, typeEl.textContent, cp);
          resultDiv.textContent = '✓ Write successful!';
          resultDiv.style.background = '#2e7d32';
          resultDiv.style.color = '#fff';
          resultDiv.classList.remove('hidden');
          setTimeout(() => {
            modal.classList.add('hidden');
            submitBtn.disabled = false;
          }, 1500);
        } catch (e) {
          resultDiv.textContent = `✗ Error: ${e.message}`;
          resultDiv.style.background = '#c62828';
          resultDiv.style.color = '#fff';
          resultDiv.classList.remove('hidden');
          submitBtn.disabled = false;
        }
      };

      cancelBtn.onclick = () => modal.classList.add('hidden');
      inputEl.addEventListener('keypress', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            submitBtn.click();
          }
        });
    }

    async function showReadContextMenuForDataAttribute(e, objRef, fc, endpoint, cp) {
        e.preventDefault();
        e.stopPropagation();

        const menuItems = [
            {
                label: `Read Value [${fc.toUpperCase()}]`,
                icon: 'fa-eye',
                action: () => readDataValue(objRef, fc, endpoint, cp),
                id: 'contextMenuReadValue',
            },
        ];

        const menu = createContextMenu(menuItems);
        menu.style.left = e.clientX + 'px';
        menu.style.top  = e.clientY + 'px';
        menu.style.display = 'block';

        requestAnimationFrame(() => {
            const rect = menu.getBoundingClientRect();
            if (rect.right > window.innerWidth)  menu.style.left = (e.clientX - rect.width) + 'px';
            if (rect.bottom > window.innerHeight) menu.style.top = (e.clientY - rect.height) + 'px';
        });
    }


    async function showContextMenuForDataAttribute(e, objRef, fc, endpoint, cp) {
        e.preventDefault();
        e.stopPropagation();

        const menuItems = [
            {
                label: `Read Value [${fc.toUpperCase()}]`,
                icon: 'fa-eye',
                action: () => readDataValue(objRef, fc, endpoint, cp),
                id: 'contextMenuReadValue',
            },
            {
                label: `Write Value [${fc.toUpperCase()}]`,
                icon: 'fa-pen',
                action: () => showWriteValueDialog(objRef, fc, endpoint, cp),
                id: 'contextMenuWriteValue',
            }
        ];

        const menu = createContextMenu(menuItems);
        menu.style.left = e.clientX + 'px';
        menu.style.top  = e.clientY + 'px';
        menu.style.display = 'block';

        requestAnimationFrame(() => {
            const rect = menu.getBoundingClientRect();
            if (rect.right > window.innerWidth)  menu.style.left = (e.clientX - rect.width) + 'px';
            if (rect.bottom > window.innerHeight) menu.style.top = (e.clientY - rect.height) + 'px';
        });
    }

    function appendDataAttributeNodes(parentLi, attributes, nodeLabel) {
      if (!attributes || attributes.length === 0) {
        return;
      }

      const ul = document.createElement('ul');
      ul.className = 'scl-tree-list';

      attributes.forEach((da) => {
      const typeSuffix = da.bType ? ` [${da.bType}]` : '';
      const daLi = createTreeNode(nodeLabel, `${da.daRef}${typeSuffix}`);

      if (da.subDataAttributes && da.subDataAttributes.length > 0) {
        console.log(`Appending subDataAttributes for ${da.daRef}:`, da.subDataAttributes);
      }
      appendDataAttributeNodes(daLi, da.subDataAttributes || [], 'SDA');
      ul.appendChild(daLi);

    });

      parentLi.appendChild(ul);
    }

    // Add to your JavaScript
    let currentBrcbRef = null;

    // Open modal with BRCB data
     function openReportControlModal(ref, type, cp, endpointTarget) {
        currentBrcbRef = ref;
        const modal = document.getElementById('brcb-modal');
        const form = document.getElementById('brcb-form');

        // Set reference
        document.getElementById('brcb-ref').value = ref;

        // Fetch current BRCB values from your backend
        fetchRCBValues(ref, type, cp, endpointTarget).then(brcbData => {
            if (brcbData) {
                // Populate form
                document.getElementById('brcb-dataset').value = brcbData.dataSet || '';
                document.getElementById('brcb-intgpd').value = brcbData.intgPd || 2000;
                document.getElementById('brcb-rptena').checked = brcbData.rptEna || false;

                // Set optFlds checkboxes
                if (brcbData.optFlds) {
                    Object.entries(brcbData.optFlds).forEach(([key, value]) => {
                        const cb = form.querySelector(`input[name="optFlds"][value="${key}"]`);
                        if (cb) cb.checked = value;
                    });
                }

                // Set trgOp checkboxes
                if (brcbData.trgOp) {
                    Object.entries(brcbData.trgOp).forEach(([key, value]) => {
                        const cb = form.querySelector(`input[name="trgOp"][value="${key}"]`);
                        if (cb) cb.checked = value;
                    });
                }
            }

            modal.style.display = 'block';
        });

        // Close handlers
        // Change these lines in openReportControlModal:
        modal.querySelector('.brcb-close-modal').onclick = () => modal.style.display = 'none';
        document.getElementById('brcb-cancel').onclick = () => modal.style.display = 'none';

        // Save handler
        document.getElementById('brcb-save').onclick = () => {
            const data = {
                ref: currentBrcbRef,
                dataSet: document.getElementById('brcb-dataset').value,
                intgPd: parseInt(document.getElementById('brcb-intgpd').value) || 0,
                rptEna: document.getElementById('brcb-rptena').checked,
                optFlds: {},
                trgOp: {}
            };

            // Get optFlds
            form.querySelectorAll('input[name="optFlds"]:checked').forEach(cb => {
                data.optFlds[cb.value] = true;
            });
            form.querySelectorAll('input[name="optFlds"]:not(:checked)').forEach(cb => {
                data.optFlds[cb.value] = false;
            });

            // Get trgOp
            form.querySelectorAll('input[name="trgOp"]:checked').forEach(cb => {
                data.trgOp[cb.value] = true;
            });
            form.querySelectorAll('input[name="trgOp"]:not(:checked)').forEach(cb => {
                data.trgOp[cb.value] = false;
            });

            // Send to backend
            saveBRCBValues(currentBrcbRef, cp, data, modal, type, endpointTarget)
                .then(() => {
                    modal.style.display = 'none';
                })
                .catch(err => {
                    alert('Error saving BRCB values: ' + err.message);
                });
        }
    }
    async function saveBRCBValues(objRef, cp, data, modal, type, endpointTarget) {
        response = executeApiCall(
                    type == "BRCB" ? getApiById('brcb-write') : getApiById('urcb-write'),
                    endpointTarget,
                    { objRef: currentBrcbRef, data: data, cp: cp })

    }

    // Example backend functions (implement these)
    async function fetchRCBValues(ref, type, cp, endpointTarget) {
        // Call your backend API to get current BRCB values
        const response = await executeApiCall(
            type == "BRCB" ? getApiById('brcb-read') : getApiById('urcb-read'),
            endpointTarget,
            { objRef: ref, cp: cp }
        );
        if (response.ok) {
            return response.payload.result.value || {};
        } else {
            throw new Error(response.payload.error || 'Failed to fetch BRCB values');
        }
    }


    function appendSubDataObjectNodes(parentLi, subDataObjects) {
      if (!subDataObjects || subDataObjects.length === 0) {
        return;
      }

      const ul = document.createElement('ul');
      ul.className = 'scl-tree-list';

      subDataObjects.forEach(function (sdo) {
        const cdcSuffix = sdo.cdc ? ` [${sdo.cdc}]` : '';
        const sdoLi = createTreeNode('SDO', `${sdo.name}${cdcSuffix}`);
        appendDataAttributeNodes(sdoLi, sdo.dataAttributes || [], 'DA');
        appendSubDataObjectNodes(sdoLi, sdo.subDataObjects || []);
        ul.appendChild(sdoLi);
      });

      parentLi.appendChild(ul);
    }

    function nodeTypeLabel(type) {
        const labels = {
            'LDevice': 'LD',
            'LogicalNode': 'LN',
            'DO': 'DO',
            'DA': 'DA',
            'SDA': 'SDA',
            'SDO': 'SDO',
            'DataSet': 'DataSet',
            'ReportControl': 'RC',
            'BRCB': 'BRCB',
            'URCB': 'URCB',
            'Group': '',
            'FCDA': 'FCDA'
        };
        return labels[type] || type || '';
    }

    function normalizeNodeType(type) {
        return (type || '').replace(/[^a-zA-Z0-9]/g, '-').toLowerCase();
    }

    function createTreeNode(nodeType, value) {
      const li = document.createElement('li');
      li.className = `scl-tree-item scl-node-${normalizeNodeType(nodeType)}`;

      const row = document.createElement('div');
      row.className = 'scl-tree-row';

      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'scl-tree-toggle';
      toggle.textContent = '';

      const isGroupNode = String(nodeType || '').toLowerCase() === 'group';
      const tag = document.createElement('span');
      tag.className = `scl-tree-tag${isGroupNode ? ' hidden' : ''}`;
      tag.textContent = isGroupNode ? '' : nodeTypeLabel(nodeType);

      const valueEl = document.createElement('span');
      valueEl.className = 'scl-tree-value';
      valueEl.textContent = value || '';

      row.appendChild(toggle);
      row.appendChild(tag);
      row.appendChild(valueEl);
      li.appendChild(row);
      return li;
    }

    function appendChildrenTree(parentLi, childrenLabels, childType) {
      if (!childrenLabels || childrenLabels.length === 0) {
        return;
      }

      const ul = document.createElement('ul');
      ul.className = 'scl-tree-list';
      childrenLabels.forEach(function (label) {
        ul.appendChild(createTreeNode(childType, label));
      });
      parentLi.appendChild(ul);
    }

    async function fetchDODefinition(node, endpointTarget, onNodeClick, container, endpoint, cp) {
        // If already has children, just toggle
        const existingUl = node.li.querySelector(':scope > ul');
        if (existingUl) {
            const row = node.li.querySelector(':scope > .scl-tree-row');
            const toggle = row.querySelector('.scl-tree-toggle');
            if (toggle && !toggle.classList.contains('hidden')) {
                const expanded = node.li.classList.toggle('expanded');
                toggle.textContent = expanded ? '▾' : '▸';
                existingUl.style.display = expanded ? '' : 'none';
            }
            return;
        }

        const ldName = node.ref.split('/')[0];
        const lnName = node.ref.split('/')[1].split('.')[0];
        const doPath = node.ref.split('/')[1].split('.').slice(1).join('.');

        const defResult = await executeApiCall(
            getApiById('data-definition'),
            endpointTarget,
            {ld_inst: ldName, ln_inst: lnName, do_path: doPath, cp:cp}
        );

        if (defResult && defResult.ok) {
            const dataAttributes = defResult.payload.result.value?.dataAttributeDefinition || [];
            const subDataObjects = defResult.payload.result.value?.subDataDefinition || [];

            const ul = document.createElement('ul');
            ul.className = 'scl-tree-list';

            // Add DAs - FIXED: Use passed 'endpoint' parameter
            dataAttributes.forEach((da) => {
                const typeSuffix = da.daType?.[0] ? ` (${da.daType[0]})` : '';
                const daName = da.name || da.daRef?.split('.').pop() || 'DA';
                const fc_display = da.fc ? ` [${da.fc}] ` : '';
                const fc = da.fc || '';
                const daLi = createTreeNode('DA', `${fc_display}${daName}${typeSuffix}`);
                const daRef = `${node.ref}.${daName}`;

                const row = daLi.querySelector(':scope > .scl-tree-row');
                row.style.cursor = 'context-menu';

                const valueDisplaySpan = document.createElement('span');
                valueDisplaySpan.className = 'tree-value-display';
                valueDisplaySpan.setAttribute('data-obj-ref', daRef);
                row.appendChild(valueDisplaySpan);


                if (da.daType[0] === "structure"){
                    da.subDataAttributes = da.daType[1];
                }

               if(fc.toLowerCase() === 'sp' || fc.toLowerCase() === 'cf') {
                row.addEventListener('contextmenu', (e) => {
                    e.preventDefault(); e.stopPropagation();
                    showContextMenuForDataAttribute(e, daRef, fc, endpoint, cp);
                });
                } else {
                    row.addEventListener('contextmenu', (e) => {
                        e.preventDefault(); e.stopPropagation();
                        showReadContextMenuForDataAttribute(e, daRef, fc, endpoint, cp);
                    });
                }



            const subDas = da.subDataAttributes || da.sub_attributes || da.sda || [];

            if (Array.isArray(subDas) && subDas.length > 0) {
                const daToggle = row.querySelector('.scl-tree-toggle');
                if (daToggle) {
                    daToggle.classList.remove('hidden');
                    daLi.classList.add('has-children');
                    daToggle.textContent = '▸';

                    daToggle.addEventListener('click', (e) => {
                        e.stopPropagation();
                        const expanded = daLi.classList.toggle('expanded');
                        daToggle.textContent = expanded ? '▾' : '▸';
                        const daUl = daLi.querySelector(':scope > ul');
                        if (daUl) {
                            daUl.style.display = expanded ? '' : 'none';
                        }
                    });
                }
            }

            if (subDas.length > 0) {
                const daUl = document.createElement('ul');
                daUl.className = 'scl-tree-list';
                subDas.forEach((sda) => {
                    const sdaTypeSuffix = ` (${sda.cmpType[0]})` || '';
                    const sdaName = sda.cmpName || sda.daRef?.split('.').pop() || 'SDA';
                    const sdaRef = `${daRef}.${sdaName}`;
                    const sdaLi = createTreeNode('SDA', `${sdaName}${sdaTypeSuffix}`);

                    const sdaRow = sdaLi.querySelector(':scope > .scl-tree-row');
                    const sdaValueDisplaySpan = document.createElement('span');
                    sdaValueDisplaySpan.className = 'tree-value-display';
                    sdaValueDisplaySpan.setAttribute('data-obj-ref', sdaRef);
                    sdaRow.appendChild(sdaValueDisplaySpan);

                    if (sda.cmpType[0] === "structure") {
                        sda.subDataAttributes = sda.cmpType[1];
                        console.log(`SDA ${sdaName} is a structure, subDataAttributes:`, sda.subDataAttributes);
                    }

                    if (sda.subDataAttributes && sda.subDataAttributes.length > 0) {
                        const sdaToggle = sdaRow.querySelector('.scl-tree-toggle');
                        if (sdaToggle) {
                            sdaToggle.classList.remove('hidden');
                            sdaLi.classList.add('has-children');
                            sdaToggle.textContent = '▸';

                            sdaToggle.addEventListener('click', (e) => {
                                e.stopPropagation();
                                const expanded = sdaLi.classList.toggle('expanded');
                                sdaToggle.textContent = expanded ? '▾' : '▸';
                                const sdaUl = sdaLi.querySelector(':scope > ul');
                                if (sdaUl) {
                                    sdaUl.style.display = expanded ? '' : 'none';
                                }
                            });
                        }

                        const sdaUl = document.createElement('ul');
                        sdaUl.className = 'scl-tree-list';

                        for (const subSda of sda.subDataAttributes) {
                            const subSdaTypeSuffix = ` (${subSda.cmpType[0]})` || '';
                            const subSdaName = subSda.cmpName || subSda.daRef?.split('.').pop() || 'SDA';
                            const subSdaRef = `${sdaRef}.${subSdaName}`;
                            const subSdaLi = createTreeNode('SDA', `${subSdaName}${subSdaTypeSuffix}`);

                            const subSdaRow = subSdaLi.querySelector(':scope > .scl-tree-row');
                            const subSdaValueDisplaySpan = document.createElement('span');
                            subSdaValueDisplaySpan.className = 'tree-value-display';
                            subSdaValueDisplaySpan.setAttribute('data-obj-ref', subSdaRef);
                            subSdaRow.appendChild(subSdaValueDisplaySpan);

                            subSdaRow.style.cursor = 'context-menu';

                            if(fc.toLowerCase() === 'sp' || fc.toLowerCase() === 'cf') {
                                subSdaRow.addEventListener('contextmenu', (e) => {
                                    e.preventDefault(); e.stopPropagation();
                                    showContextMenuForDataAttribute(e, subSdaRef, fc, endpoint, cp);
                                });
                            } else {
                                subSdaRow.addEventListener('contextmenu', (e) => {
                                    e.preventDefault(); e.stopPropagation();
                                    showReadContextMenuForDataAttribute(e, subSdaRef, fc, endpoint, cp);
                                });
                            }

                            sdaUl.appendChild(subSdaLi);
                        }

                        sdaLi.appendChild(sdaUl);
                    }

                    sdaRow.style.cursor = 'context-menu';

                     if(fc.toLowerCase() === 'sp' || fc.toLowerCase() === 'cf') {
                        sdaRow.addEventListener('contextmenu', (e) => {
                            e.preventDefault(); e.stopPropagation();
                            showContextMenuForDataAttribute(e, sdaRef, fc, endpoint, cp);
                        });
                    } else {
                        sdaRow.addEventListener('contextmenu', (e) => {
                            e.preventDefault(); e.stopPropagation();
                            showReadContextMenuForDataAttribute(e, sdaRef, fc, endpoint, cp);
                        });
                    }

                    daUl.appendChild(sdaLi);
                });
                daLi.appendChild(daUl);

            }
                ul.appendChild(daLi);
            });

            // Add SDOs - FIXED: Pass endpoint in node object
            subDataObjects.forEach((sdo) => {
                const cdcSuffix = sdo.cdc ? ` [${sdo.cdc}]` : '';
                const sdoRef = `${node.ref}.${sdo.name}`;
                const sdoLi = createTreeNode('SDO', `${sdo.name}${cdcSuffix}`);

                const sdoRow = sdoLi.querySelector(':scope > .scl-tree-row');

                if (sdoRow) {
                    sdoRow.style.cursor = 'pointer';
                    sdoRow.addEventListener('click', function(e) {
                        if (e.target && e.target.classList.contains('scl-tree-toggle')) return;
                        e.stopPropagation();

                        container.querySelectorAll('.scl-tree-row.lm-selected').forEach(function(r) {
                            r.classList.remove('lm-selected');
                        });
                        sdoRow.classList.add('lm-selected');
                        onNodeClick({ ref: sdoRef, fc: null, nodeType: 'SDO', li: sdoLi, endpoint: endpoint }); // ✅ Pass endpoint
                    });
                }

                const sdoToggle = sdoRow?.querySelector('.scl-tree-toggle');
                if (sdoToggle) {
                    sdoToggle.classList.remove('hidden');
                    sdoLi.classList.add('has-children');
                    sdoToggle.textContent = '▸';
                }

                ul.appendChild(sdoLi);
            });

            node.li.appendChild(ul);

            if (ul.children.length > 0) {
                const row = node.li.querySelector(':scope > .scl-tree-row');
                const toggle = row.querySelector('.scl-tree-toggle');

                toggle.classList.remove('hidden');
                node.li.classList.add('has-children', 'expanded');
                toggle.textContent = '▾';
                ul.style.display = '';

                toggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const expanded = node.li.classList.toggle('expanded');
                    toggle.textContent = expanded ? '▾' : '▸';
                    ul.style.display = expanded ? '' : 'none';
                });
            }
        } else {
            console.log(`Error fetching data definition for ${node.ref}:`,
                defResult?.payload?.error || defResult?.rawText || 'Failed');
        }
    }
    async function handleFetchModel(rootElement, endpoint) {

        const cp = rootElement.querySelector('#acsi-client-cp-page').value.trim() || 'cp1';

        const endpointTarget = getDefaultTargetFromEndpoint(endpoint);

        const handleNodeClick = async (node) => {
                if (node.nodeType === 'DO' || node.nodeType === 'SDO') {
                    const container = document.getElementById('acsi-client-tree-content');
                    // ✅ Pass endpoint from closure or from node object
                    const endpointToUse = node.endpoint || endpoint;
                    await fetchDODefinition(node, endpointTarget, handleNodeClick, container, endpointToUse, cp);
                    }
                else if (node.nodeType == "DataSet") {
                    const existingUl = node.li.querySelector(':scope > ul');
                     if (existingUl) {
                        return;
                    }
                    console.log('[handleNodeClick] DataSet node clicked:', node.ref, 'Existing UL:', existingUl);
                    const ld_name = node.ref.split('/')[0];
                    const ln_inst = node.ref.split('/')[1].split('.')[0];
                    const dsName = node.ref.split('/')[1].split('.')[1];

                    const defResult = await executeApiCall(
                        getApiById('dataset-directory'),
                        endpointTarget,
                        {ld_inst: ld_name, ln_inst: ln_inst, ds_inst: dsName}
                    );
                    if (defResult && defResult.ok) {
                        console.log('DataSet definition:', defResult.payload);
                        const dataAttributes = defResult.payload.result.value;

                         const ul = document.createElement('ul');
                        ul.className = 'scl-tree-list';

                        for(const da of dataAttributes) {
                            const objRef = da.ref;
                            const fc = da.fc;

                            const typeSuffix = da.bType ? ` [${da.bType}]` : '';
                            const daLi = createTreeNode('FCDA', objRef + ` [${fc}]`);
                            const row = daLi.querySelector(':scope > .scl-tree-row');
                            row.style.cursor = 'context-menu';

                            const valueDisplaySpan = document.createElement('span');
                            valueDisplaySpan.className = 'tree-value-display';
                            valueDisplaySpan.setAttribute('data-obj-ref', `${node.ref}.${da.daRef}`);
                            row.appendChild(valueDisplaySpan);

                            row.addEventListener('contextmenu', (e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                showContextMenuForDataAttribute(e, `${node.ref}.${da.daRef}`, fc, endpoint, cp);
                            });

                            ul.appendChild(daLi);
                        }
                        node.li.appendChild(ul);

                        if (ul.children.length > 0) {
                            const row = node.li.querySelector(':scope > .scl-tree-row');
                            const toggle = row.querySelector('.scl-tree-toggle');

                            toggle.classList.remove('hidden');
                            node.li.classList.add('has-children', 'expanded');
                            toggle.textContent = '▾';
                            ul.style.display = '';

                            toggle.addEventListener('click', (e) => {
                                e.stopPropagation();
                                const expanded = node.li.classList.toggle('expanded');
                                toggle.textContent = expanded ? '▾' : '▸';
                                ul.style.display = expanded ? '' : 'none';
                            });
                        }
                    }
                }
                if (node.nodeType === 'ReportControl') {
                    const rcbType = node.li.getAttribute('rcbType')
                    openReportControlModal(node.ref, rcbType, cp, endpointTarget);  // Direct modal open
                    return;  // Skip onNodeClick if you want
                }
        }

        showStatus(rootElement, 'Fetching model...', 'info');
        const result = await executeApiCall(
            getApiById('model-tree'),
            endpointTarget,
            {cp}
        );

        if (result && result.ok) {
            const treeContainer = rootElement.querySelector('#acsi-client-tree-container-page');
            const treeContent = rootElement.querySelector('#acsi-client-tree-content');
            renderLiveModelTree(result.payload || {}, treeContent, handleNodeClick, endpoint, cp);
            treeContainer.style.display = 'block';
            showStatus(rootElement, 'Model fetched successfully', 'success');
        }
         else {
            const error = result?.payload?.error || result?.rawText || 'Failed to fetch model';
            showStatus(rootElement, error, 'error');
        }
    }

    function setupCollapsibleTree(container) {
      const treeItems = container.querySelectorAll('.scl-tree-item');

      treeItems.forEach(function (item) {
        const row = item.querySelector(':scope > .scl-tree-row');
        const toggle = row ? row.querySelector('.scl-tree-toggle') : null;
        const childList = item.querySelector(':scope > .scl-tree-list');

        if (!row || !toggle) {
          return;
        }

        if (!childList || childList.children.length === 0) {
          toggle.classList.add('hidden');
          return;
        }

        item.classList.add('has-children', 'expanded');
        toggle.textContent = '▾';

        toggle.classList.remove('hidden');
        item.classList.add('has-children', 'expanded');
        toggle.textContent = '▾';

        const onToggle = function () {
          const isExpanded = item.classList.toggle('expanded');
          toggle.textContent = isExpanded ? '▾' : '▸';
          childList.style.display = isExpanded ? '' : 'none';
        };

        toggle.addEventListener('click', function (event) {
          event.stopPropagation();
          onToggle();
        });
      });
    }

    function appendSDAtoDataAttributeNode(da, daLi, daFc, daRef) {
        var subDas = (da && (da.sub_attributes || da.subDataAttributes || da.sda)) || [];
        if (subDas.length > 0) {
            var sdaUl = document.createElement('ul');
            sdaUl.className = 'scl-tree-list';
            subDas.forEach(function (sda) {
              var sdaName = (typeof sda === 'object' ? sda.name : sda) || 'SDA';
              var sdaRef  = daRef + '.' + sdaName;
              var sdaLi   = createTreeNode('SDA', sdaName);
              if (sda.sub_attributes || sda.subDataAttributes || sda.sda) {
                appendSDAtoDataAttributeNode(sda, sdaLi, daFc, sdaRef);
              }

              const sdaRow = sdaLi.querySelector(':scope > .scl-tree-row');
              const sdaValueDisplaySpan = document.createElement('span');
              sdaValueDisplaySpan.className = 'tree-value-display';
              sdaValueDisplaySpan.setAttribute('data-obj-ref', sdaRef);
              sdaRow.appendChild(sdaValueDisplaySpan);

              makeClickable(sdaLi, sdaRef, daFc, 'SDA');
              sdaUl.appendChild(sdaLi);
            });
            daLi.appendChild(sdaUl);
        }
    }

    function renderLiveModelTree(data, containerOrId, onNodeClick, endpoint, cp) {
      var container = typeof containerOrId === 'string'
        ? document.getElementById(containerOrId)
        : containerOrId;

      if (!container) return;

      container.innerHTML = '';

      var lds = [];
      lds = data.result.model.server.logicalDevices;

      if (!lds.length) {
        container.innerHTML =
          '<p style="padding:12px;color:var(--text-muted);font-style:italic;">No model data. Connect FSP/SO first.</p>';
        return;
      }

      var root = document.createElement('ul');
      root.className = 'scl-tree-root';

    function makeClickable(li, ref, fc, nodeType) {
        var row = li.querySelector(':scope > .scl-tree-row');
        if (!row) return;

        row.style.cursor = 'pointer';
        row.addEventListener('click', function (e) {
          if (e.target && e.target.classList.contains('scl-tree-toggle')) return;

          e.stopPropagation();

          container.querySelectorAll('.scl-tree-row.lm-selected').forEach(function (r) {
            r.classList.remove('lm-selected');
          });

          row.classList.add('lm-selected');

          if (onNodeClick) {
            onNodeClick({ ref: ref, fc: fc, nodeType: nodeType, li: li });
          }

            const childList = li.querySelector(':scope > .scl-tree-list');
            const toggle = row.querySelector('.scl-tree-toggle');

            if (childList && !toggle.classList.contains('hidden')) {
                const expanded = li.classList.toggle('expanded');
                toggle.textContent = expanded ? '▾' : '▸';
                childList.style.display = expanded ? '' : 'none';
            }
        });
      }

      lds.forEach(function (ld) {
        var ldName = (typeof ld === 'object' ? ld.name : ld) || 'LD';
        var ldLi = createTreeNode('LDevice', ldName);

        var lnUl = document.createElement('ul');
        lnUl.className = 'scl-tree-list';

        var lns = data.result.model.logicalDeviceMap[ldName] || [];

        lns.forEach(function (ln) {
          var lnName = (typeof ln === 'object' ? (ln.name || ln.ln_class) : ln) || 'LN';
          var lnRef = ldName + '/' + lnName;

          var lnLi = createTreeNode('LogicalNode', lnName);
          makeClickable(lnLi, lnRef, null, 'LN');

          // Create DataSets group with clickable items
            const dsLi = createTreeNode('Group', 'DataSets');
            const dsUl = document.createElement('ul');
            dsUl.className = 'scl-tree-list';
            const dataSets = data.result.model.logicalNodeDetails[ldName + '/' + lnName].dataSets || [];
            dataSets.forEach(function(ds) {
                const dsName = (typeof ds === 'object' ? ds.name : ds) || 'DataSet';
                const dsRef = lnRef + '.' + dsName;
                const dsNode = createTreeNode('DataSet', dsName);
                makeClickable(dsNode, dsRef, null, 'DataSet');
                dsUl.appendChild(dsNode);
            });
            dsLi.appendChild(dsUl);
          const rcLi = createTreeNode('Group', 'Report Controls');
          //appendChildrenTree(rcLi, data.result.model.logicalNodeDetails[ldName + '/' + lnName].reportControlBlocks.map(rcb => rcb.name) || [], 'ReportControl');
          // Create Report Controls group with clickable items
          const rcUl = document.createElement('ul');
          rcUl.className = 'scl-tree-list';
          const reportControls = data.result.model.logicalNodeDetails[ldName + '/' + lnName].reportControlBlocks || [];

           reportControls.forEach(function(rcb) {
                const rcbName = (typeof rcb === 'object' ? rcb.name : rcb) || 'ReportControl';
                const rcbRef = lnRef + '.' + rcbName;
                const rcbNode = createTreeNode(rcb.type, rcbName);
                rcbNode.setAttribute('rcbType', rcb.type);

                makeClickable(rcbNode, rcbRef, null, 'ReportControl');  // ← Make clickable
                rcUl.appendChild(rcbNode);
            });
           rcLi.appendChild(rcUl);

          // Create DOs group with clickable items
          var dos = data.result.model.logicalNodeDetails[ldName + '/' + lnName].dataObjects || ln.dataObjects || ln.do || [];
          if (dos.length > 0) {
            var doUl = document.createElement('ul');
            doUl.className = 'scl-tree-list';

            dos.forEach(function (doObj) {
              var doName  = (typeof doObj === 'object' ? doObj.name : doObj) || 'DO';
              var doFc    = (doObj && doObj.fc) || null;
              var cdcTxt  = (doObj && doObj.cdc) ? ' [' + doObj.cdc + ']' : '';
              var doRef   = lnRef + '.' + doName;

              var doLi    = createTreeNode('DO', doName + cdcTxt);
              makeClickable(doLi, doRef, doFc, 'DO');

              // Check if this is a controllable CDC
              const isControllable = doObj.cdc && CONTROLLABLE_CDCS.includes(doObj.cdc.toUpperCase());

                if (isControllable) {
                  doLi.style.cursor = 'context-menu';
                  doLi.title = `Right-click to control ${doName} (${doObj.cdc.toUpperCase()})`;

                  doLi.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    showContextMenuForControllableDO(e, doRef, doName, doObj.cdc, endpoint, cp);
                  });
                } else {
                  doLi.style.cursor = 'context-menu';
                  doLi.addEventListener('contextmenu', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    showContextMenuForDataObject(e, doRef);
                  });
                }

              var das = (doObj && (doObj.data_attributes || doObj.dataAttributes || doObj.da)) || [];
              if (das.length > 0) {
                var daUl = document.createElement('ul');
                daUl.className = 'scl-tree-list';

                das.forEach(function (da) {
                  var daName   = (typeof da === 'object' ? da.name : da) || 'DA';
                  var daFc     = (da && (da.fc || doFc)) || null;
                  var bTypeTxt = (da && da.bType) ? ' (' + da.bType + ')' : '';
                  var daRef    = doRef + '.' + daName;
                  var daLi     = createTreeNode('DA', daName + bTypeTxt + (daFc ? ' [' + daFc + ']' : ''));
                  makeClickable(daLi, daRef, daFc, 'DA');

                  const row = daLi.querySelector(':scope > .scl-tree-row');
                  const valueDisplaySpan = document.createElement('span');
                  valueDisplaySpan.className = 'tree-value-display';
                  valueDisplaySpan.setAttribute('data-obj-ref', daRef);
                  row.appendChild(valueDisplaySpan);
                  appendSDAtoDataAttributeNode(da, daLi, daFc, daRef);

//                  var subDas = (da && (da.sub_attributes || da.subDataAttributes || da.sda)) || [];
//                  if (subDas.length > 0) {
//                    var sdaUl = document.createElement('ul');
//                    sdaUl.className = 'scl-tree-list';
//                    subDas.forEach(function (sda) {
//                      var sdaName = (typeof sda === 'object' ? sda.name : sda) || 'SDA';
//                      var sdaRef  = daRef + '.' + sdaName;
//                      var sdaLi   = createTreeNode('SDA', sdaName);
//
//                      const sdaRow = sdaLi.querySelector(':scope > .scl-tree-row');
//                      const sdaValueDisplaySpan = document.createElement('span');
//                      sdaValueDisplaySpan.className = 'tree-value-display';
//                      sdaValueDisplaySpan.setAttribute('data-obj-ref', sdaRef);
//                      sdaRow.appendChild(sdaValueDisplaySpan);
//
//                      makeClickable(sdaLi, sdaRef, daFc, 'SDA');
//                      sdaUl.appendChild(sdaLi);
//                    });
//                    daLi.appendChild(sdaUl);
                  //});
                  daUl.appendChild(daLi);
                });
                doLi.appendChild(daUl);
              }
              doUl.appendChild(doLi);
            });

            lnLi.appendChild(doUl);
          }

            lnLi.appendChild(dsLi);
            lnLi.appendChild(rcLi);

          lnUl.appendChild(lnLi);
        });

        ldLi.appendChild(lnUl);
        root.appendChild(ldLi);
      });

      container.appendChild(root);
      setupCollapsibleTree(container);
    }

    // Initialize the page
    function init() {
        const rootElement = document.querySelector('.acsi-server-page') || document.body;

        // Initialize with empty endpoint
        //setupEventListeners(rootElement, {});
        renderProtocolMessages(rootElement);
        
        // Disable buttons that need connection first
        const fetchModelBtn = document.getElementById('acsi-client-fetch-model-btn');
        const disconnectBtn = document.getElementById('acsi-client-disconnect-page-btn');
        if (disconnectBtn) disconnectBtn.disabled = true;
        const startBtn = document.getElementById('messages-start-btn');
        if (startBtn) startBtn.disabled = true;
        const stopBtn = document.getElementById('messages-stop-btn');
        if (stopBtn) stopBtn.disabled = true;
    }

    function interpolateTemplate(template, values) {
        return template.replace(/{{\s*([a-zA-Z0-9_]+)\s*}}/g, (match, key) => {
            return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : match;
        });
    }

    let templateCache = null;

     async function loadTemplate() {
        if (templateCache) {
            return templateCache;
        }

        const response = await fetch('./acsi-client-page.html', { cache: 'no-store' });
        if (!response.ok) {
            throw new Error('Unable to load acsi-client-page.html');
        }

        templateCache = await response.text();
        return templateCache;
    }

    // Render function to match the server page pattern
    async function render(root, endpoint) {
        if (!root) {
            return;
        }
        const hasEndpoint = !!endpoint;
        const endpointName = hasEndpoint ? escapeHtml(endpoint.name || 'Unnamed endpoint') : 'No endpoint selected';
        const endpointType = hasEndpoint ? escapeHtml(endpoint.type || 'N/A') : 'N/A';

        try {
            // Ensure CSS is loaded
            if (!document.getElementById('acsi-client-page-css')) {
                const link = document.createElement('link');
                link.id = 'acsi-client-page-css';
                link.rel = 'stylesheet';
                link.href = 'acsi-client-page.css';
                document.head.appendChild(link);
            }

            // Ensure JS is loaded
            if (!window.__acsiClientPageLoaded) {
                await loadScript('acsi-client-page.js');
            }

            // ✅ Use ONLY template interpolation
            const template = await loadTemplate();
            root.innerHTML = interpolateTemplate(template, {
                endpointName,
                endpointType,
            });

            // Initialize the page
            setupEventListeners(root, endpoint);
            renderProtocolMessages(root);

            // Disable buttons that need connection first
            const disconnectBtn = document.getElementById('acsi-client-disconnect-page-btn');
            if (disconnectBtn) disconnectBtn.disabled = true;
            const startBtn = document.getElementById('messages-start-btn');
            if (startBtn) startBtn.disabled = true;
            const stopBtn = document.getElementById('messages-stop-btn');
            if (stopBtn) stopBtn.disabled = true;

            // Update endpoint badge if we have an endpoint
            if (endpoint) {
                const badge = root.querySelector('.acsi-endpoint-badge');
                if (badge) {
                    const name = endpoint.name || 'Endpoint';
                    const host = endpoint.host || '';
                    const port = endpoint.port || '';
                    badge.innerHTML = `<span id="endpoint-name">${name}</span> · <span id="endpoint-host">${host}</span>:<span id="endpoint-port">${port}</span>`;
                }
            }
        } catch (error) {
            console.error('Error rendering ACSI Client page:', error);
            root.innerHTML = '<p style="color: var(--text-muted);">ACSI Client page is unavailable.</p>';
        }
    }

    // Helper to load scripts (if not already available in this scope)
    function loadScript(url) {
        return new Promise((resolve, reject) => {
            if (document.querySelector(`script[src="${url}"]`)) {
                resolve();
                return;
            }
            const script = document.createElement('script');
            script.src = url;
            script.onload = resolve;
            script.onerror = reject;
            document.head.appendChild(script);
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    window.ACSIClientPage = {
        render,
        init,
        executeApiCall,
        renderLiveModelTree,
        handleFetchModel
    };
})();
