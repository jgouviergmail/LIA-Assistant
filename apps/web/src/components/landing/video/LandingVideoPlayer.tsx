'use client';

/**
 * The ONE `<video>` element of the visit (ADR-330, amended), in one of three
 * places: FRAMED over the landing's slot — placed in document coordinates, so
 * it scrolls with the page natively and is re-measured only when the layout
 * moves —, DOCKED bottom-left while its music plays with no slot on the page
 * (another public page, or the landing scrolled past the frame), HIDDEN when
 * muted or paused with no slot. The element is never re-parented: the modes
 * are attributes of its container, and the playback policy of
 * `useVideoPlayback` reads « no slot » as « out of view ».
 *
 * A language switch or a full reload remounts the player: it records where it
 * was in the session and a fresh mount resumes from there (`player-session`).
 */

import Link from 'next/link';
import { Pause, Play, Volume2, VolumeX, X } from 'lucide-react';
import { useEffect, useRef, useState, type RefObject } from 'react';

import { Button } from '@/components/ui/button';
import type { Language } from '@/i18n/settings';
import { placementFor } from '@/lib/landing/frame-placement';
import type { LandingVideoDescriptor } from '@/lib/landing/media';
import { readResume, writeResume, type ResumeRecord } from '@/lib/landing/player-session';
import { cn } from '@/lib/utils';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

import type { LandingVideoHostLabels } from './LandingVideoHost';
import type { LandingVideoSlot } from './landing-video-context';
import { useBeatSync } from './use-beat-sync';
import { useVideoPlayback, type VideoPlayback } from './use-video-playback';

export type PlayerMode = 'framed' | 'docked' | 'hidden';

const FRAME_CONTROL_CLASS =
  'size-11 rounded-full bg-black/55 text-white backdrop-blur-sm hover:bg-black/70 hover:text-white focus-visible:ring-white';
const DOCK_CONTROL_CLASS = 'size-9 rounded-full';

/**
 * Where the element goes: framed over a slot that is in view (or not
 * measured yet), or paused in it; docked while the music plays with the frame
 * off-screen or no frame at all; hidden when there is nothing to hear and no
 * frame.
 */
export function playerModeFor(
  hasSlot: boolean,
  soundOn: boolean,
  inView: boolean | null
): PlayerMode {
  if (hasSlot) return soundOn && inView === false ? 'docked' : 'framed';
  return soundOn ? 'docked' : 'hidden';
}

function sessionStorageOrNull(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    // A private window or blocked site data: no record, no resume.
    return null;
  }
}

/**
 * Keep the framed player over the slot: its rect plus the scroll offsets,
 * written on the container directly (no render per measurement), on mount, on
 * a resize of the slot or of the body, on the window's resize and load. The
 * inline placement is removed when the slot goes — the stylesheet places the
 * dock.
 */
function useFramePlacement(
  containerRef: RefObject<HTMLDivElement | null>,
  slotElement: HTMLElement | null
): void {
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !slotElement) return;
    const place = () => {
      const { top, left, width, height } = placementFor(
        slotElement.getBoundingClientRect(),
        window.scrollX,
        window.scrollY
      );
      container.style.top = `${top}px`;
      container.style.left = `${left}px`;
      container.style.width = `${width}px`;
      container.style.height = `${height}px`;
    };
    place();
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(place) : null;
    observer?.observe(slotElement);
    observer?.observe(document.body);
    window.addEventListener('resize', place);
    window.addEventListener('load', place);
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', place);
      window.removeEventListener('load', place);
      for (const property of ['top', 'left', 'width', 'height']) {
        container.style.removeProperty(property);
      }
    };
  }, [containerRef, slotElement]);
}

/**
 * Apply the resume record once the metadata is there; write a record when the
 * player unmounts (a language switch, a stop route) and on `pagehide` (a full
 * reload); pause on unmount, so a stop route silences before it removes.
 */
function useResumeRecord(
  videoRef: RefObject<HTMLVideoElement | null>,
  resume: ResumeRecord | null,
  soundOn: boolean
): void {
  const soundOnRef = useRef(soundOn);
  useEffect(() => {
    soundOnRef.current = soundOn;
  }, [soundOn]);

  useEffect(() => {
    const element = videoRef.current;
    if (!element) return;
    const apply = () => {
      const duration = element.duration || Number.POSITIVE_INFINITY;
      if (resume && resume.time > 0 && resume.time < duration) element.currentTime = resume.time;
    };
    const record = () =>
      writeResume(
        sessionStorageOrNull(),
        { time: element.currentTime, sound: soundOnRef.current },
        Date.now()
      );
    element.addEventListener('loadedmetadata', apply);
    window.addEventListener('pagehide', record);
    return () => {
      element.removeEventListener('loadedmetadata', apply);
      window.removeEventListener('pagehide', record);
      record();
      element.pause();
    };
  }, [videoRef, resume]);
}

