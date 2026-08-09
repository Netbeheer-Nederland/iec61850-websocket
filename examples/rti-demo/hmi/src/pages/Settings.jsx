import React, { useState, useEffect, useCallback } from 'react';

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

  useEffect(() => {
    setLocalSettings({ ...settings });
    // Check BFF connection on page load
    checkBffConnection();
  }, [settings]);

  const checkBffConnection = useCallback(async () => {
    try {
      const response = await fetch(`http://${localSettings.bffHost}:${localSettings.bffPort}/api/health`);
      if (response.ok) {
        setBffConnectionStatus({
          connected: true,
          text: 'Connected',
          color: 'var(--success-color)'
        });
        return true;
      } else {
        setBffConnectionStatus({
          connected: false,
          text: 'Disconnected',
          color: 'var(--danger-color)'
        });
        return false;
      }
    } catch (error) {
      setBffConnectionStatus({
        connected: false,
        text: 'Connection failed',
        color: 'var(--danger-color)'
      });
      return false;
    }
  }, [localSettings.bffHost, localSettings.bffPort]);

  const handleSaveSettings = async () => {
    // Save settings
    setSettings({ ...localSettings });
    
    // Save refresh settings to localStorage
    localStorage.setItem('rti-hmi-refresh-settings', JSON.stringify(refreshSettings));
    
    // Check BFF connection
    await checkBffConnection();
    
    alert('Settings saved and BFF connection checked!');
  };

  const handleInputChange = (e) => {
    const { id, value, type } = e.target;
    setLocalSettings(prev => ({
      ...prev,
      [id]: type === 'number' ? parseInt(value) : value
    }));
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
