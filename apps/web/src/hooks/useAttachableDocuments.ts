/**
 * The documents the composer may attach: the `ready` documents of every
 * knowledge space of the account, active or not, searched by name.
 *
 * Imperative fetch rather than `useApiQuery`: the needle changes on every
 * keystroke the search box debounces. `loading` is DERIVED — the resolved
 * page carries the needle it answers, and the hook is loading whenever the
 * current needle is not the one resolved — so no frame ever shows the
 * previous page as the answer to the new needle, and nothing sets state
 * inside the effect. A late answer to an earlier needle is dropped.
 */

'use client';

import { useEffect, useRef, useState } from 'react';

import apiClient from '@/lib/api-client';
import type { AttachableDocument, AttachableDocumentsResponse } from '@/types/rag-spaces';

/** The page the picker asks for — a scroll of fifty names is read at a glance. */
export const ATTACHABLE_PAGE_SIZE = 50;

/** The page last answered, stamped with the needle it answers. */
interface ResolvedPage {
  key: string;
  items: AttachableDocument[];
  total: number;
  error: boolean;
}

export interface AttachableDocumentsState {
  items: AttachableDocument[];
  total: number;
  loading: boolean;
  error: boolean;
}

/**
 * Fetch the attachable documents matching `needle` while `enabled`.
 *
 * @param needle - The name fragment (empty for the whole set).
 * @param enabled - Whether to fetch at all (the dialog is open).
 */
export function useAttachableDocuments(needle: string, enabled: boolean): AttachableDocumentsState {
  const [resolved, setResolved] = useState<ResolvedPage | null>(null);
  const requestRef = useRef(0);
  const key = enabled ? needle.trim() : null;

  useEffect(() => {
    if (key === null) return;
    const request = ++requestRef.current;
    apiClient
      .get<AttachableDocumentsResponse>('/rag-spaces/documents', {
        params: { q: key || undefined, limit: ATTACHABLE_PAGE_SIZE, offset: 0 },
      })
      .then(response => {
        if (request !== requestRef.current) return;
        setResolved({ key, items: response.items, total: response.total, error: false });
      })
      .catch(() => {
        if (request !== requestRef.current) return;
        setResolved({ key, items: [], total: 0, error: true });
      });
  }, [key]);

  const current = resolved !== null && resolved.key === key;
  return {
    items: resolved?.items ?? [],
    total: resolved?.total ?? 0,
    loading: key !== null && !current,
    error: current && resolved.error,
  };
}
