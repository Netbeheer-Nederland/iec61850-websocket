import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import ACSIServer from './ACSIServer';

const executeApiCall = vi.fn();
vi.mock('../services/apiService', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    executeApiCall: (...args) => executeApiCall(...args),
  };
});

// What every real navigation into this page actually passes as `endpoint`
// (via InstanceVisualization/Model's FSP card click): the clicked RTI-FSP's
// own connection record - its own host/BFF port, never a target RTI-SO.
const DEFAULT_ENDPOINT = { name: 'FSP01', host: 'rti-fsp01', port: 5001, type: 'RTI-FSP', cp: 'cp1' };

const renderPage = (fspEndpoint = DEFAULT_ENDPOINT) =>
  render(
    <MemoryRouter
      initialEntries={[
        fspEndpoint
          ? { pathname: '/acsi-server', state: { endpoint: fspEndpoint } }
          : '/acsi-server',
      ]}
    >
      <ACSIServer settings={{}} updateModel={() => {}} getModel={() => {}} bffBaseUrl="http://bff.local:5000" />
    </MemoryRouter>
  );

// Simulates a page refresh / direct URL visit with only the ?fsp= param
// surviving (no location.state - that's React Router in-memory only).
const renderPageWithParam = (fspName) =>
  render(
    <MemoryRouter initialEntries={[`/acsi-server?fsp=${encodeURIComponent(fspName)}`]}>
      <ACSIServer settings={{}} updateModel={() => {}} getModel={() => {}} bffBaseUrl="http://bff.local:5000" />
    </MemoryRouter>
  );

const mockConnections = (connections) => {
  global.fetch = vi.fn(async (url) => {
    if (String(url).endsWith('/api/connections')) {
      return { ok: true, json: async () => ({ connections }) };
    }
    return { ok: false, json: async () => ({}) };
  });
};

beforeEach(() => {
  executeApiCall.mockReset();
  executeApiCall.mockResolvedValue({ ok: false });
  localStorage.clear();

  mockConnections([
    {
      name: 'so1', host: '10.0.0.1', port: 5002, ws_port: 8765,
      type: 'RTI-SO', status: 'connected',
    },
    {
      // No ws_port configured on this one.
      name: 'so2', host: '10.0.0.2', port: 5003,
      type: 'RTI-SO', status: 'connected',
    },
  ]);
});

