import { generatePythonModelFromScl } from './dataModelFactory.js';
console.log('hmi-tools.js loaded');

window.initializeToolsPage = function () {	
	
	 const toolsSclFile = document.getElementById('tools-sclFile');
	const toolsGenerateModelBtn = document.getElementById('tools-generateModelBtn');
	const toolsStatusInfo = document.getElementById('tools-statusInfo');
	const toolsModelPanel = document.getElementById('tools-modelPanel');
	const toolsBrowseBtnText = document.getElementById('tools-browseBtnText');
	const toolsIedSelectWrap = document.getElementById('tools-iedSelectWrap');
	const toolsIedSelect = document.getElementById('tools-iedSelect');
	const toolsApSelectWrap = document.getElementById('tools-apSelectWrap');
	const toolsApSelect = document.getElementById('tools-apSelect');
	const selectEl = document.getElementById('api-select');
	const selectEndpoint = document.getElementById('endpoint-api-select');
	const bodyEl = document.getElementById('acsi-api-body');
	const runEl = document.getElementById('acsi-api-run');
    let logs = [];
let activeTab = 'sclModelFactory';

const apiDefinitions = [

    // =========================
    // IEC61850 SERVER APIs
    // =========================

    { id: 'status', label: 'GET /api/iec61850server/status', method: 'GET', path: '/api/iec61850server/status', sampleBody: '' },

    { id: 'connections', label: 'GET /api/iec61850server/connections', method: 'GET', path: '/api/iec61850server/connections', sampleBody: '' },

    { id: 'model', label: 'GET /api/iec61850server/model', method: 'GET', path: '/api/iec61850server/model', sampleBody: '' },

    { id: 'update-iedmodel', label: 'POST /api/iec61850server/update-iedmodel', method: 'POST', path: '/api/iec61850server/update-iedmodel', sampleBody: '{\n  "modelPy": "# python code"\n}' },

    { id: 'start', label: 'POST /api/iec61850server/start', method: 'POST', path: '/api/iec61850server/start', sampleBody: '{\n  "host": "0.0.0.0",\n  "port": 8765,\n  "mode": "server",\n  "cp": "cp1"\n}' },

    { id: 'stop', label: 'POST /api/iec61850server/stop', method: 'POST', path: '/api/iec61850server/stop', sampleBody: '' },

    { id: 'actions', label: 'GET /api/iec61850server/actions', method: 'GET', path: '/api/iec61850server/actions', sampleBody: '' },

    { id: 'actions-clear', label: 'POST /api/iec61850server/actions/clear', method: 'POST', path: '/api/iec61850server/actions/clear', sampleBody: '' },

    { id: 'messages', label: 'GET /api/iec61850server/messages', method: 'GET', path: '/api/iec61850server/messages', sampleBody: '' },

    { id: 'messages-clear', label: 'POST /api/iec61850server/messages/clear', method: 'POST', path: '/api/iec61850server/messages/clear', sampleBody: '' },

    { id: 'readvalue', label: 'POST /api/iec61850server/readvalue', method: 'POST', path: '/api/iec61850server/readvalue', sampleBody: '{\n  "objRef": "LD0.LLN0.Mod.stVal",\n  "fc": "ST"\n}' },

    { id: 'writevalue', label: 'POST /api/iec61850server/writevalue', method: 'POST', path: '/api/iec61850server/writevalue', sampleBody: '{\n  "objRef": "LD0.LLN0.Mod.stVal",\n  "value": "on",\n  "fc": "ST",\n  "dataType": "BOOLEAN"\n}' },


    // =========================
    // IEC61850 CLIENT APIs
    // =========================

    { id: 'client-status', label: 'GET /api/iec61850client/status', method: 'GET', path: '/api/iec61850client/status', sampleBody: '' },

    { id: 'client-connections', label: 'GET /api/iec61850client/connections', method: 'GET', path: '/api/iec61850client/connections', sampleBody: '' },

    { id: 'client-properties', label: 'GET /api/iec61850client/properties', method: 'GET', path: '/api/iec61850client/properties', sampleBody: '' },

    { id: 'client-connect', label: 'POST /api/iec61850client/connect', method: 'POST', path: '/api/iec61850client/connect', sampleBody: '{\n  "host": "localhost",\n  "port": 8765,\n  "cp": "cp1"\n}' },

    { id: 'client-disconnect', label: 'POST /api/iec61850client/disconnect', method: 'POST', path: '/api/iec61850client/disconnect', sampleBody: '' },

    { id: 'client-actions', label: 'GET /api/iec61850client/actions', method: 'GET', path: '/api/iec61850client/actions', sampleBody: '' },

    { id: 'client-actions-clear', label: 'POST /api/iec61850client/actions/clear', method: 'POST', path: '/api/iec61850client/actions/clear', sampleBody: '' },

    { id: 'client-messages', label: 'GET /api/iec61850client/messages', method: 'GET', path: '/api/iec61850client/messages', sampleBody: '' },

    { id: 'client-messages-clear', label: 'POST /api/iec61850client/messages/clear', method: 'POST', path: '/api/iec61850client/messages/clear', sampleBody: '' },

    { id: 'client-readvalue', label: 'POST /api/iec61850client/readvalue', method: 'POST', path: '/api/iec61850client/readvalue', sampleBody: '{\n  "objRef": "LD0.LLN0.Mod.stVal",\n  "fc": "ST"\n}' },

    { id: 'client-writevalue', label: 'POST /api/iec61850client/writevalue', method: 'POST', path: '/api/iec61850client/writevalue', sampleBody: '{\n  "objRef": "LD0.LLN0.Mod.stVal",\n  "value": true,\n  "fc": "ST",\n  "value_type": "BOOLEAN"\n}' }

];

	    function escapeForHtml(value) {
        return escapeHtml(value);
    }

	    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function renderLogs() {
        const logsEl = document.getElementById('acsi-api-logs');
        if (!logsEl) {
            return;
        }

        if (logs.length === 0) {
            logsEl.innerHTML = '<div class="acsi-log-empty">No logs yet. Run an API from the panel.</div>';
            return;
        }

        logsEl.innerHTML = logs.map((entry) => {
            const details = entry.details
                ? `<pre class="acsi-log-details">${escapeForHtml(entry.details)}</pre>`
                : '';
            return `
                <div class="acsi-log-item acsi-log-${entry.type}">
                    <div class="acsi-log-head">
                        <span class="acsi-log-time">${escapeForHtml(entry.timestamp)}</span>
                        <span class="acsi-log-message">${escapeForHtml(entry.message)}</span>
                    </div>
                    ${details}
                </div>
            `;
        }).join('');
    }

	function logEntry(type, message, details) {
	logs.unshift({
		timestamp: new Date().toLocaleTimeString(),
		type,
		message,
		details,
	});
	if (logs.length > 60) {
		logs = logs.slice(0, 60);
	}
    }

	let endpointTarget;

	let endpoints = window.app.getEndpoints();

	selectEndpoint.innerHTML = endpoints.map((api) => `

    <option value="${api.name}/${api.port}">
        ${api.name} (${api.port})
    </option>
        `).join('');

	selectEl.innerHTML = apiDefinitions.map((api) => `
            <option value="${api.id}">${api.label}</option>
        `).join('');

	if(endpoints.length > 0)
	{
		endpointTarget = endpoints[0];

		 // --------------------------------
    // FILTER APIs
    // --------------------------------

    	let filteredApis = apiDefinitions;

		if (endpointTarget) {

			const endpointName = endpointTarget.name.toLowerCase();

			if (endpointName.includes('client')) {

				filteredApis = apiDefinitions.filter(api =>
					api.path.includes('/iec61850client/')
				);

			} else if (endpointName.includes('server')) {

				filteredApis = apiDefinitions.filter(api =>
					api.path.includes('/iec61850server/')
				);
			}
		}
	}


	function syncBodyPlaceholder() {

	const selected = apiDefinitions.find((api) => api.id === selectEl.value) || apiDefinitions[0];
	bodyEl.placeholder = selected.sampleBody || 'No body required for this endpoint.';
	if (!bodyEl.value.trim()) {
		bodyEl.value = selected.sampleBody || '';
	}
		
		
	}

	selectEl.addEventListener('change', () => {
		bodyEl.value = '';
		syncBodyPlaceholder();
	});

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
            requestUrl.searchParams.set('fspTarget', targetValue);
        }
        return requestUrl.toString();
    }

