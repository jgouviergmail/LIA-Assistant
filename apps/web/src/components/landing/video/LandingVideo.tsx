'use client';

/**
 * The landing video's section (ADR-330, amended): the operator-hosted clip
 * between the hero and the promise. The section exists only when the server
 * answers with a descriptor — the pages are prebuilt, so nothing here is known
 * before the browser asks — and it holds no `<video>` of its own: it draws an
 * EMPTY frame at the clip's aspect ratio, the caption under it, and hands the
 * frame to the host the layout mounts (`LandingVideoHost`), which keeps the
 * one element of the visit and positions it over the frame.
 */

import { useEffect, useRef } from 'react';

import type { LandingVideoDescriptor } from '@/lib/landing/media';

import { LandingVideoCaption } from './LandingVideoCaption';
import { useLandingVideoRegistry, type LandingVideoRegistry } from './landing-video-context';
import { useLandingMedia } from './use-landing-video';

export interface LandingVideoSlotLabels {
  ariaLabel: string;
  aiDisclosure: string;
  /** Ends with the separator the language wants before the author (a space, a full-width colon). */
  creditPrefix: string;
  externalLink: string;
}

export function LandingVideo({ labels }: { labels: LandingVideoSlotLabels }) {
  const media = useLandingMedia();
  const registry = useLandingVideoRegistry();
  if (media.status !== 'ready' || registry?.failed) return null;
  return <LandingVideoSlot video={media.video} labels={labels} registry={registry} />;
}

function LandingVideoSlot({
  video,
  labels,
  registry,
}: {
  video: LandingVideoDescriptor;
  labels: LandingVideoSlotLabels;
  registry: LandingVideoRegistry | null;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const registerSlot = registry?.registerSlot;

  useEffect(() => {
    const element = frameRef.current;
    if (!element || !registerSlot) return;
    return registerSlot({ element, video });
  }, [registerSlot, video]);

  const [ratioW, ratioH] = video.aspectRatio;

  return (
    <section
      id="video"
      aria-label={labels.ariaLabel}
      className="landing-section relative scroll-mt-24 py-10 sm:py-14"
      data-testid="landing-video"
    >
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <div
          ref={frameRef}
          className="landing-video-slot relative overflow-hidden rounded-2xl border border-border/70 bg-background/80 shadow-sm"
          style={{ aspectRatio: `${ratioW} / ${ratioH}` }}
        />
        <LandingVideoCaption video={video} labels={labels} />
      </div>
    </section>
  );
}
