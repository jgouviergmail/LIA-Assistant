/**
 * useJournalPortrait — light read-only access to the compiled portrait (QW-10).
 *
 * The full `useJournals` hook fetches entries + settings + themes; surfaces
 * that only need the "How LIA sees you" portrait (settings shortcut,
 * dashboard hint) use this one instead — a single GET, gateable via
 * `enabled` (e.g. on the `journals_enabled` feature flag) so a disabled
 * feature never even fires the request.
 */

import { useApiQuery } from '@/hooks/useApiQuery';
import type { JournalPortrait } from '@/hooks/useJournals';

export interface UseJournalPortraitReturn {
  portrait: JournalPortrait | null;
  /** True when a compiled portrait exists (full or brief). */
  hasPortrait: boolean;
  loading: boolean;
}

export function useJournalPortrait(enabled = true): UseJournalPortraitReturn {
  const { data, loading } = useApiQuery<JournalPortrait>('/journals/portrait', {
    componentName: 'useJournalPortrait',
    enabled,
  });

  // A 404 (feature flag off / no conversation) resolves to a null portrait —
  // callers render nothing, never an error state (discoverability is
  // best-effort by design).
  const portrait = data ?? null;
  return {
    portrait,
    hasPortrait: Boolean(portrait?.full || portrait?.brief),
    loading,
  };
}
