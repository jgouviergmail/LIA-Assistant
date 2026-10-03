/**
 * The hooks behind the landing video (ADR-330): the descriptor the section
 * mounts on, the reader's motion preference, and the two distances that
 * drive playback — "near" (attach the sources, let the browser fetch ahead)
 * and "in view" (start; a muted video pauses when it leaves).
 */

import { useEffect, useState } from 'react';

import type { BeatTrack } from '@/lib/landing/beat-sync';
import type { LandingVideoDescriptor } from '@/lib/landing/media';

export const LANDING_MEDIA_ENDPOINT = '/api/landing-media';
export const LANDING_MEDIA_BEATS_ENDPOINT = '/api/landing-media/beats';

/** How far ahead of the viewport the video starts loading (CSS px). */
export const LANDING_VIDEO_NEAR_MARGIN_PX = 600;

export type LandingMediaState =
  | { status: 'loading' }
  | { status: 'none' }
  /** The videos in playing order, never empty. */
  | { status: 'ready'; playlist: LandingVideoDescriptor[] };

interface LandingMediaBody {
  video: LandingVideoDescriptor | null;
  /** Absent from an answer cached before the server knew of more than one video. */
  next?: LandingVideoDescriptor[];
}

/** Ask the server, once, whether this deployment shows a video — or several, one after the other. */
export function useLandingMedia(): LandingMediaState {
  const [state, setState] = useState<LandingMediaState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    fetch(LANDING_MEDIA_ENDPOINT, { headers: { accept: 'application/json' } })
      .then(async response => (response.ok ? response.json() : { video: null }))
      .then((body: LandingMediaBody) => {
        if (cancelled) return;
        setState(
          body.video
            ? { status: 'ready', playlist: [body.video, ...(body.next ?? [])] }
            : { status: 'none' }
        );
      })
      .catch(() => {
        if (!cancelled) setState({ status: 'none' });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)';

/**
 * `prefers-reduced-motion: reduce`, read at mount and followed live. The
 * hook only runs in the browser (the section mounts after the descriptor
 * arrived), so the first value is the real one, not a server guess.
 */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => window.matchMedia(REDUCED_MOTION_QUERY).matches);

  useEffect(() => {
    const query = window.matchMedia(REDUCED_MOTION_QUERY);
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  return reduced;
}

/**
 * The beat map of the video at `rank` in playing order, as a track, when the
 * sound goes on — the engine and the schema are imported then too, so a
 * visitor who never unmutes loads neither. `null` when there is no map or it
 * does not validate: the video plays, the titles stay still.
 */
export async function loadBeatTrack(rank: number): Promise<BeatTrack | null> {
  const [response, engine, schema] = await Promise.all([
    fetch(`${LANDING_MEDIA_BEATS_ENDPOINT}?video=${rank}`, {
      headers: { accept: 'application/json' },
    }),
    import('@/lib/landing/beat-sync'),
    import('@/lib/landing/beats-schema'),
  ]);
  if (!response.ok) return null;
  return engine.createBeatTrack(schema.parseBeatMap(await response.json()));
}

/** `Save-Data` from the browser, when it says so. */
export function savesData(): boolean {
  const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
  return connection?.saveData === true;
}

/**
 * `null` until the observer has reported once ON THIS ELEMENT: "not observed
 * yet" is not "out of view" — read as false, it paused the video the moment
 * autoplay started, before the viewport had been measured — and a new slot
 * starts unmeasured rather than with the previous slot's answer. A sticky
 * answer (`once`) holds across elements: what came near once stays attached.
 */
function useIntersects(
  element: Element | null,
  options: { rootMargin?: string; once?: boolean } = {}
): boolean | null {
  const [seen, setSeen] = useState<{ element: Element; value: boolean } | null>(null);
  const { rootMargin, once = false } = options;
  const sticky = once && seen?.value === true;

  useEffect(() => {
    if (!element || sticky) return;
    const observer = new IntersectionObserver(
      entries => {
        for (const entry of entries) {
          if (entry.target !== element) continue;
          setSeen({ element, value: entry.isIntersecting });
          if (once && entry.isIntersecting) observer.disconnect();
        }
      },
      rootMargin ? { rootMargin } : undefined
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [element, rootMargin, once, sticky]);

  if (sticky) return true;
  if (!element || seen?.element !== element) return null;
  return seen.value;
}

/**
 * Came within `LANDING_VIDEO_NEAR_MARGIN_PX` of the viewport (null until
 * measured) — and stays true, whatever slot comes next: the sources it
 * attaches are never detached.
 */
export function useNearViewport(element: Element | null): boolean | null {
  return useIntersects(element, {
    rootMargin: `${LANDING_VIDEO_NEAR_MARGIN_PX}px 0px`,
    once: true,
  });
}

/** Actually intersecting the viewport (null until measured on this element). */
export function useInViewport(element: Element | null): boolean | null {
  return useIntersects(element);
}

/**
 * The document is loaded: the video never competes with the page's own
 * assets. Read once at mount (this hook only runs in the browser, after the
 * descriptor arrived), then followed through the `load` event.
 */
export function usePageLoaded(): boolean {
  const [loaded, setLoaded] = useState(() => document.readyState === 'complete');

  useEffect(() => {
    if (loaded) return;
    const onLoad = () => setLoaded(true);
    window.addEventListener('load', onLoad);
    return () => window.removeEventListener('load', onLoad);
  }, [loaded]);

  return loaded;
}
