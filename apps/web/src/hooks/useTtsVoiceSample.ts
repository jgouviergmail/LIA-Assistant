'use client';

/** A voice choice starts one sample, independent of saving that choice. */
import { useCallback, useEffect, useRef, useState } from 'react';

import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useAuth } from '@/hooks/useAuth';
import apiClient from '@/lib/api-client';
import { unlockMedia } from '@/lib/audio/unlock-media';
import { base64ToArrayBuffer } from '@/lib/live/base64';
import { isSessionOpen } from '@/lib/live/session-machine';
import type { RadioPreferences, RadioSpeakingRole } from '@/lib/radio/types';
import type { RadioStatus } from '@/lib/radio/machine';
import { useLiveHoldsMicrophone, useLiveStore } from '@/stores/liveStore';
import {
  isCapturingPhase,
  useMeetingIsCapturing,
  useMeetingRecorderStore,
} from '@/stores/meetingRecorderStore';
import { useRadioStore } from '@/stores/radioStore';
import type { LiaVoiceGender } from '@/types/lia-voices';

export type TtsVoiceSampleRequest =
  | {
      endpoint: '/voice/lia-voices/sample';
      payload: { gender: LiaVoiceGender; voice_id: string | null };
    }
  | {
      endpoint: '/radio/voices/sample';
      payload: { role: RadioSpeakingRole; voices: RadioPreferences['voices'] };
    };

interface TtsVoiceSampleResponse {
  audio_base64: string;
  mime_type: string;
  voice_id: string;
}

type SampleStatus = 'idle' | 'loading' | 'playing' | 'error' | 'blocked' | 'radio_wait';

export interface TtsVoiceSamplePlayback {
  status: SampleStatus;
  canReplay: boolean;
  radioPaused: boolean;
  play: (request: TtsVoiceSampleRequest) => Promise<void>;
  replay: () => Promise<void>;
  stop: () => void;
}

interface AudioSession {
  controller: AbortController;
  audio: HTMLAudioElement;
  url: string | null;
  pausingRadio: boolean;
  radioPaused: boolean;
}

const IDLE = { status: 'idle' as SampleStatus, canReplay: false, radioPaused: false };

function obsoleteSession(session: AudioSession | null, current: AudioSession | null): boolean {
  return session !== null && (current !== session || session.controller.signal.aborted);
}

/** Re-read after asynchronous boundaries: a capture may begin before React renders it. */
function captureActive(): boolean {
  return (
    isCapturingPhase(useMeetingRecorderStore.getState().phase) ||
    isSessionOpen(useLiveStore.getState().status)
  );
}

function radioNeedsPause(status: RadioStatus): boolean {
  return status === 'playing' || status === 'waiting';
}

function blockingSource(allowRadioPause: boolean): SampleStatus | null {
  if (captureActive()) return 'blocked';
  const status = useRadioStore.getState().view.status;
  if (status === 'starting' || status === 'ending') return 'radio_wait';
  if (!allowRadioPause && radioNeedsPause(status)) return 'radio_wait';
  return null;
}

async function pauseRadioForSample(
  session: AudioSession,
  active: () => boolean,
  fail: (reason: SampleStatus) => void
): Promise<boolean> {
  if (!session.pausingRadio) return true;
  // Idle settings never initialize the radio player, music, API or AudioContext.
  const { radioPlayer } = await import('@/lib/radio/player');
  if (!active()) return false;
  const blocked = blockingSource(true);
  if (blocked) {
    fail(blocked);
    return false;
  }
  if (radioNeedsPause(useRadioStore.getState().view.status)) {
    radioPlayer().pause();
    session.radioPaused = true;
  }
  session.pausingRadio = false;
  return true;
}

