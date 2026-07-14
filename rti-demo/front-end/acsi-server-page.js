/* ==============================================
   ACSI Server - IEC 61850 Server Page
   ============================================== */

(function initACSIServerPage() {
    let templateCache = null;
    let protocolMessages = [];
    let fspTargets = [];

    const apiDefinitions = [

    // =========================
    // Acsi-Server APIs
    // =========================

    { id: 'health', label: 'GET /api/health', method: 'GET', path: '/api/health', sampleBody: '' },

    { id: 'status', label: 'GET /api/status', method: 'GET', path: '/api/status', sampleBody: '' },

    { id: 'properties', label: 'GET /api/properties', method: 'GET', path: '/api/properties', sampleBody: '' },

    { id: 'connections', label: 'GET /api/connections', method: 'GET', path: '/api/connections', sampleBody: '' },

    { id: 'model', label: 'GET /api/model', method: 'GET', path: '/api/model', sampleBody: '' },

    { id: 'update-iedmodel', label: 'POST /api/update-iedmodel', method: 'POST', path: '/api/update-iedmodel', sampleBody: '{\n  "modelPy": "# python code"\n}' },

    { id: 'update-iedmodel-file', label: 'POST /api/update-iedmodel-file', method: 'POST', path: '/api/update-iedmodel-file', sampleBody: '' },

    { id: 'start', label: 'POST /api/start', method: 'POST', path: '/api/start', sampleBody: '{\n  "host": "0.0.0.0",\n  "port": 8765,\n  "mode": "server",\n  "cp": "cp1"\n}' },

    { id: 'stop', label: 'POST /api/stop', method: 'POST', path: '/api/stop', sampleBody: '' },

    { id: 'actions', label: 'GET /api/actions_logs', method: 'GET', path: '/api/actions_logs', sampleBody: '' },

    { id: 'actions-clear', label: 'POST /api/clear_logs', method: 'POST', path: '/api/clear_logs', sampleBody: '' },

    { id: 'messages', label: 'GET /api/messages', method: 'GET', path: '/api/messages', sampleBody: '' },

    { id: 'messages-clear', label: 'POST /api/clear_messages', method: 'POST', path: '/api/clear_messages', sampleBody: '' },

    { id: 'readvalue', label: 'POST /api/readvalue', method: 'POST', path: '/api/readvalue', sampleBody: '{\n  "objRef": "LD0.LLN0.Mod.stVal",\n  "fc": "ST"\n}' },

    { id: 'writevalue', label: 'POST /api/writevalue', method: 'POST', path: '/api/writevalue', sampleBody: '{\n  "objRef": "LD0.LLN0.Mod.stVal",\n  "value": "on",\n  "fc": "ST",\n  "dataType": "BOOLEAN"\n}' },

];

    function readEndpointProperty(endpoint, key) {
        const props = endpoint && endpoint.properties_info && endpoint.properties_info.properties
            ? endpoint.properties_info.properties
            : {};
        return props[key];
    }

    function resolveServerRole(endpoint) {
        return readEndpointProperty(endpoint, 'server-role')
            || readEndpointProperty(endpoint, 'server_role')
            || 'N/A';
    }

    function resolveWsMode(endpoint) {
        return readEndpointProperty(endpoint, 'ws_mode') || 'N/A';
    }

    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function interpolateTemplate(template, values) {
        return template.replace(/{{\s*([a-zA-Z0-9_]+)\s*}}/g, (match, key) => {
            return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : match;
        });
    }

    function escapeForHtml(value) {
        return escapeHtml(value);
    }

    function renderProtocolMessages() {
        const messagesEl = document.getElementById('acsi-protocol-messages');
        if (!messagesEl) {
            return;
        }

        if (protocolMessages.length === 0) {
            messagesEl.innerHTML = '<div class="acsi-log-empty">No protocol messages yet. Run GET /api/messages.</div>';
            return;
        }

        messagesEl.innerHTML = protocolMessages.map((entry) => {
            const formatted = JSON.stringify(entry.payload, null, 2);
            return `
                <div class="acsi-log-item acsi-log-info">
                    <div class="acsi-log-head">
                        <span class="acsi-log-time">${escapeForHtml(entry.timestamp)}</span>
                        <span class="acsi-log-message">GET /api/messages</span>
                    </div>
                    <pre class="acsi-log-details">${escapeForHtml(formatted)}</pre>
                </div>
            `;
        }).join('');
    }

    function addProtocolMessagesEntry(payload) {
        protocolMessages.unshift({
            timestamp: new Date().toLocaleTimeString(),
            payload,
        });
        if (protocolMessages.length > 30) {
            protocolMessages = protocolMessages.slice(0, 30);
        }
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
                return `http://${storedHost}:${storedPort}`;
            }
        }

        if (window.location && window.location.origin && window.location.origin !== 'null') {
            return window.location.origin;
        }
        return '';
    }

    function buildBffApiUrl(path, targetValue) {
        const baseUrl = getBffBaseUrl();
        if (!baseUrl) {
            throw new Error('BFF base URL is not configured. API calls are blocked to avoid direct endpoint access.');
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

    function extractModelTree(payload) {
        if (!payload || typeof payload !== 'object') {
            return null;
        }

        if (payload.model && payload.model.tree) {
            return payload.model.tree;
        }

        if (payload.tree && payload.tree.model && payload.tree.model.tree) {
            return payload.tree.model.tree;
        }

        if (payload.tree && payload.tree.kind) {
            return payload.tree;
        }

        if (payload.kind === 'IED') {
            return payload;
        }

        return null;
    }

    function toDataAttributeNode(node, parentPath) {
        const name = node.name || 'DA';
        const objRef = parentPath ? `${parentPath}.${name}` : name;
        return {
            name,
            bType: node.type || '',
            fc: node.fc || '',
            type: '',
            objRef,
            subDataAttributes: (node.children || [])
                .filter((child) => child && child.kind === 'DA')
                .map((child) => toDataAttributeNode(child, objRef)),
        };
    }

    function toDataObjectNode(node, parentPath) {
        const doName = node.name || 'DO';
        const doPath = parentPath ? `${parentPath}.${doName}` : doName;
        return {
            name: doName,
            type: '',
            cdc: node.cdc || '',
            dataAttributes: (node.children || [])
                .filter((child) => child && child.kind === 'DA')
                .map((child) => toDataAttributeNode(child, doPath)),
            subDataObjects: (node.children || [])
                .filter((child) => child && child.kind === 'DO')
                .map((child) => toDataObjectNode(child, doPath)),
        };
    }

    function toSclTreeData(payload) {
        const sourceTree = extractModelTree(payload);
        if (!sourceTree || sourceTree.kind !== 'IED') {
            return null;
        }

        // Extract iedName from various possible locations
        const iedName = sourceTree.name 
            || (payload && payload.iedName)
            || (payload && payload.model && payload.model.iedName)
            || 'IED';
        
        // Extract accessPoints from various possible locations
        const accessPointNames = (payload && Array.isArray(payload.accessPoints) && payload.accessPoints.length > 0)
            ? payload.accessPoints
            : (payload && payload.model && payload.model.server && Array.isArray(payload.model.server.accessPoints) && payload.model.server.accessPoints.length > 0)
                ? payload.model.server.accessPoints
                : [
                    (payload && payload.model && payload.model.server && payload.model.server.name) || 'Server',
                ];

        const ldevices = (sourceTree.children || [])
            .filter((child) => child && child.kind === 'LD')
            .map((ld) => {
                const ldName = ld.ldName || ld.name || 'LDevice';
                const lnodes = (ld.children || [])
                    .filter((child) => child && child.kind === 'LN')
                    .map((ln) => {
                        const lnName = ln.name || 'LN';
                        const lnPath = `${ldName}.${lnName}`;
                        return {
                            name: lnName,
                            lnType: '',
                            dataSets: [],
                            reportControls: [],
                            dataObjects: (ln.children || [])
                                .filter((child) => child && child.kind === 'DO')
                                .map((dobj) => toDataObjectNode(dobj, lnPath)),
                        };
                    });

                return {
                    name: ldName,
                    lnodes,
                };
            });

        return {
            ieds: [
                {
                    name: iedName,
                    accessPoints: accessPointNames.map((name) => ({
                        name,
                        ldevices,
                    })),
                },
            ],
        };
    }

    function setModelPanelMessage(message, isError = false) {
        const modelPanel = document.getElementById('acsi-modelPanel');
        if (!modelPanel) {
            return;
        }

        const cssClass = isError ? 'acsi-model-state acsi-model-error' : 'acsi-model-state';
        modelPanel.innerHTML = `<div class="${cssClass}">${escapeForHtml(message)}</div>`;
    }

    function renderModelFromPayload(payload) {
        const modelPanel = document.getElementById('acsi-modelPanel');
        if (!modelPanel) {
            return;
        }

        const sclTreeData = toSclTreeData(payload);
        if (sclTreeData && window.SCLTree && typeof window.SCLTree.renderSclTree === 'function') {
            window.SCLTree.renderSclTree(sclTreeData, modelPanel);
            return;
        }

        const fallbackTree = extractModelTree(payload) || payload;
        const modelJson = JSON.stringify(fallbackTree, null, 2);
        modelPanel.innerHTML = `<pre class="acsi-model-json">${escapeForHtml(modelJson)}</pre>`;
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

    function getApiById(id) {
        return apiDefinitions.find((api) => api.id === id);
    }

    function upsertTarget(target) {
        if (!target || !target.id) {
            return;
        }
        const existingIndex = fspTargets.findIndex((item) => item.id === target.id);
        if (existingIndex >= 0) {
            fspTargets[existingIndex] = target;
            return;
        }
        fspTargets.push(target);
    }

    async function loadFspTargets(preferredTarget) {
        const baseUrl = getBffBaseUrl();
        if (!baseUrl) {
            fspTargets = [];
            return preferredTarget || '';
        }
        const encodedTarget = preferredTarget ? encodeURIComponent(preferredTarget) : '';
        const targetQuery = encodedTarget ? `?target=${encodedTarget}` : '';
        const url = `${baseUrl}/api/fsp/targets${targetQuery}`;

        try {
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const payload = await response.json();
            const loadedTargets = Array.isArray(payload.targets) ? payload.targets : [];
            fspTargets = loadedTargets.map((target) => {
                const hostPort = buildTargetValue(target.host, target.port);
                return {
                    id: target.id || hostPort || target.base_url,
                    label: `${target.name || 'FSP'} (${hostPort || target.base_url || 'unknown'})`,
                    value: target.id || hostPort || target.base_url,
                    host: target.host,
                    port: target.port,
                    baseUrl: target.base_url,
                };
            });

            const selected = payload.selected || {};
            const selectedValue = selected.id || buildTargetValue(selected.host, selected.port) || selected.base_url || preferredTarget;
            return selectedValue || '';
        } catch (error) {
            fspTargets = [];
            console.log('error', 'Failed to load FSP targets', String(error && error.message ? error.message : error));
            return preferredTarget || '';
        }
    }

    function ensureFallbackTarget(targetValue) {
        if (!targetValue) {
            return;
        }

        upsertTarget({
            id: targetValue,
            label: `FSP (${targetValue})`,
            value: targetValue,
        });
    }


    async function wireApiTester(endpoint) {
        const reloadStatusBtn = document.getElementById('acsi-reload-status-btn');
        const updatedStatusEl = document.getElementById('acsi-endpoint-updated-status');
        const daModalEl = document.getElementById('acsi-da-modal');
        const daModalCloseEl = document.getElementById('acsi-da-modal-close');
        const daModalObjRefEl = document.getElementById('acsi-da-modal-objref');
        const daModalFcEl = document.getElementById('acsi-da-modal-fc');
        const daModalValueEl = document.getElementById('acsi-da-modal-value');
        const daModalReadEl = document.getElementById('acsi-da-modal-read');
        const daModalWriteEl = document.getElementById('acsi-da-modal-write');
        const daModalResultEl = document.getElementById('acsi-da-modal-result');
        const startBtn = document.getElementById('acsi-start-btn');
        const stopBtn = document.getElementById('acsi-stop-btn');
        const loadModelBtn = document.getElementById('acsi-load-model-btn');
        const reloadBtn = document.getElementById("reloadMessagesBtn");


        const endpointTarget = getDefaultTargetFromEndpoint(endpoint);
        let activeDaSelection = null;

        if (daModalEl) {
            daModalEl.hidden = true;
        }

        setModelPanelMessage('Run GET /api/model to load the model tree.');

        renderProtocolMessages();

        function setUpdatedStatusText(text, isError = false) {
            if (!updatedStatusEl) {
                return;
            }
            updatedStatusEl.textContent = text;
            updatedStatusEl.classList.toggle('acsi-model-error', !!isError);
        }

        function formatStatusSummary(payload) {
            // Handle case where status is a stringified Python dict
            let statusObj = payload;
            if (payload && payload.status && typeof payload.status === 'string') {
                // Try to parse Python dict string representation
                try {
                    // Replace Python dict string format to JSON format
                    const pythonDictStr = payload.status;
                    // Convert {'key': 'value'} to {"key": "value"}
                    const jsonStr = pythonDictStr
                        .replace(/'/g, '"')
                        .replace(/True/g, 'true')
                        .replace(/False/g, 'false')
                        .replace(/None/g, 'null');
                    statusObj = JSON.parse(jsonStr);
                } catch (e) {
                    // If parsing fails, use the original payload
                    console.log('Warning: Could not parse status string as JSON:', e);
                    statusObj = payload;
                }
            }
            
            const status = statusObj && statusObj.status ? statusObj.status : (payload && payload.status ? payload.status : 'unknown');
            const host = statusObj && statusObj.host ? statusObj.host : (payload && payload.host ? payload.host : 'N/A');
            const port = statusObj && statusObj.port !== undefined ? statusObj.port : (payload && payload.port !== undefined ? payload.port : 'N/A');
            const clients = statusObj && statusObj.connectedClients !== undefined ? statusObj.connectedClients : (payload && payload.connectedClients !== undefined ? payload.connectedClients : 'N/A');
            const aps = statusObj && Array.isArray(statusObj.accessPoints) ? statusObj.accessPoints.join(', ') : (payload && Array.isArray(payload.accessPoints) ? payload.accessPoints.join(', ') : 'N/A');
            
            return `Updated status: ${status} | host ${host}:${port} | clients ${clients} | accessPoints ${aps}`;
        }

        function setDaModalResult(value) {
            if (!daModalResultEl) {
                return;
            }
            daModalResultEl.textContent = value;
        }

        function closeDaModal() {
            if (!daModalEl) {
                return;
            }
            daModalEl.hidden = true;
        }

        function openDaModal(selection) {
            if (!daModalEl || !selection || !selection.objRef) {
                return;
            }

            activeDaSelection = selection;
            if (daModalObjRefEl) {
                daModalObjRefEl.value = selection.objRef;
            }
            if (daModalFcEl) {
                daModalFcEl.value = selection.fc || '';
            }
            if (daModalValueEl) {
                daModalValueEl.value = '';
            }
            setDaModalResult('Select Read or Write to execute API call for this DA.');
            daModalEl.hidden = false;
        }

        // ==================== Core API Call Function ====================
        async function executeApiCall(selected, targetValue, bodyOverride) {
            if (!selected) {
                return null;
            }

            let url;
            try {
                url = buildBffApiUrl('/api/execute');
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

                // Handle special cases for model and messages
                if (selected.id === 'model') {
                    if (response.ok && parsedPayload) {
                        // The BFF wraps the response in a 'result' field
                        const modelData = parsedPayload.result || parsedPayload;
                        renderModelFromPayload(modelData);
                    } else if (!response.ok) {
                        setModelPanelMessage(`Model request failed with HTTP ${response.status}`, true);
                    } else {
                        setModelPanelMessage('Model response is not valid JSON.', true);
                    }
                }

                if (selected.id === 'messages') {
                    if (response.ok && parsedPayload) {
                        // The BFF wraps the response in a 'result' field
                        const messagesPayload = (parsedPayload.result && Object.prototype.hasOwnProperty.call(parsedPayload.result, 'messages')
                            ? parsedPayload.result.messages
                            : (Object.prototype.hasOwnProperty.call(parsedPayload, 'messages')
                                ? parsedPayload.messages
                                : parsedPayload));
                        addProtocolMessagesEntry(messagesPayload);
                        renderProtocolMessages();
                    }
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



        async function runDaAction(actionId) {
            if (!activeDaSelection || !activeDaSelection.objRef) {
                setDaModalResult('No DA selected.');
                return;
            }

            if (!endpointTarget) {
                setDaModalResult('Missing selected endpoint address (target).');
                return;
            }

            const body = {
                objRef: activeDaSelection.objRef,
            };

            if (activeDaSelection.fc) {
                body.fc = activeDaSelection.fc;
            }

            if (actionId === 'writevalue') {
                body.value = daModalValueEl ? daModalValueEl.value : '';
            }

            setDaModalResult('Loading...');
            const result = await executeApiCall(getApiById(actionId), endpointTarget, body);
            if (!result) {
                setDaModalResult('Request failed. See API Logs for details.');
                return;
            }

            if (result.payload && typeof result.payload === 'object') {
                setDaModalResult(JSON.stringify(result.payload, null, 2));
                return;
            }

            setDaModalResult(String(result.rawText || 'No response body'));
        }

        if (startBtn) {
            startBtn.addEventListener('click', async () => {
                if (!endpointTarget) {
                    console.log('error', 'Start blocked', 'No selected endpoint address available to resolve target.');
                    return;
                }
                const api = getApiById('start');
                const hostInput = document.getElementById('acsi-server-host-input');
                const portInput = document.getElementById('acsi-server-port-input');
                const modeInput = document.getElementById('acsi-server-mode-input');
                const cpInput = document.getElementById('acsi-server-cp-input');
                
                const body = {};
                if (hostInput) body.host = hostInput.value || '0.0.0.0';
                if (portInput) body.port = String(portInput.value) || '8765';
                if (modeInput) body.mode = modeInput.value || 'server';
                if (cpInput) body.cp = cpInput.value || 'cp1';
                
                await executeApiCall(api, endpointTarget, body);
            });
        }

        if (reloadBtn) {
            reloadBtn.addEventListener('click', async () => {
                if (!endpointTarget) {
                    console.log('error', 'Reload blocked', 'No selected endpoint address available to resolve target.');
                    return;
                }
                await executeApiCall(getApiById('messages'), endpointTarget, {});
            });
        }


        if (stopBtn) {
            stopBtn.addEventListener('click', async () => {
                if (!endpointTarget) {
                    console.log('error', 'Stop blocked', 'No selected endpoint address available to resolve target.');
                    return;
                }
                await executeApiCall(getApiById('stop'), endpointTarget, {});
            });
        }

        if (loadModelBtn) {
            loadModelBtn.addEventListener('click', async () => {
                if (!endpointTarget) {
                    console.log('error', 'Load model blocked', 'No selected endpoint address available to resolve target.');
                    return;
                }
                await executeApiCall(getApiById('model'), endpointTarget);
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
                    setUpdatedStatusText('Updated status: loading...');
                    await ensureBffHealthy();

                    const api = getApiById('status');
                    const result = await executeApiCall(api, endpointTarget, {});
                    
                    if (result && result.ok && result.payload) {
                        setUpdatedStatusText(formatStatusSummary(result.payload));
                        console.log('success', 'GET /api/status -> HTTP 200', JSON.stringify(result.payload, null, 2));
                    } else {
                        const message = result ? `HTTP ${result.status}` : 'Unknown error';
                        setUpdatedStatusText(`Updated status: failed (${message})`, true);
                        console.log('error', 'GET /api/status failed', message);
                    }
                } catch (error) {
                    const message = String(error && error.message ? error.message : error);
                    setUpdatedStatusText(`Updated status: failed (${message})`, true);
                    console.log('error', 'GET /api/status failed', message);
                } finally {
                    reloadStatusBtn.disabled = false;
                }
            });
        }

        if (window.SCLTree && typeof window.SCLTree.setDataAttributeClickHandler === 'function') {
            window.SCLTree.setDataAttributeClickHandler((selection) => {
                openDaModal(selection);
            });
        }

        if (daModalCloseEl) {
            daModalCloseEl.addEventListener('click', closeDaModal);
        }

        if (daModalEl) {
            daModalEl.addEventListener('click', (event) => {
                const target = event.target;
                if (target && target.getAttribute && target.getAttribute('data-da-modal-close') === 'true') {
                    closeDaModal();
                }
            });
        }

        if (daModalReadEl) {
            daModalReadEl.addEventListener('click', async () => {
                await runDaAction('readvalue');
            });
        }

        if (daModalWriteEl) {
            daModalWriteEl.addEventListener('click', async () => {
                await runDaAction('writevalue');
            });
        }

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && daModalEl && !daModalEl.hidden) {
                closeDaModal();
            }
        });

        // Auto-load status and model on page load
        (async () => {
            let targetToUse = endpointTarget;
            
            // If no endpoint target, try to load FSP targets
            if (!targetToUse) {
                try {
                    const loadedTarget = await loadFspTargets();
                    if (loadedTarget) {
                        targetToUse = loadedTarget;
                        ensureFallbackTarget(loadedTarget);
                    }
                } catch (error) {
                    console.log('Could not load FSP targets:', error && error.message ? error.message : error);
                }
            }
            
            // If still no target, try to build from localStorage
            if (!targetToUse) {
                const storedHost = localStorage.getItem('bffHost');
                const storedPort = localStorage.getItem('bffPort');
                if (storedHost && storedPort) {
                    targetToUse = buildTargetValue(storedHost, Number(storedPort));
                }
            }
            
            if (targetToUse) {
                try {
                    await ensureBffHealthy();
                    
                    // Load status automatically
                    const statusApi = getApiById('status');
                    setUpdatedStatusText('Loading status...');
                    const statusResult = await executeApiCall(statusApi, targetToUse, {});
                    if (statusResult && statusResult.ok && statusResult.payload) {
                        setUpdatedStatusText(formatStatusSummary(statusResult.payload));
                    } else {
                        const message = statusResult ? `HTTP ${statusResult.status}` : 'Unknown error';
                        setUpdatedStatusText(`Updated status: failed (${message})`, true);
                    }

                    // Load model automatically
                    setModelPanelMessage('Loading model...');
                    const modelApi = getApiById('model');
                    await executeApiCall(modelApi, targetToUse);
                } catch (error) {
                    const message = String(error && error.message ? error.message : error);
                    setUpdatedStatusText(`Auto-load failed: ${message}`, true);
                    setModelPanelMessage(`Auto-load failed: ${message}`, true);
                }
            } else {
                setUpdatedStatusText('No target configured. Check BFF settings.');
                setModelPanelMessage('No target configured. Check BFF settings.', true);
            }
        })();
    }

    async function loadTemplate() {
        if (templateCache) {
            return templateCache;
        }

        const response = await fetch('./acsi-server-page.html', { cache: 'no-store' });
        if (!response.ok) {
            throw new Error('Unable to load acsi-server-page.html');
        }

        templateCache = await response.text();
        return templateCache;
    }

    async function render(root, endpoint) {
        const hasEndpoint = !!endpoint;
        const endpointName = hasEndpoint ? escapeHtml(endpoint.name || 'Unnamed endpoint') : 'No endpoint selected';
        const endpointHost = hasEndpoint ? escapeHtml(endpoint.host || 'N/A') : 'N/A';
        const endpointPort = hasEndpoint ? escapeHtml(endpoint.port || 'N/A') : 'N/A';
        const endpointType = hasEndpoint ? escapeHtml(endpoint.type || 'N/A') : 'N/A';
        const endpointStatus = hasEndpoint ? escapeHtml(endpoint.status || 'unknown') : 'unknown';
        const endpointRole = hasEndpoint ? escapeHtml(resolveServerRole(endpoint)) : 'N/A';
        const endpointWsMode = hasEndpoint ? escapeHtml(resolveWsMode(endpoint)) : 'N/A';

        try {
            const template = await loadTemplate();
            root.innerHTML = interpolateTemplate(template, {
                endpointName,
                endpointHost,
                endpointPort,
                endpointType,
                endpointStatus,
                endpointRole,
                endpointWsMode,
            });
            await wireApiTester(endpoint);
        } catch (error) {
            root.innerHTML = '<p style="color: var(--text-muted);">Failed to load ACSI Server page template.</p>';
            console.error(error);
        }
    }

    window.ACSIServerPage = {
        render,
    };

    // Auto-initialize if this page is loaded directly (not as a module)
    if (window.location && window.location.pathname && window.location.pathname.includes('acsi-server-page.html')) {
        document.addEventListener('DOMContentLoaded', () => {
            const rootEl = document.getElementById('acsi-server-root') || document.body;
            window.ACSIServerPage.render(rootEl, null);
        });
    }
})();
