'use client';

/**
 * Zustand store of the meeting recorder (ADR-258).
 *
 * The recorder runs in the dashboard layout so a recording survives navigation
 * between the chat, the settings and the meeting pages; this store is what the
 * composer, the banner and the pages read. It persists the little a reload
 * needs to offer Resume / Finalize / Discard (the meeting id, its format and
 * the next sequence) — the server stays the truth about the meeting itself.
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { MEETING_RECORDER_STATE_KEY } from '@/lib/constants';
import type { EngineInfo, MeetingAudioFormat, MeetingLimits } from '@/types/meetings';

/**
 * Recorder phases.
 *
 * - `starting`: handshake + microphone in progress;
 * - `recording`: capturing and uploading;
 * - `offline`: capturing, uploads waiting for the connection;
 * - `interrupted`: a recording exists but nothing captures (reload, tab death,
 *   microphone lost) — the user decides: resume, finalize, discard;
 * - `stopping`: final segments flushing, then the stop request;
 * - `processing`: the server is producing the minutes;
 * - `error`: the recording ended by a failure the user must read.
 */
export type MeetingRecorderPhase =
  | 'idle'
  | 'starting'
  | 'recording'
  | 'offline'
  | 'interrupted'
  | 'stopping'
  | 'processing'
  | 'error';

/** Phases during which a microphone capture is open. */
export const CAPTURING_PHASES: readonly MeetingRecorderPhase[] = ['recording', 'offline'];

/** Phases during which a meeting exists on the server and is not yet processed. */
export const LIVE_PHASES: readonly MeetingRecorderPhase[] = [
  'starting',
  'recording',
  'offline',
  'interrupted',
  'stopping',
];

export interface PersistedRecording {
  meetingId: string;
  /** ISO timestamp the server assigned. */
  startedAt: string;
  audioFormat: MeetingAudioFormat;
  mimeType: string | null;
  segmentSeconds: number;
  /** Sequence the next segment will take — the count a stop declares. */
  nextSequence: number;
}

export interface MeetingRecorderState {
  phase: MeetingRecorderPhase;
  recording: PersistedRecording | null;
  engine: EngineInfo | null;
  limits: MeetingLimits | null;
  elapsedSeconds: number;
  /** RMS level in [0, 1] for the meter. */
  level: number;
  uploadedSegments: number;
  pendingSegments: number;
  /** The silence watchdog asked "still recording?" and awaits an answer. */
  silencePrompt: boolean;
  /** Stable error code (server `detail.code` or a client code) while `phase === 'error'`. */
  errorCode: string | null;
  /** Sequences the server never received, when a stop was refused. */
  missingSegments: number[] | null;
}

export interface MeetingRecorderActions {
  begin: (
    recording: PersistedRecording,
    engine: EngineInfo | null,
    limits: MeetingLimits | null
  ) => void;
  setPhase: (phase: MeetingRecorderPhase) => void;
  setNextSequence: (next: number) => void;
  setProgress: (uploaded: number, pending: number) => void;
  setLevel: (level: number) => void;
  setElapsed: (seconds: number) => void;
  setSilencePrompt: (open: boolean) => void;
  setMissingSegments: (missing: number[] | null) => void;
  fail: (code: string) => void;
  reset: () => void;
}

export type MeetingRecorderStore = MeetingRecorderState & MeetingRecorderActions;

const INITIAL: MeetingRecorderState = {
  phase: 'idle',
  recording: null,
  engine: null,
  limits: null,
  elapsedSeconds: 0,
  level: 0,
  uploadedSegments: 0,
  pendingSegments: 0,
  silencePrompt: false,
  errorCode: null,
  missingSegments: null,
};

/**
 * What a reload should believe about a phase it did not witness.
 *
 * A capture cannot survive a page: anything that was capturing or stopping
 * comes back as `interrupted` — the user chooses. `processing` is server-side
 * and comes back as is (the page polls it). Everything else is idle.
 */
export function phaseAfterReload(phase: MeetingRecorderPhase): MeetingRecorderPhase {
  if (LIVE_PHASES.includes(phase)) return 'interrupted';
  if (phase === 'processing') return 'processing';
  return 'idle';
}

/** True while a microphone capture is open (recording, or offline with the mic still on). */
export function isCapturingPhase(phase: MeetingRecorderPhase): boolean {
  return CAPTURING_PHASES.includes(phase);
}

export const useMeetingRecorderStore = create<MeetingRecorderStore>()(
  persist(
    set => ({
      ...INITIAL,
      begin: (recording, engine, limits) =>
        set({
          ...INITIAL,
          phase: 'recording',
          recording,
          engine,
          limits,
        }),
      setPhase: phase => set({ phase }),
      setNextSequence: next =>
        set(state => ({
          recording: state.recording ? { ...state.recording, nextSequence: next } : null,
        })),
      setProgress: (uploaded, pending) =>
        set({ uploadedSegments: uploaded, pendingSegments: pending }),
      setLevel: level => set({ level }),
      setElapsed: seconds => set({ elapsedSeconds: seconds }),
      setSilencePrompt: open => set({ silencePrompt: open }),
      setMissingSegments: missing => set({ missingSegments: missing }),
      fail: code => set({ phase: 'error', errorCode: code, level: 0, silencePrompt: false }),
      reset: () => set({ ...INITIAL }),
    }),
    {
      name: MEETING_RECORDER_STATE_KEY,
      partialize: state => ({
        phase: phaseAfterReload(state.phase),
        recording: state.recording,
        // The bounds the server published at start: a resume after a reload
        // keeps the same cadence and the same silence window.
        limits: state.limits,
      }),
    }
  )
);

/**
 * Selector hook other microphone owners read (voice playback, wake word):
 * subscribes to the phase only, so a level tick never re-renders them.
 */
export function useMeetingIsCapturing(): boolean {
  return useMeetingRecorderStore(state => isCapturingPhase(state.phase));
}
