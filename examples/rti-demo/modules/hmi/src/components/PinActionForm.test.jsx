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

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import PinActionForm from './PinActionForm';
import { loadActions } from '../utils/demoActions';
import { resetDemoActionsStore } from '../hooks/useDemoActions';

const so = { name: 'Demo_SO', type: 'RTI-SO', host: 'so', port: 5002, fspLinks: [{ cp: 'cp1', fsp: 'FSP_North' }] };
const read = { objRef: 'LD0/DWMX1.WMaxSpt.mxVal.f', fc: 'mx', valueType: 'FLOAT32' };
const operate = { objRef: 'LD0/DWMX1.WMaxSpt', cdc: 'APC' };

describe('PinActionForm', () => {
  beforeEach(() => {
    localStorage.clear();
    resetDemoActionsStore();
  });

  it('renders nothing without a selection to pin', () => {
    const { container } = render(<PinActionForm so={so} cp="cp1" />);
    expect(container).toBeEmptyDOMElement();
  });

  it('pins a read for the FSP behind the cp, with a default label', () => {
    render(<PinActionForm so={so} cp="cp1" read={read} />);

    fireEvent.click(screen.getByText('Pin as demo action'));
    expect(screen.getByText('FSP_North')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Pin'));

    expect(loadActions()).toEqual([expect.objectContaining({
      label: 'Read DWMX1.WMaxSpt.mxVal.f', service: 'read', soTarget: 'so:5002', soName: 'Demo_SO',
      cp: 'cp1', fspName: 'FSP_North', objRef: read.objRef, fc: 'mx',
    })]);
    expect(screen.getByText('Pinned "Read DWMX1.WMaxSpt.mxVal.f" for FSP_North')).toBeInTheDocument();
  });

  it('only offers Write for a writable FC, and needs a value for it', () => {
    const { rerender } = render(<PinActionForm so={so} cp="cp1" read={read} />);
    fireEvent.click(screen.getByText('Pin as demo action'));
    expect(screen.queryByRole('option', { name: 'Write' })).not.toBeInTheDocument();

    rerender(<PinActionForm so={so} cp="cp1" read={{ ...read, fc: 'sp' }} canWrite />);
    fireEvent.change(screen.getByLabelText('Service'), { target: { value: 'write' } });
    fireEvent.click(screen.getByText('Pin'));
    expect(screen.getByText('Enter the value to write')).toBeInTheDocument();
    expect(loadActions()).toEqual([]);
  });

  it('checks an operate value against the CDC before pinning', () => {
    render(<PinActionForm so={so} cp="cp1" operate={operate} />);
    fireEvent.click(screen.getByText('Pin as demo action'));

    fireEvent.change(screen.getByLabelText('Value'), { target: { value: 'lots' } });
    fireEvent.click(screen.getByText('Pin'));
    expect(screen.getByText('Invalid APC value. Must be a number')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Label'), { target: { value: 'Setpoint 50' } });
    fireEvent.change(screen.getByLabelText('Value'), { target: { value: '50' } });
    fireEvent.click(screen.getByText('Pin'));
    expect(loadActions()).toEqual([expect.objectContaining({ label: 'Setpoint 50', service: 'operate', cdc: 'APC', value: '50' })]);
  });

  it('warns when no registered FSP reports the cp', () => {
    render(<PinActionForm so={so} cp="cp7" read={read} />);
    fireEvent.click(screen.getByText('Pin as demo action'));
    expect(screen.getByText(/no registered FSP reports cp7/)).toBeInTheDocument();
  });
});
