'use client';

/**
 * Observable state of the live session (ADR-299, spec A11): what the banner
 * draws and what the eyes read. `voiceState` reuses the voice mode's
 * vocabulary so the expression engine needs no new input — `recording` while
 * the person speaks, `speaking` while LIA does, `processing` while a
 * delegation runs.
 *
 * The controller (`lib/live/session-controller.ts`) is the only writer; the
 * status moves through the machine (`apply`), never by assignment.
 */

import { create } from 'zustand';

import { LIVE_CAPTIONS_MAX } from '@/lib/constants';
import {
  isSessionOpen,
  transition,
  type LiveEvent,
  type LiveStatus,
} from '@/lib/live/session-machine';
import { EMPTY_METER, accumulateUsage, type LiveMeter } from '@/lib/live/meter';
import type {
  LiveOutcome,
  LiveRates,
  LiveVendorBill,
  LiveSessionMode,
  LiveTranscriptRole,
  LiveUsageReport,
} from '@/lib/live/types';
import type { VoiceModeState } from '@/stores/voiceModeStore';

export interface LiveCaption {
  role: LiveTranscriptRole;
  text: string;
  /** Epoch milliseconds of the first fragment of this line. */
  at: number;
}

export interface LiveStore {
  status: LiveStatus;
  voiceState: VoiceModeState;
  sessionId: string | null;
  /** The last lines said on either side, bounded (`LIVE_CAPTIONS_MAX`). */
  captions: LiveCaption[];
  muted: boolean;
  delegating: boolean;
  outcome: LiveOutcome | null;
  error: string | null;
  /** The provider's own word on a close it decided (code and reason), for the toast (ADR-300 wave 3). */
  detail: string | null;
  /** Milliseconds before the provider closes the connection, when announced. */
  timeLeftMs: number | null;
  /** Seconds of silence left before the session ends, during the announced last stretch. */
  idleCountdownSeconds: number | null;
  /** The session's cap (epoch ms), moved by every extension. */
  expiresAt: number | null;
  /** The extension dialog is up. */
  extensionOffered: boolean;
  /** What one explicit extension adds, from the API's published bound. */
  extensionMinutes: number;
  extensions: number;
  /** The session model's declared tariff, published by the start (ADR-300 wave 3). */
  rates: LiveRates | null;
  /** The platform prices nothing of this session: the meter shows the clock alone (the vendor's bill comes at the end). */
  vendorBilled: boolean;
  /** What the provider billed the person for the session that just ended — shown once, never recorded. */
  vendorBill: LiveVendorBill | null;
  /** The connector's spend ceiling for this session (euros), if any: the meter draws it. */
  budgetEur: number | null;
  /** The provider's usage reports folded together — the banner's indicative meter. */
  meter: LiveMeter;
  /** Epoch ms of the first `live` status of this session, for a duration-billed meter. */
  liveSince: number | null;
  /**
   * A start asked outside the chat page (the header menu): the chat page's
   * session consumes it on mount. A module store survives the client-side
   * navigation, and so does the click's user activation.
   */
  pendingStart: LiveSessionMode | null;
  /** What this session is: delegating to the chat, or direct (ADR-300 wave 4). */
  mode: LiveSessionMode;
  requestStart: (mode?: LiveSessionMode) => void;
  consumeStart: () => LiveSessionMode | null;
  begin: (sessionId: string, mode?: LiveSessionMode) => void;
  apply: (event: LiveEvent) => void;
  setVoiceState: (state: VoiceModeState) => void;
  /** Appends to the last caption of the same role while a turn grows, else opens a new one. */
  pushCaption: (role: LiveTranscriptRole, text: string, newTurn: boolean) => void;
  setMuted: (muted: boolean) => void;
  setDelegating: (delegating: boolean) => void;
  setTimeLeft: (ms: number | null) => void;
  setIdleCountdown: (seconds: number | null) => void;
  setExpiry: (expiresAt: number | null, extensions: number) => void;
  setExtensionMinutes: (minutes: number) => void;
  offerExtension: (offered: boolean) => void;
  setRates: (rates: LiveRates | null, budgetEur: number | null) => void;
  setVendorBill: (bill: LiveVendorBill | null) => void;
  setVendorBilled: (vendorBilled: boolean) => void;
  reportUsage: (report: LiveUsageReport) => void;
  /** The session became live: the meter's clock starts once, never on a reconnection. */
  markLive: (at: number) => void;
  finish: (outcome: LiveOutcome, error?: string | null, detail?: string | null) => void;
  /** The outcome was told to the person (a toast): clear it so a later mount stays quiet. */
  acknowledge: () => void;
  reset: () => void;
}