/** Play/pause and sound; docked, the way back to the video and the close too. */
function PlayerControls({
  playback,
  labels,
  docked,
  lng,
}: {
  playback: VideoPlayback;
  labels: LandingVideoHostLabels;
  docked: boolean;
  lng: string;
}) {
  const controlClass = docked ? DOCK_CONTROL_CLASS : FRAME_CONTROL_CLASS;
  return (
    <div
      className={cn(
        'flex items-center gap-2',
        docked ? 'landing-video-dock-bar' : 'absolute bottom-3 right-3'
      )}
    >
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={controlClass}
        aria-label={playback.playing ? labels.pause : labels.play}
        onClick={playback.togglePlay}
        data-testid="landing-video-play"
      >
        {playback.playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className={controlClass}
        aria-label={playback.muted ? labels.unmute : labels.mute}
        aria-pressed={!playback.muted}
        onClick={playback.toggleSound}
        data-testid="landing-video-sound"
      >
        {playback.muted ? <VolumeX aria-hidden="true" /> : <Volume2 aria-hidden="true" />}
      </Button>
      {docked && (
        <>
          <Link
            href={`${buildLocalizedPath('/', lng as Language)}#video`}
            className="ml-1 text-xs font-medium text-foreground hover:underline"
          >
            {labels.backToVideo}
          </Link>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={controlClass}
            aria-label={labels.close}
            onClick={playback.togglePlay}
            data-testid="landing-video-close"
          >
            <X aria-hidden="true" />
          </Button>
        </>
      )}
    </div>
  );
}

export function LandingVideoPlayer({
  lng,
  video,
  slot,
  labels,
  onFailed,
}: {
  lng: string;
  video: LandingVideoDescriptor;
  slot: LandingVideoSlot | null;
  labels: LandingVideoHostLabels;
  onFailed: () => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [resume] = useState(() => readResume(sessionStorageOrNull(), Date.now()));
  const slotElement = slot?.element ?? null;
  const playback = useVideoPlayback(video, slotElement, videoRef, {
    startMuted: resume !== null && !resume.sound,
  });
  const soundOn = playback.playing && !playback.muted;
  const mode = playerModeFor(slotElement !== null, soundOn, playback.inView);
  useBeatSync(videoRef, {
    hasBeats: video.hasBeats,
    muted: playback.muted,
    playing: playback.playing,
    reducedMotion: playback.reducedMotion,
  });
  useFramePlacement(containerRef, mode === 'framed' ? slotElement : null);
  useResumeRecord(videoRef, resume, soundOn);

  if (playback.failed) return null;

  const docked = mode === 'docked';
  const [ratioW, ratioH] = video.aspectRatio;
  const onError = () => {
    playback.handleError();
    onFailed();
  };

  return (
    <div
      ref={containerRef}
      className="landing-video-player"
      data-mode={mode}
      data-testid="landing-video-player"
      hidden={mode === 'hidden'}
      role={docked ? 'group' : undefined}
      aria-label={docked ? labels.nowPlaying : undefined}
    >
      <div
        className="landing-video-player-frame relative overflow-hidden rounded-2xl bg-background/80"
        style={{ aspectRatio: `${ratioW} / ${ratioH}` }}
      >
        {/* No caption track: the clip is an illustration with music and no
            speech. A manifest field for captions, when an operator's media
            carries speech, is the one addition this would need. */}
        <video
          ref={videoRef}
          className="size-full object-cover"
          poster={video.poster}
          preload="none"
          loop
          playsInline
          muted={playback.muted}
          aria-label={labels.ariaLabel}
          onPlay={playback.handlePlay}
          onPause={playback.handlePause}
          onError={onError}
        >
          {playback.sources?.map(rendition => (
            <source key={rendition.src} src={rendition.src} type={rendition.type} />
          ))}
        </video>
      </div>
      <PlayerControls playback={playback} labels={labels} docked={docked} lng={lng} />
    </div>
  );
}
