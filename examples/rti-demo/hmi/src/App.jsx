import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Header from './components/Header';
import Connections from './pages/Connections';
import Model from './pages/Model';
import Traffic from './pages/Traffic';
import Data from './pages/Data';
import Reports from './pages/Reports';
import Diagnostics from './pages/Diagnostics';
import Tools from './pages/Tools';
import Monitoring from './pages/Monitoring';
import Settings from './pages/Settings';
import Setup from './pages/Setup';
import ACSIClient from './pages/ACSIClient';
import ACSIServer from './pages/ACSIServer';

function App() {
  const [bffStatus, setBffStatus] = useState({
    connected: false,
    text: 'BFF disconnected'
  });
  const [endpoints, setEndpoints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connections, setConnections] = useState([]);
  const [models, setModels] = useState({});
  const [settings, setSettings] = useState({
    bffHost: 'localhost',
    bffPort: '5000'
  });

  // Models state: stores endpoint -> model mapping
  // updateModel: add/update a model for an endpoint
  const updateModel = useCallback((endpointId, modelData) => {
    setModels(prev => ({
      ...prev,
      [endpointId]: {
        data: modelData,
        timestamp: Date.now()
      }
    }));
  }, []);

  // getModel: retrieve a model by endpoint ID
  const getModel = useCallback((endpointId) => {
    return models[endpointId]?.data;
  }, [models]);

  // Load settings from localStorage
  useEffect(() => {
    const savedSettings = localStorage.getItem('rti-hmi-settings');
    if (savedSettings) {
      setSettings(JSON.parse(savedSettings));
    }
    const savedConnections = localStorage.getItem('rti-hmi-connections');
    if (savedConnections) {
      setConnections(JSON.parse(savedConnections));
    }
  }, []);

  // Save settings to localStorage
  useEffect(() => {
    localStorage.setItem('rti-hmi-settings', JSON.stringify(settings));
  }, [settings]);

  // Save connections to localStorage
  useEffect(() => {
    localStorage.setItem('rti-hmi-connections', JSON.stringify(connections));
  }, [connections]);

  // Function to fetch endpoints (memoized with useCallback)
  const fetchEndpoints = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/endpoints`);
      if (response.ok) {
        const data = await response.json();
        setEndpoints(Array.isArray(data) ? data : []);
      } else {
        setEndpoints([]);
      }
    } catch (error) {
      console.error('Failed to fetch endpoints:', error);
      setEndpoints([]);
    } finally {
      setLoading(false);
    }
  }, [settings.bffHost, settings.bffPort]);

  // Poll endpoints - COMMENTED OUT to stop automatic polling
  // useEffect(() => {
  //   fetchEndpoints();
  //   const interval = setInterval(fetchEndpoints, 5000);
  //   return () => clearInterval(interval);
  // }, [fetchEndpoints]);

  // Poll BFF status - COMMENTED OUT to stop automatic polling
  // useEffect(() => {
  //   const checkBffStatus = async () => {
  //     try {
  //       const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/health`);
  //       if (response.ok) {
  //         setBffStatus({ connected: true, text: 'BFF connected' });
  //       } else {
  //         setBffStatus({ connected: false, text: 'BFF disconnected' });
  //       }
  //     } catch (error) {
  //       setBffStatus({ connected: false, text: 'BFF disconnected' });
  //     }
  //   };

  //   checkBffStatus();
  //   const interval = setInterval(checkBffStatus, 10000);
  //   return () => clearInterval(interval);
  // }, [settings.bffHost, settings.bffPort]);

  return (
    <Router>
      <div className="container">
        <Sidebar />
        <main className="main-content">
          <Header bffStatus={bffStatus} />
          <Routes>
            <Route path="/" element={<Setup settings={settings} />} />
            <Route path="/setup" element={<Setup settings={settings} />} />
            <Route path="/connections" element={<Connections connections={connections} setConnections={setConnections} />} />
            <Route path="/model" element={<Model settings={settings} connections={connections} updateModel={updateModel} getModel={getModel} />} />
            <Route path="/traffic" element={<Traffic settings={settings} connections={connections} getModel={getModel} />} />
            <Route path="/data" element={<Data />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/diagnostics" element={<Diagnostics />} />
            <Route path="/tools" element={<Tools />} />
            <Route path="/monitoring" element={<Monitoring />} />
            <Route path="/settings" element={<Settings settings={settings} setSettings={setSettings} />} />
            <Route path="/acsi-client" element={<ACSIClient settings={settings} connections={connections} updateModel={updateModel} getModel={getModel} />} />
            <Route path="/acsi-server" element={<ACSIServer settings={settings} connections={connections} updateModel={updateModel} getModel={getModel} />} />
            <Route path="*" element={<Navigate to="/setup" replace />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
