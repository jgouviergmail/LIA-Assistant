'use client';
/**
 * What the board's page knows of its categories (ADR-276).
 *
 * Two sources, kept apart on purpose:
 *
 * - **The board's own lanes** name every category in sight — the reader's and
 *   those of the tickets they hold. Everything the page needs to DRAW or to
 *   OFFER comes from there: the lists that file a ticket, the filter, the name
 *   a held ticket shows. One read, already made, always as fresh as the board.
 * - **The categories list** — exact count per category, the caps the instance
 *   enforces — is what ADMINISTERING them needs, and is read only while the
 *   dialog is open.
 *
 * The shape mirrors `useTicketCreation`: a verb to open, and the dialog to
 * render in the page's tree.
 */
import { useMemo, useState, type ReactNode } from 'react';

import { CategoryManager } from '@/components/workboard/CategoryManager';
import { useAuth } from '@/hooks/useAuth';
import type { UseWorkboardResult } from '@/hooks/useWorkboard';
import { useWorkboardCategories } from '@/hooks/useWorkboardCategories';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { partyLabel, type PeerName } from '@/lib/workboard/display';
import { categoryNamer, laneOptions, ownCategories } from '@/lib/workboard/lanes';
import type { CategoryOption } from '@/types/workboard';

export interface BoardCategories {
  /** The reader's own categories, in order — the lanes their tickets may be filed under. */
  own: CategoryOption[];
  /** Every category the board can be narrowed to; somebody else's says whose it is. */
  lanes: CategoryOption[];
  /** The name of a category of the board, theirs or not. */
  nameOf: (categoryId: string) => string | undefined;
  /** Open the dialog that administers the reader's categories. */
  manage: () => void;
  /** The dialog, to render in the page's tree; false while closed. */
  dialog: ReactNode;
}

export function useBoardCategories({
  lng,
  board,
  peers,
}: {
  lng: Language;
  board: Pick<UseWorkboardResult, 'lanes' | 'refetch'>;
  peers: readonly PeerName[];
}): BoardCategories {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const meId = user?.id;
  const [managing, setManaging] = useState(false);
  const source = useWorkboardCategories(managing);
  const { lanes: boardLanes, refetch } = board;

  const own = useMemo(() => ownCategories(boardLanes, meId), [boardLanes, meId]);
  const nameOf = useMemo(() => categoryNamer(boardLanes), [boardLanes]);
  const lanes = useMemo(
    () =>
      laneOptions(boardLanes, meId, ownerId => {
        const peer = peers.find(connection => connection.peer_id === ownerId);
        return partyLabel(
          peer ? { kind: 'peer', name: peer.peer_display_name } : { kind: 'unknown' },
          t
        );
      }),
    [boardLanes, meId, peers, t]
  );

  return {
    own,
    lanes,
    nameOf,
    manage: () => setManaging(true),
    dialog: managing && (
      <CategoryManager
        open
        source={source}
        onClose={() => setManaging(false)}
        // Creating, renaming, moving or deleting a category changes the lanes
        // themselves: the board is re-read, never patched by guess.
        onChanged={() => void refetch()}
      />
    ),
  };
}
