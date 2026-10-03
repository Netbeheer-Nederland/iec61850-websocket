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

import { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { subscribe as subscribeLive } from '../services/liveSocket';
import { buildTargetValue } from '../services/apiService';

// Per SO-FSP link activity for the Traffic topology, counted from each
// FSP's own frame log (the BFF relays every live instance's new frames as
// "messages" pushes - push_relay_loop in bff_server.py - whether or not a
// MessageMonitor is open). The FSP side is used, not the SO's, because an
// FSP only ever has the one link, and its report frames ("unconfirmed")
// carry no associateId the SO side could attribute them by.

export const EMPTY_LINK = Object.freeze({
  requests: 0,
  responses: 0,
  reports: 0,
  errors: 0,
  last: null,
  pulse: null,
});

/**
 * What a frame logged by an FSP means for its link: "request" (SO -> FSP),
 * "response" (FSP -> SO, ok unless a serviceError) or "report" (an
 * unconfirmed FSP -> SO push). Anything else (associate, parse errors) is
 * null and ignored.
 */
export function classifyFspFrame(frame) {
  const dir = frame?.direction;
  const cat = frame?.category;
  if (dir === 'recv' && cat === 'request') return 'request';
  if (dir === 'send' && cat === 'response') return 'response';
  if (dir === 'send' && cat === 'unconfirmed') return 'report';
  return null;
}

/**
 * Fold a batch of one FSP's frames into its link state. Every frame counts,
 * but a batch only pulses once (with its last frame), so a backlog the BFF
 * replays after an instance restart doesn't fire a burst of animations.
 */
export function applyFspFrames(link = EMPTY_LINK, frames = [], seq = 0) {
  let next = link;
  let lastFrame = null;
  for (const frame of frames) {
    const type = classifyFspFrame(frame);
    if (!type) continue;
    const ok = frame.level !== 'error';
    next = {
      ...next,
      requests: next.requests + (type === 'request' ? 1 : 0),
      responses: next.responses + (type === 'response' ? 1 : 0),
      reports: next.reports + (type === 'report' ? 1 : 0),
      errors: next.errors + (ok ? 0 : 1),
      last: {
        type,
        ok,
        service: frame.service_type || frame.service || '',
        time: frame.time || frame.timestamp || '',
      },
    };
    lastFrame = type;
  }
  if (lastFrame) next = { ...next, pulse: { type: lastFrame, ok: next.last.ok, seq } };
  return next;
}

/**
 * Live activity per connected FSP, keyed by FSP name, plus a reset().
 *
 * @param {Object[]} connections - enriched connections (App.jsx)
 * @returns {{activity: Object<string, typeof EMPTY_LINK>, reset: Function}}
 */
export function useLinkActivity(connections = []) {
  const [activity, setActivity] = useState({});
  // Survives re-subscribing when connections change, so a pulse's seq (the
  // key that restarts its animation) never repeats.
  const seqRef = useRef(0);

  // "host:port" target -> FSP name, for matching the pushes' `target`.
  const fspByTarget = useMemo(() => {
    const map = {};
    connections
      .filter((c) => c.type === 'RTI-FSP' && c.host && c.port)
      .forEach((c) => { map[buildTargetValue(c.host, c.port)] = c.name; });
    return map;
  }, [connections]);

  useEffect(() => {
    return subscribeLive('messages', (msg) => {
      const name = fspByTarget[msg?.target];
      if (!name || !Array.isArray(msg.data)) return;
      seqRef.current += 1;
      const batchSeq = seqRef.current;
      setActivity((prev) => {
        const updated = applyFspFrames(prev[name], msg.data, batchSeq);
        return updated === prev[name] ? prev : { ...prev, [name]: updated };
      });
    });
  }, [fspByTarget]);

  const reset = useCallback(() => setActivity({}), []);

  return { activity, reset };
}
