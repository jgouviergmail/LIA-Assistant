'use client';

/**
 * What a reader must re-read after a writer elsewhere changed it (ADR-300
 * wave 4, owner request 2026-09-19). The query hook holds no cache shared
 * between mounts: the header's `useLiveAvailability` read the live
 * connectors once, at the dashboard layout's mount, so a provider or a model
 * changed in the Live settings kept the old brand on the voice menu until a
 * reload.
 *
 * A writer BUMPS the resource it changed; a reader hands the revision to its
 * query's `deps`. The vocabulary is closed: a misspelled resource is a type
 * error, never a bump nobody follows.
 */

import { create } from 'zustand';

/** The resources a reader may follow — one entry per resource that has a writer elsewhere. */
export type RevisedResource = 'live_connectors';

interface RevisionStore {
  revisions: Record<RevisedResource, number>;
  bump: (resource: RevisedResource) => void;
}

export const useRevisionStore = create<RevisionStore>(set => ({
  revisions: { live_connectors: 0 },
  bump: resource =>
    set(state => ({
      revisions: { ...state.revisions, [resource]: state.revisions[resource] + 1 },
    })),
}));

/** The current revision of a resource: a query dependency that changes on every bump. */
export function useResourceRevision(resource: RevisedResource): number {
  return useRevisionStore(state => state.revisions[resource]);
}

/** Declare that a resource changed: every reader following it re-reads. */
export function bumpRevision(resource: RevisedResource): void {
  useRevisionStore.getState().bump(resource);
}
