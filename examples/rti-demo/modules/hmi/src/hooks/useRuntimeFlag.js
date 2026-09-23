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

// useRuntimeFlag.js
import { useState, useCallback, useEffect } from 'react';
import { executeApiCall } from '../services/apiService';

// Whether an instance (e.g. "rti-so:5002") currently has a feature turned on,
// per its own runtime API (`apiId`, via the BFF's /api/execute) - not what's
// saved in connections.json, which can differ (e.g. after an instance
// restart). Returns [enabled, refresh]; call refresh after changing it.
export function useRuntimeFlag(apiId, field, target) {
  const [enabled, setEnabled] = useState(false);

  const refresh = useCallback(async () => {
    if (!target) return;
    try {
      const result = await executeApiCall(apiId, target);
      if (result?.ok) {
        setEnabled(Boolean(result.payload?.result?.[field] ?? result.payload?.[field]));
      }
    } catch (error) {
      console.error(`Failed to fetch ${apiId}:`, error);
    }
  }, [apiId, field, target]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return [enabled, refresh];
}
