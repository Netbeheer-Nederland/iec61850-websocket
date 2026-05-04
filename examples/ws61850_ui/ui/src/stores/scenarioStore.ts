import { create } from 'zustand';
import type { ScenarioStateMessage } from '../types/protocol';

export interface DemoScenario {
  id: string;
  name: string;
  description: string;
}

interface ScenarioStore {
  scenarios: DemoScenario[];
  activeScenarioId?: string;
  lastState?: ScenarioStateMessage;
  loadScenarios: (scenarios: DemoScenario[]) => void;
  setActiveScenario: (id?: string) => void;
  setScenarioState: (state: ScenarioStateMessage) => void;
}

const defaultScenarios: DemoScenario[] = [
  { id: 'value-change', name: 'Value Change', description: 'Pushes a few measurement updates through the event stream.' },
  { id: 'quality-degrade', name: 'Quality Degradation', description: 'Marks selected measurement points with questionable quality.' },
  { id: 'connection-loss', name: 'Connection Loss & Recovery', description: 'Simulates a reconnect cycle and resumes updates.' },
  { id: 'burst-load', name: 'Burst Load', description: 'Generates a short event burst for grid and chart stress testing.' },
];

export const useScenarioStore = create<ScenarioStore>((set) => ({
  scenarios: defaultScenarios,
  activeScenarioId: undefined,
  lastState: undefined,
  loadScenarios: (scenarios) => set({ scenarios }),
  setActiveScenario: (activeScenarioId) => set({ activeScenarioId }),
  setScenarioState: (lastState) => set({ lastState, activeScenarioId: lastState.scenarioId }),
}));
