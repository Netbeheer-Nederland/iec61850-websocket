/* ==============================================
   RTI Demo UI - Application JavaScript
   ============================================== */

class RTIDemoApp {
    constructor() {
        this.bffHost = localStorage.getItem('bffHost') || 'localhost';
        this.bffPort = localStorage.getItem('bffPort') || '5000';
        this.scanHost = localStorage.getItem('scanHost') || 'localhost';
        this.scanPorts = localStorage.getItem('scanPorts') || '5001,5002';
        this.bffBaseUrl = `http://${this.bffHost}:${this.bffPort}`;
        
        this.connections = [];
        this.endpoints = [];
        this.selectedAcsiEndpoint = null;
        this.isBffConnected = false;
        this.autoRefreshInterval = null;
        this.messageHistory = [];
        
        this.selectedEndpoint = null;

        // ACSI state
        this._acsiDataTarget   = 'fsp';   // 'fsp' | 'so'
        this._acsiModelTarget  = 'fsp';
        this._acsiMonitorTarget = 'fsp';
        this._monitorTimer     = null;
        this._modelLds         = [];
        this._modelLns         = [];
        this._selectedLd       = null;
        this._selectedLn       = null;

        this.init();
    }

    init() {
        this.setupEventListeners();
        this.loadSettings();
        this.checkBFFConnection();
        this.startAutoRefresh();
    }

    // =============================================
    // Event Listeners Setup
    // =============================================

    setupEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-item').forEach(item => {
            item.addEventListener('click', (e) => this.handleNavigation(e));
        });

        // Quick Actions
        document.getElementById('btn-connections').addEventListener('click', () => this.navigateToPage('connections'));
        document.getElementById('btn-model').addEventListener('click', () => this.navigateToPage('model'));
        document.getElementById('btn-data').addEventListener('click', () => this.navigateToPage('data'));
        document.getElementById('btn-reports').addEventListener('click', () => this.navigateToPage('reports'));
        document.getElementById('btn-diagnostics').addEventListener('click', () => this.navigateToPage('diagnostics'));

        // Connections
        document.getElementById('btn-add-connection').addEventListener('click', () => this.openConnectionModal());

        // Data Operations
        document.getElementById('btn-read-data').addEventListener('click', () => this.readData());
        document.getElementById('btn-write-data').addEventListener('click', () => this.writeData());

        // Settings
        document.getElementById('btn-save-settings').addEventListener('click', () => this.saveSettings());
        document.getElementById('dark-mode-toggle').addEventListener('change', () => this.toggleDarkMode());
        document.getElementById('auto-refresh-toggle').addEventListener('change', (e) => this.toggleAutoRefresh(e));

        // Header
        document.getElementById('refresh-btn').addEventListener('click', () => this.handleManualRefresh());
        document.getElementById('discovery-btn').addEventListener('click', () => this.discoverEndpoints());

        // Modal
        document.querySelector('.btn-close').addEventListener('click', () => this.closeConnectionModal());
        document.getElementById('btn-modal-close').addEventListener('click', () => this.closeConnectionModal());
        document.getElementById('btn-modal-save').addEventListener('click', () => this.saveConnection());

        // Reports
        document.getElementById('btn-export-reports').addEventListener('click', () => this.exportReports());
        document.getElementById('btn-clear-diagnostics').addEventListener('click', () => this.clearDiagnostics());

        // ACSI Client
        const acsiConnectBtn = document.getElementById('acsi-connect-btn');
        if (acsiConnectBtn) {
            acsiConnectBtn.addEventListener('click', () => this.connectACSIClient());
        }

        //acsi client
        document.getElementById('acsi-connect-btn').addEventListener('click', () => this.connectACSIClient());
    }

    // =============================================
    // Navigation
    // =============================================

    handleNavigation(e) {
        const navItems = document.querySelectorAll('.nav-item');
        navItems.forEach(item => item.classList.remove('active'));
        e.currentTarget.classList.add('active');

        const pageName = e.currentTarget.getAttribute('data-page');
        this.navigateToPage(pageName);
    }

    navigateToPage(pageName) {
        // Hide all pages
        document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
        // Show selected page
        const page = document.getElementById(`page-${pageName}`);
        if (page) {
            page.classList.add('active');
        }

        // Update breadcrumb and nav
        const navItem = document.querySelector(`[data-page="${pageName}"]`);
        if (navItem) {
            document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
            navItem.classList.add('active');
            const pageName_formatted = pageName.charAt(0).toUpperCase() + pageName.slice(1);
            document.getElementById('breadcrumb-text').textContent = pageName_formatted;
        }

        // Load page-specific content
        this.loadPageContent(pageName);
    }

    // =============================================
    // Tools Page Logic
    // =============================================
    loadTools() {
        // Reset status/info fields
        const statusInfo = document.getElementById('tools-statusInfo');
        if (statusInfo) statusInfo.textContent = '';

        // Reset file input
        const sclFileInput = document.getElementById('tools-sclFile');
        if (sclFileInput) sclFileInput.value = '';

        // Hide select wrappers
        const iedWrap = document.getElementById('tools-iedSelectWrap');
        const apWrap = document.getElementById('tools-apSelectWrap');
        if (iedWrap) iedWrap.style.display = 'none';
        if (apWrap) apWrap.style.display = 'none';

        // Clear SCL tree panel
        const modelPanel = document.getElementById('tools-modelPanel');
        if (modelPanel) modelPanel.innerHTML = '';

    }

    loadPageContent(pageName) {
        switch(pageName) {
            case 'dashboard':
                this.refreshDashboard();
                break;
            case 'connections':
                this.loadConnections();
                break;
            case 'model':
                this.loadModel();
                break;
            case 'reports':
                this.loadReports();
                break;
            case 'diagnostics':
                this.loadDiagnostics();
                break;
            case 'tools':
                this.loadTools();
                break;
            case 'acsi-server':
                this.loadAcsiServerPage();
                break;
            case 'acsi-client':
                this.loadAcsiClientPage();
                break;
        }
    }

    loadAcsiServerPage() {
        const root = document.getElementById('acsi-server-page-root');
        if (!root) {
            return;
        }

        if (window.ACSIServerPage && typeof window.ACSIServerPage.render === 'function') {
            window.ACSIServerPage.render(root, this.selectedAcsiEndpoint);
            return;
        }

        root.innerHTML = '<p style="color: var(--text-muted);">ACSI Server page is unavailable.</p>';
    }

    loadAcsiClientPage() {
        const root = document.getElementById('acsi-client-page-root');
        if (!root) {
            return;
        }

        if (window.ACSIClientPage && typeof window.ACSIClientPage.render === 'function') {
            window.ACSIClientPage.render(root, this.selectedAcsiEndpoint);
            return;
        }

        root.innerHTML = '<p style="color: var(--text-muted);">ACSI Client page is unavailable.</p>';
    }

    loadACSI() {
        // Simply show the page-acsi section
        // The page-acsi HTML is already in index.html with the ACSI client connection form
        // No dynamic loading needed - the form is static HTML
    }
    // =============================================
    // BFF Communication
    // =============================================

    async callBFF(endpoint, method = 'GET', data = null) {
        try {
            const options = {
                method,
                headers: {
                    'Content-Type': 'application/json',
                }
            };

            if (data) {
                options.body = JSON.stringify(data);
            }

            const response = await fetch(`${this.bffBaseUrl}${endpoint}`, options);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`BFF call failed: ${endpoint}`, error);
            this.addDiagnosticMessage(`Error: ${error.message}`, 'error');
            return null;
        }
    }

    async checkBFFConnection() {
        const result = await this.callBFF('/api/health');
        const statusDot = document.getElementById('bff-status-dot');
        const statusText = document.getElementById('bff-status-text');
        const isConnected = !!(result && ((result.bff && result.bff.connected) || result.status === 'ok'));
        this.isBffConnected = isConnected;

        if (isConnected) {
            if (statusDot) {
                statusDot.classList.add('connected');
            }
            if (statusText) {
                statusText.textContent = 'BFF connected';
            }
            this.addDiagnosticMessage('Connected to BFF server', 'success');
        } else {
            if (statusDot) {
                statusDot.classList.remove('connected');
            }
            if (statusText) {
                statusText.textContent = 'BFF disconnected';
            }
            this.addDiagnosticMessage('Failed to connect to BFF server', 'warning');
        }

        return isConnected;
    }

    // =============================================
    // Dashboard
    // =============================================

    async refreshDashboard() {
        this.renderEndpoints();
    }

    async handleManualRefresh() {
        // Always re-apply current Settings values before trying to reconnect/refresh.
        if (!this.updateBffConfigFromSettingsInputs(false)) {
            return;
        }

        await this.checkBFFConnection();
        await this.refreshDashboard();
    }

    // =============================================
    // Endpoints Discovery
    // =============================================

    async discoverEndpoints() {
        if (!this.updateScanConfigFromSettingsInputs(false)) {
            return;
        }

        const ports = this.parsePortList(this.scanPorts);
        if (ports.length === 0) {
            this.addDiagnosticMessage('Discovery ports are required (for example: 5001,5002).', 'error');
            return;
        }

        const connected = await this.checkBFFConnection();
        if (!connected) {
            this.addDiagnosticMessage('Discovery requires an active BFF connection (health check failed).', 'warning');
            return;
        }

        const result = await this.callBFF('/api/endpoints/discover', 'POST', {
            host: this.scanHost,
            ports,
        });
        
        if (result) {
            this.addDiagnosticMessage(
                `Discovery complete: Found ${result.count} endpoint(s)`,
                'success'
            );
            // Reload endpoints to show any newly discovered ones
            await this.loadEndpoints();
        }
    }

    async loadEndpoints() {
        if (!this.isBffConnected) {
            this.addDiagnosticMessage('Skipping /api/endpoints: BFF is not connected.', 'warning');
            return;
        }

        const result = await this.callBFF('/api/endpoints');
        
        if (!result) {
            this.addDiagnosticMessage('Failed to load endpoints', 'error');
            return;
        }

        this.endpoints = result.endpoints || [];
        
        // Separate discovered from manual
        const discovered = this.endpoints.filter(e => e.auto_discovered);
        const manual = this.endpoints.filter(e => !e.auto_discovered);
        
        if (discovered.length > 0) {
            this.addDiagnosticMessage(
                `Auto-discovered ${discovered.length} endpoint(s) from Docker`,
                'info'
            );
        }
        
        this.renderEndpoints();
    }

    renderEndpoints() {
        const container = document.getElementById('endpoints-container');
        container.innerHTML = '';

        if (this.endpoints.length === 0) {
            container.innerHTML = `
                <div style="padding: 20px; text-align: center; color: var(--text-muted);">
                    <p>No endpoints configured or discovered</p>
                    <button class="btn-primary" id="btn-discover-now" style="margin-top: 10px;">
                        <i class="fas fa-search"></i>
                        Search for Endpoints
                    </button>
                </div>
            `;
            document.getElementById('btn-discover-now').addEventListener('click', () => this.discoverEndpoints());
            return;
        }

        // Group endpoints
        const discovered = this.endpoints.filter(e => e.auto_discovered);
        const manual = this.endpoints.filter(e => !e.auto_discovered);

        // Render discovered first
        if (discovered.length > 0) {
            const discoveredSection = document.createElement('div');
            discoveredSection.innerHTML = `
                <div style="padding: 12px 0; border-bottom: 1px solid var(--border-color); margin-bottom: 12px;">
                    <h3 style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">
                        <i class="fas fa-docker"></i> Auto-Discovered Endpoints
                    </h3>
                </div>
            `;
            container.appendChild(discoveredSection);

            discovered.forEach(endpoint => {
                const card = this.createEndpointCard(endpoint);
                container.appendChild(card);
            });
        }

        // Render manual connections
        if (manual.length > 0) {
            const manualSection = document.createElement('div');
            manualSection.innerHTML = `
                <div style="padding: 12px 0; border-bottom: 1px solid var(--border-color); margin-bottom: 12px; margin-top: 20px;">
                    <h3 style="font-size: 12px; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">
                        <i class="fas fa-cog"></i> Manual Connections
                    </h3>
                </div>
            `;
            container.appendChild(manualSection);

            manual.forEach(endpoint => {
                const card = this.createEndpointCard(endpoint);
                container.appendChild(card);
            });
        }
    }

    createEndpointCard(endpoint) {
        const card = document.createElement('div');
        card.className = `endpoint-card ${endpoint.status === 'connected' ? '' : 'disconnected'}`;
        
        const typeIcon = endpoint.type === 'RTI-SO' ? 'server' : 'network-wired';
        const badge = endpoint.auto_discovered ? 
            '<span style="display: inline-block; margin-left: 8px; padding: 2px 8px; background: var(--info-color); color: white; border-radius: 4px; font-size: 10px; font-weight: 600;">Auto-discovered</span>' 
            : '';
        
        // Extract properties from properties_info
        const props = endpoint.properties_info.properties || {};
        const serverRole = props['acsi-role'] || props['acsi_role'] || 'N/A';
        const wsMode = props['ws_mode'] || 'N/A';
        
        card.innerHTML = `
            <div class="endpoint-card-icon">
                <i class="fas fa-${typeIcon}"></i>
            </div>
            <div class="endpoint-card-info">
                <div class="endpoint-card-name">${endpoint.name}${badge}</div>
                <div class="endpoint-card-desc">${endpoint.host}:${endpoint.port}</div>
                <div style="margin-top: 8px;">
                    <span class="endpoint-card-status">${endpoint.status}</span>
                    <small style="color: var(--text-muted); margin-left: 8px; font-size: 11px;">
                        ${endpoint.type}
                    </small>
                </div>
                <div style="margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--border-color); font-size: 12px;">
                    <div style="margin-bottom: 4px;">
                        <strong>ACSI Role:</strong> <span style="color: var(--text-muted);">${serverRole}</span>
                    </div>
                    <div>
                        <strong>WS Mode:</strong> <span style="color: var(--text-muted);">${wsMode}</span>
                    </div>
                </div>
            </div>
        `;

        card.addEventListener('click', () => this.configureEndpoint(endpoint));
        return card;
    }

    configureEndpoint(endpoint) {
        const props = endpoint.properties_info?.properties || {};
        const acsiRoleRaw = props['acsi-role'] || props['acsi_role'] || '';
        const acsiRole = String(acsiRoleRaw).trim().toLowerCase();

        if (acsiRole === 'acsi_server') {
            this.selectedAcsiEndpoint = endpoint;
            this.navigateToPage('acsi-server');
            return;
        }
        if (acsiRole === 'acsi_client') {
            this.selectedAcsiEndpoint = endpoint;
            this.navigateToPage('acsi-client');
            return;
        }

        // Default behavior for non-ACSI server endpoints.
        this.navigateToPage('connections');
        this.selectedEndpoint = endpoint;

        // Show badge with endpoint name/host:port
        const badge = document.getElementById('acsi-endpoint-badge');
        if (badge && endpoint) {
            badge.textContent = `${endpoint.name || ''} · ${endpoint.host}:${endpoint.port}`;
            badge.style.display = 'inline-block';
        }

        this.navigateToPage('acsi');
    }

    // =============================================
    // ACSI Page
    // =============================================

    async loadConnections() {
        const result = await this.callBFF('/api/connections');

        if (!result) {
            this.addDiagnosticMessage('Failed to load connections', 'error');
            return;
        }

        this.connections = result.connections || [];
        this.renderConnectionsTable();
    }

    async connectACSIClient(){
        const host = document.getElementById('acsi-client-host').value.trim();
        const port = parseInt(document.getElementById('acsi-client-port').value.trim());
        const cp   = document.getElementById('acsi-client-cp').value.trim() || 'cp1';

        // Validate inputs
        if (!host || !port) {
            this.addDiagnosticMessage('Please enter both host and port', 'error');
            return;
        }

        if (isNaN(port) || port < 1 || port > 65535) {
            this.addDiagnosticMessage('Invalid port number', 'error');
            return;
        }

        // Call the ACSI client connect endpoint
        const result = await this.callBFF('/api/iec61850client/connect', 'POST', { host, port, cp });

        if (result && result.ok) {
            this.addDiagnosticMessage(`Connected to ACSI server at ${host}:${port}`, 'success');
            this._connectedACSIClient = { host, port };
        } else {
            const errorMsg = result?.error || 'Unknown error';
            this.addDiagnosticMessage(`Failed to connect to ACSI server: ${errorMsg}`, 'error');
        }
    }
    renderConnectionsTable() {
        const container = document.getElementById('connections-container');

        if (this.connections.length === 0) {
            container.innerHTML = '<p style="padding: 20px; color: var(--text-muted);">No connections</p>';
            return;
        }

        let html = `
            <table class="table">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Host</th>
                        <th>Port</th>
                        <th>Status</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
        `;

        this.connections.forEach(conn => {
            html += `
                <tr>
                    <td>${conn.name}</td>
                    <td>${conn.type}</td>
                    <td>${conn.host}</td>
                    <td>${conn.port}</td>
                    <td>
                        <span style="display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 600; background: ${conn.status === 'connected' ? 'var(--success-color)' : 'var(--danger-color)'}; color: white;">
                            ${conn.status}
                        </span>
                    </td>
                    <td>
                        <button class="btn-primary" style="padding: 6px 12px; font-size: 12px;" onclick="app.editConnection(${conn.id})">
                            Edit
                        </button>
                        <button class="btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick="app.deleteConnection(${conn.id})">
                            Delete
                        </button>
                    </td>
                </tr>
            `;
        });

        html += `
                </tbody>
            </table>
        `;

        container.innerHTML = html;
    }

    openConnectionModal() {
        document.getElementById('modal-connection').classList.add('active');
        document.getElementById('conn-name').value = '';
        document.getElementById('conn-host').value = '';
        document.getElementById('conn-port').value = '5000';
        document.getElementById('conn-type').value = 'RTI-SO';
    }

    closeConnectionModal() {
        document.getElementById('modal-connection').classList.remove('active');
    }

    async saveConnection() {
        const connection = {
            name: document.getElementById('conn-name').value,
            host: document.getElementById('conn-host').value,
            port: parseInt(document.getElementById('conn-port').value),
            type: document.getElementById('conn-type').value,
        };

        if (!connection.name || !connection.host) {
            alert('Name and host are required');
            return;
        }

        const result = await this.callBFF('/api/connections', 'POST', connection);

        if (result) {
            this.closeConnectionModal();
            this.loadConnections();
            this.addDiagnosticMessage(`Connection '${connection.name}' saved`, 'success');
        }
    }

    async deleteConnection(id) {
        if (confirm('Are you sure?')) {
            const result = await this.callBFF(`/api/connections/${id}`, 'DELETE');
            if (result) {
                this.loadConnections();
                this.addDiagnosticMessage('Connection deleted', 'success');
            }
        }
    }

    editConnection(id) {
        const conn = this.connections.find(c => c.id === id);
        if (conn) {
            document.getElementById('conn-name').value = conn.name;
            document.getElementById('conn-host').value = conn.host;
            document.getElementById('conn-port').value = conn.port;
            document.getElementById('conn-type').value = conn.type;
            document.getElementById('modal-connection').classList.add('active');
        }
    }

    // =============================================
    // Model Management
    // =============================================

    async loadModel() {
        const container = document.getElementById('model-tree-container');
        if (!container) return;
        container.innerHTML = '<p style="padding:20px; color:var(--text-muted);">Loading model…</p>';

        const result = await this.callBFF('/api/model/tree');
        
        if (!result) {
            this.addDiagnosticMessage('Failed to load model tree', 'error');
            return;
        }

        container.innerHTML = `
            <pre style="padding:20px; font-size:12px; color:var(--text-secondary);
                white-space:pre-wrap; word-break:break-all;">
${JSON.stringify(result, null, 2)}</pre>`;
    }
    async loadModelClient() {
        const result = await this.callBFF('/api/model/tree');

        if (!result) {
            this.addDiagnosticMessage('Failed to load model tree', 'error');
            return;
        }

        this.renderModelTree(result.tree);
    }

    renderModelTree(tree) {
        const container = document.getElementById('model-tree-container');
        container.innerHTML = this.buildTreeHTML(tree);
    }

    buildTreeHTML(node, level = 0) {
        let html = '';

        if (Array.isArray(node)) {
            node.forEach(item => {
                html += this.buildTreeHTML(item, level);
            });
        } else if (typeof node === 'object' && node !== null) {
            const indent = `${level * 20}px`;
            const isExpandable = node.children && node.children.length > 0;

            html += `
                <div style="padding-left: ${indent}; margin: 4px 0;">
                    ${isExpandable ? '<i class="fas fa-chevron-right" style="cursor: pointer; width: 16px;"></i>' : '<i style="width: 16px;"></i>'}
                    <i class="fas fa-${node.icon || 'cube'}"></i>
                    <span style="margin-left: 8px;">${node.name || 'Unknown'}</span>
                </div>
            `;

            if (isExpandable) {
                html += this.buildTreeHTML(node.children, level + 1);
            }
        }

        return html;
    }

    // =============================================
    // Data Page
    // =============================================

    async readData() {
        const objRef  = document.getElementById('data-ref').value.trim();
        const output  = document.getElementById('data-output');
        if (!objRef) { output.textContent = 'Enter a data reference first.'; return; }

        const result = await this.callBFF('/api/iec61850server/readvalue', 'POST', { objRef });
        output.textContent = result ? JSON.stringify(result, null, 2) : 'Read failed.';
    }

    async writeData() {
        const objRef = document.getElementById('data-ref').value.trim();
        const value  = document.getElementById('data-value').value.trim();
        const output = document.getElementById('data-output');
        if (!objRef || !value) { output.textContent = 'Enter both a reference and a value.'; return; }

        const result = await this.callBFF('/api/iec61850server/writevalue', 'POST', { objRef, value });
        output.textContent = result ? JSON.stringify(result, null, 2) : 'Write failed.';
    }

    // =============================================
    // Reports Page
    // =============================================

    async loadReports() {
        const result = await this.callBFF('/api/reports');
        
        if (!result) {
            this.addDiagnosticMessage('Failed to load reports', 'error');
            return;
        }

        this.renderReports(result.reports);
    }

    async renderReports(reports) {
        const container = document.getElementById('reports-container');
        if (!container) return;
        const result = await this.callBFF('/api/reports');
        if (!result || !result.reports) {
            container.innerHTML = '<p style="padding:20px; color:var(--text-muted);">No reports available.</p>';
            return;
        }
        container.innerHTML = result.reports.map(r => `
            <div style="padding:16px; border-bottom:1px solid var(--border-color);">
                <strong>${r.name}</strong>
                <p style="color:var(--text-muted); font-size:13px; margin-top:4px;">${r.description || ''}</p>
                <small style="color:var(--text-muted);">${r.timestamp || ''}</small>
            </div>`).join('');
    }

    async exportReports() {
        const result = await this.callBFF('/api/reports/export', 'POST');
        if (result) {
            const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: 'application/json' });
            const url  = URL.createObjectURL(blob);
            const a    = document.createElement('a');
            a.href = url; a.download = 'reports_export.json'; a.click();
            URL.revokeObjectURL(url);
            this.addDiagnosticMessage('Reports exported.', 'success');
        }
    }

    // =============================================
    // Diagnostics
    // =============================================

    async loadDiagnostics() {
        this.renderDiagnostics();
    }

    renderDiagnostics() {
        const container = document.getElementById('diagnostics-container');
        if (!container) return;
        if (!this.messageHistory.length) {
            container.innerHTML = '<p style="padding:20px; color:var(--text-muted);">No diagnostic messages.</p>';
            return;
        }
        container.innerHTML = '<div style="max-height:600px; overflow-y:auto;">' +
            this.messageHistory.map(msg => {
                const iconMap  = { success: 'check-circle', error: 'exclamation-circle', warning: 'exclamation-triangle', info: 'info-circle' };
                const colorMap = { success: 'var(--success-color)', error: 'var(--danger-color)', warning: 'var(--warning-color)', info: 'var(--info-color)' };
                return `<div style="padding:12px; border-bottom:1px solid var(--border-color); display:flex; gap:12px;">
                    <i class="fas fa-${iconMap[msg.type] || 'info-circle'}" style="color:${colorMap[msg.type] || 'var(--info-color)'}; width:16px; flex-shrink:0; margin-top:3px;"></i>
                    <div>
                        <div style="font-size:12px; color:var(--text-muted);">${msg.timestamp}</div>
                        <div>${this._escHtml(msg.message)}</div>
                    </div>
                </div>`;
            }).join('') + '</div>';
    }

    addDiagnosticMessage(message, type = 'info') {
        this.messageHistory.unshift({ message, type, timestamp: new Date().toLocaleTimeString() });
        if (this.messageHistory.length > 100) this.messageHistory.pop();
    }

    async clearDiagnostics() {
        if (!confirm('Clear all diagnostic messages?')) return;
        this.messageHistory = [];
        this.renderDiagnostics();
        this.addDiagnosticMessage('Diagnostic messages cleared.', 'success');
    }

    // =============================================
    // Settings
    // =============================================

    loadSettings() {
        const bffHostEl   = document.getElementById('bff-host');
        const bffPortEl   = document.getElementById('bff-port');
        const scanHostEl  = document.getElementById('scan-host');
        const scanPortsEl = document.getElementById('scan-ports');
        if (bffHostEl)   bffHostEl.value   = this.bffHost;
        if (bffPortEl)   bffPortEl.value   = this.bffPort;
        if (scanHostEl)  scanHostEl.value  = this.scanHost;
        if (scanPortsEl) scanPortsEl.value = this.scanPorts;

        const darkToggle  = document.getElementById('dark-mode-toggle');
        const autoToggle  = document.getElementById('auto-refresh-toggle');
        if (darkToggle)  darkToggle.checked  = localStorage.getItem('darkMode')    !== 'false';
        if (autoToggle)  autoToggle.checked  = localStorage.getItem('autoRefresh') !== 'false';
    }

    saveSettings() {
        if (!this.updateBffConfigFromSettingsInputs(true)) return;
        if (!this.updateScanConfigFromSettingsInputs(true)) return;
        this.addDiagnosticMessage('Settings saved.', 'success');
        this.checkBFFConnection();
    }

    updateBffConfigFromSettingsInputs(persist = false) {
        const host = (document.getElementById('bff-host')?.value || '').trim();
        const port = (document.getElementById('bff-port')?.value || '').trim();
        if (!host || !/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) {
            this.addDiagnosticMessage('Invalid BFF settings — provide a valid host and port (1–65535).', 'error');
            return false;
        }

        this.bffHost = host;
        this.bffPort = port;
        this.bffBaseUrl = `http://${this.bffHost}:${this.bffPort}`;

        if (persist) {
            localStorage.setItem('bffHost', this.bffHost);
            localStorage.setItem('bffPort', this.bffPort);
        }

        return true;
    }

    updateScanConfigFromSettingsInputs(persist = false) {
        const hostInput = document.getElementById('scan-host');
        const portsInput = document.getElementById('scan-ports');

        const host = hostInput ? hostInput.value.trim() : this.scanHost;
        const portsRaw = portsInput ? portsInput.value.trim() : this.scanPorts;
        const parsedPorts = this.parsePortList(portsRaw);

        if (!host || parsedPorts.length === 0) {
            this.addDiagnosticMessage('Invalid discovery settings. Provide a host and at least one valid port.', 'error');
            return false;
        }

        this.scanHost = host;
        this.scanPorts = parsedPorts.join(',');

        if (persist) {
            localStorage.setItem('scanHost', this.scanHost);
            localStorage.setItem('scanPorts', this.scanPorts);
        }

        if (portsInput) {
            portsInput.value = this.scanPorts;
        }

        return true;
    }

    parsePortList(raw) {
        return [...new Set(
            (raw || '')
                .split(',')
                .map(v => Number(v.trim()))
                .filter(v => Number.isInteger(v) && v >= 1 && v <= 65535)
        )];
    }

    toggleDarkMode() {
        const enabled = document.getElementById('dark-mode-toggle').checked;
        localStorage.setItem('darkMode', enabled);
        // Dark mode is default in CSS, light mode would require additional CSS
    }

    toggleAutoRefresh(e) {
        localStorage.setItem('autoRefresh', e.target.checked);

        if (e.target.checked) {
            this.startAutoRefresh();
        } else {
            this.stopAutoRefresh();
        }
    }

    startAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
        }

        this.autoRefreshInterval = setInterval(() => {
            const activePage = document.querySelector('.page.active').id;
            if (activePage === 'page-dashboard') {
                this.refreshDashboard();
            }
        }, 5000); // Refresh every 5 seconds
    }

    stopAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            this.autoRefreshInterval = null;
        }
    }
}

// Initialize application
let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new RTIDemoApp();
    console.log('RTI Demo UI initialized');
});
