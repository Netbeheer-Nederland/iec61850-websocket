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

import { describe, it, expect } from 'vitest';
import { linkSoToFsps } from './fspLinks';

describe('linkSoToFsps', () => {
  it('maps each cp to the FSP reporting it, null when none does', () => {
    const fsps = [
      { name: 'fsp1', accessPoints: ['cp1'], connectedClients: 1 },
      { name: 'fsp2', accessPoints: ['cp2'], connectedClients: 1 },
    ];
    expect(linkSoToFsps(['cp2', 'cp1', 'cp9'], fsps)).toEqual([
      { cp: 'cp2', fsp: 'fsp2' },
      { cp: 'cp1', fsp: 'fsp1' },
      { cp: 'cp9', fsp: null },
    ]);
  });

  it('prefers the connected FSP when several report the same cp', () => {
    const fsps = [
      { name: 'idle', accessPoints: ['cp1'], connectedClients: 0 },
      { name: 'live', accessPoints: ['cp1'], connectedClients: 1 },
    ];
    expect(linkSoToFsps(['cp1'], fsps)).toEqual([{ cp: 'cp1', fsp: 'live' }]);
  });

  it('copes with FSPs that have no accessPoints yet', () => {
    expect(linkSoToFsps(['cp1'], [{ name: 'fsp1' }])).toEqual([{ cp: 'cp1', fsp: null }]);
  });
});
