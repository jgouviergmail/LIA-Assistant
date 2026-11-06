'use client';

/**
 * What can be seen of a document, read through the API (ADR-369, lot 14).
 *
 * A read that starts costs a transfer the server does not take back when the page drops it, so
 * it starts once the page has settled: Strict Mode's first effect and a document only passed over
 * read nothing. Loading is derived from the key, so another document never shows the previous one
 * as its answer; a read under way is dropped when another takes its place, and an image's blob
 * leaves with it. `none` says there is nothing to show of the document, the caller says it or
 * stays silent; `failed` says the read did not end, and `retry` reads again.
 */
import { useCallback, useEffect, useState } from 'react';

import type { QueryParamValue } from '@/lib/api-client';
import { getApiErrorFields } from '@/lib/api-error';
import { workbenchRefusal, type WorkbenchRefusal } from '@/lib/workbench/errors';
import { paramsOf, serialiseParams } from '@/lib/workbench/params';
import { shownOf, type Shown } from '@/lib/workbench/shown';

export type ShownState =
  | { kind: 'loading' }
  | { kind: 'none' }
  | { kind: 'failed'; refusal: WorkbenchRefusal | null }
  | Shown;

export interface ShownRead {
  state: ShownState;
  /** Reads the document again. */
  retry: () => void;
}

const LOADING: ShownState = { kind: 'loading' };
/** How long a document stays chosen before it is read. */
const SETTLE_MS = 150;
/** What the API answers of a document nothing can show. */
const NOTHING_TO_SHOW = 'not_supported_by_provider';

function failureOf(error: unknown): ShownState {
  return getApiErrorFields(error)?.code === NOTHING_TO_SHOW
    ? { kind: 'none' }
    : { kind: 'failed', refusal: workbenchRefusal(error) };
}

/**
 * @param path - Where it is read; null reads nothing.
 * @param params - What names it; part of the key.
 * @returns What is known of it so far, and how to read it again.
 */
export function useShownDocument(
  path: string | null,
  params: Readonly<Record<string, QueryParamValue>>
): ShownRead {
  const serialised = serialiseParams(params);
  const [attempt, setAttempt] = useState(0);
  const key = `${path}:${serialised}:${attempt}`;
  const [read, setRead] = useState<{ key: string; state: ShownState } | null>(null);

  useEffect(() => {
    if (path === null) return;
    const stop = new AbortController();
    const asked = `${path}:${serialised}:${attempt}`;
    let url: string | null = null;
    const start = window.setTimeout(() => {
      shownOf(path, paramsOf(serialised), stop.signal).then(
        state => {
          if (state.kind === 'image') url = state.url;
          if (stop.signal.aborted) {
            if (url) URL.revokeObjectURL(url);
            return;
          }
          setRead({ key: asked, state });
        },
        (error: unknown) => {
          if (!stop.signal.aborted) setRead({ key: asked, state: failureOf(error) });
        }
      );
    }, SETTLE_MS);
    return () => {
      window.clearTimeout(start);
      stop.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [path, serialised, attempt]);

  const retry = useCallback(() => setAttempt(count => count + 1), []);
  return { state: read?.key === key ? read.state : LOADING, retry };
}
