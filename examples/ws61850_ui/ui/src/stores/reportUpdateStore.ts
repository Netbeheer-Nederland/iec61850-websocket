import { create } from 'zustand';
import { bffApi, type ReportUpdate, type Target, TARGETS } from '../services/bffApi';

export interface TaggedUpdate extends ReportUpdate {
  target: Target;
  id: number;
}

interface ReportUpdateStore {
  updates: TaggedUpdate[];
  isPolling: boolean;
  _timerId: ReturnType<typeof setInterval> | null;
  _seq: number;

  startPolling(intervalMs?: number): void;
  stopPolling(): void;
  clearUpdates(): void;
}

const MAX_UPDATES = Number(import.meta.env.VITE_EVENT_BUFFER_SIZE ?? 5000);

export const useReportUpdateStore = create<ReportUpdateStore>((set, get) => ({
  updates: [],
  isPolling: false,
  _timerId: null,
  _seq: 0,

  startPolling(intervalMs = 2000) {
    if (get().isPolling) return;

    const tick = async () => {
      const incoming: TaggedUpdate[] = [];
      for (const target of TARGETS) {
        try {
          const items = await bffApi.reportUpdates(target);
          for (const u of items) {
            incoming.push({ ...u, target, id: get()._seq + incoming.length + 1 });
          }
        } catch {
          // ignore network errors silently
        }
      }
      if (incoming.length === 0) return;
      set((s) => ({
        _seq: s._seq + incoming.length,
        updates: [...s.updates, ...incoming].slice(-MAX_UPDATES),
      }));
    };

    const timerId = setInterval(tick, intervalMs);
    set({ isPolling: true, _timerId: timerId });
  },

  stopPolling() {
    const { _timerId } = get();
    if (_timerId !== null) clearInterval(_timerId);
    set({ isPolling: false, _timerId: null });
  },

  clearUpdates() {
    set({ updates: [] });
  },
}));
