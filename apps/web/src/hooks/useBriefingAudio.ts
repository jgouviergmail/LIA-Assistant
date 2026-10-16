'use client';

/**
 * Read the displayed briefing aloud after an explicit toggle. Each request and
 * audio resource belongs to one mounted account lifetime: stopping, unmounting
 * or changing account aborts pending work and releases playback exactly once.
 *
 * Raw fetch is needed for the binary MP3 response; BFF session credentials stay
 * in the cookie. Synthesis remains explicit and uses the existing endpoint.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { apiEndpointUrl } from '@/lib/api-client';

export interface UseBriefingAudioResult {
  /** True while the synthesis is being read aloud. */
  playing: boolean;
  /** True while the audio is being fetched/synthesized. */
  loading: boolean;
  /** True after a failed attempt — cleared on the next explicit attempt. */
  error: boolean;
  /** Start reading `text`, or stop the current request/playback. */
  toggle: (text: string, liaGender?: 'male' | 'female' | null) => Promise<void>;
}

interface AudioSession {
  controller: AbortController;
  audio: HTMLAudioElement | null;
  url: string | null;
}

const IDLE = { playing: false, loading: false, error: false };

export function useBriefingAudio(): UseBriefingAudioResult {
  const { user } = useAuth();
  const { lifetime, isCurrent } = useApplicationAccountLifetime(user?.id);
  const [saved, setSaved] = useState({ lifetime, value: IDLE });
  const state = saved.lifetime === lifetime ? saved.value : IDLE;
  // This synchronous reference, unlike rendered state, also guards two presses
  // in the same React batch. The second press cancels the first attempt.
  const sessionRef = useRef<AudioSession | null>(null);

  const release = useCallback(() => {
    const session = sessionRef.current;
    sessionRef.current = null;
    if (!session) return;
    session.controller.abort();
    if (session.audio) {
      session.audio.onended = null;
      session.audio.pause();
      session.audio.removeAttribute('src');
      session.audio.load();
    }
    if (session.url) URL.revokeObjectURL(session.url);
  }, []);

  const stop = useCallback(() => {
    release();
    if (isCurrent()) setSaved({ lifetime, value: IDLE });
  }, [release, lifetime, isCurrent]);

  // Resource cleanup has no state writes and runs for both unmount and owner
  // changes. An A-to-B-to-A switch still creates a different account lifetime.
  useEffect(() => release, [lifetime, release]);

  const toggle = useCallback(
    async (text: string, liaGender?: 'male' | 'female' | null) => {
      if (!isCurrent()) return;
      if (sessionRef.current) {
        stop();
        return;
      }
      const session: AudioSession = {
        controller: new AbortController(),
        audio: null,
        url: null,
      };
      sessionRef.current = session;
      const isActive = () =>
        isCurrent() && !session.controller.signal.aborted && sessionRef.current === session;
      setSaved({ lifetime, value: { ...IDLE, loading: true } });
      try {
        const response = await fetch(apiEndpointUrl('/briefing/synthesis/audio'), {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, lia_gender: liaGender ?? null }),
          signal: session.controller.signal,
        });
        if (!isActive()) return;
        if (!response.ok) throw new Error(`briefing audio HTTP ${response.status}`);
        const blob = await response.blob();
        if (!isActive()) return;
        session.url = URL.createObjectURL(blob);
        const audio = new Audio(session.url);
        session.audio = audio;
        audio.onended = () => {
          if (isActive()) stop();
        };
        await audio.play();
        if (isActive()) setSaved({ lifetime, value: { ...IDLE, playing: true } });
      } catch {
        // A cancelled or superseded attempt owns no state in the new session.
        if (!isActive()) return;
        release();
        setSaved({ lifetime, value: { ...IDLE, error: true } });
      }
    },
    [isCurrent, lifetime, release, stop]
  );

  return { ...state, toggle };
}
