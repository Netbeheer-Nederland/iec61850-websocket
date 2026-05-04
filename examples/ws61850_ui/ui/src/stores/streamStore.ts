import { create } from 'zustand';
import { appendRingBuffer } from '../utils/ringBuffer';
import type { RtiEventMessage } from '../types/protocol';

interface StreamFilters {
  refQuery: string;
  quality?: string;
}

interface StreamState {
  events: RtiEventMessage[];
  paused: boolean;
  filters: StreamFilters;
  appendEvent: (event: RtiEventMessage) => void;
  clearEvents: () => void;
  setPaused: (paused: boolean) => void;
  setFilters: (filters: Partial<StreamFilters>) => void;
}

const max = Number(import.meta.env.VITE_EVENT_BUFFER_SIZE ?? 5000);

export const useStreamStore = create<StreamState>((set, get) => ({
  events: [],
  paused: false,
  filters: { refQuery: '' },
  appendEvent: (event) =>
    set((state) => ({
      events: appendRingBuffer(state.events, event, max),
    })),
  clearEvents: () => set({ events: [] }),
  setPaused: (paused) => set({ paused }),
  setFilters: (filters) => set({ filters: { ...get().filters, ...filters } }),
}));