describe('ACSIServer without a navigated-in endpoint (direct visit / refresh)', () => {
  // React Router's location.state.endpoint only exists when arriving via an
  // in-app click (InstanceVisualization/Model) - it does not survive a
  // direct URL visit or a page refresh, so `endpoint` is null here. This
  // used to silently fall back to using the WS Host/Port fields (the
  // target SO's address) as the API call target instead of failing
  // visibly - see endpointTarget's useMemo in ACSIServer.jsx.
  it('shows a clear warning and disables the connection controls instead of silently using the wrong target', async () => {
    renderPage(null);

    await waitFor(() => {
      expect(screen.getByText(/No FSP instance selected/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Instance')).toBeDisabled();
    expect(screen.getByLabelText('WS Host')).toBeDisabled();
    expect(screen.getByLabelText('WS Port')).toBeDisabled();
    expect(screen.getByLabelText('WS Mode')).toBeDisabled();
    expect(document.getElementById('acsi-start-btn')).toBeDisabled();
  });

  it('never calls the status API without a real endpoint', async () => {
    renderPage(null);

    await waitFor(() => {
      expect(screen.getByText(/No FSP instance selected/i)).toBeInTheDocument();
    });
    expect(executeApiCall).not.toHaveBeenCalled();
  });
});

describe('ACSIServer recovering the endpoint from ?fsp= after a refresh', () => {
  it('resolves the FSP from the fetched connections list and enables the controls', async () => {
    mockConnections([
      { name: 'FSP01', host: 'rti-fsp01', port: 5001, type: 'RTI-FSP', cp: 'cp1', status: 'connected' },
      { name: 'so1', host: '10.0.0.1', port: 5002, ws_port: 8765, type: 'RTI-SO', status: 'connected' },
    ]);
    renderPageWithParam('FSP01');

    await waitFor(() => {
      expect(screen.queryByText(/No FSP instance selected/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toBeEnabled();
    });
    expect(document.getElementById('acsi-start-btn')).not.toBeDisabled();
    // The status API call this triggers (loadStatus, on endpointTarget
    // becoming available) must be routed to FSP01's own BFF address -
    // rti-fsp01:5001 - not anything derived from the WS Host/Port fields.
    await waitFor(() => {
      expect(executeApiCall).toHaveBeenCalledWith('status', 'rti-fsp01:5001', null);
    });
  });

  it('shows a "not found" error when the ?fsp= name has no matching connection', async () => {
    renderPageWithParam('does-not-exist');

    await waitFor(() => {
      expect(screen.getByText(/"does-not-exist" not found/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Instance')).toBeDisabled();
    expect(executeApiCall).not.toHaveBeenCalled();
  });
});

describe('ACSIServer instance selection - fresh/no prior selection', () => {
  it('stays on "Select instance..." with editable localhost/8765/active when nothing is selected or persisted', async () => {
    renderPage();

    await waitFor(() => {
      // soTargetInstances is populated once connections load, so the
      // dropdown having its options is a proxy for "the fetch that would
      // have driven an auto-select has already happened" - it still
      // shouldn't pick one of them.
      expect(screen.getByRole('option', { name: /^so1/ })).toBeInTheDocument();
    });
    // "" is the disabled "Select instance..." placeholder option's value -
    // blank is not itself a selection.
    expect(screen.getByLabelText('Instance')).toHaveValue('');

    // Landing on a blank/read-only Instance left the WS fields un-editable
    // with no real instance backing them, so Connect used those defaults
    // as-is instead of values the user could actually correct first - so
    // blank stays editable, the same as "custom" is.
    await waitFor(() => {
      expect(screen.getByLabelText('WS Host')).toHaveValue('localhost');
    });
    expect(screen.getByLabelText('WS Port')).toHaveValue('8765');
    expect(screen.getByLabelText('WS Mode')).toHaveValue('active');
    expect(screen.getByLabelText('WS Host')).not.toHaveAttribute('readonly');
    expect(screen.getByLabelText('WS Host')).toBeEnabled();
    expect(screen.getByLabelText('WS Mode').tagName).toBe('SELECT');
  });

  it('restores a previously-selected instance on remount instead of the defaults', async () => {
    localStorage.setItem('acsi-server-selected-instance-FSP01', 'so1');
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toHaveValue('so1');
    });
    await waitFor(() => {
      expect(screen.getByLabelText('WS Host')).toHaveValue('10.0.0.1');
    });
    expect(screen.getByLabelText('WS Port')).toHaveValue('8765');
  });

  it('does not seed WS Host/Port from the navigated-in endpoint - that is this FSP\'s own address, not a WS target', async () => {
    // Every real navigation to this page (from InstanceVisualization/
    // Model's FSP card click) passes the clicked RTI-FSP's *own*
    // connection record as `endpoint` - its own host/BFF port, e.g.
    // rti-fsp01:5001 - never a target RTI-SO to dial into.
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('option', { name: /^so1/ })).toBeInTheDocument();
    });
    // Falls through to the same blank-with-defaults state a direct visit
    // gets - not "rti-fsp01"/"5001" (this FSP's own address) and not
    // "custom" (which endpoint.name failing to match any soTargetInstances
    // used to force it into).
    expect(screen.getByLabelText('Instance')).toHaveValue('');
    await waitFor(() => {
      expect(screen.getByLabelText('WS Host')).toHaveValue('localhost');
    });
    expect(screen.getByLabelText('WS Port')).toHaveValue('8765');
  });
});

describe('ACSIServer instance selection - ws_port vs BFF port', () => {
  it('fills WS Port from the instance\'s ws_port (not its BFF port) on selection', async () => {
    renderPage();
    const user = userEvent.setup({ delay: null });

    await waitFor(() => {
      expect(screen.getByRole('option', { name: /^so1/ })).toBeInTheDocument();
    });
    // Wait for the default "Custom" landing state's own WS Host fill to
    // settle first - otherwise it can race with (and clobber) the
    // selection below, since both write to the same state.
    await waitFor(() => {
      expect(screen.getByLabelText('WS Host')).toHaveValue('localhost');
    });
    await user.selectOptions(screen.getByLabelText('Instance'), 'so1');

    await waitFor(() => {
      expect(screen.getByLabelText('WS Host')).toHaveValue('10.0.0.1');
    });
    // WS Port is type="text" (not "number") specifically so a read-only
    // instance-derived value renders as plain text, not a native
    // number-input control.
    expect(screen.getByLabelText('WS Port')).toHaveValue('8765');
    // A real instance is selected - these fields are read-only, not just
    // "disabled" (see ConnectionModal.jsx's identical ACSI/WebSocket Mode
    // pattern: readOnly for "fixed by other state", disabled only for a
    // genuinely temporary lock like `loading`).
    expect(screen.getByLabelText('WS Host')).toHaveAttribute('readonly');
    expect(screen.getByLabelText('WS Port')).toHaveAttribute('readonly');
    expect(screen.getByLabelText('WS Host')).toBeEnabled();
    // WS Mode renders as a read-only text display, not a disabled <select>,
    // when a real instance is selected.
    expect(screen.getByLabelText('WS Mode')).toHaveValue('Active');
    expect(screen.getByLabelText('WS Mode').tagName).toBe('INPUT');
  });

  it('leaves WS Port blank (not the BFF port) for a selected instance with no ws_port', async () => {
    // so2 has no ws_port - its dropdown option is disabled (see the
    // "usability" tests below), so a user could never pick it live via the
    // select. Land on it the way a persisted-but-now-misconfigured
    // selection would: a prior selection restored from localStorage.
    mockConnections([
      { name: 'so2', host: '10.0.0.2', port: 5003, type: 'RTI-SO', status: 'connected' },
    ]);
    localStorage.setItem('acsi-server-selected-instance-FSP01', 'so2');
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toHaveValue('so2');
    });
    await waitFor(() => {
      expect(screen.getByLabelText('WS Host')).toHaveValue('10.0.0.2');
    });
    // Must NOT be 5003 (so2's BFF port) - this is the exact bug being
    // regression-tested: silently falling back to the BFF port.
    expect(screen.getByLabelText('WS Port')).toHaveValue('');
  });

  it('clears all WS fields when switching to "custom"', async () => {
    renderPage();
    const user = userEvent.setup({ delay: null });

    await waitFor(() => {
      expect(screen.getByRole('option', { name: /^so1/ })).toBeInTheDocument();
    });
    await user.selectOptions(screen.getByLabelText('Instance'), 'so1');
    await waitFor(() => {
      expect(screen.getByLabelText('WS Host')).toHaveValue('10.0.0.1');
    });

    await user.selectOptions(screen.getByLabelText('Instance'), 'custom');

    expect(screen.getByLabelText('WS Host')).toHaveValue('');
    expect(screen.getByLabelText('WS Port')).toHaveValue('');
    expect(screen.getByLabelText('WS Mode')).toHaveValue('active');
    // Custom is the only state where these fields become editable - a real
    // <select> for WS Mode (not the read-only text display), and neither
    // disabled nor readOnly for WS Host/Port.
    expect(screen.getByLabelText('WS Host')).toBeEnabled();
    expect(screen.getByLabelText('WS Host')).not.toHaveAttribute('readonly');
    expect(screen.getByLabelText('WS Mode').tagName).toBe('SELECT');
  });
});

describe('ACSIServer instance dropdown - usability', () => {
  it('disables the option for an instance with no ws_port configured, and labels it', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole('option', { name: /^so1/ })).toBeInTheDocument();
    });

    const so2Option = screen.getByRole('option', { name: /so2/ });
    expect(so2Option).toBeDisabled();
    expect(so2Option.textContent).toMatch(/WS port not configured/);

    const so1Option = screen.getByRole('option', { name: /^so1/ });
    expect(so1Option).toBeEnabled();

    // A disabled option can't actually be selected via user interaction -
    // the dropdown stays on its current (blank, the default) value.
    const user = userEvent.setup({ delay: null });
    await user.selectOptions(screen.getByLabelText('Instance'), 'so2').catch(() => {});
    expect(screen.getByLabelText('Instance')).toHaveValue('');
  });

  it('disables the whole Instance dropdown while the server is connected, with an explanatory hint', async () => {
    localStorage.setItem('acsi-server-connected-FSP01', 'true');
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toBeDisabled();
    });
    expect(screen.getByText(/Stop the server to switch/i)).toBeInTheDocument();
  });

  it('re-enables the Instance dropdown once not connected', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText('Instance')).toBeEnabled();
    });
    expect(screen.queryByText(/Stop the server to switch/i)).not.toBeInTheDocument();
  });
});

describe('ACSIServer connection status label', () => {
  it('shows the raw "listening" status as "Serving"', async () => {
    executeApiCall.mockImplementation(async (apiId) => {
      if (apiId === 'status') {
        return {
          ok: true,
          payload: { result: { status: { status: 'listening', modelName: 'IED_2' } } },
        };
      }
      return { ok: false };
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Serving')).toBeInTheDocument();
    });
    // The raw backend value is what drives the State color, but should
    // never itself be the displayed text.
    expect(screen.queryByText('listening')).not.toBeInTheDocument();
    expect(screen.getByText('IED_2')).toBeInTheDocument();
  });
});
