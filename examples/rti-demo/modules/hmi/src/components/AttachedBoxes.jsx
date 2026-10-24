/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

// What an SO's or FSP's plugins attach (decision 0025), drawn next to it on
// Overview and Traffic: a box per item - icon for its kind, label, colour for its state -
// with its live blocks small underneath (LED dots, values, a display's text).
// Clicking a box shows its details. Every plugin's items are drawn the same
// way, as plain text: nothing here knows any one plugin.
import React, { useState } from 'react';
import { attachedItems } from '../utils/plugins';

const KIND_ICONS = {
  io: 'fa-microchip',
  ied: 'fa-industry',
  display: 'fa-tv',
  other: 'fa-cube',
};

const STATE_COLORS = {
  ok: 'var(--success-color)',
  degraded: 'var(--warning-color)',
  down: 'var(--danger-color)',
  unknown: 'var(--text-muted)',
};

const LED_COLORS = {
  green: 'var(--success-color)',
  red: 'var(--danger-color)',
  yellow: 'var(--warning-color)',
  blue: 'var(--primary-color)',
  white: '#f5f5f5',
};

function Indicators({ items }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
      {items.map((led) => (
        <span
          key={led.name}
          data-testid={`attached-led-${led.name}`}
          data-on={led.on ? 'true' : 'false'}
          title={`${led.name}: ${led.on ? 'on' : 'off'}`}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}
        >
          <span style={{
            width: '10px',
            height: '10px',
            borderRadius: '50%',
            border: '1px solid var(--border-color)',
            background: led.on ? LED_COLORS[led.color] || LED_COLORS.white : 'var(--bg-hover)',
            boxShadow: led.on ? `0 0 4px ${LED_COLORS[led.color] || LED_COLORS.white}` : 'none',
          }} />
          {led.name}
        </span>
      ))}
    </div>
  );
}

function Values({ items }) {
  return (
    <div>
      {items.map((v) => (
        <div key={v.label} style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
          <span style={{ color: 'var(--text-muted)' }}>{v.label}</span>
          <span>{v.value == null ? '-' : String(v.value)}{v.unit ? ` ${v.unit}` : ''}</span>
        </div>
      ))}
    </div>
  );
}

function Text({ lines }) {
  return (
    <div style={{
      fontFamily: 'Consolas, "Courier New", monospace',
      background: 'var(--bg-darker)',
      color: 'var(--text-primary)',
      border: '1px solid var(--border-color)',
      borderRadius: '4px',
      padding: '4px 6px',
      whiteSpace: 'pre',
      overflow: 'hidden',
      minHeight: '14px',
    }}>
      {lines.length ? lines.join('\n') : ' '}
    </div>
  );
}

const BLOCKS = { indicators: Indicators, values: Values, text: Text };

function Details({ item }) {
  const { plugin } = item;
  const rows = [
    ['Address', item.address],
    ['Detail', item.detail],
    ['Plugin', `${plugin.name}${plugin.version ? ` ${plugin.version}` : ''}${plugin.healthy ? '' : ' (unhealthy)'}`],
    ['Last error', plugin.lastError],
    ['Attached', plugin.attachedError],
  ].filter(([, value]) => value);
  return (
    <dl data-testid={`attached-details-${item.key}`} style={{ margin: '6px 0 0', display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '2px 6px' }}>
      {rows.map(([label, value]) => (
        <React.Fragment key={label}>
          <dt style={{ color: 'var(--text-muted)' }}>{label}</dt>
          <dd style={{ margin: 0, overflowWrap: 'anywhere' }}>{value}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

function AttachedBox({ item }) {
  const [open, setOpen] = useState(false);
  // The last answer, kept while the plugin couldn't say: greyed.
  const stale = item.state === 'down' || Boolean(item.plugin.attachedError);
  const toggle = () => setOpen((o) => !o);
  return (
    <div
      role="button"
      tabIndex={0}
      aria-expanded={open}
      data-testid={`attached-box-${item.key}`}
      data-state={item.state}
      onClick={toggle}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } }}
      title={`${item.label} - ${item.state}${item.plugin.attachedError ? ` (${item.plugin.attachedError})` : ''}; click for details`}
      style={{
        width: '170px',
        padding: '6px 8px',
        background: 'var(--bg-card)',
        border: '1px solid var(--border-color)',
        borderLeft: `4px solid ${STATE_COLORS[item.state] || STATE_COLORS.unknown}`,
        borderRadius: '6px',
        fontSize: '11px',
        cursor: 'pointer',
        textAlign: 'left',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, marginBottom: item.live?.length ? '4px' : 0 }}>
        <i className={`fas ${KIND_ICONS[item.kind] || KIND_ICONS.other}`} aria-hidden="true" style={{ color: STATE_COLORS[item.state] || STATE_COLORS.unknown }}></i>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.label}</span>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', opacity: stale ? 0.5 : 1 }}>
        {(item.live || []).map((block, i) => {
          const Block = BLOCKS[block.type];
          return Block ? <Block key={i} {...block} /> : null;
        })}
      </div>
      {open && <Details item={item} />}
    </div>
  );
}

/**
 * @param {Object} conn - An SO or FSP connection, with the BFF's `plugins`
 * @param {'row'|'column'} direction - Next to an FSP (column, two columns
 *   from three items on) or under the SO (row)
 */
function AttachedBoxes({ conn, direction = 'column' }) {
  const items = attachedItems(conn.plugins);
  if (!items.length) return null;
  return (
    <div
      data-testid={`attached-${conn.name}`}
      style={direction === 'row'
        ? { display: 'flex', flexWrap: 'wrap', gap: '6px', justifyContent: 'center' }
        // Next to an FSP: two columns from three items on, so a row of the
        // picture doesn't grow much taller than its circle.
        : { display: 'grid', gridTemplateColumns: items.length > 2 ? 'repeat(2, auto)' : 'auto', gap: '6px', alignItems: 'start' }}
    >
      {items.map((item) => <AttachedBox key={item.key} item={item} />)}
    </div>
  );
}

export default AttachedBoxes;
