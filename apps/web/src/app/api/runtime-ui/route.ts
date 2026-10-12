import { NextResponse } from 'next/server';
import { normalizeAvatarStyleRolloutId, type RuntimeUiConfig } from '@/lib/runtime-ui';

export const dynamic = 'force-dynamic';

/** Read only the non-secret operator option, at request time (ADR-342). */
export function GET(): NextResponse<RuntimeUiConfig> {
  return NextResponse.json(
    { avatarStyleRolloutId: normalizeAvatarStyleRolloutId(process.env.AVATAR_STYLE_ROLLOUT_ID) },
    { headers: { 'Cache-Control': 'no-store' } }
  );
}
