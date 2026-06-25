/* ==============================================
   ACSI Client - IEC 61850 Client Page
   ============================================== */

(function initACSIClientPage() {
    // ==================== API Definitions ====================
    const apiDefinitions = [
        { id: 'connect', label: 'POST /api/connect', method: 'POST', path: '/api/connect' },
        { id: 'disconnect', label: 'POST /api/disconnect', method: 'POST', path: '/api/disconnect' },
        { id: 'model-tree', label: 'GET /api/model/tree', method: 'POST', path: '/api/model/tree' },
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
            requestUrl.searchParams.set('soTarget', targetValue);
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
                method: selected.method,
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

            if (selected.method === 'POST') {
                options.body = JSON.stringify(payload);
            }

            //let payloadToSend = bodyOverride || {};

            //if (selected.method === 'POST') {
            //    if (targetValue && typeof payloadToSend === 'object' && !Array.isArray(payloadToSend)) {
            //        payloadToSend.soTarget = targetValue;
            //    }
            //    options.body = JSON.stringify(payloadToSend);
            //}

            try {
                await ensureBffHealthy();

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
                    payload: selected.method === 'POST' ? parsedPayload : null,
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

    // ==================== Event Handlers ====================
    function setupEventListeners(rootElement, endpoint) {
        const connectBtn = rootElement.querySelector('#acsi-client-connect-page-btn');
        const disconnectBtn = rootElement.querySelector('#acsi-client-disconnect-page-btn');
        const fetchModelBtn = rootElement.querySelector('#acsi-client-fetch-model-btn');

        if (connectBtn) {
            connectBtn.addEventListener('click', () => handleConnect(rootElement, endpoint));
        }

        if (disconnectBtn) {
            disconnectBtn.addEventListener('click', () => handleDisconnect(rootElement, endpoint));
        }

        if (fetchModelBtn) {
            fetchModelBtn.addEventListener('click', () => handleFetchModel(rootElement, endpoint));
        }
    }

    async function handleConnect(rootElement, endpoint) {
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
        const targetValue = buildTargetValue(endpoint.host, endpoint.port);
        const result = await executeApiCall(
            getApiById('connect'),
            targetValue,
            { host, port, cp }
        );

        if (result && result.ok) {
            showStatus(rootElement, `Connected to ${host}:${port}`, 'success');
            rootElement.querySelector('#acsi-client-connect-page-btn').disabled = true;
            rootElement.querySelector('#acsi-client-disconnect-page-btn').disabled = false;
            rootElement.querySelector('#acsi-client-fetch-model-btn').disabled = false;
        } else {
            const error = result?.payload?.error || result?.rawText || 'Unknown error';
            showStatus(rootElement, `Connection failed: ${error}`, 'error');
        }
    }

    async function handleDisconnect(rootElement, endpoint) {
        const host = rootElement.querySelector('#acsi-client-host-page').value.trim();
        const port = parseInt(rootElement.querySelector('#acsi-client-port-page').value.trim());
        const cp = rootElement.querySelector('#acsi-client-cp-page').value.trim() || 'cp1';

        showStatus(rootElement, 'Disconnecting...', 'info');
        const targetValue = buildTargetValue(endpoint.host, endpoint.port);
        const result = await executeApiCall(
            getApiById('disconnect'),
            targetValue,
            { host, port, cp }
        );

        if (result && result.ok) {
            showStatus(rootElement, 'Disconnected', 'info');
            rootElement.querySelector('#acsi-client-connect-page-btn').disabled = false;
            rootElement.querySelector('#acsi-client-disconnect-page-btn').disabled = true;
            rootElement.querySelector('#acsi-client-fetch-model-btn').disabled = true;
            rootElement.querySelector('#acsi-client-tree-container-page').style.display = 'none';
        } else {
            const error = result?.payload?.error || result?.rawText || 'Unknown error';
            showStatus(rootElement, `Disconnect failed: ${error}`, 'error');
        }
    }

    async function handleFetchModel(rootElement, endpoint) {
        const host = rootElement.querySelector('#acsi-client-host-page').value.trim();
        const port = rootElement.querySelector('#acsi-client-port-page').value.trim();
        const targetValue = buildTargetValue(endpoint.host, endpoint.port);

        showStatus(rootElement, 'Fetching model...', 'info');
        const result = await executeApiCall(
            getApiById('model-tree'),
            targetValue,
            null
        );

        if (result && result.ok) {
            const treeContainer = rootElement.querySelector('#acsi-client-tree-container-page');
            const treeContent = rootElement.querySelector('#acsi-client-tree-content');
            renderLiveModelTree(result.payload || {}, treeContent, (node) => {});
            //treeContent.innerHTML = `<pre>${JSON.stringify(result.payload || {}, null, 2)}</pre>`;
            treeContainer.style.display = 'block';
            showStatus(rootElement, 'Model fetched successfully', 'success');
        }
         else {
            const error = result?.payload?.error || result?.rawText || 'Failed to fetch model';
            showStatus(rootElement, error, 'error');
        }
    }

    // ==================== Render Function ====================
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
            onNodeClick({ ref: ref, fc: fc, nodeType: nodeType });
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

                  var subDas = (da && (da.sub_attributes || da.subDataAttributes || da.sda)) || [];
                  if (subDas.length > 0) {
                    var sdaUl = document.createElement('ul');
                    sdaUl.className = 'scl-tree-list';
                    subDas.forEach(function (sda) {
                      var sdaName = (typeof sda === 'object' ? sda.name : sda) || 'SDA';
                      var sdaRef  = daRef + '.' + sdaName;
                      var sdaLi   = createTreeNode('SDA', sdaName);
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
          lnUl.appendChild(lnLi);
        });

        ldLi.appendChild(lnUl);
        root.appendChild(ldLi);
      });

      container.appendChild(root);
      setupCollapsibleTree(container);

      window.SCLTree = {
        buildSclTreeFromText,
        renderSclTree,
        loadSclFileAndRender
      };
    }

    function render(rootElement, selectedEndpoint) {
        if (!rootElement) return;

        const endpoint = selectedEndpoint || {};
        const host = escapeHtml(endpoint.host || '');
        const port = escapeHtml(endpoint.port || '');
        const name = escapeHtml(endpoint.name || '');

        const defaultWsIP = "0.0.0.0";
        const defaultWsPort = "8765"

        rootElement.innerHTML = `
            <div class="page-header">
                <div style="display:flex; align-items:center; gap:16px;">
                    <h1><i class="fas fa-microchip" style="margin-right:10px; color:var(--primary-light);"></i>ACSI Client</h1>
                    <span class="acsi-endpoint-badge" style="display:inline-block; padding:4px 12px; background:var(--info-color); color:white; border-radius:4px; font-size:12px;">
                        ${name} · ${host}:${port}
                    </span>
                </div>
            </div>

            <div style="margin-top:24px;">
                <h2>Connection Settings</h2>
                <div style="display:flex; gap:16px; margin-top:16px;">
                    <div class="form-group">
                        <label for="acsi-client-host-page">Host</label>
                        <input type="text" id="acsi-client-host-page" value="${defaultWsIP}" placeholder="127.0.0.1">
                    </div>

                    <div class="form-group">
                        <label for="acsi-client-port-page">Port</label>
                        <input type="number" id="acsi-client-port-page" value="${defaultWsPort}" placeholder="102">
                    </div>

                    <div class="form-group">
                        <label for="acsi-client-cp-page">Connection Point (CP)</label>
                        <input type="text" id="acsi-client-cp-page" value="cp1" placeholder="cp1">
                    </div>
                </div>

                <div style="margin-top:24px; display:flex; gap:12px;">
                    <button id="acsi-client-connect-page-btn" class="btn-primary" style="padding:10px 20px;">
                        <i class="fas fa-plug" style="margin-right:8px;"></i>
                        Connect
                    </button>
                    <button id="acsi-client-disconnect-page-btn" class="btn-secondary" style="padding:10px 20px;">
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
                <button id="acsi-client-fetch-model-btn" class="btn-primary" style="margin-top:12px; padding:10px 20px;">
                    <i class="fas fa-download" style="margin-right:8px;"></i>
                    Fetch Model
                </button>
                <div id="acsi-client-tree-container-page" style="margin-top:16px; padding:16px; background:var(--bg-secondary); border-radius:8px; display:none;">
                    <div id="acsi-client-tree-content" style="max-height:600px; overflow-y:auto; color:var(--text-secondary);"></div>
                </div>
            </div>
        `;

        setupEventListeners(rootElement, endpoint);
    }

    window.ACSIClientPage = {
        render,
    };
})();