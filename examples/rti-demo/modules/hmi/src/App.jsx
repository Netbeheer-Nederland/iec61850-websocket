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
import Overview from './pages/Overview';
import ACSIClient from './pages/ACSIClient';
import ACSIServer from './pages/ACSIServer';
import { executeApiCall, buildTargetValue } from './services/apiService';
import { linkSoToFsps } from './utils/fspLinks';
import { connect as connectLiveSocket, reconnect as reconnectLiveSocket, subscribe as subscribeLive, onConnectionStateChange as onLiveSocketStateChange } from './services/liveSocket';

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

  // Single source of truth for the BFF base URL, derived from settings.
  const bffBaseUrl = `http://${settings.bffHost}:${settings.bffPort}`;

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

  // Parses the Python-dict-formatted status string the FSP's /api/status
  // endpoint returns, e.g. "{'status': 'listening', 'connectedClients': 1, ...}".
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
        if (!target || target === bffTarget) return { name: conn.name, count: 0, cps: [] };
        const result = await executeApiCall('status', target, null);
        const rawStatus = result?.payload?.result?.status;
        const parsed = typeof rawStatus === 'string' ? parsePythonDictString(rawStatus) : rawStatus;
        const isListening = parsed?.status === 'listening';
        const count = isListening ? (parsed?.connectedClients ?? 0) : 0;
        const cps = Array.isArray(parsed?.accessPoints) ? parsed.accessPoints : [];

        return { name: conn.name, count, cps };
      })
    );

    const statusMap = {};
    results.forEach(r => {
      if (r.status === 'fulfilled') statusMap[r.value.name] = r.value;
    });

    return connectionsList.map(c =>
      c.type === 'RTI-FSP'
        ? { ...c, connectedClients: statusMap[c.name]?.count ?? 0, accessPoints: statusMap[c.name]?.cps ?? [] }
        : c
    );
  }, [settings.bffHost, settings.bffPort, parsePythonDictString]);

  // Same idea as enrichFspClientCounts above, for the other side of the
  // link: how many FSPs are currently associated with each connected SO
  // (so/acsi_client.py's get_cp_list, exposed as /api/properties'
  // acsi_client_list), and which FSP sits behind each of those cps
  // (fspLinks, matched on the FSPs' accessPoints - so this must run after
  // enrichFspClientCounts). Only covers first paint - like connectedClients,
  // subsequent updates arrive already-enriched via the "connections" live
  // push (bff_server.py's _build_enriched_connections / _link_so_to_fsps).
  const enrichSoClientCounts = useCallback(async (connectionsList) => {
    const bffTarget = buildTargetValue(settings.bffHost, settings.bffPort);
    const soConns = connectionsList.filter(c => c.type === 'RTI-SO' && c.status === 'connected');

    const results = await Promise.allSettled(
      soConns.map(async (conn) => {
        const target = buildTargetValue(conn.host, conn.port);
        if (!target || target === bffTarget) return { name: conn.name, cps: [] };
        const result = await executeApiCall('properties', target, null);
        const clientList = result?.payload?.result?.acsi_client_list || result?.payload?.acsi_client_list || [];

        return { name: conn.name, cps: Array.isArray(clientList) ? clientList : [] };
      })
    );

    const cpMap = {};
    results.forEach(r => {
      if (r.status === 'fulfilled') cpMap[r.value.name] = r.value.cps;
    });

    const fsps = connectionsList.filter(c => c.type === 'RTI-FSP');
    return connectionsList.map(c => {
      if (c.type !== 'RTI-SO') return c;
      const cps = cpMap[c.name] ?? [];
      return { ...c, connectedFsps: cps.length, fspLinks: linkSoToFsps(cps, fsps) };
    });
  }, [settings.bffHost, settings.bffPort]);

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
        const withFspCounts = await enrichFspClientCounts(rawConnections);
        const enriched = await enrichSoClientCounts(withFspCounts);

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
  }, [settings.bffHost, settings.bffPort, enrichFspClientCounts, enrichSoClientCounts]);

  // Fetch once on mount / whenever BFF settings change
  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  // Live updates: the BFF pushes connection changes over /ws (see
  // push_relay_loop in bff/bff_server.py) instead of every tab polling
  // /api/connections on its own 1s timer. fetchConnections() above covers
  // first paint; the BFF only pushes on change, so anything that changed
  // while the socket was down is picked up by the refetch-on-reconnect below.
  useEffect(() => {
    connectLiveSocket();
    const unsubscribe = subscribeLive('connections', (msg) => {
      const enriched = Array.isArray(msg.data) ? msg.data : [];
      const changed = JSON.stringify(enriched) !== JSON.stringify(connectionsRef.current);
      if (changed) {
        connectionsRef.current = enriched;
        setConnections(enriched);
      }
      setConnectionsLoading(false);
    });
    return unsubscribe;
  }, []);

  // The BFF's push loop only broadcasts when the connections list changes
  // and sends nothing to a newly (re)connected socket, so a change that
  // happened while the socket was down (e.g. a BFF restart) would otherwise
  // stay invisible until the next one. Refetch on every (re)connect instead -
  // this is what makes a manual refresh button unnecessary.
  useEffect(() => onLiveSocketStateChange((connected) => {
    if (connected) fetchConnections({ background: true });
  }), [fetchConnections]);

  // Reconnect the live socket when the BFF host/port changes (not on the
  // initial mount, which already connects above), so it points at the right
  // server instead of silently going stale.
  const liveSocketMountedRef = useRef(false);
  useEffect(() => {
    if (!liveSocketMountedRef.current) {
      liveSocketMountedRef.current = true;
      return;
    }
    reconnectLiveSocket();
  }, [settings.bffHost, settings.bffPort]);

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

  // Poll BFF status so the header's connection indicator reflects reality
  // instead of being stuck on its initial "disconnected" state.
  useEffect(() => {
    let cancelled = false;
    const checkBffStatus = async () => {
      try {
        const response = await fetch(`http://${settings.bffHost}:${settings.bffPort}/api/health`);
        if (cancelled) return;
        if (response.ok) {
          setBffStatus({ connected: true, text: 'BFF connected' });
        } else {
          setBffStatus({ connected: false, text: 'BFF disconnected' });
        }
      } catch (error) {
        if (!cancelled) setBffStatus({ connected: false, text: 'BFF disconnected' });
      }
    };

    checkBffStatus();
    const interval = setInterval(checkBffStatus, 10000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [settings.bffHost, settings.bffPort]);

  return (
    <Router>
      <div className="container">
        <Sidebar />
        <main className="main-content">
          <Header bffStatus={bffStatus} />
          <Routes>
            <Route path="/" element={<Navigate to="/overview" replace />} />
            <Route path="/overview" element={<Overview connections={connections} loading={connectionsLoading} />} />
            <Route path="/connections" element={<Connections settings={settings} connections={connections} loading={connectionsLoading} onReload={fetchConnections} />} />
            <Route path="/model" element={<Model settings={settings} connections={connections} loading={connectionsLoading} onReload={fetchConnections} updateModel={updateModel} getModel={getModel} />} />
            <Route path="/traffic" element={<Traffic settings={settings} connections={connections} loading={connectionsLoading} updateModel={updateModel} getModel={getModel} />} />
            <Route path="/data" element={<Data />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/diagnostics" element={<Diagnostics />} />
            <Route path="/tools" element={<Tools />} />
            <Route path="/settings" element={<Settings settings={settings} setSettings={setSettings} />} />
            <Route path="/acsi-client" element={<ACSIClient settings={settings} bffBaseUrl={bffBaseUrl} connections={connections} updateModel={updateModel} getModel={getModel} />} />
            <Route path="/acsi-server" element={<ACSIServer settings={settings} bffBaseUrl={bffBaseUrl} connections={connections} updateModel={updateModel} getModel={getModel} />} />
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
