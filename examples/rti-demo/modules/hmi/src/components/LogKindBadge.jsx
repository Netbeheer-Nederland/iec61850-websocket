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

import React from 'react';

/**
 * The three kinds of log entry the SO/FSP produce (see
 * docs/rti-demo/design/logging-kinds.md): `kind` on actions-log entries
 * (system | acsi) and on messages-log frames (websocket).
 *
 * Kind is shown as an icon + label, never as a color - color already means
 * severity (ActionLogPanel's level badges), and the style guide reserves
 * status color for ok/not-ok.
 */
export const LOG_KINDS = {
  system: { label: 'System', icon: 'fa-gear', title: 'System - instance lifecycle and configuration' },
  acsi: { label: 'ACSI', icon: 'fa-cubes', title: 'ACSI service call' },
  websocket: { label: 'WebSocket', icon: 'fa-plug', title: 'WebSocket frame' },
};

// Entries from an instance that predates `kind` have none - shown without a
// badge and only matched by an "all kinds" filter.
export const kindOf = (entry) => (LOG_KINDS[entry?.kind] ? entry.kind : null);

function LogKindBadge({ kind }) {
  const def = LOG_KINDS[kind];
  if (!def) return null;
  return (
    <span
      className="log-kind-badge"
      data-kind={kind}
      title={def.title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '4px',
        fontSize: '11px',
        padding: '1px 6px',
        borderRadius: '3px',
        border: '1px solid var(--border-color)',
        color: 'var(--text-secondary)',
      }}
    >
      <i className={`fas ${def.icon}`} style={{ fontSize: '10px' }}></i>
      {def.label}
    </span>
  );
}

export default LogKindBadge;
