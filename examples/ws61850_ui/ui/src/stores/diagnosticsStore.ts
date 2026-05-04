import { create } from 'zustand';
import { appendRingBuffer } from '../utils/ringBuffer';
import type { DiagnosticFrameMessage, ErrorMessage } from '../types/protocol';

interface DiagnosticsState {
  frames: DiagnosticFrameMessage[];
  errors: ErrorMessage[];
  appendFrame: (frame: DiagnosticFrameMessage) => void;
  appendError: (error: ErrorMessage) => void;
  clear: () => void;
}

export const useDiagnosticsStore = create<DiagnosticsState>((set) => ({
  frames: [],
  errors: [],
  appendFrame: (frame) => set((state) => ({ frames: appendRingBuffer(state.frames, frame, 250) })),
  appendError: (error) => set((state) => ({ errors: appendRingBuffer(state.errors, error, 50) })),
  clear: () => set({ frames: [], errors: [] }),
}));
