import { create } from 'zustand';
import type { SocketState } from '../types/protocol';

interface SessionState {
  endpointUrl: string;
  socketState: SocketState;
  reconnectEnabled: boolean;
  reconnectAttempt: number;
  lastMessageAt?: string;
  connectedAt?: string;
  messageRatePerMinute: number;
  setEndpoint: (url: string) => void;
  setSocketState: (state: SocketState) => void;
  setReconnectEnabled: (enabled: boolean) => void;
  recordHeartbeat: (timestamp: string) => void;
  setConnectedAt: (timestamp?: string) => void;
  setMessageRatePerMinute: (rate: number) => void;
  incrementReconnectAttempt: () => void;
  resetSession: () => void;
}

const defaultEndpoint = import.meta.env.VITE_WS_URL ?? 'mock://demo';

export const useSessionStore = create<SessionState>((set) => ({
  endpointUrl: defaultEndpoint,
  socketState: 'disconnected',
  reconnectEnabled: true,
  reconnectAttempt: 0,
  messageRatePerMinute: 0,
  setEndpoint: (endpointUrl) => set({ endpointUrl }),
  setSocketState: (socketState) => set({ socketState }),
  setReconnectEnabled: (reconnectEnabled) => set({ reconnectEnabled }),
  recordHeartbeat: (lastMessageAt) => set({ lastMessageAt }),
  setConnectedAt: (connectedAt) => set({ connectedAt }),
  setMessageRatePerMinute: (messageRatePerMinute) => set({ messageRatePerMinute }),
  incrementReconnectAttempt: () => set((state) => ({ reconnectAttempt: state.reconnectAttempt + 1 })),
  resetSession: () => set({
    socketState: 'disconnected',
    reconnectAttempt: 0,
    lastMessageAt: undefined,
    connectedAt: undefined,
    messageRatePerMinute: 0,
  }),
}));
