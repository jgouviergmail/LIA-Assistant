/**
 * The landing video's beat map (ADR-330), served only when the manifest names
 * one and it validates. The section asks for it when the sound goes on — a
 * visitor who never unmutes never downloads it.
 */

import { NextResponse } from 'next/server';

import { parseBeatMap } from '@/lib/landing/beats-schema';
import { resolveMediaFile } from '@/lib/landing/media';
import {
  fetchJsonCached,
  LANDING_MEDIA_TTL_MS,
  loadLandingManifest,
} from '@/lib/landing/media-origin';

export const dynamic = 'force-dynamic';

function notFound(): NextResponse {
  return NextResponse.json({ error: 'no_beats' }, { status: 404 });
}

export async function GET(): Promise<NextResponse> {
  let loaded: Awaited<ReturnType<typeof loadLandingManifest>>;
  try {
    loaded = await loadLandingManifest();
  } catch {
    // Already reported by /api/landing-media, which the page asks first.
    return notFound();
  }
  if (!loaded || loaded.manifest.beats === null) return notFound();
  const map = await fetchJsonCached(
    resolveMediaFile(loaded.baseUrl, loaded.manifest.beats),
    parseBeatMap
  );
  if (!map) return notFound();
  return NextResponse.json(map, {
    headers: {
      'Cache-Control': `public, max-age=${LANDING_MEDIA_TTL_MS / 1000}, stale-while-revalidate=60`,
    },
  });
}
