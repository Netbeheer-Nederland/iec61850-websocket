import React, { useState, useEffect, useCallback, useRef } from 'react';

// Max time to wait for the BFF /api/health probe before giving up.
const HEALTH_TIMEOUT_MS = 4000;

const isValidPort = (port) => {
  const n = Number(port);
  return Number.isInteger(n) && n >= 1 && n <= 65535;
};

function Settings({ settings, setSettings }) {
  const [localSettings, setLocalSettings] = useState({ ...settings });
  const [refreshSettings, setRefreshSettings] = useState({
    connectionStatusPeriod: '10000',
    autoRefreshToggle: '5000'
  });
  const [bffConnectionStatus, setBffConnectionStatus] = useState({
    connected: false,
    text: 'Not checked',
    color: 'var(--text-muted)'
  });
  // Tracks the last settings prop content we synced from, so a parent
  // re-render that passes a new-but-equal object doesn't stomp on typing.
  const syncedSettingsRef = useRef(JSON.stringify(settings));
  const didMountRef = useRef(false);

  // Load persisted refresh settings once on mount (they were saved but never
  // restored before).
  useEffect(() => {
    const saved = localStorage.getItem('rti-hmi-refresh-settings');
    if (saved) {
      try {
        setRefreshSettings(prev => ({ ...prev, ...JSON.parse(saved) }));
      } catch (e) {
        console.warn(`Failed to parse rti-hmi-refresh-settings: ${e.message}`);
      }
    }
  }, []);

  // Sync local edits from the settings prop only when it actually changes, so a
  // parent re-render passing a new-but-equal object doesn't stomp on typing.
  useEffect(() => {
    const settingsStr = JSON.stringify(settings);
    if (!didMountRef.current) {
      didMountRef.current = true;
      return;
    }
    if (settingsStr !== syncedSettingsRef.current) {
      syncedSettingsRef.current = settingsStr;
      setLocalSettings({ ...settings });
    }
  }, [settings]);

  const checkBffConnection = useCallback(async (
    host = localSettings.bffHost,
    port = localSettings.bffPort,
    externalSignal
  ) => {
    if (!host || !isValidPort(port)) {
      setBffConnectionStatus({
        connected: false,
        text: 'Invalid host or port',
        color: 'var(--danger-color)'
      });
      return false;
    }
    if (externalSignal?.aborted) {
      return false;
    }

    setBffConnectionStatus({
      connected: false,
      text: 'Checking…',
      color: 'var(--text-muted)'
    });

    // Bound the request: an unreachable host otherwise hangs the fetch for the
    // browser's default connect timeout (tens of seconds), which made Save and
    // the live check feel frozen.
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; controller.abort(); }, HEALTH_TIMEOUT_MS);
    const onExternalAbort = () => controller.abort();
    externalSignal?.addEventListener('abort', onExternalAbort, { once: true });

    try {
      const response = await fetch(`http://${host}:${port}/api/health`, { signal: controller.signal });
      if (response.ok) {
        setBffConnectionStatus({
          connected: true,
          text: 'Connected',
          color: 'var(--success-color)'
        });
        return true;
      }
      setBffConnectionStatus({
        connected: false,
        text: 'Disconnected',
        color: 'var(--danger-color)'
      });
      return false;
    } catch (error) {
      // Superseded by a newer check (deps changed / component unmounted) —
      // leave the status for that check to set.
      if (externalSignal?.aborted && !timedOut) {
        return false;
      }
      setBffConnectionStatus({
        connected: false,
        text: timedOut ? 'Connection timed out' : 'Connection failed',
        color: 'var(--danger-color)'
      });
      return false;
    } finally {
      clearTimeout(timer);
      externalSignal?.removeEventListener('abort', onExternalAbort);
    }
  }, [localSettings.bffHost, localSettings.bffPort]);

  // Re-check on mount and (debounced) whenever host/port change, so the status
  // reflects saved settings after a reload and live edits while typing. The
  // controller aborts an in-flight check when the inputs change again.
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      checkBffConnection(undefined, undefined, controller.signal);
    }, 400);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [checkBffConnection]);

  const handleSaveSettings = () => {
    if (!localSettings.bffHost || !isValidPort(localSettings.bffPort)) {
      alert('Please enter a valid host and a port between 1 and 65535.');
      return;
    }

    const normalized = { ...localSettings, bffPort: Number(localSettings.bffPort) };
    const normalizedStr = JSON.stringify(normalized);

    // Persist synchronously so consumers that read localStorage
    // (apiService.getBffBaseUrl) pick up the new value immediately, not on the
    // next render tick.
    localStorage.setItem('rti-hmi-settings', normalizedStr);
    localStorage.setItem('rti-hmi-refresh-settings', JSON.stringify(refreshSettings));

    syncedSettingsRef.current = normalizedStr;
    setLocalSettings(normalized);
    setSettings(normalized);

    // Fire the connection test without blocking the save; the status indicator
    // updates when it resolves (or times out after HEALTH_TIMEOUT_MS).
    checkBffConnection(normalized.bffHost, normalized.bffPort);
  };

  const handleInputChange = (e) => {
    const { id, value } = e.target;
    const keyMap = { 'bff-host': 'bffHost', 'bff-port': 'bffPort' };
    const key = keyMap[id] || id;
    // Keep the raw input string while editing; it is validated and coerced to a
    // number on save. parseInt() here turned a cleared field into NaN, which was
    // then persisted as null.
    setLocalSettings(prev => ({ ...prev, [key]: value }));
  };

  const handleRefreshInputChange = (e) => {
    const { id, value } = e.target;
    setRefreshSettings(prev => ({
      ...prev,
      [id]: value
    }));
  };

  return (
    <section className="page">
      <div className="page-header">
        <h1>Settings</h1>
      </div>
      <div className="settings-section">
        <div className="settings-group">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h3>BFF Server Configuration</h3>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ color: bffConnectionStatus.color, fontWeight: '600' }}>
                {bffConnectionStatus.text}
              </span>
              <span
                className="bff-status-dot"
                style={{
                  background: bffConnectionStatus.connected ? 'var(--success-color)' : 'var(--danger-color)'
                }}
              ></span>
            </div>
          </div>

          <div className="setting-item" style={{ display: 'block' }}>
            <label htmlFor="bff-host">BFF Server Host</label>
            <input
              type="text"
              id="bff-host"
              value={localSettings.bffHost}
              onChange={handleInputChange}
              style={{ width: '100%', maxWidth: '300px' }}
            />
          </div>
          <div className="setting-item" style={{ display: 'block' }}>
            <label htmlFor="bff-port">BFF Server Port</label>
            <input
              type="number"
              id="bff-port"
              value={localSettings.bffPort}
              onChange={handleInputChange}
              style={{ width: '100%', maxWidth: '300px' }}
            />
          </div>

          <div style={{ marginTop: '24px', paddingTop: '24px', borderTop: '1px solid var(--border-color)' }}>
            <h4 style={{ marginBottom: '16px', color: 'var(--text-primary)' }}>Connection Refresh Time</h4>
            <div className="setting-item" style={{ display: 'block' }}>
              <label htmlFor="connection-status-period">Refresh Period in ms</label>
              <input
                type="text"
                id="connection-status-period"
                value={refreshSettings.connectionStatusPeriod}
                onChange={handleRefreshInputChange}
                style={{ width: '100%', maxWidth: '300px' }}
              />
            </div>
            <div className="setting-item" style={{ display: 'block' }}>
              <label htmlFor="auto-refresh-toggle">Connection Cards Refresh Period in ms</label>
              <input
                type="text"
                id="auto-refresh-toggle"
                value={refreshSettings.autoRefreshToggle}
                onChange={handleRefreshInputChange}
                style={{ width: '100%', maxWidth: '300px' }}
              />
            </div>
          </div>

          <button className="btn-primary" id="btn-save-settings" onClick={handleSaveSettings}>
            <i className="fas fa-save"></i>
            Save Settings and Test BFF Connection
          </button>
        </div>

        <div className="settings-group" style={{ display: 'none' }}>
          <h3>Display Settings</h3>
          <div className="setting-item" style={{ display: 'flex', alignItems: 'center' }}>
            <label>
              <input type="checkbox" id="dark-mode-toggle" defaultChecked />
              Dark Mode
            </label>
          </div>
        </div>
      </div>
    </section>
  );
}

export default Settings;