export function useTtsVoiceSample(): TtsVoiceSamplePlayback {
  const { user } = useAuth();
  const { lifetime, isCurrent } = useApplicationAccountLifetime(user?.id);
  const meetingCapturing = useMeetingIsCapturing();
  const liveCapturing = useLiveHoldsMicrophone();
  const radioStatus = useRadioStore(state => state.view.status);
  const [saved, setSaved] = useState({ lifetime, ...IDLE });
  const state = saved.lifetime === lifetime ? saved : IDLE;
  const sessionRef = useRef<AudioSession | null>(null);
  const choice = useRef<{ lifetime: typeof lifetime; request: TtsVoiceSampleRequest } | null>(null);

  const release = useCallback(() => {
    const session = sessionRef.current;
    sessionRef.current = null;
    if (!session) return;
    session.controller.abort();
    session.audio.onended = null;
    session.audio.onerror = null;
    session.audio.pause();
    session.audio.removeAttribute('src');
    session.audio.load();
    if (session.url) URL.revokeObjectURL(session.url);
  }, []);

  const stop = useCallback(() => {
    if (!isCurrent()) return;
    release();
    setSaved(previous => ({
      lifetime,
      status: 'idle',
      canReplay: choice.current?.lifetime === lifetime,
      radioPaused: previous.lifetime === lifetime && previous.radioPaused,
    }));
  }, [isCurrent, lifetime, release]);

  useEffect(() => release, [lifetime, release]);

  // A recording or a resumed radio takes priority over this optional sample.
  useEffect(() => {
    const session = sessionRef.current;
    if (!session || !isCurrent()) return;
    const capture = meetingCapturing || liveCapturing;
    const radioResumed =
      !session.pausingRadio && (radioStatus === 'playing' || radioStatus === 'waiting');
    const radioMoving = radioStatus === 'starting' || radioStatus === 'ending';
    if (!capture && !radioResumed && !radioMoving) return;
    release();
    setSaved({
      lifetime,
      status: capture ? 'blocked' : radioMoving ? 'radio_wait' : 'idle',
      canReplay: true,
      radioPaused: session.radioPaused,
    });
  }, [meetingCapturing, liveCapturing, radioStatus, isCurrent, lifetime, release]);

  const play = useCallback(
    async (request: TtsVoiceSampleRequest) => {
      if (!isCurrent()) return;
      choice.current = { lifetime, request };
      release();
      const blocked = blockingSource(true);
      if (blocked) {
        setSaved({
          lifetime,
          status: blocked,
          canReplay: true,
          radioPaused: false,
        });
        return;
      }
      setSaved({ lifetime, status: 'loading', canReplay: true, radioPaused: false });
      let session: AudioSession | null = null;
      try {
        // Prime within the selection/replay gesture, then reuse this very
        // element after synthesis (Safari's permission is element-specific).
        const audio = new Audio();
        session = {
          controller: new AbortController(),
          audio,
          url: null,
          pausingRadio: radioNeedsPause(useRadioStore.getState().view.status),
          radioPaused: false,
        };
        sessionRef.current = session;
        unlockMedia(audio);
        const current = session;
        const active = () =>
          isCurrent() && !current.controller.signal.aborted && sessionRef.current === current;
        const fail = (status: SampleStatus) => {
          if (!active()) return;
          release();
          setSaved({ lifetime, status, canReplay: true, radioPaused: current.radioPaused });
        };
        if (!(await pauseRadioForSample(current, active, fail))) return;
        if (!active()) return;
        const beforeRequest = blockingSource(false);
        if (beforeRequest) {
          fail(beforeRequest);
          return;
        }
        setSaved({
          lifetime,
          status: 'loading',
          canReplay: true,
          radioPaused: current.radioPaused,
        });
        const response = await apiClient.post<TtsVoiceSampleResponse>(
          request.endpoint,
          request.payload,
          { signal: current.controller.signal }
        );
        if (!active()) return;
        const beforePlayback = blockingSource(false);
        if (beforePlayback) {
          fail(beforePlayback);
          return;
        }
        current.url = URL.createObjectURL(
          new Blob([base64ToArrayBuffer(response.audio_base64)], { type: response.mime_type })
        );
        // The silent priming clip must never finish/cancel pending synthesis.
        audio.src = current.url;
        audio.onended = () => {
          if (active()) stop();
        };
        audio.onerror = () => fail('error');
        await audio.play();
        if (active()) {
          setSaved({
            lifetime,
            status: 'playing',
            canReplay: true,
            radioPaused: current.radioPaused,
          });
        }
      } catch {
        if (!isCurrent()) return;
        if (obsoleteSession(session, sessionRef.current)) return;
        release();
        setSaved({
          lifetime,
          status: 'error',
          canReplay: true,
          radioPaused: session?.radioPaused ?? false,
        });
      }
    },
    [isCurrent, lifetime, release, stop]
  );

  const replay = useCallback(async () => {
    if (isCurrent() && choice.current?.lifetime === lifetime) await play(choice.current.request);
  }, [isCurrent, lifetime, play]);

  return {
    status: state.status,
    canReplay: state.canReplay,
    radioPaused: state.radioPaused && radioStatus === 'paused',
    play,
    replay,
    stop,
  };
}
