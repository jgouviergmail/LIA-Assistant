/** Owner-bound observation of the existing background reader, never another poll. */
import { create } from 'zustand';
import { useEyesChatStore } from './eyesChatStore';
import { useEyesSignalsStore } from './eyesSignalsStore';
import { useLiveStore } from './liveStore';
import { usePsycheStore } from './psycheStore';
import { useCompanionEnvironmentStore } from './companionEnvironmentStore';
export const COMPANION_WORK_POLL_MS = 6000;
export const COMPANION_WORK_FRESH_MS = COMPANION_WORK_POLL_MS * 2 + 3000;
export interface CompanionWorkSample {
  working: boolean;
  at: number;
}
interface CompanionActivityState {
  ownerId: string | null;
  sample: CompanionWorkSample | null;
  bindOwner(ownerId: string | null): void;
  record(ownerId: string, working: boolean, at?: number): void;
  clearSample(ownerId: string): void;
}
export const useCompanionActivityStore = create<CompanionActivityState>((set, get) => ({
  ownerId: null,
  sample: null,
  bindOwner(ownerId) {
    if (get().ownerId === ownerId) return;
    useEyesSignalsStore.getState().reset();
    useEyesChatStore.getState().reset();
    usePsycheStore.getState().bindOwner(ownerId);
    useCompanionEnvironmentStore.getState().reset();
    // Only an ephemeral visual observation; microphone/session/billing state is untouched.
    useLiveStore.setState({ lastActivity: null });
    set({ ownerId, sample: null });
  },
  record(ownerId, working, at = Date.now()) {
    if (get().ownerId !== ownerId || !Number.isFinite(at)) return;
    set({ sample: { working, at } });
  },
  clearSample(ownerId) {
    if (get().ownerId === ownerId) set({ sample: null });
  },
}));
