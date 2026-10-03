'use client';

/**
 * The seam between the landing's section and the player the layout owns
 * (ADR-330, amended): the section hands its FRAME over, the host positions the
 * one `<video>` element of the visit over it. Inert outside the host — the
 * section then draws its frame and registers nowhere.
 */

import { createContext, useContext } from 'react';

import type { LandingVideoDescriptor } from '@/lib/landing/media';

export interface LandingVideoSlot {
  /** The empty frame on the page, at the first video's aspect ratio. */
  element: HTMLElement;
  /** The videos in playing order, never empty: played one after the other, then again. */
  playlist: LandingVideoDescriptor[];
}

export interface LandingVideoRegistry {
  /** The browser could play no rendition: the section hides itself too. */
  failed: boolean;
  /** The rank, in playing order, of the video the player holds — its credit is the caption's. */
  current: number;
  /** Hand the landing's frame to the host; the returned function releases it. */
  registerSlot(slot: LandingVideoSlot): () => void;
}

const LandingVideoContext = createContext<LandingVideoRegistry | null>(null);

export const LandingVideoProvider = LandingVideoContext.Provider;

/** The host's registry, or `null` where no host is mounted. */
export function useLandingVideoRegistry(): LandingVideoRegistry | null {
  return useContext(LandingVideoContext);
}
