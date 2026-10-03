/**
 * The landing video's descriptor, resolved at request time (ADR-330).
 *
 * The landing is prebuilt and host-neutral, so it cannot know at build time
 * whether this deployment shows a video or where it is. The section asks here
 * once when it mounts: `{ video: null }` means no section, a descriptor means
 * poster, renditions and credit with absolute URLs under the operator's
 * media directory (`LANDING_MEDIA_BASE_URL`), and `next` the videos that
 * follow it, in playing order (empty when the manifest names one). A down
 * origin, an invalid manifest or a malformed variable all answer "no video"
 * — the page never fails on its illustration.
 */

import { NextResponse } from 'next/server';

import { resolveLandingPlaylist } from '@/lib/landing/media';
import { LANDING_MEDIA_TTL_MS, loadLandingManifest } from '@/lib/landing/media-origin';

export const dynamic = 'force-dynamic';

function noVideo(): NextResponse {
  return NextResponse.json({ video: null }, { headers: { 'Cache-Control': 'public, max-age=60' } });
}

export async function GET(): Promise<NextResponse> {
  let loaded: Awaited<ReturnType<typeof loadLandingManifest>>;
  try {
    loaded = await loadLandingManifest();
  } catch (error) {
    // A configured-but-wrong origin: say it in the server log, once per
    // request, rather than let the operator wonder why there is no video.
    console.error(
      '[landing-media] LANDING_MEDIA_BASE_URL is not usable:',
      error instanceof Error ? error.message : String(error)
    );
    return noVideo();
  }
  if (!loaded) return noVideo();
  const [video, ...next] = resolveLandingPlaylist(loaded.manifest, loaded.baseUrl);
  return NextResponse.json(
    { video, next },
    {
      headers: {
        'Cache-Control': `public, max-age=${LANDING_MEDIA_TTL_MS / 1000}, stale-while-revalidate=60`,
      },
    }
  );
}
