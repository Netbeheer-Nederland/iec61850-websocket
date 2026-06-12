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
	const loadApisBtn = document.getElementById('load-apis-btn');
    let logs = [];
	let activeTab = 'sclModelFactory';

	let apiDefinitions = [];

	
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
		
		endpointTarget = endpoints.length > 0
			? `${endpoints[0].name}:${endpoints[0].port}`
			: null;


		 // --------------------------------
    // FILTER APIs
    // --------------------------------

    	let filteredApis = apiDefinitions;

		if (endpointTarget) {

			const endpointName = endpointTarget.toLowerCase();

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

	if(loadApisBtn)
	{
		loadApisBtn.addEventListener('click', async () => {

			for(const ep of endpoints)
			{
				const targetValue = `${ep.host}:${ep.port}`;
				await bootstrapApiDefinitions(targetValue);
			}
		});
	}

	async function bootstrapApiDefinitions(targetValue) {

		let endpointsToCall = null;
		const baseUrl = getBffBaseUrl();

		if(targetValue.includes('server'))
		{
			endpointsToCall = {
				id: 'apis-server',
				method: 'GET',
				path: '/api/iec61850server/apis'
			};
		}
		else if(targetValue.includes('client'))
		{
			endpointsToCall = {
				id: 'apis-client',
				method: 'GET',
				path: '/api/iec61850client/apis'
			};
		}
		else
			return;

		let allApis = [];

		const result = await executeApiCall(endpointsToCall, targetValue);

		if (!result || !result.ok || !result.payload) return;

		
		const apiPayload = result.payload?.result || result.payload;
		const endpoints = apiPayload?.endpoints || [];

		allApis = allApis.concat(endpoints);

		// ✅ transform to UI model
		
		const newApis = allApis.map((ep) => {
			const method = (ep.methods && ep.methods[0]) || 'GET';
			const path = ep.path;

			const id = path
				.replace('/api/', '')
				.replace(/\//g, '-')
				.replace(/^-/, '');

			return {
				id,
				label: `${method} ${path}`,
				method,
				path,
				sampleBody: method === 'POST' ? '{}' : ''
			};
		});

		// ✅ append WITHOUT duplicates
		newApis.forEach((newApi) => {
			const exists = apiDefinitions.some(api =>
				api.method === newApi.method &&
				api.path === newApi.path
			);

			if (!exists && !newApi.path.endsWith('/apis')) {  // <-- optional filter
				apiDefinitions.push(newApi);
			}
		});


		// ✅ update dropdown
		selectEl.innerHTML = apiDefinitions.map((api) => `
			<option value="${api.id}">
				${api.label}
			</option>
		`).join('');

		console.log("✅ Bootstrap API loaded:", apiDefinitions);
	}
``

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

		console.log("fspTarget:", targetValue, typeof targetValue);

		
		if (targetValue && typeof targetValue !== 'string') {
			console.error("Invalid fspTarget, fixing:", targetValue);
			targetValue = `${targetValue.name}:${targetValue.port}`;
		}


        //if (targetValue) {
          //  requestUrl.searchParams.set('fspTarget', targetValue);
        //}
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
				url = buildBffApiUrl('/api/execute');
                //url = buildBffApiUrl(selected.path, targetValue);
            } catch (error) {
                logEntry('error', `Blocked ${selected.label}`, String(error && error.message ? error.message : error));
                renderLogs();
                return null;
            }

            
			const options = {
				method: 'POST',  // ✅ always POST to /execute
				headers: {
					'Content-Type': 'application/json',
				},
			};


            // ✅ build generic execute payload
			let payloadToSend = {
				target: targetValue,
				method: selected.method,
				path: selected.path
			};

			// ✅ attach body only if POST
			if (selected.method === 'POST') {
				const raw = bodyEl.value.trim();
				if (raw) {
					try {
						payloadToSend.body = JSON.parse(raw);
					} catch (error) {
						logEntry('error', `Invalid JSON body`, error.message);
						renderLogs();
						return null;
					}
				}
			}

			options.body = JSON.stringify(payloadToSend);

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

						// ✅ unwrap /api/execute response
						const realPayload = parsedPayload.result || parsedPayload;

						formatted = JSON.stringify(realPayload, null, 2);

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

					if (selected.id === 'apis' && response.ok && parsedPayload) {

						const endpoints = parsedPayload?.apis?.endpoints || [];

						apiDefinitions = endpoints.map((ep) => {
							const method = (ep.methods && ep.methods[0]) || 'GET';
							const path = ep.path;

							const id = path
								.replace('/api/', '')
								.replace(/\//g, '-')
								.replace(/^-/, '');

							return {
								id,
								label: `${method} ${path}`,
								method,
								path,
								sampleBody: method === 'POST' ? '{}' : ''
							};
		});

		// ✅ refresh dropdown
		selectEl.innerHTML = apiDefinitions.map((api) => `
			<option value="${api.id}">
				${api.label}
			</option>
		`).join('');

		logEntry('success', 'API list updated dynamically', JSON.stringify(apiDefinitions, null, 2));
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