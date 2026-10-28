'use client';
import { useSyncExternalStore } from 'react';
import type { WorldGameClient } from './game-client';
/** The arcade panel's own subscription; nothing above it re-renders on a game publish. */
export function useWorldArcade(client: WorldGameClient) {
  return useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
}
