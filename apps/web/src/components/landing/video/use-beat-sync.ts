/**
 * The beat-synced titles (ADR-330, amended), as one hook: the beat map is
 * loaded once the video plays with its sound on, and the driver runs while
 * that holds and the reader did not ask for less motion. It writes on the
 * DOCUMENT (`:root`), so the titles of whatever page the visitor is on read
 * it — the element lives in the layout, not in the landing. Each video of a
 * playlist has its own map: the one loaded is the playing video's, and the
 * driver never runs one video's map against another's clock.
 */

import { useEffect, useState, type RefObject } from 'react';

import type { BeatTrack } from '@/lib/landing/beat-sync';

import { loadBeatTrack } from './use-landing-video';

export interface BeatSyncInputs {
  /** The playing video's rank in playing order. */
  rank: number;
  hasBeats: boolean;
  muted: boolean;
  playing: boolean;
  reducedMotion: boolean;
}

export function useBeatSync(
  videoRef: RefObject<HTMLVideoElement | null>,
  { rank, hasBeats, muted, playing, reducedMotion }: BeatSyncInputs
): void {
  const [loaded, setLoaded] = useState<{ rank: number; track: BeatTrack } | null>(null);
  const beatTrack = loaded !== null && loaded.rank === rank ? loaded.track : null;

  // Loaded once the sound is actually heard — playing AND unmuted — not when
  // it is merely wanted: a start the browser turns muted never fetches it.
  useEffect(() => {
    if (muted || !playing || beatTrack !== null || !hasBeats) return;
    let cancelled = false;
    loadBeatTrack(rank)
      .then(track => {
        if (!cancelled && track) setLoaded({ rank, track });
      })
      .catch(() => {
        // No beat map: the video plays, the titles stay still.
      });
    return () => {
      cancelled = true;
    };
  }, [rank, muted, playing, beatTrack, hasBeats]);

  useEffect(() => {
    const element = videoRef.current;
    if (!element || !beatTrack || muted || !playing || reducedMotion) return;
    let stop: (() => void) | null = null;
    let cancelled = false;
    import('@/lib/landing/beat-sync').then(({ startBeatDriver }) => {
      if (cancelled) return;
      stop = startBeatDriver(element, document.documentElement, beatTrack);
    });
    return () => {
      cancelled = true;
      stop?.();
    };
  }, [videoRef, beatTrack, muted, playing, reducedMotion]);
}
