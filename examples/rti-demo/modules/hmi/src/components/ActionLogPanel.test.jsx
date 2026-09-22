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

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ActionLogPanel from './ActionLogPanel';

// Newest-first, matching how ACSIServer.jsx/ACSIClient.jsx actually build
// this array (each new entry prepended).
const MESSAGES = [
  { id: 3, timestamp: '10:00:02', level: 'error', message: 'Stop failed: boom' },
  { id: 2, timestamp: '10:00:01', level: 'warn', message: 'objRef is required' },
  { id: 1, timestamp: '10:00:00', level: 'info', message: 'Server started' },
];

const renderPanel = (overrides = {}) =>
  render(
    <ActionLogPanel
      messages={MESSAGES}
      isMonitoring={true}
      disabled={false}
      onStart={vi.fn()}
      onStop={vi.fn()}
      onClear={vi.fn()}
      {...overrides}
    />
  );

describe('ActionLogPanel severity', () => {
  it('renders a distinct badge for "warn" - not the default/info styling', () => {
    // Regression test: the inline implementations this replaces checked
    // msg.level === 'warning', but fsp/acsi_server.py's _log_action only
    // ever sends "warn" - so warnings always rendered with default/info
    // styling. warn must get its own color, distinct from both info and
    // error.
    renderPanel();
    const badges = screen.getAllByText(/^(error|warn|info)$/);
    const warnBadge = badges.find((b) => b.textContent === 'warn');
    const infoBadge = badges.find((b) => b.textContent === 'info');
    const errorBadge = badges.find((b) => b.textContent === 'error');
    expect(warnBadge.style.color).not.toBe(infoBadge.style.color);
    expect(warnBadge.style.color).not.toBe(errorBadge.style.color);
  });

  it('shows a per-severity count summary in the header', () => {
    renderPanel();
    expect(screen.getByText(/3 total/)).toBeInTheDocument();
    expect(screen.getByText(/1 error/)).toBeInTheDocument();
    expect(screen.getByText(/1 warning/)).toBeInTheDocument();
  });

  it('treats an unrecognized level as info, not a crash', () => {
    renderPanel({ messages: [{ id: 1, timestamp: '10:00:00', level: 'bogus', message: 'x' }] });
    expect(screen.getByText('info')).toBeInTheDocument();
  });
});

describe('ActionLogPanel filtering', () => {
  it('filters to only the selected severity', async () => {
    const user = userEvent.setup({ delay: null });
    renderPanel();

    await user.selectOptions(screen.getByTitle('Filter by severity'), 'error');

    expect(screen.getByText('Stop failed: boom')).toBeInTheDocument();
    expect(screen.queryByText('objRef is required')).not.toBeInTheDocument();
    expect(screen.queryByText('Server started')).not.toBeInTheDocument();
  });

  it('shows a distinct empty-state message when the filter excludes everything', async () => {
    const user = userEvent.setup({ delay: null });
    renderPanel({ messages: [MESSAGES[2]] }); // only the info entry

    await user.selectOptions(screen.getByTitle('Filter by severity'), 'error');

    expect(screen.getByText(/No messages match the selected severity filter/)).toBeInTheDocument();
  });
});

describe('ActionLogPanel sorting', () => {
  it('defaults to newest-first (the order messages are passed in)', () => {
    renderPanel();
    const rows = screen.getAllByText(/^#\d+ -/).map((el) => el.textContent);
    expect(rows).toEqual(['#3 - 10:00:02', '#2 - 10:00:01', '#1 - 10:00:00']);
  });

  it('reverses to oldest-first on toggle, without mutating the messages prop', async () => {
    const user = userEvent.setup({ delay: null });
    renderPanel();

    await user.click(screen.getByTitle(/Showing newest first/));

    const rows = screen.getAllByText(/^#\d+ -/).map((el) => el.textContent);
    expect(rows).toEqual(['#1 - 10:00:00', '#2 - 10:00:01', '#3 - 10:00:02']);
    expect(MESSAGES.map((m) => m.id)).toEqual([3, 2, 1]); // unchanged
  });
});

describe('ActionLogPanel controls', () => {
  it('wires Start/Stop/Clear to the given callbacks and disabled state', async () => {
    const onStart = vi.fn();
    const onStop = vi.fn();
    const onClear = vi.fn();
    const user = userEvent.setup({ delay: null });
    renderPanel({ isMonitoring: false, onStart, onStop, onClear });

    expect(document.getElementById('messages-stop-btn')).toBeDisabled();
    await user.click(document.getElementById('messages-start-btn'));
    expect(onStart).toHaveBeenCalledTimes(1);

    await user.click(document.getElementById('messages-clear-btn'));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it('disables Start and Clear when disabled=true', () => {
    renderPanel({ disabled: true, isMonitoring: false });
    expect(document.getElementById('messages-start-btn')).toBeDisabled();
    expect(document.getElementById('messages-clear-btn')).toBeDisabled();
  });

  it('does not render the message list at all while not monitoring', () => {
    renderPanel({ isMonitoring: false });
    expect(screen.queryByText('Protocol Messages')).not.toBeInTheDocument();
  });
});
