'use client';

/**
 * PWA share-target receiver (UXR Lot 9, A6 — text/URL only; file sharing is
 * deliberately deferred, arbitration 8b). Registered in the localized
 * manifests as a GET share_target: the OS share sheet lands here with
 * title/text/url params, which are composed into a chat draft and handed to
 * the existing `?draft=` prefill rail — NEVER auto-sent.
 *
 * Known limitation (documented): an unauthenticated share loses the draft
 * across the login redirect (the 401 path does not carry a returnTo) —
 * sharing is a warm-user feature.
 */

import { useEffect } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';

import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { CHAT_INPUT_MAX_LENGTH } from '@/lib/constants';

/** Compose the shared parts into one draft, clamped at the input cap. */
export function composeShareDraft(
  title: string | null,
  text: string | null,
  url: string | null
): string {
  return [title, text, url]
    .map(part => part?.trim())
    .filter((part): part is string => !!part)
    .join('\n')
    .slice(0, CHAT_INPUT_MAX_LENGTH);
}

export default function SharePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const params = useParams<{ lng: string }>();

  useEffect(() => {
    const draft = composeShareDraft(
      searchParams?.get('title') ?? null,
      searchParams?.get('text') ?? null,
      searchParams?.get('url') ?? null
    );
    const lng = params?.lng || 'fr';
    const target = draft
      ? `/${lng}/dashboard/chat?draft=${encodeURIComponent(draft)}`
      : `/${lng}/dashboard/chat`;
    router.replace(target);
  }, [router, searchParams, params]);

  return (
    <div className="min-h-screen flex items-center justify-center" role="status" aria-live="polite">
      <LoadingSpinner size="xl" />
    </div>
  );
}
