import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MessageMonitor from './MessageMonitor';

const executeApiCall = vi.fn();
vi.mock('../services/apiService', () => ({
  executeApiCall: (...args) => executeApiCall(...args),
  buildTargetValue: (host, port) => `${host}:${port}`,
}));

let liveMessageHandlers;
let liveStateHandlers;
const isConnected = vi.fn();
vi.mock('../services/liveSocket', () => ({
  subscribe: (type, handler) => {
    liveMessageHandlers.push({ type, handler });
    return () => {
      liveMessageHandlers = liveMessageHandlers.filter((h) => h.handler !== handler);
    };
  },
  isConnected: (...args) => isConnected(...args),
  onConnectionStateChange: (handler) => {
    liveStateHandlers.push(handler);
    return () => {
      liveStateHandlers = liveStateHandlers.filter((h) => h !== handler);
    };
  },
}));

const endpoint = { host: '10.0.0.1', port: 5001, name: 'fsp1' };

const emptyMessagesResponse = { ok: true, payload: { messages: [] } };
const withMessagesResponse = (msgs) => ({ ok: true, payload: { messages: msgs } });

const pushLiveMessages = async (target, data) => {
  await act(async () => {
    liveMessageHandlers
      .filter((h) => h.type === 'messages')
      .forEach((h) => h.handler({ type: 'messages', target, data }));
  });
};

// Each catch-up/poll fetches both logs (frames + actions); count the frame
// fetches - one per catch-up or poll tick.
const messageFetches = () => executeApiCall.mock.calls.filter(([apiId]) => apiId === 'messages').length;

const pushLiveActions = async (target, data) => {
  await act(async () => {
    liveMessageHandlers
      .filter((h) => h.type === 'actions')
      .forEach((h) => h.handler({ type: 'actions', target, data }));
  });
};

const flipConnectionState = async (connected) => {
  await act(async () => {
    liveStateHandlers.forEach((handler) => handler(connected));
    await Promise.resolve();
  });
};

beforeEach(() => {
  localStorage.clear();
  executeApiCall.mockReset();
  executeApiCall.mockResolvedValue(emptyMessagesResponse);
  isConnected.mockReset();
  liveMessageHandlers = [];
  liveStateHandlers = [];
  // Scoped to what MessageMonitor.jsx actually uses (setInterval/
  // clearInterval for fallback polling). Faking everything (the default)
  // hangs every userEvent.click() forever under this project's current
  // vitest/@testing-library versions - userEvent's internal event dispatch
  // relies on real timers/microtasks that a full fake-timer install
  // intercepts and never advances.
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
});

async function startMonitoring() {
  const user = userEvent.setup({ delay: null });
  await user.click(screen.getByTitle('Start Monitoring'));
}

describe('MessageMonitor live push wiring', () => {
  it('does not poll while the live socket is connected - one catch-up fetch, then push only', async () => {
    isConnected.mockReturnValue(true);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);

    await startMonitoring();
    expect(messageFetches()).toBe(1); // immediate catch-up

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(messageFetches()).toBe(1); // still just the catch-up - no polling

    await pushLiveMessages('10.0.0.1:5001', [{ id: 1, message: 'hello' }]);
    expect(screen.getByText('#1')).toBeInTheDocument();
  });

  it('ignores pushed messages for a different target', async () => {
    isConnected.mockReturnValue(true);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();

    await pushLiveMessages('other-host:9999', [{ id: 1, message: 'not for us' }]);
    expect(screen.queryByText('#1')).not.toBeInTheDocument();
  });

  it('falls back to polling when the live socket is not connected', async () => {
    isConnected.mockReturnValue(false);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);

    await startMonitoring();
    expect(messageFetches()).toBe(1); // immediate fetch

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(messageFetches()).toBe(2); // fallback poll fired

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(messageFetches()).toBe(3);
  });

  it('stops fallback polling and catches up once the socket reconnects', async () => {
    isConnected.mockReturnValue(false);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);

    await startMonitoring();
    expect(messageFetches()).toBe(1);

    await flipConnectionState(true);
    expect(messageFetches()).toBe(2); // catch-up fetch on reconnect

    // Fallback polling should now be stopped - no further HTTP calls even
    // after the old interval would have fired again.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(messageFetches()).toBe(2);
  });

  it('starts fallback polling if the socket drops while monitoring', async () => {
    isConnected.mockReturnValue(true);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);

    await startMonitoring();
    expect(messageFetches()).toBe(1);

    await flipConnectionState(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(messageFetches()).toBe(2); // fallback poll kicked in
  });

  it('stop monitoring clears the fallback polling interval', async () => {
    isConnected.mockReturnValue(false);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);

    await startMonitoring();
    expect(messageFetches()).toBe(1);

    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByTitle('Stop Monitoring'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(messageFetches()).toBe(1); // no more polling after stop
  });
});

