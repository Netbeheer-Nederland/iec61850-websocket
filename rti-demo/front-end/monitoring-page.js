/* ==============================================
   Monitoring Page - Messages Monitoring
   ============================================== */

class MonitoringPage {
    constructor(app) {
        this.app = app;
        this.monitorIntervals = {
            monitor1: null,
            monitor2: null
        };
        this.monitorStates = {
            monitor1: false,
            monitor2: false
        };
    }

    async render(root) {
        try {
            const response = await fetch('./monitoring-page.html', { cache: 'no-store' });
            if (response.ok) {
                const html = await response.text();
                root.innerHTML = html;
                this.initialize();
            } else {
                root.innerHTML = '<div style="padding:20px;color:red;">Failed to load monitoring page</div>';
            }
        } catch (error) {
            console.error('Failed to load monitoring page:', error);
            root.innerHTML = '<div style="padding:20px;color:red;">Failed to load monitoring page</div>';
        }
    }

    initialize() {
        this.populateEndpoints();
        this.initMonitorControls('monitor1');
        this.initMonitorControls('monitor2');
        this.initMessageCardDelegation();
    }

    initMessageCardDelegation() {
        // Use event delegation for message cards (since they're dynamically added)
        document.addEventListener('click', (e) => {
            const header = e.target.closest('.message-header');
            if (header) {
                this.toggleMessage(header);
            }
        });
    }

    populateEndpoints() {
        const endpoints = this.app.getEndpoints();
        
        const monitor1Endpoint = document.getElementById('monitor1-endpoint');
        const monitor2Endpoint = document.getElementById('monitor2-endpoint');
        
        const options = '<option value="">Select Endpoint</option>' +
            endpoints.map(ep => `<option value="${ep.host}:${ep.port}">${ep.name} (${ep.host}:${ep.port})</option>`).join('');
        
        if (monitor1Endpoint) {
            monitor1Endpoint.innerHTML = options;
        }
        
        if (monitor2Endpoint) {
            monitor2Endpoint.innerHTML = options;
        }
    }

