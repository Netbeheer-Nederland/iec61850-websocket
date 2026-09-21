import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('./apiService', () => ({
  getBffBaseUrl: () => 'http://bff.local:5000',
}));

class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances = [];

  constructor(url) {
    this.url = url;
    this.readyState = MockWebSocket.CONNECTING;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    MockWebSocket.instances.push(this);
  }

  close() {
    if (this.readyState === MockWebSocket.CLOSED) return;
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({});
  }

  // test helpers, not part of the real WebSocket API
  _open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({});
  }

  _receive(payload) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }
}

let liveSocket;

beforeEach(async () => {
  vi.useFakeTimers();
  MockWebSocket.instances = [];
  global.WebSocket = MockWebSocket;
  vi.resetModules();
  liveSocket = await import('./liveSocket');
});

afterEach(() => {
  vi.useRealTimers();
  delete global.WebSocket;
});

describe('connect', () => {
  it('opens a ws:// connection to the BFF base URL + /ws', () => {
    liveSocket.connect();
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toBe('ws://bff.local:5000/ws');
  });

  it('is a no-op if already open or connecting', () => {
    liveSocket.connect();
    liveSocket.connect();
    liveSocket.connect();
    expect(MockWebSocket.instances).toHaveLength(1);
  });
});

describe('connection state', () => {
  it('notifies listeners immediately with the current (disconnected) state', () => {
    const states = [];
    liveSocket.onConnectionStateChange((connected) => states.push(connected));
    expect(states).toEqual([false]);
  });

  it('notifies listeners when the socket opens', () => {
    const states = [];
    liveSocket.onConnectionStateChange((connected) => states.push(connected));
    liveSocket.connect();
    MockWebSocket.instances[0]._open();
    expect(states).toEqual([false, true]);
    expect(liveSocket.isConnected()).toBe(true);
  });

  it('notifies listeners when the socket closes', () => {
    liveSocket.connect();
    MockWebSocket.instances[0]._open();

    const states = [];
    liveSocket.onConnectionStateChange((connected) => states.push(connected));
    states.length = 0; // drop the immediate replay so we only see the close
    MockWebSocket.instances[0].close();

    expect(states).toEqual([false]);
    expect(liveSocket.isConnected()).toBe(false);
  });

  it('unsubscribe stops further state notifications', () => {
    const states = [];
    const unsubscribe = liveSocket.onConnectionStateChange((connected) => states.push(connected));
    unsubscribe();

    liveSocket.connect();
    MockWebSocket.instances[0]._open();

    expect(states).toEqual([false]); // only the initial replay
  });
});

describe('subscribe', () => {
  it('delivers messages matching the event type', () => {
    liveSocket.connect();
    const ws = MockWebSocket.instances[0];
    ws._open();

    const received = [];
    liveSocket.subscribe('connections', (msg) => received.push(msg));

    ws._receive({ type: 'connections', data: [{ name: 'fsp1' }] });

    expect(received).toEqual([{ type: 'connections', data: [{ name: 'fsp1' }] }]);
  });

  it('does not deliver messages of a different type', () => {
    liveSocket.connect();
    const ws = MockWebSocket.instances[0];
    ws._open();

    const received = [];
    liveSocket.subscribe('connections', (msg) => received.push(msg));

    ws._receive({ type: 'messages', target: 'host:1', data: [] });

    expect(received).toEqual([]);
  });

  it('ignores malformed (non-JSON) payloads instead of throwing', () => {
    liveSocket.connect();
    const ws = MockWebSocket.instances[0];
    ws._open();

    liveSocket.subscribe('connections', () => {
      throw new Error('should not be called');
    });

    expect(() => ws.onmessage({ data: 'not json' })).not.toThrow();
  });

  it('a handler throwing does not prevent other handlers from running', () => {
    liveSocket.connect();
    const ws = MockWebSocket.instances[0];
    ws._open();

    const received = [];
    liveSocket.subscribe('connections', () => {
      throw new Error('boom');
    });
    liveSocket.subscribe('connections', (msg) => received.push(msg));

    expect(() => ws._receive({ type: 'connections', data: [] })).not.toThrow();
    expect(received).toEqual([{ type: 'connections', data: [] }]);
  });

  it('unsubscribe stops delivering further messages', () => {
    liveSocket.connect();
    const ws = MockWebSocket.instances[0];
    ws._open();

    const received = [];
    const unsubscribe = liveSocket.subscribe('connections', (msg) => received.push(msg));
    unsubscribe();

    ws._receive({ type: 'connections', data: [] });

    expect(received).toEqual([]);
  });
});

describe('reconnect behaviour', () => {
  it('auto-reconnects with backoff after the socket closes', () => {
    liveSocket.connect();
    MockWebSocket.instances[0]._open();
    MockWebSocket.instances[0].close();

    expect(MockWebSocket.instances).toHaveLength(1); // not yet reconnected

    vi.advanceTimersByTime(1000);
    expect(MockWebSocket.instances).toHaveLength(2);
  });

  it('resets the backoff delay after a successful reconnect', () => {
    liveSocket.connect();
    MockWebSocket.instances[0]._open();
    MockWebSocket.instances[0].close();

    vi.advanceTimersByTime(1000); // first reconnect attempt (1s backoff)
    expect(MockWebSocket.instances).toHaveLength(2);
    MockWebSocket.instances[1]._open(); // succeeds -> backoff resets to 1s
    MockWebSocket.instances[1].close();

    vi.advanceTimersByTime(1000); // would need 2s if backoff hadn't reset
    expect(MockWebSocket.instances).toHaveLength(3);
  });

  it('reconnect() closes the current socket and opens a new one immediately', () => {
    liveSocket.connect();
    MockWebSocket.instances[0]._open();

    liveSocket.reconnect();

    expect(MockWebSocket.instances[0].readyState).toBe(MockWebSocket.CLOSED);
    expect(MockWebSocket.instances).toHaveLength(2);
  });

  it('reconnect() does not trigger the closed socket\'s own auto-reconnect (avoiding a double connect)', () => {
    liveSocket.connect();
    MockWebSocket.instances[0]._open();

    liveSocket.reconnect();
    vi.advanceTimersByTime(5000);

    // Only the one explicit reconnect() socket, no extra auto-reconnect from
    // the stale onclose handler.
    expect(MockWebSocket.instances).toHaveLength(2);
  });
});
