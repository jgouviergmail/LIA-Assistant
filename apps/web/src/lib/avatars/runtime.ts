import { useSyncExternalStore } from 'react';
import type { AvatarEngine } from './engine';
import type { AvatarConnectionState } from './types';

interface AvatarRuntime {
  engine: AvatarEngine | null;
  state: AvatarConnectionState;
  present: boolean;
}
const EMPTY: AvatarRuntime = { engine: null, state: 'off', present: false };
let snapshot = EMPTY;
let unsubscribe: (() => void) | null = null;
const listeners = new Set<() => void>();
function publish(engine: AvatarEngine | null): void {
  snapshot = engine ? { engine, state: engine.state, present: engine.present } : EMPTY;
  for (const listener of listeners) listener();
}
/** Memory only. Neither credentials, provider tokens nor media enter a store. */
export function mountAvatarEngine(engine: AvatarEngine): () => void {
  unsubscribe?.();
  publish(engine);
  unsubscribe = engine.subscribe(() => publish(engine));
  return () => {
    if (snapshot.engine !== engine) return;
    unsubscribe?.();
    unsubscribe = null;
    publish(null);
  };
}
export function avatarEngine(): AvatarEngine | null {
  return snapshot.engine;
}
export function stopAvatarCommentsForChatFailure(): void {
  snapshot.engine?.chatFailed();
}
export function useAvatarRuntime(): AvatarRuntime {
  return useSyncExternalStore(
    listener => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => snapshot,
    () => EMPTY
  );
}

/** Call before removing the encrypted key so remote closure can still be verified. */
export async function stopAvatarForConnectorChange(): Promise<void> {
  const engine = avatarEngine();
  engine?.setDemand(null);
  // The owner keeps its conservative lease if the provider cannot confirm closure.
  await engine?.settled();
}

/**
 * Bound on the wait for the face before a Live speaks. The engine's own
 * connection deadline (`connect_timeout_seconds`, read from the API) normally
 * settles it first, as `ready` or `unavailable`.
 */
export const AVATAR_LIVE_START_WAIT_MS = 20_000;

/**
 * Resolve once the account's avatar can carry the Live voice — ready — or has
 * given up (unavailable, no demand), or at the bound. A Live whose provider
 * connected while the face was still connecting spoke its first reply through
 * the local player (owner decision 2026-10-05: the face is loaded before the
 * Live speaks). Without an avatar demand there is nothing to wait for.
 */
export function awaitAvatarReady(limitMs = AVATAR_LIVE_START_WAIT_MS): Promise<void> {
  const engine = avatarEngine();
  if (!engine?.present) return Promise.resolve();
  return new Promise(resolve => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      unsubscribe();
      clearTimeout(timer);
      resolve();
    };
    const check = () => {
      if (!engine.present || engine.ready || engine.state === 'unavailable') finish();
    };
    const unsubscribe = engine.subscribe(check);
    const timer = setTimeout(finish, limitMs);
    check();
  });
}
