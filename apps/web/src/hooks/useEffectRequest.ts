'use client';

import { useCallback, useEffect, useRef } from 'react';

/** One effect lifetime of a request, and the read currently in flight inside it. */
interface RequestScope<T> {
  request: (signal: AbortSignal) => T | Promise<T>;
  lifetime: AbortController;
  read: AbortController | null;
}

/** Supersede the read in flight: every read of a lifetime gets a signal of its own. */
function beginRead<T>(scope: RequestScope<T>): AbortSignal {
  scope.read?.abort();
  const read = new AbortController();
  scope.read = read;
  return AbortSignal.any([scope.lifetime.signal, read.signal]);
}

/**
 * Start external IO after effect setup/cleanup, like useApiQuery. Strict Mode
 * and immediate unmounts cancel an unsent request. Readers must honour the
 * supplied signal before committing a response, and hand it to their
 * transport; errors belong to the reader.
 *
 * Returns `rerun`, the manual read (a retry, a re-read after a change). Every
 * read — the automatic one and each rerun — belongs to one generation: it
 * receives its own signal, a newer read aborts the older one, and cleanup
 * aborts whichever is in flight, so a late answer can neither overwrite the
 * newer one nor end its loading state. A retained `rerun` of a request that is
 * no longer current (its inputs changed, the component unmounted) sends
 * nothing and resolves `undefined`.
 */
export function useEffectRequest<T>(
  request: (signal: AbortSignal) => T | Promise<T>
): () => Promise<T | undefined> {
  const active = useRef<RequestScope<T> | null>(null);
  useEffect(() => {
    const scope: RequestScope<T> = { request, lifetime: new AbortController(), read: null };
    active.current = scope;
    queueMicrotask(() => {
      if (!scope.lifetime.signal.aborted) void request(beginRead(scope));
    });
    return () => {
      scope.lifetime.abort();
      if (active.current === scope) active.current = null;
    };
  }, [request]);
  return useCallback(async () => {
    const scope = active.current;
    if (scope?.request !== request || scope.lifetime.signal.aborted) return undefined;
    return request(beginRead(scope));
  }, [request]);
}
