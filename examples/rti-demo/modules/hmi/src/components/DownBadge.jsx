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

import React from 'react';

const LABELS = { 'link-down': 'link down', unreachable: 'unreachable' };

/**
 * "link down" / "unreachable" next to a dropped FSP's name on Traffic
 * (useFspPresence's state); nothing while it's up or unknown.
 */
function DownBadge({ state }) {
  if (!LABELS[state]) return null;
  return (
    <span
      className="down-badge"
      style={{
        marginLeft: '6px', fontSize: '10px', fontWeight: 600, color: 'var(--danger-color)',
        border: '1px solid var(--danger-color)', borderRadius: '3px', padding: '0 4px',
      }}
    >
      {LABELS[state]}
    </span>
  );
}

export default DownBadge;
