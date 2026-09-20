/*
 * SPDX-FileCopyrightText: 2025 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 *
 * Copyright 2025 Netbeheer Nederland
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import React, {useState, useEffect, useCallback, useReducer, useRef} from 'react';
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
import Settings from './pages/Settings';
import Setup from './pages/Setup';
import ACSIClient from './pages/ACSIClient';
import ACSIServer from './pages/ACSIServer';
import { executeApiCall, buildTargetValue } from './services/apiService';

function App() {
  const [bffStatus, setBffStatus] = useState({
    connected: false,
    text: 'BFF disconnected'
  });
  const [endpoints, setEndpoints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [connections, setConnections] = useState([]);
  const [connectionsLoading, setConnectionsLoading] = useState(true);
  const [models, setModels] = useState({});
  const [settings, setSettings] = useState({
    bffHost: 'localhost',
    bffPort: '5000'
  });

  const bffBaseUrl = `http://${settings.bffHost}:${settings.bffPort}`;

  const updateModel = useCallback((endpointId, modelData) => {
    setModels(prev => ({
      ...prev,
      [endpointId]: {
        data: modelData,
        timestamp: Date.now()
      }
    }));
  }, []);

  const getModel = useCallback((endpointId) => {
    return models[endpointId]?.data;
  }, [models]);

  const parsePythonDictString = useCallback((pythonStr) => {
    if (!pythonStr || typeof pythonStr !== 'string') return null;
    try {
      const jsonStr = pythonStr
        .replace(/'/g, '"')
        .replace(/True/g, 'true')
        .replace(/False/g, 'false')
        .replace(/None/g, 'null');
      return JSON.parse(jsonStr);
    } catch (e) {
      return null;
    }
  }, []);

  const enrichFspClientCounts = useCallback(async (connectionsList) => {
    const bffTarget = buildTargetValue(settings.bffHost, settings.bffPort);
    const fspConns = connectionsList.filter(c => c.type === 'RTI-FSP' && c.status === 'connected');

    const results = await Promise.allSettled(
      fspConns.map(async (conn) => {
        const target = buildTargetValue(conn.host, conn.port);
        if (!target || target === bffTarget) return { name: conn.name, count: 0 };
        const result = await executeApiCall('status', target, null);
        const rawStatus = result?.payload?.result?.status;
        const parsed = typeof rawStatus === 'string' ? parsePythonDictString(rawStatus) : rawStatus;
        const isListening = parsed?.status === 'listening';
        const count = isListening ? (parsed?.connectedClients ?? 0) : 0;

        return { name: conn.name, count };
      })
    );

    const countMap = {};
    results.forEach(r => {
      if (r.status === 'fulfilled') countMap[r.value.name] = r.value.count;
    });

    return connectionsList.map(c =>
      c.type === 'RTI-FSP' ? { ...c, connectedClients: countMap[c.name] ?? 0 } : c
    );
  }, [settings.bffHost, settings.bffPort, parsePythonDictString]);

  const connectionsRef = useRef([]);
  const isFetchingRef = useRef(false);

  const fetchConnections = useCallback(async ({ background = false} = {}) => {
    if (isFetchingRef.current) return connectionsRef.current;
    isFetchingRef.current = true;
    try {
      if (!background) setConnectionsLoading(true);
      const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/connections`);
      if (response.ok) {
        const data = await response.json();
        const rawConnections = data.connections || [];
        const enriched = await enrichFspClientCounts(rawConnections);

        const changed = JSON.stringify(enriched) !== JSON.stringify(connectionsRef.current);
        if (changed) {
          connectionsRef.current = enriched;
          setConnections(enriched);
        }
        return enriched;
      }
      return connectionsRef.current;
    } catch (error) {
      console.error('Failed to fetch connections:', error);
      return connectionsRef.current;
    } finally {
      if (!background) setConnectionsLoading(false);
      isFetchingRef.current = false;
    }
  }, [settings.bffHost, settings.bffPort, enrichFspClientCounts]);

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  useEffect(() => {
    const interval = setInterval(() => {
      fetchConnections({ background: true});
    }, 1000);
    return () => clearInterval(interval);
  }, [fetchConnections]);

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

  useEffect(() => {
    localStorage.setItem('rti-hmi-settings', JSON.stringify(settings));
  }, [settings]);

  useEffect(() => {
    localStorage.setItem('rti-hmi-connections', JSON.stringify(connections));
  }, [connections]);

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

  return (
    <Router>
      <div className="container">
        <Sidebar />
        <main className="main-content">
          <Header bffStatus={bffStatus} />
          <Routes>
            <Route path="/" element={<Setup settings={settings} />} />
            <Route path="/setup" element={<Setup settings={settings} connections={connections} loading={connectionsLoading} onReload={fetchConnections}/>} />
            <Route path="/connections" element={<Connections connections={connections} setConnections={setConnections} />} />
            <Route path="/model" element={<Model settings={settings} connections={connections} loading={connectionsLoading} onReload={fetchConnections} updateModel={updateModel} getModel={getModel} />} />
            <Route path="/traffic" element={<Traffic settings={settings} connections={connections} loading={connectionsLoading} onReload={fetchConnections} updateModel={updateModel} getModel={getModel} />} />
            <Route path="/data" element={<Data />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/diagnostics" element={<Diagnostics />} />
            <Route path="/tools" element={<Tools />} />
            <Route path="/settings" element={<Settings settings={settings} setSettings={setSettings} />} />
            <Route path="/acsi-client" element={<ACSIClient settings={settings} bffBaseUrl={bffBaseUrl} connections={connections} updateModel={updateModel} getModel={getModel} />} />
            <Route path="/acsi-server" element={<ACSIServer settings={settings} bffBaseUrl={bffBaseUrl} connections={connections} updateModel={updateModel} getModel={getModel} />} />
            <Route path="*" element={<Navigate to="/setup" replace />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
