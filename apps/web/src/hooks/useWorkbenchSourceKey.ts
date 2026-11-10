'use client';

import { usePathname, useSearchParams } from 'next/navigation';
import { cardSourceHeaders, CARD_SOURCE_HEADER } from '@/lib/workbench/card-source';

/** A same-id navigation under a new card source is a new read, not cached screen state. */
export function useWorkbenchSourceKey(endpoint: string | null): string {
  const pathname = usePathname();
  const params = useSearchParams();
  return (
    cardSourceHeaders(endpoint ?? '', { pathname, search: params.toString() })[
      CARD_SOURCE_HEADER
    ] ?? ''
  );
}
