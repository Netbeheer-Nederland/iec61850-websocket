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

import { useSyncExternalStore } from 'react';
import { clicksToSteps } from '../utils/playbooks';

// The playbook being recorded: one store for the whole page, so clicks on
// the demo bar's pinned buttons land in the Playbook bar's recording. Not
// persisted - a reload ends a recording.

const EMPTY = { recording: false, so: null, steps: [], notes: [], cps: {} };
let state = EMPTY;
const listeners = new Set();

const set = (next) => {
  state = next;
  listeners.forEach((l) => l());
};

const subscribe = (listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export const startRecording = () => set({ ...EMPTY, recording: true });
/** Stop adding clicks; the steps stay until saved or discarded. */
export const stopRecording = () => set({ ...state, recording: false });
export const clearRecording = () => set(EMPTY);
export const resetPlaybookRecorderStore = clearRecording;

/**
 * Add one click (an entry per action it ran: { action, fsp, result }).
 * The first recorded click fixes the SO - run.py drives one SO.
 */
export function recordClick(entries) {
  if (!state.recording || entries.length === 0) return;
  const first = entries[0].action;
  const so = state.so || { name: first.soName || first.soTarget, target: first.soTarget };
  const notes = [...state.notes];
  const elsewhere = entries.filter((e) => e.action.soTarget !== so.target);
  if (elsewhere.length > 0) {
    const other = elsewhere[0].action;
    notes.push(`Not recorded: "${other.label}" is on ${other.soName || other.soTarget} - a playbook drives one SO (${so.name})`);
  }
  const onTarget = entries.filter((e) => e.action.soTarget === so.target);
  const { steps, skipped } = clicksToSteps(onTarget);
  skipped.forEach((e) => notes.push(`Not recorded: "${e.action.label}" on ${e.fsp} failed (${e.result?.message})`));
  const cps = { ...state.cps };
  onTarget.forEach((e) => { if (e.action.cp) cps[e.fsp] = e.action.cp; });
  set({ ...state, so: steps.length > 0 ? so : state.so, steps: [...state.steps, ...steps], notes, cps });
}

/** The recording as a playbook, titled `title`. */
export const recordedPlaybook = (title) => ({
  name: title, so: state.so?.name, pace: '2s',
  ...(Object.keys(state.cps).length > 0 ? { cps: state.cps } : {}),
  steps: state.steps,
});

/** @returns {{recording: boolean, so: ?{name: string, target: string}, steps: Object[], notes: string[], cps: Object<string, string>}} */
export function usePlaybookRecorder() {
  return useSyncExternalStore(subscribe, () => state);
}
