// Typed HTTP client for the RTI-BFF REST API.
// In production the Nginx /api/ proxy routes these to the BFF container.
// In development the Vite proxy (vite.config.ts) forwards /api → localhost:8000.

const BASE = '/api';

export type Target = 'rti-so' | 'rti-fsp';
export const TARGETS: Target[] = ['rti-so', 'rti-fsp'];

export const TARGET_LABELS: Record<Target, string> = {
  'rti-so':  'RTI-SO',
  'rti-fsp': 'RTI-FSP',
};

async function req<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`BFF ${method} ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

const get  = <T>(path: string)                  => req<T>(path);
const post = <T>(path: string, body?: unknown)   => req<T>(path, 'POST', body ?? {});

// ── Connection ────────────────────────────────────────────────────────────────

export interface ConnectParams {
  target: Target;
  url?: string;
  port: number;
  cp: string;
  is_server?: boolean;
  application_role?: 'iec_client' | 'iec_server';
  security?: { enableTLS?: boolean; enableOAuth?: boolean };
}

export interface ConnectionStatus {
  state: 'not-connected' | 'listening' | 'connecting' | 'connected' | 'error';
  detail: Record<string, unknown>;
}

// ── Report updates ────────────────────────────────────────────────────────────

export interface ReportUpdate {
  dataRef: string;
  values: unknown;
  timestamp: number;
}

// ── Action / message log entries ──────────────────────────────────────────────

export interface ActionEntry {
  id: number;
  target: string;
  time: string;
  level: string;
  message: string;
  op: string | null;
  status: string;
  duration_ms: number | null;
  detail: Record<string, unknown>;
}

export interface MessageEntry {
  id: number;
  target: string;
  timestamp: string;
  direction: string;
  category: string;
  service_type: string;
  message: string;
  preview: string;
}

// ── API surface ───────────────────────────────────────────────────────────────

export const bffApi = {
  // Connection
  connect:    (params: ConnectParams)   => post<{ status: string }>('/connect', params),
  disconnect: (target: Target)          => post<{ status: string }>('/disconnect', { target }),
  status:     (target: Target)          => get<ConnectionStatus>(`/status?target=${target}`),
  statuses:   ()                        => get<Record<Target, ConnectionStatus>>('/statuses'),

  // Model
  model:        (target: Target)        => get<unknown>(`/model?target=${target}`),
  modelRebuild: (target: Target)        => post<unknown>('/model/rebuild', { target }),
  listLd:       (ld: string, target: Target) =>
                  get<unknown>(`/ld/${encodeURIComponent(ld)}?target=${target}`),
  getLn:        (ld: string, ln: string, target: Target) =>
                  get<unknown>(`/ln/${encodeURIComponent(ld)}/${encodeURIComponent(ln)}?target=${target}`),
  getDoDef:     (ld: string, ln: string, doName: string, target: Target) =>
                  get<unknown>(`/dodef/${encodeURIComponent(ld)}/${encodeURIComponent(ln)}/${encodeURIComponent(doName)}?target=${target}`),

  // Data read / write
  getFcs:     (objRef: string, target: Target) =>
                post<unknown>('/getfcs', { objRef, target }),
  readValue:  (objRef: string, fc: string, target: Target) =>
                post<unknown>('/readvalue', { objRef, fc, target }),
  writeValue: (objRef: string, fc: string, value: unknown, dataType: string, target: Target) =>
                post<unknown>('/writevalue', { objRef, fc, value, dataType, target }),

  // RCB
  rcbValues: (rcbRef: string, rcbType: string, target: Target) =>
               post<unknown>('/rcb/values', { rcbRef, rcbType, target }),
  rcbSet:    (rcbRef: string, rcbType: string, values: Record<string, unknown>, target: Target) =>
               post<unknown>('/rcb/set', { rcbRef, rcbType, values, target }),

  // Report updates (draining queue — call periodically)
  reportUpdates: (target: Target) =>
                   get<ReportUpdate[]>(`/report-updates?target=${target}`),

  // Control
  controlSelect:  (objRef: string, target: Target) =>
                    post<unknown>('/control/select', { objRef, target }),
  controlOperate: (objRef: string, ctlVal: unknown, ctlNum: number, target: Target) =>
                    post<unknown>('/control/operate', { objRef, ctlVal, ctlNum, target }),
  controlCancel:  (objRef: string, target: Target) =>
                    post<unknown>('/control/cancel', { objRef, target }),

  // Diagnostics
  actions:       (target?: Target) =>
                   get<ActionEntry[]>(target ? `/actions?target=${target}` : '/actions'),
  messages:      (target?: Target) =>
                   get<MessageEntry[]>(target ? `/messages?target=${target}` : '/messages'),
  clearMessages: (target?: Target) =>
                   post<unknown>('/messages/clear', target ? { target } : {}),
  messageSettings: () => get<{ limit: number }>('/messages/settings'),
  setMessageLimit: (limit: number) =>
                     post<{ limit: number }>('/messages/settings', { limit }),
};
