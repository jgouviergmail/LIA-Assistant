'use client';

/**
 * The recorder as React sees it (ADR-258).
 *
 * One controller per provider, created with the production dependencies; the
 * hook subscribes to the store and exposes the handful of commands the UI
 * needs. Consumers get the SAME controller wherever they are in the dashboard
 * — the composer starts, the banner stops, the page resumes.
 */

import { useCallback, useEffect, useMemo } from 'react';

import { MeetingRecorderController, type StopOutcome } from '@/lib/meetings/recorder-controller';
import { createRecorderDeps } from '@/lib/meetings/recorder-deps';
import { isMeetingRecordingSupported } from '@/lib/meetings/audio-format';
import {
  LIVE_PHASES,
  isCapturingPhase,
  useMeetingRecorderStore,
  type MeetingRecorderState,
} from '@/stores/meetingRecorderStore';
import type { MeetingDetail } from '@/types/meetings';

export interface UseMeetingRecorderReturn extends MeetingRecorderState {
  /** Whether this browser can capture at all. */
  isSupported: boolean;
  /** True while a capture is open (recording or offline). */
  isCapturing: boolean;
  /** True while a meeting exists and is not yet processed. */
  isLive: boolean;
  start: () => Promise<void>;
  stop: () => Promise<StopOutcome>;
  finalizeWithGaps: () => Promise<StopOutcome>;
  resume: () => Promise<void>;
  discard: () => Promise<void>;
  dismiss: () => void;
  continueAfterSilence: () => void;
}

/**
 * Create the recorder and bind it to the store.
 *
 * @param onProcessed - Called when a meeting this page stopped reaches its
 *   terminal state (the provider toasts and links to the minutes).
 */
export function useMeetingRecorder(
  onProcessed?: (detail: MeetingDetail) => void
): UseMeetingRecorderReturn {
  const state = useMeetingRecorderStore();
  const controller = useMemo(() => new MeetingRecorderController(createRecorderDeps()), []);

  // The completion listener is re-bound as an effect, never through a ref
  // written during render (react-hooks/refs).
  useEffect(() => {
    controller.setOnProcessed(onProcessed ?? null);
  }, [controller, onProcessed]);

  useEffect(() => {
    void controller.reconcile();
    return () => {
      void controller.dispose();
    };
  }, [controller]);

  const start = useCallback(() => controller.start(), [controller]);
  const stop = useCallback(() => controller.stop({ reason: 'user' }), [controller]);
  const finalizeWithGaps = useCallback(() => controller.finalizeWithGaps(), [controller]);
  const resume = useCallback(() => controller.resume(), [controller]);
  const discard = useCallback(() => controller.discard(), [controller]);
  const dismiss = useCallback(() => controller.dismiss(), [controller]);
  const continueAfterSilence = useCallback(() => controller.continueAfterSilence(), [controller]);

  return {
    ...state,
    isSupported: isMeetingRecordingSupported(),
    isCapturing: isCapturingPhase(state.phase),
    isLive: LIVE_PHASES.includes(state.phase),
    start,
    stop,
    finalizeWithGaps,
    resume,
    discard,
    dismiss,
    continueAfterSilence,
  };
}
