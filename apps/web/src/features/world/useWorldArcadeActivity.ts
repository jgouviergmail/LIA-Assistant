'use client';
import { useEffect } from 'react';
import { Gamepad2, LayoutGrid } from 'lucide-react';
import type { WorldActivityEntry } from './useWorldActivityState';
import type { WorldGameClient } from './game-client';
import { CABINET_GAMES } from './game-catalogue';

/** One cleanup owner for Escape, navigation and account teardown. */
export function useWorldArcadeActivity(
  client: WorldGameClient | undefined,
  entry: WorldActivityEntry,
  t: (key: string) => string
) {
  const cabinet = entry.selection === 'world-arcade' ? entry.cabinet : undefined;
  useEffect(
    () => () => {
      if (cabinet) client?.close(cabinet);
    },
    [client, cabinet]
  );
  if (!cabinet) return { cabinet, title: undefined, description: undefined, icon: LayoutGrid };
  return {
    cabinet,
    title: t('world.arcade.games.' + CABINET_GAMES[cabinet] + '.title'),
    description: t('world.arcade.shared'),
    icon: Gamepad2,
  };
}
