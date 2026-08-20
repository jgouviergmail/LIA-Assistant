'use client';

/**
 * useBriefingAudio — play the displayed briefing synthesis aloud (A2).
 *
 * One toggle: POST the rendered text to `/briefing/synthesis/audio`
 * (server-side TTS, cost-tracked), play the returned MP3, stop on second
 * press. Unmount stops playback and revokes the object URL — no leaked
 * blob, no ghost audio after navigating away.
 *
 * Raw `fetch` (hooks-layer precedent: `useLLMPricingSheet`) because the
 * response is BINARY — `apiClient` methods parse JSON by contract. The
 * session cookie rides along via `credentials: 'include'` (BFF doctrine).
 */

import { useCallback, useEffect, useRef, useState } from 'react';

import { apiEndpointUrl } from '@/lib/api-client';

export interface UseBriefingAudioResult {
  /** True while the synthesis is being read aloud. */
  playing: boolean;
  /** True while the audio is being fetched/synthesized. */
  loading: boolean;
  /** True after a failed fetch — cleared on the next attempt. */
  error: boolean;
  /** Start reading `text`, or stop if already playing. */
  toggle: (text: string, liaGender?: 'male' | 'female' | null) => Promise<void>;
}

export function useBriefingAudio(): UseBriefingAudioResult {
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);

  const stop = useCallback(() => {
    audioRef.current?.pause();
    audioRef.current = null;
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
    setPlaying(false);
  }, []);

  // Unmount: never leave a ghost voice reading to nobody.
  useEffect(() => stop, [stop]);

  const toggle = useCallback(
    async (text: string, liaGender?: 'male' | 'female' | null) => {
      if (playing || loading) {
        stop();
        return;
      }
      setError(false);
      setLoading(true);
      try {
        const response = await fetch(apiEndpointUrl('/briefing/synthesis/audio'), {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, lia_gender: liaGender ?? null }),
        });
        if (!response.ok) {
          throw new Error(`briefing audio HTTP ${response.status}`);
        }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        urlRef.current = url;
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = stop;
        await audio.play();
        setPlaying(true);
      } catch {
        stop();
        setError(true);
      } finally {
        setLoading(false);
      }
    },
    [playing, loading, stop]
  );

  return { playing, loading, error, toggle };
}
