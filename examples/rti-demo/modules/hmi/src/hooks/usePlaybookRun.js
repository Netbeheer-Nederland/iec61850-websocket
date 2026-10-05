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

import { useEffect, useState } from 'react';
import { subscribe } from '../services/liveSocket';
import { getPlaybookRun } from '../utils/playbooks';

/**
 * The BFF's current (or last) playbook run: fetched once, then kept up to
 * date by its "playbook-run" pushes on /ws - so a reloaded page, or a second
 * HMI, follows a run started elsewhere.
 * @returns {?Object} run state (bff/playbook_runs.py), or null before any run
 */
export function usePlaybookRun() {
  const [run, setRun] = useState(null);
  useEffect(() => {
    let alive = true;
    let pushed = false;
    const off = subscribe('playbook-run', (msg) => {
      pushed = true;
      setRun(msg.data);
    });
    getPlaybookRun()
      .then((r) => { if (alive && !pushed) setRun(r); })
      .catch(() => {});
    return () => {
      alive = false;
      off();
    };
  }, []);
  return run;
}
