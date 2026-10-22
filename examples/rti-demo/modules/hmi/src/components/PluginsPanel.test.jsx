/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PluginsPanel from './PluginsPanel';

const STATUS = {
  plugins: [{ name: 'io', version: '1.2', url: 'http://rpi-io:9000/plugin', claims: ['LD0/CSWI1.Pos.Oper.ctlVal'], routes: true, healthy: true, last_error: null }],
  failed: { display: "Can't reach http://pi:8000/plugin" },
  definitions: {
    io: { url: 'http://rpi-io:9000/plugin', settings: {} },
    display: { url: 'http://pi:8000/plugin', settings: { rotate: 90 } },
  },
};

// Every call goes through the BFF's /api/execute; answers per instance path.
let calls;
function mockBff(answers = {}) {
  calls = [];
  global.fetch = vi.fn(async (url, init) => {
    const req = JSON.parse(init.body);
    calls.push(req);
    const answer = answers[`${req.method} ${req.path}`] ?? { status: 200, body: { ok: true, result: STATUS } };
    return { ok: answer.status === 200, status: answer.status, text: async () => JSON.stringify(answer.body) };
  });
}

beforeEach(() => mockBff());

describe('PluginsPanel', () => {
  it("lists the FSP's plugins, unreachable ones with the reason, and its claims", async () => {
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);

    const io = await screen.findByTestId('plugin-row-io');
    expect(within(io).getByText('Healthy')).toBeInTheDocument();
    expect(within(io).getByTitle('LD0/CSWI1.Pos.Oper.ctlVal').textContent).toBe('1');
    const display = screen.getByTestId('plugin-row-display');
    expect(within(display).getByText('Unreachable')).toBeInTheDocument();
    expect(within(display).getByText("Can't reach http://pi:8000/plugin")).toBeInTheDocument();
    expect(calls[0]).toMatchObject({ target: 'rti-fsp01:5001', method: 'GET', path: '/api/plugins' });
  });

  it('has no Controls column on the SO, whose plugins claim nothing', async () => {
    render(<PluginsPanel target="rti-so:5000" role="so" />);
    await screen.findByTestId('plugin-row-io');
    expect(screen.queryByText('Controls')).not.toBeInTheDocument();
  });

  it('follows the pushed status', async () => {
    const { rerender } = render(<PluginsPanel target="rti-fsp01:5001" role="fsp" pushed={STATUS} />);
    await screen.findByTestId('plugin-row-display');

    rerender(<PluginsPanel target="rti-fsp01:5001" role="fsp" pushed={{ plugins: STATUS.plugins, failed: {} }} />);
    await waitFor(() => expect(screen.queryByTestId('plugin-row-display')).not.toBeInTheDocument());
  });

  it("reloads a plugin by name, through the instance's management route", async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Reload display'));

    await waitFor(() => expect(calls).toContainEqual(expect.objectContaining({ method: 'POST', path: '/api/plugins/display/reload' })));
  });

  it('removes a plugin after confirming', async () => {
    const user = userEvent.setup({ delay: null });
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Remove io'));

    await waitFor(() => expect(calls).toContainEqual(expect.objectContaining({ method: 'DELETE', path: '/api/plugins/io' })));
  });

  it("adds a plugin from a URL, and shows the instance's reason when it refuses", async () => {
    mockBff({
      'POST /api/plugins': {
        status: 500,
        body: { ok: false, error: '403 Client Error: Forbidden - http://x/plugin is not allowed; add it to PLUGIN_ALLOWED_SOURCES' },
      },
    });
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await screen.findByTestId('plugin-row-io');

    await user.click(screen.getByRole('button', { name: 'Add plugin' }));
    await user.type(document.getElementById('plugins-add-name'), 'x');
    await user.type(document.getElementById('plugins-add-url'), 'http://x/plugin');
    await user.click(document.getElementById('plugins-add-settings'));
    await user.paste('{"blink_seconds": 1}');
    await user.click(document.getElementById('plugins-add-submit'));

    expect(await screen.findByRole('alert')).toHaveTextContent('Add x failed: 403 Client Error: Forbidden - http://x/plugin is not allowed');
    expect(calls).toContainEqual(expect.objectContaining({
      method: 'POST', path: '/api/plugins', body: { name: 'x', url: 'http://x/plugin', settings: { blink_seconds: 1 } },
    }));
  });

  it("edits an unreachable plugin's URL and settings, from its definition", async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Edit display'));

    const form = screen.getByRole('form', { name: 'Edit display' });
    expect(document.getElementById('plugins-add-name')).toBeDisabled();
    expect(document.getElementById('plugins-add-url')).toHaveValue('http://pi:8000/plugin');
    expect(JSON.parse(document.getElementById('plugins-add-settings').value)).toEqual({ rotate: 90 });

    await user.clear(document.getElementById('plugins-add-url'));
    await user.type(document.getElementById('plugins-add-url'), 'http://pi2:8000/plugin');
    await user.clear(document.getElementById('plugins-add-settings'));
    await user.click(within(form).getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(calls).toContainEqual(expect.objectContaining({
      method: 'PUT', path: '/api/plugins/display', body: { url: 'http://pi2:8000/plugin', settings: {} },
    })));
    await waitFor(() => expect(screen.queryByRole('form')).not.toBeInTheDocument());
  });

  it("keeps the form open with the instance's reason when an edit is refused", async () => {
    mockBff({
      'PUT /api/plugins/io': { status: 500, body: { ok: false, error: "422 Client Error - Can't reach http://x/plugin" } },
    });
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Edit io'));
    await user.click(screen.getByRole('button', { name: 'Save' }));

    expect(await screen.findByRole('alert')).toHaveTextContent("Edit io failed: 422 Client Error - Can't reach http://x/plugin");
    expect(screen.getByRole('form', { name: 'Edit io' })).toBeInTheDocument();
  });

  it("can't edit without definitions, from an older instance", async () => {
    mockBff({ 'GET /api/plugins': { status: 200, body: { ok: true, result: { plugins: STATUS.plugins, failed: {} } } } });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await screen.findByTestId('plugin-row-io');
    expect(screen.getByTitle(/^Edit io/)).toBeDisabled();
  });

  it('refuses settings that are not JSON, without calling the instance', async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await screen.findByTestId('plugin-row-io');
    await user.click(screen.getByRole('button', { name: 'Add plugin' }));
    await user.type(document.getElementById('plugins-add-name'), 'x');
    await user.type(document.getElementById('plugins-add-url'), 'http://x/plugin');
    await user.type(document.getElementById('plugins-add-settings'), 'not json');
    await user.click(document.getElementById('plugins-add-submit'));

    expect(await screen.findByRole('alert')).toHaveTextContent('Settings must be JSON');
    expect(calls.filter((c) => c.method === 'POST')).toEqual([]);
  });
});
