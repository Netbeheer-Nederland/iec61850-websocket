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

// usePersistentFlag.js
import { useState, useCallback } from 'react';

const readFlag = (key) => {
  if (!key) return false;
  try {
    return localStorage.getItem(key) === 'true';
  } catch {
    return false;
  }
};

// A boolean kept in localStorage under `key`, so it survives the page
// unmounting (switching pages) and reloads. Used for "the user turned
// monitoring on" - pages resume monitoring on mount while it's true.
// `key` may change (e.g. once a page resolves which instance it's showing);
// the value is then re-read from the new key. A null/empty key reads as
// false and isn't persisted. Returns [value, setValue].
export function usePersistentFlag(key) {
  const [state, setState] = useState(() => ({ key, value: readFlag(key) }));
  const value = state.key === key ? state.value : readFlag(key);

  const setValue = useCallback((next) => {
    if (key) {
      try {
        localStorage.setItem(key, String(next));
      } catch {
        // Storage unavailable (private mode, blocked) - still works for
        // this mount, just doesn't survive navigation.
      }
    }
    setState({ key, value: next });
  }, [key]);

  return [value, setValue];
}
