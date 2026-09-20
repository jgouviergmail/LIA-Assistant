'use client';

/**
 * Hear a live voice before choosing it (ADR-299, wave 2 spec A4): one
 * sentence synthesised on the PERSON's own key by the API, handed back as a
 * WAV the browser plays with a plain audio element. One sample at a time —
 * a new one stops the previous; a failure is told once, as a toast.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import apiClient from '@/lib/api-client';
import { base64ToArrayBuffer } from '@/lib/live/base64';
import type { LiveVoiceSampleResponse } from '@/lib/live/types';

export interface UseVoiceSampleReturn {
  /** Play `voice`; `apiKey` before the connector exists (the form), the stored key otherwise. */
  play: (voice: string, apiKey?: string, provider?: string) => Promise<void>;
  playing: boolean;
}

export function useVoiceSample(): UseVoiceSampleReturn {
  const { t } = useTranslation();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);

  const stop = useCallback(() => {
    const current = audioRef.current;
    if (!current) return;
    current.pause();
    current.onended = null;
    URL.revokeObjectURL(current.src);
    audioRef.current = null;
  }, []);

  const play = useCallback(
    async (voice: string, apiKey?: string, provider = 'gemini') => {
      stop();
      try {
        const sample = await apiClient.post<LiveVoiceSampleResponse>('/live/voices/sample', {
          provider,
          voice,
          ...(apiKey ? { api_key: apiKey } : {}),
        });
        const blob = new Blob([base64ToArrayBuffer(sample.audio_base64)], { type: 'audio/wav' });
        const audio = new Audio(URL.createObjectURL(blob));
        audioRef.current = audio;
        audio.onended = () => {
          URL.revokeObjectURL(audio.src);
          if (audioRef.current === audio) audioRef.current = null;
          setPlaying(false);
        };
        setPlaying(true);
        await audio.play();
      } catch {
        setPlaying(false);
        toast.error(t('settings.live_mode.voice_sample_failed'));
      }
    },
    [stop, t]
  );

  useEffect(() => stop, [stop]);

  return { play, playing };
}
