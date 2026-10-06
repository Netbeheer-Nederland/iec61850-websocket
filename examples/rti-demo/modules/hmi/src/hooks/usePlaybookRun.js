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

import { useEffect, useState } from 'react';
import { subscribe, onConnectionStateChange } from '../services/liveSocket';
import { getPlaybookRun } from '../utils/playbooks';

/**
 * The BFF's current (or last) playbook run: fetched on mount and on every
 * reconnect, then kept up to date by its "playbook-run" pushes on /ws - so a
 * reloaded page, a second HMI, or a dropped connection (even a BFF restart)
 * follows a run started elsewhere, instead of showing "running" forever.
 *
 * Returns [run, setRun] - the state, and a setter callers can use to apply a
 * run they just started themselves (e.g. what runPlaybook() returns) without
 * waiting for the push.
 * @returns {[?Object, Function]} run state (bff/playbook_runs.py), or null before any run
 */
export function usePlaybookRun() {
  const [run, setRun] = useState(null);
  useEffect(() => {
    let alive = true;
    // Bumped on every push, so a fetch in flight when a newer push arrives
    // doesn't get to overwrite it once it resolves.
    let pushSeq = 0;
    const fetchRun = () => {
      const seqAtStart = pushSeq;
      getPlaybookRun()
        .then((r) => { if (alive && pushSeq === seqAtStart) setRun(r); })
        .catch(() => {});
    };
    const offPush = subscribe('playbook-run', (msg) => {
      pushSeq += 1;
      setRun(msg.data);
    });
    fetchRun();
    // Re-fetch whenever the socket (re)connects - onConnectionStateChange
    // also calls this once immediately, which just repeats the mount fetch.
    const offConn = onConnectionStateChange((connected) => {
      if (connected) fetchRun();
    });
    return () => {
      alive = false;
      offPush();
      offConn();
    };
  }, []);
  return [run, setRun];
}