selectEndpoint.addEventListener('change', () => {

    const selectedValue = selectEndpoint.value;

    let selectedEndpoint = endpoints.find(
        (ep) => `${ep.name}/${ep.port}` === selectedValue
    );

    console.log(selectedEndpoint);

    endpointTarget = selectedEndpoint
        ? `${selectedEndpoint.name}:${selectedEndpoint.port}`
        : null;

    // --------------------------------
    // FILTER APIs
    // --------------------------------

    let filteredApis = apiDefinitions;

    if (selectedEndpoint) {

        const endpointName = selectedEndpoint.name.toLowerCase();

        if (endpointName.includes('client')) {

            filteredApis = apiDefinitions.filter(api =>
                api.path.includes('/iec61850client/')
            );

        } else if (endpointName.includes('server')) {

            filteredApis = apiDefinitions.filter(api =>
                api.path.includes('/iec61850server/')
            );
        }
    }

    // Reload select options
    selectEl.innerHTML = filteredApis.map((api) => `
        <option value="${api.id}">
            ${api.label}
        </option>
    `).join('');

});

	const selectedApiById = (id) => apiDefinitions.find((api) => api.id === id);

	renderLogs();
	wireTabs();

	 async function executeApiCall(selected, targetValue, bodyOverride) {
            if (!selected) {
                return null;
            }

            let url;
            try {
                url = buildBffApiUrl(selected.path, targetValue);
            } catch (error) {
                logEntry('error', `Blocked ${selected.label}`, String(error && error.message ? error.message : error));
                renderLogs();
                return null;
            }

            const options = {
                method: selected.method,
                headers: {
                    'Content-Type': 'application/json',
                },
            };

            if (targetValue) {
                options.headers['X-FSP-Target'] = targetValue;
            }

            if (selected.method === 'POST') {
                let payloadToSend = null;

                if (bodyOverride !== undefined) {
                    if (bodyOverride && typeof bodyOverride === 'object' && !Array.isArray(bodyOverride)) {
                        payloadToSend = { ...bodyOverride };
                    }
                } else {
                    const raw = bodyEl.value.trim();
                    if (raw) {
                        try {
                            payloadToSend = JSON.parse(raw);
                        } catch (error) {
                            logEntry('error', `Invalid JSON body for ${selected.label}`, String(error && error.message ? error.message : error));
                            renderLogs();
                            return null;
                        }
                    }
                }

                if (!payloadToSend) {
                    payloadToSend = {};
                }

                if (targetValue && typeof payloadToSend === 'object' && !Array.isArray(payloadToSend) && !payloadToSend.fspTarget) {
                    payloadToSend.fspTarget = targetValue;
                }

                options.body = JSON.stringify(payloadToSend);
            }

            try {
                runEl.disabled = true;
                logEntry('info', 'Checking BFF health', `URL: ${buildBffApiUrl('/api/health')}`);
                renderLogs();

                await ensureBffHealthy();

                logEntry('info', `Calling ${selected.label}`, `FSP target: ${targetValue || 'default'}\nURL: ${url}`);
                renderLogs();

                const response = await fetch(url, options);
                const rawText = await response.text();
                let formatted = rawText;
                let parsedPayload = null;

                try {
                    parsedPayload = JSON.parse(rawText);
                    formatted = JSON.stringify(parsedPayload, null, 2);
                } catch (error) {
                    // keep raw text for non-JSON responses
                }

                if (selected.id === 'model') {
                    if (!response.ok) {
                        setModelPanelMessage(`Model request failed with HTTP ${response.status}`, true);
                    } else {
                        setModelPanelMessage('Model response is not valid JSON.', true);
                    }
                }

                if (selected.id === 'messages') {
                    if (response.ok && parsedPayload) {
                        const messagesPayload = Object.prototype.hasOwnProperty.call(parsedPayload, 'messages')
                            ? parsedPayload.messages
                            : parsedPayload;
                        addProtocolMessagesEntry(messagesPayload);
                        renderProtocolMessages();
                    }
                }

                const messagePrefix = response.ok ? 'success' : 'error';
                logEntry(
                    messagePrefix,
                    `${selected.label} -> HTTP ${response.status}`,
                    formatted
                );

                return {
                    ok: response.ok,
                    status: response.status,
                    payload: parsedPayload,
                    rawText,
                };
            } catch (error) {
                logEntry('error', `Request failed for ${selected.label}`, String(error && error.message ? error.message : error));
                return null;
            } finally {
                runEl.disabled = false;
               
                renderLogs();
            }
	}

	    function setModelPanelMessage(message, isError = false) {
        const modelPanel = document.getElementById('acsi-modelPanel');
        if (!modelPanel) {
            return;
        }

        const cssClass = isError ? 'acsi-model-state acsi-model-error' : 'acsi-model-state';
        modelPanel.innerHTML = `<div class="${cssClass}">${escapeForHtml(message)}</div>`;
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
	    function buildTargetValue(host, port) {
        if (!host || port === undefined || port === null) {
            return '';
        }
        return `${host}:${port}`;
    }

	runEl.addEventListener('click', async () => {
            const selected = apiDefinitions.find((api) => api.id === selectEl.value);
            if (!selected) {
                return;
            }

            if (!endpointTarget) {
                logEntry('error', 'Run API blocked', 'No selected endpoint address available to resolve fspTarget.');
                renderLogs();
                return;
            }

            await executeApiCall(selected, endpointTarget);
        });

	let loadedTreeData = null;

	console.log('DOM elements:', { toolsSclFile, toolsGenerateModelBtn, toolsStatusInfo, toolsModelPanel });

	if (!toolsSclFile || !toolsGenerateModelBtn || !toolsStatusInfo || !toolsModelPanel) {
		console.error('Missing required DOM elements');
		return;
	}

	function resetSelectionControls() {
		if (toolsIedSelectWrap) toolsIedSelectWrap.style.display = 'none';
		if (toolsApSelectWrap) toolsApSelectWrap.style.display = 'none';
		if (toolsIedSelect) toolsIedSelect.innerHTML = '';
		if (toolsApSelect) toolsApSelect.innerHTML = '';
	}

	function populateSelect(selectElement, values) {
		if (!selectElement) return;
		selectElement.innerHTML = '';
		values.forEach(function (value) {
			const option = document.createElement('option');
			option.value = value;
			option.textContent = value;
			selectElement.appendChild(option);
		});
	}

	function getIedsFromTree() {
		if (!loadedTreeData || !Array.isArray(loadedTreeData.ieds)) {
			return [];
		}
		return loadedTreeData.ieds;
	}

	function updateSelectionControls() {
		if (!toolsIedSelectWrap || !toolsIedSelect || !toolsApSelectWrap || !toolsApSelect) {
			return;
		}

		const ieds = getIedsFromTree();
		if (ieds.length === 0) {
			resetSelectionControls();
			return;
		}

		let selectedIedName = toolsIedSelect.value;
		if (!selectedIedName || !ieds.some(function (ied) { return ied.name === selectedIedName; })) {
			selectedIedName = ieds[0].name;
		}

		const needsIedSelection = ieds.length > 1;
		if (needsIedSelection) {
			populateSelect(toolsIedSelect, ieds.map(function (ied) { return ied.name; }));
			toolsIedSelect.value = selectedIedName;
			toolsIedSelectWrap.style.display = 'grid';
		} else {
			toolsIedSelectWrap.style.display = 'none';
			toolsIedSelect.innerHTML = '';
		}

		const selectedIed = ieds.find(function (ied) { return ied.name === selectedIedName; }) || ieds[0];
		const accessPoints = Array.isArray(selectedIed.accessPoints) ? selectedIed.accessPoints : [];

		let selectedApName = toolsApSelect.value;
		if (!selectedApName || !accessPoints.some(function (ap) { return ap.name === selectedApName; })) {
			selectedApName = accessPoints[0] ? accessPoints[0].name : '';
		}

		const needsApSelection = accessPoints.length > 1;
		if (needsApSelection) {
			populateSelect(toolsApSelect, accessPoints.map(function (ap) { return ap.name; }));
			toolsApSelect.value = selectedApName;
			toolsApSelectWrap.style.display = 'grid';
		} else {
			toolsApSelectWrap.style.display = 'none';
			toolsApSelect.innerHTML = '';
		}
	}

	if (toolsIedSelect) {
		toolsIedSelect.addEventListener('change', function () {
			updateSelectionControls();
		});
	}

	toolsSclFile.addEventListener('change', async function () {
		console.log('SCL file change event triggered');
		const file = toolsSclFile.files && toolsSclFile.files[0];
		if (!file) {
			loadedTreeData = null;
			resetSelectionControls();
			if (toolsBrowseBtnText) {
				toolsBrowseBtnText.textContent = 'Browse SCL File';
			}
			toolsStatusInfo.textContent = 'Select an SCL file first.';
			return;
		}

		if (toolsBrowseBtnText) {
			toolsBrowseBtnText.textContent = file.name;
		}

		console.log('File selected:', file.name);
		toolsStatusInfo.textContent = 'Loading SCL model...';
		try {
			console.log('window.SCLTree:', window.SCLTree);
			if (!window.SCLTree || typeof window.SCLTree.loadSclFileAndRender !== 'function') {
				throw new Error('SCL tree renderer not available.');
			}

			loadedTreeData = await window.SCLTree.loadSclFileAndRender(file, 'tools-modelPanel');
			updateSelectionControls();
			toolsStatusInfo.textContent = 'SCL model loaded successfully.';
		} catch (error) {
			console.error('Error loading SCL:', error);
			loadedTreeData = null;
			resetSelectionControls();
			toolsModelPanel.textContent = '';
			toolsStatusInfo.textContent = 'Load SCL failed: ' + error.message;
		}
	});

	toolsGenerateModelBtn.addEventListener('click', async function () {
		console.log('Generate button clicked');
		const file = toolsSclFile.files && toolsSclFile.files[0];
		if (!file) {
			toolsStatusInfo.textContent = 'Select an SCL file first.';
			return;
		}

		toolsStatusInfo.textContent = 'Generating model.py...';
		toolsGenerateModelBtn.disabled = true;

		try {
			const sourceFromLoadedFile = file.path || file.webkitRelativePath || file.name;
			const ieds = getIedsFromTree();
			let selectedIedName = '';
			let selectedApName = '';

			const iedFromSelect = toolsIedSelect && toolsIedSelect.value;
			const selectedIed = ieds.find(function (ied) { return ied.name === iedFromSelect; }) || ieds[0] || null;

			if (selectedIed) {
				const selectedIedAccessPoints = Array.isArray(selectedIed.accessPoints) ? selectedIed.accessPoints : [];

				if (ieds.length > 1 || selectedIedAccessPoints.length > 1) {
					selectedIedName = selectedIed.name;
				}

				if (selectedIedAccessPoints.length > 1) {
					selectedApName = (toolsApSelect && toolsApSelect.value) || '';
					if (!selectedApName) {
						toolsStatusInfo.textContent = 'Select an Access Point before generating.';
						return;
					}
				}
			}

			await generatePythonModelFromScl(file, sourceFromLoadedFile, selectedIedName, selectedApName);
			toolsStatusInfo.textContent = 'model.py generated and downloaded.';
		} catch (error) {
			toolsStatusInfo.textContent = 'Generate model.py failed: ' + error.message;
		} finally {
			toolsGenerateModelBtn.disabled = false;
		}
	});

	   function setActiveTab(tab) {
        activeTab = tab === 'sclModelFactory' ? 'sclModelFactory' : 'api';

        const apiBtn = document.getElementById('api-btn');
        const sclModelBtn = document.getElementById('scl-model-factory-btn');
        const apiPanel = document.getElementById('api-tab');
        const sclModelPanel = document.getElementById('scl-model-factory-tab');

        if (apiBtn && sclModelBtn) {
            const apiActive = activeTab === 'api';
            apiBtn.classList.toggle('active', apiActive);
            sclModelBtn.classList.toggle('active', !apiActive);
            apiBtn.setAttribute('aria-selected', apiActive ? 'true' : 'false');
            sclModelBtn.setAttribute('aria-selected', apiActive ? 'false' : 'true');
        }

        if (apiPanel && sclModelPanel) {
            const apiActive = activeTab === 'api';
            apiPanel.classList.toggle('active', apiActive);
            sclModelPanel.classList.toggle('active', !apiActive);
            apiPanel.hidden = !apiActive;
            sclModelPanel.hidden = apiActive;
        }

		if(tab == "api")
		{
			let endpoints = window.app.getEndpoints();

			selectEndpoint.innerHTML = endpoints.map((api) => `

    <option value="${api.name}/${api.port}">
        ${api.name} (${api.port})
    </option>
        `).join('');

		}
    }

    function wireTabs() {
        const apiBtn = document.getElementById('api-btn');
        const sclModelBtn = document.getElementById('scl-model-factory-btn');
        if (!apiBtn || !sclModelBtn) {
            return;
        }

        apiBtn.addEventListener('click', () => setActiveTab('api'));
        sclModelBtn.addEventListener('click', () => setActiveTab('sclModelFactory'));
        setActiveTab(activeTab);
    }

	 async function loadTemplate() {
        if (templateCache) {
            return templateCache;
        }

        const response = await fetch('./tools-page.html', { cache: 'no-store' });
        if (!response.ok) {
            throw new Error('Unable to load tools-page.html');
        }

        templateCache = await response.text();
        return templateCache;
    }
};