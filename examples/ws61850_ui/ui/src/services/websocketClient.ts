import {
  CommandResultSchema,
  DiagnosticFrameSchema,
  ErrorMessageSchema,
  ModelSnapshotSchema,
  OutboundCommandRequestSchema,
  RtiEventSchema,
  ScenarioStateSchema,
  SessionStatusSchema,
  type DiagnosticFrameMessage,
  type InboundMessage,
  type OutboundMessage,
  type RtiEventMessage,
} from '../types/protocol';
import { useCommandStore } from '../stores/commandStore';
import { useDiagnosticsStore } from '../stores/diagnosticsStore';
import { useModelStore } from '../stores/modelStore';
import { useScenarioStore } from '../stores/scenarioStore';
import { useSessionStore } from '../stores/sessionStore';
import { useStreamStore } from '../stores/streamStore';

const mockNodes = [
  { ref: 'LD0/MMXU1.TotW.mag.f', logicalDevice: 'LD0', logicalNode: 'MMXU1', description: 'Total active power', commandable: false, functionalConstraint: 'MX' },
  { ref: 'LD0/MMXU1.Hz.mag.f', logicalDevice: 'LD0', logicalNode: 'MMXU1', description: 'Grid frequency', commandable: false, functionalConstraint: 'MX' },
  { ref: 'LD0/XCBR1.Pos.stVal', logicalDevice: 'LD0', logicalNode: 'XCBR1', description: 'Breaker status', commandable: false, functionalConstraint: 'ST' },
  { ref: 'LD0/CSWI1.Pos.Oper', logicalDevice: 'LD0', logicalNode: 'CSWI1', description: 'Breaker operate', commandable: true, functionalConstraint: 'CO' },
];

const eventTemplates = [
  { ref: 'LD0/MMXU1.TotW.mag.f', base: 1275, delta: 14, quality: 'good', cause: 'report' },
  { ref: 'LD0/MMXU1.Hz.mag.f', base: 50.0, delta: 0.08, quality: 'good', cause: 'report' },
  { ref: 'LD0/XCBR1.Pos.stVal', base: 1, delta: 1, quality: 'good', cause: 'report' },
];

class WebSocketClient {
  private socket?: WebSocket;
  private retryTimer?: number;
  private manuallyClosed = false;
  private mockInterval?: number;
  private sequence = 0;

