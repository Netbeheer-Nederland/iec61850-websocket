import { z } from 'zod';

export const SocketStateSchema = z.enum(['disconnected', 'connecting', 'connected', 'reconnecting', 'error']);

export const SessionStatusSchema = z.object({
  type: z.literal('session.status'),
  timestamp: z.string(),
  state: SocketStateSchema,
  endpoint: z.string(),
  reconnectAttempt: z.number().int().nonnegative(),
  tls: z.boolean().optional(),
  auth: z.string().optional(),
  messageRatePerMinute: z.number().optional(),
});

export const IecNodeSummarySchema = z.object({
  ref: z.string(),
  logicalDevice: z.string(),
  logicalNode: z.string(),
  description: z.string().optional(),
  commandable: z.boolean().default(false),
  functionalConstraint: z.string().optional(),
});

export const ModelSnapshotSchema = z.object({
  type: z.literal('model.snapshot'),
  timestamp: z.string(),
  nodes: z.array(IecNodeSummarySchema),
});

export const RtiEventSchema = z.object({
  type: z.literal('rti.event'),
  timestamp: z.string(),
  ref: z.string(),
  value: z.union([z.string(), z.number(), z.boolean(), z.null()]),
  quality: z.string().optional(),
  cause: z.string().optional(),
  sequence: z.number().optional(),
  rawPayload: z.string().optional(),
  meta: z.object({
    logicalDevice: z.string().optional(),
    logicalNode: z.string().optional(),
    fc: z.string().optional(),
  }).optional(),
});

export const CommandResultSchema = z.object({
  type: z.literal('command.result'),
  timestamp: z.string(),
  commandId: z.string(),
  ref: z.string(),
  requestedValue: z.union([z.string(), z.number(), z.boolean(), z.null()]).optional(),
  status: z.enum(['accepted', 'rejected', 'transport-error']),
  message: z.string().optional(),
});

export const ScenarioStateSchema = z.object({
  type: z.literal('scenario.state'),
  timestamp: z.string(),
  scenarioId: z.string(),
  state: z.enum(['idle', 'running', 'completed', 'failed']),
  step: z.number().int().nonnegative().default(0),
});

export const DiagnosticFrameSchema = z.object({
  type: z.literal('diagnostic.frame'),
  timestamp: z.string(),
  direction: z.enum(['inbound', 'outbound', 'local']),
  label: z.string(),
  payload: z.string(),
});

export const ErrorMessageSchema = z.object({
  type: z.literal('error'),
  timestamp: z.string(),
  message: z.string(),
});

export const InboundMessageSchema = z.discriminatedUnion('type', [
  SessionStatusSchema,
  ModelSnapshotSchema,
  RtiEventSchema,
  CommandResultSchema,
  ScenarioStateSchema,
  DiagnosticFrameSchema,
  ErrorMessageSchema,
]);

export const OutboundSessionConnectSchema = z.object({
  type: z.literal('session.connect'),
  endpoint: z.string(),
});

export const OutboundModelRequestSchema = z.object({
  type: z.literal('model.request'),
});

export const OutboundCommandRequestSchema = z.object({
  type: z.literal('command.request'),
  commandId: z.string(),
  timestamp: z.string(),
  ref: z.string(),
  value: z.union([z.string(), z.number(), z.boolean(), z.null()]),
});

export const OutboundScenarioRunSchema = z.object({
  type: z.literal('scenario.run'),
  scenarioId: z.string(),
});

export const OutboundScenarioResetSchema = z.object({
  type: z.literal('scenario.reset'),
});

export type SocketState = z.infer<typeof SocketStateSchema>;
export type SessionStatusMessage = z.infer<typeof SessionStatusSchema>;
export type IecNodeSummary = z.infer<typeof IecNodeSummarySchema>;
export type ModelSnapshotMessage = z.infer<typeof ModelSnapshotSchema>;
export type RtiEventMessage = z.infer<typeof RtiEventSchema>;
export type CommandResultMessage = z.infer<typeof CommandResultSchema>;
export type ScenarioStateMessage = z.infer<typeof ScenarioStateSchema>;
export type DiagnosticFrameMessage = z.infer<typeof DiagnosticFrameSchema>;
export type ErrorMessage = z.infer<typeof ErrorMessageSchema>;
export type InboundMessage = z.infer<typeof InboundMessageSchema>;
export type OutboundMessage =
  | z.infer<typeof OutboundSessionConnectSchema>
  | z.infer<typeof OutboundModelRequestSchema>
  | z.infer<typeof OutboundCommandRequestSchema>
  | z.infer<typeof OutboundScenarioRunSchema>
  | z.infer<typeof OutboundScenarioResetSchema>;
