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

import { useSyncExternalStore, useCallback } from 'react';
import { loadActions, saveActions } from '../utils/demoActions';

// One store for the whole page, so an action pinned in a Data Access Panel
// shows up on Traffic's demo bar straight away.
let actions = null;
const listeners = new Set();

const current = () => {
  if (actions === null) actions = loadActions();
  return actions;
};

const update = (next) => {
  actions = next;
  saveActions(next);
  listeners.forEach((l) => l());
};

const subscribe = (listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

/** Forget the in-memory copy, so the next read comes from localStorage (tests). */
export const resetDemoActionsStore = () => {
  actions = null;
};

let nextId = 0;
const newId = () => `${Date.now().toString(36)}-${(nextId += 1)}`;

/**
 * The pinned demo actions (utils/demoActions.js), with add / remove.
 * @returns {{actions: Object[], addAction: Function, removeAction: Function}}
 */
export function useDemoActions() {
  const list = useSyncExternalStore(subscribe, current);
  const addAction = useCallback((action) => update([...current(), { ...action, id: newId() }]), []);
  const removeAction = useCallback((id) => update(current().filter((a) => a.id !== id)), []);
  return { actions: list, addAction, removeAction };
}
