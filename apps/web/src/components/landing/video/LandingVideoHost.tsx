'use client';

/**
 * The landing video's host (ADR-330, amended): mounted by the `[lng]` layout
 * around every page, it keeps ONE `<video>` element for the whole visit. The
 * landing's section registers its frame here; the element is framed over it,
 * docked when its music plays with no frame on the page, and gone on the
 * sign-in and dashboard routes (`lib/landing/player-routes.ts`).
 *
 * The descriptor comes from the section's own request: no page but the
 * landing ever asks the server about the video, and the player exists only
 * once a frame has been registered.
 *
 * The section may hand over several videos: the host keeps the rank of the
 * one the player holds, moves to the next when it ends and back to the first
 * after the last — a single video simply loops. A new section mount answers
 * the same list with new objects; the host keeps the list it holds then, so
 * returning to the landing never reloads what is playing.
 */

import { usePathname } from 'next/navigation';
import { useCallback, useMemo, useState, type ReactNode } from 'react';

import type { LandingVideoDescriptor } from '@/lib/landing/media';
import { playerRouteKind } from '@/lib/landing/player-routes';
import { readResume, sessionStorageOrNull } from '@/lib/landing/player-session';

import { LandingVideoPlayer } from './LandingVideoPlayer';
import {
  LandingVideoProvider,
  type LandingVideoRegistry,
  type LandingVideoSlot,
} from './landing-video-context';

export interface LandingVideoHostLabels {
  ariaLabel: string;
  play: string;
  pause: string;
  unmute: string;
  mute: string;
  nowPlaying: string;
  backToVideo: string;
  close: string;
}

export function LandingVideoHost({
  lng,
  labels,
  children,
}: {
  lng: string;
  labels: LandingVideoHostLabels;
  children: ReactNode;
}) {
  const [slot, setSlot] = useState<LandingVideoSlot | null>(null);
  const [playlist, setPlaylist] = useState<LandingVideoDescriptor[] | null>(null);
  const [failed, setFailed] = useState(false);
  // What the previous mount was doing (a language switch, a reload): read once.
  const [resume] = useState(() => readResume(sessionStorageOrNull(), Date.now()));
  const [rank, setRank] = useState(() => resume?.video ?? 0);

  const registerSlot = useCallback((next: LandingVideoSlot) => {
    setSlot(next);
    setPlaylist(held => (samePlaylist(held, next.playlist) ? held : next.playlist));
    return () => setSlot(current => (current === next ? null : current));
  }, []);
  // A rank the list does not hold (a resume record from a longer list) is the first video.
  const current = playlist !== null && rank < playlist.length ? rank : 0;
  const registry = useMemo<LandingVideoRegistry>(
    () => ({ failed, current, registerSlot }),
    [failed, current, registerSlot]
  );
  const onFailed = useCallback(() => setFailed(true), []);
  const length = playlist?.length ?? 1;
  const onEnded = useCallback(() => setRank((current + 1) % length), [current, length]);

  const pathname = usePathname();
  const onPublicRoute = playerRouteKind(pathname ?? '') === 'public';

  return (
    <LandingVideoProvider value={registry}>
      {children}
      {playlist !== null && onPublicRoute && !failed && (
        // The stage clips the framed player's halo at the page's edges
        // (`.landing-video-stage` in globals.css).
        <div className="landing-video-stage">
          <LandingVideoPlayer
            lng={lng}
            video={playlist[current]}
            rank={current}
            loop={playlist.length === 1}
            // A record for another video, or another list, resumes nothing but the sound.
            resume={resume !== null && resume.video === current ? resume : null}
            startMuted={resume !== null && !resume.sound}
            slot={slot}
            labels={labels}
            onEnded={onEnded}
            onFailed={onFailed}
          />
        </div>
      )}
    </LandingVideoProvider>
  );
}

/** Same videos, same files: a re-fetched list is the list already held. */
function samePlaylist(
  held: LandingVideoDescriptor[] | null,
  next: LandingVideoDescriptor[]
): boolean {
  return held !== null && JSON.stringify(held) === JSON.stringify(next);
}
