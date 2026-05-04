import { create } from 'zustand';
import type { CommandResultMessage } from '../types/protocol';

interface PendingCommand {
  commandId: string;
  ref: string;
  value: string | number | boolean | null;
  timestamp: string;
}

interface CommandStore {
  pendingCommands: PendingCommand[];
  recentResults: CommandResultMessage[];
  queueCommand: (command: PendingCommand) => void;
  resolveCommand: (result: CommandResultMessage) => void;
  clearHistory: () => void;
}

export const useCommandStore = create<CommandStore>((set) => ({
  pendingCommands: [],
  recentResults: [],
  queueCommand: (command) => set((state) => ({ pendingCommands: [command, ...state.pendingCommands].slice(0, 20) })),
  resolveCommand: (result) =>
    set((state) => ({
      pendingCommands: state.pendingCommands.filter((command) => command.commandId !== result.commandId),
      recentResults: [result, ...state.recentResults].slice(0, 50),
    })),
  clearHistory: () => set({ pendingCommands: [], recentResults: [] }),
}));
