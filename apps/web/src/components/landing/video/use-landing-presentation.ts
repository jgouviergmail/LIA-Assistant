/** Abortable same-origin metadata read, owned by the open presentation dialog. */
import { useEffect, useState } from 'react';

import type { LandingVideoDescriptor } from '@/lib/landing/media';
import { readPublicUiJson } from '@/lib/api-client';
import { LANDING_MEDIA_ENDPOINT } from './use-landing-video';

type PresentationState =
  | { status: 'loading' }
  | { status: 'ready'; video: LandingVideoDescriptor }
  | { status: 'unavailable' }
  | { status: 'error' };

interface PresentationResponse {
  presentation?: LandingVideoDescriptor | null;
}

export function useLandingPresentation(request: number): PresentationState {
  const [initialRequest] = useState(request);
  const [snapshot, setSnapshot] = useState<{
    request: number;
    state: PresentationState;
  } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const read = async () => {
      try {
        const endpoint =
          request === initialRequest ? LANDING_MEDIA_ENDPOINT : '/api/landing-media?refresh=1';
        const body = await readPublicUiJson<PresentationResponse>(endpoint, {
          signal: controller.signal,
          timeout: 10_000,
        });
        if (controller.signal.aborted) return;
        setSnapshot({
          request,
          state: body.presentation
            ? { status: 'ready', video: body.presentation }
            : { status: 'unavailable' },
        });
      } catch {
        if (!controller.signal.aborted) setSnapshot({ request, state: { status: 'error' } });
      }
    };
    // A Strict Mode cleanup cancels the read before it reaches the server.
    void Promise.resolve().then(() => {
      if (!controller.signal.aborted) return read();
    });
    return () => controller.abort();
  }, [request, initialRequest]);

  return snapshot?.request === request ? snapshot.state : { status: 'loading' };
}
