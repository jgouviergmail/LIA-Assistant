/**
 * The playback policy of the landing video (ADR-330, amended), as one hook.
 *
 * The sources attach when the slot comes near and the browser fetches ahead;
 * playback starts when the slot is IN VIEW — not merely near — never on its
 * own under reduced motion or Save-Data; a muted video pauses when it leaves
 * the view or the tab and resumes when back; a video with sound keeps
 * playing, its music is what the visitor chose; a pause the visitor asked for
 * is kept across the scroll. No slot on the page — another page, or the
 * landing scrolled past the frame — reads as out of view, and the sources,
 * once attached, stay attached whatever slot comes next. When a video of a
 * playlist ends and the next one's sources arrive, playback carries on from
 * its first frame with the sound it had; when the visitor skips to it, it plays
 * whatever the current one was doing — a skip is a request to watch.
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from 'react';

import type { LandingRendition, LandingVideoDescriptor } from '@/lib/landing/media';

import {
  savesData,
  useInViewport,
  useNearViewport,
  usePageLoaded,
  usePrefersReducedMotion,
} from './use-landing-video';

export interface VideoPlayback {
  /** `null` until the viewport has been measured. */
  inView: boolean | null;
  /** The `<source>` list once the frame came near; `null` before. */
  sources: LandingRendition[] | null;
  playing: boolean;
  muted: boolean;
  failed: boolean;
  reducedMotion: boolean;
  togglePlay: () => void;
  toggleSound: () => void;
  handlePlay: () => void;
  handlePause: () => void;
  /** The video ended (a playlist's, never a looping one): the next one plays on. */
  handleEnded: () => void;
  /** The visitor skips to the next video: it plays as soon as its sources load. */
  continueWithNext: () => void;
  handleError: () => void;
}

/** The browser's refusal to play without a user gesture — the only error a muted retry answers. */
function isNotAllowed(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'NotAllowedError';
}

/** The renditions a viewport may be offered, in manifest order. */
export function renditionsFor(
  renditions: LandingRendition[],
  viewportWidth: number
): LandingRendition[] {
  const wide = renditions.filter(r => r.minWidth === undefined || r.minWidth <= viewportWidth);
  if (wide.length > 0) return wide;
  return renditions;
}

export interface VideoPlaybackOptions {
  /** Start muted — a resume record said the sound was off when the page left. */
  startMuted: boolean;
  /** Another explicitly opened player owns playback until it closes. */
  suspended?: boolean;
}

/**
 * The video ref stays the component's (it attaches it in its JSX); the hook
 * reads it from effects and handlers only, never during render. The slot is
 * an ELEMENT: it belongs to another component, and may be absent.
 */
