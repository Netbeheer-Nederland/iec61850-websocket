/**
 * ACSI Client Page Renderer
 * Renders the ACSI Client interface for connecting to IEC 61850 servers
 */

window.ACSIClientPage = {
    render: function(rootElement, selectedEndpoint) {
        if (!rootElement) return;

        const endpoint = selectedEndpoint || {};
        const host = endpoint.host || '';
        const port = endpoint.port || '';

        rootElement.innerHTML = `
            <div class="page-header">
                <div style="display:flex; align-items:center; gap:16px;">
                    <h1><i class="fas fa-microchip" style="margin-right:10px; color:var(--primary-light);"></i>ACSI Client</h1>
                    <span class="acsi-endpoint-badge" style="display:inline-block; padding:4px 12px; background:var(--info-color); color:white; border-radius:4px; font-size:12px;">
                        ${endpoint.name || ''} · ${host}:${port}
                    </span>
                </div>
            </div>

            <div style="margin-top:24px;">
                <h2>Connection Settings</h2>
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap:16px; margin-top:16px;">
                    <div class="setting-item">
                        <label for="acsi-client-host-page">Host</label>
                        <input type="text" id="acsi-client-host-page" value="${host}" placeholder="127.0.0.1">
                    </div>

                    <div class="setting-item">
                        <label for="acsi-client-port-page">Port</label>
                        <input type="number" id="acsi-client-port-page" value="${port}" placeholder="102">
                    </div>

                    <div class="setting-item">
                        <label for="acsi-client-cp-page">Connection Point (CP)</label>
                        <input type="text" id="acsi-client-cp-page" value="cp1" placeholder="cp1">
                    </div>
                </div>

                <div style="margin-top:24px; display:flex; gap:12px;">
                    <button id="acsi-client-connect-page-btn" class="btn-primary" style="padding:10px 20px;">
                        <i class="fas fa-plug" style="margin-right:8px;"></i>
                        Connect
                    </button>
                    <button id="acsi-client-disconnect-page-btn" class="btn-secondary" style="padding:10px 20px;" disabled>
                        <i class="fas fa-plug" style="margin-right:8px;"></i>
                        Disconnect
                    </button>
                </div>
            </div>

            <div id="acsi-client-status" style="margin-top:24px; padding:16px; background:var(--bg-secondary); border-radius:8px; display:none;">
                <h3>Status</h3>
                <div id="acsi-client-status-message" style="margin-top:8px; color:var(--text-muted);"></div>
            </div>

            <div id="acsi-client-tree-page" style="margin-top:24px;">
                <h2>Server Model</h2>
                <button id="acsi-client-fetch-model-btn" class="btn-primary" style="margin-top:12px; padding:10px 20px;" disabled>
                    <i class="fas fa-download" style="margin-right:8px;"></i>
                    Fetch Model
                </button>
                <div id="acsi-client-tree-container-page" style="margin-top:16px; padding:16px; background:var(--bg-secondary); border-radius:8px; display:none;">
                    <div id="acsi-client-tree-content" style="max-height:600px; overflow-y:auto; color:var(--text-secondary);"></div>
                </div>
            </div>
        `;

        // Setup event listeners
        this.setupEventListeners(rootElement);
    },

    setupEventListeners: function(rootElement) {
        const connectBtn = rootElement.querySelector('#acsi-client-connect-page-btn');
        const disconnectBtn = rootElement.querySelector('#acsi-client-disconnect-page-btn');
        const fetchModelBtn = rootElement.querySelector('#acsi-client-fetch-model-btn');

        if (connectBtn) {
            connectBtn.addEventListener('click', () => this.handleConnect(rootElement));
        }

        if (disconnectBtn) {
            disconnectBtn.addEventListener('click', () => this.handleDisconnect(rootElement));
        }

        if (fetchModelBtn) {
            fetchModelBtn.addEventListener('click', () => this.handleFetchModel(rootElement));
        }
    },

    handleConnect: function(rootElement) {
        const host = rootElement.querySelector('#acsi-client-host-page').value.trim();
        const port = parseInt(rootElement.querySelector('#acsi-client-port-page').value.trim());
        const cp = rootElement.querySelector('#acsi-client-cp-page').value.trim() || 'cp1';

        if (!host || !port) {
            this.showStatus(rootElement, 'Please enter both host and port', 'error');
            return;
        }

        if (isNaN(port) || port < 1 || port > 65535) {
            this.showStatus(rootElement, 'Invalid port number', 'error');
            return;
        }

        // Call BFF to connect
        this.callBFF('/api/iec61850client/connect', 'POST', { host, port, cp })
            .then(result => {
                if (result && result.ok) {
                    this.showStatus(rootElement, `Connected to ${host}:${port}`, 'success');
                    rootElement.querySelector('#acsi-client-connect-page-btn').disabled = true;
                    rootElement.querySelector('#acsi-client-disconnect-page-btn').disabled = false;
                    rootElement.querySelector('#acsi-client-fetch-model-btn').disabled = false;
                } else {
                    const error = result?.error || 'Unknown error';
                    this.showStatus(rootElement, `Connection failed: ${error}`, 'error');
                }
            })
            .catch(err => {
                this.showStatus(rootElement, `Error: ${err.message}`, 'error');
            });
    },

    handleDisconnect: function(rootElement) {
        this.callBFF('/api/iec61850client/disconnect', 'POST', {})
            .then(result => {
                if (result && result.ok) {
                    this.showStatus(rootElement, 'Disconnected', 'info');
                    rootElement.querySelector('#acsi-client-connect-page-btn').disabled = false;
                    rootElement.querySelector('#acsi-client-disconnect-page-btn').disabled = true;
                    rootElement.querySelector('#acsi-client-fetch-model-btn').disabled = true;
                    rootElement.querySelector('#acsi-client-tree-container-page').style.display = 'none';
                } else {
                    const error = result?.error || 'Unknown error';
                    this.showStatus(rootElement, `Disconnect failed: ${error}`, 'error');
                }
            })
            .catch(err => {
                this.showStatus(rootElement, `Error: ${err.message}`, 'error');
            });
    },

    handleFetchModel: function(rootElement) {
        this.showStatus(rootElement, 'Fetching model...', 'info');

        this.callBFF('/api/iec61850client/model/tree', 'GET', null)
            .then(result => {
                if (result && result.ok) {
                    const treeContainer = rootElement.querySelector('#acsi-client-tree-container-page');
                    const treeContent = rootElement.querySelector('#acsi-client-tree-content');

                    treeContent.innerHTML = `<pre>${JSON.stringify(result.result || result, null, 2)}</pre>`;
                    treeContainer.style.display = 'block';

                    this.showStatus(rootElement, 'Model fetched successfully', 'success');
                } else {
                    const error = result?.error || 'Failed to fetch model';
                    this.showStatus(rootElement, error, 'error');
                }
            })
            .catch(err => {
                this.showStatus(rootElement, `Error: ${err.message}`, 'error');
            });
    },

    showStatus: function(rootElement, message, type = 'info') {
        const statusDiv = rootElement.querySelector('#acsi-client-status');
        const statusMessage = rootElement.querySelector('#acsi-client-status-message');

        statusDiv.style.display = 'block';
        statusMessage.textContent = message;

        const colorMap = {
            'success': 'var(--success-color)',
            'error': 'var(--danger-color)',
            'warning': 'var(--warning-color)',
            'info': 'var(--info-color)'
        };

        statusDiv.style.borderLeft = `4px solid ${colorMap[type] || colorMap['info']}`;
    },

    callBFF: function(endpoint, method = 'GET', data = null) {
        const bffBaseUrl = window.app?.bffBaseUrl || 'http://localhost:5000';

        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
            }
        };

        if (data) {
            options.body = JSON.stringify(data);
        }

        return fetch(`${bffBaseUrl}${endpoint}`, options)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            });
    }
};

