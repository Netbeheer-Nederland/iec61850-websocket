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

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { executeApiCall, buildTargetValue, getApiById, getAutoRefreshIntervalMs } from '../services/apiService';
import Tree from '../components/Tree';
import { transformModelToTree } from '../utils/modelUtils';

import TLSConfigModal from '../components/TLSConfigModal';
import ContextMenu  from "../components/ContextMenu.jsx";
import WriteValueModal from '../components/WriteValueModal.jsx';
import ActionLogPanel from '../components/ActionLogPanel.jsx';

function ACSIServer({ settings, updateModel, getModel, connections: propConnections, bffBaseUrl = 'http://localhost:5000'}) {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const fspParam = searchParams.get('fsp');

  // React Router's location.state.endpoint (the RTI-FSP this page manages)
  // is only set by an in-app click (InstanceVisualization/Model) and is
  // lost on a page refresh or a direct/bookmarked URL visit. paramEndpoint
  // is the fallback: resolved asynchronously (see the effect below, once
  // `connections` has actually loaded) from the ?fsp=<name> URL param that
  // navigation now also seeds, so a refresh can recover the same instance
  // instead of leaving this page permanently unusable until the user
  // navigates back in via Setup/Model/Traffic again.
  const navEndpoint = location.state?.endpoint;
  const [paramEndpoint, setParamEndpoint] = useState(null);
  const endpoint = navEndpoint || paramEndpoint;

  // Create instance-specific storage keys. Computed up front (before the
  // host/port state below) so the port initializer can use portStorageKey
  // without depending on state that doesn't exist yet.
  const instanceId = endpoint?.name || `${endpoint?.host || 'rti-so'}:${endpoint?.port || 8765}`;
  const storageKey = `acsi-server-connected-${instanceId}`;
  const portStorageKey = `acsi-server-port-${instanceId}`;
  const cpStorageKey = `acsi-server-cp-${instanceId}`;
  const selectedInstanceStorageKey = `acsi-server-selected-instance-${instanceId}`;

  // Start blank rather than guessing ("rti-so", 8765, "cp1", "active") - a
  // real value only appears once an instance is actually resolved, either
  // by matching a fetched RTI-SO connection (below) or by picking one on
  // the page. Not endpoint.host/endpoint.port: `endpoint` here is this
  // RTI-FSP's *own* connection record (its own host/BFF port, used
  // correctly below for endpointTarget) - seeding the WS Host/Port fields
  // from it pre-filled this FSP's own address as the WS dial-out target,
  // which it can never actually be.
  const [host, setHost] = useState('');
  const [port, setPort] = useState(() => localStorage.getItem(portStorageKey) || '');
  const [cp, setCp] = useState(() => {
    const cachedCp = localStorage.getItem(cpStorageKey);
    return cachedCp || endpoint?.cp || '';
  });
  const [mode, setMode] = useState(() => {
    if (endpoint?.mode === 'passive') return 'passive';
    return endpoint ? 'active' : '';
  });
  const hostPortInitializedRef = useRef(false);

  const [connected, setConnected] = useState(() => localStorage.getItem(storageKey) === 'true');
  const [treeData, setTreeData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [statusInfo, setStatusInfo] = useState(null);
  const [protocolMessages, setProtocolMessages] = useState([]);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState({});
  const [connections, setConnections] = useState([]);
  const [autoRefreshValues, setAutoRefreshValues] = useState(false);
  // Mirrors ACSIClient.jsx's per-cp expandedClients accordion, except this
  // page only ever has the one connection point (its own), so a single
  // boolean is enough instead of a map keyed by cp.
  const [modelExpanded, setModelExpanded] = useState(false);
  const valuesRefreshIntervalRef = useRef(null);
  const monitorIntervalRef = useRef(null);
  const statusIntervalRef = useRef(null);

  // Candidate RTI-SO instances this FSP can dial *into* as a WS client -
  // not FSP instances (this page manages exactly one FSP, itself).
  const soTargetInstances = useMemo(
    () => connections.filter(c => c.type === 'RTI-SO'),
    [connections]
  );

  // A restart (or fresh visit with no navigation state) should not guess a
  // real instance - only a real prior selection counts as "preferred", so
  // the dropdown falls back to blank ("Select instance...") rather than
  // guessing one. Blank is *not* itself a selection - it's just "nothing
  // chosen yet" - so it's never persisted (see the effect below); whatever
  // the dropdown's value actually is (a real instance name, or "custom")
  // is the selection. Not endpoint?.name: `endpoint` is this RTI-FSP's own
  // connection record, not a target RTI-SO instance, so its name never
  // matches one in soTargetInstances - seeding it here just meant every arrival
  // via a navigation link silently fell through to "custom" (see the sync
  // effect's "not found in soTargetInstances" branch) instead of honoring the
  // persisted preference or blank default like a direct visit would.
  const [selectedInstanceName, setSelectedInstanceName] = useState(() =>
    localStorage.getItem(selectedInstanceStorageKey) || ''
  );
  const instanceMatchedRef = useRef(false);
  // WS Host/Port/Mode are editable in both states where there's no real
  // instance backing them: "custom" (an explicit choice) and blank
  // (nothing chosen yet, showing "Select instance..." with usable
  // placeholder defaults instead of leaving the fields read-only and
  // un-correctable - see the sync effect below).
  const isCustomInstance = selectedInstanceName === 'custom';
  const isEditableInstance = isCustomInstance || selectedInstanceName === '';

  // Remember the selection so it's preferred again on the next visit/restart
  // - once the user has actually picked something (including "custom").
  useEffect(() => {
    if (!selectedInstanceName) return;
    localStorage.setItem(selectedInstanceStorageKey, selectedInstanceName);
  }, [selectedInstanceName, selectedInstanceStorageKey]);

  const [showTLSModal, setShowTLSModal] = useState(false);
  const [useOAuth, setUseOAuth] = useState(false);
  const [message, setMessage] = useState(null);

  const [contextMenu, setContextMenu] = useState({ visible: false, x: 0, y: 0 });
  const [contextMenuTarget, setContextMenuTarget] = useState(null);
  const [showWriteModal, setShowWriteModal] = useState(false);
  const [writeModalTarget, setWriteModalTarget] = useState({ ref: '', fc: '' });

  useEffect(() => {
    localStorage.setItem(storageKey, String(connected));
  }, [connected, storageKey]);

  // Persist the port for this instance whenever it changes, so it survives
  // navigating away and back.
  useEffect(() => {
    localStorage.setItem(portStorageKey, port);
  }, [port, portStorageKey]);

  useEffect(() => {
    localStorage.setItem(cpStorageKey, cp);
  }, [cp, cpStorageKey]);


  const handleInstanceSelect = useCallback((e) => {
    const value = e.target.value;
    setSelectedInstanceName(value);
    if (value === 'custom') {
      // Fresh custom entry starts fully blank for the user to fill in, not
      // whatever host/port were left over from a previously-selected
      // instance. CP is read-only (this FSP's own connection point, see
      // endpoint.cp) and isn't part of the per-instance custom entry.
      setHost('');
      setPort('');
      setMode('active');
      return;
    }
    const inst = soTargetInstances.find(c => c.name === value);
    if (inst) {
      setHost(inst.host || '');
      // Was missing: without this, port kept whatever was previously set
      // (e.g. left over from a prior instance, or the BFF's own port if
      // nothing else had set it), so switching instances silently kept
      // talking to the wrong port.
      //
      // This is the SO's *WebSocket* port (ws_port) - the address this FSP
      // dials out to - not its BFF server port (inst.port, used for
      // /api/execute calls to that SO instance). Left blank rather than
      // falling back to inst.port when ws_port isn't set on the connection,
      // so a misconfigured instance is visibly incomplete instead of
      // silently pointing at the wrong port again.
      setPort(inst.ws_port ? String(inst.ws_port) : '');
      // CP is owned by this RTI-FSP connection itself (endpoint.cp, seeded
      // above), not by the target RTI-SO instance - don't clobber it here.
      // FSP only ever supports "active" mode (see fsp/bff_endpoint.py's
      // /start), and connection entries don't carry a per-instance mode -
      // but the field must have a valid value once a real instance is
      // selected, not stay blank.
      setMode('active');
    }
  }, [soTargetInstances]);

  const handleExpandToggle = useCallback((ref, expanded) => {
    setExpandedNodes(prev => ({
      ...prev,
      [ref]: expanded
    }));
  }, []);

  const [connectionsLoaded, setConnectionsLoaded] = useState(false);
  // Fetch connections from BFF to get live TLS/status config.
  // Returns the fetched list (or null on failure) so callers can act on
  // freshly-fetched data instead of relying on component state that may
  // lag behind a background status update.
  const fetchConnections = useCallback(async () => {
    try {
      const url = `${bffBaseUrl}/api/connections`;
      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        const list = data.connections || [];
        setConnections(list);
        setConnectionsLoaded(true);
        return list;
      }
    } catch (error) {
      console.error('Failed to fetch connections:', error);
    }
    return null;
  }, [bffBaseUrl]);

  useEffect(() => {
    if (bffBaseUrl) {
      fetchConnections();
    }
  }, [bffBaseUrl, fetchConnections]);

  // True once we're sure selectedInstanceName (and the port/cp/connected
  // state next to it) reflect their FINAL values, not just whatever the
  // generic pre-resolution storage key happened to hold. navEndpoint
  // resolves synchronously at mount (no gap), so it starts settled
  // immediately in that case, same as when there's no ?fsp= param to
  // resolve at all. Only the async paramEndpoint path (a refresh/direct
  // visit landing on ?fsp=...) starts unsettled, and flips true once
  // either a match is found *and re-synced* (see the effect below) or
  // resolution completes with no match. syncInitialConfig further down
  // waits on this - without it, it could run one render too early, see
  // selectedInstanceName still at its stale generic-key value, and
  // permanently lock itself out (via initialSyncDoneRef) before the
  // restore had a chance to complete - leaving WS Host stuck on
  // "localhost" forever instead of the restored instance's real host,
  // even though the Instance dropdown and WS Port correctly show the
  // restored selection a moment later (they're plain localStorage reads,
  // not dependent on this cross-reference-with-soTargetInstances lookup).
  const [identitySettled, setIdentitySettled] = useState(
    () => Boolean(navEndpoint) || !fspParam
  );

  // Resolve paramEndpoint from the ?fsp=<name> URL param once connections
  // have loaded - only needed when we didn't already get a real endpoint
  // from navigation state (that always wins; the URL param exists purely
  // as a refresh/direct-visit fallback). Runs once per param value.
  const paramResolvedForRef = useRef(null);
  useEffect(() => {
    if (navEndpoint) return;
    if (!fspParam || !connectionsLoaded) return;
    if (paramResolvedForRef.current === fspParam) return;
    paramResolvedForRef.current = fspParam;
    const found = connections.find(c => c.type === 'RTI-FSP' && c.name === fspParam);
    if (found) {
      setParamEndpoint(found);
      // Don't settle yet - wait for the re-sync effect below to actually
      // apply the now-correct instance-keyed state first.
    } else {
      setIdentitySettled(true); // resolution attempted, nothing found - settle with blanks
    }
  }, [navEndpoint, fspParam, connections, connectionsLoaded]);

  // port/cp/connected/selectedInstanceName were already initialized once,
  // at mount, using the generic pre-resolution storage keys (paramEndpoint
  // wasn't known synchronously - it needs the async connections fetch
  // above). Once it resolves, re-read them from their now-correct
  // instance-specific keys so a direct-URL/refresh visit with ?fsp=...
  // ends up in the same state a normal in-app navigation would have, not
  // stuck with whatever the generic fallback key happened to hold.
  useEffect(() => {
    if (!paramEndpoint) return;
    setPort(localStorage.getItem(portStorageKey) || '');
    setCp(localStorage.getItem(cpStorageKey) || paramEndpoint.cp || '');
    setConnected(localStorage.getItem(storageKey) === 'true');
    setSelectedInstanceName(localStorage.getItem(selectedInstanceStorageKey) || '');
    setIdentitySettled(true);
  }, [paramEndpoint, portStorageKey, cpStorageKey, storageKey, selectedInstanceStorageKey]);

  // Keep the URL's ?fsp= param in sync with a real navigated-in endpoint,
  // so a later refresh of this same page has something to recover from
  // (see paramEndpoint above). Replaces history instead of pushing, so
  // this doesn't add a back-button entry.
  useEffect(() => {
    if (!navEndpoint?.name) return;
    if (searchParams.get('fsp') === navEndpoint.name) return;
    const next = new URLSearchParams(searchParams);
    next.set('fsp', navEndpoint.name);
    // Must pass `state` through explicitly - setSearchParams doesn't
    // preserve the existing location.state on its own, so omitting this
    // wiped navEndpoint out from under us on the very next render.
    setSearchParams(next, { replace: true, state: location.state });
  }, [navEndpoint, searchParams, setSearchParams, location.state]);

  // Helper to parse Python dict string to JS object
  const parsePythonDictString = useCallback((pythonStr) => {
    if (!pythonStr || typeof pythonStr !== 'string') {
      return pythonStr;
    }
    try {
      const jsonStr = pythonStr
        .replace(/'/g, '"')
        .replace(/True/g, 'true')
        .replace(/False/g, 'false')
        .replace(/None/g, 'null')
        .replace(/""+/g, '"');
      return JSON.parse(jsonStr);
    } catch (e) {
      console.warn('Could not parse Python dict string:', e);
      return pythonStr;
    }
  }, []);

  // Resolve the IDP server name associated with this connection's OAuth config
  const resolveIdpServerName = useCallback((ep) => {
    const oauthConfig = ep?.OAuth || ep?.oauth || {};
    return oauthConfig.idp_server || ep?.idp_server || '';
  }, []);

  // This FSP's own BFF address (e.g. "rti-fsp01:5001") - every status/
  // start/stop/model call is routed here. Deliberately no fallback to
  // host/port: those are the *target SO's* WS Host/Port form fields, an
  // entirely different address (see handleStartServer's request body) -
  // falling back to them here used to silently misdirect every API call
  // whenever `endpoint` was missing (a direct visit or refresh of this
  // page loses React Router's in-memory location.state.endpoint), instead
  // of failing visibly like ACSIClient.jsx's identical `apiTarget` does.
  const endpointTarget = useMemo(
    () => (endpoint ? buildTargetValue(endpoint.host, endpoint.port) : null),
    [endpoint]
  );

  const stopMonitoring = useCallback(() => {
    if (monitorIntervalRef.current) {
      clearInterval(monitorIntervalRef.current);
      monitorIntervalRef.current = null;
    }
    setIsMonitoring(false);
  }, []);

  const stopStatusPolling = useCallback(() => {
    if (statusIntervalRef.current) {
      clearInterval(statusIntervalRef.current);
      statusIntervalRef.current = null;
    }
  }, []);

  const loadStatus = useCallback(async () => {
    if (!endpointTarget) return;
    try {
      const result = await executeApiCall('status', endpointTarget, null);
      if (result?.ok) {
        // Parse Python dict string in status field
        const parsedPayload = result.payload;
        if (parsedPayload?.result?.status && typeof parsedPayload.result.status === 'string') {
          parsedPayload.result.status = parsePythonDictString(parsedPayload.result.status);
        }
        setStatusInfo(parsedPayload);

        // Sync connected state with actual server status
        const serverStatus = parsedPayload.result?.status;
        if (serverStatus.status) {
          // Server is considered connected if status is 'running', 'listening', 'connected', or 'starting'
          setConnected(['running', 'listening', 'connected', 'starting'].includes(serverStatus.status));
        }
        // CP is read-only in this page now (see the "Connection Point"
        // display next to Load Model), so the live server's reported
        // access point always wins here - there's no manual edit to protect.
        if (Array.isArray(serverStatus?.accessPoints) && serverStatus.accessPoints.length > 0) {
          setCp(serverStatus.accessPoints[0]);
        }
      }
    } catch (error) { console.error('Failed to load status:', error); }
  }, [endpointTarget, executeApiCall, parsePythonDictString]);

  // Load server status and OAuth status on page load
  useEffect(() => {
    if (!endpointTarget) return;
    const fetchInitialData = async () => {
      try {
        // Load server status
        await loadStatus();

        // Fetch OAuth status - only when this connection is actually
        // configured for OAuth (endpoint.OAuth.enable_oauth, set via
        // ConnectionModal). Connections that never use OAuth would always
        // just get "false" back, so probing them on every load is pure
        // noise - see the identical guard in ACSIClient.jsx.
        if (endpoint?.OAuth?.enable_oauth) {
          const result = await executeApiCall('oauth-status', endpointTarget, {});
          if (result?.ok) {
            const enableOAuth = result.payload?.result?.enable_oauth ?? result.payload?.enable_oauth ?? false;
            setUseOAuth(enableOAuth);
          }
        }
      } catch (error) {
        console.error('Failed to fetch initial data:', error);
      }
    };
    fetchInitialData();
  }, [endpointTarget, loadStatus, endpoint]);

  const initialSyncDoneRef = useRef(false);

  useEffect(() => {
  if (initialSyncDoneRef.current) return;

    const syncInitialConfig = async () => {
      if (connected) {
        // Already connected — trust the live server's own reported config.
        // (Only this branch needs endpointTarget - the "resolve which
        // instance to auto-select" branch below doesn't have one yet until
        // it runs, since host/port start blank and endpointTarget is
        // derived from them.)
        if (!endpointTarget) return;
        try {
          const result = await executeApiCall('status', endpointTarget, null);
          if (result?.ok) {
            let serverConfig = result.payload?.result?.status;
            if (typeof serverConfig === 'string') {
              serverConfig = parsePythonDictString(serverConfig);
            }
            if (serverConfig) {
              if (serverConfig.host) setHost(serverConfig.host);
              if (serverConfig.mode) setMode(serverConfig.mode);
            }
          }
          initialSyncDoneRef.current = true;
        } catch (e) {
          console.error('Failed to sync from live server status:', e);
        }
      } else {
        if (!connectionsLoaded || !identitySettled) return; // wait for the real fetch, and for the ?fsp= restore, before deciding

        if (selectedInstanceName === 'custom' || selectedInstanceName === '') {
          // Fill in only whatever's still blank - a real host from
          // navigation state, or a port already restored from
          // portStorageKey, should win over these placeholder defaults.
          // Applies to blank too (nothing chosen yet) so Connect has
          // usable, editable values instead of empty ones - without
          // treating "blank" itself as an actual selection.
          if (!host) setHost('localhost');
          if (!port) setPort('8765');
          if (!mode) setMode('active');
          initialSyncDoneRef.current = true;
          return;
        }

        let inst = selectedInstanceName
          ? soTargetInstances.find(c => c.name === selectedInstanceName)
          : null;

        if (selectedInstanceName && !inst) {
          // A name came in (e.g. via navigation state, or a persisted
          // selection whose instance was since removed) but it's not in
          // the list.
          setSelectedInstanceName('custom');
        }

        if (inst) {
          setHost(inst.host || '');
          // See the identical comment in handleInstanceSelect: this is the
          // SO's ws_port (WS listen port), not its BFF port (inst.port).
          setPort(inst.ws_port ? String(inst.ws_port) : '');
          // CP is owned by this RTI-FSP connection itself (endpoint.cp,
          // seeded at mount), not by the target RTI-SO instance.
          setMode('active');
        }

        initialSyncDoneRef.current = true;
      }
    };

    syncInitialConfig();
  }, [connected, soTargetInstances, selectedInstanceName, connectionsLoaded, identitySettled, endpointTarget, executeApiCall, parsePythonDictString, host, port, mode]);

  const handleStartServer = useCallback(async () => {
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    setLoading(true); setError(null);
    try {
      const result = await executeApiCall('start', endpointTarget, { host, port, mode, cp });
      if (result?.ok) {
        await loadStatus();
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to start server');
      }
    } catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }, [endpointTarget, host, port, mode, cp, executeApiCall, loadStatus]);

  const handleStopServer = useCallback(async () => {
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    setLoading(true); setError(null);
    try {
      const result = await executeApiCall('stop', endpointTarget, {});
      if (result?.ok) {
        await loadStatus();
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to stop server');
      }
    } catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }, [endpointTarget, executeApiCall, loadStatus]);

  const fetchActionLogs = useCallback(async () => {
    if (!endpointTarget) return;
    try {
      const result = await executeApiCall('actions-logs', endpointTarget, {});
      if (result?.ok) {
        const actions = result.payload.result?.actions || result.payload.actions || [];
        if (Array.isArray(actions) && actions.length > 0) {
          setProtocolMessages(prev => {
            const existingIds = new Set(prev.map(msg => msg.id));
            // `actions` comes back oldest-first (the backend appends to a
            // deque) - reverse before prepending so a poll that catches
            // more than one new entry doesn't put them in front of `prev`
            // in their original oldest-first sub-order, which broke the
            // newest-first ordering ActionLogPanel's default view relies on.
            const newMessages = actions.filter(msg => msg && msg.id && !existingIds.has(msg.id))
              .map(msg => ({ ...msg, timestamp: new Date().toLocaleTimeString() }))
              .reverse();
            return [...newMessages, ...prev].slice(0, 30);
          });
        }
      }
    } catch (error) { console.error('Failed to fetch action logs:', error); }
  }, [endpointTarget, executeApiCall]);

  const startMonitoring = useCallback(async () => {
    if (isMonitoring) return;
    if (!endpointTarget) { setError('No endpoint configured'); return; }

    stopMonitoring();
    setIsMonitoring(true);
    await fetchActionLogs();
    monitorIntervalRef.current = setInterval(fetchActionLogs, 5000);
  }, [endpointTarget, isMonitoring, fetchActionLogs, stopMonitoring]);

  const stopMonitoringHandler = useCallback(async () => {
    if (!isMonitoring) return;
    stopMonitoring();
  }, [isMonitoring, stopMonitoring]);

  const clearMessages = useCallback(async () => {
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    const result = await executeApiCall('clear-logs', endpointTarget, {});
    if (result?.ok) setProtocolMessages([]);
    else setError(`Error clearing messages: ${result?.payload?.error || 'Unknown error'}`);
  }, [endpointTarget, executeApiCall]);

  const loadServerModel = useCallback(async () => {
    if (!endpointTarget) { setError('No endpoint configured'); return; }
    setLoading(true); setError(null);
    try {
      const result = await executeApiCall('model', endpointTarget, {});
      if (result?.ok) {
        let modelData = result.payload;

        // Path 1: result.result.model (BFF wraps response in result)
        if (modelData?.result?.model) {
          modelData = modelData.result.model;
        }
        // Path 2: Direct model field
        else if (modelData?.model) {
          modelData = modelData.model;
        }
        // Path 3: The payload itself might be the model

        // Check if there's a tree field
        if (modelData?.tree) {
          modelData = modelData.tree;
        }

        // Handle case where model is a Python dict string
        if (typeof modelData === 'string') {
          // Try to parse as JSON first
          try {
            modelData = JSON.parse(modelData);
          } catch (e) {
            // If not JSON, try to parse as Python dict string
            const jsonStr = modelData
              .replace(/'/g, '"')
              .replace(/True/g, 'true')
              .replace(/False/g, 'false')
              .replace(/None/g, 'null');
            try {
              modelData = JSON.parse(jsonStr);
            } catch (e2) {
              console.error('Failed to parse model data:', e2);
            }
          }
        }

        // If we still have the full BFF response, try result field
        if (modelData === result.payload && modelData?.result) {
          modelData = modelData.result;
        }

        // If modelData has accessPoints but no children structure, create a simple tree
        if (modelData?.accessPoints && !modelData.children && !modelData.ieds && !modelData.kind) {
          modelData = {
            iedName: modelData.iedName || endpoint?.name || 'Server',
            accessPoints: modelData.accessPoints.map(apName => ({
              name: apName,
              ldevices: []
            }))
          };
        }

        if (modelData && Object.keys(modelData).length > 0) {
          setTreeData(transformModelToTree(modelData));
          // Every fresh load starts fully collapsed, not whatever was
          // expanded from a previous load (refs may coincidentally match
          // between loads of the "same" model).
          setExpandedNodes({});
          // Save the model in the global models list
          updateModel(endpointTarget, modelData);
        } else {
          setError('No model data found in response');
        }
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to load model');
      }
    } catch (error) { setError(error.message); }
    finally { setLoading(false); }
  }, [endpointTarget, executeApiCall, endpoint]);

  const formatValueForDisplay = useCallback((valuesData, isError = false) => {
    if (isError) {
      return { display: '✗ Error', color: '#c62828' };
    }

    function asn1TimeStampToISOString(ts) {
      if (!ts || typeof ts.secondSinceEpoch !== 'number') return '';
      const seconds = ts.secondSinceEpoch;
      let ms = 0;
      if (typeof ts.fractionOfSecond === 'number') {
        ms = Math.floor(ts.fractionOfSecond / 1000);
      }
      const date = new Date((seconds * 1000) + ms);
      return date.toISOString();
    }

    // valuesData is the flat { type, value } object from result.values
    const type = valuesData?.type;
    let value = valuesData?.value;

    if (value && typeof value === 'object' && typeof value.secondSinceEpoch === 'number') {
      value = asn1TimeStampToISOString(value) || JSON.stringify(value);
    } else if (typeof value === 'number') {
      value = type === 'enumerated' || Number.isInteger(value) ? String(value) : value.toFixed(2);
    } else if (typeof value === 'boolean') {
      value = value ? 'true' : 'false';
    } else if (value && typeof value === 'object') {
      value = JSON.stringify(value);
    }

    return { display: value !== undefined ? String(value) : '—', color: '#4caf50' };
  }, []);

  const readDataValue = useCallback(
    async (objRef, fc) => {
      if (!endpointTarget) {
        setError('No endpoint configured');
        return;
      }
      try {
        // Server role: no cp needed, it already owns the model
        const result = await executeApiCall('read', endpointTarget, { objRef, fc });

        const updateTreeWithValue = (nodes, targetRef, valueData, isError) => {
          const formatted = formatValueForDisplay(valueData, isError);
          return nodes.map((node) =>
            node.ref === targetRef
              ? { ...node, value: formatted.display, valueColor: formatted.color }
              : node.children
              ? { ...node, children: updateTreeWithValue(node.children, targetRef, valueData, isError) }
              : node
          );
        };

        if (result?.ok) {
          const valueData = result.payload?.result?.values;
          if (valueData && treeData) {
            setTreeData((prev) => ({ ...prev, children: updateTreeWithValue(prev.children, objRef, valueData, false) }));
          }
        } else {
          const errorValue = result?.payload?.error || 'Unknown error';
          if (treeData) {
            setTreeData((prev) => ({ ...prev, children: updateTreeWithValue(prev.children, objRef, errorValue, true) }));
          }
        }
      } catch (error) {
        if (treeData) {
          setTreeData((prev) => ({
            ...prev,
            children: (function updateErr(nodes) {
              const formatted = formatValueForDisplay(error.message, true);
              return nodes.map((node) =>
                node.ref === objRef
                  ? { ...node, value: formatted.display, valueColor: formatted.color }
                  : node.children
                  ? { ...node, children: updateErr(node.children) }
                  : node
              );
            })(prev.children),
          }));
        }
      }
    },
    [endpointTarget, executeApiCall, treeData, formatValueForDisplay]
  );

  // Re-reads every DA/SDA leaf that already has a displayed value (i.e. was
  // read at least once via the context menu), so previously-read values stay
  // live instead of freezing at whatever they were when last read.
  const refreshReadValues = useCallback(() => {
    if (!treeData) return;
    const collectReadNodes = (nodes, acc = []) => {
      for (const node of nodes || []) {
        if ((node.type === 'DA' || node.type === 'SDA') && node.value !== undefined) {
          acc.push({ ref: node.ref, fc: node.fc || 'st' });
        }
        if (node.children) collectReadNodes(node.children, acc);
      }
      return acc;
    };
    collectReadNodes(treeData.children).forEach(({ ref, fc }) => readDataValue(ref, fc));
  }, [treeData, readDataValue]);

  // Auto-refresh: while enabled, periodically replay reads for every value
  // currently shown in the tree, using the interval configured in Settings.
  useEffect(() => {
    if (valuesRefreshIntervalRef.current) {
      clearInterval(valuesRefreshIntervalRef.current);
      valuesRefreshIntervalRef.current = null;
    }
    if (!autoRefreshValues || !treeData) return undefined;

    valuesRefreshIntervalRef.current = setInterval(refreshReadValues, getAutoRefreshIntervalMs());
    return () => {
      if (valuesRefreshIntervalRef.current) {
        clearInterval(valuesRefreshIntervalRef.current);
        valuesRefreshIntervalRef.current = null;
      }
    };
  }, [autoRefreshValues, treeData, refreshReadValues]);

  const handleContextMenu = useCallback((e, nodeInfo) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenuTarget(nodeInfo);
    setContextMenu({ visible: true, x: e.clientX, y: e.clientY });
  }, []);

  const closeContextMenu = useCallback(() => {
    setContextMenu({ visible: false, x: 0, y: 0 });
    setContextMenuTarget(null);
  }, []);

  const getContextMenuItems = useCallback(() => {
    if (!contextMenuTarget) return [];
    const { nodeType, ref, fc } = contextMenuTarget;

    // Only DA / SDA leaves are readable/writable. No Operate — not needed here.
    if (nodeType !== 'DA' && nodeType !== 'SDA') return [];

    const displayFc = fc || 'st';

    return [
      {
        label: `Read Value [${displayFc.toUpperCase()}]`,
        icon: 'fa-eye',
        action: () => {
          readDataValue(ref, displayFc);
          closeContextMenu();
        },
      },
      {
        // Unrestricted on the server side — every FC is writable, not just CF/SP
        label: `Write Value [${displayFc.toUpperCase()}]`,
        icon: 'fa-pen',
        action: () => {
          setWriteModalTarget({ ref, fc: displayFc });
          setShowWriteModal(true);
          closeContextMenu();
        },
      },
    ];
  }, [contextMenuTarget, readDataValue, closeContextMenu]);

  // Auto-poll server status when endpoint is available
  useEffect(() => {
    if (!endpointTarget) return;
    statusIntervalRef.current = setInterval(loadStatus, 10000);
    return () => stopStatusPolling();
  }, [endpointTarget, loadStatus]);

  useEffect(() => () => {
    stopMonitoring();
    stopStatusPolling();
  }, [stopMonitoring, stopStatusPolling]);

  // Display-only translation of the raw backend status (see
  // fsp/acsi_server.py's runtime.status docstring: stopped|starting|
  // listening|stopping|error|reloading) - same approach as
  // ACSIClient.jsx's connectionStatusLabel. The raw value itself is left
  // untouched everywhere it's actually compared (the State color check
  // below, connected-state checks elsewhere), only this label changes.
  // "listening" reads as the passive/SO side's role; FSP is the active
  // side that dials out and then serves ACSI data to that one client, so
  // "Serving" fits its actual behavior better.
  const rawState = statusInfo?.result?.status?.status;
  const stateLabel = (() => {
    const STATUS_LABELS = {
      stopped: 'Stopped',
      starting: 'Starting',
      listening: 'Serving',
      stopping: 'Stopping',
      error: 'Error',
      reloading: 'Reloading',
    };
    return STATUS_LABELS[rawState] || rawState || 'N/A';
  })();

  // Same host/port match TLSConfigModal's own `connection` prop below uses
  // to find the live connection record - kept separate (not literally
  // shared) since the modal's version also builds a full fallback shape
  // (type/ws_mode/properties_info) this button doesn't need, just the
  // live TLS.enable_tls value to reflect on the button itself.
  const liveTlsConnection = useMemo(() =>
    connections.find(c =>
      (c.host === endpoint?.host && String(c.port) === String(endpoint?.port)) ||
      (c.host === host && String(c.port) === String(port))
    ) || (endpoint?.TLS ? endpoint : null),
    [connections, endpoint, host, port]
  );
  const tlsEnabled = Boolean(liveTlsConnection?.TLS?.enable_tls);

  return (
    <section className="page">
      <div className="page-header" style={{ position: 'relative' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1><i className="fas fa-server" style={{ marginRight: '10px', color: 'var(--primary-light)' }}></i>Websocket Connection</h1>
        </div>
      </div>

      {!endpoint && fspParam && !connectionsLoaded && (
        <div className="alert" style={{ marginBottom: '16px', padding: '12px', background: 'var(--info-bg)', color: 'var(--text-secondary)', borderRadius: '4px' }}>
          <i className="fas fa-spinner fa-spin" style={{ marginRight: '8px' }}></i>
          Resolving FSP instance "{fspParam}"...
        </div>
      )}
      {!endpoint && fspParam && connectionsLoaded && (
        <div className="alert alert-error" style={{ marginBottom: '16px', padding: '12px', background: 'var(--danger-bg)', color: 'var(--danger-color)', borderRadius: '4px' }}>
          <i className="fas fa-exclamation-triangle" style={{ marginRight: '8px' }}></i>
          FSP instance "{fspParam}" not found - it may have been removed or
          renamed. Open this page again from a Setup, Model, or Traffic
          page instead.
        </div>
      )}
      {!endpoint && !fspParam && (
        <div className="alert alert-error" style={{ marginBottom: '16px', padding: '12px', background: 'var(--danger-bg)', color: 'var(--danger-color)', borderRadius: '4px' }}>
          <i className="fas fa-exclamation-triangle" style={{ marginRight: '8px' }}></i>
          No FSP instance selected. This page needs to know which RTI-FSP
          it's managing - open it from a Setup, Model, or Traffic page by
          clicking that FSP's icon, rather than visiting this URL directly.
        </div>
      )}

      <div className="acsi-connection-section" style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '16px', flexWrap: 'wrap' }}>
          <div className="form-group">
            <label htmlFor="acsi-server-instance-select">Instance</label>
            <select
              id="acsi-server-instance-select"
              value={selectedInstanceName}
              onChange={handleInstanceSelect}
              disabled={!endpoint || loading || connected}
              title={!endpoint ? 'No FSP instance selected' : connected ? 'Stop the server before switching instances' : undefined}
            >
              <option value="" disabled>Select instance...</option>
              {soTargetInstances.map(inst => {
                // Without a ws_port this instance has nowhere for the FSP to
                // dial into - selecting it is a dead end (WS Port stays
                // blank, Start Server just fails later) - disable it here
                // instead, so the fix (configure it, or use Custom) is
                // obvious upfront rather than after the fact.
                const missingWsPort = !inst.ws_port;
                return (
                  <option key={inst.name} value={inst.name} disabled={missingWsPort}>
                    {/* WS address this instance's Passive endpoint listens
                        on (what this page will dial into) - not its BFF
                        port. */}
                    {inst.name} ({inst.host}:{inst.ws_port || '—'})
                    {missingWsPort ? ' – WS port not configured' : ''}
                  </option>
                );
              })}
              <option value="custom">Custom...</option>
            </select>
            {connected && (
              <small style={{ color: 'var(--text-muted)' }}>
                Stop the server to switch to a different instance.
              </small>
            )}
          </div>
        </div>

        {/* Editable when there's no real instance backing them yet: a
            "custom" choice, or nothing chosen at all (blank, showing
            "Select instance..." with usable defaults). Picking a real
            instance from the dropdown above pre-fills these read-only,
            from that instance's own configuration. */}
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '16px', flexWrap: 'wrap' }}>
          <div className="form-group">
            <label htmlFor="acsi-server-ws-host">WS Host</label>
            <input
              id="acsi-server-ws-host"
              type="text"
              value={host}
              placeholder="0.0.0.0"
              onChange={(e) => setHost(e.target.value)}
              readOnly={!isEditableInstance}
              disabled={loading || !endpoint}
            />
          </div>
          <div className="form-group">
            <label htmlFor="acsi-server-ws-port">WS Port</label>
            <input
              id="acsi-server-ws-port"
              type="text"
              value={port}
              placeholder="8765"
              onChange={(e) => setPort(e.target.value)}
              readOnly={!isEditableInstance}
              disabled={loading || !endpoint}
            />
          </div>
          <div className="form-group">
            <label htmlFor="acsi-server-ws-mode">WS Mode</label>
            {isEditableInstance ? (
              <select
                id="acsi-server-ws-mode"
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                disabled={loading || !endpoint}
              >
                {!mode && <option value="" disabled>Select instance...</option>}
                <option value="active">Active</option>
                <option value="passive">Passive</option>
              </select>
            ) : (
              // Fixed by the selected instance, not a real choice here -
              // shown as read-only text, not a disabled dropdown that
              // looks interactive but isn't (see ConnectionModal.jsx's
              // identical ACSI/WebSocket Mode pattern).
              <input
                id="acsi-server-ws-mode"
                type="text"
                readOnly
                value={mode === 'active' ? 'Active' : mode === 'passive' ? 'Passive' : ''}
              />
            )}
          </div>
        </div>
      </div>

      {/* Security Configuration Buttons */}
      <div style={{ display: 'flex', gap: '16px', marginLeft: 'auto', marginBottom: '24px' }}>
        <button id="acsi-start-btn" className={connected ? 'btn-secondary' : 'btn-primary'} onClick={handleStartServer} disabled={loading || connected || !endpoint}>
            {loading ? 'Starting...' : 'Connect'}
          </button>
          <button id="acsi-stop-btn" className={connected ? 'btn-primary' : 'btn-secondary'} onClick={handleStopServer} disabled={loading || !connected}>
            {loading ? 'Stopping...' : 'Disconnect'}
          </button>
        <button
          className="btn-secondary"
          onClick={() => setShowTLSModal(true)}
          disabled={loading}
          title={tlsEnabled ? 'TLS is enabled - click to configure' : 'Configure TLS settings'}
          id="acsi-tls-btn"
          style={tlsEnabled ? {
            borderColor: 'var(--success-color)',
            color: 'var(--success-color)',
          } : undefined}
        >
          <i className={`fas ${tlsEnabled ? 'fa-lock' : 'fa-shield-alt'}`} style={{ marginRight: '8px' }}></i>
          TLS Config{tlsEnabled ? ' (On)' : ''}
        </button>
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={useOAuth}
            onChange={async (e) => {
              const newValue = e.target.checked;

              if (!endpointTarget || !endpoint?.name) return;

              setLoading(true);

              // Only gate the ENABLE path on IDP availability. Disabling proceeds unchecked.
              if (newValue) {
                const idpServerName = resolveIdpServerName(endpoint);
                const latestConnections = await fetchConnections();
                const idpServerConn = (latestConnections || connections).find(
                  c => c.type === 'IDP-Server' && c.name === idpServerName
                );

                if (!idpServerConn || idpServerConn.status !== 'connected') {
                  setMessage({ type: 'error', text: 'IDP server unavailable' });
                  setLoading(false);
                  return;
                }
              }

              setUseOAuth(newValue);
              // Call reconfig-oauth immediately when checkbox is toggled
              try {
                  // Build OAuth config from endpoint
                  const oauthConfig = endpoint?.OAuth || {};

                  // For active mode (FSP), use the client's port for WebSocket connection
                  let connectionPort = endpoint?.port || port;
                  if (endpoint?.ws_mode === 'active' || endpoint?.ws_mode === 'Active') {
                      // Find corresponding client connection (SO) by replacing Server with Client in endpoint name
                      const clientName = endpoint.name.replace('Server', 'Client');
                      const clientConnection = connections.find(c =>
                          (c.type === 'RTI-SO' || c.acsi === 'client') &&
                          c.name === clientName
                      );
                      if (clientConnection) {
                          connectionPort = clientConnection.port;
                      }
                  }

                  // Use the connection's own host/port for the target endpoint
                  const targetHost = endpoint?.host || host;
                  const targetPort = endpoint?.port || port;
                  const connectionTarget = buildTargetValue(targetHost, targetPort);

                  const requestBody = {
                    connection_name: endpoint?.name,
                    enable_oauth: newValue,
                    ws_mode: endpoint?.ws_mode || 'active',
                    host: host || "127.0.0.1",
                    port: String(port) || "8675",
                    cp: cp,
                    // Always send OAuth config fields (null when disabling)
                    token_endpoint_url: newValue ? (oauthConfig.token_endpoint || '') : null,
                    client_id: newValue ? (oauthConfig.client_id || '') : null,
                    client_secret: newValue ? (oauthConfig.client_secret || '') : null,
                    ca_certificate: newValue ? (oauthConfig.auth_server_ca || '') : null,
                    enable_token_refresh: newValue ? (oauthConfig.enable_token_refresh || false) : false
                  };

                  // Save to SO/FSP server
                  const soResult = await executeApiCall('reconfig-oauth', connectionTarget, requestBody);

                  // Also save to BFF's connections.json
                  const bffOauthConfig = {
                    connection_name: endpoint?.name || host,
                    enable_oauth: newValue,
                    ws_mode: endpoint?.ws_mode || 'Active',
                    // Always send OAuth config fields (null when disabling)
                    token_endpoint_url: newValue ? (oauthConfig.token_endpoint || '') : null,
                    client_id: newValue ? (oauthConfig.client_id || '') : null,
                    client_secret: newValue ? (oauthConfig.client_secret || '') : null,
                    ca_certificate: newValue ? (oauthConfig.auth_server_ca || '') : null,
                    enable_token_refresh: newValue ? (oauthConfig.enable_token_refresh || false) : false
                  };
                  const bffResult = await fetch(`${bffBaseUrl}/api/connections/oauth-config`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(bffOauthConfig)
                  });

                  if (soResult?.ok && bffResult.ok) {
                    setMessage({ type: 'success', text: `OAuth ${newValue ? 'enabled' : 'disabled'} successfully` });
                  } else {
                    setMessage({ type: 'error', text: soResult?.payload?.error || bffResult.statusText || 'Failed to update OAuth' });
                    setUseOAuth(!newValue); // Revert on failure
                  }
                } catch (error) {
                  setMessage({ type: 'error', text: error.message });
                  setUseOAuth(!newValue); // Revert on failure
                } finally {
                  setLoading(false);
                }
            }}
            disabled={loading}
            id="acsi-oauth-checkbox"
          />
          <span style={{ color: 'var(--text-primary)' }}>Enable OAuth</span>
        </label>
      </div>

        <div className="page-header" style={{ position: 'relative' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <h1><i className="fas fa-server" style={{ marginRight: '10px', color: 'var(--primary-light)' }}></i>ACSI Server</h1>
          </div>
        </div>

      {/*<div style={{ display: 'flex', gap: '16px', marginBottom: '24px', alignItems: 'center' }}>
        <button id="acsi-reload-status-btn" className="btn-secondary" onClick={loadStatus} disabled={!endpointTarget}>
          Reload Status
        </button>
      </div>*/}

      {message && (
      <div className="alert" style={{
        marginBottom: '16px',
        padding: '12px',
        background: message.type === 'success' ? 'var(--success-bg)' : 'var(--danger-bg)',
        color: message.type === 'success' ? 'var(--success-color)' : 'var(--danger-color)',
        borderRadius: '4px',
        display: 'flex',
        alignItems: 'center'
      }}>
        <i className={`fas fa-${message.type === 'success' ? 'check-circle' : 'exclamation-circle'}`} style={{ marginRight: '8px' }}></i>
        {message.text}
      </div>
    )}

      {error && <div className="alert alert-error" style={{ marginBottom: '16px', padding: '12px', background: 'var(--danger-bg)', color: 'var(--danger-color)', borderRadius: '4px' }}>
        <i className="fas fa-exclamation-triangle" style={{ marginRight: '8px' }}></i>{error}
      </div>}

      {statusInfo && (
        <div style={{ marginBottom: '24px', padding: '16px', background: 'var(--bg-card)', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
          <h3 style={{ margin: 0, marginBottom: '12px', fontSize: '16px' }}>Connection Status</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
            <div><span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Model</span><div style={{ fontWeight: '500' }}>{statusInfo.result?.status?.modelName || 'N/A'}</div></div>
            <div><span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>State</span><div style={{ fontWeight: '500', color: ['running', 'listening', 'connected', 'starting'].includes(rawState) ? 'var(--success-color)' : 'var(--text-secondary)' }}>{stateLabel}</div></div>
          </div>
        </div>
      )}

      {/* Connection point, expandable - same accordion approach as
          ACSIClient.jsx's per-client list, just a single entry since this
          page only ever has its own one connection point. */}
      <div className="acsi-clients-list" style={{ marginBottom: '24px' }}>
        <div
          className="acsi-client-entry"
          style={{
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            marginBottom: '8px',
            overflow: 'hidden',
          }}
        >
          <div
            onClick={() => setModelExpanded(prev => !prev)}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '12px 16px',
              cursor: 'pointer',
              background: 'var(--bg-card)',
            }}
          >
            <span style={{ fontWeight: 500 }}>{cp || 'Connection Point'}</span>
            <i className={`fas fa-chevron-${modelExpanded ? 'up' : 'down'}`}></i>
          </div>
          {modelExpanded && (
            <div
              style={{
                padding: '16px',
                background: 'var(--bg-card)',
                borderTop: '1px solid var(--border-color)',
              }}
            >
              <div style={{ display: 'flex', gap: '16px', marginBottom: '16px', alignItems: 'center' }}>
                <button id="acsi-load-model-btn" className="btn-primary" onClick={loadServerModel} disabled={loading}>
                  {loading ? 'Loading...' : 'Load Model'}
                </button>
                <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-muted)', cursor: treeData ? 'pointer' : 'default' }}>
                  <input
                    type="checkbox"
                    checked={autoRefreshValues}
                    disabled={!treeData}
                    onChange={(e) => setAutoRefreshValues(e.target.checked)}
                  />
                  Auto-refresh read values
                </label>
              </div>
              <div id="acsi-modelPanel" className="model-tree">
                {treeData ? (
                  <Tree
                    data={treeData}
                    expandedNodes={expandedNodes}
                    onExpandToggle={handleExpandToggle}
                    onContextMenu={handleContextMenu}
                  />
                ) : (
                  <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '12px' }}>
                    {endpoint ? `Click "Load Model" to view the server model for ${endpoint.name || endpoint.host}:${endpoint.port}` : 'Configure and start the ACSI Server to load model'}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="page-header">
        <div style={{  display: 'flex', alignItems: 'center', gap: '16px' }}>
          <h1><i className="fas fa-server" style={{ marginRight: '10px', color: 'var(--primary-light)' }}></i>Monitoring</h1>
        </div>
      </div>

      <ActionLogPanel
        messages={protocolMessages}
        isMonitoring={isMonitoring}
        disabled={!endpointTarget}
        onStart={startMonitoring}
        onStop={stopMonitoringHandler}
        onClear={clearMessages}
      />

      <TLSConfigModal
        isOpen={showTLSModal}
        onClose={() => {
          setShowTLSModal(false);
          setTimeout(() => setMessage(null), 3000);
        }}
        connection={(
          () => {
            // Try to find matching connection from live connections (has updated TLS)
            const liveConn = connections.find(c =>
              (c.host === endpoint?.host && String(c.port) === String(endpoint?.port)) ||
              (c.host === host && String(c.port) === String(port))
            );
            if (liveConn) {
              return liveConn;
            }
            // Fallback to endpoint with TLS if available
            if (endpoint?.TLS) {
              return {
                name: endpoint.name || host,
                host: endpoint.host || host,
                port: endpoint.port || port,
                type: 'RTI-SO',
                ws_mode: 'Active',
                TLS: endpoint.TLS,
                properties_info: {
                  properties: {
                    ws_mode: 'Active'
                  }
                }
              };
            }
            // Final fallback
            return {
              name: endpoint?.name || host,
              host: endpoint?.host || host,
              port: endpoint?.port || port,
              type: 'RTI-SO',
              ws_mode: 'Active',
              TLS: {},
              properties_info: {
                properties: {
                  ws_mode: 'Active'
                }
              }
            };
          }
        )()}
        bffBaseUrl={bffBaseUrl}
        wsHost={host}
        wsPort={port}
        onSuccess={(msg) => {
          setMessage({ type: 'success', text: msg });
          // Refetch connections to get updated TLS config
          fetchConnections();
        }}
        onError={(msg) => setMessage({ type: 'error', text: msg })}
      />

      <ContextMenu
        x={contextMenu.x}
        y={contextMenu.y}
        visible={contextMenu.visible}
        onClose={closeContextMenu}
        items={getContextMenuItems()}
      />

      {showWriteModal && (
        <WriteValueModal
          objRef={writeModalTarget.ref}
          fc={writeModalTarget.fc}
          endpoint={{ host: endpoint?.host || host, port: endpoint?.port || port }}
          cp={null}
          onClose={() => {
            setShowWriteModal(false);
            setWriteModalTarget({ ref: '', fc: '' });
          }}
          onSuccess={async () => {
            setShowWriteModal(false);
            if (writeModalTarget.ref && writeModalTarget.fc) {
              await readDataValue(writeModalTarget.ref, writeModalTarget.fc);
            }
            setWriteModalTarget({ ref: '', fc: '' });
          }}
        />
      )}

    </section>
  );
}

export default ACSIServer;