export function useVideoPlayback(
  video: LandingVideoDescriptor,
  slotElement: HTMLElement | null,
  videoRef: RefObject<HTMLVideoElement | null>,
  options: VideoPlaybackOptions = { startMuted: false }
): VideoPlayback {
  const near = useNearViewport(slotElement);
  const observedInView = useInViewport(slotElement);
  // No slot on the page reads as out of view: a muted video pauses, a video
  // with sound keeps playing — docked, where the host draws it.
  const suspended = options.suspended ?? false;
  const inView = !suspended && slotElement ? observedInView : false;
  const pageLoaded = usePageLoaded();
  const reducedMotion = usePrefersReducedMotion();

  // Derived, not set in an effect: `near` is sticky, so once attached the
  // sources stay attached; the width is the one the frame came near with.
  const sources = useMemo(
    () => (near && pageLoaded ? renditionsFor(video.renditions, window.innerWidth) : null),
    [near, pageLoaded, video.renditions]
  );
  const [playing, setPlaying] = useState(false);
  // Sound is wanted by default (owner decision 2026-10-01): the first start is
  // attempted with it, and falls back to a muted start where the browser
  // refuses sound without a gesture — the sound button then says so. A resume
  // record that left muted starts muted.
  const [muted, setMuted] = useState(options.startMuted);
  const [userPaused, setUserPaused] = useState(false);
  const [failed, setFailed] = useState(false);
  // Paused by the page (scrolled away, tab hidden), to be resumed by the
  // page; and "already started for this entry into the view", so a start is
  // attempted ONCE per entry whatever re-renders in between. Refs, because
  // they drive no rendering and must not re-run the effects that set them.
  const pausedByPage = useRef(false);
  const startedForEntry = useRef(false);
  // A playlist video ended while playing: the next sources start as they load.
  const continueAfterSwitch = useRef(false);
  const resumeAfterExclusive = useRef(false);
  const previousSuspended = useRef(false);
  const attempt = useRef({ active: true, suspended, generation: 0, pending: false });

  useLayoutEffect(() => {
    const state = attempt.current;
    state.active = true;
    return () => {
      state.active = false;
      state.generation++;
      state.pending = false;
    };
  }, []);

  const autoplayAllowed = !suspended && !reducedMotion && !savesData();

  const startPlayback = useCallback(() => {
    const state = attempt.current;
    if (!state.active || state.suspended) return;
    const element = videoRef.current;
    if (!element) return;
    const generation = ++state.generation;
    state.pending = true;
    const current = () =>
      state.active &&
      !state.suspended &&
      generation === state.generation &&
      videoRef.current === element;
    element.play().catch((error: unknown) => {
      if (!current()) return;
      if (!element.muted && isNotAllowed(error)) {
        // The common autoplay policy: sound needs a gesture, a muted start
        // does not. Start muted and let the sound button say so.
        element.muted = true;
        setMuted(true);
        element.play().catch(() => {
          if (current()) state.pending = false;
          // Refused even muted (Low Power Mode, policy): the poster stays,
          // the play button is the way in. Nothing to retry.
        });
        return;
      }
      state.pending = false;
      // Refused (Low Power Mode, policy) or interrupted: the poster stays,
      // the play button is the way in. Nothing to retry.
    });
  }, [videoRef]);

  // Suspension owns its own resume intention. It must also stop pending native
  // play attempts, not only a `playing` state whose event has already arrived.
  useLayoutEffect(() => {
    const state = attempt.current;
    state.suspended = suspended;
    if (previousSuspended.current === suspended) return;
    previousSuspended.current = suspended;
    const element = videoRef.current;
    if (suspended) {
      resumeAfterExclusive.current =
        !userPaused && (playing || state.pending || (element !== null && !element.paused));
      element?.pause();
    }
    state.generation++;
    state.pending = false;
  }, [suspended, playing, userPaused, videoRef]);

  // Near the viewport, once the page is loaded, the sources are attached (see
  // `sources`): let the browser fetch ahead, so the first frame is there when
  // the frame is in view.
  useEffect(() => {
    const element = videoRef.current;
    if (sources === null || !element) return;
    attempt.current.generation++;
    attempt.current.pending = false;
    element.preload = 'auto';
    element.load();
  }, [sources, videoRef]);

  // Source loading and playback continuation are separate: suspending a stable
  // source must never reload it or reset its native currentTime.
  useEffect(() => {
    if (sources === null || suspended) return;
    if (continueAfterSwitch.current) {
      continueAfterSwitch.current = false;
      resumeAfterExclusive.current = false;
      startedForEntry.current = true;
      startPlayback();
      return;
    }
    if (!resumeAfterExclusive.current) return;
    resumeAfterExclusive.current = false;
    if (userPaused) return;
    if (!muted || inView === true) {
      pausedByPage.current = false;
      startedForEntry.current = true;
      startPlayback();
    } else pausedByPage.current = true;
  }, [sources, suspended, userPaused, muted, inView, startPlayback]);

  // In view: start (autoplay, or resume what the page paused). Out of view:
  // a muted video pauses — a video with sound keeps playing.
  useEffect(() => {
    const element = videoRef.current;
    if (!element || sources === null || inView === null || suspended) return;
    if (!inView) {
      startedForEntry.current = false;
      if (playing && muted && !userPaused) {
        pausedByPage.current = true;
        element.pause();
      }
      return;
    }
    if (userPaused || playing || startedForEntry.current) return;
    if (autoplayAllowed || pausedByPage.current) {
      startedForEntry.current = true;
      pausedByPage.current = false;
      startPlayback();
    }
  }, [
    inView,
    playing,
    muted,
    suspended,
    userPaused,
    sources,
    autoplayAllowed,
    startPlayback,
    videoRef,
  ]);

  // A hidden tab: pause a muted video (a visitor who hears nothing gains
  // nothing from a decoder running); resume on return, like the scroll.
  useEffect(() => {
    const onVisibility = () => {
      const element = videoRef.current;
      if (!element || userPaused) return;
      if (document.hidden && playing && muted) {
        pausedByPage.current = true;
        element.pause();
      } else if (!document.hidden && pausedByPage.current && !playing && inView) {
        pausedByPage.current = false;
        startedForEntry.current = true;
        startPlayback();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => document.removeEventListener('visibilitychange', onVisibility);
  }, [playing, muted, userPaused, inView, startPlayback, videoRef]);

  const togglePlay = useCallback(() => {
    const element = videoRef.current;
    if (!element) return;
    if (playing) {
      setUserPaused(true);
      element.pause();
      return;
    }
    setUserPaused(false);
    pausedByPage.current = false;
    startedForEntry.current = true;
    startPlayback();
  }, [playing, startPlayback, videoRef]);

  const toggleSound = useCallback(() => {
    const element = videoRef.current;
    if (!element) return;
    const next = !muted;
    element.muted = next;
    setMuted(next);
    if (!next && !playing) {
      setUserPaused(false);
      pausedByPage.current = false;
      startedForEntry.current = true;
      startPlayback();
    }
  }, [muted, playing, startPlayback, videoRef]);

  const handlePlay = useCallback(() => {
    if (!attempt.current.active) return;
    if (attempt.current.suspended) {
      videoRef.current?.pause();
      return;
    }
    attempt.current.pending = false;
    setPlaying(true);
  }, [videoRef]);
  const handlePause = useCallback(() => setPlaying(false), []);
  // `ended` follows the `pause` the end of a non-looping element fires, so
  // nothing here says "the visitor paused": the next video simply plays on.
  const handleEnded = useCallback(() => {
    continueAfterSwitch.current = !userPaused;
  }, [userPaused]);
  // A skip is a gesture asking for the next video: it plays even after a pause.
  const continueWithNext = useCallback(() => {
    setUserPaused(false);
    pausedByPage.current = false;
    startedForEntry.current = true;
    continueAfterSwitch.current = true;
  }, []);
  const handleError = useCallback(() => setFailed(true), []);

  return {
    inView,
    sources,
    playing,
    muted,
    failed,
    reducedMotion,
    togglePlay,
    toggleSound,
    handlePlay,
    handlePause,
    handleEnded,
    continueWithNext,
    handleError,
  };
}