const INITIAL = {
  status: 'idle' as LiveStatus,
  voiceState: 'idle' as VoiceModeState,
  sessionId: null,
  captions: [],
  muted: false,
  delegating: false,
  outcome: null,
  error: null,
  detail: null,
  timeLeftMs: null,
  idleCountdownSeconds: null,
  expiresAt: null,
  extensionOffered: false,
  extensionMinutes: 0,
  extensions: 0,
  rates: null,
  vendorBilled: false,
  vendorBill: null,
  budgetEur: null,
  meter: EMPTY_METER,
  liveSince: null,
  pendingStart: null,
  mode: 'delegated' as LiveSessionMode,
};

export const useLiveStore = create<LiveStore>((set, get) => ({
  ...INITIAL,
  requestStart: (mode = 'delegated') => set({ pendingStart: mode }),
  consumeStart: () => {
    const mode = get().pendingStart;
    if (mode === null) return null;
    set({ pendingStart: null });
    return mode;
  },
  begin: (sessionId, mode = 'delegated') => set({ ...INITIAL, sessionId, mode, status: 'minting' }),
  apply: event => set(state => ({ status: transition(state.status, event) })),
  setVoiceState: voiceState => set({ voiceState }),
  pushCaption: (role, text, newTurn) =>
    set(state => {
      const last = state.captions[state.captions.length - 1];
      if (last && last.role === role && !newTurn) {
        const merged = { ...last, text: last.text + text };
        return { captions: [...state.captions.slice(0, -1), merged] };
      }
      const captions = [...state.captions, { role, text, at: Date.now() }];
      return { captions: captions.slice(-LIVE_CAPTIONS_MAX) };
    }),
  setMuted: muted => set({ muted }),
  setDelegating: delegating => set({ delegating }),
  setTimeLeft: timeLeftMs => set({ timeLeftMs }),
  setIdleCountdown: seconds =>
    set(state =>
      state.idleCountdownSeconds === seconds ? state : { idleCountdownSeconds: seconds }
    ),
  setExpiry: (expiresAt, extensions) => set({ expiresAt, extensions }),
  setExtensionMinutes: extensionMinutes => set({ extensionMinutes }),
  offerExtension: extensionOffered => set({ extensionOffered }),
  setRates: (rates, budgetEur) => set({ rates, budgetEur }),
  setVendorBilled: vendorBilled => set({ vendorBilled }),
  setVendorBill: bill => set({ vendorBill: bill }),
  reportUsage: report => set(state => ({ meter: accumulateUsage(state.meter, report) })),
  markLive: at => set(state => (state.liveSince === null ? { liveSince: at } : state)),
  finish: (outcome, error = null, detail = null) =>
    set({
      status: 'ended',
      voiceState: 'idle',
      outcome,
      error,
      detail,
      delegating: false,
      timeLeftMs: null,
      idleCountdownSeconds: null,
      expiresAt: null,
      extensionOffered: false,
    }),
  acknowledge: () => set({ outcome: null, error: null, detail: null }),
  reset: () => set(INITIAL),
}));

/**
 * True while a live session claims the microphone (ADR-258's one-owner rule):
 * the wake-word loop and the push-to-talk stand aside, like they do for a
 * meeting recording.
 */
export function useLiveHoldsMicrophone(): boolean {
  return useLiveStore(state => isSessionOpen(state.status));
}

/**
 * The voice state the expression engine reads: the live session's while it
 * holds the microphone (`recording` while the person speaks, `speaking` while
 * LIA does, `processing` during a delegation), the voice mode's otherwise —
 * so the eyes need no new input (ADR-299, spec A11).
 */
export function effectiveVoiceState(voiceModeState: VoiceModeState): VoiceModeState {
  const live = useLiveStore.getState();
  return isSessionOpen(live.status) ? live.voiceState : voiceModeState;
}
