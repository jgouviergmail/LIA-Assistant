'use client';
/** Durable native aggregates; asset reads start only after an invalidation/gap. */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useApplicationAccountQuery } from '@/hooks/useApplicationAccountQuery';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import {
  subscribeApplicationResource,
  type ApplicationResource,
} from '@/lib/application-resources';
import {
  readResourceSignal,
  UNKNOWN_RESOURCE,
  type ResourceSignal,
} from './private-signal-projection';

/** A displayed aggregate and the invalidation revision its answer belongs to (0 = none yet). */
export interface ShownResource extends ResourceSignal {
  revision: number;
}
interface Answer {
  ownerId: string;
  revision: number;
  /** The read's payload, or null when the latest read failed. */
  data: unknown;
}

function useResourceRevision(ownerId: string, resource: ApplicationResource) {
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const [state, setState] = useState({ ownerId, revision: 0 });
  const revision = state.ownerId === ownerId ? state.revision : 0;
  const invalidate = useCallback(() => {
    if (!isCurrent()) return;
    setState(previous => ({
      ownerId,
      revision: previous.ownerId === ownerId ? (previous.revision % (2 ** 31 - 1)) + 1 : 1,
    }));
  }, [ownerId, isCurrent]);
  useEffect(
    () => subscribeApplicationResource(ownerId, resource, invalidate),
    [ownerId, resource, invalidate]
  );
  return { revision, invalidate };
}
/**
 * A re-read keeps the marker on screen until its answer lands (refresh in place); only a
 * read that fails withdraws it, and a later success replaces that failure in turn.
 */
function useResourceCount(
  ownerId: string,
  endpoint: string,
  enabled: boolean,
  revision: number,
  collection: 'items' | 'tickets',
  params?: Record<string, number>
): ShownResource {
  const [answer, setAnswer] = useState<Answer | null>(null);
  const onData = useCallback(
    (data: unknown) => setAnswer({ ownerId, revision, data }),
    [ownerId, revision]
  );
  const query = useApplicationAccountQuery<unknown>(
    endpoint,
    'World.objectSignal',
    enabled,
    onData,
    { params, deps: [revision] }
  );
  if (query.error && !(answer?.ownerId === ownerId && answer.data === null))
    setAnswer({ ownerId, revision, data: null });
  const shown = answer?.ownerId === ownerId ? answer : null;
  return useMemo(
    () =>
      shown
        ? { ...readResourceSignal(shown.data, collection), revision: shown.revision }
        : { ...UNKNOWN_RESOURCE, revision: 0 },
    [shown, collection]
  );
}
export function useWorldSignalReads(
  ownerId: string,
  enabled: boolean,
  workboard: boolean,
  assets: boolean
) {
  const { revision: boardRevision, invalidate: invalidateBoard } = useResourceRevision(
    ownerId,
    'workboard'
  );
  const { revision: galleryRevision, invalidate: invalidateGallery } = useResourceRevision(
    ownerId,
    'generated_assets'
  );
  const needsMe = useResourceCount(
    ownerId,
    '/workboard/needs-me',
    enabled && workboard,
    boardRevision,
    'tickets',
    { limit: 1, offset: 0 }
  );
  const readAssets = enabled && assets && galleryRevision > 0;
  const images = useResourceCount(
    ownerId,
    '/generated-assets?family=images&limit=1',
    readAssets,
    galleryRevision,
    'items'
  );
  const documents = useResourceCount(
    ownerId,
    '/generated-assets?family=documents&limit=1',
    readAssets,
    galleryRevision,
    'items'
  );
  const screenshots = useResourceCount(
    ownerId,
    '/generated-assets?family=screenshots&limit=1',
    readAssets,
    galleryRevision,
    'items'
  );
  const refreshDurable = useCallback(() => {
    invalidateBoard();
    invalidateGallery();
  }, [invalidateBoard, invalidateGallery]);
  // An acknowledgment holds while the gallery still shows the answers it acknowledged.
  const shownGallery = Math.min(images.revision, documents.revision, screenshots.revision);
  return useMemo(
    () => ({
      workboard: needsMe,
      images,
      documents,
      screenshots,
      galleryRevision: shownGallery,
      refreshDurable,
    }),
    [needsMe, images, documents, screenshots, shownGallery, refreshDurable]
  );
}
