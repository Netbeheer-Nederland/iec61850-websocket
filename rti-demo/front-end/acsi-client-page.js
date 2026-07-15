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
        { id: 'model-tree', label: 'GET /api/model/tree', method: 'POST', path: '/api/model/tree' },
        { id: 'data-definition', label: 'POST /api/getDataDefinition', method: 'POST', path: '/api/getDataDefinition' },
        { id: 'read', label: 'POST /api/readvalue', method: 'POST', path: '/api/readvalue' },
        { id: 'write', label: 'POST /api/writevalue', method: 'POST', path: '/api/writevalue' },
        { id: 'dataset-directory', label: 'POST /api/getDataSetDirectory', method: 'POST', path: '/api/getDataSetDirectory' },
        { id: 'actions-logs', label: 'GET /api/actions_logs', method: 'GET', path: '/api/actions_logs', sampleBody: '' },
        { id: 'clear-logs', label: 'POST /api/clear_logs', method: 'POST', path: '/api/clear_logs', sampleBody: '' },
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
        const connectBtn = rootElement.querySelector('#acsi-client-connect-page-btn');
        const disconnectBtn = rootElement.querySelector('#acsi-client-disconnect-page-btn');
        const fetchModelBtn = rootElement.querySelector('#acsi-client-fetch-model-btn');
        const messagesStartBtn = rootElement.querySelector('#messages-start-btn');
        const messagesStopBtn = rootElement.querySelector('#messages-stop-btn');
        const messagesClearBtn = rootElement.querySelector('#messages-clear-btn');
        const reloadMessagesBtn = rootElement.querySelector('#reloadMessagesBtn');

        const endpointTarget = getDefaultTargetFromEndpoint(endpoint);

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

        if (messagesClearBtn) {
            messagesClearBtn.addEventListener('click', () => {
                clearMessages(rootElement, endpointTarget);
            });
        }

        // Initialize messages status
        updateMessagesStatus(rootElement, 'Select an endpoint and click Start');
    }

    async function handleConnect(rootElement, endpoint) {
        const endpointTarget = getDefaultTargetFromEndpoint(endpoint);
        const host = rootElement.querySelector('#acsi-client-host-page').value.trim();
        const port = parseInt(rootElement.querySelector('#acsi-client-port-page').value.trim());
        const cp = rootElement.querySelector('#acsi-client-cp-page').value.trim() || 'cp1';

        if (!host || !port) {
            showStatus(rootElement, 'Please enter both host and port', 'error');
            return;
        }

        if (isNaN(port) || port < 1 || port > 65535) {
            showStatus(rootElement, 'Invalid port number', 'error');
            return;
        }

        showStatus(rootElement, 'Connecting...', 'info');
        const result = await executeApiCall(
            getApiById('connect'),
            endpointTarget,
            { host, port, cp }
        );

        if (result && result.ok) {
            showStatus(rootElement, `Connected to ${host}:${port}`, 'success');
            rootElement.querySelector('#acsi-client-connect-page-btn').disabled = true;
            rootElement.querySelector('#acsi-client-disconnect-page-btn').disabled = false;
            rootElement.querySelector('#acsi-client-fetch-model-btn').disabled = false;
            updateEndpointBadge(host, port, '');
            
            // Enable message monitoring buttons
            const startBtn = rootElement.querySelector('#messages-start-btn');
            if (startBtn) startBtn.disabled = false;
        } else {
            const error = result?.payload?.error || result?.rawText || 'Unknown error';
            showStatus(rootElement, `Connection failed: ${error}`, 'error');
        }
    }

    async function handleDisconnect(rootElement, endpoint) {
        const endpointTarget = getDefaultTargetFromEndpoint(endpoint);
        const host = rootElement.querySelector('#acsi-client-host-page').value.trim();
        const port = parseInt(rootElement.querySelector('#acsi-client-port-page').value.trim());
        const cp = rootElement.querySelector('#acsi-client-cp-page').value.trim() || 'cp1';

        showStatus(rootElement, 'Disconnecting...', 'info');
        
        const result = await executeApiCall(
            getApiById('disconnect'),
            endpointTarget,
            { host, port, cp }
        );

        if (result && result.ok) {
            showStatus(rootElement, 'Disconnected', 'info');
            rootElement.querySelector('#acsi-client-connect-page-btn').disabled = false;
            rootElement.querySelector('#acsi-client-disconnect-page-btn').disabled = true;
            rootElement.querySelector('#acsi-client-fetch-model-btn').disabled = true;
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
            showStatus(rootElement, `Disconnect failed: ${error}`, 'error');
        }
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

    async function readDataValue(objRef, fc, endpoint) {
      console.log('[readDataValue] Reading:', objRef, 'FC:', fc);
      const endpointTarget = getDefaultTargetFromEndpoint(endpoint);
      const host = document.getElementById('acsi-client-host-page').value.trim();
      const port = document.getElementById('acsi-client-port-page').value.trim();

      try {
        const res = await executeApiCall(
            getApiById('read'),
            endpointTarget,
            { objRef, fc }
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

    async function writeDataValue(objRef, fc, endpoint, value, value_type) {
      console.log('[writeDataValue] Writing:', objRef, 'FC:', fc, 'Value:', value);
      const endpointTarget = getDefaultTargetFromEndpoint(endpoint);

      try {
        const res = await executeApiCall(
            getApiById('write'),
            endpointTarget,
            { objRef, fc, value, value_type }
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

    async function showWriteValueDialog(objRef, fc, endpoint) {
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

      modal.classList.add('active');
      inputEl.focus();

      const endpointTarget = getDefaultTargetFromEndpoint(endpoint);
      
      try {
        const res = await executeApiCall(
            getApiById('read'),
            endpointTarget,
            { objRef, fc }
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
          await writeDataValue(objRef, fc, endpoint, newValue, typeEl.textContent);
          resultDiv.textContent = '✓ Write successful!';
          resultDiv.style.background = '#2e7d32';
          resultDiv.style.color = '#fff';
          resultDiv.classList.remove('hidden');
          setTimeout(() => {
            modal.classList.remove('active');
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

      cancelBtn.onclick = () => modal.classList.remove('active');
      inputEl.addEventListener('keypress', (e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            submitBtn.click();
          }
        });
    }

    async function showContextMenuForDataAttribute(e, objRef, fc, endpoint) {
        e.preventDefault();
        e.stopPropagation();

        const menuItems = [
            {
                label: `Read Value [${fc.toUpperCase()}]`,
                icon: 'fa-eye',
                action: () => readDataValue(objRef, fc, endpoint)
            },
            {
                label: `Write Value [${fc.toUpperCase()}]`,
                icon: 'fa-pen',
                action: () => showWriteValueDialog(objRef, fc, endpoint)
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

      appendDataAttributeNodes(daLi, da.subDataAttributes || [], 'SDA');
      ul.appendChild(daLi);

    });

      parentLi.appendChild(ul);
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

    async function handleFetchModel(rootElement, endpoint) {
        const endpointTarget = getDefaultTargetFromEndpoint(endpoint);

        const handleNodeClick = async (node) => {
                if (node.nodeType === 'DO') {
                    const existingUl = node.li.querySelector(':scope > ul');

                    if (existingUl) {
                        return;
                    }
                    const ldName = node.ref.split('/')[0];
                    const lnName = node.ref.split('/')[1].split('.')[0];
                    const doPath = node.ref.split('/')[1].split('.').slice(1).join('.');

                    const defResult = await executeApiCall(
                        getApiById('data-definition'),
                        endpointTarget,
                        {ld_inst: ldName, ln_inst: lnName, do_path: doPath}
                    );
                    if (defResult && defResult.ok) {
                        console.log('Data definition:', defResult.payload);
                        const dataAttributes = defResult.payload.result.value?.dataAttributeDefinition || [];
                        const subDataObjects = defResult.payload.result.value?.subDataDefinition || [];

                        const ul = document.createElement('ul');
                        ul.className = 'scl-tree-list';

                        dataAttributes.forEach((da) => {
                            const typeSuffix = da.daType[0] ? ` [${da.daType[0]}]` : '';
                            const daName = da.name || da.daRef.split('.').pop() || 'DA';
                            const fc = da.fc || 'mx';
                            const daLi = createTreeNode('DA', `${daName}${typeSuffix}`);

                            const daRef = `${node.ref}.${daName}`;

                            const row = daLi.querySelector(':scope > .scl-tree-row');
                            row.style.cursor = 'context-menu';

                            const valueDisplaySpan = document.createElement('span');
                            valueDisplaySpan.className = 'tree-value-display';
                            valueDisplaySpan.setAttribute('data-obj-ref', daRef);
                            row.appendChild(valueDisplaySpan);

                            row.addEventListener('contextmenu', (e) => {
                                e.preventDefault();
                                e.stopPropagation();
                                showContextMenuForDataAttribute(e, daRef, fc, endpoint);
                            });

                            const subDas = da.subDataAttributes || da.sub_attributes || da.sda || [];
                            if (subDas.length > 0) {
                                const daUl = document.createElement('ul');
                                daUl.className = 'scl-tree-list';
                                subDas.forEach((sda) => {
                                    const sdaTypeSuffix = sda.daType[0] ? ` [${sda.daType[0].bType}]` : '';
                                    const sdaName = sda.name || sda.daRef.split('.').pop() || 'SDA';
                                    const sdaRef = `${daRef}.${sdaName}`;

                                    const sdaLi = createTreeNode('SDA', `${sdaName}${sdaTypeSuffix}`);
                                    const sdaRow = sdaLi.querySelector(':scope > .scl-tree-row');
                                    const sdaValueDisplaySpan = document.createElement('span');
                                    sdaValueDisplaySpan.className = 'tree-value-display';
                                    sdaValueDisplaySpan.setAttribute('data-obj-ref', sdaRef);
                                    sdaRow.appendChild(sdaValueDisplaySpan);

                                    sdaRow.style.cursor = 'context-menu';
                                    sdaRow.addEventListener('contextmenu', (e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                        showContextMenuForDataAttribute(e, sdaRef, fc, endpoint);
                                    });

                                    daUl.appendChild(sdaLi);
                                });
                                daLi.appendChild(daUl);
                            }
                            ul.appendChild(daLi);
                        });

                        subDataObjects.forEach((sdo) => {
                            const cdcSuffix = sdo.cdc ? ` [${sdo.cdc}]` : '';
                            const sdoLi = createTreeNode('SDO', `${sdo.name}${cdcSuffix}`);

                            const sdoDas = sdo.dataAttributes || sdo.data_attributes || sdo.da || [];
                            const sdoSubSdos = sdo.subDataObjects || sdo.sub_data_objects || [];
                            if (sdoDas.length > 0 || sdoSubSdos.length > 0) {
                                const sdoUl = document.createElement('ul');
                                sdoUl.className = 'scl-tree-list';
                                sdoDas.forEach((da) => {
                                    const typeSuffix = da.bType ? ` [${da.bType}]` : '';
                                    const daName = da.name || da.daRef.split('.').pop() || 'DA';
                                    const daRef = `${node.ref}.${sdo.name}.${daName}`;
                                    const daLi = createTreeNode('DA', `${daName}${typeSuffix}`);
                                    
                                    const daRow = daLi.querySelector(':scope > .scl-tree-row');
                                    const valueDisplaySpan = document.createElement('span');
                                    valueDisplaySpan.className = 'tree-value-display';
                                    valueDisplaySpan.setAttribute('data-obj-ref', daRef);
                                    daRow.appendChild(valueDisplaySpan);
                                    daRow.style.cursor = 'context-menu';
                                    daRow.addEventListener('contextmenu', (e) => {
                                        e.preventDefault();
                                        e.stopPropagation();
                                        showContextMenuForDataAttribute(e, daRef, da.fc || 'mx', endpoint);
                                    });
                                    
                                    sdoUl.appendChild(daLi);
                                });
                                sdoSubSdos.forEach((nestedSdo) => {
                                    const nestedCdc = nestedSdo.cdc ? ` [${nestedSdo.cdc}]` : '';
                                    sdoUl.appendChild(createTreeNode('SDO', `${nestedSdo.name}${nestedCdc}`));
                                });
                                sdoLi.appendChild(sdoUl);
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

                            const onToggle = () => {
                                const expanded = node.li.classList.toggle('expanded');
                                toggle.textContent = expanded ? '▾' : '▸';
                                ul.style.display = expanded ? '' : 'none';
                            };

                            toggle.addEventListener('click', (e) => {
                                e.stopPropagation();
                                onToggle();
                            });
                        }
                    }
                    else
                    {
                        const error = defResult?.payload?.error || defResult?.rawText || 'Failed to fetch data definition';
                        console.log(`Error fetching data definition for ${node.ref}:`, error);
                    }
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
                                showContextMenuForDataAttribute(e, `${node.ref}.${da.daRef}`, fc, endpoint);
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
        }

        showStatus(rootElement, 'Fetching model...', 'info');
        const result = await executeApiCall(
            getApiById('model-tree'),
            endpointTarget,
            null
        );

        if (result && result.ok) {
            const treeContainer = rootElement.querySelector('#acsi-client-tree-container-page');
            const treeContent = rootElement.querySelector('#acsi-client-tree-content');
            renderLiveModelTree(result.payload || {}, treeContent, handleNodeClick);
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

    function renderLiveModelTree(data, containerOrId, onNodeClick) {
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
          appendChildrenTree(rcLi, data.result.model.logicalNodeDetails[ldName + '/' + lnName].reportControlBlocks.map(rcb => rcb.name) || [], 'ReportControl');

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

              var das = (doObj && (doObj.data_attributes || doObj.dataAttributes || doObj.da)) || [];
              if (das.length > 0) {
                var daUl = document.createElement('ul');
                daUl.className = 'scl-tree-list';

                das.forEach(function (da) {
                  var daName   = (typeof da === 'object' ? da.name : da) || 'DA';
                  var daFc     = (da && (da.fc || doFc)) || null;
                  var bTypeTxt = (da && da.bType) ? ' [' + da.bType + ']' : '';
                  var daRef    = doRef + '.' + daName;
                  var daLi     = createTreeNode('DA', daName + bTypeTxt);
                  makeClickable(daLi, daRef, daFc, 'DA');

                  const row = daLi.querySelector(':scope > .scl-tree-row');
                  const valueDisplaySpan = document.createElement('span');
                  valueDisplaySpan.className = 'tree-value-display';
                  valueDisplaySpan.setAttribute('data-obj-ref', daRef);
                  row.appendChild(valueDisplaySpan);

                  var subDas = (da && (da.sub_attributes || da.subDataAttributes || da.sda)) || [];
                  if (subDas.length > 0) {
                    var sdaUl = document.createElement('ul');
                    sdaUl.className = 'scl-tree-list';
                    subDas.forEach(function (sda) {
                      var sdaName = (typeof sda === 'object' ? sda.name : sda) || 'SDA';
                      var sdaRef  = daRef + '.' + sdaName;
                      var sdaLi   = createTreeNode('SDA', sdaName);

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
        setupEventListeners(rootElement, {});
        renderProtocolMessages(rootElement);
        
        // Disable buttons that need connection first
        const fetchModelBtn = document.getElementById('acsi-client-fetch-model-btn');
        if (fetchModelBtn) fetchModelBtn.disabled = true;
        const disconnectBtn = document.getElementById('acsi-client-disconnect-page-btn');
        if (disconnectBtn) disconnectBtn.disabled = true;
        const startBtn = document.getElementById('messages-start-btn');
        if (startBtn) startBtn.disabled = true;
        const stopBtn = document.getElementById('messages-stop-btn');
        if (stopBtn) stopBtn.disabled = true;
    }

    // Render function to match the server page pattern
    async function render(root, endpoint) {
        if (!root) {
            return;
        }

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

            // Fetch and inject the HTML (without the script tag to avoid double-loading)
            const response = await fetch('acsi-client-page.html');
            if (!response.ok) {
                throw new Error('Failed to load HTML');
            }
            let html = await response.text();
            
            // Remove the script tag from the HTML to prevent double-loading
            html = html.replace(/<script\s+src=["']acsi-client-page\.js["']><\/script>/gi, '');
            
            root.innerHTML = html;

            // Initialize the page
            setupEventListeners(root, endpoint);
            renderProtocolMessages(root);
            
            // Disable buttons that need connection first
            const fetchModelBtn = document.getElementById('acsi-client-fetch-model-btn');
            if (fetchModelBtn) fetchModelBtn.disabled = true;
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
