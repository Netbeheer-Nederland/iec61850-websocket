import { create } from 'zustand';
import type { IecNodeSummary } from '../types/protocol';

interface ModelStore {
  selectedRef?: string;
  searchQuery: string;
  refsById: Record<string, IecNodeSummary>;
  loadSnapshot: (nodes: IecNodeSummary[]) => void;
  selectRef: (ref: string) => void;
  setSearchQuery: (searchQuery: string) => void;
}

export const useModelStore = create<ModelStore>((set) => ({
  selectedRef: undefined,
  searchQuery: '',
  refsById: {},
  loadSnapshot: (nodes) =>
    set({
      refsById: Object.fromEntries(nodes.map((node) => [node.ref, node])),
      selectedRef: nodes[0]?.ref,
    }),
  selectRef: (selectedRef) => set({ selectedRef }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
}));
