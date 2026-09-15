/**
 * Live push channel to the BFF's /ws endpoint.
 *
 * Phase 0 of the reactiveness work: instead of every open tab/page polling
 * the BFF (and the BFF polling every RTI-SO/RTI-FSP instance) on its own
 * schedule, the BFF polls once centrally (see push_relay_loop in
 * bff/bff_server.py) and pushes deltas over one shared WebSocket. This module
 * owns that single connection and lets pages subscribe to the event types
 * they care about ("connections", "messages") instead of running their own
 * setInterval polling loops.
 *
 * Auto-reconnects with backoff if the BFF restarts or the connection drops.
 */
import { getBffBaseUrl } from './apiService';

let socket = null;
let reconnectTimer = null;
let reconnectDelay = 1000;
const MAX_RECONNECT_DELAY_MS = 15000;

// event type -> Set<handler>
const listeners = new Map();
// handler(connected: boolean)
const stateListeners = new Set();

const notifyState = (connected) => {
  stateListeners.forEach((fn) => {
    try {
      fn(connected);
    } catch (e) {
      console.error('liveSocket state listener failed:', e);
    }
  });
};

const scheduleReconnect = () => {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    connect();
  }, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY_MS);
};

/**
 * Open (or reuse) the shared WebSocket connection to the BFF. Safe to call
 * multiple times - a no-op if already open/connecting.
 */
export const connect = () => {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  const wsUrl = `${getBffBaseUrl().replace(/^http/, 'ws')}/ws`;

  let ws;
  try {
    ws = new WebSocket(wsUrl);
  } catch (e) {
    scheduleReconnect();
    return;
  }
  socket = ws;

  ws.onopen = () => {
    reconnectDelay = 1000;
    notifyState(true);
  };

  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (e) {
      return;
    }
    const handlers = listeners.get(msg?.type);
    if (!handlers) return;
    handlers.forEach((fn) => {
      try {
        fn(msg);
      } catch (e) {
        console.error(`liveSocket handler for "${msg.type}" failed:`, e);
      }
    });
  };

  ws.onclose = () => {
    if (socket === ws) {
      notifyState(false);
      scheduleReconnect();
    }
  };

  ws.onerror = () => {
    ws.close();
  };
};

/**
 * Close the current connection (if any) and reconnect immediately with the
 * reconnect backoff reset. Call this when the BFF host/port settings change.
 */
export const reconnect = () => {
  clearTimeout(reconnectTimer);
  reconnectDelay = 1000;
  if (socket) {
    const stale = socket;
    socket = null;
    stale.onclose = null;
    stale.onerror = null;
    stale.close();
  }
  connect();
};

/**
 * Subscribe to a push event type (currently "connections" or "messages").
 * Returns an unsubscribe function.
 */
export const subscribe = (type, handler) => {
  if (!listeners.has(type)) listeners.set(type, new Set());
  listeners.get(type).add(handler);
  return () => listeners.get(type)?.delete(handler);
};

/**
 * Subscribe to connection-state changes (true = open). Immediately invoked
 * once with the current state. Returns an unsubscribe function.
 */
export const onConnectionStateChange = (handler) => {
  stateListeners.add(handler);
  handler(isConnected());
  return () => stateListeners.delete(handler);
};

export const isConnected = () => socket?.readyState === WebSocket.OPEN;

export default {
  connect,
  reconnect,
  subscribe,
  onConnectionStateChange,
  isConnected,
};
