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

import React, { useState, useMemo } from 'react';
import { buildTimeline } from '../utils/timeline';

// Same colors as the topology's link pulses (InstanceVisualization).
const TYPE_COLORS = {
  call: 'var(--primary-color)',
  report: 'var(--warning-color)',
  local: 'var(--text-secondary)',
};
const TYPE_LABELS = { call: 'Calls', report: 'Reports', local: 'Local' };
const UNKNOWN_LANE = '?';
// Rows rendered at most (newest kept); the hook keeps more.
const MAX_ROWS = 300;
const MONO = { fontFamily: 'Consolas, "Courier New", monospace' };

const levelMark = (level) => {
  if (level === 'error') return { mark: '✗', color: 'var(--danger-color)', title: 'Failed' };
  if (level === 'warn') return { mark: '…', color: 'var(--warning-color)', title: 'No response' };
  return { mark: '✓', color: 'var(--success-color)', title: 'Ok' };
};

// A horizontal arrow across the lanes it spans; `towards` is the side its
// head is on.
function Arrow({ color, towards, label, sub, lanes = 1 }) {
  // The arrow's grid area spans `lanes` equal lanes; inset it by half a lane
  // each side so it runs lifeline to lifeline.
  const inset = `calc(100% / ${2 * lanes})`;
  const head = {
    position: 'absolute',
    top: '50%',
    marginTop: '-5px',
    width: 0,
    height: 0,
    borderTop: '5px solid transparent',
    borderBottom: '5px solid transparent',
    ...(towards === 'right'
      ? { right: 0, borderLeft: `8px solid ${color}` }
      : { left: 0, borderRight: `8px solid ${color}` }),
  };
  return (
    <div style={{ padding: '2px 0', marginLeft: inset, marginRight: inset }}>
      <div style={{ display: 'flex', justifyContent: 'center', gap: '6px', fontSize: '12px', whiteSpace: 'nowrap', overflow: 'hidden' }}>
        {label}
      </div>
      <div style={{ position: 'relative', height: '10px' }}>
        <div style={{ position: 'absolute', top: '4px', left: 0, right: 0, height: '2px', background: color }} />
        <span style={head} />
      </div>
      {sub && <div style={{ textAlign: 'center', fontSize: '10px', color: 'var(--text-muted)' }}>{sub}</div>}
    </div>
  );
}

function FrameList({ title, frames, emptyText }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div style={{ fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '4px' }}>{title}</div>
      {frames.length === 0 ? (
        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{emptyText}</div>
      ) : frames.map((f) => (
        <div key={f.id} className="timeline-frame" style={{ ...MONO, fontSize: '11px', display: 'flex', gap: '8px', whiteSpace: 'nowrap' }}>
          <span style={{ color: 'var(--text-muted)' }}>#{f.id}</span>
          <span style={{ color: 'var(--text-muted)' }}>{f.time || f.timestamp}</span>
          <span>{f.direction}</span>
          <span>{f.category}</span>
          <span style={{ color: f.level === 'error' ? 'var(--danger-color)' : 'var(--text-secondary)' }}>{f.service_type || f.service}</span>
          {f.invokeId != null && <span style={{ color: 'var(--text-muted)' }}>invokeId {f.invokeId}</span>}
        </div>
      ))}
    </div>
  );
}

/**
 * Traffic's merged timeline: every SO-FSP exchange in one list, laid out
 * as a sequence diagram - a lane per SO and FSP, a call as an arrow from the
 * SO to the FSP it went to, a report as an arrow back, an FSP's local ACSI
 * entry as a box in its lane. Expanding a row shows the frames on both
 * ends. See utils/timeline.js for how the rows are paired.
 *
 * @param {Object} timeline - useTrafficTimeline's result (Traffic owns it, so
 *   the report values table reads the same entries)
 * @param {string|null} focusedFsp - only this FSP's lane and rows are shown
 * @param {Function} onFocusFsp - called with an FSP name (or null) from a lane header
 */
