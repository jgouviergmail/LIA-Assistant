'use client';

/**
 * The state both brick maps share: the selected brick (the page's hash), the
 * brick under the pointer, the isolated family, the search, and the journey
 * player — resolved into the ONE highlight both maps draw (`computeHighlight`).
 * Any new focus (a selection, a family, a search) stops the journey, as the
 * reader has moved on.
 */

import { useMemo, useState } from 'react';

import { computeHighlight, matchBricks, type Highlight } from '@/lib/maps/highlight';
import type { BrickMapView, BrickView } from '@/lib/maps/types';
import { setMapHash, useMapHash } from '@/lib/maps/use-map-hash';
import { useFlowPlayer, type FlowPlayer } from '@/lib/maps/use-flow-player';

export interface BrickMapState {
  highlight: Highlight;
  player: FlowPlayer;
  selected: BrickView | null;
  family: string | null;
  query: string;
  /** Bricks matching the search, or null when nothing is searched. */
  matches: ReadonlySet<string> | null;
  hover: (id: string | null) => void;
  select: (id: string) => void;
  close: () => void;
  toggleFamily: (id: string) => void;
  search: (value: string) => void;
  /** Enter in the search box: open the first match. */
  openFirstMatch: () => void;
  playFlow: (id: string) => void;
}

/**
 * @param map - The map being shown.
 * @param playerRef - Where the journey player sits, so a journey started from a
 *   card or a brick's detail can bring it into view. Owned by the component: a
 *   ref travelling inside the returned state would make every read of that
 *   state a ref read during render.
 */
export function useBrickMap(
  map: BrickMapView,
  playerRef: React.RefObject<HTMLDivElement | null>
): BrickMapState {
  const hash = useMapHash();
  const [hovered, setHovered] = useState<string | null>(null);
  const [family, setFamily] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const player = useFlowPlayer(map.flows);

  const selected = useMemo(() => map.bricks.find(b => b.id === hash) ?? null, [map.bricks, hash]);
  const matchList = useMemo(
    () => matchBricks(map.bricks, map.families, query),
    [map.bricks, map.families, query]
  );
  const matches = useMemo(() => (query.trim() ? new Set(matchList) : null), [matchList, query]);
  const highlight = useMemo(
    () =>
      computeHighlight({
        bricks: map.bricks,
        flow: player.active,
        hovered,
        selected: selected?.id ?? null,
        family,
        matches,
      }),
    [map.bricks, player.active, hovered, selected, family, matches]
  );

  const select = (id: string) => {
    player.clear();
    setMapHash(id);
  };

  return {
    highlight,
    player,
    selected,
    family,
    query,
    matches,
    hover: setHovered,
    select,
    close: () => setMapHash(null),
    toggleFamily: id => {
      player.clear();
      setFamily(current => (current === id ? null : id));
    },
    search: value => {
      player.clear();
      setQuery(value);
    },
    openFirstMatch: () => {
      if (matchList[0]) select(matchList[0]);
    },
    playFlow: id => {
      setMapHash(null);
      player.playById(id);
      playerRef.current?.scrollIntoView({ block: 'nearest' });
    },
  };
}
