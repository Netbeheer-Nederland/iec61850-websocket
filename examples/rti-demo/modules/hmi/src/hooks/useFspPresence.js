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

import { useState, useEffect } from 'react';

// Whether each FSP's link to the SO is up, for showing a dropped FSP on
// Traffic instead of letting it vanish:
//   up          - the FSP is reachable and has its WebSocket to the SO open
//   link-down   - reachable (its REST API answers the BFF), but no WebSocket
//   unreachable - the BFF can't reach the FSP at all
// Changes after the page opened are kept as events, which the timeline
// shows as "link down" / "link back up" rows.

export const fspStateOf = (conn) => {
  if (!conn || conn.status !== 'connected') return 'unreachable';
  return (conn.connectedClients ?? 0) > 0 ? 'up' : 'link-down';
};

/**
 * Fold the current connections into the presence state: per FSP name its
 * { state, since (ms, null if already so when first seen), downs }, plus an
 * event per change. FSPs no longer in the connections (deleted) are dropped.
 */
export function updatePresence(prev, connections, now) {
  const fsps = connections.filter((c) => c.type === 'RTI-FSP');
  const byName = {};
  const events = [];
  fsps.forEach((conn) => {
    const state = fspStateOf(conn);
    const before = prev.byName[conn.name];
    if (!before) {
      byName[conn.name] = { state, since: null, downs: 0 };
      return;
    }
    if (before.state === state) {
      byName[conn.name] = before;
      return;
    }
    const wasUp = before.state === 'up';
    const isUp = state === 'up';
    byName[conn.name] = { state, since: now, downs: before.downs + (wasUp && !isUp ? 1 : 0) };
    events.push({
      fsp: conn.name,
      from: before.state,
      to: state,
      at: now,
      // How long it was down, when it comes back up.
      downMs: isUp && before.since != null ? now - before.since : null,
    });
  });
  const sameFsps = Object.keys(byName).length === Object.keys(prev.byName).length
    && Object.keys(byName).every((name) => byName[name] === prev.byName[name]);
  if (sameFsps) return prev;
  return { byName, events: events.length ? [...prev.events, ...events] : prev.events };
}

/** Re-render every second while `active`, for running "down for" clocks. */
export function useNow(active) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  return now;
}

/**
 * @param {Object[]} connections - enriched connections (App.jsx)
 * @returns {{byName: Object<string, {state, since, downs}>, events: Object[]}}
 */
export function useFspPresence(connections = []) {
  const [presence, setPresence] = useState(() => updatePresence({ byName: {}, events: [] }, connections, Date.now()));
  // Unchanged connections give back the same state, so this is a no-op on
  // pushes that change nothing (and on the first render).
  useEffect(() => {
    setPresence((prev) => updatePresence(prev, connections, Date.now()));
  }, [connections]);
  return presence;
}
