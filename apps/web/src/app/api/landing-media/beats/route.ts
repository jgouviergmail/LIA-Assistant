/**
 * A landing video's beat map (ADR-330), served only when the manifest names
 * one and it validates. The section asks for it when the sound goes on — a
 * visitor who never unmutes never downloads it — naming the video by its
 * rank in playing order (`?video=N`, the first when absent).
 */

import { NextResponse } from 'next/server';

import { parseBeatMap } from '@/lib/landing/beats-schema';
import { beatsFileAt, LANDING_MEDIA_MAX_NEXT, resolveMediaFile } from '@/lib/landing/media';
import {
  fetchJsonCached,
  LANDING_MEDIA_TTL_MS,
  loadLandingManifest,
} from '@/lib/landing/media-origin';

export const dynamic = 'force-dynamic';

function notFound(): NextResponse {
  return NextResponse.json({ error: 'no_beats' }, { status: 404 });
}

/** The rank asked for: absent is the first video, anything but a small integer is none. */
function rankOf(request: Request): number | null {
  const raw = new URL(request.url).searchParams.get('video');
  if (raw === null) return 0;
  if (!/^\d{1,2}$/.test(raw)) return null;
  const rank = Number(raw);
  return rank <= LANDING_MEDIA_MAX_NEXT ? rank : null;
}

export async function GET(request: Request): Promise<NextResponse> {
  const rank = rankOf(request);
  if (rank === null) return notFound();
  let loaded: Awaited<ReturnType<typeof loadLandingManifest>>;
  try {
    loaded = await loadLandingManifest();
  } catch {
    // Already reported by /api/landing-media, which the page asks first.
    return notFound();
  }
  const beats = loaded ? beatsFileAt(loaded.manifest, rank) : null;
  if (!loaded || beats === null) return notFound();
  const map = await fetchJsonCached(resolveMediaFile(loaded.baseUrl, beats), parseBeatMap);
  if (!map) return notFound();
  return NextResponse.json(map, {
    headers: {
      'Cache-Control': `public, max-age=${LANDING_MEDIA_TTL_MS / 1000}, stale-while-revalidate=60`,
    },
  });
}
