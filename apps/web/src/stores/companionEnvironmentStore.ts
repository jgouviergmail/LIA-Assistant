import { create } from 'zustand';
import type { CompanionEnvironment } from '@/components/eyes/environment';

/** The person's channel event saying LIA read newer weather at their place (ADR-294). */
export const COMPANION_WEATHER_SIGNAL = 'companion_weather';

interface EnvironmentState {
  environment: CompanionEnvironment | null;
  /** How many times the server said a newer weather was read (ADR-294, 2026-11-13). */
  refreshRequests: number;
  setEnvironment: (environment: CompanionEnvironment | null) => void;
  /** The person's channel said LIA read newer weather: the owning hook reads it again. */
  requestRefresh: () => void;
  reset: () => void;
}

/** Ephemeral and account-scoped by the owning hook; never persisted. */
export const useCompanionEnvironmentStore = create<EnvironmentState>(set => ({
  environment: null,
  refreshRequests: 0,
  setEnvironment: environment => set({ environment }),
  requestRefresh: () => set(state => ({ refreshRequests: state.refreshRequests + 1 })),
  // A request counter only ever grows: the hook compares it, it never clears it.
  reset: () => set({ environment: null }),
}));
