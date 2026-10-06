/*
 * SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 *
 * Copyright 2025-2026 Netbeheer Nederland
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

import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { subscribe as subscribeLive, onConnectionStateChange } from '../services/liveSocket';
import { executeApiCall, buildTargetValue } from '../services/apiService';
import { usePersistentFlag } from './usePersistentFlag';
import { unwrapList } from '../utils/timeline';

// Most entries kept per target and kind; older ones drop off.
export const MAX_ENTRIES = 2000;
const POLL_MS = 5000;

const byTime = (a, b) => String(a.time || a.timestamp || '').localeCompare(String(b.time || b.timestamp || ''));

/**
 * The frames and ACSI entries of every connected SO and FSP, for Traffic's
 * merged timeline (utils/timeline.js). Catches up over HTTP when started
 * (and on reconnect), then follows the BFF's "messages" / "actions" pushes,
 * polling only while the push socket is down - same scheme as
 * MessageMonitor, but across all instances at once.
 *
 * Runs by default; Stop is remembered (localStorage) like a monitor's.
 * Clear only empties this view - the instances' logs, which the per-instance
 * monitors also show, are left alone.
 *
 * @returns {{sos, fsps, stores, running, start, stop, clear}}
 */
export function useTrafficTimeline(connections = []) {
  const [paused, setPaused] = usePersistentFlag('traffic-timeline-paused');
  const running = !paused;
  const [stores, setStores] = useState({});

  const withTarget = useCallback((type, connectedOnly) => connections
    .filter((c) => c.type === type && c.host && c.port && (!connectedOnly || c.status === 'connected'))
    .map((c) => ({ ...c, target: buildTargetValue(c.host, c.port) })), [connections]);
  const sos = useMemo(() => withTarget('RTI-SO', true), [withTarget]);
  // Every FSP, reachable or not - one that dropped keeps its lane and the
  // entries already held; only reachable ones are fetched from below. The
  // BFF only knows an FSP's cps (accessPoints) while it can reach it, and
  // the SO drops the cp's link, so the last cps seen are kept: without them
  // a dropped FSP's earlier calls would no longer be matched to it.
  const lastCpsRef = useRef({});
  const fsps = useMemo(() => withTarget('RTI-FSP', false).map((f) => {
    if (f.accessPoints?.length) {
      lastCpsRef.current[f.name] = f.accessPoints;
      return f;
    }
    const known = lastCpsRef.current[f.name];
    return known ? { ...f, accessPoints: known } : f;
  }), [withTarget]);
  const targetsKey = [...sos, ...fsps.filter((f) => f.status === 'connected')].map((c) => c.target).join(',');

  // Per "target|kind": ids already held, and the id Clear hid up to.
  const seenRef = useRef({});
  const clearedRef = useRef({});
  const arrivalRef = useRef(0);

  const ingest = useCallback((target, kind, entries) => {
    if (!target || !Array.isArray(entries) || entries.length === 0) return;
    const slot = `${target}|${kind}`;
    const maxId = Math.max(0, ...entries.map((e) => Number(e?.id) || 0));
    // ids went backwards past the clear point: the instance restarted.
    if (maxId < (clearedRef.current[slot] || 0)) clearedRef.current[slot] = 0;
    const seen = seenRef.current[slot] || (seenRef.current[slot] = new Set());
    const fresh = entries
      .filter((e) => e && typeof e === 'object')
      .filter((e) => (Number(e.id) || 0) > (clearedRef.current[slot] || 0))
      .filter((e) => (kind === 'acsi' ? e.kind === 'acsi' : true))
      .filter((e) => !seen.has(e.id))
      .sort(byTime)
      .map((e) => {
        seen.add(e.id);
        arrivalRef.current += 1;
        // _receivedAt (this browser's clock) places link up/down rows, which
        // have no instance time, among the instances' entries.
        return { ...e, _arrival: arrivalRef.current, _receivedAt: Date.now() };
      });
    if (fresh.length === 0) return;
    setStores((prev) => {
      const store = prev[target] || { frames: [], acsi: [] };
      const list = [...store[kind], ...fresh].slice(-MAX_ENTRIES);
      return { ...prev, [target]: { ...store, [kind]: list } };
    });
  }, []);

  // Keyed on the joined string, so a connections push that changes nothing
  // about which instances are up doesn't re-subscribe and re-fetch.
  const targets = useMemo(() => (targetsKey ? targetsKey.split(',') : []), [targetsKey]);

  const catchUp = useCallback(() => Promise.all(targets.map(async (target) => {
    try {
      const [frames, actions] = await Promise.all([
        executeApiCall('messages', target, {}),
        executeApiCall('actions-logs', target, {}),
      ]);
      if (frames?.ok) ingest(target, 'frames', unwrapList(frames.payload, 'messages'));
      if (actions?.ok) ingest(target, 'acsi', unwrapList(actions.payload, 'actions'));
    } catch (error) {
      console.error(`Timeline: failed to fetch ${target}:`, error);
    }
  })), [targets, ingest]);

  // Live pushes, plus a catch-up whenever started or the instances change.
  useEffect(() => {
    if (!running) return undefined;
    catchUp();
    const known = new Set(targets);
    const offMessages = subscribeLive('messages', (msg) => {
      if (known.has(msg?.target)) ingest(msg.target, 'frames', msg.data);
    });
    const offActions = subscribeLive('actions', (msg) => {
      if (known.has(msg?.target)) ingest(msg.target, 'acsi', msg.data);
    });
    return () => { offMessages(); offActions(); };
  }, [running, targets, catchUp, ingest]);

  // Poll while the push socket is down (onConnectionStateChange reports the
  // current state straight away); catch up once it's back.
  useEffect(() => {
    if (!running) return undefined;
    let timer = null;
    const stopTimer = () => { if (timer) clearInterval(timer); timer = null; };
    const off = onConnectionStateChange((connected) => {
      if (connected) {
        if (timer) catchUp();
        stopTimer();
      } else if (!timer) {
        timer = setInterval(catchUp, POLL_MS);
      }
    });
    return () => { off(); stopTimer(); };
  }, [running, catchUp]);

  const clear = useCallback(() => {
    setStores((prev) => {
      Object.entries(prev).forEach(([target, store]) => {
        ['frames', 'acsi'].forEach((kind) => {
          const slot = `${target}|${kind}`;
          const maxId = Math.max(0, ...store[kind].map((e) => Number(e.id) || 0));
          clearedRef.current[slot] = Math.max(clearedRef.current[slot] || 0, maxId);
        });
      });
      return {};
    });
    seenRef.current = {};
  }, []);

  const start = useCallback(() => setPaused(false), [setPaused]);
  const stop = useCallback(() => setPaused(true), [setPaused]);

  return { sos, fsps, stores, running, start, stop, clear };
}
