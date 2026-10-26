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
  plugins: [{ name: 'io', version: '1.2', url: 'http://dr-panel:9000/plugin', claims: ['LD0/CSWI1.Pos.Oper.ctlVal'], routes: true, healthy: true, last_error: null }],
  failed: { display: "Can't reach http://pi:8000/plugin" },
  definitions: {
    io: { url: 'http://dr-panel:9000/plugin', settings: {} },
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
      plugins: [{ ...STATUS.plugins[0], attached: [{ kind: 'io', label: 'IO server', state: 'ok', address: 'http://dr-panel:9000' }], attached_error: 'attached timed out after 1.0s' }],
    };
    mockBff({ 'GET /api/plugins': { status: 200, body: { ok: true, result: status } } });
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Details io'));

    const details = screen.getByTestId('plugin-details-io');
    expect(details).toHaveTextContent('LD0/CSWI1.Pos.Oper.ctlVal');
    expect(details).toHaveTextContent('/api/plugins/io/');
    expect(details).toHaveTextContent('IO server');
    expect(details).toHaveTextContent('http://dr-panel:9000');
    expect(details).toHaveTextContent('attached timed out after 1.0s');

    await user.click(screen.getByTitle('Details display'));
    expect(screen.getByTestId('plugin-details-display')).toHaveTextContent('"rotate": 90');
    await user.click(screen.getByTitle('Details io'));
    expect(screen.queryByTestId('plugin-details-io')).not.toBeInTheDocument();
  });

  it('sends a request to a plugin route from its details, and shows the answer', async () => {
    mockBff({ 'GET /api/plugins/io/leds/1?on=1&color=red': { status: 200, body: { ok: true, result: { leds: [{ name: 'red', on: true }] } } } });
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Details io'));

    const form = screen.getByRole('form', { name: 'Request to io' });
    await user.type(within(form).getByLabelText('Path'), 'leds/1');
    await user.type(within(form).getByLabelText('Query'), 'on=1&color=red');
    await user.click(within(form).getByRole('button', { name: 'Send' }));

    const answer = await screen.findByTestId('plugin-answer-io');
    expect(answer).toHaveTextContent('OK');
    expect(answer).toHaveTextContent('"name": "red"');
    expect(calls).toContainEqual(expect.objectContaining({ target: 'rti-fsp01:5001', method: 'GET', path: '/api/plugins/io/leds/1?on=1&color=red' }));
  });

  it('has no request form for a plugin without routes', async () => {
    const status = { ...STATUS, plugins: [{ ...STATUS.plugins[0], routes: false }] };
    mockBff({ 'GET /api/plugins': { status: 200, body: { ok: true, result: status } } });
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Details io'));
    expect(screen.queryByRole('form', { name: 'Request to io' })).not.toBeInTheDocument();
  });

  it('asks before a request that may change the plugin, and sends its JSON body', async () => {
    const confirm = vi.spyOn(window, 'confirm').mockReturnValueOnce(false).mockReturnValueOnce(true);
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Details io'));
    const form = screen.getByRole('form', { name: 'Request to io' });
    await user.selectOptions(within(form).getByLabelText('Method'), 'POST');
    await user.type(within(form).getByLabelText('Path'), 'leds');
    await user.click(await screen.findByRole('textbox', { name: 'Body (JSON)' }));
    await user.keyboard('{{"on": true}');

    await user.click(within(form).getByRole('button', { name: 'Send' }));
    expect(confirm).toHaveBeenLastCalledWith("POST /api/plugins/io/leds may change the plugin's state. Send?");
    expect(calls.filter((c) => c.path === '/api/plugins/io/leds')).toEqual([]);

    await user.click(within(form).getByRole('button', { name: 'Send' }));
    await waitFor(() => expect(calls).toContainEqual(expect.objectContaining({ method: 'POST', path: '/api/plugins/io/leds', body: { on: true } })));
  });

  it("shows the instance's error as the answer when the plugin route fails", async () => {
    mockBff({ 'GET /api/plugins/io/nope': { status: 500, body: { detail: '404 Client Error: Not Found for url: http://dr-panel:5001/api/plugins/io/nope' } } });
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Details io'));
    const form = screen.getByRole('form', { name: 'Request to io' });
    await user.type(within(form).getByLabelText('Path'), 'nope');
    await user.click(within(form).getByRole('button', { name: 'Send' }));

    const answer = await screen.findByTestId('plugin-answer-io');
    expect(answer).toHaveTextContent('Failed');
    expect(answer).toHaveTextContent('404 Client Error');
  });

  it("refuses POST reload as a plugin route, without calling the instance", async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Details io'));
    const form = screen.getByRole('form', { name: 'Request to io' });
    await user.selectOptions(within(form).getByLabelText('Method'), 'POST');
    await user.type(within(form).getByLabelText('Path'), 'reload');
    await user.click(within(form).getByRole('button', { name: 'Send' }));

    expect(await screen.findByRole('alert')).toHaveTextContent("POST reload is the instance's own Reload");
    expect(calls.filter((c) => c.method === 'POST')).toEqual([]);
  });

  it('keeps the request and its answer when the details are closed and opened again', async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await user.click(await screen.findByTitle('Details io'));
    await user.type(within(screen.getByRole('form', { name: 'Request to io' })).getByLabelText('Path'), 'leds');
    await user.click(screen.getByTitle('Details io'));
    await user.click(screen.getByTitle('Details io'));
    expect(within(screen.getByRole('form', { name: 'Request to io' })).getByLabelText('Path')).toHaveValue('leds');
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

    expect(JSON.parse((await screen.findByTestId('plugins-config-entry')).textContent)).toEqual({ name: 'io', url: 'http://dr-panel:9000/plugin' });
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

  // The BFF's connections, as App.jsx passes them; rti-fsp02 has display already.
  const INSTANCES = [
    { name: 'rti-so', type: 'RTI-SO', host: 'rti-so', port: 5000, status: 'connected' },
    { name: 'rti-fsp01', type: 'RTI-FSP', host: 'rti-fsp01', port: 5001, status: 'connected' },
    { name: 'rti-fsp02', type: 'RTI-FSP', host: 'rti-fsp02', port: 5005, status: 'connected', plugins: { plugins: [], failed: { display: 'down' } } },
    { name: 'rti-fsp03', type: 'RTI-FSP', host: 'rti-fsp03', port: 5006, status: 'disconnected' },
    { name: 'idp', type: 'IDP-Server', host: 'keycloak', port: 8081, status: 'connected' },
  ];
  const addToOptions = () => within(document.getElementById('plugins-add-to')).getAllByRole('option').slice(1);

  it('offers the other connected SOs and FSPs to add to, not this one', async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" instances={INSTANCES} />);
    await user.click(await screen.findByTitle('Add display to another SO or FSP'));

    expect(addToOptions().map((o) => [o.textContent, o.disabled])).toEqual([
      ['rti-so (SO, rti-so:5000)', false],
      ['rti-fsp02 (FSP, rti-fsp02:5005) - has display', true],
    ]);
    expect(document.getElementById('plugins-add-to')).toHaveValue('rti-so:5000');
    expect(document.getElementById('plugins-add-url')).toHaveValue('http://pi:8000/plugin');
    expect(JSON.parse(await settingsText())).toEqual({ rotate: 90 });
  });

  it('offers only FSPs for a plugin with claims', async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" instances={INSTANCES} />);
    await user.click(await screen.findByTitle('Add io to another SO or FSP'));
    expect(addToOptions().map((o) => o.value)).toEqual(['rti-fsp02:5005']);
    expect(screen.getByRole('form', { name: 'Add io to another instance' }).textContent).toMatch(/only FSPs are offered/);
  });

  it('adds the plugin to the chosen instance, with its definition', async () => {
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" instances={INSTANCES} />);
    await user.click(await screen.findByTitle('Add io to another SO or FSP'));
    await user.click(screen.getByRole('button', { name: 'Add to instance' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Added io to rti-fsp02.');
    expect(calls).toContainEqual(expect.objectContaining({
      target: 'rti-fsp02:5005', method: 'POST', path: '/api/plugins', body: { name: 'io', url: 'http://dr-panel:9000/plugin', settings: {} },
    }));
    expect(screen.queryByRole('form')).not.toBeInTheDocument();
  });

  it("keeps the form open with the other instance's reason when it refuses", async () => {
    mockBff({
      'POST /api/plugins': { status: 500, body: { ok: false, error: "409 Client Error - 'LD0/CSWI1.Pos.Oper.ctlVal' is claimed by io" } },
    });
    const user = userEvent.setup({ delay: null });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" instances={INSTANCES} />);
    await user.click(await screen.findByTitle('Add io to another SO or FSP'));
    await user.click(screen.getByRole('button', { name: 'Add to instance' }));

    expect(await screen.findByRole('alert')).toHaveTextContent("Add io to rti-fsp02 failed: 409 Client Error - 'LD0/CSWI1.Pos.Oper.ctlVal' is claimed by io");
    expect(screen.getByRole('form', { name: 'Add io to another instance' })).toBeInTheDocument();
  });

  it("can't edit without definitions, from an older instance", async () => {
    mockBff({ 'GET /api/plugins': { status: 200, body: { ok: true, result: { plugins: STATUS.plugins, failed: {} } } } });
    render(<PluginsPanel target="rti-fsp01:5001" role="fsp" />);
    await screen.findByTestId('plugin-row-io');
    expect(screen.getByTitle(/^Edit io/)).toBeDisabled();
    expect(screen.getByTitle(/^Copy io as configuration/)).toBeDisabled();
    expect(screen.getByTitle(/^Add io to another SO or FSP/)).toBeDisabled();
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