  connect(url: string) {
    this.disconnect(false);
    this.manuallyClosed = false;
    useSessionStore.getState().setSocketState('connecting');
    this.emitLocalFrame('Connecting', JSON.stringify({ endpoint: url }));

    if (url.startsWith('mock://')) {
      this.connectMock(url);
      return;
    }

    this.socket = new WebSocket(url);

    this.socket.onopen = () => {
      const now = new Date().toISOString();
      useSessionStore.getState().setSocketState('connected');
      useSessionStore.getState().setConnectedAt(now);
      this.handleMessage({
        type: 'session.status',
        timestamp: now,
        state: 'connected',
        endpoint: url,
        reconnectAttempt: useSessionStore.getState().reconnectAttempt,
        tls: url.startsWith('wss://'),
        auth: 'none',
      });
      this.send({ type: 'model.request' });
    };

    this.socket.onmessage = (event) => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(String(event.data));
      } catch {
        this.emitError('Received non-JSON frame');
        return;
      }
      this.handleMessage(parsed);
    };

    this.socket.onclose = () => {
      useSessionStore.getState().setSocketState('disconnected');
      if (!this.manuallyClosed && useSessionStore.getState().reconnectEnabled) {
        this.scheduleReconnect();
      }
    };

    this.socket.onerror = () => {
      useSessionStore.getState().setSocketState('error');
      this.emitError('WebSocket transport error');
    };
  }

  disconnect(manual = true) {
    this.manuallyClosed = manual;
    window.clearTimeout(this.retryTimer);
    if (this.mockInterval) {
      window.clearInterval(this.mockInterval);
      this.mockInterval = undefined;
    }
    this.socket?.close();
    this.socket = undefined;
    if (manual) {
      useSessionStore.getState().resetSession();
    }
  }

  send(message: OutboundMessage) {
    this.emitLocalFrame('Outbound', JSON.stringify(message, null, 2), 'outbound');

    if (useSessionStore.getState().endpointUrl.startsWith('mock://')) {
      this.handleMockOutbound(message);
      return;
    }

    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    }
  }

  private connectMock(url: string) {
    const now = new Date().toISOString();
    useSessionStore.getState().setSocketState('connected');
    useSessionStore.getState().setConnectedAt(now);
    this.handleMessage({
      type: 'session.status',
      timestamp: now,
      state: 'connected',
      endpoint: url,
      reconnectAttempt: useSessionStore.getState().reconnectAttempt,
      tls: false,
      auth: 'mock',
      messageRatePerMinute: 0,
    });
    this.handleMessage({
      type: 'model.snapshot',
      timestamp: now,
      nodes: mockNodes,
    });

    this.mockInterval = window.setInterval(() => {
      const paused = useStreamStore.getState().paused;
      if (paused) return;

      const template = eventTemplates[this.sequence % eventTemplates.length];
      const timestamp = new Date().toISOString();
      let value: string | number | boolean = template.base;
      if (template.ref.endsWith('stVal')) {
        value = Math.random() > 0.5;
      } else if (template.ref.endsWith('Hz.mag.f')) {
        value = Number((template.base + (Math.random() - 0.5) * template.delta).toFixed(3));
      } else {
        value = Number((template.base + (Math.random() - 0.5) * template.delta * 10).toFixed(2));
      }
      this.handleMessage({
        type: 'rti.event',
        timestamp,
        ref: template.ref,
        value,
        quality: template.quality,
        cause: template.cause,
        sequence: ++this.sequence,
        rawPayload: JSON.stringify({ ref: template.ref, value }),
        meta: {
          logicalDevice: 'LD0',
          logicalNode: template.ref.split('/')[1]?.split('.')[0] ?? 'UNK',
          fc: template.ref.includes('.Oper') ? 'CO' : 'MX',
        },
      });
    }, 1200);
  }

  private handleMockOutbound(message: OutboundMessage) {
    if (message.type === 'model.request') {
      this.handleMessage({
        type: 'model.snapshot',
        timestamp: new Date().toISOString(),
        nodes: mockNodes,
      });
      return;
    }

    if (message.type === 'command.request') {
      const parsed = OutboundCommandRequestSchema.parse(message);
      window.setTimeout(() => {
        const accepted = parsed.ref === 'LD0/CSWI1.Pos.Oper';
        this.handleMessage({
          type: 'command.result',
          timestamp: new Date().toISOString(),
          commandId: parsed.commandId,
          ref: parsed.ref,
          requestedValue: parsed.value,
          status: accepted ? 'accepted' : 'rejected',
          message: accepted ? 'Mock command executed successfully' : 'Point is not commandable in the mock simulator',
        });
        if (accepted) {
          this.handleMessage({
            type: 'rti.event',
            timestamp: new Date().toISOString(),
            ref: 'LD0/XCBR1.Pos.stVal',
            value: Boolean(parsed.value),
            quality: 'good',
            cause: 'command',
            sequence: ++this.sequence,
            rawPayload: JSON.stringify(parsed),
            meta: { logicalDevice: 'LD0', logicalNode: 'XCBR1', fc: 'ST' },
          });
        }
      }, 650);
      return;
    }

    if (message.type === 'scenario.run') {
      const timestamp = new Date().toISOString();
      this.handleMessage({
        type: 'scenario.state',
        timestamp,
        scenarioId: message.scenarioId,
        state: 'running',
        step: 1,
      });

      const complete = () =>
        this.handleMessage({
          type: 'scenario.state',
          timestamp: new Date().toISOString(),
          scenarioId: message.scenarioId,
          state: 'completed',
          step: 2,
        });

      if (message.scenarioId === 'quality-degrade') {
        this.handleMessage({
          type: 'rti.event',
          timestamp,
          ref: 'LD0/MMXU1.Hz.mag.f',
          value: 49.834,
          quality: 'questionable',
          cause: 'quality-change',
          sequence: ++this.sequence,
          rawPayload: '{"scenario":"quality-degrade"}',
          meta: { logicalDevice: 'LD0', logicalNode: 'MMXU1', fc: 'MX' },
        });
        window.setTimeout(complete, 800);
      } else if (message.scenarioId === 'burst-load') {
        for (let index = 0; index < 10; index += 1) {
          window.setTimeout(() => {
            this.handleMessage({
              type: 'rti.event',
              timestamp: new Date().toISOString(),
              ref: 'LD0/MMXU1.TotW.mag.f',
              value: Number((1260 + Math.random() * 45).toFixed(2)),
              quality: 'good',
              cause: 'burst',
              sequence: ++this.sequence,
              rawPayload: '{"scenario":"burst-load"}',
              meta: { logicalDevice: 'LD0', logicalNode: 'MMXU1', fc: 'MX' },
            });
          }, index * 80);
        }
        window.setTimeout(complete, 1000);
      } else if (message.scenarioId === 'connection-loss') {
        useSessionStore.getState().setSocketState('reconnecting');
        window.setTimeout(() => {
          useSessionStore.getState().setSocketState('connected');
          complete();
        }, 1000);
      } else {
        this.handleMessage({
          type: 'rti.event',
          timestamp,
          ref: 'LD0/MMXU1.TotW.mag.f',
          value: Number((1275 + Math.random() * 20).toFixed(2)),
          quality: 'good',
          cause: 'scenario',
          sequence: ++this.sequence,
          rawPayload: `{"scenario":"${message.scenarioId}"}`,
          meta: { logicalDevice: 'LD0', logicalNode: 'MMXU1', fc: 'MX' },
        });
        window.setTimeout(complete, 600);
      }
      return;
    }

    if (message.type === 'scenario.reset') {
      useScenarioStore.getState().setActiveScenario(undefined);
    }
  }

  private handleMessage(message: unknown) {
    useSessionStore.getState().recordHeartbeat(new Date().toISOString());

    const parsed = SessionStatusSchema.safeParse(message);
    if (parsed.success) {
      useSessionStore.getState().setSocketState(parsed.data.state);
      useSessionStore.getState().setMessageRatePerMinute(parsed.data.messageRatePerMinute ?? useSessionStore.getState().messageRatePerMinute);
      this.emitLocalFrame('Session status', JSON.stringify(parsed.data, null, 2));
      return;
    }

    const model = ModelSnapshotSchema.safeParse(message);
    if (model.success) {
      useModelStore.getState().loadSnapshot(model.data.nodes);
      this.emitLocalFrame('Model snapshot', JSON.stringify(model.data, null, 2));
      return;
    }

    const eventMessage = RtiEventSchema.safeParse(message);
    if (eventMessage.success) {
      useStreamStore.getState().appendEvent(eventMessage.data);
      this.emitLocalFrame('RTI event', JSON.stringify(eventMessage.data, null, 2));
      return;
    }

    const commandResult = CommandResultSchema.safeParse(message);
    if (commandResult.success) {
      useCommandStore.getState().resolveCommand(commandResult.data);
      this.emitLocalFrame('Command result', JSON.stringify(commandResult.data, null, 2));
      return;
    }

    const scenarioState = ScenarioStateSchema.safeParse(message);
    if (scenarioState.success) {
      useScenarioStore.getState().setScenarioState(scenarioState.data);
      this.emitLocalFrame('Scenario state', JSON.stringify(scenarioState.data, null, 2));
      return;
    }

    const diagnosticFrame = DiagnosticFrameSchema.safeParse(message);
    if (diagnosticFrame.success) {
      useDiagnosticsStore.getState().appendFrame(diagnosticFrame.data);
      return;
    }

    const errorMessage = ErrorMessageSchema.safeParse(message);
    if (errorMessage.success) {
      useDiagnosticsStore.getState().appendError(errorMessage.data);
      return;
    }

    this.emitError('Unknown inbound message shape');
  }

  private emitLocalFrame(label: string, payload: string, direction: DiagnosticFrameMessage['direction'] = 'local') {
    useDiagnosticsStore.getState().appendFrame({
      type: 'diagnostic.frame',
      timestamp: new Date().toISOString(),
      direction,
      label,
      payload,
    });
  }

  private emitError(message: string) {
    useDiagnosticsStore.getState().appendError({
      type: 'error',
      timestamp: new Date().toISOString(),
      message,
    });
  }

  private scheduleReconnect() {
    useSessionStore.getState().incrementReconnectAttempt();
    useSessionStore.getState().setSocketState('reconnecting');
    this.retryTimer = window.setTimeout(() => {
      this.connect(useSessionStore.getState().endpointUrl);
    }, 1000);
  }
}

export const websocketClient = new WebSocketClient();
