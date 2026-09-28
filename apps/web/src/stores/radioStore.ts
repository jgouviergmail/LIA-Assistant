'use client';

/**
 * Observable state of the radio player (ADR-324): what the header button, the
 * mini-player, the page and the dashboard card draw.
 *
 * The controller (`lib/radio/controller.ts`) is the only writer: it pushes its
 * whole view on every change, and the status only ever moves through its state
 * machine.
 */

import { create } from 'zustand';

import type { RadioView } from '@/lib/radio/controller';
import { isOnAir } from '@/lib/radio/machine';

export const IDLE_RADIO_VIEW: RadioView = {
  status: 'idle',
  sessionId: null,
  current: null,
  next: null,
  costEur: null,
  stopAt: null,
  startupEstimateS: null,
  endReason: null,
  error: null,
  refusedBudget: null,
  stationName: null,
  costEstimateEur: null,
  costEstimateS: null,
  articles: [],
};

export interface RadioStore {
  view: RadioView;
  setView: (view: RadioView) => void;
}

export const useRadioStore = create<RadioStore>()(set => ({
  view: IDLE_RADIO_VIEW,
  setView: view => set({ view }),
}));

/**
 * True while the radio holds the audio output (ADR-258's one-owner rule): the
 * wake-word loop and the spoken replies stand aside, as they do for a live
 * session — the station's host saying « LIA » must never wake the assistant.
 */
export function useRadioHoldsAudio(): boolean {
  return useRadioStore(state => isOnAir(state.view.status));
}
