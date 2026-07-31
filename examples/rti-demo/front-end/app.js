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

        this.getEndpoints = () => {
            return [...this.endpoints];
        };
        
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

        this.currentConnectionId = null;
        this.connectionStatusTimeout = null;
        this.monitoringPage = null;

    }

    init() {
        this.setupEventListeners();
        this.loadSettings();
        this.checkBFFConnection();
        this.startAutoRefresh();
        this.refreshDashboard(); 
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
        document.getElementById('btn-save-refresh-period').addEventListener('click', () => this.savePollingSettings());
        document.getElementById('dark-mode-toggle').addEventListener('change', () => this.toggleDarkMode());
        //document.getElementById('auto-refresh-toggle').addEventListener('change', (e) => this.toggleAutoRefresh(e));

        // Header
        document.getElementById('refresh-btn').addEventListener('click', () => this.handleManualRefresh());
        document.getElementById('refresh-endpoints-btn').addEventListener('click', () => this.discoverEndpoints());

        // Modal
        document.querySelector('.btn-close').addEventListener('click', () => this.closeConnectionModal());
        document.getElementById('btn-modal-close').addEventListener('click', () => this.closeConnectionModal());
        document.getElementById('btn-modal-save').addEventListener('click', () => this.saveConnection());

        // Connections Table
        document.getElementById('refresh-cons-btn').addEventListener('click', () => this.loadEndpoints());

        // Reports
        document.getElementById('btn-export-reports').addEventListener('click', () => this.exportReports());
        document.getElementById('btn-clear-diagnostics').addEventListener('click', () => this.clearDiagnostics());

        // ACSI Client
        const acsiConnectBtn = document.getElementById('acsi-connect-btn');
        if (acsiConnectBtn) {
            acsiConnectBtn.addEventListener('click', () => this.connectACSIClient());
        }

        // TLS Certificate file input
        const tlsCertInput = document.getElementById('tls-ca-cert');
        if (tlsCertInput) {
            tlsCertInput.addEventListener('change', (e) => this.handleFileInput(e, 'tls'));
        }

        // OAuth Certificate file input
        const oauthCertInput = document.getElementById('oauth-ca-cert');
        if (oauthCertInput) {
            oauthCertInput.addEventListener('change', (e) => this.handleFileInput(e, 'oauth'));
        }
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
        // Hide all modals
        document.querySelectorAll('.modal').forEach(modal => modal.classList.remove('active'));
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

         if (pageName !== 'connections') {
            this.stopConnectionStatusPolling();
        }

        // Load page-specific content
        this.loadPageContent(pageName);
    }

    // =============================================
    // Tools Page Logic
    // =============================================
    async  loadTools() {
        // Reset status/info fields
 
        const toolsPage = document.getElementById('page-tools');

        if (!toolsPage) {
            return;
        }

        try {
            const response = await fetch('./tools-page.html');
            const html = await response.text();

            toolsPage.innerHTML = html;

            // Initialize tools page AFTER HTML exists
            if (window.initializeToolsPage) {
                window.initializeToolsPage();
            }

        } catch (error) {
            console.error(error);

            toolsPage.innerHTML = `
                <div style="padding:20px;color:red;">
                    Failed to load tools page
                </div>
            `;
        }

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

    async executeApiCall(api, targetValue, bodyOverride = {}) {
        // Execute an API call through the BFF /api/execute endpoint
        try {
            const url = `${this.bffBaseUrl}/api/execute`;
            
            const payload = {
                target: targetValue,
                method: api.method || 'GET',
                path: api.path || '/'
            };
            
            if (bodyOverride && Object.keys(bodyOverride).length > 0) {
                payload.body = bodyOverride;
            }
            
            const options = {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            };
            
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
                payload: parsedPayload
            };
        } catch (error) {
            console.error('API execution failed:', error);
            return {
                ok: false,
                status: 0,
                payload: null,
                error: error.message
            };
        }
    }

    formatPayloadForDisplay(payload) {
        if (!payload || typeof payload !== 'object') {
            return payload;
        }
        const formatted = JSON.parse(JSON.stringify(payload));
        
        // Parse any stringified Python dicts in the result
        if (formatted.result && typeof formatted.result === 'object') {
            if (formatted.result.status && typeof formatted.result.status === 'string') {
                formatted.result.status = this.parsePythonDictString(formatted.result.status);
            }
            if (formatted.result.message && typeof formatted.result.message === 'string') {
                formatted.result.message = this.parsePythonDictString(formatted.result.message);
            }
        }
        
        // Also check at top level
        if (formatted.status && typeof formatted.status === 'string') {
            formatted.status = this.parsePythonDictString(formatted.status);
        }
        
        return formatted;
    }

    parsePythonDictString(pythonStr) {
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

    loadMonitoring() {
        const root = document.getElementById('monitoring-page-root');
        if (root) {
            if (!this.monitoringPage) {
                if (window.MonitoringPage) {
                    this.monitoringPage = new window.MonitoringPage(this);
                }
            }
            if (this.monitoringPage && typeof this.monitoringPage.render === 'function') {
                this.monitoringPage.render(root);
            }
        }
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
            case 'monitoring':
                this.loadMonitoring();
                break;
            case 'acsi-server':
                this.loadAcsiServerPage();
                break;
            case 'acsi-client':
                this.loadAcsiClientPage();
                break;
            case 'acsi':
                this.loadACSI();
                break;
            case 'tls-oauth':
                this.loadTLSOAuthPage();
                break;
        }
    }

    async loadTLSOAuthPage() {
        const container = document.getElementById('tls-oauth-container');
        if (!container) return;

        // Show loading state
        container.innerHTML = '<div class="spinner"></div>';

        // Load connections
        const result = await this.callBFF('/api/connections');
        if (!result || !result.connections) {
            container.innerHTML = '<p style="color: var(--text-muted);">No connections found</p>';
            return;
        }

        this.renderTLSOAuthConnections(result.connections);
    }

    renderTLSOAuthConnections(connections) {
        const container = document.getElementById('tls-oauth-container');

        if (connections.length === 0) {
            container.innerHTML = '<p style="padding: 20px; color: var(--text-muted);">No connections configured</p>';
            return;
        }

        let html = `
            <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 20px;">
        `;

        connections.forEach(conn => {
            html += `
                <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px;">
                    <h3 style="margin-bottom: 15px; color: var(--text-primary);">${conn.name}</h3>
                    <div style="margin-bottom: 15px;">
                        <p style="margin: 5px 0; color: var(--text-muted);">
                            <strong>Host:</strong> ${conn.host}:${conn.port}
                        </p>
                        <p style="margin: 5px 0; color: var(--text-muted);">
                            <strong>Type:</strong> ${conn.type}
                        </p>
                        <p style="margin: 5px 0; color: var(--text-muted);">
                            <strong>WS Mode:</strong>
                            <span id="ws-mode-${conn.name}">${conn?.properties_info?.properties?.ws_mode ?? 'N/A'}</span>
                        </p>
                    </div>
                    <div style="display: flex; gap: 10px;">
                        <button class="btn-primary" style="flex: 1;"
                                onclick="app.openOAuthConfig('${conn.name}')">
                            <i class="fas fa-key"></i> OAuth Config
                        </button>
                        <button class="btn-secondary" style="flex: 1;"
                                onclick="app.openTLSConfig('${conn.name}')">
                            <i class="fas fa-shield-alt"></i> TLS Config
                        </button>
                    </div>
                </div>
            `;
        });

        html += `</div>`;
        container.innerHTML = html;
    }

    openOAuthConfig(connectionName) {
        const conn = this.connections.find(c => c.name === connectionName);
        if (!conn) return;

        this.selectedConnection = conn;
        this.showOAuthModal();
    }

    openTLSConfig(connectionName) {
        const conn = this.connections.find(c => c.name === connectionName);
        if (!conn) return;

        this.selectedConnection = conn;
        this.showTLSModal();
    }

    // =============================================
    // TLS/OAuth Modal Methods
    // =============================================

    // Show TLS Modal
    showTLSModal() {
        const modal = document.getElementById('modal-tls');
        const ws_mode = this.selectedConnection?.properties_info?.properties?.ws_mode || 'N/A';

        console.log("Modal before:", modal.className);
        if (modal && ws_mode !== 'N/A') {
            modal.classList.add('active');

            console.log("Modal after:", modal.className);


            let isServer = false;

            if (ws_mode === "passive" || ws_mode === "Passive")
                isServer = true;

            console.log(`showTLSModal: ws_mode=${ws_mode}, isServer=${isServer}`);

            const serverFields = document.getElementById('tls-server-fields');
            const clientFields = document.getElementById('tls-client-fields');
            serverFields.hidden = false;
            clientFields.hidden = false;

            if(isServer)
            {
                clientFields.hidden = true;
            }
            else
            {
                serverFields.hidden = true;
            }
        }
    }

    // Close TLS Modal
    closeTLSModal() {
        document.getElementById('modal-tls').classList.remove('active');
    }

    // Show OAuth Modal
    showOAuthModal() {
        const modal = document.getElementById('modal-oauth');
        if (modal) {
            modal.classList.add('active');
            // Reset form
            document.getElementById('oauth-enable').checked = false;
            document.getElementById('oauth-token-url').value = '';
            document.getElementById('oauth-client-id').value = '';
            document.getElementById('oauth-client-secret').value = '';
            document.getElementById('oauth-ca-cert').value = '';
            document.getElementById('oauth-cert-file-name').textContent = 'No file chosen';
            document.getElementById('oauth-cert-content').value = '';
            document.getElementById('oauth-enable-refresh').checked = false;
        }
    }

    // Close OAuth Modal
    closeOAuthModal() {
        document.getElementById('modal-oauth').classList.remove('active');
    }

    // Handle file input for both modals
    handleFileInput(event, type) {
        const file = event.target.files[0];
        if (!file) return;

        const fileNameSpan = document.getElementById(`${type}-cert-file-name`);
        const contentTextarea = document.getElementById(`${type}-cert-content`);

        if (fileNameSpan) {
            fileNameSpan.textContent = file.name;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            if (contentTextarea) {
                contentTextarea.value = e.target.result;
            }
        };
        reader.readAsText(file);
    }

    // Save TLS Config
    async saveTLSConfig() {
        const enableTLS = document.getElementById('tls-enable').checked;
        const certContent = document.getElementById('tls-cert-content').value;

        if (!this.selectedConnection) {
            this.addDiagnosticMessage('No connection selected', 'error');
            return;
        }

        const config = {
            connection_name: this.selectedConnection.name,
            enable_tls: enableTLS,
            ca_certificate: certContent
        };

        try {
            const result = await this.callBFF('/api/connections/tls-config', 'POST', config);
            if (result) {
                this.addDiagnosticMessage(`TLS config saved for ${this.selectedConnection.name}`, 'success');
                this.closeTLSModal();
            }
        } catch (error) {
            this.addDiagnosticMessage(`Failed to save TLS config: ${error.message}`, 'error');
        }
    }

    // Save OAuth Config
    async saveOAuthConfig() {
        const enableOAuth = document.getElementById('oauth-enable').checked;
        const tokenUrl = document.getElementById('oauth-token-url').value;
        const clientId = document.getElementById('oauth-client-id').value;
        const clientSecret = document.getElementById('oauth-client-secret').value;
        const certContent = document.getElementById('oauth-cert-content').value;
        const enableRefresh = document.getElementById('oauth-enable-refresh').checked;

        if (!this.selectedConnection) {
            this.addDiagnosticMessage('No connection selected', 'error');
            return;
        }

        if (enableOAuth && !tokenUrl) {
            alert('Token Endpoint URL is required when OAuth is enabled');
            return;
        }

        const config = {
            connection_name: this.selectedConnection.name,
            enable_oauth: enableOAuth,
            token_endpoint_url: tokenUrl,
            client_id: clientId,
            client_secret: clientSecret,
            ca_certificate: certContent,
            enable_token_refresh: enableRefresh
        };

        try {
            const result = await this.callBFF('/api/connections/oauth-config', 'POST', config);
            if (result) {
                this.addDiagnosticMessage(`OAuth config saved for ${this.selectedConnection.name}`, 'success');
                this.closeOAuthModal();
            }
        } catch (error) {
            this.addDiagnosticMessage(`Failed to save OAuth config: ${error.message}`, 'error');
        }
    }

    loadAcsiServerPage() {
        // Hide the connection modal explicitly
        const modal = document.getElementById('modal-connection');
        if (modal) modal.classList.remove('active');
        
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
        // Hide the connection modal explicitly
        const modal = document.getElementById('modal-connection');
        if (modal) modal.classList.remove('active');
        
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

    async loadScript(url) {
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
        const isConnected = !!(result && ((result.bff && result.bff.status)));
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
        // Fetch the latest endpoints from the BFF (which also renders them).
        // Previously this only re-rendered stale in-memory data, so on first
        // load the cards were empty until another code path called loadEndpoints.
        await this.loadEndpoints();
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
        //if (!this.updateScanConfigFromSettingsInputs(false)) {
        //    return;
        //}

        //const ports = this.parsePortList(this.scanPorts);
        //if (ports.length === 0) {
        //    this.addDiagnosticMessage('Discovery ports are required (for example: 5001,5002).', 'error');
        //    return;
        //}

        const connected = await this.checkBFFConnection();
        if (!connected) {
            this.addDiagnosticMessage('Discovery requires an active BFF connection (health check failed).', 'warning');
            return;
        }

        await this.loadEndpoints();
        //const result = await this.callBFF('/api/endpoints/discover-network', 'POST', {
        //    host: this.scanHost,
        //    ports,
        //});
        
        //if (result) {
        //    this.addDiagnosticMessage(
        //        `Discovery complete: Found ${result.count} endpoint(s)`,
        //        'success'
        //    );
            // Reload endpoints to show any newly discovered ones
        //    await this.loadEndpoints();
        //}
    }

    async loadEndpoints() {
        if (!this.isBffConnected) {
            this.addDiagnosticMessage('Skipping /api/endpoints: BFF is not connected.', 'warning');
            return;
        }

        // Only show the loading spinner on the very first load, when there is
        // nothing on screen yet. Background auto-refreshes should swap the data
        // in silently to avoid the cards flickering/disappearing every cycle.
        if (this.endpoints.length === 0) {
            this.showEndpointsLoading();
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
    showEndpointsLoading() {
        const container = document.getElementById('endpoints-container');
        if (!container) return;

        container.innerHTML = `
            <div class="endpoints-loading">
                <span class="spinner"></span>
                <span>Loading connections...</span>
            </div>
        `;
    }


    renderEndpoints() {
        const container = document.getElementById('endpoints-container');
        container.innerHTML = '';

        if (this.endpoints.length === 0) {
            container.innerHTML = `
                <div style="padding: 20px; text-align: center; color: var(--text-muted);">
                    <p>No endpoints configured or discovered</p>
                    <button class="btn-primary" id="btn-discover-now" style="margin-top: 10px;" hidden>
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
                    <!-- <span class="endpoint-card-status">${endpoint.status}</span> -->
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
        const endpointType = (endpoint.type || '').toLowerCase();

        if (acsiRole === 'acsi-server' || endpointType === 'rti-fsp') {
            this.selectedAcsiEndpoint = endpoint;
            this.navigateToPage('acsi-server');
            return;
        }
        if (acsiRole === 'acsi-client' || endpointType === 'rti-so') {
            this.selectedAcsiEndpoint = endpoint;
            this.navigateToPage('acsi-client');
            return;
        }

        // For any other ACSI-related endpoint, default to client page
        this.selectedAcsiEndpoint = endpoint;
        this.navigateToPage('acsi-client');
    }

    // =============================================
    // ACSI Page
    // =============================================
    // ========== POLLING FUNCTION ==========
    async refreshConnectionStatuses() {
        try {
            const result = await this.callBFF('/api/endpoints');
            if (!result?.endpoints) return;

            // Create a map: "host:port" -> status for fast lookup
            const statusMap = new Map();
            result.endpoints.forEach(ep => {
                statusMap.set(`${ep.host}:${ep.port}`, ep.status);
            });

            // Update statuses in our connections array
            let updated = false;
            this.connections.forEach(conn => {
                const key = `${conn.host}:${conn.port}`;
                const newStatus = statusMap.get(key);
                if (newStatus && newStatus !== conn.status) {
                    conn.status = newStatus;
                    //connField = document.getElementById(`status-button-${conn.name}`);
                    //if (connField)
                    //    connField.textContent = newStatus;
                    //updated = true;
                }
            });

            // Re-render table only if we're on the connections page and something changed
            if (updated && document.querySelector('.page.active')?.id === 'page-connections') {
                this.renderConnectionsTable();
            }
        } catch (error) {
            this.addDiagnosticMessage(`Status poll error: ${error.message}`, 'error');
        }
    }

    // ========== START/STOP POLLING ==========

    stopConnectionStatusPolling() {
        if (this.connectionStatusTimeout) {
            clearTimeout(this.connectionStatusTimeout);
            this.connectionStatusTimeout = null;
        }
    }

    startConnectionStatusPolling() {
        this.stopConnectionStatusPolling();

        const poll_time = Number(document.getElementById("connection-status-period").value);
        const poll = async () => {
            // Only poll if we're actually viewing connections
            if (document.querySelector('.page.active')?.id !== 'page-connections') {
                this.connectionStatusTimeout = setTimeout(poll, poll_time);
                return;
            }

            await this.refreshConnectionStatuses();
            this.connectionStatusTimeout = setTimeout(poll, poll_time);
        };

        poll();
    }



    showConnectionsLoading() {
        const tbody = document.getElementById('connections-container');

        tbody.innerHTML = `
            <tr>
                <td colspan="5" style="text-align:center;">
                    <span class="spinner"></span>
                    Loading connections...
                </td>
            </tr>
        `;
    }

    async loadConnections() {
        this.showConnectionsLoading();
        const result = await this.callBFF('/api/connections');
        
        if (!result) {
            this.addDiagnosticMessage('Failed to load connections', 'error');
            return;
        }

        this.connections = result.connections || [];
        this.renderConnectionsTable();
        this.startConnectionStatusPolling(); // Start polling
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

            const statusColor =
                conn.status === 'connected'
                    ? 'var(--success-color)'
                    : conn.status === 'disconnected'
                        ? 'var(--danger-color)'
                        : '#eab308';

            const statusText = 'Live' || '⏳ checking...';
            html += `
                <tr>
                    <td>${conn.name}</td>
                    <td>${conn.type}</td>
                    <td>${conn.host}</td>
                    <td>${conn.port}</td>
                    <td>
                        <span id='status-button-${conn.name}' style="display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 11px; font-weight: 600; background: ${statusColor}; color: white;">
                            ${statusText}
                        </span>
                    </td>
                    <td>
                        <button class="btn-primary" style="padding: 6px 12px; font-size: 12px;" onclick='app.editConnection(${JSON.stringify(conn.name)})'>
                            Edit
                        </button>
                        <button class="btn-secondary" style="padding: 6px 12px; font-size: 12px;" onclick='app.deleteConnection(${JSON.stringify(conn.name)})'>
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
        this.currentConnectionId = null;  // ← Mark as NEW
        document.getElementById('conn-name').readOnly = false;

    }

    closeConnectionModal() {
        document.getElementById('modal-connection').classList.remove('active');
    }

    async saveConnection() {
        const isEdit = this.currentConnectionId !== null;
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

        if(!isEdit && this.connections.map(c => c.name).includes(connection.name)) {
            alert('Connection name must be unique');
            return;
        }

        const result = await this.callBFF('/api/connections', 'POST', connection);

        if (result) {

            this.closeConnectionModal();
            this.loadConnections();
            this.addDiagnosticMessage(`Connection '${connection.name}' saved`, 'success');
            this.renderConnectionsTable();
            // Re-fetch endpoints from the BFF so the dashboard cards reflect the
            // edit immediately, instead of re-rendering stale in-memory data.
            await this.loadEndpoints();
        }
    }

    async deleteConnection(name) {
        if (confirm('Are you sure?')) {
            const result = await this.callBFF(`/api/connections/${name}`, 'DELETE');
            if (result) {
                this.loadConnections();
                this.addDiagnosticMessage('Connection deleted', 'success');
                this.loadEndpoints();
            }
        }
    }

    async editConnection(name) {
        const conn = this.connections.find(c => c.name === name);
        if (conn) {
            document.getElementById('conn-name').value = conn.name;
            document.getElementById('conn-name').readOnly = true;
            document.getElementById('conn-host').value = conn.host;
            document.getElementById('conn-port').value = conn.port;
            document.getElementById('conn-type').value = conn.type;
            document.getElementById('modal-connection').classList.add('active');
            this.currentConnectionId = conn.id;

            const result = await this.callBFF(`/api/connections/${name}`, 'PUT', {
                name: conn.name,
                host: conn.host,
                port: conn.port,
                type: conn.type,
                status: conn.status
            });
            if (result) {
                this.loadConnections();
                this.addDiagnosticMessage('Connection deleted', 'success');
                this.loadEndpoints();
            }
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
    // Data Read/Write
    // =============================================

    async readData() {
        const objRef = document.getElementById('data-ref').value;
        
        if (!objRef) {
            alert('Please enter a data reference');
            return;
        }

        const result = await this.callBFF('/api/data/read', 'POST', { objRef });
        
        if (result) {
            const output = document.getElementById('data-output');
            output.textContent = JSON.stringify(result, null, 2);
            document.getElementById('data-value').value = result.value || '';
        }
    }

    async writeData() {
        const objRef = document.getElementById('data-ref').value;
        const value = document.getElementById('data-value').value;
        
        if (!objRef || !value) {
            alert('Please enter both reference and value');
            return;
        }

        const result = await this.callBFF('/api/data/write', 'POST', { objRef, value });
        
        if (result) {
            const output = document.getElementById('data-output');
            output.textContent = JSON.stringify(result, null, 2);
            this.addDiagnosticMessage(`Data written to ${objRef}`, 'success');
        }
    }

    // =============================================
    // Reports
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
        
        if (!reports || reports.length === 0) {
            container.innerHTML = '<p style="padding: 20px; color: var(--text-muted);">No reports available</p>';
            return;
        }

        let html = '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px;">';
        
        reports.forEach(report => {
            html += `
                <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 12px; padding: 16px;">
                    <h3 style="margin-bottom: 12px;">${report.name}</h3>
                    <p style="color: var(--text-muted); font-size: 12px; margin-bottom: 8px;">${report.timestamp}</p>
                    <p>${report.description}</p>
                </div>
            `;
        });
        
        html += '</div>';
        container.innerHTML = html;
    }

    async exportReports() {
        const result = await this.callBFF('/api/reports/export', 'POST');
        
        if (result && result.data) {
            const blob = new Blob([JSON.stringify(result.data, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `reports-${new Date().toISOString()}.json`;
            a.click();
            this.addDiagnosticMessage('Reports exported', 'success');
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

        let html = '<div style="max-height: 600px; overflow-y: auto;">';
        
        this.messageHistory.forEach(msg => {
            const iconClass = msg.type === 'success' ? 'check-circle' : msg.type === 'error' ? 'exclamation-circle' : 'info-circle';
            const color = msg.type === 'success' ? 'var(--success-color)' : msg.type === 'error' ? 'var(--danger-color)' : 'var(--info-color)';
            
            html += `
                <div style="padding: 12px; border-bottom: 1px solid var(--border-color); display: flex; gap: 12px;">
                    <i class="fas fa-${iconClass}" style="color: ${color}; width: 16px; flex-shrink: 0;"></i>
                    <div>
                        <div style="font-size: 12px; color: var(--text-muted);">${msg.timestamp}</div>
                        <div>${msg.message}</div>
                    </div>
                </div>
            `;
        });
        
        html += '</div>';
        container.innerHTML = html;
    }

    addDiagnosticMessage(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        this.messageHistory.unshift({ message, type, timestamp });
        
        // Keep only last 100 messages
        if (this.messageHistory.length > 100) {
            this.messageHistory.pop();
        }
    }

    async clearDiagnostics() {
        if (confirm('Clear all diagnostic messages?')) {
            this.messageHistory = [];
            this.renderDiagnostics();
            this.addDiagnosticMessage('Diagnostic messages cleared', 'success');
        }
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

    savePollingSettings(){
        this.startConnectionStatusPolling();
        this.toggleAutoRefresh();
    }

    updateBffConfigFromSettingsInputs(persist = false) {
        const host = (document.getElementById('bff-host')?.value || '').trim();
        const port = (document.getElementById('bff-port')?.value || '').trim();
        if (!host || !/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535) {
            this.addDiagnosticMessage('Invalid BFF settings — provide a valid host and port (1–65535).', 'error');
            return false;
        }
        this.bffHost   = host;
        this.bffPort   = port;
        this.bffBaseUrl = `http://${host}:${port}`;
        if (persist) { localStorage.setItem('bffHost', host); localStorage.setItem('bffPort', port); }
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

        this.stopAutoRefresh();
        this.startAutoRefresh();
    }

    startAutoRefresh() {
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
        }
        const poll_time = Number(document.getElementById("auto-refresh-toggle").value);

        this.autoRefreshInterval = setInterval(() => {
            const activePage = document.querySelector('.page.active').id;
            if (activePage === 'page-dashboard') {
                this.refreshDashboard();
            }
        }, poll_time);
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
    window.app = app;
    console.log('RTI Demo UI initialized');
});