describe('MessageMonitor sort order', () => {
  // Messages arrive oldest-first (each push/poll appends to the end of the
  // underlying array, same as the id order below) - the sort toggle should
  // default to showing the latest one first regardless, same as
  // ActionLogPanel's Protocol Messages list does.
  const ids = () => screen.getAllByText(/^#\d+$/).map((el) => el.textContent);

  it('defaults to newest-first even though messages arrive oldest-first', async () => {
    isConnected.mockReturnValue(true);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();

    await pushLiveMessages('10.0.0.1:5001', [
      { id: 1, message: 'first' },
      { id: 2, message: 'second' },
      { id: 3, message: 'third' },
    ]);

    expect(ids()).toEqual(['#3', '#2', '#1']);
    expect(screen.getByTitle('Showing newest first - click for oldest first')).toBeInTheDocument();
  });

  it('toggles to oldest-first on click, and back on a second click', async () => {
    isConnected.mockReturnValue(true);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();
    await pushLiveMessages('10.0.0.1:5001', [
      { id: 1, message: 'first' },
      { id: 2, message: 'second' },
    ]);

    const user = userEvent.setup({ delay: null });
    const sortButton = screen.getByTitle('Showing newest first - click for oldest first');
    await user.click(sortButton);

    expect(ids()).toEqual(['#1', '#2']);
    expect(screen.getByTitle('Showing oldest first - click for newest first')).toBeInTheDocument();

    await user.click(screen.getByTitle('Showing oldest first - click for newest first'));

    expect(ids()).toEqual(['#2', '#1']);
  });

  it('disables the sort button while there are no messages', async () => {
    isConnected.mockReturnValue(true);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();

    expect(screen.getByTitle('Showing newest first - click for oldest first')).toBeDisabled();
  });
});

describe('MessageMonitor - monitoring survives switching pages', () => {
  it('resumes monitoring on remount if it was left on', async () => {
    isConnected.mockReturnValue(true);
    const { unmount } = render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();
    unmount();

    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);

    await waitFor(() => expect(screen.getByTitle('Stop Monitoring')).toBeEnabled());
    expect(screen.getByTitle('Start Monitoring')).toBeDisabled();
  });

  it('stays stopped on remount once the user stopped it', async () => {
    isConnected.mockReturnValue(true);
    const { unmount } = render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByTitle('Stop Monitoring'));
    unmount();

    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);

    expect(screen.getByTitle('Start Monitoring')).toBeEnabled();
    expect(screen.getByTitle('Stop Monitoring')).toBeDisabled();
  });

  it('keeps the flag per endpoint', async () => {
    isConnected.mockReturnValue(true);
    const { unmount } = render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();
    unmount();

    render(<MessageMonitor endpoints={[{ host: '10.0.0.9', port: 5009, name: 'other' }]} defaultInterval={10000} />);

    expect(screen.getByTitle('Start Monitoring')).toBeEnabled();
  });
});

