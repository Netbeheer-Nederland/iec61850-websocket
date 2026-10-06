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

import React, { useState } from 'react';
import { useDemoActions } from '../hooks/useDemoActions';
import { recordClick } from '../hooks/usePlaybookRecorder';
import { runAction, groupByLabel } from '../utils/demoActions';
import { buildTargetValue } from '../services/apiService';
import DownBadge from './DownBadge';

const SERVICE_ICONS = {
  read: 'fa-eye', write: 'fa-pen', operate: 'fa-bolt', 'enable-report': 'fa-flag', 'disable-report': 'fa-ban',
};

/**
 * Traffic's demo bar: the actions pinned from Data Access Panels
 * (utils/demoActions.js) as one-click buttons, a row per FSP, plus an
 * "All FSPs" button for every label pinned on more than one FSP - it runs
 * them all at once (the SO serializes its ACSI calls, so they go out one
 * after another; the timeline shows each).
 *
 * @param {Object[]} connections - enriched connections (App.jsx)
 * @param {string|null} focusedFsp - only this FSP's row is shown
 * @param {Object|null} presence - useFspPresence's result, to mark a dropped FSP's row
 */
function DemoActionsBar({ connections = [], focusedFsp = null, presence = null }) {
  const { actions, removeAction } = useDemoActions();
  // action id -> 'running' | { ok, message }
  const [results, setResults] = useState({});
  const [editing, setEditing] = useState(false);

  const connectedSos = new Map(connections
    .filter((c) => c.type === 'RTI-SO' && c.status === 'connected' && c.host && c.port)
    .map((c) => [buildTargetValue(c.host, c.port), c]));

  // The FSP an action reaches now - its SO's current link for the cp, else
  // the FSP it was pinned for.
  const fspOf = (action) => {
    const so = connectedSos.get(action.soTarget);
    return (so?.fspLinks || []).find((l) => l.cp === action.cp)?.fsp || action.fspName || `cp ${action.cp}`;
  };
  const isLive = (action) => {
    const so = connectedSos.get(action.soTarget);
    return Boolean(so && (so.fspLinks || []).some((l) => l.cp === action.cp));
  };

  // Runs the actions of one click; while a playbook is being recorded, the
  // click is added to it once every action has answered.
  const run = async (list) => {
    const fsps = list.map(fspOf);
    setResults((prev) => ({ ...prev, ...Object.fromEntries(list.map((a) => [a.id, 'running'])) }));
    const answers = await Promise.all(list.map(async (a) => {
      const result = await runAction(a);
      setResults((prev) => ({ ...prev, [a.id]: result }));
      return result;
    }));
    recordClick(list.map((action, i) => ({ action, fsp: fsps[i], result: answers[i] })));
  };

  if (actions.length === 0) {
    return (
      <p style={{ color: 'var(--text-muted)', fontSize: '12px', margin: 0 }}>
        No demo actions yet. In a Data Access Panel, pick the SO, a cp and a data object, then use
        {' '}<strong>Pin as demo action</strong>. Give the actions on different FSPs the same label to run them
        together from <strong>All FSPs</strong>.
      </p>
    );
  }

  const rows = new Map();
  actions.forEach((a) => {
    const fsp = fspOf(a);
    if (!rows.has(fsp)) rows.set(fsp, { cp: a.cp, actions: [] });
    rows.get(fsp).actions.push(a);
  });
  const visibleRows = [...rows.entries()].filter(([fsp]) => !focusedFsp || fsp === focusedFsp);
  const shared = groupByLabel(actions).filter((g) => new Set(g.actions.map(fspOf)).size > 1);

  const resultMark = (id) => {
    const r = results[id];
    if (r === 'running') return <i className="fas fa-spinner fa-spin" style={{ fontSize: '10px' }}></i>;
    if (!r) return null;
    return r.ok
      ? <span style={{ color: 'var(--success-color)' }}>{'✓'}</span>
      : <span style={{ color: 'var(--danger-color)' }}>{'✗'}</span>;
  };

  const buttonStyle = { padding: '4px 10px', fontSize: '12px' };

  return (
    <div className="demo-actions-bar" style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        {shared.length > 0 && <span style={{ color: 'var(--text-secondary)', fontWeight: 600, minWidth: '140px' }}>All FSPs</span>}
        {shared.map((g) => {
          const live = g.actions.filter(isLive);
          const running = g.actions.some((a) => results[a.id] === 'running');
          return (
            <button
              key={`all-${g.label}`}
              className="btn-primary"
              style={buttonStyle}
              disabled={live.length === 0 || running}
              onClick={() => run(live)}
              title={`Run "${g.label}" on ${live.map(fspOf).join(', ') || 'no connected FSP'}`}
            >
              {g.label} ({live.length})
            </button>
          );
        })}
        <span style={{ flex: 1 }} />
        <button
          className="btn-secondary"
          style={buttonStyle}
          onClick={() => setEditing((e) => !e)}
          title={editing ? 'Done removing actions' : 'Remove pinned actions'}
        >
          <i className={`fas ${editing ? 'fa-check' : 'fa-pen'}`} style={{ fontSize: '11px' }}></i>{editing ? 'Done' : 'Edit'}
        </button>
      </div>

      {visibleRows.map(([fsp, row]) => (
        <div key={fsp} data-testid={`demo-row-${fsp}`} style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ minWidth: '140px', fontWeight: 600 }}>
            {fsp}
            <span style={{ fontFamily: 'Consolas, "Courier New", monospace', fontWeight: 400, color: 'var(--text-muted)', marginLeft: '6px' }}>{row.cp}</span>
            <DownBadge state={presence?.byName[fsp]?.state} />
          </span>
          {row.actions.map((a) => {
            const live = isLive(a);
            const result = results[a.id];
            return (
              <span key={a.id} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                <button
                  className="btn-secondary"
                  style={buttonStyle}
                  disabled={!live || result === 'running'}
                  onClick={() => run([a])}
                  title={`${a.service} ${a.objRef}${a.value !== undefined ? ` = ${a.value}` : ''} via ${a.soName || a.soTarget}${live ? '' : ' - SO or FSP not connected'}${result && result !== 'running' && !result.ok ? `\nLast run failed: ${result.message}` : ''}`}
                >
                  <i className={`fas ${SERVICE_ICONS[a.service]}`} style={{ fontSize: '10px' }}></i>
                  {a.label}
                  {resultMark(a.id)}
                </button>
                {editing && (
                  <button
                    className="btn-secondary"
                    style={{ padding: '2px 6px', fontSize: '11px' }}
                    onClick={() => removeAction(a.id)}
                    title={`Unpin "${a.label}"`}
                  >
                    <i className="fas fa-times"></i>
                  </button>
                )}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export default DemoActionsBar;