    initMonitorControls(monitorId) {
        const startBtn = document.getElementById(`${monitorId}-start`);
        const pauseBtn = document.getElementById(`${monitorId}-pause`);
        const clearBtn = document.getElementById(`${monitorId}-clear`);
        const endpointSelect = document.getElementById(`${monitorId}-endpoint`);
        const intervalSelect = document.getElementById(`${monitorId}-interval`);
        const messagesDiv = document.getElementById(`${monitorId}-messages`);
        const statusDiv = document.getElementById(`${monitorId}-status`);
        
        if (startBtn) {
            startBtn.addEventListener('click', () => this.startMonitoring(monitorId));
        }
        
        if (pauseBtn) {
            pauseBtn.addEventListener('click', () => this.pauseMonitoring(monitorId));
        }
        
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearMessages(monitorId));
        }
        
        if (endpointSelect) {
            endpointSelect.addEventListener('change', () => this.updateStatus(monitorId));
        }
        
        // Initialize status
        this.updateStatus(monitorId);
    }

    startMonitoring(monitorId) {
        if (this.monitorStates[monitorId]) {
            return;
        }
        
        const endpointSelect = document.getElementById(`${monitorId}-endpoint`);
        const startBtn = document.getElementById(`${monitorId}-start`);
        const pauseBtn = document.getElementById(`${monitorId}-pause`);
        const statusDiv = document.getElementById(`${monitorId}-status`);
        const intervalSelect = document.getElementById(`${monitorId}-interval`);
        
        const endpoint = endpointSelect?.value;
        if (!endpoint) {
            if (statusDiv) statusDiv.textContent = 'Please select an endpoint first';
            return;
        }
        
        // Clear any existing interval
        this.stopMonitoring(monitorId);
        
        // Start monitoring
        this.monitorStates[monitorId] = true;
        if (startBtn) startBtn.disabled = true;
        if (pauseBtn) pauseBtn.disabled = false;
        if (statusDiv) statusDiv.textContent = `Monitoring ${endpoint}...`;
        
        // Start polling
        const interval = parseInt(intervalSelect?.value || 5000);
        this.monitorIntervals[monitorId] = setInterval(() => {
            this.fetchMessages(monitorId, endpoint);
        }, interval);
        
        // Fetch immediately
        this.fetchMessages(monitorId, endpoint);
    }

    pauseMonitoring(monitorId) {
        this.stopMonitoring(monitorId);
        
        const startBtn = document.getElementById(`${monitorId}-start`);
        const pauseBtn = document.getElementById(`${monitorId}-pause`);
        const statusDiv = document.getElementById(`${monitorId}-status`);
        const endpointSelect = document.getElementById(`${monitorId}-endpoint`);
        
        if (startBtn) startBtn.disabled = false;
        if (pauseBtn) pauseBtn.disabled = true;
        if (statusDiv) statusDiv.textContent = `Monitoring paused. Click Start to resume.`;
    }

    stopMonitoring(monitorId) {
        this.monitorStates[monitorId] = false;
        if (this.monitorIntervals[monitorId]) {
            clearInterval(this.monitorIntervals[monitorId]);
            this.monitorIntervals[monitorId] = null;
        }
    }

    async clearMessages(monitorId) {
        const messagesDiv = document.getElementById(`${monitorId}-messages`);
        const statusDiv = document.getElementById(`${monitorId}-status`);
        const endpointSelect = document.getElementById(`${monitorId}-endpoint`);
        
        const endpoint = endpointSelect?.value;
        if (!endpoint) {
            if (statusDiv) statusDiv.textContent = 'Please select an endpoint first';
            return;
        }
        
        // Clear local display
        if (messagesDiv) messagesDiv.innerHTML = '';
        if (statusDiv) statusDiv.textContent = 'Clearing messages...';
        
        try {
            // Call /api/messages/clear on the endpoint
            const api = { id: 'messages-clear', method: 'POST', path: '/api/messages/clear' };
            const result = await this.app.executeApiCall(api, endpoint, {});
            
            if (result && result.ok) {
                if (statusDiv) statusDiv.textContent = 'Messages cleared';
            } else {
                const message = result ? `HTTP ${result.status}` : 'Unknown error';
                if (statusDiv) statusDiv.textContent = `Error clearing messages: ${message}`;
            }
        } catch (error) {
            if (statusDiv) statusDiv.textContent = `Error: ${error.message}`;
            console.error(`Clear messages error:`, error);
        }
        
        setTimeout(() => {
            this.updateStatus(monitorId);
        }, 2000);
    }

    updateStatus(monitorId) {
        const endpointSelect = document.getElementById(`${monitorId}-endpoint`);
        const statusDiv = document.getElementById(`${monitorId}-status`);
        
        const endpoint = endpointSelect?.value;
        if (statusDiv) {
            if (endpoint) {
                statusDiv.textContent = this.monitorStates[monitorId] ? `Monitoring ${endpoint}...` : `Ready to monitor ${endpoint}`;
            } else {
                statusDiv.textContent = 'Select an endpoint and click Start';
            }
        }
    }

    async fetchMessages(monitorId, endpoint) {
        try {
            const api = { id: 'messages', method: 'GET', path: '/api/messages' };
            const result = await this.app.executeApiCall(api, endpoint, {});
            
            const messagesDiv = document.getElementById(`${monitorId}-messages`);
            const statusDiv = document.getElementById(`${monitorId}-status`);
            
            if (result && result.ok && result.payload) {
                // Extract messages array from result
                const messages = result.payload.result?.messages || [];
                
                if (messagesDiv) {
                    if (messages.length === 0) {
                        messagesDiv.innerHTML = '<div class="monitor-no-messages">No messages yet</div>';
                    } else {
                        messagesDiv.innerHTML = messages.map(msg => this.createMessageCard(msg)).join('');
                    }
                }
                
                if (statusDiv) {
                    statusDiv.textContent = `Last updated: ${new Date().toLocaleTimeString()} - ${endpoint} (${messages.length} messages)`;
                }
            } else {
                const message = result ? `HTTP ${result.status}` : 'Unknown error';
                if (statusDiv) {
                    statusDiv.textContent = `Error fetching messages: ${message}`;
                }
            }
        } catch (error) {
            const statusDiv = document.getElementById(`${monitorId}-status`);
            if (statusDiv) {
                statusDiv.textContent = `Error: ${error.message}`;
            }
            console.error(`Monitor ${monitorId} error:`, error);
        }
    }

    createMessageCard(message) {
        // Handle message.message - it might be a string or already parsed
        let msgObj;
        try {
            if (typeof message.message === 'string') {
                msgObj = JSON.parse(message.message);
            } else {
                msgObj = message.message;
            }
        } catch (e) {
            msgObj = message.message;
        }
        
        const msgJson = JSON.stringify(msgObj, null, 2).replace(/</g, '&lt;').replace(/>/g, '&gt;');
        
        return `
            <div class="message-card" data-id="${message.id}">
                <div class="message-header">
                    <div class="message-meta">
                        <span class="message-id">#${message.id}</span>
                        <span class="message-timestamp">${message.timestamp}</span>
                        <span class="message-direction ${message.direction}">${message.direction}</span>
                        <span class="message-category">${message.category}</span>
                        <span class="message-service">${message.service_type}</span>
                    </div>
                    <i class="fas fa-chevron-down message-toggle-icon"></i>
                </div>
                <div class="message-body" style="display: none;">
                    <div class="message-json">${msgJson}</div>
                </div>
            </div>
        `;
    }

    toggleMessage(header) {
        const card = header.closest('.message-card');
        const body = card.querySelector('.message-body');
        const icon = header.querySelector('.message-toggle-icon');
        
        if (body.style.display === 'none') {
            body.style.display = 'block';
            icon.classList.remove('fa-chevron-down');
            icon.classList.add('fa-chevron-up');
        } else {
            body.style.display = 'none';
            icon.classList.remove('fa-chevron-up');
            icon.classList.add('fa-chevron-down');
        }
    }

    cleanup() {
        // Stop all monitors when page is unloaded
        this.stopMonitoring('monitor1');
        this.stopMonitoring('monitor2');
    }
}

// Export for use by app.js
window.MonitoringPage = MonitoringPage;
