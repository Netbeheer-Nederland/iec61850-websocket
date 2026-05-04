import { create } from 'zustand';

type ThemeMode = 'light' | 'dark';

interface UiStore {
  themeMode: ThemeMode;
  toggleTheme: () => void;
}

export const useUiStore = create<UiStore>((set) => ({
  themeMode: 'dark',
  toggleTheme: () => set((state) => ({ themeMode: state.themeMode === 'dark' ? 'light' : 'dark' })),
}));
