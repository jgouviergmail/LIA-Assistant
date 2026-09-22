import { create } from 'zustand';
import type { CompanionEnvironment } from '@/components/eyes/environment';

interface EnvironmentState {
  environment: CompanionEnvironment | null;
  setEnvironment: (environment: CompanionEnvironment | null) => void;
  reset: () => void;
}

/** Ephemeral and account-scoped by the owning hook; never persisted. */
export const useCompanionEnvironmentStore = create<EnvironmentState>(set => ({
  environment: null,
  setEnvironment: environment => set({ environment }),
  reset: () => set({ environment: null }),
}));
