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
  address: 'http://rti-io:9000',
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
    expect(details).toHaveTextContent('http://rti-io:9000');
    expect(details).toHaveTextContent('6 devices');
    expect(details).toHaveTextContent('io 1.0');
    expect(details).toHaveTextContent('attached timed out after 1.0s');
  });

  it('draws nothing while there is nothing attached', () => {
    const { container } = render(<AttachedBoxes conn={{ name: 'SO', plugins: null }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
