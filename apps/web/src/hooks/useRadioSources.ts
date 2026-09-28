'use client';

/**
 * useRadioSources — every source of the listener's newsroom, and what it holds for them
 * (ADR-324 decision 38).
 *
 * `GET /radio/sources` answers the base sources (ticked or not) and the
 * listener's own sites (running or paused), each with the stories it published
 * within the window and how many the listener never heard, and the totals the
 * station can air. Every change is followed by a fresh read — the counts move
 * with it, and the page never computes them.
 *
 * A site is PREVIEWED first — the API looks for the feed it serves and
 * describes it (title, language, entries) or says why there is none — and only
 * then added; the API looks again when adding (the address is what is sent,
 * never a feed URL the page could have been handed).
 */

import { useCallback } from 'react';

import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { RADIO_ENDPOINTS } from '@/lib/radio/api';
import { sourceLookupRefusalOf, type RadioWrite } from '@/lib/radio/errors';
import type { RadioCustomSource, RadioDiscovery, RadioSources } from '@/lib/radio/types';

interface SourceRequest {
  address: string;
}

interface SourceChange {
  title?: string;
  paused?: boolean;
}

export interface UseRadioSourcesReturn {
  /** The newsroom, counted; null until read (or when the read failed). */
  sources: RadioSources | null;
  /** What looking for a site's feed found, or why the call failed. */
  preview: (address: string) => Promise<RadioWrite<RadioDiscovery>>;
  /** The added site, or why it was not added (a site without a feed, the limit…). */
  add: (address: string) => Promise<RadioWrite<RadioCustomSource>>;
  /** Whether the site was removed. */
  remove: (sourceId: string) => Promise<boolean>;
  /** Whether the site was renamed or paused (or resumed). */
  change: (sourceId: string, change: SourceChange) => Promise<boolean>;
  /** Whether what the listener heard was forgotten. */
  forget: () => Promise<boolean>;
  /** Read the newsroom again (after a base source was ticked or unticked). */
  refresh: () => Promise<void>;
  busy: boolean;
}

const COMPONENT = 'useRadioSources';

export function useRadioSources(): UseRadioSourcesReturn {
  const view = useApiQuery<RadioSources>(RADIO_ENDPOINTS.sources, { componentName: COMPONENT });
  const { refetch } = view;
  const previewing = useApiMutation<SourceRequest, RadioDiscovery>({
    method: 'POST',
    componentName: COMPONENT,
  });
  const adding = useApiMutation<SourceRequest, RadioCustomSource>({
    method: 'POST',
    componentName: COMPONENT,
  });
  const patching = useApiMutation<SourceChange, unknown>({
    method: 'PATCH',
    componentName: COMPONENT,
  });
  const deleting = useApiMutation<undefined, unknown>({
    method: 'DELETE',
    componentName: COMPONENT,
  });
  const { mutate: previewMutate } = previewing;
  const { mutate: addMutate } = adding;
  const { mutate: patchMutate } = patching;
  const { mutate: deleteMutate } = deleting;

  const preview = useCallback(
    async (address: string): Promise<RadioWrite<RadioDiscovery>> => {
      try {
        const found = await previewMutate(RADIO_ENDPOINTS.sourcePreview, { address });
        return found
          ? { ok: true, value: found }
          : { ok: false, refusal: null };
      } catch (error) {
        return { ok: false, refusal: sourceLookupRefusalOf(error) };
      }
    },
    [previewMutate]
  );

  const add = useCallback(
    async (address: string): Promise<RadioWrite<RadioCustomSource>> => {
      try {
        const created = await addMutate(RADIO_ENDPOINTS.sources, { address });
        if (!created) return { ok: false, refusal: null };
        await refetch();
        return { ok: true, value: created };
      } catch (error) {
        return { ok: false, refusal: sourceLookupRefusalOf(error) };
      }
    },
    [addMutate, refetch]
  );

  /** A write, then a fresh read; false when the write failed. */
  const written = useCallback(
    async (write: () => Promise<unknown>): Promise<boolean> => {
      try {
        await write();
      } catch {
        return false;
      }
      await refetch();
      return true;
    },
    [refetch]
  );

  const remove = useCallback(
    (sourceId: string) => written(() => deleteMutate(RADIO_ENDPOINTS.source(sourceId))),
    [deleteMutate, written]
  );
  const change = useCallback(
    (sourceId: string, update: SourceChange) =>
      written(() => patchMutate(RADIO_ENDPOINTS.source(sourceId), update)),
    [patchMutate, written]
  );
  const forget = useCallback(
    () => written(() => deleteMutate(RADIO_ENDPOINTS.heard)),
    [deleteMutate, written]
  );

  return {
    sources: view.data ?? null,
    preview,
    add,
    remove,
    change,
    forget,
    refresh: refetch,
    busy: previewing.loading || adding.loading || patching.loading || deleting.loading,
  };
}