describe('MessageMonitor - WebSocket frames and ACSI service entries', () => {
  const kinds = (container) => [...container.querySelectorAll('.message-card .log-kind-badge')].map((b) => b.dataset.kind);

  it('shows pushed ACSI entries next to frames, each with its kind badge - even with the same id', async () => {
    isConnected.mockReturnValue(true);
    const { container } = render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();

    await pushLiveMessages('10.0.0.1:5001', [{ id: 1, direction: 'recv', service_type: 'getDataValues', message: '{}' }]);
    await pushLiveActions('10.0.0.1:5001', [{ id: 1, kind: 'acsi', message: 'Server readvalue', detail: { objRef: 'LD0/LLN0.Mod.stVal' } }]);

    expect(kinds(container).sort()).toEqual(['acsi', 'websocket']);
    expect(screen.getByText('Server readvalue')).toBeInTheDocument();
  });

  it('catches up on the actions log too, keeping only its ACSI entries', async () => {
    isConnected.mockReturnValue(true);
    executeApiCall.mockImplementation(async (apiId) => {
      if (apiId === 'actions-logs') {
        return {
          ok: true,
          payload: {
            actions: [
              { id: 1, kind: 'system', time: '10:00:00', message: 'Server listening' },
              { id: 2, kind: 'acsi', time: '10:00:01', message: 'Server writevalue' },
            ],
          },
        };
      }
      return emptyMessagesResponse;
    });
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);

    await startMonitoring();

    expect(await screen.findByText('Server writevalue')).toBeInTheDocument();
    expect(screen.queryByText('Server listening')).not.toBeInTheDocument();
  });

  it('filters to one kind', async () => {
    isConnected.mockReturnValue(true);
    const { container } = render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();
    await pushLiveMessages('10.0.0.1:5001', [{ id: 1, direction: 'recv', message: '{}' }]);
    await pushLiveActions('10.0.0.1:5001', [{ id: 1, kind: 'acsi', message: 'Server readvalue' }]);

    const user = userEvent.setup({ delay: null });
    await user.selectOptions(screen.getByTitle('Filter by kind'), 'acsi');

    expect(kinds(container)).toEqual(['acsi']);

    await user.selectOptions(screen.getByTitle('Filter by kind'), 'websocket');

    expect(kinds(container)).toEqual(['websocket']);
  });

  it('does not bring cleared ACSI entries back on the next catch-up', async () => {
    isConnected.mockReturnValue(true);
    executeApiCall.mockImplementation(async (apiId) => {
      if (apiId === 'actions-logs') {
        return { ok: true, payload: { actions: [{ id: 7, kind: 'acsi', message: 'Server readvalue' }] } };
      }
      return { ok: true, payload: { messages: [] } };
    });
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();
    expect(await screen.findByText('Server readvalue')).toBeInTheDocument();

    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByTitle('Clear Messages'));
    expect(screen.queryByText('Server readvalue')).not.toBeInTheDocument();

    await flipConnectionState(true); // reconnect -> catch-up fetch

    expect(screen.queryByText('Server readvalue')).not.toBeInTheDocument();
  });
});

describe('MessageMonitor - ACSI entries linked to their frames', () => {
  const acsiRead = {
    id: 9,
    kind: 'acsi',
    message: 'GetDataValues LD0/LLN0.Mod.stVal [ST] - ok',
    cp: 'cp1',
    correlation: { cp: 'cp1', invokeId: 3, messageSeqFrom: 11, messageSeqTo: 12 },
  };

  it('lists the frames in the entry\'s range on its cp when expanded, and counts them in the row', async () => {
    isConnected.mockReturnValue(true);
    const { container } = render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();
    await pushLiveMessages('10.0.0.1:5001', [
      { id: 10, cp: 'cp1', direction: 'recv', category: 'response', service_type: 'getDataValues', preview: 'earlier' },
      { id: 11, cp: 'cp1', direction: 'send', category: 'request', service_type: 'getDataValues', preview: 'req' },
      { id: 12, cp: 'cp1', direction: 'recv', category: 'response', service_type: 'getDataValues', preview: 'resp' },
      { id: 13, cp: 'cp2', direction: 'recv', category: 'response', service_type: 'getDataValues', preview: 'other cp' },
    ]);
    await pushLiveActions('10.0.0.1:5001', [acsiRead]);

    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByText(acsiRead.message));

    const linked = [...container.querySelectorAll('.message-linked-frame')].map((el) => el.textContent);
    expect(linked).toHaveLength(2);
    expect(linked[0]).toContain('#11');
    expect(linked[1]).toContain('#12');
    expect(container.querySelector('.message-frame-count').textContent).toBe('2');
  });

  it('says so when the linked frames are not in view', async () => {
    isConnected.mockReturnValue(true);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);
    await startMonitoring();
    await pushLiveActions('10.0.0.1:5001', [acsiRead]);

    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByText(acsiRead.message));

    expect(screen.getByText(/Frames #11-#12 aren't in this view/)).toBeInTheDocument();
  });
});

