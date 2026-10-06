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

import React, { useMemo } from 'react';
import { buildReportValues } from '../utils/reports';
import DownBadge from './DownBadge';

const MONO = { fontFamily: 'Consolas, "Courier New", monospace' };
const cell = { padding: '3px 8px', borderBottom: '1px solid var(--border-color)', textAlign: 'left' };

/**
 * What the SO has received by report, per FSP: the latest value of every
 * data attribute its reports carried (utils/reports.js). Values the newest
 * report changed are highlighted. Reads the same entries as the timeline -
 * Stop / Clear there apply here too.
 *
 * @param {Object} timeline - useTrafficTimeline's result
 * @param {string|null} focusedFsp - only this FSP's values are shown
 * @param {Object|null} presence - useFspPresence's result: a dropped FSP's last
 *   values stay, dimmed and marked
 */
function ReportValues({ timeline, focusedFsp = null, presence = null }) {
  const { sos, fsps, stores, running } = timeline;
  const groups = useMemo(() => buildReportValues({ sos, fsps, stores }), [sos, fsps, stores]);
  const visible = focusedFsp ? groups.filter((g) => g.fsp === focusedFsp) : groups;

  if (visible.length === 0) {
    return (
      <p style={{ color: 'var(--text-muted)', fontSize: '12px', margin: 0 }}>
        {running
          ? 'No reports received by the SO yet. Enable a report (e.g. an Enable report demo action), then change a value on the FSP.'
          : 'The timeline is stopped - start it to follow the reports the SO receives.'}
      </p>
    );
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '16px' }}>
      {visible.map((group) => {
        const state = presence?.byName[group.fsp]?.state;
        const down = Boolean(state && state !== 'up');
        return (
        <div key={group.fsp} data-testid={`report-values-${group.fsp}`} style={{ minWidth: 0, opacity: down ? 0.55 : 1 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '6px', fontSize: '12px' }}>
            <strong>{group.fsp}</strong>
            {group.cp && <span style={{ ...MONO, color: 'var(--text-muted)' }}>{group.cp}</span>}
            <DownBadge state={state} />
            {down && <span style={{ color: 'var(--text-muted)' }}>last known values</span>}
            <span style={{ color: 'var(--text-muted)' }}>
              {group.reports} report{group.reports === 1 ? '' : 's'}{group.lastTime ? ` · last ${group.lastTime}` : ''}
            </span>
          </div>
          {group.values.length === 0 ? (
            <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              {group.undecoded > 0 ? 'Its reports are BER-encoded - their values aren’t decoded here.' : 'Its reports carried no values.'}
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr style={{ color: 'var(--text-muted)' }}>
                  <th style={cell}>Data attribute</th>
                  <th style={cell}>Value</th>
                  <th style={cell}>Report</th>
                  <th style={cell}>Time</th>
                </tr>
              </thead>
              <tbody>
                {group.values.map((v) => (
                  <tr
                    key={v.dataRef}
                    data-latest={v.latest ? 'true' : 'false'}
                    style={{ background: v.latest ? 'var(--bg-hover)' : 'transparent' }}
                  >
                    <td style={{ ...cell, ...MONO, wordBreak: 'break-all' }}>{v.dataRef}</td>
                    <td style={{ ...cell, ...MONO, fontWeight: v.latest ? 700 : 400, color: v.latest ? 'var(--warning-color)' : 'var(--text-primary)' }} title={v.detail ? `${v.type}: ${v.detail}` : v.type}>{v.text}</td>
                    <td style={{ ...cell, color: 'var(--text-secondary)' }}>{v.rptID}</td>
                    <td style={{ ...cell, ...MONO, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{v.time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        );
      })}
    </div>
  );
}

export default ReportValues;
