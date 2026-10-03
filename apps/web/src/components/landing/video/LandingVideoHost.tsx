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
 */

import { usePathname } from 'next/navigation';
import { useCallback, useMemo, useState, type ReactNode } from 'react';

import type { LandingVideoDescriptor } from '@/lib/landing/media';
import { playerRouteKind } from '@/lib/landing/player-routes';

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
  const [video, setVideo] = useState<LandingVideoDescriptor | null>(null);
  const [failed, setFailed] = useState(false);

  const registerSlot = useCallback((next: LandingVideoSlot) => {
    setSlot(next);
    setVideo(next.video);
    return () => setSlot(current => (current === next ? null : current));
  }, []);
  const registry = useMemo<LandingVideoRegistry>(
    () => ({ failed, registerSlot }),
    [failed, registerSlot]
  );
  const onFailed = useCallback(() => setFailed(true), []);

  const pathname = usePathname();
  const onPublicRoute = playerRouteKind(pathname ?? '') === 'public';

  return (
    <LandingVideoProvider value={registry}>
      {children}
      {video !== null && onPublicRoute && !failed && (
        // The stage clips the framed player's halo at the page's edges
        // (`.landing-video-stage` in globals.css).
        <div className="landing-video-stage">
          <LandingVideoPlayer
            lng={lng}
            video={video}
            slot={slot}
            labels={labels}
            onFailed={onFailed}
          />
        </div>
      )}
    </LandingVideoProvider>
  );
}
