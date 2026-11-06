'use client';

/**
 * The selection of a listing (ADR-369), shared by every tool that acts on several.
 *
 * It belongs to ONE listing: another folder, other words or other chips start
 * with nothing selected (derived, never reset by an effect), and Shift ticks
 * every item from the last one ticked.
 */
import { useCallback, useMemo, useState } from 'react';

import { toggleId } from '@/lib/selection';

export interface ListSelection {
  selected: ReadonlySet<string>;
  select: (ids: ReadonlySet<string>) => void;
  /**
   * Ticks an item or takes it back.
   *
   * @param id - The item.
   * @param range - With Shift, the listing's order: every item from the last one
   *   ticked to this one is selected.
   */
  toggle: (id: string, range?: readonly string[]) => void;
}

interface HeldSelection {
  key: string;
  ids: ReadonlySet<string>;
  /** The last item ticked, where a range starts. */
  anchor: string | null;
}

/** @param listingKey - The listing the selection belongs to (its params, serialised). */
export function useListSelection(listingKey: string): ListSelection {
  const [selection, setSelection] = useState<HeldSelection>({
    key: '',
    ids: new Set(),
    anchor: null,
  });
  const selected = useMemo(
    () => (selection.key === listingKey ? selection.ids : new Set<string>()),
    [listingKey, selection]
  );
  const select = useCallback(
    (ids: ReadonlySet<string>) => setSelection({ key: listingKey, ids, anchor: null }),
    [listingKey]
  );
  const toggle = useCallback(
    (id: string, range?: readonly string[]) => {
      const anchor = selection.key === listingKey ? selection.anchor : null;
      const from = range && anchor !== null ? range.indexOf(anchor) : -1;
      const to = range?.indexOf(id) ?? -1;
      const ids =
        range && from >= 0 && to >= 0
          ? new Set([...selected, ...range.slice(Math.min(from, to), Math.max(from, to) + 1)])
          : toggleId(selected, id);
      setSelection({ key: listingKey, ids, anchor: id });
    },
    [listingKey, selected, selection]
  );
  return { selected, select, toggle };
}