function TrafficTimeline({ timeline, focusedFsp = null, onFocusFsp = null }) {
  const { sos, fsps, stores, running, start, stop, clear } = timeline;
  const [types, setTypes] = useState({ call: true, report: true, local: true });
  const [expandedKey, setExpandedKey] = useState(null);

  const allRows = useMemo(() => buildTimeline({ sos, fsps, stores }), [sos, fsps, stores]);
  const counts = useMemo(() => allRows.reduce((acc, r) => ({ ...acc, [r.type]: (acc[r.type] || 0) + 1 }), {}), [allRows]);

  const rows = useMemo(() => allRows
    .filter((r) => types[r.type])
    .filter((r) => !focusedFsp || r.fsp === focusedFsp)
    .slice(-MAX_ROWS)
    .reverse(), [allRows, types, focusedFsp]);

  const fspLanes = focusedFsp ? fsps.filter((f) => f.name === focusedFsp) : fsps;
  const lanes = [
    ...sos.map((s) => ({ name: s.name, kind: 'so' })),
    ...fspLanes.map((f) => ({ name: f.name, kind: 'fsp', cp: f.accessPoints?.[0] })),
    ...(rows.some((r) => r.type === 'call' && !r.fsp) ? [{ name: UNKNOWN_LANE, kind: 'unknown' }] : []),
  ];
  const laneIndex = (name) => {
    const i = lanes.findIndex((l) => l.name === (name ?? UNKNOWN_LANE));
    return i < 0 ? 0 : i;
  };
  const gridTemplateColumns = `84px repeat(${Math.max(lanes.length, 1)}, minmax(110px, 1fr))`;
  const span = (a, b) => `${2 + Math.min(a, b)} / ${3 + Math.max(a, b)}`;

  const renderSegment = (row) => {
    const soLane = laneIndex(row.so);
    const fspLane = laneIndex(row.fsp);
    if (row.type === 'local') {
      const { mark, color, title } = levelMark(row.level);
      return (
        <div style={{ gridColumn: span(fspLane, fspLane), justifySelf: 'center', maxWidth: '100%', background: 'var(--bg-card)', position: 'relative', border: '1px dashed var(--border-color)', borderRadius: '4px', padding: '2px 6px', fontSize: '12px', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }} title={row.message}>
          {row.service || 'local'} <span style={{ color }} title={title}>{mark}</span>
          <span style={{ color: 'var(--text-muted)', fontSize: '10px', marginLeft: '6px' }}>local</span>
        </div>
      );
    }
    if (row.type === 'report') {
      return (
        <div style={{ gridColumn: span(soLane, fspLane) }}>
          <Arrow
            lanes={Math.abs(soLane - fspLane) + 1}
            color={TYPE_COLORS.report}
            towards={soLane < fspLane ? 'left' : 'right'}
            label={<><i className="fas fa-flag" style={{ fontSize: '10px', color: TYPE_COLORS.report }}></i><span>{row.service}</span></>}
          />
        </div>
      );
    }
    const { mark, color, title } = levelMark(row.level);
    const failed = row.level === 'error';
    return (
      <div style={{ gridColumn: span(soLane, fspLane) }}>
        <Arrow
          lanes={Math.abs(soLane - fspLane) + 1}
          color={failed ? 'var(--danger-color)' : TYPE_COLORS.call}
          towards={soLane < fspLane ? 'right' : 'left'}
          label={<><span>{row.service}</span><span style={{ color }} title={title}>{mark}</span>{!row.fsp && <span style={{ color: 'var(--text-muted)' }}>{row.cp} (no FSP)</span>}</>}
          sub={`SO ${row.soFrames.length} · FSP ${row.fspFrames.length} frame${row.fspFrames.length === 1 ? '' : 's'}`}
        />
      </div>
    );
  };

  return (
    <div className="traffic-timeline">
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', marginBottom: '12px', fontSize: '12px' }}>
        {running ? (
          <button className="btn-secondary" style={{ padding: '3px 10px', fontSize: '12px' }} onClick={stop} title="Stop following traffic">
            <i className="fas fa-pause" style={{ fontSize: '11px', marginRight: '4px' }}></i>Stop
          </button>
        ) : (
          <button className="btn-secondary" style={{ padding: '3px 10px', fontSize: '12px' }} onClick={start} title="Follow traffic">
            <i className="fas fa-play" style={{ fontSize: '11px', marginRight: '4px' }}></i>Start
          </button>
        )}
        <button className="btn-secondary" style={{ padding: '3px 10px', fontSize: '12px' }} onClick={clear} title="Empty this timeline (the instances' logs are kept)">
          <i className="fas fa-eraser" style={{ fontSize: '11px', marginRight: '4px' }}></i>Clear
        </button>
        <span style={{ flex: 1 }} />
        {Object.keys(TYPE_LABELS).map((type) => (
          <label key={type} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', cursor: 'pointer', color: TYPE_COLORS[type] }}>
            <input
              type="checkbox"
              checked={types[type]}
              onChange={() => setTypes((prev) => ({ ...prev, [type]: !prev[type] }))}
            />
            {TYPE_LABELS[type]} ({counts[type] || 0})
          </label>
        ))}
      </div>

      <div style={{ position: 'relative' }}>
      {/* A lifeline down the middle of each lane, behind the rows. */}
      {rows.length > 0 && lanes.map((lane, i) => (
        <div
          key={`lifeline-${lane.name}`}
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: '28px',
            bottom: 0,
            left: `calc(84px + (100% - 84px) * ${(2 * i + 1) / (2 * lanes.length)})`,
            borderLeft: '1px dashed var(--border-color)',
          }}
        />
      ))}
      <div style={{ position: 'relative', display: 'grid', gridTemplateColumns, columnGap: '0', rowGap: '2px', alignItems: 'center' }}>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Time</div>
        {lanes.map((lane) => (
          <div
            key={lane.name}
            data-testid={`timeline-lane-${lane.name}`}
            style={{ textAlign: 'center', fontSize: '12px', fontWeight: 600, padding: '4px', borderBottom: '2px solid var(--border-color)', cursor: lane.kind === 'fsp' && onFocusFsp ? 'pointer' : 'default' }}
            onClick={() => lane.kind === 'fsp' && onFocusFsp?.(focusedFsp === lane.name ? null : lane.name)}
            title={lane.kind === 'fsp' ? (focusedFsp === lane.name ? 'Show all FSPs' : `Only ${lane.name}`) : undefined}
          >
            {lane.kind === 'unknown' ? 'No FSP' : lane.name}
            {lane.cp && <span style={{ ...MONO, fontWeight: 400, color: 'var(--text-muted)', marginLeft: '6px' }}>{lane.cp}</span>}
          </div>
        ))}

        {rows.map((row) => (
          <React.Fragment key={row.key}>
            <div
              data-testid="timeline-row"
              data-type={row.type}
              onClick={() => setExpandedKey((prev) => (prev === row.key ? null : row.key))}
              style={{ display: 'contents', cursor: 'pointer' }}
            >
              {/* Explicit column 1, so each row's time starts a new grid row
                  instead of filling a lane the previous row left empty. */}
              <div style={{ gridColumn: '1', ...MONO, fontSize: '11px', color: 'var(--text-muted)', cursor: 'pointer' }}>{row.time}</div>
              {renderSegment(row)}
            </div>
            {expandedKey === row.key && (
              <div style={{ gridColumn: '1 / -1', background: 'var(--bg-hover)', borderRadius: '4px', padding: '8px', margin: '2px 0 6px' }}>
                {row.message && <div style={{ fontSize: '12px', marginBottom: '6px' }}>{row.message}</div>}
                {row.type === 'call' ? (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <FrameList
                      title={`${row.so} (SO)`}
                      frames={row.soFrames}
                      emptyText={row.hasCorrelation ? 'Its frames are not in this view (logged before the timeline started, or cleared).' : 'No frame range recorded for this call.'}
                    />
                    <FrameList
                      title={`${row.fsp || 'No FSP'} (FSP)`}
                      frames={row.fspFrames}
                      emptyText={row.fsp ? 'No matching frames on the FSP side yet (cp + invokeId).' : `No registered FSP reports cp ${row.cp}.`}
                    />
                  </div>
                ) : row.type === 'report' ? (
                  <FrameList title={`${row.fsp} (FSP)`} frames={row.fspFrames} emptyText="" />
                ) : (
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Served by the FSP itself - no frames.</div>
                )}
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
      </div>

      {rows.length === 0 && (
        <p style={{ color: 'var(--text-muted)', fontSize: '12px', textAlign: 'center', margin: '16px 0 4px' }}>
          {running
            ? 'No traffic yet. Run a demo action or a Data Access Panel service, or trigger a report on an FSP.'
            : 'Timeline stopped. Start to follow the traffic between the SO and its FSPs.'}
        </p>
      )}
    </div>
  );
}

export default TrafficTimeline;
