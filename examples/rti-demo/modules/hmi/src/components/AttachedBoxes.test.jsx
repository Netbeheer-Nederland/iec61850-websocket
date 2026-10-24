/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AttachedBoxes from './AttachedBoxes';

const IO = {
  kind: 'io',
  label: 'IO server',
  address: 'http://rpi-io:9000',
  state: 'ok',
  detail: '6 devices',
  live: [
    { type: 'indicators', items: [{ name: 'led1', on: true, color: 'green' }, { name: 'led2', on: false, color: 'red' }] },
    { type: 'values', items: [{ label: 'pot1', value: 42, unit: '%' }, { label: 'button1', value: null, unit: null }] },
  ],
};
const LCD = { kind: 'display', label: 'lcd1', state: 'down', live: [{ type: 'text', lines: ['FSP Connected: cp1', '<b>x</b>'] }] };

const conn = (attached, extra = {}) => ({
  name: 'FSP01',
  plugins: { plugins: [{ name: 'io', version: '1.0', healthy: true, last_error: null, attached_error: null, attached, ...extra }], failed: {} },
});

describe('AttachedBoxes', () => {
  it('draws a box per item, with its live blocks', () => {
    render(<AttachedBoxes conn={conn([IO, LCD])} />);

    const io = screen.getByTestId('attached-box-io:0');
    expect(io).toHaveAttribute('data-state', 'ok');
    expect(io).toHaveTextContent('IO server');
    expect(screen.getByTestId('attached-led-led1')).toHaveAttribute('data-on', 'true');
    expect(screen.getByTestId('attached-led-led2')).toHaveAttribute('data-on', 'false');
    expect(io).toHaveTextContent('pot142 %');
    expect(io).toHaveTextContent('button1-');

    const lcd = screen.getByTestId('attached-box-io:1');
    expect(lcd).toHaveAttribute('data-state', 'down');
    // Plain text, never HTML.
    expect(lcd).toHaveTextContent('<b>x</b>');
    expect(lcd.querySelector('b')).toBeNull();
  });

  it('shows the details on a click', () => {
    render(<AttachedBoxes conn={conn([IO], { attached_error: 'attached timed out after 1.0s' })} />);
    expect(screen.queryByTestId('attached-details-io:0')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('attached-box-io:0'));

    const details = screen.getByTestId('attached-details-io:0');
    expect(details).toHaveTextContent('http://rpi-io:9000');
    expect(details).toHaveTextContent('6 devices');
    expect(details).toHaveTextContent('io 1.0');
    expect(details).toHaveTextContent('attached timed out after 1.0s');
  });

  it("colours each box's left edge for its plugin's state, the icon for the item's own", () => {
    render(<AttachedBoxes conn={conn([IO, LCD])} />);
    const lcd = screen.getByTestId('attached-box-io:1');
    expect(lcd).toHaveAttribute('data-plugin-state', 'healthy');
    expect(lcd.style.borderLeft).toContain('var(--success-color)');
    expect(lcd.querySelector('i').style.color).toBe('var(--danger-color)');
  });

  it('is orange while the plugin is unhealthy or not answering /attached', () => {
    const { unmount } = render(<AttachedBoxes conn={conn([IO], { healthy: false, last_error: 'boom' })} />);
    expect(screen.getByTestId('attached-box-io:0').style.borderLeft).toContain('var(--warning-color)');
    unmount();
    render(<AttachedBoxes conn={conn([IO], { attached_error: 'timed out' })} />);
    expect(screen.getByTestId('attached-box-io:0')).toHaveAttribute('data-plugin-state', 'stale');
    expect(screen.getByTestId('attached-box-io:0').style.borderLeft).toContain('var(--warning-color)');
  });

  it('draws a red Disconnected box for a plugin that can\'t be reached', () => {
    render(<AttachedBoxes conn={{ name: 'FSP01', plugins: { plugins: [], failed: { sim_leds: "Can't reach http://sim-leds:8099/plugin" } } }} />);
    const box = screen.getByTestId('attached-box-sim_leds:disconnected');
    expect(box).toHaveTextContent('sim_leds');
    expect(box).toHaveTextContent('Disconnected');
    expect(box.style.borderLeft).toContain('var(--danger-color)');
    expect(box.title).toBe("Plugin sim_leds: disconnected - Can't reach http://sim-leds:8099/plugin; click for details");
  });

  it('draws nothing while there is nothing attached', () => {
    const { container } = render(<AttachedBoxes conn={{ name: 'SO', plugins: null }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
