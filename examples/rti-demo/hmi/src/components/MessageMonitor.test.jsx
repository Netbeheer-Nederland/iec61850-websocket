import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, act } from '@testing-library/react';
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

const flipConnectionState = async (connected) => {
  await act(async () => {
    liveStateHandlers.forEach((handler) => handler(connected));
    await Promise.resolve();
  });
};

beforeEach(() => {
  executeApiCall.mockReset();
  executeApiCall.mockResolvedValue(emptyMessagesResponse);
  isConnected.mockReset();
  liveMessageHandlers = [];
  liveStateHandlers = [];
  vi.useFakeTimers();
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
    expect(executeApiCall).toHaveBeenCalledTimes(1); // immediate catch-up

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(executeApiCall).toHaveBeenCalledTimes(1); // still just the catch-up - no polling

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
    expect(executeApiCall).toHaveBeenCalledTimes(1); // immediate fetch

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(executeApiCall).toHaveBeenCalledTimes(2); // fallback poll fired

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(executeApiCall).toHaveBeenCalledTimes(3);
  });

  it('stops fallback polling and catches up once the socket reconnects', async () => {
    isConnected.mockReturnValue(false);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);

    await startMonitoring();
    expect(executeApiCall).toHaveBeenCalledTimes(1);

    await flipConnectionState(true);
    expect(executeApiCall).toHaveBeenCalledTimes(2); // catch-up fetch on reconnect

    // Fallback polling should now be stopped - no further HTTP calls even
    // after the old interval would have fired again.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(executeApiCall).toHaveBeenCalledTimes(2);
  });

  it('starts fallback polling if the socket drops while monitoring', async () => {
    isConnected.mockReturnValue(true);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);

    await startMonitoring();
    expect(executeApiCall).toHaveBeenCalledTimes(1);

    await flipConnectionState(false);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(executeApiCall).toHaveBeenCalledTimes(2); // fallback poll kicked in
  });

  it('stop monitoring clears the fallback polling interval', async () => {
    isConnected.mockReturnValue(false);
    render(<MessageMonitor endpoints={[endpoint]} defaultInterval={10000} />);

    await startMonitoring();
    expect(executeApiCall).toHaveBeenCalledTimes(1);

    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByTitle('Stop Monitoring'));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(executeApiCall).toHaveBeenCalledTimes(1); // no more polling after stop
  });
});
