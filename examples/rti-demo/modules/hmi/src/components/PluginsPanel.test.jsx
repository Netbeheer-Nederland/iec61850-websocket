/*
 * SPDX-FileCopyrightText: 2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EditorView } from '@codemirror/view';
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

// The settings field is a CodeMirror editor (JsonEditor), not a textarea.
// It loads lazily, so wait for it before using it.
const settingsBox = () => screen.findByRole('textbox', { name: 'Settings (JSON)' });
const settingsEditor = () => EditorView.findFromDOM(document.querySelector('#plugins-add-settings .cm-editor'));
const settingsText = async () => { await settingsBox(); return settingsEditor().state.doc.toString(); };
const typeSettings = async (user, text) => {
  await user.click(await settingsBox());
  await user.keyboard(text.replace(/[{[]/g, '$&$&'));
};
const clearSettings = async () => {
  await settingsBox();
  act(() => {
    const view = settingsEditor();
    view.dispatch({ changes: { from: 0, to: view.state.doc.length } });
  });
};

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
    await user.click(await screen.findByTitle('Reload io'));

    await waitFor(() => expect(calls).toContainEqual(expect.objectContaining({ method: 'POST', path: '/api/plugins/io/reload' })));
  });

  it('retries an unreachable plugin now, with the same reload', async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Retry display now'));

    await waitFor(() => expect(calls).toContainEqual(expect.objectContaining({ method: 'POST', path: '/api/plugins/display/reload' })));
  });

  it('retries every plugin with a problem, and says which still fail', async () => {
    const status = { ...STATUS, plugins: [...STATUS.plugins, { name: 'leds', url: 'http://leds/plugin', claims: [], healthy: false, last_error: 'timed out' }] };
    mockBff({
      'GET /api/plugins': { status: 200, body: { ok: true, result: status } },
      'POST /api/plugins/display/reload': { status: 500, body: { ok: false, error: "422 Client Error - Can't reach http://pi:8000/plugin" } },
    });
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByRole('button', { name: 'Retry 2 plugins' }));

    expect(await screen.findByRole('alert')).toHaveTextContent("Retry failed for display: 422 Client Error - Can't reach http://pi:8000/plugin");
    expect(calls.filter((c) => c.method === 'POST').map((c) => c.path)).toEqual(['/api/plugins/leds/reload', '/api/plugins/display/reload']);
  });

  it('has no Retry button while every plugin is healthy', async () => {
    mockBff({ 'GET /api/plugins': { status: 200, body: { ok: true, result: { plugins: STATUS.plugins, failed: {} } } } });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await screen.findByTestId('plugin-row-io');
    expect(screen.queryByRole('button', { name: /^Retry \d+ plugin/ })).not.toBeInTheDocument();
  });

  it("shows a plugin's claims, routes, attached items and settings in its details", async () => {
    const status = {
      ...STATUS,
      plugins: [{ ...STATUS.plugins[0], attached: [{ kind: 'io', label: 'IO server', state: 'ok', address: 'http://rpi-io:9000' }], attached_error: 'attached timed out after 1.0s' }],
    };
    mockBff({ 'GET /api/plugins': { status: 200, body: { ok: true, result: status } } });
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Details io'));

    const details = screen.getByTestId('plugin-details-io');
    expect(details).toHaveTextContent('LD0/CSWI1.Pos.Oper.ctlVal');
    expect(details).toHaveTextContent('/api/plugins/io/');
    expect(details).toHaveTextContent('IO server');
    expect(details).toHaveTextContent('http://rpi-io:9000');
    expect(details).toHaveTextContent('attached timed out after 1.0s');

    await user.click(screen.getByTitle('Details display'));
    expect(screen.getByTestId('plugin-details-display')).toHaveTextContent('"rotate": 90');
    await user.click(screen.getByTitle('Details io'));
    expect(screen.queryByTestId('plugin-details-io')).not.toBeInTheDocument();
  });

  it('copies a plugin as a plugin configuration entry', async () => {
    const user = userEvent.setup({ delay: null });
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Copy display as configuration'));

    expect(JSON.parse(writeText.mock.calls[0][0])).toEqual({ name: 'display', url: 'http://pi:8000/plugin', settings: { rotate: 90 } });
    expect(await screen.findByRole('status')).toHaveTextContent('Copied display');
  });

  it("shows the entry to copy by hand where the browser won't copy", async () => {
    const user = userEvent.setup({ delay: null });
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('not allowed'));
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Copy io as configuration'));

    expect(JSON.parse((await screen.findByTestId('plugins-config-entry')).textContent)).toEqual({ name: 'io', url: 'http://rpi-io:9000/plugin' });
    await user.click(screen.getByTitle('Dismiss'));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
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
    await typeSettings(user, '{"blink_seconds": 1}');
    await user.click(document.getElementById('plugins-add-submit'));

    expect(await screen.findByRole('alert')).toHaveTextContent('Add x failed: 403 Client Error: Forbidden - http://x/plugin is not allowed');
    expect(calls).toContainEqual(expect.objectContaining({
      method: 'POST', path: '/api/plugins', body: { name: 'x', url: 'http://x/plugin', settings: { blink_seconds: 1 } },
    }));
  });

  it('says in the add and edit forms which URLs the instance accepts, wildcards and * included', async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByRole('button', { name: 'Add plugin' }));
    const add = screen.getByRole('form', { name: 'Add plugin' });
    expect(add.textContent).toMatch(/PLUGIN_ALLOWED_SOURCES.*http:\/\/192\.168\.0\.\*:8000.*\* for any URL/);

    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    await user.click(screen.getByTitle('Edit display'));
    const edit = screen.getByRole('form', { name: 'Edit display' });
    expect(edit.textContent).toMatch(/new URL must be allowed by .*PLUGIN_ALLOWED_SOURCES.*\* for any URL/);
  });

  it("edits an unreachable plugin's URL and settings, from its definition", async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Edit display'));

    const form = screen.getByRole('form', { name: 'Edit display' });
    expect(document.getElementById('plugins-add-name')).toBeDisabled();
    expect(document.getElementById('plugins-add-url')).toHaveValue('http://pi:8000/plugin');
    expect(JSON.parse(await settingsText())).toEqual({ rotate: 90 });

    await user.clear(document.getElementById('plugins-add-url'));
    await user.type(document.getElementById('plugins-add-url'), 'http://pi2:8000/plugin');
    await clearSettings();
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
    expect(screen.getByTitle(/^Copy io as configuration/)).toBeDisabled();
  });

  it('refuses settings that are not JSON, without calling the instance', async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await screen.findByTestId('plugin-row-io');
    await user.click(screen.getByRole('button', { name: 'Add plugin' }));
    await user.type(document.getElementById('plugins-add-name'), 'x');
    await user.type(document.getElementById('plugins-add-url'), 'http://x/plugin');
    await typeSettings(user, 'not json');
    await user.click(document.getElementById('plugins-add-submit'));

    expect(await screen.findByRole('alert')).toHaveTextContent('Settings must be JSON');
    expect(calls.filter((c) => c.method === 'POST')).toEqual([]);
  });
});
