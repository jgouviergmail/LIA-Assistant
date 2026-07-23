'use client';

/**
 * useBriefingPreferences — briefing grid visibility + ordering
 * (UXR Lot 5, B4; server-persisted in users.briefing_preferences).
 *
 * GET returns the sanitized view (complete canonical order); PUT is a full
 * replace with optimistic local state and rollback on error. The pure
 * `moveSection` helper implements the keyboard reordering (↑/↓ buttons — the
 * universal path; drag-and-drop is a pointer-only enhancement).
 */

import { useCallback, useState } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import type { BriefingPreferences, BriefingSection } from '@/types/briefing';

/** Immutable move of `name` one step up/down; identity when impossible. */
export function moveSection(
  order: BriefingSection[],
  name: BriefingSection,
  direction: 'up' | 'down'
): BriefingSection[] {
  const index = order.indexOf(name);
  const target = direction === 'up' ? index - 1 : index + 1;
  if (index < 0 || target < 0 || target >= order.length) return order;
  const next = [...order];
  next[index] = next[target];
  next[target] = name;
  return next;
}

/** Immutable move of `name` to `targetIndex` (drag-and-drop enhancement). */
export function reorderTo(
  order: BriefingSection[],
  name: BriefingSection,
  targetIndex: number
): BriefingSection[] {
  const from = order.indexOf(name);
  if (from < 0 || targetIndex < 0 || targetIndex >= order.length || from === targetIndex) {
    return order;
  }
  const next = order.filter(n => n !== name);
  next.splice(targetIndex, 0, name);
  return next;
}

/** Immutable visibility toggle. */
export function toggleHidden(
  hidden: BriefingSection[],
  name: BriefingSection
): BriefingSection[] {
  return hidden.includes(name) ? hidden.filter(n => n !== name) : [...hidden, name];
}

export interface UseBriefingPreferencesReturn {
  preferences: BriefingPreferences | null;
  loading: boolean;
  error: boolean;
  /** Optimistic full replace; rolls back local state on API error. */
  save: (next: BriefingPreferences) => Promise<boolean>;
}

export function useBriefingPreferences(enabled = true): UseBriefingPreferencesReturn {
  const { data, loading, error } = useApiQuery<BriefingPreferences>('/briefing/preferences', {
    componentName: 'useBriefingPreferences',
    enabled,
  });
  // Derived-with-override (no state-sync effect — react-hooks ratchet): the
  // server payload is the base; an optimistic save overrides it locally and
  // rolls back to the pre-save view on error.
  const [override, setOverride] = useState<BriefingPreferences | null>(null);
  const preferences = override ?? data ?? null;

  const { mutate } = useApiMutation<BriefingPreferences, BriefingPreferences>({
    method: 'PUT',
    componentName: 'useBriefingPreferences',
  });

  const save = useCallback(
    async (next: BriefingPreferences): Promise<boolean> => {
      const previous = preferences;
      setOverride(next);
      try {
        await mutate('/briefing/preferences', next);
        return true;
      } catch {
        setOverride(previous);
        return false;
      }
    },
    [preferences, mutate]
  );

  return { preferences, loading, error: !!error, save };
}
