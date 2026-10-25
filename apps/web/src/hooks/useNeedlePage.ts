/**
 * One page of a list searched by name, and its EXACT total (ADR-185).
 *
 * The composer's pickers list what the person holds — knowledge documents,
 * kept answers, generated files — and search them on every keystroke the box
 * debounces. Imperative fetch rather than `useApiQuery` for that reason.
 * `loading` is DERIVED: the resolved page carries the key it answers, and the
 * hook is loading whenever the current key is not the one resolved — so no
 * frame ever shows the previous page as the answer to the new needle, and
 * nothing sets state inside the effect. A late answer to an earlier needle is
 * dropped.
 */

'use client';

import { useEffect, useRef, useState } from 'react';

import apiClient from '@/lib/api-client';

/** The page a picker asks for — a scroll of fifty names is read at a glance. */
export const NEEDLE_PAGE_SIZE = 50;

interface ResolvedPage<T> {
  key: string;
  items: T[];
  total: number;
  error: boolean;
}

export interface NeedlePageState<T> {
  items: T[];
  total: number;
  loading: boolean;
  error: boolean;
}

/**
 * Fetch the page of `path` matching `needle` while `enabled`.
 *
 * @param path - The list endpoint; it answers `{ items, total }` and reads `q`.
 * @param needle - The name fragment (empty for the whole set).
 * @param enabled - Whether to fetch at all (the dialog is open).
 * @param filter - Fixed params of the list (a gallery family), part of the key.
 */
export function useNeedlePage<T>(
  path: string,
  needle: string,
  enabled: boolean,
  filter?: Readonly<Record<string, string>>
): NeedlePageState<T> {
  const [resolved, setResolved] = useState<ResolvedPage<T> | null>(null);
  const requestRef = useRef(0);
  const q = needle.trim();
  const filterKey = filter ? JSON.stringify(filter) : '';
  const key = enabled ? `${path}|${filterKey}|${q}` : null;

  useEffect(() => {
    if (key === null) return;
    const request = ++requestRef.current;
    const fixed = filterKey ? (JSON.parse(filterKey) as Record<string, string>) : {};
    apiClient
      .get<{ items: T[]; total: number }>(path, {
        params: { ...fixed, q: q || undefined, limit: NEEDLE_PAGE_SIZE, offset: 0 },
      })
      .then(response => {
        if (request !== requestRef.current) return;
        setResolved({ key, items: response.items, total: response.total, error: false });
      })
      .catch(() => {
        if (request !== requestRef.current) return;
        setResolved({ key, items: [], total: 0, error: true });
      });
  }, [key, path, q, filterKey]);

  const current = resolved !== null && resolved.key === key;
  return {
    items: resolved?.items ?? [],
    total: resolved?.total ?? 0,
    loading: key !== null && !current,
    error: current && resolved.error,
  };
}
