import { create } from 'zustand';
import { bffApi, type ConnectParams, type ConnectionStatus, type Target, TARGETS } from '../services/bffApi';

type BffConnState = ConnectionStatus['state'];

interface TargetState {
  connectionState: BffConnState;
  detail: Record<string, unknown>;
}

interface ConnectionStore {
  targets: Record<Target, TargetState>;
  loading: Record<Target, boolean>;
  error: Record<Target, string | null>;

  refreshStatuses(): Promise<void>;
  connect(params: ConnectParams): Promise<void>;
  disconnect(target: Target): Promise<void>;
}

const defaultTarget = (): TargetState => ({ connectionState: 'not-connected', detail: {} });

export const useConnectionStore = create<ConnectionStore>((set, get) => ({
  targets: { 'rti-so': defaultTarget(), 'rti-fsp': defaultTarget() },
  loading: { 'rti-so': false, 'rti-fsp': false },
  error:   { 'rti-so': null,  'rti-fsp': null  },

  async refreshStatuses() {
    try {
      const all = await bffApi.statuses();
      set(() => ({
        targets: Object.fromEntries(
          TARGETS.map((t) => [t, {
            connectionState: all[t]?.state ?? 'not-connected',
            detail: all[t]?.detail ?? {},
          }])
        ) as Record<Target, TargetState>,
      }));
    } catch {
      // BFF unreachable — leave current state unchanged
    }
  },

  async connect(params) {
    const { target } = params;
    set((s) => ({ loading: { ...s.loading, [target]: true }, error: { ...s.error, [target]: null } }));
    try {
      await bffApi.connect(params);
      await get().refreshStatuses();
    } catch (e: unknown) {
      set((s) => ({ error: { ...s.error, [target]: String(e) } }));
    } finally {
      set((s) => ({ loading: { ...s.loading, [target]: false } }));
    }
  },

  async disconnect(target) {
    set((s) => ({ loading: { ...s.loading, [target]: true }, error: { ...s.error, [target]: null } }));
    try {
      await bffApi.disconnect(target);
      await get().refreshStatuses();
    } catch (e: unknown) {
      set((s) => ({ error: { ...s.error, [target]: String(e) } }));
    } finally {
      set((s) => ({ loading: { ...s.loading, [target]: false } }));
    }
  },
}));
